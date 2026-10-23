# Risk score and tiers: design note

Written 23 Oct 2026 for Day 4, window C, step 1. It turns Guide §A11 decision 9 (the vulnerability index, the thirds, the score, the block order and where it is built; decided 23 Oct, 18:26 SGT), decision 8(d) (the heat side) and decision 7 (the cut-off) into a build plan. **Status: approved 23 Oct 2026 with two changes and your answers to the open points (§13):** (1) both MLflow runs go to the trial workspace's tracking server, not a local store (§10); (2) the small-area rule is corrected (Guide decision 9(g)): 0.5 applies only to shares and rates with a small denominator, and counts always keep their real value (§2 to §4).

**Read for it:** Guide §A11 decisions 7 to 9, §14.1 and §A13 (EMA); `docs/design/backtest.md` (§1, §2, area-days); `docs/checks/refuge_park_access.md`; `coolcheck-data/analysis/area_access.csv`, `area_exposure.csv` and `hdb_blocks_to_areas.csv`; HDB Property Information (header and rental columns); EMA `SES_tidy` table T3.5 (header and a profile of the 1–2 room rows); `predictions_area_days.parquet` (schema and Parquet statistics only, no rows).

**Counted for it, 23 Oct:** 32 rated areas; 9 not rated, with 4,730 residents aged 65+; confirmed HDB dwelling units Changi 166, Tanglin 166, Downtown Core 240; Changi 660 residents, the only rated area under 1,000; the 10 unconfirmed blocks hold no 1–2 room rental flats (61,748 in all); T3.5 has 1–2 room rows for 29 planning areas in 2021 to 2024, which by name cover 29 of the 32 rated areas (not Changi, Downtown Core or Tanglin).

## At a glance

- 32 rated planning areas get a vulnerability index V from seven components, each a percentile among the rated areas; thirds of 11, 11 and 10; a plain reason from the two largest contributors.
- Tomorrow's heat level comes from window B's probabilities and the H4 cut-off; the tier from the 3×3 rule; P(High) × V orders areas inside a tier and is never shown.
- Built as three SQL views in Unity Catalog over the Silver tables and two reference tables loaded from repo files. A Python twin of the same rules runs the checks and the tests, and the tests compare it with the SQL on the same rows.
- One MLflow run in the trial workspace: back-test tier frequencies and reach (target dates up to 31 Aug 2026 only), and seven sensitivity runs. The electricity term has its own run in the same experiment and its own Silver table.
- Nothing dated 1 Sep to 19 Oct 2026 is read (§1).

## 1. The hard rule: nothing dated 1 Sep to 19 Oct 2026

- **What it covers (my reading; §13 Q11):** every dated observation: WBGT readings, labels, forecasts, model predictions and `gold.heat_forecast` rows. The static layers behind V (SingStat June 2026, HDB Property Information, the refuge and park files, EMA to Jun 2025) are reference layers decided in R1 and R2, not observations. Two carry update stamps inside the window: the People's Association club file of 2 Oct 2026 and HDB Property Information of 8 Oct 2026.
- **Back-test rows:** `predictions_area_days.parquet` is read with a pyarrow filter `target_date <= 2026-08-31` (`coolcheck.backtest.LAST_BACKTEST_DATE`), and the frame is asserted right after the read. A test plants a 2026-09-01 row and the assertion must fire. The file's own Parquet statistics give 2025-07-01 to 2026-08-31 (17,438 area-days), so the filter should remove nothing.
- **`gold.heat_forecast`:** not read in steps 1 and 2. In step 3 the view is created without reading rows, and any read-back reads target dates after 19 Oct 2026 only.

## 2. Which areas are rated

