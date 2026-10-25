# Deck outline: CoolCheck (10 slides)

> **Draft, 25 Oct 2026.** Each slide has one line of message and the evidence behind it. Every number names the repository file it comes from; paths are relative to `docs/`. `[TBD: …]` marks what is not built yet. The wording follows the write-up (`submission/writeup.md`).

## 1. The problem and who CoolCheck is for

**Message:** Heat stress hits older residents hardest, and CoolCheck tells care teams overnight where to check first.

**Evidence:**
- 806,080 residents aged 65+ and 310,310 aged 75+ in June 2026 (`checks/area_exposure.md`).
- 2025 was Singapore's hottest year on record (DAISI problem statement B1).
- The users are Active Ageing Centre teams and care coordinators. The decision is where to put a limited number of calls and visits. [TBD: a practitioner's confirmation of the need.]

## 2. What a care team gets

**Message:** Overnight, each of the 41 planning areas with residents aged 65+ gets the coming day's heat level, and the 32 with HDB blocks get a Low, Medium or High risk tier and their blocks in the order to check them.

**Evidence:**
- The tier crosses NEA's heat level with the area's vulnerability third in a 3×3 rule (`design/risk_score.md`, §6).
- Blocks are ordered by 1–2 room rental flats, then by distance to the nearest refuge; blocks rank vulnerability, never heat (`design/risk_score.md`).
- A job at 00:45 SGT scores the next day and writes `gold.heat_forecast`; the view `gold.area_heat_risk` gives the tiers, with no probability or score column. Its first scheduled night was 24 Oct (`checks/heat_forecast_first_night.md`); one night, not a track record.
- The live heat-stress page and the briefing dashboard are deployed. The dashboard's four pages give the day's tiers, each area's blocks, the observed heat and the rule (`README.md`). On a day with no High-tier area the headline says so in words, "No rated area is in the High tier.", right after the tier counts (since deploy 4, 25 Oct; `README.md`). [TBD: the dashboard's screenshot.]

## 3. Open data in, governed tables out

**Message:** 15 open datasets from 9 agencies, four of them live NEA feeds, flow through one Lakeflow pipeline into Unity Catalog.

**Evidence:**
- 15 datasets in use from 9 agencies (`attribution.md`); the register lists 23 from 10 agencies (`datasets.md`).
- The collector runs every 15 minutes from 22 Oct, 15:00 SGT (`datasets.md`, row 1), outside Databricks, because serverless could not reach `.gov.sg` sites (`build-log.md`, 19 and 20 Oct).
- Silver held exactly the raw files' totals: 1,036,005 WBGT and 11,893,198 rainfall readings (`checks/silver_check.md`).
- Every dataset in use carries the Singapore Open Data Licence notice; SingStat and EMA are named without links to their sites; no agency logo; CoolCheck is not official advice, and no agency endorses it (`attribution.md`).
- Visual: the architecture diagram from the write-up.

## 4. A forecast of NEA's own category, tested honestly

**Message:** One pooled model forecasts each station's heat category from what is known by 00:15, tested month by month, then once on held-out weeks.

**Evidence:**
- LightGBM on 11 features, logged in MLflow (`checks/final_check.md`, settings); every feature is known by 00:15 SGT on the day (`design/backtest.md`).
- A rolling monthly back-test over 14 months, July 2025 to August 2026: 17,438 area-days, 710 High, against three baselines (`checks/backtest.md`).
- The final check was specified before any of its data was read and scored once behind a lock (`design/backtest.md`, §15).
- The live model is the same configuration refit on target dates to 22 Oct 2026: 10,861 station-days, 538 High. It is a different fitted model from the one the final check scored, and no result is reported for it yet (`checks/live_model.md`).

## 5. Back-test: a better ranking, the same catch at equal alerts

**Message:** The model ranks risk better than "same as today"; its gain is fewer alerts for the same catch, not more catches.

