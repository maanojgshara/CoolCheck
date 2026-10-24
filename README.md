# CoolCheck

Next-day heat briefing for community care teams in Singapore (DAISI Round 2, team AIsenal, problem B1 HeatGuard).

**Status on 24 Oct 2026.** Built so far: the four live feeds, the pipeline from raw files to Silver, the live page, the back-test (`docs/checks/backtest.md`), the refuge and park access measures, the risk score and tiers, the live model and the nightly forecast (a job at 00:45 SGT, first scheduled run on 24 Oct), and the agent's three tools as Unity Catalog functions. Not built yet: the briefing dashboard, the agent loop and the approval App, the four languages and the evaluations (placeholders below). All times are Singapore time (SGT).

## Live feeds

The collector fetches four NEA feeds from data.gov.sg's real-time API:

| feed | title on data.gov.sg | readings | used for |
|---|---|---|---|
| WBGT heat stress (`weather?api=wbgt`) | not confirmed yet (`docs/attribution.md`, flag 3) | every 15 minutes, per station | the model's label and heat input; the live page |
| Rainfall | Rainfall across Singapore | every 5 minutes, per station | model input; the live page |
| 24-hour weather forecast | 24-hour Weather Forecast | NEA's island-wide forecast, a forecast rather than a reading stream | model input |
| Air temperature | Air Temperature across Singapore | every minute, per station | the live page only |

The collector (`scripts/collector/collect.py`, run by `.github/workflows/collector.yml`) runs on GitHub Actions, outside Databricks, because Databricks serverless cannot reach `.gov.sg` hosts. It uploads the raw responses to the Unity Catalog Volume `coolcheck.bronze.raw_files`, under `<feed>/live/<date>/`. Each run writes new files (the run id is in the name) and never overwrites one, because Auto Loader reads a path once. A run re-fetches the last 2 hours, and a run between 00:00 and 00:59 also re-reads all of yesterday for WBGT, rainfall and the forecast; air temperature has no such sweep. The history from 16 Jan 2025 for WBGT, rainfall and the forecast came from a backfill (`scripts/backfill/backfill.py`), under `<feed>/backfill/`.

## How the collector is started

- **cron-job.org** calls the workflow's `workflow_dispatch` API every 15 minutes, at :00, :15, :30 and :45, with `dry_run` false. It uses a fine-grained token limited to this repository's Actions. Only the scheduler holds that token; it is not stored in the repository or in the Actions secrets.
- **GitHub's own schedule** (`schedule:` in the workflow, at minutes 4, 19, 34 and 49) is kept as a second start. It is best effort: GitHub starts only a fraction of the slots, so it cannot be relied on alone. When both fire, the extra files are harmless, because Silver deduplicates.
- **One switch:** the repository variable `COLLECTOR_ENABLED`. Scheduled runs and real dispatches (`dry_run` false) run only while it is `true`; set it to `false` to stop both. A manual dispatch with `dry_run` true (the default) always runs, writes files on the runner only and uploads nothing.
- **Manual catch-up:** a dispatch can set `window_hours` up to 48; air temperature is capped at 12 hours.

The workflow reads the data.gov.sg API key and the service principal's OAuth client ID and secret from the Actions secrets `DATA_GOV_SG_API_KEY`, `DATABRICKS_CLIENT_ID` and `DATABRICKS_CLIENT_SECRET`, and the workspace host and the Volume path from the repository variables `DATABRICKS_HOST` and `COLLECTOR_VOLUME_ROOT`. No value is stored in the repository.

## Where the data lives

The pipeline, the jobs, the MLflow experiment and the live page are deployed from this repository by the bundle in `databricks.yml` (target `dev`). In that target every deployed job, pipeline and dashboard name starts with `[dev <user>]`. The Volume and the tables loaded by local scripts are created by those scripts, not by the bundle. The Unity Catalog catalog is `coolcheck` (the bundle variable `catalog`), with schemas `bronze`, `silver`, `gold` and `ml` (the registered model `heat_model`).

