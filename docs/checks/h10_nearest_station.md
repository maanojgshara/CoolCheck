# H10 nearest reporting station, and the final-check High dates

Generated 2026-10-21 17:46 SGT by `scripts/checks/h10_high_days.py` from `coolcheck.gold.area_nearest_station_daily` (boundary mp2025, cut-off 00:15 SGT, reporting = at least one counted WBGT reading in the 7 days before the cut-off), `coolcheck.silver.area_station_distance` and `coolcheck.silver.station_daily_label`.

SingStat June 2026: 55 planning areas, 41 with residents aged 65+ (806,080 residents 65+, figures rounded to 10 by SingStat); names not found in the MP2025 boundary: none.

## 1. Target date 2026-10-20: view against the nearest of all 31 stations

55 areas in the view for 2026-10-20; 30 stations reporting. Areas where the view differs from the all-stations nearest: **1**.

| planning_area | view_station | view_km | all_station | all_km | all_station_last_counted_reading |
|---|---|---|---|---|---|
| CLEMENTI | S153 | 3.28 | S130 | 0.84 | 2026-06-24 08:00:00 |

## 2. Distance to the nearest reporting station per month (areas with residents 65+)

Over area-days (each area once per target day). Back-test months Jul 2025 to Aug 2026; the final check (Sep to 20 Oct 2026) and the training-only months (Jan to Jun 2025) are shown separately.

| period | month | areas | area_days | median_km | max_km | area_at_max | station_at_max | min_stations_reporting | max_stations_reporting |
|---|---|---|---|---|---|---|---|---|---|
| training only | 2025-01 | 41 | 615 | 3.37 | 8.54 | PUNGGOL | S128 | 8 | 8 |
| training only | 2025-02 | 41 | 1148 | 3.37 | 8.54 | PUNGGOL | S128 | 8 | 8 |
| training only | 2025-03 | 41 | 1271 | 3.37 | 8.54 | PUNGGOL | S128 | 8 | 8 |
| training only | 2025-04 | 41 | 1230 | 3.37 | 8.54 | PUNGGOL | S128 | 8 | 8 |
| training only | 2025-05 | 41 | 1271 | 3.37 | 8.54 | PUNGGOL | S128 | 8 | 8 |
| training only | 2025-06 | 41 | 1230 | 3.37 | 8.54 | PUNGGOL | S128 | 8 | 8 |
| back-test | 2025-07 | 41 | 1271 | 3.37 | 8.54 | PUNGGOL | S128 | 8 | 9 |
| back-test | 2025-08 | 41 | 1271 | 3.37 | 8.54 | PUNGGOL | S128 | 9 | 9 |
| back-test | 2025-09 | 41 | 1230 | 2.77 | 8.54 | PUNGGOL | S128 | 9 | 15 |
| back-test | 2025-10 | 41 | 1271 | 2.77 | 4.89 | SEMBAWANG | S125 | 15 | 15 |
| back-test | 2025-11 | 41 | 1230 | 2.77 | 4.89 | SEMBAWANG | S125 | 15 | 15 |
| back-test | 2025-12 | 41 | 1271 | 2.77 | 4.89 | SEMBAWANG | S125 | 15 | 15 |
| back-test | 2026-01 | 41 | 1271 | 2.13 | 4.89 | SEMBAWANG | S125 | 15 | 20 |
| back-test | 2026-02 | 41 | 1148 | 1.99 | 4.89 | SEMBAWANG | S125 | 20 | 20 |
| back-test | 2026-03 | 41 | 1271 | 1.99 | 4.89 | SEMBAWANG | S125 | 20 | 20 |
| back-test | 2026-04 | 41 | 1230 | 1.99 | 4.89 | SEMBAWANG | S125 | 20 | 27 |
| back-test | 2026-05 | 41 | 1271 | 1.97 | 4.89 | SEMBAWANG | S125 | 27 | 27 |
| back-test | 2026-06 | 41 | 1230 | 1.97 | 4.89 | SEMBAWANG | S125 | 27 | 27 |
| back-test | 2026-07 | 41 | 1271 | 1.99 | 4.89 | SEMBAWANG | S125 | 26 | 27 |
| back-test | 2026-08 | 41 | 1271 | 1.97 | 4.89 | SEMBAWANG | S125 | 26 | 30 |
| final check | 2026-09 | 41 | 1230 | 1.59 | 4.89 | SEMBAWANG | S125 | 30 | 30 |
| final check | 2026-10 | 41 | 820 | 1.59 | 4.89 | SEMBAWANG | S125 | 30 | 30 |

