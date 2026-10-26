# Tier explanations: the first run, 26 Oct 2026

Window C, 26 Oct 2026, 21:50 to 23:40 SGT. One sentence per rated planning area saying why it has its tier, for the briefing dashboard's "Why, in a sentence" column. Design: `docs/design/tier_explanations.md`. Code: `src/coolcheck/explain.py` and `scripts/explanations/generate.py` at commit `75013d9`. `<user>` stands for the user's e-mail and user name.

## What ran

- **Commit:** `75013d9`, run from the repo root; the script printed "files this run uses unchanged from it" (`git status` of `src/coolcheck`, `scripts/explanations` and `reference` was clean).
- **Command:** `.venv\Scripts\python scripts/explanations/generate.py --target-date 2026-10-26 --out <scratch>/run_26oct.json`.
- **When:** 2026-10-26 14:55:42 to 14:56:34 UTC (22:55 to 22:56 SGT).
- **Model:** `ai_query('system.ai.meta-llama-3-3-70b-instruct', request, modelParameters => named_struct('temperature', 0.0D, 'max_tokens', 120), failOnError => false)` on the SQL warehouse `7aa1dc56400d5b33`, one call per area in one statement: 32 answers in 12 s. The name was tested on one row first ("Reply with the single word OK." gave `{"result":"OK","errorMessage":null}`).
- **Read:** `gold.area_heat_risk` for 2026-10-26, the rated areas with a tier: 32 (7 Medium, 25 Low, none High); `gold.area_vulnerability`, 32 rated areas; `gold.observed_heat_daily` for 25 Oct. The 32 areas take 20 stations, and each had a usable row for 25 Oct, so all 32 facts carry the observed peak. Not read: P(High), p_moderate, p_low, V, its rank, tier_rank, model_version, run_id (`explain.NEVER_READ`; `tests/explanations` scans every statement).
- **Written:** `coolcheck.gold.area_tier_explanation`, created by this run: 32 rows for 2026-10-26, read back as 32, one per area; every column has a comment; the tags are `source` and `licence`, the keys the other gold tables carry.

## Counts

| written_by | Rows |
|---|---|
| AI, checked | 31 |
| Template | 1 |

The one template is Clementi: the model's sentence left out the second measure, "10,410 residents aged 75+", and the check "facts: does not give 10,410" replaced it.

## Before the run: dry runs and prompt changes

`--dry-run` calls the model on 26 Oct's rows and writes nothing. Five dry runs before the commit changed the prompt and the check. No change was made for one area's case alone.

1. **One area (Toa Payoh), first prompt.** The model wrote "Medium: Moderate, upper, 3,835, 5th, 30.5°C observed.", a list and not a sentence, and it passed the check as it then was. The check gained three rules: the heat level and the third must be said in words, and each measure's value must be given; without the values, two areas could read the same. The prompt now asks for a natural sentence.
2. **Three areas.** Bukit Panjang's sentence dropped "for 25,690 residents aged 65+", and Changi's left out the observed peak, which an area with no measure needs. The prompt now says to copy each measure in full, and to give the note and the observed peak when there is no measure.
3. **Six areas: 4 passed, but read as lists** ("because 5 refuges in the area for 25,690 residents aged 65+, 57% of HDB flats…"). The prompt gained three worked examples with made-up facts. Because a model can copy an example's date, temperature or rank, the check now requires each of those to be its own fact. A number found elsewhere in the facts no longer passes (an example's "1 Jan" against "1-2 room").
4. **Six areas:** 6 passed.
5. **All 32:** 32 passed.

The committed run gave 31 of 32. With the same prompt at temperature 0, the sentences for 2 areas differed from dry run 5: Clementi's lost a measure, and Toa Payoh's lost its rank. Temperature 0 does not make the sentences repeat from one run to the next here. The check keeps what is shown correct either way.

## Every sentence with its facts

In tier order, then by name. The facts are those given to the model (the `facts` column); "Shown" is the `explanation` column.

- **Geylang**: Medium; forecast Moderate heat; middle third; observed at its station on 25 Oct: peak WBGT 30.5 °C (Low).
  - Facts: 3,182 1-2 room rental flats (7th most of 32 rated areas); 10,740 residents aged 75+ (14th most of 32 rated areas).
  - Shown (AI, checked): "Medium: forecast Moderate heat and the middle third for vulnerability, with 3,182 1-2 room rental flats (7th most of 32 rated areas) and 10,740 residents aged 75+."
- **Kallang**: Medium; forecast Moderate heat; upper third; observed at its station on 25 Oct: peak WBGT 30.5 °C (Low).
  - Facts: 5,921 1-2 room rental flats (2nd most of 32 rated areas); an 11% share of residents aged 75+ (5th highest of 31 rated areas measured).
  - Shown (AI, checked): "Medium: forecast Moderate heat and the upper third for vulnerability, with 5,921 1-2 room rental flats and an 11% share of residents aged 75+."
- **Punggol**: Medium; forecast Moderate heat; middle third; observed at its station on 25 Oct: peak WBGT 32.6 °C (Moderate).
  - Facts: 2,268 1-2 room rental flats (11th most of 32 rated areas); 60% of HDB flats beyond 400 m of a refuge (3rd highest of 29 rated areas measured).
  - Shown (AI, checked): "Medium: forecast Moderate heat and the middle third for vulnerability, with 2,268 1-2 room rental flats and 60% of HDB flats beyond 400 m of a refuge."
