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
