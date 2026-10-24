# The heat forecast's first scheduled night (`coolcheck heat forecast`, job 131450384398104)

Read 24 Oct 2026 in the morning, read-only: the run from `databricks jobs get-run`, the rows from `coolcheck.gold.heat_forecast` through Databricks Connect (serverless, session time zone Asia/Singapore). One night only, not a track record.

## Answer

The forecast for 24 Oct 2026 was written for all 41 areas at **00:49:49 SGT**, 34 min 49 s after the 00:15 cut-off and 5 h 10 min before 06:00.

## The run

| | |
|---|---|
| Job run | 647995027381846, trigger `PERIODIC` (the 00:45 SGT schedule), result `SUCCESS` |
| Run | 00:45:01 to 00:50:02 SGT |
| Task `refresh` (pipeline update) | 00:45:01 to 00:48:23, `SUCCESS` |
| Task `score` | 00:48:24 to 00:50:01, `SUCCESS` |
| Model | `coolcheck.ml.heat_model` version 1, alias champion; MLflow run e6189b13621b46e686d7fce44e25c448; trained on 2025-01-17 to 2026-10-22, so 24 Oct is out of sample (reported by window B from the job output) |

## The rows for 24 Oct

| | |
|---|---|
| Rows | 41 |
| Distinct planning areas | 41 |
| Scored (`p_high` not NULL) | 41 |
| `forecast_missing` | 0 rows |
| `scored_at` | 2026-10-24 00:49:49 SGT, one value for all rows |
| `cutoff_ts` | 2026-10-24 00:15:00 SGT, one value for all rows |
| `model_version` | 1 |
| `run_id` | 647995027381846 |

The table also holds 41 rows for 23 Oct, from job run 675333288811564, a one-time run with `target_date` 2026-10-23 scored at 21:52:20 SGT on 23 Oct. It was not the schedule and is not a publication time.

## Query

```sql
SELECT target_date, count(*) n_rows, count(DISTINCT planning_area) n_areas, count(p_high) n_scored,
       count_if(forecast_missing) n_fc_missing, min(scored_at) min_scored, max(scored_at) max_scored,
       min(cutoff_ts) min_cut, max(cutoff_ts) max_cut, collect_set(model_version) versions, collect_set(run_id) runs
FROM coolcheck.gold.heat_forecast GROUP BY target_date ORDER BY target_date
```
