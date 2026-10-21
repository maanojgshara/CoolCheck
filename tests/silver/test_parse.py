from datetime import date, datetime, timezone

import pytest
from pyspark.sql import functions as F

from silver_fixtures import bronze_rows, page, wbgt_page
from coolcheck import silver as S
from coolcheck.bronze import bronze_columns
from coolcheck.timeutil import sgt_instant


@pytest.mark.parametrize("tz", ["UTC", "Asia/Singapore"])
def test_sgt_date_near_midnight_does_not_depend_on_session_tz(spark, tz):
    spark.conf.set("spark.sql.session.timeZone", tz)
    try:
        line = wbgt_page(("2025-03-01T23:55:00+08:00", [("S1", "26.0", "Low")]),
                         ("2025-03-02T00:00:00+08:00", [("S1", "26.0", "Low")]),
                         ("2025-03-02T00:05:00+08:00", [("S1", "26.0", "Low")]),
                         ("2025-03-01T16:10:00Z", [("S1", "26.0", "Low")]))
        rows = S.parse_wbgt(bronze_rows(spark, [line])).orderBy("reading_ts") \
            .select("reading_ts_raw", "sgt_date", "sgt_minute", "fail_sgt_offset", "fail_file_date_matches").collect()
        got = [(r.reading_ts_raw, r.sgt_date, r.sgt_minute, r.fail_sgt_offset, r.fail_file_date_matches) for r in rows]
        assert got == [
            ("2025-03-01T23:55:00+08:00", date(2025, 3, 1), 1435, False, False),
            ("2025-03-02T00:00:00+08:00", date(2025, 3, 2), 0, False, True),
            ("2025-03-02T00:05:00+08:00", date(2025, 3, 2), 5, False, True),
            ("2025-03-01T16:10:00Z", date(2025, 3, 2), 10, True, True),  # 00:10 SGT; offset flagged, converted right
        ]
        cut = spark.range(1).select(F.unix_seconds(sgt_instant(F.lit(date(2025, 7, 21)), 15)).alias("c")).first().c
        assert cut == int(datetime(2025, 7, 20, 16, 15, tzinfo=timezone.utc).timestamp())  # 2025-07-21 00:15 SGT
    finally:
        spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")


def test_bronze_columns_from_auto_loader_metadata(spark):
    df = spark.createDataFrame(
        [("x", ("dbfs:/Volumes/coolcheck/bronze/raw_files/wbgt/backfill/wbgt_2025-01-16.jsonl", "wbgt_2025-01-16.jsonl", 10,
                datetime(2026, 10, 21, 4, 0, tzinfo=timezone.utc))),
         ("y", ("/Volumes/coolcheck/bronze/raw_files/wbgt/live/2026-10-21T0015.jsonl", "2026-10-21T0015.jsonl", 5,
                datetime(2026, 10, 21, 4, 0, tzinfo=timezone.utc)))],
        "value STRING, _metadata STRUCT<file_path: STRING, file_name: STRING, file_size: LONG, file_modification_time: TIMESTAMP>")
    rows = {r.raw: r for r in bronze_columns(df).collect()}
    assert rows["x"].source_file.startswith("/Volumes/") and rows["x"].source_kind == "backfill"
    assert rows["x"].file_date == date(2025, 1, 16)
    assert rows["y"].source_kind == "live" and rows["y"].file_date is None


def test_wbgt_flags_keep_every_row(spark):
    line = wbgt_page(("2025-03-01T14:00:00+08:00", [("S1", "26.1", "Low"), ("S2", None, "NA"), ("S3", "14.3", "Low"),
                                                     ("S4", "36.6", "High"), ("S5", "abc", "Hot")]))
    rows = {r.station_id: r for r in S.parse_wbgt(bronze_rows(spark, [line])).collect()}
    assert len(rows) == 5
    assert not any(getattr(rows["S1"], f"fail_{k}") for k in S.WBGT_RULES)
    assert rows["S2"].fail_heat_stress_known and rows["S2"].fail_wbgt_present and not rows["S2"].fail_wbgt_in_range
    assert rows["S3"].fail_wbgt_in_range and rows["S4"].fail_wbgt_in_range and not rows["S4"].fail_heat_stress_known
    assert rows["S5"].wbgt is None and rows["S5"].fail_wbgt_present and rows["S5"].fail_heat_stress_known


def test_quarantine_reasons(spark):
    good = wbgt_page(("2025-03-01T14:00:00+08:00", [("S1", "26.1", "Low")]))
    bad = ["not json", '{"code": 1, "errorMsg": "boom", "data": null}', '{"code": 0, "errorMsg": ""}']
    q = S.quarantine_lines(bronze_rows(spark, [good] + bad), "wbgt").collect()
    assert sorted(r.reason for r in q) == ["api_code_1", "no_data_field", "unparsable_json"]
    assert S.parse_wbgt(bronze_rows(spark, [good] + bad)).count() == 1


