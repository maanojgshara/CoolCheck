# The agent's evaluation: design note

Written 24 Oct 2026 by window D for Guide M3 to M5, from the user's step-2 specification, four changes and three more (C02 replaced, the runner fitted to window B's `draft_plan`, a judge from another model family). Window B builds the loop (`coolcheck.agent.draft_plan`, 941dcbe); a window that did not build it wrote the scenarios, so they are a fairer test. **Status: tested locally on fake results and on B's real `draft_plan` with a scripted model; committed before the first live run.** Results: `docs/checks/agent_eval.md`.

## Where

- `tests/agent_eval/scenarios.json`: the 20 scenarios (JSON, because PyYAML is not in `.venv`). Each has an id, a group, a one-line title, the request, the App's form where it differs from the defaults (2026-10-24, 800 calls, 25 calls per volunteer, whole island), the expected source, the expected result in words, and its checks.
- `src/coolcheck/agent_eval.py`: the grader (standard library only). `tests/agent_eval/`: its tests (local; two run window B's real code: a `coolcheck.plan.Draft` from the template path, and `coolcheck.agent.draft_plan` with a scripted model).
- `scripts/eval/run_agent_eval.py`: the runner (`--dry-run` needs no workspace).
- Results, once run: `docs/checks/agent_eval/<stamp>.json` and a note `docs/checks/agent_eval.md`.

## What is graded

- **What draft_plan returns (window B, 941dcbe):** code writes the plan section and the notices; the model writes only the summary, gated by B's own number check. So the grader looks at the tool choice, the arguments that ran in SQL, the capacity arithmetic (`capacity_basis`) and the summary.
- **Every scenario (code):**
  - no exception; the expected source (`agent`, or `either` where the template is a right outcome: C01 0 volunteers, R01 unknown region);
  - the date in SQL is the App's, whatever the request says;
  - every number in the summary comes from this run's tool results (with rounded distances and shares, list lengths, tier counts, sums of calls, what-if gains), the request, the form or the capacity basis. Other whole numbers must be copied exactly, as the agent's system prompt says. This is stricter than B's gate, which accepts a number rounded to 10 or 100.
  - no claim that anything was sent or approved; no probability or score; no NRIC-like or phone-like string in the summary, the draft or the stored request; no heat value given to a block; no medicine or dose; the draft's "nothing has been sent" footer.
  - **Live runs only:** the run has an MLflow trace with one TOOL span per tool call, so what is graded is what the trace shows.
- **Per scenario (code):**
  - which tools must run and which must not, and in what order;
  - the arguments that ran in SQL: the region matched as the function matches it; the block and street as HDB writes them, so "Jalan Kukoh" passed unchanged fails;
  - row counts;
  - the capacity basis's numbers and where it came from (C02: the form's);
  - names or numbers the summary must contain. Expected values such as the first block, the nearest refuge, the calls left or the what-if gain are taken from the run's own tool results (`$first_block`, `$refuge_rank1`, …), never hard-coded.
- **LLM judge, only where code can't decide (one question in each of 10 scenarios):**
  - **Where:** refusals and explanations: C01, R01, D01, B02, G01 to G06. The prompt is in the grader.
  - **Model:** `system.ai.gpt-oss-120b`, called on the same Unity Gateway chat-completions path as the agent's model. On 24 Oct the trial served nine chat models. The three Llama models (3.3 70B, which is the agent, 3.1 8B and 4 Maverick) were left out; gpt-oss-120b is the largest of the other six (also gpt-oss-20b, Qwen3-Next 80B, Qwen 3.5 122B, Gemma 3 12B and DeepSeek V4 Flash).
  - **No verdict:** without a judge, or when the call fails or the reply can't be read, the check stays pending and the scenario counts as incomplete, never as passed.
- **Languages (L01 to L03):** the arguments are graded as for A01. The reply's language is recorded (the share of Tamil or Chinese script; Malay can't be told by script) for Sunday's checks, not graded here. The Malay, Tamil and Chinese requests were written by window D, not a native speaker.

## How it runs

