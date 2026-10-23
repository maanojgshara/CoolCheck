# Risk score and tiers: back-test tier counts, reach and sensitivity

Script: `scripts/analysis/risk_score_check.py`; rules: `src/coolcheck/risk.py` (the same rules as the SQL of the three views, compared row by row in `tests/static/test_risk_sql.py`); design: `docs/design/risk_score.md`. Artifacts: `coolcheck-data/analysis/risk_score_check/` (outside the repo). Nothing was loaded to Unity Catalog.

<!-- mlflow -->
MLflow: experiment `coolcheck-risk-score` in the trial workspace (your user folder), ID `962587213821840`; `electricity` run `d025205e33f04f97ae5370c1c770da54`; `risk_score_check` run `34289fb00d3d42298a105e910e010f7f`; logged 2026-10-23 19:37 SGT from git `05d080a` with these code files not yet committed (their sha256 are logged; a git_commit tag is added once the commit's files match).
<!-- /mlflow -->

Back-test rows: `backtest_run_c509ab9a/predictions_area_days.parquet`, read with `target_date <= 2026-08-31` and asserted: 17,438 area-days, 2025-07-01 to 2026-08-31, 427 days, 41 areas. Of these, 13,602 are in the 32 rated areas and 3,836 in the 9 not rated. The thirds use today's layers (population June 2026, refuges and parks October 2026) on every back-test day, a stated simplification.

## 1. Tier counts in the back-test months, under both matrices

Main matrix: decision 9 (Moderate heat gives Low in the lower third, Medium in the middle and upper thirds). Variant: Moderate heat in a middle-third area gives Low (decision 9(f), yours to decide). The High tier is the same under both.

| tier | main: area-days | share of rated | areas per day | days with any | most in a day | variant: area-days | share of rated | areas per day | days with any | most in a day |
|---|---|---|---|---|---|---|---|---|---|---|
| High | 566 | 4.2% | 1.33 | 168 | 14 | 566 | 4.2% | 1.33 | 168 | 14 |
| Medium | 4,773 | 35.1% | 11.18 | 346 | 23 | 2,499 | 18.4% | 5.85 | 341 | 13 |
| Low | 8,263 | 60.7% | 19.35 | 427 | 32 | 10,537 | 77.5% | 24.68 | 427 | 32 |

Not rated: 3,836 area-days (heat level only). No forecast: 0 (every back-test row has its three probabilities). 427 days; rated area-days 13,602.

Heat level by vulnerability third, rated area-days (the variant moves only the Moderate × middle cell from Medium to Low):

| heat level | lower third | middle third | upper third | all |
|---|---|---|---|---|
| High | 271 | 291 | 275 | 837 |
| Moderate | 1,734 | 2,274 | 2,228 | 6,236 |
| Low | 2,252 | 2,102 | 2,175 | 6,529 |

By season and year (rated area-days):

| season | days | rated area-days | High | Medium (main) | Low (main) | Medium (variant) | Low (variant) |
|---|---|---|---|---|---|---|---|
| SW monsoon 2025 | 92 | 2,919 | 74 | 995 | 1,850 | 530 | 2,315 |
| Inter-monsoon 2 2025 | 61 | 1,939 | 25 | 656 | 1,258 | 323 | 1,591 |
| NE monsoon 2025/26 | 90 | 2,874 | 2 | 135 | 2,737 | 72 | 2,800 |
| Inter-monsoon 1 2026 | 92 | 2,940 | 273 | 1,616 | 1,051 | 857 | 1,810 |
| SW monsoon 2026 | 92 | 2,930 | 192 | 1,371 | 1,367 | 717 | 2,021 |

## 2. Reach (residents aged 75+, June 2026; the same under both matrices)

- **Residents aged 75+ in High-tier areas per day:** mean 16,524, median 0, most 168,440; 7,055,590 senior-days over 427 days (566 High-tier area-days).
- **Headline: 75+ senior-days in areas correctly flagged High a day ahead** (tier High and an observed High day): **1,806,220** of 4,571,620 75+ senior-days on observed High days in the rated areas (39.5%); 143 of 471 observed High area-days.
- **Beside it, heat level High and an observed High day:** rated areas 2,289,060 senior-days (220 area-days); all 41 areas 2,305,210 of 4,607,600 (355 area-days, the back-test's 355 caught). The gap to the tier figure is the High-heat days in lower-third areas, which are Medium.

## 3. The vulnerability index (32 rated areas)

Weights (`reference/score_weights.csv`): aged_75_plus 0.20; share_75_plus 0.15; rental_1_2_room 0.25; electricity_hot_rise 0.05; refuge_beyond_400m 0.15; refuges_per_1000_65 0.10; park_beyond_400m 0.10. Percentiles among the rated areas with a usable value; 0.5 when missing or over a small denominator (9(g)).

| rank | planning area | third | V | reason | 75+ | 75+ share | 1–2 room rental | elec. ratio | beyond 400 m refuge | refuges /1,000 65+ | beyond 400 m park | held at 0.5 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | BEDOK | upper | 0.729 | many 1–2 room rental flats; many residents aged 75+ | 27,590 | 10.2% | 4,155 | 1.135 | 43.7% | 0.18 | 51.1% |  |
| 2 | WOODLANDS | upper | 0.681 | many 1–2 room rental flats; many residents aged 75+ | 11,700 | 4.6% | 3,817 | 1.093 | 57.6% | 0.21 | 76.6% |  |
| 3 | TAMPINES | upper | 0.678 | many residents aged 75+; many 1–2 room rental flats | 18,360 | 6.2% | 2,570 | 1.139 | 51.0% | 0.18 | 69.9% |  |
| 4 | ANG MO KIO | upper | 0.651 | many 1–2 room rental flats; many residents aged 75+ | 18,760 | 11.9% | 4,169 | 1.098 | 18.8% | 0.36 | 19.5% |  |
| 5 | BUKIT MERAH | upper | 0.624 | many 1–2 room rental flats; many residents aged 75+ | 17,300 | 12.0% | 7,933 | 1.073 | 16.1% | 0.49 | 16.3% |  |
| 6 | HOUGANG | upper | 0.617 | many residents aged 75+; many flats beyond 400 m of a refuge | 17,410 | 7.8% | 1,462 | 1.103 | 52.2% | 0.15 | 51.2% |  |
| 7 | JURONG EAST | upper | 0.603 | many flats beyond 400 m of a refuge; a high share of residents aged 75+ | 7,190 | 10.0% | 624 | 1.115 | 72.1% | 0.11 | 90.4% |  |
| 8 | KALLANG | upper | 0.598 | many 1–2 room rental flats; a high share of residents aged 75+ | 10,860 | 10.7% | 5,921 | 1.100 | 27.1% | 0.37 | 48.2% |  |
| 9 | JURONG WEST | upper | 0.595 | many residents aged 75+; many 1–2 room rental flats | 15,590 | 6.2% | 2,255 | 1.090 | 43.1% | 0.26 | 66.1% |  |
| 10 | YISHUN | upper | 0.591 | many residents aged 75+; many 1–2 room rental flats | 14,030 | 6.1% | 2,192 | 1.115 | 55.1% | 0.24 | 62.6% |  |
| 11 | TOA PAYOH | upper | 0.583 | many 1–2 room rental flats; many residents aged 75+ | 14,290 | 9.7% | 3,835 | 1.115 | 16.5% | 0.47 | 67.0% |  |
| 12 | SENGKANG | middle | 0.581 | many residents aged 75+; many 1–2 room rental flats | 12,260 | 4.6% | 1,687 | 1.094 | 54.1% | 0.16 | 59.3% |  |
| 13 | PUNGGOL | middle | 0.568 | many 1–2 room rental flats; many flats beyond 400 m of a refuge | 7,660 | 3.7% | 2,268 | 1.072 | 60.1% | 0.28 | 72.4% |  |
| 14 | QUEENSTOWN | middle | 0.553 | many 1–2 room rental flats; a high share of residents aged 75+ | 11,190 | 11.2% | 2,763 | 1.089 | 15.7% | 0.44 | 55.8% |  |
| 15 | CHOA CHU KANG | middle | 0.541 | many flats beyond 400 m of a refuge; many flats beyond 400 m of a park | 9,200 | 5.0% | 1,378 | 1.066 | 55.2% | 0.24 | 68.2% |  |
| 16 | SERANGOON | middle | 0.532 | many residents aged 75+; a high share of residents aged 75+ | 11,260 | 9.8% | 519 | 1.138 | 45.8% | 0.11 | 54.5% |  |
| 17 | GEYLANG | middle | 0.527 | many 1–2 room rental flats; many residents aged 75+ | 10,740 | 9.0% | 3,182 | 1.089 | 33.2% | 0.38 | 49.2% |  |
| 18 | BUKIT BATOK | middle | 0.523 | many 1–2 room rental flats; many residents aged 75+ | 10,540 | 6.4% | 1,703 | 1.166 | 47.7% | 0.22 | 63.9% |  |
| 19 | CLEMENTI | middle | 0.508 | a high share of residents aged 75+; many residents aged 75+ | 10,410 | 10.1% | 941 | 1.078 | 36.3% | 0.27 | 61.8% |  |
| 20 | OUTRAM | middle | 0.485 | many 1–2 room rental flats; a high share of residents aged 75+ | 2,180 | 13.2% | 2,747 | 1.057 | 39.8% | 0.43 | 0.0% |  |
| 21 | MARINE PARADE | middle | 0.474 | a high share of residents aged 75+; many flats beyond 400 m of a refuge | 5,130 | 10.7% | 1,324 | 1.102 | 51.8% | 0.19 | 2.8% |  |
| 22 | SEMBAWANG | middle | 0.459 | many 1–2 room rental flats; many flats beyond 400 m of a refuge | 4,400 | 3.8% | 1,838 | 1.088 | 59.3% | 0.21 | 44.6% |  |
| 23 | BUKIT PANJANG | lower | 0.429 | few refuges per resident aged 65+; many flats beyond 400 m of a park | 8,540 | 6.3% | 500 | 1.028 | 34.5% | 0.19 | 56.8% |  |
| 24 | ROCHOR | lower | 0.383 | many flats beyond 400 m of a refuge; a high share of residents aged 75+ | 1,250 | 10.6% | 299 | 1.101 | 59.1% | 0.36 | 30.6% |  |
| 25 | PASIR RIS | lower | 0.364 | many flats beyond 400 m of a refuge; few refuges per resident aged 65+ | 7,660 | 5.3% | 420 | 1.132 | 47.1% | 0.21 | 51.8% |  |
| 26 | TANGLIN | lower | 0.353 | few refuges per resident aged 65+ | 1,840 | 7.5% | 0 |  | 100.0% | 0.00 | 0.0% | electricity_hot_rise, refuge_beyond_400m, park_beyond_400m |
| 27 | NOVENA | lower | 0.338 | a high share of residents aged 75+; many flats beyond 400 m of a park | 4,470 | 8.6% | 756 | 1.093 | 24.1% | 0.41 | 60.9% |  |
| 28 | BISHAN | lower | 0.330 | a high share of residents aged 75+ | 8,280 | 9.5% | 408 | 1.156 | 38.5% | 0.30 | 24.4% |  |
| 29 | BUKIT TIMAH | lower | 0.304 | few refuges per resident aged 65+; a high share of residents aged 75+ | 7,390 | 8.6% | 0 | 1.115 | 28.3% | 0.13 | 16.3% |  |
| 30 | CHANGI | lower | 0.287 | no component above the middle of the rated areas | 60 | 9.1% | 0 |  | 100.0% | 0.00 | 0.0% | share_75_plus, electricity_hot_rise, refuge_beyond_400m, refuges_per_1000_65, park_beyond_400m |
| 31 | TENGAH | lower | 0.285 | many flats beyond 400 m of a refuge; many flats beyond 400 m of a park | 680 | 2.0% | 82 |  | 63.9% | 0.38 | 55.2% | electricity_hot_rise |
| 32 | DOWNTOWN CORE | lower | 0.224 | no component above the middle of the rated areas | 140 | 2.5% | 0 |  | 100.0% | 0.00 | 0.0% | electricity_hot_rise, refuge_beyond_400m, refuges_per_1000_65, park_beyond_400m |

Held at 0.5: CHANGI: share_75_plus (fewer than 1,000 residents); electricity_hot_rise (no value); refuge_beyond_400m (fewer than 1,000 confirmed HDB dwelling units); refuges_per_1000_65 (fewer than 1,000 residents aged 65+); park_beyond_400m (fewer than 1,000 confirmed HDB dwelling units); DOWNTOWN CORE: electricity_hot_rise (no value); refuge_beyond_400m (fewer than 1,000 confirmed HDB dwelling units); refuges_per_1000_65 (fewer than 1,000 residents aged 65+); park_beyond_400m (fewer than 1,000 confirmed HDB dwelling units); TANGLIN: electricity_hot_rise (no value); refuge_beyond_400m (fewer than 1,000 confirmed HDB dwelling units); park_beyond_400m (fewer than 1,000 confirmed HDB dwelling units); TENGAH: electricity_hot_rise (no value).

## 4. Sensitivity runs

Each against the main design: Spearman's rho of V over the 32 areas, the areas that change third, and the back-test's rated area-days that change tier (up = more severe), under each matrix. Under the main matrix the middle and upper thirds give the same tier, so only a move across the lower-third boundary (ranks 22 and 23) changes a tier; under the variant, Moderate heat separates the middle third from the upper too.

| run | what changes | Spearman rho | areas changing third | main: up / down | variant: up / down |
|---|---|---|---|---|---|
| equal_weights | each of the seven components weighted 1/7 | 0.900 | 10: BUKIT MERAH upper→middle, BUKIT PANJANG lower→middle, CHOA CHU KANG middle→upper, CLEMENTI middle→upper, KALLANG upper→middle, MARINE PARADE middle→lower, PUNGGOL middle→upper, SENGKANG middle→upper, TOA PAYOH upper→middle, YISHUN upper→middle | 189 / 288 | 749 / 804 |
| no_electricity | electricity dropped; the other six weights scaled by 1/0.95 | 0.990 | 0 | 0 / 0 | 0 / 0 |
| refuges_clubs_only | both refuge components from the clubs-only set | 0.888 | 6: CLEMENTI middle→upper, JURONG WEST upper→middle, KALLANG upper→middle, MARINE PARADE middle→lower, QUEENSTOWN middle→upper, ROCHOR lower→middle | 251 / 288 | 359 / 484 |
| refuges_with_sac_2016 | both refuge components with the 2016 SACs added | 0.976 | 6: BUKIT PANJANG lower→middle, JURONG EAST upper→middle, KALLANG upper→middle, OUTRAM middle→lower, PUNGGOL middle→upper, QUEENSTOWN middle→upper | 189 / 251 | 427 / 427 |
| parks_ura | the park component from the URA layer | 0.915 | 4: JURONG EAST upper→middle, SENGKANG middle→upper, SERANGOON middle→upper, TOA PAYOH upper→middle | 0 / 0 | 335 / 266 |
| parks_with_reserves | the park component with the reserves in | 1.000 | 0 | 0 / 0 | 0 / 0 |
| aged_65 | the 65+ count and share in place of the 75+ pair, same weights and residents rule | 0.967 | 6: BUKIT PANJANG lower→middle, CHOA CHU KANG middle→upper, KALLANG upper→middle, MARINE PARADE middle→lower, SENGKANG middle→upper, TOA PAYOH upper→middle | 189 / 288 | 406 / 392 |

## 5. Checks

- **Hard rule:** the back-test rows were read with `target_date <= 2026-08-31` (pyarrow filter) and asserted after the read; the latest date read is 2026-08-31. Nothing else read here is a dated observation.
- **Consistency with the back-test:** over all 41 areas the heat level gives 1,180 High area-days, 355 of them observed High, of 710 observed High, over 427 days, as in `backtest_review.md` (1,180, 355, 710, 427).
- **Weights:** 7 components summing to 1.00; thirds 11 / 11 / 10.
- **400 m flags:** blocks whose stored distance (2 decimals) to the nearest refuge or park lies within 0.01 m of 400 m: 0, so the flags `gold.block_vulnerability` reads from the stored distance cannot differ from the unrounded distance the area shares used.
- **SQL against Python:** the views' SQL is compared with these rules on the same rows in `tests/static/test_risk_sql.py` (Databricks Connect, temp views only).

## 6. Limits

- The weights are a judgement (decision 9(b)), not fitted: there is no open outcome data to fit them to. Section 4 shows how much they matter. They are not yet reviewed by a practitioner, nor are the actions.
- The AAC layer is partial (93 of about 223), so the refuge components overstate the gap where AACs are missing; `refuges_with_sac_2016` bounds the effect.
- The electricity term is weak (a smaller rise may indicate less air-con use, no more) and missing for 4 rated areas.
- Back-test tiers apply today's vulnerability thirds to every day from July 2025.
