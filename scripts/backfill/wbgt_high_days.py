"""High-day counts from the backfilled WBGT files (no API calls).

Run from the repo root after the WBGT stage of backfill.py:
    .venv\\Scripts\\python scripts/backfill/wbgt_high_days.py [--out-dir <coolcheck-data>]

Definitions (all from the API's own heatStress field; no numeric cut-off is coded):
- A reading's day is the SGT date of its record's `datetime`. Readings are deduplicated on (datetime, station).
- A reading counts if heatStress is Low, Moderate or High. "NA" readings are counted separately and excluded;
  any other value is listed and excluded.
- Station-day: a station with at least one counted reading that SGT day.
- High station-day: a station-day on which that station has at least one High reading.
- High day: a day on which any station (or, for the original-8 columns, any of the 8) has a High reading.

Writes docs/checks/wbgt_high_days.md (also printed) and CSVs in <out-dir>/analysis/.
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from backfill import DEFAULT_OUT, REPO, SGT, START, State

CATS = ("Low", "Moderate", "High")
NA = "NA"
ORIGINAL_8 = ("S124", "S125", "S126", "S127", "S128", "S129", "S130", "S132")  # stations reporting on 2025-01-16 (check 9)
RULE = 30  # §14.4 Labels: "fewer than about 30 High station-days in the test period"
WINDOWS = [("Jan–Jun 2025", date(2025, 1, 1), date(2025, 6, 30)),
           ("Jul 2025–Aug 2026", date(2025, 7, 1), date(2026, 8, 31)),
           ("Sep–Oct 2026", date(2026, 9, 1), date(2026, 10, 31))]


class Data:
    """Every station reading in the raw WBGT files, reduced to one row per (station, SGT day)."""

    def __init__(self):
        self.files = self.lines = self.records = self.readings = self.dupes = 0
        self.bad_time = self.off_file_date = self.no_station = self.high_no_value = 0
        self.cats = Counter()
        self.ranges = {}
        self.names = {}
        self.daily = {}  # (station, sgt_date) -> dict
        self._seen = set()

    def add_body(self, body, file_date=None):
        data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), dict) else {}
        for rec in data.get("records") or []:
            if not isinstance(rec, dict):
                continue
            self.records += 1
            try:
                dt = datetime.fromisoformat(rec.get("datetime"))
            except (TypeError, ValueError):
                dt = None
            if dt is None or dt.tzinfo is None:
                self.bad_time += 1
                continue
            dt = dt.astimezone(SGT)
            item = rec.get("item") if isinstance(rec.get("item"), dict) else {}
            for r in item.get("readings") or []:
                if isinstance(r, dict):
                    self.add_reading(dt, r, file_date)

    def add_reading(self, dt, r, file_date):
        st = r.get("station") if isinstance(r.get("station"), dict) else {}
        sid = st.get("id")
        if sid is None:
            self.no_station += 1
            return
        sid = str(sid)
        if (dt, sid) in self._seen:
            self.dupes += 1
            return
        self._seen.add((dt, sid))
        self.readings += 1
        self.names.setdefault(sid, st.get("name"))
        day = dt.date()
        if file_date and day != file_date:
            self.off_file_date += 1
        cat = r.get("heatStress")
        cat = cat if isinstance(cat, str) else repr(cat)
        self.cats[cat] += 1
        try:
            value = float(r.get("wbgt"))
        except (TypeError, ValueError):
            value = None
        row = self.daily.setdefault((sid, day), {"valid": 0, "na": 0, "other": 0, "max_cat": None, "max_wbgt": None, "high": False})
        if cat not in CATS:
            row["na" if cat == NA else "other"] += 1
            return
        row["valid"] += 1
        if row["max_cat"] is None or CATS.index(cat) > CATS.index(row["max_cat"]):
            row["max_cat"] = cat
        if cat == "High":
            row["high"] = True
            self.high_no_value += value is None
        if value is not None:
            row["max_wbgt"] = value if row["max_wbgt"] is None else max(row["max_wbgt"], value)
            lo, hi = self.ranges.get(cat, (value, value))
            self.ranges[cat] = (min(lo, value), max(hi, value))

    def load(self, raw_dir):
        for path in sorted(Path(raw_dir).glob("wbgt_*.jsonl")):
            self.files += 1
            file_date = date.fromisoformat(path.stem.split("_", 1)[1])
            for line in path.read_bytes().splitlines():
                if line.strip():
                    self.lines += 1
                    self.add_body(json.loads(line), file_date)
        return self

    def per_day(self, stations=None):
        """sgt_date -> (station-days, High station-days) over the given stations (None = all)."""
        out = defaultdict(lambda: [0, 0])
        for (sid, day), row in self.daily.items():
            if row["valid"] and (stations is None or sid in stations):
                out[day][0] += 1
                out[day][1] += row["high"]
        return out


def totals(per_day, lo, hi):
    """Days with data, station-days, High station-days and High days between lo and hi (inclusive)."""
    days = [v for d, v in per_day.items() if lo <= d <= hi]
    return {"days": len(days), "sd": sum(v[0] for v in days), "hsd": sum(v[1] for v in days),
            "hdays": sum(1 for v in days if v[1])}


def vs_rule(n):
    side = f"below {RULE}" if n < RULE else f"at or above {RULE}"
    return side + (" (within the rule's 'about')" if abs(n - RULE) <= 5 else "")


def share(a, b):
    return f"{100 * a / b:.1f}%" if b else "–"


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return lines


def months(first, last):
    out, (y, m) = [], (first.year, first.month)
    while (y, m) <= (last.year, last.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def month_end(y, m):
    return date(y + (m == 12), m % 12 + 1, 1).toordinal() - 1


def read_progress(state):
    days, runs = {}, []
    if state.progress.exists():
        for line in state.progress.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("event") == "day" and rec.get("feed") == "wbgt":
                days[rec["date"]] = rec
            elif rec.get("event") == "run_end" and "wbgt" in rec.get("feeds", []):
                runs.append(rec)
    return days, runs


def report(data, prog_days, runs, end, raw_dir):
    all_days, o8_days = data.per_day(), data.per_day(set(ORIGINAL_8))
    status = Counter(r["status"] for r in prog_days.values())
    short = sorted((d, r.get("distinct_on_day")) for d, r in prog_days.items() if r["status"] == "short")
    missing = sorted(d for d, r in prog_days.items() if r["status"] in ("no_data", "empty", "date_mismatch"))
    calls = sum(r["calls"] for r in runs)
    n429 = sum(r["statuses"].get("429", 0) for r in runs)
    L = ["# WBGT High days from the backfill (check 9 part B)", "",
         f"Script: `scripts/backfill/wbgt_high_days.py`, reading the raw WBGT files written by `scripts/backfill/backfill.py` "
         f"(`{raw_dir.relative_to(raw_dir.parents[3]).as_posix()}` in the data folder beside the repo). No API calls. "
         f"Generated {datetime.now(SGT):%Y-%m-%d %H:%M} SGT. Dates are SGT.", ""]

    L += ["## Data read", "",
          f"- Backfill days in the progress file: {len(prog_days)} ({min(prog_days, default='–')} to {max(prog_days, default='–')}); "
          f"statuses {dict(status)}.",
          f"- Backfill calls (machine-logged in `progress.jsonl`, {len(runs)} run(s)): {calls:,}, of which HTTP 429 {n429:,} "
          f"({share(n429, calls)}); stops: {[r['stopped'] for r in runs if r.get('stopped')] or 'none'}; "
          f"key: {sorted({r['key'] for r in runs}) or '–'}.",
          f"- Files {data.files}, pages (lines) {data.lines:,}, records (timestamps) {data.records:,}, station readings {data.readings:,} "
          f"after removing {data.dupes:,} duplicate (datetime, station) pairs.",
          f"- Records without a usable `datetime`: {data.bad_time}; readings without a station id: {data.no_station}; "
          f"readings whose SGT date differs from their file's date: {data.off_file_date}.",
          f"- Days without data (HTTP 404, empty or date mismatch): {', '.join(missing) or 'none'}.",
          f"- Short days (fewer than 96 distinct timestamps): {len(short)}"
          + (": " + ", ".join(f"{d} ({n})" for d, n in short[:25]) + (" …" if len(short) > 25 else "") if short else "") + ".", ""]

    L += ["## heatStress values", ""]
    rng = {c: tuple(f"{v:.1f}" for v in data.ranges[c]) for c in data.ranges}
    L += table(["value", "readings", "WBGT min", "WBGT max"],
               [(c, f"{n:,}", *rng.get(c, ("–", "–"))) for c, n in sorted(data.cats.items(), key=lambda x: -x[1])])
    unexpected = {c: n for c, n in data.cats.items() if c not in CATS and c != NA}
    L += ["", f"Counted values: {', '.join(CATS)}. `NA` readings ({data.cats.get(NA, 0):,}) are excluded from station-days. "
          f"Other values, also excluded: {unexpected or 'none'}. High readings without a numeric WBGT: {data.high_no_value}.", ""]
    if all(c in data.ranges for c in CATS):
        lo_m, hi_m = data.ranges["Moderate"]
        lo_h, _ = data.ranges["High"]
        L += [f"Boundary from the API's own field: highest Moderate {hi_m:.1f}, lowest High {lo_h:.1f}; "
              f"the categories {'do not overlap' if hi_m < lo_h else 'OVERLAP'} in value (§12.6 item 11).", ""]

    first = min((d for (_, d) in data.daily), default=None)
    first_ids = sorted({sid for (sid, d), row in data.daily.items() if d == first and row["valid"]})
    L += ["## Original 8 stations", "",
          f"List used: {', '.join(ORIGINAL_8)}. Stations with counted readings on the first day ({first}): "
          f"{', '.join(first_ids) or 'none'} — {'matches the list' if first_ids == list(ORIGINAL_8) else 'DIFFERS from the list'}.",
          "The monthly table shows how many of the 8 reported each month; a month with fewer has fewer chances of a High.", ""]

    L += ["## High station-days by window, against the §14.4 rule", "",
          "§14.4 (Labels): *fewer than about 30 High station-days in the test period means recall on High days is too unstable to "
          "quote as three classes*. The windows below are the ones asked for; none of them is yet the agreed test period (D6).", ""]
    rows, csv_windows = [], []
    for name, lo, hi in WINDOWS:
        lo, hi = max(lo, START), min(hi, end)
        if lo > hi:
            rows.append((name, "not in the backfill", *["–"] * 9))
            continue
        a, o = totals(all_days, lo, hi), totals(o8_days, lo, hi)
        rows.append((name, f"{lo} – {hi}",a["days"], f"{a['sd']:,}", a["hsd"], vs_rule(a["hsd"]), a["hdays"],
                     f"{o['sd']:,}", o["hsd"], vs_rule(o["hsd"]), o["hdays"]))
        csv_windows.append({"window": name, "from": lo, "to": hi, "days_with_data": a["days"],
                            "all_station_days": a["sd"], "all_high_station_days": a["hsd"], "all_high_days": a["hdays"],
                            "orig8_station_days": o["sd"], "orig8_high_station_days": o["hsd"], "orig8_high_days": o["hdays"]})
    L += table(["window", "dates covered", "days with data", "station-days (all)", "High station-days (all)", "vs rule (all)",
                "High days (all)", "station-days (8)", "High station-days (8)", "vs rule (8)", "High days (8)"], rows)
    L += ["", f"The last window ends at the backfill's end ({end}), so it is shorter than two months.", ""]

    L += ["## By month", "",
          "High day = any station reaches High that day. 'all' = every station reporting that month; '8' = only the original 8.", ""]
    short_by_month = Counter(d[:7] for d, _ in short)
    per_month_ids = defaultdict(set)
    per_month_o8 = defaultdict(set)
    per_day_n = defaultdict(int)
    for (sid, d), row in data.daily.items():
        if row["valid"]:
            per_month_ids[(d.year, d.month)].add(sid)
            per_day_n[d] += 1
            if sid in ORIGINAL_8:
                per_month_o8[(d.year, d.month)].add(sid)
    rows, csv_months = [], []
    for y, m in months(START, end):
        lo, hi = max(date(y, m, 1), START), min(date.fromordinal(month_end(y, m)), end)
        a, o = totals(all_days, lo, hi), totals(o8_days, lo, hi)
        counts = [n for d, n in per_day_n.items() if lo <= d <= hi]
        span = f"{min(counts)}–{max(counts)}" if counts else "–"
        key = f"{y}-{m:02d}"
        rows.append((key, (hi - lo).days + 1, a["days"], short_by_month.get(key, 0), span, f"{a['sd']:,}", a["hsd"],
                     share(a["hsd"], a["sd"]), a["hdays"], len(per_month_o8[(y, m)]), o["sd"], o["hsd"], o["hdays"]))
        csv_months.append({"month": key, "days_in_range": (hi - lo).days + 1, "days_with_data": a["days"],
                           "short_days": short_by_month.get(key, 0), "stations_per_day": span,
                           "stations_in_month": len(per_month_ids[(y, m)]), "station_days": a["sd"],
                           "high_station_days": a["hsd"], "high_days": a["hdays"],
                           "orig8_reporting": len(per_month_o8[(y, m)]), "orig8_station_days": o["sd"],
                           "orig8_high_station_days": o["hsd"], "orig8_high_days": o["hdays"]})
    a, o = totals(all_days, START, end), totals(o8_days, START, end)
    rows.append(("**total**", (end - START).days + 1, a["days"], len(short), "", f"**{a['sd']:,}**", f"**{a['hsd']}**",
                 share(a["hsd"], a["sd"]), f"**{a['hdays']}**", "", f"**{o['sd']:,}**", f"**{o['hsd']}**", f"**{o['hdays']}**"))
    L += table(["month", "days in range", "days with data", "short days", "stations per day (min–max)", "station-days (all)",
                "High station-days (all)", "High share (all)", "High days (all)", "of the 8 reporting", "station-days (8)",
                "High station-days (8)", "High days (8)"], rows)
    L += ["", "All-station High days rise partly because the network grew from 8 to about 30 stations: more stations give more "
          "chances that one of them reaches High. The original-8 columns hold the station set fixed (as far as those 8 keep reporting).", ""]

    st_rows, csv_stations = [], []
    by_station = defaultdict(list)
    for (sid, d), row in data.daily.items():
        if row["valid"]:
            by_station[sid].append((d, row["high"]))
    for sid in sorted(by_station):
        ds = by_station[sid]
        hsd = sum(h for _, h in ds)
        st_rows.append((sid, data.names.get(sid) or "", min(d for d, _ in ds), max(d for d, _ in ds), len(ds), hsd,
                        share(hsd, len(ds)), "yes" if sid in ORIGINAL_8 else ""))
        csv_stations.append({"station": sid, "name": data.names.get(sid) or "", "first": min(d for d, _ in ds),
                             "last": max(d for d, _ in ds), "station_days": len(ds), "high_station_days": hsd,
                             "original_8": sid in ORIGINAL_8})
    L += ["## By station", ""]
    L += table(["station", "name", "first day", "last day", "station-days", "High station-days", "High share", "original 8"], st_rows)
    L += ["", "Station-by-month counts are in `analysis/wbgt_station_month.csv` in the data folder.", ""]

    L += ["## Not covered", "",
          "- Whether High days cluster in a way that matters for the back-test split (D6); this report counts, it does not choose.",
          "- Whether three classes are supportable: the §14.4 rule needs the agreed test period, which is not fixed yet.",
          "- Readings revised after publication: the backfill stores what the API returns today.",
          "- Daily labels per planning area (nearest station, D5): Day 2 Silver work.", ""]
    return L, csv_windows, csv_months, csv_stations


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--report", default=str(REPO / "docs" / "checks" / "wbgt_high_days.md"))
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    state = State(Path(args.out_dir).resolve())
    raw_dir = state.raw_dir("wbgt")
    prog_days, runs = read_progress(state)
    if not prog_days:
        print(f"No WBGT days in {state.progress}; run backfill.py --feeds wbgt first.", file=sys.stderr)
        return 2
    end = date.fromisoformat(max(prog_days))
    data = Data().load(raw_dir)
    L, csv_windows, csv_months, csv_stations = report(data, prog_days, runs, end, raw_dir)

    analysis = state.out / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    write_csv(analysis / "wbgt_windows.csv", csv_windows)
    write_csv(analysis / "wbgt_monthly.csv", csv_months)
    write_csv(analysis / "wbgt_stations.csv", csv_stations)
    sm = Counter()
    for (sid, d), row in data.daily.items():
        if row["valid"]:
            sm[(sid, f"{d:%Y-%m}", "sd")] += 1
            sm[(sid, f"{d:%Y-%m}", "hsd")] += row["high"]
    write_csv(analysis / "wbgt_station_month.csv",
              [{"station": sid, "month": m, "station_days": sm[(sid, m, "sd")], "high_station_days": sm[(sid, m, "hsd")]}
               for sid, m in sorted({(s, m) for s, m, _ in sm})])
    write_csv(analysis / "wbgt_station_daily.csv",
              [{"station": sid, "name": data.names.get(sid) or "", "sgt_date": d, "readings": row["valid"], "na": row["na"],
                "other": row["other"], "max_category": row["max_cat"] or "", "max_wbgt": row["max_wbgt"], "high": row["high"]}
               for (sid, d), row in sorted(data.daily.items())])

    text = "\n".join(L)
    print(text)
    Path(args.report).write_text(text, encoding="utf-8")
    print(f"\nWrote {args.report} and CSVs in {analysis}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
