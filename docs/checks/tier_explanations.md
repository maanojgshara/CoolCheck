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
