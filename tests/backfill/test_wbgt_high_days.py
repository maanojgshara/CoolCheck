"""wbgt_high_days.py on a small fixture of raw WBGT lines."""
import json
from datetime import date

import backfill as bf
import wbgt_high_days as hd


def reading(sid, cat, wbgt="30.0"):
    r = {"station": {"id": sid, "name": f"name {sid}", "townCenter": "x"}, "location": {"latitude": 1.3, "longitude": 103.8},
         "heatStress": cat}
    if wbgt is not None:
        r["wbgt"] = wbgt
    return r


def body(*records):
    return {"code": 0, "data": {"records": [{"datetime": dt, "updatedTimestamp": dt, "item": {"readings": list(rs)}}
                                            for dt, rs in records]}, "errorMsg": ""}


DAY1 = [
    body(("2025-01-16T13:00:00+08:00", [reading("S124", "High", "33.2"), reading("S300", "Moderate", "31.5")]),
         ("2025-01-16T14:00:00+08:00", [reading("S124", "NA", None), reading("S300", "Low", "29.0")])),
    body(("2025-01-16T13:00:00+08:00", [reading("S124", "High", "33.2"), reading("S300", "Moderate", "31.5")]),  # duplicate page
         ("2025-01-16T23:59:00+08:00", [reading("S125", "High", "33.0")]),
         ("2025-01-17T00:00:00+08:00", [reading("S125", "Low", "27.0")])),  # next SGT day, inside the day-1 file
]
DAY2 = [
    body(("2025-01-17T13:00:00+08:00", [reading("S300", "High", "34.0"), reading("S126", "NA", None)]),
         ("2025-01-16T16:30:00Z", [reading("S127", "Low", "28.0"), reading("S999", "Extreme", "40.0")])),  # 00:30 SGT on the 17th
]


def write_fixture(out):
    state = bf.State(out)
    raw = state.raw_dir("wbgt")
    raw.mkdir(parents=True)
    for d, pages in (("2025-01-16", DAY1), ("2025-01-17", DAY2)):
        (raw / f"wbgt_{d}.jsonl").write_bytes(b"".join(json.dumps(p, separators=(",", ":")).encode() + b"\n" for p in pages))
    state.append({"event": "day", "feed": "wbgt", "date": "2025-01-16", "status": "short", "distinct_on_day": 3, "calls": 2})
    state.append({"event": "day", "feed": "wbgt", "date": "2025-01-17", "status": "short", "distinct_on_day": 1, "calls": 1})
    state.append({"event": "run_end", "feeds": ["wbgt"], "calls": 4, "statuses": {"200": 3, "429": 1}, "key": "absent", "stopped": None})
    return state


def test_aggregation(tmp_path):
    state = write_fixture(tmp_path / "out")
    d = hd.Data().load(state.raw_dir("wbgt"))
    assert d.dupes == 2 and d.off_file_date == 1  # 00:00 SGT in the day-1 file; 16:30Z in the day-2 file is the 17th SGT
    assert d.cats["NA"] == 2 and d.cats["Extreme"] == 1
    allp, o8 = d.per_day(), d.per_day(set(hd.ORIGINAL_8))
    # 16th: S124 High, S300 (Moderate/Low), S125 High at 23:59. 17th: S125 Low at 00:00, S300 High, S127 Low; S126 NA-only and S999 'Extreme' excluded.
    assert dict(allp) == {date(2025, 1, 16): [3, 2], date(2025, 1, 17): [3, 1]}
    assert dict(o8) == {date(2025, 1, 16): [2, 2], date(2025, 1, 17): [2, 0]}
    lo, hi = date(2025, 1, 1), date(2025, 6, 30)
    assert hd.totals(allp, lo, hi) == {"days": 2, "sd": 6, "hsd": 3, "hdays": 2}
    assert hd.totals(o8, lo, hi) == {"days": 2, "sd": 4, "hsd": 2, "hdays": 1}
    assert d.daily[("S124", date(2025, 1, 16))]["max_cat"] == "High" and d.daily[("S124", date(2025, 1, 16))]["na"] == 1
    assert d.ranges["High"] == (33.0, 34.0) and d.ranges["Moderate"] == (31.5, 31.5)


def test_vs_rule():
    assert hd.vs_rule(3) == "below 30"
    assert hd.vs_rule(29) == "below 30 (within the rule's 'about')"
    assert hd.vs_rule(30) == "at or above 30 (within the rule's 'about')"
    assert hd.vs_rule(36) == "at or above 30"


def test_report_end_to_end(tmp_path):
    state = write_fixture(tmp_path / "out")
    rep = tmp_path / "r.md"
    assert hd.main(["--out-dir", str(state.out), "--report", str(rep)]) == 0
    text = rep.read_text(encoding="utf-8")
    assert "| Jan–Jun 2025 | 2025-01-16 – 2025-01-17 | 2 | 6 | 3 | below 30 | 2 | 4 | 2 | below 30 | 1 |" in text
    assert "| Sep–Oct 2026 | not in the backfill |" in text
    assert "Other values, also excluded: {'Extreme': 1}" in text
    assert "highest Moderate 31.5, lowest High 33.0" in text
    assert (state.out / "analysis" / "wbgt_station_daily.csv").exists()
