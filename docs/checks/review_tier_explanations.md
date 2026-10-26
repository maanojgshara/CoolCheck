# Independent review: the tier explanations

Reviewed 26 Oct 2026 by window D, as a skeptic: first from about 23:00 to 23:28 SGT (`35c7a79`), on window C's commit `75013d9`:
- `src/coolcheck/explain.py`;
- `scripts/explanations/generate.py` and `patch_live_briefing.py`;
- `scripts/dashboards/build_briefing.py` and `src/dashboards/briefing.lvdash.json`;
- `tests/explanations/` and `tests/dashboards/test_briefing_dashboard.py`.

C's later commits `a30b32d`, `e41cc38` and `b84c674` change only `docs/checks/tier_explanations.md` and `docs/design/tier_explanations.md` (`git diff --name-only 75013d9..b84c674 -- src scripts tests` is empty). The two docs were read only to test their claims.

**Then check 4 again, on `93a6dd9`, from about 23:37 SGT.** C's `93a6dd9` (23:36 SGT) hides "Why this tier" and "Why vulnerable" from both area tables, the user's choice at 23:28. It changes `build_briefing.py`, the dashboard JSON, `patch_live_briefing.py`, their tests and C's two docs, and it fixes the restore step. On the user's instruction:
- check 4 (the live patch) was redone on `93a6dd9`, from a `git archive` of that commit and a fresh read-only get;
- so were the dashboard parts of checks 3 and 6;
- checks 1, 2 and 5 stand. They rest on `explain.py`, `generate.py` and the table, which `93a6dd9` does not change (`git diff --name-only 75013d9 93a6dd9 -- src/coolcheck scripts/explanations/generate.py` is empty). `93a6dd9` also changes no dataset query.

`<user>` stands for the user's e-mail and user name.

## How

- **Read:** every file above, and the helpers the check relies on:
  - in `coolcheck.agent`: `check_summary`, `grounded`, `unseen_areas`, `NUMBER_WORDS` and the App's banned list;
  - in `coolcheck.risk`: `neutral_reason`, `vulnerability` (the reason rule) and `TIER_MAIN`.
- **Workspace: reads only.** All queries ran on warehouse `7aa1dc56400d5b33` through the statement API. The runner refuses anything but SELECT, DESCRIBE or SHOW, any `SELECT *`, and any never-shown name. What was read:
  - `information_schema.columns` for the five gold tables (names only);
  - `gold.area_tier_explanation`, all 10 columns;
  - `gold.area_heat_risk` for 26 Oct: `rated, tier, heat_level, third, reason, station_id, tier_sentence, scored_at`;
  - `gold.area_vulnerability`: the raw values, `third`, `reason`, `neutral_components` and the small-area flags (no `p_*`, `v` or `v_rank`);
  - `gold.observed_heat_daily` for 24 to 26 Oct, and the `gold.refuge_layer` count per area;
  - `DESCRIBE HISTORY` of the new table, with its tags and comment;
  - the briefing dashboard `01f1cfb36fe51bb8906bbd306b88c9bc`: `databricks lakeview get` and `get-published` at 23:15 SGT, and again at about 23:40 SGT for `93a6dd9` (C's new restore step 1, replicated);
  - `databricks jobs list`.

  No `ai_query`, no `generate.py`, no `lakeview create`, `update` or `publish`, no deploy, no job change.
- **Offline:**
  - the facts, recomputed by my own code (it does not import `coolcheck.explain`);
  - 54 adversarial sentences and 3 controls, run against `explain.check`;
  - C's patch, run on the fresh live JSON and then diffed by my own code, at `75013d9` and again at `93a6dd9`;
  - C's restore step 1, replicated before and after its fix (its `lakeview get` is a read);
  - pytest.

  The saved get, the bodies and the scripts are in the session's scratch folder, outside the repo, and are not committed.

## Verdict

**Switch it on after fixes** (unchanged by `93a6dd9`). The 26 Oct sentences are faithful: 32 of 32 are true to the data. The patch at `93a6dd9` does exactly what it says on the live JSON. Nothing reads a never-shown value. The restore point is fixed in `93a6dd9`. One thing must still be done before the apply, and one more is strongly advised.

1. **Must, for tomorrow: write 27 Oct's sentences first, and read them.**
   - At 00:45 SGT the heat forecast job (131450384398104, `0 45 0 * * ?` Asia/Singapore, UNPAUSED) makes 27 Oct the latest date. The table holds only 26 Oct.
   - From then until `generate.py` runs for 27 Oct, every "Why, in a sentence" cell falls back to the tier sentence. Since `93a6dd9` hides "Why this tier" and "Why vulnerable", this no longer repeats a column beside it. Instead, neither table gives any area's vulnerability reason: only the Blocks page still has it, one area at a time. Meanwhile the note under the top 10 says Llama wrote each sentence.
   - So apply only after 27 Oct's rows are written (on the user's word: it calls the model and writes a table) and have been read. If they are not, leave the live dashboard as it is.
