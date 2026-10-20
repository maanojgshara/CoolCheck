"""Resumable, idempotent backfill of data.gov.sg real-time feeds to raw JSONL on this computer.

Order: WBGT, then the 24-hour forecast, then rainfall, each from 2025-01-16 to yesterday (SGT).
Run from the repo root:
    .venv\\Scripts\\python scripts/backfill/backfill.py --feeds wbgt [--dry-run]

Layout under --out-dir (default: coolcheck-data beside the repo, never inside it):
    raw/<feed>/backfill/<feed>_<YYYY-MM-DD>.jsonl   one unmodified response body per line, one line per page
    raw/_meta/backfill_end.json                     last contiguous finished day per feed (for the collector)
    backfill/progress.jsonl                         append-only: one line per finished (feed, day), plus run lines
    backfill/backfill.log, backfill/backfill.lock

A day is written to <file>.partial and renamed only after its last page (no paginationToken), so a .jsonl file
is always a complete day. A restart skips finished days, deletes leftover .partial files, and records a finished
.jsonl that has no progress line after re-checking it (no calls).

The API key is optional: read only from DATA_GOV_SG_API_KEY and sent as the x-api-key header. It is never
printed, logged or written; logs say only whether a key is present.
Throttled to 1 call/second; backs off on 429; stops and reports on a persistent 429/403/401/5xx.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter, deque
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

SGT = ZoneInfo("Asia/Singapore")
BASE = "https://api-open.data.gov.sg/v2/real-time/api/"
START = date(2025, 1, 16)  # first day with WBGT history (check 9)
ORDER = ["wbgt", "forecast", "rainfall"]
FEEDS = {
    # name: (url, fixed params, readings expected per day, pages per day measured in checks 9 and 10)
    "wbgt": (BASE + "weather", {"api": "wbgt"}, 96, 4),
    "forecast": (BASE + "twenty-four-hr-forecast", {}, None, 1),
    "rainfall": (BASE + "rainfall", {}, 288, 12),
}
KEY_ENV = "DATA_GOV_SG_API_KEY"
KEY_HEADER = "x-api-key"
BOGUS_KEY = "coolcheck-invalid-key-0000"  # placeholder for --verify-key, not a secret
USER_AGENT = "coolcheck-backfill"
MIN_GAP = 1.0
BACKOFF = [5, 10, 20, 40, 80]
RETRY_AFTER_CAP = 120
WINDOW = 100  # stop when more than half of the last WINDOW calls got a 429
MAX_PAGES = 40
TIMEOUT = 30
FINISHED = ("done", "short", "empty", "date_mismatch", "no_data")
SECONDS_PER_CALL = 1.7  # 1 s gap plus the 14% 429 rate seen in check 9 at >= 5 s each
REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO.parent / "coolcheck-data"


class StopRun(Exception):
    pass


class Log:
    """Console + backfill.log. Every message is scrubbed of the key before it goes anywhere."""

    def __init__(self, path, secret=None):
        self.path, self._secret = path, secret

    def __call__(self, msg):
        if self._secret:
            msg = msg.replace(self._secret, "***")
        line = f"{datetime.now(SGT):%Y-%m-%d %H:%M:%S} {msg}"
        print(line, flush=True)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")


class Fetcher:
    """Throttled GET with the back-off and stop rules. Returns (status, raw bytes) for 200 and 404 only."""

    def __init__(self, session, key_present, max_calls=None, sleep=time.sleep, clock=time.monotonic):
        self.session, self.key_present, self.max_calls = session, key_present, max_calls
        self.sleep, self.clock = sleep, clock
        self.calls = self.retries = 0
        self.statuses = Counter()
        self.recent = deque(maxlen=WINDOW)
        self._last = None

    def _wait(self, seconds):
        self.retries += 1
        self.sleep(seconds)

    def get(self, url, params):
        rate = server = conn = n403 = 0
        while True:
            if self.max_calls is not None and self.calls >= self.max_calls:
                raise StopRun(f"--max-calls {self.max_calls} reached")
            if self._last is not None:
                gap = MIN_GAP - (self.clock() - self._last)
                if gap > 0:
                    self.sleep(gap)
            self._last = self.clock()
            self.calls += 1
            try:
                r = self.session.get(url, params=params, timeout=TIMEOUT)
            except requests.RequestException as e:
                conn += 1
                self.recent.append(False)
                if conn >= 3:
                    raise StopRun(f"connection failed 3 times in a row ({type(e).__name__})")
                self._wait(BACKOFF[conn - 1])
                continue
            status = r.status_code
            self.statuses[status] += 1
            self.recent.append(status == 429)
            if status == 429:
                if sum(self.recent) > WINDOW // 2:
                    raise StopRun(f"HTTP 429 on {sum(self.recent)} of the last {len(self.recent)} calls")
                if rate >= len(BACKOFF):
                    raise StopRun("HTTP 429 persisted through 5 retries")
                retry_after = r.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else BACKOFF[rate]
                rate += 1
                self._wait(min(delay, RETRY_AFTER_CAP))
                continue
            if status == 401:
                raise StopRun("HTTP 401: key rejected" if self.key_present else "HTTP 401: the endpoint refuses unauthenticated calls")
            if status == 403:
                if self.key_present:
                    raise StopRun("HTTP 403 with the key set: key rejected")
                n403 += 1
                if n403 >= 2:
                    raise StopRun("HTTP 403 twice in a row")
                self._wait(BACKOFF[0])
                continue
            if status >= 500:
                server += 1
                if server > 2:
                    raise StopRun(f"HTTP {status} persisted after 2 retries")
                self._wait(BACKOFF[server - 1])
                continue
            if status in (200, 404):
                return status, r.content
            raise StopRun(f"unexpected HTTP {status}")


# ---- reading dates (the date check: readings must fall on the requested SGT date) ----

def reading_stamps(feed, data):
    """One date/time string per reading on a page: WBGT records[].datetime, rainfall readings[].timestamp,
    forecast records[].date (the forecast's own date field, as in check 10)."""
    if feed == "rainfall":
        return [r.get("timestamp") for r in data.get("readings") or [] if isinstance(r, dict)]
    key = "datetime" if feed == "wbgt" else "date"
    return [r.get(key) for r in data.get("records") or [] if isinstance(r, dict)]


def sgt_date_of(feed, stamp):
    if not isinstance(stamp, str):
        return None
    if feed == "forecast":
        return stamp[:10]
    try:
        dt = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return dt.astimezone(SGT).date().isoformat() if dt.tzinfo else None


def check_line(content):
    """A body may go on one JSONL line unchanged only if it has no line break, except one trailing \\n."""
    inner = content[:-1] if content.endswith(b"\n") else content
    return b"\n" not in inner and b"\r" not in inner


class DayStats:
    def __init__(self, feed, day):
        self.feed, self.day = feed, day
        self.pages = self.readings = self.on_day = self.bytes = 0
        self.stamps = set()
        self.other = Counter()
        self.sha = hashlib.sha256()
        self.token = None

    def add(self, line):
        """One page as written to the file (the body plus its line ending), so bytes and sha256 match the file."""
        body = json.loads(line)
        data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), dict) else {}
        self.pages += 1
        self.bytes += len(line)
        self.sha.update(line)
        self.token = data.get("paginationToken")
        for st in reading_stamps(self.feed, data):
            self.readings += 1
            d = sgt_date_of(self.feed, st)
            if d == self.day.isoformat():
                self.on_day += 1
                self.stamps.add(st)
            else:
                self.other[d or "undated"] += 1

    def status(self):
        expected = FEEDS[self.feed][2]
        if self.readings == 0:
            return "empty"
        if self.on_day == 0:
            return "date_mismatch"
        if expected and len(self.stamps) < expected:
            return "short"
        return "done"

    def record(self, calls, key_present, recovered=False):
        rec = {"event": "day", "feed": self.feed, "date": self.day.isoformat(), "status": self.status(),
               "pages": self.pages, "readings": self.readings, "distinct_on_day": len(self.stamps),
               "other_date_readings": dict(self.other), "bytes": self.bytes, "sha256": self.sha.hexdigest(),
               "calls": calls, "key": "present" if key_present else "absent",
               "fetched_at": f"{datetime.now(SGT):%Y-%m-%dT%H:%M:%S%z}"}
        if recovered:
            rec["recovered"] = True
        return rec


