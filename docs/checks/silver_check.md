# Silver check after the first full pipeline update

Generated 2026-10-21 17:35 SGT by `scripts/checks/silver_check.py`; pipeline update `284d69cd-b4f7-40be-a86e-0c1e6484f73a`. Tables read only.

## Row counts

| table | rows |
|---|---|
| `bronze.wbgt_raw` | 2,563 |
| `bronze.rainfall_raw` | 7,687 |
| `bronze.forecast_raw` | 641 |
| `silver.wbgt_readings_all` | 1,036,005 |
| `silver.wbgt_readings` | 1,036,005 |
| `silver.rainfall_readings_all` | 11,893,198 |
| `silver.rainfall_readings` | 11,893,198 |
| `silver.forecast_issues_all` | 4,673 |
| `silver.forecast_issues` | 4,673 |
| `silver.quarantine` | 0 |
| `silver.wbgt_first_arrival` | 1,036,005 |
| `silver.station_daily_label` | 10,836 |
| `silver.dq_day` | 1,926 |
| `silver.dq_events` | 39 |
| `silver.dq_conflicts` | 0 |
| `silver.station_gaps` | 1,263 |
| `silver.forecast_periods` | 74,580 |

## Silver readings against the raw-file totals

| feed | expected (raw files) | `_all` (every copy) | deduplicated | removed as duplicates | rows without a key |
|---|---|---|---|---|---|
| wbgt | 1,036,005 | 1,036,005 (matches) | 1,036,005 | 0 | 0 |
| rainfall | 11,893,198 | 11,893,198 (matches) | 11,893,198 | 0 | 0 |
| forecast | 4,673 | 4,673 (matches) | 4,673 | 0 | 0 |

## dq_events (rule failures and other checks)

A rule failure flags the row; nothing is removed. Rules are in `src/coolcheck/silver.py`.

| feed | check_name | n | detail |
|---|---|---|---|
| forecast | copies_with_key | 4,673 | dedupe keys: issue_ts, updated_ts |
| forecast | distinct_keys | 4,673 | dedupe keys: issue_ts, updated_ts |
| forecast | keys_with_conflicting_copies | 0 | dedupe keys: issue_ts, updated_ts |
| forecast | keys_with_duplicate_copies | 0 | dedupe keys: issue_ts, updated_ts |
| forecast | rule:file_date_matches | 0 | of 4673 rows (all copies) |
| forecast | rule:has_key | 0 | of 4673 rows (all copies) |
| forecast | rule:record_date_matches | 0 | of 4673 rows (all copies) |
| forecast | rule:sgt_offset | 0 | of 4673 rows (all copies) |
| forecast | rule:temp_in_range | 0 | of 4673 rows (all copies) |
| forecast | rule:temp_present | 0 | of 4673 rows (all copies) |
| forecast | rule:validity_24h | 527 | of 4673 rows (all copies) |
| forecast | rule:validity_end_after_start | 6 | of 4673 rows (all copies) |
| forecast | rule:validity_parsed | 0 | of 4673 rows (all copies) |
| forecast | rule:validity_start_near_issue | 3 | of 4673 rows (all copies) |
| forecast | rule:validity_text_agrees | 522 | of 4673 rows (all copies) |
| forecast | rule:validity_text_parsed | 0 | of 4673 rows (all copies) |
| rainfall | copies_with_key | 11,893,198 | dedupe keys: station_id, reading_ts |
| rainfall | distinct_keys | 11,893,198 | dedupe keys: station_id, reading_ts |
| rainfall | keys_with_conflicting_copies | 0 | dedupe keys: station_id, reading_ts |
| rainfall | keys_with_duplicate_copies | 0 | dedupe keys: station_id, reading_ts |
| rainfall | rule:file_date_matches | 0 | of 11893198 rows (all copies) |
| rainfall | rule:has_key | 0 | of 11893198 rows (all copies) |
| rainfall | rule:rain_non_negative | 0 | of 11893198 rows (all copies) |
| rainfall | rule:rain_present | 0 | of 11893198 rows (all copies) |
| rainfall | rule:sgt_offset | 0 | of 11893198 rows (all copies) |
| rainfall | rule:station_listed | 111 | of 11893198 rows (all copies) |
| rainfall | stations_moved_over_about_100m | 23 | location differs at 3 decimal places: S06, S07, S102, S107, S109, S112, S113, S116, S117, S119, S121, S215, S23, S24, S35, S40, S43, S50, S64, S81, S88, S900, S94 |
| wbgt | copies_with_key | 1,036,005 | dedupe keys: station_id, reading_ts |
| wbgt | distinct_keys | 1,036,005 | dedupe keys: station_id, reading_ts |
| wbgt | keys_with_conflicting_copies | 0 | dedupe keys: station_id, reading_ts |
| wbgt | keys_with_duplicate_copies | 0 | dedupe keys: station_id, reading_ts |
| wbgt | readings_first_arrived_over_1h_late | 0 | of 0 readings seen in live files (backfill readings are never late) |
| wbgt | rule:file_date_matches | 0 | of 1036005 rows (all copies) |
| wbgt | rule:has_key | 0 | of 1036005 rows (all copies) |
| wbgt | rule:heat_stress_known | 2,894 | of 1036005 rows (all copies) |
| wbgt | rule:sgt_offset | 0 | of 1036005 rows (all copies) |
| wbgt | rule:wbgt_in_range | 79 | of 1036005 rows (all copies) |
| wbgt | rule:wbgt_present | 2,894 | of 1036005 rows (all copies) |
| wbgt | stations_moved_over_about_100m | 1 | location differs at 3 decimal places: S187 |

