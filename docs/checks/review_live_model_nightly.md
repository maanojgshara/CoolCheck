# Independent review: the live model and the nightly heat forecast

Reviewed 24 Oct 2026 by window D (Guide §A3, Saturday): commits `e6cd561` (live model refit, nightly scoring, tests), `0660e9f` (the two job files renamed from `.draft`) and `490f2f3` (schedule unpaused on dev, kept paused on the free target). Window B wrote them.

## How

- Read every changed file: `src/coolcheck/live_model.py`, `live_registry.py`, `heat_model.py`, `src/jobs/live_model.py`, `src/jobs/heat_forecast.py`, `resources/live_model.job.yml`, `resources/heat_forecast.job.yml`, `databricks.yml`, `tests/backtest/test_live_model.py` and `test_live_model_mlflow.py`, and the helpers they call (`check_git_sha`, `pin_version`, `check_feature_cutoffs`, `assert_completed_days`); `docs/checks/collector_catch_up.md` for the midnight sweep.
- `pytest tests/backtest/test_live_model.py tests/backtest/test_live_model_mlflow.py` in `.venv`: 11 passed, 1 skipped (the MLflow file skips there by design; it runs in a throwaway venv).
- Nothing was run in the workspace. The first scheduled run (24 Oct 00:45 SGT, job run 647995027381846, 41 rows, `scored_at` 00:49:49 SGT) is taken from window B's read-only check.

## Verdict

No blocking bug. Checked and sound:
- **Writes:** a rerun's MERGE on (target_date, planning_area) replaces the date's rows, and the read-back checks 41 rows, the scored count, NaN, the probability sums and one model version and job run.
- **Date:** the target date comes from the wall clock at UTC+08:00, not the Spark session; a future date or one before the first target date is refused.
- **Model:** loaded by the version number the `champion` alias points to when the run starts; the High cut-off is recorded, never re-derived; a date the model trained on is labelled in-sample.
- **Missing data:** an area whose station has no feature row is kept with NULL probabilities and listed, not an error.
- **Schedule:** the explicit `UNPAUSED` holds in development mode (the 00:45 run on 24 Oct ran).
- **The registered model** is self-contained (`heat_model.py`), and the tests pin its preparation equal to the back-test functions, including a missing forecast and an unseen forecast text.

## Findings (all open; routed to windows B and A by the user)

| # | Severity | Finding | Suggested fix | Status |
|---|---|---|---|---|
| 1 | Medium | Nothing records whether the previous day's data was complete when the job scores. `check_feature_cutoffs` and `assert_completed_days` catch inputs that are too late, never inputs that are missing. The previous day's holes are filled by the collector's midnight sweep (four runs, 00:00 to 00:59 SGT); the 00:45 refresh can start before a delayed sweep run has landed, and the day is then scored from a day with holes, without a warning. | Print `silver.dq_day` for the day before the target date in the score task's log, and optionally each station's latest input time (`inputs_max_ts`). A few lines; no result changes. | Open |
| 2 | Medium | One failed night quietly shows the previous day's briefing. Neither task retries (`score` has `max_retries: 0`; `refresh` has no retry setting), so one transient pipeline error means no forecast that day, and only the failure e-mail says so. The App defaults to the latest date in `gold.area_heat_risk`, so on 24 Oct it would show 23 Oct's plan without saying so. | One retry on `refresh`, 5 minutes apart. `score` can retry safely too, because its MERGE replaces the rows. The App and the briefing say "no forecast for today" when the latest date is before today in SGT. | Open |
| 3 | Low | If `register_model` succeeds but setting the alias (or a tag) then fails, `refuse_if_registered` blocks a second refit ("already has version(s)…"), and the nightly job fails on `get_model_version_by_alias`. Relevant to window A's run of `live_model` on Free Edition. | Write the recovery down: set the alias by hand on the registered version (`client.set_registered_model_alias`), then rerun the nightly job. | Open |
| 4 | Low | After `490f2f3`, Free Edition's `heat_forecast` (beside `latest_readings`) stays paused. Once a champion is registered there, unpausing needs a commit and a deploy. | Add it to window A's list for the 4 Nov finale. | Open |
| 5 | Low | The MLflow test of the missing-forecast path uses `mlflow-skinny` 2.22.0, and only some rows lack a forecast. A night where every station lacks one (the `fc_text` column all None) has not been run against the MLflow version in the job's serverless environment (environment version 4). | A one-off check in the workspace: load the champion and predict on one feature row with the forecast removed. | Open |
