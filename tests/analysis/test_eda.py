"""Tests for the pure helpers and the window guard in scripts/analysis/eda.py (no Spark needed)."""
import importlib.util
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SPEC = importlib.util.spec_from_file_location("eda", Path(__file__).resolve().parents[2] / "scripts" / "analysis" / "eda.py")
eda = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(eda)

SGT = timezone(timedelta(hours=8))


def ts(*a):
    return int(datetime(*a, tzinfo=SGT).timestamp())


def test_window_ends_before_held_out_period():
    assert eda.WIN_END < eda.HELD_OUT[0]
    assert (eda.WIN_START, eda.WIN_END) == (date(2025, 1, 16), date(2026, 8, 31))


def test_reader_sql_refuses_table_names():
    r = eda.Reader(spark=None)
    with pytest.raises(RuntimeError):
        r.sql("SELECT * FROM coolcheck.silver.station_daily_label")


def test_collect_rejects_dates_outside_window():
    class Fake:
        def __init__(self, d):
            self.d = d

        def toPandas(self):
            return pd.DataFrame({"sgt_date": self.d})

    eda.collect(Fake([date(2025, 1, 16), date(2026, 8, 31)]), "ok", ["sgt_date"])
    with pytest.raises(AssertionError):
        eda.collect(Fake([date(2026, 9, 1)]), "held-out day", ["sgt_date"])
    with pytest.raises(AssertionError):
        eda.collect(Fake([date(2025, 1, 15)]), "before the window", ["sgt_date"])


def test_wilson():
    assert all(np.isnan(v) for v in eda.wilson(0, 0))
    lo, hi = eda.wilson(50, 100)
    assert (round(lo, 3), round(hi, 3)) == (0.404, 0.596)
    lo, hi = eda.wilson(0, 10)
    assert lo == 0 and 0.27 < hi < 0.29


def test_auc():
    y = pd.Series([False, False, True, True])
    assert eda.auc(pd.Series([1, 2, 3, 4.0]), y) == 1.0
    assert eda.auc(pd.Series([4, 3, 2, 1.0]), y) == 0.0
    assert eda.auc(pd.Series([1, 1, 1, 1.0]), y) == 0.5
    assert eda.auc(pd.Series([np.nan, 1, 2, 3.0]), y) == 1.0  # NaN dropped: 1 negative, 2 positives, all separated


def test_fix_start_sets_year_from_issue_time():
    # stored start carries the wrong year (2025 for a 1 Jan 2026 start), issued 31 Dec 2025 23:00
    assert eda.fix_start(ts(2025, 12, 31, 23), ts(2025, 1, 1, 0)) == datetime(2026, 1, 1, 0, tzinfo=SGT)
    # same-year start stays
    assert eda.fix_start(ts(2025, 12, 31, 11, 32), ts(2025, 12, 31, 12)) == datetime(2025, 12, 31, 12, tzinfo=SGT)
    # issued just after new year, start the evening before: the start is in the old year
    assert eda.fix_start(ts(2026, 1, 1, 0, 5), ts(2026, 12, 31, 18)) == datetime(2025, 12, 31, 18, tzinfo=SGT)
    # 29 Feb does not exist in a non-leap candidate year, so it falls back to the leap year
    assert eda.fix_start(ts(2028, 2, 29, 1), ts(2028, 2, 29, 6)).year == 2028


def _fc(rows):
    df = pd.DataFrame(rows, columns=["issue_s", "upd_s", "vs_s", "temp_high", "forecast_text"])
    return eda.prepare_forecasts(df)


