"""The rolling back-test (docs/design/backtest.md §5): 14 monthly folds, Jul 2025 to Aug 2026, each trained on the target
dates before its month; the forecast fill and the text categories fitted inside each fold; four LightGBM candidates,
the fold's configuration chosen from earlier folds only; three baselines and three ablations on the same rows.

Held-out guard: nothing fitted, tuned or chosen may see a target date after 2026-08-31. Labels come through
backtest_labels (usable_labels with last_date), and every training, test, history and pooled frame is asserted
before 2026-09-01. The final check (1 Sep to 19 Oct 2026) is scored only when the user says so; nothing here scores it.
"""
from datetime import date

import lightgbm as lgb
import numpy as np
import pandas as pd

from coolcheck.features import CATEGORICAL, FEATURES, LATE_STARTERS, ORIGINAL_8, SEASONS, usable_labels
from coolcheck.metrics import at_load, block_of, evaluate, group_counts, load_weights, pr_auc, pr_curve, resample_blocks

FIRST_TARGET = pd.Timestamp("2025-01-17")  # the first target date with a yesterday
LAST_BACKTEST_DATE = date(2026, 8, 31)
HOLDOUT_START = date(2026, 9, 1)
FOLDS = tuple(pd.date_range("2025-07-01", "2026-08-01", freq="MS"))  # the 14 test months
SAME_MONTH_FIRST = pd.Timestamp("2026-02-01")  # same month last year needs a full month a year before
HP_CANDIDATES = ((7, 150), (15, 150), (7, 400), (15, 400))  # (num_leaves, rounds), smallest leaves x rounds first
LGB_FIXED = {"objective": "multiclass", "num_class": 3, "learning_rate": 0.05, "min_data_in_leaf": 40,
             "lambda_l2": 1.0, "feature_fraction": 0.9, "bagging_fraction": 0.8, "bagging_freq": 1, "max_bin": 63,
             "min_data_per_group": 50, "cat_smooth": 10, "seed": 42, "deterministic": True, "force_row_wise": True,
             "num_threads": 4, "verbose": -1}
FILL_MIN_DATES = 10       # a calendar month's fill needs at least 10 training dates, else all training dates
SAME_MONTH_MIN_DAYS = 15  # a station's own share needs 15 usable days in that month a year earlier
HALF_LIFE_DAYS = 180      # recency ablation, fixed in advance, not tuned
HIGH = 2


def backtest_labels(labels, run_date):
    """Usable labels for the back-test (Spark): completed days only, and nothing after 2026-08-31."""
    return usable_labels(labels, run_date, last_date=LAST_BACKTEST_DATE)


def assert_before_holdout(frame, what, col="target_date"):
    """Fail if any target date of a frame is after 2026-08-31."""
    if len(frame) and pd.Timestamp(frame[col].max()) > pd.Timestamp(LAST_BACKTEST_DATE):
        raise AssertionError(f"{what}: target date {pd.Timestamp(frame[col].max()):%Y-%m-%d} is after "
                             f"{LAST_BACKTEST_DATE}; the final check (from {HOLDOUT_START}) is scored only when the "
                             "user says so")


def assert_fitted_before(max_date, m, what):
    """A fitted or chosen object for fold m may only use target dates before m."""
    if max_date is not None and not pd.isna(max_date) and pd.Timestamp(max_date) >= pd.Timestamp(m):
        raise AssertionError(f"{what} for fold {pd.Timestamp(m):%Y-%m} used target date "
                             f"{pd.Timestamp(max_date):%Y-%m-%d}, on or after the fold start")