- **Volume** `coolcheck.bronze.raw_files`: the raw responses from the backfill and the collector.
- **Bronze**, one row per API page, loaded by Auto Loader in the Lakeflow pipeline `coolcheck_pipeline` (`src/pipeline/`, serverless, triggered): `bronze.wbgt_raw`, `bronze.rainfall_raw`, `bronze.forecast_raw`, `bronze.air_temperature_raw`.
- **Silver**, from the same pipeline:
  - every parsed copy, with a `fail_<rule>` flag per quality rule: `wbgt_readings_all`, `rainfall_readings_all`, `air_temperature_readings_all`, `forecast_issues_all`;
  - deduplicated: `wbgt_readings`, `rainfall_readings`, `air_temperature_readings`, `forecast_issues`, and `forecast_periods` (forecast issues by period and region);
  - `station_daily_label`: each station's highest NEA heat-stress category of the day (Low, Moderate or High);
  - data quality: `quarantine`, `dq_day`, `dq_events`, `dq_conflicts`, `station_gaps`, `wbgt_first_arrival`, and `dq_reconcile` (written by the `reconcile` job).
- **Silver, loaded by local scripts:** `area_station_distance` (planning-area to station distances, `scripts/static/area_station_distance.py`), `area_exposure` (residents, and those aged 65+ and 75+, per planning area, `scripts/static/load_area_exposure.py`), and the four access tables from `scripts/static/load_refuge_park_access.py`: `refuge_points` and `park_polygons` (the refuge and park layers), `block_access` (per HDB block) and `area_access` (per planning area).
- **Gold:** `gold.latest_readings` and `gold.stream_status`, refreshed from the live files in the Volume by the `latest_readings` job (hourly at :05), which fails, and so e-mails the user who deployed it, when the newest WBGT reading is over 90 minutes old; `gold.area_nearest_station_daily`, the nearest reporting WBGT station per planning area and day (a view created by `src/jobs/nearest_station.py`). The forecast and risk tables are under Risk score and Tiers below.

The pipeline runs in triggered mode: Bronze and Silver move only when an update is started.

## The live page

The AI/BI dashboard **CoolCheck live heat stress** (`src/dashboards/live_heat_stress.lvdash.json`, deployed through `resources/live_heat_stress.dashboard.yml`) shows the newest readings of three feeds: WBGT stations on a map, coloured by NEA's heat-stress category; rain per station, labelled "Rain in the hour to" the end of the rainfall window; and air temperature (shown live only, not a model input). It reads only `gold.latest_readings` and runs on the existing Serverless Starter Warehouse. A station shows "no recent reading" when it has no reading in the hour before the table's last refresh. When that refresh is more than 90 minutes old, a banner says so and every station shows "no recent reading". In the workspace it is in the Dashboards list as `[dev <user>] CoolCheck live heat stress`.

## Risk score

The vulnerability index **V** ranks the 32 planning areas that have at least one confirmed HDB block. It says how many seniors an area has, how likely they are to be unable to cool down at home, and how far they are from a cooling refuge. It says nothing about heat. Design: `docs/design/risk_score.md`. Back-test counts, reach and sensitivity runs: `docs/checks/risk_score.md`. The rules are in `src/coolcheck/risk.py`, written once in Python and once as the SQL of the views; `tests/static/test_risk_sql.py` compares the two row by row through Databricks Connect.

**What V is made of.** Seven components. Each becomes a percentile among the rated areas, ranked so that 1 is the most vulnerable (ties share a rank), and V is the weighted sum, from 0 to 1.

| group (weight) | component | weight | an area is more vulnerable when |
|---|---|---|---|
| senior exposure (0.35) | residents aged 75+ | 0.20 | there are more |
| | their share of residents | 0.15 | it is higher |
| can't cool down (0.30) | 1-room plus 2-room rental flats, summed over the area's confirmed blocks | 0.25 | there are more |
| | hot-month rise in 1–2 room electricity use (EMA) | 0.05 | the rise is smaller |
| cooling-access gap (0.35) | share of HDB flats beyond 400 m of a refuge | 0.15 | it is higher |
| | refuges per 1,000 residents aged 65+ | 0.10 | there are fewer |
| | share of HDB flats beyond 400 m of a park | 0.10 | it is higher |