## Days that are not ok (dq_day)

| feed | status | days | dates |
|---|---|---|---|
| forecast | no_data | 1 | 2025-07-20 (0 issues) |
| rainfall | short | 17 | 2025-01-20 (272 of 288 timestamps), 2025-02-21 (284 of 288 timestamps), 2025-03-26 (271 of 288 timestamps), 2025-05-06 (271 of 288 timestamps), 2025-05-28 (220 of 288 timestamps), 2025-05-29 (281 of 288 timestamps), 2025-07-20 (149 of 288 timestamps), 2025-08-23 (272 of 288 timestamps), 2025-09-13 (234 of 288 timestamps), 2025-11-18 (266 of 288 timestamps), 2026-02-04 (283 of 288 timestamps), 2026-04-14 (271 of 288 timestamps), 2026-06-02 (286 of 288 timestamps), 2026-06-05 (280 of 288 timestamps), 2026-08-14 (284 of 288 timestamps), 2026-08-20 (279 of 288 timestamps), 2026-08-22 (281 of 288 timestamps) |
| wbgt | short | 21 | 2025-01-16 (2 of 96 timestamps), 2025-01-17 (46 of 96 timestamps), 2025-01-29 (89 of 96 timestamps), 2025-07-09 (95 of 96 timestamps), 2025-08-14 (95 of 96 timestamps), 2025-08-25 (95 of 96 timestamps), 2025-11-18 (89 of 96 timestamps), 2025-11-19 (95 of 96 timestamps), 2025-12-18 (95 of 96 timestamps), 2026-03-23 (95 of 96 timestamps), 2026-03-25 (95 of 96 timestamps), 2026-04-22 (95 of 96 timestamps), 2026-06-05 (93 of 96 timestamps), 2026-07-23 (95 of 96 timestamps), 2026-08-14 (93 of 96 timestamps), 2026-08-19 (94 of 96 timestamps), 2026-08-20 (91 of 96 timestamps), 2026-08-31 (90 of 96 timestamps), 2026-09-14 (95 of 96 timestamps), 2026-09-19 (95 of 96 timestamps), 2026-10-05 (95 of 96 timestamps) |

## Label rule effects (station_daily_label)

| station_days_with_rows | station_days_labelled | no_label | low_coverage | low_coverage_low | low_coverage_moderate | low_coverage_high_kept | usable | changed_if_out_of_range_excluded | changed_if_late_excluded | out_of_range_readings |
|---|---|---|---|---|---|---|---|---|---|---|
| 10,836 | 10,834 | 2 | 67 | 52 | 10 | 5 | 10,772 | 0 | 0 | 79 |

How the out-of-range exclusion would change labels:

| label | label_if_out_of_range_excluded | station_days |
|---|---|---|

Station-days with a WBGT gap over 60 minutes that overlaps 10:00 to 18:00 SGT (the silent rule), by label:

| label | station_days |
|---|---|
| (none) | 2 |
| High | 13 |
| Low | 48 |
| Moderate | 48 |

## High-day counts against docs/checks/wbgt_high_days.md

Definitions as in that file: station-day = at least one counted reading; High station-day = label High; High day = a day on which any station (or any of the original 8) is High.

| measure | notes (20 Oct) | Silver labels | same? |
|---|---|---|---|
| station-days | 10,834 | 10,834 | yes |
| High station-days | 535 | 535 | yes |
| High days | 247 | 247 | yes |
| station-days, original 8 | 5,014 | 5,014 | yes |
| High station-days, original 8 | 166 | 166 | yes |
| High days, original 8 | 128 | 128 | yes |
| High station-days Jan–Jun 2025 | 44 | 44 | yes |
| High station-days Jul 2025–Aug 2026 | 421 | 421 | yes |
| … original 8 | 106 | 106 | yes |
| High station-days Sep–19 Oct 2026 | 70 | 70 | yes |
| … original 8 | 16 | 16 | yes |
