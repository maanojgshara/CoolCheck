"""Live files per 15-minute slot and reading coverage per day, from a local copy of the collector's live folders.

Read-only: copy the folders first (no compute is started), then count locally. From the repo root:
    for f in wbgt rainfall forecast air_temperature; do for d in 2026-10-22 2026-10-23; do
      databricks fs cp -r dbfs:/Volumes/coolcheck/bronze/raw_files/$f/live/$d <copy>/$f/$d -p coolcheck; done; done
    .venv\\Scripts\\python scripts/checks/live_completeness.py <copy> --now 2026-10-23T15:30:00+08:00 \\
        --slots 2026-10-22 2026-10-23 --coverage 2026-10-22 2026-10-23

A slot is the 15-minute window that holds a run's start time (SGT, from the file name); the slot in progress at --now
is not counted. Reading coverage counts, for one SGT day, the reading times that have a value in any file of that day's
folder or the next day's (the next day's 00:xx runs re-read the whole day: the midnight sweep), and the stations per
time. WBGT has a reading every 15 minutes, rainfall every 5, air temperature every minute; the forecast is listed by
issue time.
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SGT = timezone(timedelta(hours=8))
FEEDS = ["wbgt", "rainfall", "forecast", "air_temperature"]
STEP_MIN = {"wbgt": 15, "rainfall": 5, "air_temperature": 1}
NAME = re.compile(r"^(?P<feed>[a-z_]+)_(?P<d>\d{4}-\d{2}-\d{2})T(?P<t>\d{6})_(?P<run>[A-Za-z0-9-]+)\.jsonl$")


def files(root, feed, day):
    out = []
    for p in sorted((root / feed / day).glob("*.jsonl")):
        m = NAME.match(p.name)
        if m:
            start = datetime.strptime(m["d"] + m["t"], "%Y-%m-%d%H%M%S").replace(tzinfo=SGT)
            out.append((start, m["run"], p))
    return out


def slot(t):
    return t.replace(minute=t.minute - t.minute % 15, second=0, microsecond=0)


def slot_report(root, day, now):
    d0 = datetime.fromisoformat(day + "T00:00:00+08:00")
    end = min(d0 + timedelta(days=1), slot(now))
    slots, t = [], d0
    while t < end:
        slots.append(t)
        t += timedelta(minutes=15)
    print(f"\n=== {day}: {len(slots)} slots expected (00:00 to {'24:00' if end > d0 + timedelta(hours=23) else f'{end:%H:%M}'})")
    per_feed, runs = {}, {}
    for feed in FEEDS:
        fs = files(root, feed, day)
        by_slot = defaultdict(list)
        for start, run, _ in fs:
            by_slot[slot(start)].append(start)
            runs.setdefault(run, start)
        per_feed[feed] = by_slot
        filled = sum(1 for s in slots if by_slot.get(s))
        print(f"{feed:16s} files {len(fs):3d}  slots with a file {filled:3d}/{len(slots)}")
    run_slots = defaultdict(list)
    for run, start in runs.items():
        run_slots[slot(start)].append(start)
    print(f"runs (run ids with any file) {len(runs)}; slots with a run {sum(1 for s in slots if run_slots.get(s))}/"
          f"{len(slots)}")
    print("slots with no run: " + (", ".join(f"{s:%H:%M}" for s in slots if not run_slots.get(s)) or "none"))
    print("slots with 2+ runs: " + (", ".join(f"{s:%H:%M} ({', '.join(f'{x:%H:%M:%S}' for x in sorted(v))})"
                                              for s, v in sorted(run_slots.items()) if len(v) > 1 and s in slots)
                                    or "none"))
    for feed in FEEDS:
        miss = [s for s in slots if run_slots.get(s) and not per_feed[feed].get(s)]
        if miss:
            print(f"slots with a run but no {feed} file: " + ", ".join(f"{s:%H:%M}" for s in miss))


def lines(p):
    with open(p, "rb") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def readings(feed, body):
    """(time, station id or forecast date, has a value) for every reading on a page."""
    data = body.get("data") or {}
    if feed == "wbgt":
        for rec in data.get("records") or []:
            t = datetime.fromisoformat(rec["datetime"])
            for r in (rec.get("item") or {}).get("readings") or []:
                yield t, r["station"]["id"], r.get("wbgt") not in (None, "")
    elif feed in ("rainfall", "air_temperature"):
        for rec in data.get("readings") or []:
            t = datetime.fromisoformat(rec["timestamp"])
            for r in rec.get("data") or []:
                yield t, r["stationId"], r.get("value") is not None
    elif feed == "forecast":
        for rec in data.get("records") or []:
            yield datetime.fromisoformat(rec["timestamp"]), rec.get("date"), True


def ranges(times, step):
    out, a, prev = [], times[0], times[0]
    for t in times[1:] + [None]:
        if t is None or t - prev != timedelta(minutes=step):
            out.append(f"{a:%H:%M}" + (f"-{prev:%H:%M}" if prev != a else ""))
            a = t
        if t is not None:
            prev = t
    return out


def coverage(root, day):
    d0 = datetime.fromisoformat(day + "T00:00:00+08:00")
    d1 = d0 + timedelta(days=1)
    print(f"\n=== reading coverage for {day} (files of {day} and {d1:%Y-%m-%d})")
    for feed in FEEDS:
        seen, first, sweep = defaultdict(set), {}, defaultdict(set)
        for dd in (day, f"{d1:%Y-%m-%d}"):
            for start, _, p in files(root, feed, dd):
                is_sweep = start.date() == d1.date() and start.hour == 0
                for body in lines(p):
                    for t, sid, ok in readings(feed, body):
                        t = t.astimezone(SGT)
                        if d0 <= t < d1 and ok:
                            seen[t].add(sid)
                            first[t] = min(first.get(t, start), start)
                            if is_sweep:
                                sweep[t].add(sid)
        if feed == "forecast":
            print(f"forecast: {len(seen)} issue times: " + ", ".join(f"{t:%H:%M}" for t in sorted(seen))
                  + f"; in the midnight-sweep files: {len(sweep)}")
            continue
        step = STEP_MIN[feed]
        expected = [d0 + timedelta(minutes=step * i) for i in range(24 * 60 // step)]
        missing = [t for t in expected if not seen.get(t)]
        per_station = Counter(s for t in seen for s in seen[t])
        only_next = sum(1 for t in expected if seen.get(t) and first[t].date() == d1.date())
        print(f"{feed}: reading times with a value {len(expected) - len(missing)}/{len(expected)}; stations "
              f"{len(per_station)}; times in the midnight-sweep files {sum(1 for t in expected if sweep.get(t))}; "
              f"times found only in next-day files {only_next}")
        if missing:
            print("  missing reading times: " + ", ".join(ranges(missing, step)))
        short = sorted((c, s) for s, c in per_station.items() if c < len(expected) - len(missing))
        print(f"  stations at every time that has data: {len(per_station) - len(short)}; short: "
              + (", ".join(f"{s} {c}" for c, s in short) or "none"))
        print(f"  stations per reading time (number of times): {dict(sorted(Counter(map(len, seen.values())).items()))}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", type=Path, help="local copy: <root>/<feed>/<YYYY-MM-DD>/*.jsonl")
    ap.add_argument("--now", required=True, help="ISO time with offset; the slot in progress is not counted")
    ap.add_argument("--slots", nargs="*", default=[], help="SGT days to count runs per slot for")
    ap.add_argument("--coverage", nargs="*", default=[], help="SGT days to count reading coverage for")
    args = ap.parse_args()
    now = datetime.fromisoformat(args.now)
    for day in args.slots:
        slot_report(args.root, day, now)
    for day in args.coverage:
        coverage(args.root, day)


if __name__ == "__main__":
    main()
