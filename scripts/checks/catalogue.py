"""Crawl the data.gov.sg dataset catalogue (id, name, agency, format, dates) and search it by name.

Public, unauthenticated calls only: no key or token is read, sent or written.
Run from the repo root: .venv\\Scripts\\python scripts/checks/catalogue.py --cache-dir <dir> [--grep word ...]
The listing endpoint ignores a search query, so every page is fetched (about 470 calls at 1 a second); pages are cached.
"""
import argparse
import json
import sys
from pathlib import Path

from _common import Client, StopRun

URL = "https://api-production.data.gov.sg/v2/public/api/datasets"


def crawl(cache_dir, cap=900):
    c = Client(cache_dir, url=URL, cap=cap, user_agent="coolcheck-catalogue")
    first = c.get({"page": 1})["body"]["data"]
    out, pages = list(first["datasets"]), first["pages"]
    for p in range(2, pages + 1):
        out += c.get({"page": p})["body"]["data"]["datasets"]
    return out, c


def search(rows, words):
    words = [w.lower() for w in words]
    return [r for r in rows if all(w in (r["name"] + " " + r.get("description", "")).lower() for w in words)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--out", help="write the full catalogue as JSON here (outside the repo)")
    ap.add_argument("--grep", nargs="*", action="append", default=[], help="words that must all appear in name or description")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        rows, c = crawl(args.cache_dir)
    except StopRun as e:
        print("stopped:", e)
        return
    print(f"{len(rows)} datasets; network calls {c.network_calls}, retries {c.retries}, statuses {dict(c.statuses)}")
    if args.out:
        Path(args.out).write_text(json.dumps(rows), encoding="utf-8")
    for words in args.grep:
        print(f"\n== {' '.join(words)}")
        for r in search(rows, words):
            print(r["datasetId"], "|", r["name"], "|", r.get("managedByAgencyName"), "|", r.get("format"), "|", r.get("lastUpdatedAt", "")[:10])


if __name__ == "__main__":
    main()
