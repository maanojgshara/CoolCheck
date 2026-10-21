"""Live collector: fetch the three Bronze feeds and put raw JSONL in the raw-files Volume (Day 2, step 5).

Runs every 15 minutes in GitHub Actions (.github/workflows/collector.yml), because the workspace cannot reach .gov.sg
hosts (§14.6). Reuses the backfill's fetch code: the throttled Fetcher (1 call/s), the session with the optional
x-api-key header, the one-line check and the log that scrubs secrets.

Layout under the Volume root (repository variable COLLECTOR_VOLUME_ROOT), as the backfill's raw/ except `live` in place
of `backfill` (Silver ranks live copies above backfill copies) and one new file per feed per run (Auto Loader loads a
path once and ignores later overwrites):
    <root>/<feed>/live/<YYYY-MM-DD>/<feed>_<YYYY-MM-DD>T<HHMMSS>_<run id>.jsonl
one unmodified response body per line, one line per page. Date and time are the run's start in SGT, computed
explicitly (the runner's clock is UTC); the run id is GITHUB_RUN_ID, or "local" outside Actions.

Pages: each feed is read newest first from date=<today SGT> until the window start (default 2 h back) is covered,
then from earlier dates while the window reaches them. A run whose SGT hour is 0 also reads every page of yesterday
for all three feeds (the midnight sweep). A 404 on page 1 of a date means no data yet, not an error, except for
today's WBGT and rainfall from 01:00 SGT, when readings must exist: then the feed fails (the forecast is unchanged).

Throttle and stops: 1 call/s; a 429 is retried at most twice, 11 s apart (longer than the 10 s window; the API sends
no Retry-After); the run stops fetching when a call runs out of retries, once the run has had 3 HTTP 429s, after
401/403 with the key, or after 180 s. Each feed's file is written and uploaded on its own; exit code 1 if anything
failed, 2 for a usage error.

Run from the repo root:
    .venv\\Scripts\\python scripts/collector/collect.py --dry-run --out-dir ..\\coolcheck-data\\collector_dryrun

--dry-run writes the files under --out-dir only and makes no Databricks call. --out-dir must be outside the repo and
outside coolcheck-data/raw (upload_raw.py uploads everything there). Without --dry-run each file is uploaded with one
Files API PUT (overwrite=false, so a name clash fails) as the service principal in DATABRICKS_HOST,
DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET. Secrets come from the environment only and are never printed.
"""
import argparse
import io
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backfill"))
import backfill as bf  # noqa: E402
from backfill import SGT, StopRun  # noqa: E402

WINDOW_HOURS = 2
MAX_WINDOW_HOURS = 48  # manual catch-up from workflow_dispatch, capped at two days
BACKOFF = [11, 11]
MAX_429 = 3
BUDGET_S = 180
ROOT_ENV = "COLLECTOR_VOLUME_ROOT"
DBX_ENV = ("DATABRICKS_HOST", "DATABRICKS_CLIENT_ID", "DATABRICKS_CLIENT_SECRET")
ROOT_RE = re.compile(r"^/Volumes(/[A-Za-z0-9_-]+){3,}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9-]+$")
DEFAULT_OUT = Path(tempfile.gettempdir()) / "coolcheck-collector"


class FeedError(Exception):
    """A problem with one feed's pages; the other feeds still run."""


class Log(bf.Log):
    """The backfill's log, scrubbing every secret given (the API key and the OAuth secret)."""

    def __init__(self, path, secrets):
        super().__init__(path)
        self._secrets = [s for s in secrets if s]

    def scrub(self, msg):
        for s in self._secrets:
            msg = msg.replace(s, "***")
        return msg

    def __call__(self, msg):
        super().__call__(self.scrub(msg))


class Guard:
    """The run-level stops around Fetcher.get: 3 HTTP 429s in the run, or the time budget spent."""

    def __init__(self, fetcher, clock, budget=BUDGET_S, max_429=MAX_429):
        self.fetcher, self.clock, self.budget, self.max_429 = fetcher, clock, budget, max_429
        self.t0 = clock()

    def get(self, url, params):
        if self.fetcher.statuses[429] >= self.max_429:
            raise StopRun(f"{self.fetcher.statuses[429]} HTTP 429s this run")
        if self.clock() - self.t0 > self.budget:
            raise StopRun(f"time budget of {self.budget} s spent")
        return self.fetcher.get(url, params)


def plan(now, window_hours):
    """[(date, reach)] newest first: read the date's pages until one holds a reading at or before `reach`;
    reach None means every page (yesterday, in a run whose SGT hour is 0)."""
    start = now - timedelta(hours=window_hours)
    out, d = [], now.date()
    while d >= start.date():
        out.append([d, start])
        d -= timedelta(days=1)
    if now.hour == 0:
        yesterday = now.date() - timedelta(days=1)
        hit = [x for x in out if x[0] == yesterday]
        if hit:
            hit[0][1] = None
        else:
            out.append([yesterday, None])
    return [tuple(x) for x in out]