def station_day_rows(features, labels):
    """features: pandas output of station_day_features; labels: pandas output of backtest_labels. Inner join on
    (station_id, target_date), one-to-one: a row per reporting station with a usable label. The label day's High
    reading count is kept as label_n_high, for the sustained-High check only (never a feature)."""
    f, lab = features.copy(), labels.copy()
    for d in (f, lab):
        d["target_date"] = pd.to_datetime(d["target_date"])
    lab = lab[["station_id", "target_date", "y", "n_high"]].rename(columns={"n_high": "label_n_high"})
    rows = f.merge(lab, on=["station_id", "target_date"], how="inner", validate="one_to_one")
    assert_before_holdout(rows, "station-day rows")
    return rows.sort_values(["target_date", "station_id"]).reset_index(drop=True)


def assert_fold(train, test, m):
    m = pd.Timestamp(m)
    nxt = m + pd.offsets.MonthBegin(1)
    if len(train) and train.target_date.max() >= m:
        raise AssertionError(f"fold {m:%Y-%m}: a training row on or after the fold start")
    if len(test) and not ((test.target_date >= m) & (test.target_date < nxt)).all():
        raise AssertionError(f"fold {m:%Y-%m}: a test row outside the month")
    assert_before_holdout(train, f"fold {m:%Y-%m} training rows")
    assert_before_holdout(test, f"fold {m:%Y-%m} test rows")


def fold_split(rows, m):
    """Training rows: target dates before month m. Test rows: target dates in m."""
    m = pd.Timestamp(m)
    train = rows[rows.target_date < m]
    test = rows[(rows.target_date >= m) & (rows.target_date < m + pd.offsets.MonthBegin(1))]
    assert_fold(train, test, m)
    return train, test


def _mode(values):
    counts = values.value_counts()
    return sorted(counts[counts == counts.max()].index)[0]  # ties alphabetical


def fit_forecast_fill(train):
    """Fill values for missing forecasts from the fold's training rows, one value per date (a date's forecast is
    shared by all its stations): per calendar month the median high temperature and the most common text when the
    month has at least FILL_MIN_DATES training dates, else over all training dates."""
    d = train.loc[~train.forecast_missing.astype(bool), ["target_date", "fc_temp_high", "fc_text"]]
    per_date = d.groupby("target_date").agg(t=("fc_temp_high", "first"), x=("fc_text", "first"),
                                            nt=("fc_temp_high", "nunique"), nx=("fc_text", "nunique"))
    if (per_date.nt > 1).any() or (per_date.nx > 1).any():
        raise AssertionError("a target date has more than one forecast across stations")
    by_month = {mo: (float(g.t.median()), _mode(g.x)) for mo, g in per_date.groupby(per_date.index.month)
                if len(g) >= FILL_MIN_DATES}
    return {"by_month": by_month, "overall": (float(per_date.t.median()), _mode(per_date.x)),
            "max_date": train.target_date.max()}


def apply_forecast_fill(frame, fill):
    """A copy with the missing forecasts filled, and the filled dates with their values and source."""
    out = frame.copy()
    miss = out.forecast_missing.astype(bool).to_numpy()
    months = out.loc[miss, "target_date"].dt.month
    vals = [fill["by_month"].get(mo, fill["overall"]) for mo in months]
    out.loc[miss, "fc_temp_high"] = [v[0] for v in vals]
    out.loc[miss, "fc_text"] = [v[1] for v in vals]
    filled = out.loc[miss, ["target_date", "fc_temp_high", "fc_text"]].drop_duplicates("target_date")
    filled["source"] = ["calendar month" if d.month in fill["by_month"] else "all training dates"
                        for d in filled.target_date]
    return out, filled


def encode(frame, text_categories, drop=()):
    """The model's input frame: the features in FEATURES order (less `drop`), the two categoricals with fixed
    categories (a text unseen in training becomes missing)."""
    x = frame[[f for f in FEATURES if f not in drop]].copy()
    for c in x.columns:
        if c not in CATEGORICAL:
            x[c] = pd.to_numeric(x[c], errors="raise").astype(float)
    if "fc_text" in x:
        x["fc_text"] = pd.Categorical(x["fc_text"], categories=list(text_categories))
    if "season" in x:
        x["season"] = pd.Categorical(x["season"], categories=list(SEASONS))
    return x


