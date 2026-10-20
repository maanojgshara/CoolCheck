"""Day-1 check 9 part A: NEA WBGT and rainfall feeds from data.gov.sg (history depth, stations, volume, categories).

Public, unauthenticated calls only: no key or token is read, sent or written.
Run from the repo root: .venv\\Scripts\\python scripts/checks/check9_wbgt_rainfall.py --cache-dir <dir>
Throttled to 1 call/second, hard cap of 300 network calls (retries included), stops on a persistent 403/429.
Raw responses are cached in --cache-dir (keep it outside the repo); --cached-only rebuilds the report with no calls.
Every station reading fetched from the WBGT feed is also written to <cache-dir>/wbgt_readings.csv.
"""
import argparse
import csv
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path

from _common import SGT, CacheMiss, Client, StopRun, key_paths, months_between, parse_sgt, table

BASE = "https://api-open.data.gov.sg/v2/real-time/api/"
WBGT_CANDIDATES = [(BASE + "weather", {"api": "wbgt"}), (BASE + "wbgt", {}),
                   (BASE + "heat-stress", {}), (BASE + "wet-bulb-globe-temperature", {})]
RAIN_ENDPOINT = (BASE + "rainfall", {})
CAP = 300
RESERVE = 15  # kept free for retries while the optional pre-2023 sampling runs
FLOOR = date(2016, 1, 1)
PRESENT = ("OK", "OK_UTC", "PARTIAL")
ID_KEYS = ("station.id", "stationId", "station_id", "stationCode", "id", "deviceId")
VALUE_KEYS = ("value", "wbgt", "wbgtValue")
CATEGORY_RE = re.compile("categ|level|heat|stress|class|status", re.I)
THRESHOLD_RE = re.compile("thresh|cutoff|cut_off|range|limit|boundar", re.I)


# ---- reading accessors (field names are detected, not assumed; the report prints what was found) ----

def station_of(item):
    return next((str(item[k]) for k in ID_KEYS if item.get(k) is not None), None)


def value_of(item):
    """Numeric value; the WBGT feed sends it as a string (\"30.1\")."""
    for k in VALUE_KEYS:
        v = item.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                pass
    return None


def category_of(item, reading):
    for src in (item, {k: v for k, v in reading.items() if k not in ("data", "timestamp")}):
        for k, v in src.items():
            if isinstance(v, str) and CATEGORY_RE.search(k) and k not in ID_KEYS:
                return v
    return None


def category_key(item, reading):
    for src, label in ((item, "data[]"), ({k: v for k, v in reading.items() if k not in ("data", "timestamp")}, "reading")):
        for k, v in src.items():
            if isinstance(v, str) and CATEGORY_RE.search(k) and k not in ID_KEYS:
                return f"{label}.{k}"
    return None


def items_of(reading):
    return [i for i in (reading.get("data") or []) if isinstance(i, dict)]


def meta_id(m):
    return next((str(m[k]) for k in ("id", "stationId", "deviceId") if m.get(k) is not None), None)


# ---- fetching ----

class Feed:
    def __init__(self, name, url=None, params=None):
        self.name, self.url, self.params = name, url, params or {}
        self.earliest = None
        self.earliest_note = ""
        self.bisect_log, self.neighbours = [], []
        self.full_days = []


def flatten(d, prefix=""):
    """Scalar leaves of a nested dict, keys joined with dots (lists are dropped)."""
    out = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        elif not isinstance(v, list):
            out[key] = v
    return out


class Page:
    """One response page, normalised to readings = [{"timestamp", "data": [flat station items], ...}].

    Two shapes are handled: data.readings[].data[] (rainfall style, with data.stations) and
    data.records[] with item.readings[] (the WBGT feed: `datetime`, station.id, wbgt, heatStress).
    """

    def __init__(self, http, data, note=""):
        self.http, self.data, self.note = http, data if isinstance(data, dict) else {}, note
        self.shape = "readings" if "readings" in self.data else "records" if "records" in self.data else None
        self.meta = [m for m in (self.data.get("stations") or []) if isinstance(m, dict)]
        if self.shape == "records":
            self.readings = []
            for rec in (self.data.get("records") or []):
                if not isinstance(rec, dict):
                    continue
                item = rec.get("item") if isinstance(rec.get("item"), dict) else {}
                reading = {"timestamp": rec.get("datetime") or rec.get("timestamp"),
                           "data": [flatten(i) for i in (item.get("readings") or []) if isinstance(i, dict)]}
                reading.update({k: v for k, v in rec.items() if k not in ("datetime", "timestamp", "item") and not isinstance(v, (dict, list))})
                reading.update({f"item.{k}": v for k, v in item.items() if not isinstance(v, (dict, list))})
                self.readings.append(reading)
            seen = {}
            for r in self.readings:
                for i in r["data"]:
                    if i.get("station.id") is not None:
                        seen.setdefault(str(i["station.id"]), {"id": str(i["station.id"]), "name": i.get("station.name")})
            self.meta = list(seen.values())
        else:
            self.readings = [r for r in (self.data.get("readings") or []) if isinstance(r, dict)]
        self.token = self.data.get("paginationToken")


