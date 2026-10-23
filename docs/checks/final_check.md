# Final check report

Generated 2026-10-23 20:51 SGT by `src/jobs/final_check.py` (bundle job, stage score). MLflow run `8d7e969d569440b4addedde0978e83a6` (role = final_check) in experiment `/Users/<user>/[dev <user>] coolcheck-backtest`. Git `353c13930f60edf1674337d13ac61b5f993a4609`, code sha256 `2811d2cd7ce41d7d9c40d8edec2408bd0a785311c01f04535e93d86d362e61ad`, run date 2026-10-23 (SGT), cut-off 15 min after 00:00 on the target date. Specification: docs/design/backtest.md §15, decided 22 Oct 2026 before any final-check data was read. This report states numbers; the reading pre-declared in §15 is applied mechanically.

Packages this run used: python 3.12.3, pandas 2.2.3, numpy 2.1.3, scikit-learn 1.6.1, lightgbm 4.6.0, mlflow 2.22.0, scipy 1.15.1, pyarrow 19.0.1.

## Pre-declared reading (§15)

The final check agrees with the back-test if the model's area-day PR-AUC is above persistence's (continuous score).

Area-day PR-AUC over 1 Sep to 19 Oct 2026: model 0.489, persistence (continuous) 0.360. Model above persistence: yes. The final check agrees with the back-test.

## The cut-off beside the back-test (§15 item 5)

Area-days, alert when P(High) ≥ 0.10975585695894975:

- 1 Sep to 19 Oct: 176 alerts over 49 days, 3.59 a day; recall 0.792, 61 of 77 High area-days.
- Sep: 100 alerts over 30 days, 3.33 a day; recall 0.800, 48 of 60 High area-days.
- Oct (1 to 19): 76 alerts over 19 days, 4.00 a day; recall 0.765, 13 of 17 High area-days.
- Back-test (Jul 2025 to Aug 2026, §14): 1,180 alerts over 427 days, 2.76 a day; recall 0.500, 355 of 710 High area-days.

## Settings

- Model: LightGBM multiclass on the 11 features (wbgt_peak_d1, wbgt_peak_mean_7d, station_char_30d, n_high_d1, panel_peak_mean_d1, panel_high_count_d1, fc_temp_high, fc_text, rain_d1_mm, month, season), num_leaves 7, 150 rounds, the fixed parameters of §5.2 (`{"objective": "multiclass", "num_class": 3, "learning_rate": 0.05, "min_data_in_leaf": 40, "lambda_l2": 1.0, "feature_fraction": 0.9, "bagging_fraction": 0.8, "bagging_freq": 1, "max_bin": 63, "min_data_per_group": 50, "cat_smooth": 10, "seed": 42, "deterministic": true, "force_row_wise": true, "num_threads": 4, "verbose": -1}`); model sha256 `d614c3bc959ad16781158acf8fa2aa5114be4043305244fbe4674435750f1f64`.
- Trained once on target dates 2025-01-17 to 2026-08-31: 9,308 station-days, 465 High (§15 item 1: 9,308 and 465); no refit.
- Fitted on the training rows only: forecast fill by calendar month 1: 33.0 °C, Thundery Showers; 2: 33.0 °C, Thundery Showers; 3: 34.0 °C, Thundery Showers; 4: 34.0 °C, Thundery Showers; 5: 34.0 °C, Thundery Showers; 6: 34.0 °C, Thundery Showers; 7: 34.0 °C, Thundery Showers; 8: 34.0 °C, Thundery Showers; 9: 33.0 °C, Thundery Showers; 10: 33.0 °C, Thundery Showers; 11: 33.0 °C, Thundery Showers; 12: 33.0 °C, Thundery Showers; all training dates: 34.0 °C, Thundery Showers. Text categories: 12. NEA rule θ = 34.0 °C (training F1 0.120). Same month last year from the labels of Sep and Oct 2025.
- Latest target date each fitted object used: forecast fill 2026-08-31; text categories 2026-08-31; LightGBM model 2026-08-31; NEA rule threshold 2026-08-31; same month last year (labels) 2026-08-31.
- Scored: target dates 2026-09-01 to 2026-10-19, 49 days (Sep 30, Oct 19).