def fit_lgb(x, y, num_leaves, rounds, weight=None):
    ds = lgb.Dataset(x, label=y, weight=weight, categorical_feature=[c for c in CATEGORICAL if c in x.columns],
                     free_raw_data=False)
    return lgb.train({**LGB_FIXED, "num_leaves": num_leaves}, ds, num_boost_round=rounds)


def choose_config(history, m):
    """The candidate (index into HP_CANDIDATES) with the highest pooled station-level average precision for High over
    the folds before m; ties to the smaller; the first fold takes the smallest. history holds out-of-fold rows with
    target_date, y and p_high_c0 .. p_high_c3. Returns (index, {index: average precision}, latest date used)."""
    m = pd.Timestamp(m)
    h = history[history.target_date < m] if history is not None else None
    if h is None or h.empty:
        return 0, {}, None
    assert_before_holdout(h, f"hyper-parameter history for fold {m:%Y-%m}")
    aps = {i: pr_auc(h.y == HIGH, h[f"p_high_c{i}"]) for i in range(len(HP_CANDIDATES))}
    best = max(aps, key=lambda i: (-1.0 if np.isnan(aps[i]) else aps[i], -i))
    return best, aps, h.target_date.max()


def best_overall(pooled):
    """The candidate with the best pooled average precision over all 14 folds (the secondary line, chosen on the same
    folds; also the Day 4 choice). Returns (index, {index: average precision})."""
    assert_before_holdout(pooled, "best-overall choice")
    aps = {i: pr_auc(pooled.y == HIGH, pooled[f"p_high_c{i}"]) for i in range(len(HP_CANDIDATES))}
    return max(aps, key=lambda i: (-1.0 if np.isnan(aps[i]) else aps[i], -i)), aps


def same_month_last_year(labels, test, m, panel=ORIGINAL_8):
    """Scores for the test rows of month m, from Feb 2026: each station's High share over its usable days in the same
    month a year earlier when it has at least SAME_MONTH_MIN_DAYS of them, else the panel's pooled share in that month.
    NaN before Feb 2026. Reads only labels from a year before m."""
    m = pd.Timestamp(m)
    if m < SAME_MONTH_FIRST:
        return pd.Series(np.nan, index=test.index)
    s0 = m - pd.DateOffset(years=1)
    src = labels[(labels.target_date >= s0) & (labels.target_date < s0 + pd.offsets.MonthBegin(1))]
    assert_fitted_before(src.target_date.max() if len(src) else None, m, "same month last year")
    high = (src.y == HIGH).rename("high")
    by_station = pd.concat([src.station_id, high], axis=1).groupby("station_id").high.agg(["size", "mean"])
    own = by_station.loc[by_station["size"] >= SAME_MONTH_MIN_DAYS, "mean"]
    in_panel = src.station_id.isin(panel)
    panel_share = float((src.y[in_panel] == HIGH).mean()) if in_panel.any() else np.nan
    return test.station_id.map(own).astype(float).fillna(panel_share)


def fit_nea_threshold(train):
    """theta = the observed forecast high temperature (after the fill) that maximises F1 for High on the training rows;
    ties to the higher theta. Returns (theta, F1)."""
    x = train.fc_temp_high.to_numpy(dtype=float)
    hi = (train.y == HIGH).to_numpy()
    best_f1, best_th = -1.0, None
    for th in np.unique(x[~np.isnan(x)]):
        alert = x >= th
        tp, fp, fn = (alert & hi).sum(), (alert & ~hi).sum(), (~alert & hi).sum()
        f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
        if f1 >= best_f1:  # ascending, so an equal F1 moves to the higher theta
            best_f1, best_th = f1, float(th)
    return best_th, best_f1


def recency_weights(train, m):
    """0.5 ** (age / 180 days), age = days from the row's target date to the fold start (ablation only)."""
    age = (pd.Timestamp(m) - train.target_date).dt.days.to_numpy()
    return 0.5 ** (age / HALF_LIFE_DAYS)


