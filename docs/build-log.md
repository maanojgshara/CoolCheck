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