2. **Fixed in `93a6dd9`: the restore point** (finding 2). C's step 1 used to save a body that would restore "Peak WBGT (Â°C)" in two places. It now writes the get to a file, reads it as UTF-8 and asserts the body. Replicated on a fresh get: the body equals the live draft.
3. **Strongly advised: tighten the check, or have a person read each date's sentences before they are shown.**
   - The check let 36 of 54 wrong sentences through (finding 3). None of them appeared on 26 Oct.
   - But the sentences that will be on screen tomorrow do not exist yet, and the model's run is not repeatable.
   - With "Why vulnerable" hidden, the sentence is now the tables' only account of each area's vulnerability, so it matters more that it is right.

## The six checks

| # | Check | Result | Evidence (detail below) |
|---|---|---|---|
| 1 | Faithfulness, 32 rows | **Pass**, with wording concerns | My facts equal the stored `facts` for 32 of 32. Each shown sentence has its own tier, heat level and third, each measure verbatim, the right ranks and observed peaks, and nothing else but joining words. The 32 sentences all differ. None claims a cause, says something about people, or gives advice. |
| 2 | The check, adversarially | **Concern** | It caught 18 of 54 wrong sentences; 36 passed, 15 of them of high severity. |
| 3 | Never shown | **Pass** (the dashboard part re-checked at `93a6dd9`) | No forbidden name appears in any SQL that reads or writes. The table's 10 columns hold none, and no stored cell names one. `93a6dd9` changes no query. |
| 4 | The live patch, **reviewed at `93a6dd9`** | **Pass** (it also passed at `75013d9`, where the restore step failed; that is fixed in `93a6dd9`) | Only these change: the 3 datasets' queries; the 2 tables' fields and columns ("Why, in a sentence" in; "Why this tier" and "Why vulnerable" out); the note; and 2 widgets moved down one row. Every editor change is kept. C's new restore step saves the live draft unchanged. |
| 5 | Repeatability | **Concern** | The table holds one run (Delta version 12): 31 "AI, checked" and 1 Template. The "32 of 32" in `75013d9`'s message was a dry run that wrote nothing. A re-run replaces the date's rows. |
| 6 | Tests, **run at `93a6dd9`**, after C's test changes landed | **Pass** | At `93a6dd9`: `tests/explanations`, 37 passed offline, the changed patch tests among them, and the 15 offline structural dashboard tests, 15 passed. The same counts at `75013d9`. The 18 Connect tests were not run by me. |

## Findings

