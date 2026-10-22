"""The rolling back-test job (docs/design/backtest.md): pin the inputs, build the station-day features and labels, run the
folds, evaluate, log to MLflow and write the report.

From the bundle (resources/backtest.job.yml, kept as .draft until deployed) it logs to the experiment given by
--experiment-id. With --profile it runs through Databricks Connect for development: it logs nothing to MLflow and writes
the report and artifacts to --out-dir. Nothing here reads, fits on or scores a target date after 2026-08-31.
"""
import argparse
import hashlib
import json
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _src_path():
    if "--src" in sys.argv:
        return sys.argv[sys.argv.index("--src") + 1]
    return str(Path(__file__).resolve().parents[1])


sys.path.insert(0, _src_path())

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from coolcheck import backtest as B  # noqa: E402
from coolcheck.features import (FEATURES, ORIGINAL_8, assert_completed_days, rain_min_readings,  # noqa: E402
                                station_day_features)
from coolcheck.nearest import nearest_station_sql  # noqa: E402

SGT = timezone(timedelta(hours=8))
BOUNDARY, VIEW_CUTOFF, LOOKBACK = "mp2025", 15, 7
CODE_FILES = ["coolcheck/features.py", "coolcheck/backtest.py", "coolcheck/metrics.py", "coolcheck/nearest.py",
              "coolcheck/timeutil.py", "jobs/backtest.py"]
WBGT_COLS = ["station_id", "reading_ts", "sgt_date", "wbgt", "heat_stress", "station_lat", "station_lon"]
RAIN_COLS = ["station_id", "reading_ts", "sgt_date", "rainfall_mm", "station_lat", "station_lon"]
FC_COLS = ["issue_ts", "updated_ts", "issue_sgt_date", "valid_start_raw", "temp_high", "forecast_text", "text_start_hour",
           "text_start_day", "text_start_month", "text_end_hour", "text_end_day", "text_end_month"]
LABEL_COLS = ["station_id", "sgt_date", "label", "usable", "n_high", "n_valid", "first_valid_ts", "last_valid_ts"]
IM1_2025 = (pd.Timestamp("2025-03-01"), pd.Timestamp("2025-06-01"))


