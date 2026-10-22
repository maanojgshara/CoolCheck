"""Evaluation for the back-test (docs/design/backtest.md §6): average precision and the PR curve for P(High), recall and
precision at a fixed alert load with ties resolved in expectation, and a paired 7-day block bootstrap.

Scores mean "higher is more likely High"; a missing score ranks lowest. Average precision is the step-wise area
(sklearn.metrics.average_precision_score), never an interpolated one. In the bootstrap a resample re-weights each row by
how often its block was drawn, so all rows of a block move together; thresholds and tie weights stay at their
full-sample values.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

MISSING_SCORE = -1e18


def _clean(score):
    s = np.asarray(score, dtype=float)
    return np.where(np.isnan(s), MISSING_SCORE, s)


def pr_auc(y, score, weight=None):
    """Average precision; NaN when there is no positive."""
    y = np.asarray(y, dtype=bool)
    if not y.any():
        return float("nan")
    return float(average_precision_score(y, _clean(score), sample_weight=weight))


def pr_curve(y, score):
    """One row per distinct score, highest first: threshold, alerts (rows scoring at or above it), tp, recall,
    precision. This is the table the H4 cut-off is chosen from."""
    y = np.asarray(y, dtype=bool)
    s = _clean(score)
    order = np.argsort(-s, kind="mergesort")
    s_o, y_o = s[order], y[order]
    last = np.r_[np.flatnonzero(np.diff(s_o) != 0), len(s_o) - 1] if len(s_o) else np.array([], dtype=int)
    tp = np.cumsum(y_o)[last]
    alerts = last + 1
    pos = int(y.sum())
    return pd.DataFrame({"threshold": s_o[last], "alerts": alerts, "tp": tp,
                         "recall": tp / pos if pos else np.nan, "precision": tp / alerts})


def load_weights(score, k):
    """Each row's expected alert (0 to 1) when the k highest scores alert and ties at the k-th score are broken at
    random, so the expected number of alerts is exactly k. Returns (weights, threshold)."""
    s = _clean(score)
    k = int(min(max(k, 0), len(s)))
    w = np.zeros(len(s))
    if k == 0:
        return w, float("inf")
    th = np.sort(s)[::-1][k - 1]
    above, tie = s > th, s == th
    w[above] = 1.0
    w[tie] = (k - above.sum()) / tie.sum()
    return w, float(th)


def at_load(y, w):
    """Counts, recall and precision from per-row expected alerts w (load_weights, or a binary rule as 0/1)."""
    y = np.asarray(y, dtype=bool)
    w = np.asarray(w, dtype=float)
    alerts, tp, pos = w.sum(), (w * y).sum(), int(y.sum())
    return {"alerts": alerts, "tp": tp, "fp": alerts - tp, "fn": pos - tp, "positives": pos,
            "recall": tp / pos if pos else np.nan, "precision": tp / alerts if alerts else np.nan}


class SortedScore:
    """A score sorted once, so a resample's weighted average precision is two cumulative sums (equal to
    average_precision_score with sample_weight; tests/backtest/test_metrics.py checks it)."""

    def __init__(self, y, score):
        s = _clean(score)
        self.order = np.argsort(-s, kind="mergesort")
        s_o = s[self.order]
        self.y_o = np.asarray(y, dtype=bool)[self.order].astype(float)
        self.last = np.r_[np.flatnonzero(np.diff(s_o) != 0), len(s_o) - 1]

    def ap(self, w):
        w_o = np.asarray(w, dtype=float)[self.order]
        tp = np.cumsum(w_o * self.y_o)[self.last]
        alerts = np.cumsum(w_o)[self.last]
        pos = tp[-1]
        if pos <= 0:
            return float("nan")
        precision = np.divide(tp, alerts, out=np.zeros_like(tp), where=alerts > 0)
        return float(np.sum(np.diff(np.r_[0.0, tp / pos]) * precision))


def block_of(dates, start, days=7):
    """Block number of each date: consecutive `days`-day blocks counted from start."""
    d = (pd.to_datetime(pd.Series(dates)).reset_index(drop=True) - pd.Timestamp(start)).dt.days.to_numpy()
    if (d < 0).any():
        raise ValueError(f"a date before the first block ({start})")
    return d // days


def resample_blocks(universe, n_boot, seed):
    """n_boot draws, each len(universe) blocks with replacement from the given block numbers, shared by every method
    of an evaluation set (so differences between methods are paired)."""
    uni = np.asarray(sorted(set(int(b) for b in universe)))
    rng = np.random.default_rng(seed)
    return uni[rng.integers(0, len(uni), size=(n_boot, len(uni)))]


def row_weights(blocks, draw):
    """How many times each row's block was drawn in one resample."""
    return np.bincount(draw, minlength=int(blocks.max()) + 1)[blocks].astype(float)


