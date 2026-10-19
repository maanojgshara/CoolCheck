# CoolCheck (DAISI Round 2, team AIsenal, problem B1 HeatGuard)

Next-day heat briefing for community care teams in Singapore: forecast tomorrow's heat stress (WBGT), combine it with where seniors live and how far they are from a cooling refuge, rank planning areas and blocks, and let an approval-gated agent draft outreach. Built on Databricks (trial workspace, US$400 credit).

## Plan and reference (read the section you need, never the whole file)
- `../CoolCheck Project.md`: the plan. Decisions are in section 14, the day-by-day schedule in section 15, Day-1 checks and agreed fallbacks in section 12.6.
- `../DAISI.md`: the organisers' brief and Databricks limits.
- The plan overrides this file where they differ; tell me if they conflict.

## Environment
- Databricks CLI profile: `coolcheck`. Pass `-p coolcheck`. Bundle target: `dev` (development mode).
- Python 3.12 in `.venv` (Windows: `.venv\Scripts\activate`). `databricks-connect==17.3.*`. Do not use any other Python.
- Serverless only. Never create clusters or SQL warehouses. Pipelines run in triggered mode.
- Unity Catalog catalog `coolcheck`, schemas `bronze`, `silver`, `gold`, `ml`.
- Time zone is Asia/Singapore everywhere: set `spark.sql.session.timeZone`, derive an explicit `sgt_date` column. Serverless defaults to UTC.

## Rules
- Never print, log, write or commit a token, password or key. Do not run `databricks auth token`. Secrets live in a Databricks secret scope.
- No personal data anywhere.
- Heat categories (NEA) are Low / Moderate / High. Area risk is Low / Medium / High. Do not mix them.
- Read WBGT category cut-offs from the API field; do not hard-code them.
- Every number in the write-up must come from a logged run. If a result is weak, report it as it is.
- Heat is planning-area level. Blocks rank vulnerability, never heat.
- The agent only drafts. A person approves. Allocation to call capacity is done in code, not by the LLM.

## Working
- Plan first for anything touching several files. Keep changes small.
- Before any deploy: `databricks bundle validate -t dev`. Deploys and runs ask me first.
- Test transformations with pytest on small fixtures through Databricks Connect; show the output as evidence.
- Commit after each working step with a clear message.
- Only Claude Code deploys to the workspace. Do not run two deploys at once.
- At the end of a session, run `/log` to append an entry to `docs/build-log.md` (tried and approach, learned, decisions, stuck, questions). It is the shared record the mentor asked for.
