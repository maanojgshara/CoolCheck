# The live model (`coolcheck.ml.heat_model`, version 1)

Read 24 Oct 2026, read-only: the MLflow run through `databricks experiments get-run`, the alias through `databricks model-versions get-by-alias`, and the final check's settings from `checks/final_check.md`. Nothing was run or changed. The refit itself is `src/jobs/live_model.py` (run 230292292912810, 23 Oct 2026), registered by `src/coolcheck/live_registry.py`.

## Answer

The live model is the final check's configuration refit on more days. It is a different fitted model, and no result is reported for it.

| | live model | final check's model |
|---|---|---|
| Target dates trained on | 2025-01-17 to 2026-10-22 | 2025-01-17 to 2026-08-31 |
| Station-days | 10,861 | 9,308 |
| High station-days | 538 | 465 |
| High rate | 0.049535 | 0.049957 (465 of 9,308) |
| Model sha256 | `715d7f887dced8282c42ec59fb1938e3ff0de73c3ffe00ec21c37b4d34b53060` | `d614c3bc959ad16781158acf8fa2aa5114be4043305244fbe4674435750f1f64` |

- The live model trained on 1,553 more station-days than the final check's model, 73 of them High.
- The High rate lies inside the range the back-test folds' training sets had, 150 of 5,388 to 390 of 7,682 (`src/coolcheck/live_model.py`, `FOLD_RATES`), which is the guard the registration applied.
- The settings are the same. Compared in this read: the 11 features and the fixed LightGBM parameters equal the final check's (`checks/final_check.md`, Settings), `num_leaves` 7, 150 rounds, and the alert cut-off 0.10975585695894975. The forecast fill and the text categories are fitted again on the new training rows.

## What was read

| | |
|---|---|
| MLflow run | `e6189b13621b46e686d7fce44e25c448`, name `live_model`, `role` = live_model, FINISHED, experiment 2219956337470140, logged 23 Oct 2026 21:46 SGT |
| Registered model | `coolcheck.ml.heat_model`, version 1, READY |
| Alias | `champion` points to version 1, run `e6189b13621b46e686d7fce44e25c448` |
| Git | `0660e9f332fb427decb2eb1b6904f802681e6c6b` |
| Code sha256 | `a7e9c1f6dcfdb55552932c1edebeb9578c095e8a6031b7c4a5506a2c197af223` |
| `training_window` | 2025-01-17..2026-10-22 |
| `train_rows`, `train_high`, `train_high_rate` | 10861, 538, 0.049535 |
| Packages | python 3.12.3, pandas 2.2.3, numpy 2.1.3, scikit-learn 1.6.1, lightgbm 4.6.0, mlflow 2.22.0, scipy 1.15.1, pyarrow 19.0.1 (the same as the final check's) |

## Not reported

- No score for the live model: it has no held-out weeks. Its first target date, 24 Oct 2026, is out of sample, and no outcome has been compared with it.
- 1 Sep to 19 Oct 2026 is in its training window, so the final check's numbers do not describe it (`checks/final_check.md` scores the model fitted to 31 Aug 2026).
- It is fitted once, to 22 Oct. It is not refit as days complete.

## A refit elsewhere does not give the same file

Window A's Free Edition run of 24 Oct refit it with the same code sha256, packages, input checksums and training counts (10,861 station-days, 538 High). It gave a different model file: sha256 `ae8fe0f9307ae16a100ec0c322bb2bff538466b43f7cc39879be23711e2db273` against this one's `715d7f88…`. On 23 and 24 Oct its P(High) differed from this model's by at most 0.0047 for any area, and no heat level or tier changed (`checks/free_edition_chain.md`, The model). Why it differs is not tested.

## Corrected

- 24 Oct, about 23:45 SGT: this note's first version gave the model sha256 with two characters missing (`715d887d…`, 62 characters: the `7f` after `715d` was dropped). Read again from the MLflow run's `model_sha256` value, it is `715d7f88…`, as in the table above.