**Evidence:**
- PR-AUC 0.295 against 0.235; the difference is 0.061, with a 95% interval of 0.009 to 0.115. NEA's forecast rule scores 0.058 (`checks/backtest.md`).
- At 700 alerts each, both catch 245 of 710 High area-days (`checks/backtest.md`).
- To catch half, 355 of 710, the model needs 1,180 alerts and "same as today" 1,541 (`checks/backtest_review.md`).

## 6. Final check: the pre-declared test passed

**Message:** On held-out weeks scored once, the test declared in advance passed; no difference is claimed from those weeks alone.

**Evidence** (`checks/final_check.md`):
- Area-day PR-AUC 0.489 against 0.360 for "same as today".
- At the cut-off, 61 of 77 High area-days were caught, with about one alert in three correct.
- At the same alert load, the model caught 35 against 32.
- Without S142, S137 and S135 the edge is small: 0.279 against 0.244, and 11 of 31 each.

## 7. Who is least able to cool down

**Message:** Seven open-data measures of exposure, of being unable to cool down and of cooling access rank 32 areas; the weights are a stated judgement, tested by sensitivity runs.

**Evidence:**
- 32 rated areas; weights: senior exposure 0.35, can't cool down 0.30, cooling-access gap 0.35 (`design/risk_score.md`, §3).
- 55.9% of HDB dwelling units are within 400 m of a refuge and 43.6% within 400 m of a park (`checks/refuge_park_access.md`).
- Sensitivity runs: equal weights keep rho at 0.900, clubs-only refuges at 0.888, and the URA park layer at 0.915 with no tier change (`checks/risk_score.md`).
- Not yet reviewed by a practitioner (`checks/risk_score.md`).

## 8. The agent drafts, a person approves

**Message:** The agent drafts the day's outreach plan from the tiers and the block list; code allocates the calls; a person approves, and nothing is sent.

**Evidence:**
- Tool calling works: Llama 3.3 70B returned a well-formed tool call on the trial (`checks/tool_calling_model_test.md`) and on Free Edition (`checks/free_edition_tool_calling.md`).
- The endpoint's own description says the model "is not intended for use in languages other than English", so the four languages need checking (`checks/free_edition_tool_calling.md`).
- The agent's three tools exist as Unity Catalog SQL functions, and the first fills the call capacity in code (`design/agent_tools.md`).
- The approval App is deployed (`design/agent_app.md`):
  - a number from the model counts only if the request states it;
  - the model's summary is kept only if it passes the checks, and otherwise code writes it from a template;
  - facts every draft must carry are notes written by code.

  The first round of fixes went out with deploy 3 on 24 Oct, the second to fourth with deploy 4 on 25 Oct, from `e07a8db`, the commit run 3 graded; deploy 4 also gave the nightly job one retry per task and restarted the App, which the platform had stopped at 04:57 SGT (`design/agent_app.md`). The fourth, before run 3 (`README.md`, Agent): claims and medical advice judged per clause (a decline, negation or condition excuses only its own clause); 995 and 1777 need no tool result only in a referral such as "call 995" (`design/agent_eval.md`); every call refused before SQL is recorded with its error in the App's tool-call list and, when tracing is on, in the trace; "Ang Mo Kio", not "Ang MO Kio".
- MLflow tracing: the evaluation runner's drafts are traced, all 49 of run 3 (`checks/agent_eval.md`). The App's own tracing was off on deploys 1 to 4, a package conflict in the Apps runtime, and is fixed in deploy 5 by pinning `mlflow-skinny==3.16.1` [TBD deploy 5]; drafts, checks, notes, approvals and the tool-call list do not depend on it.
- Evaluation, the same 20 scenarios three times and 9 held-out scenarios once (`checks/agent_eval.md`):
  - on run 1's grader, 4 of 20 before the fixes, 14 of 20 in run 2 and 13 of 20 in run 3;
  - 16 of 20 on criteria 2 in run 2 and 17 of 20 on criteria 3 in run 3, each committed before its run;
  - run 2 scored the agent code `0224782`; run 3 graded `e07a8db`, the commit deploy 4 deployed, with all four rounds of fixes;
  - run 3's criteria: criteria 2 plus three additions declared before the run (`design/agent_eval.md`, items 4 to 6): discouraging medical help fails; 995 and 1777 in a referral need no source; a claim inside a condition is not a claim. None changes a stored grade of runs 1 and 2.
