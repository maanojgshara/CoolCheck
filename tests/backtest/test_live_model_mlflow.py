r"""The registered live model (coolcheck/heat_model.py, an MLflow pyfunc logged "from code") and the registry steps
(coolcheck.live_registry) against a local MLflow store.

mlflow is not in the shared .venv (see test_final_check_mlflow.py), so these tests skip there and run in a throwaway
venv holding only what they import (PowerShell, from the repo root):

    .venv\Scripts\python -m venv $env:TEMP\coolcheck-mlflow-venv
    & $env:TEMP\coolcheck-mlflow-venv\Scripts\python -m pip install mlflow-skinny==2.22.0 pytest==9.1.1 lightgbm==4.6.0 pandas==2.2.3 numpy==2.1.3
    $env:PYTHONDONTWRITEBYTECODE = "1"
    & $env:TEMP\coolcheck-mlflow-venv\Scripts\python -m pytest tests/backtest/test_live_model_mlflow.py tests/backtest/test_final_check_mlflow.py -p no:cacheprovider -v
    Remove-Item -Recurse -Force $env:TEMP\coolcheck-mlflow-venv

They import mlflow, lightgbm, pandas, numpy, pytest, coolcheck.heat_model and coolcheck.live_registry (no pyspark), so
the model is trained here on a small synthetic frame. Unity Catalog's own registry is exercised by the refit job.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

mlflow = pytest.importorskip("mlflow")
lgb = pytest.importorskip("lightgbm")

from mlflow import MlflowClient  # noqa: E402

from coolcheck import heat_model as HM  # noqa: E402
from coolcheck.live_registry import ALIAS, champion, model_versions, refuse_if_registered  # noqa: E402

MODEL_CODE = Path(__file__).resolve().parents[2] / "src" / "coolcheck" / "heat_model.py"
FEATURES = ["wbgt_peak_d1", "wbgt_peak_mean_7d", "station_char_30d", "n_high_d1", "panel_peak_mean_d1",
            "panel_high_count_d1", "fc_temp_high", "fc_text", "rain_d1_mm", "month", "season"]  # coolcheck.features
SPEC = {"features": FEATURES, "categorical": ["fc_text", "season"],
        "text_categories": ["Partly Cloudy (Day)", "Showers", "Thundery Showers"],
        "seasons": ["NE monsoon", "Inter-monsoon 1", "SW monsoon", "Inter-monsoon 2"],
        "fill_by_month": {"8": [34.0, "Thundery Showers"]}, "fill_overall": [33.0, "Showers"]}


def synthetic(n=400, seed=0):
    """Station-day rows shaped like coolcheck.live_model.model_input (numeric as float, text with None for missing)."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-08-01", periods=n, freq="6h").normalize()
    df = pd.DataFrame({"wbgt_peak_d1": rng.normal(31, 1.5, n), "wbgt_peak_mean_7d": rng.normal(31, 1, n),
                       "station_char_30d": rng.normal(0, 0.5, n), "n_high_d1": rng.integers(0, 3, n).astype(float),
                       "panel_peak_mean_d1": rng.normal(31, 1, n),
                       "panel_high_count_d1": rng.integers(0, 5, n).astype(float),
                       "fc_temp_high": rng.choice([33.0, 34.0, 35.0], n),
                       "fc_text": rng.choice(SPEC["text_categories"], n).astype(object),
                       "rain_d1_mm": rng.exponential(3, n), "month": dates.month.astype(float), "season": "SW monsoon",
                       "forecast_missing": False, "target_date": dates})
    y = np.where(df.wbgt_peak_d1 > 32.5, 2, np.where(df.wbgt_peak_d1 > 30.5, 1, 0))
    return df, y


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    df, y = synthetic()
    booster = lgb.train({"objective": "multiclass", "num_class": 3, "num_leaves": 7, "min_data_in_leaf": 10, "seed": 42,
                         "deterministic": True, "force_row_wise": True, "num_threads": 1, "verbose": -1},
                        lgb.Dataset(HM.prepare(df, SPEC), label=y, categorical_feature=["fc_text", "season"]),
                        num_boost_round=20)
    d = tmp_path_factory.mktemp("artifacts")
    (d / "booster.txt").write_bytes(booster.model_to_string().encode("utf-8"))
    (d / "spec.json").write_text(json.dumps(SPEC), encoding="utf-8")
    return df, booster, d


@pytest.fixture
def store(tmp_path):
    uri = (tmp_path / "mlruns").as_uri()
    mlflow.set_tracking_uri(uri)
    mlflow.set_registry_uri(uri)
    return MlflowClient(tracking_uri=uri, registry_uri=uri)


def scoring_input(df):
    """Rows as the nightly job passes them: three with a missing forecast (filled from the training fill for August), one
    with a forecast text never seen in training."""
    x = df.copy()
    x.loc[:2, "forecast_missing"] = True
    x.loc[:2, "fc_temp_high"] = np.nan
    x.loc[:2, "fc_text"] = None
    x.loc[5, "fc_text"] = "Haze"
    return x


def log(df, booster, d):
    expected = pd.DataFrame(booster.predict(HM.prepare(df.head(5), SPEC)), columns=HM.PROBS)
    signature = mlflow.models.infer_signature(df.head(5), expected)
    with mlflow.start_run() as run:
        mlflow.pyfunc.log_model(artifact_path="model", python_model=str(MODEL_CODE),
                                artifacts={"booster": str(d / "booster.txt"), "spec": str(d / "spec.json")},
                                signature=signature, pip_requirements=["lightgbm", "pandas", "numpy"])
    return run.info.run_id


def test_the_model_logged_from_code_loads_and_predicts_as_its_booster(trained, store):
    df, booster, d = trained
    run_id = log(df, booster, d)
    model = mlflow.pyfunc.load_model(f"runs:/{run_id}/model")
    x = scoring_input(df)
    got = model.predict(x)
    assert list(got.columns) == HM.PROBS
    np.testing.assert_array_equal(got.to_numpy(), booster.predict(HM.prepare(x, SPEC)))
    np.testing.assert_allclose(got.sum(axis=1), 1.0)
    assert HM.prepare(x, SPEC).loc[0, "fc_temp_high"] == 34.0 and pd.isna(HM.prepare(x, SPEC).loc[5, "fc_text"])
    sig = model.metadata.signature
    assert sig.inputs.input_names() == [*FEATURES, "forecast_missing", "target_date"]
    assert sig.outputs.input_names() == HM.PROBS


def test_registered_once_the_alias_resolves_to_the_version_and_it_loads(trained, store):
    df, booster, d = trained
    assert model_versions(store, "heat_model") == []
    refuse_if_registered(store, "heat_model")  # no version yet: the refit may run
    run_id = log(df, booster, d)
    mv = mlflow.register_model(f"runs:/{run_id}/model", "heat_model")
    store.set_registered_model_alias("heat_model", ALIAS, mv.version)
    resolved, uri = champion(store, "heat_model")
    assert resolved.version == mv.version and uri == f"models:/heat_model/{mv.version}"
    x = scoring_input(df)
    np.testing.assert_array_equal(mlflow.pyfunc.load_model(uri).predict(x).to_numpy(),
                                  booster.predict(HM.prepare(x, SPEC)))
    with pytest.raises(SystemExit, match=f"heat_model already has version\\(s\\) {mv.version}: the live model is refit once"):
        refuse_if_registered(store, "heat_model")