- **Rated:** the 32 planning areas with at least one confirmed HDB block in `silver.area_access`. My count matches the spec.
- **Not rated** (heat level only, tier "Not rated"): the other 9 of the 41 areas with residents aged 65+: Mandai, Museum, Newton, Orchard, River Valley, Seletar, Singapore River, Southern Islands, Sungei Kadut (4,730 residents aged 65+, 0.6% of 806,080).
- **Small-area rule, flagged (decision 9(g), correcting 9(a)):** 0.5 applies only to shares and rates with a small denominator: the two 400 m shares where the area has fewer than 1,000 confirmed HDB dwelling units (Changi, Tanglin, Downtown Core); the 75+ share where it has fewer than 1,000 residents (Changi); refuges per 1,000 aged 65+ where it has fewer than 1,000 residents aged 65+ (Changi 170, Downtown Core 420). Counts always keep their real value, so the 1–2 room rental count and the 75+ count are real for every rated area.
- *Why (decision 9(a), 9(g)):* the vulnerability measures come from HDB blocks, so an area without blocks has nothing to rate. A share or a rate over a small denominator jumps to an extreme percentile on a few units, so it is held at the middle; a count has no denominator, and a small count is a real "few", so it keeps its value. The 1,000 threshold is the one `area_exposure` already uses for its share tables.

## 3. The seven components

| key | sub-index | weight | raw value | source | more vulnerable when | small-area rule |
|---|---|---:|---|---|---|---|
| `aged_75_plus` | senior exposure | 0.20 | residents aged 75+ | `silver.area_exposure` | higher | none |
| `share_75_plus` | senior exposure | 0.15 | their share of residents | `silver.area_exposure` | higher | residents < 1,000 |
| `rental_1_2_room` | can't-cool-down | 0.25 | `1room_rental` + `2room_rental`, summed over the area's confirmed blocks | `silver.block_access` (two columns added, §9) | higher | none (a count) |
| `electricity_hot_rise` | can't-cool-down | 0.05 | 1–2 room hot-month ratio, mean of 2022 to 2024 (§8) | `silver.ema_area_electricity` | lower (inverted) | none; no EMA value gives 0.5 |
| `refuge_beyond_400m` | cooling-access gap | 0.15 | 1 − `share_du_within_400m` (refuge, main) | `silver.area_access` | higher | HDB DU < 1,000 |
| `refuges_per_1000_65` | cooling-access gap | 0.10 | `refuges_per_1000_65_plus` (main) | `silver.area_access` | lower (inverted) | aged 65+ < 1,000 |
| `park_beyond_400m` | cooling-access gap | 0.10 | 1 − `share_du_within_400m` (park, main) | `silver.area_access` | higher | HDB DU < 1,000 |

The weights sum to 1.00: senior exposure 0.35, can't-cool-down 0.30, cooling-access gap 0.35. The loader refuses a weights file that does not sum to 1.

- *Why (decision 9(b)):* age and low income drive heat harm in seniors, so exposure and can't-cool-down carry 0.65 of the weight. 1–2 room rental flats are the best open proxy for low-income seniors, often living alone and without air-conditioning. Counts as well as shares, because the briefing directs outreach effort and the number of calls scales with the number of people. Parks get only 0.10 because the NParks and URA layers rank the areas almost oppositely (rho 0.08, `refuge_park_access.md`), so a larger weight would make the result depend on the source. Electricity gets 0.05 because the inference is weak (a smaller rise "may indicate" less air-con use, no more) and EMA covers only part of the areas. The weights are a judgement, not fitted: there is no open outcome data (heat illness) to fit them to. The sensitivity runs (§10) show how much they matter, and the weights sit in a reference table, so a practitioner's review changes them by a reload, not a rebuild.
- **Confirmed blocks only** for every component built from blocks (the rental count and the two 400 m shares), as `geocode_hdb.md` asks of any use that needs a block's coordinate (a block's area comes from its coordinate). For the rental count this changes nothing today: the 10 unconfirmed blocks hold no 1–2 room rental flats.

## 4. Percentiles, neutral values and flags