class Day:
    """First page of a dated call, classified against the requested date."""

    def __init__(self, feed, when, page, status, note, phase):
        self.feed, self.when, self.page, self.status, self.note, self.phase = feed, when, page, status, note, phase
        self.date = date.fromisoformat(when[:10])

    @property
    def present(self):
        return self.status in PRESENT


class Study:
    def __init__(self, client, today):
        self.c, self.today = client, today
        self.wbgt, self.rain = Feed("wbgt"), Feed("rainfall", *RAIN_ENDPOINT)
        self.days = {}
        self.rows = []  # one dict per WBGT station reading fetched
        self.row_keys = set()
        self.discovery = []
        self.probe = {}
        self.point_ok = False
        self.point_info = None
        self.station_days = []
        self.pre_planned = self.pre_sampled = 0
        self.sample_skipped = 0
        self.stop = None

    def page(self, feed, params):
        resp = self.c.get({**feed.params, **params}, url=feed.url)
        body = resp["body"] if isinstance(resp["body"], dict) else {}
        note = "" if resp["status"] == 200 else str(body.get("errorMsg") or body.get("name") or resp["text"])[:120]
        return Page(resp["status"], body.get("data"), note)

    def add_rows(self, feed, page):
        if feed.name != "wbgt":
            return
        for r in page.readings:
            ts = parse_sgt(r.get("timestamp"))
            for it in items_of(r):
                key = (r.get("timestamp"), station_of(it))
                if key in self.row_keys:
                    continue
                self.row_keys.add(key)
                self.rows.append({"timestamp_sgt": ts.isoformat() if ts else r.get("timestamp"), "station": station_of(it),
                                  "wbgt": value_of(it), "category": category_of(it, r)})

    def day(self, feed, when, phase):
        key = (feed.name, when)
        if key in self.days:
            return self.days[key]
        self.c.phase = phase
        pg = self.page(feed, {"date": when})
        d = date.fromisoformat(when[:10])
        if pg.http != 200:
            status, note = "ERROR", pg.note
        elif not pg.readings:
            status, note = "EMPTY", ""
        else:
            sgt = Counter(parse_sgt(r.get("timestamp")).date() for r in pg.readings if parse_sgt(r.get("timestamp")))
            utc = Counter(parse_sgt(r.get("timestamp")).astimezone(timezone.utc).date() for r in pg.readings if parse_sgt(r.get("timestamp")))
            if set(sgt) == {d}:
                status, note = "OK", ""
            elif set(utc) == {d}:
                status, note = "OK_UTC", "all readings are on the requested UTC date, not the SGT date"
            elif d in sgt or d in utc:
                status, note = "PARTIAL", f"SGT dates {sorted(map(str, sgt))}"
            else:
                status, note = "MISMATCH", f"SGT dates {sorted(map(str, sgt))}"
        self.add_rows(feed, pg)
        day = Day(feed.name, when, pg, status, note, phase)
        self.days[key] = day
        return day

    # ---- steps ----

    def step1_discover(self):
        self.c.phase = "1 probe"
        found = None
        for url, params in WBGT_CANDIDATES:
            self.wbgt.url, self.wbgt.params = url, params
            pg = self.page(self.wbgt, {})
            self.discovery.append((url + (f"?{next(iter(params))}={next(iter(params.values()))}" if params else ""),
                                   pg.http, len(pg.readings), sorted(pg.data.keys())[:6]))
            if pg.http == 200 and pg.readings:
                found = pg
                break
        if not found:
            raise StopRun("no WBGT endpoint candidate returned readings: " + json.dumps(self.discovery))
        self.probe["wbgt"] = found
        self.add_rows(self.wbgt, found)
        pr = self.page(self.rain, {})
        if pr.http != 200 or not pr.readings:
            raise StopRun(f"rainfall probe gave HTTP {pr.http}, {len(pr.readings)} readings")
        self.probe["rainfall"] = pr
        yest = self.today - timedelta(days=1)
        when = f"{yest.isoformat()}T13:00:00"
        pt = self.day(self.wbgt, when, "1 probe")
        near = [abs((parse_sgt(r["timestamp"]) - datetime.combine(yest, dtime(13, 0), SGT)).total_seconds()) / 60
                for r in pt.page.readings if parse_sgt(r.get("timestamp"))]
        self.point_ok = bool(near) and min(near) <= 30 and pt.present
        times = [parse_sgt(r["timestamp"]) for r in pt.page.readings if parse_sgt(r.get("timestamp"))]
        self.point_info = {"status": pt.status, "n": len(pt.page.readings), "first": min(times) if times else None,
                           "last": max(times) if times else None, "closest_min": min(near) if near else None}

    def bisect(self, feed, phase):
        recent = self.day(feed, (self.today - timedelta(days=30)).isoformat(), phase)
        if not recent.present:
            raise StopRun(f"{feed.name}: date check failed for {recent.date}: {recent.status} {recent.note}; date= cannot be trusted")
        floor = self.day(feed, FLOOR.isoformat(), phase)
        if floor.present:
            feed.earliest, feed.earliest_note = FLOOR, f"records exist at the search floor ({floor.status}); true start is on or before it"
            return
        lo, hi = FLOOR, recent.date
        while (hi - lo).days > 1:
            mid = lo + (hi - lo) // 2
            day = self.day(feed, mid.isoformat(), phase)
            feed.bisect_log.append((mid, day.status))
            lo, hi = (lo, mid) if day.present else (mid, hi)
        feed.earliest = hi
        for back in (1, 7, 30):
            n = self.day(feed, (hi - timedelta(days=back)).isoformat(), phase)
            feed.neighbours.append((n.date, n.status))
        bad = [str(d) for d, s in feed.neighbours if s in PRESENT]
        feed.earliest_note = ("bisect assumes no gaps; days before it were present at " + ", ".join(bad) if bad
                              else "days 1, 7 and 30 before it are absent (consistent with a clean start)")

    def full_day(self, feed, d, phase, max_pages=40):
        self.c.phase = phase
        pages, token = [], None
        for _ in range(max_pages):
            params = {"date": d.isoformat()}
            if token:
                params["paginationToken"] = token
            pg = self.page(feed, params)
            pages.append(pg)
            if pg.http != 200:
                break
            self.add_rows(feed, pg)
            token = pg.token
            if not token:
                break
        feed.full_days.append((d, pages))
        return pages

    def step3_full_days(self):
        yest = self.today - timedelta(days=1)
        for feed in (self.wbgt, self.rain):
            old = date(2024, 6, 12)
            if old < feed.earliest:
                old = feed.earliest + timedelta(days=14)
            self.full_day(feed, yest, f"3 full day {feed.name}")
            self.full_day(feed, old, f"3 full day {feed.name}")

    def split_timestamps(self):
        """Timestamps that appear on more than one page of the WBGT full-day pulls."""
        n = 0
        for _, pages in self.wbgt.full_days:
            ts = [r.get("timestamp") for pg in pages for r in pg.readings]
            n += len(ts) - len(set(ts))
        return n

    def step4_stations(self):
        start = max(date(2023, 1, 1), self.wbgt.earliest)
        for (y, m) in months_between((start.year, start.month), (self.today.year, self.today.month)):
            d = max(date(y, m, 15), start)
            if d >= self.today:
                continue
            if self.c.network_calls >= CAP - 5:
                self.sample_skipped += 1
                continue
            self.sample_station_day(d, "4 stations 2023-01 to today (1/month)")

    def sample_station_day(self, d, phase):
        when = f"{d.isoformat()}T13:00:00" if self.point_ok else d.isoformat()
        try:
            day = self.day(self.wbgt, when, phase)
        except CacheMiss:
            return
        self.station_days.append(day)

    def step5_pre2023(self):
        if self.wbgt.earliest >= date(2023, 1, 1):
            return
        dates, (y, m) = [], (self.wbgt.earliest.year, self.wbgt.earliest.month)
        while (y, m) < (2023, 1):
            if m in (1, 4, 7, 10):
                dates.append(max(date(y, m, 15), self.wbgt.earliest))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        self.pre_planned = len(dates)
        for d in dates:
            if self.c.network_calls >= CAP - RESERVE and not self.c.cached_only:
                break
            self.sample_station_day(d, "5 stations before 2023 (1/quarter)")
            self.pre_sampled += 1


