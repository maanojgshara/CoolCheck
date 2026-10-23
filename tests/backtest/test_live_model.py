"""The live model's refit and the nightly heat forecast (Guide §A11 decision 8(e)) on synthetic data: local, no Spark
and no workspace. The registered model logged from code, and the registry steps, are tested against a local MLflow
store in test_live_model_mlflow.py."""
import importlib.util
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest_fixtures import synthetic_rows
from coolcheck import heat_model as HM
from coolcheck import live_model as LM
from coolcheck.backtest import apply_forecast_fill, encode, fit_forecast_fill
from coolcheck.features import CATEGORICAL, FEATURES
from coolcheck.final_check import FINAL_CUTOFF

JOBS = Path(__file__).resolve().parents[2] / "src" / "jobs"


@pytest.fixture(scope="module")
def fitted():
    rows = synthetic_rows(end=LM.LIVE_LAST)
    return rows, LM.fit_live(rows)


def test_the_live_settings():
    assert (LM.LIVE_FIRST, LM.LIVE_LAST) == (date(2025, 1, 17), date(2026, 10, 22))
    assert (LM.DQ_FIRST, LM.DQ_LAST) == (date(2026, 10, 20), date(2026, 10, 22))
    assert LM.FOLD_RATES == ((150, 5388), (390, 7682)) and LM.FINAL_TRAIN == (9308, 465)
    assert (LM.N_AREAS, LM.CUTOFF_MINUTES, LM.ROLE) == (41, 15, "live_model")
    assert [c for c, _ in LM.FORECAST_COLUMNS] == ["target_date", "planning_area", "station_id", "p_low", "p_moderate",
                                                   "p_high", "model_version", "run_id", "cutoff_ts", "scored_at",
                                                   "forecast_missing"]
    assert [t for _, t in LM.FORECAST_COLUMNS] == ["DATE", "STRING", "STRING", "DOUBLE", "DOUBLE", "DOUBLE", "STRING",
                                                   "STRING", "TIMESTAMP", "TIMESTAMP", "BOOLEAN"]


def test_fit_live_uses_the_final_checks_settings_and_the_training_rows_only(fitted):
    rows, fit = fitted
    assert fit.booster.current_iteration() == 150 and fit.booster.params["num_leaves"] == 7
    assert fit.booster.params["seed"] == 42
    assert (fit.train_rows, fit.train_high) == (len(rows), int((rows.y == 2).sum()))
    assert fit.fill == fit_forecast_fill(rows) and {9, 10} <= set(fit.fill["by_month"])
    assert all(pd.Timestamp(v) <= pd.Timestamp(LM.LIVE_LAST) for v in fit.used.values())
    late = rows.tail(1).assign(target_date=pd.Timestamp("2026-10-23"))
    late["target_date"] = late.target_date.astype(rows.target_date.dtype)
    with pytest.raises(AssertionError, match="outside 2025-01-17 to 2026-10-22"):
        LM.fit_live(pd.concat([rows, late], ignore_index=True))


def _rows(n, high):
    return pd.DataFrame({"y": [2] * high + [0] * (n - high)})


def test_the_training_rate_guard():
    ok = LM.check_training_rate(_rows(10000, 497))
    assert (ok["rows"], ok["high"]) == (10000, 497)
    assert "final check's model 9,308 rows, 465 High (4.996%)" in ok["line"]
    assert "back-test folds 2.784% (150 of 5,388) to 5.077% (390 of 7,682)" in ok["line"]
    LM.check_training_rate(_rows(5388, 150))  # the folds' bounds themselves pass
    LM.check_training_rate(_rows(7682, 390))
    for n, high in ((5388, 149), (7682, 391), (10000, 600)):
        with pytest.raises(AssertionError, match="outside the folds' range, so nothing is logged or registered"):
            LM.check_training_rate(_rows(n, high))


def test_every_feed_must_be_present_on_20_to_22_oct_and_a_short_day_is_fine():
    days = pd.date_range("2026-10-20", "2026-10-22").date
    dq = pd.DataFrame([(d, f, "ok") for d in days for f in LM.DQ_FEEDS], columns=["sgt_date", "feed", "status"])
    dq.loc[0, "status"] = "short"
    lines, missing = LM.feeds_by_day(dq)
    assert missing == [] and len(lines) == 9 and "  2026-10-20 wbgt: short" in lines
    lines, missing = LM.feeds_by_day(dq.drop(index=4))  # 21 Oct rainfall
    assert missing == [("2026-10-21", "rainfall")] and "  2026-10-21 rainfall: no row" in lines
    no_data = dq.copy()
    no_data.loc[8, "status"] = "no_data"  # 22 Oct forecast
    assert LM.feeds_by_day(no_data)[1] == [("2026-10-22", "forecast")]