def test_rainfall_parse_and_flags(spark):
    line = page("rainfall", {"stations": [{"id": "S1", "deviceId": "S1", "name": "One", "location": {"latitude": 1.3, "longitude": 103.8}}],
                             "readings": [{"timestamp": "2025-03-01T10:05:00+08:00",
                                           "data": [{"stationId": "S1", "value": 0}, {"stationId": "S1x", "value": -1.5}]}],
                             "readingType": "TB1 Rainfall 5 Minute Total F", "readingUnit": "mm"})
    rows = {r.station_id: r for r in S.parse_rainfall(bronze_rows(spark, [line], "rainfall_2025-03-01.jsonl")).collect()}
    assert rows["S1"].rainfall_mm == 0.0 and rows["S1"].station_name == "One" and not rows["S1"].fail_station_listed
    assert rows["S1x"].fail_station_listed and rows["S1x"].fail_rain_non_negative


def _fc(issue, start, end, text, date_="2025-01-17"):
    return {"date": date_, "timestamp": issue, "updatedTimestamp": issue,
            "general": {"temperature": {"low": 24, "high": 33, "unit": "Degrees Celsius"},
                        "relativeHumidity": {"low": 60, "high": 95, "unit": "Percentage"},
                        "forecast": {"code": "TL", "text": "Thundery Showers"},
                        "validPeriod": {"start": start, "end": end, "text": text},
                        "wind": {"speed": {"low": 10, "high": 20}, "direction": "NNE"}},
            "periods": [{"timePeriod": {"start": start, "end": end, "text": "x"},
                         "regions": {"west": {"code": "SH", "text": "Showers"}, "east": {"code": "SH", "text": "Showers"}}}]}


def test_forecast_validity_rules(spark):
    recs = [
        _fc("2025-01-17T23:11:00+08:00", "2025-01-18T00:00:00+08:00", "2025-01-19T00:00:00+08:00", "0 AM 18 Jan to 0 AM 19 Jan"),
        _fc("2025-01-17T23:30:00+08:00", "2025-01-18T00:00:00+08:00", "2025-01-20T00:00:00+08:00", "0 AM 18 Jan to 0 AM 19 Jan"),
        _fc("2025-01-17T17:30:00+08:00", "2025-01-17T18:00:00+08:00", "2024-01-18T18:00:00+08:00", "6 PM 17 Jan to 6 PM 18 Jan"),
        _fc("2025-01-17T11:30:00+08:00", "2025-01-17T12:00:00+08:00", "2025-01-18T12:00:00+08:00", "12 PM 17 Jan to 12 PM 18 Jan"),
    ]
    line = page("forecast", {"records": recs})
    rows = {r.issue_ts_raw: r for r in S.parse_forecast(bronze_rows(spark, [line], "forecast_2025-01-17.jsonl", file_date=date(2025, 1, 17))).collect()}
    ok, h48, yr, noon = (rows[k] for k in ("2025-01-17T23:11:00+08:00", "2025-01-17T23:30:00+08:00",
                                            "2025-01-17T17:30:00+08:00", "2025-01-17T11:30:00+08:00"))
    assert not any(getattr(ok, f"fail_{k}") for k in S.FORECAST_RULES)
    assert not any(getattr(noon, f"fail_{k}") for k in S.FORECAST_RULES)  # "12 PM" is noon
    assert h48.valid_hours == 48 and h48.fail_validity_24h and h48.fail_validity_text_agrees
    assert not h48.fail_validity_end_after_start
    assert yr.fail_validity_end_after_start and yr.fail_validity_24h
    assert not yr.fail_validity_text_agrees  # the text has no year, so a wrong year passes this rule
    assert ok.periods[0].regions["west"].code == "SH"


def test_dedupe_order_live_then_mtime_then_path(spark):
    line_a = wbgt_page(("2025-03-01T14:00:00+08:00", [("S1", "26.1", "Low")]))
    line_b = wbgt_page(("2025-03-01T14:00:00+08:00", [("S1", "26.2", "Low")]))
    t1, t2 = datetime(2026, 10, 20, 1, tzinfo=timezone.utc), datetime(2026, 10, 21, 1, tzinfo=timezone.utc)
    copies = (bronze_rows(spark, [line_a], "wbgt_2025-03-01.jsonl", mtime=t2)                     # backfill, later mtime
              .unionByName(bronze_rows(spark, [line_b], "2025-03-01T1415.jsonl", kind="live", mtime=t1)))  # live, earlier
    parsed = S.parse_wbgt(copies)
    winner = parsed.orderBy(S.sequence_col().desc()).first()
    assert winner.source_kind == "live" and winner.wbgt_raw == "26.2"

    same_kind = (bronze_rows(spark, [line_a], "wbgt_2025-03-01.jsonl", mtime=t1)
                 .unionByName(bronze_rows(spark, [line_b], "wbgt_2025-03-01b.jsonl", mtime=t2)))
    assert S.parse_wbgt(same_kind).orderBy(S.sequence_col().desc()).first().wbgt_raw == "26.2"  # later mtime

    same_mtime = (bronze_rows(spark, [line_b], "wbgt_2025-03-01a.jsonl", mtime=t1)
                  .unionByName(bronze_rows(spark, [line_a], "wbgt_2025-03-01b.jsonl", mtime=t1)))
    assert S.parse_wbgt(same_mtime).orderBy(S.sequence_col().desc()).first().wbgt_raw == "26.1"  # later path ("b")