def _interval(values):
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    return (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))) if len(v) else (np.nan, np.nan)


def evaluate(y, scores, ref_alert, blocks, draws, sustained=None, diffs=()):
    """One evaluation set. y: High or not per row; scores: {method: score}; ref_alert: the binary reference rule
    (persistence), whose alert count K fixes the load; blocks: block number per row; draws: resample_blocks for this
    set; sustained: rows labelled High with 3 or more High readings; diffs: (method, other) pairs for paired
    differences. The reference rule is reported as "reference" at its own load.

    Returns {"K", "positives", "rows", "skipped", "methods": {name: {metric: value}}, "diffs": {(a, b): {...}}}.
    Each metric has its full-sample value and a 95% percentile interval (_lo, _hi) from the resamples; a resample with
    no positive is skipped and counted."""
    y = np.asarray(y, dtype=bool)
    ref = np.asarray(ref_alert, dtype=bool)
    sus = np.zeros(len(y), dtype=bool) if sustained is None else np.asarray(sustained, dtype=bool)
    k = int(ref.sum())
    weights = {"reference": (ref.astype(float), None)}
    weights.update({m: load_weights(s, k) for m, s in scores.items()})
    sorted_scores = {m: SortedScore(y, s) for m, s in scores.items()}

    def stats(rw, name):
        w = weights[name][0]
        pos, sus_n, alerts = (rw * y).sum(), (rw * sus).sum(), (rw * w).sum()
        tp = (rw * w * y).sum()
        out = {"recall_at_load": tp / pos if pos else np.nan, "precision_at_load": tp / alerts if alerts else np.nan,
               "sustained_recall": (rw * w * sus).sum() / sus_n if sus_n else np.nan}
        if name in sorted_scores:
            out["pr_auc"] = sorted_scores[name].ap(rw)
        return out

    names = list(weights)
    full = {m: stats(np.ones(len(y)), m) for m in names}
    boot = {m: {key: [] for key in full[m]} for m in names}
    skipped = 0
    for draw in draws:
        rw = row_weights(blocks, draw)
        if (rw * y).sum() == 0:
            skipped += 1
            continue
        for m in names:
            for key, v in stats(rw, m).items():
                boot[m][key].append(v)
    methods = {}
    for m in names:
        res = at_load(y, weights[m][0])
        res.update(full[m])
        res["threshold"] = weights[m][1]
        for key in full[m]:
            res[f"{key}_lo"], res[f"{key}_hi"] = _interval(boot[m][key])
        methods[m] = res
    diff_out = {}
    for a, b in diffs:
        d = {}
        for key in set(full[a]) & set(full[b]):
            d[key] = full[a][key] - full[b][key]
            d[f"{key}_lo"], d[f"{key}_hi"] = _interval(np.asarray(boot[a][key]) - np.asarray(boot[b][key]))
        diff_out[(a, b)] = d
    return {"K": k, "positives": int(y.sum()), "rows": len(y), "skipped": skipped, "methods": methods,
            "diffs": diff_out}


def group_counts(groups, y, w, p_high=None):
    """Counts (not rates) per group: rows, High, expected alerts, TP, FP, FN, and the sum of P(High) when given."""
    df = pd.DataFrame({"group": np.asarray(groups), "y": np.asarray(y, dtype=bool).astype(int),
                       "w": np.asarray(w, dtype=float)})
    df["tp"] = df.w * df.y
    if p_high is not None:
        df["p_high"] = np.asarray(p_high, dtype=float)
    agg = {"rows": ("y", "size"), "high": ("y", "sum"), "alerts": ("w", "sum"), "tp": ("tp", "sum")}
    if p_high is not None:
        agg["sum_p_high"] = ("p_high", "sum")
    g = df.groupby("group", sort=True).agg(**agg).reset_index()
    g["fp"], g["fn"] = g.alerts - g.tp, g.high - g.tp
    return g
