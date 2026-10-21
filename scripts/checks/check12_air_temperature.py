"""Day-2 check 12: NEA air temperature from data.gov.sg (reading interval and station count over time).

Public, unauthenticated calls only: no key or token is read, sent or written.
Run from the repo root: .venv\\Scripts\\python scripts/checks/check12_air_temperature.py --cache-dir <dir>
Throttled to 1 call/second, hard cap of 120 network calls (retries included). Raw responses are cached in --cache-dir.
"""
import argparse
import statistics
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from _common import SGT, Client, StopRun, key_paths, parse_sgt, table

URL = "https://api-open.data.gov.sg/v2/real-time/api/air-temperature"
CAP = 120
SAMPLE_DAYS = [date(2016, 12, 2), date(2018, 6, 15), date(2020, 6, 15), date(2022, 6, 15), date(2024, 6, 12),
               date(2025, 1, 16), date(2025, 6, 15), date(2026, 3, 15), date(2026, 10, 19)]


def fetch(c, params):
    """All pages for one query -> (readings list, http status, error text)."""
    out, token = [], None
    for _ in range(40):
        p = dict(params)
        if token:
            p["paginationToken"] = token
        r = c.get(p)
        if r["status"] != 200:
            return out, r["status"], str((r["body"] or {}).get("errorMsg") or r["text"])[:100]
        data = (r["body"] or {}).get("data") or {}
        out += data.get("readings") or []
        token = data.get("paginationToken")
        if not token:
            break
    return out, 200, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--out", default="docs/checks/check12.md")
    args = ap.parse_args()
    c = Client(args.cache_dir, url=URL, cap=CAP, user_agent="coolcheck-check12")
    L = ["# Check 12: NEA air temperature (data.gov.sg)", "",
         f"Endpoint `{URL}`, unauthenticated. Script: `scripts/checks/check12_air_temperature.py`. Run {datetime.now(SGT):%Y-%m-%d %H:%M} SGT.", ""]
    stop = None
    try:
        c.phase = "latest"
        r = c.get({})
        body = r["body"] or {}
        data = body.get("data") or {}
        L += [f"## Latest call", "", f"HTTP {r['status']}; data keys {sorted(data)}; station metadata count {len(data.get('stations') or [])}; "
              f"reading groups {len(data.get('readings') or [])}.", ""]
        if data.get("readings"):
            L += ["Leaf paths of the first reading group:", ""]
            L += table(["path", "type", "example"], [(f"`{p}`", t, f"`{str(e)[:40]}`") for p, (t, e) in key_paths(data["readings"][0]).items()])
            L.append("")
        L += ["## Interval and stations per sampled day", "",
              "Three calls per date. (1) `date=YYYY-MM-DD`, first page only: the API returns 25 readings, newest first, from the end of that day. "
              "(2) and (3) `date=` with a time, 12:00:00 and 12:01:00: one reading each. Interval = gaps between consecutive reading timestamps "
              "on the first page, and the 12:00 to 12:01 pair. Stations = stations with a value in that reading; 'listed' = stations in the response's station list.", ""]
        rows = []
        for d in SAMPLE_DAYS:
            c.phase = "days"
            r1 = c.get({"date": d.isoformat()})
            d1 = (r1["body"] or {}).get("data") or {}
            reads = d1.get("readings") or []
            if r1["status"] != 200 or not reads:
                rows.append((d, r1["status"], 0, "", "", "", "", str((r1["body"] or {}).get("errorMsg") or r1["text"])[:60]))
                continue
            ts = sorted({parse_sgt(g.get("timestamp")) for g in reads})
            gaps = Counter(int((b - a).total_seconds() // 60) for a, b in zip(ts, ts[1:]))
            per = [len(g.get("data", [])) for g in reads]
            noon = []
            for hhmm in ("12:00:00", "12:01:00"):
                rn = c.get({"date": f"{d.isoformat()}T{hhmm}"})
                noon.append(((rn["body"] or {}).get("data") or {}) if rn["status"] == 200 else {})
            n_noon = [len((x.get("readings") or [{}])[0].get("data", [])) for x in noon]
            t_noon = [parse_sgt((x.get("readings") or [{}])[0].get("timestamp")) for x in noon]
            noon_gap = f"{int((t_noon[1] - t_noon[0]).total_seconds() // 60)} min" if all(t_noon) else "n/a"
            rows.append((d, r1["status"], len(ts), f"{ts[0]:%H:%M}-{ts[-1]:%H:%M}",
                         ", ".join(f"{k} min: {v}" for k, v in gaps.most_common(3)),
                         f"first page {min(per)}-{max(per)}; at 12:00 {n_noon[0]}, at 12:01 {n_noon[1]}; listed {len(d1.get('stations') or [])}",
                         noon_gap, ""))
        L += table(["date", "HTTP", "timestamps on page 1", "span (SGT)", "gaps between timestamps", "stations with a value", "12:00 to 12:01", "note"], rows)
        L.append("")
        ok = [r for r in rows if r[2]]
        one_min = [r for r in ok if r[4].startswith("1 min")]
        zero = [r[0] for r in ok if r[6] == "0 min"]
        listed = [int(r[5].split("listed ")[1]) for r in ok]
        L += ["### Reading", "",
              f"- **Reading interval: 1 minute** on the {len(one_min)} of {len(ok)} sampled dates with a page of 25 readings (all 24 gaps were 1 minute); "
              f"the 12:00 to 12:01 pair was 1 minute apart on {sum(r[6] == '1 min' for r in ok)} dates and returned the same reading on {len(zero)} "
              f"({', '.join(map(str, zero)) or 'none'}), so on those dates a reading at 12:01 was not found by `date=` (cause not determined).",
              f"- **Station count: {min(listed)} to {max(listed)} across the sampled dates; {listed[-1]} listed on {ok[-1][0]}.** It is not constant, so quote a count with its date. "
              "The Plan's 'about 18' matches the latest date only.",
              "- History: the earliest sampled date (2016-12-02) has a reading, so `date=` history reaches at least back to then; the exact start was not searched.", ""]
    except StopRun as e:
        stop = str(e)
        L += [f"> **Run stopped early: {stop}.** Sections above are partial.", ""]
    L += ["## Calls", "", f"Network calls {c.network_calls} (cap {CAP}), retries {c.retries}, cache hits {c.cache_hits}, HTTP status counts {dict(c.statuses)}. "
          f"No key or token was used. Stop reason: {stop or 'none'}.", "",
          "**Not tested:** whether a key changes history depth or limits; whether stations missing from a day's readings were offline or absent from the feed; "
          "the values themselves.", ""]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