- **Sembawang**: Medium; forecast Moderate heat; middle third; observed at its station on 25 Oct: peak WBGT 31.4 °C (Moderate).
  - Facts: 1,838 1-2 room rental flats (14th most of 32 rated areas); 59% of HDB flats beyond 400 m of a refuge (4th highest of 29 rated areas measured).
  - Shown (AI, checked): "Medium: forecast Moderate heat and the middle third for vulnerability, with 1,838 1-2 room rental flats and 59% of HDB flats beyond 400 m of a refuge."
- **Sengkang**: Medium; forecast Moderate heat; middle third; observed at its station on 25 Oct: peak WBGT 31.7 °C (Moderate).
  - Facts: 12,260 residents aged 75+ (9th most of 32 rated areas); 1,687 1-2 room rental flats (16th most of 32 rated areas).
  - Shown (AI, checked): "Medium: forecast Moderate heat and the middle third for vulnerability, with 12,260 residents aged 75+ and 1,687 1-2 room rental flats."
- **Toa Payoh**: Medium; forecast Moderate heat; upper third; observed at its station on 25 Oct: peak WBGT 30.5 °C (Low).
  - Facts: 3,835 1-2 room rental flats (5th most of 32 rated areas); 14,290 residents aged 75+ (7th most of 32 rated areas).
  - Shown (AI, checked): "Medium: forecast Moderate heat and the upper third for vulnerability, with 3,835 1-2 room rental flats and 14,290 residents aged 75+."
- **Woodlands**: Medium; forecast Moderate heat; upper third; observed at its station on 25 Oct: peak WBGT 31.4 °C (Moderate).
  - Facts: 3,817 1-2 room rental flats (6th most of 32 rated areas); 11,700 residents aged 75+ (10th most of 32 rated areas).
  - Shown (AI, checked): "Medium: forecast Moderate heat and the upper third for vulnerability, with 3,817 1-2 room rental flats (6th most of 32 rated areas) and 11,700 residents aged 75+."
- **Ang Mo Kio**: Low; forecast Low heat; upper third; observed at its station on 25 Oct: peak WBGT 30.7 °C (Low).
  - Facts: 4,169 1-2 room rental flats (3rd most of 32 rated areas); 18,760 residents aged 75+ (2nd most of 32 rated areas).
  - Shown (AI, checked): "Low: forecast Low heat and the upper third for vulnerability, with 4,169 1-2 room rental flats (3rd most of 32 rated areas) and 18,760 residents aged 75+."
- **Bedok**: Low; forecast Low heat; upper third; observed at its station on 25 Oct: peak WBGT 31.1 °C (Moderate).
  - Facts: 4,155 1-2 room rental flats (4th most of 32 rated areas); 27,590 residents aged 75+ (the most of 32 rated areas).
  - Shown (AI, checked): "Low: forecast Low heat and the upper third for vulnerability, with 4,155 1-2 room rental flats and 27,590 residents aged 75+."
- **Bishan**: Low; forecast Moderate heat; lower third; observed at its station on 25 Oct: peak WBGT 30.5 °C (Low).
  - Facts: a 10% share of residents aged 75+ (13th highest of 31 rated areas measured).
  - Shown (AI, checked): "Low: forecast Moderate heat and the lower third for vulnerability, with a 10% share of residents aged 75+."
- **Bukit Batok**: Low; forecast Low heat; middle third; observed at its station on 25 Oct: peak WBGT 31.2 °C (Moderate).
  - Facts: 1,703 1-2 room rental flats (15th most of 32 rated areas); 10,540 residents aged 75+ (15th most of 32 rated areas).
  - Shown (AI, checked): "Low: forecast Low heat and the middle third for vulnerability, with 1,703 1-2 room rental flats and 10,540 residents aged 75+."
- **Bukit Merah**: Low; forecast Low heat; upper third; observed at its station on 25 Oct: peak WBGT 31.2 °C (Moderate).
  - Facts: 7,933 1-2 room rental flats (the most of 32 rated areas); 17,300 residents aged 75+ (5th most of 32 rated areas).
  - Shown (AI, checked): "Low: forecast Low heat and the upper third for vulnerability, with 7,933 1-2 room rental flats and 17,300 residents aged 75+."
- **Bukit Panjang**: Low; forecast Low heat; lower third; observed at its station on 25 Oct: peak WBGT 30.4 °C (Low).
  - Facts: 5 refuges in the area for 25,690 residents aged 65+ (10th fewest per resident of 30 rated areas measured); 57% of HDB flats beyond 400 m of a park (13th highest of 29 rated areas measured).
  - Shown (AI, checked): "Low: forecast Low heat and the lower third for vulnerability, with 5 refuges in the area for 25,690 residents aged 65+ and 57% of HDB flats beyond 400 m of a park."
- **Bukit Timah**: Low; forecast Low heat; lower third; observed at its station on 25 Oct: peak WBGT 30.1 °C (Low).
  - Facts: 2 refuges in the area for 15,970 residents aged 65+ (4th fewest per resident of 30 rated areas measured); a 9% share of residents aged 75+ (15th highest of 31 rated areas measured).
  - Shown (AI, checked): "Low: forecast Low heat and the lower third for vulnerability, with 2 refuges in the area for 15,970 residents aged 65+ and a 9% share of residents aged 75+."
- **Changi**: Low; forecast Moderate heat; lower third; observed at its station on 25 Oct: peak WBGT 32.1 °C (Moderate).
  - Facts: no component above the middle of the rated areas.
  - Shown (AI, checked): "Low: forecast Moderate heat and the lower third for vulnerability, with no component above the middle of the rated areas; its station observed a peak WBGT of 32.1 °C on 25 Oct."
