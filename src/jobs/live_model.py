"""The live model's refit (Guide §A11 decision 8(e)), run once by hand: the final check's configuration refit on all
completed target dates from 2025-01-17 to 2026-10-22, logged to MLflow (role = live_model) and registered in Unity
Catalog as <catalog>.ml.heat_model with the alias champion. Nothing is re-derived: the High cut-off stays
0.10975585695894975 and is only recorded. Predictions for dates the model trained on are in-sample.

In order, each step stopping the run when it fails:
1. refuse if the model already has a version (it is refit once);
2. print silver.dq_day for 20 to 22 Oct (date, feed and status); stop if a feed is missing on a day (a short day is
   fine, as in the final check);
3. the back-test path's rows to 31 Aug (the final-check job's build_training, which also stops unless they are 9,308
   station-days with 465 High) and the scoring builder's rows for the whole window (build_window); the builder's rows to
   31 Aug must equal the back-test path's exactly (check_builder_equivalence, as in the final check's stage fit);
4. the training High rate must lie within the back-test folds' range, printed beside the final check's model;
5. the fit (coolcheck.live_model.fit_live), one MLflow run with the pyfunc model (coolcheck/heat_model.py, logged from
   code), its registration and the alias, all inside the run, so a failure there leaves the run FAILED.

Runs only as the bundle job (resources/live_model.job.yml). The final-check job (and through it the back-test job) is
loaded from its file for the builder and the back-test path; neither file is changed.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path


def _src_path():
    if "--src" in sys.argv:
        return sys.argv[sys.argv.index("--src") + 1]
    return str(Path(__file__).resolve().parents[1])


sys.path.insert(0, _src_path())

import pandas as pd  # noqa: E402

from coolcheck import backtest as B  # noqa: E402
from coolcheck import final_check as FC  # noqa: E402
from coolcheck import live_model as LM  # noqa: E402
from coolcheck import live_registry as LR  # noqa: E402
from coolcheck.features import FEATURES  # noqa: E402


def _final_check_job():
    """The final-check job's scoring builder and back-test path (and the back-test job's helpers through it), loaded from
    its file; its main() does not run."""
    spec = importlib.util.spec_from_file_location("final_check_job", Path(_src_path()) / "jobs" / "final_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FJ = _final_check_job()
BT = FJ.BT
MODEL_CODE = "coolcheck/heat_model.py"
CODE_FILES = FJ.CODE_FILES + ["coolcheck/live_model.py", MODEL_CODE, "coolcheck/live_registry.py", "jobs/live_model.py"]


def code_sha256():
    """sha256 over the code files this run used (the back-test's, the final check's and the live model's)."""
    h = hashlib.sha256()
    for f in CODE_FILES:
        h.update(f.encode("utf-8"))
        h.update((Path(_src_path()) / f).read_bytes())
    return h.hexdigest()


def pin_static(spark, ws, t):
    """As the final-check job's main(): the input tables' versions, the distance table as bt_dist_pinned (the builder's
    area mapping runs the view's SQL on it), the 41 areas and the view-definition check."""
    ver = {k: BT.pin_version(spark, t[k]) for k in ("wbgt", "rain", "fc", "dist", "areas")}
    BT.read(spark, t["dist"], ver["dist"], ["*"], "TRUE").createOrReplaceTempView("bt_dist_pinned")
    areas = BT.read(spark, t["areas"], ver["areas"], ["planning_area", "aged_65_plus"], "aged_65_plus > 0").toPandas()
    if len(areas) != LM.N_AREAS:
        raise SystemExit(f"{len(areas)} areas with residents aged 65+, expected {LM.N_AREAS}")
    return ver, areas, BT.check_view(ws, t["view"], t["labels"], t["dist"], LM.CUTOFF_MINUTES)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="coolcheck")
    ap.add_argument("--src")
    ap.add_argument("--experiment-id", required=True)
    ap.add_argument("--git-sha", required=True)
    ap.add_argument("--model-name", required=True)
    a = ap.parse_args()
    FJ.check_git_sha(a.git_sha)
    started = datetime.now(LM.SGT)
    run_date = started.date()
    if not run_date > LM.LIVE_LAST:
        raise SystemExit(f"run date {run_date} is not after {LM.LIVE_LAST}: the refit trains on completed days only")
    code_sha = code_sha256()
    print(f"live model refit; git {a.git_sha}; code sha256 {code_sha}; run date {run_date} (SGT); model {a.model_name}; "
          f"training window {LM.LIVE_FIRST} to {LM.LIVE_LAST}", flush=True)

    import lightgbm as lgb
    import mlflow
    import numpy as np
    from mlflow import MlflowClient

    mlflow.set_tracking_uri("databricks")
    mlflow.set_registry_uri("databricks-uc")
    client = MlflowClient()
    LR.refuse_if_registered(client, a.model_name)
    print(f"{a.model_name}: no version registered yet", flush=True)

    from databricks.sdk import WorkspaceClient
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    ws = WorkspaceClient()
    spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    packages = BT.package_versions()
    print("packages:", json.dumps(packages), flush=True)
    stages = {}

    def mark(stage):
        stages[stage] = round((datetime.now(LM.SGT) - started).total_seconds(), 1)
        print(f"[{stages[stage]:7.1f} s] {stage}", flush=True)

    t = LM.tables(a.catalog)
    ver, areas, view_check = pin_static(spark, ws, t)
    mark("static inputs pinned")

    # ---- 2. every feed present on 20 to 22 Oct
    dq = spark.sql(f"SELECT sgt_date, feed, status FROM {t['dq']} "
                   f"WHERE sgt_date BETWEEN DATE'{LM.DQ_FIRST}' AND DATE'{LM.DQ_LAST}'").toPandas()
    dq_lines, missing = LM.feeds_by_day(dq)
    print(f"silver.dq_day, {LM.DQ_FIRST} to {LM.DQ_LAST} (date, feed, status):\n" + "\n".join(dq_lines), flush=True)
    if missing:
        raise SystemExit("a feed is missing on a day: " + ", ".join(f"{d} {f}" for d, f in missing) + "; stop")

    # ---- 3. the back-test path to 31 Aug, the builder for the whole window, and their equivalence to 31 Aug
    train = FJ.build_training(spark, t, ver, areas, run_date)
    mark(f"back-test path to {B.LAST_BACKTEST_DATE}: {len(train['rows']):,} station-days, "
         f"{int((train['rows'].y == B.HIGH).sum()):,} High")
    w = FJ.build_window(spark, t, ver, areas, LM.LIVE_FIRST, LM.LIVE_LAST, run_date, train["lab_pdf"], "live")
    mark(f"scoring builder for {LM.LIVE_FIRST} to {LM.LIVE_LAST}: {len(w['rows']):,} station-days")
    aug = pd.Timestamp(B.LAST_BACKTEST_DATE)
    bt_area = train["amap41"].merge(train["rows"], on=["station_id", "target_date"], how="inner")
    w_rows = w["rows"][w["rows"].target_date <= aug]
    summary = FC.check_builder_equivalence(train["rows"], bt_area, w_rows,
                                           FC.area_days(w["amap41"][w["amap41"].target_date <= aug], w_rows))
    print(f"the builder's rows to {B.LAST_BACKTEST_DATE} equal the back-test path's: {json.dumps(summary)}")
    print("largest float difference (tolerance 1e-9): "
          + "; ".join(f"{k} {v['max_abs_diff']!r}" for k, v in summary.items()), flush=True)

    # ---- 4. the training High rate
    try:
        rate = LM.check_training_rate(w["rows"])
    except AssertionError as e:
        raise SystemExit(str(e))
    print(rate["line"], flush=True)

    # ---- 5. fit, log, register
    fit = LM.fit_live(w["rows"])
    model_text = fit.booster.model_to_string()
    model_sha = hashlib.sha256(model_text.encode("utf-8")).hexdigest()
    mark("fitted")
    print(f"fit: {fit.train_rows:,} station-days, {fit.train_high:,} High; config {FC.FINAL_CONFIG}; model sha256 "
          f"{model_sha}; {len(fit.categories)} text categories; fill by month {fit.fill['by_month']}; overall "
          f"{fit.fill['overall']}; training dates with a filled forecast {len(fit.filled)}; latest target date used: "
          + "; ".join(f"{k} {pd.Timestamp(v):%Y-%m-%d}" for k, v in fit.used.items()), flush=True)
    spec = LM.model_spec(fit)
    x = LM.model_input(w["rows"])
    example = x[~x.forecast_missing].head(5)
    signature = mlflow.models.infer_signature(example, LM.predict_proba(fit, example))
    window = f"{LM.LIVE_FIRST}..{LM.LIVE_LAST}"
    params = {"git_sha": a.git_sha, "code_sha256": code_sha, "model_sha256": model_sha, "run_date": str(run_date),
              "training_window": window, "train_rows": fit.train_rows, "train_high": fit.train_high,
              "train_high_rate": round(rate["rate"], 6), "num_leaves": FC.FINAL_CONFIG[0], "rounds": FC.FINAL_CONFIG[1],
              "lgb_fixed": json.dumps(B.LGB_FIXED), "features": ",".join(FEATURES), "cutoff_minutes": LM.CUTOFF_MINUTES,
              "high_cutoff": repr(FC.FINAL_CUTOFF), "text_categories": len(fit.categories),
              "fill_by_month": json.dumps(spec["fill_by_month"]), "fill_overall": json.dumps(spec["fill_overall"]),
              "model_name": a.model_name, "view_definition_ok": view_check["equals_nearest_station_sql"]}
    params.update({f"pkg.{k}": v for k, v in packages.items()})
    lineage = {"inputs": train["lineage"] + w["lineage"], "view_check": view_check, "dq_day_20_22_oct": dq_lines,
               "equivalence_to_31_aug": summary, "training_rate": rate, "git_sha": a.git_sha, "code_sha256": code_sha,
               "packages": packages, "stages_seconds": stages}
    with tempfile.TemporaryDirectory() as d, \
            mlflow.start_run(experiment_id=a.experiment_id, run_name=LM.ROLE,
                             tags={"role": LM.ROLE, "git_sha": a.git_sha}) as run:
        booster_path, spec_path = Path(d) / "booster.txt", Path(d) / "spec.json"
        booster_path.write_bytes(model_text.encode("utf-8"))  # LF, byte for byte the string model_sha256 hashes
        spec_path.write_text(json.dumps(spec, indent=1), encoding="utf-8")
        items = list(params.items())
        for i in range(0, len(items), 100):
            mlflow.log_params(dict(items[i:i + 100]))
        mlflow.pyfunc.log_model(artifact_path="model", python_model=str(Path(_src_path()) / MODEL_CODE),
                                artifacts={"booster": str(booster_path), "spec": str(spec_path)}, signature=signature,
                                pip_requirements=[f"lightgbm=={lgb.__version__}", f"pandas=={pd.__version__}",
                                                  f"numpy=={np.__version__}"])
        mlflow.log_dict(json.loads(json.dumps(lineage, default=str)), "lineage.json")
        mark("logged to MLflow")
        mv = mlflow.register_model(f"runs:/{run.info.run_id}/model", a.model_name)
        client.set_registered_model_alias(a.model_name, LR.ALIAS, mv.version)
        for k, v in {"git_sha": a.git_sha, "code_sha256": code_sha, "model_sha256": model_sha, "training_window": window,
                     "train_rows": fit.train_rows, "train_high": fit.train_high, "high_cutoff": repr(FC.FINAL_CUTOFF),
                     "mlflow_run_id": run.info.run_id}.items():
            client.set_model_version_tag(a.model_name, mv.version, k, str(v))
        mlflow.set_tag("model_version", str(mv.version))
        mark("registered")
    resolved, uri = LR.champion(client, a.model_name)
    print(f"MLflow run {run.info.run_id} (role = {LM.ROLE}); registered {a.model_name} version {mv.version}; alias "
          f"{LR.ALIAS} -> version {resolved.version} ({uri})")
    print("stages (s):", json.dumps(stages), flush=True)


if __name__ == "__main__":
    main()
