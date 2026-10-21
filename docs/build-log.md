# Build log

A shared record of what was tried, what was learned, decisions, blockers and questions. One entry per working session, oldest first. Entries are written with the `/log` command in Claude Code.

## 2026-10-19: Planning and tool setup (before Day 1 of the build)

**Tried and approach**
- Reconciled the Round 1 slides, the organisers' brief and the Round 1 plan, and resolved 13 conflicts between them (for example how many air-temperature stations the feed really has, and what "real-time" can honestly mean).
- Wrote a 7-day build schedule with the data and access checks first and agreed fallbacks for each check that could fail.
- Connected the tools: Databricks CLI with OAuth login, the Databricks extension in Cursor, Databricks Connect on serverless compute, and the official Databricks skills for Claude Code and Cursor.
- Added project rules (`CLAUDE.md`) and permission rules so the coding agent can read freely, must ask before deploying, and cannot create compute or delete data.

**Learned**
- Databricks Connect needs Python 3.12; the requirements page lists no newer Python version, so a 3.15 install cannot be used for this project.
- Serverless sessions default to UTC per the docs, so Singapore-time day boundaries need an explicit time zone setting.
- Databricks Asset Bundles are now called Declarative Automation Bundles.
- Databricks' skills installer needs the `claude` command on the PATH, and Cursor accepts only globally scoped skills.

**Decisions and why**
- Build on the Databricks free trial (US$400 credit) in the work-account workspace. The mentor confirmed the project is not restricted to Free Edition. The final submission must not depend on this workspace, because trial workspaces expire.
- Product name CoolCheck, subtitle "a HeatGuard solution"; Unity Catalog name `coolcheck`.
- Drop PM2.5 and the HDB Elderly dataset from the model. The brief only requires at least one open dataset, PM2.5 has no clear role in a next-day heat model, and Census 2020 covers elderly density per planning area. Both are listed as "considered and not used".
- Area risk is Low/Medium/High from tomorrow's forecast heat category and the area's vulnerability third; NEA's heat categories stay Low/Moderate/High. The tier rule is a proposal to be validated.
- Keep advisories in four languages; the three non-English ones are checked by back-translation, not by a native speaker, and are labelled that way.
- Geocode HDB blocks once with OneMap as a background job, because rental flats per planning area depend on it. Fallback if OneMap fails: the plan's HDB-town lookup without geocoding.

**Stuck** (all resolved)
- Python 3.15 was installed: created the virtual environment with Python 3.12 instead.
- `claude: cli-not-on-path`: installed the standalone Claude Code command.
- `Cursor: does not support project-scoped skills`: reinstalled for Cursor with global scope.

**Challenges and questions**
- Is leaving out PM2.5 and HDB Elderly acceptable for B1?
- Which workspace will judges check, and does it need to stay live after submission?
- Are three near-real-time streams (1 to 15 minutes) enough for "at least 2 real-time streams"?
- How many High-heat days are needed before a recall figure is convincing? If they are rare, is reporting High vs not-High acceptable?

## 2026-10-19: Catalog and schemas created

**Tried and approach**
- Ran `databricks:doctor` for the `coolcheck` profile: CLI v1.21.0, OAuth valid, workspace reachable.
- Listed catalogs and the session time zone through Databricks Connect on serverless (`test_connect.py`).
- Wrote `setup_catalog.py` (idempotent `IF NOT EXISTS`; stops with the exact error if `CREATE CATALOG` fails; no storage locations or credentials created). Reviewed it, then ran it with approval.
- Checked the result with `databricks schemas list coolcheck`.

**Learned**
- Serverless session time zone is `Etc/UTC`, so jobs must set `Asia/Singapore` and derive `sgt_date`.
- Before setup the workspace had no `coolcheck` catalog; the only managed catalog was `daisi` (others: `system`, `samples`).
- `CREATE CATALOG` worked on the trial with default storage. `coolcheck` now has `bronze`, `silver`, `gold` and `ml` (plus auto-created `default` and `information_schema`).
- `.databrickscfg` has a duplicate `CoolCheck` profile and an empty `[DEFAULT]` section next to `coolcheck`.

**Decisions and why**
- Use a separate `coolcheck` catalog, not the pre-existing `daisi`: the project's tables stay isolated from the workspace's default catalog, so they are easy to find, grant, clean up and show to judges, and the table names match the plan.
- Creating the catalog was permitted on the trial with default storage, so no fallback (such as using `daisi`) was needed.

**Stuck**
- Nothing blocked. `CREATE CATALOG` did not fail, so no workaround was needed.

**Challenges and questions**
- The duplicate `CoolCheck` profile is not removed yet; decide whether to delete it from `.databrickscfg`.
- `daisi` is unused; unclear if the organisers expect anything in it.

## 2026-10-19: Bundle variable, free target and trial end date

**Tried and approach**
- Added a bundle variable `catalog` (default `coolcheck`) and a second target `free` (`mode: development`, no default, placeholder host) to `databricks.yml`. Ran `databricks bundle validate -t dev`: "Validation OK!". Nothing deployed (commit 047cd7f).
- `free` was not validated: its host is still a placeholder.

**Learned**
- The trial banner shows the trial ending 30 Oct (read from the banner by the team, not checked in the API). The finale at the Databricks office is 4 Nov, so the trial ends before the finale.
- Not verified: the 14 trial days may be shared across workspaces on the account. This is a guess.

**Decisions and why**
- The Day 7 clean redeploy will target the Free Edition workspace through bundle target `free`, so the project has a home after 30 Oct. Rejected: relying on the trial workspace, which expires before the finale.

**Stuck**
- Nothing blocked this session.

**Challenges and questions**
- Question for mentor: will organisers provide a workspace or extend credits for finalists, or should we plan a recorded demo plus a personal Free Edition workspace?
- The `free` host is a placeholder and must be filled in. Free Edition limits (serverless only, no extra compute) are not yet checked against the plan.

## 2026-10-19: Smoke job and network check

**Tried and approach**
- Smoke job (`smoke/hello.py`, serverless): wrote 3 rows to `coolcheck.bronze._smoke`, logged one MLflow run, then one HTTPS GET to the data.gov.sg real-time air temperature endpoint. The URL was from my own knowledge; `DAISI.md` has none.
- Second job `network_check` (run 348652983808900, `max_retries: 0`): `socket.getaddrinfo(host, 443)` for 10 hosts.
- Read-only query of `system.access.outbound_network`.

