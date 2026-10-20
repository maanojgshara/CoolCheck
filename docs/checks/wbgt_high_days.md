# WBGT High days from the backfill (check 9 part B)

Script: `scripts/backfill/wbgt_high_days.py`, reading the raw WBGT files written by `scripts/backfill/backfill.py` (`coolcheck-data/raw/wbgt/backfill` in the data folder beside the repo). No API calls. Generated 2026-10-20 20:18 SGT. Dates are SGT.

## Data read

- Backfill days in the progress file: 642 (2025-01-16 to 2026-10-19); statuses {'short': 21, 'done': 621}.
- Backfill calls (machine-logged in `progress.jsonl`, 1 run(s)): 2,990, of which HTTP 429 427 (14.3%); stops: none; key: ['absent'].
- Files 642, pages (lines) 2,563, records (timestamps) 61,443, station readings 1,036,005 after removing 0 duplicate (datetime, station) pairs.
- Records without a usable `datetime`: 0; readings without a station id: 0; readings whose SGT date differs from their file's date: 0.
- Days without data (HTTP 404, empty or date mismatch): none.
- Short days (fewer than 96 distinct timestamps): 21: 2025-01-16 (2), 2025-01-17 (46), 2025-01-29 (89), 2025-07-09 (95), 2025-08-14 (95), 2025-08-25 (95), 2025-11-18 (89), 2025-11-19 (95), 2025-12-18 (95), 2026-03-23 (95), 2026-03-25 (95), 2026-04-22 (95), 2026-06-05 (93), 2026-07-23 (95), 2026-08-14 (93), 2026-08-19 (94), 2026-08-20 (91), 2026-08-31 (90), 2026-09-14 (95), 2026-09-19 (95), 2026-10-05 (95).

## heatStress values

| value | readings | WBGT min | WBGT max |
|---|---|---|---|
| Low | 989,238 | 14.3 | 30.9 |
| Moderate | 41,780 | 31.0 | 32.9 |
| NA | 2,894 | – | – |
| High | 2,093 | 33.0 | 36.6 |

Counted values: Low, Moderate, High. `NA` readings (2,894) are excluded from station-days. Other values, also excluded: none. High readings without a numeric WBGT: 0.

Boundary from the API's own field: highest Moderate 32.9, lowest High 33.0; the categories do not overlap in value (§12.6 item 11).

## Original 8 stations

List used: S124, S125, S126, S127, S128, S129, S130, S132. Stations with counted readings on the first day (2025-01-16): S124, S125, S126, S127, S128, S129, S130, S132 — matches the list.
The monthly table shows how many of the 8 reported each month; a month with fewer has fewer chances of a High.

## High station-days by window, against the §14.4 rule

§14.4 (Labels): *fewer than about 30 High station-days in the test period means recall on High days is too unstable to quote as three classes*. The windows below are the ones asked for; none of them is yet the agreed test period (D6).

| window | dates covered | days with data | station-days (all) | High station-days (all) | vs rule (all) | High days (all) | station-days (8) | High station-days (8) | vs rule (8) | High days (8) |
|---|---|---|---|---|---|---|---|---|---|---|
| Jan–Jun 2025 | 2025-01-16 – 2025-06-30 | 166 | 1,325 | 44 | at or above 30 | 31 | 1,325 | 44 | at or above 30 | 31 |
| Jul 2025–Aug 2026 | 2025-07-01 – 2026-08-31 | 427 | 8,040 | 421 | at or above 30 | 181 | 3,347 | 106 | at or above 30 | 82 |
| Sep–Oct 2026 | 2026-09-01 – 2026-10-19 | 49 | 1,469 | 70 | at or above 30 | 35 | 342 | 16 | below 30 | 15 |

The last window ends at the backfill's end (2026-10-19), so it is shorter than two months.

## By month

High day = any station reaches High that day. 'all' = every station reporting that month; '8' = only the original 8.

