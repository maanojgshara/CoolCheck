"""Station-day features (docs/design/backtest.md §3): values, event time, missing values, panel, rainfall, rows and
completed days."""
from datetime import date, timedelta

import pytest

from feature_fixtures import LABEL_SCHEMA, Readings, at, fc_record, forecast_versions
from coolcheck.features import (FEATURES, ORIGINAL_8, assert_completed_days, rain_min_readings, station_day_features,
                                usable_labels)

T = date(2026, 3, 10)
Y = T - timedelta(days=1)
RUN = date(2026, 10, 23)
FC_T = fc_record("2026-03-09T23:05:00+08:00", "2026-03-10T00:00:00+08:00", "2026-03-11T00:00:00+08:00",
                 "0 AM 10 Mar to 0 AM 11 Mar", updated="2026-03-09T23:10:00+08:00", high=34)


def _base(rain_after=None):
    """Panel stations S124 (peak 30.0) and S125 (31.0) from T-30 to T-2; on T-1 S124 peaks at 33.2 (one High reading)
    and S125 at 31.0. S1, not in the panel, peaks at 32.0 from T-25 to T-2 and at 33.5 on T-1 (readings 32.5, 33.5
    and 33.0: two High). Rainfall station R2 sits 1.0 km north of S1 with 288 readings on T-1, ten of them 0.5 mm."""
    rd = Readings()
    for i in range(2, 31):
        d = T - timedelta(days=i)
        rd.day("S124", d, 30.0, lat=1.35, lon=103.85).day("S125", d, 31.0, lat=1.40, lon=103.90)
        if i <= 25:
            rd.day("S1", d, 32.0)
    rd.day("S124", Y, 33.2, lat=1.35, lon=103.85).day("S125", Y, 31.0, lat=1.40, lon=103.90).day("S1", Y, 33.5)
    rd.rain_day("R2", Y, lat=1.309, lon=103.80, after=rain_after)
    return rd


def _features(spark, rd, fc_records=(), targets=(T,), run_date=RUN, cutoff_minutes=15, panel=ORIGINAL_8):
    wbgt, rain = rd.frames(spark)
    t = spark.createDataFrame([(d,) for d in targets], "target_date DATE")
    out = station_day_features(wbgt, rain, forecast_versions(spark, *fc_records), t, run_date, cutoff_minutes, panel)
    return {(r.station_id, r.target_date): r.asDict() for r in out.collect()}


def test_feature_values_for_one_station_day(spark):
    got = _features(spark, _base(), [FC_T])
    assert set(got) == {("S1", T), ("S124", T), ("S125", T)}
    r = got[("S1", T)]
    assert set(FEATURES) <= set(r)
    assert (r["wbgt_peak_d1"], r["n_high_d1"], r["wbgt_n_d1"]) == (33.5, 2, 3)
    assert r["wbgt_peak_mean_7d"] == pytest.approx((6 * 32.0 + 33.5) / 7) and r["n_days_7d"] == 7
    # 24 days at 32.0 - 30.5 and T-1 at 33.5 - 32.1
    assert r["station_char_30d"] == pytest.approx((24 * 1.5 + 1.4) / 25) and r["n_days_30d"] == 25
    assert r["panel_peak_mean_d1"] == pytest.approx((33.2 + 31.0) / 2)
    assert (r["panel_high_count_d1"], r["panel_n_d1"]) == (1, 2)
    assert (r["fc_temp_high"], r["fc_text"], r["forecast_missing"], r["fc_text_agrees"]) == (34, "Thundery Showers", False, True)
    assert r["fc_lead_h"] == pytest.approx(6 + 50 / 60)
    assert (r["rain_station_id"], r["rain_n_readings"]) == ("R2", 288) and r["rain_d1_mm"] == pytest.approx(5.0)
    assert r["rain_dist_km"] == pytest.approx(1.0008, abs=1e-3)
    assert (r["month"], r["season"]) == (3, "Inter-monsoon 1")
    assert r["inputs_max_day"] == Y
    s124 = got[("S124", T)]
    assert (s124["wbgt_peak_d1"], s124["n_high_d1"]) == (33.2, 1)
    assert s124["station_char_30d"] == pytest.approx((29 * -0.5 + 1.1) / 30) and s124["n_days_30d"] == 30