- **Percentile:** p = (r̄ − 1) / (n − 1), where r̄ is the area's mean rank among the n rated areas with a usable value (ties share the mean of their ranks), ranked so that a larger p is more vulnerable: ascending for "higher", descending for "inverted". p runs from 0 to 1 (§13 Q1).
- **Neutral 0.5:** an area whose value is missing (no EMA value) or set aside by the small-area rule gets p = 0.5 and is left out of that component's ranking, so n is smaller for that component (§13 Q2). Today that gives n = 32 for the 75+ count and the rental count, 31 for the 75+ share, 30 for refuges per 1,000 aged 65+, 29 for each 400 m share, and at most 29 for electricity.
- **Flags on each area:** `small_hdb` (confirmed HDB DU < 1,000), `small_residents` (residents < 1,000), `small_aged_65` (residents aged 65+ < 1,000), `electricity_missing`, and `neutral_components`, which names each component held at 0.5 and why.
- *Why (decision 9(b)):* percentile ranks make components with different units comparable and keep one extreme value from dominating; the US CDC's Social Vulnerability Index is built this way. 0.5 is the middle, so a component without a trustworthy value neither raises nor lowers V.

## 5. V, the thirds and the reason

- **V** = Σ weight × p over the seven components, from 0 to 1.
- **Thirds:** order the 32 by V, highest first: places 1 to 11 are the upper third, 12 to 22 the middle, 23 to 32 the lower. A tie across a boundary is broken by residents aged 75+, more first, then by name (§13 Q4).
- **Reason:** the two components with the largest weight × p, in plain words:

| component | phrase |
|---|---|
| `aged_75_plus` | many residents aged 75+ |
| `share_75_plus` | a high share of residents aged 75+ |
| `rental_1_2_room` | many 1–2 room rental flats |
| `electricity_hot_rise` | a small hot-month rise in 1–2 room electricity use (may indicate less air-con use) |
| `refuge_beyond_400m` | many flats beyond 400 m of a refuge |
| `refuges_per_1000_65` | few refuges per resident aged 65+ |
| `park_beyond_400m` | many flats beyond 400 m of a park |

  Only a component with a real value can be named, and only at or above the middle (p ≥ 0.5), so the phrase stays true; an area with fewer than two such components names one, or says "no component above the middle of the rated areas" (§13 Q5).
- *Why (decision 9(b), §14.1):* the tier rule needs three groups a non-technical reader can follow, and the reason makes each area explainable in one sentence ("many residents aged 75+; many 1–2 room rental flats").

## 6. Tomorrow's heat, the tier and the score

- **Heat level** (decision 8(d)): High if `p_high` ≥ 0.10975585695894975; otherwise Moderate if `p_moderate` ≥ `p_low`; otherwise Low. The rule has no gap: below the cut-off, High cannot be the most likely class. The constant lives once, in `coolcheck.risk.HIGH_CUTOFF`, and a test checks that it equals `coolcheck.final_check.FINAL_CUTOFF`.
- **Tier** (the 3×3 rule, §14.1); an unrated area gets "Not rated":

| forecast heat ↓ / vulnerability → | lower third | middle third | upper third |
|---|---|---|---|
| Low | Low | Low | Low |
| Moderate | Low | Medium | Medium |
| High | Medium | High | High |

  The matrix is a parameter in both the SQL and the Python, so the choice left open in decision 9(f), Moderate heat in a middle-third area becoming Low, is a one-line change. The check reports the tier counts under both.