| # | Severity | Finding | Suggested fix |
|---|---|---|---|
| 1 | High (for tomorrow) | There are no rows for 27 Oct (verdict, item 1). Since `93a6dd9`, the fallback no longer repeats a column. But it leaves the tables with no vulnerability reason, under a note that says Llama wrote each sentence. | After the 00:45 run, run `generate.py` for 27 Oct on the user's word. Read the rows: my faithfulness script runs read-only in about 2 minutes. Then apply. Otherwise leave the live dashboard as it is. |
| 2 | Medium; **fixed in `93a6dd9`** | **The restore point was corrupted** (at `75013d9` to `b84c674`). Step 1 of "Applying it" (`docs/design/tier_explanations.md`) pipes the CLI's UTF-8 JSON into `python -I -c "…json.load(sys.stdin)…"`.<br>• `-I` ignores `PYTHONUTF8` and `PYTHONIOENCODING`, so stdin is read as cp1252 (`sys.stdin.encoding` under `-I`: `cp1252`).<br>• Replicated: the saved body differs from the live JSON from character 67,558 on. It has "Peak WBGT (Â°C)" twice: the Observed heat page's chart axis and its table column. Step 2 would publish that.<br>• The patch body is not affected: `patch_live_briefing.py` reads the saved get as UTF-8. | Add `-X utf8` to that `python -I` (or load the saved get with `encoding="utf-8"`). Tried on the same get: the body then equals the live JSON. Before the apply, assert that the restore body's `serialized_dashboard` equals the get's.<br>**Fixed in `93a6dd9`, verified:** step 1 now writes the get to a file, reads it with `-X utf8` and `encoding='utf-8'`, and asserts the body. Replicated on a fresh get (the live draft of 07:19:18.685Z): the body equals the draft, with no `Â`. |
| 3 | Medium | **The check is narrower than the note claims.** The note says "code checks the tier and every number". The check does test that each number is in the area's facts. It does not test that the number sits by the right measure, and its word lists are short. It passed 36 of 54 wrong sentences (section 2). | Add three rules to the current ones:<br>(a) each measure's text appears verbatim;<br>(b) a bracket right after a measure holds that measure's rank;<br>(c) after removing the facts' own phrases (the measures, ranks, note, peak, and the peak's date and category), only frame words remain.<br>A scratch prototype caught 52 of 54, and all 31 stored AI sentences and the prompt's 3 examples still pass it. A rejected sentence costs only the template, which is right by construction. Until the rules are in, a person reads each date's sentences before the apply; the 32 of 26 Oct take about 5 minutes. |
| 4 | Low | The note overstates while finding 3 is open. | Either "code checks the tier, heat level and third, and that every number is one of the area's facts", or keep the note once finding 3's rules are in. |
| 5 | Low | **A sentence can go stale.** The join is on `(target_date, planning_area)` only. If a date is re-scored after `generate.py` ran, a sentence can state a tier or heat level that the Tier column no longer shows. For 26 Oct the scoring (00:49 SGT) came before the sentences (22:56 SGT), and the facts match the current rows. | After Demo Day: join on the tier and heat level too, stored as columns or read with `get_json_object(e.facts, '$.tier')`, and fall back to the tier sentence when they differ. |
| 6 | Low | A row cannot be tied to the code that checked it. `generate.py` prints the commit but does not store it. | After Demo Day: add a `code_commit` column. |
| 7 | Low | **Two wordings are true of the data but may mislead.**<br>• Tanglin's "no refuges in the area for 4,070 residents aged 65+" rests on a partial refuge list (C's flag 1, agreed).<br>• "No component above the middle of the rated areas" (Changi, Downtown Core) does not say that 5 and 4 of their 7 measures are held at the middle because they have too few residents or flats. | After Demo Day. Neither area is likely to be in the top 10 (both are Low tier, lower third). |
| 8 | Note | **The model adds little.** In all 31 AI sentences, removing the facts' own phrases leaves only "and the … third for vulnerability, with", "and", and "; its station observed a peak WBGT of … on …". | A team decision: keep the model (with finding 3's frame rule the risk is small), or show the template, which reads almost the same. |

## Sentences I would not want on screen tomorrow

- **Any 27 Oct sentence nobody has read.** None exists yet. The model is not repeatable, and the check has the gaps in section 2.
- **The tier sentence in the new column, under a note that says Llama wrote it, and since `93a6dd9` with no vulnerability reason anywhere in the tables.** The page shows this from 00:45 SGT if the patch is applied before 27 Oct's rows exist (finding 1).
- **Of the 26 Oct sentences,** which are on screen tomorrow only if the 00:45 run fails, none is false and I would block none. I would reword Tanglin's "no refuges" (finding 7) before it can be shown.

