# Demo Day operations: the Free Edition redeploy, the checks to Tuesday, the App stop

Window A, 25 Oct 2026, written 17:00 to 18:20 SGT, for Guide §A3 tasks 15, 19 and 25. Read-only on both workspaces while writing: listings, gets, SELECTs, `bundle validate`, `bundle plan` and one `copy_live_free.py --dry-run`. The state below is as read at 17:42 SGT, after deploy 4 (`e07a8db`, 16:56 to 17:00 SGT; `docs/design/agent_app.md`). Steps marked **writes** wait for the user's OK; deploys go from a clean worktree, one at a time, by Claude Code (`CLAUDE.md`). `<user>` stands for the user's e-mail and user name.

## 0. Before any command

Git Bash, started in the repo root. Once per shell:

```bash
REPO="$(pwd -W)"; PY="$REPO/.venv/Scripts/python.exe"            # the repo's Python 3.12; no other
DATA="$(cd ../coolcheck-data && pwd -W)"
SCR="$(cygpath -m "$TEMP")/coolcheck-ops"; mkdir -p "$SCR"         # logs and digests, outside the repo
q() { databricks experimental aitools tools query "$1" -p coolcheck; }   # one SELECT on the trial's warehouse
dash_id() { databricks lakeview list -p coolcheck -o json | "$PY" -I -c "import json,sys; print(next(d['dashboard_id'] for d in json.load(sys.stdin) if d['display_name'].endswith(sys.argv[1])))" "$1"; }
BRIEF=$(dash_id "CoolCheck briefing"); LIVE=$(dash_id "CoolCheck live heat stress")
```

Put `MSYS_NO_PATHCONV=1` before every command that passes a path starting with `/` (`/Volumes/...`, `/Workspace/...`, `/api/...`): Git Bash rewrites such paths otherwise (23 and 24 Oct, `docs/build-log.md`). `q`, `dash_id`, the helpers `ops_status` and `night` (section 2) and the snippets of steps 6 and 9 were run as written on 25 Oct, read-only. No command marked **writes** has been run.

| | Trial (`-p coolcheck`, target `dev`) | Free Edition (`-p freeedition`, target `free`) |
|---|---|---|
| Nightly job "heat forecast" | `131450384398104`: 00:45 SGT, UNPAUSED; one retry per task after 5 minutes (since deploy 4) | `107197531541954`: PAUSED |
| Live page job "latest readings" | `997063708299006`: hourly at :05, UNPAUSED; `edit_mode` `UI_LOCKED` | `456499726092564`: PAUSED |
| Pipeline | `dbff017a-3751-4806-b529-5d347b49d9bb` | `0b6e55e9-e41e-4137-819f-806307665b48` |
| SQL warehouse | `7aa1dc56400d5b33`, "Serverless Starter Warehouse", Small, auto-stop 10 min | looked up by the same name |
| App | `coolcheck`, compute MEDIUM | none: the App and its experiment are defined for `dev` only |
| MLflow experiments | the App's traces `3392806487792873` (`[dev <user>] coolcheck-agent`); the evaluation's `751187284353678` (`coolcheck-agent-eval`) | none |
| Raw-files Volume | `/Volumes/coolcheck/bronze/raw_files` | `/Volumes/workspace/bronze/raw_files` |

## 1. Task 15: the Free Edition redeploy

### Where Free Edition stands (read 25 Oct, 16:15 to 17:45 SGT)

- **Deployed commit `dbe5f93`:** the score task's `--git-sha` on job `107197531541954`; the chain of 24 Oct is written up in `36a995d` (`docs/checks/free_edition_chain.md`). Both schedules PAUSED; no run since the chain's two scores (24 Oct, 22:27 and 22:28 SGT). Pipeline IDLE, last update `5b580101` COMPLETED (24 Oct, 21:13 SGT).
- **Bronze there** has read live files to run stamp `2026-10-24T004524` (the chain's stage 1; stage 2 was copied after the last update). The trial's Bronze has read to `2026-10-25T004524` for all four feeds (`max(file_name)` of `coolcheck.bronze.*_raw` where `source_kind = 'live'`).
- **`bundle validate -t free`** passes on `e07a8db` (the two style recommendations, as on dev). **`bundle plan -t free`** from `e07a8db`: 1 to add (`dashboards.briefing`), 4 to change (`jobs.backtest`, `final_check`, `heat_forecast`, `live_model`), 0 to delete, 6 unchanged. The commits since, to `090eabf` (17:45), change nothing under `resources/` or in `databricks.yml`.
- **The remote sync list** (`.bundle/coolcheck/free/state/deployment.json`, written 24 Oct 20:19 SGT, 224 files) holds one file that is in no later commit: `resources/briefing.dashboard.yml.draft`, renamed to `.yml` in `6101ee9`. A deploy of any later commit deletes that one remote file. It is expected, but it is a deletion that `bundle plan` does not show; see step 6.
- **Missing in catalog `workspace`** for the briefing dashboard: `silver.planning_area_boundary`, `silver.park_planning_area`, and the views `gold.planning_area_map`, `refuge_layer`, `park_layer`, `observed_heat_daily` (`databricks tables list workspace silver|gold -p freeedition`: 23 silver and 7 gold objects; the trial has 26 and 14). The views' other inputs exist there: `silver.refuge_points`, `silver.park_polygons`, `silver.station_daily_label`, `gold.area_nearest_station_daily`.
- **The chain's billing row** (Free Edition's `system.billing.usage`, read 25 Oct about 16:15; Free Edition has no list price, so DBU only): update `5b580101` 0.7139 DBU (the estimate before it was about 3); the jobs of 24 Oct, 14:00 to 15:00 UTC: `heat_forecast` (the two scores) 0.8330, `live_model` 0.3861, `nearest_station` 0.3377; interactive serverless (the Databricks Connect sessions) 3.0091; SQL 2.6244 DBU; storage 1.7619 DSU for the day.

