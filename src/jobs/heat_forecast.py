"""The nightly heat forecast, task 2 of resources/heat_forecast.job.yml (task 1 is a refresh-only pipeline update):
scores the target date with the champion model and writes gold.heat_forecast, one row per area of the 41 with residents
aged 65+, with MERGE on (target_date, planning_area), so a rerun replaces rather than duplicates.

The target date is the run date in SGT, or --target-date for a backfill. Its features are built as on that night (run
date = target date, cut-off 00:15 SGT) through the final check's scoring builder: read_inputs, station_day_features and
the same cut-off and completed-day checks. Each area takes its nearest reporting station for that date from
gold.area_nearest_station_daily. An area whose station has no feature row (only a 00:00 to 00:15 reading, note §1)
gets NULL probabilities: flagged, not scored. The model is the version the alias champion points to when the run
starts, loaded by that version number; it is never retrained here. A target date the model trained on is in-sample:
written, but never reported as performance.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import date, datetime
from pathlib import Path


def _src_path():
    if "--src" in sys.argv:
        return sys.argv[sys.argv.index("--src") + 1]
    return str(Path(__file__).resolve().parents[1])


sys.path.insert(0, _src_path())

import pandas as pd  # noqa: E402

from coolcheck import final_check as FC  # noqa: E402
from coolcheck import live_model as LM  # noqa: E402
from coolcheck import live_registry as LR  # noqa: E402
from coolcheck.features import assert_completed_days, forecast_for_targets, station_day_features  # noqa: E402


def _final_check_job():
    """The final-check job's scoring builder (and the back-test job's helpers through it), loaded from its file; its
    main() does not run."""
    spec = importlib.util.spec_from_file_location("final_check_job", Path(_src_path()) / "jobs" / "final_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FJ = _final_check_job()
BT = FJ.BT
CODE_FILES = FJ.CODE_FILES + ["coolcheck/live_model.py", "coolcheck/live_registry.py", "jobs/heat_forecast.py"]
STAGE_VIEW = "heat_forecast_stage"


def code_sha256():
    """sha256 over the code files this run used."""
    h = hashlib.sha256()
    for f in CODE_FILES:
        h.update(f.encode("utf-8"))
        h.update((Path(_src_path()) / f).read_bytes())
    return h.hexdigest()


def start_line(target, git_sha, run_id):
    """Printed first: the date scored, the commit and the code it runs, the job run that writes the rows."""
    return f"heat forecast for {target}; git {git_sha}; code sha256 {code_sha256()}; job run {run_id}"


def trained_to(mv):
    """The last target date the model version trained on, from its training_window tag (first..last)."""
    window = (mv.tags or {}).get("training_window", "")
    return date.fromisoformat(window.split("..")[1]) if ".." in window else LM.LIVE_LAST


def log_completeness(spark, dq_table, feats, target):
    """Review finding 1: silver.dq_day for the day before the target date and each station's latest input time, as log
    lines. Any error in them is printed and swallowed, so this can never fail the night or change a result."""
    try:
        dq = [r.asDict() for r in spark.sql(LM.previous_day_sql(dq_table, target)).collect()]
        for line in LM.completeness_lines(dq, feats, target):
            print(line, flush=True)
    except Exception as e:  # noqa: BLE001 - log lines only
        print(f"completeness lines not written ({type(e).__name__}: {str(e)[:300]}); the score goes on", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="coolcheck")
    ap.add_argument("--src")
    ap.add_argument("--model-name", required=True)
    ap.add_argument("--git-sha", required=True)
    ap.add_argument("--run-id", required=True, help="the job run that writes the rows ({{job.run_id}})")
    ap.add_argument("--target-date", default="", help="empty: the run date in SGT; a date: a backfill")
    a = ap.parse_args()
    FJ.check_git_sha(a.git_sha)
    try:
        target = LM.target_date_of(a.target_date, datetime.now(LM.SGT))
    except ValueError as e:
        raise SystemExit(str(e))
    print(start_line(target, a.git_sha, a.run_id), flush=True)

    import mlflow
    from mlflow import MlflowClient

    mlflow.set_tracking_uri("databricks")
    mlflow.set_registry_uri("databricks-uc")
    mv, uri = LR.champion(MlflowClient(), a.model_name)
    model = mlflow.pyfunc.load_model(uri)
    sample = "in-sample (the model trained on it): written, never reported as performance" \
        if target <= trained_to(mv) else "out of sample"
    print(f"model {a.model_name} version {mv.version} (alias {LR.ALIAS}; MLflow run {mv.run_id}; trained on "
          f"{(mv.tags or {}).get('training_window', '?')}; model sha256 {(mv.tags or {}).get('model_sha256', '?')}); "
          f"target date {target}: {sample}", flush=True)

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    t = LM.tables(a.catalog)

    # ---- features for the target date, as the scoring builder builds them
    ver = {k: BT.pin_version(spark, t[k]) for k in ("wbgt", "rain", "fc")}
    src, lineage = FJ.read_inputs(spark, t, ver, target, target, "nightly")
    for r in lineage:
        print(f"input {r['input']}: {r['pinned']}; {r['filter']}")
    targets = spark.sql(f"SELECT DATE'{target}' AS target_date")
    feats = station_day_features(src["wbgt"], src["rain"], src["fc"], targets, target, LM.CUTOFF_MINUTES).toPandas()
    if feats.empty:
        raise SystemExit(f"no station has a feature row for {target}: nothing to score")
    BT.check_feature_cutoffs(feats)
    assert_completed_days(feats, target, ["inputs_max_day"])
    feats["target_date"] = pd.to_datetime(feats.target_date)
    FC.assert_in_window(feats, target, target, "features")
    log_completeness(spark, t["dq"], feats, target)
    forecast_missing = bool(forecast_for_targets(src["fc"], targets, LM.CUTOFF_MINUTES).toPandas()
                            .forecast_missing.iloc[0])

    # ---- the 41 areas' nearest reporting stations for the target date
    areas = spark.sql(f"SELECT planning_area FROM {t['areas']} WHERE aged_65_plus > 0").toPandas().planning_area
    if len(areas) != LM.N_AREAS:
        raise SystemExit(f"{len(areas)} areas with residents aged 65+, expected {LM.N_AREAS}")
    amap = spark.sql(f"SELECT target_date, planning_area, station_id FROM {t['view']} "
                     f"WHERE target_date = DATE'{target}'").toPandas()
    amap41, flagged = LM.area_map_live(amap, areas, feats.station_id, target)

    # ---- score and write
    p = model.predict(LM.model_input(feats))
    preds = pd.concat([feats[["station_id"]].reset_index(drop=True), p.reset_index(drop=True)], axis=1)
    rows = LM.forecast_rows(amap41, preds, forecast_missing, target, mv.version, a.run_id, datetime.now(LM.SGT))
    n_scored = int(rows.p_high.notna().sum())
    print(f"{len(feats)} stations with a feature row; {len(rows)} areas, {n_scored} scored; flagged (station without a "
          f"feature row, NULL probabilities): {', '.join(flagged) or 'none'}; forecast_missing {forecast_missing}",
          flush=True)
    spark.sql(LM.create_table_sql(t["forecast"]))
    spark.createDataFrame(rows, schema=LM.FORECAST_SCHEMA).createOrReplaceTempView(STAGE_VIEW)
    merged = spark.sql(LM.merge_sql(t["forecast"], STAGE_VIEW)).toPandas()
    print("MERGE:", json.dumps(merged.to_dict("records"), default=str))
    back = spark.sql(LM.read_back_sql(t["forecast"], target)).first().asDict()
    print("read-back:", json.dumps(back, default=str), flush=True)
    LM.check_read_back(back, n_scored, mv.version, a.run_id)
    print(f"{t['forecast']}: {back['n_rows']} rows for {target}, model version {mv.version}, job run {a.run_id}")


if __name__ == "__main__":
    main()
