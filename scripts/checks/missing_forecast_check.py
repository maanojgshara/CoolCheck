"""Review finding 5 (docs/checks/review_live_model_nightly.md): the champion on a night with no forecast at all, in the
nightly job's own serverless environment (version 4: MLflow and pandas from the base, lightgbm 4.6.0 added).

Read-only. It builds the target date's feature rows as the nightly job does (the job's own read_inputs and
station_day_features, from --src), loads the version the alias champion points to, and predicts:
  1. the rows as they are, compared with gold.heat_forecast for that date (same model, same data: no difference expected);
  2. one row with its forecast removed (fc_temp_high NaN, fc_text None, forecast_missing True);
  3. every row with its forecast removed, so the fc_text column is all None (the case the local test does not cover);
  4. the same rows with the training fill written in by hand and forecast_missing False: (2) and (3) must equal these.
Nothing is written to a table or to the registry. Run once as a one-time run (jobs submit), not as a bundle resource:
    databricks jobs submit --json @<spec.json> -p coolcheck
with a spark_python_task on this file uploaded to the workspace, environment version 4 with lightgbm==4.6.0, and
parameters --catalog coolcheck --src <bundle files>/src --model-name coolcheck.ml.heat_model --target-date YYYY-MM-DD.
"""
import argparse
import importlib.util
import sys
from datetime import date
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--src", required=True, help="the deployed bundle's src folder")
    ap.add_argument("--model-name", required=True)
    ap.add_argument("--target-date", required=True, type=date.fromisoformat)
    a = ap.parse_args()
    sys.path.insert(0, a.src)

    import lightgbm
    import mlflow
    import numpy as np
    import pandas as pd
    from mlflow import MlflowClient
    from pyspark.sql import SparkSession

    from coolcheck import live_model as LM
    from coolcheck import live_registry as LR
    from coolcheck.features import station_day_features

    print(f"environment: mlflow {mlflow.__version__}, pandas {pd.__version__}, numpy {np.__version__}, "
          f"lightgbm {lightgbm.__version__}, python {sys.version.split()[0]}", flush=True)
    spec = importlib.util.spec_from_file_location("heat_forecast_job", Path(a.src) / "jobs" / "heat_forecast.py")
    hf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hf)  # module level only: loads the final-check job's helpers; main() does not run

    mlflow.set_tracking_uri("databricks")
    mlflow.set_registry_uri("databricks-uc")
    mv, uri = LR.champion(MlflowClient(), a.model_name)
    model = mlflow.pyfunc.load_model(uri)
    print(f"model {a.model_name} version {mv.version} ({uri}); model sha256 {(mv.tags or {}).get('model_sha256', '?')}")

    spark = SparkSession.builder.getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    t, target = LM.tables(a.catalog), a.target_date
    ver = {k: hf.BT.pin_version(spark, t[k]) for k in ("wbgt", "rain", "fc")}
    src, _ = hf.FJ.read_inputs(spark, t, ver, target, target, "nightly")
    targets = spark.sql(f"SELECT DATE'{target}' AS target_date")
    feats = station_day_features(src["wbgt"], src["rain"], src["fc"], targets, target, LM.CUTOFF_MINUTES).toPandas()
    x = LM.model_input(feats)
    print(f"{len(x)} station rows for {target}; forecast_missing in the data: {int(x.forecast_missing.sum())}", flush=True)

    failed = []

    def predict(label, frame):
        try:
            p = model.predict(frame)
            gap = float(np.abs(p.sum(axis=1) - 1).max())
            print(f"{label}: {len(p)} rows, NaN {int(p.isna().sum().sum())}, largest |sum - 1| {gap:.2e}", flush=True)
            if p.isna().any().any() or gap > 1e-9:
                failed.append(label)
            return p
        except Exception as e:  # noqa: BLE001 - the error is the finding; recorded and the check goes on
            print(f"{label}: FAILED {type(e).__name__}: {str(e)[:600]}", flush=True)
            failed.append(label)
            return None

    # 1. as they are, against the stored forecast
    p0 = predict("1. rows as they are", x)
    stored = spark.sql(f"SELECT DISTINCT station_id, p_low, p_moderate, p_high FROM {t['forecast']} "
                       f"WHERE target_date = DATE'{target}' AND p_high IS NOT NULL").toPandas()
    if p0 is not None:
        ids = feats[["station_id"]].reset_index(drop=True)  # model_input keeps only the model's columns
        m = pd.concat([ids, p0.reset_index(drop=True)], axis=1).merge(stored, on="station_id", suffixes=("", "_stored"))
        diff = max(float((m[c] - m[f"{c}_stored"]).abs().max()) for c in LM.PROBS)
        print(f"   against {t['forecast']} for {target}: {len(m)} stations matched, largest difference {diff:.2e}")
        if diff > 1e-12:
            failed.append("1. equal to the stored forecast")

    # 2 and 3. the forecast removed
    removed = x.assign(fc_temp_high=np.nan, fc_text=pd.Series([None] * len(x), dtype=object), forecast_missing=True)
    print(f"   removed: fc_text values {removed.fc_text.unique().tolist()}, dtype {removed.fc_text.dtype}; "
          f"fc_temp_high all NaN {bool(removed.fc_temp_high.isna().all())}")
    p_one = predict("2. one row, forecast removed", removed.head(1).reset_index(drop=True))
    p_all = predict("3. every row, forecast removed (fc_text all None)", removed)

    # 4. the fill written in by hand: what (2) and (3) must equal
    fill = model.unwrap_python_model().spec
    by_month = {int(k): v for k, v in fill["fill_by_month"].items()}
    temp, text = by_month.get(target.month, fill["fill_overall"])
    print(f"   training fill for month {target.month}: fc_temp_high {temp}, fc_text {text!r}")
    filled = x.assign(fc_temp_high=float(temp), fc_text=text, forecast_missing=False)
    p_fill = predict("4. the fill by hand, forecast_missing False", filled)
    if p_fill is not None:
        for label, p, ref in (("2", p_one, p_fill.head(1)), ("3", p_all, p_fill)):
            if p is not None:
                d = float((p.reset_index(drop=True) - ref.reset_index(drop=True)).abs().max().max())
                print(f"   {label} against 4: largest difference {d:.2e}")
                if d > 0:
                    failed.append(f"{label} equal to the fill by hand")
        if p0 is not None:
            print(f"   for scale: removing the forecast moves P(High) by up to "
                  f"{float((p_fill.p_high - p0.p_high).abs().max()):.4f} on {target}")

    print("RESULT: " + ("all checks passed" if not failed else "FAILED: " + "; ".join(failed)), flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