KEEP = ["station_id", "target_date", "y", "label_n_high", "season", "n_high_d1", "wbgt_peak_d1", "forecast_missing"]


def run_folds(rows, labels, folds=FOLDS, ablations=True):
    """All folds. rows: station_day_rows; labels: backtest_labels as pandas (for same month last year).

    Returns (pooled, records, fills, boosters). pooled: one row per test station-day with the fold, the four
    candidates' probabilities (p_low_c*, p_moderate_c*, p_high_c*), the per-fold choice (config, p_low, p_moderate,
    p_high), the ablations (p_high_no_char, p_high_wo3, p_high_recency), persistence (persist_alert, persist_score),
    same month last year (same_month_score) and the NEA rule (nea_score, nea_alert). records: one row per fold.
    fills: the dates whose forecast was filled. boosters: {(fold, candidate or ablation): model text}."""
    rows, labels = rows.copy(), labels.copy()
    labels["target_date"] = pd.to_datetime(labels["target_date"])
    assert_before_holdout(rows, "station-day rows")
    assert_before_holdout(labels, "labels")
    pooled, records, fills, boosters, history = [], [], [], {}, None
    for m in folds:
        m = pd.Timestamp(m)
        train, test = fold_split(rows, m)
        fill = fit_forecast_fill(train)
        assert_fitted_before(fill["max_date"], m, "forecast fill")
        tr, filled_tr = apply_forecast_fill(train, fill)
        te, filled_te = apply_forecast_fill(test, fill)
        cats = sorted(tr.fc_text.dropna().unique())
        x_tr, x_te, y_tr = encode(tr, cats), encode(te, cats), tr.y.to_numpy()
        pred = te[KEEP].copy()
        pred["fold"] = m
        for i, (leaves, rounds) in enumerate(HP_CANDIDATES):
            b = fit_lgb(x_tr, y_tr, leaves, rounds)
            p = b.predict(x_te)
            pred[f"p_low_c{i}"], pred[f"p_moderate_c{i}"], pred[f"p_high_c{i}"] = p[:, 0], p[:, 1], p[:, 2]
            boosters[(m, f"c{i}")] = b.model_to_string()
        choice, aps, used = choose_config(history, m)
        assert_fitted_before(used, m, "hyper-parameter choice")
        pred["config"] = choice
        for cls in ("low", "moderate", "high"):
            pred[f"p_{cls}"] = pred[f"p_{cls}_c{choice}"]
        leaves, rounds = HP_CANDIDATES[choice]
        if ablations:
            drop = ("station_char_30d",)
            b = fit_lgb(encode(tr, cats, drop), y_tr, leaves, rounds)
            pred["p_high_no_char"] = b.predict(encode(te, cats, drop))[:, HIGH]
            keep = ~tr.station_id.isin(LATE_STARTERS).to_numpy()
            b2 = fit_lgb(x_tr[keep], y_tr[keep], leaves, rounds)
            pred["p_high_wo3"] = b2.predict(x_te)[:, HIGH]
            b3 = fit_lgb(x_tr, y_tr, leaves, rounds, weight=recency_weights(tr, m))
            pred["p_high_recency"] = b3.predict(x_te)[:, HIGH]
            boosters.update({(m, "no_char"): b.model_to_string(), (m, "wo3"): b2.model_to_string(),
                             (m, "recency"): b3.model_to_string()})
        pred["persist_alert"] = te.n_high_d1.fillna(0).to_numpy() >= 1  # yesterday's highest API category was High
        pred["persist_score"] = te.wbgt_peak_d1.to_numpy(dtype=float)
        pred["same_month_score"] = same_month_last_year(labels, te, m).to_numpy()
        theta, theta_f1 = fit_nea_threshold(tr)
        pred["nea_score"] = te.fc_temp_high.to_numpy(dtype=float)
        pred["nea_alert"] = (pred.nea_score >= theta) if theta is not None else False
        unseen = te.fc_text.notna() & ~te.fc_text.isin(cats)
        records.append({"fold": m, "train_rows": len(tr), "train_high": int((tr.y == HIGH).sum()),
                        "train_last_date": tr.target_date.max(), "test_rows": len(te),
                        "test_high": int((te.y == HIGH).sum()), "config": choice,
                        "test_pr_auc": pr_auc(te.y == HIGH, pred.p_high),  # NaN in a month with no High
                        "num_leaves": leaves, "rounds": rounds,
                        "choice_aps": {HP_CANDIDATES[i]: round(v, 6) for i, v in aps.items()},
                        "nea_theta": theta, "nea_theta_f1": theta_f1, "text_categories": len(cats),
                        "unseen_text_rows": int(unseen.sum()), "filled_train_dates": len(filled_tr),
                        "filled_test_dates": len(filled_te)})
        for split, f in (("train", filled_tr), ("test", filled_te)):
            if len(f):
                fills.append(f.assign(fold=m, split=split))
        cand_cols = [f"p_high_c{i}" for i in range(len(HP_CANDIDATES))]
        part = pred[["target_date", "y", *cand_cols]]
        history = part if history is None else pd.concat([history, part], ignore_index=True)
        pooled.append(pred)
    pooled = pd.concat(pooled, ignore_index=True)
    assert_before_holdout(pooled, "pooled predictions")
    fills = (pd.concat(fills, ignore_index=True) if fills else
             pd.DataFrame(columns=["target_date", "fc_temp_high", "fc_text", "source", "fold", "split"]))
    return pooled, pd.DataFrame(records), fills, boosters