# ---- analysis ----

def full_day_stats(feed, d, pages):
    readings = [r for pg in pages if pg.http == 200 for r in pg.readings]
    ts = sorted({parse_sgt(r.get("timestamp")) for r in readings if parse_sgt(r.get("timestamp"))})
    per_ts = [len({station_of(i) for i in items_of(r)} - {None}) for r in readings]
    union = {station_of(i) for r in readings for i in items_of(r)} - {None}
    gaps = [(b - a).total_seconds() / 60 for a, b in zip(ts, ts[1:])]
    return {
        "date": d, "pages": len(pages), "http": [pg.http for pg in pages][-1:], "readings": len(readings),
        "values": sum(len(items_of(r)) for r in readings), "page_sizes": [len(pg.readings) for pg in pages],
        "first": ts[0] if ts else None, "last": ts[-1] if ts else None,
        "median_gap": statistics.median(gaps) if gaps else None, "min_gap": min(gaps) if gaps else None,
        "max_gap": max(gaps) if gaps else None, "dup_ts": len(readings) - len(set(r.get("timestamp") for r in readings)),
        "per_ts": per_ts, "union": union, "meta": max((len(pg.meta) for pg in pages), default=0),
        "sgt_in": sum(t.date() == d for t in ts), "utc_in": sum(t.astimezone(timezone.utc).date() == d for t in ts),
        "token_end": bool(pages and pages[-1].token),
        "order": ("newest first" if pages and len(pages[0].readings) > 1
                  and parse_sgt(pages[0].readings[0].get("timestamp")) > parse_sgt(pages[0].readings[-1].get("timestamp")) else "oldest first"),
    }


