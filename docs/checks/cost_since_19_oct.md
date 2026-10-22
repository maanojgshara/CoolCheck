# Cost since 19 Oct 2026, by product (trial workspace)

Source: `system.billing.usage` joined to `system.billing.list_prices` (default list price per SKU), read 22 Oct 2026 at about 16:40 SGT. Days are `usage_date`, which is UTC. The table's latest day is 21 Oct (usage ends 22 Oct 00:00 UTC), so nothing for 22 Oct is in yet. Prices are list prices, not the credit actually drawn.

| Day (UTC) | Product | Quantity | Unit | List price (US$) |
|---|---|---|---|---|
| 19 Oct | Interactive (serverless) | 0.653 | DBU | 0.54 |
| 19 Oct | Jobs (serverless) | 0.421 | DBU | 0.16 |
| 19 Oct | Predictive optimization | 0.134 | DBU | 0.05 |
| 19 Oct | Default storage | 0.068 | DSU | 0.00 |
| 19 Oct | Genie (free usage) | 0.280 | DBU | not priced |
| 20 Oct | SQL (serverless warehouse) | 2.193 | DBU | 1.93 |
| 20 Oct | Default storage | 0.036 | DSU | 0.00 |
| 20 Oct | Genie (free usage) | 4.740 | DBU | not priced |
| 21 Oct | SQL (serverless warehouse) | 5.592 | DBU | 4.92 |
| 21 Oct | Interactive (serverless) | 3.791 | DBU | 3.15 |
| 21 Oct | Pipelines (DLT) | 3.184 | DBU | 1.24 |
| 21 Oct | Jobs (serverless) | 1.458 | DBU | 0.57 |
| 21 Oct | Predictive optimization | 0.814 | DBU | 0.32 |
| 21 Oct | Default storage | 2.558 | DSU | 0.06 |
| 21 Oct | Model serving | 0.017 | DBU | 0.00 |
| 21 Oct | AI Gateway | 0.000 | DBU | 0.00 |
| 21 Oct | Genie (free usage) | 0.189 | DBU | not priced |

| Day (UTC) | Total list price (US$) |
|---|---|
| 19 Oct | 0.76 |
| 20 Oct | 1.93 |
| 21 Oct | 10.26 |
| **19 to 21 Oct** | **12.95** |

- Genie usage is the SKU `GENIE_FREE_USAGE`, which has no list price, so it adds nothing here.
- Pipelines (DLT) usage first appears on 21 Oct, the day the pipeline was built and first run; SQL and Interactive also rise that day. This table does not split usage by job or notebook, so the rise is not attributed further.
- Rows for 16 to 18 Oct exist but total US$0.00.

## Setup status (22 Oct 2026)

- SQL warehouse auto-stop: already 10 minutes on `Serverless Starter Warehouse` (the only warehouse); no change made.
- Databricks secret scope: not created. Deferred until something needs it: no Databricks job calls an external API (the workspace cannot reach them) and the collector's secrets are in GitHub Actions.
