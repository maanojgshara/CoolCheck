# Rolling back-test report

Generated 2026-10-22 20:25 SGT by `src/jobs/backtest.py` (bundle job). Git `678a5d8d6ffdc7e43adec5a2320ff851c4fca7ce`, code sha256 `a3c87a8814b7b4ac…`, run date 2026-10-22 (SGT), cut-off 15 min after 00:00 on the target date, folds 2025-07 to 2026-08, 2,000 block resamples, seed 42. This report states numbers; it does not interpret them. Nothing was read, fitted or scored after 2026-08-31.

Packages this run used: python 3.12.3, pandas 2.2.3, numpy 2.1.3, scikit-learn 1.6.1, lightgbm 4.6.0, mlflow 2.22.0, scipy 1.15.1, pyarrow 19.0.1.

## Inputs (pinned)

| input | type | pinned | filter |
|---|---|---|---|
| coolcheck.silver.wbgt_readings | streaming table | Delta version 6; rows 895,135; checksum 416625100565876409 | sgt_date <= DATE'2026-08-31' AND sgt_date < DATE'2026-10-22' |
| coolcheck.silver.rainfall_readings | streaming table | Delta version 6; rows 10,644,768; checksum -8701651613798288135 | sgt_date <= DATE'2026-08-31' AND sgt_date < DATE'2026-10-22' |
| coolcheck.silver.forecast_issues | streaming table | Delta version 9; rows 4,324; checksum -1603625231816017810 | issue_sgt_date <= DATE'2026-08-31' |
| coolcheck.silver.station_daily_label | materialized view | pulled once; rows 9,367; sha256 b95fcee4e5a49b7fb1b37dc9c6f5cbfb881a68244cd8a0cfffc768d55bddaf20 | sgt_date <= DATE'2026-08-31' AND sgt_date < DATE'2026-10-22' |
| coolcheck.silver.area_station_distance | Delta table | Delta version 3 | boundary mp2025 in the SQL |
| coolcheck.silver.area_exposure | Delta table | Delta version 1; 41 areas | aged_65_plus > 0 |
| coolcheck.gold.area_nearest_station_daily | view | definition sha256 bddb8f5cb9a97ed97fde7a3dd3c81b92530df8c5fcb44c787958357481a009d8 | definition only |

View `coolcheck.gold.area_nearest_station_daily`: definition equals `nearest_station_sql(..., island_rule=True)`: True; the job ran that SQL on the pinned copies (definition sha256 `bddb8f5cb9a97ed9…`).

### Window audit

| frame | column | rows | first | last |
|---|---|---|---|---|
| labels (pinned) | sgt_date | 9,367 | 2025-01-16 | 2026-08-31 |
| features | target_date | 9,350 | 2025-01-17 | 2026-08-31 |
| labels (usable) | target_date | 9,309 | 2025-01-17 | 2026-08-31 |
| area mapping | target_date | 32,560 | 2025-01-17 | 2026-08-31 |
| pooled predictions | target_date | 8,001 | 2025-07-01 | 2026-08-31 |
| area-days | target_date | 17,438 | 2025-07-01 | 2026-08-31 |

## Rows

