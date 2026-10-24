# The approval App and the agent loop: design note

Written 24 Oct 2026 by window B, from the plan the user approved at about 17:30 SGT (all seven recommendations, plus six additions). It turns Guide D13 and M6 into a Databricks App whose Approve button writes `pending_approval`. Phase 1 (this note's first part) calls the three tools directly; phase 2 adds the agent loop (`coolcheck.agent.draft_plan`), with phase 1 as its fallback (decision 4).

## Where

- `src/app.py`: the Streamlit page. `src/requirements.txt`: its packages (databricks-sdk 0.154.0 as in `.venv`, mlflow-tracing 3.16.1, streamlit 1.50.0).
- `src/coolcheck/plan.py`: the tools through the SQL warehouse (Statement Execution API, typed parameters), the per-tier template, the notices, the plan text, masking and the approval MERGE. Python 3.11 compatible.
- `src/tables/pending_approval.sql` and `scripts/static/create_pending_approval.py` (`--catalog`, `--profile`, `--print-sql`): the table, created only on the user's word.
- `resources/coolcheck_app.app.yml.draft`: the App `coolcheck` and the experiment `coolcheck-agent`, dev target only; renamed to `.yml` for its first deploy. The App's source is all of `src/`, so it runs the same `coolcheck` package as window D's evaluations.
- Tests: `tests/agent/` (local, fake warehouse).

## The App

- **Inputs:** the briefing date (the latest `target_date` in `gold.area_heat_risk` first), the call capacity (800, a placeholder until the user decides), calls per volunteer (25, an assumption used only when a request gives volunteers) and a region (whole island or one of five).
- **The draft:** a header (date, region, when the forecast was scored in SGT, the capacity and where it came from), the summary (template or agent), the notices, the plan (each area given calls: tier sentence, reason, actions, blocks with calls and partial, the nearest refuge rounded to 10 m in a straight line, calls left) and a footer ("Draft only: nothing has been sent"). Areas without calls are in a table; every tool call with its arguments and rows is listed.
- **Notices, always shown by code:** a missing forecast issue; every Not-rated area with High heat; and when no rated area is High, the plain sentence "No rated area is High on <date>. <Area> has High heat but is Not rated …" (Southern Islands on 23 Oct).
- **Approve:** one MERGE on `approval_id` (made with the draft), insert only, so a second press writes nothing; the button is off without the Apps sign-in header. Nothing is sent: the App imports no messaging or raw network library (a test checks), and its only calls are the warehouse, MLflow and, in phase 2, the model gateway.
- **The approver** is the Databricks user ID from the Apps proxy's `X-Forwarded-User` header, never a name or e-mail; the repo holds only the header name. Diagnostics shows the header's shape (numeric ID or not), not its value.
- **Diagnostics** (collapsed, below the page): the self-check as the App's service principal, positive (the view, the three functions, a MERGE-free `INSERT … WHERE false` into `pending_approval`, a trace) and negative (`gold.heat_forecast` and `silver.block_access` must be refused).

## pending_approval

`<catalog>.gold.pending_approval`, one row per Approve: `approval_id`, `approved_at`, `approved_sgt_date`, `target_date`, `region`, `call_capacity`, `capacity_basis`, `calls_allocated`, `source` (agent or template), `fallback_reason`, `request_text` (masked), `draft_text`, `plan_json`, `tool_calls_json`, `llm_model`, `mlflow_trace_id`, `forecast_run_id`, `forecast_scored_at`, `approved_by`, `app_commit`, `status` (always `approved_not_sent`). Every column has a comment.

## Grants (the App's service principal, applied by the deploy from the App's resources)

CAN_USE on the Serverless Starter Warehouse; EXECUTE on the three functions (all `SECURITY DEFINER` in Unity Catalog, so no SELECT on the tables they read); SELECT on the `gold.area_heat_risk` view; SELECT and MODIFY on `gold.pending_approval`; CAN_EDIT on `coolcheck-agent`. Phase 2 adds EXECUTE on `system.ai.meta-llama-3-3-70b-instruct`. USE CATALOG and USE SCHEMA by CLI only if the deploy does not add them. Nothing on `gold.heat_forecast` or `silver`.

## Privacy

Before a request is stored or sent to the model, NRIC-like strings (S, T, F, G or M, 7 digits, a letter) and 8-digit phone-like numbers starting with 6, 8 or 9 (optionally with +65, a space or a hyphen) are masked, and the page says so beside the "no names or personal details" note.

## Later

- The free target gets the App and the experiment once its functions and `pending_approval` exist (Sunday, window A's redeploy).

## Phase 2: the agent loop (`src/coolcheck/agent.py`)

- `draft_plan(request, *, target_date, default_capacity, calls_per_volunteer, region, catalog, runner or warehouse_id, workspace_client, model, forecast, max_rounds=4, max_tool_calls=6, timeout_s=90)` returns a `coolcheck.plan.Draft`: `draft_text`, `summary_text`, `source` (agent or template), `fallback_reason`, `tool_calls` (each with the model's arguments, the SQL arguments, rows, error, time), `checks` and `trace_id`. The App and window D's evaluations call the same function.
- Model: `system.ai.meta-llama-3-3-70b-instruct` on `/ai-gateway/mlflow/v1/chat/completions` through the workspace client, temperature 0. Tools: the three functions, described by their Unity Catalog comments; for `get_priority_areas` the model gives only the request's values (volunteers, calls per volunteer, calls, region) and the App fixes the date. Values in the request override the form; the multiplication is `coolcheck.plan.capacity_from`.
- Checks on the model's summary: every number (digits, in any script) is found in a tool result or an input, allowing rounding (a multiple of 100 within 50, of 10 within 5) and shares as percentages; number words fail unless a tool result uses the same word (for example "four languages" in the tier actions); P(High), probabilities, scores, claims that something was sent, and medical terms fail. Any failure, model error, timeout, cap or a missing `get_priority_areas` call gives the template with the reason on screen.
- The request is masked before the model sees it or the row stores it. A stale-forecast notice ("No forecast for today yet; this is the plan for <date>") tops the page when the newest date is before today on the Singapore clock (UTC+8 in code, not the warehouse's `current_date()`).
- Deploy 2 adds EXECUTE on the model service (an App resource) and `LLM_MODEL`.

## Checks (24 Oct 2026)

- Local: `tests/agent` 66 passed (plan 42, agent 24).
- Live, as the user, reads only: `briefing_dates` gave 24 and 23 Oct; the 24 Oct draft at 800 calls equals the function's read-back (Toa Payoh: 208A WOODLEIGH LINK 312 of 312, 170 LOR 1 TOA PAYOH 308 of 308, 5 LOR 7 TOA PAYOH 180 of 258 partial) with the note on Southern Islands and Sungei Kadut; 23 Oct gives the "No rated area is High" sentence; the page ran headless (Streamlit AppTest) with no exception and Approve off without the sign-in header.
- `bundle validate -t dev` with the App file renamed in a scratch worktree: valid; the App is named `coolcheck`, the experiment `[dev …] coolcheck-agent`.
- Deploy 1 (19:00 SGT, from `5470b7e` in a clean worktree, after the guard: 2 creations, 4 job updates changing only `--git-sha`, 0 deletions): the App `coolcheck` started; its principal's effective grants were exactly the planned ones, and the deploy added USE CATALOG and USE SCHEMA itself; none on `gold.heat_forecast` or `silver`.
- The loop's first real request, locally as the user (19:35 SGT): "Only 8 volunteers tomorrow. Which blocks should we call first?" for 24 Oct: the model called `get_priority_areas` with `{volunteers: 8}`, code made 200 calls, the summary passed the checks (2 rounds, 16 s). In the page, headless, a North-East request with an NRIC: masked, 200 calls to Blk 182 RIVERVALE CRES, summary passed. A first page run fell back on "four" (from the tier actions), which led to the number-word rule above.