**Learned**
- Table written (3 rows) and MLflow run visible (param `purpose`, metric `rows_written=3`). The HTTP step failed: `URLError: Temporary failure in name resolution`.
- Blocked (gaierror): `api-open.data.gov.sg`, `data.gov.sg`, `api.data.gov.sg`, `www.onemap.gov.sg`, `www.weather.gov.sg`, `www.ema.gov.sg`, `google.com`. Resolve: `pypi.org`, `github.com`, `raw.githubusercontent.com`.
- `system.access.outbound_network` is readable: 4 rows, all `DROP`, all DNS for `api-open.data.gov.sg`, in two pairs about 57 s apart. The column is `access_type`, not `event_type`.
- The first smoke run shows task attempts 0 and 1, both FAILED. The automatic retry explains the two identical MLflow runs.

**Decisions and why**
- Set `max_retries: 0` on the `network_check` task so one failure gives one attempt. Not yet set on `smoke`.
- Pending: whether to collect data outside the workspace (e.g. a local or GitHub-hosted collector) because `.gov.sg` hosts are blocked from here.

**Stuck**
- Outbound DNS to every `.gov.sg` host is blocked from serverless on this trial workspace. Open. Plan Day 1 check 7 fails here, so its fallbacks apply.
- The 10 hosts in `network_check` have no rows in the system table; cause not checked (lag or partial logging).

**Challenges and questions**
- Question for mentor: does the organisers' workspace allow `.gov.sg`, or do we plan an outside collector?
- Does Free Edition's trusted-domain list include data.gov.sg?

## 2026-10-20: Free Edition check and fetch-outside decision

**Tried and approach**
- Ran the same ten-host DNS check in the personal Free Edition workspace (reported by the team; not run in this Claude Code session).
- Dropped: the old no-geocoding fallback from check 7.

**Learned**
- Free Edition gives the identical result to the trial: all `.gov.sg` hosts and `google.com` blocked; `pypi.org`, `github.com` and `raw.githubusercontent.com` resolve. Neither workspace can fetch the feeds.
- Plan notes were updated (new section 14.6, check 7 fallback, Day 1, 2 and 7), as reported by the team.

**Decisions and why**
- Fetch outside Databricks and push in. Static data, the backfill and OneMap geocoding run on a local computer and are uploaded to a Unity Catalog Volume.
- Live feeds come from a scheduled GitHub Actions collector that pushes raw JSON to a Volume every 15 minutes; Auto Loader reads it into Bronze inside the workspace.
- Rejected: dropping geocoding and using the old no-geocoding fallback, because fetching outside keeps the full design.

**Stuck**
- Outbound access to data.gov.sg and OneMap is blocked in both workspaces. Worked around by the decision above; the blocker itself is unchanged.

**Challenges and questions**
- This replaces the 2026-10-19 question about the organisers' workspace and Free Edition.
- Question for mentor: both our trial and Free Edition block data.gov.sg and OneMap, so we plan to fetch outside Databricks and push into a Volume. Is that acceptable for the real-time requirement, and is it known and common among other teams?
- Open: whether the trial allows a service principal for the collector's credential.

## 2026-10-20: Checks 9 and 10, shared client, backfill and High-day counts

- **Tried and approach:** Check 10 (NEA 24-hour forecast): 291 of 300 unauthenticated calls, then a 10:00-16:00 window beside 06:00-18:00 and a list of the 13 uncovered 2026 days. Check 9 part A (WBGT and rainfall history): 103 of 300 calls. Moved the client and helpers to `scripts/checks/_common.py` (check 10 replays from cache with a byte-identical report). Wrote a resumable backfill (`scripts/backfill/backfill.py`: .partial files, `progress.jsonl`, 1 call/s, 429 back-off) and `wbgt_high_days.py` for check 9 part B. Tests use a fake HTTP session (24 passing).
- **Learned:** WBGT history starts 2025-01-16; stations grew from 8 to 30. Backfill: 642 days (621 done, 21 short), 2,990 calls, 427 HTTP 429 (14.3%), no stops. 61,443 timestamps, 1,036,005 readings. `heatStress` is Low/Moderate/High/NA; Moderate max 32.9, High min 33.0 (2,093 High readings, 2,894 NA excluded).
- **Learned:** 535 High station-days, 247 High days over all stations; 166 and 128 for the original 8. Original-8 High station-days by window: 44 (Jan-Jun 2025), 106 (Jul 2025-Aug 2026), 16 (Sep-19 Oct 2026, below the 30 rule in section 14.4). S142 holds 165 of 535 (31%).
- **Learned:** Bad-validity records number 12 (from the earlier session, not in the files). Unknown from the files: why 21 days are short, and why 13 2026 days lack a covering forecast (listed in check10.md, cause not stated in the commit).
- **Decisions and why:** Counted High only from the API `heatStress` field, not a hard-coded cut-off (project rule). Excluded NA from station-days. Reported the original-8 set beside all stations so network growth does not inflate High days.
- **Stuck:** Check 9's first attempt stopped after 4 calls because the parser did not recognise the WBGT response shape (records vs readings). Fixed, and disclosed in the report.
- **Stuck:** Bad-validity records were first miscounted as 7 from a truncated table. The true count is 12.
- **Stuck:** Test expectation `off_file_date` changed from 2 to 1. The first expectation was wrong, not the code: the 16:30Z record is 00:30 SGT on the next day, so it is not off its file's date.
- **Challenges and questions:** Daily forecast cut-off: A (21:00 SGT, with a coverage rule and fallback) or B (about 00:15)?
- **Challenges and questions:** Back-test split: rolling monthly Jul 2025 to Aug 2026, untouched final check Sep to 19 Oct 2026. That check is small: 16 High station-days for the original 8 stations.
- **Challenges and questions:** Station approach: the network grew from 8 to 30 stations, and S142 holds 31% of High station-days.
- **Challenges and questions:** The forecast and rainfall backfill marker still says 2025-01-15, so those stages must run before the collector's first run.
- **Decisions and why (backfill design):** One JSONL file per feed and day, each line an unmodified response body. A day is marked done in `progress.jsonl` only after its file is complete, and a crash after the file but before the log line is repaired on restart with no calls. The end date is yesterday SGT, and before 01:00 SGT it is the day before yesterday so late readings have arrived. An OS file lock prevents two runs. It stops on a persistent 429 (5 retries), more than 50 of the last 100 calls being 429, any 401, two 403s in a row, a persistent 5xx, or 3 connection failures in a row. A key, if set, is never used silently: a 401 or 403 with a key stops with "key rejected".
- **Learned:** S130 West Coast Road stops reporting after 2026-06-24, so the original 8 stations are effectively 7 from July 2026, which partly explains the 16 High station-days in Sep to 19 Oct 2026. High days peak in Apr to Jun and are near zero in Jan to Feb, so the final check window is off-peak.