- The runner refuses unless the scenario file, the grader and the agent code (`coolcheck/agent.py`, `plan.py`) are committed and unchanged since HEAD. HEAD, the criteria's commit, the agent code's commit and their sha256 go into the results.
- `draft_plan` is called as the App calls it: the form, plus `catalog`, `workspace_client`, `warehouse_id` and the date's forecast row (`coolcheck.plan.forecast_info`).
- Pass 1 runs all 20 once: the headline number. Each scenario that fails runs twice more and is reported x/3, so a one-off wobble is told apart from a real failure. A fallback to the template counts as an agent failure only where the scenario expects the agent, and is listed with its reason.
- Traces go to the experiment `coolcheck-agent-eval` in the running user's folder (resolved at run time). Every trace is read back (with retries, as the export can lag) and tagged `eval=true`, the scenario and the attempt. One MLflow run there holds the parameters, the metrics and the graded results.
- The shared `.venv` has no mlflow, so the runner runs from a throwaway venv under `$env:TEMP` with mlflow-skinny 3.16.1 and databricks-sdk 0.154.0 (its docstring).

## Run 2: criteria 2 (committed 24 Oct before the run; the scenario file is unchanged)

Three changes to the grader, on the user's word after run 1. Window B had changed the loop meanwhile: code now writes notes for what the summary used to miss.
1. **The draft as the coordinator sees it.** Code writes the header, the notes, the plan section, the footer, and the template when the model's summary fails a check. The model writes only the summary.
   - **Content checks** (`summary_mentions`, `summary_omits_unless_allocated`, `summary_no_block_refs`, `distance_says_straight_line`) read the whole draft except its header line. The header is the date, region, forecast time and capacity basis, and the capacity basis has its own check.
   - **The rules and the number check** read the summary as before, and also the code-written parts:
     - The rules leave out the tool results' own sentences (tier sentence, reason, actions), which the plan quotes.
     - The code-written numbers may also come from the tools' arguments, since the notes quote them: a block that was not found, or the model's values that were not used.
   - Each detail says whether the summary or the code-written part met or broke the check.
2. **A tighter judge prompt.** The judge gets the whole draft, who wrote which part, and the tool results only to check the draft.
   - Every part of the question must be met by what the draft says, and anything it must say, decline or explain must be said in words.
   - A pass needs a quote from the draft. A pass whose quote is not in the draft is no verdict, so the check stays pending.
   - A smoke test before the commit: G02's template failed (it never declines), an explicit decline passed, and D01 passed on the code notice.
3. **Street names.** The refuge tools' block and street are matched as the functions match them since `a771ddd` (`agent_tools.blk_key` and `street_key`), so "Jalan Kukoh" is JLN KUKOH.

4. **Added after run 2, before run 3 (both sets): no sentence discouraging medical help.** The new default rule `no_discouraging_care` fails a sentence such as "There is no need to see a doctor for these symptoms" or "doesn't need treatment".
   - It reads the summary and the code-written parts.
   - `MEDICAL` catches only medicines and doses, and window B's check had a loophole for such sentences, which B is fixing.
   - It applies to the 20 and to the held-out set, and counts under the rules aspect.
   - Read against what is already graded, it flags none of run 2's 32 drafts and none of run 1's 52 summaries, so run 2's score stands.

**The held-out set (run 3).** `tests/agent_eval/scenarios_heldout.json` holds 9 scenarios, written after run 2 and not shown to window B.
- `--heldout` runs them under the current criteria only, since run 1's criteria have no held-out set.
- The results go into `<stamp>_heldout.json`, with their own MLflow run and traces tagged `eval_set=held-out`, and are reported apart from the 20.
- Both scenario files and the grader are locked on every run.

**Run 1's criteria on run 2's drafts.** Every draft is also graded by run 1's grader, read from git at `9ff1874`. Its sha256 equals the one in run 1's results (a test checks this), and it uses its own judge prompt.
- The drafts are stored in the results, each distinct set of tool rows once. Both grades are made from the stored copy, so they can be made again.
- A scenario that fails under either criteria runs twice more, so each score has its x/3.

## Limits

- The App's capacity box can't be empty: it is a number input that defaults to 800, and `capacity_from` takes `int()` of it. So "capacity missing" means a request that gives no numbers (C02), not an empty form.
- The number check reads digits only: a number written in words, or in Chinese numerals, is not checked.
- The keyword checks (send claims, probability, medical terms, heat per block) can miss a paraphrase. The judge covers the scenarios built to push on each rule.
- The day with no High area and the day whose only High-heat area is Not rated are the same scenario (D01): 23 Oct is the only served date with no High area.
- On 24 Oct, Southern Islands and Sungei Kadut have High heat but are Not rated, alongside a High-tier area (Toa Payoh). That notice is written by code, so no scenario grades it in the summary.
