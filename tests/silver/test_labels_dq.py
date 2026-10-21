from datetime import date, datetime, timedelta, timezone

from silver_fixtures import bronze_rows, wbgt_page
from coolcheck import dq, labels
from coolcheck import silver as S

DAY = date(2025, 3, 1)
SGT = timezone(timedelta(hours=8))
READ_SCHEMA = ("station_id STRING, station_name STRING, reading_ts TIMESTAMP, sgt_date DATE, sgt_minute INT, "
               "heat_stress STRING, wbgt DOUBLE, fail_wbgt_in_range BOOLEAN")


def _r(sid, minute, hs="Low", w=28.0, out_of_range=False):
    ts = datetime(DAY.year, DAY.month, DAY.day, tzinfo=SGT) + timedelta(minutes=minute)
    return (sid, f"name {sid}", ts, DAY, minute, hs, None if hs == "NA" else w, out_of_range)


def _slots(sid, n, start=600):
    return [_r(sid, start + 15 * i) for i in range(n)]


def test_daily_label_rule_and_coverage(spark):
    rows = (_slots("A", 32)[:-2] + [_r("A", 600 + 15 * 30, "Moderate", 31.5), _r("A", 600 + 15 * 31, "High", 37.0, True)]
            + _slots("B", 23) + _slots("C", 24)
            + [_r("D", 600, "High", 33.2), _r("D", 615)]
            + [_r("E", 600, "NA"), _r("E", 615, "NA")]
            + _slots("F", 31) + [_r("F", 600 + 15 * 31, "High", 33.5)]
            + [_r("G", 540, "High", 33.1)] + _slots("G", 24))  # a High at 09:00, outside the peak window
    readings = spark.createDataFrame(rows, READ_SCHEMA)
    late_ts = datetime(DAY.year, DAY.month, DAY.day, tzinfo=SGT) + timedelta(minutes=600 + 15 * 31)
    arrival = spark.createDataFrame([("F", late_ts, True)], "station_id STRING, reading_ts TIMESTAMP, late_over_1h BOOLEAN")
    got = {r.station_id: r for r in labels.station_daily_label(readings, arrival).collect()}

    a = got["A"]
    assert (a.label, a.label_if_out_of_range_excluded, a.peak_slots, a.low_coverage, a.usable) == ("High", "Moderate", 32, False, True)
    assert (a.n_high, a.n_moderate, a.n_out_of_range, a.max_wbgt) == (1, 1, 1, 37.0)
    assert (got["B"].label, got["B"].peak_slots, got["B"].low_coverage, got["B"].usable) == ("Low", 23, True, False)
    assert (got["C"].peak_slots, got["C"].low_coverage, got["C"].usable) == (24, False, True)
    assert (got["D"].label, got["D"].low_coverage, got["D"].usable) == ("High", True, True)  # High stands
    e = got["E"]
    assert (e.label, e.n_na, e.n_valid, e.usable, e.no_label_reason) == (None, 2, 0, False, "no_valid_reading")
    assert (got["F"].label, got["F"].label_if_late_excluded, got["F"].n_late) == ("High", "Low", 1)
    assert (got["G"].label, got["G"].peak_slots) == ("High", 24)


def test_dq_day_lists_short_and_missing_days(spark):
    d2 = date(2025, 3, 2)
    base = datetime(2025, 3, 1, tzinfo=SGT)
    w = [("S1", base + timedelta(minutes=15 * i), DAY) for i in range(96)] + \
        [("S1", base + timedelta(days=1, minutes=15 * i), d2) for i in range(10)]
    r = [("S9", base + timedelta(minutes=5 * i), DAY) for i in range(288)]
    f = [(base + timedelta(hours=23), base + timedelta(hours=23), DAY)]
    sch = "station_id STRING, reading_ts TIMESTAMP, sgt_date DATE"
    out = dq.dq_day(spark.createDataFrame(w, sch), spark.createDataFrame(r, sch),
                    spark.createDataFrame(f, "issue_ts TIMESTAMP, updated_ts TIMESTAMP, issue_sgt_date DATE"))
    got = {(x.feed, x.sgt_date): (x.status, x.note) for x in out.collect()}
    assert got[("wbgt", DAY)] == ("ok", "96 of 96 timestamps")
    assert got[("wbgt", d2)] == ("short", "10 of 96 timestamps")
    assert got[("rainfall", d2)] == ("no_data", "0 of 288 timestamps")
    assert got[("forecast", DAY)] == ("ok", "1 issues") and got[("forecast", d2)][0] == "no_data"