What the briefing dashboard on Free Edition shows without those objects (its datasets in `src/dashboards/briefing.lvdash.json`):

| Page | Fails without them | Works |
|---|---|---|
| Briefing | "Planning areas by tier", the tier map (`planning_area_map`); "Observed heat, last 30 days" (`observed_heat_daily`) | the headline, the top 10, the other High and Medium areas |
| Blocks | "Blocks and refuges" (`refuge_layer`) | the area facts, the blocks in priority order |
| Observed heat | both widgets (`observed_heat_daily`) | |
| About | | both |

No dataset reads `park_layer` (the polygon maps were dropped on 24 Oct); it and `park_planning_area` are made for parity with the trial.

### The copy: dry run of 25 Oct, 17:09 SGT

```bash
MSYS_NO_PATHCONV=1 "$PY" scripts/free_edition/copy_live_free.py --src-profile coolcheck --dst-profile freeedition \
  --src-root /Volumes/coolcheck/bronze/raw_files --dst-root /Volumes/workspace/bronze/raw_files \
  --stage all --log "$SCR/copy_live_free_dryrun.log" --dry-run
```

Exit 0 in 23 s; it lists both Volumes and writes only its local log. The trial holds 1,195 live files (110.59 MB), Free Edition 895 (80.74 MB), and all 895 are on both sides with the same size. **To copy: 300 files, 29.85 MB**, from 79 collector runs, run stamps `2026-10-24T224531` to `2026-10-25T170042` (the newest already on Free Edition: `2026-10-24T223031`). No size clash, no file on Free Edition only. By date and feed (the same listing grouped, with the script's own `live_files` and `select`):

| SGT date | Files: WBGT / rainfall / forecast / air temperature | MB, same order |
|---|---|---|
| 24 Oct, 22:45 to 23:45 | 5 / 5 / 5 / 5 | 0.71 / 0.39 / 0.04 / 0.46 |
| 25 Oct, 00:00 to 17:00 | 74 / 74 / 58 / 74 | 11.77 / 10.27 / 0.29 / 5.93 |

The forecast has 16 files fewer on 25 Oct by design: none from 02:00 to 05:30 SGT, because the forecast's `date=today` answers 404 until the day's first issue and `collect.py` writes no file for a feed without pages (the same 16 runs on 24 Oct). The real copy will find more: each 15-minute run adds about 4 files and 0.4 MB.

### The steps

`FINAL` is the commit of the trial's last deploy, so both workspaces run the same code (your decision of 24 Oct): `e07a8db` (deploy 4) now, deploy 5's commit if there is one. The trial's nightly job logs it:

```bash
FINAL=$(databricks jobs get 131450384398104 -p coolcheck -o json | "$PY" -I -c "import json,sys; p=[t for t in json.load(sys.stdin)['settings']['tasks'] if t['task_key']=='score'][0]['spark_python_task']['parameters']; print(p[p.index('--git-sha')+1])")
```

| # | Step | Reads or writes |
|---|---|---|
| 1 | The dry run again | reads |
| 2 | The copy | **writes**: files in Free Edition's Volume |
| 3 | A clean worktree of `FINAL` | local only |
| 4 | The two Silver tables | **writes** |
| 5 | The four gold views | **writes** |
| 6 | The remote sync list against `FINAL` | reads |
| 7 | `bundle validate` and `bundle plan -t free` | reads |
| 8 | `bundle deploy -t free` | **writes** |
| 9 | Read-back | reads |
| 10 | `compare_ws.py` digests and diff | reads |
| 11 | Remove the worktree | local only |

**1. Dry run** (reads): the command above, just before step 2. "Already at … with the same size" should equal Free Edition's file count, with no `STOP` line.

**2. Copy** (writes, on your OK):

```bash
MSYS_NO_PATHCONV=1 "$PY" scripts/free_edition/copy_live_free.py --src-profile coolcheck --dst-profile freeedition \
  --src-root /Volumes/coolcheck/bronze/raw_files --dst-root /Volumes/workspace/bronze/raw_files \
  --stage all --log "$SCR/copy_live_free.log"
```

One file at a time in name order, `overwrite=false`; the first failure stops it (order matters). The log must end with `VERIFY …, missing or wrong size 0, .partial 0 …` and `FINISHED OK`. Nothing is ingested: Free Edition's Bronze stays at `2026-10-24T004524` (see the decision below).

**3. Worktree** (local):

```bash
git status -sb                                     # the shared folder; nothing is taken from it
WT="$(cygpath -m "$TEMP")/coolcheck-free-${FINAL:0:7}"
git worktree add --detach "$WT" "$FINAL" && cd "$WT"
```

Every later step runs in `$WT` with `"$PY"` from the shared folder's `.venv`. No step needs an untracked or ignored file: the layers read `--data`, the views and the bundle only tracked files (`src/dashboards/*.lvdash.json` and `resources/*.yml` are tracked).

**4. Layers** (writes, on your OK):

```bash
"$PY" scripts/static/planning_area_layers.py --data "$DATA" --load --catalog workspace --profile freeedition
```

- Flags, from the source: `--data` (default: `coolcheck-data` beside the script's repo, which from the worktree is under `$TEMP`, so it must be given), `--load` (without it nothing is written to a workspace), `--catalog` (default `coolcheck`, checked against `\w+`), `--profile` (default `coolcheck`).
- Writes, through Databricks Connect (serverless): `workspace.silver.planning_area_boundary` and `workspace.silver.park_planning_area`, each `CREATE OR REPLACE TABLE` with column and table comments, then the rows, then the tags `source` and `licence` (`load_refuge_park_access.write_table`). First it rewrites the two local files it loads, `$DATA/analysis/planning_area_boundary.csv` and `park_planning_area.csv`, from the same inputs (the GeoJSON in `static/ura_mp2025_planning_area_boundary/` and `analysis/park_polygons.csv`).
- Check: the first line names 55 planning areas; each table's read-back line (rows equal to the file's, no column without a comment, both tags); 55 and 471 rows, the trial's counts today; and the CSV sha256 in each table comment equal to the trial's, `4d2ecbc69470…` (boundary) and `450c0a20f6ec…` (park areas), which are also the hashes of the two files on disk today (`databricks tables get workspace.silver.<table> -p freeedition`, field `comment`).

**5. Views** (writes, on your OK; only after step 4):

```bash
"$PY" scripts/static/create_briefing_views.py --catalog workspace --print-sql     # prints the four statements, touches nothing
"$PY" scripts/static/create_briefing_views.py --catalog workspace --profile freeedition
```

- Flags, from the source: `--catalog` and `--profile` (defaults `coolcheck`), `--views` (any of the four; default all, in the order below), `--print-sql`.
- Writes, through Databricks Connect, in this order: `workspace.gold.planning_area_map` (over `silver.planning_area_boundary`), `refuge_layer` (`silver.refuge_points`), `park_layer` (`silver.park_polygons` joined to `silver.park_planning_area`), `observed_heat_daily` (`silver.station_daily_label` and `gold.area_nearest_station_daily`); each a `CREATE OR REPLACE VIEW` with column comments and a comment, then `ALTER VIEW … SET TAGS` (`source`, `licence`).
- Check: the script stops unless `planning_area_map` reads 55 rows and `refuge_layer` 206, every column has a comment and both tags are set. The trial today: `park_layer` 471, `observed_heat_daily` 1,737 rows, 25 Sep to 24 Oct. Expect fewer recent days on Free Edition: its labels end where its Bronze ends (early on 24 Oct).
- **If the views were created before the layers:** the first statement, `planning_area_map`, names `workspace.silver.planning_area_boundary`, which would not exist yet. Databricks analyses a view's query when the view is created, so it fails with a table-not-found error (expected; not tried here). The script has no error handling around its loop, so it stops there and creates none of the four. With `--views refuge_layer observed_heat_daily` those two would be created (their inputs exist), and `park_layer` would fail the same way on `silver.park_planning_area`. A failed `CREATE` leaves nothing behind, so loading the layers and running step 5 again repairs it. Separately, if the deploy (step 8) went before step 5, the deploy itself should pass (I expect it does not run the dashboard's queries; not tried), and the widgets in the table above would fail when opened until the views exist.

