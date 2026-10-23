"""The final check (docs/design/backtest.md §15): one LightGBM model fitted on target dates 2025-01-17 to 2026-08-31
with the back-test's settings and guards, then scored once on 1 Sep to 19 Oct 2026, with no refit.

run_final_check fixes the order: the lock first (refuse if a scored final_check run exists), then the training rows and
the fit, and only then the scoring rows, which go to predict and the evaluation, never to a fit. Once scoring has
completed, record writes the lock first (coolcheck.final_lock: the final_check run, tagged scored when it is created)
and then the record. The training rows come through the back-test's own path (backtest_labels, station_day_rows) with
its guards; HOLDOUT_START and those guards are unchanged. The scoring rows use copies of the back-test's join and
area-day construction (window_rows, area_map_41, area_days), because station_day_rows stops any date after 2026-08-31;
they are asserted inside the scoring window, and stage fit checks the copies against the back-test path on 1 Jul to
31 Aug 2026 (check_builder_equivalence).

Evaluation (§15 items 2, 3 and 5): no bootstrap (49 days make only 7 weekly blocks); PR-AUC, recall and precision with
the functions behind the back-test report (metrics.evaluate, load_weights, at_load); counts for Sep and Oct
separately; Wilson 95% intervals on the station-day counts only.
"""
import math
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from coolcheck.backtest import (FIRST_TARGET, HIGH, HOLDOUT_START, KEEP, LAST_BACKTEST_DATE, apply_forecast_fill,
                                assert_before_holdout, assert_fitted_before, encode, fit_forecast_fill, fit_lgb,
                                fit_nea_threshold, same_month_last_year)
from coolcheck.features import LATE_STARTERS, ORIGINAL_8
from coolcheck.final_lock import refuse_if_scored
from coolcheck.metrics import at_load, evaluate, load_weights

FINAL_FIRST, FINAL_LAST = HOLDOUT_START, date(2026, 10, 19)  # labels from completed days, so the run is from 20 Oct
EQUIV_FIRST, EQUIV_LAST = date(2026, 7, 1), LAST_BACKTEST_DATE  # stage fit: the builder against the back-test path
FINAL_CUTOFF = 0.10975585695894975  # §14: an alert when P(High) is at or above it
FINAL_CONFIG = (7, 150)             # (num_leaves, rounds), chosen on all 14 folds (§5.2)
EXPECTED_TRAIN = (9308, 465)        # station-days and High (§15 item 1)
BACKTEST_AT_CUTOFF = {"alerts": 1180, "tp": 355, "high": 710, "days": 427}  # §14: area-days over the 41 areas
FLOAT_ATOL = 1e-9                   # equivalence: Spark may add the same values in another order
WILSON_Z = 1.959963984540054
NO_RESAMPLES = np.empty((0, 1), dtype=int)
SCORES = {"model": "p_high", "persistence_continuous": "persist_score", "nea_rule": "nea_score",
          "same_month_last_year": "same_month_score"}
POINTS = (("model", "cutoff"), ("model", "persistence_load"), ("persistence_binary", "own_rule"),
          ("persistence_continuous", "persistence_load"), ("nea_rule", "theta"), ("nea_rule", "persistence_load"),
          ("same_month_last_year", "persistence_load"))
PERIODS = (("all", FINAL_FIRST, FINAL_LAST), ("2026-09", date(2026, 9, 1), date(2026, 9, 30)),
           ("2026-10", date(2026, 10, 1), FINAL_LAST))
AREA_KEYS, STATION_KEYS = ["planning_area", "target_date"], ["station_id", "target_date"]


def assert_in_window(frame, first, last, what, col="target_date"):
    """Fail if any date of the frame lies outside first..last (both included)."""
    d = pd.to_datetime(frame[col])
    out = (d < pd.Timestamp(first)) | (d > pd.Timestamp(last))
    if out.any():
        raise AssertionError(f"{what}: {int(out.sum())} row(s) outside {first} to {last} (e.g. "
                             f"{d[out].iloc[0]:%Y-%m-%d})")


def window_table(frames, first, last):
    """The window audit of frames from a window after the back-test's: rows, first and last date of each, asserted
    inside first..last. frames: {name: (frame, date column)}."""
    rows = []
    for name, (df, col) in frames.items():
        assert_in_window(df, first, last, name, col)
        d = pd.to_datetime(df[col])
        rows.append({"frame": name, "column": col, "rows": len(df), "first": d.min(), "last": d.max()})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- the fit (§15 item 1, item 4 (a))