def test_inputs_after_the_cutoff_change_no_feature(spark):
    base = _features(spark, _base(), [FC_T])
    rd = _base()
    for s in ("S1", "S124"):
        rd.w(s, at(T, 0, 20), 36.0, "High").w(s, at(T, 10), 36.0, "High")
    rd.w("S9", at(T, 0, 20), 36.0, "High")  # a new station whose only reading is after the cut-off
    rd.rain_day("R2", T, n=12, wet=12, mm=50.0, lat=1.309, lon=103.80)  # heavy rain on T, after the cut-off
    late = fc_record("2026-03-09T23:05:00+08:00", "2026-03-10T00:00:00+08:00", "2026-03-11T00:00:00+08:00",
                     "0 AM 10 Mar to 0 AM 11 Mar", updated="2026-03-10T00:20:00+08:00", high=36, forecast_text="Fair & Warm")
    assert _features(spark, rd, [FC_T, late]) == base


def test_inputs_after_an_evening_cutoff_change_no_feature(spark):
    # cut-off 21:00 on T-1 (-180): T-1 itself is cut, so a reading on T-1 after 21:00 must not count
    fc = fc_record("2026-03-09T17:30:00+08:00", "2026-03-09T18:00:00+08:00", "2026-03-10T18:00:00+08:00",
                   "6 PM 9 Mar to 6 PM 10 Mar", updated="2026-03-09T17:40:00+08:00", high=34)
    base = _features(spark, _base(), [fc], cutoff_minutes=-180)
    rd = _base(rain_after=(21 * 60, 50.0))  # R2's readings from 21:00 on T-1 hold 50 mm each
    for s in ("S1", "S124"):
        rd.w(s, at(Y, 22), 36.0, "High")
    late = fc_record("2026-03-09T17:30:00+08:00", "2026-03-09T18:00:00+08:00", "2026-03-10T18:00:00+08:00",
                     "6 PM 9 Mar to 6 PM 10 Mar", updated="2026-03-09T22:00:00+08:00", high=36)
    assert _features(spark, rd, [fc, late], cutoff_minutes=-180) == base
    r = base[("S1", T)]
    assert (r["wbgt_peak_d1"], r["n_high_d1"], r["rain_n_readings"], r["fc_temp_high"]) == (33.5, 2, 252, 34)


@pytest.mark.parametrize("tz", ["Asia/Singapore", "UTC"])
def test_midnight_does_not_depend_on_the_session_time_zone(spark, tz):
    rd = Readings().w("S1", at(Y, 12), 29.0).w("S1", at(Y, 23, 45), 30.0).w("S1", at(T, 0, 0), 35.0, "High")
    spark.conf.set("spark.sql.session.timeZone", tz)
    try:
        r = _features(spark, rd)[("S1", T)]
    finally:
        spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    # 23:45 on T-1 is yesterday; the High at 00:00 on T is not
    assert (r["wbgt_peak_d1"], r["n_high_d1"], r["wbgt_n_d1"]) == (30.0, 0, 2)


def test_missing_is_not_zero_and_minimum_days(spark):
    rd = _base()
    for i in (2, 3, 4):  # S2: three days in the trailing week, and only an NA reading on T-1
        rd.day("S2", T - timedelta(days=i), 30.0)
    rd.w("S2", at(Y, 12), None, "NA")
    for i in (2, 3, 4, 5):  # S3: four days
        rd.day("S3", T - timedelta(days=i), 31.0)
    for i in range(2, 22):  # S4: 20 days in the last 30
        rd.day("S4", T - timedelta(days=i), 31.0)
    for i in range(2, 21):  # S5: 19 days
        rd.day("S5", T - timedelta(days=i), 31.0)
    got = _features(spark, rd, [FC_T])
    s2 = got[("S2", T)]
    assert (s2["wbgt_peak_d1"], s2["n_high_d1"], s2["wbgt_n_d1"]) == (None, None, 0)
    assert s2["wbgt_peak_mean_7d"] is None and s2["n_days_7d"] == 3
    assert got[("S3", T)]["wbgt_peak_mean_7d"] == pytest.approx(31.0) and got[("S3", T)]["n_days_7d"] == 4
    assert got[("S4", T)]["station_char_30d"] == pytest.approx(0.5) and got[("S4", T)]["n_days_30d"] == 20
    assert got[("S5", T)]["station_char_30d"] is None and got[("S5", T)]["n_days_30d"] == 19