def sec_endpoints(s):
    L = ["## Endpoints", "",
         "The WBGT endpoint is not stated in `DAISI.md`, `CoolCheck Project.md` or `smoke/` (grep found only the air-temperature path in `smoke/hello.py`), "
         "so candidates were tried in order until one returned readings:", ""]
    L += table(["candidate", "HTTP", "readings on page", "data keys"], [(f"`{u}`", h, n, k) for u, h, n, k in s.discovery])
    L.append("")
    w = s.wbgt
    L.append(f"- **WBGT: `{w.url}`" + (f" with `{w.params}`" if w.params else "") + f"**; **rainfall: `{s.rain.url}`**.")
    L.append("")
    return L


def sec_structure(s):
    L = ["## Response structure (latest call, no `date=`)", ""]
    for name in ("wbgt", "rainfall"):
        pg = s.probe[name]
        L.append(f"### {name}")
        L.append("")
        L.append(f"`data` keys: {sorted(pg.data.keys())}; readings on the first page: {len(pg.readings)}; "
                 f"`stations` in metadata: {len(pg.meta)}; paginationToken present: {bool(pg.token)}.")
        L.append("")
        paths = key_paths({k: v for k, v in pg.data.items() if k != "paginationToken"})
        shown = [kv for kv in paths.items() if not kv[0].startswith("stations[]")][:30] + [kv for kv in paths.items() if kv[0].startswith("stations[]")][:8]
        L += table(["path", "type", "example"], [(f"`{p}`", t, f"`{str(e)[:40]}`") for p, (t, e) in shown])
        L.append("")
        r0 = pg.readings[0]
        it = items_of(r0)[0] if items_of(r0) else {}
        L.append(f"Detected fields: station id = `{next((k for k in ID_KEYS if k in it), None)}`, value = "
                 f"`{next((k for k in VALUE_KEYS if k in it), None)}`, category = `{category_key(it, r0)}`.")
        thr = [p for p in paths if THRESHOLD_RE.search(p)]
        L.append(f"Paths that look like thresholds/cut-offs in the response: {thr or 'none'}.")
        L.append("")
    return L


def sec_datecheck(s):
    L = ["## Date check (every `date=` call, first page)", ""]
    cols = ["OK", "OK_UTC", "PARTIAL", "EMPTY", "MISMATCH", "ERROR"]
    rows, tot = [], Counter()
    by = defaultdict(Counter)
    for d in s.days.values():
        by[d.phase][d.status] += 1
    for ph, c in sorted(by.items()):
        rows.append((ph, sum(c.values()), *[c[k] for k in cols]))
        tot.update(c)
    rows.append(("**total**", sum(tot.values()), *[tot[k] for k in cols]))
    L += table(["phase", "calls", *cols], rows)
    L += ["", "OK = every reading's SGT date equals the requested date. OK_UTC = all readings fall on the requested UTC date instead. "
          "PARTIAL = requested date plus others. MISMATCH = readings returned, none on the requested date (API ignoring `date=`). "
          "EMPTY = HTTP 200 with no readings. ERROR = non-200.", ""]
    errs = Counter((d.feed, d.page.http, d.page.note) for d in s.days.values() if d.status == "ERROR")
    L.append("ERROR breakdown (feed, HTTP, message): " + (", ".join(f"{k}: {v}" for k, v in errs.items()) or "none") + ".")
    odd = [d for d in s.days.values() if d.status in ("PARTIAL", "MISMATCH", "OK_UTC")]
    if odd:
        L.append("")
        L.append("OK_UTC / PARTIAL / MISMATCH examples (first 10): " + "; ".join(f"{d.feed} {d.when}: {d.status} {d.note}" for d in odd[:10]))
    L.append("")
    pi = s.point_info
    if pi:
        L.append(f"Datetime form `date=YYYY-MM-DDT13:00:00` (WBGT, yesterday): status {pi['status']}, {pi['n']} readings, "
                 f"first {pi['first']:%H:%M} last {pi['last']:%H:%M} SGT, closest to 13:00 by {pi['closest_min']:.0f} min → "
                 f"**{'usable as a point query, used for station sampling' if s.point_ok else 'not usable as a point query; station sampling used the first page of the day'}**."
                 if pi["first"] else f"Datetime form: status {pi['status']}, no readings; station sampling used the first page of the day.")
        L.append("")
    return L