@dataclass
class Fitted:
    booster: object
    fill: dict
    categories: list
    theta: float
    theta_f1: float
    labels: pd.DataFrame     # training labels, for same month last year (Sep and Oct 2025)
    filled: pd.DataFrame     # training dates whose forecast was filled
    used: dict               # the latest target date each fitted object used
    train_rows: int
    train_high: int


def fit_final(rows, labels):
    """One model on all training rows (station_day_rows over target dates 2025-01-17 to 2026-08-31) with
    FINAL_CONFIG and the fixed parameters of §5.2; the forecast fill, the text categories and the NEA rule's threshold
    from the training rows (§5.1, §5.3). Every fitted object records the latest target date it used, asserted on or
    before 2026-08-31. labels: backtest_labels as pandas."""
    rows, labels = rows.copy(), labels.copy()
    labels["target_date"] = pd.to_datetime(labels["target_date"])
    assert_before_holdout(rows, "final-check training rows")
    assert_before_holdout(labels, "final-check training labels")
    if len(rows) and rows.target_date.min() < FIRST_TARGET:
        raise AssertionError(f"final-check training rows: a target date before {FIRST_TARGET:%Y-%m-%d}")
    fill = fit_forecast_fill(rows)
    tr, filled = apply_forecast_fill(rows, fill)
    cats = sorted(tr.fc_text.dropna().unique())
    booster = fit_lgb(encode(tr, cats), tr.y.to_numpy(), *FINAL_CONFIG)
    theta, theta_f1 = fit_nea_threshold(tr)
    last = tr.target_date.max()
    used = {"forecast fill": fill["max_date"], "text categories": last, "LightGBM model": last,
            "NEA rule threshold": last, "same month last year (labels)": labels.target_date.max()}
    for what, d in used.items():
        assert_fitted_before(d, FINAL_FIRST, what)
    return Fitted(booster, fill, cats, theta, theta_f1, labels, filled, used, len(tr), int((tr.y == HIGH).sum()))


# ---------------------------------------------------------------- the scoring rows (copies of the back-test's)
def window_rows(features, labels, first, last):
    """Copy of backtest.station_day_rows for a window after the back-test's: the same inner one-to-one join on
    (station_id, target_date) keeping the label day's High count as label_n_high, asserted inside first..last."""
    f, lab = features.copy(), labels.copy()
    for d in (f, lab):
        d["target_date"] = pd.to_datetime(d["target_date"])
    lab = lab[["station_id", "target_date", "y", "n_high"]].rename(columns={"n_high": "label_n_high"})
    rows = f.merge(lab, on=STATION_KEYS, how="inner", validate="one_to_one")
    assert_in_window(rows, first, last, "station-day rows")
    return rows.sort_values(["target_date", "station_id"]).reset_index(drop=True)


def area_map_41(amap, areas, feature_keys, first, last):
    """Copy of the back-test job's area mapping step for a window: the view's rows (target_date, planning_area,
    station_id) restricted to the areas with residents aged 65+, and every area-day's station must have a feature
    row."""
    amap = amap.assign(target_date=pd.to_datetime(amap.target_date))
    assert_in_window(amap, first, last, "area mapping")
    amap41 = amap[amap.planning_area.isin(set(areas))]
    orphan = amap41.merge(feature_keys, how="left", indicator=True).query("_merge == 'left_only'")
    if len(orphan):
        raise AssertionError(f"{len(orphan)} area-days whose station has no feature row, e.g. "
                             f"{orphan.head(3).to_dict('records')}")
    return amap41


def area_days(amap41, frame):
    """Copy of the back-test job's area-days: the mapping joined to its station's row (inner, so an area-day whose
    station-day is not usable drops out)."""
    return amap41.merge(frame, on=STATION_KEYS, how="inner")