- **Choa Chu Kang**: Low; forecast Low heat; middle third; observed at its station on 25 Oct: peak WBGT 30.4 °C (Low).
  - Facts: 55% of HDB flats beyond 400 m of a refuge (7th highest of 29 rated areas measured); 68% of HDB flats beyond 400 m of a park (5th highest of 29 rated areas measured).
  - Shown (AI, checked): "Low: forecast Low heat and the middle third for vulnerability, with 55% of HDB flats beyond 400 m of a refuge and 68% of HDB flats beyond 400 m of a park."
- **Clementi**: Low; forecast Low heat; middle third; observed at its station on 25 Oct: peak WBGT 31.2 °C (Moderate).
  - Facts: a 10% share of residents aged 75+ (9th highest of 31 rated areas measured); 10,410 residents aged 75+ (16th most of 32 rated areas).
  - Shown (Template): "Low: forecast Low heat, middle third for vulnerability, with a 10% share of residents aged 75+ (9th highest of 31 rated areas measured) and 10,410 residents aged 75+ (16th most of 32 rated areas)."
  - The model's sentence: "Low: forecast Low heat and the middle third for vulnerability, with a 10% share of residents aged 75+." Failed: facts: does not give 10,410.
- **Downtown Core**: Low; forecast Low heat; lower third; observed at its station on 25 Oct: peak WBGT 29.9 °C (Low).
  - Facts: no component above the middle of the rated areas.
  - Shown (AI, checked): "Low: forecast Low heat and the lower third for vulnerability, with no component above the middle of the rated areas; its station observed a peak WBGT of 29.9 °C on 25 Oct."
- **Hougang**: Low; forecast Low heat; upper third; observed at its station on 25 Oct: peak WBGT 31.2 °C (Moderate).
  - Facts: 17,410 residents aged 75+ (4th most of 32 rated areas); 52% of HDB flats beyond 400 m of a refuge (10th highest of 29 rated areas measured).
  - Shown (AI, checked): "Low: forecast Low heat and the upper third for vulnerability, with 17,410 residents aged 75+ and 52% of HDB flats beyond 400 m of a refuge."
- **Jurong East**: Low; forecast Low heat; upper third; observed at its station on 25 Oct: peak WBGT 31.2 °C (Moderate).
  - Facts: 72% of HDB flats beyond 400 m of a refuge (the highest of 29 rated areas measured); a 10% share of residents aged 75+ (10th highest of 31 rated areas measured).
  - Shown (AI, checked): "Low: forecast Low heat and the upper third for vulnerability, with 72% of HDB flats beyond 400 m of a refuge and a 10% share of residents aged 75+."
- **Jurong West**: Low; forecast Low heat; upper third; observed at its station on 25 Oct: peak WBGT 30.2 °C (Low).
  - Facts: 15,590 residents aged 75+ (6th most of 32 rated areas); 2,255 1-2 room rental flats (12th most of 32 rated areas).
  - Shown (AI, checked): "Low: forecast Low heat and the upper third for vulnerability, with 15,590 residents aged 75+ and 2,255 1-2 room rental flats."
- **Marine Parade**: Low; forecast Low heat; middle third; observed at its station on 25 Oct: peak WBGT 31.1 °C (Moderate).
  - Facts: an 11% share of residents aged 75+ (6th highest of 31 rated areas measured); 52% of HDB flats beyond 400 m of a refuge (11th highest of 29 rated areas measured).
  - Shown (AI, checked): "Low: forecast Low heat and the middle third for vulnerability, with an 11% share of residents aged 75+ and 52% of HDB flats beyond 400 m of a refuge."
- **Novena**: Low; forecast Low heat; lower third; observed at its station on 25 Oct: peak WBGT 30.6 °C (Low).
  - Facts: a 9% share of residents aged 75+ (16th highest of 31 rated areas measured); 61% of HDB flats beyond 400 m of a park (11th highest of 29 rated areas measured).
  - Shown (AI, checked): "Low: forecast Low heat and the lower third for vulnerability, with a 9% share of residents aged 75+ and 61% of HDB flats beyond 400 m of a park."
- **Outram**: Low; forecast Low heat; middle third; observed at its station on 25 Oct: peak WBGT 30.8 °C (Low).
  - Facts: 2,747 1-2 room rental flats (9th most of 32 rated areas); a 13% share of residents aged 75+ (the highest of 31 rated areas measured).
  - Shown (AI, checked): "Low: forecast Low heat and the middle third for vulnerability, with 2,747 1-2 room rental flats and a 13% share of residents aged 75+."
- **Pasir Ris**: Low; forecast Low heat; lower third; observed at its station on 25 Oct: peak WBGT 31.0 °C (Moderate).
  - Facts: 47% of HDB flats beyond 400 m of a refuge (14th highest of 29 rated areas measured); 5 refuges in the area for 24,320 residents aged 65+ (11th fewest per resident of 30 rated areas measured).
  - Shown (AI, checked): "Low: forecast Low heat and the lower third for vulnerability, with 47% of HDB flats beyond 400 m of a refuge and 5 refuges in the area for 24,320 residents aged 65+."
- **Queenstown**: Low; forecast Low heat; middle third; observed at its station on 25 Oct: peak WBGT 31.2 °C (Moderate).
  - Facts: 2,763 1-2 room rental flats (8th most of 32 rated areas); an 11% share of residents aged 75+ (4th highest of 31 rated areas measured).
  - Shown (AI, checked): "Low: forecast Low heat and the middle third for vulnerability, with 2,763 1-2 room rental flats and an 11% share of residents aged 75+."
- **Rochor**: Low; forecast Low heat; lower third; observed at its station on 25 Oct: peak WBGT 29.9 °C (Low).
  - Facts: 59% of HDB flats beyond 400 m of a refuge (5th highest of 29 rated areas measured); an 11% share of residents aged 75+ (7th highest of 31 rated areas measured).
  - Shown (AI, checked): "Low: forecast Low heat and the lower third for vulnerability, with 59% of HDB flats beyond 400 m of a refuge and an 11% share of residents aged 75+."