def earliest_section(s, feed, title):
    L = [title, ""]
    if feed.earliest is None:
        return L + ["Not reached.", ""]
    L.append(f"- Earliest date with readings: **{feed.earliest}** ({feed.earliest_note}).")
    if feed.bisect_log:
        L.append("- Bisect probes: " + ", ".join(f"{d}: {st}" for d, st in feed.bisect_log))
    if feed.neighbours:
        L.append("- Neighbour probes before it: " + ", ".join(f"{d}: {st}" for d, st in feed.neighbours))
    day = next((d for (name, when), d in s.days.items() if name == feed.name and when == feed.earliest.isoformat()), None)
    if day is not None and day.present:
        ts = sorted(parse_sgt(r["timestamp"]) for r in day.page.readings if parse_sgt(r.get("timestamp")))
        if day.page.token is None:
            L.append(f"- On {feed.earliest} the page holds all of that day's {len(ts)} reading(s), {ts[0]:%H:%M} to {ts[-1]:%H:%M} SGT, "
                     f"so the first day is {'partial' if ts[0].hour > 0 or ts[0].minute > 0 else 'complete from midnight'}.")
        else:
            L.append(f"- On {feed.earliest} only the first page was fetched ({len(ts)} readings, {ts[0]:%H:%M} to {ts[-1]:%H:%M} SGT, newest first), "
                     "so whether that first day is complete was not checked.")
    L.append("")
    return L


def sec_q2(s):
    L = ["## Q2. WBGT station count over time", ""]
    days = sorted(s.station_days, key=lambda d: d.date)
    if not days:
        return L + ["Not reached.", ""]
    split = s.split_timestamps()
    L.append(f"Method: {'point query at 13:00 SGT (the page returned is the 25 readings up to 13:00, newest first)' if s.point_ok else 'first page of the day'}, "
             f"1 call per sampled day. Stations are counted from the station values inside the readings (distinct IDs). The WBGT response has no separate "
             f"station list, so 'stations in metadata' is derived from the same readings. "
             f"Full-day pulls show {split} timestamp(s) split across pages, so one page "
             f"{'holds every station for a timestamp' if split == 0 else 'does NOT always hold every station for a timestamp'}.")
    L.append("")
    seen, first_seen, names, rows = set(), {}, {}, []
    # first-seen dates use every dated WBGT page fetched (bisect probes, full days, samples), not only the monthly samples
    dated = ([(d.date, d.page) for d in s.days.values() if d.feed == "wbgt" and d.present]
             + [(dd, pg) for dd, ps in s.wbgt.full_days for pg in ps if pg.http == 200])
    for dd, pg_ in sorted(dated, key=lambda x: x[0]):
        for r in pg_.readings:
            for i in items_of(r):
                if station_of(i):
                    first_seen.setdefault(station_of(i), dd)
                    names.setdefault(station_of(i), i.get("station.name"))
    for d in days:
        pg = d.page
        for m in pg.meta:
            if meta_id(m):
                names.setdefault(meta_id(m), m.get("name"))
        union = {station_of(i) for r in pg.readings for i in items_of(r)} - {None}
        nearest = None
        if pg.readings:
            tgt = datetime.combine(d.date, dtime(13, 0), SGT)
            nearest = min(pg.readings, key=lambda r: abs((parse_sgt(r["timestamp"]) - tgt).total_seconds()) if parse_sgt(r.get("timestamp")) else 1e12)
        at_ts = {station_of(i) for i in items_of(nearest)} - {None} if nearest else set()
        new = sorted(union - seen)
        seen |= union
        rows.append((d.date, d.status, len(pg.readings), len(at_ts), len(union), len(pg.meta), len(new)))
    L += table(["sampled day", "date check", "readings on page", "stations at the chosen timestamp", "stations on the page", "stations in metadata", "first seen here"], rows)
    L.append("")
    counts = [r[3] for r in rows if r[1] in PRESENT]
    L.append(f"Stations at the chosen timestamp over {len(counts)} sampled days: min {min(counts)}, max {max(counts)}, "
             f"latest {counts[-1]}; distinct IDs seen in total: {len(first_seen)}.")
    ok_days = [d for d in days if d.status in PRESENT]
    latest_ids = {station_of(i) for r in ok_days[-1].page.readings for i in items_of(r)} - {None}
    gone = sorted(set(first_seen) - latest_ids)
    L.append(f"Seen at some point but absent from the latest sampled page: {', '.join(f'{g} ({names.get(g)})' for g in gone) or 'none'}. "
             "The 'first seen here' column counts IDs new to the monthly samples only; the first-seen table below also uses the bisect probes and full-day pulls.")
    errs_ = [d for d in days if d.status not in PRESENT]
    if errs_:
        L.append("Sampled days without data (" + ", ".join(f"{d.date}: {d.status} {d.page.note}" for d in errs_)
                 + "): the day's data starts after 13:00, so the point query found nothing.")
    L.append("")
    L.append("First date each station appears in any dated WBGT page fetched (accurate only to the sampling gap of about a month; a station may have appeared earlier between samples):")
    L.append("")
    L += table(["station id", "name", "first seen (any dated page fetched)"], [(st, names.get(st, ""), first_seen[st]) for st in sorted(first_seen, key=lambda x: (first_seen[x], x))])
    L.append("")
    if s.sample_skipped:
        L.append(f"Budget ran out: {s.sample_skipped} month(s) from 2023 were not sampled.")
    if s.pre_planned:
        L.append(f"Before 2023: {s.pre_sampled} of {s.pre_planned} quarterly samples taken with the leftover budget.")
    L.append("")
    return L