def instants(feed, data):
    """Aware datetimes on a page: WBGT records[].datetime, rainfall readings[].timestamp, forecast records[].timestamp."""
    if feed == "forecast":
        raw = [r.get("timestamp") for r in data.get("records") or [] if isinstance(r, dict)]
    else:
        raw = bf.reading_stamps(feed, data)
    out = []
    for s in raw:
        try:
            dt = datetime.fromisoformat(s)
        except (TypeError, ValueError):
            continue
        if dt.tzinfo:
            out.append(dt)
    return out


def walk(get, feed, day, reach, lines, info, missing_is_failure=False):
    """Read one date newest first, appending each body as a JSONL line. missing_is_failure: a 404 on page 1 fails
    the feed (today's WBGT or rainfall from 01:00 SGT, when readings must exist)."""
    url, fixed, _, _ = bf.FEEDS[feed]
    params = {**fixed, "date": day.isoformat()}
    for page in range(1, bf.MAX_PAGES + 1):
        status, content = get(url, params)
        if status == 404:
            if page > 1 or missing_is_failure:
                raise FeedError(f"{feed} {day}: HTTP 404 on page {page}")
            info["no_data"].append(day.isoformat())
            return
        if not bf.check_line(content):
            raise FeedError(f"{feed} {day} page {page}: the response body contains a line break")
        line = content if content.endswith(b"\n") else content + b"\n"
        try:
            body = json.loads(line)
        except ValueError:
            raise FeedError(f"{feed} {day} page {page}: response is not JSON")
        data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), dict) else {}
        lines.append(line)
        stamps = instants(feed, data)
        info["pages"] += 1
        info["stamps"] += len(stamps)
        info["other_date"] += sum(1 for s in stamps if s.astimezone(SGT).date() != day)
        if stamps:
            info["oldest"] = min([s for s in (info["oldest"], min(stamps)) if s])
            info["newest"] = max([s for s in (info["newest"], max(stamps)) if s])
        token = data.get("paginationToken")
        if not token or (reach is not None and stamps and min(stamps) <= reach):
            return
        params = {**fixed, "date": day.isoformat(), "paginationToken": token}
    raise FeedError(f"{feed} {day}: more than {bf.MAX_PAGES} pages")


def rel_path(feed, start, run_id):
    return f"{feed}/live/{start:%Y-%m-%d}/{feed}_{start:%Y-%m-%dT%H%M%S}_{run_id}.jsonl"


def write_local(out_dir, rel, data):
    path = out_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".partial")
    part.write_bytes(data)
    os.replace(part, path)
    return path


def files_api_uploader(env):
    """One Files API PUT per file, overwrite=false. The principal needs READ_VOLUME and WRITE_VOLUME on the Volume
    (the upload failed with WRITE_VOLUME alone), USE_SCHEMA, USE_CATALOG and the Consumer entitlement; the OAuth
    secret needs the all-apis scope. The collector itself makes no listing or metadata call (the SDK's newer
    files.upload may probe or go multipart, so the plain generated method is used)."""
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.files import FilesAPI
    host, client_id, secret = (env[k] for k in DBX_ENV)
    w = WorkspaceClient(host=host, client_id=client_id, client_secret=secret, auth_type="oauth-m2m")
    api = FilesAPI(w.api_client)

    def upload(dest, data):
        api.upload(dest, io.BytesIO(data), overwrite=False)
    return upload


def out_dir_problem(out):
    raw = (bf.DEFAULT_OUT / "raw").resolve()
    for bad, why in ((bf.REPO, "the repo"), (raw, "coolcheck-data/raw (upload_raw.py uploads it)")):
        if out == bad or bad in out.parents:
            return f"--out-dir must be outside {why}: {bad}"
    return None