def test_panel_uses_the_fixed_stations_and_the_api_category(spark):
    rd = _base()
    rd.w("S1", at(Y, 14), 34.0, "High")        # a High at a station outside the panel
    rd.w("S125", at(Y, 14), 33.5, "Moderate")  # the API says Moderate: it does not count as High
    r = _features(spark, rd, [FC_T])[("S1", T)]
    assert (r["panel_high_count_d1"], r["panel_n_d1"]) == (1, 2)
    assert r["panel_peak_mean_d1"] == pytest.approx((33.2 + 33.5) / 2)
    rd.day("S130", Y, 30.0, lat=1.33, lon=103.70)  # a third panel station reporting: counted only when it reports
    r = _features(spark, rd, [FC_T])[("S1", T)]
    assert r["panel_n_d1"] == 3 and r["panel_peak_mean_d1"] == pytest.approx((33.2 + 33.5 + 30.0) / 3)


def test_rainfall_skips_short_days_and_breaks_ties_by_id(spark):
    rd = Readings().day("S1", Y, 30.0)  # S1 at (1.30, 103.80)
    rd.rain_day("R1", Y, n=215, lat=1.302, lon=103.80)  # nearest, but 215 readings
    rd.rain_day("R3", Y, wet=4, lat=1.309, lon=103.80)  # R2 and R3 tie at 1.0 km: the lower ID wins
    rd.rain_day("R2", Y, wet=10, lat=1.309, lon=103.80)
    r = _features(spark, rd)[("S1", T)]
    assert (r["rain_station_id"], r["rain_n_readings"]) == ("R2", 288) and r["rain_d1_mm"] == pytest.approx(5.0)
    only_short = Readings().day("S1", Y, 30.0).rain_day("R1", Y, n=215, lat=1.302, lon=103.80)
    r = _features(spark, only_short)[("S1", T)]
    assert (r["rain_station_id"], r["rain_d1_mm"]) == (None, None)


def test_rainfall_station_location_by_date(spark):
    d2 = T - timedelta(days=2)
    rd = Readings().day("S1", Y, 30.0).day("S1", d2, 30.0)
    rd.rain_day("R4", d2, wet=2, lat=1.40, lon=103.80)    # 11 km away on T-2 ...
    rd.rain_day("R4", Y, wet=6, lat=1.301, lon=103.80)    # ... and 0.1 km away on T-1
    for d in (d2, Y):
        rd.rain_day("R5", d, wet=8, lat=1.31, lon=103.80)  # 1.1 km on both days
    got = _features(spark, rd, targets=(T, Y))
    assert got[("S1", T)]["rain_station_id"] == "R4"   # yesterday of T is T-1
    assert got[("S1", Y)]["rain_station_id"] == "R5"   # yesterday of T-1 is T-2


def test_rows_follow_the_reporting_window_and_completed_days(spark):
    rd = Readings()
    rd.w("S6", at(T - timedelta(days=7), 0, 10), 28.0)  # 00:10 on T-7: before the window opens at 00:15
    rd.w("S7", at(T - timedelta(days=7), 0, 15), 28.0)  # 00:15 on T-7: inside
    rd.w("S8", at(T, 0, 14), 28.0)                      # 00:14 on T: before the cut-off, inside
    rd.w("S9", at(T, 0, 15), 28.0)                      # 00:15 on T: at the cut-off, outside
    assert {s for s, _ in _features(spark, rd)} == {"S7", "S8"}
    # run on T itself (the live job): T is not a completed day, so its readings are not read and S8 has no row
    assert {s for s, _ in _features(spark, rd, run_date=T)} == {"S7"}


def test_labels_from_completed_days_only(spark):
    labels = spark.createDataFrame([
        ("S1", Y, "High", True, 4),
        ("S1", RUN, "Moderate", True, 0),               # the run date: provisional, however usable it looks
        ("S1", T - timedelta(days=2), "Low", False, 0),  # low coverage: not usable
    ], LABEL_SCHEMA)
    got = usable_labels(labels, RUN).toPandas()
    assert [(r.target_date, r.label, r.y, r.n_high) for r in got.itertuples()] == [(Y, "High", 2, 4)]
    assert usable_labels(labels, RUN, last_date=T - timedelta(days=2)).count() == 0
    assert_completed_days(got, RUN, ["target_date"])
    with pytest.raises(AssertionError, match="on or after run_date"):
        assert_completed_days(labels.toPandas(), RUN, ["sgt_date"])


def test_refuses_targets_after_the_run_date_and_bad_cutoffs(spark):
    with pytest.raises(ValueError, match="after run_date"):
        _features(spark, _base(), [FC_T], run_date=Y)
    with pytest.raises(ValueError, match="cutoff_minutes"):
        _features(spark, _base(), [FC_T], cutoff_minutes=1440)


def test_rain_minimum_readings_scale_with_the_cutoff():
    assert (rain_min_readings(15), rain_min_readings(0), rain_min_readings(-180)) == (216, 216, 189)