def sec_q3(s):
    L = ["## Q3. Calls and records per day (full-day pulls, following pagination)", ""]
    rows, stats = [], []
    for feed in (s.wbgt, s.rain):
        for d, pages in feed.full_days:
            st = full_day_stats(feed, d, pages)
            st["feed"] = feed.name
            stats.append(st)
            per = st["per_ts"]
            rows.append((feed.name, d, st["pages"], "/".join(map(str, st["page_sizes"][:3])) + ("…" if st["pages"] > 3 else ""), st["readings"], st["values"],
                         f"{st['first']:%H:%M}–{st['last']:%H:%M}" if st["first"] else "–",
                         f"{st['min_gap']:.0f}/{st['median_gap']:.0f}/{st['max_gap']:.0f}" if st["median_gap"] is not None else "–",
                         f"{min(per)}/{statistics.median(per):.0f}/{max(per)}" if per else "–", st["dup_ts"]))
    L += table(["feed", "day", "calls (pages)", "readings per page (first 3)", "readings (timestamps)", "station values", "first–last SGT",
                "gap min/median/max (min)", "stations per timestamp min/median/max", "timestamps on >1 page"], rows)
    L.append("")
    for st in stats:
        sem = ("the SGT day" if st["sgt_in"] == st["readings"] and st["readings"] else
               "the UTC day" if st["utc_in"] == st["readings"] and st["readings"] else
               f"neither exactly (SGT-date readings {st['sgt_in']}, UTC-date {st['utc_in']} of {st['readings']})")
        complete = ""
        if st["median_gap"]:
            exp = round(1440 / st["median_gap"])
            complete = f"; expected about {exp} readings at a {st['median_gap']:.0f}-minute interval, got {st['readings']}"
        L.append(f"- {st['feed']} {st['date']}: `date=` returned {sem}; union of stations over the day {len(st['union'])}, "
                 f"metadata stations {st['meta']}; pages come back {st['order']}; last page still had a pagination token: {st['token_end']}{complete}.")
    L.append("")
    s.stats = stats
    return L


def sec_q4(s):
    L = ["## Q4. WBGT category field and values at the boundaries", ""]
    pg = s.probe["wbgt"]
    r0 = pg.readings[0]
    it = items_of(r0)[0] if items_of(r0) else {}
    L.append(f"Category field detected by name: `{category_key(it, r0)}`.")
    # string-valued leaf paths inside readings, whatever their name
    seen_paths = defaultdict(Counter)
    pages = [d.page for d in s.days.values() if d.feed == "wbgt"] + [pg for _, ps in s.wbgt.full_days for pg in ps] + [s.probe["wbgt"]]
    for pg_ in pages:
        for r in pg_.readings:
            for i in items_of(r):
                for k, v in i.items():
                    if isinstance(v, str) and k not in ID_KEYS:
                        seen_paths[f"readings[].data[].{k}"][v] += 1
            for k, v in r.items():
                if isinstance(v, str) and k != "timestamp":
                    seen_paths[f"readings[].{k}"][v] += 1
    low_card = {p: c for p, c in seen_paths.items() if len(c) <= 12}
    L.append("String fields inside readings with at most 12 distinct values (all pages fetched, first pages and full days): "
             + ("; ".join(f"`{p}` = {dict(c)}" for p, c in low_card.items()) or "none") + ".")
    L.append("")
    rows = [r for r in s.rows if r["wbgt"] is not None]
    nulls = sum(1 for r in s.rows if r["wbgt"] is None)
    null_cats = Counter(r["category"] for r in s.rows if r["wbgt"] is None)
    L.append(f"Station readings recorded: {len(s.rows)} distinct (timestamp, station) pairs from every WBGT page fetched "
             f"({nulls} without a numeric value; their category values: {dict(null_cats)}). Written to `wbgt_readings.csv` in the cache directory.")
    L.append("")
    by = defaultdict(list)
    for r in rows:
        by[r["category"]].append(r["wbgt"])
    if not any(k for k in by):
        L.append("**No category value could be paired with a WBGT value, so the boundary check could not be done.**")
        L.append("")
        return L
    order = sorted(by, key=lambda c: (c is None, min(by[c])))
    L += table(["category (exact value)", "readings", "min WBGT", "max WBGT"], [(repr(c), len(by[c]), f"{min(by[c]):.1f}", f"{max(by[c]):.1f}") for c in order])
    L.append("")
    named = [c for c in order if c]
    for lo, hi in zip(named, named[1:]):
        gap = min(by[hi]) - max(by[lo])
        L.append(f"- Boundary {lo!r} → {hi!r}: highest {lo!r} = {max(by[lo]):.1f}, lowest {hi!r} = {min(by[hi]):.1f} "
                 f"({'overlap' if gap < 0 else 'gap'} of {abs(gap):.1f})")
    high = next((c for c in named if c.lower() == "high"), None)
    L.append("")
    if high is None:
        L.append("**No `High` reading was seen in the data fetched, so the High boundary was not observed. Item 11 (High = WBGT ≥ 33 °C, C14) needs the backfill.**")
    else:
        below = [c for c in named if c != high and max(by[c]) < min(by[high])]
        lo_val = max(by[below[-1]]) if below else None
        L.append(f"`High` observed {len(by[high])} times; lowest High value {min(by[high]):.1f}; "
                 + (f"highest value in the category below ({below[-1]!r}) {lo_val:.1f}. " if below else "no lower category observed to bracket it. ")
                 + f"Against the project assumption (High ≥ 33.0): lowest High {'≥' if min(by[high]) >= 33.0 else '<'} 33.0"
                 + (f" and highest lower-category value {'<' if lo_val < 33.0 else '≥'} 33.0" if lo_val is not None else "")
                 + ". The cut-off is taken from these observed pairs, not coded; observed only on the days fetched.")
    L += ["", "No High-day counts are given: those need the full backfill (estimate below).", ""]
    return L