- **Serangoon**: Low; forecast Low heat; middle third; observed at its station on 25 Oct: peak WBGT 31.2 °C (Moderate).
  - Facts: 11,260 residents aged 75+ (11th most of 32 rated areas); a 10% share of residents aged 75+ (11th highest of 31 rated areas measured).
  - Shown (AI, checked): "Low: forecast Low heat and the middle third for vulnerability, with 11,260 residents aged 75+ and a 10% share of residents aged 75+."
- **Tampines**: Low; forecast Low heat; upper third; observed at its station on 25 Oct: peak WBGT 30.9 °C (Low).
  - Facts: 18,360 residents aged 75+ (3rd most of 32 rated areas); 2,570 1-2 room rental flats (10th most of 32 rated areas).
  - Shown (AI, checked): "Low: forecast Low heat and the upper third for vulnerability, with 18,360 residents aged 75+ and 2,570 1-2 room rental flats."
- **Tanglin**: Low; forecast Low heat; lower third; observed at its station on 25 Oct: peak WBGT 30.1 °C (Low).
  - Facts: no refuges in the area for 4,070 residents aged 65+ (the fewest per resident of 30 rated areas measured).
  - Shown (AI, checked): "Low: forecast Low heat and the lower third for vulnerability, with no refuges in the area for 4,070 residents aged 65+."
- **Tengah**: Low; forecast Low heat; lower third; observed at its station on 25 Oct: peak WBGT 30.0 °C (Low).
  - Facts: 64% of HDB flats beyond 400 m of a refuge (2nd highest of 29 rated areas measured); 55% of HDB flats beyond 400 m of a park (15th highest of 29 rated areas measured).
  - Shown (AI, checked): "Low: forecast Low heat and the lower third for vulnerability, with 64% of HDB flats beyond 400 m of a refuge and 55% of HDB flats beyond 400 m of a park."
- **Yishun**: Low; forecast Low heat; upper third; observed at its station on 25 Oct: peak WBGT 30.7 °C (Low).
  - Facts: 14,030 residents aged 75+ (8th most of 32 rated areas); 2,192 1-2 room rental flats (13th most of 32 rated areas).
  - Shown (AI, checked): "Low: forecast Low heat and the upper third for vulnerability, with 14,030 residents aged 75+ and 2,192 1-2 room rental flats."

The 32 sentences are all different from one another. On the same rows, the dashboard's "Why vulnerable" column, with its own merge of the two 75+ phrases, gives 24 of the 32 areas a text that at least one other area also shows. They fall into 8 groups of 7, 4, 3, 2, 2, 2, 2 and 2 areas; the largest is "many 1–2 room rental flats; many residents aged 75+".

## Flagged

I read all 32 against their facts. None gives a number that is not in its facts, the wrong tier, heat level or third, or ties the observed peak to the forecast. Three passed the check but could mislead a reader:

1. **"No refuges" rests on a partial list (Tanglin).** "No refuges in the area for 4,070 residents aged 65+" is true of the data, but the refuge layer holds 93 of about 223 Active Ageing Centres, so it may overstate the gap. The About page says the list is partial; the sentence does not. The same caveat applies to the counts for Bukit Panjang (5 refuges), Bukit Timah (2) and Pasir Ris (5).
2. **A value without its rank can look notable when it is mid-table.** 28 of the 31 model sentences give the measures' values without their ranks; Geylang, Woodlands and Ang Mo Kio give one rank each. The prompt allows that, and puts ranks after the values. Bishan's "a 10% share of residents aged 75+" is 13th of 31, and nothing in the sentence says so. The template gives ranks wherever they fit. A next step would be a prompt that asks for the ranks unless the sentence would pass 35 words. That would need a new run; this run is the committed prompt's.
3. **A Low tier in the upper third reads oddly.** Eight Low areas are in the upper third (Ang Mo Kio, Bedok, Bukit Merah, Hougang, Jurong East, Jurong West, Tampines, Yishun): "Low: forecast Low heat and the upper third for vulnerability, with …". This is correct, because Low heat gives Low in every third. But the measures after "with" explain the third, not the Low tier. The dashboard's own tier sentence has the same shape. Not changed.

Two more points, not flags:
- Changi and Downtown Core use the dashboard's wording "no component above the middle of the rated areas". "Component" is a word a coordinator may not use.
- The model's sentences follow the worked examples' frame closely. They read as sentences, but they add little beyond the template.

## Tokens and cost (estimate)

`ai_query` does not return token counts, so the counts below are estimates from characters.
- **Characters:** this run sent 116,414 characters and received 4,532. The five dry runs before it sent 156,372 and received 6,679, and the one-row name test about 30.
- **Tokens:** at about 4 characters per token (an estimate), this run is about 29,100 input and 1,130 output tokens. All runs together are about 68,200 and 2,800.

The rate per token comes from this workspace's own billing, not from a price page:
- **DBUs per token:** for Llama 3.3 70B, 7.143 DBU per million input tokens and 21.429 per million output tokens reproduce the billed DBUs from `system.ai_gateway.usage`'s token counts. On 24 Oct: 1,178,321 and 20,309 tokens give 8.852 DBU, against 8.858 billed. On 25 Oct: 796,053 and 7,372 tokens give 5.844 DBU, against 5.848 billed.
- **Price:** the SKU `PREMIUM_SERVERLESS_REAL_TIME_INFERENCE_AP_SINGAPORE` lists at US$0.088 per DBU (`system.billing.list_prices`).