## 2026-10-21: Backfills finished and modelling decisions

- **Tried and approach:** Committed the build log and the High-day report separately (8e5ccd9, c479869). Ran `backfill.py` for forecast, then rainfall, with no key and `--end 2026-10-19`, as a detached hidden PowerShell script (rainfall only if forecast exits 0). Checked progress with single log reads, no polling.
- **Learned:** WBGT: 642 files, 2,990 calls, 427 HTTP 429 (14.3%), 191 MB, 21 short days (from the earlier run).
- **Learned:** Forecast: 641 files, 9.0 MB; 641 done, 1 `no_data` (2025-07-20, HTTP 404); 748 calls, 106 429s (14.2%), 19.6 min.
- **Learned:** Rainfall: 642 files, 412 MB; 625 done, 17 short (e.g. 2025-07-20 had 149 readings, 2025-05-28 had 220, of 288 expected); 8,969 calls, 1,281 429s (14.3%), 235.8 min. No stops in any stage; key absent throughout.
- **Learned:** `raw/_meta/backfill_end.json` now reads 2026-10-19 for wbgt, forecast and rainfall (written 2026-10-21 01:58 SGT). The earlier open item (forecast and rainfall marker at 2025-01-15) is resolved.
- **Learned:** data.gov.sg documents its limit as 6 calls per 10 seconds without a key, which explains the 429s.
- **Decisions and why:** Ran forecast and rainfall in sequence in one detached script, not in parallel, so the script's 1 call/s pace is not doubled against data.gov.sg's documented limit of 6 calls per 10 seconds without a key. Rejected: two simultaneous processes.
- **Decisions and why:** The nightly run is about 00:15 SGT (option B), because the 17:30 forecast was missing on most sampled days from Mar to Jul 2026.
- **Decisions and why:** Back-test is rolling monthly Jul 2025 to Aug 2026, with one untouched final check Sep to 19 Oct 2026. Tuning uses the rolling months only.
- **Decisions and why:** One pooled model with no station ID, using the nearest reporting station per planning area and date. A trailing 30-day station feature is tested with and without.
- **Decisions and why:** Scope drop order and risk score agreed: model probability of High as the heat term, with a 3x3 tier rule.
- **Stuck:** First detached launch failed silently: no `stage_forecast.out` and no python process, cause a quoting problem in the inline PowerShell command (not otherwise diagnosed). Fixed by launching from `run_stages.ps1` in the scratchpad.
- **Challenges and questions:** Unknown: why 17 rainfall days are short, and whether the forecast 404 on 2025-07-20 is a real gap (rainfall was also short that day). On 2025-07-20 WBGT was complete (96 readings) while the forecast had no data and rainfall had 149 of 288, which looks like an upstream gap on those two feeds (not confirmed). Not yet checked: contents of the new files, and the forecast issue-time coverage against the cut-off rule.
- **Challenges and questions:** Next: upload the three feeds to a Unity Catalog Volume (plan section 14.6), which has not been started.

## 2026-10-21: Day 2 step 2, model test, service principal, Volume, upload

- **Tried and approach:** (a) Listed serving endpoints with the `coolcheck` profile (12, 9 chat) and called `databricks-meta-llama-3-3-70b-instruct` once per run with one dummy tool `save_advisory`, asking for a Malay and a Tamil heat advisory. (b) Created service principal `coolcheck-collector`, Volume `coolcheck.bronze.raw_files`, and grants. (c) Wrote `scripts/upload/upload_raw.py` (SDK Files API, 6 threads, skips same-size files, logs, verifies counts) and launched it detached.
- **Tried and approach:** Run 1 used a tool with `language` and `sentence`; run 2 used a tool with `malay` and `tamil`. Run 1 is kept in `docs/checks/tool_calling_model_test_run1.md`.
- **Learned:** Run 1 returned 1 tool call (Malay only). Run 2 returned 1 well-formed call (known name, valid JSON, exact keys) with both sentences. The Tamil text has not been checked by a Tamil speaker.
- **Learned:** The trial allows creating a service principal (user is in `admins`). Granted `READ_VOLUME` and `WRITE_VOLUME` on the Volume only, plus `USE_CATALOG` on `coolcheck` and `USE_SCHEMA` on `coolcheck.bronze`. No token or secret was created.
- **Learned:** Upload log: 1,926 local files (636 MB) uploaded in about 2 minutes, 0 failed. Verify: wbgt 642, forecast 641, rainfall 642, 0 `.partial`, 0 size mismatches, `FINISHED OK` at 12:37:07 SGT. The 1,926th file is `_meta/backfill_end.json`.
- **Decisions and why:** Chose Llama 3.3 70B Instruct for the test: a standard chat endpoint with tool calling; other endpoints (gpt-oss, Qwen, Llama 4) were not tested, so this is not a ranking.
- **Decisions and why:** Called the REST invocations route through `api_client.do` instead of `get_open_ai_client()`, to avoid adding the `openai` package.
- **Decisions and why:** Used the SDK Files API per file, not `databricks fs cp`, so skip-if-same-size and the count check live in one script. Rejected: copying the whole folder with the CLI.
- **Stuck:** `ModuleNotFoundError: No module named 'openai'` from `get_open_ai_client()`; resolved by the REST route above.
- **Challenges and questions:** Run 1 gave only the Malay call, so a one-call-per-language design is unreliable on this model; the agent should use one call that carries all fields. One run each, so this is not a measured rate.
- **Challenges and questions:** Still open: an OAuth secret for the principal (needs the user), a test write as the principal, and the GitHub Actions collector. Untracked scripts `catalogue.py`, `check12_air_temperature.py`, `datagov.py`, `download_static.py` came from another process and are not part of this entry.

## 2026-10-21: Day 2 step 3, checks 1 to 4, 6, 12, 13 and static data