**6. Remote sync list** (reads). It shows the remote files the deploy would delete, which `bundle plan` does not:

```bash
U=$(databricks current-user me -p freeedition -o json | "$PY" -I -c "import json,sys; print(json.load(sys.stdin)['userName'])")
MSYS_NO_PATHCONV=1 databricks workspace export "/Workspace/Users/$U/.bundle/coolcheck/free/state/deployment.json" --format AUTO -p freeedition > "$SCR/free_deployment.json"
git ls-tree -r --name-only HEAD > "$SCR/files_final.txt"
"$PY" -I -c "import json,sys; r={f['local_path'] for f in json.load(open(sys.argv[1]))['files']}; h=set(open(sys.argv[2]).read().splitlines()); print(len(r), 'remote;', sorted(r - h))" "$SCR/free_deployment.json" "$SCR/files_final.txt"
```

Today, against `090eabf`: `224 remote; ['resources/briefing.dashboard.yml.draft']`. Your rule of 24 Oct stops a free redeploy on any deletion in `bundle plan`; this deletion is in the file sync instead. I would treat it the same: report it and wait for your word before step 8.

**7. Plan** (reads):

```bash
databricks bundle validate -t free -p freeedition && databricks bundle plan -t free -p freeedition
```

Expected, as from `e07a8db`: 1 to add (`dashboards.briefing`), 4 to change (`jobs.backtest`, `final_check`, `heat_forecast`, `live_model`: the git SHA), 0 to delete, 6 unchanged. Stop and report on any delete or recreate, or anything else (your rule, 24 Oct).

