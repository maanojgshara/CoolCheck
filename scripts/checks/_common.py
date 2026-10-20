"""Shared helpers for the Day-1 check scripts: throttled cached HTTP client, SGT time parsing, markdown tables.

Public, unauthenticated calls only: no key or token is read, sent or written.
"""
import hashlib
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

SGT = ZoneInfo("Asia/Singapore")
MIN_GAP = 1.0
BACKOFF = [5, 10, 20, 40, 80]


class StopRun(Exception):
    pass


class CacheMiss(Exception):
    pass


class Client:
    def __init__(self, cache_dir, cached_only=False, url=None, cap=300, user_agent="coolcheck-check"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cached_only = cached_only
        self.url = url
        self.cap = cap
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.network_calls = 0
        self.retries = 0
        self.cache_hits = 0
        self.phase = "init"
        self.phase_calls = Counter()
        self.statuses = Counter()
        self._last = 0.0
        self._n403 = 0

    def get(self, params, url=None):
        """GET `url` (default: the client's) with `params`. The cache key is params only for the default url."""
        payload = params if url is None else {"_url": url, **params}
        key = hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        url = url or self.url
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            self.cache_hits += 1
            return json.loads(path.read_text(encoding="utf-8"))
        if self.cached_only:
            raise CacheMiss(params)
        rate_tries = conn_fails = server_tries = 0
        while True:
            if self.network_calls >= self.cap:
                raise StopRun(f"call cap of {self.cap} reached")
            time.sleep(max(0.0, MIN_GAP - (time.monotonic() - self._last)))
            self.network_calls += 1
            self.phase_calls[self.phase] += 1
            self._last = time.monotonic()
            try:
                r = self.session.get(url, params=params, timeout=30)
            except requests.RequestException as e:
                conn_fails += 1
                if conn_fails > 3:
                    raise StopRun(f"connection kept failing ({type(e).__name__})")
                self.retries += 1
                time.sleep(BACKOFF[conn_fails - 1])
                continue
            status = r.status_code
            self.statuses[status] += 1
            if status == 429:
                if rate_tries >= len(BACKOFF):
                    raise StopRun("HTTP 429 persisted through 5 retries")
                retry_after = r.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else BACKOFF[rate_tries]
                rate_tries += 1
                self.retries += 1
                time.sleep(min(delay, 120))
                continue
            if status in (401, 403):
                self._n403 += 1
                if status == 401 or self._n403 >= 2:
                    raise StopRun(f"HTTP {status}: the endpoint refuses unauthenticated calls")
                self.retries += 1
                time.sleep(BACKOFF[0])
                continue
            self._n403 = 0
            if status >= 500:
                server_tries += 1
                if server_tries > 2:
                    raise StopRun(f"HTTP {status} persisted")
                self.retries += 1
                time.sleep(BACKOFF[server_tries - 1])
                continue
            try:
                body = r.json()
            except ValueError:
                body = None
            out = {"status": status, "body": body, "text": "" if body is not None else r.text[:200]}
            path.write_text(json.dumps(out), encoding="utf-8")
            return out


def parse_sgt(ts):
    """ISO timestamp -> aware datetime in Asia/Singapore; None if missing or naive."""
    if not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return dt.astimezone(SGT) if dt.tzinfo else None


def key_paths(obj, prefix="", out=None):
    """Leaf paths of a record: path -> (type, example). Lists are merged across elements as []."""
    out = {} if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_paths(v, f"{prefix}.{k}" if prefix else k, out)
    elif isinstance(obj, list):
        for v in obj:
            key_paths(v, prefix + "[]", out)
    else:
        out.setdefault(prefix, (type(obj).__name__, obj))
    return out


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return lines


def hm(dt):
    return dt.strftime("%H:%M")


def months_between(a, b):
    out, (y, m) = [], a
    while (y, m) <= b:
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out