| month | days in range | days with data | short days | stations per day (min–max) | station-days (all) | High station-days (all) | High share (all) | High days (all) | of the 8 reporting | station-days (8) | High station-days (8) | High days (8) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2025-01 | 16 | 16 | 3 | 7–8 | 125 | 1 | 0.8% | 1 | 8 | 125 | 1 | 1 |
| 2025-02 | 28 | 28 | 0 | 8–8 | 224 | 0 | 0.0% | 0 | 8 | 224 | 0 | 0 |
| 2025-03 | 31 | 31 | 0 | 8–8 | 248 | 5 | 2.0% | 4 | 8 | 248 | 5 | 4 |
| 2025-04 | 30 | 30 | 0 | 8–8 | 240 | 13 | 5.4% | 8 | 8 | 240 | 13 | 8 |
| 2025-05 | 31 | 31 | 0 | 8–8 | 248 | 19 | 7.7% | 12 | 8 | 248 | 19 | 12 |
| 2025-06 | 30 | 30 | 0 | 8–8 | 240 | 6 | 2.5% | 6 | 8 | 240 | 6 | 6 |
| 2025-07 | 31 | 31 | 1 | 8–9 | 271 | 12 | 4.4% | 9 | 8 | 248 | 8 | 7 |
| 2025-08 | 31 | 31 | 2 | 9–9 | 279 | 2 | 0.7% | 2 | 8 | 248 | 0 | 0 |
| 2025-09 | 30 | 30 | 0 | 15–15 | 450 | 25 | 5.6% | 17 | 8 | 240 | 3 | 2 |
| 2025-10 | 31 | 31 | 0 | 14–15 | 463 | 32 | 6.9% | 19 | 8 | 248 | 3 | 3 |
| 2025-11 | 30 | 30 | 2 | 15–15 | 450 | 18 | 4.0% | 9 | 8 | 240 | 5 | 2 |
| 2025-12 | 31 | 31 | 1 | 15–15 | 465 | 5 | 1.1% | 4 | 8 | 248 | 1 | 1 |
| 2026-01 | 31 | 31 | 0 | 15–20 | 550 | 0 | 0.0% | 0 | 8 | 248 | 0 | 0 |
| 2026-02 | 28 | 28 | 0 | 19–20 | 558 | 3 | 0.5% | 3 | 8 | 224 | 0 | 0 |
| 2026-03 | 31 | 31 | 2 | 20–20 | 620 | 9 | 1.5% | 5 | 8 | 248 | 3 | 2 |
| 2026-04 | 30 | 30 | 1 | 20–27 | 663 | 82 | 12.4% | 23 | 8 | 240 | 26 | 19 |
| 2026-05 | 31 | 31 | 0 | 27–27 | 837 | 97 | 11.6% | 23 | 8 | 248 | 19 | 14 |
| 2026-06 | 30 | 30 | 1 | 26–27 | 803 | 61 | 7.6% | 23 | 8 | 234 | 19 | 14 |
| 2026-07 | 31 | 31 | 1 | 25–26 | 805 | 33 | 4.1% | 20 | 7 | 216 | 7 | 7 |
| 2026-08 | 31 | 31 | 4 | 26–30 | 826 | 42 | 5.1% | 24 | 7 | 217 | 12 | 11 |
| 2026-09 | 30 | 30 | 2 | 29–30 | 899 | 49 | 5.5% | 22 | 7 | 209 | 15 | 14 |
| 2026-10 | 19 | 19 | 1 | 30–30 | 570 | 21 | 3.7% | 13 | 7 | 133 | 1 | 1 |
| **total** | 642 | 642 | 21 |  | **10,834** | **535** | 4.9% | **247** |  | **5,014** | **166** | **128** |

All-station High days rise partly because the network grew from 8 to about 30 stations: more stations give more chances that one of them reaches High. The original-8 columns hold the station set fixed (as far as those 8 keep reporting).

## By station

