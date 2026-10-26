# Tier explanations: one sentence per rated area, written by a model and checked by code

Window C, 26 Oct 2026. Code: `src/coolcheck/explain.py`, `scripts/explanations/generate.py`, `scripts/explanations/patch_live_briefing.py`; the dashboard: `scripts/dashboards/build_briefing.py`. The first run, every sentence and the cost: `docs/checks/tier_explanations.md`. `<user>` stands for the user's e-mail and user name.

## What it is

The briefing dashboard's two area tables get a column, "Why, in a sentence", right after "Tier". It holds one plain-English sentence per rated area saying why the area has its tier. It fixes a weakness of the "Why vulnerable" column. That column is a fixed phrase for the area's two largest components, so areas with the same two components show the same text: 24 of the 32 rated areas on 26 Oct. The new sentence differs wherever the areas' facts differ.

How a sentence is made, in order:

1. **Facts, by code.** `explain.facts` builds them from the latest `gold.area_heat_risk`, `gold.area_vulnerability` and `gold.observed_heat_daily`.
2. **Words, by the model.** Llama 3.3 70B writes the sentence through Databricks AI Functions: `ai_query('system.ai.meta-llama-3-3-70b-instruct', …)` on the SQL warehouse, at temperature 0, with at most 120 output tokens. That is the App's model, under the name `ai_query` accepts.
3. **The check, by code.** `explain.check` tests the sentence. If it fails, the template takes its place (`explain.template`, code, the same facts).
4. **The table.** `scripts/explanations/generate.py` stores the result in `gold.area_tier_explanation`, replacing the date's rows.
5. **The dashboard.** It reads the table through a `LEFT JOIN` on `(target_date, planning_area)` with `coalesce(explanation, tier_sentence)`. A missing row shows the existing tier sentence, never a blank. No dataset calls `ai_query`.

The note under the top-10 table says who writes the sentences and how they are checked.

**Six columns, not eight (the user, 26 Oct 23:28).** Both area tables now show #, Planning area, Tier, Why, in a sentence, 1-2 room rental flats, and Actions (a proposal). "Why this tier" and "Why vulnerable" are hidden, for two reasons:
- At the presenting laptop's width the top-10 table scrolled sideways: "Why this tier" was cut off, and "Why vulnerable", "1-2 room rental flats" and "Actions (a proposal)" were off-screen.
- Each sentence's first half repeated "Why this tier" word for word beside it. The sentence carries both: it begins with the tier sentence and names the same measures, with their values.

Only the two widgets' columns changed. The datasets keep both fields: the map's tooltip still uses the tier sentence, and the sentence falls back to it when a row is missing.

## Why these facts

