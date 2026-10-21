r"""Does api-open.data.gov.sg read DATA_GOV_SG_API_KEY from a given header? One burst of 14 GETs per run.

Run from the repo root: .venvScripts\python scripts/checks/check_apikey_burst.py --mode none|x-api-key|bearer|api-key
The key is read from the environment, sent only as a request header, and never printed or written.
"""
import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

URL = "https://api-open.data.gov.sg/v2/real-time/api/twenty-four-hr-forecast"
N = 14


def headers_for(mode):
    if mode == "none":
        return {}
    key = os.environ.get("DATA_GOV_SG_API_KEY")
    if not key:
        sys.exit("DATA_GOV_SG_API_KEY is not set")
    return {"x-api-key": key} if mode == "x-api-key" else {"Authorization": f"Bearer {key}"} if mode == "bearer" else {"api-key": key}


def one(h):
    t = time.time()
    try:
        r = requests.get(URL, headers=h, timeout=30)
        return r.status_code, r.headers.get("Retry-After"), t
    except requests.RequestException as e:
        return type(e).__name__, None, t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["none", "x-api-key", "bearer", "api-key"])
    h = headers_for(ap.parse_args().mode)
    start = time.time()
    with ThreadPoolExecutor(max_workers=N) as ex:
        res = list(ex.map(lambda _: one(h), range(N)))
    ok = sum(1 for s, _, _ in res if s == 200)
    n429 = sum(1 for s, _, _ in res if s == 429)
    other = [s for s, _, _ in res if s not in (200, 429)]
    spread = max(t for _, _, t in res) - min(t for _, _, t in res)
    print(f"mode={ap.parse_args().mode} ok={ok} 429={n429} other={other} send_spread_s={spread:.2f} "
          f"retry_after={sorted({r for _, r, _ in res if r})} started={time.strftime('%H:%M:%S', time.localtime(start))}")


if __name__ == "__main__":
    main()