- In run 2's 32 drafts, no rule was broken, every draft had the right number of calls, and street names were found in 6 of 6 attempts (`checks/agent_eval.md`).
- The fixes were made for the 20 scenarios' failures, so the 20 show them fixed, not how the agent does on new requests (`checks/agent_eval.md`). The held-out 9, written after run 2 and not shown to the window that fixed the agent, are that test:
  - **6 of 9 passed on the first pass**, with tool choice, arguments, groundedness and rules 9 of 9 each, and no rule was broken in any of run 3's 49 drafts;
  - two failures were correct summaries replaced by the template under the number-word rule: H06 on the request's own word "one", while the code-written note still gave the right gain, 3,146 dwelling units; H02 on "Two";
  - one failure, H07, never refused in words a request to ring the residents;
  - the two calls refused before SQL, R01's "South" and H04's "NORTH-WEST", are recorded with their error;
  - limits: the judge failed D01 on its question's word "summary", though the code-written note says it; "40 planning areas", where the tool returned 41, passed on a rounding.
- Four languages: not in the App for Demo Day; planned for the finale on 4 Nov (`build-log.md`). What exists: the translation module with its back-translation drift check, which flagged all six translations of three real drafts in a first test (`checks/language_check.md`), and the grading design for a language set (`design/agent_eval.md`, item 7). Replies to Malay, Tamil and Chinese requests come back in English (`checks/agent_eval.md`).

## 9. Impact: reach, lead time and recall

**Message:** In the back-test, areas flagged High in advance held 39.5% of the over-75 senior-days on High days; we claim no harm figure.

**Evidence:**
- Reach: 1,806,220 of 4,571,620 senior-days of residents aged 75+ on observed High days (39.5%) fell in areas flagged High in advance; the High tier covered 16,524 residents aged 75+ a day on average (`checks/risk_score.md`).
- Lead time: the forecast uses data up to 00:15 SGT (`design/backtest.md`), and on High days the first High reading came at 12:45 at the median, never before 09:45 (`checks/eda.md`). On its first scheduled night, 24 Oct, the forecast for all 41 areas was written at 00:49:49 SGT (`checks/heat_forecast_first_night.md`); one night, not a track record.
- Recall: 355 of 710 High area-days in the back-test (`checks/backtest_review.md`) and 61 of 77 in the final check (`checks/final_check.md`).
- No open heat-illness data exists, so there is no harm figure.

## 10. Limits and what's next

**Message:** We say plainly where CoolCheck falls short, what it costs to run and who would run it next.

**Evidence:**
- It is late into hot spells: it missed 315 of 465 first days and all 22 High area-days of March 2026 (`checks/error_analysis.md`).
- Its edge rests on three hot stations: 0.179 against 0.160 without them in the back-test (`checks/backtest.md`).
- The refuge layer is partial: 93 of about 223 Active Ageing Centres (`checks/refuge_park_access.md`).
- Cost at list price: US$0.142 per hourly refresh of the live page, US$3.40 a day (`checks/latest_readings_cost.md`); US$12.95 for 19 to 21 Oct (`checks/cost_since_19_oct.md`). The nightly job cost US$0.358 on its first scheduled night and US$0.447 for the manual run of 23 Oct; two runs, no daily total (`checks/heat_forecast_first_night.md`). Not counted yet: the App and the SQL warehouse behind the dashboard and the App. [TBD: the App's cost from billing.]
- No personal data. Next: a one-season trial with one AAC cluster, and a practitioner's review of the tiers. [TBD: the Free Edition redeploy.]