def compare_frames(a, b, keys, what, atol=FLOAT_ATOL):
    """Equal keys, row counts and values: floats within atol, everything else exactly, missing equal to missing.
    Returns {"rows", "columns", "max_abs_diff"}; raises AssertionError naming what differs."""
    if set(a.columns) != set(b.columns):
        raise AssertionError(f"{what}: columns differ: {sorted(set(a.columns) ^ set(b.columns))}")
    if len(a) != len(b):
        raise AssertionError(f"{what}: {len(a):,} rows on the back-test path, {len(b):,} from the builder")
    for name, d in (("back-test path", a), ("builder", b)):
        if d.duplicated(keys).any():
            raise AssertionError(f"{what}: duplicate keys on the {name}")
    a = a.sort_values(keys).reset_index(drop=True)
    b = b[list(a.columns)].sort_values(keys).reset_index(drop=True)
    if not a[keys].equals(b[keys]):
        bad = (a[keys] != b[keys]).any(axis=1)
        raise AssertionError(f"{what}: keys differ, first at {a.loc[bad, keys].iloc[0].to_dict()} against "
                             f"{b.loc[bad, keys].iloc[0].to_dict()}")
    diffs, max_abs = [], 0.0
    for c in a.columns:
        x, y = a[c], b[c]
        if pd.api.types.is_float_dtype(x) and pd.api.types.is_float_dtype(y):
            xv, yv = x.to_numpy(dtype=float), y.to_numpy(dtype=float)
            nan_x, nan_y = np.isnan(xv), np.isnan(yv)
            gap = np.abs(np.where(nan_x | nan_y, 0.0, xv - yv))
            bad = (nan_x != nan_y) | (gap > atol)
            max_abs = max(max_abs, float(gap.max()) if len(gap) else 0.0)
        else:
            bad = (~((x == y) | (x.isna() & y.isna()))).to_numpy()
        if bad.any():
            i = int(np.flatnonzero(bad)[0])
            diffs.append(f"{c} ({int(bad.sum())} rows; first at {a.loc[i, keys].to_dict()}: {x.iloc[i]!r} against "
                         f"{y.iloc[i]!r})")
    if diffs:
        raise AssertionError(f"{what}: values differ: " + "; ".join(diffs))
    return {"rows": len(a), "columns": len(a.columns), "max_abs_diff": max_abs}


def check_builder_equivalence(backtest_rows, backtest_area, builder_rows, builder_area):
    """Stage fit: on 1 Jul to 31 Aug 2026 the scoring builder's station-day and area-day rows must equal the back-test
    path's: keys, row counts and every column (features, diagnostics, labels, the area's station)."""
    return {"station-day rows": compare_frames(backtest_rows, builder_rows, STATION_KEYS, "station-day rows"),
            "area-day rows": compare_frames(backtest_area, builder_area, AREA_KEYS, "area-day rows")}


# ---------------------------------------------------------------- scoring (item 4 (b)) and evaluation (items 2, 3, 5)
def score_final(fitted, rows):
    """Predictions and baselines for the scoring rows; nothing is fitted here (persistence as in the folds; same month
    last year from the training labels of Sep and Oct 2025; the NEA rule at the training threshold). Returns
    (predictions, filled dates, rows whose forecast text was not seen in training)."""
    assert_in_window(rows, FINAL_FIRST, FINAL_LAST, "scoring rows")
    te, filled = apply_forecast_fill(rows, fitted.fill)
    pred = te[KEEP].copy()
    p = fitted.booster.predict(encode(te, fitted.categories))
    pred["p_low"], pred["p_moderate"], pred["p_high"] = p[:, 0], p[:, 1], p[:, 2]
    pred["persist_alert"] = te.n_high_d1.fillna(0).to_numpy() >= 1  # yesterday's highest API category was High
    pred["persist_score"] = te.wbgt_peak_d1.to_numpy(dtype=float)
    pred["nea_score"] = te.fc_temp_high.to_numpy(dtype=float)
    pred["nea_alert"] = (pred.nea_score >= fitted.theta) if fitted.theta is not None else False
    pred["same_month_score"] = np.nan
    month = te.target_date.dt.to_period("M").dt.to_timestamp()
    for m, idx in te.groupby(month).groups.items():
        pred.loc[idx, "same_month_score"] = same_month_last_year(fitted.labels, te.loc[idx], m).to_numpy()
    unseen = int((te.fc_text.notna() & ~te.fc_text.isin(fitted.categories)).sum())
    return pred, filled, unseen


