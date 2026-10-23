"""The live model and the nightly heat forecast (Guide §A11 decision 8(e)): the final check's configuration refit once
on all completed target dates from 2025-01-17 to 2026-10-22, registered in Unity Catalog as <catalog>.ml.heat_model
with the alias champion, and the rows the nightly job writes to gold.heat_forecast.

The refit keeps the final check's settings (the 11 features, (7, 150), the fixed parameters of §5.2, seed 42) and its
rules (the forecast fill and the text categories from the training rows). Nothing is re-derived: the High cut-off stays
0.10975585695894975 and is only recorded. Predictions for dates the model trained on are in-sample and are never
reported as performance. The registered model itself is coolcheck/heat_model.py (self-contained).
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

import pandas as pd

from coolcheck.backtest import FIRST_TARGET, HIGH, LGB_FIXED, apply_forecast_fill, encode, fit_forecast_fill, fit_lgb
from coolcheck.features import CATEGORICAL, FEATURES, SEASONS
from coolcheck.final_check import FINAL_CONFIG, FINAL_CUTOFF, assert_in_window

LIVE_FIRST, LIVE_LAST = FIRST_TARGET.date(), date(2026, 10, 22)  # completed target dates the refit trains on
DQ_FIRST, DQ_LAST = date(2026, 10, 20), date(2026, 10, 22)        # the days after the final check's window
DQ_FEEDS = ("wbgt", "rainfall", "forecast")
FOLD_RATES = ((150, 5388), (390, 7682))  # the back-test folds' lowest and highest training High rates (run c509ab9a)
FINAL_TRAIN = (9308, 465)                # the final check's model (§15 item 1)
ROLE = "live_model"
N_AREAS = 41
CUTOFF_MINUTES = 15
SGT = timezone(timedelta(hours=8))
INPUT_COLUMNS = [*FEATURES, "forecast_missing", "target_date"]  # the registered model's input
PROBS = ["p_low", "p_moderate", "p_high"]
FORECAST_COLUMNS = (("target_date", "DATE"), ("planning_area", "STRING"), ("station_id", "STRING"), ("p_low", "DOUBLE"),
                    ("p_moderate", "DOUBLE"), ("p_high", "DOUBLE"), ("model_version", "STRING"), ("run_id", "STRING"),
                    ("cutoff_ts", "TIMESTAMP"), ("scored_at", "TIMESTAMP"), ("forecast_missing", "BOOLEAN"))
FORECAST_SCHEMA = ", ".join(f"{c} {t}" for c, t in FORECAST_COLUMNS)
FORECAST_COMMENT = ("Next-day heat forecast per planning area (the 41 with residents aged 65+): class probabilities from "
                    "the champion model for the nearest reporting station of each area; one row per area per target "
                    "date, written by the nightly job (window B) with MERGE on (target_date, planning_area). NULL "
                    "probabilities: the station had no feature row, so the area is flagged, not scored.")


def tables(catalog):
    c = catalog
    return {"wbgt": f"{c}.silver.wbgt_readings", "rain": f"{c}.silver.rainfall_readings",
            "fc": f"{c}.silver.forecast_issues", "labels": f"{c}.silver.station_daily_label",
            "dist": f"{c}.silver.area_station_distance", "areas": f"{c}.silver.area_exposure",
            "dq": f"{c}.silver.dq_day", "view": f"{c}.gold.area_nearest_station_daily",
            "forecast": f"{c}.gold.heat_forecast"}


# ---------------------------------------------------------------- the refit
@dataclass
class LiveFit:
    booster: object
    fill: dict
    categories: list
    filled: pd.DataFrame  # training dates whose forecast was filled
    used: dict            # the latest target date each fitted object used
    train_rows: int
    train_high: int


def feeds_by_day(dq, first=DQ_FIRST, last=DQ_LAST):
    """silver.dq_day rows (sgt_date, feed, status) for first..last. Returns (lines to print, missing (date, feed)): a
    feed is missing on a day when it has no row or the status no_data; a short day is fine, as in the final check."""
    got = {(pd.Timestamp(r.sgt_date).date(), r.feed): r.status for r in dq.itertuples()}
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    lines = [f"  {d} {f}: {got.get((d, f), 'no row')}" for d in days for f in DQ_FEEDS]
    missing = [(str(d), f) for d in days for f in DQ_FEEDS if got.get((d, f)) in (None, "no_data")]
    return lines, missing


def check_training_rate(rows):
    """The training High rate beside the final check's model and the back-test folds' range; outside the range it
    stops before anything is logged or registered (decision 8(e))."""
    n, high = len(rows), int((rows.y == HIGH).sum())
    (lo_k, lo_n), (hi_k, hi_n) = FOLD_RATES
    rate = high / n if n else float("nan")
    line = (f"training rows {n:,}, High {high:,}, High rate {rate:.3%}; final check's model {FINAL_TRAIN[0]:,} rows, "
            f"{FINAL_TRAIN[1]:,} High ({FINAL_TRAIN[1] / FINAL_TRAIN[0]:.3%}); back-test folds {lo_k / lo_n:.3%} "
            f"({lo_k} of {lo_n:,}) to {hi_k / hi_n:.3%} ({hi_k} of {hi_n:,})")
    if not lo_k / lo_n <= rate <= hi_k / hi_n:
        raise AssertionError(line + ": outside the folds' range, so nothing is logged or registered (decision 8(e))")
    return {"rows": n, "high": high, "rate": rate, "line": line}


def fit_live(rows, first=LIVE_FIRST, last=LIVE_LAST):
    """One model on the training rows (the scoring builder's station-day rows for first..last) with FINAL_CONFIG and
    the fixed parameters of §5.2; the forecast fill and the text categories from the training rows (§5.1). As
    final_check.fit_final, without its 31 Aug guard and without the NEA rule (no baseline here)."""
    rows = rows.assign(target_date=pd.to_datetime(rows.target_date))
    assert_in_window(rows, first, last, "live training rows")
    fill = fit_forecast_fill(rows)
    tr, filled = apply_forecast_fill(rows, fill)
    cats = sorted(tr.fc_text.dropna().unique())
    booster = fit_lgb(encode(tr, cats), tr.y.to_numpy(), *FINAL_CONFIG)
    last_used = tr.target_date.max()
    used = {"forecast fill": fill["max_date"], "text categories": last_used, "LightGBM model": last_used}
    late = {k: v for k, v in used.items() if pd.Timestamp(v) > pd.Timestamp(last)}
    if late:
        raise AssertionError(f"fitted objects used target dates after {last}: {late}")
    return LiveFit(booster, fill, cats, filled, used, len(tr), int((tr.y == HIGH).sum()))


def model_input(frame):
    """The registered model's input: the 11 features, forecast_missing and target_date, with the dtypes of its
    signature (numeric features as float, the two categoricals as text with None for missing)."""
    x = frame[INPUT_COLUMNS].copy().reset_index(drop=True)
    for c in FEATURES:
        if c not in CATEGORICAL:
            x[c] = pd.to_numeric(x[c], errors="raise").astype(float)
    for c in CATEGORICAL:
        x[c] = x[c].astype(object).where(x[c].notna(), None)
    x["forecast_missing"] = x["forecast_missing"].astype(bool)
    x["target_date"] = pd.to_datetime(x["target_date"])
    return x


def predict_proba(fit, frame):
    """The probabilities the back-test functions give (fill, encode, booster); the registered model must equal it."""
    filled, _ = apply_forecast_fill(frame, fit.fill)
    p = fit.booster.predict(encode(filled, fit.categories))
    return pd.DataFrame(p, columns=PROBS, index=frame.index)


def model_spec(fit):
    """spec.json of the registered model: what coolcheck/heat_model.py needs to prepare the input, and the settings."""
    return {"features": list(FEATURES), "categorical": list(CATEGORICAL), "text_categories": list(fit.categories),
            "seasons": list(SEASONS),
            "fill_by_month": {str(int(m)): [float(t), str(x)] for m, (t, x) in sorted(fit.fill["by_month"].items())},
            "fill_overall": [float(fit.fill["overall"][0]), str(fit.fill["overall"][1])],
            "num_leaves": FINAL_CONFIG[0], "rounds": FINAL_CONFIG[1], "lgb_fixed": LGB_FIXED,
            "high_cutoff": FINAL_CUTOFF, "training_window": [str(LIVE_FIRST), str(LIVE_LAST)],
            "train_rows": fit.train_rows, "train_high": fit.train_high}


# ---------------------------------------------------------------- the nightly forecast
def target_date_of(arg, now):
    """The date scored: --target-date when given (a backfill), else the run date in SGT, from the wall clock at UTC+08:00
    (not the Spark session). A date after today, or before the first target date, is refused."""
    today = now.astimezone(SGT).date()
    t = date.fromisoformat(arg) if arg else today
    if t > today:
        raise ValueError(f"target date {t} is after today ({today}, SGT)")
    if t < LIVE_FIRST:
        raise ValueError(f"target date {t} is before the first target date {LIVE_FIRST}")
    return t


def cutoff_ts(t):
    """The information cut-off of target date t: 00:15 SGT on t."""
    return datetime.combine(t, time(0, CUTOFF_MINUTES), tzinfo=SGT)


def area_map_live(amap, areas, feature_stations, t):
    """The view's rows for target date t restricted to the 41 areas, as final_check.area_map_41 does, with one change:
    an area whose station has no feature row for t (only a 00:00 to 00:15 reading, note §1) is kept and flagged, not
    scored, and not an error. Exactly one row per area. Returns (rows, flagged areas)."""
    amap = amap.assign(target_date=pd.to_datetime(amap.target_date))
    if not (amap.target_date == pd.Timestamp(t)).all():
        raise AssertionError(f"area mapping: a row for a date other than {t}")
    areas = set(areas)
    m = amap[amap.planning_area.isin(areas)].reset_index(drop=True)
    if m.planning_area.duplicated().any():
        raise AssertionError(f"area mapping: more than one row for {sorted(m.planning_area[m.planning_area.duplicated()])}")
    missing = sorted(areas - set(m.planning_area))
    if missing:
        raise AssertionError(f"area mapping: no row on {t} for {len(missing)} area(s), e.g. {missing[:3]}")
    flagged = sorted(m.loc[~m.station_id.isin(set(feature_stations)), "planning_area"])
    return m, flagged


def forecast_rows(amap41, preds, forecast_missing, t, model_version, run_id, scored_at):
    """gold.heat_forecast's rows for target date t, in its column order, one per area. preds: station_id and the three
    probabilities, one row per station with a feature row; an area whose station has none keeps NULL probabilities."""
    rows = amap41[["planning_area", "station_id"]].merge(preds[["station_id", *PROBS]], on="station_id", how="left",
                                                         validate="many_to_one")
    for p in PROBS:
        rows[p] = rows[p].astype(object).where(rows[p].notna(), None)
    rows = rows.assign(target_date=t, model_version=str(model_version), run_id=str(run_id), cutoff_ts=cutoff_ts(t),
                       scored_at=scored_at, forecast_missing=bool(forecast_missing))
    return rows[[c for c, _ in FORECAST_COLUMNS]]


def create_table_sql(table):
    return f"CREATE TABLE IF NOT EXISTS {table} ({FORECAST_SCHEMA}) COMMENT '{FORECAST_COMMENT}'"


def merge_sql(table, source):
    """A rerun for the same target date replaces its rows rather than adding to them."""
    return (f"MERGE INTO {table} AS t USING {source} AS s "
            "ON t.target_date = s.target_date AND t.planning_area = s.planning_area "
            "WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *")


def read_back_sql(table, t):
    return (f"SELECT count(*) AS n_rows, count(DISTINCT planning_area) AS n_areas, count(p_high) AS n_scored, "
            f"count_if(isnan(p_low) OR isnan(p_moderate) OR isnan(p_high)) AS n_nan, "
            f"max(abs(p_low + p_moderate + p_high - 1)) AS max_sum_gap, "
            f"count(DISTINCT model_version) AS n_versions, min(model_version) AS model_version, "
            f"count(DISTINCT run_id) AS n_run_ids, min(run_id) AS run_id, min(cutoff_ts) AS cutoff_ts, "
            f"max(scored_at) AS scored_at, count_if(forecast_missing) AS n_forecast_missing "
            f"FROM {table} WHERE target_date = DATE'{t}'")


def check_read_back(back, n_scored, model_version, run_id):
    """The rows read back for the target date: 41 areas, one row each, the expected probabilities and provenance."""
    problems = []
    if back["n_rows"] != N_AREAS or back["n_areas"] != N_AREAS:
        problems.append(f"{back['n_rows']} rows for {back['n_areas']} areas, not {N_AREAS}")
    if back["n_scored"] != n_scored or back["n_nan"]:
        problems.append(f"{back['n_scored']} scored rows ({back['n_nan']} NaN), expected {n_scored}")
    if back["max_sum_gap"] is not None and back["max_sum_gap"] > 1e-9:
        problems.append(f"probabilities do not sum to 1 (largest gap {back['max_sum_gap']})")
    if (back["n_versions"], back["model_version"], back["n_run_ids"], back["run_id"]) != (1, str(model_version), 1,
                                                                                            str(run_id)):
        problems.append(f"provenance: {back['n_versions']} version(s) {back['model_version']}, {back['n_run_ids']} "
                        f"run id(s) {back['run_id']}")
    if problems:
        raise AssertionError("read-back of gold.heat_forecast: " + "; ".join(problems))