- **Thirds.** The 11 areas with the highest V are the upper third, the next 11 the middle, the last 10 the lower. A tie at a boundary goes to the area with more residents aged 75+, then to the name.
- **Reason.** Each area carries a plain reason, the two components with the largest weight × percentile, for example "many residents aged 75+; many 1–2 room rental flats". A component can be named only if it has a real value and sits at or above the middle.
- **Small areas.** A share or a rate over a small denominator is held at the middle (0.5) and flagged: the two 400 m shares where an area has fewer than 1,000 confirmed HDB dwelling units (Changi, Downtown Core, Tanglin), the 75+ share under 1,000 residents (Changi), and refuges per 1,000 aged 65+ under 1,000 residents aged 65+ (Changi, Downtown Core). Counts keep their real value. A missing electricity value also gives 0.5; four rated areas have none.
- **Refuges** are the People's Association's community clubs and the 93 Active Ageing Centres in open data, which is partial (about 223 exist), so the refuge gap is overstated where centres are missing. Distances are straight lines, not walking routes.

**The weights are a judgement, not fitted.** There is no open data on heat illness by area and day to fit them to. They were tested by seven sensitivity runs (equal weights, no electricity term, refuges from clubs only, with the 2016 Senior Activity Centres, the URA park layer, with the reserves, and aged 65+ in place of 75+). Against the main design, Spearman's rho runs from 0.888 to 1.000, and between 0 and 10 areas change third (`docs/checks/risk_score.md`, §4). **The weights, and the actions below, are not yet reviewed by a practitioner.** They sit in a table, `gold.score_weights`, so a review changes them by a reload, not a rebuild.

**Where it is.** Created by `scripts/static/load_risk_tables.py` and `scripts/static/create_risk_views.py`, in the catalog `coolcheck`:

| object | what it holds |
|---|---|
| `gold.area_vulnerability` (view, 32 rows) | one row per rated area: the seven raw values and percentiles, V, its rank, the third, the reason and the small-area flags |
| `gold.block_vulnerability` (view, 10,817 rows) | every HDB block in a rated area, with its `priority` in the area: 1–2 room rental flats, most first, then distance to the nearest refuge, farthest first. **Blocks rank vulnerability, never heat**: heat is known only per planning area |
| `gold.score_weights` (table, 7 rows) | the weights, directions, small-area rules and reason phrases |
| `gold.tier_actions` (table, 4 rows) | the actions per tier (see Tiers) |
| `silver.ema_area_electricity` | the electricity ratios behind the 0.05 term |

No personal data is held. An Active Ageing Centre matches the block list against its own client list.

## Tiers

Two scales appear here, and they are kept apart. **Heat level** is NEA's own WBGT category for tomorrow, **Low / Moderate / High**. **Tier** is the area's risk, **Low / Medium / High**, from the heat level and the vulnerability third.

**Tomorrow's heat level.** The job `coolcheck heat forecast` (`resources/heat_forecast.job.yml`, `src/jobs/heat_forecast.py`) runs at 00:45 SGT. It refreshes the pipeline, then scores the target date with the registered model `coolcheck.ml.heat_model` at the alias `champion`, using only what is known by 00:15 SGT. It writes one row per area of the 41 with residents aged 65+ to `gold.heat_forecast`, with a MERGE on (`target_date`, `planning_area`), so a rerun replaces rather than duplicates. Each area takes its nearest reporting WBGT station for that day. An area whose station has no feature row gets NULL probabilities, flagged, not scored. The model is the final check's configuration refit on target dates to 22 Oct 2026; it is a different fitted model from the one the final check scored, and nothing is reported for it yet (`docs/checks/live_model.md`).

The heat level is High when the model's probability of High reaches the cut-off chosen on the back-test, 0.110 (`docs/checks/backtest_review.md`); otherwise Moderate if Moderate is at least as likely as Low; otherwise Low. **The probability itself is never shown as a number**, because the calibration check found it too high at its highest values and too low at the start of a hot season (`docs/checks/error_analysis.md`, `docs/checks/backtest_review.md`). Tiers and heat levels are shown instead.

**The tier rule** (a 3×3 table, main version):

| heat level ↓ / vulnerability → | lower third | middle third | upper third |
|---|---|---|---|
| Low | Low | Low | Low |
| Moderate | Low | Medium | Medium |
| High | Medium | High | High |