- **Tried and approach:** Crawled the data.gov.sg catalogue (4,664 datasets, 466 calls, no 429s) to get dataset IDs, since the listing API ignores a search query. Built `datagov.py` (download without printing the signed link) and `download_static.py` (8 datasets, provenance per folder, in `coolcheck-data/static/`, nothing uploaded). Ran checks 1, 2, 3, 6, 12 and 13 as scripts. Tried EMA with plain GETs and with Claude in Chrome; dropped both.
- **Learned:** Check 1: the Eldercare file has 133 points, none named an Active Ageing Centre (60 Senior Activity Centres, 6 "Silver ACE"), all stamped 2016; SingStat counts 223 Active Ageing Centres in 2024. Checks 2 and 3: Park Connector Loop (878 lines, 336.1 km) and Cycling Path Network (8,523 lines, 433.8 km) are GeoJSON on data.gov.sg, so no LTA key.
- **Learned:** Check 12: readings are 1 minute apart; stations 12 to 19 on 9 sampled dates, 18 listed on 2026-10-19; 2 of 9 dates returned the same reading at 12:00 and 12:01 (cause unknown). Check 13: EMA planning-area files on data.gov.sg cover 2009 to 2013 only; in the 2013 file 26 of 55 areas are all zeros and Bukit Timah and Tanglin have no 1-2 room value.
- **Learned:** Check 6: MSS terms allow personal, internal, non-commercial or informational use (4.3), need written permission to republish (4.1) and ban robots or automatic devices (6.2); no open-data licence is stated. SingStat has June 2025 and June 2026 planning-area files; June 2026 (63,080 rows, total 4,199,180) says its areas follow Master Plan 2025, while its 55 names match the Master Plan 2019 file.
- **Decisions and why:** Kept the June 2026 SingStat file and a 2026 Community Club / PAssion WaVe file (128 points) as extra downloads, because the Census 2020 and 2024 Community Clubs files are older; this is not a choice between sources. Used the file called "Parks" (462 points) over other NParks files without comparing them. Did not try to get past EMA's bot protection.
- **Stuck:** EMA pages return an Incapsula bot-protection page (about 840 bytes) to scripts, so check 4 is not answered and check 13 is answered only for 2013. Chrome: "Browser extension is not connected." Open; needs the user's browser.
- **Stuck:** The first Eldercare download failed with `429 Client Error: Too Many Requests` while the catalogue crawl shared the rate limit; rerun after the crawl finished. Check 12 stopped at its 120-call cap because a full day is about 58 pages of 25 readings; redesigned to 3 calls per date.
- **Stuck:** A Python edit put control characters into regexes in `check1_refuges.py`; fixed by rewriting those lines. The first version counted "Silver ACE" as Active Ageing and missed "SAC"; corrected.
- **Challenges and questions:** Licence per data.gov.sg dataset page was read only for Eldercare (search snippet); the SingStat licence is unconfirmed (terms page needs JavaScript). My own scripts fetched a few MSS pages, which clause 6.2 arguably covers.
- **Challenges and questions:** Decide Census 2020 or June 2026 (C1) and which boundary file (Master Plan 2019 or 2025, the latter not downloaded). Mentor: are "Silver ACE" centres Active Ageing Centres, and is it worth emailing NEA_MSS_Engage for permission? Check 5 (OneMap) not run.

## 2026-10-21: Day 2, check 5 (OneMap) and the Master Plan 2025 boundary

- **Tried and approach:** Check 5 in `scripts/checks/check5_onemap.py`, token only from the environment, a shared 30-call cap (all OneMap calls counted) with 3 s pauses. Fetched the terms and API-docs pages (2 calls), decoded the token's expiry only, geocoded 20 HDB blocks (one per town, seeded), then re-queried 6 with raw results saved and made 2 `getPlanningarea` calls. Downloaded the Master Plan 2025 boundary with `download_static.py` and compared it with 2019 in `compare_boundaries.py`.
- **Learned:** All 30 calls were used. The terms and API-docs pages are JavaScript shells (113 and 1 visible characters), so the terms and the rate limit were not read. The 26 search calls (about 20 a minute) showed no rate-limit header and no 429.
- **Learned:** The token works (HTTP 200 on all 28 API calls); expiry from the token's `exp` claim is 2026-10-24 12:58 SGT. Search returns `SEARCHVAL, BLK_NO, ROAD_NAME, BUILDING, ADDRESS, POSTAL, X, Y, LATITUDE, LONGITUDE`; 20 of 20 queries returned the right block and road (scored from saved address strings; coordinates seen for 6). Point-in-polygon gave the same planning area under both boundary files for those 6, and `getPlanningarea` returned `pln_area_n` BISHAN for the Bishan block.
- **Learned:** Master Plan 2025 vs 2019: the same 55 names and fields; 12 of 55 areas have the same vertex count; 52 of 55 changed in area by 1% or less; Changi Bay 1.97 to 11.63 km², Changi +4.6%, Pasir Ris +1.0%; on a 110 m grid 98.4% of cells carry the same area, 0.12 km² moved between areas.
- **Decisions and why:** Assign planning areas locally by point-in-polygon rather than one `getPlanningarea` call per block (one extra call per block). I recommended the 2025 boundary with the SingStat June 2026 figures; the user decides (C1). Did not try more pages for the terms, because each counts against the 30.
- **Stuck:** My first matcher compared "ST"/"AVE" with OneMap's "STREET"/"AVENUE" and scored 1 of 20; I had not saved raw responses and the cap did not allow a 20-call rerun, so I fixed the matcher, scored the 20 from saved address strings and re-queried 6. Also `ModuleNotFoundError: No module named '_common'` when run with `python -I`; fixed by running without `-I`.
- **Challenges and questions:** Open: the OneMap terms and rate limit (user to read in a browser), whether storing coordinates and public-repo use are allowed, the token expires before Demo Day, and the grid comparison is a sample (no shapely). The 20 of 20 rate is a small sample from different towns, not all 13,392 rows.

## 2026-10-21: API key burst check (does data.gov.sg read `x-api-key`?)

- **Tried and approach:** `scripts/checks/check_apikey_burst.py` sends 14 concurrent GETs (ThreadPoolExecutor, all sent within 0.01 s) to the `twenty-four-hr-forecast` v2 endpoint and records status codes and any Retry-After. Ran no key twice, then the key in `x-api-key` twice, 15 s idle between runs. The key came from the environment and was never printed or written; only its presence was checked.
- **Learned:** No key: 6 x 200 and 8 x 429, both runs. `x-api-key`: 12 x 200 and 2 x 429, both runs. These match the documented limits (6 and 12 per 10 s). No 429 carried a Retry-After header.
- **Decisions and why:** Verdict "yes, under `x-api-key`", since successes doubled and both runs of each condition agreed. Did not try `Authorization: Bearer` or `api-key`, because that fallback was only for the case where `x-api-key` failed.
- **Stuck:** The system `python` has no `requests`; ran with `.venv\Scripts\python.exe`. A docstring with `\S` raised a SyntaxWarning; made it a raw string.
- **Challenges and questions:** Two runs per condition on one day, so this confirms the tier, not long-run behaviour. Back-off must be a fixed wait because there is no Retry-After. Committed as 6d86623 (two files only: the script and `docs/checks/apikey_burst.md`).