# ---- state ----

class State:
    def __init__(self, out_dir):
        self.out = Path(out_dir)
        self.state_dir = self.out / "backfill"
        self.progress = self.state_dir / "progress.jsonl"

    def raw_dir(self, feed):
        return self.out / "raw" / feed / "backfill"

    def day_file(self, feed, day):
        return self.raw_dir(feed) / f"{feed}_{day.isoformat()}.jsonl"

    def load(self):
        """(feed, date) -> last day record. A truncated or unreadable line is ignored."""
        done = {}
        if self.progress.exists():
            for line in self.progress.read_text(encoding="utf-8").splitlines():
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict) and rec.get("event") == "day":
                    done[(rec["feed"], rec["date"])] = rec
        return done

    def append(self, rec):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with open(self.progress, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
            f.flush()
            os.fsync(f.fileno())


def acquire_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise StopRun("another backfill holds the lock on this out-dir")
    return f


def default_end(now):
    """Yesterday SGT; before 01:00 SGT the day before, so yesterday's late readings have arrived."""
    now = now.astimezone(SGT)
    return now.date() - timedelta(days=2 if now.hour < 1 else 1)


def days_between(a, b):
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def make_session(key):
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    if key:
        s.headers[KEY_HEADER] = key
    return s


# ---- one day ----

def recover(state, feed, day, path, key_present):
    """Re-check a finished .jsonl that has no progress line. Returns its record, or None if it is not a complete day."""
    st = DayStats(feed, day)
    try:
        lines = path.read_bytes().splitlines(keepends=True)
        for line in lines:
            st.add(line)
    except ValueError:
        return None
    if not lines or st.token:
        return None
    return st.record(calls=0, key_present=key_present, recovered=True)


def fetch_day(state, fetcher, feed, day, key_present):
    url, fixed, _, _ = FEEDS[feed]
    final = state.day_file(feed, day)
    part = final.with_name(final.name + ".partial")
    final.parent.mkdir(parents=True, exist_ok=True)
    st, calls0 = DayStats(feed, day), fetcher.calls
    params = {**fixed, "date": day.isoformat()}
    try:
        with open(part, "wb") as f:
            for page in range(1, MAX_PAGES + 1):
                status, content = fetcher.get(url, params)
                if status == 404:
                    if page > 1:
                        raise StopRun(f"{feed} {day}: HTTP 404 on page {page}")
                    f.close()
                    part.unlink()
                    return {"event": "day", "feed": feed, "date": day.isoformat(), "status": "no_data", "pages": 0,
                            "calls": fetcher.calls - calls0, "key": "present" if key_present else "absent",
                            "fetched_at": f"{datetime.now(SGT):%Y-%m-%dT%H:%M:%S%z}"}
                if not check_line(content):
                    raise StopRun(f"{feed} {day} page {page}: the response body contains a line break, so it cannot "
                                  "go on one JSONL line unchanged; decide whether to compact bodies")
                line = content if content.endswith(b"\n") else content + b"\n"
                try:
                    st.add(line)
                except ValueError:
                    raise StopRun(f"{feed} {day} page {page}: response is not JSON")
                f.write(line)
                if not st.token:
                    break
                params = {**fixed, "date": day.isoformat(), "paginationToken": st.token}
            else:
                raise StopRun(f"{feed} {day}: more than {MAX_PAGES} pages")
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        if part.exists():
            part.unlink()
        raise
    os.replace(part, final)
    return st.record(calls=fetcher.calls - calls0, key_present=key_present)


# ---- run ----

def contiguous_end(done, feed, end):
    last = None
    for d in days_between(START, end):
        if (feed, d.isoformat()) not in done:
            break
        last = d
    return last


def write_marker(state, done, end):
    path = state.out / "raw" / "_meta" / "backfill_end.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    marker = {f: (contiguous_end(done, f, end) or START - timedelta(days=1)).isoformat() for f in ORDER}
    marker["note"] = "last day (SGT) finished contiguously from 2025-01-16; the collector's first run starts the next day"
    marker["written_at"] = f"{datetime.now(SGT):%Y-%m-%dT%H:%M:%S%z}"
    path.write_text(json.dumps(marker, indent=1) + "\n", encoding="utf-8")


def dry_run(state, feeds, start, end, retry_missing, log):
    done = state.load()
    total = 0
    for feed in feeds:
        days = days_between(start, end)
        fin = [d for d in days if (feed, d.isoformat()) in done
               and not (retry_missing and done[(feed, d.isoformat())]["status"] == "no_data")]
        todo = len(days) - len(fin)
        partials = list(state.raw_dir(feed).glob("*.partial")) if state.raw_dir(feed).exists() else []
        calls = todo * FEEDS[feed][3]
        total += calls
        log(f"[dry-run] {feed}: {len(days)} days {start}..{end}; finished {len(fin)}; to fetch {todo}; "
            f"about {calls:,} calls ({calls * SECONDS_PER_CALL / 3600:.1f} h); leftover .partial files {len(partials)}")
    log(f"[dry-run] total about {total:,} calls, {total * SECONDS_PER_CALL / 3600:.1f} h. No calls made.")


def verify_key(key, end, sleep, log, session_factory=make_session):
    """Three calls to one WBGT day: no key, an invalid placeholder key, the real key. Prints statuses only."""
    url, fixed, _, _ = FEEDS["wbgt"]
    params = {**fixed, "date": end.isoformat()}
    results = {}
    for i, (label, k) in enumerate((("no key", None), ("invalid placeholder key", BOGUS_KEY), ("your key", key))):
        if i:
            sleep(2 * MIN_GAP)
        try:
            r = session_factory(k).get(url, params=params, timeout=TIMEOUT)
        except requests.RequestException as e:
            log(f"[verify-key] {label}: request failed ({type(e).__name__})")
            results[label] = None
            continue
        rate_hdrs = {n: v for n, v in r.headers.items() if "ratelimit" in n.lower() or n.lower() == "retry-after"}
        log(f"[verify-key] {label}: HTTP {r.status_code}; header names: {', '.join(sorted(r.headers.keys()))}; "
            f"rate-limit headers: {rate_hdrs or 'none'}")
        results[label] = r.status_code
    bogus, real = results["invalid placeholder key"], results["your key"]
    if bogus in (401, 403) and real == 200:
        verdict = f"the server reads {KEY_HEADER}: an invalid key is refused and your key is accepted"
    elif real in (401, 403):
        verdict = f"your key was refused (HTTP {real}); do not use it"
    elif bogus == 200:
        verdict = (f"inconclusive: an invalid key also got HTTP 200, so {KEY_HEADER} is ignored or bad keys pass "
                   "silently; treat the key as unverified and compare 429 rates during the run")
    else:
        verdict = "inconclusive; see the statuses above"
    log(f"[verify-key] verdict: {verdict}")
    return 0 if bogus in (401, 403) and real == 200 else 1


def run(state, fetcher, feeds, start, end, retry_missing, key_present, log):
    done = state.load()
    stop, mismatch_run, n = None, 0, Counter()
    for feed in feeds:
        raw = state.raw_dir(feed)
        if raw.exists():
            for p in sorted(raw.glob("*.partial")):
                log(f"{feed}: deleting unfinished {p.name}; the day will be refetched")
                p.unlink()
    try:
        for feed in feeds:
            for day in days_between(start, end):
                key = (feed, day.isoformat())
                if key in done and not (retry_missing and done[key]["status"] == "no_data"):
                    continue
                path = state.day_file(feed, day)
                rec = None
                if path.exists():
                    rec = recover(state, feed, day, path, key_present)
                    if rec is None:
                        log(f"{feed} {day}: {path.name} has no progress line and is not a complete day; refetching")
                        path.unlink()
                    else:
                        log(f"{feed} {day}: recorded the finished file that had no progress line (0 calls)")
                if rec is None:
                    rec = fetch_day(state, fetcher, feed, day, key_present)
                state.append(rec)
                done[key] = rec
                n[(feed, rec["status"])] += 1
                other = rec.get("other_date_readings")
                log(f"{feed} {day} {rec['status']:<13} pages={rec['pages']} readings={rec.get('readings', 0)}"
                    f"{' other-date=' + json.dumps(other) if other else ''} calls={rec['calls']} (run total {fetcher.calls}, "
                    f"429s {fetcher.statuses[429]})")
                mismatch_run = mismatch_run + 1 if rec["status"] == "date_mismatch" else 0
                if mismatch_run >= 3:
                    raise StopRun("3 days in a row with no readings on the requested date (the API may be ignoring date=)")
    except StopRun as e:
        stop = str(e)
    except KeyboardInterrupt:
        stop = "interrupted (Ctrl+C)"
    write_marker(state, done, end)
    return stop, done, n


def summary(state, done, feeds, start, end, fetcher, stop, n, elapsed, key_present, log):
    for feed in feeds:
        days = days_between(start, end)
        st = Counter(done[(feed, d.isoformat())]["status"] for d in days if (feed, d.isoformat()) in done)
        remaining = len(days) - sum(st.values())
        log(f"{feed}: {dict(st)}; remaining {remaining} of {len(days)} days ({start}..{end})")
    rate = fetcher.statuses[429] / fetcher.calls if fetcher.calls else 0.0
    log(f"calls this run {fetcher.calls}; retries {fetcher.retries}; HTTP statuses {dict(fetcher.statuses)}; "
        f"429 share {100 * rate:.1f}%; elapsed {elapsed / 60:.1f} min; key {'present' if key_present else 'absent'}")
    state.append({"event": "run_end", "feeds": feeds, "start": start.isoformat(), "end": end.isoformat(),
                  "calls": fetcher.calls, "retries": fetcher.retries,
                  "statuses": {str(k): v for k, v in fetcher.statuses.items()},
                  "days_this_run": {f"{f}:{s}": c for (f, s), c in n.items()}, "elapsed_s": round(elapsed, 1),
                  "key": "present" if key_present else "absent", "stopped": stop,
                  "at": f"{datetime.now(SGT):%Y-%m-%dT%H:%M:%S%z}"})
    if stop:
        log(f"STOPPED: {stop}. Rerun the same command to resume.")


def main(argv=None, session=None, sleep=time.sleep, clock=time.monotonic, now=None, env=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--feeds", default=",".join(ORDER), help="comma-separated, run in the fixed order wbgt,forecast,rainfall")
    ap.add_argument("--start", type=date.fromisoformat, default=START)
    ap.add_argument("--end", type=date.fromisoformat, help="default: yesterday SGT (the day before, before 01:00)")
    ap.add_argument("--max-calls", type=int)
    ap.add_argument("--retry-missing", action="store_true", help="refetch days recorded as no_data (HTTP 404)")
    ap.add_argument("--dry-run", action="store_true", help="show what would be fetched; no calls")
    ap.add_argument("--verify-key", action="store_true", help="3 calls to check that the server reads the key header")
    args = ap.parse_args(argv)

    env = os.environ if env is None else env
    key = env.get(KEY_ENV) or None
    now = now or datetime.now(SGT)
    out = Path(args.out_dir).resolve()
    if out == REPO or REPO in out.parents:
        print(f"--out-dir must be outside the repo ({REPO})", file=sys.stderr)
        return 2
    feeds = [f for f in ORDER if f in args.feeds.split(",")]
    unknown = set(args.feeds.split(",")) - set(ORDER)
    if unknown or not feeds:
        print(f"unknown feeds: {sorted(unknown)}; choose from {ORDER}", file=sys.stderr)
        return 2
    latest = default_end(now)
    end = args.end or latest
    if end > latest:
        print(f"--end {end} is after {latest}, the last complete SGT day", file=sys.stderr)
        return 2
    if args.start < START or args.start > end:
        print(f"--start must be between {START} and {end}", file=sys.stderr)
        return 2

    state = State(out)
    state.state_dir.mkdir(parents=True, exist_ok=True)
    log = Log(state.state_dir / "backfill.log", secret=key)
    log(f"backfill: feeds {feeds}, {args.start}..{end}, out-dir {out}, key {'present' if key else 'absent'}")
    if args.dry_run:
        dry_run(state, feeds, args.start, end, args.retry_missing, log)
        return 0
    if args.verify_key:
        if not key:
            log(f"[verify-key] {KEY_ENV} is not set; nothing to verify")
            return 2
        return verify_key(key, end, sleep, log)

    try:
        lock = acquire_lock(state.state_dir / "backfill.lock")
    except StopRun as e:
        log(f"STOPPED: {e}")
        return 3
    try:
        fetcher = Fetcher(session or make_session(key), key_present=bool(key), max_calls=args.max_calls,
                          sleep=sleep, clock=clock)
        t0 = clock()
        state.append({"event": "run_start", "feeds": feeds, "start": args.start.isoformat(), "end": end.isoformat(),
                      "key": "present" if key else "absent", "at": f"{datetime.now(SGT):%Y-%m-%dT%H:%M:%S%z}"})
        stop, done, n = run(state, fetcher, feeds, args.start, end, args.retry_missing, bool(key), log)
        summary(state, done, feeds, args.start, end, fetcher, stop, n, clock() - t0, bool(key), log)
        return 1 if stop else 0
    finally:
        lock.close()


if __name__ == "__main__":
    sys.exit(main())