# ---------------------------------------------------------------- pinning the inputs
def pin_version(spark, table):
    """The table's current Delta version if time travel to it works, else None (then rows and checksum only)."""
    try:
        v = int(spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").first()["version"])
        spark.sql(f"SELECT 1 FROM {table} VERSION AS OF {v} LIMIT 1").collect()
        return v
    except Exception as e:  # noqa: BLE001 - recorded in the lineage
        print(f"no time travel for {table}: {type(e).__name__}: {str(e)[:200]}")
        return None


def read(spark, table, version, cols, where):
    src = f"{table} VERSION AS OF {version}" if version is not None else table
    return spark.sql(f"SELECT {', '.join(cols)} FROM {src} WHERE {where}")


def fingerprint(df, cols):
    """Row count and an order-free checksum (bit_xor of xxhash64 over the columns) of exactly what was read."""
    r = df.selectExpr("count(*) AS n", f"bit_xor(xxhash64({', '.join(cols)})) AS h").first()
    return {"rows": int(r["n"]), "checksum": None if r["h"] is None else int(r["h"])}


def pin_labels(spark, table, last_target, run_date):
    """The labels materialized view cannot be time-travelled (h10_v2.md method): pulled once, hashed as a canonical CSV,
    rebuilt as a temp view, and the rebuilt copy checked against the view."""
    src = spark.sql(f"SELECT {', '.join(LABEL_COLS)} FROM {table} "
                    f"WHERE sgt_date <= DATE'{last_target}' AND sgt_date < DATE'{run_date}'")
    pdf = src.toPandas().sort_values(["station_id", "sgt_date"]).reset_index(drop=True)
    csv_bytes = pdf.to_csv(index=False).encode("utf-8")
    pinned = spark.createDataFrame(pdf, schema=src.schema)
    pinned.createOrReplaceTempView("bt_labels_pinned")
    chk = ["count(*) AS n", "sum(unix_seconds(first_valid_ts)) AS f", "sum(unix_seconds(last_valid_ts)) AS l",
           "sum(n_valid) AS v"]
    if tuple(pinned.selectExpr(*chk).first()) != tuple(src.selectExpr(*chk).first()):
        raise SystemExit("the rebuilt label copy differs from the view (did the pipeline update during the run?)")
    return pinned, pdf, csv_bytes


def check_view(ws, view, labels, dist, cutoff):
    """The view's stored definition must be the SQL nearest_station_sql builds for the live tables (island rule on,
    cut-off 15, look-back 7, mp2025); the job then runs that SQL over the pinned copies. No row of the view is read."""
    info = ws.tables.get(view)
    text = info.view_definition or ""
    want = nearest_station_sql(labels, dist, BOUNDARY, VIEW_CUTOFF, LOOKBACK, True)
    same = " ".join(text.split()) == " ".join(want.split())
    out = {"view": view, "definition_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
           "updated_at": info.updated_at, "equals_nearest_station_sql": same}
    if cutoff == VIEW_CUTOFF and not same:
        raise SystemExit(f"{view}: its definition differs from nearest_station_sql(..., island_rule=True); stop")
    return out


def code_sha256():
    h = hashlib.sha256()
    for f in CODE_FILES:
        h.update(f.encode("utf-8"))
        h.update((Path(_src_path()) / f).read_bytes())
    return h.hexdigest()


def window_audit(frames, last_target):
    rows = []
    for name, (df, col) in frames.items():
        d = pd.to_datetime(df[col])
        rows.append({"frame": name, "column": col, "rows": len(df), "first": d.min(), "last": d.max()})
        if len(df) and d.max() > pd.Timestamp(last_target):
            raise SystemExit(f"window audit: {name}.{col} reaches {d.max():%Y-%m-%d}, after {last_target}")
    return pd.DataFrame(rows)


def check_feature_cutoffs(f):
    cut = pd.to_datetime(f.cutoff_ts)
    late = ((pd.to_datetime(f.inputs_max_ts) >= cut) | (pd.to_datetime(f.rain_inputs_max_ts) >= cut)
            | (pd.to_datetime(f.fc_updated_ts) > cut)
            | (pd.to_datetime(f.fc_issue_ts) < pd.to_datetime(f.target_date) - np.timedelta64(7, "h")))
    if late.any():
        raise SystemExit(f"{int(late.sum())} feature rows used an input outside the cut-off rules")


# ---------------------------------------------------------------- report
def _cell(v):
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NaT:
        return "—"
    if isinstance(v, (pd.Timestamp, datetime)):
        return f"{v:%Y-%m-%d}"
    if isinstance(v, (bool, np.bool_)):
        return str(bool(v))
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}"
    if isinstance(v, (float, np.floating)):
        return f"{v:,.0f}" if float(v).is_integer() and abs(v) >= 1 else f"{v:,.3f}"
    return str(v)