## 2026-10-21: EMA SES Chapter 3 workbooks into static data

- **Tried and approach:** Copied the two user-saved EMA workbooks (`SES_tabular...`, `SES_tidy...`) byte-for-byte into `coolcheck-data/static/ema_singapore_energy_statistics/`, rechecked SHA-256, wrote `provenance.json`, added a `SOURCES.md` row, added a section to `docs/checks/static_data.md`, read the header of sheet `T3.5` in read-only mode. Did not run `download_static.py`. Committed one file (`docs/checks/static_data.md`, f0e25fd) by name because another window is working in the repo.
- **Learned:** Both hashes match the ones taken earlier (1,526,537 and 6,138,682 bytes). T3.5 in the tidy file is `A1:G97895`; header `('Dwelling Type', 'Year', 'Month', 'Region', 'Description', 'Kwh Per Acc', None)`: the area column is called "Region", and column G has no header. The tidy workbook has 36 sheets (T1.1 to T7.3 plus a contents sheet).
- **Learned:** EMA Terms of Use PDF, "Terms of Use of Datasets", clause 20: "This is version 1.0 of the Singapore Open Data Licence." Clause 9 requires an attribution notice with a licence link, 6.1 excludes personal data, 7 forbids implying EMA endorsement. No single sentence says the EMA datasets are under SODL v1.0.
- **Learned:** `download_static.py` rebuilds `SOURCES.md` from every `*/provenance.json` on each run, and reads a top-level `bytes` with `:,` formatting.
- **Decisions and why:** Added top-level `bytes` (sum, 7,665,219) and `source_page` to `provenance.json` instead of editing the script, so a rerun regenerates the row. The source URL is recorded as user-supplied, not checked by script (ema.gov.sg is not fetchable). Installed `openpyxl` into `.venv` only; did not add it to `requirements-dev.txt` because the other window has that file modified.
- **Stuck:** The Read tool could not render the PDF (`pdftoppm is not installed`); used `pdftotext` from the shell. `ReadOnlyWorksheet` has no `dimensions`; used `calculate_dimension()`. `ModuleNotFoundError: No module named 'openpyxl'`; fixed by installing it in `.venv`.
- **Challenges and questions:** Is the clause-20 wording enough to call the EMA data SODL v1.0 in the write-up? Is "Region" in T3.5 a planning area (not checked; no analysis done)? Add `openpyxl` to `requirements-dev.txt`? `SOURCES.md` is outside git, so the new row is not versioned.

## 2026-10-21: Day 2 step 4, Bronze, Silver, labels and H10

- **Tried and approach:** Design reviewed twice, then one Lakeflow Declarative Pipeline (`coolcheck_pipeline`, serverless, triggered): Auto Loader (text) into `bronze.*_raw`; `silver.*_all` with C8 rules as warn-only expectations plus `fail_<rule>` columns; Auto CDC dedupe (live over backfill, then file time, path, content hash); `station_daily_label` and DQ views. Jobs `reconcile` and `nearest_station` (serverless, `max_retries: 0`). Logic in `src/coolcheck`; 13 pytest tests through Databricks Connect pass. Runs: validate-only update 1f01fe9d, Bronze-only refresh 6a844765, reconcile (bronze), normal update 284d69cd (about 3.5 min), reconcile (all), local distance matrix (shapely 2.2.0) loaded, `nearest_station` job. Commits 5fce608, 3a11102, 9d3ed07, 22ad7ce (not pushed).
- **Learned:** Bronze agrees four ways (local, progress.jsonl, Volume, Bronze): 642 files/2,563 lines WBGT, 642/7,687 rainfall, 641/641 forecast; bytes and sha256 equal. Silver equals the raw totals: 1,036,005 WBGT, 11,893,198 rainfall, 4,673 forecast records; no duplicate or conflicting copies, quarantine empty.
- **Learned:** Rule failures: WBGT NA 2,894; WBGT outside 20-36 °C 79 (74 below, 5 above; no label changes); rainfall station not in the page's list 111; forecast not 24 h 527, end before start 6, start a year off 3, text disagrees 522. Labels reproduce `wbgt_high_days.md` (10,834 station-days, 535 High, 247 High days; original 8: 5,014/166/128). Coverage rule: 67 low-coverage station-days (52 Low and 10 Moderate leave training, 5 High kept), 10,772 usable.
- **Learned:** Forecast: the notes' "end before start" gives 6 records, all issued 30-31 Dec 2025; the 2023 part of the notes' 12 is outside the files. 521 records have a 48-h window, all issued in 2025, text always 24 h, 358 of them 23:xx issues; with the stored validity the 00:15 rule would carry the 07-19 23:02 issue into 2025-07-21.
- **Learned:** Sep to 19 Oct 2026: 35 distinct High dates (23 without S142); S142 holds 31 of 70 High station-days. H10: 0 of 35,310 area-days without a station; on 2026-10-20 only Clementi differs from the all-stations nearest (S130 silent since 2026-06-24); worst distance 8.54 km (Punggol) to Sep 2025, then 4.89 km (Sembawang).
- **Decisions and why:** One pipeline, not a plain job (the deck says "1 pipeline"; Free Edition allows one). Flag, never drop. Forecast 2025-07-20: skip, not carry (the previous issue is for another day). H10 reporting = a counted reading in the 7 days before the 00:15 cut-off, not "has a label that day" (leakage). Boundary MP2025 by default, MP2019 for comparison (C1). Forecast validity fix goes into the Day 3 feature code (text, or start + 24 h); Silver forecast code unchanged. `pipelines.reset.allowed=false` on Bronze.
- **Stuck:** `[UNRESOLVED_COLUMN] ... updated_ts_raw` (column dropped before hashing; fixed). `from_json` returns a struct of NULLs for a malformed line, so unparsable lines need `json_object_keys`. On serverless, `isNull()` of `element_at(array literal, NULL)` came back false; replaced by CASE. `[NOT_COLUMN] Argument condition should be a Column` (fixed). Cost unknown: `system.billing.usage` still ended at 13:00 SGT after 17:45.
- **Challenges and questions:** Pipeline cost once billing catches up. `pipelines.reset.allowed` is set but not tested by a full refresh, and I believe it does not protect against deleting the pipeline (Day 7 clean redeploy). Why NEA's 2025 forecasts carry 48-h end times (unknown). S187's 'move' is a first-day glitch (2025-09-01, 9.4 km off), not a real move; the 23 rainfall stations are a third-decimal comparison, not measured. Western Islands uses a point on the surface. S142 (Sentosa) was the nearest reporting station for Bukit Merah and Outram 2025-09-02 to 2026-01-15 (136 area-days each): Day 3 to decide whether island or offshore stations may serve mainland areas.

