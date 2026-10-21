"""Download the static datasets to a folder beside the repo (default ../coolcheck-data/static), one new directory each.

Public, unauthenticated calls only. Nothing is uploaded anywhere. Each directory gets provenance.json (source, licence,
download time, size, sha256); the folder gets SOURCES.md. Directories that already hold a file are skipped.
Run from the repo root: .venv\\Scripts\\python scripts/checks/download_static.py [--only name ...]
"""
import argparse
import hashlib
import json
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

import requests

from _common import SGT
from datagov import HEADERS, PAGE, download, write_provenance

SODL = "Singapore Open Data Licence v1.0 (https://data.gov.sg/open-data-licence), the licence data.gov.sg applies to its datasets; not in the API metadata, and the individual dataset page was read only for Eldercare (search snippet), not for this one"
SINGSTAT_BASE = "https://www.singstat.gov.sg/files/"

# name -> (kind, id or file, extra)
ITEMS = {
    "eldercare_services": ("datagov", "d_f0fd1b3643ed8bd34bd403dedd7c1533", SODL),
    "community_clubs": ("datagov", "d_f706de1427279e61fe41e89e24d440fa", SODL),
    "community_club_passion_wave_outlet": ("datagov", "d_9de02d3fb33d96da1855f4fbef549a0f", SODL),
    "parks": ("datagov", "d_0542d48f0991541706b58059381a6eca", SODL),
    "ura_mp2019_planning_area_boundary": ("datagov", "d_4765db0e87b9c86336792efe8a1f7a66", SODL),
    "hdb_property_information": ("datagov", "d_17f5382f26140b1fdae0ba2ef6239d2f", SODL),
    "census2020_pop_planning_area_age_sex": ("datagov", "d_d95ae740c0f8961a0b10435836660ce0", SODL),
    "singstat_pop_pa_age_sex_floor_area_jun2026": (
        "singstat", "a2b9150d-9ed4-4c0b-ab20-a26035f95065.zip",
        "Not confirmed: the SingStat Terms of Use page is rendered by JavaScript and could not be read by script"),
}


def fetch_singstat(file_id, dest, licence):
    dest.mkdir(parents=True, exist_ok=True)
    url = SINGSTAT_BASE + file_id
    r = requests.get(url, headers=HEADERS, timeout=120)
    r.raise_for_status()
    (dest / file_id).write_bytes(r.content)
    names = []
    if file_id.endswith(".zip"):
        with zipfile.ZipFile(dest / file_id) as z:
            for info in z.infolist():
                target = (dest / info.filename).resolve()
                if info.is_dir() or not str(target).startswith(str(dest.resolve())):
                    continue  # skip directories and any path escaping the folder
                z.extract(info, dest)
                names.append(info.filename)
    return {"name": "SingStat: " + ", ".join(names or [file_id]), "agency": "Singapore Department of Statistics",
            "source_url": url, "page": "https://www.singstat.gov.sg/find-data/explore-data-themes/population/geographic-distribution/latest-news-data",
            "licence": licence, "file": file_id, "extracted": names, "bytes": len(r.content),
            "sha256": hashlib.sha256(r.content).hexdigest(), "last_modified_header": r.headers.get("Last-Modified"),
            "downloaded": f"{datetime.now(SGT):%Y-%m-%d %H:%M} SGT"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default="../coolcheck-data/static")
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    root = Path(args.dest)
    sys.stdout.reconfigure(encoding="utf-8")
    for name, (kind, ident, licence) in ITEMS.items():
        if args.only and name not in args.only:
            continue
        d = root / name
        if d.exists() and any(p.suffix in (".geojson", ".csv", ".zip") for p in d.iterdir()):
            print("skip (already downloaded):", name)
            continue
        try:
            rec = download(ident, d) if kind == "datagov" else fetch_singstat(ident, d, licence)
        except Exception as e:  # report and continue with the others
            print(f"FAILED {name}: {type(e).__name__}: {str(e)[:160]}")
            continue
        rec["licence"] = licence
        rec.pop("meta", None) if kind != "datagov" else None
        write_provenance(d, rec)
        print(f"ok {name}: {rec['bytes']:,} bytes, sha256 {rec['sha256'][:12]}")
        time.sleep(1.5)
    lines = ["# Static data sources", "", "Downloaded by `scripts/checks/download_static.py`. Not uploaded anywhere.", "",
             "| folder | dataset | agency | source | licence | downloaded (SGT) | bytes | source last updated |", "|---|---|---|---|---|---|---|---|"]
    for p in sorted(root.glob("*/provenance.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        src = r.get("source_page") or r.get("source_url")
        lines.append(f"| {p.parent.name} | {r.get('name')} | {r.get('agency')} | {src} | {r.get('licence')} | {r.get('downloaded')} | "
                     f"{r.get('bytes'):,} | {r.get('last_updated_at') or r.get('last_modified_header') or ''} |")
    (root / "SOURCES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
