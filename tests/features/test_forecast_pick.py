"""Forecast selection (docs/design/backtest.md §3.3) against the known bad records of docs/checks/forecast_validity.md.

The real records are copied from the raw backfill files named in the comments, keeping the fields the rule reads."""
from datetime import date, datetime

import pytest
from pyspark.sql import functions as F

from feature_fixtures import fc_record, forecast_versions
from coolcheck.features import forecast_for_targets

# forecast_2025-12-30.jsonl: a 24-hour issue, and the 23:00 issue whose stored end (2025-01-02) is before its start
DEC30_1744 = fc_record("2025-12-30T17:44:00+08:00", "2025-12-30T18:00:00+08:00", "2025-12-31T18:00:00+08:00",
                       "6 PM 30 Dec to 6 PM 31 Dec", updated="2025-12-30T17:51:03+08:00", high=33)
DEC30_2300 = fc_record("2025-12-30T23:00:00+08:00", "2025-12-31T00:00:00+08:00", "2025-01-02T00:00:00+08:00",
                       "0 AM 31 Dec to 0 AM 1 Jan", updated="2025-12-30T23:10:47+08:00", high=33)
# forecast_2025-12-31.jsonl: five daytime issues whose stored end is a year early ...
DEC31_DAY = [fc_record(i, s, e, txt, updated=u, high=h, forecast_text=ft) for i, u, s, e, txt, h, ft in (
    ("2025-12-31T05:31:00+08:00", "2025-12-31T05:40:47+08:00", "2025-12-31T06:00:00+08:00", "2025-01-01T06:00:00+08:00",
     "6 AM 31 Dec to 6 AM 1 Jan", 33, "Thundery Showers"),
    ("2025-12-31T09:00:00+08:00", "2025-12-31T09:11:01+08:00", "2025-12-31T06:00:00+08:00", "2025-01-01T06:00:00+08:00",
     "6 AM 31 Dec to 6 AM 1 Jan", 33, "Thundery Showers"),
    ("2025-12-31T11:32:00+08:00", "2025-12-31T11:40:58+08:00", "2025-12-31T12:00:00+08:00", "2025-01-01T12:00:00+08:00",
     "12 PM 31 Dec to 12 PM 1 Jan", 33, "Thundery Showers"),
    ("2025-12-31T14:07:00+08:00", "2025-12-31T14:10:52+08:00", "2025-12-31T12:00:00+08:00", "2025-01-01T12:00:00+08:00",
     "12 PM 31 Dec to 12 PM 1 Jan", 32, "Showers"),
    ("2025-12-31T15:54:00+08:00", "2025-12-31T16:00:41+08:00", "2025-12-31T12:00:00+08:00", "2025-01-01T12:00:00+08:00",
     "12 PM 31 Dec to 12 PM 1 Jan", 32, "Showers"))]
# ... and the 23:04 issue whose stored start is a year early
DEC31_2304 = fc_record("2025-12-31T23:04:00+08:00", "2025-01-01T00:00:00+08:00", "2025-01-02T00:00:00+08:00",
                       "0 AM 1 Jan to 0 AM 2 Jan", updated="2025-12-31T23:10:57+08:00", high=33)
# forecast_2026-01-01.jsonl: issued on 1 Jan, stored start a year early
JAN01 = [fc_record(i, "2025-01-01T06:00:00+08:00", "2025-01-02T06:00:00+08:00", "6 AM 1 Jan to 6 AM 2 Jan", updated=u, high=h)
         for i, u, h in (("2026-01-01T05:35:00+08:00", "2026-01-01T05:40:54+08:00", 33),
                         ("2026-01-01T11:15:00+08:00", "2026-01-01T11:20:37+08:00", 32))]
# forecast_2025-01-16.jsonl: both with a stored 48-hour window
JAN16_0333 = fc_record("2025-01-16T03:33:00+08:00", "2025-01-17T00:00:00+08:00", "2025-01-19T00:00:00+08:00",
                       "0 AM 17 Jan to 0 AM 18 Jan", updated="2025-01-16T03:40:46+08:00", high=33)
