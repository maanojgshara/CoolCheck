# Back-test review tables

Generated 2026-10-22 20:44 SGT by `scripts/analysis/backtest_review.py` at git `06d09e6` from the artifacts of MLflow run `c509ab9ad0d8464f8a1df07354b1bf98` (the run of `docs/checks/backtest.md`), saved in `backtest_run_c509ab9a` under `coolcheck-data/analysis/`. Numbers only; no cut-off is chosen here. Nothing after 2026-08-31 is read (the predictions end on 2026-08-31).

## H4 operating points, area-days over the 41 areas

Pooled out-of-fold predictions, 17,438 area-days, 710 High, 427 test days (91 in Apr to Jun 2026). The model's score is P(High); persistence (continuous) is yesterday's peak WBGT at the area's station, in °C. At each recall level: the highest threshold reaching it, the alerts at or above it (area-days), and alerts per day.

### Model, P(High)

| recall at least | threshold | alerts | alerts per day (all 14 months) | alerts per day (Apr to Jun 2026) | TP | recall | precision |
|---|---|---|---|---|---|---|---|
| 0.300 | 0.236 | 575 | 1.347 | 2.912 | 213 | 0.300 | 0.370 |
| 0.400 | 0.154 | 853 | 1.998 | 5.198 | 284 | 0.400 | 0.333 |
| 0.500 | 0.110 | 1,180 | 2.763 | 7.736 | 355 | 0.500 | 0.301 |
| 0.600 | 0.068 | 1,925 | 4.508 | 13.055 | 427 | 0.601 | 0.222 |
| 0.700 | 0.036 | 3,232 | 7.569 | 19.198 | 498 | 0.701 | 0.154 |
| 0.800 | 0.021 | 4,697 | 11 | 25.549 | 570 | 0.803 | 0.121 |

### Persistence (continuous), yesterday's peak WBGT

| recall at least | threshold | alerts | alerts per day (all 14 months) | alerts per day (Apr to Jun 2026) | TP | recall | precision |
|---|---|---|---|---|---|---|---|
| 0.300 | 33.100 | 567 | 1.328 | 3.846 | 214 | 0.301 | 0.377 |
| 0.400 | 32.700 | 1,120 | 2.623 | 6.824 | 296 | 0.417 | 0.264 |
| 0.500 | 32.500 | 1,541 | 3.609 | 9.253 | 355 | 0.500 | 0.230 |
| 0.600 | 32.200 | 2,432 | 5.696 | 13.451 | 442 | 0.623 | 0.182 |
| 0.700 | 31.800 | 4,048 | 9.480 | 19.725 | 501 | 0.706 | 0.124 |
| 0.800 | 31.200 | 7,078 | 16.576 | 27.824 | 581 | 0.818 | 0.082 |

## The model at the NEA rule's alert load (area-days)

The NEA rule at its own per-fold thresholds alerts on 4,747 area-days. The model's 4,747 highest P(High) (ties shared in expectation):

| method | alerts | TP | High | recall | precision |
|---|---|---|---|---|---|
| model at the NEA load | 4,747 | 570 | 710 | 0.803 | 0.120 |
| NEA rule at its own thresholds | 4,747 | 435 | 710 | 0.613 | 0.092 |

## Sustained High (3 or more High readings) at persistence's load

Persistence alerts K times (its binary rule); the model alerts on its K highest P(High), ties shared in expectation. Recall over the High days with 3 or more High readings.

| set | K | method | sustained High | caught | recall |
|---|---|---|---|---|---|
| area-days, 41 areas | 700 | model | 257 | 133 | 0.518 |
| area-days, 41 areas | 700 | persistence | 257 | 124 | 0.482 |
| station-days, all stations | 416 | model | 198 | 103 | 0.520 |
| station-days, all stations | 416 | persistence | 198 | 96 | 0.485 |

## Per month: observed High against the sum of P(High)

### area-days, 41 areas

| month | rows | observed_high | sum_p_high | observed − expected |
|---|---|---|---|---|
| 2025-07 | 1,261 | 31 | 27.852 | 3.148 |
| 2025-08 | 1,271 | 0 | 22.315 | -22.315 |
| 2025-09 | 1,213 | 38 | 7.822 | 30.178 |
| 2025-10 | 1,260 | 33 | 23.196 | 9.804 |
| 2025-11 | 1,225 | 32 | 32.880 | -0.880 |
| 2025-12 | 1,271 | 7 | 6.859 | 0.141 |
| 2026-01 | 1,271 | 0 | 8.290 | -8.290 |
| 2026-02 | 1,142 | 3 | 2.883 | 0.117 |
| 2026-03 | 1,269 | 22 | 19.269 | 2.731 |
| 2026-04 | 1,230 | 184 | 81.672 | 102.328 |
| 2026-05 | 1,269 | 158 | 115.387 | 42.613 |
| 2026-06 | 1,221 | 91 | 71.735 | 19.265 |
| 2026-07 | 1,264 | 48 | 65.125 | -17.125 |
| 2026-08 | 1,271 | 63 | 81.962 | -18.962 |
| all | 17,438 | 710 | 567.248 | 142.752 |

### station-days, all stations

| month | rows | observed_high | sum_p_high | observed − expected |
|---|---|---|---|---|
| 2025-07 | 268 | 12 | 7.254 | 4.746 |
| 2025-08 | 279 | 2 | 8.184 | -6.184 |
| 2025-09 | 439 | 25 | 3.571 | 21.429 |
| 2025-10 | 461 | 32 | 24.215 | 7.785 |
| 2025-11 | 448 | 18 | 29.252 | -11.252 |
| 2025-12 | 465 | 5 | 3.360 | 1.640 |
| 2026-01 | 545 | 0 | 2.876 | -2.876 |
| 2026-02 | 557 | 3 | 1.396 | 1.604 |
| 2026-03 | 619 | 9 | 9.518 | -0.518 |
| 2026-04 | 656 | 82 | 43.403 | 38.597 |
| 2026-05 | 836 | 97 | 80.484 | 16.516 |
| 2026-06 | 802 | 61 | 52.017 | 8.983 |
| 2026-07 | 804 | 33 | 38.545 | -5.545 |
| 2026-08 | 822 | 42 | 48.421 | -6.421 |
| all | 8,001 | 421 | 352.495 | 68.505 |