def md(df):
    if df.empty and not len(df.columns):
        return ["None."]
    cols = list(df.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return out


def _ci(r, key):
    v, lo, hi = r.get(key), r.get(f"{key}_lo"), r.get(f"{key}_hi")
    if v is None or np.isnan(v):
        return "—"
    return f"{v:.3f} ({lo:.3f} to {hi:.3f})" if lo is not None and not np.isnan(lo) else f"{v:.3f}"


def _num(x):
    """An expected count: whole numbers plain, a tie-split count to one decimal."""
    return f"{x:,.0f}" if float(x).is_integer() else f"{x:,.1f}"


def method_table(res):
    rows = []
    for name, r in res["methods"].items():
        rows.append({"method": "persistence (binary)" if name == "reference" else name,
                     "PR-AUC (95%)": _ci(r, "pr_auc") if "pr_auc" in r else "— (binary)",
                     "recall at persistence load (95%)": _ci(r, "recall_at_load"),
                     "TP of High": f"{_num(r['tp'])} of {r['positives']:,}",
                     "alerts": _num(r["alerts"]),
                     "precision (95%)": _ci(r, "precision_at_load"),
                     "sustained-High recall (95%)": _ci(r, "sustained_recall")})
    return md(pd.DataFrame(rows))


def diff_table(res):
    rows = []
    for (a, b), d in res["diffs"].items():
        rows.append({"difference": f"{a} − {'persistence (binary)' if b == 'reference' else b}",
                     "PR-AUC (95%)": _ci(d, "pr_auc") if "pr_auc" in d else "—",
                     "recall at load (95%)": _ci(d, "recall_at_load"),
                     "sustained-High recall (95%)": _ci(d, "sustained_recall")})
    return md(pd.DataFrame(rows))


def curve_sample(curve):
    """The first threshold reaching each recall level from 0.30 to 0.95: a sample of the full curve (an artifact)."""
    rows = []
    for level in np.arange(0.30, 0.951, 0.05):
        hit = curve[curve.recall >= level - 1e-12]
        if len(hit):
            r = hit.iloc[0]
            rows.append({"recall at least": round(level, 2), "threshold P(High)": r.threshold, "alerts": int(r.alerts),
                         "TP": int(r.tp), "recall": r.recall, "precision": r.precision})
    return md(pd.DataFrame(rows))


def render_report(ctx):
    res, rec, L = ctx["results"], ctx["records"], []
    L += ["# Rolling back-test report", "",
          f"Generated {ctx['finished']:%Y-%m-%d %H:%M} SGT by `src/jobs/backtest.py` ({ctx['mode']}). Git `{ctx['git_sha']}`, "
          f"code sha256 `{ctx['code_sha256'][:16]}…`, run date {ctx['run_date']} (SGT), cut-off {ctx['cutoff']} min "
          f"after 00:00 on the target date, folds {ctx['folds'][0]:%Y-%m} to {ctx['folds'][-1]:%Y-%m}, "
          f"{ctx['bootstrap']:,} block resamples, seed {ctx['seed']}. This report states numbers; it does not interpret "
          "them. Nothing was read, fitted or scored after 2026-08-31.", ""]
    L += ["## Inputs (pinned)", ""] + md(pd.DataFrame(ctx["lineage_rows"])) + [""]
    v = ctx["view_check"]
    L += [f"View `{v['view']}`: definition equals `nearest_station_sql(..., island_rule=True)`: "
          f"{v['equals_nearest_station_sql']}; the job ran that SQL on the pinned copies (definition sha256 "
          f"`{v['definition_sha256'][:16]}…`).", ""]
    L += ["### Window audit", ""] + md(ctx["audit"]) + [""]
    L += ["## Rows", "",
          f"Station-day rows (reporting station, usable label): {ctx['n_rows']:,}. Usable station-days without a feature "
          f"row (a station's first day, or first day back): {len(ctx['no_feature_row']):,}. Test area-days over the 41 "
          f"areas: {ctx['n_area']:,}; dropped because their station-day is not usable: {ctx['area_dropped']:,}.", ""]
    L += md(rec[["fold", "train_rows", "train_high", "train_last_date", "test_rows", "test_high", "config", "num_leaves",
                 "rounds", "nea_theta", "unseen_text_rows", "filled_test_dates"]]) + [""]
    tf = ctx["fills"]
    tf = tf[tf.split == "test"] if len(tf) else tf
    L += ["### Forecasts filled in the test months (rule: §5.1 step 2)", ""]
    L += (md(tf[["fold", "target_date", "fc_temp_high", "fc_text", "source"]]) if len(tf) else ["None."]) + [""]
    L += [f"Selected forecasts whose text disagrees with the corrected validity: {ctx['text_disagree']}.", ""]
    L += ["## Hyper-parameters chosen per fold (from earlier folds only)", ""]
    hp = rec[["fold", "config", "num_leaves", "rounds", "choice_aps"]].copy()
    hp["choice_aps"] = hp.choice_aps.map(lambda d: "; ".join(f"{k}: {v:.3f}" for k, v in d.items()) or "first fold")
    L += md(hp) + ["",
                   f"Secondary line, chosen on the same folds: candidate {B.HP_CANDIDATES[ctx['best']]} has the best pooled "
                   "station-level PR-AUC over all folds ("
                   + "; ".join(f"{B.HP_CANDIDATES[i]}: {a:.3f}" for i, a in ctx["best_aps"].items()) + ").", ""]
    titles = {"area41": "Headline: area-days over the 41 areas with residents aged 65+",
              "station_all": "Station-days: all stations", "station_wo3": "Station-days: without S142, S137 and S135",
              "station_o8": "Station-days: the original 8 (7 after 24 Jun 2026)",
              "area41_feb_aug_2026": "Feb to Aug 2026, area-days (same month last year)",
              "station_all_feb_aug_2026": "Feb to Aug 2026, station-days (same month last year)"}
    L += ["## Bootstrap resamples skipped, per evaluation set and period", "",
          "A resample (7-day blocks drawn with replacement) with no High row in a set has no recall or PR-AUC, so it is "
          "skipped; the intervals use the rest.", ""]
    L += md(pd.DataFrame([{"set": n, "period": f"{r['first_date']:%Y-%m-%d} to {r['last_date']:%Y-%m-%d}",
                           "rows": r["rows"], "High": r["positives"], "resamples": r["resamples"],
                           "skipped": r["skipped"], "used": r["resamples"] - r["skipped"]}
                          for n, r in res["sets"].items()])) + [""]
    for name, r in res["sets"].items():
        L += [f"## {titles.get(name, name)}", "",
              f"Rows {r['rows']:,}; High {r['positives']:,} ({r['positives'] / max(r['rows'], 1):.1%}, the no-skill "
              f"PR-AUC); persistence alerts K = {r['K']:,}; resamples skipped (no High): {r['skipped']} of "
              f"{r['resamples']:,}.", ""]
        L += method_table(r) + [""]
        if name == "area41" and ("model", "persistence_continuous") in r["diffs"]:
            d = r["diffs"][("model", "persistence_continuous")]
            L += [f"Input to note §13 (the briefing's heat term): pooled area-day PR-AUC, model − persistence (continuous "
                  f"score) = {_ci(d, 'pr_auc')}.", ""]
        nt = r["nea_rule_at_theta"]
        L += [f"NEA rule at its own per-fold threshold: {nt['tp']:,.0f} of {nt['positives']:,} High (recall "
              f"{nt['recall']:.3f}), {nt['alerts']:,.0f} alerts (precision {nt['precision']:.3f}).", ""]
        if name.startswith("area41"):
            L += [B.LABEL_NOISE_NOTE, ""]
        L += ["Paired differences:", ""] + diff_table(r) + [""]
    for name, t in res["per_month"].items():
        L += [f"## Per month, counts ({name}; model at the persistence load)", ""] + md(t) + [""]
    for name, t in res["season"].items():
        L += [f"## Season by year, counts ({name})", ""] + md(t) + [""]
    L += ["## Inter-monsoon 1, 2025 (persistence and base rate only; no fold predicts Mar to May 2025)", ""]
    for level, r in res["im1_2025"].items():
        L += [f"- {level}: {r['rows']:,} rows, {r['positives']:,} High ({r['positives'] / max(r['rows'], 1):.1%}); "
              f"persistence {r['tp']:,.0f} of {r['positives']:,} (recall {r['recall']:.3f}), {r['alerts']:,.0f} alerts "
              f"(precision {r['precision']:.3f})."]
    L += ["", "Inter-monsoon 1 of 2026 for every method is in the season tables above.", ""]
    hb = res["high_by_readings"]
    L += ["## High station-days in the test months by High readings that day", "",
          f"1 reading: {hb['1']:,}; 2 readings: {hb['2']:,}; 3 or more (sustained): {hb['3 or more']:,}.", ""]
    L += ["## Three classes (station-days, model)", "", f"Multiclass log loss {res['log_loss']:.4f}. Rows: label "
          "(0 Low, 1 Moderate, 2 High); columns: the most probable class.", ""]
    L += md(res["three_class"].reset_index()) + [""]
    for name, c in res["pr_curve"].items():
        L += [f"## PR curve sample, model ({name}); the full curve is an artifact", ""] + curve_sample(c) + [""]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- MLflow
def _metrics(r, prefix):
    out = {}
    for k, v in r.items():
        if k == "threshold" or v is None or not isinstance(v, (int, float, np.integer, np.floating)) or not np.isfinite(v):
            continue
        out[f"{prefix}/{k.replace('_at_load', '_at_persistence_load')}"] = float(v)
    return out


def log_mlflow(ctx, out):
    import mlflow

    mlflow.set_tracking_uri("databricks")
    res, exp, bid = ctx["results"], ctx["experiment_id"], ctx["backtest_id"]
    params = {"backtest_id": bid, "git_sha": ctx["git_sha"], "code_sha256": ctx["code_sha256"],
              "run_date": str(ctx["run_date"]), "cutoff_minutes": ctx["cutoff"],
              "folds": f"{ctx['folds'][0]:%Y-%m}..{ctx['folds'][-1]:%Y-%m}", "bootstrap": ctx["bootstrap"],
              "seed": ctx["seed"], "features": ",".join(FEATURES), "panel": ",".join(ORIGINAL_8),
              "rain_min_readings": rain_min_readings(ctx["cutoff"]), "trail_min_days": "4 of 7",
              "char_min_days": "20 of 30", "same_month_min_days": B.SAME_MONTH_MIN_DAYS,
              "half_life_days": B.HALF_LIFE_DAYS, "lgb_fixed": json.dumps(B.LGB_FIXED),
              "view_definition_ok": ctx["view_check"]["equals_nearest_station_sql"]}
    params.update({f"input.{r['input']}": f"{r['type']}; {r['pinned']}; {r['filter']}"[:500] for r in ctx["lineage_rows"]})
    tags = {"backtest_id": bid, "git_sha": ctx["git_sha"]}

    def run(name, role, metrics, extra_params=None, extra_tags=None, artifacts=False):
        with mlflow.start_run(experiment_id=exp, run_name=name, tags={**tags, "role": role, **(extra_tags or {})}) as r:
            p = {**params, **(extra_params or {})}
            items = list(p.items())
            for i in range(0, len(items), 100):
                mlflow.log_params(dict(items[i:i + 100]))
            mlflow.log_metrics(metrics)
            if artifacts:
                mlflow.log_artifacts(str(out))
            return r.info.run_id

    def collect(method):
        m = {}
        for s, r in res["sets"].items():
            if method in r["methods"]:
                m.update(_metrics(r["methods"][method], s))
        return m

    model_metrics = collect("model")
    for s, r in res["sets"].items():
        model_metrics[f"{s}/bootstrap_resamples"] = float(r["resamples"])
        model_metrics[f"{s}/bootstrap_skipped"] = float(r["skipped"])
        for (a, b), d in r["diffs"].items():
            model_metrics.update(_metrics(d, f"{s}/diff_vs_{'persistence_binary' if b == 'reference' else b}"))
    choices = {f"config.{f:%Y-%m}": str(B.HP_CANDIDATES[c]) for f, c in zip(ctx["records"].fold, ctx["records"].config)}
    model_id = run("model", "model", model_metrics, choices, artifacts=True)
    pers = collect("reference")
    for s, r in res["sets"].items():
        if "persistence_continuous" in r["methods"]:
            pers.update(_metrics({"pr_auc": r["methods"]["persistence_continuous"].get("pr_auc"),
                                  "pr_auc_lo": r["methods"]["persistence_continuous"].get("pr_auc_lo"),
                                  "pr_auc_hi": r["methods"]["persistence_continuous"].get("pr_auc_hi")}, s))
            pers.update(_metrics(r["methods"]["persistence_continuous"], f"{s}/continuous"))
    link = {"artifacts_in_run": model_id}
    run("baseline_persistence", "baseline", pers, link)
    run("baseline_same_month_last_year", "baseline", collect("same_month_last_year"), link)
    nea = collect("nea_rule")
    for s, r in res["sets"].items():
        nea.update(_metrics(r["nea_rule_at_theta"], f"{s}/at_theta"))
    run("baseline_nea_forecast_rule", "baseline", nea, link)
    for name in ("ablation_no_station_char", "ablation_without_S142_S137_S135", "ablation_recency_hl180"):
        m = collect(name)
        if m:
            run(name, "ablation", m, link)
    for i, (leaves, rounds) in enumerate(B.HP_CANDIDATES):
        chosen = [f"{f:%Y-%m}" for f, c in zip(ctx["records"].fold, ctx["records"].config) if c == i]
        m = {"station_all/pr_auc_all_folds": float(ctx["best_aps"][i])} if np.isfinite(ctx["best_aps"][i]) else {}
        secondary = i == ctx["best"]
        if secondary:
            m.update(collect("best_overall"))
        run(f"hp_candidate_{i + 1}", "hp_candidate", m,
            {**link, "num_leaves": leaves, "rounds": rounds, "folds_chosen": ",".join(chosen) or "none"},
            {"secondary": "chosen on the same folds"} if secondary else None)
    return model_id


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="coolcheck")
    ap.add_argument("--src")
    ap.add_argument("--experiment-id")
    ap.add_argument("--git-sha", default="unknown")
    ap.add_argument("--cutoff-minutes", type=int, default=15)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--folds", type=int, default=len(B.FOLDS), help="the first N folds (the dry run uses 2)")
    ap.add_argument("--no-ablations", action="store_true")
    ap.add_argument("--profile", help="run through Databricks Connect with this CLI profile; nothing is logged to MLflow")
    ap.add_argument("--out-dir", help="where a Connect run writes its report and artifacts")
    a = ap.parse_args()
    if not 1 <= a.folds <= len(B.FOLDS):
        raise SystemExit(f"--folds must be 1 to {len(B.FOLDS)}")
    if a.profile and not a.out_dir:
        raise SystemExit("--profile needs --out-dir (a Connect run logs nothing to MLflow)")
    if not a.profile and not a.experiment_id:
        raise SystemExit("--experiment-id is required for a job run")

    from databricks.sdk import WorkspaceClient

    if a.profile:
        from databricks.connect import DatabricksSession
        spark = DatabricksSession.builder.serverless().profile(a.profile).getOrCreate()
        ws = WorkspaceClient(profile=a.profile)
    else:
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        ws = WorkspaceClient()
    spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")

    started = datetime.now(SGT)
    run_date = started.date()
    folds = B.FOLDS[:a.folds]
    last_target = (folds[-1] + pd.offsets.MonthEnd(0)).date()
    if not last_target <= B.LAST_BACKTEST_DATE < run_date:
        raise SystemExit(f"last target date {last_target} must be on or before {B.LAST_BACKTEST_DATE}, itself before "
                         f"the run date {run_date}")
    cat = a.catalog
    t = {"wbgt": f"{cat}.silver.wbgt_readings", "rain": f"{cat}.silver.rainfall_readings",
         "fc": f"{cat}.silver.forecast_issues", "labels": f"{cat}.silver.station_daily_label",
         "dist": f"{cat}.silver.area_station_distance", "areas": f"{cat}.silver.area_exposure",
         "view": f"{cat}.gold.area_nearest_station_daily"}

    # ---- pin
    if not spark.catalog.tableExists(t["areas"]):
        raise SystemExit(f"{t['areas']} does not exist: run scripts/static/load_area_exposure.py first (decision 1)")
    ver = {k: pin_version(spark, t[k]) for k in ("wbgt", "rain", "fc", "dist", "areas")}
    within = f"sgt_date <= DATE'{last_target}' AND sgt_date < DATE'{run_date}'"
    fc_where = f"issue_sgt_date <= DATE'{last_target}'"
    wbgt = read(spark, t["wbgt"], ver["wbgt"], WBGT_COLS, within)
    rain = read(spark, t["rain"], ver["rain"], RAIN_COLS, within)
    fc = read(spark, t["fc"], ver["fc"], FC_COLS, fc_where)
    dist = read(spark, t["dist"], ver["dist"], ["*"], "TRUE")
    dist.createOrReplaceTempView("bt_dist_pinned")
    areas = read(spark, t["areas"], ver["areas"], ["planning_area", "aged_65_plus"], "aged_65_plus > 0").toPandas()
    if len(areas) != 41:
        raise SystemExit(f"{len(areas)} areas with residents aged 65+, expected 41")
    lab_pinned, lab_pdf, lab_csv = pin_labels(spark, t["labels"], last_target, run_date)
    view_check = check_view(ws, t["view"], t["labels"], t["dist"], a.cutoff_minutes)
    lineage_rows = []
    for key, df, cols, where in (("wbgt", wbgt, WBGT_COLS, within), ("rain", rain, RAIN_COLS, within),
                                 ("fc", fc, FC_COLS, fc_where)):
        fp = fingerprint(df, cols)
        lineage_rows.append({"input": t[key], "type": "streaming table",
                             "pinned": (f"Delta version {ver[key]}" if ver[key] is not None else "no time travel")
                             + f"; rows {fp['rows']:,}; checksum {fp['checksum']}", "filter": where})
    lineage_rows += [
        {"input": t["labels"], "type": "materialized view", "filter": within,
         "pinned": f"pulled once; rows {len(lab_pdf):,}; sha256 {hashlib.sha256(lab_csv).hexdigest()}"},
        {"input": t["dist"], "type": "Delta table", "filter": "boundary mp2025 in the SQL",
         "pinned": f"Delta version {ver['dist']}"},
        {"input": t["areas"], "type": "Delta table", "filter": "aged_65_plus > 0",
         "pinned": f"Delta version {ver['areas']}; {len(areas)} areas"},
        {"input": t["view"], "type": "view", "filter": "definition only",
         "pinned": f"definition sha256 {view_check['definition_sha256']}"}]

    # ---- features, labels, rows
    targets = spark.sql(f"SELECT explode(sequence(DATE'{B.FIRST_TARGET:%Y-%m-%d}', DATE'{last_target}')) AS target_date")
    feats = station_day_features(wbgt, rain, fc, targets, run_date, a.cutoff_minutes).toPandas()
    check_feature_cutoffs(feats)
    assert_completed_days(feats, run_date, ["inputs_max_day"])
    feats["target_date"] = pd.to_datetime(feats.target_date)
    labels = B.backtest_labels(lab_pinned, run_date).toPandas()
    assert_completed_days(labels, run_date, ["target_date"])
    labels["target_date"] = pd.to_datetime(labels.target_date)
    rows = B.station_day_rows(feats, labels)
    keys = feats[["station_id", "target_date"]]
    lab_in = labels[labels.target_date >= B.FIRST_TARGET]
    no_row = lab_in.merge(keys, how="left", indicator=True).query("_merge == 'left_only'")
    text_disagree = int((~feats.forecast_missing & ~feats.fc_text_agrees.eq(True)).sum())

    # ---- area mapping: the view's SQL over the pinned copies
    amap = (spark.sql(nearest_station_sql("bt_labels_pinned", "bt_dist_pinned", BOUNDARY, a.cutoff_minutes, LOOKBACK, True))
            .where(f"target_date BETWEEN DATE'{B.FIRST_TARGET:%Y-%m-%d}' AND DATE'{last_target}'")
            .select("target_date", "planning_area", "station_id").toPandas())
    amap["target_date"] = pd.to_datetime(amap.target_date)
    amap41 = amap[amap.planning_area.isin(set(areas.planning_area))]
    orphan = amap41.merge(keys, how="left", indicator=True).query("_merge == 'left_only'")
    if len(orphan):
        raise SystemExit(f"{len(orphan)} area-days whose station has no feature row, e.g. {orphan.head(3).to_dict('records')}")

    # ---- folds and evaluation
    pooled, records, fills, boosters = B.run_folds(rows, labels, folds=folds, ablations=not a.no_ablations)
    best, best_aps = B.best_overall(pooled)
    test41 = amap41[amap41.target_date >= folds[0]]
    area = test41.merge(pooled, on=["station_id", "target_date"], how="inner")
    im1 = {"station": rows[(rows.target_date >= IM1_2025[0]) & (rows.target_date < IM1_2025[1])]
           .assign(persist_alert=lambda d: d.n_high_d1.fillna(0) >= 1)}
    im1_area = amap41[(amap41.target_date >= IM1_2025[0]) & (amap41.target_date < IM1_2025[1])]
    im1["area"] = im1_area.merge(rows[["station_id", "target_date", "y", "n_high_d1"]], on=["station_id", "target_date"],
                                 how="inner").assign(persist_alert=lambda d: d.n_high_d1.fillna(0) >= 1)
    results = B.evaluate_all(pooled, area, best, a.bootstrap, a.seed, im1)
    audit = window_audit({"labels (pinned)": (lab_pdf, "sgt_date"), "features": (feats, "target_date"),
                          "labels (usable)": (labels, "target_date"), "area mapping": (amap, "target_date"),
                          "pooled predictions": (pooled, "target_date"), "area-days": (area, "target_date")}, last_target)

    # ---- artifacts and report
    out = Path(a.out_dir) if a.profile else Path(tempfile.mkdtemp(prefix="backtest_"))
    out.mkdir(parents=True, exist_ok=True)
    pooled.to_parquet(out / "predictions_station_days.parquet", index=False)
    area.to_parquet(out / "predictions_area_days.parquet", index=False)
    rec_out = records.assign(choice_aps=records.choice_aps.map(lambda d: json.dumps({str(k): v for k, v in d.items()})))
    rec_out.to_csv(out / "fold_records.csv", index=False)
    fills.to_csv(out / "forecast_fills.csv", index=False)
    no_row.drop(columns="_merge").to_csv(out / "usable_station_days_without_feature_row.csv", index=False)
    for kind in ("per_month", "season", "pr_curve"):
        for name, df in results[kind].items():
            df.to_csv(out / f"{kind}_{name}.csv", index=False)
    results["three_class"].to_csv(out / "three_class.csv")
    audit.to_csv(out / "window_audit.csv", index=False)
    (out / "labels_pinned.csv").write_bytes(lab_csv)
    import lightgbm as lgb
    imp = []
    with zipfile.ZipFile(out / "fold_models.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for (m, key), text in boosters.items():
            booster = lgb.Booster(model_str=text)
            imp.append(pd.DataFrame({"fold": m, "model": key, "feature": booster.feature_name(),
                                     "gain": booster.feature_importance("gain")}))
            chosen = key == f"c{int(records.loc[records.fold == m, 'config'].iloc[0])}"
            if chosen or key == f"c{best}":
                z.writestr(f"{m:%Y-%m}_{key}.txt", text)
    pd.concat(imp, ignore_index=True).to_csv(out / "feature_importance.csv", index=False)
    finished = datetime.now(SGT)
    ctx = {"results": results, "records": records, "fills": fills, "folds": folds, "best": best, "best_aps": best_aps,
           "lineage_rows": lineage_rows, "view_check": view_check, "audit": audit, "n_rows": len(rows),
           "no_feature_row": no_row, "n_area": len(area), "area_dropped": len(test41) - len(area),
           "text_disagree": text_disagree, "git_sha": a.git_sha, "code_sha256": code_sha256(), "run_date": run_date,
           "cutoff": a.cutoff_minutes, "bootstrap": a.bootstrap, "seed": a.seed, "finished": finished,
           "mode": "Databricks Connect, not logged" if a.profile else "bundle job",
           "experiment_id": a.experiment_id, "backtest_id": uuid.uuid4().hex[:12]}
    (out / "lineage.json").write_text(json.dumps({"inputs": lineage_rows, "view_check": view_check,
                                                  "git_sha": a.git_sha, "code_sha256": ctx["code_sha256"],
                                                  "run_date": str(run_date), "started": started.isoformat(),
                                                  "finished": finished.isoformat()}, default=str, indent=1))
    (out / "report.md").write_text(render_report(ctx), encoding="utf-8")
    print(f"report and artifacts in {out}")
    if not a.profile:
        print("model run:", log_mlflow(ctx, out))


if __name__ == "__main__":
    main()