## 1. Faithfulness (pass)

My code rebuilt each area's facts from the gold tables, without importing `coolcheck.explain`:
- **Usable set per measure:** from `area_vulnerability.neutral_components` (the pipeline's own record). Cross-checked against the small-area rule in `reference/score_weights.csv`: the two agree for all 7 measures × 32 areas.
- **Ranks:** within those sets, in each measure's own direction.
- **Refuge count:** from `refuge_layer`.
- **Station:** from `area_heat_risk.station_id`.
- **Observed peak:** the 25 Oct peak, rounded half-up.

It then compared the stored facts and the shown sentences.

**Facts:** equal to the stored `facts` for **32 of 32**, as exact JSON equality: the tier, heat level and third, each measure's text and rank, and the observed peak with its date and category. Also:
- every tier is the 3×3 rule's for its heat level and third;
- `third` and `reason` agree between `area_heat_risk` and `area_vulnerability`;
- the refuge counts derived from the rate equal `refuge_layer`'s: Bukit Panjang 5, Bukit Timah 2, Pasir Ris 5, Tanglin 0;
- all 32 have an observed peak, from 20 stations, and each forecast station is the one the Observed heat page shows for the area on 25 Oct;
- no share falls on a rounding tie.

**Sentences:** each of the 32 shown sentences:
- starts with its tier, and says "forecast <heat> heat" and "<third> third";
- contains each measure's text verbatim;
- gives the right rank wherever it gives one: Ang Mo Kio 3rd, Geylang 7th, Woodlands 6th, and Clementi's template 9th and 16th;
- for Changi (32.1 °C) and Downtown Core (29.9 °C), gives the peak as "its station observed …".

Once those are removed, no number is left. The 32 sentences are all different. None says anything about residents beyond counts and shares, gives advice, or ties the peak to the forecast.

**Concerns, all about wording:**
- C's three flags, which I agree with:
  - Tanglin's "no refuges";
  - values given without ranks: Bishan's 10% share is only 13th of 31;
  - a Low tier in the upper third reads oddly, in 8 areas: Ang Mo Kio, Bedok, Bukit Merah, Hougang, Jurong East, Jurong West, Tampines and Yishun.
- The held measures of finding 7.

## 2. The check, adversarially (concern)

Run offline against `explain.check`, on the stored 26 Oct facts of Toa Payoh, Tengah and Ang Mo Kio. For the confidence words, Toa Payoh's facts were also given a made-up High tier and High heat. The 3 controls pass: the stored sentence, the same with its true rank, and the same with the peak in the prompt's form.

**Caught (18):**
- a wrong rank in brackets, including "(the most of 32 rated areas)";
- "one in ten" and "a tenth";
- "live alone";
- "at risk of heat stroke" (the App's medical rule);
- "after a 30.5 °C peak" and "because its station peaked at 30.5 °C";
- "as in Bedok";
- "chance" and "more likely than not";
- "High heat is possible" in a Moderate area;
- "Medium heat";
- "volunteers should check on them";
- a wrong °C value and a wrong date;
- two sentences, and a 38-word sentence.

**Passed, though wrong (36):**

| Severity | Group | What passed (on Toa Payoh's facts unless named) |
|---|---|---|
| High | Values swapped | "14,290 1-2 room rental flats and 3,835 residents aged 75+"; Tengah's "55% … of a refuge and 64% … of a park" (true: 64% and 55%) |
| High | Labels dropped or changed | "with 3,835 and 14,290"; "3,835 rental flats and 14,290 seniors" |
| High | Ranks in other words (true: 5th) | "ranked 2nd of 32 rated areas"; "(2nd largest number of 32 rated areas)"; "the most 1-2 room rental flats of any rated area" |
| High | Residents | "many of whom live on their own"; "frail and isolated"; "who cannot afford to cool their homes"; "needy households" |
| High | Superlatives | "the most vulnerable area"; "in the hottest part of Singapore" |
| High | Reassurance | "so no action is needed" and "so it is safe" (Ang Mo Kio: Low tier, upper third) |
| Medium | The peak as the cause, in other words | "as its station reached 30.5 °C"; "in line with the 30.5 °C peak"; "its 30.5 °C peak … points to Moderate heat"; "on the back of a 30.5 °C peak" |
| Medium | Confidence in words | "almost certainly Moderate heat"; "long odds of anything worse"; "though it could turn High"; "a near-certain High-heat day" (made-up High area) |
| Medium | Tier and heat words mixed | "a High-risk area" (Medium tier); "a Moderate-tier area" |
| Medium | Advice | "call the rental blocks"; "consider visiting the rental blocks"; "keep an eye on its seniors" |
| Medium | Numbers in words outside the App's list | "fifteen"; "sixty" (the list has one to twelve, twenty to fifty by tens, dozen, hundred and thousand) |
| Medium | Observed values | "a peak WBGT of 32": no unit; 32 is in the facts as "of 32 rated areas"; the peak was 30.5 °C. "30.5 °C (High)": the category was Low |
| Low | Other | "on Saturday" (25 Oct 2026 was a Sunday); "Tiong Bahru" (a subzone) and "Jurong" (not a planning area); "High vulnerability" for the upper third |

**What the check does well:**
- the tier, heat level and third;
- numbers against the facts, with the App's normalisation;
- dates, °C values and bracketed ranks matched to their own fact;
- the length;
- the words on its lists.

**What it cannot do:** tie a value to its measure, or notice words outside its lists.

**The prototype:** its frame words were `and the upper middle lower third for vulnerability with its station observed a peak wbgt of on forecast heat low moderate high medium in at`. It missed only "High vulnerability" and the "(High)" after the peak. Catching the second needs a rule that the bracket after the peak equals the NEA category.

**How likely this is:** none of these appeared on 26 Oct. All 31 AI sentences are the facts' phrases joined by the frame words above. But C's check doc says the model did not repeat itself between its last dry run and the stored run. And a day with High heat, or with other measures, gives the model new facts to phrase.

## 3. Never shown (pass)

**What the SQL reads and writes.** `explain.py`'s SQL reads:
- from `area_heat_risk`: `target_date, planning_area, tier, heat_level, third, reason, station_id`, with `rated` in the filter;
- from `area_vulnerability`: the 7 raw values, `residents`, `aged_65_plus` and `hdb_dwelling_units_confirmed`;
- from `observed_heat_daily`: `station_id, max_wbgt, heat_category`.

It writes 8 text columns, the date and `generated_at`. `generate.py`'s own statements read only the new table's `written_by` and `planning_area`, `DESCRIBE TABLE`, and `table_tags`. The forbidden names occur only in `NEVER_READ`, in a docstring and in the text of a column comment (`grep -w`).

**What the table holds.** Its 10 columns (`information_schema.columns`) are `target_date, planning_area, facts, template_sentence, ai_sentence, explanation, written_by, checks_failed, model, generated_at`. No stored cell matches P(High), probability, chance, score, percentile, `v_rank`, `tier_rank`, `model_version` or `run_id`. The facts' keys are only `area, tier, forecast_heat_level, vulnerability_third, vulnerable_because, vulnerability_note, observed_heat`.

**What the dashboard takes from it.** The three datasets take only `e.explanation`, `e.target_date` and `e.planning_area` from the table, as the test checks. `r.tier_rank` stays in the existing `row_number()` order: C's diff neither adds nor removes it, and it is never shown. At `93a6dd9` this all still holds. No query changed; only the two table widgets dropped `tier_sentence` and `reason`, which are not never-shown values. The test that the datasets read only the sentence and join keys from the table passes there.

## 4. The live patch (pass, reviewed at `93a6dd9`)

**What was reviewed.** `93a6dd9`, from a `git archive` of that commit; the patch reads the committed JSON beside it. The results below are `93a6dd9`'s. The first pass, at `75013d9` with the old 8-column tables, passed on the same points, except the restore step (finding 2).

**The get, about 23:40 SGT,** taken by replicating C's new restore step 1 into my scratch folder:
- It is unchanged since my first get at 23:15 SGT.
- The draft's `update_time` is 07:19:18.685Z and the published revision 07:19:20.248Z, so the published page is that draft.
- Credentials are embedded, so viewers need no new grant. The warehouse is `7aa1dc56400d5b33`.
- The pages are About, Briefing, Blocks and Observed heat. The user has confirmed that the 15:19 SGT edits are theirs and stay.

**The restore point (finding 2, fixed).** Step 1 printed "restore body = live draft of 2026-10-26T07:19:18.685Z". By my own comparison, the body's `serialized_dashboard` equals the get's, the warehouse is kept, and there is no `Â`.

**The patch at `93a6dd9`, run offline on that get.** It printed "wrote …: the live draft of 2026-10-26T07:19:18.685Z with the explanation column; nothing else changed". Its own check passed, and it now compares the tables' fields as well as their columns. My diff, independent of that check:
- **What changes:** the Briefing page's layout, and the `queryLines` of `ds_area_map`, `ds_top_areas` and `ds_more_areas`. Nothing else: the About, Blocks and Observed heat pages, `uiSettings`, the page order, the datasets' `catalog`, `schema` and display names, and the Briefing page's other keys are identical.
- **The queries:** the three live queries were exactly the committed ones from before the change (`e98fcc9`), so no editor edit is lost. All 11 patched queries equal `93a6dd9`'s, which are also `75013d9`'s: `93a6dd9` changes no query.
- **The tables:** `top-areas` and `more-areas` go from 7 fields and columns to 6.
  - They are now `briefing_order, area, tier, explanation, rental_1_2_room, actions`, shown as #, Planning area, Tier, Why, in a sentence, 1-2 room rental flats, and Actions (a proposal).
  - Out: `tier_sentence` ("Why this tier") and `reason` ("Why vulnerable").
  - Fields and columns both equal `93a6dd9`'s, and the 24 px titles are kept.
  - The datasets still select both hidden fields: the map's tooltip and the sentence's fallback use the tier sentence.
- **The layout:** the note goes in at (x 0, y 30, w 12, h 1). `more-areas` moves from y 30 to 31, and `trend-chart` from 34 to 35. No two widgets overlap, and none runs past column 12.
- **The body:** only `serialized_dashboard` and `warehouse_id`, with the warehouse kept and the non-ASCII characters unchanged.

**Applying:**
- The body has no `etag`, so the update overwrites whatever is live. Take step 1 right before step 5, and make no editor change in between.
- C's publish line passes `--embed-credentials`, which keeps today's setting. Keep it.
- The CLI (v1.21.0) has `--dataset-catalog`, `--dataset-schema` and `--embed-credentials` as the steps use them.
- **Rendering.** C's check doc records the user's 1920×1080 screenshot of the copy with 8 columns (`b84c674`): each sentence on one line, in full, judged readable by the user, and the table scrolling sideways.
  - For the six columns, the doc (`93a6dd9`) gives an estimate, not a render: the table still scrolls, with "Actions" only partly in view.
  - The copy was updated with the six columns at 23:33 SGT and can be looked at.
  - I have seen neither the screenshot nor the copy.

## 5. Repeatability (concern)

**What is stored.** `DESCRIBE HISTORY` shows the create and comment steps at 14:56:11 to 14:56:19Z, then one data write: version 12, at 14:56:26Z, `REPLACE WHERE target_date = DATE '2026-10-26'`. So the table holds exactly one run, generated at 22:56:20 SGT:
- 31 "AI, checked";
- 1 Template: Clementi, "facts: does not give 10,410".

Re-checking the 32 stored model sentences with the committed check gives the same verdicts. Each AI row's `explanation` is its `ai_sentence`, trimmed.

**What the stored run does not show.** `75013d9`'s commit message says "a dry run … gave 32 of 32 sentences that pass". That was a dry run, and it wrote nothing. C's check doc says 2 sentences changed between dry run 5 and the stored run: Clementi lost a measure, and Toa Payoh its rank. That comes from C's run output, which I did not see. Any number in the write-up should be the table's: 31 and 1, version 12.

**What a re-run changes:**
- `ai_sentence`, and with it possibly `written_by`, `explanation` and `checks_failed` in any row, plus `generated_at`.
- Not the facts or the template: they are code, and on the same gold rows they come out the same (my independent rebuild matched them). The check is deterministic too.
- A re-run replaces the date's rows, so the earlier run survives only in Delta history (time travel, until a vacuum).

**Is the stored table the evidence?** Yes, for what is shown. The dashboard reads it directly, and each row carries the facts, both sentences, who wrote the one shown, the checks it failed, the model and the time. It lacks the commit (finding 6). It is not evidence about tomorrow: 27 Oct's sentences will come from a new call that does not repeat itself.

C's line "The check keeps what is shown correct either way" holds for 26 Oct, which I checked by hand. As a general claim it is too strong (section 2).

## 6. Tests (pass, run at `93a6dd9`)

**Results.** Check 6 was run after C's test changes landed, from the `git archive` of `93a6dd9`, offline in `.venv`:
- `pytest tests/explanations`: **37 passed**.
- The 15 structural tests of `tests/dashboards/test_briefing_dashboard.py`: **15 passed**.
- By name, these passed:
  - `test_both_area_tables_show_six_columns_with_why_in_a_sentence_after_the_tier`;
  - `test_the_explanation_table_gives_the_datasets_its_sentence_only`;
  - `test_the_note_on_who_writes_the_sentences_is_under_the_top_ten`;
  - `test_file_is_what_the_builder_makes`;
  - both patch tests in `tests/explanations/test_patch_live_briefing.py`.
- At `75013d9` the counts were the same: 37 passed in 0.07 s, and 15 passed.
- The 18 SQL tests need Databricks Connect and were not run by me. C reports 33 of 33 through Connect on temp views, at both commits.

**What the dashboard tests assert about the new column (at `93a6dd9`):**
- Both area tables show exactly six columns: #, Planning area, Tier, Why, in a sentence, 1-2 room rental flats, and Actions (a proposal). "Why this tier" and "Why vulnerable" are gone.
- The datasets still select `tier_sentence` and `reason` (`SELECT briefing_order, area, tier, explanation, tier_sentence, reason, rental_1_2_room, actions FROM ordered`).
- At `75013d9` the test was instead that every column was kept.
- The patch tests rebuild the dashboard as it was before the change and check that the patch gives the committed one back. On a dashboard edited in the editor, they check the six display names and the six fields.
- The SQL has `coalesce(e.explanation, r.tier_sentence)` and the `LEFT JOIN … ON e.target_date = r.target_date AND e.planning_area = r.planning_area`.
- Only `ds_area_map`, `ds_top_areas` and `ds_more_areas` read the table, and they take only its sentence and join keys. None reads `facts`, `ai_sentence`, `template_sentence`, `checks_failed` or `written_by`, and none calls `ai_query`. The table's columns hold no never-shown name.
- The note's exact text sits right under the top 10, full width and one row high.
- The JSON is what the builder makes.
- Through Connect: an area with a row for the latest date shows that row's sentence, an older date's row is ignored, and every other area shows its tier sentence. So no cell is blank, and there is one row per area.

**What they do not assert:**
- They run on the committed JSON, not the live one (section 4 covers the live).
- No test checks that a sentence's tier equals the row's tier (finding 5).
- No test covers a duplicate `(target_date, planning_area)` row. The `REPLACE WHERE` write makes one unlikely, but it would show an area twice and shift the order.
- Nothing tests the rendering. Only the user's screenshot covers it, by eye (section 4).
