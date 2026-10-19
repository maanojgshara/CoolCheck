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
