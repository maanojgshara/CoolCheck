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