def test_dq_events_counts_duplicates_conflicts_and_rule_failures(spark):
    t1, t2 = datetime(2026, 10, 20, 1, tzinfo=timezone.utc), datetime(2026, 10, 21, 1, tzinfo=timezone.utc)
    same = wbgt_page(("2025-03-01T14:00:00+08:00", [("S1", "26.1", "Low"), ("S2", "27.0", "Low")]))
    changed = wbgt_page(("2025-03-01T14:00:00+08:00", [("S1", "26.1", "Low"), ("S2", "27.5", "Low")]))
    no_key = wbgt_page(("not a time", [("S3", "26.0", "Low")]))
    all_copies = S.parse_wbgt(bronze_rows(spark, [same, no_key], "wbgt_2025-03-01.jsonl", mtime=t1)
                              .unionByName(bronze_rows(spark, [changed], "wbgt_2025-03-01b.jsonl", mtime=t2)))
    quarantine = S.quarantine_lines(bronze_rows(spark, ["oops"]), "wbgt")
    arrival = S.first_arrival(all_copies)
    ev = {(r.feed, r.check_name): r.n for r in dq.dq_events({"wbgt": all_copies}, quarantine, {"wbgt": arrival}).collect()}
    assert ev[("wbgt", "rule:has_key")] == 1
    assert ev[("wbgt", "copies_with_key")] == 4 and ev[("wbgt", "distinct_keys")] == 2
    assert ev[("wbgt", "keys_with_duplicate_copies")] == 2 and ev[("wbgt", "keys_with_conflicting_copies")] == 1
    assert ev[("wbgt", "quarantine:unparsable_json")] == 1
    assert ev[("wbgt", "readings_first_arrived_over_1h_late")] == 0  # backfill only
    conflicts = dq.dq_conflicts(all_copies, "wbgt").collect()
    assert len(conflicts) == 2 and {c.n_versions for c in conflicts} == {2} and all('"S2"' in c.key for c in conflicts)


def test_lateness_ignores_readings_timed_before_the_first_live_file(spark):
    def at(h, m=0):
        return f"2026-10-22T{h:02d}:{m:02d}:00+08:00"
    l1, l2 = datetime(2026, 10, 22, 10, 0, tzinfo=SGT), datetime(2026, 10, 22, 12, 0, tzinfo=SGT)
    first = wbgt_page((at(4), [("S1", "29.0", "Low")]), (at(9, 50), [("S1", "30.0", "Low")]))   # 6 h of history
    second = wbgt_page((at(9, 50), [("S1", "30.0", "Low")]), (at(10, 30), [("S1", "30.2", "Low")]),
                       (at(11, 50), [("S1", "30.4", "Low")]))
    all_copies = S.parse_wbgt(
        bronze_rows(spark, [first], "wbgt_2026-10-22T100000_1.jsonl", kind="live", mtime=l1)
        .unionByName(bronze_rows(spark, [second], "wbgt_2026-10-22T120000_2.jsonl", kind="live", mtime=l2))
        .unionByName(bronze_rows(spark, [first], "wbgt_2026-10-22.jsonl", mtime=l2, file_date=date(2026, 10, 22))))
    arrival = {r.reading_ts.astimezone(SGT).strftime("%H:%M"): (r.before_first_live, r.late_over_1h)
               for r in S.first_arrival(all_copies).collect()}
    # every reading in the first live file is timed before it lands, so none of them is judged
    assert arrival == {"04:00": (True, False),    # 6 h old when the first live file landed: history, not late
                       "09:50": (True, False),    # also in the first file (10 min old): not judged
                       "10:30": (False, True),    # first carried 90 min after its time: late
                       "11:50": (False, False)}   # first carried 10 min after its time
    quarantine = S.quarantine_lines(bronze_rows(spark, ["oops"]), "wbgt")
    ev = {(r.feed, r.check_name): (r.n, r.detail) for r in
          dq.dq_events({"wbgt": all_copies}, quarantine, {"wbgt": S.first_arrival(all_copies)}).collect()}
    n, detail = ev[("wbgt", "readings_first_arrived_over_1h_late")]
    assert n == 1 and detail.startswith("of 4 readings seen in live files, 2 of them timed before the first live file")


def test_station_gaps_over_one_hour(spark):
    base = datetime(2025, 3, 1, 10, tzinfo=SGT)
    rows = [("S1", base, "Low"), ("S1", base + timedelta(minutes=15), "Low"), ("S1", base + timedelta(minutes=30), "NA"),
            ("S1", base + timedelta(minutes=90), "Low"), ("S2", base, "Low"), ("S2", base + timedelta(minutes=60), "Low")]
    df = spark.createDataFrame(rows, "station_id STRING, reading_ts TIMESTAMP, heat_stress STRING")
    gaps = dq.station_gaps(df, "wbgt", "heat_stress IN ('Low', 'Moderate', 'High')").collect()
    assert [(g.station_id, g.gap_minutes) for g in gaps] == [("S1", 75.0)]  # the NA reading does not end the gap
