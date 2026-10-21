"""Geocode the residential HDB blocks with OneMap's search API (H12, D5): resumable, one search call per block, more
only when the block is not on the first page of results.

Input: HDB Property Information (coolcheck-data/static/hdb_property_information), the rows with residential = Y and
total_dwelling_units above 0 (10,817 blocks; blk_no plus street is unique). The 637 blocks with any rental flat
(1room_rental, 2room_rental, 3room_rental or other_room_rental above 0) go first, then the rest, each in file order.
Query as in check 5: searchVal "<blk_no> <street>", returnGeom=Y, getAddrDetails=Y, pageNum=1. When page 1 holds no
candidate (below) and totalNumPages is above 1, pages 2 to 5 are read in turn, stopping at the first page with one.

Matching, without guessing. A result is a candidate when its BLK_NO equals the block number and its ROAD_NAME equals
the street once both are normalised (upper case; full stops and apostrophes dropped; HDB's abbreviations expanded,
such as ST to STREET and C'WEALTH to COMMONWEALTH; a leading ST. read as SAINT). A kept record is a confirmed match
only if its POSTAL has 6 digits. Outcomes:
    matched             one candidate, with a postal code (confirmed)
    matched_same_place  several candidates at one place: at most one postal code among them and all within 50 m of
                        each other (check 5: 187 BISHAN ST 13 is listed as the block and as a family service centre
                        with postal NIL, 5 m away); the first candidate with the postal code is kept (confirmed)
    matched_postal_rule several candidates at different places, but exactly one distinct postal code among them ends
                        in the block number (its leading digits, zero-padded to three: 5 gives 005, 18C gives 018);
                        that candidate is kept and the others are listed as rejected in the report (confirmed). HDB
                        postal codes end in the block number: 10,746 of the 10,754 blocks matched without this rule
                        do (the exceptions are 1 TOH YI DR and The Pinnacle@Duxton, 1A to 1G CANTONMENT RD)
    matched_no_postal   one candidate, or several at one place, none with a postal code: the first is kept, flagged
                        confirmed = N with the note "address match through a tenant record" (the address is a
                        record of a tenant, not of the block); not a confirmed match
    ambiguous           several candidates at different places, and no one postal code or more than one fits the
                        rule above; nothing is kept
    not_found           no candidate on the pages read
progress.jsonl keeps every result seen, so a change to the matching is applied with --report-only, without calls.

Pace and stops: one call at a time, extra pages included, at most --rate calls a second (default 3). HTTP 429: a
fixed 30 s wait and at most 2 retries per call; the run stops at the 3rd 429 in a row. HTTP 401 or 403 stops the run
at once (401: the token was refused; the message gives its expiry). A 5xx or a failed connection is retried twice,
30 s apart, then stops the run. Any other status, or a body that is not a search result (OneMap reports a missing,
expired or invalid token with an "error" attribute), stops it at once. A block is recorded only once all its pages
are read, so a stop loses at most the block in flight, which a rerun fetches again from page 1.

Files under --out-dir (default coolcheck-data/geocode beside the repo; refused inside the repo or coolcheck-data/raw):
    progress.jsonl       append-only, one line per finished block: key, query, found, total pages, the pages read,
                         every result seen on them, the calls the block took
    runs.jsonl           append-only, one line per run: calls (and those for pages 2 to 5), retries, HTTP statuses,
                         outcomes, why it stopped
    geocoded_blocks.csv  one row per finished block, in input order: the outcome, whether it is confirmed, and the
                         kept record's fields
    report.md            counts per outcome, checks, the runs (with the extra calls), and the blocks not plainly
                         matched, those without a postal code listed with their building names
    geocode.log, geocode.lock
A rerun skips finished blocks, so a run is safe to stop (Ctrl+C) and restart.

The token comes only from the environment variable ONEMAP_TOKEN and is sent only as the Authorization header. It is
never printed, logged or written: only its expiry (the JWT exp claim, no other claim) is reported, and every log line,
stop message and progress line is scrubbed of it as well.

Run from the repo root:
    .venv\\Scripts\\python scripts/static/geocode_hdb.py --limit 20 --out-dir ..\\coolcheck-data\\geocode\\dryrun_20b
    .venv\\Scripts\\python scripts/static/geocode_hdb.py                   the full run; rerun the same to resume
    .venv\\Scripts\\python scripts/static/geocode_hdb.py --report-only     rebuild the CSV and the report; no calls
"""
import argparse
import base64
import csv
import io
import json
import math
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

