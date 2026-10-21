"""Check 5 (guide 12.6): OneMap terms, rate limit, token and a 20-block geocoding sample.

The token is read only from the environment variable ONEMAP_TOKEN and is sent only as the Authorization header. It is never
printed, logged or written; only its expiry time (decoded from the JWT payload, no other claim) is reported.
At most 30 calls to onemap.gov.sg in total, counted across runs in .cache/check5_calls.json (page fetches count too),
with a pause between calls. Run from the repo root, one stage at a time:
  .venv\\Scripts\\python scripts/checks/check5_onemap.py terms|token|geocode|report
"""
import base64
import csv
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from _common import SGT

CAP = 30
PAUSE = 3.0
CACHE = Path(".cache/check5")
COUNTER = CACHE / "calls.json"
STATIC = Path("../coolcheck-data/static")
HDB_CSV = STATIC / "hdb_property_information/d_17f5382f26140b1fdae0ba2ef6239d2f.csv"
PA_FILE = STATIC / "ura_mp2019_planning_area_boundary/d_4765db0e87b9c86336792efe8a1f7a66.geojson"
SEARCH = "https://www.onemap.gov.sg/api/common/elastic/search"
TERMS_PAGES = ["https://www.onemap.gov.sg/legal/termsofuse", "https://www.onemap.gov.sg/apidocs/"]
UA = {"User-Agent": "coolcheck-check"}


def calls_used():
    return json.loads(COUNTER.read_text())["n"] if COUNTER.exists() else 0


def get(url, **kw):
    """One counted, paused GET. Raises if the 30-call cap would be passed."""
    n = calls_used()
    if n >= CAP:
        raise SystemExit(f"call cap of {CAP} reached; stopping")
    CACHE.mkdir(parents=True, exist_ok=True)
    COUNTER.write_text(json.dumps({"n": n + 1}))
    if n:
        time.sleep(PAUSE)
    return requests.get(url, timeout=30, **kw)


def token_headers():
    t = os.environ.get("ONEMAP_TOKEN")
    if not t:
        raise SystemExit("ONEMAP_TOKEN is not set; stopping")
    return {**UA, "Authorization": t}


def stage_terms():
    out = {}
    for u in TERMS_PAGES:
        r = get(u, headers=UA)
        text = re.sub(r"\s+", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", " ", r.text, flags=re.S | re.I))
        hits = [m.group(0) for m in re.finditer(r".{0,160}(rate limit|per minute|requests? per|calls? per|terms of use|licen[cs]e).{0,200}", text, flags=re.I)]
        out[u] = {"status": r.status_code, "content_type": r.headers.get("content-type"), "html_bytes": len(r.text),
                  "visible_text_chars": len(text), "hits": hits[:8], "head": text[:300]}
    (CACHE / "terms.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1)[:6000])


def stage_token():
    h = token_headers()
    t = h["Authorization"]
    exp = None
    try:
        payload = t.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        exp = datetime.fromtimestamp(claims["exp"], timezone.utc).astimezone(SGT).strftime("%Y-%m-%d %H:%M SGT")
    except Exception as e:
        print("could not decode expiry:", type(e).__name__)
    print("token expiry (from JWT exp claim):", exp, "| now:", datetime.now(SGT).strftime("%Y-%m-%d %H:%M SGT"))


ABBR = {"ST": "STREET", "AVE": "AVENUE", "RD": "ROAD", "DR": "DRIVE", "CL": "CLOSE", "CRES": "CRESCENT", "NTH": "NORTH",
        "STH": "SOUTH", "JLN": "JALAN", "CTRL": "CENTRAL", "BT": "BUKIT", "LOR": "LORONG", "TER": "TERRACE", "PL": "PLACE",
        "GDNS": "GARDENS", "HTS": "HEIGHTS", "PK": "PARK", "UPP": "UPPER", "TG": "TANJONG", "KG": "KAMPONG", "CTR": "CENTRE"}


def norm_road(s):
    """Expand HDB road abbreviations to OneMap's spelling before comparing."""
    return " ".join(ABBR.get(w, w) for w in s.upper().split())


def pick_blocks(n=20):
    with HDB_CSV.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["residential"] == "Y" and int(r["total_dwelling_units"] or 0) > 0]
    rng = random.Random(0)
    by_town = {}
    for r in rows:
        by_town.setdefault(r["bldg_contract_town"], []).append(r)
    towns = sorted(by_town)
    rng.shuffle(towns)
    return [rng.choice(by_town[t]) for t in towns[:n]]


def point_in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def planning_area(x, y, features):
    for ft in features:
        g = ft["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for poly in polys:
            if point_in_ring(x, y, poly[0]) and not any(point_in_ring(x, y, h) for h in poly[1:]):
                return ft["properties"]["PLN_AREA_N"]
    return None


def stage_geocode(limit=20):
    h = token_headers()
    feats = json.loads(PA_FILE.read_text(encoding="utf-8"))["features"]
    blocks = pick_blocks()[:limit]
    results, headers_seen = [], {}
    for b in blocks:
        q = f"{b['blk_no']} {b['street']}"
        r = get(SEARCH, headers=h, params={"searchVal": q, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1})
        for k, v in r.headers.items():
            if k.lower().startswith(("x-ratelimit", "ratelimit", "retry-after")):
                headers_seen[k] = v
        res = []
        row = {"query": q, "town": b["bldg_contract_town"], "status": r.status_code, "found": 0, "match": None}
        if r.status_code == 200:
            j = r.json()
            row["found"] = j.get("found", 0)
            row["keys"] = sorted(j.keys())
            res = j.get("results") or []
            # accept only a hit whose block number and road match the query (the search is fuzzy)
            for c in res:
                if c.get("BLK_NO", "").upper() == b["blk_no"].upper() and norm_road(c.get("ROAD_NAME", "")) == norm_road(b["street"]):
                    row["match"] = {k: c.get(k) for k in ("BLK_NO", "ROAD_NAME", "POSTAL", "LATITUDE", "LONGITUDE", "X", "Y")}
                    row["result_fields"] = sorted(c.keys())
                    row["planning_area_local"] = planning_area(float(c["LONGITUDE"]), float(c["LATITUDE"]), feats)
                    break
            if res and "result_fields" not in row:
                row["result_fields"] = sorted(res[0].keys())
                row["first_hit"] = res[0].get("ADDRESS")
        else:
            row["body"] = r.text[:200]
        row["raw_results"] = res if r.status_code == 200 else None
        results.append(row)
        print(q, "|", row["status"], "found", row["found"], "| match", bool(row["match"]), "|", row.get("planning_area_local"))
    (CACHE / f"geocode_{limit}.json").write_text(json.dumps({"rows": results, "rate_headers": headers_seen}, indent=1))
    print("rate-limit headers seen:", headers_seen or "none")
    print("calls used in total:", calls_used())


def stage_report():
    d = json.loads((CACHE / "geocode.json").read_text())
    rows = d["rows"]
    ok = [r for r in rows if r["match"]]
    print(f"{len(ok)}/{len(rows)} exact matches; statuses {sorted({r['status'] for r in rows})}")
    print("planning areas:", sorted({r['planning_area_local'] or 'None' for r in ok}))
    print("result fields:", next((r["result_fields"] for r in rows if r.get("result_fields")), None))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1] == "geocode" and len(sys.argv) > 2:
        stage_geocode(int(sys.argv[2]))
    else:
        {"terms": stage_terms, "token": stage_token, "geocode": stage_geocode, "report": stage_report}[sys.argv[1]]()
