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
  - A value from the model counts only if its number is in the request (digits in any script, or the number words the check knows, combined as in "two hundred and fifty"); otherwise the form's value is used and `checks.ignored_arguments` records what was dropped. A stated 0 counts ("0 volunteers" gives 0 calls).
  - The region is the model's when it sends one (ALL for the whole island) and the form's when it sends none, never an earlier call's; an unknown region goes back to the model as an error naming the five.
  - The tool reply adds three values computed in code, which the prompt asks the summary to use: `high_tier_areas`, `not_rated_high_heat` and `calls_left_over` (the last area's `calls_left`).
- Checks on the model's summary: every number (digits, in any script) is found in a tool result the model saw or an input, allowing rounding (a multiple of 100 within 50, of 10 within 5, any other whole number within 0.5, so 448 m for 448.34 m) and shares as percentages; number words fail unless a tool result uses the same word (for example "four languages" in the tier actions); P(High), probabilities, scores, claims that something was sent, medical terms, a tier given to a block ("a High-tier block") and "no area is in the High tier" when one is all fail.
- If the model does not call `get_priority_areas`, the code runs it with the form's values (a TOOL span like the model's calls; `checks.get_priority_areas` says so) and keeps the model's reply if it passes the checks: a refusal or a block lookup's "not found" reaches the coordinator with the plan below it. Any failure, model error, timeout or cap gives the template with the reason on screen.
- The request is masked before the model sees it or the row stores it. A stale-forecast notice ("No forecast for today yet; this is the plan for <date>") tops the page when the newest date is before today on the Singapore clock (UTC+8 in code, not the warehouse's `current_date()`).
- Deploy 2 adds EXECUTE on the model service (an App resource) and `LLM_MODEL`.

## Checks (24 Oct 2026)

- Local: `tests/agent` 66 passed (plan 42, agent 24).
- Live, as the user, reads only: `briefing_dates` gave 24 and 23 Oct; the 24 Oct draft at 800 calls equals the function's read-back (Toa Payoh: 208A WOODLEIGH LINK 312 of 312, 170 LOR 1 TOA PAYOH 308 of 308, 5 LOR 7 TOA PAYOH 180 of 258 partial) with the note on Southern Islands and Sungei Kadut; 23 Oct gives the "No rated area is High" sentence; the page ran headless (Streamlit AppTest) with no exception and Approve off without the sign-in header.
- `bundle validate -t dev` with the App file renamed in a scratch worktree: valid; the App is named `coolcheck`, the experiment `[dev …] coolcheck-agent`.
- Deploy 1 (19:00 SGT, from `5470b7e` in a clean worktree, after the guard: 2 creations, 4 job updates changing only `--git-sha`, 0 deletions): the App `coolcheck` started; its principal's effective grants were exactly the planned ones, and the deploy added USE CATALOG and USE SCHEMA itself; none on `gold.heat_forecast` or `silver`.
- The loop's first real request, locally as the user (19:35 SGT): "Only 8 volunteers tomorrow. Which blocks should we call first?" for 24 Oct: the model called `get_priority_areas` with `{volunteers: 8}`, code made 200 calls, the summary passed the checks (2 rounds, 16 s). In the page, headless, a North-East request with an NRIC: masked, 200 calls to Blk 182 RIVERVALE CRES, summary passed. A first page run fell back on "four" (from the tier actions), which led to the number-word rule above.
- Fixes from window D's evaluation (`docs/checks/agent_eval.md`: 4 of 20 on the first pass against `941dcbe`), in the user's order: the request-number rule for the model's values, `get_priority_areas` in code when the model skips it, the region rule, rounding to the unit, no tier for a block, and the two prompt lines (Not-rated High heat, calls left over). `tests/agent` 116 passed (agent 56).
- Live spot-check of those fixes (24 Oct, 22:00 to 22:15 SGT), as the user, reads only, tracing off, one try per scenario. This is not D's evaluation: there was no grader.
  - All 10 of D's scenario requests run (A01, B02, B03, C01, C03, D01, G01, G04, L01, R01) were agent-written with every number grounded.
  - L01: the model sent `{volunteers: 8, calls_per_volunteer: 0, call_capacity: 0}`; the 0s were dropped, giving 200 calls in the East. C01: `{volunteers: 0}` gave 0 calls. B03: the model's `call_capacity: 0` was dropped, so the form's 800 ran; its 448 m and 979 m distances passed.
  - G01, G04 and B02: the model's reply was kept, with `get_priority_areas` run in code. C03: "40309 calls are left over".
  - The first wording of the D01 line ("If no area is in the High tier, say so") made 4 of 10 summaries claim that falsely for 24 Oct, when Toa Payoh is High (C01, C03, R01, B03). It now depends on `high_tier_areas`, and the check above fails the claim. On a rerun of eight scenarios none made it falsely; L01 said it for the East, where it is true.
  - D01 named Southern Islands as High heat but Not rated, and said no rated area is High, in 3 of 4 runs.
  - Left for D's rerun:
    - R01: the model sent ALL for "the South region" and did not say South is not a region.
    - G04: the refusal said heat levels are not provided, though the tools give them per area.
    - D01: 2 of 4 runs wrote "a refuge about 0 m away" for a refuge at the block.
- Deploy 3 (22:54 to 22:57 SGT, from `7f1ec30` in a clean worktree, after the guard): the plan had 0 creations, 6 updates and 0 deletions; the App's only change was APP_COMMIT, the four jobs' only change was the git SHA, and the briefing dashboard went to `4ea632f` (four pages). `bundle run coolcheck_app` started a new deployment, which was running the new code.
- Second round (24 Oct, after deploy 3; not deployed, for D's next run and one deploy on Sunday):
  - `3174ca7`: the "no High tier" sentence names the plan's region ("No rated area in the North-East region is in the High tier.") in the template, the notices and a sentence the model copies (`no_high_tier_sentence`); the check fails such a sentence in a regional plan if it does not name the region.
  - `1ff4473`: notes written by code. A lookup that found nothing; a region that is not one of the five, whether the model sent it or the request names "the South region"; the model's values that were not used; calls left over, unless the summary already gives the number. (The plan section's per-area "calls left after this area" does not count as saying it.)
  - `3c32ef3`: a planning area named in the reply must be in a tool result the model saw, or in the request. The 55 Master Plan 2025 names are compared using HDB's abbreviations.
  - `6278b7b` and the next commit: the G04 line. A question about a block's heat is in scope; the reply gives the area's heat level, never "not available".
  - `4a3d38f`: anything under 10 m reads "at the block", and a 0 m distance in the summary fails the check. D01's "about 0 m" came from the model: Blk 5's refuge is 0.0 m, which already read "at the block".
- Live spot-check of the second round (23:13 to 23:16 SGT), as the user, reads only, tracing off, one try each:
  - Requests: A01, B01, B02, B03, C01, C03, D01, G01, G04, L01, R01, W01 and the North-East demo. All 13 were agent-written, with every number grounded and no unseen planning area.
  - R01 got the note "South is not one of the five regions; this plan covers the whole island." B01, B02 and W01 got their not-found notes; B03 got its unused-capacity note.
  - D01 said no area is High tier and named Southern Islands.
  - With the reworded line, G04 called `get_priority_areas` in 3 of 3 runs and gave Toa Payoh's heat level as the area's.
  - Left:
    - The demo summary did not copy the North-East sentence. The template has it, but no note does.
    - C03 misspelt Sembawang as "Sembrwong" (only exact names are checked) and wrote "after allocating 100000 calls", when 59691 were allocated.
    - B03 still calls `find_refuges` on a placeholder first, and used all 4 rounds.
- `0224782`: a regional plan with no High-tier area gets the code note "No rated area in the <region> region is in the High tier." A note the summary already contains verbatim is not repeated.
- Third round (25 Oct, after D's run 2, which scored `0224782` at 16 of 20 on the revised grader; not deployed):
  - `4d575c4`: the App's street hint ("Street, as people write it (e.g. Jalan Kukoh or JLN KUKOH)"), once D's functions were live. Checked read-only at 00:19: Jalan Kukoh gives 5 rows.
  - `e9baed2` (G06): a medicine or a dose fails anywhere; other medical words fail only in a sentence that neither declines nor refers the person to medical help. 995 and 1777 are allowed numbers.
  - `4858f23` (W01): the what-if gain is computed in code (`plan.whatif_gain`), given to the model and written as a code note.
  - `e1291d9` (B03): a prompt line asks for `get_priority_areas` before a lookup that depends on it, and a block number with no digit is refused without a query.
  - Live spot-check (00:24 SGT), reads only, tracing off, one try each. G06, W01, B03, B01, A01 and D01 were all agent-written with no failed check:
    - G06's refusal was kept.
    - W01 gave "8011 more homes", and the note gives 32349 to 40360 and 72 blocks.
    - B03 called `get_priority_areas` first and used 3 rounds.
    - B01 found 5 refuges for Jalan Kukoh.