## 3. Area-days with no station

Target days 2025-01-17 to 2026-10-20 × 55 areas = 35,310 area-days; with a station 35,310; **without a station 0**.

## 4. Distinct High dates, 1 Sep to 19 Oct 2026 (from `silver.station_daily_label`)

High station-days 70 (39 without S142). **Distinct High dates: 35 with any station; 23 without S142.**

| sgt_date | high_stations | stations | s142_only |
|---|---|---|---|
| 2026-09-01 | 3 | S128, S141, S142 | False |
| 2026-09-02 | 4 | S128, S135, S141, S142 | False |
| 2026-09-03 | 2 | S141, S142 | False |
| 2026-09-06 | 2 | S128, S142 | False |
| 2026-09-08 | 1 | S142 | True |
| 2026-09-09 | 2 | S128, S142 | False |
| 2026-09-10 | 1 | S142 | True |
| 2026-09-11 | 1 | S142 | True |
| 2026-09-13 | 1 | S142 | True |
| 2026-09-14 | 2 | S124, S142 | False |
| 2026-09-15 | 1 | S128 | False |
| 2026-09-16 | 1 | S142 | True |
| 2026-09-18 | 2 | S128, S142 | False |
| 2026-09-19 | 2 | S128, S142 | False |
| 2026-09-20 | 2 | S142, S910 | False |
| 2026-09-21 | 3 | S128, S137, S142 | False |
| 2026-09-23 | 1 | S128 | False |
| 2026-09-24 | 4 | S126, S128, S142, S147 | False |
| 2026-09-25 | 3 | S128, S142, S147 | False |
| 2026-09-26 | 4 | S128, S135, S142, S147 | False |
| 2026-09-29 | 1 | S147 | False |
| 2026-09-30 | 6 | S128, S131, S135, S142, S143, S147 | False |
| 2026-10-01 | 1 | S147 | False |
| 2026-10-02 | 2 | S135, S142 | False |
| 2026-10-03 | 1 | S142 | True |
| 2026-10-04 | 1 | S142 | True |
| 2026-10-05 | 1 | S142 | True |
| 2026-10-06 | 1 | S142 | True |
| 2026-10-07 | 1 | S142 | True |
| 2026-10-10 | 1 | S142 | True |
| 2026-10-11 | 1 | S142 | True |
| 2026-10-13 | 2 | S135, S142 | False |
| 2026-10-16 | 4 | S124, S135, S142, S146 | False |
| 2026-10-18 | 3 | S135, S142, S146 | False |
| 2026-10-19 | 2 | S142, S147 | False |

High station-days per station in the window:

| station_id | name | high_station_days |
|---|---|---|
| S142 | Sentosa Palawan Green | 31 |
| S128 | Bishan Street | 13 |
| S135 | Mandai Wildlife Reserve | 7 |
| S147 | Marina Barrage | 7 |
| S141 | Yio Chu Kang Stadium | 3 |
| S124 | Upper Changi Road North | 2 |
| S146 | Jalan Bahar | 2 |
| S126 | Old Chua Chu Kang Road | 1 |
| S131 | Hougang Stadium | 1 |
| S137 | Sakra Road | 1 |
| S143 | Punggol North | 1 |
| S910 | Outward Bound Singapore(East Coast) | 1 |