## 2026-10-21: Day 2 step 5, live collector (GitHub Actions)

- **Tried and approach:** Read-only design note first, approved with changes (2-h window, no watermark, air temperature out until Day 5, midnight sweep, run id in file names, Volume root as a repository variable, explicit SGT with tests, overlap test, lateness exclusion, SHA-pinned actions, no pull_request trigger). Built `scripts/collector/collect.py` on the backfill's `Fetcher` (its back-off list is now a parameter, default unchanged), `.github/workflows/collector.yml`, `requirements-collector.txt` (all dependencies pinned to the `.venv` versions), `scripts/checks/collector_overlap.py` and 28 collector tests against a fake API. Upload is one plain Files API PUT per file with overwrite=false, not SDK 0.154's `files.upload`, which can probe or go multipart. Two local dry runs to `coolcheck-data/collector_dryrun` (outside the repo and outside `raw/`).
- **Learned:** Repo is private (unauthenticated GitHub API returns 404). GitHub docs: each job is rounded up to a whole minute; Pro includes 3,000 minutes, reset each billing cycle; schedules can be delayed or dropped at high load, including the start of every hour; schedule and workflow_dispatch need the workflow on the default branch; scheduled-run emails go to whoever last changed the cron line.
- **Learned:** Dry runs at 18:27 and 18:31 SGT: 3 calls and 2.1 s each, about 227 KB per run. Page 1 held WBGT 25 timestamps x 30 stations (12:15-18:15), rainfall 25 timestamps (16:30-18:30), forecast 4 issues. Overlap of the two runs: 2,825 identical copies (WBGT 750, rainfall 2,071, forecast 4), 0 conflicts.
- **Learned:** Tests: 52 local pass (collector and backfill); 14 Silver tests pass through Databricks Connect (23 s).
- **Decisions and why:** Fixed 2-h window, not a watermark: page 1 already spans about 2 h of rainfall and 6 h of WBGT, and Actions keeps no state between runs. Every page of yesterday in the 00:xx SGT hour. A 404 on today's WBGT or rainfall page 1 from 01:00 SGT fails the feed (forecast unchanged). Live files go under `<feed>/live/` so Silver ranks them above backfill, with a new name per run because Auto Loader loads a path once. Kill switch: repository variable `COLLECTOR_ENABLED` (a skipped job costs no minutes). Lateness ignores readings timed before the first live file, which carries about 6 h of history. Rejected: air temperature now (no Bronze table; the panel needs only the latest value); `READ_VOLUME` (the collector never lists; user to revoke).
- **Stuck:** No YAML parser or workflow linter locally (`ModuleNotFoundError: No module named 'yaml'`), so GitHub will be the first parser. Two test mistakes of mine, code unchanged: `AttributeError: 'function' object has no attribute 'pages'`, and the lateness test expected the 09:50 reading in the first live file to be judged, though every reading in that file is timed before it lands.
- **Challenges and questions:** Not done: OAuth secret, GitHub secrets and variables, `READ_VOLUME` revoke, push, dispatch runs, acceptance checks in Databricks, deploy of the lateness change, the D9 job (planned tomorrow, hourly). Untested: data.gov.sg from GitHub's runners; whether `WRITE_VOLUME` alone allows the PUT; the trial ends 30 Oct and the finale is 4 Nov (a Free Edition service principal is unverified). Commits fd559b5, 5bce776, 1449bd2, not pushed. For the mentor: is collection outside Databricks acceptable for the brief's real-time requirement?

## 2026-10-21: Day 2 step 5, first collector dispatches and the principal's real permissions

- **Tried and approach:** The user created the OAuth secret, set the GitHub secrets and variables and pushed; four collector workflow runs followed (runs 39589083284, 39589832036, 39590361248 failed; 39590724749 succeeded). Outcomes are as the user reported them: the run logs were not read here, and which runs were dry runs is not recorded. I then re-read the principal's permissions with the CLI (read-only) and updated `docs/checks/service_principal_and_volume.md` and the `files_api_uploader` docstring (commit 5f065b5, not pushed).
- **Learned:** `grants get` on 21 Oct: `coolcheck-collector` has `READ_VOLUME` and `WRITE_VOLUME` on `coolcheck.bronze.raw_files`, `USE_SCHEMA` on `coolcheck.bronze`, `USE_CATALOG` on `coolcheck`; entitlement `workspace-consume` (Consumer access), active. Per the user, the OAuth secret has scope `all-apis`, a 30-day life and expires about 20 Nov 2026 (secret not re-read).
- **Learned:** Per the user, the three failures were because the SDK requests `all-apis`, the Files API needs a workspace entitlement, and the upload needs `READ_VOLUME` as well as `WRITE_VOLUME`; the user did not say which run hit which.
- **Decisions and why:** `READ_VOLUME` stays. This corrects the earlier step-5 entry above (its "Rejected: `READ_VOLUME`", "user to revoke" and "whether `WRITE_VOLUME` alone allows the PUT" lines): `WRITE_VOLUME` alone did not work. I did not edit that entry, per the log rules. The docstring now lists all required permissions.
- **Stuck:** Nothing new. The earlier assumption that the collector would need only write access was wrong; the cause was found by the user from the failed runs, not by me.
- **Challenges and questions:** Not yet done or not seen: the acceptance checks on what run 39590724749 uploaded (files in the Volume, pipeline update, overlap on real runs, 0 conflicts, late flag), setting `COLLECTOR_ENABLED`, the first scheduled run, the Silver change deployed, the D9 job. The secret expires after the trial (30 Oct), so Day 7 re-pointing needs a new principal, grants, entitlement and secret on Free Edition (unverified there). Steady-state Actions minutes per run are still unmeasured.
- **Correction (same day):** which run failed for which reason, as the user reported it: 39589083284 the OAuth secret's `all-apis` scope was not assigned; 39589832036 the principal had no workspace entitlement; 39590361248 it lacked `READ_VOLUME`. Dry run 39588791785 succeeded first, so these were the first three real dispatches; 39590724749 then succeeded. This replaces "the user did not say which run hit which" above; the mapping is also in `docs/checks/service_principal_and_volume.md`.

## 2026-10-22: Day 2, HDB block geocoding with OneMap search