def test_the_registered_model_prepares_and_predicts_as_the_backtest_functions(fitted):
    rows, fit = fitted
    spec = json.loads(json.dumps(LM.model_spec(fit)))  # as spec.json stores it
    frame = rows.tail(60).copy()
    first3 = frame.index[:3]
    frame.loc[first3, "forecast_missing"] = True  # filled from the training fill for their calendar month
    frame.loc[first3, "fc_temp_high"] = np.nan
    frame.loc[first3, "fc_text"] = None
    frame.loc[frame.index[5], "fc_text"] = "Haze"  # a text never seen in training
    x = LM.model_input(frame)
    got = HM.prepare(x, spec)
    pd.testing.assert_frame_equal(got, encode(apply_forecast_fill(x, fit.fill)[0], fit.categories))
    month_fill = fit.fill["by_month"].get(x.loc[0, "target_date"].month, fit.fill["overall"])
    assert pd.isna(got.loc[5, "fc_text"]) and got.loc[0, "fc_temp_high"] == month_fill[0]
    model = HM.HeatModel()
    model.booster, model.spec = fit.booster, spec
    p = model.predict(None, x)
    assert list(p.columns) == ["p_low", "p_moderate", "p_high"]
    np.testing.assert_array_equal(p.to_numpy(), LM.predict_proba(fit, x).to_numpy())
    np.testing.assert_allclose(p.sum(axis=1), 1.0)


def test_the_model_input_has_the_signature_dtypes(fitted):
    rows, _ = fitted
    x = LM.model_input(rows[rows.forecast_missing].head(3))
    assert list(x.columns) == LM.INPUT_COLUMNS
    assert all(x[c].dtype == float for c in FEATURES if c not in CATEGORICAL)
    assert x.forecast_missing.dtype == bool and str(x.target_date.dtype).startswith("datetime64")
    assert x.fc_text.isna().all() and x.fc_text.dtype == object


def test_the_spec_records_the_fill_and_the_settings(fitted):
    _, fit = fitted
    spec = LM.model_spec(fit)
    assert json.loads(json.dumps(spec)) == spec
    assert (spec["num_leaves"], spec["rounds"], spec["high_cutoff"]) == (7, 150, FINAL_CUTOFF)
    assert spec["training_window"] == ["2025-01-17", "2026-10-22"] and spec["text_categories"] == fit.categories
    assert spec["fill_by_month"]["9"] == [float(fit.fill["by_month"][9][0]), fit.fill["by_month"][9][1]]


def test_the_target_date_rule():
    now = datetime(2026, 10, 23, 16, 45, tzinfo=timezone.utc)  # 00:45 SGT on 24 Oct
    assert LM.target_date_of("", now) == date(2026, 10, 24)
    assert LM.target_date_of("2026-10-23", now) == date(2026, 10, 23)
    with pytest.raises(ValueError, match="after today"):
        LM.target_date_of("2026-10-25", now)
    with pytest.raises(ValueError, match="before the first target date"):
        LM.target_date_of("2025-01-16", now)
    assert LM.cutoff_ts(date(2026, 10, 23)) == datetime(2026, 10, 22, 16, 15, tzinfo=timezone.utc)


