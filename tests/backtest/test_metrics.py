"""Evaluation helpers (docs/design/backtest.md §6) on hand-worked examples and against scikit-learn."""
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import average_precision_score

from coolcheck.metrics import (SortedScore, at_load, block_of, evaluate, group_counts, load_weights, pr_auc, pr_curve,
                               resample_blocks, row_weights)


def test_average_precision_and_curve_on_a_hand_example():
    y, s = [1, 0, 1, 0], [0.9, 0.8, 0.7, 0.1]
    # thresholds 0.9 (P 1, R 1/2), 0.8 (P 1/2, R 1/2), 0.7 (P 2/3, R 1): AP = 1/2 * 1 + 0 + 1/2 * 2/3
    assert pr_auc(y, s) == pytest.approx(5 / 6)
    c = pr_curve(y, s)
    assert list(c.alerts) == [1, 2, 3, 4] and list(c.tp) == [1, 1, 2, 2]
    assert list(c.recall) == [0.5, 0.5, 1.0, 1.0] and c.precision.iloc[2] == pytest.approx(2 / 3)
    assert np.isnan(pr_auc([0, 0], [0.1, 0.2]))


def test_missing_scores_rank_lowest():
    assert pr_auc([0, 1, 1], [np.nan, 0.2, 0.1]) == pytest.approx(1.0)


def test_load_weights_resolve_ties_in_expectation():
    y = np.array([1, 1, 0, 0, 1], dtype=bool)
    w, th = load_weights([0.9, 0.5, 0.5, 0.5, 0.1], k=2)
    # one row above the threshold, three tied at it share the one remaining alert
    assert th == 0.5 and w.sum() == pytest.approx(2) and list(w) == pytest.approx([1, 1 / 3, 1 / 3, 1 / 3, 0])
    r = at_load(y, w)
    assert r["tp"] == pytest.approx(4 / 3) and r["recall"] == pytest.approx(4 / 9) and r["precision"] == pytest.approx(2 / 3)


@pytest.mark.parametrize("seed", range(5))
def test_weighted_average_precision_equals_scikit_learn(seed):
    rng = np.random.default_rng(seed)
    y = rng.random(400) < 0.1
    s = np.round(rng.random(400), 1)        # many ties
    w = rng.integers(0, 4, 400).astype(float)  # resample multiplicities, zeros included
    assert SortedScore(y, s).ap(w) == pytest.approx(average_precision_score(y, s, sample_weight=w), abs=1e-12)
    assert SortedScore(y, s).ap(np.ones(400)) == pytest.approx(average_precision_score(y, s), abs=1e-12)


def test_blocks_and_resamples():
    dates = pd.to_datetime(["2025-07-01", "2025-07-07", "2025-07-08", "2026-08-31"])
    blocks = block_of(dates, "2025-07-01")
    assert list(blocks) == [0, 0, 1, 60]   # 2025-07-01 to 2026-08-31 is 61 blocks of 7 days
    draws = resample_blocks(range(61), n_boot=3, seed=7)
    assert draws.shape == (3, 61) and (draws == resample_blocks(range(61), 3, 7)).all()
    rw = row_weights(blocks, draws[0])
    assert rw[0] == rw[1] == (draws[0] == 0).sum()  # rows of one block move together
    with pytest.raises(ValueError):
        block_of(pd.to_datetime(["2025-06-30"]), "2025-07-01")


def test_evaluate_counts_and_paired_intervals():
    rng = np.random.default_rng(3)
    n = 700
    dates = pd.date_range("2025-07-01", periods=100, freq="D").repeat(7)
    blocks = block_of(dates, "2025-07-01")
    y = rng.random(n) < 0.1
    good = y + rng.normal(0, 0.5, n)     # informative score
    noise = rng.normal(0, 1, n)           # uninformative score
    ref = good > np.quantile(good, 0.9)   # a binary rule with about 70 alerts
    res = evaluate(y, {"good": good, "noise": noise}, ref, blocks, resample_blocks(np.unique(blocks), 200, 1),
                   sustained=y & (rng.random(n) < 0.5), diffs=[("good", "noise")])
    assert res["K"] == int(ref.sum()) and res["positives"] == int(y.sum())
    g = res["methods"]["good"]
    assert g["alerts"] == pytest.approx(res["K"])                 # compared at the reference's load
    assert g["pr_auc_lo"] <= g["pr_auc"] <= g["pr_auc_hi"]
    assert res["methods"]["reference"]["recall_at_load"] == pytest.approx(at_load(y, ref)["recall"])
    d = res["diffs"][("good", "noise")]
    assert d["pr_auc"] > 0 and d["pr_auc_lo"] > 0               # clearly better, paired
    assert res["skipped"] == 0


def test_group_counts_are_counts():
    g = group_counts(["a", "a", "b"], [True, False, True], [1.0, 0.5, 0.0], p_high=[0.6, 0.2, 0.3])
    a = g[g.group == "a"].iloc[0]
    assert (a.rows, a.high, a.alerts, a.tp, a.fp, a.fn) == (2, 1, 1.5, 1.0, 0.5, 0)
    assert a.sum_p_high == pytest.approx(0.8)