- **Tried and approach:** `scripts/static/geocode_hdb.py` (resumable: append-only `progress.jsonl`, lock, pace 3 calls a second, 429/401/403 stop rules, token from `ONEMAP_TOKEN` only and scrubbed from every output) with 78 pytest tests on a fake API, then 20-block dry runs (`dryrun_20`, `dryrun_20b`). Two changes on review: a 6-digit postal code needed for a confirmed match (else matched_no_postal), and pages 2 to 5 read only when page 1 has no match. Then the G1 postal-suffix rule and the G2 note, applied with `--report-only`, no call. Dropped: counting every multi-candidate block as ambiguous (check 5 shows a block plus a facility at the same address).
- **Learned:** Full runs (21 Oct 21:34 and 21:56 SGT, `runs.jsonl`): 10,817 calls, all HTTP 200, 3,613.7 s, no 429, no retry, no stop, no page 2 to 5 read. Only 2 blocks had more than one page (1 THOMSON RD, 678 WOODLANDS AVE 6); both matched on page 1.
- **Learned:** Before G1: matched 9,181, matched_same_place 1,573, matched_no_postal 10, ambiguous 53 (confirmed 10,754). Postal code ends in the block number (leading digits, zero-padded to 3) for 10,746 of those 10,754 (99.93%); the 8 exceptions are 1 TOH YI DR and 1A to 1G CANTONMENT RD.
- **Learned:** After G1 (`--report-only`): matched_postal_rule 53 (all 53 ambiguous blocks had exactly one fitting code; 4 are rental), ambiguous 0, not_found 0, confirmed 10,807 of 10,817. The 10,764 other blocks are unchanged. The 10 matched_no_postal blocks are tenant records (ElderCare, child care, HDB public shelters); 703 TAMPINES ST 71 is named "SHERWINN EDUCATION CENTRE (TAMPINES ST 33)".
- **Learned:** Tests: 87 pass in `tests/static`; mutation checks (25 on the first version, 8 more on the postal rule) were all caught.
- **Decisions and why:** Not guessing: candidates at different places stay ambiguous unless the postal rule resolves them (G1, user's decision). G2: keep the 10 coordinates with confirmed=N and a note; no re-query. Pages 2 to 5 stop at the first page with a match, to save calls. Rejected: a looser rule (any trailing digit), which would pick wrongly for block 5 versus 560015.
- **Stuck:** My mutation script lost its `\n` in a bash heredoc (search string count 0, `AssertionError`); rewrote it with the Write tool. A mutant name with a colon failed on Windows (`NotADirectoryError: [WinError 267]`); renamed. Three older ambiguous-case tests used postal codes the G1 rule now resolves; I changed the codes, not the rule.
- **Challenges and questions:** Pages 2 to 5 are tested only on the fake API, never on the real one. 4C ST. GEORGE'S LANE keeps "HDB PUBLIC SHELTERS" and 703 TAMPINES ST 71 keeps a centre named for another street; both coordinates are unchecked against the block's real position. Are OneMap's terms open to storing coordinates (still open from check 5)? The token expires 24 Oct 2026 12:58 SGT. Commit 0754c6e is local, not pushed.

## 2026-10-22: Day 2, targeted EDA on the 16 Jan 2025 to 31 Aug 2026 window

- **Tried and approach:** `scripts/analysis/eda.py` (Databricks Connect, serverless) writes `docs/checks/eda.md` and 7 charts in `docs/checks/eda_figs/`; 11 pytest tests in `tests/analysis`. The window is enforced in code: a `Reader` filters every scan by date and refuses SQL that names a `coolcheck.` table; `collect()` asserts every frame is inside the window; the report ends with an audit of first and last date per frame (all inside; 1 Sep to 19 Oct 2026 never read). Seven checks: base rate, month, persistence, label robustness, station effects, feature signal and leakage, missingness. `matplotlib` was the only package added. Commit 91b0d77, local, not pushed.
- **Learned:** 465 High of 9,365 labelled station-days (5.0%); 1,297 of 32,480 area-days (4.0%). Back-test months Jul 2025 to Aug 2026: 421 High station-days, min 0, median 22, max 97 a month; 8 of 14 months have under 30; 2026-01 has none.
- **Learned:** P(High tomorrow given High today) is 35.7% against a 5.0% base rate (station-days, lift 7.17); NE monsoon has 7 High today and 0 High tomorrow. Inter-monsoon 1 lift is 1.14 in 2025 and 4.35 in 2026.
- **Learned:** 260 of 465 High station-days (55.9%) rest on 1 or 2 High readings (original 8: 114 of 150, 76.0%). First High reading: median 12:45, earliest 09:45, latest 16:15.
- **Learned:** S142 has 134 High of 365 days (36.7%) against 3.4% for the original 8 on the same dates. Without S142, S137 and S135 the rate is 3.0% (250 of 8,449); the three alone 23.5% (215 of 916).
- **Learned:** Features: yesterday's peak WBGT at the nearest station AUC 0.77 (own station 0.80), rainfall 0.47, forecast high temperature 0.60, forecast text 0.58 (in-sample). None met the flag rule (AUC 0.85 or above, or a band with 30 or more rows and a High rate of 50% or more). No forecast issue matched 3 of 592 target dates. Short days 18 WBGT, 17 rainfall, 1 forecast; NA readings 2,199 (the table's n_na sums to 2,199).
- **Decisions and why:** Did not read `gold.area_nearest_station_daily`: its `targets` CTE takes max(sgt_date) over all labels, which would reach the held-out days. Re-ran its builder (`nearest_station_sql`, mp2025, 15 min, 7 days) on window-filtered labels. Not checked: that the deployed view uses those parameters, and that the two agree on in-window dates. Rejected: reading the view and dropping rows afterwards. No interpretation and no feature choice, per the brief. Area-day intervals are too narrow (55 areas share 31 stations); the report says so.
- **Decisions and why:** The plan's 2,894 NA and 21 short days differ from 2,199 and 18. Per the user, the plan counted to 19 Oct 2026, so the window explains the gap; the flags now say so (the script cannot test it). I added a short-day flag beside the NA one.
- **Stuck:** `matplotlib` missing, installed. Wilson lower bound for 0 of 10 returned -2e-17, clamped to [0, 1]. A "|" in a column name broke markdown tables; renamed. Years printed as "2,025" and hours as "0.00"; fixed with plain-integer columns. `-W error::DeprecationWarning` failed on an unrelated `logging.warn`; not a code issue.
- **Challenges and questions:** Four stations (S131, S133, S138, S910) have 5 labelled days from 2026-08-27. 16 stations have a High rate at least double or at most half the original-8 rate on the same dates. The committed report header still reads "git 917e39a (script not committed)". For the mentor: the High label rests on 1 or 2 readings for 55.9% of High station-days; is that acceptable for a next-day target?