**Estimated cost:** this run about 0.232 DBU, about US$0.02; all runs about 0.55 DBU, about US$0.05. A nightly run would cost about US$0.02 a night.

The exact counts will be in `system.ai_gateway.usage` once it has the run. At 23:00 SGT its latest event was 09:47:47 UTC.

**Exact counts, read on 27 Oct at 00:57 SGT: twice the calls, so about twice the cost.**
- **What the table holds.** For this run's window, `system.ai_gateway.usage` holds 64 calls, not 32, all `AI_QUERY` with status 200: 65,834 input and 2,476 output tokens.
- **Every statement doubled.** Each of my `ai_query` statements with an `ORDER BY` logged two calls per row. The dry runs show the same: 2 calls for 1 area, 6 for 3, 12 for 6, 64 for 32. The one-row name test, without an `ORDER BY`, logged 1.
- **The exact cost.** At the rates above, the run cost 0.523 DBU, about **US$0.05**. That is twice the calls, and 1,029 input tokens per call against the 909 the characters suggested.
- **A likely cause, not tested.** The sort's sampling pass may evaluate `ai_query` a second time. Dropping the `ORDER BY` from `explain.ai_sql` should halve the calls, since `generate.py` matches the answers to areas by name. That is a code change for a later commit.

```sql
SELECT count(*) AS calls, sum(input_tokens) AS input_tokens, sum(output_tokens) AS output_tokens
FROM system.ai_gateway.usage
WHERE service_name = 'system.ai.meta-llama-3-3-70b-instruct'
  AND event_time BETWEEN TIMESTAMP'2026-10-26 14:55:42' AND TIMESTAMP'2026-10-26 14:56:34'
```

## Tests

- `tests/explanations`: 37 passed, offline, in 0.07 s. They cover the facts, the template, the check (a correct sentence passes; a wrong number, a wrong tier, a banned word or a long sentence falls back, among 19 cases), the prompt's own examples, the SQL never reading what is never shown, and the patch on the live JSON.
- `tests/dashboards/test_briefing_dashboard.py`: 33 passed through Databricks Connect serverless, on temp views only (205 s). They cover:
  - the new column after Tier in both area tables, with every other column kept;
  - the `coalesce` and the join;
  - no dataset reading a column that is never shown, through the new table either;
  - the note under the top 10;
  - a missing row showing the tier sentence.

## The dashboard

- **The committed change is not applied.** The JSON adds the column and the note. The live briefing `01f1cfb36fe51bb8906bbd306b88c9bc` is not touched. The apply waits for window D's review and the user's go.
- **The live dashboard carries the user's editor changes.** The user made them on 26 Oct, 15:19 SGT (draft saved 07:19:18 UTC, published 07:19:20 UTC) and keeps them. They are layout and styling only, so the pages and `uiSettings` differ from the committed file, while the datasets are identical apart from the catalog and schema the server adds. The changes go into `build_briefing.py` after Demo Day. Until then the change is applied with `scripts/explanations/patch_live_briefing.py` on the live JSON; see `docs/design/tier_explanations.md`, "Applying it".
- **A copy for the rendering check.** "CoolCheck briefing (explanations check, copy)", `01f1d14e8fd0135a9fb1f6639088d3b3`, was created on the user's word at 23:04 SGT. It is an unpublished draft in `/Users/<user>`, made from the live JSON with the explanation patch.
- **Screenshot at 1920×1080: readable, the user's judgement.** The Chrome extension was not connected (six tries, 23:05 to 23:16 SGT), so the user took the screenshot of the copy: `Why, in a sentence.png`, 3367×1077 px, 23:24 SGT, in the project folder outside the repo. It shows the top-10 table with 26 Oct's rows, Punggol to Bishan, and the column "Why, in a sentence" after "Tier". Each sentence sits on one line, in full, and the 10 rows fit without scrolling down. The table scrolls sideways: "Why this tier" is cut off at the right edge, and "Why vulnerable", "1-2 room rental flats" and "Actions" are reached with the table's horizontal scroll bar, whose thumb spans about half its track. The user judged it readable, so no column was dropped. The note under the table is not in the screenshot.
- **The user's decision, 26 Oct 23:28, after the screenshot: hide "Why this tier" and "Why vulnerable" from both area tables.**
  - The reason: at the presenting laptop's width the top-10 table scrolls sideways; "Why this tier" is cut off, and "Why vulnerable", "1-2 room rental flats" and "Actions (a proposal)" are off-screen. Also, each sentence's first half repeats "Why this tier" word for word beside it; the sentence carries both.
  - The two tables now show #, Planning area, Tier, Why, in a sentence, 1-2 room rental flats, and Actions (a proposal). Only the widgets' columns changed; the datasets keep both fields.
  - The change is in `build_briefing.py`, the regenerated JSON, `patch_live_briefing.py` and their tests. `tests/explanations` passed 37 offline. `test_briefing_dashboard.py` passed 33 of 33 through Databricks Connect (temp views only, 203 s).
- **The copy, updated at 23:33 SGT, and only the copy.** Before writing, the live draft was read again and was unchanged since 22:45 (same `update_time` and `etag`; published revision 07:19:20 UTC). The copy was built from it with the updated patch. Read back, the copy equals the body sent, catalog and schema included. Both of its area tables show the six columns, and it is still unpublished. The live dashboard was not touched.
- **Does "Actions" now show at the presenting width?** Mostly not. This is an estimate from the screenshot's geometry, not a render: the Chrome extension was still not connected.
  - In the screenshot, scaled to 2,000 px, the table's viewport is about 1,980 px and the scroll thumb spans about 54% of its track, so the table is about 3,650 px wide. "Why, in a sentence" ends at about x = 1,645.
  - The two hidden columns are each about 466 px wide. Their longest top-10 texts are 62 characters, at about 7.1 px per character plus padding.
  - Without them, the table is about 2,715 px wide. "1-2 room rental flats" runs to about x = 1,831, and Actions from there to about 2,715.
  - So at that width Actions would show its header and the Low rows' "Routine.", but the Medium rows' 128-character action only for its first 20 or so characters. The table would still scroll sideways, with about 73% in view instead of 54%.
  - The user can look at the copy to see it as rendered.