def sec_estimate(s):
    L = ["## Backfill size (D12)", ""]
    st = {(x["feed"], x["date"]): x for x in getattr(s, "stats", [])}
    if not st or s.wbgt.earliest is None or s.rain.earliest is None:
        return L + ["Not reached.", ""]
    yest = s.today - timedelta(days=1)
    c = s.c
    if c.cached_only:  # replay: the live counters are in stats.json
        live = json.loads((c.cache_dir / "stats.json").read_text(encoding="utf-8"))
        p429 = live["statuses"].get("429", 0) / live["network_calls"]
    else:
        p429 = (c.statuses.get(429, 0) / c.network_calls) if c.network_calls else 0.0
    forecast_start = date(2016, 3, 16)  # earliest 24-h forecast date, check 10
    start_w = s.wbgt.earliest
    feeds = [("wbgt", s.wbgt.earliest), ("rainfall", s.rain.earliest), ("24-h forecast", forecast_start)]
    rows, tot = [], [0, 0, 0]
    for name, own in feeds:
        if name == "24-h forecast":
            per, shown = 1, "1 (check 10: one request per date)"
        else:
            per_day = [x["pages"] for k, x in st.items() if k[0] == name and x["http"] == [200]]
            per = st[(name, yest)]["pages"] if (name, yest) in st else per_day[0]
            shown = "/".join(map(str, per_day))
        a_ = per * (s.today - start_w).days
        b_ = per * (s.today - max(own, date(2024, 1, 1))).days
        full = per * (s.today - own).days
        for i, v in enumerate((a_, b_, full)):
            tot[i] += v
        rows.append((name, shown, per, f"{a_:,}", f"{b_:,}", f"{full:,}"))
    rows.append(("**total**", "", "", f"**{tot[0]:,}**", f"**{tot[1]:,}**", f"**{tot[2]:,}**"))
    L += table(["feed", "calls on the measured days", "calls/day used (yesterday)",
                f"all feeds from the WBGT start ({start_w})", "from 2024-01-01, or the feed's own start if later", "each feed's full history"], rows)
    secs = lambda n: n * (1 + p429 * 5) / 3600
    L += ["", "WBGT has no readings before its start date, so the Plan's 'WBGT from January 2024' would spend calls on 404s; "
          "the model's labels cannot start before the WBGT start. "
          f"At 1 call/s with this run's 429 rate ({100 * p429:.0f}% of calls, each costing at least 5 s of back-off) the three scenarios take roughly "
          f"{secs(tot[0]):.1f} h, {secs(tot[1]):.1f} h and {secs(tot[2]):.1f} h. Assumes pages per day stay as measured and that a key does not change the limits; "
          "rainfall could be dropped if MSS daily records are cleared (M10).", ""]
    return L


