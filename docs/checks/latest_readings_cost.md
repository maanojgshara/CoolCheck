# Cost of the latest-readings job (`coolcheck latest readings`, job 997063708299006)

Read 23 Oct 2026 at about 15:35 SGT (window A), read-only, through the Serverless Starter Warehouse. Source: `system.billing.usage` filtered on `usage_metadata.job_id`, joined to `system.billing.list_prices` (default list price per SKU, valid at the usage time). Run times are from `databricks jobs list-runs`. Prices are list prices, not the credit actually drawn.

## Answer

| | DBU | US$ at list price |
|---|---|---|
| Per run (mean of 18 billed runs) | 0.363 | 0.142 |
| Per run, range | 0.337 to 0.406 | 0.131 to 0.158 |
| A day at hourly runs (24 × the mean) | 8.71 | 3.40 |
| A day at every 15 minutes (96 × the mean; estimate) | 34.86 | 13.59 |

- SKU `PREMIUM_JOBS_SERVERLESS_COMPUTE_AP_SINGAPORE`, US$0.39 per DBU.
- The 15-minute figure assumes every run costs what an hourly run costs. Each run reads the same 3-hour window of live files whatever the interval, so a shorter interval should not make a run smaller. It is an estimate, not a measurement.
- At that rate, 30 days at every 15 minutes would be about US$408, more than the whole US$400 trial credit. Hourly is about US$102 for 30 days.

## What was measured

- The job ran 21 times, every hour at :05 SGT from 22 Oct 19:05 to 23 Oct 15:05, all scheduled and all successful. Wall time 61 to 84 s per run.
- Billing had rows for the first 18 runs, to the 12:05 run on 23 Oct. Billing data ended at 23 Oct 12:10 SGT (04:10 UTC), about 3.5 hours behind. The newest row may still be revised.
- No full billing day exists yet: `usage_date` 22 Oct (UTC, 08:00 to 08:00 SGT) holds the 13 runs from 19:05 to 07:05 SGT, 4.76 DBU and US$1.86. The daily figures above are therefore 24 and 96 times the per-run mean, not a measured day.

| Run start (SGT) | DBU | US$ |
|---|---|---|
| 22 Oct 19:05 | 0.367 | 0.143 |
| 22 Oct 20:05 | 0.370 | 0.144 |
| 22 Oct 21:05 | 0.388 | 0.151 |
| 22 Oct 22:05 | 0.347 | 0.135 |
| 22 Oct 23:05 | 0.348 | 0.136 |
| 23 Oct 00:05 | 0.351 | 0.137 |
| 23 Oct 01:05 | 0.406 | 0.158 |
| 23 Oct 02:05 | 0.364 | 0.142 |
| 23 Oct 03:05 | 0.384 | 0.150 |
| 23 Oct 04:05 | 0.350 | 0.137 |
| 23 Oct 05:05 | 0.352 | 0.137 |
| 23 Oct 06:05 | 0.378 | 0.148 |
| 23 Oct 07:05 | 0.354 | 0.138 |
| 23 Oct 08:05 | 0.370 | 0.144 |
| 23 Oct 09:05 | 0.366 | 0.143 |
| 23 Oct 10:05 | 0.350 | 0.137 |
| 23 Oct 11:05 | 0.353 | 0.138 |
| 23 Oct 12:05 | 0.337 | 0.131 |
| **18 runs** | **6.536** | **2.549** |

## Query

```sql
SELECT u.usage_metadata.job_run_id AS run_id, min(u.usage_start_time) AS start_utc, max(u.usage_end_time) AS end_utc,
       u.usage_date, u.sku_name, u.usage_unit, sum(u.usage_quantity) AS qty,
       sum(u.usage_quantity * p.pricing.default) AS usd_list
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
  ON u.sku_name = p.sku_name AND u.cloud = p.cloud AND u.usage_end_time >= p.price_start_time
 AND (p.price_end_time IS NULL OR u.usage_end_time < p.price_end_time)
WHERE u.usage_metadata.job_id = '997063708299006'
GROUP BY ALL ORDER BY start_utc
```