# ---------------------------------------------------------------- evaluation (note §6)
METHODS = {"model": "p_high", "persistence_continuous": "persist_score", "nea_rule": "nea_score",
           "ablation_no_station_char": "p_high_no_char", "ablation_without_S142_S137_S135": "p_high_wo3",
           "ablation_recency_hl180": "p_high_recency"}
SAME_MONTH = {"same_month_last_year": "same_month_score"}
LABEL_NOISE_NOTE = ("Label-noise reference (docs/checks/h10_v2.md (viii)): near-equidistant stations' daily categories "
                    "differ on 22.1% (29 of 131 days, Jurong West) and 22.0% (128 of 582, Marine Parade).")
SEASON_OF_MONTH = {12: SEASONS[0], 1: SEASONS[0], 2: SEASONS[0], 3: SEASONS[1], 4: SEASONS[1], 5: SEASONS[1],
                   6: SEASONS[2], 7: SEASONS[2], 8: SEASONS[2], 9: SEASONS[2], 10: SEASONS[3], 11: SEASONS[3]}


def season_period(ts):
    """Season with its year; the NE monsoon spans the new year (Dec 2025 to Feb 2026 is "NE monsoon 2025/26")."""
    ts = pd.Timestamp(ts)
    if ts.month in (12, 1, 2):
        y0 = ts.year if ts.month == 12 else ts.year - 1
        return f"{SEASONS[0]} {y0}/{str(y0 + 1)[2:]}"
    return f"{SEASON_OF_MONTH[ts.month]} {ts.year}"


def _set_eval(frame, methods, n_boot, seed, diffs):
    y = (frame.y == HIGH).to_numpy()
    blocks = block_of(frame.target_date, FOLDS[0])
    draws = resample_blocks(np.unique(blocks), n_boot, seed)
    scores = {m: frame[c].to_numpy(dtype=float) for m, c in methods.items() if c in frame}
    sustained = y & (frame.label_n_high.to_numpy() >= 3)
    res = evaluate(y, scores, frame.persist_alert.to_numpy(dtype=bool), blocks, draws, sustained,
                   [d for d in diffs if d[0] in scores and (d[1] in scores or d[1] == "reference")])
    # recall at load also for the NEA rule at its own threshold (its binary operating point)
    res["nea_rule_at_theta"] = at_load(y, frame.nea_alert.to_numpy(dtype=float))
    res["first_date"], res["last_date"] = frame.target_date.min(), frame.target_date.max()
    res["resamples"] = len(draws)
    res["model_weights"] = load_weights(frame.p_high.to_numpy(dtype=float), res["K"])[0]
    return res


