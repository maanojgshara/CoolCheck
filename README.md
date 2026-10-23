# CoolCheck

Next-day heat briefing for community care teams in Singapore (DAISI Round 2, team AIsenal, problem B1 HeatGuard).

**Status on 23 Oct 2026.** Built so far: the four live feeds, the pipeline from raw files to Silver, the live page, the back-test (`docs/checks/backtest.md`) and the refuge and park access measures. Not built yet: the risk score, the tiers, the briefing dashboard and the agent (placeholders below). All times are Singapore time (SGT).

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

The pipeline, the jobs, the MLflow experiment and the live page are deployed from this repository by the bundle in `databricks.yml` (target `dev`). In that target every deployed job, pipeline and dashboard name starts with `[dev <user>]`. The Volume and the tables loaded by local scripts are created by those scripts, not by the bundle. The Unity Catalog catalog is `coolcheck` (the bundle variable `catalog`), with schemas `bronze`, `silver`, `gold` and `ml` (empty so far).

- **Volume** `coolcheck.bronze.raw_files`: the raw responses from the backfill and the collector.
- **Bronze**, one row per API page, loaded by Auto Loader in the Lakeflow pipeline `coolcheck_pipeline` (`src/pipeline/`, serverless, triggered): `bronze.wbgt_raw`, `bronze.rainfall_raw`, `bronze.forecast_raw`, `bronze.air_temperature_raw`.
- **Silver**, from the same pipeline:
  - every parsed copy, with a `fail_<rule>` flag per quality rule: `wbgt_readings_all`, `rainfall_readings_all`, `air_temperature_readings_all`, `forecast_issues_all`;
  - deduplicated: `wbgt_readings`, `rainfall_readings`, `air_temperature_readings`, `forecast_issues`, and `forecast_periods` (forecast issues by period and region);
  - `station_daily_label`: each station's highest NEA heat-stress category of the day (Low, Moderate or High);
  - data quality: `quarantine`, `dq_day`, `dq_events`, `dq_conflicts`, `station_gaps`, `wbgt_first_arrival`, and `dq_reconcile` (written by the `reconcile` job).
- **Silver, loaded by local scripts:** `area_station_distance` (planning-area to station distances, `scripts/static/area_station_distance.py`), `area_exposure` (residents, and those aged 65+ and 75+, per planning area, `scripts/static/load_area_exposure.py`), and the four access tables from `scripts/static/load_refuge_park_access.py`: `refuge_points` and `park_polygons` (the refuge and park layers), `block_access` (per HDB block) and `area_access` (per planning area).
- **Gold:** `gold.latest_readings` and `gold.stream_status`, refreshed from the live files in the Volume by the `latest_readings` job (hourly at :05), which fails, and so e-mails the user who deployed it, when the newest WBGT reading is over 90 minutes old; `gold.area_nearest_station_daily`, the nearest reporting WBGT station per planning area and day (a view created by `src/jobs/nearest_station.py`).

The pipeline runs in triggered mode: Bronze and Silver move only when an update is started.

## The live page

The AI/BI dashboard **CoolCheck live heat stress** (`src/dashboards/live_heat_stress.lvdash.json`, deployed through `resources/live_heat_stress.dashboard.yml`) shows the newest readings of three feeds: WBGT stations on a map, coloured by NEA's heat-stress category; rain per station, labelled "Rain in the hour to" the end of the rainfall window; and air temperature (shown live only, not a model input). It reads only `gold.latest_readings` and runs on the existing Serverless Starter Warehouse. A station shows "no recent reading" when it has no reading in the hour before the table's last refresh. When that refresh is more than 90 minutes old, a banner says so and every station shows "no recent reading". In the workspace it is in the Dashboards list as `[dev <user>] CoolCheck live heat stress`.

## Risk score

> **PLACEHOLDER: not built yet.** This section will describe the area risk score once it exists.

## Tiers

> **PLACEHOLDER: not built yet.** This section will describe the area risk tiers once they exist.

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