SGT = ZoneInfo("Asia/Singapore")
REPO = Path(__file__).resolve().parents[2]
DATA = REPO.parent / "coolcheck-data"
HDB_CSV = DATA / "static/hdb_property_information/d_17f5382f26140b1fdae0ba2ef6239d2f.csv"
DEFAULT_OUT = DATA / "geocode"
SEARCH = "https://www.onemap.gov.sg/api/common/elastic/search"
GET_TOKEN = "https://www.onemap.gov.sg/api/auth/post/getToken"
TOKEN_ENV = "ONEMAP_TOKEN"
USER_AGENT = "coolcheck-geocode"
RENTAL = ("1room_rental", "2room_rental", "3room_rental", "other_room_rental")
RATE = 3.0
MAX_RATE = 4.0  # the pace agreed on 21 Oct: start at 2 to 4 calls a second
MAX_PAGE = 5
WAIT_S = 30
RETRIES = 2
MAX_429_IN_A_ROW = 3
TIMEOUT = 30
SAME_PLACE_M = 50.0
SUMMARY_EVERY = 250
LIST_MAX = 200
POSTAL_RE = re.compile(r"\d{6}")
SG_BOX = (1.13, 1.48, 103.59, 104.10)  # latitude from, to; longitude from, to: loosely around Singapore
OUTCOMES = ("matched", "matched_same_place", "matched_postal_rule", "matched_no_postal", "ambiguous", "not_found")
CONFIRMED = ("matched", "matched_same_place", "matched_postal_rule")
NOTES = {"matched_no_postal": "address match through a tenant record",
         "matched_postal_rule": "postal code ends in the block number; the other candidates were rejected"}
# every abbreviation in the street column of the 10,817 blocks, with OneMap's spelling
ABBR = {"AVE": "AVENUE", "BT": "BUKIT", "CL": "CLOSE", "CRES": "CRESCENT", "CTRL": "CENTRAL", "CWEALTH": "COMMONWEALTH",
        "DR": "DRIVE", "GDN": "GARDEN", "GDNS": "GARDENS", "HTS": "HEIGHTS", "JLN": "JALAN", "KG": "KAMPONG",
        "LOR": "LORONG", "MKT": "MARKET", "NTH": "NORTH", "PK": "PARK", "PL": "PLACE", "RD": "ROAD", "SQ": "SQUARE",
        "ST": "STREET", "STH": "SOUTH", "TER": "TERRACE", "TG": "TANJONG", "UPP": "UPPER"}
FIELDS = ("SEARCHVAL", "BLK_NO", "ROAD_NAME", "POSTAL", "LATITUDE", "LONGITUDE", "X", "Y")
CSV_COLUMNS = (["blk_no", "street", "rental_block", "outcome", "confirmed", "found", "total_pages", "pages_read",
                "candidates"] + [f"onemap_{f.lower()}" for f in FIELDS] + ["note", "fetched_at"])
RENEW = (f"Get a new token (POST the account email and password to {GET_TOKEN}), set {TOKEN_ENV} again and rerun; "
         "finished blocks are kept")


class Stop(Exception):
    """Stops the run; finished blocks are kept."""


