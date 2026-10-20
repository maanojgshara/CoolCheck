"""Day-1 check 10: NEA 24-hour forecast from data.gov.sg (schema, history depth, issue times).

Public, unauthenticated calls only: no key or token is read, sent or written.
Run from the repo root: .venv\\Scripts\\python scripts/checks/check10_forecast_history.py --cache-dir <dir>
Throttled to 1 call/second, hard cap of 300 network calls (retries included), stops on a
persistent 403/429. Raw responses are cached in --cache-dir so a rerun costs no calls.
"""
import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path

from _common import SGT, CacheMiss, Client, StopRun, hm, key_paths, months_between, parse_sgt, table

URL = "https://api-open.data.gov.sg/v2/real-time/api/twenty-four-hr-forecast"
CAP = 300
RETRY_RESERVE = 15
HISTORY_FLOOR = date(2016, 1, 1)
CUTOFF = dtime(21, 0)
PRESENT = ("OK", "PARTIAL")


def rec_key(rec):
    return (rec.get("timestamp"), rec.get("updatedTimestamp"))


class Day:
    def __init__(self, d, status, http, records, returned, note, phase):
        self.date, self.status, self.http = d, status, http
        self.records, self.returned, self.note, self.phase = records, returned, note, phase

    @property
    def present(self):
        return self.status in PRESENT


class Run:
    def __init__(self, client, today, field):
        self.c, self.today, self.field = client, today, field
        self.days = {}
        self.latest_resp = None
        self.latest_records = []
        self.earliest = None
        self.earliest_note = ""
        self.bisect_log = []
        self.neighbours = []
        self.midnight = []
        self.q3_days = []
        self.use_next = False
        self.pre_months = []
        self.pre_sampled = []
        self.pre_total = 0
        self.placement = None
        self.stop = None

    def fetch_day(self, d, phase):
        if d in self.days:
            return self.days[d]
        self.c.phase = phase
        records, http, note, token = [], None, "", None
        for _ in range(10):
            params = {"date": d.isoformat()}
            if token:
                params["paginationToken"] = token
            resp = self.c.get(params)
            http = resp["status"]
            body = resp["body"] or {}
            if http != 200:
                note = str(body.get("errorMsg") or body.get("name") or resp["text"])[:120]
                break
            data = body.get("data") or {}
            records += data.get("records") or []
            token = data.get("paginationToken")
            if not token:
                break
        returned = Counter(str(r.get("date"))[:10] for r in records)
        if http != 200:
            status = "ERROR"
        elif not records:
            status = "EMPTY"
        elif set(returned) == {d.isoformat()}:
            status = "OK"
        elif d.isoformat() in returned:
            status = "PARTIAL"
            note = f"also returned {sorted(set(returned) - {d.isoformat()})}"
        else:
            status = "MISMATCH"
            note = f"returned dates {sorted(returned)}"
        day = Day(d, status, http, records, returned, note, phase)
        self.days[d] = day
        return day

    # ---- steps ----

    def step0_probe(self):
        self.c.phase = "0 probe"
        self.latest_resp = self.c.get({})
        body = self.latest_resp["body"] or {}
        self.latest_records = (body.get("data") or {}).get("records") or []
        if self.latest_resp["status"] != 200 or not self.latest_records:
            raise StopRun(f"no-date probe gave HTTP {self.latest_resp['status']}, "
                          f"{len(self.latest_records)} records: {self.latest_resp['text']}")
        self.fetch_day(self.today, "0 probe")

    def step2_earliest(self):
        recent = self.fetch_day(self.today - timedelta(days=30), "2 date check + bisect")
        if recent.status != "OK":
            raise StopRun(f"date check failed for {recent.date}: {recent.status} {recent.note}. "
                          "date= cannot be trusted, so the bisect and sampling were not run")
        floor = self.fetch_day(HISTORY_FLOOR, "2 date check + bisect")
        if floor.present:
            self.earliest = HISTORY_FLOOR
            self.earliest_note = f"records exist at the search floor ({floor.status}); true start is on or before it"
            return
        lo, hi = HISTORY_FLOOR, recent.date
        while (hi - lo).days > 1:
            mid = lo + (hi - lo) // 2
            day = self.fetch_day(mid, "2 date check + bisect")
            self.bisect_log.append((mid, day.status))
            if day.present:
                hi = mid
            else:
                lo = mid
        self.earliest = hi
        for back in (1, 7, 30):
            n = self.fetch_day(hi - timedelta(days=back), "2 date check + bisect")
            self.neighbours.append((n.date, n.status))
        bad = [str(d) for d, s in self.neighbours if s in PRESENT]
        self.earliest_note = ("bisect assumes no gaps; days before it were present at " + ", ".join(bad)
                              if bad else "days 1, 7 and 30 before it are absent (consistent with a clean start)")

    def step4_sample_recent(self):
        y, m = 2023, 1
        while (y, m) <= (self.today.year, self.today.month):
            for d in sample_days(y, m, self.today):
                self.fetch_day(d, "4 sample 2023-01 to today")
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    def issue(self, rec, field=None):
        return parse_sgt(rec.get(field or self.field))

    def step3_midnight(self):
        cands = []
        for day in self.days.values():
            if day.date.year < 2023 or not day.present:
                continue
            for r in day.records:
                dt = self.issue(r)
                if dt is None:
                    continue
                off = dt.hour * 60 + dt.minute
                cands.append((off - 1440 if off > 720 else off, day, r, dt))
        before = max((c for c in cands if c[0] < 0), key=lambda c: c[0], default=None)
        after = min((c for c in cands if c[0] >= 0), key=lambda c: c[0], default=None)
        for label, c in (("last before midnight", before), ("first after midnight", after)):
            if c is None:
                continue
            off, day, r, dt = c
            vp = (r.get("general") or {}).get("validPeriod") or {}
            under = {}
            for delta in (-1, 1):
                nb = self.fetch_day(day.date + timedelta(days=delta), "3 midnight probe")
                under[delta] = any(rec_key(x) == rec_key(r) for x in nb.records)
            self.midnight.append({
                "label": label, "requested": day.date, "rec_date": r.get("date"),
                "timestamp": r.get("timestamp"), "updated": r.get("updatedTimestamp"),
                "issue_sgt": dt, "valid_start": parse_sgt(vp.get("start")), "valid_end": parse_sgt(vp.get("end")),
                "also_prev": under[-1], "also_next": under[1],
            })
        self.placement = self.placement_counts()
        self.use_next = not (self.placement["all_sgt"] or self.placement["all_utc"])

    def placement_counts(self):
        n = sgt = utc = rdate = valid = 0
        for day in self.days.values():
            if day.date.year < 2025 or not day.present:
                continue
            for r in day.records:
                dt = self.issue(r)
                if dt is None:
                    continue
                n += 1
                sgt += dt.date() == day.date
                utc += dt.astimezone(timezone.utc).date() == day.date
                rdate += str(r.get("date"))[:10] == day.date.isoformat()
                vs = parse_sgt(((r.get("general") or {}).get("validPeriod") or {}).get("start"))
                valid += bool(vs and vs.date() == day.date)
        return {"n": n, "sgt": sgt, "utc": utc, "rdate": rdate, "valid_start": valid,
                "all_sgt": n > 0 and sgt == n, "all_utc": n > 0 and utc == n}

    def pick_q3(self):
        by_year = {2025: [], 2026: []}
        for d in sorted(self.days):
            if d.year in by_year and self.days[d].status == "OK" and d < self.today:
                by_year[d.year].append(d)
        for year, k in ((2025, 13), (2026, 12)):
            pool = by_year[year]
            idx = sorted({round(i * (len(pool) - 1) / (k - 1)) for i in range(k)}) if len(pool) >= k else range(len(pool))
            self.q3_days += [pool[i] for i in idx]

    def step5_next_day(self):
        if self.use_next:
            for d in self.q3_days:
                self.fetch_day(d + timedelta(days=1), "5 D+1 for Q3 days")

    def step6_pre2023(self):
        start = (self.earliest.year, self.earliest.month)
        months, (y, m) = [], start
        while (y, m) < (2023, 1):
            months.append((y, m))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        remaining = CAP - self.c.network_calls - RETRY_RESERVE
        if self.c.cached_only:
            self.pre_months = months  # replay: take whatever the live run cached
        elif remaining <= 0:
            self.pre_months = []
        elif remaining >= len(months):
            self.pre_months = months
        else:
            k = remaining
            self.pre_months = [months[round(i * (len(months) - 1) / (k - 1))] for i in range(k)] if k > 1 else months[:1]
        self.pre_total = len(months)
        for y, m in self.pre_months:
            d = date(y, m, min(28, max(15, self.earliest.day if (y, m) == start else 15)))
            try:
                self.fetch_day(d, "6 sample before 2023 (1/month)")
            except CacheMiss:
                continue
            self.pre_sampled.append(d)
        self.pre_months = [(d.year, d.month) for d in self.pre_sampled]

    # ---- analysis ----

    def day_times(self, d, field):
        """Issue times (SGT) of records belonging to calendar day d, deduplicated."""
        recs = list(self.days[d].records)
        nxt = self.days.get(d + timedelta(days=1))
        if self.use_next and nxt:
            recs += nxt.records
        seen, out = set(), []
        for r in recs:
            dt = self.issue(r, field)
            if dt is None or rec_key(r) in seen:
                continue
            if self.use_next and dt.date() != d:
                continue
            seen.add(rec_key(r))
            out.append(dt)
        return sorted(out)