## 2026-10-22: Day 2, Active Ageing Centre list and park polygons (survey; work run 21 Oct 22:36 to 22:52 SGT)

- **Tried and approach:** Pulled the whole data.gov.sg catalogue listing (4,664 datasets, 467 pages) and searched names and descriptions for AAC, senior and park terms; downloaded the candidates with the existing `datagov.py` helpers (four new folders under `coolcheck-data/static/`, each with `provenance.json`, plus `SOURCES.md` rows); `scripts/checks/static_data_2.py` prints every number in `docs/checks/static_data_2.md`, committed as `2dea1df` (not pushed). No geocoding, no OneMap call. Read the AIC and Age Well SG terms from saved HTML; did not scrape either. Dropped: operator sites (one set of terms each) and the SupportGoWhere locator.
- **Learned:** No complete current AAC list is open data. MOH's Dementia Friendly Go-To-Points file (831 points, updated 2026-08-20) has 93 AACs plus 4 SACs by name, all with 6-digit postal codes and coordinates: 42% of SingStat's 223 for 2024. Against Eldercare's 66 SAC/Silver ACE/AAC points, 43 share a postal code; the union is 120 postal codes, which is not an AAC count.
- **Learned:** AIC terms 7.2 and 5.1 and the Age Well SG (MOH) terms bar reproducing or caching the sites without written permission; neither site offers a download. 22 of 831 Go-To-Points names contain U+FFFD.
- **Learned:** NParks Parks and Nature Reserves is 462 polygons, with the same 462 names as the Parks point file we held; Park Connector Loop is 878 line features, about 336.5 km (check2.md: 336.1 km). The dataset pages state "Free forever for personal or commercial use, under the Open Data Licence" (read in the page HTML for seven datasets).
- **Learned:** Park share by planning area depends on the definition: NParks with all 462 polygons has a maximum of 0.835 (Central Water Catchment), without the 7 reserves and Pulau Ubin 0.315 (Museum); the URA Master Plan 2025 park layer correlates 0.30 with that (0.24 with reserves in), and 117 of its 426 polygons are interim.
- **Decisions and why:** Use the 93 plus 4 as a labelled partial AAC layer and keep Eldercare as a separate 2016 layer (deduplicate by postal code), rather than treat 120 as the AAC count. Proposed excluding nature reserves from the park share; the user has not decided. Did not download the 190 MB Master Plan 2025 Land Use layer; waiting for the user.
- **Stuck:** The first commit was held: `static_data_2.md` was written after the run log, and a number check found loop-segment counts and a flat-area check that only existed in scratch runs, and `check3.md` cited where `check2.md` was right. Fixed at the user's request: added both prints to the script, re-ran it, saved the new log, reworded the Land Use sizes, then committed. Other errors: "Browser extension is not connected" (Chrome tools; SupportGoWhere terms stay unread, the page needs JavaScript); `UnicodeEncodeError: 'charmap' codec can't encode character '�'` (fixed with `sys.stdout.reconfigure`); the catalogue crawl passed the 300 s foreground limit and ran in the background.
- **Challenges and questions:** Who chose the Go-To-Points sites, and which towns are missing from the 93, are unknown. Ask the mentor for an AAC contact, or ask MOH or AIC in writing for the full list under the Open Data Licence. Which park definition (nature reserves in or out, NParks or the Land Use zoning) goes into the score, with a sensitivity run reported either way. Whether any Eldercare-only SAC has closed or been renamed.

## 2026-10-22: Day 2, OneMap page 2 on the real API, and the first 700-block run (work run 21 Oct 21:30 to 21:38 SGT)

- **Tried and approach:** Before committing `scripts/static/geocode_hdb.py`, made one real page-2 call for 1 THOMSON RD through the script's own `Client` (same session headers, token from `ONEMAP_TOKEN`, nothing of it printed; output piped through a sed mask as a second guard). Ran `pytest tests/static` (78 passed), committed the script and three test files by name as `917e39a` (not pushed), then ran stage 1: `geocode_hdb.py --limit 700` into `coolcheck-data/geocode`.
- **Learned:** 1 THOMSON RD, pages 1 and 2: `pageNum` 1 and 2, `found` 35, `totalNumPages` 4, 10 results each, HTTP 200 on both. Page 1 is `1 | THOMSON ROAD | 300001` plus nine `1 | MOUNT PLEASANT ROAD | 298333`; page 2 is ten `1 | MOUNT PLEASANT ROAD | 298333`. BLK_NO, ROAD_NAME and POSTAL alone do not show whether page 2's Mount Pleasant rows are new records.
- **Learned:** Stage 1 (`runs.jsonl`, started 21 Oct 21:34:19): 700 blocks, 700 calls, 0 for pages 2 to 5, 0 retries, statuses {200: 700}, 233.5 s (about 3 calls a second). matched 599, matched_same_place 94, ambiguous 7, not_found 0, matched_no_postal 0; confirmed 693 of 700, 633 of them rental blocks. 0 confirmed records outside the Singapore box. 1 block had more than one page and matched on page 1.
- **Learned:** The 7 ambiguous blocks: 128 BT MERAH VIEW (spread shown as 50 m, so just over the 50 m limit), 72 GEYLANG BAHRU 59 m, 727 CLEMENTI WEST ST 2 77 m, 100 BEDOK NTH AVE 4 75 m (each with at most one postal code among the candidates); 52 CHIN SWEE RD 186 m and 1 BEACH RD 1,497 m (two different postal codes); 1 TG PAGAR PLAZA 158 m (082001 twice).
- **Decisions and why:** Treated page 2 as different from page 1 because page 1's THOMSON ROAD row is not on page 2, and committed. This was a judgement: the fields asked for could not rule out that the Mount Pleasant rows repeat. Rejected: another call to compare SEARCHVAL, BUILDING and coordinates, which was outside the one call agreed. Changed no matching rule after the run.
- **Stuck:** My first command started an interactive Python (an empty heredoc to `python3`: "warning: can't use pyrepl: [WinError 6] The handle is invalid."), which was harmless and ended with the command. The probe cost 2 calls, not 1, because page 1 is needed for the comparison.
- **Challenges and questions:** Whether page 2's rows for 1 THOMSON RD are distinct records is unchecked (it needs the full records). The entry above says pages 2 to 5 were tested only on the fake API; one real page-2 request has now returned a normal result, but no real block has needed pages 2 to 5 (0 extra page calls in the 700-block run).
