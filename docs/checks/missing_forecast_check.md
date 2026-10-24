# The champion on a night with no forecast (review finding 5)

Run once on 24 Oct 2026, 23:47:19 to 23:48:45 SGT, window A, on the trial: one-time run 1017034183079241 (task run 969239703829774, `databricks jobs submit`, not a bundle resource), result `SUCCESS`. Script: `scripts/checks/missing_forecast_check.py`, uploaded to a scratch folder of the user's workspace for the run and deleted afterwards. Read-only: nothing was written to a table or to the registry; no pipeline update ran.

## Answer

The registered champion predicts a night where every station lacks the forecast (`fc_text` all None, `fc_temp_high` all NaN) in the nightly job's own serverless environment, and the result equals the training fill written in by hand: the largest difference is 0. Finding 5 of `docs/checks/review_live_model_nightly.md` is closed by this run.

## Setup

| | |
|---|---|
| Environment | serverless environment version 4 with `lightgbm==4.6.0`, as `resources/heat_forecast.job.yml`: MLflow 2.22.0, pandas 2.2.3, numpy 2.1.3, LightGBM 4.6.0, Python 3.12.3 |
| Code | the dev bundle's deployed `src` (commit `7f1ec30`; the nightly code is unchanged from there to `0224782`), read by the script for the feature builder |
| Model | `coolcheck.ml.heat_model` version 1 through the alias `champion`, model sha256 `715d7f887dced8282c42ec59fb1938e3ff0de73c3ffe00ec21c37b4d34b53060` |
| Rows | the 30 station rows for target date 2026-10-24, built as the nightly job builds them; none lacked a forecast that day |

## Results

| Check | Result |
|---|---|
| 1. The rows as they are | 30 rows, no NaN, probabilities sum to 1 (largest gap 2.2e-16); equal to `gold.heat_forecast` for 24 Oct on the 22 stations the areas use (largest difference 0) |
| 2. One row with its forecast removed | 1 row, no NaN, sums to 1 |
| 3. Every row with its forecast removed (`fc_text` all None, dtype object) | 30 rows, no NaN, sums to 1 |
| 4. The October fill by hand (`fc_temp_high` 34.0, `fc_text` "Thundery Showers", `forecast_missing` False) | 30 rows; checks 2 and 3 equal it exactly (largest difference 0) |

The model's input signature accepts a text column that is entirely None, and the fill inside the model is applied as in training.

One limit: on 24 Oct the actual forecast equalled the October fill, so removing it did not move the probabilities (largest change in P(High) 0). The check still shows that a night without a forecast runs and gets the fill; it does not show how much a missing forecast moves a night whose forecast differs from the fill.