def sample_days(y, m, today):
    last = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    last = min(last, today - timedelta(days=1))
    first = 3 if last.day > 3 else 1
    n = min(4, last.day - first + 1)
    days = sorted({round(first + i * (last.day - first) / max(n - 1, 1)) for i in range(n)})
    return [date(y, m, d) for d in days]


# ---- report sections ----

def sec_q1(run):
    L = ["## Q1. Schema and granularity", ""]
    resp = run.latest_resp
    L.append(f"No-date call: HTTP {resp['status']}, {len(run.latest_records)} record(s); "
             f"top-level keys of the body: {sorted((resp['body'] or {}).keys())}, "
             f"data keys: {sorted(((resp['body'] or {}).get('data') or {}).keys())}.")
    L.append("")
    rec = run.latest_records[0]
    paths = key_paths(rec)
    L.append("Leaf paths of one record (`[]` = list element):")
    L.append("")
    L += table(["path", "type", "example"], [(f"`{p}`", t, f"`{str(e)[:40]}`") for p, (t, e) in paths.items()])
    L.append("")
    tp = {p: v for p, v in paths.items() if "temp" in p.lower() or "humid" in p.lower()}
    general = [p for p in tp if p.startswith("general")]
    regional = [p for p in tp if p.startswith("periods")]
    numeric_regional = [p for p, (t, _) in paths.items() if p.startswith("periods") and t in ("int", "float")]
    region_keys = sorted({p.split("regions.")[1].split(".")[0] for p in paths if "regions." in p})
    region_fields = sorted({p.split("regions.")[1].split(".", 1)[1] for p in paths if "regions." in p and "." in p.split("regions.")[1]})
    L.append("Answer:")
    L.append(f"- Temperature/humidity paths under `general` (island-wide): {general or 'none'}")
    L.append(f"- Temperature/humidity paths under `periods` (per region): {regional or 'none'}")
    L.append(f"- Regions present: {region_keys}; fields per region: {region_fields or '(value is not an object)'}")
    L.append(f"- Numeric fields anywhere under `periods`: {numeric_regional or 'none'}")
    verdict = ("island-wide low/high only; regional fields carry forecast text/code, no temperature or humidity"
               if general and not regional else
               "per-region temperature/humidity present" if regional else "no temperature/humidity found")
    L.append(f"- **Verdict from this record: {verdict}.**")
    L.append("")
    return L