- **Score** = `p_high` × V, used only to order areas within a tier on a date: `tier_rank`, 1 first, ties by name. My proposal: `gold.area_heat_risk` exposes `tier_rank` and not the score or the probabilities, so neither can reach a page or the agent by accident; they stay in `gold.heat_forecast` for audit.
- **Tier sentence** (§14.1): "High: forecast High heat, upper third for vulnerability"; for an unrated area, "Not rated: forecast Moderate heat; no HDB blocks to rate".
- **Missing forecast** (§13 Q6) and the order of unrated areas (§13 Q7) are open.
- *Why (decision 9(c)):* a tier must be explainable to a non-technical user in one sentence (tomorrow's heat crossed with how vulnerable the area is), which a continuous score is not. Absolute heat, not rank, so alerts do not fire on cool days (§14.1). P(High) is not shown because the calibration check found it over-states at its highest values and under-states at the start of a hot season (§A6 (n)).

## 7. Actions per tier: `gold.tier_actions`

| tier | actions |
|---|---|
| High | Phone checks before noon on flagged seniors in the priority blocks; AACs and community clubs extend hours as cooling spaces; the town council is told. |
| Medium | The AAC broadcasts a hydration and heat advisory in four languages; volunteers flag seniors living alone in the priority blocks. |
| Low | Routine. |
| Not rated | Heat level shown only. |

Every row carries `review_status` = "proposal, not yet reviewed by a practitioner".

- *Why (§14.1, decision 9(f)):* the actions live once, in a small table read by the dashboard and the agent. CoolCheck supplies areas, blocks and counts; the AACs' own client lists supply the people, so no personal data is held. The status stays in the table until a practitioner reviews it.

## 8. The electricity term (its own logged run)

- **Source:** `../Docs/EMA/SES_tidy.xlsx.coredownload.xlsx`, sheet T3.5, "Average Monthly Household Electricity Consumption by Planning Area & Dwelling Type". Columns `Dwelling Type`, `Year`, `Month`, `Region`, `Description`, `Kwh Per Acc`; monthly from 2005 to Jun 2025, plus `Annual` rows, which are ignored. Rows with `Dwelling Type` = "1-room / 2-room" only. In 2021 to 2024, `Description` holds 29 planning areas, the 5 regions and "Overall". The 1–2 room rows hold numbers only (no "s").
- **Per area:** for each Y in 2022, 2023 and 2024, ratio_Y = mean(Apr, May, Jun of Y) / mean(Nov and Dec of Y − 1, Jan and Feb of Y). A year's ratio needs all seven months. The area's value is the mean of the three ratios when all three exist; otherwise it is missing (0.5 in V).
- **The first reading, reproduced (your answer to Q9):** the mean over area-years of each year's April–June / November–February ratio, 1–2 room, 2015 to 2024, with the number of area-years (the first reading was 1.09 over 280). Beside it, EMA's "Overall" row pooled: the mean of all its April to June values over 2015 to 2024 over the mean of all its November-to-February values (Nov 2014 to Feb 2024).
- **Names:** EMA's names, upper-cased, matched to Master Plan 2025 `PLN_AREA_N`; every name that does not match is listed. EMA's areas follow the Singapore Land Authority's Aggregated Data Zone 2024 (footnote b), not URA's Master Plan 2025, so boundaries may differ slightly; this is stated.
- **Reported:** coverage among the 32 rated areas (by name and with all three years), the yearly ratios, the pooled ratios and EMA's footnotes: (a) numbers may not add up because of rounding; (b) planning areas follow the Aggregated Data Zone 2024; (c, d) a missing or zero value can be nil, negligible or not applicable; "s" is suppressed; (e) solar PV is excluded; "Data for 2025 is at Jun 2025"; "accurate as of Sep 2025"; "Source: Energy Market Authority (EMA)".
- **Wording:** a smaller rise "may indicate" less air-con use; never more than that.
- **Output:** `scripts/static/ema_electricity.py` writes `coolcheck-data/analysis/ema_area_electricity.csv` and `docs/checks/ema_electricity.md`, and the run is logged to MLflow as its own run (§10). In step 3 it is loaded as `silver.ema_area_electricity`: one row per EMA planning area with `planning_area` (Master Plan 2025 name), `ema_name`, `ema_region`, `ratio_2022`, `ratio_2023`, `ratio_2024`, `years_2022_2024`, `hot_ratio_mean`, `mean_ratio_2015_2024`, `years_2015_2024`. The table comment carries attribution notice 22 with its date of access ("Contains information from Singapore Energy Statistics 2025, Chapter 3: Energy Consumption accessed on 21 October 2026 from Energy Market Authority ..."), the footnotes and the workbook's sha256; tags `source`, `licence` and `date_of_access`.
- *Why (decision 9(b), (e), Wording rules 23 Oct 16:02):* the logged run replaces the unlogged "about 9%" and "29 areas", and the 0.05 weight matches how weak the inference is.

## 9. Tables, views and files

**Reference tables, loaded from repo files:**
- `reference/score_weights.csv` → `gold.score_weights`: `component`, `sub_index`, `weight`, `direction` (higher or inverted), `source_column`, `small_area_rule` (hdb_du, residents or none), `reason_phrase`, `review_status` ("judgement, not yet reviewed by a practitioner"). It holds the main weights only; the sensitivity variants are defined in the check and logged as MLflow parameters. `gold.area_vulnerability` reads weight, direction, rule and phrase from it, so a reload changes V.
- `reference/tier_actions.csv` → `gold.tier_actions`: `tier`, `actions`, `review_status`, `source` (Guide §14.1, decision 9).

**Silver changes:**
- `silver.block_access` gains `1room_rental` and `2room_rental` (BIGINT), joined from HDB Property Information on `blk_no` + `street`. `refuge_park_access.py` writes them, `load_refuge_park_access.py` gets their comments and a `--tables` option, and only `block_access` is reloaded. The names start with a digit, so the SQL always back-quotes them.
- `silver.ema_area_electricity` (§8).

**Views** (each `CREATE OR REPLACE VIEW` with column comments and `source` and `licence` tags; catalog as a parameter):
- `gold.area_vulnerability`, one row per rated area: names, region, residents, aged 65+ and 75+, 75+ share, confirmed HDB dwelling units, the seven raw values, their seven percentiles, `v`, `v_rank`, `third`, `reason`, `small_hdb`, `small_residents`, `electricity_missing`, `neutral_components`.
- `gold.block_vulnerability`, one row per HDB block in a rated area: area, `blk_no`, `street`, `confirmed`, dwelling units, `1room_rental`, `2room_rental`, `rental_1_2_room`, `refuge_main_m`, `refuge_main_name`, `refuge_within_400m`, `park_main_m`, `park_main_name`, `park_within_400m`, `lat`, `lon`, and `priority` within the area: 1–2 room rental flats, most first, then distance to the nearest refuge, farthest first, then `blk_no` and `street` so the order is fixed. No heat column. The 400 m flags read the stored distance (2 decimals) with `<= 400`; the build reports any block whose flag would differ from the unrounded distance the area shares used (expected none).
- `gold.area_heat_risk`, one row per area in `gold.heat_forecast` per target date: `target_date`, area, region, `station_id`, `heat_level`, `rated`, `third`, `tier`, `tier_rank`, `tier_sentence`, `reason`, `actions`, `actions_status`, `small_hdb`, `small_residents`, `forecast_missing`, `model_version`, `run_id`, `cutoff_ts`, `scored_at`. Step 3 creates it only once `gold.heat_forecast` exists, since a view cannot be created over a missing table.

**`gold.heat_forecast`, window B's table, not created here.** Fixed columns: `target_date`, `planning_area`, `station_id`, `p_low`, `p_moderate`, `p_high`, `model_version`, `run_id`, `cutoff_ts`, `scored_at`, `forecast_missing`; one row per area per target date. The types I expect: DATE, STRING, STRING, DOUBLE ×3, STRING, STRING, TIMESTAMP, TIMESTAMP, BOOLEAN. The view needs only the probabilities to be numeric and `target_date` to be a date.

**Code** (every script takes `--catalog` and `--profile`, default `coolcheck`, and `--data`):
- `src/coolcheck/risk.py`: the Python twin (percentiles, V, thirds, reason, heat level, tier, tier rank) and the three SQL builders, which take table names, so the tests can point them at temp views. `src/coolcheck/electricity.py`: the EMA ratios.
- `scripts/static/ema_electricity.py`; `scripts/static/load_risk_tables.py` (the two reference tables and the EMA table, with `--check-only`); `scripts/static/create_risk_views.py`.
- `scripts/analysis/risk_score_check.py` (the checks, in `.venv`); `scripts/analysis/log_risk_runs.py` (MLflow only, §10).
- Tests in `tests/static/` (§11).

- *Why (decision 9(e)):* views keep the logic visible in Unity Catalog and need no extra job, since the nightly risk rows update when B's forecast does. Fixing B's columns now lets B and C build at the same time.

## 10. Checks: one MLflow run

- **Store (change 1):** the trial workspace's MLflow tracking server, tracking URI `databricks://coolcheck`, experiment `/Users/<workspace user>/coolcheck-risk-score`, created if missing; its ID goes in the report. mlflow cannot go into the shared `.venv` (mlflow-skinny 2.22.0 needs protobuf below 7, and `.venv` pins 7.36.2 for Databricks Connect). So the checks compute in `.venv` and write their parameters, metrics and artifacts to `coolcheck-data/analysis/`; then `log_risk_runs.py`, which imports only mlflow, databricks-sdk and the standard library, logs them from a throwaway venv under `$env:TEMP` (mlflow-skinny 2.22.0, plus databricks-sdk if it needs it; never in `.venv`), which is then removed; the commands are in its docstring. If the throwaway venv cannot authenticate, it stops; there is no local fallback. Two runs: `electricity` (§8) and `risk_score_check`. Each logs the git SHA, whether the tree was dirty and the sha256 of every code file it ran; after the commit, the runs get a `git_commit` tag once the committed files' hashes match.
- **Inputs:** V from the same local CSVs that the Silver tables were loaded from (sha256 logged); back-test rows from `predictions_area_days.parquet`, filtered and asserted (§1). V and the thirds use today's layers on every back-test day, a stated simplification: population is June 2026 and refuges October 2026.
- **Consistency gate:** over all 41 areas, heat level High must give 1,180 area-days, 355 of them labelled High (y = 2), as in `backtest_review.md` and `coolcheck.final_check.BACKTEST_AT_CUTOFF`; the check stops if not.
- **Tier frequencies:** area-days per tier (High, Medium, Low, Not rated), overall and by season and year (`coolcheck.backtest.season_period`: SW monsoon 2025, inter-monsoon 2 2025, NE monsoon 2025/26, inter-monsoon 1 2026, SW monsoon 2026); per day, the mean and largest number of areas in High and in Medium, and the days with any High-tier area. All of it under both matrices (main, and Moderate × middle → Low).
- **Reach:** (i) residents aged 75+ in High-tier areas per day: mean, median, largest, and the total of 75+ senior-days; (ii) 75+ senior-days in area-days with tier High and an observed High label (y = 2); (iii) beside it, the same for heat level High, rated or not (§13 Q10).
- **Sensitivity runs:** equal weights; no electricity term; refuges from the clubs only; with the 2016 SACs; parks from the URA layer; with the reserves; aged 65+ in place of 75+ (§13 Q8 for the exact definitions). For each: Spearman's rho of V against the main design over the 32 areas, the areas that change third (named), and the back-test area-days that change tier (counted, by direction).
- **Report:** `docs/checks/risk_score.md`. You see the counts before any workspace load, and decide on them whether Moderate heat in a middle-third area becomes Low.

## 11. Tests

- **Percentiles:** mean rank for ties; orientation (inverted gives 1 − p when there are no ties); n shrinks for neutral areas; the endpoints are 0 and 1.
- **Neutral and small-area rules (9(g)):** DU under 1,000 gives 0.5 on exactly the two 400 m shares; residents under 1,000 on the 75+ share only; residents aged 65+ under 1,000 on refuges per 1,000 aged 65+ only; the rental count and the 75+ count keep their real values whatever the area's size; a missing EMA value gives 0.5; the flags and `neutral_components` are filled.
- **V and thirds:** the weights sum to 1; the 11/11/10 split; the tie-break; the reason rule (two components, p ≥ 0.5, neutral ones never named).
- **Heat and tier:** `p_high` exactly at the cut-off is High; `p_moderate` equal to `p_low` is Moderate; all nine cells of the matrix, "Not rated", and the variant matrix; `tier_rank` order and ties.
- **Electricity:** a year with a missing month gives no ratio; the three-year mean needs all three; the pooled ratio on a small fixture.
- **Hard rule:** a planted 2026-09-01 row makes the back-test reader fail.
- **Constant:** `HIGH_CUTOFF` equals `coolcheck.final_check.FINAL_CUTOFF`.
- **Python against SQL, through Databricks Connect** (temp views only, nothing written): `gold.area_vulnerability`'s SQL on the real 32-area inputs (from the CSVs), compared column by column with the Python (V to 1e-12, third, reason, flags); `gold.area_heat_risk`'s SQL on a temp view built from the back-test rows (filtered and asserted), compared row by row (heat level, tier, tier rank); `gold.block_vulnerability`'s priority order on the real blocks.

## 12. Steps, and what I will not do

1. This note; wait for your OK and your answers to §13.
2. Build and run locally: the electricity run, the block columns, the views' SQL tested through Connect on temp views, the checks and the report. Show the diffs, the test output and the report, then wait for your OK before committing, by path only.
3. On your word: load `silver.ema_area_electricity`, reload `silver.block_access`, load the two reference tables, then create the views, with a read-back of each.

Not here: creating `gold.heat_forecast`; reading any row dated 1 Sep to 19 Oct 2026; a deploy or bundle change; a push; showing P(High) or the score as a number anywhere.

## 13. Open points: answered 23 Oct 2026

Your answers: 1 to 8 and 10 to 12 as recommended; 9 replaced by the first reading's method (§8); 13 yes, as a second run in the workspace experiment. Q3 is now part of decision 9(g). The questions as asked:

1. **Percentile ties:** mean rank, so p = (r̄ − 1)/(n − 1) (recommended: inverting a component then mirrors it exactly, and it matches the Spearman rank used elsewhere); or SQL `percent_rank`, which gives tied areas the lowest rank, so a tie scores differently once a component is inverted.
2. **Neutral areas:** left out of the ranking, so each component is ranked among the areas with a real value (recommended: a set-aside value then cannot shift other areas' percentiles); or ranked with their raw values, then overwritten with 0.5.
3. **Refuges per 1,000 aged 65+ in tiny areas:** it is not HDB-based, so as written Changi, Downtown Core and Tanglin (0 refuges each, and the only rated areas with none) share the most vulnerable percentile on it. Recommended: 0.5 where fewer than 1,000 residents are aged 65+ (Changi 170 and Downtown Core 420; Tanglin, 4,070, keeps its value), mirroring the 75+ share rule. The alternative is the rule as written.
4. **A tie for V across a thirds boundary:** broken by residents aged 75+, more first, then by name (recommended); or both areas take the higher third, which breaks the 11/11/10 split.
5. **Reason wording:** name only components at or above the middle (p ≥ 0.5) and never a neutral one (recommended: "many residents aged 75+" stays true for a lower-third area); or always the top two, whatever their percentile.
6. **A missing forecast:** if `p_low`, `p_moderate` and `p_high` are present, the tier is computed as usual and `forecast_missing` is passed through as a flag; if any probability is null, the heat level is null and the tier is "No forecast", never Low by default (recommended). The back-test rows have probabilities on `forecast_missing` days (backtest.md's forecast fill).
7. **Order of unrated areas:** by heat level (High first), then name (recommended; they have no V, hence no score).
8. **Sensitivity definitions:** equal weights = 1/7 for each of the seven components (recommended; the other reading is 1/3 per sub-index, split equally inside it); no electricity term = the other six weights scaled by 1/0.95 (recommended; the other reading moves its 0.05 to the rental count); 65+ = residents aged 65+ and their share in place of the 75+ pair, same weights and the same residents rule.
9. **"Pooled ratio, 2015 to 2024":** months pooled over the ten years, per area and for EMA's "Overall" row, with "Overall" compared against the earlier "about 9%" (recommended); or the mean of the ten yearly ratios.
10. **Reach headline:** (ii), tier High and observed High (recommended, since a tier is what triggers an action), with (iii) beside it for context.
11. **The hard rule's reach:** it applies to dated observations (WBGT readings, labels, forecasts, predictions, `gold.heat_forecast`), not to the static layers' update stamps (recommended; otherwise R1's club file of 2 Oct 2026 and HDB's file of 8 Oct 2026 could not be used).
12. **Areas with no residents aged 65+:** the 14 others are outside the back-test's 41 areas, and I expect them outside `gold.heat_forecast` too. If B writes rows for them, they show as "Not rated" with heat level only (recommended), or the view drops them.
13. **Electricity's own run:** a second MLflow run (`electricity`) in the same local experiment (recommended), beside its report and CSV; or only the report and CSV.