**8. Deploy** (writes; your rule of 24 Oct lets it go without asking when the plan is exactly as expected, and step 6's file is asked about):

```bash
databricks bundle deploy -t free -p freeedition
```

Window B's deploy 4 took 22 s (16:56:39 to 16:57:01). No other deploy at the same time.

**9. Read-back** (reads):

```bash
for j in 107197531541954 456499726092564; do databricks jobs get $j -p freeedition -o json | "$PY" -I -c "import json,sys; s=json.load(sys.stdin)['settings']; p=[t.get('spark_python_task',{}).get('parameters',[]) for t in s['tasks']]; print(s['name'], s['schedule']['pause_status'], [x[x.index('--git-sha')+1][:7] for x in p if '--git-sha' in x])"; done
databricks lakeview list -p freeedition -o json | "$PY" -I -c "import json,sys; [print(d['dashboard_id'], d['display_name']) for d in json.load(sys.stdin)]"
```

Both jobs PAUSED and the forecast's score task on `FINAL` (today: `dbe5f93`); two dashboards, "CoolCheck live heat stress" and the new "CoolCheck briefing" (production mode: no prefix). Then open the briefing's four pages once in a browser.

**10. Compare** (reads; one digest per process):

```bash
"$PY" scripts/free_edition/compare_ws.py digest --profile coolcheck --catalog coolcheck --out "$SCR/digest_trial.json" --dates 2026-10-23,2026-10-24
"$PY" scripts/free_edition/compare_ws.py digest --profile freeedition --catalog workspace --out "$SCR/digest_free.json" --dates 2026-10-23,2026-10-24
"$PY" scripts/free_edition/compare_ws.py diff "$SCR/digest_trial.json" "$SCR/digest_free.json" --tolerance 1e-9
```

`--dates` stays at 23 and 24 Oct, the only dates scored on Free Edition. Exit code 1 means something differs. The differences to expect without a pipeline update there: Bronze and Silver for 24 and 25 Oct (the trial has read 24 hours more of live files); the lateness count in `dq_events`; `area_station_distance.station_last_day` (19 against 21 Oct, as on 24 Oct); anything dated after 24 Oct; and the forecast's probabilities within the model difference recorded on 24 Oct (P(High) by at most 0.0047, no tier change). Anything else is a finding.

**11. Worktree** (local): `cd "$REPO" && git worktree remove "$WT"`.

### Decision for you: a pipeline update on Free Edition

Your plan of 24 Oct is the redeploy only, so the steps above run no update. Then Free Edition's Bronze stays at `2026-10-24T004524`; its newest forecast stays 24 Oct, so the briefing there shows 24 Oct's tiers (High 1, Medium 22, Low 9, Not rated 9); and the 300 files and later ones wait in its Volume until the schedules are unpaused. If you want its Silver equal to the trial's again, the method of 24 Oct: step 2 as stage 1 with `--stage 1 --cutoff 2026-10-25T004524` (the trial's newest ingested run stamp until its 26 Oct 00:45 run; the query below reads it again); after step 8, one incremental update, `databricks bundle run coolcheck_pipeline -t free -p freeedition` from `$WT` (24 Oct's took 5 min 58 s and 0.7139 DBU); step 10, where Silver should then differ only in the lateness count; then `--stage 2` with the same cutoff. The update is a run, so it waits for your word.

```bash
q "SELECT 'wbgt' AS feed, max(file_name) AS newest FROM coolcheck.bronze.wbgt_raw WHERE source_kind = 'live' UNION ALL SELECT 'rainfall', max(file_name) FROM coolcheck.bronze.rainfall_raw WHERE source_kind = 'live' UNION ALL SELECT 'forecast', max(file_name) FROM coolcheck.bronze.forecast_raw WHERE source_kind = 'live' UNION ALL SELECT 'air_temperature', max(file_name) FROM coolcheck.bronze.air_temperature_raw WHERE source_kind = 'live'"
```

### What stays paused or absent on Free Edition after task 15

- `heat_forecast` and `latest_readings`: PAUSED (`targets.free` in `databricks.yml`). Unpausing is a commit, a plan and a redeploy, together with pointing the collector at Free Edition (Guide §A4 row 6; 28 or 29 Oct).
- No pipeline update unless you decide it above. The collector writes only to the trial.
- No App and no agent experiment: both are defined for `dev` only (`resources/coolcheck_app.app.yml`).
- The live heat-stress dashboard there has no tables to read: `gold.latest_readings` and `gold.stream_status` are written by `latest_readings`, which has never run there.

## 2. Demo Day: the workspace side

The presentation side is in `../CoolCheck Demo Script.md` (outside the repo). Two helpers, read-only:

```bash
ops_status() {   # the App, the last run of both trial jobs, the warehouse
  databricks apps get coolcheck -p coolcheck -o json | "$PY" -I -c "import json,sys; d=json.load(sys.stdin); c=d['compute_status']; print('App:', c['state'], '/', d['app_status']['state'], '|', c.get('message'), '| record updated', d['update_time'], '| deployment', (d.get('active_deployment') or {}).get('deployment_id', '-')[:12])"
  for j in 131450384398104 997063708299006; do
    databricks jobs list-runs --job-id $j --limit 1 -p coolcheck -o json | "$PY" -I -c "import json,sys,datetime as d; r=json.load(sys.stdin)[0]; s=r['state']; t=d.datetime.fromtimestamp(r['start_time']/1000, d.timezone(d.timedelta(hours=8))); print('Job', r['job_id'], 'run', r['run_id'], t.strftime('%d %b %H:%M SGT'), s.get('result_state') or s.get('life_cycle_state'))"
  done
  databricks warehouses get 7aa1dc56400d5b33 -p coolcheck -o json | "$PY" -I -c "import json,sys; d=json.load(sys.stdin); print('Warehouse:', d['state'], d['cluster_size'], 'auto-stop', d['auto_stop_mins'], 'min')"
}
night() {   # $1 = target date: the newest nightly run, its task attempts, its log lines, its rows
  RUN=$(databricks jobs list-runs --job-id 131450384398104 --limit 1 -p coolcheck -o json | "$PY" -I -c "import json,sys; print(json.load(sys.stdin)[0]['run_id'])")
  databricks jobs get-run "$RUN" -p coolcheck -o json > "$SCR/night.json"
  "$PY" -I -c "import json,sys; d=json.load(open(sys.argv[1])); print('run', d['run_id'], d['trigger'], d['state'].get('result_state')); [print('  ', t['task_key'], 'attempt', t.get('attempt_number'), t['state'].get('result_state'), 'task run', t['run_id']) for t in d['tasks']]" "$SCR/night.json"
  SCORE=$("$PY" -I -c "import json,sys; print(max((t for t in json.load(open(sys.argv[1]))['tasks'] if t['task_key']=='score'), key=lambda t: t.get('attempt_number', 0))['run_id'])" "$SCR/night.json")
  databricks jobs get-run-output "$SCORE" -p coolcheck -o json | "$PY" -I -c "import json,sys; [print('  ', l[:250]) for l in json.load(sys.stdin).get('logs', '').splitlines() if l.startswith(('heat forecast for', 'model ', 'silver.dq_day', 'latest ', 'completeness'))]"
  q "SELECT count(*) AS rows, count(DISTINCT planning_area) AS areas, max(scored_at) AS scored_at_utc, max(run_id) AS run_id FROM coolcheck.gold.heat_forecast WHERE target_date = DATE'$1'"
}
```

Read at 17:42 SGT today: the App ACTIVE / RUNNING since window B's restart (16:59:59); the 25 Oct night SUCCESS with 41 rows (`night 2026-10-25`); the live page's job SUCCESS every hour to 17:05; the warehouse RUNNING, Small, auto-stop 10 min.

### What to open

Built from the IDs; not opened from here (no browser in this window). `echo` the first two after setting `BRIEF` and `LIVE`.

| What | Where |
|---|---|
| Briefing dashboard: Briefing, Blocks, Observed heat, About | `https://dbc-2152ed82-df35.cloud.databricks.com/dashboardsv3/$BRIEF/published` |
| Live heat-stress page | `https://dbc-2152ed82-df35.cloud.databricks.com/dashboardsv3/$LIVE/published` |
| The App | `https://coolcheck-7474646896364032.aws.databricksapps.com` (the `url` of `databricks apps get coolcheck`) |
| The pipeline | `https://dbc-2152ed82-df35.cloud.databricks.com/pipelines/dbff017a-3751-4806-b529-5d347b49d9bb` |
| The evaluation's traces | `https://dbc-2152ed82-df35.cloud.databricks.com/ml/experiments/751187284353678` |
| The App's traces | the same with `3392806487792873` |

### Tonight, about 22:00 SGT (10 minutes)

1. `ops_status`: the App ACTIVE / RUNNING. If not, record it (section 3) and restart (below).
2. If deploy 5 happened: `FINAL` (section 1) gives its commit, and both tasks of job `131450384398104` still have `max_retries` 1 (`databricks jobs get 131450384398104 -p coolcheck -o json`).
3. One draft in the App, then `MSYS_NO_PATHCONV=1 databricks api get "/api/2.0/mlflow/traces?experiment_ids=3392806487792873&max_results=1" -p coolcheck`. At 17:42 today it returned `{}`: **no trace in the App's experiment**, while the evaluation's has more than 100 (the newest 25 Oct, 16:04:26 SGT). If it is still `{}` after a draft, the App's Diagnostics expander shows the tracing note (`tracing_ready` in `src/app.py`). For a trace on screen on Tuesday, the evaluation's experiment works today.
4. The collector: `MSYS_NO_PATHCONV=1 databricks fs ls dbfs:/Volumes/coolcheck/bronze/raw_files/wbgt/live/2026-10-25 -p coolcheck | tail -3`: a file every 15 minutes, the newest less than 15 minutes old.

### Monday 26 Oct, morning (task 19; 10 minutes)

1. `night 2026-10-26`. Expect: run PERIODIC, SUCCESS; `refresh` and `score` attempt 0, SUCCESS (an attempt 1 means a retry ran: this is the first night with retries, so record it either way); the log lines `heat forecast for 2026-10-26; git <deployed commit> …`, `model …`, then the two new with deploy 4, `silver.dq_day for 2026-10-25 (the day before the target date): …` and `latest … input per station: …` (a line starting `completeness lines not written` means they failed and the score went on); 41 rows, 41 areas, `scored_at` about 16:50 UTC on 25 Oct (00:50 SGT).
2. `ops_status`: the App (if it stopped overnight, section 3 first, then restart); the live page's job every hour.
3. The collector for 26 Oct, as tonight (no forecast file from 02:00 to 05:30 is by design).
4. The phone hotspot: over it, `databricks apps get coolcheck -p coolcheck`, then the App and the briefing in the browser.

### Tuesday 27 Oct, before 15:15 (task 25)

From home in the morning:

1. `night 2026-10-27`: SUCCESS and 41 rows, as on Monday.
2. The day's tiers for the talk: `q "SELECT tier, count(*) AS areas FROM coolcheck.gold.area_heat_risk WHERE target_date = DATE'2026-10-27' GROUP BY tier ORDER BY tier"`.
3. The live page's freshness: `q "SELECT measure, last_reading_ts, age_minutes, loaded_at FROM coolcheck.gold.stream_status"`: `loaded_at` within about 65 minutes (the page turns stale at 90).
4. The dashboards' published revisions: `databricks lakeview get-published $BRIEF -p coolcheck -o json`, and the same with `$LIVE`, field `revision_create_time`. Today: the briefing 2026-10-25T08:57:01Z (16:57:01 SGT, deploy 4; a later deploy that changes it republishes it); the live page 2026-10-23T09:35:21Z (17:35:21 SGT, 23 Oct), unchanged since.
5. The evaluation's traces: `MSYS_NO_PATHCONV=1 databricks api get "/api/2.0/mlflow/traces?experiment_ids=751187284353678&max_results=1" -p coolcheck` returns one trace.

At about 13:00 to 14:00, before leaving:

6. **Restart the App** (below), wait for RUNNING, open it once: Diagnostics shows the deployed commit (`APP_COMMIT`; the API returns env names only, not values); draft once.
7. A fresh browser window: sign in and open everything under "What to open"; every dashboard page once.
8. Nothing for the warehouse: it starts on the first query in 2 to 3 s (21 starts since 23 Oct, `system.compute.warehouse_events`) and stops after 10 idle minutes.

At 2 Central Boulevard, about 15:00:

9. `ops_status` over the venue's network, then over the hotspot; the App RUNNING.
10. The 15-minute refresh, if you turn it on (below): switch it on now.

### Restarting the App

- **If the App is stopped** (`compute_status.state` STOPPED): `databricks apps start coolcheck -p coolcheck` (writes). The command exists in CLI 1.21.0 (`databricks apps start --help`: NAME, waits for ACTIVE, `--timeout` default 20 minutes, `--no-wait`); given a NAME it calls the API directly, from any folder. It is enough on its own: at window B's restart today, after `startApp` at 16:57:02 SGT the platform itself made a deployment of the last snapshot at 16:59:15, with no `deployApp` call in the audit log, and it reached "App started successfully" at 16:59:38 (`databricks apps list-deployments coolcheck -p coolcheck`; `docs/design/agent_app.md` reads it the same way). So the start brings back the last deployed code and needs no worktree. Then `ops_status` until the App reads RUNNING.
- **If the App is running and a fresh start is wanted:** `databricks bundle run coolcheck_app -t dev -p coolcheck`, from a clean worktree of `FINAL` (section 1), as window B ran it today (16:57:01 to 16:59:59). It starts the compute if needed and makes a new deployment of `.bundle/coolcheck/dev/files/src` with the bundle's command and environment. The environment comes from the local bundle (the audit log's `deployApp` request carries the env names), so from the shared folder it would stamp `APP_COMMIT` with that folder's HEAD instead of the deployed commit. Not `databricks apps deploy` by hand: `src/` has no `app.yaml`, so the command and environment come only from the bundle. What `apps start` does to a running App: not tried.
- **Time to come up:** 2 min 35 s today (`startApp` 16:57:02 to SUCCEEDED 16:59:38) and 2 min 43 s on 24 Oct (`startApp` 19:21:45 to the bundle's deployment SUCCEEDED 19:24:28). Allow 5 minutes.
- **When:** a restart at 13:00 to 14:00 keeps 15:15 to 19:00 inside both 24 hours of the start (the Free Edition limit in `DAISI Brief.md` §7.6; nothing shows the trial has it) and 9 h 36 min (the one stop seen on the trial, section 3). A restart before about 09:25 would put 19:00 beyond 9 h 36 min.
- **Cost while running:** 0.5 DBU an hour (the App's billing rows of 24 Oct), about US$0.41 an hour at list price.

### The 15-minute refresh (§A4 row 9, your decision)

Now: every hour at :05 (`quartz_cron_expression: "0 5 * * * ?"` in `resources/latest_readings.job.yml`, deployed the same). The job is `UI_LOCKED`, so the UI cannot change it. Two ways; neither tried:

- **Direct, no deploy (my recommendation for the day).** On, at about 15:55 SGT (writes):

  ```bash
  databricks jobs update -p coolcheck --json '{"job_id": 997063708299006, "new_settings": {"schedule": {"quartz_cron_expression": "0 5,20,35,50 * * * ?", "timezone_id": "Asia/Singapore", "pause_status": "UNPAUSED"}}}'
  ```

  It runs at :05, :20, :35 and :50, five minutes after each collector run (:00, :15, :30, :45). Off, after 19:00 (writes): the same command with `"0 5 * * * ?"`. Check either way with `databricks jobs get 997063708299006 -p coolcheck -o json` (`settings.schedule`). While it is on, the trial's `bundle plan -t dev` shows `update jobs.latest_readings`, and any trial deploy sets it back to hourly.
- **Through the bundle:** the cron in `resources/latest_readings.job.yml`, a commit and a deploy from a clean worktree; afterwards a revert and a second deploy. Two deploys on Demo Day, each also moving four jobs' git SHA.
- **Cost:** US$0.1421 a run at list price (the mean of 66 billed runs, 22 Oct 19:05 to 25 Oct 12:05 SGT, `system.billing.usage`). On at 15:55 and off at 19:00: 9 extra runs (16:20, 16:35, 16:50, 17:20, 17:35, 17:50, 18:20, 18:35, 18:50), about US$1.28. Switched on before 15:50, the 15:50 run makes ten.
- **Hourly, as now:** the page can be up to about 65 minutes old during the demo; the stale banner starts at 90.

### If something fails

- **The App does not come up within 5 minutes:** `ops_status` for the message; record it (section 3); the Demo Script's fallback (§4: the video).
- **The 00:45 run failed after its retry:** the failure e-mail goes to the deploying user. The briefing reads the latest target date in `gold.area_heat_risk` (window C's entry of 24 Oct) and the App takes its default date from the same view, so both would show 26 Oct. To score the day (writes): `databricks jobs run-now 131450384398104 -p coolcheck` (the deployed job, refresh then score; its empty `target_date` means the run date in SGT), about 5 minutes; then `night 2026-10-27`.
- **The live page is stale:** `ops_status` (the job's last run) and the collector's newest file (tonight's step 4).
- **The network:** the phone hotspot; the video, the deck PDF and the screenshots offline (task 22).

## 3. The App stop of 25 Oct, 04:57 SGT

### What is known

| SGT | Event | Source |
|---|---|---|
| 24 Oct 18:56:54 | `createApp` | audit |
| 19:21:45 | `startApp` | audit |
| 19:23:58 to 19:24:28 | `deployApp`; SUCCEEDED, "App started successfully" | audit; `apps list-deployments` |
| 20:15:26; 20:16:29 to 20:16:47 | `createUpdate`; `deployApp`, SUCCEEDED (deploy 2) | audit; deployments |
| 22:01:42 | `createUpdate` (window C's deploy of the briefing dashboard) | audit |
| 22:54:23; 22:56:42 to 22:57:01 | `createUpdate`; `deployApp`, SUCCEEDED (deploy 3) | audit; deployments |
| 25 Oct 04:57:51 | the App record's `update_time`: compute STOPPED, "App compute was stopped due to workspace or account status."; app UNAVAILABLE, "App status is unavailable."; `active_deployment` empty; `updater` `<user>` | `apps get`, read 16:12 |
| 16:57:02 | `startApp` (window B, `bundle run coolcheck_app`, deploy 4) | audit |
| 16:59:15 to 16:59:38 | a deployment of the last snapshot, made by the start (no `deployApp` call) | deployments; audit |
| 16:59:41 to 16:59:59 | `deployApp`, SUCCEEDED; RUNNING since | audit; deployments |

- The stop came 9 h 36 min after the start (19:21:45) and 6 h 1 min after the last deployment (22:56:42).
- No stop by anyone in the audit log (`system.access.audit`, `service_name = 'apps'`): after `deployApp` at 22:56:42 the next App event is `startApp` at 16:57:02 today. The audit table held other services' events around the stop (20:38, 21:05 and 21:06 UTC), so the gap is not lag. The App record names `<user>` as updater at 04:57:51, with no action of that user on the App in the audit log then.
- The App's billing (`billing_origin_product = 'APPS'`): one row an hour from 19:00 SGT on 24 Oct, 0.500 DBU for a full hour, 0.303 for the first (from 19:21) and 0.477 for 04:00 to 05:00, which fits a stop at about 04:57; 4.78 DBU in all. No App row after 05:00 SGT up to the end of billing when read (25 Oct, 15:00 SGT).
- The rest of the trial ran through it: the live page's job at 04:05 and 05:05 SGT (billed per run), the collector every 15 minutes, and the 00:45 run before it (SUCCESS).
- The App's compute size is MEDIUM; no budget policy applies (`effective_budget_policy_id` empty). Spend at list price to 25 Oct, 13:00 SGT: US$139.13 (`system.billing.usage` joined to `system.billing.list_prices`).
- The Brief's "Apps run for up to 24 hours after being started, updated, or redeployed" is in its Free Edition limits table (§7.6). This stop came earlier and gave another reason.

### What is not known

- The cause. The message names "workspace or account status"; nothing in the audit log, the billing or the App record says more.
- Whether it happens again, and after how long; whether the trial limits an App's run time at all.
- Whether Databricks e-mailed the user at that time (the user's inbox).
- The trial's credit balance: the account console shows it, the workspace does not.

### What to watch

- **When to look:** tonight about 22:00 (5 hours after the restart); Monday morning, which covers 02:35 (9 h 36 min after 16:59); Monday about 17:00 (24 hours); Tuesday before leaving and at the venue. Deploy 5 or a restart moves these times.
- **What to look at:** `ops_status`, or `databricks apps get coolcheck -p coolcheck -o json` for `compute_status` (state, message), `app_status`, `update_time` and `active_deployment`.
- **If it has stopped, record before restarting:** the `update_time` (the stop), both messages word for word, the time since the last `startApp` and the last deployment (`databricks apps list-deployments coolcheck -p coolcheck`), and the two queries below (UTC in both tables; the audit lags by minutes, billing by 3 to 4 hours). Then restart (section 2) and add a line to the build log.

```bash
q "SELECT event_time, action_name, response.status_code FROM system.access.audit WHERE service_name = 'apps' AND event_time >= '2026-10-25 08:50:00' ORDER BY event_time"
q "SELECT usage_start_time, usage_end_time, usage_quantity FROM system.billing.usage WHERE billing_origin_product = 'APPS' AND usage_start_time >= '2026-10-25 08:00:00' ORDER BY usage_start_time"
```