def test_pick_forecast_cutoff_validity_and_latest():
    t = pd.Timestamp("2026-03-10")
    fc = _fc([
        (ts(2026, 3, 9, 17, 30), ts(2026, 3, 9, 17, 40), ts(2026, 3, 9, 18), 33, "evening issue"),     # covers to 18:00 on the 10th: ok, but older
        (ts(2026, 3, 9, 23, 0), ts(2026, 3, 9, 23, 10), ts(2026, 3, 10, 0), 34, "late issue"),         # ok, the latest at the cut-off
        (ts(2026, 3, 10, 0, 30), ts(2026, 3, 10, 0, 40), ts(2026, 3, 10, 0), 35, "after the cut-off"),  # excluded
        (ts(2026, 3, 9, 11, 30), ts(2026, 3, 9, 11, 40), ts(2026, 3, 9, 12), 31, "too early to cover 18:00"),
    ])
    assert eda.pick_forecast(fc, t)["forecast_text"] == "late issue"
    # an update stamped exactly at 00:15 counts, one second later does not
    at = _fc([(ts(2026, 3, 9, 23), ts(2026, 3, 10, 0, 15), ts(2026, 3, 10, 0), 34, "at cut-off")])
    assert eda.pick_forecast(at, t)["forecast_text"] == "at cut-off"
    late = _fc([(ts(2026, 3, 9, 23), ts(2026, 3, 10, 0, 15) + 1, ts(2026, 3, 10, 0), 34, "late")])
    assert eda.pick_forecast(late, t) is None


def test_forecast_features_marks_missing_and_guards_leakage():
    fc = _fc([(ts(2026, 3, 9, 23), ts(2026, 3, 9, 23, 10), ts(2026, 3, 10, 0), 34, "Showers")])
    out = eda.forecast_features(fc, [pd.Timestamp("2026-03-10"), pd.Timestamp("2026-03-20")])
    assert list(out["fc_found"]) == [True, False]
    assert out.loc[0, "fc_temp_high"] == 34 and out.loc[0, "fc_text"] == "Showers"
    assert out.loc[0, "fc_upd_s"] <= out.loc[0, "fc_cutoff_s"]
    assert round(out.loc[0, "fc_lead_h"], 2) == round((ts(2026, 3, 10, 6) - ts(2026, 3, 9, 23, 10)) / 3600, 2)


def test_persistence_pairs_and_table():
    d = pd.to_datetime(["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-05"])
    df = pd.DataFrame({"id": ["a"] * 4, "d": d, "high": [True, True, False, True]})
    p = eda.persistence_pairs(df, "id", "d")
    assert len(p) == 2  # 1->2 and 2->3; 3->5 is not consecutive
    t = eda.persistence_table(p, None).iloc[0]
    assert t["pairs"] == 2 and t["High today"] == 2 and t["High tomorrow too"] == 1
    assert t["P(High tomorrow given High today)"] == "50.0%"


def test_rainfall_prev_day_nearest_station_with_a_full_day():
    areas = pd.DataFrame({"planning_area": ["A"], "ref_lat": [1.30], "ref_lon": [103.80]})
    rain_st = pd.DataFrame({"station_id": ["R1", "R2"], "lat": [1.301, 1.35], "lon": [103.80, 103.80]})
    day = pd.Timestamp("2026-03-09")
    sd = pd.DataFrame({"station_id": ["R1", "R2"], "sgt_date": [day, day], "total_mm": [0.5, 12.0], "n": [100, 288]})
    out = eda.rainfall_prev_day(areas, rain_st, sd, [pd.Timestamp("2026-03-10")])
    assert out.loc[0, "rain_prev"] == 12.0  # R1 is nearer but has only 100 of 288 readings
    assert not out.loc[0, "rain_is_nearest_any"]
    sd.loc[0, "n"] = 288
    assert eda.rainfall_prev_day(areas, rain_st, sd, [pd.Timestamp("2026-03-10")]).loc[0, "rain_prev"] == 0.5


def test_season_period_keeps_ne_monsoon_together():
    assert eda.season_period(date(2025, 12, 15)) == eda.season_period(date(2026, 1, 15)) == "NE monsoon 2025/26"
    assert eda.season_period(date(2025, 1, 20)) == "NE monsoon 2024/25"
    assert eda.season_period(date(2026, 6, 1)) == "SW monsoon 2026"
