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

## The tier view over those rows

Read 24 Oct 2026, read-only, through Databricks Connect. `coolcheck.gold.area_heat_risk` is a view (`src/coolcheck/risk.py`, `area_heat_risk_sql`) over `gold.heat_forecast`. It has 41 rows for 41 areas on each of 23 and 24 Oct (23 Oct is the manual run above). The view holds no probability column and no score: its columns are `target_date`, `planning_area`, `planning_area_code`, `region`, `station_id`, `heat_level`, `rated`, `third`, `tier`, `tier_rank`, `tier_sentence`, `reason`, `actions`, `actions_status`, `small_hdb`, `small_residents`, `small_aged_65`, `forecast_missing`, `model_version`, `run_id`, `cutoff_ts` and `scored_at`.

The tables it joins: `gold.area_vulnerability` 32 rows, `gold.block_vulnerability` 10,817 rows, `gold.score_weights` 7 rows, `gold.tier_actions` 4 rows.

Areas on 24 Oct by heat level and vulnerability third, with the tier the view gave. Every cell is the main 3×3 rule (`design/risk_score.md`, §6):

| heat level | third | tier | areas |
|---|---|---|---|
| High | upper | High | 1 |
| High | lower | Medium | 1 |
| High | not rated | Not rated | 2 |
| Moderate | middle | Medium | 11 |
| Moderate | upper | Medium | 10 |
| Moderate | lower | Low | 9 |
| Moderate | not rated | Not rated | 7 |

By tier: High 1, Medium 22, Low 9, Not rated 9, 41 areas in all. One night, not a track record.

```sql
SELECT heat_level, third, tier, count(*) AS n
FROM coolcheck.gold.area_heat_risk WHERE target_date = DATE'2026-10-24' GROUP BY ALL ORDER BY 1, 2, 3
```

## Cost of the run

Read 24 Oct 2026 through `system.billing.usage` joined to `system.billing.list_prices` (list price, US$0.39 a DBU, SKU `PREMIUM_JOBS_SERVERLESS_COMPUTE_AP_SINGAPORE`), as in `checks/latest_readings_cost.md`. Billing ended at 16:00 SGT on 24 Oct when read, so both runs are fully billed. The job's own compute is billed under the job run ID, and the pipeline update of the `refresh` task under its own update ID, so each night has two parts.

| run | job compute (DBU) | pipeline update (DBU) | total (DBU) | US$ at list price |
|---|---|---|---|---|
| Scheduled, 24 Oct 00:45 SGT (job run 647995027381846, update 910b793c-e939-47a4-93d5-6779751c8dbb) | 0.447 | 0.472 | 0.919 | 0.358 |
| Manual, 23 Oct about 21:47 SGT (job run 675333288811564, update 5b2c733e-c55b-4cf1-bbc1-1f984b494a83) | 0.617 | 0.529 | 1.146 | 0.447 |

- Two runs, so no daily average or monthly total is claimed.
- Not counted here: the App, which bills while it runs, and the SQL warehouse behind the dashboard and the App. The App's cost is to be read from billing once it has run a day.
- The scheduled run's job-compute rows are hour-binned: 0.018 DBU from 00:00 to 01:00, 0.062 from 00:40 to 00:50 and 0.367 from 00:50 to 01:00, summed to 0.447.

```sql
SELECT u.usage_metadata.job_run_id, u.usage_metadata.dlt_update_id, u.usage_start_time, u.usage_end_time,
       u.usage_quantity, u.usage_quantity * p.pricing.default AS usd_list
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
  ON u.sku_name = p.sku_name AND u.cloud = p.cloud AND u.usage_end_time >= p.price_start_time
 AND (p.price_end_time IS NULL OR u.usage_end_time < p.price_end_time)
WHERE u.usage_metadata.job_run_id IN ('647995027381846', '675333288811564')
   OR u.usage_metadata.dlt_update_id IN ('910b793c-e939-47a4-93d5-6779751c8dbb', '5b2c733e-c55b-4cf1-bbc1-1f984b494a83')
ORDER BY u.usage_start_time
```