Station-day rows (reporting station, usable label): 9,308. Usable station-days without a feature row (a station's first day, or first day back): 1. Test area-days over the 41 areas: 17,438; dropped because their station-day is not usable: 69.

| fold | train_rows | train_high | train_last_date | test_rows | test_high | config | num_leaves | rounds | test_pr_auc | nea_theta | unseen_text_rows | filled_test_dates |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2025-07-01 | 1,307 | 44 | 2025-06-30 | 268 | 12 | 0 | 7 | 150 | 0.323 | 35 | 0 | 1 |
| 2025-08-01 | 1,575 | 56 | 2025-07-31 | 279 | 2 | 1 | 15 | 150 | 0.041 | 35 | 0 | 0 |
| 2025-09-01 | 1,854 | 58 | 2025-08-31 | 439 | 25 | 3 | 15 | 400 | 0.233 | 35 | 15 | 0 |
| 2025-10-01 | 2,293 | 83 | 2025-09-30 | 461 | 32 | 2 | 7 | 400 | 0.492 | 35 | 14 | 0 |
| 2025-11-01 | 2,754 | 115 | 2025-10-31 | 448 | 18 | 0 | 7 | 150 | 0.228 | 35 | 15 | 0 |
| 2025-12-01 | 3,202 | 133 | 2025-11-30 | 465 | 5 | 0 | 7 | 150 | 0.097 | 35 | 0 | 0 |
| 2026-01-01 | 3,667 | 138 | 2025-12-31 | 545 | 0 | 0 | 7 | 150 | — | 35 | 0 | 0 |
| 2026-02-01 | 4,212 | 138 | 2026-01-31 | 557 | 3 | 0 | 7 | 150 | 0.029 | 35 | 0 | 0 |
| 2026-03-01 | 4,769 | 141 | 2026-02-28 | 619 | 9 | 0 | 7 | 150 | 0.047 | 35 | 0 | 0 |
| 2026-04-01 | 5,388 | 150 | 2026-03-31 | 656 | 82 | 0 | 7 | 150 | 0.326 | 34 | 0 | 1 |
| 2026-05-01 | 6,044 | 232 | 2026-04-30 | 836 | 97 | 0 | 7 | 150 | 0.275 | 34 | 0 | 1 |
| 2026-06-01 | 6,880 | 329 | 2026-05-31 | 802 | 61 | 0 | 7 | 150 | 0.481 | 34 | 0 | 0 |
| 2026-07-01 | 7,682 | 390 | 2026-06-30 | 804 | 33 | 0 | 7 | 150 | 0.502 | 34 | 0 | 1 |
| 2026-08-01 | 8,486 | 423 | 2026-07-31 | 822 | 42 | 0 | 7 | 150 | 0.536 | 34 | 0 | 0 |

`test_pr_auc` is the model's station-level PR-AUC within the fold's month (no interval; a month with no High has none).

### Forecasts filled in the test months (rule: §5.1 step 2)

| fold | target_date | fc_temp_high | fc_text | source |
|---|---|---|---|---|
| 2025-07-01 | 2025-07-21 | 34 | Thundery Showers | all training dates |
| 2026-04-01 | 2026-04-29 | 34 | Thundery Showers | calendar month |
| 2026-05-01 | 2026-05-18 | 34 | Thundery Showers | calendar month |
| 2026-07-01 | 2026-07-07 | 34 | Thundery Showers | calendar month |

Selected forecasts whose text disagrees with the corrected validity: 0.

## Hyper-parameters chosen per fold (from earlier folds only)

| fold | config | num_leaves | rounds | choice_aps |
|---|---|---|---|---|
| 2025-07-01 | 0 | 7 | 150 | first fold |
| 2025-08-01 | 1 | 15 | 150 | (7, 150): 0.323; (15, 150): 0.332; (7, 400): 0.285; (15, 400): 0.289 |
| 2025-09-01 | 3 | 15 | 400 | (7, 150): 0.140; (15, 150): 0.146; (7, 400): 0.145; (15, 400): 0.150 |
| 2025-10-01 | 2 | 7 | 400 | (7, 150): 0.151; (15, 150): 0.152; (7, 400): 0.153; (15, 400): 0.152 |
| 2025-11-01 | 0 | 7 | 150 | (7, 150): 0.351; (15, 150): 0.337; (7, 400): 0.318; (15, 400): 0.298 |
| 2025-12-01 | 0 | 7 | 150 | (7, 150): 0.287; (15, 150): 0.274; (7, 400): 0.275; (15, 400): 0.257 |
| 2026-01-01 | 0 | 7 | 150 | (7, 150): 0.276; (15, 150): 0.263; (7, 400): 0.265; (15, 400): 0.247 |
| 2026-02-01 | 0 | 7 | 150 | (7, 150): 0.273; (15, 150): 0.260; (7, 400): 0.260; (15, 400): 0.241 |
| 2026-03-01 | 0 | 7 | 150 | (7, 150): 0.266; (15, 150): 0.253; (7, 400): 0.253; (15, 400): 0.235 |
| 2026-04-01 | 0 | 7 | 150 | (7, 150): 0.249; (15, 150): 0.236; (7, 400): 0.235; (15, 400): 0.214 |
| 2026-05-01 | 0 | 7 | 150 | (7, 150): 0.269; (15, 150): 0.251; (7, 400): 0.256; (15, 400): 0.235 |
| 2026-06-01 | 0 | 7 | 150 | (7, 150): 0.263; (15, 150): 0.248; (7, 400): 0.246; (15, 400): 0.235 |
| 2026-07-01 | 0 | 7 | 150 | (7, 150): 0.303; (15, 150): 0.293; (7, 400): 0.290; (15, 400): 0.279 |
| 2026-08-01 | 0 | 7 | 150 | (7, 150): 0.322; (15, 150): 0.313; (7, 400): 0.309; (15, 400): 0.295 |

Secondary line, chosen on the same folds: candidate (7, 150) has the best pooled station-level PR-AUC over all folds ((7, 150): 0.345; (15, 150): 0.337; (7, 400): 0.330; (15, 400): 0.314).

## Bootstrap resamples skipped, per evaluation set and period

A resample (7-day blocks drawn with replacement) with no High row in a set has no recall or PR-AUC, so it is skipped; the intervals use the rest.

| set | period | rows | High | resamples | skipped | used |
|---|---|---|---|---|---|---|
| area41 | 2025-07-01 to 2026-08-31 | 17,438 | 710 | 2,000 | 0 | 2,000 |
| station_all | 2025-07-01 to 2026-08-31 | 8,001 | 421 | 2,000 | 0 | 2,000 |
| station_wo3 | 2025-07-01 to 2026-08-31 | 7,089 | 206 | 2,000 | 0 | 2,000 |
| station_o8 | 2025-07-01 to 2026-08-31 | 3,335 | 106 | 2,000 | 0 | 2,000 |
| area41_feb_aug_2026 | 2026-02-01 to 2026-08-31 | 8,666 | 569 | 2,000 | 0 | 2,000 |
| station_all_feb_aug_2026 | 2026-02-01 to 2026-08-31 | 5,096 | 327 | 2,000 | 0 | 2,000 |

## Headline: area-days over the 41 areas with residents aged 65+

Rows 17,438; High 710 (4.1%, the no-skill PR-AUC); persistence alerts K = 700; resamples skipped (no High): 0 of 2,000.

| method | PR-AUC (95%) | recall at persistence load (95%) | TP of High | alerts | precision (95%) | sustained-High recall (95%) |
|---|---|---|---|---|---|---|
| persistence (binary) | — (binary) | 0.345 (0.257 to 0.420) | 245 of 710 | 700 | 0.350 (0.275 to 0.413) | 0.482 (0.381 to 0.567) |
| model | 0.295 (0.233 to 0.365) | 0.345 (0.263 to 0.438) | 245 of 710 | 700 | 0.350 (0.277 to 0.423) | 0.518 (0.395 to 0.652) |
| persistence_continuous | 0.235 (0.171 to 0.306) | 0.345 (0.257 to 0.420) | 245 of 710 | 700 | 0.350 (0.275 to 0.413) | 0.482 (0.381 to 0.567) |
| nea_rule | 0.058 (0.040 to 0.081) | 0.032 (0.011 to 0.062) | 22.5 of 710 | 700 | 0.032 (0.014 to 0.054) | 0.040 (0.017 to 0.070) |
| ablation_no_station_char | 0.240 (0.187 to 0.305) | 0.297 (0.225 to 0.374) | 211 of 710 | 700 | 0.301 (0.228 to 0.387) | 0.447 (0.335 to 0.575) |
| ablation_without_S142_S137_S135 | 0.238 (0.175 to 0.314) | 0.313 (0.240 to 0.388) | 222 of 710 | 700 | 0.317 (0.239 to 0.410) | 0.455 (0.352 to 0.557) |
| ablation_recency_hl180 | 0.292 (0.229 to 0.360) | 0.356 (0.267 to 0.450) | 253 of 710 | 700 | 0.361 (0.283 to 0.441) | 0.494 (0.368 to 0.630) |
| best_overall | 0.300 (0.238 to 0.370) | 0.354 (0.269 to 0.445) | 251 of 710 | 700 | 0.359 (0.285 to 0.434) | 0.514 (0.388 to 0.652) |

Input to note §13 (the briefing's heat term): pooled area-day PR-AUC, model − persistence (continuous score) = 0.061 (0.009 to 0.115).

NEA rule at its own per-fold threshold: 435 of 710 High (recall 0.613), 4,747 alerts (precision 0.092).

Label-noise reference (docs/checks/h10_v2.md (viii)): near-equidistant stations' daily categories differ on 22.1% (29 of 131 days, Jurong West) and 22.0% (128 of 582, Marine Parade).

Paired differences:

| difference | PR-AUC (95%) | recall at load (95%) | sustained-High recall (95%) |
|---|---|---|---|
| model − persistence_continuous | 0.061 (0.009 to 0.115) | 0.000 (-0.082 to 0.102) | 0.035 (-0.113 to 0.194) |
| model − nea_rule | 0.237 (0.178 to 0.302) | 0.313 (0.230 to 0.401) | 0.477 (0.361 to 0.607) |
| model − ablation_no_station_char | 0.055 (0.019 to 0.095) | 0.048 (-0.010 to 0.109) | 0.070 (0.011 to 0.123) |
| model − ablation_without_S142_S137_S135 | 0.057 (0.024 to 0.092) | 0.032 (-0.009 to 0.082) | 0.062 (-0.015 to 0.142) |
| model − ablation_recency_hl180 | 0.003 (-0.010 to 0.018) | -0.011 (-0.050 to 0.030) | 0.023 (-0.011 to 0.064) |
| model − best_overall | -0.005 (-0.012 to -0.001) | -0.008 (-0.021 to 0.004) | 0.004 (-0.011 to 0.025) |
| model − persistence (binary) | — | 0.000 (-0.082 to 0.102) | 0.035 (-0.113 to 0.194) |

## Station-days: all stations

Rows 8,001; High 421 (5.3%, the no-skill PR-AUC); persistence alerts K = 416; resamples skipped (no High): 0 of 2,000.

| method | PR-AUC (95%) | recall at persistence load (95%) | TP of High | alerts | precision (95%) | sustained-High recall (95%) |
|---|---|---|---|---|---|---|
| persistence (binary) | — (binary) | 0.382 (0.319 to 0.436) | 161 of 421 | 416 | 0.387 (0.329 to 0.437) | 0.485 (0.392 to 0.567) |
| model | 0.340 (0.277 to 0.408) | 0.378 (0.298 to 0.462) | 159 of 421 | 416 | 0.382 (0.315 to 0.446) | 0.520 (0.408 to 0.636) |
| persistence_continuous | 0.277 (0.221 to 0.332) | 0.382 (0.319 to 0.436) | 161 of 421 | 416 | 0.387 (0.329 to 0.437) | 0.485 (0.392 to 0.567) |
| nea_rule | 0.066 (0.049 to 0.085) | 0.054 (0.022 to 0.094) | 22.5 of 421 | 416 | 0.054 (0.029 to 0.083) | 0.073 (0.032 to 0.121) |
| ablation_no_station_char | 0.296 (0.245 to 0.349) | 0.347 (0.278 to 0.421) | 146 of 421 | 416 | 0.351 (0.297 to 0.408) | 0.480 (0.366 to 0.593) |
| ablation_without_S142_S137_S135 | 0.283 (0.216 to 0.361) | 0.325 (0.268 to 0.385) | 137 of 421 | 416 | 0.329 (0.265 to 0.407) | 0.439 (0.345 to 0.530) |
| ablation_recency_hl180 | 0.330 (0.268 to 0.397) | 0.378 (0.296 to 0.466) | 159 of 421 | 416 | 0.382 (0.318 to 0.448) | 0.510 (0.389 to 0.635) |
| best_overall | 0.345 (0.282 to 0.413) | 0.382 (0.302 to 0.467) | 161 of 421 | 416 | 0.387 (0.322 to 0.451) | 0.530 (0.417 to 0.649) |

NEA rule at its own per-fold threshold: 246 of 421 High (recall 0.584), 2,852 alerts (precision 0.086).

Paired differences:

| difference | PR-AUC (95%) | recall at load (95%) | sustained-High recall (95%) |
|---|---|---|---|
| model − persistence_continuous | 0.063 (0.004 to 0.124) | -0.005 (-0.089 to 0.094) | 0.035 (-0.092 to 0.174) |
| model − nea_rule | 0.274 (0.212 to 0.343) | 0.324 (0.239 to 0.412) | 0.447 (0.330 to 0.565) |
| model − ablation_no_station_char | 0.044 (0.009 to 0.078) | 0.031 (-0.014 to 0.070) | 0.040 (-0.027 to 0.100) |
| model − ablation_without_S142_S137_S135 | 0.057 (0.018 to 0.096) | 0.052 (0.000 to 0.120) | 0.081 (0.006 to 0.163) |
| model − ablation_recency_hl180 | 0.010 (-0.002 to 0.022) | 0.000 (-0.026 to 0.027) | 0.010 (-0.026 to 0.049) |
| model − best_overall | -0.005 (-0.015 to 0.003) | -0.005 (-0.014 to 0.005) | -0.010 (-0.030 to 0.010) |
| model − persistence (binary) | — | -0.005 (-0.089 to 0.094) | 0.035 (-0.092 to 0.174) |

## Station-days: without S142, S137 and S135

Rows 7,089; High 206 (2.9%, the no-skill PR-AUC); persistence alerts K = 202; resamples skipped (no High): 0 of 2,000.

| method | PR-AUC (95%) | recall at persistence load (95%) | TP of High | alerts | precision (95%) | sustained-High recall (95%) |
|---|---|---|---|---|---|---|
| persistence (binary) | — (binary) | 0.257 (0.158 to 0.339) | 53 of 206 | 202 | 0.262 (0.166 to 0.338) | 0.328 (0.216 to 0.422) |
| model | 0.179 (0.123 to 0.247) | 0.252 (0.161 to 0.350) | 52 of 206 | 202 | 0.257 (0.174 to 0.347) | 0.310 (0.171 to 0.459) |
| persistence_continuous | 0.160 (0.098 to 0.233) | 0.257 (0.158 to 0.339) | 53 of 206 | 202 | 0.262 (0.166 to 0.338) | 0.328 (0.216 to 0.422) |
| nea_rule | 0.040 (0.025 to 0.059) | 0.011 (0.002 to 0.026) | 2.3 of 206 | 202 | 0.011 (0.002 to 0.023) | 0.000 (0.000 to 0.000) |
| ablation_no_station_char | 0.140 (0.091 to 0.211) | 0.199 (0.129 to 0.273) | 41 of 206 | 202 | 0.203 (0.123 to 0.302) | 0.276 (0.158 to 0.406) |
| ablation_without_S142_S137_S135 | 0.138 (0.094 to 0.201) | 0.209 (0.141 to 0.277) | 43 of 206 | 202 | 0.213 (0.142 to 0.299) | 0.207 (0.103 to 0.320) |
| ablation_recency_hl180 | 0.176 (0.119 to 0.245) | 0.243 (0.156 to 0.329) | 50 of 206 | 202 | 0.248 (0.165 to 0.331) | 0.310 (0.180 to 0.444) |
| best_overall | 0.182 (0.125 to 0.251) | 0.248 (0.156 to 0.346) | 51 of 206 | 202 | 0.252 (0.167 to 0.342) | 0.293 (0.153 to 0.438) |

NEA rule at its own per-fold threshold: 139 of 206 High (recall 0.675), 2,536 alerts (precision 0.055).

Paired differences:

| difference | PR-AUC (95%) | recall at load (95%) | sustained-High recall (95%) |
|---|---|---|---|
| model − persistence_continuous | 0.019 (-0.021 to 0.069) | -0.005 (-0.086 to 0.093) | -0.017 (-0.170 to 0.160) |
| model − nea_rule | 0.139 (0.088 to 0.198) | 0.241 (0.149 to 0.339) | 0.310 (0.171 to 0.459) |
| model − ablation_no_station_char | 0.039 (0.001 to 0.075) | 0.053 (-0.005 to 0.111) | 0.034 (-0.056 to 0.118) |
| model − ablation_without_S142_S137_S135 | 0.041 (0.012 to 0.070) | 0.044 (-0.013 to 0.098) | 0.103 (0.014 to 0.192) |
| model − ablation_recency_hl180 | 0.003 (-0.009 to 0.017) | 0.010 (-0.030 to 0.047) | 0.000 (-0.092 to 0.086) |
| model − best_overall | -0.003 (-0.011 to 0.001) | 0.005 (0.000 to 0.019) | 0.017 (0.000 to 0.065) |
| model − persistence (binary) | — | -0.005 (-0.086 to 0.093) | -0.017 (-0.170 to 0.160) |

## Station-days: the original 8 (7 after 24 Jun 2026)

Rows 3,335; High 106 (3.2%, the no-skill PR-AUC); persistence alerts K = 105; resamples skipped (no High): 0 of 2,000.

| method | PR-AUC (95%) | recall at persistence load (95%) | TP of High | alerts | precision (95%) | sustained-High recall (95%) |
|---|---|---|---|---|---|---|
| persistence (binary) | — (binary) | 0.292 (0.184 to 0.394) | 31 of 106 | 105 | 0.295 (0.190 to 0.388) | 0.345 (0.219 to 0.478) |
| model | 0.242 (0.173 to 0.331) | 0.302 (0.194 to 0.419) | 32 of 106 | 105 | 0.305 (0.211 to 0.400) | 0.448 (0.250 to 0.645) |
| persistence_continuous | 0.186 (0.120 to 0.275) | 0.292 (0.184 to 0.394) | 31 of 106 | 105 | 0.295 (0.190 to 0.388) | 0.345 (0.219 to 0.478) |
| nea_rule | 0.046 (0.031 to 0.064) | 0.024 (0.005 to 0.048) | 2.5 of 106 | 105 | 0.024 (0.005 to 0.049) | 0.000 (0.000 to 0.000) |
| ablation_no_station_char | 0.184 (0.128 to 0.268) | 0.255 (0.160 to 0.362) | 27 of 106 | 105 | 0.257 (0.160 to 0.368) | 0.310 (0.114 to 0.500) |
| ablation_without_S142_S137_S135 | 0.195 (0.131 to 0.288) | 0.274 (0.200 to 0.349) | 29 of 106 | 105 | 0.276 (0.196 to 0.378) | 0.310 (0.138 to 0.458) |
| ablation_recency_hl180 | 0.238 (0.171 to 0.321) | 0.311 (0.208 to 0.422) | 33 of 106 | 105 | 0.314 (0.224 to 0.408) | 0.448 (0.250 to 0.645) |
| best_overall | 0.250 (0.180 to 0.338) | 0.311 (0.205 to 0.429) | 33 of 106 | 105 | 0.314 (0.225 to 0.410) | 0.448 (0.250 to 0.645) |

NEA rule at its own per-fold threshold: 65 of 106 High (recall 0.613), 884 alerts (precision 0.074).

Paired differences:

| difference | PR-AUC (95%) | recall at load (95%) | sustained-High recall (95%) |
|---|---|---|---|
| model − persistence_continuous | 0.056 (0.000 to 0.109) | 0.009 (-0.081 to 0.113) | 0.103 (-0.080 to 0.281) |
| model − nea_rule | 0.196 (0.131 to 0.278) | 0.278 (0.162 to 0.405) | 0.448 (0.250 to 0.645) |
| model − ablation_no_station_char | 0.058 (0.011 to 0.108) | 0.047 (-0.043 to 0.133) | 0.138 (0.030 to 0.300) |
| model − ablation_without_S142_S137_S135 | 0.047 (0.004 to 0.091) | 0.028 (-0.066 to 0.130) | 0.138 (0.032 to 0.300) |
| model − ablation_recency_hl180 | 0.004 (-0.015 to 0.026) | -0.009 (-0.054 to 0.037) | 0.000 (0.000 to 0.000) |
| model − best_overall | -0.008 (-0.023 to -0.001) | -0.009 (-0.033 to 0.000) | 0.000 (0.000 to 0.000) |
| model − persistence (binary) | — | 0.009 (-0.081 to 0.113) | 0.103 (-0.080 to 0.281) |

## Feb to Aug 2026, area-days (same month last year)

Rows 8,666; High 569 (6.6%, the no-skill PR-AUC); persistence alerts K = 561; resamples skipped (no High): 0 of 2,000.

| method | PR-AUC (95%) | recall at persistence load (95%) | TP of High | alerts | precision (95%) | sustained-High recall (95%) |
|---|---|---|---|---|---|---|
| persistence (binary) | — (binary) | 0.378 (0.274 to 0.460) | 215 of 569 | 561 | 0.383 (0.305 to 0.445) | 0.512 (0.410 to 0.601) |
| model | 0.337 (0.269 to 0.417) | 0.381 (0.286 to 0.496) | 217 of 569 | 561 | 0.387 (0.307 to 0.471) | 0.579 (0.448 to 0.733) |
| persistence_continuous | 0.262 (0.183 to 0.346) | 0.378 (0.274 to 0.460) | 215 of 569 | 561 | 0.383 (0.305 to 0.445) | 0.512 (0.410 to 0.601) |
| nea_rule | 0.075 (0.050 to 0.104) | 0.031 (0.007 to 0.066) | 17.5 of 569 | 561.0 | 0.031 (0.010 to 0.055) | 0.038 (0.012 to 0.071) |
| ablation_no_station_char | 0.289 (0.222 to 0.363) | 0.357 (0.265 to 0.463) | 203 of 569 | 561 | 0.362 (0.276 to 0.452) | 0.512 (0.385 to 0.655) |
| ablation_without_S142_S137_S135 | 0.279 (0.204 to 0.368) | 0.337 (0.266 to 0.415) | 192 of 569 | 561 | 0.342 (0.253 to 0.444) | 0.502 (0.392 to 0.614) |
| ablation_recency_hl180 | 0.330 (0.260 to 0.411) | 0.380 (0.278 to 0.503) | 216 of 569 | 561 | 0.385 (0.303 to 0.463) | 0.555 (0.418 to 0.711) |
| best_overall | 0.337 (0.269 to 0.417) | 0.381 (0.286 to 0.496) | 217 of 569 | 561 | 0.387 (0.307 to 0.471) | 0.579 (0.448 to 0.733) |
| same_month_last_year | 0.095 (0.064 to 0.128) | 0.068 (0.030 to 0.104) | 38.5 of 569 | 561.0 | 0.069 (0.031 to 0.107) | 0.039 (0.003 to 0.088) |

NEA rule at its own per-fold threshold: 429 of 569 High (recall 0.754), 4,583 alerts (precision 0.094).

Label-noise reference (docs/checks/h10_v2.md (viii)): near-equidistant stations' daily categories differ on 22.1% (29 of 131 days, Jurong West) and 22.0% (128 of 582, Marine Parade).

Paired differences:

| difference | PR-AUC (95%) | recall at load (95%) | sustained-High recall (95%) |
|---|---|---|---|
| model − persistence_continuous | 0.075 (0.016 to 0.142) | 0.004 (-0.094 to 0.129) | 0.067 (-0.092 to 0.253) |
| model − nea_rule | 0.262 (0.198 to 0.343) | 0.351 (0.257 to 0.456) | 0.541 (0.416 to 0.685) |
| model − ablation_no_station_char | 0.048 (0.005 to 0.093) | 0.025 (-0.041 to 0.089) | 0.067 (-0.004 to 0.136) |
| model − ablation_without_S142_S137_S135 | 0.058 (0.018 to 0.101) | 0.044 (0.000 to 0.101) | 0.077 (-0.003 to 0.168) |
| model − ablation_recency_hl180 | 0.007 (-0.011 to 0.024) | 0.002 (-0.044 to 0.038) | 0.024 (-0.006 to 0.062) |
| model − best_overall | 0.000 (0.000 to 0.000) | 0.000 (0.000 to 0.000) | 0.000 (0.000 to 0.000) |
| model − persistence (binary) | — | 0.004 (-0.094 to 0.129) | 0.067 (-0.092 to 0.253) |
| model − same_month_last_year | 0.242 (0.168 to 0.326) | 0.314 (0.188 to 0.461) | 0.540 (0.371 to 0.722) |

## Feb to Aug 2026, station-days (same month last year)

Rows 5,096; High 327 (6.4%, the no-skill PR-AUC); persistence alerts K = 324; resamples skipped (no High): 0 of 2,000.

| method | PR-AUC (95%) | recall at persistence load (95%) | TP of High | alerts | precision (95%) | sustained-High recall (95%) |
|---|---|---|---|---|---|---|
| persistence (binary) | — (binary) | 0.398 (0.323 to 0.457) | 130 of 327 | 324 | 0.401 (0.332 to 0.458) | 0.513 (0.424 to 0.599) |
| model | 0.376 (0.296 to 0.464) | 0.398 (0.308 to 0.500) | 130 of 327 | 324 | 0.401 (0.330 to 0.479) | 0.584 (0.467 to 0.714) |
| persistence_continuous | 0.292 (0.226 to 0.358) | 0.398 (0.323 to 0.457) | 130 of 327 | 324 | 0.401 (0.332 to 0.458) | 0.513 (0.424 to 0.599) |
| nea_rule | 0.071 (0.050 to 0.094) | 0.045 (0.013 to 0.088) | 14.9 of 327 | 324 | 0.046 (0.019 to 0.072) | 0.060 (0.020 to 0.112) |
| ablation_no_station_char | 0.320 (0.260 to 0.384) | 0.370 (0.292 to 0.465) | 121 of 327 | 324 | 0.373 (0.308 to 0.449) | 0.532 (0.408 to 0.672) |
| ablation_without_S142_S137_S135 | 0.308 (0.235 to 0.405) | 0.330 (0.265 to 0.399) | 108 of 327 | 324 | 0.333 (0.261 to 0.438) | 0.455 (0.355 to 0.562) |
| ablation_recency_hl180 | 0.367 (0.288 to 0.452) | 0.398 (0.297 to 0.505) | 130 of 327 | 324 | 0.401 (0.331 to 0.478) | 0.571 (0.436 to 0.714) |
| best_overall | 0.376 (0.296 to 0.464) | 0.398 (0.308 to 0.500) | 130 of 327 | 324 | 0.401 (0.330 to 0.479) | 0.584 (0.467 to 0.714) |
| same_month_last_year | 0.093 (0.064 to 0.124) | 0.063 (0.034 to 0.088) | 20.5 of 327 | 324 | 0.063 (0.032 to 0.095) | 0.028 (0.004 to 0.058) |

NEA rule at its own per-fold threshold: 239 of 327 High (recall 0.731), 2,798 alerts (precision 0.085).

Paired differences:

| difference | PR-AUC (95%) | recall at load (95%) | sustained-High recall (95%) |
|---|---|---|---|
| model − persistence_continuous | 0.085 (0.011 to 0.162) | 0.000 (-0.091 to 0.109) | 0.071 (-0.057 to 0.207) |
| model − nea_rule | 0.306 (0.227 to 0.398) | 0.352 (0.265 to 0.447) | 0.524 (0.413 to 0.643) |
| model − ablation_no_station_char | 0.057 (0.011 to 0.099) | 0.028 (-0.023 to 0.069) | 0.052 (-0.013 to 0.103) |
| model − ablation_without_S142_S137_S135 | 0.068 (0.026 to 0.114) | 0.067 (0.012 to 0.134) | 0.130 (0.045 to 0.217) |
| model − ablation_recency_hl180 | 0.009 (-0.010 to 0.027) | 0.000 (-0.029 to 0.033) | 0.013 (-0.033 to 0.065) |
| model − best_overall | 0.000 (0.000 to 0.000) | 0.000 (0.000 to 0.000) | 0.000 (0.000 to 0.000) |
| model − persistence (binary) | — | 0.000 (-0.091 to 0.109) | 0.071 (-0.057 to 0.207) |
| model − same_month_last_year | 0.283 (0.199 to 0.381) | 0.335 (0.226 to 0.457) | 0.557 (0.419 to 0.704) |

## Per month, counts (area41; model at the persistence load)

| group | rows | high | alerts | tp | sum_p_high | fp | fn | alerts_persistence | tp_persistence | fp_persistence | fn_persistence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2025-07 | 1,261 | 31 | 21 | 7 | 27.852 | 14 | 24 | 31 | 8 | 23 | 23 |
| 2025-08 | 1,271 | 0 | 27 | 0.000 | 22.315 | 27 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2025-09 | 1,213 | 38 | 14 | 2 | 7.822 | 12 | 36 | 37 | 8 | 29 | 30 |
| 2025-10 | 1,260 | 33 | 29 | 13 | 23.196 | 16 | 20 | 28 | 11 | 17 | 22 |
| 2025-11 | 1,225 | 32 | 28 | 4 | 32.880 | 24 | 28 | 36 | 3 | 33 | 29 |
| 2025-12 | 1,271 | 7 | 1 | 0.000 | 6.859 | 1 | 7 | 7 | 0.000 | 7 | 7 |
| 2026-01 | 1,271 | 0 | 0.000 | 0.000 | 8.290 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2026-02 | 1,142 | 3 | 0.000 | 0.000 | 2.883 | 0.000 | 3 | 0.000 | 0.000 | 0.000 | 3 |
| 2026-03 | 1,269 | 22 | 0.000 | 0.000 | 19.269 | 0.000 | 22 | 23 | 3 | 20 | 19 |
| 2026-04 | 1,230 | 184 | 81 | 39 | 81.672 | 42 | 145 | 163 | 77 | 86 | 107 |
| 2026-05 | 1,269 | 158 | 181 | 52 | 115.387 | 129 | 106 | 175 | 56 | 119 | 102 |
| 2026-06 | 1,221 | 91 | 93 | 42 | 71.735 | 51 | 49 | 93 | 35 | 58 | 56 |
| 2026-07 | 1,264 | 48 | 103 | 34 | 65.125 | 69 | 14 | 35 | 13 | 22 | 35 |
| 2026-08 | 1,271 | 63 | 122 | 52 | 81.962 | 70 | 11 | 72 | 31 | 41 | 32 |

## Per month, counts (station_all; model at the persistence load)

| group | rows | high | alerts | tp | sum_p_high | fp | fn | alerts_persistence | tp_persistence | fp_persistence | fn_persistence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2025-07 | 268 | 12 | 5 | 2 | 7.254 | 3 | 10 | 11 | 4 | 7 | 8 |
| 2025-08 | 279 | 2 | 9 | 0.000 | 8.184 | 9 | 2 | 2 | 0.000 | 2 | 2 |
| 2025-09 | 439 | 25 | 4 | 1 | 3.571 | 3 | 24 | 25 | 9 | 16 | 16 |
| 2025-10 | 461 | 32 | 40 | 18 | 24.215 | 22 | 14 | 29 | 15 | 14 | 17 |
| 2025-11 | 448 | 18 | 45 | 11 | 29.252 | 34 | 7 | 20 | 3 | 17 | 15 |
| 2025-12 | 465 | 5 | 1 | 0.000 | 3.360 | 1 | 5 | 5 | 0.000 | 5 | 5 |
| 2026-01 | 545 | 0 | 0.000 | 0.000 | 2.876 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2026-02 | 557 | 3 | 0.000 | 0.000 | 1.396 | 0.000 | 3 | 1 | 0.000 | 1 | 3 |
| 2026-03 | 619 | 9 | 0.000 | 0.000 | 9.518 | 0.000 | 9 | 10 | 3 | 7 | 6 |
| 2026-04 | 656 | 82 | 30 | 14 | 43.403 | 16 | 68 | 71 | 28 | 43 | 54 |
| 2026-05 | 836 | 97 | 103 | 31 | 80.484 | 72 | 66 | 105 | 41 | 64 | 56 |
| 2026-06 | 802 | 61 | 63 | 30 | 52.017 | 33 | 31 | 63 | 27 | 36 | 34 |
| 2026-07 | 804 | 33 | 53 | 22 | 38.545 | 31 | 11 | 28 | 11 | 17 | 22 |
| 2026-08 | 822 | 42 | 63 | 30 | 48.421 | 33 | 12 | 46 | 20 | 26 | 22 |

## Season by year, counts (area41)

| group | rows | high | alerts | tp | sum_p_high | fp | fn | alerts_persistence | tp_persistence | fp_persistence | fn_persistence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Inter-monsoon 1 2026 | 3,768 | 364 | 262 | 91 | 216.328 | 171 | 273 | 361 | 136 | 225 | 228 |
| Inter-monsoon 2 2025 | 2,485 | 65 | 57 | 17 | 56.076 | 40 | 48 | 64 | 14 | 50 | 51 |
| NE monsoon 2025/26 | 3,684 | 10 | 1 | 0.000 | 18.032 | 1 | 10 | 7 | 0.000 | 7 | 10 |
| SW monsoon 2025 | 3,745 | 69 | 62 | 9 | 57.990 | 53 | 60 | 68 | 16 | 52 | 53 |
| SW monsoon 2026 | 3,756 | 202 | 318 | 128 | 218.822 | 190 | 74 | 200 | 79 | 121 | 123 |

## Season by year, counts (station_all)

| group | rows | high | alerts | tp | sum_p_high | fp | fn | alerts_persistence | tp_persistence | fp_persistence | fn_persistence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Inter-monsoon 1 2026 | 2,111 | 188 | 133 | 45 | 133.404 | 88 | 143 | 186 | 72 | 114 | 116 |
| Inter-monsoon 2 2025 | 909 | 50 | 85 | 29 | 53.467 | 56 | 21 | 49 | 18 | 31 | 32 |
| NE monsoon 2025/26 | 1,567 | 8 | 1 | 0.000 | 7.632 | 1 | 8 | 6 | 0.000 | 6 | 8 |
| SW monsoon 2025 | 986 | 39 | 18 | 3 | 19.009 | 15 | 36 | 38 | 13 | 25 | 26 |
| SW monsoon 2026 | 2,428 | 136 | 179 | 82 | 138.983 | 97 | 54 | 137 | 58 | 79 | 78 |

## Inter-monsoon 1, 2025 (persistence and base rate only; no fold predicts Mar to May 2025)

- station: 736 rows, 37 High (5.0%); persistence 2 of 37 (recall 0.054), 35 alerts (precision 0.057).
- area: 3,772 rows, 222 High (5.9%); persistence 13 of 222 (recall 0.059), 215 alerts (precision 0.060).

Inter-monsoon 1 of 2026 for every method is in the season tables above.

## High station-days in the test months by High readings that day

1 reading: 158; 2 readings: 65; 3 or more (sustained): 198.

## Three classes (station-days, model)

Multiclass log loss 0.6621. Rows: label (0 Low, 1 Moderate, 2 High); columns: the most probable class.

| label | 0 | 1 | 2 |
|---|---|---|---|
| 0 | 2,920 | 1,236 | 29 |
| 1 | 753 | 2,585 | 57 |
| 2 | 25 | 304 | 92 |

## PR curve sample, model (area41); the full curve is an artifact

| recall at least | threshold P(High) | alerts | TP | recall | precision |
|---|---|---|---|---|---|
| 0.300 | 0.236 | 575 | 213 | 0.300 | 0.370 |
| 0.350 | 0.183 | 720 | 250 | 0.352 | 0.347 |
| 0.400 | 0.154 | 853 | 284 | 0.400 | 0.333 |
| 0.450 | 0.137 | 980 | 320 | 0.451 | 0.327 |
| 0.500 | 0.110 | 1,180 | 355 | 0.500 | 0.301 |
| 0.550 | 0.087 | 1,595 | 391 | 0.551 | 0.245 |
| 0.600 | 0.068 | 1,925 | 427 | 0.601 | 0.222 |
| 0.650 | 0.052 | 2,386 | 462 | 0.651 | 0.194 |
| 0.700 | 0.036 | 3,232 | 498 | 0.701 | 0.154 |
| 0.750 | 0.026 | 4,158 | 534 | 0.752 | 0.128 |
| 0.800 | 0.021 | 4,697 | 570 | 0.803 | 0.121 |
| 0.850 | 0.014 | 5,722 | 605 | 0.852 | 0.106 |
| 0.900 | 0.007 | 8,695 | 639 | 0.900 | 0.073 |
| 0.950 | 0.003 | 12,728 | 676 | 0.952 | 0.053 |

## PR curve sample, model (station_all); the full curve is an artifact

| recall at least | threshold P(High) | alerts | TP | recall | precision |
|---|---|---|---|---|---|
| 0.300 | 0.313 | 285 | 127 | 0.302 | 0.446 |
| 0.350 | 0.259 | 364 | 148 | 0.352 | 0.407 |
| 0.400 | 0.216 | 442 | 169 | 0.401 | 0.382 |
| 0.450 | 0.174 | 545 | 190 | 0.451 | 0.349 |
| 0.500 | 0.146 | 637 | 211 | 0.501 | 0.331 |
| 0.550 | 0.126 | 728 | 232 | 0.551 | 0.319 |
| 0.600 | 0.093 | 946 | 253 | 0.601 | 0.267 |
| 0.650 | 0.077 | 1,086 | 274 | 0.651 | 0.252 |
| 0.700 | 0.058 | 1,287 | 295 | 0.701 | 0.229 |
| 0.750 | 0.040 | 1,703 | 316 | 0.751 | 0.186 |
| 0.800 | 0.030 | 2,073 | 337 | 0.800 | 0.163 |
| 0.850 | 0.020 | 2,556 | 358 | 0.850 | 0.140 |
| 0.900 | 0.010 | 3,589 | 379 | 0.900 | 0.106 |
| 0.950 | 0.004 | 5,323 | 400 | 0.950 | 0.075 |

## Addendum, 22 Oct 2026 (added after the run): why the four test-month forecasts were missing

Added at your request; the job's report above is unchanged. The reasons come from `coolcheck.features.forecast_gaps` and `gap_reason` over `coolcheck.silver.forecast_issues VERSION AS OF 9` (the version this run pinned) at the 00:15 cut-off, the same rules as the selection (note §3.3). Runs after the next deploy print this column in the report themselves.

| target date | filled with (source) | why no forecast qualified |
|---|---|---|
| 2025-07-21 | 34, Thundery Showers (all training dates) | No issue known by the cut-off has a corrected validity covering 06:00 to 18:00, and no forecast was issued at all on 20 Jul (NEA returned no data that day; `forecast_validity.md`). |
| 2026-04-29 | 34, Thundery Showers (calendar month) | The 23:01 issue of 28 Apr covers the day, but its only version was updated at 05:55 on 29 Apr, after the cut-off. |
| 2026-05-18 | 34, Thundery Showers (calendar month) | The only covering issue was made at 02:53 on 17 May, before 17:00 the day before (the age limit; the 27-hour case `eda.md` anticipated). No issue was made on 17 May from 17:00. |
| 2026-07-07 | 34, Thundery Showers (calendar month) | Two covering issues, both rejected: the 05:04 issue of 6 Jul (age limit), and an issue stamped 00:31 on 7 Jul, after the cut-off, although its updated time is 23:41 on 6 Jul (earlier than its own issue time). The strict rule, both times at or before the cut-off, stays (your decision, 22 Oct). |