def summary_md(rows, start, run_id, dry_run, fetcher, stop, elapsed):
    lines = [f"### Collector run {run_id} ({start:%Y-%m-%d %H:%M:%S} SGT){' - dry run, nothing uploaded' if dry_run else ''}",
             "", "| feed | dates read | pages | readings | oldest (SGT) | newest (SGT) | file | bytes | result |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        fmt = (lambda t: f"{t.astimezone(SGT):%m-%d %H:%M}" if t else "")
        lines.append(f"| {r['feed']} | {r['dates']} | {r['pages']} | {r['stamps']} | {fmt(r['oldest'])} | "
                     f"{fmt(r['newest'])} | {r['file'] or ''} | {r['bytes']} | {r['result']} |")
    lines += ["", f"Calls {fetcher.calls}, retries {fetcher.retries}, HTTP statuses {dict(fetcher.statuses)}, "
                  f"elapsed {elapsed:.1f} s.{' Stopped: ' + stop if stop else ''}"]
    return "\n".join(lines) + "\n"


def main(argv=None, session=None, sleep=time.sleep, clock=time.monotonic, now=None, env=None, uploader=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--window-hours", type=float, default=WINDOW_HOURS)
    ap.add_argument("--dry-run", action="store_true", help="write files under --out-dir only; no Databricks call")
    args = ap.parse_args(argv)

    env = os.environ if env is None else env
    key = env.get(bf.KEY_ENV) or None
    out = Path(args.out_dir).resolve()
    run_id = env.get("GITHUB_RUN_ID") or "local"
    root = (env.get(ROOT_ENV) or "").rstrip("/")
    problems = []
    if (msg := out_dir_problem(out)):
        problems.append(msg)
    if not 0 < args.window_hours <= MAX_WINDOW_HOURS:
        problems.append(f"--window-hours must be above 0 and at most {MAX_WINDOW_HOURS}")
    if not RUN_ID_RE.match(run_id):
        problems.append("GITHUB_RUN_ID has unexpected characters")
    if not args.dry_run:
        if not ROOT_RE.match(root):
            problems.append(f"{ROOT_ENV} must look like /Volumes/<catalog>/<schema>/<volume>")
        missing = [k for k in DBX_ENV if not env.get(k)]
        if missing and uploader is None:
            problems.append(f"not set: {', '.join(missing)} (needed to upload; use --dry-run to write locally)")
    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        return 2

    out.mkdir(parents=True, exist_ok=True)
    log = Log(out / "collector.log", secrets=[key, env.get("DATABRICKS_CLIENT_SECRET")])
    start = (now or datetime.now(SGT)).astimezone(SGT).replace(microsecond=0)
    dates = plan(start, args.window_hours)
    log(f"collector run {run_id}: start {start:%Y-%m-%d %H:%M:%S} SGT, window {args.window_hours:g} h, "
        f"{'dry run, out-dir ' + str(out) if args.dry_run else 'upload to ' + root}, key {'present' if key else 'absent'}")
    log("dates: " + ", ".join(f"{d} {'every page' if r is None else 'back to ' + f'{r:%H:%M}'}" for d, r in dates))

    fetcher = bf.Fetcher(session or bf.make_session(key), key_present=bool(key), sleep=sleep, clock=clock,
                         backoff=BACKOFF)
    guard = Guard(fetcher, clock)
    if not args.dry_run and uploader is None:
        try:
            uploader = files_api_uploader(env)
        except Exception as e:
            log(f"STOPPED: cannot set up the Databricks client: {type(e).__name__}: {str(e)[:200]}")
            return 1
    stop, failed, rows = None, False, []
    for feed in bf.ORDER:
        info = {"feed": feed, "pages": 0, "stamps": 0, "other_date": 0, "oldest": None, "newest": None,
                "no_data": [], "file": None, "bytes": 0, "result": "ok",
                "dates": "; ".join(f"{d:%m-%d}{' all' if r is None else ''}" for d, r in dates)}
        rows.append(info)
        if stop:
            info["result"] = "not fetched (run stopped)"
            continue
        lines = []
        try:
            for day, reach in dates:
                strict = feed != "forecast" and day == start.date() and start.hour >= 1
                walk(guard.get, feed, day, reach, lines, info, missing_is_failure=strict)
        except FeedError as e:
            info["result"], failed = f"failed: {e}", True
        except StopRun as e:
            stop, failed = str(e), True
            info["result"] = f"stopped: {e}"
        if lines:
            data = b"".join(lines)
            rel = rel_path(feed, start, run_id)
            write_local(out, rel, data)
            info["file"], info["bytes"] = rel.rsplit("/", 1)[1], len(data)
            if not args.dry_run:
                try:
                    uploader(f"{root}/{rel}", data)
                except Exception as e:  # a name clash or an auth/permission error; never print the request
                    info["result"], failed = f"upload failed: {type(e).__name__}: {str(e)[:200]}", True
        span = (f"{info['oldest'].astimezone(SGT):%m-%d %H:%M} to {info['newest'].astimezone(SGT):%m-%d %H:%M}"
                if info["oldest"] else "-")
        log(f"{feed}: pages {info['pages']}, readings {info['stamps']} ({span} SGT), other-date {info['other_date']}, "
            f"no data {info['no_data'] or '-'}, file {info['file'] or '-'} ({info['bytes']:,} bytes): {info['result']}")

    elapsed = clock() - guard.t0
    md = summary_md(rows, start, run_id, args.dry_run, fetcher, stop, elapsed)
    log(f"calls {fetcher.calls}; retries {fetcher.retries}; HTTP statuses {dict(fetcher.statuses)}; "
        f"elapsed {elapsed:.1f} s{'; STOPPED: ' + stop if stop else ''}")
    if env.get("GITHUB_STEP_SUMMARY"):
        with open(env["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(log.scrub(md))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