- **Window D's finding 2 is fixed.** The design note's restore step 1 now writes the get to a file, reads it as UTF-8 and asserts that the restore body equals the live draft. Run read-only into a scratch folder at about 23:34 SGT, the body equalled the live draft and "Peak WBGT (°C)" was intact.

## The check tightened, after window D's review (26 Oct, 23:40 to 00:00 SGT)

Window D's review (`docs/checks/review_tier_explanations.md`, findings 3 and 4) found that the check let 36 of 54 wrong sentences through. The user chose to tighten it before 27 Oct's sentences are made. `explain.check` gained D's three rules, beside the checks it had (`docs/design/tier_explanations.md`, "Why the check"):
- (a) each measure's text, or the note, as given;
- (b) each bracket its own fact: a measure's rank right after the measure, the NEA category right after the observed peak;
- (c) nothing but the facts' own phrases and 18 frame words.

**The stored 26 Oct sentences, re-checked offline.** A read-only SELECT of `gold.area_tier_explanation` for 2026-10-26, at about 23:45 SGT, read back 32 rows. They are kept as `tests/explanations/stored_26oct.json`, a regression test. Under the tightened check:
- **31 of the 31** model sentences that were shown ("AI, checked") still pass. D's prototype found the same.
- **32 of the 32** templates pass.
- Clementi's model sentence still fails: it now also reports "not as given: 10,410 residents aged 75+".
- The prompt's 3 worked examples pass.

**Tests.** `tests/explanations` passed 76, offline, in 0.16 s: the earlier 37 and 39 new.
- D's 3 controls pass: Toa Payoh's stored sentence, the same with its true rank, and the same with the peak in the prompt's form.
- 36 wrong sentences from D's section 2 fall back: 13 groups, one or more cases each, on the stored facts of Toa Payoh, Tengah and Ang Mo Kio (and Toa Payoh with a made-up High tier, for "a near-certain High-heat day").
  - The checks before the rules let 35 of the 36 through. The 36th ("its 30.5 °C peak on 25 Oct points to forecast Moderate heat") was already caught, because "points to" ties the peak to the forecast.
  - A test requires every group to keep at least one case that only the new rules catch.
- The 15 offline structural tests of `test_briefing_dashboard.py` passed. The whole file ran through Databricks Connect: see the last line of this section.