| station | name | first day | last day | station-days | High station-days | High share | original 8 |
|---|---|---|---|---|---|---|---|
| S124 | Upper Changi Road North | 2025-01-16 | 2026-10-19 | 641 | 2 | 0.3% | yes |
| S125 | Woodlands Street 13 | 2025-01-16 | 2026-10-19 | 641 | 16 | 2.5% | yes |
| S126 | Old Chua Chu Kang Road | 2025-01-16 | 2026-10-19 | 642 | 35 | 5.5% | yes |
| S127 | Stadium Road | 2025-01-16 | 2026-10-19 | 639 | 20 | 3.1% | yes |
| S128 | Bishan Street | 2025-01-16 | 2026-10-19 | 642 | 79 | 12.3% | yes |
| S129 | Bedok North Street 2 | 2025-01-16 | 2026-10-19 | 642 | 9 | 1.4% | yes |
| S130 | West Coast Road | 2025-01-16 | 2026-06-24 | 525 | 4 | 0.8% | yes |
| S131 | Hougang Stadium | 2026-08-27 | 2026-10-19 | 54 | 1 | 1.9% |  |
| S132 | Jurong West Street 93 | 2025-01-16 | 2026-10-19 | 642 | 1 | 0.2% | yes |
| S133 | Cathay Green | 2026-08-27 | 2026-10-19 | 54 | 0 | 0.0% |  |
| S135 | Bird Paradise | 2026-04-22 | 2026-10-19 | 181 | 23 | 12.7% |  |
| S137 | Sakra Road | 2025-07-09 | 2026-10-19 | 468 | 66 | 14.1% |  |
| S138 | Stirling Road | 2026-08-27 | 2026-10-19 | 54 | 0 | 0.0% |  |
| S139 | Tuas Terminal Gateway | 2025-09-01 | 2026-10-19 | 414 | 0 | 0.0% |  |
| S140 | Choa Chu Kang Stadium | 2025-09-01 | 2026-10-19 | 414 | 0 | 0.0% |  |
| S141 | Yio Chu Kang Stadium | 2025-09-01 | 2026-10-19 | 413 | 19 | 4.6% |  |
| S142 | Sentosa Palawan Green | 2025-09-01 | 2026-10-19 | 414 | 165 | 39.9% |  |
| S143 | Punggol North | 2025-09-01 | 2026-10-19 | 412 | 15 | 3.6% |  |
| S144 | Upper Pickering Street | 2026-01-15 | 2026-10-19 | 278 | 16 | 5.8% |  |
| S145 | MacRitchie Reservoir | 2026-04-22 | 2026-10-19 | 181 | 10 | 5.5% |  |
| S146 | Jalan Bahar | 2026-04-22 | 2026-10-19 | 181 | 3 | 1.7% |  |
| S147 | Marina Barrage | 2026-04-22 | 2026-10-19 | 181 | 20 | 11.0% |  |
| S148 | Pasir Ris Walk | 2026-04-22 | 2026-10-19 | 181 | 1 | 0.6% |  |
| S149 | Tampines Walk | 2026-01-15 | 2026-10-19 | 278 | 0 | 0.0% |  |
| S150 | Evans Road | 2026-01-15 | 2026-10-19 | 278 | 3 | 1.1% |  |
| S151 | Outward Bound Singapore(Pulau ubin) | 2026-04-22 | 2026-10-19 | 181 | 8 | 4.4% |  |
| S153 | Bukit Batok Street 22 | 2026-01-15 | 2026-10-19 | 276 | 4 | 1.4% |  |
| S180 | Taman Jurong Greens | 2026-04-22 | 2026-10-19 | 181 | 2 | 1.1% |  |
| S184 | Sengkang East Avenue | 2026-01-15 | 2026-10-19 | 278 | 7 | 2.5% |  |
| S187 | Bukit Timah(West) | 2025-09-01 | 2026-10-19 | 414 | 5 | 1.2% |  |
| S910 | Outward Bound Singapore(East Coast) | 2026-08-27 | 2026-10-19 | 54 | 1 | 1.9% |  |

Station-by-month counts are in `analysis/wbgt_station_month.csv` in the data folder.

## Not covered

- Whether High days cluster in a way that matters for the back-test split (D6); this report counts, it does not choose.
- Whether three classes are supportable: the §14.4 rule needs the agreed test period, which is not fixed yet.
- Readings revised after publication: the backfill stores what the API returns today.
- Daily labels per planning area (nearest station, D5): Day 2 Silver work.