def sec_notes(s):
    c = s.c
    if c.cached_only:
        stats = json.loads((c.cache_dir / "stats.json").read_text(encoding="utf-8"))
        net, ret, sts, ph, when = stats["network_calls"], stats["retries"], stats["statuses"], stats["phase_calls"], stats["run_time"]
        head = [f"Report regenerated from the cache ({c.cache_hits} cache reads, 0 new calls); figures below are from the live run."]
    else:
        net, ret, sts, ph, when = c.network_calls, c.retries, dict(c.statuses), dict(c.phase_calls), f"{datetime.now(SGT):%Y-%m-%d %H:%M} SGT"
        head = []
    dates = sorted(d.date for d in s.days.values())
    L = ["## Calls, range and limits", ""] + head + [""]
    L += table(["phase", "network calls"], [(p, n) for p, n in sorted(ph.items())] + [("**total**", net)])
    seeded = (json.loads((c.cache_dir / "stats.json").read_text(encoding="utf-8")).get("seeded_calls") if c.cached_only
              else getattr(c, "seeded_calls", 0))
    L += ["", f"- Network calls: {net} (cap {CAP}); retries after 429/403/5xx/connection errors: {ret}. HTTP status counts: {sts}."
          + (f" Includes {seeded} calls from a first attempt that stopped after probing, because the parser did not yet recognise the WBGT response shape." if seeded else ""),
          f"- Dated first-page calls: {len(s.days)}, from {dates[0]} to {dates[-1]}." if dates else "- No dated calls.",
          f"- Live run time: {when}. No key or token was used. Stop reason: {s.stop or 'none, ran to completion'}.",
          "", "**Not tested:**",
          "- High-day counts per month, and whether the three-class target is supportable: needs the full backfill (D6, §14.4).",
          "- Whether a key changes history depth, page size or rate limits.",
          "- Rainfall station counts over time, and rainfall values or categories.",
          "- Days not sampled: station counts use 1 day per month from 2023 and at most 1 per quarter before; stations that appear and "
          "disappear between samples are missed, and first-seen dates are only as precise as the sampling gap.",
          "- Station metadata beyond ID and name (locations, device types).",
          "- Whether history was revised after the original readings.",
          "- Whether the High boundary holds on days other than those fetched (see Q4 for what was observed).",
          ""]
    return L


def build(s):
    L = ["# Check 9 part A: WBGT and rainfall feeds (data.gov.sg)", "",
         "Unauthenticated calls. Script: `scripts/checks/check9_wbgt_rainfall.py`. Dates are SGT unless stated.", ""]
    if s.stop:
        L += [f"> **Run stopped early: {s.stop}.** Sections below are partial.", ""]
    parts = []
    if s.discovery:
        parts.append(lambda: sec_endpoints(s))
    if s.probe.get("wbgt") and s.probe.get("rainfall"):
        parts.append(lambda: sec_structure(s))
    parts += [lambda: sec_datecheck(s),
              lambda: earliest_section(s, s.wbgt, "## Q1. Earliest date with WBGT history"),
              lambda: sec_q2(s),
              lambda: sec_q3(s),
              lambda: sec_q4(s) if s.probe.get("wbgt") else [],
              lambda: earliest_section(s, s.rain, "## Q5. Rainfall: earliest date (records per day are in Q3)"),
              lambda: sec_estimate(s),
              lambda: sec_notes(s)]
    for fn in parts:
        try:
            L += fn()
        except Exception as e:
            L += [f"_Section could not be built: {type(e).__name__}: {e}_", ""]
    return "\n".join(L)


def write_rows(s, cache_dir):
    path = Path(cache_dir) / "wbgt_readings.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp_sgt", "station", "wbgt", "category"])
        w.writeheader()
        w.writerows(s.rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", required=True, help="outside the repo")
    ap.add_argument("--out", default="docs/checks/check9.md")
    ap.add_argument("--cached-only", action="store_true", help="rebuild the report from the cache, no network calls")
    args = ap.parse_args()

    client = Client(args.cache_dir, args.cached_only, url=None, cap=CAP, user_agent="coolcheck-check9")
    prior = client.cache_dir / "stats.json"
    if prior.exists() and not args.cached_only:
        # an earlier attempt on this cache already spent calls: count them against the cap and in the totals
        old = json.loads(prior.read_text(encoding="utf-8"))
        client.network_calls, client.retries = old["network_calls"], old["retries"]
        client.statuses = Counter({int(k): v for k, v in old["statuses"].items()})
        client.phase_calls = Counter(old["phase_calls"])
        client.seeded_calls = old.get("seeded_calls", 0) + old["network_calls"]
    s = Study(client, datetime.now(SGT).date())
    try:
        s.step1_discover()
        s.bisect(s.wbgt, "2 bisect wbgt")
        s.bisect(s.rain, "2 bisect rainfall")
        s.step3_full_days()
        s.step4_stations()
        s.step5_pre2023()
    except StopRun as e:
        s.stop = str(e)
    except CacheMiss as e:
        s.stop = f"cache miss in --cached-only mode: {e}"
    if not args.cached_only:
        c = s.c
        (c.cache_dir / "stats.json").write_text(json.dumps({
            "network_calls": c.network_calls, "retries": c.retries, "statuses": {str(k): v for k, v in c.statuses.items()},
            "phase_calls": dict(c.phase_calls), "run_time": f"{datetime.now(SGT):%Y-%m-%d %H:%M} SGT", "stop": s.stop,
            "seeded_calls": getattr(c, "seeded_calls", 0)}), encoding="utf-8")
    write_rows(s, args.cache_dir)
    text = build(s)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
