"""data.gov.sg dataset helpers: metadata and file download with a provenance record.

Public, unauthenticated calls only. The download endpoint returns a short-lived signed link; it is used once and never
printed or stored (only the dataset id, name, licence text and sha256 are recorded).
"""
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

import requests

from _common import SGT

META = "https://api-production.data.gov.sg/v2/public/api/datasets/{}/metadata"
POLL = "https://api-open.data.gov.sg/v1/public/api/datasets/{}/poll-download"
PAGE = "https://data.gov.sg/datasets/{}/view"
HEADERS = {"User-Agent": "coolcheck-check"}


def _get(url, tries=6, **kw):
    for i in range(tries):
        r = requests.get(url, headers=HEADERS, timeout=60, **kw)
        if r.status_code != 429:
            return r
        time.sleep(min(5 * 2 ** i, 60))
    return r


def metadata(dataset_id):
    r = _get(META.format(dataset_id))
    r.raise_for_status()
    return r.json()["data"]


def download(dataset_id, dest_dir):
    """Download the dataset file into dest_dir (created, expected empty) -> provenance dict."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    meta = metadata(dataset_id)
    time.sleep(1)
    r = _get(POLL.format(dataset_id))
    r.raise_for_status()
    link = r.json()["data"]["url"]
    fmt = (meta.get("format") or "bin").lower()
    path = dest / f"{dataset_id}.{'geojson' if fmt == 'geojson' else fmt}"
    f = _get(link)
    f.raise_for_status()
    path.write_bytes(f.content)
    return {
        "dataset_id": dataset_id, "name": meta.get("name"), "agency": meta.get("managedBy"), "format": meta.get("format"),
        "last_updated_at": meta.get("lastUpdatedAt"), "created_at": meta.get("createdAt"),
        "source_page": PAGE.format(dataset_id), "file": path.name, "bytes": len(f.content),
        "sha256": hashlib.sha256(f.content).hexdigest(),
        "downloaded": f"{datetime.now(SGT):%Y-%m-%d %H:%M} SGT", "meta": meta,
    }


def write_provenance(dest_dir, record):
    (Path(dest_dir) / "provenance.json").write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