JAN16_2308 = fc_record("2025-01-16T23:08:00+08:00", "2025-01-17T00:00:00+08:00", "2025-01-19T00:00:00+08:00",
                       "0 AM 17 Jan to 0 AM 18 Jan", updated="2025-01-16T23:21:05+08:00", high=30)
# forecast_2025-07-19.jsonl: a stored 48-hour window; NEA returned no forecast data for 2025-07-20
JUL19_2302 = fc_record("2025-07-19T23:02:00+08:00", "2025-07-20T00:00:00+08:00", "2025-07-22T00:00:00+08:00",
                       "0 AM 20 Jul to 0 AM 21 Jul", updated="2025-07-19T23:11:18+08:00", high=34, forecast_text="Showers")


def _s(iso):
    return int(datetime.fromisoformat(iso).timestamp())


def _pick(spark, records, targets, cutoff_minutes=15):
    fc = forecast_versions(spark, *records)
    t = spark.createDataFrame([(d,) for d in targets], "target_date DATE")
    rows = forecast_for_targets(fc, t, cutoff_minutes).select(
        "target_date", "forecast_missing", "fc_temp_high", "fc_text", "fc_text_agrees", "fc_lead_h",
        F.unix_seconds("fc_issue_ts").alias("issue_s"), F.unix_seconds("fc_updated_ts").alias("updated_s")).collect()
    return {r.target_date: r for r in rows}


def test_end_before_start_is_corrected_and_the_latest_version_wins(spark):
    r = _pick(spark, [DEC30_1744, DEC30_2300, *DEC31_DAY], [date(2025, 12, 31)])[date(2025, 12, 31)]
    # the stored validity rejects the 23:00 issue (end before start) and picks 17:44 (forecast_validity.md §4)
    assert (r.issue_s, r.updated_s) == (_s("2025-12-30T23:00:00+08:00"), _s("2025-12-30T23:10:47+08:00"))
    assert r.fc_text_agrees and not r.forecast_missing
    assert r.fc_lead_h == pytest.approx(6 + 49 / 60 + 13 / 3600)  # 23:10:47 to 06:00


def test_daytime_issues_of_31_dec_are_never_selected(spark):
    got = _pick(spark, DEC31_DAY, [date(2025, 12, 31), date(2026, 1, 1)])
    assert got[date(2025, 12, 31)].forecast_missing  # issued after the 00:15 cut-off of 31 Dec
    assert got[date(2026, 1, 1)].forecast_missing    # issued before 17:00 on 31 Dec, and none covers 1 Jan 18:00


def test_start_a_year_off_is_corrected(spark):
    got = _pick(spark, [DEC31_2304, *JAN01], [date(2026, 1, 1), date(2026, 1, 2)])
    r = got[date(2026, 1, 1)]
    assert r.issue_s == _s("2025-12-31T23:04:00+08:00") and r.fc_temp_high == 33 and r.fc_text_agrees
    assert got[date(2026, 1, 2)].forecast_missing  # the 1 Jan issues: too old for 2 Jan, and valid only to 2 Jan 06:00


def test_a_48_hour_window_counts_only_its_first_24_hours(spark):
    got = _pick(spark, [JAN16_0333, JAN16_2308], [date(2025, 1, 17), date(2025, 1, 18)])
    r = got[date(2025, 1, 17)]
    assert r.issue_s == _s("2025-01-16T23:08:00+08:00") and r.fc_temp_high == 30 and r.fc_text_agrees
    assert got[date(2025, 1, 18)].forecast_missing


def test_2025_07_21_gets_no_forecast(spark):
    got = _pick(spark, [JUL19_2302], [date(2025, 7, 20), date(2025, 7, 21)])
    assert got[date(2025, 7, 20)].issue_s == _s("2025-07-19T23:02:00+08:00")
    # the stored 48-hour validity covers 21 Jul (forecast_validity.md §4 chose it); corrected, it ends 21 Jul 00:00
    assert got[date(2025, 7, 21)].forecast_missing