**The note under the top 10 (D's finding 4)** now reads: "Each sentence is written by Llama 3.3 70B through Databricks AI Functions from the row's facts; code checks that it states the tier, heat level, third and each measure as given, and nothing but the facts, or shows the template sentence." It is "each measure", not "each fact", because the ranks and the observed peak are optional. The change is in `build_briefing.py` and the regenerated JSON, and the dashboard test checks the exact wording. `patch_live_briefing.py` copies the note from the committed JSON, so it needed no change; its tests pass with the new note.

**The copy, updated at 23:53:44 SGT, and only the copy.** The live draft was read again first and was unchanged (`update_time` 07:19:18 UTC, the same `etag`). The copy was built from it with the patch. Read back, the copy equals the body sent: the six columns, the new note, still unpublished. The live dashboard was not touched, and `generate.py` was not run: 27 Oct's sentences wait for the 00:45 SGT job and the user's word.

`test_briefing_dashboard.py` through Databricks Connect: 33 of 33 passed (temp views only, 215 s).

## The second run: 27 Oct (27 Oct 2026, 00:55 SGT)

The user's OK was for one run, after the 00:45 SGT heat forecast. It came after window D's re-review 3 (`cffdf6c`), which found that the check with rule (d) catches every wrong sentence D had tried.

**Read-only checks first:**
- **The forecast job ran.** Job 131450384398104, run 1102490184153637: periodic, 00:45:01 to 00:50:22 SGT, `SUCCESS`.
- **27 Oct's rows are in.** `gold.area_heat_risk` holds 41 rows for 27 Oct, 32 of them rated: 9 Medium, 23 Low, none High, 9 Not rated, no "No forecast". They were scored at 00:50:09 SGT, and 27 Oct is the latest date.
- **The observations are in.** `gold.observed_heat_daily` has usable rows for 30 stations on 26 Oct.
- **The table held only 26 Oct.** `gold.area_tier_explanation` had 26 Oct's 32 rows and nothing else.

**The run:**
- **Code:** commit `cffdf6c` (`7f66d1f`'s check with rule (d), and D's re-review 3). The tree was clean, and the script printed "files this run uses unchanged from it".
- **Command:** `.venv\Scripts\python scripts/explanations/generate.py --target-date 2026-10-27 --out <scratch>/run_27oct.json`, run once.
- **When:** 2026-10-26 16:55:44 to 16:56:23 UTC (27 Oct, 00:55 to 00:56 SGT).
- **What it did:** it read 32 rated areas with a tier, each with an observed peak for 26 Oct. `ai_query` returned 32 answers in 12 s. It sent 116,386 characters and received 4,554. By the count above, the gateway should record 64 calls; the exact tokens come a few hours later.

**Counts:** 32 "AI, checked", 0 "Template". No sentence failed a check, so no template is shown and there are no failed checks to list.

**Read-back** (the script's, and a separate read-only query):
- 32 rows for 2026-10-27, one per area, all "AI, checked".
- 26 Oct's 32 rows are unchanged.
- All 10 columns have a comment, and the tags are `source` and `licence`.
- The table comment now names the observation rule too: `comment_sqls` rewrote it to the current code's text.

**The 32 sentences in briefing order.** The order is read through the dashboard's own query (by tier, then within the tier as the page orders it; only the position is read). Items 1 to 10 are the top-10 table. With 9 Medium areas, the table under it shows "None: every High or Medium area is in the top 10".

1. **Woodlands** (Medium): "Medium: forecast Moderate heat and the upper third for vulnerability, with 3,817 1-2 room rental flats (6th most of 32 rated areas) and 11,700 residents aged 75+."
2. **Toa Payoh** (Medium): "Medium: forecast Moderate heat and the upper third for vulnerability, with 3,835 1-2 room rental flats (5th most of 32 rated areas) and 14,290 residents aged 75+."
3. **Punggol** (Medium): "Medium: forecast Moderate heat and the middle third for vulnerability, with 2,268 1-2 room rental flats and 60% of HDB flats beyond 400 m of a refuge."
4. **Kallang** (Medium): "Medium: forecast Moderate heat and the upper third for vulnerability, with 5,921 1-2 room rental flats and an 11% share of residents aged 75+."
5. **Sengkang** (Medium): "Medium: forecast Moderate heat and the middle third for vulnerability, with 12,260 residents aged 75+ and 1,687 1-2 room rental flats."
6. **Geylang** (Medium): "Medium: forecast Moderate heat and the middle third for vulnerability, with 3,182 1-2 room rental flats and 10,740 residents aged 75+."
7. **Sembawang** (Medium): "Medium: forecast Moderate heat and the middle third for vulnerability, with 1,838 1-2 room rental flats and 59% of HDB flats beyond 400 m of a refuge."
8. **Hougang** (Medium): "Medium: forecast Moderate heat and the upper third for vulnerability, with 17,410 residents aged 75+ and 52% of HDB flats beyond 400 m of a refuge."
9. **Serangoon** (Medium): "Medium: forecast Moderate heat and the middle third for vulnerability, with 11,260 residents aged 75+ and a 10% share of residents aged 75+."
10. **Bishan** (Low): "Low: forecast Moderate heat and the lower third for vulnerability, with a 10% share of residents aged 75+."
11. **Changi** (Low): "Low: forecast Moderate heat and the lower third for vulnerability, with no component above the middle of the rated areas; its station observed a peak WBGT of 30.5 °C on 26 Oct."
12. **Ang Mo Kio** (Low): "Low: forecast Low heat and the upper third for vulnerability, with 4,169 1-2 room rental flats and 18,760 residents aged 75+."
13. **Bedok** (Low): "Low: forecast Low heat and the upper third for vulnerability, with 4,155 1-2 room rental flats and 27,590 residents aged 75+."
14. **Yishun** (Low): "Low: forecast Low heat and the upper third for vulnerability, with 14,030 residents aged 75+ and 2,192 1-2 room rental flats."
15. **Bukit Merah** (Low): "Low: forecast Low heat and the upper third for vulnerability, with 7,933 1-2 room rental flats and 17,300 residents aged 75+."
16. **Queenstown** (Low): "Low: forecast Low heat and the middle third for vulnerability, with 2,763 1-2 room rental flats and an 11% share of residents aged 75+."
17. **Tengah** (Low): "Low: forecast Moderate heat and the lower third for vulnerability, with 64% of HDB flats beyond 400 m of a refuge and 55% of HDB flats beyond 400 m of a park."
18. **Marine Parade** (Low): "Low: forecast Low heat and the middle third for vulnerability, with an 11% share of residents aged 75+ and 52% of HDB flats beyond 400 m of a refuge."
19. **Tampines** (Low): "Low: forecast Low heat and the upper third for vulnerability, with 18,360 residents aged 75+ and 2,570 1-2 room rental flats."
20. **Tanglin** (Low): "Low: forecast Low heat and the lower third for vulnerability, with no refuges in the area for 4,070 residents aged 65+."
21. **Jurong West** (Low): "Low: forecast Low heat and the upper third for vulnerability, with 15,590 residents aged 75+ and 2,255 1-2 room rental flats."
22. **Jurong East** (Low): "Low: forecast Low heat and the upper third for vulnerability, with 72% of HDB flats beyond 400 m of a refuge and a 10% share of residents aged 75+."
23. **Novena** (Low): "Low: forecast Low heat and the lower third for vulnerability, with a 9% share of residents aged 75+ and 61% of HDB flats beyond 400 m of a park."
24. **Bukit Timah** (Low): "Low: forecast Low heat and the lower third for vulnerability, with 2 refuges in the area for 15,970 residents aged 65+ and a 9% share of residents aged 75+."
25. **Choa Chu Kang** (Low): "Low: forecast Low heat and the middle third for vulnerability, with 55% of HDB flats beyond 400 m of a refuge and 68% of HDB flats beyond 400 m of a park."
26. **Outram** (Low): "Low: forecast Low heat and the middle third for vulnerability, with 2,747 1-2 room rental flats and a 13% share of residents aged 75+."
27. **Bukit Batok** (Low): "Low: forecast Low heat and the middle third for vulnerability, with 1,703 1-2 room rental flats and 10,540 residents aged 75+."
28. **Clementi** (Low): "Low: forecast Low heat and the middle third for vulnerability, with a 10% share of residents aged 75+ and 10,410 residents aged 75+."
29. **Bukit Panjang** (Low): "Low: forecast Low heat and the lower third for vulnerability, with 5 refuges in the area for 25,690 residents aged 65+ and 57% of HDB flats beyond 400 m of a park."
30. **Rochor** (Low): "Low: forecast Low heat and the lower third for vulnerability, with 59% of HDB flats beyond 400 m of a refuge and an 11% share of residents aged 75+."
31. **Pasir Ris** (Low): "Low: forecast Low heat and the lower third for vulnerability, with 47% of HDB flats beyond 400 m of a refuge and 5 refuges in the area for 24,320 residents aged 65+."
32. **Downtown Core** (Low): "Low: forecast Low heat and the lower third for vulnerability, with no component above the middle of the rated areas; its station observed a peak WBGT of 29.1 °C on 26 Oct."

**Read against their facts (window C):**
- **All 32 are right.** Every sentence:
  - begins with its tier and states its forecast heat level and third;
  - gives each measure exactly as in the facts;
  - adds nothing else.
- **The tiers follow the 3×3 rule.** The 9 Medium areas have Moderate heat in the upper or middle third. The Low areas have Low heat, or Moderate heat in the lower third (Bishan, Changi, Tengah).
- **The two ranks given are right:** Woodlands 6th and Toa Payoh 5th for rental flats.
- **The two observations are right.** Changi's and Downtown Core's are the 26 Oct peaks in the facts, after the semicolon.
- **All different.** The 32 sentences differ from one another, and run from 18 to 32 words.

The three flags of 26 Oct still stand:
- Tanglin's "no refuges" rests on a partial refuge list.
- 30 of the 32 give values without ranks.
- Seven Low areas in the upper third read "Low … upper third, with …": Ang Mo Kio, Bedok, Yishun, Bukit Merah, Tampines, Jurong West and Jurong East.

**Not done:** nothing was applied to the live dashboard. The apply waits for window D's review and the user's go, by `patch_live_briefing.py`.

## The apply to the live dashboard (27 Oct 2026, 01:29 SGT)

The user's go came after window D's read-only check of 27 Oct's rows (`d1b3096`: all 32 true to their facts). It covered applying the explanation change to the live briefing `01f1cfb36fe51bb8906bbd306b88c9bc` as `docs/design/tier_explanations.md`, "Applying it", says. The run went from a clean tree at `d1b3096`, in Git Bash, with `SCR` = `%TEMP%/coolcheck-ops`, outside the repo.

**Before the apply (reads only).**
- The published version was revision 07:19:20.248 UTC, with warehouse `7aa1dc56400d5b33` and credentials embedded.
- `SCR` held no earlier `briefing_*explanations*` file, so nothing was overwritten.

**Step 1, the restore point.** The design note's step 1 command, as written, saved the live draft to `$SCR/briefing_before_explanations.get.json`. It wrote the restore body `$SCR/briefing_before_explanations.body.json` and asserted that the body's `serialized_dashboard` equals the draft's, with no `Â`. It printed "restore body = live draft of 2026-10-26T07:19:18.685Z": the draft of the user's 15:19 editor changes, unchanged since.

**Step 2, the body.** The design note's step 3 ran `patch_live_briefing.py` on that saved draft and wrote `$SCR/briefing_with_explanations.body.json`; its own check passed. The body equals the copy dashboard as checked at 23:53, so the copy step was not repeated.

**Step 3, update and publish.** The design note's step 5 ran `lakeview update` with that body, `--dataset-catalog coolcheck --dataset-schema gold`, then `lakeview publish` with `--warehouse-id 7aa1dc56400d5b33 --embed-credentials`.
- The draft was updated at 17:29:52.911 UTC (01:29:52 SGT).
- The published revision is 17:29:53.334 UTC (01:29:53 SGT), with warehouse `7aa1dc56400d5b33` and `embed_credentials` true.

**Step 4, the read-back (reads only).** Every check passed:
- **The draft equals the body sent.**
- **Only the patch's changes.** Against the saved draft, `patch_live_briefing.check` passed: only the patch's changes, so every editor change of 26 Oct, 15:19 is kept. The patch's changes are:
  - the queries of `ds_area_map`, `ds_top_areas` and `ds_more_areas`;
  - the two tables' fields and columns;
  - the note at (0, 30, 12, 1);
  - `more-areas` and `trend-chart` one row lower.

  The page order (About first) and `uiSettings` are unchanged.
- **Both area tables show six columns:** #, Planning area, Tier, Why, in a sentence, 1-2 room rental flats, and Actions (a proposal).
- **The published version is newer than the update** (17:29:53.334 against 17:29:52.911 UTC), with that warehouse and embedded credentials.
- **The top-10 query returns 27 Oct's rows.** The `ds_top_areas` query as the draft holds it (its catalog `coolcheck`, schema `gold`) was run read-only through the statement API. It returned 27 Oct's ten rows, positions 1 to 10, Woodlands to Bishan. Each row's "Why, in a sentence" equals the table's 27 Oct sentence for the area.

**The one-command restore** (Git Bash or PowerShell 7). It puts the saved draft back and publishes it as before:

```bash
databricks lakeview update 01f1cfb36fe51bb8906bbd306b88c9bc -p coolcheck --dataset-catalog coolcheck --dataset-schema gold --json "@C:/Users/<user>/AppData/Local/Temp/coolcheck-ops/briefing_before_explanations.body.json" && databricks lakeview publish 01f1cfb36fe51bb8906bbd306b88c9bc -p coolcheck --warehouse-id 7aa1dc56400d5b33 --embed-credentials
```

**Not done:** no bundle deploy, no job change, nothing else on the workspace. The copy dashboard `01f1d14e8fd0135a9fb1f6639088d3b3` stays as it was, unpublished.