def evaluate_all(pooled, area, best_config, n_boot=2000, seed=42, im1_2025=None):
    """Every set of note §6. pooled: run_folds' station-days; area: area-days (planning_area, target_date, station_id)
    joined to their station's pooled row; best_config: best_overall's index; im1_2025: {"station": frame, "area":
    frame} of Mar to May 2025 rows with y and persist_alert (persistence and base rate only, as no fold predicts them).
    Returns a dict of results for the report and MLflow."""
    assert_before_holdout(pooled, "evaluation")
    assert_before_holdout(area, "evaluation (area-days)")
    methods = {**METHODS, "best_overall": f"p_high_c{best_config}"}
    diffs = [("model", m) for m in methods if m != "model"] + [("model", "reference")]
    o8, wo3 = pooled.station_id.isin(ORIGINAL_8), ~pooled.station_id.isin(LATE_STARTERS)
    feb_aug = pooled.target_date >= SAME_MONTH_FIRST
    sets = {"area41": (area, methods), "station_all": (pooled, methods), "station_wo3": (pooled[wo3], methods),
            "station_o8": (pooled[o8], methods)}
    if feb_aug.any():
        fa_methods = {**methods, **SAME_MONTH}
        sets["area41_feb_aug_2026"] = (area[area.target_date >= SAME_MONTH_FIRST], fa_methods)
        sets["station_all_feb_aug_2026"] = (pooled[feb_aug], fa_methods)
        diffs = diffs + [("model", "same_month_last_year")]
    out = {"sets": {}, "per_month": {}, "season": {}, "pr_curve": {}}
    for name, (frame, ms) in sets.items():
        if frame.empty:
            continue
        res = _set_eval(frame, ms, n_boot, seed, diffs)
        out["sets"][name] = res
        if name in ("area41", "station_all"):
            y = frame.y == HIGH
            month = frame.target_date.dt.strftime("%Y-%m")
            m = group_counts(month, y, res["model_weights"], frame.p_high)
            p = group_counts(month, y, frame.persist_alert.astype(float))
            out["per_month"][name] = m.merge(p[["group", "alerts", "tp", "fp", "fn"]], on="group",
                                             suffixes=("", "_persistence"))
            season = frame.target_date.map(season_period)
            s = group_counts(season, y, res["model_weights"], frame.p_high)
            sp = group_counts(season, y, frame.persist_alert.astype(float))
            out["season"][name] = s.merge(sp[["group", "alerts", "tp", "fp", "fn"]], on="group",
                                          suffixes=("", "_persistence"))
            out["pr_curve"][name] = pr_curve(y, frame.p_high)
        del res["model_weights"]
    hi = pooled[pooled.y == HIGH]
    out["high_by_readings"] = {"1": int((hi.label_n_high == 1).sum()), "2": int((hi.label_n_high == 2).sum()),
                               "3 or more": int((hi.label_n_high >= 3).sum())}
    probs = pooled[["p_low", "p_moderate", "p_high"]].to_numpy()
    out["three_class"] = pd.crosstab(pooled.y.rename("label"), pd.Series(probs.argmax(axis=1), name="most_probable",
                                                                      index=pooled.index))
    eps = 1e-15
    out["log_loss"] = float(-np.mean(np.log(np.clip(probs[np.arange(len(probs)), pooled.y.to_numpy()], eps, 1))))
    out["im1_2025"] = {}
    for level, frame in (im1_2025 or {}).items():
        out["im1_2025"][level] = at_load(frame.y == HIGH, frame.persist_alert.astype(float))
        out["im1_2025"][level]["rows"] = len(frame)
    return out
