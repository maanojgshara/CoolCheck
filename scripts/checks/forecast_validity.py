"""Forecast validity recount from the raw backfill files (no API calls): Day 2 step 3.

Run from the repo root:
    .venv\\Scripts\\python scripts/checks/forecast_validity.py [--data <coolcheck-data>]

Counts, per record (one issue version = one record in a forecast_<date>.jsonl file):
- the notes' original definition: validPeriod.end before validPeriod.start;
- the wider classes used by the Silver rules: end equal to start, a window that is not 24 h, a start more than 6 h
  before or 24 h after the issue (`timestamp`), text that disagrees with start/end, text that does not parse;
- for the 48-hour windows: by issue slot, by month, by what validPeriod.text says;
- the 00:15 cut-off rule (§14.4) per target day, using the stated validity and the text's validity, and where they differ.
Writes docs/checks/forecast_validity.md.
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SGT = timezone(timedelta(hours=8))
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
TEXT_RE = re.compile(r"^\s*(\d{1,2}) (AM|PM) (\d{1,2}) ([A-Za-z]{3}) to (\d{1,2}) (AM|PM) (\d{1,2}) ([A-Za-z]{3})\s*$")
CUTOFF = time(0, 15)


def slot(t):
    """Issue slot by SGT time of `timestamp` (the heuristic grouping in check10.md)."""
    m = t.hour * 60 + t.minute
    for name, lo in (("05:30", 325), ("11:30", 685), ("17:30", 1045)):
        if lo <= m < lo + 20:
            return name
    return "23:xx" if t.hour == 23 else "ad-hoc"


def text_window(text, start_hint):
    """validPeriod.text -> (start, end) in SGT, year taken from the stated start (crossing New Year handled)."""
    m = TEXT_RE.match(text or "")
    if not m or m.group(4) not in MONTHS or m.group(8) not in MONTHS:
        return None
    def hour(h, ap):
        return int(h) % 12 + (12 if ap == "PM" else 0)
    y = start_hint.year
    sm, em = MONTHS[m.group(4)], MONTHS[m.group(8)]
    if start_hint.month == 12 and sm == 1:
        y += 1
    try:
        s = datetime(y, sm, int(m.group(3)), hour(m.group(1), m.group(2)), tzinfo=SGT)
        e = datetime(y + (1 if em < sm else 0), em, int(m.group(7)), hour(m.group(5), m.group(6)), tzinfo=SGT)
    except ValueError:
        return None
    return s, e


def load(raw):
    recs = []
    for f in sorted((raw / "forecast").rglob("*.jsonl")):
        for ln in f.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            for r in (json.loads(ln).get("data") or {}).get("records") or []:
                vp = r["general"]["validPeriod"]
                issue = datetime.fromisoformat(r["timestamp"]).astimezone(SGT)
                s = datetime.fromisoformat(vp["start"]).astimezone(SGT)
                e = datetime.fromisoformat(vp["end"]).astimezone(SGT)
                recs.append({"file": f.name, "issue": issue, "updated": r.get("updatedTimestamp"), "start": s, "end": e,
                             "text": vp.get("text"), "date": r.get("date"), "hours": (e - s).total_seconds() / 3600,
                             "issue_to_start": (s - issue).total_seconds() / 3600,
                             "text_win": text_window(vp.get("text"), s)})
    return recs


def pick(recs, target, use_text):
    """Latest issue at or before T 00:15 whose validity covers T 06:00 to 18:00 (§14.4 option B)."""
    cut = datetime.combine(target, CUTOFF, SGT)
    lo, hi = datetime.combine(target, time(6), SGT), datetime.combine(target, time(18), SGT)
    best = None
    for r in recs:
        win = r["text_win"] if use_text else (r["start"], r["end"])
        if r["issue"] <= cut and win and win[0] <= lo and win[1] >= hi:
            if best is None or (r["issue"], r["updated"] or "") > (best["issue"], best["updated"] or ""):
                best = r
    return best


def table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO.parent / "coolcheck-data"))
    ap.add_argument("--out", default=str(REPO / "docs" / "checks" / "forecast_validity.md"))
    a = ap.parse_args()
    recs = load(Path(a.data) / "raw")
    files = sorted({r["file"] for r in recs})
    first, last = files[0][9:19], files[-1][9:19]
    distinct = {(r["issue"], r["updated"]) for r in recs}

    end_before = [r for r in recs if r["end"] < r["start"]]
    classes = {
        "end before start (the notes' definition)": end_before,
        "end equal to start": [r for r in recs if r["end"] == r["start"]],
        "window not 24 h": [r for r in recs if r["hours"] != 24],
        "  of which 48 h": [r for r in recs if r["hours"] == 48],
        "start more than 6 h before or 24 h after the issue": [r for r in recs if not -6 <= r["issue_to_start"] <= 24],
        "text does not parse": [r for r in recs if r["text_win"] is None],
        "text disagrees with start/end (day, month, hour; the text has no year)":
            [r for r in recs if r["text_win"] and (r["text_win"][0].replace(year=1) != r["start"].replace(year=1)
                                                   or r["text_win"][1].replace(year=1) != r["end"].replace(year=1))],
        "record `date` differs from the issue's SGT date": [r for r in recs if r["date"] != r["issue"].date().isoformat()],
    }

    L = ["# Forecast validity recount (Day 2 step 3)", "",
         f"Generated {datetime.now(SGT):%Y-%m-%d %H:%M} SGT by `scripts/checks/forecast_validity.py` from the raw backfill files "
         f"(`coolcheck-data/raw/forecast/`, {len(files)} files, {first} to {last}; no file for 2025-07-20, NEA returned no data). "
         f"{len(recs):,} records ({len(distinct):,} distinct issue time and updatedTimestamp pairs). Issue time = `timestamp` (§14.4).", "",
         "## 1. The notes' definition: validity end before the start", ""]
    L.append(f"**{len(end_before)} records** in these files have `validPeriod.end` before `validPeriod.start`.")
    L += table(["file", "issue time (SGT)", "updatedTimestamp", "validPeriod.start", "validPeriod.end", "text"],
               [(r["file"], f"{r['issue']:%Y-%m-%d %H:%M}", r["updated"], f"{r['start']:%Y-%m-%d %H:%M}",
                 f"{r['end']:%Y-%m-%d %H:%M}", r["text"]) for r in sorted(end_before, key=lambda r: r["issue"])])
    by_window = Counter(r["issue"].strftime("%Y-%m") for r in end_before)
    L += ["", "By month of issue: " + (", ".join(f"{k} {v}" for k, v in sorted(by_window.items())) or "none") + "."]
    L += ["", "The notes' 12 are placed on 31 Dec 2023 and 31 Dec 2025 (§12.6 item 10, from check 10's API sample since "
          "Jan 2023). These files start on 2025-01-16, so they can confirm or refute only the 31 Dec 2025 part; the 31 Dec "
          "2023 part (and any other day before 2025-01-16) cannot be checked from them.", ""]

    L += ["## 2. Wider rule classes (the Silver rules)", ""]
    L += table(["class", "records", "by month of issue"],
               [(k, len(v), ", ".join(f"{m} {n}" for m, n in sorted(Counter(r['issue'].strftime('%Y-%m') for r in v).items())) or "—")
                for k, v in classes.items()])
    other = Counter(r["hours"] for r in recs if r["hours"] not in (24, 48))
    L += ["", "Window lengths other than 24 and 48 h: " + (", ".join(f"{h:g} h × {n}" for h, n in sorted(other.items())) or "none") + ".", ""]

    h48 = classes["  of which 48 h"]
    L += [f"## 3. The {len(h48)} records with a 48-hour window", ""]
    all_slot = Counter(slot(r["issue"].time()) for r in recs)
    s48 = Counter(slot(r["issue"].time()) for r in h48)
    L += ["By issue slot (SGT time of `timestamp`; 05:30 = 05:25–05:44, 11:30 = 11:25–11:44, 17:30 = 17:25–17:44, "
          "23:xx = 23:00–23:59, else ad-hoc):", ""]
    L += table(["slot", "48-h records", "all records in the slot", "share"],
               [(s, s48.get(s, 0), all_slot[s], f"{s48.get(s, 0) / all_slot[s]:.0%}") for s in ("05:30", "11:30", "17:30", "23:xx", "ad-hoc")])
    m48, mall = Counter(r["issue"].strftime("%Y-%m") for r in h48), Counter(r["issue"].strftime("%Y-%m") for r in recs)
    L += ["", "By month of issue:", ""]
    L += table(["month", "48-h records", "all records"], [(m, m48.get(m, 0), mall[m]) for m in sorted(mall)])
    says = Counter()
    for r in h48:
        tw = r["text_win"]
        if tw is None:
            says["text does not parse"] += 1
        else:
            th = (tw[1] - tw[0]).total_seconds() / 3600
            same_start = tw[0].replace(year=1) == r["start"].replace(year=1)
            same_end = tw[1].replace(year=1) == r["end"].replace(year=1)
            says[f"text says {th:g} h; start {'agrees' if same_start else 'differs'}; end {'agrees' if same_end else 'differs'}"] += 1
    L += ["", "What validPeriod.text says for them:", ""]
    L += table(["text", "records"], sorted(says.items(), key=lambda kv: -kv[1]))
    forms = Counter(re.sub(r"\d+", "N", r["text"] or "") for r in h48)
    L += ["", "Text forms (digits as N): " + ", ".join(f"`{k}` × {v}" for k, v in forms.most_common(6)) + ".", ""]
    ex = sorted(h48, key=lambda r: r["issue"])[:5]
    L += ["First five, as examples:", ""]
    L += table(["file", "issue (SGT)", "start", "end", "text"],
               [(r["file"], f"{r['issue']:%Y-%m-%d %H:%M}", f"{r['start']:%Y-%m-%d %H:%M}", f"{r['end']:%Y-%m-%d %H:%M}", r["text"]) for r in ex])

    # 4. the 00:15 cut-off rule
    by_day = defaultdict(list)
    for r in recs:
        for d in (r["issue"].date(), r["issue"].date() + timedelta(days=1)):
            by_day[d].append(r)
    d0, d1 = date.fromisoformat(first) + timedelta(days=1), date.fromisoformat(last) + timedelta(days=1)
    n = none_stated = none_text = differ = picked48 = picked48_23 = 0
    differ_rows, none_rows = [], []
    d = d0
    while d <= d1:
        cand = by_day[d - timedelta(days=1)] + by_day[d]
        ps, pt = pick(cand, d, False), pick(cand, d, True)
        n += 1
        none_stated += ps is None
        none_text += pt is None
        if ps is None:
            none_rows.append(d)
        if ps is not None and ps["hours"] == 48:
            picked48 += 1
            picked48_23 += slot(ps["issue"].time()) == "23:xx"
        if (ps and (ps["issue"], ps["updated"])) != (pt and (pt["issue"], pt["updated"])):
            differ += 1
            differ_rows.append((d, ps and f"{ps['issue']:%m-%d %H:%M} ({ps['hours']:g} h)", pt and f"{pt['issue']:%m-%d %H:%M}"))
        d += timedelta(days=1)
    L += ["## 4. Effect on the 00:15 cut-off rule (§14.4 option B)", "",
          f"Rule: for target day T, the latest issue at or before T 00:15 SGT whose validity covers T 06:00 to 18:00. "
          f"Target days {d0} to {d1} ({n} days).", "",
          f"- With the stated validPeriod: no issue on {none_stated} days ({', '.join(map(str, none_rows)) or 'none'}).",
          f"- With the validity read from the text: no issue on {none_text} days.",
          f"- The chosen issue is a 48-hour record on {picked48} days; {picked48_23} of those are 23:xx issues.",
          f"- The choice differs between stated and text validity on {differ} days."]
    if differ_rows:
        L += [""] + table(["target day", "chosen with stated validity", "chosen with text validity"], differ_rows[:40])
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