class Log:
    """Console + geocode.log with SGT time stamps; every message is scrubbed of the token first."""

    def __init__(self, path, secret=None):
        self.path, self._secret = path, secret

    def scrub(self, text):
        return text.replace(self._secret, "***") if self._secret else text

    def __call__(self, msg):
        line = f"{datetime.now(SGT):%Y-%m-%d %H:%M:%S} {self.scrub(msg)}"
        print(line, flush=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


# ---- input ----

def load_blocks(path):
    """Residential blocks with dwelling units: those with any rental flat first, then the rest, each in file order."""
    with open(path, encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["residential"] == "Y" and int(r["total_dwelling_units"] or 0) > 0]
    blocks = [{"key": f"{r['blk_no']}|{r['street']}", "blk_no": r["blk_no"], "street": r["street"],
               "query": f"{r['blk_no']} {r['street']}", "rental": any(int(r[c] or 0) > 0 for c in RENTAL)}
              for r in rows]
    dup = [k for k, n in Counter(b["key"] for b in blocks).items() if n > 1]
    if dup:
        raise ValueError("blk_no plus street is not unique: " + ", ".join(k.replace("|", " ") for k in dup[:5]))
    return [b for b in blocks if b["rental"]] + [b for b in blocks if not b["rental"]]


# ---- matching ----

def norm_road(name):
    """Upper case, full stops and apostrophes dropped, abbreviations expanded and a leading ST read as SAINT, so that
    HDB's "ST. GEORGE'S RD" and OneMap's "SAINT GEORGE'S ROAD" compare equal."""
    words = [w for w in (w.replace(".", "").replace("'", "").replace("’", "") for w in name.upper().split()) if w]
    return " ".join("SAINT" if i == 0 and w == "ST" else ABBR.get(w, w) for i, w in enumerate(words))


def has_postal(r):
    return bool(POSTAL_RE.fullmatch(str(r.get("POSTAL", ""))))


def spread_m(results):
    """The largest distance in metres between two results (OneMap's SVY21 X and Y); inf if a coordinate is missing."""
    try:
        pts = [(float(r["X"]), float(r["Y"])) for r in results]
    except (KeyError, TypeError, ValueError):
        return math.inf
    return max((math.dist(a, b) for i, a in enumerate(pts) for b in pts[i + 1:]), default=0.0)


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def candidates(blk_no, street, results):
    """The results whose BLK_NO is the block number and whose ROAD_NAME is the street, both normalised."""
    blk, road = blk_no.strip().upper(), norm_road(street)
    return [r for r in results if isinstance(r, dict) and str(r.get("BLK_NO", "")).strip().upper() == blk
            and norm_road(str(r.get("ROAD_NAME", ""))) == road]


def suffix_code(blk_no):
    """The block number's leading digits, zero-padded to three (5 gives 005, 18C gives 018), or None if it has none."""
    m = re.match(r"\d+", blk_no.strip())
    return m.group().zfill(3) if m else None

def postal_rule_pick(blk_no, cands):
    """The candidate to keep when exactly one distinct postal code among them ends in the block number, else None."""
    code = suffix_code(blk_no)
    fit = [r for r in cands if code and has_postal(r) and r["POSTAL"][-3:] == code]
    return fit[0] if len({r["POSTAL"] for r in fit}) == 1 else None

def classify(rec):
    """The outcome of one finished block, from its stored results (the rules are in the module docstring)."""
    cands = candidates(rec["blk_no"], rec["street"], rec["results"])
    out = {"outcome": "not_found", "candidates": len(cands), "kept": None, "rejected": [], "spread_m": None,
           "pages_left": (as_int(rec.get("total_pages")) or 1) > max(rec.get("pages_read") or [1])}
    if len(cands) > 1:
        out["spread_m"] = spread_m(cands)
        if len({r["POSTAL"] for r in cands if has_postal(r)}) > 1 or out["spread_m"] > SAME_PLACE_M:
            out["kept"] = postal_rule_pick(rec["blk_no"], cands)
            out["outcome"] = "matched_postal_rule" if out["kept"] else "ambiguous"
            out["rejected"] = [r for r in cands if r is not out["kept"]] if out["kept"] else []
            return out
    if cands:
        with_postal = [r for r in cands if has_postal(r)]
        out["kept"] = (with_postal or cands)[0]
        out["outcome"] = ("matched" if len(cands) == 1 else "matched_same_place") if with_postal else "matched_no_postal"
    return out


# ---- calls ----

def token_expiry(token):
    """The token's expiry from its JWT exp claim (no other claim is used), or None if it cannot be read."""
    try:
        payload = token.split(".")[1]
        exp = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["exp"]
        return datetime.fromtimestamp(int(exp), timezone.utc).astimezone(SGT)
    except Exception:
        return None


def error_detail(r):
    """A short reason from a failed response: its error attribute, or the start of the body."""
    try:
        body = json.loads(r.content)
    except ValueError:
        body = None
    if isinstance(body, dict) and "error" in body:
        return f" (error: {str(body['error'])[:200]})"
    text = r.content[:200].decode("utf-8", errors="replace").strip()
    return f" ({text})" if text else ""


def parse_search(content):
    """(body, None) for a search result, or (None, why it is not one)."""
    try:
        body = json.loads(content)
    except ValueError:
        return None, "the body is not JSON"
    if not isinstance(body, dict):
        return None, "the body is not a JSON object"
    if "error" in body:
        return None, f"the body has an error attribute ({str(body['error'])[:200]})"
    if as_int(body.get("found")) is None or not isinstance(body.get("results"), list):
        return None, "the body has no found count or no results list"
    return body, None


class Client:
    """Search calls one at a time, at most `rate` a second, with the retry and stop rules in the module docstring.
    calls counts every call (retries and pages 2 to 5 included); page_calls those for pages 2 to 5."""

    def __init__(self, session, rate, expiry, sleep=time.sleep, clock=time.monotonic, now=None):
        self.session, self.gap, self.expiry = session, 1.0 / rate, expiry
        self.sleep, self.clock, self.now = sleep, clock, now or (lambda: datetime.now(SGT))
        self.calls = self.page_calls = self.retries = self.in_a_row_429 = 0
        self.statuses = Counter()
        self._last = None

    def token_note(self):
        if self.expiry is None:
            return f"The token's expiry could not be read (OneMap tokens last 3 days and do not renew). {RENEW}."
        when = ("that time has passed" if self.now() >= self.expiry
                else "that time has not come, so the token may be mistyped or revoked")
        return f"The token in {TOKEN_ENV} expires {self.expiry:%d %b %Y %H:%M} SGT; {when}. {RENEW}."

    def _pace(self):
        if self._last is not None:
            gap = self.gap - (self.clock() - self._last)
            if gap > 0:
                self.sleep(gap)
        self._last = self.clock()

    def _wait(self):
        self.retries += 1
        self.sleep(WAIT_S)

    def search(self, query, page=1):
        """The body of a good search response for `query` and `page`; raises Stop."""
        params = {"searchVal": query, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": page}
        where = f"{query!r}" + (f" page {page}" if page > 1 else "")
        tries_429 = transient = 0
        while True:
            self._pace()
            self.calls += 1
            if page > 1:
                self.page_calls += 1
            try:
                r = self.session.get(SEARCH, params=params, timeout=TIMEOUT)
            except requests.RequestException as e:  # the type only: the message may quote the request
                self.statuses[type(e).__name__] += 1
                transient += 1
                if transient > RETRIES:
                    raise Stop(f"the connection failed at {where} ({type(e).__name__}) after {RETRIES} retries "
                               f"{WAIT_S} s apart; rerun later")
                self._wait()
                continue
            status = r.status_code
            self.statuses[status] += 1
            if status == 429:
                self.in_a_row_429 += 1
                if self.in_a_row_429 >= MAX_429_IN_A_ROW or tries_429 >= RETRIES:
                    raise Stop(f"{self.in_a_row_429} HTTP 429s in a row (API limit exceeded) at {where}, {WAIT_S} s "
                               "apart, so OneMap's limit is below this pace; rerun later, perhaps with a lower --rate")
                tries_429 += 1
                self._wait()
                continue
            self.in_a_row_429 = 0
            if status == 401:
                raise Stop(f"HTTP 401 at {where}: OneMap refused the token{error_detail(r)}. {self.token_note()}")
            if status == 403:
                raise Stop(f"HTTP 403 at {where}: OneMap refused access{error_detail(r)}. The token may not allow "
                           "Search, or OneMap may have blocked this client; find out which before rerunning")
            if status >= 500:
                transient += 1
                if transient > RETRIES:
                    raise Stop(f"HTTP {status} at {where}{error_detail(r)} after {RETRIES} retries {WAIT_S} s apart; "
                               "rerun later")
                self._wait()
                continue
            if status != 200:
                raise Stop(f"unexpected HTTP {status} at {where}{error_detail(r)}")
            body, why = parse_search(r.content)
            if why:
                note = (f" OneMap reports a missing, expired or invalid token this way. {self.token_note()}"
                        if "error attribute" in why else "")
                raise Stop(f"HTTP 200 at {where}, but {why}.{note}")
            return body


def fetch_block(client, b):
    """Page 1, then pages 2 to MAX_PAGE in turn while no result seen so far is a candidate. Returns the block's
    progress line; raises Stop, and then nothing of the block is recorded."""
    calls0 = client.calls
    first = client.search(b["query"])
    results, pages = list(first["results"]), [1]
    last = min(as_int(first.get("totalNumPages")) or 1, MAX_PAGE)
    while pages[-1] < last and not candidates(b["blk_no"], b["street"], results):
        pages.append(pages[-1] + 1)
        results += client.search(b["query"], pages[-1])["results"]
    return {"key": b["key"], "blk_no": b["blk_no"], "street": b["street"], "query": b["query"],
            "found": as_int(first["found"]), "total_pages": first.get("totalNumPages"), "pages_read": pages,
            "results": results, "calls": client.calls - calls0, "fetched_at": f"{datetime.now(SGT):%Y-%m-%dT%H:%M:%S%z}"}


# ---- files ----

def append_jsonl(path, rec, scrub=lambda s: s):
    """Append one JSON line and sync it to disk, so a finished block survives a crash right after."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(scrub(json.dumps(rec)) + "\n")
        f.flush()
        os.fsync(f.fileno())


def load_progress(path):
    """key -> the block's last line, and the count of lines that could not be read. A line cut short by a crash is
    ignored (its block is fetched again) and ended with a newline, so the next line starts clean."""
    done, bad = {}, 0
    if not path.exists():
        return done, bad
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        with open(path, "ab") as f:
            f.write(b"\n")
    for line in data.split(b"\n"):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            rec = None
        if (isinstance(rec, dict) and all(isinstance(rec.get(k), str) for k in ("key", "blk_no", "street"))
                and isinstance(rec.get("results"), list)):
            done[rec["key"]] = rec
        else:
            bad += 1
    return done, bad


def load_runs(path):
    runs = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                runs.append(json.loads(line))
            except ValueError:
                continue
    return runs


def write_atomic(path, text):
    part = path.with_name(path.name + ".partial")
    part.write_text(text, encoding="utf-8", newline="")
    os.replace(part, path)


def acquire_lock(path):
    """An exclusive lock on the out-dir, so that two runs never append to one progress file."""
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
        raise Stop("another geocoding run holds the lock on this out-dir")
    return f


def out_dir_problem(out):
    raw = (DATA / "raw").resolve()
    for bad, why in ((REPO, "the repo"), (raw, "coolcheck-data/raw")):
        if out == bad or bad in out.parents:
            return f"--out-dir must be outside {why}: {bad}"
    return None


# ---- outputs ----

def md(text):
    return str(text).replace("|", "\\|")


def name_of(r):
    """A record's building name, or its search value when the building is NIL."""
    b = str(r.get("BUILDING", "")).strip()
    return b if b and b != "NIL" else str(r.get("SEARCHVAL", ""))


def in_singapore(r):
    try:
        lat, lon = float(r["LATITUDE"]), float(r["LONGITUDE"])
    except (KeyError, TypeError, ValueError):
        return False
    return SG_BOX[0] <= lat <= SG_BOX[1] and SG_BOX[2] <= lon <= SG_BOX[3]


def counts_text(n):
    return ", ".join(f"{o} {n[o]:,}" for o in OUTCOMES if n[o]) or "none"


def csv_text(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    for b, rec, c in rows:
        kept = c["kept"] or {}
        w.writerow([b["blk_no"], b["street"], "Y" if b["rental"] else "N", c["outcome"],
                    "Y" if c["outcome"] in CONFIRMED else "N", rec.get("found"), rec.get("total_pages"),
                    len(rec.get("pages_read") or [1]), c["candidates"], *(kept.get(f, "") for f in FIELDS),
                    NOTES.get(c["outcome"], ""), rec.get("fetched_at")])
    return buf.getvalue()


def report_text(hdb_csv, blocks, rows, runs, unreadable, extra):
    n_rental = sum(b["rental"] for b in blocks)
    done_rental = sum(1 for b, _, _ in rows if b["rental"])
    by = Counter((c["outcome"], b["rental"]) for b, _, c in rows)
    confirmed = [(b, c) for b, _, c in rows if c["outcome"] in CONFIRMED]
    lines = [
        "# HDB block geocoding with OneMap search", "",
        f"Built {datetime.now(SGT):%Y-%m-%d %H:%M} SGT by `scripts/static/geocode_hdb.py` from `progress.jsonl`, with no "
        f"calls. Input `{Path(hdb_csv).name}`: {len(blocks):,} blocks with residential = Y and dwelling units above 0; "
        f"the {n_rental:,} with rental flats are fetched first. Query `<blk_no> <street>` with returnGeom=Y and "
        f"getAddrDetails=Y: page 1, then pages 2 to {MAX_PAGE} in turn only while no result matches the block.", "",
        "## Counts per outcome", "",
        "| outcome | rental blocks | other blocks | all |", "|---|---:|---:|---:|"]
    for o in OUTCOMES:
        lines.append(f"| {o} | {by[(o, True)]:,} | {by[(o, False)]:,} | {by[(o, True)] + by[(o, False)]:,} |")
    lines += [f"| not fetched yet | {n_rental - done_rental:,} | {len(blocks) - n_rental - (len(rows) - done_rental):,} "
              f"| {len(blocks) - len(rows):,} |",
              f"| total | {n_rental:,} | {len(blocks) - n_rental:,} | {len(blocks):,} |", "",
              f"Confirmed matches ({", ".join(CONFIRMED)}): {len(confirmed):,} of {len(rows):,} finished blocks, "
              f"{sum(b['rental'] for b, _ in confirmed):,} of them rental blocks.", "",
              "- matched: one result has the block number and the road, and a 6-digit postal code.",
              f"- matched_same_place: several do, at one place (at most one postal code among them, all within "
              f"{SAME_PLACE_M:g} m); the first with the postal code is kept.",
              "- matched_postal_rule: several do, at different places, but exactly one distinct postal code among them "
              "ends in the block number (its leading digits, zero-padded to three); that candidate is kept, the others "
              "are listed beside it as rejected.",
              f"- matched_no_postal: the only such result, or every one at one place, has no 6-digit postal code; the "
              f"first is kept in the CSV with confirmed = N and the note \"{NOTES['matched_no_postal']}\"; it is not a "
              "confirmed match.",
              "- ambiguous: several do, at different places, and no one postal code, or more than one, ends in the "
              "block number; nothing is kept.",
              "- not_found: none does, on the pages read.", ""]
    multi = [(rec, c) for _, rec, c in rows if (as_int(rec.get("total_pages")) or 1) > 1]
    paged = [(rec, c) for _, rec, c in rows if len(rec.get("pages_read") or [1]) > 1]
    lines += ["## Checks", "",
              f"- Confirmed records whose latitude or longitude is not a number or lies outside {SG_BOX[0]} to "
              f"{SG_BOX[1]} N, {SG_BOX[2]} to {SG_BOX[3]} E: {sum(not in_singapore(c['kept']) for _, c in confirmed):,}.",
              f"- Blocks with more than one page of results: {len(multi):,}. Of those, with a candidate on page 1, so no "
              f"later page read: {sum(1 for rec, c in multi if len(rec.get('pages_read') or [1]) == 1 and c['candidates']):,}.",
              f"- Blocks for which pages 2 to {MAX_PAGE} were read: {len(paged):,}; extra pages read: "
              f"{sum(len(rec['pages_read']) - 1 for rec, _ in paged):,}; of those blocks, with a candidate on the extra "
              f"pages: {sum(1 for _, c in paged if c['candidates']):,}; with no candidate on pages 1 to {MAX_PAGE} and "
              f"pages left unread: {sum(1 for _, c in paged if not c['candidates'] and c['pages_left']):,}.",
              f"- Lines in progress.jsonl that could not be read: {unreadable:,}. Finished blocks not in the input: "
              f"{extra:,}.", "",
              "## Runs", "",
              f"| started (SGT) | blocks | calls | of them for pages 2 to {MAX_PAGE} | retries | HTTP statuses | seconds "
              "| result |", "|---|---:|---:|---:|---:|---|---:|---|"]
    for r in runs:
        lines.append(f"| {r.get('started_at')} | {r.get('blocks', 0):,} | {r.get('calls', 0):,} | "
                     f"{r.get('page_calls', 0):,} | {r.get('retries', 0):,} | {md(json.dumps(r.get('statuses', {})))} | "
                     f"{r.get('elapsed_s')} | {md(r.get('stopped') or 'finished')} |")
    if len(runs) > 1:
        lines.append(f"| all {len(runs)} runs | {sum(r.get('blocks', 0) for r in runs):,} | "
                     f"{sum(r.get('calls', 0) for r in runs):,} | {sum(r.get('page_calls', 0) for r in runs):,} | "
                     f"{sum(r.get('retries', 0) for r in runs):,} | | "
                     f"{round(sum(r.get('elapsed_s') or 0 for r in runs), 1)} | |")
    for o in ("ambiguous", "not_found", "matched_no_postal", "matched_postal_rule", "matched_same_place"):
        sel = [(b, rec, c) for b, rec, c in rows if c["outcome"] == o]
        lines += ["", f"## {o} ({len(sel):,})", ""]
        if not sel:
            lines.append("None.")
            continue
        if o in NOTES:
            lines += [f"Note on each: {NOTES[o]}.", ""]
        if o == "matched_postal_rule":
            lines += ["| block | kept: POSTAL, BUILDING | rejected: BLK_NO, ROAD_NAME, POSTAL, BUILDING |",
                      "|---|---|---|"]
            for b, rec, c in sel[:LIST_MAX]:
                rej = "; ".join(", ".join(str(x.get(k, "")) for k in ("BLK_NO", "ROAD_NAME", "POSTAL", "BUILDING"))
                                for x in c["rejected"])
                lines.append(f"| {md(b['query'])} | {md(c['kept'].get('POSTAL'))}, {md(name_of(c['kept']))} | {md(rej)} |")
            if len(sel) > LIST_MAX:
                lines += ["", f"{len(sel) - LIST_MAX:,} more are in geocoded_blocks.csv and progress.jsonl."]
            continue
        what = "first results seen" if o == "not_found" else "candidates"
        lines += [f"| block | found | pages read | spread m | kept record: building | {what}: BLK_NO, ROAD_NAME, "
                  "POSTAL, BUILDING |", "|---|---:|---:|---:|---|---|"]
        for b, rec, c in sel[:LIST_MAX]:
            res = (candidates(rec["blk_no"], rec["street"], rec["results"]) if c["candidates"]
                   else [x for x in rec["results"] if isinstance(x, dict)])
            shown = "; ".join(", ".join(str(x.get(k, "")) for k in ("BLK_NO", "ROAD_NAME", "POSTAL", "BUILDING"))
                              for x in res[:4]) + (f"; and {len(res) - 4} more" if len(res) > 4 else "")
            sp = c["spread_m"]
            sp = "" if sp is None else "n/a" if math.isinf(sp) else f"{sp:.0f}"
            kept = name_of(c["kept"]) if c["kept"] else ""
            lines.append(f"| {md(b['query'])} | {rec.get('found')} | {len(rec.get('pages_read') or [1])} of "
                         f"{rec.get('total_pages')} | {sp} | {md(kept)} | {md(shown)} |")
        if len(sel) > LIST_MAX:
            lines += ["", f"{len(sel) - LIST_MAX:,} more are in geocoded_blocks.csv and progress.jsonl."]
    return "\n".join(lines) + "\n"


def write_outputs(out, hdb_csv, blocks, done, unreadable, log):
    """Rebuild geocoded_blocks.csv and report.md from every finished block; returns the counts per outcome."""
    rows = [(b, done[b["key"]], classify(done[b["key"]])) for b in blocks if b["key"] in done]
    extra = len(set(done) - {b["key"] for b in blocks})
    try:
        write_atomic(out / "geocoded_blocks.csv", log.scrub(csv_text(rows)))
        write_atomic(out / "report.md", log.scrub(report_text(hdb_csv, blocks, rows, load_runs(out / "runs.jsonl"),
                                                              unreadable, extra)))
    except OSError as e:
        log(f"could not write the CSV or the report ({type(e).__name__}; is one open in another program?); "
            "rebuild them with --report-only")
    return Counter(c["outcome"] for _, _, c in rows)


def block_line(i, n, b, rec, c):
    pages, total = rec.get("pages_read") or [1], as_int(rec.get("total_pages")) or 1
    s = f"[{i:,}/{n:,}] {b['query']}{' (rental)' if b['rental'] else ''}: found {rec['found']}"
    if total > 1:
        s += f" over {total} pages ({'page 1' if len(pages) == 1 else f'pages 1-{pages[-1]}'} read)"
    s += f", {c['outcome']}"
    if c["candidates"] > 1:
        sp = c["spread_m"]
        s += f" ({c['candidates']} candidates{'' if math.isinf(sp) else f', {sp:.0f} m apart'})"
    kept = c["kept"]
    if kept and c["outcome"] in CONFIRMED:
        s += f": {kept.get('POSTAL')} at {kept.get('LATITUDE')}, {kept.get('LONGITUDE')}"
        if c["rejected"]:
            s += f"; rejected postal codes {', '.join(str(x.get('POSTAL')) for x in c['rejected'])}"
    elif kept:
        s += (f": kept {name_of(kept)!r}, postal {kept.get('POSTAL')}, at {kept.get('LATITUDE')}, "
              f"{kept.get('LONGITUDE')}; not confirmed ({NOTES['matched_no_postal']})")
    if rec["calls"] > 1:
        s += f" [{rec['calls']} calls]"
    return s


# ---- run ----

def fetch_run(args, out, blocks, done, unreadable, token, log, session, sleep, clock, now):
    todo = [b for b in blocks if b["key"] not in done]
    left = len(todo)
    if args.limit:
        todo = todo[:args.limit]
    expiry = token_expiry(token)
    started = now()
    need_s = len(todo) / args.rate
    log(f"geocode: {len(blocks):,} blocks, the {sum(b['rental'] for b in blocks):,} with rental flats first; finished "
        f"{len(blocks) - left:,}; this run fetches {len(todo):,}{f' (--limit {args.limit})' if args.limit else ''} at "
        f"most {args.rate:g} calls a second (at least {need_s / 60:.1f} min); out-dir {out}; token present, expires "
        + (f"{expiry:%d %b %Y %H:%M} SGT" if expiry else "unknown (no exp claim)"))
    if expiry and expiry <= started:
        log(f"STOPPED before any call: the token in {TOKEN_ENV} expired {expiry:%d %b %Y %H:%M} SGT. {RENEW}.")
        return 2
    if expiry and (expiry - started).total_seconds() < need_s:
        log("warning: the token expires before this run can end; the run will stop at the first HTTP 401")
    sess = session or requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT, "Authorization": token})
    client = Client(sess, args.rate, expiry, sleep=sleep, clock=clock, now=now)
    t0, stop, n = clock(), None, Counter()
    try:
        for i, b in enumerate(todo, 1):
            rec = fetch_block(client, b)
            append_jsonl(out / "progress.jsonl", rec, scrub=log.scrub)
            done[b["key"]] = rec
            c = classify(rec)
            n[c["outcome"]] += 1
            log(block_line(i, len(todo), b, rec, c))
            if i % SUMMARY_EVERY == 0 and i < len(todo):
                pace = i / max(clock() - t0, 1e-9)
                log(f"-- {i:,} of {len(todo):,} this run: {counts_text(n)}; calls {client.calls:,} "
                    f"({client.page_calls:,} for pages 2 to {MAX_PAGE}), retries {client.retries:,}, HTTP 429s "
                    f"{client.statuses[429]:,}; {pace:.2f} blocks a second, about {(len(todo) - i) / pace / 60:.0f} min "
                    "to go")
    except Stop as e:
        stop = log.scrub(str(e))
    except KeyboardInterrupt:
        stop = "interrupted (Ctrl+C)"
    elapsed = clock() - t0
    append_jsonl(out / "runs.jsonl", {
        "started_at": f"{started:%Y-%m-%d %H:%M:%S}", "ended_at": f"{now():%Y-%m-%d %H:%M:%S}", "rate": args.rate,
        "limit": args.limit, "blocks": sum(n.values()), "outcomes": dict(n), "calls": client.calls,
        "page_calls": client.page_calls, "retries": client.retries,
        "statuses": {str(k): v for k, v in client.statuses.items()}, "elapsed_s": round(elapsed, 1), "stopped": stop},
        scrub=log.scrub)
    total = write_outputs(out, args.hdb_csv, blocks, done, unreadable, log)
    log(f"this run: {sum(n.values()):,} blocks ({counts_text(n)}) in {elapsed:.1f} s; calls {client.calls:,} "
        f"({client.page_calls:,} for pages 2 to {MAX_PAGE}), retries {client.retries:,}, HTTP statuses "
        f"{dict(client.statuses)}")
    log(f"all finished: {sum(total.values()):,} of {len(blocks):,} blocks ({counts_text(total)}), confirmed "
        f"{sum(total[o] for o in CONFIRMED):,}; report.md and geocoded_blocks.csv in {out}")
    if stop:
        log(f"STOPPED: {stop}. Finished blocks are kept in progress.jsonl; rerun the same command to resume.")
    return 1 if stop else 0


def main(argv=None, session=None, sleep=time.sleep, clock=time.monotonic, now=None, env=None):
    """session, sleep, clock and now (a function returning the current time) are for tests; env defaults to os.environ."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hdb-csv", default=str(HDB_CSV))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--limit", type=int, help="fetch at most this many unfinished blocks in this run")
    ap.add_argument("--rate", type=float, default=RATE, help=f"calls a second, above 0 and at most {MAX_RATE:g}")
    ap.add_argument("--report-only", action="store_true", help="rebuild the CSV and the report from progress.jsonl")
    args = ap.parse_args(argv)

    env = os.environ if env is None else env
    now = now or (lambda: datetime.now(SGT))
    out = Path(args.out_dir).resolve()
    token = (env.get(TOKEN_ENV) or "").strip()
    problems = []
    if (msg := out_dir_problem(out)):
        problems.append(msg)
    if not 0 < args.rate <= MAX_RATE:
        problems.append(f"--rate must be above 0 and at most {MAX_RATE:g} calls a second")
    if args.limit is not None and args.limit < 1:
        problems.append("--limit must be at least 1")
    if not args.report_only:
        if not token:
            problems.append(f"{TOKEN_ENV} is not set (the token is read from the environment only); nothing was called")
        elif " " in token or not (token.isascii() and token.isprintable()):
            problems.append(f"{TOKEN_ENV} holds a space or a character a token cannot have; set it to the token alone")
    try:
        blocks = load_blocks(args.hdb_csv)
    except (OSError, KeyError, ValueError) as e:
        problems.append(f"cannot use --hdb-csv {args.hdb_csv}: {type(e).__name__}: {e}")
        blocks = []
    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        return 2

    out.mkdir(parents=True, exist_ok=True)
    log = Log(out / "geocode.log", secret=token or None)
    try:
        lock = acquire_lock(out / "geocode.lock")
    except Stop as e:
        log(f"STOPPED: {e}")
        return 3
    try:
        done, unreadable = load_progress(out / "progress.jsonl")
        if unreadable:
            log(f"progress.jsonl: {unreadable:,} line(s) could not be read and are ignored; their blocks are fetched "
                "again")
        if args.report_only:
            n = write_outputs(out, args.hdb_csv, blocks, done, unreadable, log)
            log(f"report only, no calls: {sum(n.values()):,} of {len(blocks):,} blocks finished ({counts_text(n)}), "
                f"confirmed {sum(n[o] for o in CONFIRMED):,}; geocoded_blocks.csv and report.md rebuilt in {out}")
            return 0
        return fetch_run(args, out, blocks, done, unreadable, token, log, session, sleep, clock, now)
    finally:
        lock.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