def sec_datecheck(run):
    L = ["## Date check (every call that used `date=`)", ""]
    by_phase = defaultdict(Counter)
    for day in run.days.values():
        by_phase[day.phase][day.status] += 1
    cols = ["OK", "PARTIAL", "EMPTY", "MISMATCH", "ERROR"]
    rows = [(p, sum(c.values()), *[c[k] for k in cols]) for p, c in sorted(by_phase.items())]
    tot = Counter()
    for c in by_phase.values():
        tot.update(c)
    rows.append(("**total**", sum(tot.values()), *[tot[k] for k in cols]))
    L += table(["phase", "dates requested", *cols], rows)
    L += ["", "OK = every returned record's own `date` equals the requested date. PARTIAL = requested date plus other dates. "
          "EMPTY = HTTP 200, zero records. MISMATCH = records returned, none for the requested date "
          "(API ignoring `date=` or returning the latest forecast). ERROR = non-200.", ""]
    errs = Counter((d.http, d.note) for d in run.days.values() if d.status == "ERROR")
    L.append("ERROR breakdown (HTTP code, message): " + (", ".join(f"{k}: {v}" for k, v in errs.items()) or "none")
             + ". The API signals a date with no data by HTTP 404, not by an empty 200 (EMPTY count above).")
    L.append("")
    odd = [d for d in run.days.values() if d.status in ("PARTIAL", "MISMATCH", "ERROR")]
    if odd:
        L.append("Non-OK, non-EMPTY examples (first 10):")
        L += [f"- {d.date}: {d.status} (HTTP {d.http}) {d.note}" for d in sorted(odd, key=lambda d: d.date)[:10]]
    else:
        L.append("No PARTIAL, MISMATCH or ERROR responses.")
    L.append("")
    return L


def sec_q2(run):
    L = ["## Q2. History depth", ""]
    if run.earliest is None:
        return L + ["Not reached.", ""]
    L.append(f"- Earliest date with records: **{run.earliest}** ({run.earliest_note}).")
    if run.bisect_log:
        L.append("- Bisect probes (date: status): " + ", ".join(f"{d}: {s}" for d, s in run.bisect_log))
    if run.neighbours:
        L.append("- Neighbour probes before it: " + ", ".join(f"{d}: {s}" for d, s in run.neighbours))
    L.append("")
    months = defaultdict(list)
    for d, day in run.days.items():
        if d.year >= 2016 and day.phase.startswith(("4", "6")):
            months[(d.year, d.month)].append(day)
    earliest_ym = (run.earliest.year, run.earliest.month)
    cat = {}
    for ym, ds in months.items():
        n_present = sum(x.present for x in ds)
        cat[ym] = "full" if n_present == len(ds) else "zero" if n_present == 0 else "partial"
    recent = months_between((2023, 1), (run.today.year, run.today.month))
    rows = []
    for year in range(run.earliest.year, run.today.year + 1):
        yms = [(year, m) for m in range(1, 13) if earliest_ym <= (year, m) <= (run.today.year, run.today.month)]
        c = Counter(cat.get(ym, "unsampled") for ym in yms)
        rows.append((year, len(yms), c["full"], c["partial"], c["zero"], c["unsampled"]))
    L += table(["year", "months", "all samples have records", "some samples empty", "no sample has records", "not sampled"], rows)
    L.append("")
    rec_full = [ym for ym in recent if cat.get(ym) == "full"]
    L.append(f"**Jan 2023 to {run.today:%b %Y}: {len(rec_full)} of {len(recent)} months have records on every sampled day** "
             f"(4 days/month; {run.today:%b %Y} is sampled only up to {run.today - timedelta(days=1)}).")
    problem = [ym for ym in recent if cat.get(ym) != "full"]
    L.append("- Months in that window that are not full: " + (", ".join(f"{y}-{m:02d} ({cat.get((y, m), 'unsampled')})" for y, m in problem) or "none"))
    zero_after = [ym for ym, c in sorted(cat.items()) if c == "zero" and ym >= earliest_ym]
    L.append("- Zero-record months on or after the start month (gaps): " + (", ".join(f"{y}-{m:02d}" for y, m in zero_after) or "none"))
    partial = [ym for ym, c in sorted(cat.items()) if c == "partial"]
    L.append("- Partially covered months (some sampled days empty): " + (", ".join(f"{y}-{m:02d}" for y, m in partial) or "none"))
    gap_days = sorted(d for d, day in run.days.items() if d >= run.earliest and day.phase.startswith(("4", "6")) and not day.present)
    L.append(f"- Sampled days after the start with no data: {len(gap_days)}"
             + (": " + ", ".join(f"{d} ({run.days[d].status} {run.days[d].http})" for d in gap_days) if gap_days else "")
             + f"; sampled days in Jan 2023 to today: {sum(1 for d, day in run.days.items() if d.year >= 2023 and day.phase.startswith('4'))}.")
    if run.pre_months or run.pre_total:
        unsamp = run.pre_total - len(run.pre_months)
        L.append(f"- Before 2023: {len(run.pre_months)} of {run.pre_total} months sampled, 1 day each, because of the call cap; "
                 f"{unsamp} not sampled. A single empty sample is weak evidence of a gap.")
    L.append("")
    return L