def test_the_area_mapping_keeps_and_flags_an_area_whose_station_has_no_feature_row():
    t = date(2026, 10, 23)
    areas = [f"AREA {i:02d}" for i in range(41)]
    stations = [f"S{100 + i % 7}" for i in range(41)]
    amap = pd.DataFrame({"target_date": [t] * 42, "planning_area": areas + ["NO SENIORS"],
                         "station_id": stations + ["S100"]})
    with_rows = pd.Series([f"S{100 + i}" for i in range(6)])  # S106 has no feature row on t
    m, flagged = LM.area_map_live(amap, areas, with_rows, t)
    assert len(m) == 41 and "NO SENIORS" not in set(m.planning_area)
    assert flagged == sorted(a for a, s in zip(areas, stations) if s == "S106") and len(flagged) == 5
    preds = pd.DataFrame({"station_id": with_rows, "p_low": 0.5, "p_moderate": 0.3, "p_high": 0.2})
    rows = LM.forecast_rows(m, preds, True, t, "1", "12345", datetime(2026, 10, 23, 21, tzinfo=LM.SGT))
    assert list(rows.columns) == [c for c, _ in LM.FORECAST_COLUMNS] and len(rows) == 41 and rows.planning_area.is_unique
    flag = rows.planning_area.isin(flagged)
    assert rows.loc[flag, LM.PROBS].isna().all().all() and rows.loc[~flag, "p_high"].eq(0.2).all()
    assert (rows.target_date == t).all() and (rows.model_version == "1").all() and (rows.run_id == "12345").all()
    assert (rows.cutoff_ts == pd.Timestamp("2026-10-23 00:15", tz=LM.SGT)).all() and rows.forecast_missing.all()
    with pytest.raises(AssertionError, match="no row on 2026-10-23 for 1 area"):
        LM.area_map_live(amap.iloc[1:], areas, with_rows, t)
    with pytest.raises(AssertionError, match="more than one row"):
        LM.area_map_live(pd.concat([amap, amap.head(1)]), areas, with_rows, t)
    with pytest.raises(AssertionError, match="a date other than"):
        LM.area_map_live(amap.assign(target_date=date(2026, 10, 22)), areas, with_rows, t)


def test_the_table_the_merge_and_the_read_back():
    ddl = LM.create_table_sql("cat.gold.heat_forecast")
    assert ddl.startswith("CREATE TABLE IF NOT EXISTS cat.gold.heat_forecast (target_date DATE, planning_area STRING, "
                          "station_id STRING, p_low DOUBLE, p_moderate DOUBLE, p_high DOUBLE, model_version STRING, "
                          "run_id STRING, cutoff_ts TIMESTAMP, scored_at TIMESTAMP, forecast_missing BOOLEAN) COMMENT '")
    assert "'" not in LM.FORECAST_COMMENT
    merge = LM.merge_sql("cat.gold.heat_forecast", "stage")
    assert merge.startswith("MERGE INTO cat.gold.heat_forecast AS t USING stage AS s ")
    assert "ON t.target_date = s.target_date AND t.planning_area = s.planning_area" in merge
    assert merge.endswith("WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *")
    assert "WHERE target_date = DATE'2026-10-23'" in LM.read_back_sql("cat.gold.heat_forecast", date(2026, 10, 23))
    good = {"n_rows": 41, "n_areas": 41, "n_scored": 40, "n_nan": 0, "max_sum_gap": 1e-12, "n_versions": 1,
            "model_version": "1", "n_run_ids": 1, "run_id": "9"}
    LM.check_read_back(good, 40, 1, 9)
    for change, message in ((dict(n_rows=82), "82 rows"), (dict(n_scored=41), "41 scored rows"), (dict(n_nan=1), "NaN"),
                            (dict(max_sum_gap=1e-3), "do not sum to 1"), (dict(n_versions=2), "provenance")):
        with pytest.raises(AssertionError, match=message):
            LM.check_read_back({**good, **change}, 40, 1, 9)


def _job(name):
    spec = importlib.util.spec_from_file_location(f"{name}_job", JOBS / f"{name}.py")
    job = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(job)
    return job


def test_the_jobs_record_their_code_and_the_nightly_start_line():
    live, nightly = _job("live_model"), _job("heat_forecast")
    assert {"coolcheck/live_model.py", "coolcheck/heat_model.py", "coolcheck/live_registry.py", "jobs/live_model.py",
            "jobs/final_check.py", "coolcheck/backtest.py"} <= set(live.CODE_FILES)
    assert {"coolcheck/live_model.py", "coolcheck/live_registry.py", "jobs/heat_forecast.py",
            "jobs/final_check.py"} <= set(nightly.CODE_FILES)
    assert re.fullmatch(r"[0-9a-f]{64}", live.code_sha256()) and re.fullmatch(r"[0-9a-f]{64}", nightly.code_sha256())
    assert nightly.start_line(date(2026, 10, 23), "bff0577", "123") == (
        f"heat forecast for 2026-10-23; git bff0577; code sha256 {nightly.code_sha256()}; job run 123")

    class Version:
        def __init__(self, tags):
            self.tags = tags

    assert nightly.trained_to(Version({"training_window": "2025-01-17..2026-10-22"})) == date(2026, 10, 22)
    assert nightly.trained_to(Version({})) == LM.LIVE_LAST
