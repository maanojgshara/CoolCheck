"""The final check job (docs/design/backtest.md §15): one model fitted on target dates 2025-01-17 to 2026-08-31 through
the back-test's path and guards, scored once on 1 Sep to 19 Oct 2026.

Stages (job parameter `stage`), each run on the user's word, in this order; every stage first prints the commit and
the sha256 of the code files it runs:
- lock: the lock query alone, read-only: the experiment is the back-test's, the query sees the back-test's model run,
  and no scored final_check run exists (coolcheck.final_lock).
- fit: the lock, then the training half, which reads nothing after 2026-08-31: the back-test path's rows, the §15 count
  check (9,308 station-days, 465 High) and the fit; then the scoring builder on 1 Jul to 31 Aug 2026 must give the
  back-test path's station-day and area-day rows for those dates. Writes nothing.
- score: the lock, then coolcheck.final_check.run_final_check: the fit, only then the rows of 1 Sep to 19 Oct, the
  scores, and the one MLflow run tagged role = final_check. That run is the lock: it is created, tagged scored, the
  moment scoring has completed, before the report and the outputs are written into it; nothing about the scores is
  printed before it.

--override-incomplete <run_id> (job parameter override_incomplete, empty by default) lets a rerun past a scored run
whose record is not whole; only on the user's word (coolcheck.final_lock).

Runs only as the bundle job (resources/final_check.job.yml); there is no Databricks Connect path, which would score
without writing the lock. Deploy from a clean tree, so --git-sha is the code that runs. The back-test job's helpers are
loaded from src/jobs/backtest.py, which is not changed.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
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
from coolcheck import final_check as FC  # noqa: E402
from coolcheck import final_lock as FL  # noqa: E402
from coolcheck.features import (FEATURES, ORIGINAL_8, assert_completed_days, forecast_gaps, gap_reason,  # noqa: E402
                                station_day_features, usable_labels)
from coolcheck.nearest import nearest_station_sql  # noqa: E402


def _backtest_job():
    """The back-test job's helpers (reads, pins, fingerprints, view check, cut-off check, window audit, package
    versions, report cells), loaded from its file; its main() does not run."""
    spec = importlib.util.spec_from_file_location("backtest_job", Path(_src_path()) / "jobs" / "backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BT = _backtest_job()
SGT = timezone(timedelta(hours=8))
CUTOFF_MINUTES = 15
STAGES = ("lock", "fit", "score")
CODE_FILES = BT.CODE_FILES + ["coolcheck/final_check.py", "coolcheck/final_lock.py", "jobs/final_check.py"]
WINDOW_LABELS = "fc_labels_window"  # temp view: the training label pull before the window plus the window's pull
METHOD_NAMES = {"model": "model", "persistence_binary": "persistence (binary)",
                "persistence_continuous": "persistence (continuous)", "nea_rule": "NEA rule",
                "same_month_last_year": "same month last year"}
POINT_NAMES = {"cutoff": "at the cut-off", "persistence_load": "at persistence's alert load",
               "own_rule": "own rule (yesterday High)", "theta": "own rule (forecast ≥ θ)"}
PERIOD_NAMES = {"all": "1 Sep to 19 Oct", "2026-09": "Sep", "2026-10": "Oct (1 to 19)"}
SET_TITLES = {"area41": "Area-days over the 41 areas with residents aged 65+", "station_all": "Station-days: all stations",
              "station_wo3": "Station-days: without S142, S137 and S135",
              "station_o8": "Station-days: the original 8 (7 after S130 stopped)"}


# ---------------------------------------------------------------- checks before anything is read
def check_git_sha(sha):
    """(d): the commit the job runs, from ${bundle.git.commit}; refused when the bundle had none."""
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha or ""):
        raise SystemExit(f"--git-sha {sha!r} is not a commit hash: deploy from a clean git tree so the run logs its "
                         "commit")
    return sha


def check_run_date(run_date):
    """Labels from completed days only (note §1): the last scored day, 19 Oct 2026, must be over."""
    if not run_date > FC.FINAL_LAST:
        raise SystemExit(f"run date {run_date} is not after {FC.FINAL_LAST}: the final check runs from "
                         f"{FC.FINAL_LAST + timedelta(days=1)}")


def check_override(run_id):
    """--override-incomplete: empty for none, else an MLflow run id (32 hex characters). Whether that run may be passed
    (scored, not complete) is decided by the lock (FL.MlflowLock)."""
    if not run_id:
        return None
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise SystemExit(f"--override-incomplete {run_id!r} is not an MLflow run id")
    return run_id


def code_sha256():
    """sha256 over the code files this run used (the back-test's and the final check's)."""
    h = hashlib.sha256()
    for f in CODE_FILES:
        h.update(f.encode("utf-8"))
        h.update((Path(_src_path()) / f).read_bytes())
    return h.hexdigest()


def start_line(stage, git_sha, run_date, override):
    """Printed first in every stage: the stage, the commit and the code it runs."""
    return (f"stage {stage}; git {git_sha}; code sha256 {code_sha256()}; run date {run_date} (SGT); "
            f"override-incomplete {override or 'none'}")


# ---------------------------------------------------------------- reads
def read_inputs(spark, t, ver, last, run_date, phase):
    """WBGT and rainfall readings with sgt_date up to `last` (completed days) and forecast issues up to `last`, at the
    pinned versions, with their lineage rows (as the back-test job reads them)."""
    within = f"sgt_date <= DATE'{last}' AND sgt_date < DATE'{run_date}'"
    fc_where = f"issue_sgt_date <= DATE'{last}'"
    frames, lineage = {}, []
    for key, cols, where in (("wbgt", BT.WBGT_COLS, within), ("rain", BT.RAIN_COLS, within),
                             ("fc", BT.FC_COLS, fc_where)):
        frames[key] = BT.read(spark, t[key], ver[key], cols, where)
        fp = BT.fingerprint(frames[key], cols)
        lineage.append({"phase": phase, "input": t[key], "type": "streaming table", "filter": where,
                        "pinned": (f"Delta version {ver[key]}" if ver[key] is not None else "no time travel")
                        + f"; rows {fp['rows']:,}; checksum {fp['checksum']}"})
    return frames, lineage


def pull_labels(spark, table, first, last, run_date):
    """The label view's rows with sgt_date first..last (completed days), pulled once, hashed and checked as
    BT.pin_labels does (the view cannot be time-travelled)."""
    src = spark.sql(f"SELECT {', '.join(BT.LABEL_COLS)} FROM {table} "
                    f"WHERE sgt_date BETWEEN DATE'{first}' AND DATE'{last}' AND sgt_date < DATE'{run_date}'")
    pdf = src.toPandas().sort_values(["station_id", "sgt_date"]).reset_index(drop=True)
    csv_bytes = pdf.to_csv(index=False).encode("utf-8")
    pinned = spark.createDataFrame(pdf, schema=src.schema)
    chk = ["count(*) AS n", "sum(unix_seconds(first_valid_ts)) AS f", "sum(unix_seconds(last_valid_ts)) AS l",
           "sum(n_valid) AS v"]
    if tuple(pinned.selectExpr(*chk).first()) != tuple(src.selectExpr(*chk).first()):
        raise SystemExit("the rebuilt label copy differs from the view (did the pipeline update during the run?)")
    return pinned, pdf, csv_bytes


def build_training(spark, t, ver, areas, run_date):
    """The back-test's path for target dates 2025-01-17 to 2026-08-31, as src/jobs/backtest.py main() runs it: scan
    filters to 2026-08-31, station_day_features, the cut-off and completed-day checks, B.backtest_labels and
    B.station_day_rows with their guards, the area mapping over the pinned copies with its orphan check, the window
    audit. Then the §15 count check: the training rows must be the 9,308 station-days and 465 High of item 1."""
    last = B.LAST_BACKTEST_DATE
    src, lineage = read_inputs(spark, t, ver, last, run_date, "training")
    lab_pinned, lab_pdf, lab_csv = BT.pin_labels(spark, t["labels"], last, run_date)
    lineage.append({"phase": "training", "input": t["labels"], "type": "materialized view",
                    "filter": f"sgt_date <= DATE'{last}' AND sgt_date < DATE'{run_date}'",
                    "pinned": f"pulled once; rows {len(lab_pdf):,}; sha256 {hashlib.sha256(lab_csv).hexdigest()}"})
    targets = spark.sql(f"SELECT explode(sequence(DATE'{B.FIRST_TARGET:%Y-%m-%d}', DATE'{last}')) AS target_date")
    feats = station_day_features(src["wbgt"], src["rain"], src["fc"], targets, run_date, CUTOFF_MINUTES).toPandas()
    BT.check_feature_cutoffs(feats)
    assert_completed_days(feats, run_date, ["inputs_max_day"])
    feats["target_date"] = pd.to_datetime(feats.target_date)
    labels = B.backtest_labels(lab_pinned, run_date).toPandas()
    assert_completed_days(labels, run_date, ["target_date"])
    labels["target_date"] = pd.to_datetime(labels.target_date)
    rows = B.station_day_rows(feats, labels)
    amap = (spark.sql(nearest_station_sql("bt_labels_pinned", "bt_dist_pinned", BT.BOUNDARY, CUTOFF_MINUTES,
                                          BT.LOOKBACK, True))
            .where(f"target_date BETWEEN DATE'{B.FIRST_TARGET:%Y-%m-%d}' AND DATE'{last}'")
            .select("target_date", "planning_area", "station_id").toPandas())
    amap["target_date"] = pd.to_datetime(amap.target_date)
    amap41 = amap[amap.planning_area.isin(set(areas.planning_area))]
    orphan = amap41.merge(feats[["station_id", "target_date"]], how="left", indicator=True).query("_merge == 'left_only'")
    if len(orphan):
        raise SystemExit(f"{len(orphan)} area-days whose station has no feature row, e.g. {orphan.head(3).to_dict('records')}")
    audit = BT.window_audit({"labels (pinned)": (lab_pdf, "sgt_date"), "features": (feats, "target_date"),
                             "labels (usable)": (labels, "target_date"), "area mapping": (amap, "target_date"),
                             "station-day rows": (rows, "target_date")}, last)
    n, high = len(rows), int((rows.y == B.HIGH).sum())
    if (n, high) != FC.EXPECTED_TRAIN:
        raise SystemExit(f"training rows: {n:,} station-days with {high:,} High, not the {FC.EXPECTED_TRAIN[0]:,} and "
                         f"{FC.EXPECTED_TRAIN[1]:,} of §15 item 1; stop and ask")
    return {"rows": rows, "labels": labels, "amap41": amap41, "lab_pdf": lab_pdf, "lineage": lineage,
            "audit": audit.assign(phase="training")}


def build_window(spark, t, ver, areas, first, last, run_date, train_lab_pdf, phase):
    """The scoring builder for target dates first..last: 1 Sep to 19 Oct 2026 for the score, 1 Jul to 31 Aug 2026 in
    stage fit. Its own reads (readings and forecast issues up to `last`, labels pulled for first..last),
    station_day_features for the window's targets, then the copies of the back-test's join and area-day construction
    (FC.window_rows, FC.area_map_41); the area mapping runs the view's SQL over the training pull before `first` plus
    this pull. Everything is asserted inside first..last."""
    src, lineage = read_inputs(spark, t, ver, last, run_date, phase)
    win_sdf, win_pdf, win_csv = pull_labels(spark, t["labels"], first, last, run_date)
    lineage.append({"phase": phase, "input": t["labels"], "type": "materialized view",
                    "filter": f"sgt_date BETWEEN DATE'{first}' AND DATE'{last}' AND sgt_date < DATE'{run_date}'",
                    "pinned": f"pulled once; rows {len(win_pdf):,}; sha256 {hashlib.sha256(win_csv).hexdigest()}"})
    before = pd.to_datetime(train_lab_pdf.sgt_date) < pd.Timestamp(first)
    copy = pd.concat([train_lab_pdf[before], win_pdf], ignore_index=True)
    spark.createDataFrame(copy, schema=win_sdf.schema).createOrReplaceTempView(WINDOW_LABELS)
    targets = spark.sql(f"SELECT explode(sequence(DATE'{first}', DATE'{last}')) AS target_date")
    feats = station_day_features(src["wbgt"], src["rain"], src["fc"], targets, run_date, CUTOFF_MINUTES).toPandas()
    BT.check_feature_cutoffs(feats)
    assert_completed_days(feats, run_date, ["inputs_max_day"])
    feats["target_date"] = pd.to_datetime(feats.target_date)
    labels = usable_labels(win_sdf, run_date, last_date=last).toPandas()
    assert_completed_days(labels, run_date, ["target_date"])
    labels["target_date"] = pd.to_datetime(labels.target_date)
    rows = FC.window_rows(feats, labels, first, last)
    keys = feats[["station_id", "target_date"]]
    amap = (spark.sql(nearest_station_sql(WINDOW_LABELS, "bt_dist_pinned", BT.BOUNDARY, CUTOFF_MINUTES, BT.LOOKBACK,
                                          True))
            .where(f"target_date BETWEEN DATE'{first}' AND DATE'{last}'")
            .select("target_date", "planning_area", "station_id").toPandas())
    amap41 = FC.area_map_41(amap, areas.planning_area, keys, first, last)
    audit = FC.window_table({"labels (pulled)": (win_pdf, "sgt_date"), "features": (feats, "target_date"),
                             "labels (usable)": (labels, "target_date"), "area mapping": (amap, "target_date"),
                             "station-day rows": (rows, "target_date")}, first, last)
    no_row = labels.merge(keys, how="left", indicator=True).query("_merge == 'left_only'").drop(columns="_merge")
    missing = sorted(set(feats.loc[feats.forecast_missing, "target_date"]))
    reasons = {}
    if missing:
        gaps = forecast_gaps(src["fc"], spark.createDataFrame([(d.date(),) for d in missing], "target_date DATE"),
                             CUTOFF_MINUTES).toPandas()
        reasons = {pd.Timestamp(d): gap_reason(g) for d, g in gaps.groupby("target_date")}
    return {"rows": rows, "amap41": amap41, "lab_pdf": win_pdf, "lab_csv": win_csv, "lineage": lineage,
            "audit": audit.assign(phase=phase), "no_row": no_row, "gap_reasons": reasons,
            "text_disagree": int((~feats.forecast_missing & ~feats.fc_text_agrees.eq(True)).sum())}


# ---------------------------------------------------------------- report
def _rate(v, lo=None, hi=None):
    if v is None or np.isnan(v):
        return "—"
    return f"{v:.3f} ({lo:.3f} to {hi:.3f})" if lo is not None and not np.isnan(lo) else f"{v:.3f}"


def counts_table(counts, name):
    """One row per operating point and period: "X of Y High days", recall, alerts, precision, alerts per day; with
    Wilson 95% intervals on the station-day sets."""
    station = name.startswith("station")
    ci = " (Wilson 95%)" if station else ""
    rows = []
    for r in counts[counts.set == name].to_dict("records"):
        rows.append({"method": METHOD_NAMES[r["method"]], "operating point": POINT_NAMES[r["point"]],
                     "period": PERIOD_NAMES[r["period"]],
                     "High days caught": f"{BT._num(r['tp'])} of {r['high']:,} High days",
                     f"recall{ci}": _rate(r["recall"], r.get("recall_lo"), r.get("recall_hi")),
                     "alerts": BT._num(r["alerts"]),
                     f"precision{ci}": _rate(r["precision"], r.get("precision_lo"), r.get("precision_hi")),
                     "alerts per day": f"{r['alerts_per_day']:.2f}"})
    return BT.md(pd.DataFrame(rows))


def render_final_report(ctx):
    res, fitted = ctx["results"], ctx["fitted"]
    vb, rd = res["versus_backtest"], res["reading"]
    fin, bt = vb["final"], vb["backtest"]
    L = ["# Final check report", "",
         f"Generated {ctx['finished']:%Y-%m-%d %H:%M} SGT by `src/jobs/final_check.py` (bundle job, stage score). MLflow "
         f"run `{ctx['run_id']}` (role = final_check) in experiment `{ctx['experiment']}`. Git `{ctx['git_sha']}`, code "
         f"sha256 `{ctx['code_sha256']}`, run date {ctx['run_date']} (SGT), cut-off {CUTOFF_MINUTES} min after 00:00 on "
         "the target date. Specification: docs/design/backtest.md §15, decided 22 Oct 2026 before any final-check data "
         "was read. This report states numbers; the reading pre-declared in §15 is applied mechanically.", ""]
    if ctx.get("override"):
        L += [f"This run was allowed past the incomplete scored run `{ctx['override']}` with --override-incomplete, on "
              "the user's word; that run's status and tags are in the experiment.", ""]
    L += ["Packages this run used: " + ", ".join(f"{k} {v}" for k, v in ctx["packages"].items()) + ".", ""]
    verdict = ("yes. The final check agrees with the back-test." if rd["agrees"] else
               "no. The final check does not agree with the back-test; the back-test stays the main evidence.")
    L += ["## Pre-declared reading (§15)", "",
          "The final check agrees with the back-test if the model's area-day PR-AUC is above persistence's (continuous "
          "score).", "",
          f"Area-day PR-AUC over 1 Sep to 19 Oct 2026: model {_rate(rd['model'])}, persistence (continuous) "
          f"{_rate(rd['persistence_continuous'])}. Model above persistence: {verdict}", ""]
    L += ["## The cut-off beside the back-test (§15 item 5)", "",
          f"Area-days, alert when P(High) ≥ {FC.FINAL_CUTOFF!r}:", ""]
    for period in ("all", "2026-09", "2026-10"):
        f = fin[period]
        L += [f"- {PERIOD_NAMES[period]}: {BT._num(f['alerts'])} alerts over {f['days']} days, {f['alerts_per_day']:.2f} "
              f"a day; recall {_rate(f['recall'])}, {BT._num(f['tp'])} of {f['high']:,} High area-days."]
    L += [f"- Back-test (Jul 2025 to Aug 2026, §14): {bt['alerts']:,} alerts over {bt['days']} days, "
          f"{bt['alerts_per_day']:.2f} a day; recall {bt['recall']:.3f}, {bt['tp']} of {bt['high']} High area-days.", ""]
    L += ["## Settings", "",
          f"- Model: LightGBM multiclass on the 11 features ({', '.join(FEATURES)}), num_leaves {FC.FINAL_CONFIG[0]}, "
          f"{FC.FINAL_CONFIG[1]} rounds, the fixed parameters of §5.2 (`{json.dumps(B.LGB_FIXED)}`); model sha256 "
          f"`{ctx['model_sha256']}`.",
          f"- Trained once on target dates {B.FIRST_TARGET:%Y-%m-%d} to {B.LAST_BACKTEST_DATE}: {fitted.train_rows:,} "
          f"station-days, {fitted.train_high:,} High (§15 item 1: {FC.EXPECTED_TRAIN[0]:,} and {FC.EXPECTED_TRAIN[1]:,}); "
          "no refit.",
          "- Fitted on the training rows only: forecast fill by calendar month "
          + "; ".join(f"{m}: {v[0]:.1f} °C, {v[1]}" for m, v in sorted(fitted.fill["by_month"].items()))
          + f"; all training dates: {fitted.fill['overall'][0]:.1f} °C, {fitted.fill['overall'][1]}. Text categories: "
          f"{len(fitted.categories)}. NEA rule θ = {fitted.theta} °C (training F1 {fitted.theta_f1:.3f}). Same month "
          "last year from the labels of Sep and Oct 2025.",
          "- Latest target date each fitted object used: "
          + "; ".join(f"{k} {pd.Timestamp(v):%Y-%m-%d}" for k, v in fitted.used.items()) + ".",
          f"- Scored: target dates {FC.FINAL_FIRST} to {FC.FINAL_LAST}, 49 days (Sep 30, Oct 19).", ""]
    L += ["## How to read the numbers", "",
          "- Wilson 95% intervals are given on station-day counts only, and they are too narrow: consecutive days are "
          "not independent.",
          "- Area-day counts have no intervals, since area-days share stations.",
          "- No difference between the model and a baseline is claimed from the final check alone: the 49 days make only "
          "7 weekly blocks, too few for the block bootstrap.",
          "- The baselines have no P(High), so \"at the cut-off\" is the model's alone. Continuous scores are also shown "
          "at persistence's alert load (the whole window's load, split by month); the binary rules at their own rule. A "
          "tie at the load is split in expectation, so some counts are not whole numbers.", ""]
    lineage = pd.DataFrame(ctx["lineage_rows"])[["phase", "input", "type", "pinned", "filter"]]
    L += ["## Inputs (pinned)", ""] + BT.md(lineage) + [""]
    v = ctx["view_check"]
    L += [f"View `{v['view']}`: definition equals `nearest_station_sql(..., island_rule=True)`: "
          f"{v['equals_nearest_station_sql']}; the job ran that SQL on the pinned copies.", ""]
    L += ["### Window audit", ""] + BT.md(ctx["audit"][["phase", "frame", "column", "rows", "first", "last"]]) + [""]
    L += ["## Rows", "",
          f"Scoring station-days (reporting station, usable label): {len(ctx['predictions']):,}. Usable station-days "
          f"without a feature row: {len(ctx['no_row']):,}. Area-days over the 41 areas: {len(ctx['area_days']):,}; "
          f"dropped because their station-day is not usable: {ctx['area_dropped']:,}. Rows whose forecast text was not "
          f"seen in training (scored as missing): {ctx['unseen_text_rows']:,}. Selected forecasts whose text disagrees "
          f"with the corrected validity: {ctx['text_disagree']:,}.", ""]
    L += ["### Forecasts filled in the scoring window (rule: §5.1 step 2), with why each was missing", ""]
    filled = ctx["filled"]
    if len(filled):
        filled = filled.assign(reason=[ctx["gap_reasons"].get(pd.Timestamp(d), "—") for d in filled.target_date])
        L += BT.md(filled[["target_date", "fc_temp_high", "fc_text", "source", "reason"]])
    else:
        L += ["None."]
    L += [""]
    for name, s in res["sets"].items():
        L += [f"## {SET_TITLES[name]}", "",
              f"Rows {s['rows']:,}; High {s['high']:,} ({s['high'] / max(s['rows'], 1):.1%}, the no-skill PR-AUC); "
              f"persistence alerts K = {s['K']:,}.", ""]
        L += BT.md(pd.DataFrame([{"score": METHOD_NAMES[m], "PR-AUC": _rate(a)} for m, a in s["pr_auc"].items()]))
        L += [""] + counts_table(res["counts"], name) + [""]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- MLflow content
KEY = re.compile(r"^[/\w.\- ]+$")


def run_metrics(results):
    m = {}
    for name, s in results["sets"].items():
        m.update({f"{name}/rows": s["rows"], f"{name}/high": s["high"], f"{name}/persistence_alerts_K": s["K"]})
        m.update({f"{name}/{method}/pr_auc": v for method, v in s["pr_auc"].items()})
    for r in results["counts"].to_dict("records"):
        base = f"{r['set']}/{r['period']}/{r['method']}_at_{r['point']}"
        for k in ("high", "alerts", "tp", "recall", "precision", "alerts_per_day", "recall_lo", "recall_hi",
                  "precision_lo", "precision_hi"):
            if k in r:
                m[f"{base}/{k}"] = r[k]
    m["area41/reading_model_above_persistence"] = float(results["reading"]["agrees"])
    return {k: float(v) for k, v in m.items() if v is not None and np.isfinite(float(v))}


def run_params(ctx):
    f = ctx["fitted"]
    p = {"git_sha": ctx["git_sha"], "code_sha256": ctx["code_sha256"], "run_date": str(ctx["run_date"]),
         "stage": "score", "cutoff_minutes": CUTOFF_MINUTES, "high_cutoff": repr(FC.FINAL_CUTOFF),
         "train_window": f"{B.FIRST_TARGET:%Y-%m-%d}..{B.LAST_BACKTEST_DATE}",
         "score_window": f"{FC.FINAL_FIRST}..{FC.FINAL_LAST}", "num_leaves": FC.FINAL_CONFIG[0],
         "rounds": FC.FINAL_CONFIG[1], "lgb_fixed": json.dumps(B.LGB_FIXED), "features": ",".join(FEATURES),
         "panel": ",".join(ORIGINAL_8), "train_rows": f.train_rows, "train_high": f.train_high, "nea_theta": f.theta,
         "nea_theta_f1": f.theta_f1, "text_categories": len(f.categories),
         "fill_by_month": json.dumps({str(k): v for k, v in sorted(f.fill["by_month"].items())}),
         "fill_overall": json.dumps(f.fill["overall"]), "model_sha256": ctx["model_sha256"],
         "experiment": ctx["experiment"], "view_definition_ok": ctx["view_check"]["equals_nearest_station_sql"]}
    p.update({f"pkg.{k}": v for k, v in ctx["packages"].items()})
    p.update({f"input.{r['phase']}.{r['input']}": f"{r['type']}; {r['pinned']}; {r['filter']}"[:500]
              for r in ctx["lineage_rows"]})
    return p


def write_artifacts(ctx, out):
    ctx["predictions"].to_parquet(out / "predictions_station_days.parquet", index=False)
    ctx["area_days"].to_parquet(out / "predictions_area_days.parquet", index=False)
    ctx["results"]["counts"].to_csv(out / "counts.csv", index=False)
    pd.concat([ctx["fitted"].filled.assign(split="train"), ctx["filled"].assign(split="score")],
              ignore_index=True).to_csv(out / "forecast_fills.csv", index=False)
    ctx["no_row"].to_csv(out / "usable_station_days_without_feature_row.csv", index=False)
    ctx["audit"].to_csv(out / "window_audit.csv", index=False)
    (out / "labels_pulled_scoring_window.csv").write_bytes(ctx["lab_csv"])
    (out / "final_model.txt").write_text(ctx["fitted"].booster.model_to_string(), encoding="utf-8")
    (out / "lineage.json").write_text(json.dumps({k: ctx[k] for k in ("lineage_rows", "view_check", "git_sha",
                                                                      "code_sha256", "packages", "stages_seconds")},
                                                 default=str, indent=1), encoding="utf-8")


def final_context(result, train, window, meta):
    """Everything the report and the run need: the result of run_final_check, the training and scoring builders'
    outputs, and the run's metadata."""
    audit = pd.concat([train["audit"], window["audit"],
                       FC.window_table({"predictions": (result["predictions"], "target_date"),
                                        "area-days": (result["area_days"], "target_date")},
                                       FC.FINAL_FIRST, FC.FINAL_LAST).assign(phase="scoring")], ignore_index=True)
    return {**meta, **result, "lineage_rows": train["lineage"] + window["lineage"], "audit": audit,
            "no_row": window["no_row"], "gap_reasons": window["gap_reasons"], "text_disagree": window["text_disagree"],
            "lab_csv": window["lab_csv"],
            "model_sha256": hashlib.sha256(result["fitted"].booster.model_to_string().encode("utf-8")).hexdigest()}


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="coolcheck")
    ap.add_argument("--src")
    ap.add_argument("--experiment-id", required=True)
    ap.add_argument("--git-sha", required=True)
    ap.add_argument("--stage", choices=STAGES, required=True)
    ap.add_argument("--override-incomplete", default="",
                    help="run id of a scored final_check run whose record is not whole; a rerun past it, on the user's word")
    a = ap.parse_args()
    check_git_sha(a.git_sha)
    override = check_override(a.override_incomplete)
    started = datetime.now(SGT)
    run_date = started.date()
    check_run_date(run_date)
    print(start_line(a.stage, a.git_sha, run_date, override), flush=True)

    import mlflow
    from mlflow import MlflowClient

    mlflow.set_tracking_uri("databricks")
    client = MlflowClient()
    lock = FL.MlflowLock(client, a.experiment_id, override=override)
    print("lock check:\n" + "\n".join(lock.check()), flush=True)
    if a.stage == "lock":
        print("stage lock: the lock query sees the back-test's model run and no scored final_check run; nothing else was "
              "read")
        return

    from databricks.sdk import WorkspaceClient
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    ws = WorkspaceClient()
    spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    packages = BT.package_versions()
    print("packages:", json.dumps(packages), flush=True)
    stages = {}

    def mark(stage):
        stages[stage] = round((datetime.now(SGT) - started).total_seconds(), 1)
        print(f"[{stages[stage]:7.1f} s] {stage}", flush=True)

    cat = a.catalog
    t = {"wbgt": f"{cat}.silver.wbgt_readings", "rain": f"{cat}.silver.rainfall_readings",
         "fc": f"{cat}.silver.forecast_issues", "labels": f"{cat}.silver.station_daily_label",
         "dist": f"{cat}.silver.area_station_distance", "areas": f"{cat}.silver.area_exposure",
         "view": f"{cat}.gold.area_nearest_station_daily"}
    if not spark.catalog.tableExists(t["areas"]):
        raise SystemExit(f"{t['areas']} does not exist")
    ver = {k: BT.pin_version(spark, t[k]) for k in ("wbgt", "rain", "fc", "dist", "areas")}
    BT.read(spark, t["dist"], ver["dist"], ["*"], "TRUE").createOrReplaceTempView("bt_dist_pinned")
    areas = BT.read(spark, t["areas"], ver["areas"], ["planning_area", "aged_65_plus"], "aged_65_plus > 0").toPandas()
    if len(areas) != 41:
        raise SystemExit(f"{len(areas)} areas with residents aged 65+, expected 41")
    view_check = BT.check_view(ws, t["view"], t["labels"], t["dist"], CUTOFF_MINUTES)
    static = [{"phase": "both", "input": t["dist"], "type": "Delta table", "filter": "boundary mp2025 in the SQL",
               "pinned": f"Delta version {ver['dist']}"},
              {"phase": "both", "input": t["areas"], "type": "Delta table", "filter": "aged_65_plus > 0",
               "pinned": f"Delta version {ver['areas']}; {len(areas)} areas"},
              {"phase": "both", "input": t["view"], "type": "view", "filter": "definition only",
               "pinned": f"definition sha256 {view_check['definition_sha256']}"}]
    mark("static inputs pinned")
    state = {}

    def load_training():
        state["train"] = build_training(spark, t, ver, areas, run_date)
        state["train"]["lineage"] = static + state["train"]["lineage"]
        mark(f"training rows: {len(state['train']['rows']):,} station-days, "
             f"{int((state['train']['rows'].y == B.HIGH).sum()):,} High")
        return state["train"]["rows"], state["train"]["labels"]

    if a.stage == "fit":
        rows, labels = load_training()
        fitted = FC.fit_final(rows, labels)
        mark("fitted")
        model_sha = hashlib.sha256(fitted.booster.model_to_string().encode("utf-8")).hexdigest()
        print(f"fit: {fitted.train_rows:,} station-days, {fitted.train_high:,} High; config {FC.FINAL_CONFIG}; model "
              f"sha256 {model_sha}; NEA θ {fitted.theta} (F1 {fitted.theta_f1:.3f}); {len(fitted.categories)} text "
              f"categories; fill by month {fitted.fill['by_month']}; overall {fitted.fill['overall']}; latest target "
              f"date used: " + "; ".join(f"{k} {pd.Timestamp(v):%Y-%m-%d}" for k, v in fitted.used.items()), flush=True)
        first, last = FC.EQUIV_FIRST, FC.EQUIV_LAST
        w = build_window(spark, t, ver, areas, first, last, run_date, state["train"]["lab_pdf"], "equivalence")
        mark("scoring builder on 1 Jul to 31 Aug 2026")
        # the back-test path for the same dates: its rows, and its area-days as src/jobs/backtest.py builds them
        tr = state["train"]
        bt_rows = tr["rows"][(tr["rows"].target_date >= pd.Timestamp(first))
                             & (tr["rows"].target_date <= pd.Timestamp(last))]
        test41 = tr["amap41"][(tr["amap41"].target_date >= pd.Timestamp(first))
                              & (tr["amap41"].target_date <= pd.Timestamp(last))]
        bt_area = test41.merge(bt_rows, on=["station_id", "target_date"], how="inner")
        summary = FC.check_builder_equivalence(bt_rows, bt_area, w["rows"], FC.area_days(w["amap41"], w["rows"]))
        print(f"equivalence on {first} to {last}: the builder's rows equal the back-test path's: {json.dumps(summary)}")
        print("largest float difference (tolerance 1e-9): "
              + "; ".join(f"{k} {v['max_abs_diff']!r}" for k, v in summary.items()))
        print("stage fit done: nothing was read after 2026-08-31 and nothing was written")
        print("stages (s):", json.dumps(stages))
        return

    # ---- score
    def load_scoring():
        state["window"] = build_window(spark, t, ver, areas, FC.FINAL_FIRST, FC.FINAL_LAST, run_date,
                                       state["train"]["lab_pdf"], "scoring")
        mark("scoring rows built")
        return state["window"]["rows"], state["window"]["amap41"]

    def record(result):
        # scoring has completed: the lock is written first (write_final_run creates the run tagged scored), then this
        def build(rid):
            mark(f"lock written: final_check run {rid} created, tagged {FL.SCORED_TAG} = true")
            meta = {"git_sha": a.git_sha, "code_sha256": code_sha256(), "run_date": run_date, "packages": packages,
                    "view_check": view_check, "experiment": client.get_experiment(a.experiment_id).name,
                    "finished": datetime.now(SGT), "stages_seconds": stages, "override": override}
            ctx = final_context(result, state["train"], state["window"], meta)
            out = Path(tempfile.mkdtemp(prefix="final_check_"))
            write_artifacts(ctx, out)
            return render_final_report({**ctx, "run_id": rid}), run_params(ctx), run_metrics(ctx["results"]), out

        return FL.write_final_run(client, a.experiment_id, {"git_sha": a.git_sha}, build, override=override)

    run_id, report, sha = FC.run_final_check(lock.locks, load_training, load_scoring, record)
    mark(f"record complete: final_check run {run_id} has {FL.COMPLETE_TAG} = true")
    print(f"MLflow final_check run: {ws.config.host.rstrip('/')}/ml/experiments/{a.experiment_id}/runs/{run_id}")
    print(f"report.md sha256 {sha}")
    print("stages (s):", json.dumps(stages))
    print("=== REPORT START ===")
    print(report)
    print("=== REPORT END ===", flush=True)


if __name__ == "__main__":
    main()