def test_only_the_24_hour_correction_rejects_this_record(spark):
    # issued after 17:00 the day before and updated before the cut-off; the stored end (T+1 12:00) would cover T,
    # the corrected end (start + 24 h = T 12:00) does not
    rec = fc_record("2025-03-09T17:05:00+08:00", "2025-03-09T12:00:00+08:00", "2025-03-11T12:00:00+08:00",
                    "12 PM 9 Mar to 12 PM 10 Mar", updated="2025-03-09T17:10:00+08:00")
    assert _pick(spark, [rec], [date(2025, 3, 10)])[date(2025, 3, 10)].forecast_missing


def test_age_limit(spark):
    t = date(2025, 3, 10)
    win = ("2025-03-09T18:00:00+08:00", "2025-03-10T18:00:00+08:00", "6 PM 9 Mar to 6 PM 10 Mar")
    at_1700 = fc_record("2025-03-09T17:00:00+08:00", *win, updated="2025-03-09T17:06:00+08:00")
    before = fc_record("2025-03-09T16:59:59+08:00", *win, updated="2025-03-09T17:06:00+08:00")
    assert not _pick(spark, [at_1700], [t])[t].forecast_missing
    assert _pick(spark, [before], [t])[t].forecast_missing
    # a real record: issued 03:33 on 16 Jan with validity 17 Jan, too old for 17 Jan
    assert _pick(spark, [JAN16_0333], [date(2025, 1, 17)])[date(2025, 1, 17)].forecast_missing


def test_version_rule_at_the_cutoff(spark):
    t = date(2025, 3, 10)
    win = ("2025-03-10T00:00:00+08:00", "2025-03-11T00:00:00+08:00", "0 AM 10 Mar to 0 AM 11 Mar")
    versions = [fc_record("2025-03-09T23:05:00+08:00", *win, updated=u, high=h)
                for u, h in (("2025-03-09T23:10:00+08:00", 33), ("2025-03-10T00:15:00+08:00", 34),
                             ("2025-03-10T00:15:01+08:00", 36))]
    r = _pick(spark, versions, [t])[t]
    assert r.fc_temp_high == 34 and r.updated_s == _s("2025-03-10T00:15:00+08:00")  # at the cut-off counts
    assert _pick(spark, versions, [t], cutoff_minutes=16)[t].fc_temp_high == 36     # a later cut-off takes the next


def test_text_check_flags_a_mismatch(spark):
    t = date(2025, 12, 31)
    rec = fc_record("2025-12-30T23:00:00+08:00", "2025-12-31T00:00:00+08:00", "2026-01-01T00:00:00+08:00",
                    "6 PM 30 Dec to 6 PM 31 Dec", updated="2025-12-30T23:10:00+08:00")
    r = _pick(spark, [rec], [t])[t]
    assert not r.forecast_missing and not r.fc_text_agrees


@pytest.mark.parametrize("cutoff", [-420, -421, -1439])
def test_cutoff_at_or_before_the_first_issue_time_is_refused(spark, cutoff):
    with pytest.raises(ValueError, match="first forecast issue time"):
        _pick(spark, [JUL19_2302], [date(2025, 7, 20)], cutoff_minutes=cutoff)


def test_cutoff_just_after_the_first_issue_time_is_accepted(spark):
    rec = fc_record("2025-07-19T17:00:00+08:00", "2025-07-19T18:00:00+08:00", "2025-07-20T18:00:00+08:00",
                    "6 PM 19 Jul to 6 PM 20 Jul")  # issued and updated at 17:00:00
    r = _pick(spark, [rec], [date(2025, 7, 20)], cutoff_minutes=-419)[date(2025, 7, 20)]
    assert r.issue_s == _s("2025-07-19T17:00:00+08:00")


def test_no_candidate_gives_missing_and_nulls(spark):
    r = _pick(spark, [], [date(2025, 3, 10)])[date(2025, 3, 10)]
    assert r.forecast_missing and (r.fc_temp_high, r.fc_text, r.issue_s) == (None, None, None)