## How to read the numbers

- Wilson 95% intervals are given on station-day counts only, and they are too narrow: consecutive days are not independent.
- Area-day counts have no intervals, since area-days share stations.
- No difference between the model and a baseline is claimed from the final check alone: the 49 days make only 7 weekly blocks, too few for the block bootstrap.
- The baselines have no P(High), so "at the cut-off" is the model's alone. Continuous scores are also shown at persistence's alert load (the whole window's load, split by month); the binary rules at their own rule. A tie at the load is split in expectation, so some counts are not whole numbers.

## Inputs (pinned)

| phase | input | type | pinned | filter |
|---|---|---|---|---|
| both | coolcheck.silver.area_station_distance | Delta table | Delta version 3 | boundary mp2025 in the SQL |
| both | coolcheck.silver.area_exposure | Delta table | Delta version 1; 41 areas | aged_65_plus > 0 |
| both | coolcheck.gold.area_nearest_station_daily | view | definition sha256 bddb8f5cb9a97ed97fde7a3dd3c81b92530df8c5fcb44c787958357481a009d8 | definition only |
| training | coolcheck.silver.wbgt_readings | streaming table | Delta version 11; rows 895,135; checksum 416625100565876409 | sgt_date <= DATE'2026-08-31' AND sgt_date < DATE'2026-10-23' |
| training | coolcheck.silver.rainfall_readings | streaming table | Delta version 10; rows 10,644,768; checksum -8701651613798288135 | sgt_date <= DATE'2026-08-31' AND sgt_date < DATE'2026-10-23' |
| training | coolcheck.silver.forecast_issues | streaming table | Delta version 12; rows 4,324; checksum -1603625231816017810 | issue_sgt_date <= DATE'2026-08-31' |
| training | coolcheck.silver.station_daily_label | materialized view | pulled once; rows 9,367; sha256 b95fcee4e5a49b7fb1b37dc9c6f5cbfb881a68244cd8a0cfffc768d55bddaf20 | sgt_date <= DATE'2026-08-31' AND sgt_date < DATE'2026-10-23' |
| scoring | coolcheck.silver.wbgt_readings | streaming table | Delta version 11; rows 1,036,005; checksum 6099213691760387355 | sgt_date <= DATE'2026-10-19' AND sgt_date < DATE'2026-10-23' |
| scoring | coolcheck.silver.rainfall_readings | streaming table | Delta version 10; rows 11,893,198; checksum 4571681704683401155 | sgt_date <= DATE'2026-10-19' AND sgt_date < DATE'2026-10-23' |
| scoring | coolcheck.silver.forecast_issues | streaming table | Delta version 12; rows 4,673; checksum -9149434083322239040 | issue_sgt_date <= DATE'2026-10-19' |
| scoring | coolcheck.silver.station_daily_label | materialized view | pulled once; rows 1,469; sha256 35c1da2df5a617af45d74a85c4868cf802fb9a89016969ef83f2047dda8e792f | sgt_date BETWEEN DATE'2026-09-01' AND DATE'2026-10-19' AND sgt_date < DATE'2026-10-23' |

View `coolcheck.gold.area_nearest_station_daily`: definition equals `nearest_station_sql(..., island_rule=True)`: True; the job ran that SQL on the pinned copies.

### Window audit

| phase | frame | column | rows | first | last |
|---|---|---|---|---|---|
| training | labels (pinned) | sgt_date | 9,367 | 2025-01-16 | 2026-08-31 |
| training | features | target_date | 9,350 | 2025-01-17 | 2026-08-31 |
| training | labels (usable) | target_date | 9,309 | 2025-01-17 | 2026-08-31 |
| training | area mapping | target_date | 32,560 | 2025-01-17 | 2026-08-31 |
| training | station-day rows | target_date | 9,308 | 2025-01-17 | 2026-08-31 |
| scoring | labels (pulled) | sgt_date | 1,469 | 2026-09-01 | 2026-10-19 |
| scoring | features | target_date | 1,470 | 2026-09-01 | 2026-10-19 |
| scoring | labels (usable) | target_date | 1,463 | 2026-09-01 | 2026-10-19 |
| scoring | area mapping | target_date | 2,695 | 2026-09-01 | 2026-10-19 |
| scoring | station-day rows | target_date | 1,463 | 2026-09-01 | 2026-10-19 |
| scoring | predictions | target_date | 1,463 | 2026-09-01 | 2026-10-19 |
| scoring | area-days | target_date | 1,998 | 2026-09-01 | 2026-10-19 |

## Rows

Scoring station-days (reporting station, usable label): 1,463. Usable station-days without a feature row: 0. Area-days over the 41 areas: 1,998; dropped because their station-day is not usable: 11. Rows whose forecast text was not seen in training (scored as missing): 0. Selected forecasts whose text disagrees with the corrected validity: 0.

### Forecasts filled in the scoring window (rule: §5.1 step 2), with why each was missing

None.

## Area-days over the 41 areas with residents aged 65+

Rows 1,998; High 77 (3.9%, the no-skill PR-AUC); persistence alerts K = 75.

| score | PR-AUC |
|---|---|
| model | 0.489 |
| persistence (continuous) | 0.360 |
| NEA rule | 0.036 |
| same month last year | 0.302 |

| method | operating point | period | High days caught | recall | alerts | precision | alerts per day |
|---|---|---|---|---|---|---|---|
| model | at the cut-off | 1 Sep to 19 Oct | 61 of 77 High days | 0.792 | 176 | 0.347 | 3.59 |
| model | at persistence's alert load | 1 Sep to 19 Oct | 35 of 77 High days | 0.455 | 75 | 0.467 | 1.53 |
| persistence (binary) | own rule (yesterday High) | 1 Sep to 19 Oct | 32 of 77 High days | 0.416 | 75 | 0.427 | 1.53 |
| persistence (continuous) | at persistence's alert load | 1 Sep to 19 Oct | 32 of 77 High days | 0.416 | 75 | 0.427 | 1.53 |
| NEA rule | own rule (forecast ≥ θ) | 1 Sep to 19 Oct | 58 of 77 High days | 0.753 | 1,754 | 0.033 | 35.80 |
| NEA rule | at persistence's alert load | 1 Sep to 19 Oct | 3.1 of 77 High days | 0.041 | 75.0 | 0.042 | 1.53 |
| same month last year | at persistence's alert load | 1 Sep to 19 Oct | 33.6 of 77 High days | 0.436 | 75 | 0.448 | 1.53 |
| model | at the cut-off | Sep | 48 of 60 High days | 0.800 | 100 | 0.480 | 3.33 |
| model | at persistence's alert load | Sep | 27 of 60 High days | 0.450 | 55 | 0.491 | 1.83 |
| persistence (binary) | own rule (yesterday High) | Sep | 25 of 60 High days | 0.417 | 51 | 0.490 | 1.70 |
| persistence (continuous) | at persistence's alert load | Sep | 25 of 60 High days | 0.417 | 51 | 0.490 | 1.70 |
| NEA rule | own rule (forecast ≥ θ) | Sep | 41 of 60 High days | 0.683 | 975 | 0.042 | 32.50 |
| NEA rule | at persistence's alert load | Sep | 2.6 of 60 High days | 0.043 | 52.2 | 0.050 | 1.74 |
| same month last year | at persistence's alert load | Sep | 21.6 of 60 High days | 0.360 | 56 | 0.386 | 1.87 |
| model | at the cut-off | Oct (1 to 19) | 13 of 17 High days | 0.765 | 76 | 0.171 | 4.00 |
| model | at persistence's alert load | Oct (1 to 19) | 8 of 17 High days | 0.471 | 20 | 0.400 | 1.05 |
| persistence (binary) | own rule (yesterday High) | Oct (1 to 19) | 7 of 17 High days | 0.412 | 24 | 0.292 | 1.26 |
| persistence (continuous) | at persistence's alert load | Oct (1 to 19) | 7 of 17 High days | 0.412 | 24 | 0.292 | 1.26 |
| NEA rule | own rule (forecast ≥ θ) | Oct (1 to 19) | 17 of 17 High days | 1.000 | 779 | 0.022 | 41.00 |
| NEA rule | at persistence's alert load | Oct (1 to 19) | 0.6 of 17 High days | 0.033 | 22.8 | 0.024 | 1.20 |
| same month last year | at persistence's alert load | Oct (1 to 19) | 12 of 17 High days | 0.706 | 19 | 0.632 | 1.00 |

## Station-days: all stations

Rows 1,463; High 70 (4.8%, the no-skill PR-AUC); persistence alerts K = 67.

| score | PR-AUC |
|---|---|
| model | 0.501 |
| persistence (continuous) | 0.361 |
| NEA rule | 0.043 |
| same month last year | 0.324 |

| method | operating point | period | High days caught | recall (Wilson 95%) | alerts | precision (Wilson 95%) | alerts per day |
|---|---|---|---|---|---|---|---|
| model | at the cut-off | 1 Sep to 19 Oct | 52 of 70 High days | 0.743 (0.630 to 0.831) | 136 | 0.382 (0.305 to 0.466) | 2.78 |
| model | at persistence's alert load | 1 Sep to 19 Oct | 36 of 70 High days | 0.514 (0.400 to 0.628) | 67 | 0.537 (0.419 to 0.651) | 1.37 |
| persistence (binary) | own rule (yesterday High) | 1 Sep to 19 Oct | 29 of 70 High days | 0.414 (0.306 to 0.531) | 67 | 0.433 (0.321 to 0.552) | 1.37 |
| persistence (continuous) | at persistence's alert load | 1 Sep to 19 Oct | 29 of 70 High days | 0.414 (0.306 to 0.531) | 67 | 0.433 (0.321 to 0.552) | 1.37 |
| NEA rule | own rule (forecast ≥ θ) | 1 Sep to 19 Oct | 53 of 70 High days | 0.757 (0.645 to 0.842) | 1,284 | 0.041 (0.032 to 0.054) | 26.20 |
| NEA rule | at persistence's alert load | 1 Sep to 19 Oct | 2.7 of 70 High days | 0.039 (0.013 to 0.113) | 67 | 0.041 (0.013 to 0.118) | 1.37 |
| same month last year | at persistence's alert load | 1 Sep to 19 Oct | 31 of 70 High days | 0.443 (0.332 to 0.559) | 67 | 0.463 (0.349 to 0.581) | 1.37 |
| model | at the cut-off | Sep | 37 of 49 High days | 0.755 (0.619 to 0.854) | 71 | 0.521 (0.407 to 0.633) | 2.37 |
| model | at persistence's alert load | Sep | 26 of 49 High days | 0.531 (0.394 to 0.663) | 47 | 0.553 (0.412 to 0.686) | 1.57 |
| persistence (binary) | own rule (yesterday High) | Sep | 21 of 49 High days | 0.429 (0.300 to 0.567) | 42 | 0.500 (0.355 to 0.645) | 1.40 |
| persistence (continuous) | at persistence's alert load | Sep | 21 of 49 High days | 0.429 (0.300 to 0.567) | 42 | 0.500 (0.355 to 0.645) | 1.40 |
| NEA rule | own rule (forecast ≥ θ) | Sep | 32 of 49 High days | 0.653 (0.513 to 0.771) | 714 | 0.045 (0.032 to 0.063) | 23.80 |
| NEA rule | at persistence's alert load | Sep | 2.0 of 49 High days | 0.042 (0.012 to 0.138) | 46.6 | 0.044 (0.012 to 0.145) | 1.55 |
| same month last year | at persistence's alert load | Sep | 19 of 49 High days | 0.388 (0.264 to 0.528) | 30 | 0.633 (0.455 to 0.781) | 1.00 |
| model | at the cut-off | Oct (1 to 19) | 15 of 21 High days | 0.714 (0.500 to 0.862) | 65 | 0.231 (0.145 to 0.346) | 3.42 |
| model | at persistence's alert load | Oct (1 to 19) | 10 of 21 High days | 0.476 (0.283 to 0.676) | 20 | 0.500 (0.299 to 0.701) | 1.05 |
| persistence (binary) | own rule (yesterday High) | Oct (1 to 19) | 8 of 21 High days | 0.381 (0.208 to 0.591) | 25 | 0.320 (0.172 to 0.516) | 1.32 |
| persistence (continuous) | at persistence's alert load | Oct (1 to 19) | 8 of 21 High days | 0.381 (0.208 to 0.591) | 25 | 0.320 (0.172 to 0.516) | 1.32 |
| NEA rule | own rule (forecast ≥ θ) | Oct (1 to 19) | 21 of 21 High days | 1.000 (0.845 to 1.000) | 570 | 0.037 (0.024 to 0.056) | 30.00 |
| NEA rule | at persistence's alert load | Oct (1 to 19) | 0.7 of 21 High days | 0.032 (0.004 to 0.205) | 20.4 | 0.033 (0.004 to 0.210) | 1.07 |
| same month last year | at persistence's alert load | Oct (1 to 19) | 12 of 21 High days | 0.571 (0.365 to 0.755) | 37 | 0.324 (0.196 to 0.485) | 1.95 |

## Station-days: without S142, S137 and S135

Rows 1,316; High 31 (2.4%, the no-skill PR-AUC); persistence alerts K = 29.

| score | PR-AUC |
|---|---|
| model | 0.279 |
| persistence (continuous) | 0.244 |
| NEA rule | 0.020 |
| same month last year | 0.029 |

| method | operating point | period | High days caught | recall (Wilson 95%) | alerts | precision (Wilson 95%) | alerts per day |
|---|---|---|---|---|---|---|---|
| model | at the cut-off | 1 Sep to 19 Oct | 19 of 31 High days | 0.613 (0.438 to 0.763) | 74 | 0.257 (0.171 to 0.367) | 1.51 |
| model | at persistence's alert load | 1 Sep to 19 Oct | 11 of 31 High days | 0.355 (0.211 to 0.531) | 29 | 0.379 (0.227 to 0.560) | 0.59 |
| persistence (binary) | own rule (yesterday High) | 1 Sep to 19 Oct | 11 of 31 High days | 0.355 (0.211 to 0.531) | 29 | 0.379 (0.227 to 0.560) | 0.59 |
| persistence (continuous) | at persistence's alert load | 1 Sep to 19 Oct | 11 of 31 High days | 0.355 (0.211 to 0.531) | 29 | 0.379 (0.227 to 0.560) | 0.59 |
| NEA rule | own rule (forecast ≥ θ) | 1 Sep to 19 Oct | 21 of 31 High days | 0.677 (0.501 to 0.814) | 1,155 | 0.018 (0.012 to 0.028) | 23.57 |
| NEA rule | at persistence's alert load | 1 Sep to 19 Oct | 0.5 of 31 High days | 0.018 (0.002 to 0.140) | 29 | 0.019 (0.002 to 0.148) | 0.59 |
| same month last year | at persistence's alert load | 1 Sep to 19 Oct | 2.9 of 31 High days | 0.094 (0.032 to 0.245) | 29.0 | 0.100 (0.034 to 0.260) | 0.59 |
| model | at the cut-off | Sep | 17 of 26 High days | 0.654 (0.462 to 0.806) | 38 | 0.447 (0.301 to 0.603) | 1.27 |
| model | at persistence's alert load | Sep | 11 of 26 High days | 0.423 (0.255 to 0.611) | 24 | 0.458 (0.279 to 0.649) | 0.80 |
| persistence (binary) | own rule (yesterday High) | Sep | 10 of 26 High days | 0.385 (0.224 to 0.575) | 21 | 0.476 (0.283 to 0.676) | 0.70 |
| persistence (continuous) | at persistence's alert load | Sep | 10 of 26 High days | 0.385 (0.224 to 0.575) | 21 | 0.476 (0.283 to 0.676) | 0.70 |
| NEA rule | own rule (forecast ≥ θ) | Sep | 16 of 26 High days | 0.615 (0.425 to 0.776) | 642 | 0.025 (0.015 to 0.040) | 21.40 |
| NEA rule | at persistence's alert load | Sep | 0.5 of 26 High days | 0.021 (0.002 to 0.163) | 20.2 | 0.027 (0.003 to 0.202) | 0.67 |
| same month last year | at persistence's alert load | Sep | 2.9 of 26 High days | 0.112 (0.038 to 0.285) | 29 | 0.100 (0.034 to 0.260) | 0.97 |
| model | at the cut-off | Oct (1 to 19) | 2 of 5 High days | 0.400 (0.118 to 0.769) | 36 | 0.056 (0.015 to 0.181) | 1.89 |
| model | at persistence's alert load | Oct (1 to 19) | 0 of 5 High days | 0.000 (0.000 to 0.434) | 5 | 0.000 (0.000 to 0.434) | 0.26 |
| persistence (binary) | own rule (yesterday High) | Oct (1 to 19) | 1 of 5 High days | 0.200 (0.036 to 0.624) | 8 | 0.125 (0.022 to 0.471) | 0.42 |
| persistence (continuous) | at persistence's alert load | Oct (1 to 19) | 1 of 5 High days | 0.200 (0.036 to 0.624) | 8 | 0.125 (0.022 to 0.471) | 0.42 |
| NEA rule | own rule (forecast ≥ θ) | Oct (1 to 19) | 5 of 5 High days | 1.000 (0.566 to 1.000) | 513 | 0.010 (0.004 to 0.023) | 27.00 |
| NEA rule | at persistence's alert load | Oct (1 to 19) | 0 of 5 High days | 0.000 (0.000 to 0.434) | 8.8 | 0.000 (0.000 to 0.303) | 0.46 |
| same month last year | at persistence's alert load | Oct (1 to 19) | 0 of 5 High days | 0.000 (0.000 to 0.434) | 0 | — | 0.00 |

## Station-days: the original 8 (7 after S130 stopped)

Rows 339; High 16 (4.7%, the no-skill PR-AUC); persistence alerts K = 15.

| score | PR-AUC |
|---|---|
| model | 0.357 |
| persistence (continuous) | 0.262 |
| NEA rule | 0.042 |
| same month last year | 0.045 |

| method | operating point | period | High days caught | recall (Wilson 95%) | alerts | precision (Wilson 95%) | alerts per day |
|---|---|---|---|---|---|---|---|
| model | at the cut-off | 1 Sep to 19 Oct | 13 of 16 High days | 0.812 (0.570 to 0.934) | 53 | 0.245 (0.149 to 0.376) | 1.08 |
| model | at persistence's alert load | 1 Sep to 19 Oct | 6 of 16 High days | 0.375 (0.185 to 0.614) | 15 | 0.400 (0.198 to 0.643) | 0.31 |
| persistence (binary) | own rule (yesterday High) | 1 Sep to 19 Oct | 5 of 16 High days | 0.312 (0.142 to 0.556) | 15 | 0.333 (0.152 to 0.583) | 0.31 |
| persistence (continuous) | at persistence's alert load | 1 Sep to 19 Oct | 5 of 16 High days | 0.312 (0.142 to 0.556) | 15 | 0.333 (0.152 to 0.583) | 0.31 |
| NEA rule | own rule (forecast ≥ θ) | 1 Sep to 19 Oct | 11 of 16 High days | 0.688 (0.444 to 0.858) | 297 | 0.037 (0.021 to 0.065) | 6.06 |
| NEA rule | at persistence's alert load | 1 Sep to 19 Oct | 0.7 of 16 High days | 0.042 (0.006 to 0.256) | 15 | 0.045 (0.006 to 0.269) | 0.31 |
| same month last year | at persistence's alert load | 1 Sep to 19 Oct | 0 of 16 High days | 0.000 (0.000 to 0.194) | 15.0 | 0.000 (0.000 to 0.204) | 0.31 |
| model | at the cut-off | Sep | 13 of 15 High days | 0.867 (0.621 to 0.963) | 31 | 0.419 (0.264 to 0.592) | 1.03 |
| model | at persistence's alert load | Sep | 6 of 15 High days | 0.400 (0.198 to 0.643) | 12 | 0.500 (0.254 to 0.746) | 0.40 |
| persistence (binary) | own rule (yesterday High) | Sep | 5 of 15 High days | 0.333 (0.152 to 0.583) | 13 | 0.385 (0.177 to 0.645) | 0.43 |
| persistence (continuous) | at persistence's alert load | Sep | 5 of 15 High days | 0.333 (0.152 to 0.583) | 13 | 0.385 (0.177 to 0.645) | 0.43 |
| NEA rule | own rule (forecast ≥ θ) | Sep | 10 of 15 High days | 0.667 (0.417 to 0.848) | 164 | 0.061 (0.033 to 0.109) | 5.47 |
| NEA rule | at persistence's alert load | Sep | 0.7 of 15 High days | 0.045 (0.006 to 0.269) | 10.3 | 0.065 (0.009 to 0.358) | 0.34 |
| same month last year | at persistence's alert load | Sep | 0 of 15 High days | 0.000 (0.000 to 0.204) | 0 | — | 0.00 |
| model | at the cut-off | Oct (1 to 19) | 0 of 1 High days | 0.000 (0.000 to 0.793) | 22 | 0.000 (0.000 to 0.149) | 1.16 |
| model | at persistence's alert load | Oct (1 to 19) | 0 of 1 High days | 0.000 (0.000 to 0.793) | 3 | 0.000 (0.000 to 0.561) | 0.16 |
| persistence (binary) | own rule (yesterday High) | Oct (1 to 19) | 0 of 1 High days | 0.000 (0.000 to 0.793) | 2 | 0.000 (0.000 to 0.658) | 0.11 |
| persistence (continuous) | at persistence's alert load | Oct (1 to 19) | 0 of 1 High days | 0.000 (0.000 to 0.793) | 2 | 0.000 (0.000 to 0.658) | 0.11 |
| NEA rule | own rule (forecast ≥ θ) | Oct (1 to 19) | 1 of 1 High days | 1.000 (0.207 to 1.000) | 133 | 0.008 (0.001 to 0.041) | 7.00 |
| NEA rule | at persistence's alert load | Oct (1 to 19) | 0 of 1 High days | 0.000 (0.000 to 0.793) | 4.7 | 0.000 (0.000 to 0.450) | 0.25 |
| same month last year | at persistence's alert load | Oct (1 to 19) | 0 of 1 High days | 0.000 (0.000 to 0.793) | 15 | 0.000 (0.000 to 0.204) | 0.79 |