def sec_q3(run):
    L = ["## Q3. Issue times", ""]
    if not run.q3_days:
        return L + ["Not reached.", ""]
    other = "updatedTimestamp" if run.field == "timestamp" else "timestamp"
    L.append(f"Issue time used: `{run.field}`, converted to Asia/Singapore. {len(run.q3_days)} days "
             f"({sum(d.year == 2025 for d in run.q3_days)} in 2025, {sum(d.year == 2026 for d in run.q3_days)} in 2026), "
             f"chosen evenly from the days sampled in Q2; {sum(d.weekday() >= 5 for d in run.q3_days)} fall on a weekend. "
             f"`date=` placement rule: {'D+1 also fetched' if run.use_next else 'issue date, D only'}.")
    L.append("")
    rows, counts, hours, hour_days, nolate = [], [], Counter(), defaultdict(set), []
    diff_last = []
    for d in run.q3_days:
        times = run.day_times(d, run.field)
        n_returned = len(run.days[d].records)
        counts.append(len(times) if run.use_next else n_returned)
        late = [t for t in times if t.time() <= CUTOFF]
        last = max(late) if late else None
        if last is None:
            nolate.append(d)
        alt = [t for t in run.day_times(d, other) if t.time() <= CUTOFF]
        if (max(alt) if alt else None) != last:
            diff_last.append(d)
        for t in times:
            hours[t.hour] += 1
            hour_days[t.hour].add(d)
        shown = ", ".join(hm(t) for t in times[:10]) + (f", … (+{len(times) - 10})" if len(times) > 10 else "")
        rows.append((d, d.strftime("%a"), n_returned, shown, hm(last) if last else "**NONE**"))
    L += table(["day", "dow", "records under date=", f"issue times SGT ({run.field})", "last issue ≤ 21:00 SGT"], rows)
    L += ["", f"**Records per day (Q3 days):** min {min(counts)}, max {max(counts)}, "
          f"median {statistics.median(counts)}, mean {statistics.mean(counts):.1f}; "
          f"distribution {dict(sorted(Counter(counts).items()))}.", ""]
    all_counts = [len(d.records) for d in run.days.values() if d.status == "OK" and d.date.year >= 2025]
    if all_counts:
        L.append(f"All sampled OK days in 2025–2026 ({len(all_counts)}): min {min(all_counts)}, max {max(all_counts)}, "
                 f"mean {statistics.mean(all_counts):.1f}.")
        L.append("")
    late_none, n_all = [], 0
    for d, day in sorted(run.days.items()):
        if d.year < 2023 or day.status != "OK" or not day.phase.startswith("4"):
            continue
        n_all += 1
        if not [t for t in run.day_times(d, run.field) if t.time() <= CUTOFF]:
            late_none.append(d)
    L.append(f"**All {n_all} sampled OK days from Jan 2023 (not just the Q3 25) with no issue at or before 21:00 SGT: "
             f"{', '.join(map(str, late_none)) if late_none else 'none'}.**")
    L.append("")
    per_year = defaultdict(lambda: [[], 0])
    for d, day in run.days.items():
        if d.year >= 2023 and day.status == "OK" and day.phase.startswith("4"):
            per_year[d.year][0].append(len(day.records))
            per_year[d.year][1] += d in late_none
    L.append("**Records per day by year, all sampled OK days from Jan 2023:**")
    L.append("")
    L += table(["year", "sampled OK days", "records/day min", "mean", "max", "days with no issue ≤ 21:00 SGT"],
               [(y, len(v[0]), min(v[0]), f"{statistics.mean(v[0]):.1f}", max(v[0]), v[1]) for y, v in sorted(per_year.items())])
    L.append("")
    L.append("**Distribution of issue hour (SGT) over the Q3 days:**")
    L.append("")
    L += table(["hour", "records", "days with ≥1"], [(f"{h:02d}:00", hours[h], len(hour_days[h])) for h in sorted(hours)])
    L.append("")
    L.append(f"**Days with no issue at or before 21:00 SGT: {', '.join(map(str, nolate)) if nolate else 'none'}** "
             f"(of {len(run.q3_days)}); so there {'is not always' if nolate else 'is always'} one in this sample.")
    L.append(f"Using `{other}` instead changes the last-before-21:00 time on {len(diff_last)} of {len(run.q3_days)} days"
             f"{': ' + ', '.join(map(str, diff_last[:8])) if diff_last else ''}.")
    L.append("")
    return L