def wilson(k, n, z=WILSON_Z):
    """Wilson score interval for k of n (k may be an expected, tie-split count)."""
    if not n:
        return float("nan"), float("nan")
    p, z2 = k / n, z * z
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = z * math.sqrt(max(p * (1 - p), 0.0) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return centre - half, centre + half


def evaluate_final(pred, area, cutoff=FINAL_CUTOFF):
    """The sets of §15: area-days over the 41 areas; station-days for all stations, without S142, S137 and S135, and
    the original 8. Per set: PR-AUC of each score from metrics.evaluate with no resamples; for each operating point in
    POINTS, counts, recall and precision for the whole window and for Sep and Oct (at_load; persistence's load is the
    whole window's, split by month, as in the back-test's monthly tables) and alerts per calendar day; Wilson intervals
    on the station-day sets only. Also the pre-declared reading and the cut-off beside the back-test's."""
    assert_in_window(pred, FINAL_FIRST, FINAL_LAST, "predictions")
    assert_in_window(area, FINAL_FIRST, FINAL_LAST, "area-days")
    sets = {"area41": area, "station_all": pred, "station_wo3": pred[~pred.station_id.isin(LATE_STARTERS)],
            "station_o8": pred[pred.station_id.isin(ORIGINAL_8)]}
    out, counts = {"sets": {}}, []
    for name, frame in sets.items():
        if frame.empty:
            continue
        y = (frame.y == HIGH).to_numpy()
        ref = frame.persist_alert.to_numpy(dtype=bool)
        scores = {m: frame[c].to_numpy(dtype=float) for m, c in SCORES.items()}
        res = evaluate(y, scores, ref, np.zeros(len(y), dtype=int), NO_RESAMPLES)
        k = res["K"]
        weights = {("model", "cutoff"): (scores["model"] >= cutoff).astype(float),
                   ("persistence_binary", "own_rule"): ref.astype(float),
                   ("nea_rule", "theta"): frame.nea_alert.to_numpy(dtype=float)}
        weights.update({(m, "persistence_load"): load_weights(s, k)[0] for m, s in scores.items()})
        out["sets"][name] = {"rows": res["rows"], "high": res["positives"], "K": k,
                             "pr_auc": {m: res["methods"][m]["pr_auc"] for m in SCORES}, "evaluate": res["methods"]}
        for period, first, last in PERIODS:
            mask = ((frame.target_date >= pd.Timestamp(first)) & (frame.target_date <= pd.Timestamp(last))).to_numpy()
            days = (last - first).days + 1
            for method, point in POINTS:
                c = at_load(y[mask], weights[(method, point)][mask])
                row = {"set": name, "period": period, "days": days, "method": method, "point": point,
                       "high": c["positives"], "alerts": c["alerts"], "tp": c["tp"], "recall": c["recall"],
                       "precision": c["precision"], "alerts_per_day": c["alerts"] / days}
                if name.startswith("station"):
                    row["recall_lo"], row["recall_hi"] = wilson(c["tp"], c["positives"])
                    row["precision_lo"], row["precision_hi"] = wilson(c["tp"], c["alerts"])
                counts.append(row)
    out["counts"] = pd.DataFrame(counts)
    a = out["sets"]["area41"]["pr_auc"]
    out["reading"] = {"model": a["model"], "persistence_continuous": a["persistence_continuous"],
                      "agrees": bool(a["model"] > a["persistence_continuous"])}  # NaN or a tie is not "above"
    at = out["counts"].query("set == 'area41' and method == 'model' and point == 'cutoff'").set_index("period")
    out["versus_backtest"] = {"final": at[["days", "high", "alerts", "tp", "recall", "alerts_per_day"]].to_dict("index"),
                              "backtest": {**BACKTEST_AT_CUTOFF,
                                           "recall": BACKTEST_AT_CUTOFF["tp"] / BACKTEST_AT_CUTOFF["high"],
                                           "alerts_per_day": BACKTEST_AT_CUTOFF["alerts"] / BACKTEST_AT_CUTOFF["days"]}}
    return out


# ---------------------------------------------------------------- the order (item 4)
def run_final_check(find_locks, load_training, load_scoring, record):
    """§15 item 4, in this order:
    1. refuse if find_locks() lists a scored final_check run, before anything is read;
    2. load_training() -> (rows, labels) through the back-test path, then fit_final;
    3. only then load_scoring() -> (station-day rows, area mapping over the 41 areas) for 1 Sep to 19 Oct, asserted
       inside it; predictions and baselines (nothing fitted), area-days, the evaluation;
    4. refuse again if a scored run appeared meanwhile, then record(result): scoring has completed, so its first act
       writes the lock (the final_check run, tagged scored), then the record; it returns what record returns. Nothing
       about the scores leaves this function before record."""
    refuse_if_scored(find_locks)
    rows, labels = load_training()
    fitted = fit_final(rows, labels)
    s_rows, s_map = load_scoring()
    assert_in_window(s_rows, FINAL_FIRST, FINAL_LAST, "scoring rows")
    assert_in_window(s_map, FINAL_FIRST, FINAL_LAST, "scoring area mapping")
    if s_rows.empty or s_map.empty:
        raise AssertionError("no scoring station-days or area-days in 1 Sep to 19 Oct 2026")
    pred, filled, unseen = score_final(fitted, s_rows)
    area = area_days(s_map, pred)
    results = evaluate_final(pred, area)
    refuse_if_scored(find_locks)
    return record({"fitted": fitted, "predictions": pred, "area_days": area, "filled": filled,
                   "unseen_text_rows": unseen, "area_dropped": len(s_map) - len(area), "results": results})
