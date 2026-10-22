"""The fold loop and its guards (docs/design/backtest.md §5, §8.1) on synthetic station-days; one Spark test for the
label loader."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from backtest_fixtures import labels_of, synthetic_rows
from coolcheck.backtest import (FOLDS, HP_CANDIDATES, assert_before_holdout, assert_fold, backtest_labels,
                                choose_config, encode, fit_forecast_fill, fit_lgb, fit_nea_threshold, fold_split,
                                apply_forecast_fill, run_folds, same_month_last_year, station_day_rows)
from coolcheck.features import FEATURES


def test_fourteen_folds_jul_2025_to_aug_2026():
    assert len(FOLDS) == 14 and FOLDS[0] == pd.Timestamp("2025-07-01") and FOLDS[-1] == pd.Timestamp("2026-08-01")


def test_fold_split_boundaries():
    rows = synthetic_rows()
    for m in FOLDS:
        tr, te = fold_split(rows, m)
        assert tr.target_date.max() < m <= te.target_date.min()
        assert te.target_date.max() < m + pd.offsets.MonthBegin(1)


def test_a_training_row_on_the_fold_start_is_caught():
    rows = synthetic_rows()
    tr, te = fold_split(rows, FOLDS[3])
    with pytest.raises(AssertionError, match="on or after the fold start"):
        assert_fold(pd.concat([tr, te.head(1)]), te, FOLDS[3])


def test_a_date_after_2026_08_31_never_reaches_a_fold():
    rows = synthetic_rows()
    late = rows.groupby("station_id").tail(1).assign(target_date=pd.Timestamp("2026-09-01"))  # one per station
    bad = pd.concat([rows, late], ignore_index=True)
    with pytest.raises(AssertionError, match="after 2026-08-31"):
        run_folds(bad, labels_of(rows), folds=FOLDS[:1])        # a row in the final-check window
    with pytest.raises(AssertionError, match="after 2026-08-31"):
        run_folds(rows, labels_of(bad), folds=FOLDS[:1])        # a label in the final-check window
    with pytest.raises(AssertionError, match="after 2026-08-31"):
        fold_split(bad, pd.Timestamp("2026-09-01"))              # a 15th fold would score the final check
    with pytest.raises(AssertionError, match="after 2026-08-31"):
        station_day_rows(bad.drop(columns=["y", "label_n_high"]),
                         bad[["station_id", "target_date", "y"]].assign(n_high=0))
    with pytest.raises(AssertionError, match="after 2026-08-31"):
        assert_before_holdout(late, "a training frame")


def test_backtest_labels_stop_at_2026_08_31(spark):
    labels = spark.createDataFrame([("S1", date(2026, 8, 31), "High", True, 3), ("S1", date(2026, 9, 1), "High", True, 3)],
                                   "station_id STRING, sgt_date DATE, label STRING, usable BOOLEAN, n_high LONG")
    got = [r.target_date for r in backtest_labels(labels, date(2026, 10, 23)).collect()]
    assert got == [date(2026, 8, 31)]


def test_forecast_fill_by_month_with_fallback():
    def block(month, n, t, x):
        return [{"target_date": pd.Timestamp(2025, month, 1 + i), "fc_temp_high": t, "fc_text": x,
                 "forecast_missing": False} for i in range(n)]
    train = pd.DataFrame(block(4, 12, 34.0, "Thundery Showers") + block(7, 5, 31.0, "Showers")
                         + block(9, 30, 32.0, "Partly Cloudy (Day)"))
    fill = fit_forecast_fill(train)
    assert fill["by_month"] == {4: (34.0, "Thundery Showers"), 9: (32.0, "Partly Cloudy (Day)")}  # July: 5 dates
    assert fill["overall"] == (32.0, "Partly Cloudy (Day)")
    test = pd.DataFrame({"target_date": pd.to_datetime(["2026-04-29", "2026-07-21"]), "fc_temp_high": [np.nan] * 2,
                         "fc_text": [None] * 2, "forecast_missing": [True] * 2})
    out, filled = apply_forecast_fill(test, fill)
    assert list(zip(out.fc_temp_high, out.fc_text)) == [(34.0, "Thundery Showers"), (32.0, "Partly Cloudy (Day)")]
    assert list(filled.source) == ["calendar month", "all training dates"]


def test_test_month_values_change_no_fill_and_no_threshold():
    rows = synthetic_rows()
    m = pd.Timestamp("2026-04-01")
    in_m = (rows.target_date >= m) & (rows.target_date < pd.Timestamp("2026-05-01"))
    changed = rows.copy()
    changed.loc[in_m & ~changed.forecast_missing, "fc_temp_high"] = 40.0
    changed.loc[in_m, "y"] = 2
    a = run_folds(rows, labels_of(rows), folds=[m], ablations=False)
    b = run_folds(changed, labels_of(rows), folds=[m], ablations=False)
    assert a[2].equals(b[2])                                                   # the filled dates and values
    assert a[1].nea_theta.iloc[0] == b[1].nea_theta.iloc[0]


def test_nea_threshold_ties_go_to_the_higher_value():
    # at 33: 2 TP and 2 FP (F1 2/3); at 34: 1 TP, 0 FP, 1 FN (F1 2/3)
    theta, f1 = fit_nea_threshold(pd.DataFrame({"fc_temp_high": [33.0, 33.0, 33.0, 34.0], "y": [0, 0, 2, 2]}))
    assert theta == 34.0 and f1 == pytest.approx(2 / 3)


def test_same_month_last_year():
    lab = [("A", pd.Timestamp(2025, 3, d), 2 if d <= 5 else 0) for d in range(1, 21)]           # 20 days, 5 High
    lab += [("B", pd.Timestamp(2025, 3, d), 2) for d in range(1, 11)]                            # 10 days: too few
    lab += [(s, pd.Timestamp(2025, 3, d), 2 if d == 1 else 0) for s in ("S124", "S125") for d in range(1, 31)]
    lab += [("A", pd.Timestamp(2026, 3, 2), 2)]                                                  # the test month itself
    labels = pd.DataFrame(lab, columns=["station_id", "target_date", "y"])
    test = pd.DataFrame({"station_id": ["A", "B", "C"], "target_date": [pd.Timestamp("2026-03-10")] * 3})
    got = same_month_last_year(labels, test, pd.Timestamp("2026-03-01"))
    assert list(got) == pytest.approx([0.25, 2 / 60, 2 / 60])   # own share; else the panel's (2 High of 60)
    assert same_month_last_year(labels, test, pd.Timestamp("2026-01-01")).isna().all()


def _history(scores_by_candidate, dates, y):
    h = pd.DataFrame({"target_date": dates, "y": y})
    for i, s in enumerate(scores_by_candidate):
        h[f"p_high_c{i}"] = s
    return h


def test_per_fold_choice_uses_earlier_folds_only():
    jul = pd.date_range("2025-07-01", periods=6)
    y = [2, 0, 2, 0, 0, 0]
    perfect, poor = [0.9, 0.1, 0.8, 0.2, 0.3, 0.1], [0.1, 0.9, 0.2, 0.8, 0.3, 0.1]
    h = _history([poor, poor, perfect, poor], jul, y)
    assert choose_config(None, FOLDS[0])[0] == 0                       # the first fold takes the smallest
    assert choose_config(h, FOLDS[1])[0] == 2
    aug = _history([perfect, poor, poor, poor], pd.date_range("2025-08-01", periods=6), y)
    assert choose_config(pd.concat([h, aug]), FOLDS[1])[0] == 2       # fold M's own rows are not used
    # an earlier fold's rows are used: Jul favours candidate 2 and Aug candidate 0 by the same margin, a tie
    assert choose_config(pd.concat([h, aug]), FOLDS[2])[0] == 0
    tie = _history([poor, perfect, poor, perfect], jul, y)
    assert choose_config(tie, FOLDS[1])[0] == 1                       # ties go to the smaller candidate
    with pytest.raises(AssertionError, match="after 2026-08-31"):
        choose_config(_history([perfect] * 4, pd.date_range("2026-09-01", periods=6), y), pd.Timestamp("2026-10-01"))


def test_lightgbm_fit_repeats_exactly():
    rows = synthetic_rows()
    tr, te = fold_split(rows, FOLDS[0])
    fill = fit_forecast_fill(tr)
    tr, _ = apply_forecast_fill(tr, fill)
    te, _ = apply_forecast_fill(te, fill)
    cats = sorted(tr.fc_text.dropna().unique())
    p1 = fit_lgb(encode(tr, cats), tr.y.to_numpy(), *HP_CANDIDATES[0]).predict(encode(te, cats))
    p2 = fit_lgb(encode(tr, cats), tr.y.to_numpy(), *HP_CANDIDATES[0]).predict(encode(te, cats))
    assert np.array_equal(p1, p2) and p1.shape == (len(te), 3)


def test_run_folds_on_two_folds():
    rows = synthetic_rows()
    pooled, records, fills, boosters = run_folds(rows, labels_of(rows), folds=FOLDS[:2])
    assert set(pooled.fold) == {FOLDS[0], FOLDS[1]} and pooled.target_date.max() < FOLDS[2]
    assert len(pooled) == len(rows[(rows.target_date >= FOLDS[0]) & (rows.target_date < FOLDS[2])])
    assert records.config.iloc[0] == 0 and (records.train_last_date < records.fold).all()
    np.testing.assert_allclose(pooled[["p_low", "p_moderate", "p_high"]].sum(axis=1), 1.0)
    assert (pooled.persist_alert == (pooled.n_high_d1.fillna(0) >= 1)).all()
    assert pooled.same_month_score.isna().all()                     # defined from Feb 2026 only
    assert {"p_high_no_char", "p_high_wo3", "p_high_recency"} <= set(pooled.columns)
    assert len(boosters) == 2 * (len(HP_CANDIDATES) + 3)
    assert pd.Timestamp("2025-07-21") in set(fills[fills.split == "test"].target_date)
    assert set(FEATURES) <= set(rows.columns)