def sec_timestamps(run):
    L = ["### Which timestamp is the issue time", ""]
    recs = [(d, r) for d in run.q3_days for r in run.days[d].records]
    if not recs:
        return L + ["No records.", ""]
    step = max(1, len(recs) // 8)
    rows = []
    for d, r in recs[::step][:8]:
        t, u = parse_sgt(r.get("timestamp")), parse_sgt(r.get("updatedTimestamp"))
        diff = f"{(u - t).total_seconds() / 60:.0f} min" if t and u else "n/a"
        rows.append((d, r.get("timestamp"), r.get("updatedTimestamp"), diff))
    L += table(["day", "timestamp", "updatedTimestamp", "updated − timestamp"], rows)
    diffs = [(parse_sgt(r.get("updatedTimestamp")) - parse_sgt(r.get("timestamp"))).total_seconds() / 60
             for _, r in recs if parse_sgt(r.get("timestamp")) and parse_sgt(r.get("updatedTimestamp"))]
    t_round = sum(parse_sgt(r.get("timestamp")).minute == 0 for _, r in recs if parse_sgt(r.get("timestamp")))
    u_round = sum(parse_sgt(r.get("updatedTimestamp")).minute == 0 for _, r in recs if parse_sgt(r.get("updatedTimestamp")))
    L += ["", f"Over {len(recs)} Q3 records: updated − timestamp min {min(diffs):.0f}, max {max(diffs):.0f}, "
          f"median {statistics.median(diffs):.0f} min; `timestamp` on the hour in {t_round}, `updatedTimestamp` on the hour in {u_round}.", ""]
    lag = []
    for day in run.days.values():
        if day.date.year >= 2023 and day.present:
            for r in day.records:
                t, u = parse_sgt(r.get("timestamp")), parse_sgt(r.get("updatedTimestamp"))
                if t and u:
                    lag.append((u - t).total_seconds() / 60)
    lag.sort()
    L += [f"Over all {len(lag)} sampled records from 2023: updated − timestamp median {statistics.median(lag):.0f} min, "
          f"95th percentile {lag[int(0.95 * (len(lag) - 1))]:.0f} min, max {lag[-1] / 1440:.1f} days; "
          f"more than 1 hour: {sum(x > 60 for x in lag)}; more than 1 day: {sum(x > 1440 for x in lag)}; negative: {sum(x < 0 for x in lag)}.",
          "",
          "**Treated as the issue time: `timestamp`.** It is the forecast's own time and clusters at NEA's scheduled issue times "
          "(about 05:30, 11:30, 17:30 and 23:00/23:30 SGT, plus ad-hoc updates in between). `updatedTimestamp` is when the record was "
          "last written: typically about 10 minutes after `timestamp`, but it can be much later (see the lag figures above and the "
          "midnight example), so it would date a past forecast to a time it was not yet available. `timestamp` can be a few minutes "
          "earlier than the public release, so a cut-off should leave a margin.", ""]
    return L


def sec_midnight(run):
    L = ["### Does `date=` filter by issue date or validity date?", ""]
    p = run.placement
    if p:
        L.append(f"Across {p['n']} records on sampled 2025–2026 days (issue time = `{run.field}`): record `date` field = requested date "
                 f"in {p['rdate']}; issue date in SGT = requested date in {p['sgt']}; issue date in UTC = requested date in {p['utc']}; "
                 f"`validPeriod.start` date in SGT = requested date in {p['valid_start']}.")
        L.append("")
    for m in run.midnight:
        L.append(f"- **{m['label']}**: requested `date={m['requested']}`, record `date` = {m['rec_date']}, "
                 f"timestamp {m['timestamp']}, updatedTimestamp {m['updated']}, issue SGT {m['issue_sgt']:%Y-%m-%d %H:%M}, "
                 f"validPeriod {m['valid_start']:%Y-%m-%d %H:%M} to {m['valid_end']:%Y-%m-%d %H:%M} SGT. "
                 f"The same record also appears under D−1: {m['also_prev']}; under D+1: {m['also_next']}."
                 if m["valid_start"] and m["valid_end"] else
                 f"- **{m['label']}**: requested `date={m['requested']}`, issue SGT {m['issue_sgt']:%Y-%m-%d %H:%M} (no parsable validPeriod).")
    if p:
        L.append("")
        L.append("Rule for the 21:00 analysis: " + (
            "records are filed under their SGT issue date; D only." if p["all_sgt"] else
            "records are filed under their UTC issue date; D only for the 21:00 question." if p["all_utc"] else
            "records are NOT all filed under the SGT or UTC issue date (validity-style placement), so D+1 was also fetched."))
    L.append("")
    return L


def slot_of(dt):
    """Issue slot by SGT time: the three scheduled daytime slots (+/- window), any 23:xx, else ad-hoc."""
    m = dt.hour * 60 + dt.minute
    for name, centre in (("05:30", 330), ("11:30", 690), ("17:30", 1050)):
        if centre - 5 <= m <= centre + 14:
            return name
    return "23:xx" if dt.hour == 23 else "ad-hoc"


def covers(d, vs, ve, window=(6, 18)):
    """Does validity [vs, ve] contain tomorrow (d+1) from window[0]:00 to window[1]:00 SGT in full?"""
    tomorrow = d + timedelta(days=1)
    return (vs <= datetime.combine(tomorrow, dtime(window[0], 0), SGT)
            and ve >= datetime.combine(tomorrow, dtime(window[1], 0), SGT))


def collect_items(run):
    """Sampled OK days from Jan 2023 -> (days, items, days without a 23:xx issue, n unparsable validPeriod, n duplicates).

    An item is (day, issue time SGT, slot, validPeriod start, end), deduplicated per day by record key.
    """
    days = sorted(d for d, day in run.days.items() if d.year >= 2023 and day.status == "OK" and day.phase.startswith("4"))
    items, no23, unparsed, dups = [], [], 0, 0
    for d in days:
        seen, got23 = set(), False
        for r in run.days[d].records:
            dt = run.issue(r)
            if dt is None:
                continue
            if rec_key(r) in seen:
                dups += 1
                continue
            seen.add(rec_key(r))
            vp = (r.get("general") or {}).get("validPeriod") or {}
            vs, ve = parse_sgt(vp.get("start")), parse_sgt(vp.get("end"))
            if vs is None or ve is None:
                unparsed += 1
            items.append((d, dt, slot_of(dt), vs, ve))
            got23 |= dt.hour == 23
        no23.append(d) if not got23 else None
    return days, items, no23, unparsed, dups


def sec_slots(run):
    L = ["## Cut-off follow-up: 23:xx issues and validity by issue slot", ""]
    if run.use_next:
        return L + ["Skipped: `date=` placement is not by SGT issue date, so per-day records are incomplete.", ""]
    days, items, no23, unparsed, _ = collect_items(run)
    L.append(f"### 1. Is there a 23:00–23:59 SGT issue? ({len(days)} sampled OK days from Jan 2023, issue time = `{run.field}`)")
    L.append("")
    L.append(f"Days with one: {len(days) - len(no23)}; days without: **{len(no23)}**"
             + (": " + ", ".join(map(str, no23)) if no23 else "") + ".")
    L.append("")

    L.append("### 2. Does the validPeriod cover tomorrow 06:00–18:00 SGT in full?")
    L.append("")
    L.append("Slots by SGT issue time: 05:30 = 05:25–05:44, 11:30 = 11:25–11:44, 17:30 = 17:25–17:44, 23:xx = 23:00–23:59, "
             "everything else = ad-hoc (a heuristic grouping). 'Tomorrow' is the day after the issue date. "
             f"Records with an unparsable validPeriod are excluded ({unparsed}).")
    L.append("")
    rows, order = [], ["05:30", "11:30", "17:30", "23:xx", "ad-hoc"]
    ok = [x for x in items if x[3] and x[4]]
    for s in order:
        sub = [x for x in ok if x[2] == s]
        full = sum(covers(d, vs, ve) for d, _, _, vs, ve in sub)
        rows.append((s, len(sub), full, f"{100 * full / len(sub):.0f}%" if sub else "n/a"))
    full_all = sum(covers(d, vs, ve) for d, _, _, vs, ve in ok)
    rows.append(("**all records**", len(ok), full_all, f"{100 * full_all / len(ok):.0f}%"))
    L += table(["issue slot", "records", "cover tomorrow 06–18 in full", "share"], rows)
    L.append("")

    last = []
    for d in days:
        cand = [x for x in items if x[0] == d and x[1].time() <= CUTOFF and x[3] and x[4]]
        if cand:
            last.append(max(cand, key=lambda x: x[1]))
    full_last = sum(covers(d, vs, ve) for d, _, _, vs, ve in last)
    L.append(f"**'Last issue ≤ 21:00 SGT' record, per day ({len(last)} days): {full_last} cover tomorrow 06:00–18:00 in full "
             f"({100 * full_last / len(last):.0f}%).** By slot of that last issue:")
    L.append("")
    rows = []
    for s in order:
        sub = [x for x in last if x[2] == s]
        f = sum(covers(d, vs, ve) for d, _, _, vs, ve in sub)
        rows.append((s, len(sub), f, f"{100 * f / len(sub):.0f}%" if sub else "n/a"))
    L += table(["slot of the last issue ≤ 21:00", "days", "cover in full", "share"], rows)
    L.append("")
    n23 = [x for x in ok if x[2] == "23:xx"]
    f23 = sum(covers(d, vs, ve) for d, _, _, vs, ve in n23)
    L.append(f"**23:xx issues: {f23} of {len(n23)} cover tomorrow 06:00–18:00 in full ({100 * f23 / len(n23):.0f}%).**")
    L.append("")
    L.append("Most common validPeriod patterns by slot (start → end, as day offset from the issue date and SGT time):")
    L.append("")
    rows = []
    for s in order:
        pat = Counter(f"{(vs.date() - d).days:+d}d {vs:%H:%M} → {(ve.date() - d).days:+d}d {ve:%H:%M}"
                      for d, _, sl, vs, ve in ok if sl == s)
        rows += [(s, p, n) for p, n in pat.most_common(3)]
    L += table(["slot", "validPeriod pattern", "records"], rows)
    L.append("")
    return L


def pick_rule(items, days, cut, window=(6, 18)):
    """Per day: latest issue at or before `cut` (SGT) whose validPeriod covers tomorrow's window in full."""
    by_day = defaultdict(list)
    for x in items:
        by_day[x[0]].append(x)
    chosen = {}
    for d in days:
        c = [x for x in by_day[d] if x[1].time() <= cut and x[3] and x[4] and covers(d, x[3], x[4], window)]
        if c:
            chosen[d] = max(c, key=lambda x: x[1])
    return chosen


def sec_rule(run):
    L = ["## Cut-off rule: latest issue at or before CUT that covers tomorrow 06:00–18:00 SGT in full", ""]
    if run.use_next:
        return L + ["Skipped: `date=` placement is not by SGT issue date.", ""]
    days, items, _, _, _ = collect_items(run)
    cuts = [("20:45", dtime(20, 45)), ("21:00", dtime(21, 0)), ("23:59", dtime(23, 59))]
    order = ["05:30", "11:30", "17:30", "23:xx", "ad-hoc"]
    picks = {name: pick_rule(items, days, t) for name, t in cuts}
    L.append(f"Tested on {len(days)} sampled OK days from Jan 2023 (issue time = `{run.field}`). Hours are from the chosen issue "
             "to tomorrow 06:00 SGT.")
    L.append("")
    rows = []
    for name, _ in cuts:
        ch = picks[name]
        hrs = [(datetime.combine(d + timedelta(days=1), dtime(6, 0), SGT) - x[1]).total_seconds() / 3600 for d, x in ch.items()]
        mix = Counter(x[2] for x in ch.values())
        rows.append((name, f"{len(ch)} of {len(days)}", ", ".join(f"{s}: {mix[s]}" for s in order if mix[s]),
                     f"{min(hrs):.1f} / {statistics.median(hrs):.1f} / {max(hrs):.1f}"))
    L += table(["CUT", "days with such a record", "slot mix of the chosen record", "hours to tomorrow 06:00 (min / median / max)"], rows)
    L.append("")
    for name, _ in cuts:
        none = [d for d in days if d not in picks[name]]
        L.append(f"- CUT {name}: days with none ({len(none)}): " + (", ".join(map(str, none)) or "none"))
    L.append("")
    L.append("Days with no qualifying record, by year:")
    L.append("")
    L += table(["year", "sampled OK days", *[f"none at {name}" for name, _ in cuts]],
               [(y, sum(d.year == y for d in days), *[sum(d.year == y and d not in picks[name] for d in days) for name, _ in cuts])
                for y in sorted({d.year for d in days})])
    L.append("")
    base = picks["20:45"]
    rows = []
    for name in ("21:00", "23:59"):
        ch = picks[name]
        both = [d for d in days if d in base and d in ch]
        diff = [d for d in both if rec_key_item(base[d]) != rec_key_item(ch[d])]
        gained = [d for d in days if d not in base and d in ch]
        rows.append((name, len(both), len(diff), len(gained)))
    L.append("**Compared with CUT = 20:45:**")
    L.append("")
    L += table(["CUT", "days with a record under both", "of which a different record is chosen", "days with none at 20:45 but one at this CUT"], rows)
    L.append("")
    return L


def rec_key_item(x):
    return (x[0], x[1])


def sec_reconcile(run):
    L = ["## Reconciling 1,415 vs 1,460 records, and records whose validPeriod ends before it starts", ""]
    if run.use_next:
        return L + ["Skipped.", ""]
    days, items, _, unparsed, dups = collect_items(run)
    basis_a, by_phase = 0, Counter()
    for day in run.days.values():
        if day.date.year >= 2023 and day.present:
            for r in day.records:
                if parse_sgt(r.get("timestamp")) and parse_sgt(r.get("updatedTimestamp")):
                    basis_a += 1
                    by_phase[day.phase] += 1
    basis_b = sum(1 for x in items if x[3] and x[4])
    p4 = sum(n for p, n in by_phase.items() if p.startswith("4"))
    other = {p: n for p, n in by_phase.items() if not p.startswith("4")}
    resid = basis_a - basis_b - sum(other.values()) - dups - unparsed
    L.append("The lag statistic (`updated − timestamp`) counted every record on every fetched day from 2023 that is OK or PARTIAL, "
             "in any phase, without deduplication. The slot tables count only the sampled-OK days of phase 4 "
             "(sample 2023-01 to today), deduplicated per day, with a parsable validPeriod.")
    L.append("")
    L += table(["item", "records"],
               [("Lag-statistic basis (all phases, from 2023)", basis_a)]
               + [(f"− phase '{p}' (not part of the phase-4 sample)", n) for p, n in sorted(other.items())]
               + [("− duplicates inside phase-4 days (same timestamp and updatedTimestamp)", dups),
                  ("− phase-4 records with an unparsable validPeriod", unparsed),
                  ("− other (e.g. unparsable `timestamp`)", resid),
                  ("**= slot-table basis**", basis_b)])
    L.append("")
    L.append(f"Phase-4 records before deduplication: {p4}.")
    L.append("")
    bad = [x for x in items if x[3] and x[4] and x[4] < x[3]]
    L.append(f"**Records whose validPeriod.end is before validPeriod.start: {len(bad)}** (in the slot-table basis).")
    L.append("")
    L += table(["day (`date`)", "issue time SGT", "validPeriod.start", "validPeriod.end"],
               [(x[0], f"{x[1]:%Y-%m-%d %H:%M}", f"{x[3]:%Y-%m-%d %H:%M}", f"{x[4]:%Y-%m-%d %H:%M}") for x in sorted(bad, key=lambda x: x[1])])
    L.append("")
    return L


def fmt_vp(d, vs, ve):
    return f"{(vs.date() - d).days:+d}d {vs:%H:%M} → {(ve.date() - d).days:+d}d {ve:%H:%M}"


def sec_window(run):
    L = ["## Window sensitivity at CUT = 20:45, and why 2026 days have no qualifying record", ""]
    if run.use_next:
        return L + ["Skipped: `date=` placement is not by SGT issue date.", ""]
    days, items, _, _, _ = collect_items(run)
    cut = dtime(20, 45)
    wide = pick_rule(items, days, cut, (6, 18))
    peak = pick_rule(items, days, cut, (10, 16))
    L.append(f"Same rule (latest issue at or before 20:45 SGT whose validPeriod covers tomorrow's window in full), "
             f"{len(days)} sampled OK days from Jan 2023, issue time = `{run.field}`.")
    L.append("")
    L += table(["year", "sampled OK days", "with a record: 06:00–18:00", "with a record: 10:00–16:00"],
               [(y, sum(d.year == y for d in days), sum(d.year == y and d in wide for d in days), sum(d.year == y and d in peak for d in days))
                for y in sorted({d.year for d in days})]
               + [("**all**", len(days), len(wide), len(peak))])
    L.append("")
    none_peak = [d for d in days if d not in peak]
    L.append(f"Days with none under 10:00–16:00 ({len(none_peak)}; 2026: {sum(d.year == 2026 for d in none_peak)}). "
             "2026 days: " + (", ".join(str(d) for d in none_peak if d.year == 2026) or "none")
             + ". Other years: " + (", ".join(str(d) for d in none_peak if d.year != 2026) or "none") + ".")
    L.append("")

    by_day = defaultdict(list)
    for x in items:
        by_day[x[0]].append(x)
    miss = [d for d in days if d.year == 2026 and d not in wide]
    L.append(f"### The {len(miss)} days in 2026 with no qualifying record at 20:45 under 06:00–18:00")
    L.append("")
    L.append("Every issue at or before 20:45 SGT that day. validPeriod is shown as day offset from the issue date and SGT time; "
             "covering tomorrow 06:00–18:00 needs a start of +1d 06:00 or earlier (or +0d, +1d 00:00, …) and an end of +1d 18:00 or later.")
    L.append("")
    rows = []
    for d in miss:
        for x in sorted((x for x in by_day[d] if x[1].time() <= cut), key=lambda x: x[1]):
            rows.append((d, f"{x[1]:%H:%M}", x[2], fmt_vp(d, x[3], x[4]) if x[3] and x[4] else "unparsable"))
    L += table(["day", "issue SGT", "slot", "validPeriod start → end"], rows)
    L.append("")
    no17_miss = [d for d in miss if not any(x[1].hour == 17 for x in by_day[d])]
    L.append(f"Of these {len(miss)} days, {len(no17_miss)} have no 17:xx SGT issue at all.")
    L.append("")

    L.append("### Sampled days with no 17:xx SGT issue, by month")
    L.append("")
    rows, tot_n, tot_no = [], 0, 0
    for (y, m) in months_between((2026, 1), (run.today.year, run.today.month)):
        ds = [d for d in days if (d.year, d.month) == (y, m)]
        if not ds:
            continue
        no17 = [d for d in ds if not any(x[1].hour == 17 for x in by_day[d])]
        rows.append((f"{y}-{m:02d}", len(ds), len(no17), ", ".join(str(d) for d in no17) or "–"))
    L += table(["month (2026)", "sampled OK days", "days with no 17:xx issue", "which days"], rows)
    L.append("")
    prev = [d for d in days if d.year < 2026]
    prev_no = [d for d in prev if not any(x[1].hour == 17 for x in by_day[d])]
    L.append(f"For comparison, 2023–2025: {len(prev_no)} of {len(prev)} sampled OK days have no 17:xx issue.")
    L.append("")
    return L


def sec_raw(run):
    return ["## One complete raw record", "",
            "First record of the no-date (latest) call; public data, unmodified.", "",
            "```json", json.dumps(run.latest_records[0], indent=2, ensure_ascii=False), "```", ""]


def sec_notes(run):
    c = run.c
    dates = sorted(run.days)
    L = ["## Calls, range and limits", ""]
    L += table(["phase", "network calls"], [(p, n) for p, n in sorted(c.phase_calls.items())] + [("**total**", c.network_calls)])
    if c.cached_only:
        L += ["", f"Report regenerated from the cache ({c.cache_hits} cache reads, 0 new calls). The figures below are from the live run:"]
        stats = json.loads((c.cache_dir / "stats.json").read_text(encoding="utf-8"))
        L += table(["phase", "network calls"], [(p, n) for p, n in sorted(stats["phase_calls"].items())] + [("**total**", stats["network_calls"])])
        net, ret, sts = stats["network_calls"], stats["retries"], stats["statuses"]
        when = stats["run_time"]
        if "copied" in when:
            L += ["", "**Caveat: the live-run call counts above were hand-copied from the first run's printed report, not machine-logged** "
                  "(that run predates the stats file)."]
    else:
        L += table(["phase", "network calls"], [(p, n) for p, n in sorted(c.phase_calls.items())] + [("**total**", c.network_calls)])
        net, ret, sts, when = c.network_calls, c.retries, dict(c.statuses), f"{datetime.now(SGT):%Y-%m-%d %H:%M} SGT"
    L += ["", f"- Network calls: {net} (cap {CAP}); of which retries after 429/403/5xx/connection errors: {ret}. HTTP status counts: {sts}.",
          f"- Dates requested with `date=`: {len(dates)}, from {dates[0]} to {dates[-1]}." if dates else "- No dated calls.",
          f"- Live run time: {when}. No key or token was used. Stop reason: {run.stop or 'none, ran to completion'}.",
          "", "**Not tested:**",
          "- Whether an API key changes history depth, pagination or rate limits.",
          "- Days not sampled: Q2 checks 4 days/month from Jan 2023 and 1 day/month before; a month listed as full can still have missing days.",
          "- Whether past records are the originally issued forecasts or were later revised or backfilled.",
          "- Forecast values or accuracy; the 2-hour and 4-day forecast endpoints.",
          "- Whether the issue pattern seen on sampled days holds on other days or in the future (only ~25 days examined for Q3).",
          "- Issue-time behaviour on days when the 21:00 forecast was late or missing beyond the sampled days.",
          ""]
    return L


def build(run, full):
    L = ["# Check 10: NEA 24-hour forecast (data.gov.sg)", "",
         f"Endpoint `{URL}`, unauthenticated. Script: `scripts/checks/check10_forecast_history.py`. Date `date=YYYY-MM-DD`.", ""]
    if run.stop:
        L += [f"> **Run stopped early: {run.stop}.** Sections below are partial.", ""]
    sections = []
    if run.latest_records:
        sections.append(sec_q1)
    sections += [sec_datecheck, sec_q2, sec_q3, sec_timestamps, sec_midnight, sec_slots, sec_rule, sec_reconcile, sec_window]
    for fn in sections:
        try:
            L += fn(run)
        except Exception as e:
            L += [f"_Section {fn.__name__} could not be built: {type(e).__name__}: {e}_", ""]
    if full and run.latest_records:
        L += sec_raw(run)
    L += sec_notes(run)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default=".cache/check10")
    ap.add_argument("--out", default="docs/checks/check10.md")
    ap.add_argument("--issue-field", default="timestamp", choices=["timestamp", "updatedTimestamp"])
    ap.add_argument("--cached-only", action="store_true", help="rebuild the report from the cache, no network calls")
    args = ap.parse_args()

    run = Run(Client(args.cache_dir, args.cached_only, url=URL, cap=CAP, user_agent="coolcheck-check10"), datetime.now(SGT).date(), args.issue_field)
    try:
        run.step0_probe()
        run.step2_earliest()
        run.step4_sample_recent()
        run.c.phase = "3 midnight probe"
        run.step3_midnight()
        run.pick_q3()
        run.step5_next_day()
        run.step6_pre2023()
    except StopRun as e:
        run.stop = str(e)
    if not args.cached_only:
        c = run.c
        (c.cache_dir / "stats.json").write_text(json.dumps({
            "network_calls": c.network_calls, "retries": c.retries, "statuses": dict(c.statuses),
            "phase_calls": dict(c.phase_calls), "run_time": f"{datetime.now(SGT):%Y-%m-%d %H:%M} SGT", "stop": run.stop}), encoding="utf-8")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(run, full=True) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(build(run, full=False))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
