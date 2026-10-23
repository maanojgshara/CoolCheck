"""The registered live model (<catalog>.ml.heat_model): an MLflow pyfunc logged "from code". The file is
self-contained (pandas, numpy and lightgbm; no coolcheck import), so the champion keeps its behaviour when the
repository's code changes after it is registered.

Its artifacts: booster.txt (the LightGBM model) and spec.json (coolcheck.live_model.model_spec: the feature order, the
categories, the forecast fill from the training rows, the settings). predict takes the station-day rows (the 11
features, forecast_missing, target_date) and returns p_low, p_moderate and p_high. The preparation repeats
coolcheck.backtest's apply_forecast_fill and encode; tests/backtest/test_live_model.py pins them equal.
"""
import json

import lightgbm as lgb
import pandas as pd

try:
    import mlflow
    from mlflow.pyfunc import PythonModel
except ImportError:  # the shared .venv has no mlflow; its tests call prepare and HeatModel directly
    mlflow, PythonModel = None, object

PROBS = ["p_low", "p_moderate", "p_high"]


def prepare(frame, spec):
    """The booster's input: missing forecasts filled with the training fill for the target date's calendar month (else
    over all training dates), then the features in order, numeric as float, the two categoricals on the training
    categories (a text not seen in training becomes missing)."""
    x = frame.copy()
    miss = x["forecast_missing"].astype(bool).to_numpy()
    by_month = {int(m): v for m, v in spec["fill_by_month"].items()}
    vals = [by_month.get(m, spec["fill_overall"]) for m in pd.to_datetime(x.loc[miss, "target_date"]).dt.month]
    x.loc[miss, "fc_temp_high"] = [v[0] for v in vals]
    x.loc[miss, "fc_text"] = [v[1] for v in vals]
    out = x[spec["features"]].copy()
    for c in out.columns:
        if c not in spec["categorical"]:
            out[c] = pd.to_numeric(out[c], errors="raise").astype(float)
    out["fc_text"] = pd.Categorical(out["fc_text"], categories=spec["text_categories"])
    out["season"] = pd.Categorical(out["season"], categories=spec["seasons"])
    return out


class HeatModel(PythonModel):
    def load_context(self, context):
        # read as text and passed as a string: LightGBM's model_file reader fails on a file with CRLF line endings
        with open(context.artifacts["booster"], encoding="utf-8") as f:
            self.booster = lgb.Booster(model_str=f.read())
        with open(context.artifacts["spec"], encoding="utf-8") as f:
            self.spec = json.load(f)

    def predict(self, context, model_input, params=None):
        p = self.booster.predict(prepare(model_input, self.spec))
        return pd.DataFrame(p, columns=PROBS, index=model_input.index)


if mlflow is not None:
    mlflow.models.set_model(HeatModel())