- **Not rated.** The 9 of the 41 areas with no HDB blocks (Mandai, Museum, Newton, Orchard, River Valley, Seletar, Singapore River, Southern Islands, Sungei Kadut) have nothing to rate. They show their heat level only, with the tier "Not rated". They hold 4,730 residents aged 65+ (`docs/design/risk_score.md`, §2).
- **No forecast.** If any of an area's three probabilities is missing, its heat level is empty and its tier is "No forecast", never Low by default.
- **Order inside a tier.** `tier_rank` orders the areas of one tier on one date by probability of High × V. Neither number leaves the view.
- **Medium is not an alert:** heightened care where heat is Moderate in an upper- or middle-third area, or High in a lower-third one. In the back-test months it fired for about 11 areas a day on average, against about 1.3 for High (`docs/checks/risk_score.md`, §1). Whether that is useful is a question for the practitioner review.

**Where it is.** `gold.area_heat_risk` is a view over `gold.heat_forecast`: one row per area per target date, with `heat_level`, `third`, `tier`, `tier_rank`, `tier_sentence` (for example "High: forecast High heat, upper third for vulnerability"), `reason`, `actions` and small-area flags. It has no probability and no score column. `gold.heat_forecast` keeps the probabilities for audit, and the agent's tools do not read it. The first scheduled night, 24 Oct, wrote 41 rows for 41 areas at 00:49:49 SGT (`docs/checks/heat_forecast_first_night.md`). That is one night, not a track record.

**The actions** (`gold.tier_actions`, from `reference/tier_actions.csv`) are a proposal; every row is marked "proposal, not yet reviewed by a practitioner":

| tier | actions |
|---|---|
| High | Phone checks before noon on flagged seniors in the priority blocks; AACs and community clubs extend hours as cooling spaces; the town council is told. |
| Medium | The AAC broadcasts a hydration and heat advisory in four languages; volunteers flag seniors living alone in the priority blocks. |
| Low | Routine. |
| Not rated | Heat level shown only. |

**The agent's tools.** Three Unity Catalog SQL functions in `coolcheck.gold` read these views and allocate calls to capacity in code: `get_priority_areas`, `find_refuges` and `what_if_add_refuge` (`docs/design/agent_tools.md`; `scripts/static/create_agent_functions.py`). None returns a probability or the score.

## Briefing dashboard

> **PLACEHOLDER: not built yet.** This section will describe the briefing dashboard once it exists.

## Agent

> **PLACEHOLDER: not built yet.** This section will describe the outreach agent once it exists.

## Running the tests

The tests run in the project's Python 3.12 virtual environment, `.venv`, which holds `databricks-connect` 17.3 and the packages in `requirements-dev.txt` and `requirements-backtest.txt`.

From the repository root, in PowerShell:

```powershell
.venv\Scripts\activate
pytest tests/analysis tests/backfill tests/collector   # local only
pytest tests                                          # everything
```

Tests that take the `spark` fixture run through Databricks Connect on serverless compute with the CLI profile `coolcheck`, so they need a login to the workspace (`databricks auth login --profile coolcheck`) and use serverless time. They are most of `tests/silver`, `tests/features`, `tests/latest` and `tests/dashboards`, and one test each in `tests/static` and `tests/backtest`. The rest run locally, with no workspace.

Two kinds of test skip on purpose. One test in `tests/silver/test_air_temperature.py` needs a saved real response that is kept outside the repository. `tests/backtest/test_final_check_mlflow.py` skips in `.venv`, because the MLflow version it tests needs an older protobuf than the one `.venv` keeps for Databricks Connect; its docstring gives the commands to run it in a throwaway virtual environment.

## Data sources and licences

`docs/datasets.md` is the dataset register: every dataset or feed CoolCheck uses or holds, with its agency, ID, licence, role and date of access. `docs/attribution.md` gives the attribution notice each dataset in use needs and where it must appear (the dashboards, this README and the write-up). The datasets are used under the Singapore Open Data Licence version 1.0 (https://data.gov.sg/open-data-licence). CoolCheck is not official advice, and no agency endorses it.