The tier is made of two things, by the 3×3 rule: the forecast heat level (NEA's Low, Moderate or High) and the area's vulnerability third. Both go in, as words. The rest of the facts are the reason's measures, a few names, and the day before's observed heat.

**The reason's measures.** The vulnerability side is the components that `reason` already names: the two with the largest weight × percentile among those with a usable value at or above the middle. Their values come raw from `gold.area_vulnerability`, written as a coordinator reads them:
- counts as counts: "3,835 1-2 room rental flats", "14,290 residents aged 75+";
- shares as whole percentages, rounded as the dashboard's `format_number` rounds them;
- refuges per 1,000 residents aged 65+ as the area's own count, "5 refuges in the area for 25,690 residents aged 65+". That is the rate times the residents, a whole number for every area on 26 Oct; otherwise the rate itself is given;
- the hot-month electricity ratio as a rise in per cent.

**Ranks.** Each measure's rank is counted among the rated areas with a usable value for it. That is the percentile's own set: the small-area rule 9(g) and missing values are left out. It also uses the percentile's own direction, so rank 1 is the most vulnerable. The ranks are computed from the same raw values as the percentile. Ties share the best rank ("joint 3rd"). When some areas are left out, the rank reads "of 29 rated areas measured".

**Names and words.** The area's name is written as the dashboard shows it. Shares are written so "an 11%" reads right.

**The day before's observed heat.** The facts also give the peak WBGT observed on the day before the target date at the area's station (`station_id` in `gold.area_heat_risk`), with its NEA category, from `gold.observed_heat_daily`. It is left out when the station has no usable row for that day. This is the user's decision of 26 Oct: it is given as an observation, not as the model's input.
- The model's strongest input in the back-test, `wbgt_peak_d1`, is built by the same rule: the station's highest counted reading on the day before. In back-test run `c509ab9a` (`feature_importance.csv`), it has 24.7% of the mean gain across the 14 monthly models of configuration (7, 150), the one the live model refits. The next is `panel_peak_mean_d1`, at 16.0%. The live refit's own importance is not logged.
- The nightly job keeps its features in memory only. The stored observation may therefore include readings that arrived after the job ran, so it is not shown to be the value the model used.
- That is why the sentence presents it as what the station observed, and why the check fails a sentence that ties it to the forecast or the tier.

**Why values at all.** Values make the sentences differ wherever the facts differ: the 32 of 26 Oct are all different. For that reason the check requires each measure's value, or the observed peak for an area with no measure.

## Why no probability

P(High) is not calibrated. See `docs/design/backtest.md`, item 2, "The model under-predicts hot months", and `docs/submission/writeup.md`, "The probability is not shown". It is never shown.

Nothing here reads P(High), p_moderate, p_low, V, its rank, tier_rank, model_version or run_id (`explain.NEVER_READ`):
- `tests/explanations` scans every statement for them;
- the dashboard tests check that the new table holds none of them, and that the datasets take only its sentence and the join keys from it.

So the model cannot repeat any of them. The prompt also forbids probability, chance, likelihood and a score, and the check fails a sentence that has one.

## Why the check

A model can change a number, mix the tier and heat words, drop a fact, add advice or say things about people. `explain.check` tests every sentence in code before it is shown:

- **The words.** The tier word comes first. The forecast heat level and the third are said in words, and every tier, heat level and third named is the area's. Medium is only a tier and Moderate only a heat level; a heat word may also be the observed category.
- **The values.** Each measure's value is given, or, for an area with no measure, the observed peak.
- **The numbers.** Every number is in the facts, by the App's own normalisation (`coolcheck.agent.check_summary`: thousands separators, decimal commas, the tolerance of round numbers, a percentage against its share).
  - A number in words fails, and so does an ordinal word.
  - A date, a temperature and a rank must each be its own fact. An example's "1 Jan", a copied "31.0 °C" or two swapped ranks fail even when the number appears elsewhere in the facts.
- **The length.** One sentence of at most 35 words.
- **Banned words.** Probability, chance, likelihood, alone, poor, low-income, air-con, die, death and guarantee, with their inflections, fail unless a fact holds the word. Three more groups were added beyond the brief's list:
  - today, tomorrow and yesterday, which go wrong when the page is read on another day;
  - the model, because the sentence does not explain the model;
  - advice words.
- **The App's other checks.** P(High) or a score, a claim that something was sent, medical advice, a planning area that is not in the facts.
- **The observation.** The observed peak may not be tied to the forecast or the tier.

**When a sentence fails.** A failed sentence, or a failed call, is replaced by the template. The template is the dashboard's tier sentence followed by the measures, their ranks, then the observed peak. It takes the first of four forms that fits in 35 words: with ranks and the peak, ranks only, values and the peak, values only. Both sentences are kept, with `written_by` ("AI, checked" or "Template") and `checks_failed`.

**What the check cannot see.** It cannot see a fact that is true of the data but rests on a partial source: Tanglin's "no refuges" comes from a list with 93 of about 223 Active Ageing Centres. Nor can it see a value given without the rank that would put it in context. A person read all 32 of 26 Oct's sentences (`docs/checks/tier_explanations.md`, "Flagged").

## Why materialised, not at view time

- **Cost and time.** There is one `ai_query` per area per date, about US$0.02 a night (an estimate, `docs/checks/tier_explanations.md`), rather than calls on every view or refresh of the dashboard.
- **One sentence for everyone, and a record.** Every viewer sees the same sentence. The table records the facts given, both sentences, who wrote the one shown, the checks it failed, the model and the time. Temperature 0 does not make the model repeat itself here: 2 of 32 sentences differed between two runs on the same facts.
- **A plain Delta table.** The dashboard reads it like any other table. A missing row shows the tier sentence, never a blank: another date, or a night the script did not run.

## What it is not

It explains the tier from its inputs: the forecast heat level and the vulnerability measures. It does not explain the model's own reasoning.

Why the model forecast Moderate rather than High heat for an area is the forecast's own explanation. That would be per-station feature contributions for the nightly rows, such as LightGBM's SHAP values (`predict(..., pred_contrib=True)`). This is a next step; the nightly job would have to keep them.

## Running it

- **Before Demo Day, by hand, for each new date.** `.venv\Scripts\python scripts/explanations/generate.py` takes the latest date, or `--target-date` a given one; `--dry-run` calls the model and writes nothing. The script replaces the date's rows in one Delta write (`INSERT INTO … REPLACE WHERE target_date = …`).
- **In the nightly job: a documented next step, deploy 6, not done.** It would be a task `explain` after `score` in `resources/heat_forecast.job.yml`, running the same script for the night's date.
  - Its failure must not fail the night, because the page falls back to the tier sentence.
  - The job's identity needs the right to call the model through `ai_query` and to use the warehouse.

## Applying it to the dashboard (prepared, not run)

Nothing is applied to the live dashboard. The apply waits for window D's review and the user's go.

Found on 26 Oct, from 22:40 to 23:00 SGT, by reads only (`lakeview get`, `lakeview get-published`):

- **Catalog and schema.** The deployed briefing `01f1cfb36fe51bb8906bbd306b88c9bc` holds the bundle's dataset catalog and schema on each dataset: `"catalog": "coolcheck", "schema": "gold"` on all 11 datasets of its serialized JSON. An update passes `--dataset-catalog coolcheck --dataset-schema gold`.
- **The live dashboard carries the user's editor changes.** The user changed it in the dashboard editor on 26 Oct, 15:19 SGT: the draft was saved at 07:19:18 UTC and published at 07:19:20 UTC, with embedded credentials and warehouse `7aa1dc56400d5b33`. The changes are layout and styling only, and the user keeps them:
  - the pages reordered, About first;
  - the titles at 24 px;
  - the guide and the Blocks, Observed heat and About text set as bullets;
  - a new Briefing layout: the map full width, the "other areas" table 4 rows tall;
  - the filters' query names regenerated by the editor.

  The datasets are unchanged. These changes are not yet in `scripts/dashboards/build_briefing.py` (nor in `src/dashboards/briefing.lvdash.json`); they go into it after Demo Day.
- **The change goes on the live JSON.** The committed JSON, applied as it stands, would undo the user's changes, so it is not applied. `scripts/explanations/patch_live_briefing.py` puts the explanation change on the live draft's own JSON instead: the three datasets' queries; in the two tables, "Why, in a sentence" in and "Why this tier" and "Why vulnerable" out; the note; and the rows below it moved down one. It checks that nothing else changed, and that the two tables' fields and columns equal the committed ones.
- **The body goes through a file.** The served JSON is about 72,000 characters, too long for a Windows command line, so the request body is passed with `--json @file`. The body has no `etag`, so it also restores over a later version.
- **Before deploy 6.** A bundle deploy writes the committed JSON over whatever is live, so the user's changes must be in `build_briefing.py` first. They go into it after Demo Day.
- **The table must exist.** The new datasets read `gold.area_tier_explanation`; in a workspace without the table, the two area tables fail (Free Edition). Before a deploy there, create the table: run `generate.py` with that profile, or run only its `CREATE TABLE`, which leaves every row on the tier sentence.

The commands below are in Git Bash, from the repo root, in the style of `docs/runbooks/demo_day_ops.md`. The ones marked **writes** wait for window D's review and the user's go.

```bash
REPO="$(pwd -W)"; PY="$REPO/.venv/Scripts/python.exe"
SCR="$(cygpath -m "$TEMP")/coolcheck-ops"; mkdir -p "$SCR"     # outside the repo
BRIEF=01f1cfb36fe51bb8906bbd306b88c9bc; COPY=01f1d14e8fd0135a9fb1f6639088d3b3; WH=7aa1dc56400d5b33
```

1. Save the live draft outside the repo: the restore point (read only). The get goes to a file and Python reads it as UTF-8. Piped into `python -I`, it was read as cp1252 and the body would have restored "Peak WBGT (Â°C)" twice (window D's review, finding 2). The last statement asserts that the body holds the live draft unchanged.

   ```bash
   databricks lakeview get $BRIEF -p coolcheck -o json > "$SCR/briefing_before_explanations.get.json" && "$PY" -I -X utf8 -c "import json,sys; d=json.load(open(sys.argv[1], encoding='utf-8')); open(sys.argv[2], 'w', encoding='utf-8').write(json.dumps({'serialized_dashboard': d['serialized_dashboard'], 'warehouse_id': d['warehouse_id']}, ensure_ascii=False)); assert json.load(open(sys.argv[2], encoding='utf-8'))['serialized_dashboard'] == d['serialized_dashboard'] and chr(194) not in d['serialized_dashboard']; print('restore body = live draft of', d['update_time'])" "$SCR/briefing_before_explanations.get.json" "$SCR/briefing_before_explanations.body.json"
   ```

2. The one-command restore (**writes**): the saved draft back, then published as now.

   ```bash
   databricks lakeview update $BRIEF -p coolcheck --dataset-catalog coolcheck --dataset-schema gold --json "@$SCR/briefing_before_explanations.body.json" && databricks lakeview publish $BRIEF -p coolcheck --warehouse-id $WH --embed-credentials
   ```

3. The body to apply (local only): the saved live draft with the explanation change and nothing else. The script stops if the draft already has the note.

   ```bash
   "$PY" scripts/explanations/patch_live_briefing.py "$SCR/briefing_before_explanations.get.json" "$SCR/briefing_with_explanations.body.json"
   ```

4. The copy first (**writes** the copy only), then look at its Briefing page at 1920×1080. `COPY` is the unpublished draft made on 26 Oct for the rendering check, in `/Users/<user>`.

   ```bash
   databricks lakeview update $COPY -p coolcheck --dataset-catalog coolcheck --dataset-schema gold --json "@$SCR/briefing_with_explanations.body.json"
   ```

5. The real one, then publish with the same warehouse and embedded credentials as now (**writes**):

   ```bash
   databricks lakeview update $BRIEF -p coolcheck --dataset-catalog coolcheck --dataset-schema gold --json "@$SCR/briefing_with_explanations.body.json" && databricks lakeview publish $BRIEF -p coolcheck --warehouse-id $WH --embed-credentials
   ```

6. Check, by reads:
   - `lakeview get` shows the body's datasets, with catalog and schema on each;
   - `lakeview get-published` shows a new `revision_create_time`;
   - the published page shows the column and the note.

   If anything is wrong, run step 2.
