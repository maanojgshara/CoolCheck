# Check 10: NEA 24-hour forecast (data.gov.sg)

Endpoint `https://api-open.data.gov.sg/v2/real-time/api/twenty-four-hr-forecast`, unauthenticated. Script: `scripts/checks/check10_forecast_history.py`. Date `date=YYYY-MM-DD`.

## Q1. Schema and granularity

No-date call: HTTP 200, 1 record(s); top-level keys of the body: ['code', 'data', 'errorMsg'], data keys: ['records'].

Leaf paths of one record (`[]` = list element):

| path | type | example |
|---|---|---|
| `date` | str | `2026-10-20` |
| `timestamp` | str | `2026-10-20T11:33:00+08:00` |
| `updatedTimestamp` | str | `2026-10-20T11:40:50+08:00` |
| `general.validPeriod.start` | str | `2026-10-20T12:00:00+08:00` |
| `general.validPeriod.end` | str | `2026-10-21T12:00:00+08:00` |
| `general.validPeriod.text` | str | `12 PM 20 Oct to 12 PM 21 Oct` |
| `general.temperature.high` | int | `34` |
| `general.temperature.low` | int | `25` |
| `general.temperature.unit` | str | `Degrees Celsius` |
| `general.relativeHumidity.high` | int | `95` |
| `general.relativeHumidity.low` | int | `60` |
| `general.relativeHumidity.unit` | str | `Percentage` |
| `general.wind.direction` | str | `SE` |
| `general.wind.speed.low` | int | `10` |
| `general.wind.speed.high` | int | `20` |
| `general.forecast.code` | str | `TL` |
| `general.forecast.text` | str | `Thundery Showers` |
| `periods[].regions.east.code` | str | `TL` |
| `periods[].regions.east.text` | str | `Thundery Showers` |
| `periods[].regions.west.code` | str | `TL` |
| `periods[].regions.west.text` | str | `Thundery Showers` |
| `periods[].regions.north.code` | str | `TL` |
| `periods[].regions.north.text` | str | `Thundery Showers` |
| `periods[].regions.south.code` | str | `CL` |
| `periods[].regions.south.text` | str | `Cloudy` |
| `periods[].regions.central.code` | str | `CL` |
| `periods[].regions.central.text` | str | `Cloudy` |
| `periods[].timePeriod.text` | str | `Midday to 6 pm 20 Oct` |
| `periods[].timePeriod.start` | str | `2026-10-20T12:00:00+08:00` |
| `periods[].timePeriod.end` | str | `2026-10-20T18:00:00+08:00` |

Answer:
- Temperature/humidity paths under `general` (island-wide): ['general.temperature.high', 'general.temperature.low', 'general.temperature.unit', 'general.relativeHumidity.high', 'general.relativeHumidity.low', 'general.relativeHumidity.unit']
- Temperature/humidity paths under `periods` (per region): none
- Regions present: ['central', 'east', 'north', 'south', 'west']; fields per region: ['code', 'text']
- Numeric fields anywhere under `periods`: none
- **Verdict from this record: island-wide low/high only; regional fields carry forecast text/code, no temperature or humidity.**

## Date check (every call that used `date=`)

| phase | dates requested | OK | PARTIAL | EMPTY | MISMATCH | ERROR |
|---|---|---|---|---|---|---|
| 0 probe | 1 | 1 | 0 | 0 | 0 | 0 |
| 2 date check + bisect | 15 | 9 | 0 | 0 | 0 | 6 |
| 3 midnight probe | 4 | 4 | 0 | 0 | 0 | 0 |
| 4 sample 2023-01 to today | 184 | 180 | 0 | 0 | 0 | 4 |
| 6 sample before 2023 (1/month) | 45 | 45 | 0 | 0 | 0 | 0 |
| **total** | 249 | 239 | 0 | 0 | 0 | 10 |

OK = every returned record's own `date` equals the requested date. PARTIAL = requested date plus other dates. EMPTY = HTTP 200, zero records. MISMATCH = records returned, none for the requested date (API ignoring `date=` or returning the latest forecast). ERROR = non-200.

ERROR breakdown (HTTP code, message): (404, 'Data not found'): 10. The API signals a date with no data by HTTP 404, not by an empty 200 (EMPTY count above).

Non-OK, non-EMPTY examples (first 10):
- 2016-01-01: ERROR (HTTP 404) Data not found
- 2016-02-15: ERROR (HTTP 404) Data not found
- 2016-03-02: ERROR (HTTP 404) Data not found
- 2016-03-09: ERROR (HTTP 404) Data not found
- 2016-03-13: ERROR (HTTP 404) Data not found
- 2016-03-15: ERROR (HTTP 404) Data not found
- 2023-01-03: ERROR (HTTP 404) Data not found
- 2023-04-21: ERROR (HTTP 404) Data not found
- 2023-05-12: ERROR (HTTP 404) Data not found
- 2024-01-03: ERROR (HTTP 404) Data not found

## Q2. History depth

- Earliest date with records: **2016-03-16** (days 1, 7 and 30 before it are absent (consistent with a clean start)).
- Bisect probes (date: status): 2021-05-11: OK, 2018-09-05: OK, 2017-05-04: OK, 2016-09-01: OK, 2016-05-02: OK, 2016-03-02: ERROR, 2016-04-01: OK, 2016-03-17: OK, 2016-03-09: ERROR, 2016-03-13: ERROR, 2016-03-15: ERROR, 2016-03-16: OK
- Neighbour probes before it: 2016-03-15: ERROR, 2016-03-09: ERROR, 2016-02-15: ERROR

| year | months | all samples have records | some samples empty | no sample has records | not sampled |
|---|---|---|---|---|---|
| 2016 | 10 | 5 | 0 | 0 | 5 |
| 2017 | 12 | 6 | 0 | 0 | 6 |
| 2018 | 12 | 7 | 0 | 0 | 5 |
| 2019 | 12 | 7 | 0 | 0 | 5 |
| 2020 | 12 | 6 | 0 | 0 | 6 |
| 2021 | 12 | 7 | 0 | 0 | 5 |
| 2022 | 12 | 7 | 0 | 0 | 5 |
| 2023 | 12 | 9 | 3 | 0 | 0 |
| 2024 | 12 | 11 | 1 | 0 | 0 |
| 2025 | 12 | 12 | 0 | 0 | 0 |
| 2026 | 10 | 10 | 0 | 0 | 0 |

**Jan 2023 to Oct 2026: 42 of 46 months have records on every sampled day** (4 days/month; Oct 2026 is sampled only up to 2026-10-19).
- Months in that window that are not full: 2023-01 (partial), 2023-04 (partial), 2023-05 (partial), 2024-01 (partial)
- Zero-record months on or after the start month (gaps): none
- Partially covered months (some sampled days empty): 2023-01, 2023-04, 2023-05, 2024-01
- Sampled days after the start with no data: 4: 2023-01-03 (ERROR 404), 2023-04-21 (ERROR 404), 2023-05-12 (ERROR 404), 2024-01-03 (ERROR 404); sampled days in Jan 2023 to today: 184.
- Before 2023: 46 of 82 months sampled, 1 day each, because of the call cap; 36 not sampled. A single empty sample is weak evidence of a gap.

## Q3. Issue times

Issue time used: `timestamp`, converted to Asia/Singapore. 25 days (13 in 2025, 12 in 2026), chosen evenly from the days sampled in Q2; 8 fall on a weekend. `date=` placement rule: issue date, D only.

| day | dow | records under date= | issue times SGT (timestamp) | last issue ≤ 21:00 SGT |
|---|---|---|---|---|
| 2025-01-03 | Fri | 8 | 05:32, 09:16, 09:21, 11:35, 17:37, 20:11, 20:32, 23:01 | 20:32 |
| 2025-02-03 | Mon | 7 | 05:31, 11:38, 16:17, 17:18, 17:54, 19:31, 23:02 | 19:31 |
| 2025-03-03 | Mon | 9 | 05:31, 06:05, 07:05, 09:16, 11:32, 16:23, 17:37, 18:51, 23:00 | 18:51 |
| 2025-04-03 | Thu | 11 | 01:10, 01:58, 02:56, 03:27, 03:34, 05:30, 11:32, 17:33, 19:50, 21:08, … (+1) | 19:50 |
| 2025-05-03 | Sat | 14 | 05:39, 08:51, 09:19, 10:10, 13:26, 14:27, 15:19, 16:06, 17:02, 17:10, … (+4) | 17:41 |
| 2025-06-03 | Tue | 8 | 05:30, 09:45, 11:20, 11:38, 13:28, 14:51, 17:33, 23:00 | 17:33 |
| 2025-07-03 | Thu | 10 | 05:30, 11:33, 13:56, 16:38, 17:31, 19:27, 19:55, 20:30, 20:41, 23:01 | 20:41 |
| 2025-07-31 | Thu | 7 | 05:30, 09:24, 11:32, 14:55, 18:21, 18:32, 23:02 | 18:32 |
| 2025-08-31 | Sun | 5 | 05:30, 11:31, 13:34, 17:36, 23:00 | 17:36 |
| 2025-09-30 | Tue | 12 | 05:30, 07:48, 11:31, 14:23, 14:41, 15:30, 16:02, 16:31, 17:36, 17:39, … (+2) | 18:57 |
| 2025-10-31 | Fri | 6 | 05:30, 11:40, 15:10, 17:31, 18:10, 23:00 | 18:10 |
| 2025-11-30 | Sun | 6 | 05:30, 08:36, 11:44, 17:16, 17:36, 23:00 | 17:36 |
| 2025-12-31 | Wed | 10 | 05:31, 09:00, 11:32, 14:07, 15:54, 17:34, 18:50, 20:04, 21:24, 23:04 | 20:04 |
| 2026-01-03 | Sat | 6 | 05:30, 08:01, 11:34, 17:31, 17:40, 23:00 | 17:40 |
| 2026-02-03 | Tue | 4 | 05:32, 11:30, 17:32, 23:00 | 17:32 |
| 2026-02-28 | Sat | 6 | 05:30, 11:30, 15:31, 16:28, 17:31, 23:00 | 17:31 |
| 2026-03-31 | Tue | 5 | 05:30, 11:30, 14:27, 15:59, 23:02 | 15:59 |
| 2026-04-30 | Thu | 5 | 05:30, 11:30, 16:05, 16:39, 23:32 | 16:39 |
| 2026-05-22 | Fri | 7 | 05:37, 05:57, 09:19, 11:32, 14:20, 15:35, 23:30 | 15:35 |
| 2026-06-21 | Sun | 4 | 05:33, 11:33, 14:47, 23:31 | 14:47 |
| 2026-07-12 | Sun | 8 | 05:31, 07:43, 10:34, 10:44, 12:02, 15:06, 16:22, 23:30 | 16:22 |
| 2026-08-12 | Wed | 4 | 05:30, 11:31, 17:32, 23:30 | 17:32 |
| 2026-09-12 | Sat | 6 | 05:32, 10:33, 10:40, 11:30, 17:31, 23:32 | 17:31 |
| 2026-09-30 | Wed | 11 | 05:31, 08:35, 08:55, 11:31, 16:05, 16:15, 17:31, 18:32, 19:10, 19:38, … (+1) | 19:38 |
| 2026-10-19 | Mon | 6 | 05:32, 07:37, 11:35, 16:47, 17:37, 23:30 | 17:37 |

**Records per day (Q3 days):** min 4, max 14, median 7, mean 7.4; distribution {4: 3, 5: 3, 6: 6, 7: 3, 8: 3, 9: 1, 10: 2, 11: 2, 12: 1, 14: 1}.

All sampled OK days in 2025–2026 (90): min 3, max 14, mean 7.3.

**All 180 sampled OK days from Jan 2023 (not just the Q3 25) with no issue at or before 21:00 SGT: 2023-02-20.**

**Records per day by year, all sampled OK days from Jan 2023:**

| year | sampled OK days | records/day min | mean | max | days with no issue ≤ 21:00 SGT |
|---|---|---|---|---|---|
| 2023 | 45 | 1 | 8.1 | 14 | 1 |
| 2024 | 47 | 5 | 8.6 | 17 | 0 |
| 2025 | 48 | 4 | 8.3 | 14 | 0 |
| 2026 | 40 | 3 | 6.1 | 11 | 0 |

**Distribution of issue hour (SGT) over the Q3 days:**

| hour | records | days with ≥1 |
|---|---|---|
| 01:00 | 2 | 1 |
| 02:00 | 1 | 1 |
| 03:00 | 2 | 1 |
| 05:00 | 26 | 25 |
| 06:00 | 1 | 1 |
| 07:00 | 4 | 4 |
| 08:00 | 5 | 4 |
| 09:00 | 8 | 7 |
| 10:00 | 5 | 3 |
| 11:00 | 24 | 23 |
| 12:00 | 1 | 1 |
| 13:00 | 4 | 4 |
| 14:00 | 9 | 8 |
| 15:00 | 8 | 8 |
| 16:00 | 13 | 10 |
| 17:00 | 25 | 19 |
| 18:00 | 7 | 6 |
| 19:00 | 6 | 4 |
| 20:00 | 5 | 3 |
| 21:00 | 3 | 3 |
| 22:00 | 1 | 1 |
| 23:00 | 25 | 25 |

**Days with no issue at or before 21:00 SGT: none** (of 25); so there is always one in this sample.
Using `updatedTimestamp` instead changes the last-before-21:00 time on 25 of 25 days: 2025-01-03, 2025-02-03, 2025-03-03, 2025-04-03, 2025-05-03, 2025-06-03, 2025-07-03, 2025-07-31.

### Which timestamp is the issue time

| day | timestamp | updatedTimestamp | updated − timestamp |
|---|---|---|---|
| 2025-01-03 | 2025-01-03T23:01:00+08:00 | 2025-01-03T23:10:47+08:00 | 10 min |
| 2025-03-03 | 2025-03-03T05:31:00+08:00 | 2025-03-03T05:40:46+08:00 | 10 min |
| 2025-05-03 | 2025-05-03T09:19:00+08:00 | 2025-05-03T09:30:48+08:00 | 12 min |
| 2025-07-31 | 2025-07-31T18:21:00+08:00 | 2025-07-31T18:30:57+08:00 | 10 min |
| 2025-10-31 | 2025-10-31T18:10:00+08:00 | 2025-10-31T18:20:50+08:00 | 11 min |
| 2026-01-03 | 2026-01-03T17:31:00+08:00 | 2026-01-03T17:40:40+08:00 | 10 min |
| 2026-04-30 | 2026-04-30T05:30:00+08:00 | 2026-04-30T05:41:10+08:00 | 11 min |
| 2026-08-12 | 2026-08-12T05:30:00+08:00 | 2026-08-12T05:41:15+08:00 | 11 min |

Over 185 Q3 records: updated − timestamp min 3, max 191, median 10 min; `timestamp` on the hour in 11, `updatedTimestamp` on the hour in 11.

Over all 1460 sampled records from 2023: updated − timestamp median 11 min, 95th percentile 695921 min, max 552.7 days; more than 1 hour: 595; more than 1 day: 590; negative: 0.

**Treated as the issue time: `timestamp`.** It is the forecast's own time and clusters at NEA's scheduled issue times (about 05:30, 11:30, 17:30 and 23:00/23:30 SGT, plus ad-hoc updates in between). `updatedTimestamp` is when the record was last written: typically about 10 minutes after `timestamp`, but it can be much later (see the lag figures above and the midnight example), so it would date a past forecast to a time it was not yet available. `timestamp` can be a few minutes earlier than the public release, so a cut-off should leave a margin.

### Does `date=` filter by issue date or validity date?

Across 657 records on sampled 2025–2026 days (issue time = `timestamp`): record `date` field = requested date in 657; issue date in SGT = requested date in 657; issue date in UTC = requested date in 512; `validPeriod.start` date in SGT = requested date in 540.

- **last before midnight**: requested `date=2024-06-03`, record `date` = 2024-06-03, timestamp 2024-06-03T23:54:00+08:00, updatedTimestamp 2024-07-17T16:35:31+08:00, issue SGT 2024-06-03 23:54, validPeriod 2024-06-04 00:00 to 2024-06-05 00:00 SGT. The same record also appears under D−1: False; under D+1: False.
- **first after midnight**: requested `date=2024-09-21`, record `date` = 2024-09-21, timestamp 2024-09-21T00:05:00+08:00, updatedTimestamp 2024-09-21T00:11:13+08:00, issue SGT 2024-09-21 00:05, validPeriod 2024-09-22 00:00 to 2024-09-23 00:00 SGT. The same record also appears under D−1: False; under D+1: False.

Rule for the 21:00 analysis: records are filed under their SGT issue date; D only.

## Cut-off follow-up: 23:xx issues and validity by issue slot

### 1. Is there a 23:00–23:59 SGT issue? (180 sampled OK days from Jan 2023, issue time = `timestamp`)

Days with one: 177; days without: **3**: 2023-03-31, 2023-05-31, 2026-10-08.

### 2. Does the validPeriod cover tomorrow 06:00–18:00 SGT in full?

Slots by SGT issue time: 05:30 = 05:25–05:44, 11:30 = 11:25–11:44, 17:30 = 17:25–17:44, 23:xx = 23:00–23:59, everything else = ad-hoc (a heuristic grouping). 'Tomorrow' is the day after the issue date. Records with an unparsable validPeriod are excluded (0).

| issue slot | records | cover tomorrow 06–18 in full | share |
|---|---|---|---|
| 05:30 | 170 | 3 | 2% |
| 11:30 | 161 | 0 | 0% |
| 17:30 | 149 | 145 | 97% |
| 23:xx | 181 | 179 | 99% |
| ad-hoc | 754 | 218 | 29% |
| **all records** | 1415 | 545 | 39% |

**'Last issue ≤ 21:00 SGT' record, per day (179 days): 161 cover tomorrow 06:00–18:00 in full (90%).** By slot of that last issue:

| slot of the last issue ≤ 21:00 | days | cover in full | share |
|---|---|---|---|
| 05:30 | 0 | 0 | n/a |
| 11:30 | 4 | 0 | 0% |
| 17:30 | 78 | 78 | 100% |
| 23:xx | 0 | 0 | n/a |
| ad-hoc | 97 | 83 | 86% |

**23:xx issues: 179 of 181 cover tomorrow 06:00–18:00 in full (99%).**

Most common validPeriod patterns by slot (start → end, as day offset from the issue date and SGT time):

| slot | validPeriod pattern | records |
|---|---|---|
| 05:30 | +0d 06:00 → +1d 06:00 | 165 |
| 05:30 | +0d 06:00 → -364d 06:00 | 2 |
| 05:30 | +0d 06:00 → +2d 06:00 | 1 |
| 11:30 | +0d 12:00 → +1d 12:00 | 158 |
| 11:30 | +0d 12:00 → -364d 12:00 | 2 |
| 11:30 | +0d 06:00 → +1d 06:00 | 1 |
| 17:30 | +0d 18:00 → +1d 18:00 | 145 |
| 17:30 | +0d 12:00 → +1d 12:00 | 3 |
| 17:30 | +0d 18:00 → -364d 18:00 | 1 |
| 23:xx | +1d 00:00 → +2d 00:00 | 131 |
| 23:xx | +1d 00:00 → +3d 00:00 | 47 |
| 23:xx | -364d 00:00 → -363d 00:00 | 2 |
| ad-hoc | +0d 12:00 → +1d 12:00 | 281 |
| ad-hoc | +0d 06:00 → +1d 06:00 | 238 |
| ad-hoc | +0d 18:00 → +1d 18:00 | 168 |

## Cut-off rule: latest issue at or before CUT that covers tomorrow 06:00–18:00 SGT in full

Tested on 180 sampled OK days from Jan 2023 (issue time = `timestamp`). Hours are from the chosen issue to tomorrow 06:00 SGT.

| CUT | days with such a record | slot mix of the chosen record | hours to tomorrow 06:00 (min / median / max) |
|---|---|---|---|
| 20:45 | 164 of 180 | 05:30: 1, 17:30: 80, ad-hoc: 83 | 9.3 / 12.3 / 25.1 |
| 21:00 | 165 of 180 | 05:30: 1, 17:30: 78, ad-hoc: 86 | 9.2 / 12.2 / 25.1 |
| 23:59 | 179 of 180 | 17:30: 2, 23:xx: 175, ad-hoc: 2 | 6.1 / 7.0 / 12.5 |

- CUT 20:45: days with none (16): 2023-02-20, 2023-11-21, 2023-12-31, 2026-03-12, 2026-03-31, 2026-04-12, 2026-04-21, 2026-04-30, 2026-05-03, 2026-05-12, 2026-05-22, 2026-05-31, 2026-06-03, 2026-06-21, 2026-07-03, 2026-07-12
- CUT 21:00: days with none (15): 2023-02-20, 2023-12-31, 2026-03-12, 2026-03-31, 2026-04-12, 2026-04-21, 2026-04-30, 2026-05-03, 2026-05-12, 2026-05-22, 2026-05-31, 2026-06-03, 2026-06-21, 2026-07-03, 2026-07-12
- CUT 23:59: days with none (1): 2023-12-31

Days with no qualifying record, by year:

| year | sampled OK days | none at 20:45 | none at 21:00 | none at 23:59 |
|---|---|---|---|---|
| 2023 | 45 | 3 | 2 | 1 |
| 2024 | 47 | 0 | 0 | 0 |
| 2025 | 48 | 0 | 0 | 0 |
| 2026 | 40 | 13 | 13 | 0 |

**Compared with CUT = 20:45:**

| CUT | days with a record under both | of which a different record is chosen | days with none at 20:45 but one at this CUT |
|---|---|---|---|
| 21:00 | 164 | 2 | 1 |
| 23:59 | 164 | 161 | 15 |

## Reconciling 1,415 vs 1,460 records, and records whose validPeriod ends before it starts

The lag statistic (`updated − timestamp`) counted every record on every fetched day from 2023 that is OK or PARTIAL, in any phase, without deduplication. The slot tables count only the sampled-OK days of phase 4 (sample 2023-01 to today), deduplicated per day, with a parsable validPeriod.

| item | records |
|---|---|
| Lag-statistic basis (all phases, from 2023) | 1460 |
| − phase '0 probe' (not part of the phase-4 sample) | 3 |
| − phase '2 date check + bisect' (not part of the phase-4 sample) | 10 |
| − phase '3 midnight probe' (not part of the phase-4 sample) | 32 |
| − duplicates inside phase-4 days (same timestamp and updatedTimestamp) | 0 |
| − phase-4 records with an unparsable validPeriod | 0 |
| − other (e.g. unparsable `timestamp`) | 0 |
| **= slot-table basis** | 1415 |

Phase-4 records before deduplication: 1415.

**Records whose validPeriod.end is before validPeriod.start: 12** (in the slot-table basis).

| day (`date`) | issue time SGT | validPeriod.start | validPeriod.end |
|---|---|---|---|
| 2023-12-31 | 2023-12-31 05:38 | 2023-12-31 06:00 | 2023-01-01 06:00 |
| 2023-12-31 | 2023-12-31 07:20 | 2023-12-31 06:00 | 2023-01-01 06:00 |
| 2023-12-31 | 2023-12-31 07:46 | 2023-12-31 06:00 | 2023-01-01 06:00 |
| 2023-12-31 | 2023-12-31 11:32 | 2023-12-31 12:00 | 2023-01-01 12:00 |
| 2023-12-31 | 2023-12-31 17:33 | 2023-12-31 18:00 | 2023-01-01 18:00 |
| 2023-12-31 | 2023-12-31 18:25 | 2023-12-31 18:00 | 2023-01-01 18:00 |
| 2023-12-31 | 2023-12-31 21:00 | 2023-12-31 18:00 | 2023-01-01 18:00 |
| 2025-12-31 | 2025-12-31 05:31 | 2025-12-31 06:00 | 2025-01-01 06:00 |
| 2025-12-31 | 2025-12-31 09:00 | 2025-12-31 06:00 | 2025-01-01 06:00 |
| 2025-12-31 | 2025-12-31 11:32 | 2025-12-31 12:00 | 2025-01-01 12:00 |
| 2025-12-31 | 2025-12-31 14:07 | 2025-12-31 12:00 | 2025-01-01 12:00 |
| 2025-12-31 | 2025-12-31 15:54 | 2025-12-31 12:00 | 2025-01-01 12:00 |

## One complete raw record

First record of the no-date (latest) call; public data, unmodified.

```json
{
  "date": "2026-10-20",
  "timestamp": "2026-10-20T11:33:00+08:00",
  "updatedTimestamp": "2026-10-20T11:40:50+08:00",
  "general": {
    "validPeriod": {
      "start": "2026-10-20T12:00:00+08:00",
      "end": "2026-10-21T12:00:00+08:00",
      "text": "12 PM 20 Oct to 12 PM 21 Oct"
    },
    "temperature": {
      "high": 34,
      "low": 25,
      "unit": "Degrees Celsius"
    },
    "relativeHumidity": {
      "high": 95,
      "low": 60,
      "unit": "Percentage"
    },
    "wind": {
      "direction": "SE",
      "speed": {
        "low": 10,
        "high": 20
      }
    },
    "forecast": {
      "code": "TL",
      "text": "Thundery Showers"
    }
  },
  "periods": [
    {
      "regions": {
        "east": {
          "code": "TL",
          "text": "Thundery Showers"
        },
        "west": {
          "code": "TL",
          "text": "Thundery Showers"
        },
        "north": {
          "code": "TL",
          "text": "Thundery Showers"
        },
        "south": {
          "code": "CL",
          "text": "Cloudy"
        },
        "central": {
          "code": "CL",
          "text": "Cloudy"
        }
      },
      "timePeriod": {
        "text": "Midday to 6 pm 20 Oct",
        "start": "2026-10-20T12:00:00+08:00",
        "end": "2026-10-20T18:00:00+08:00"
      }
    },
    {
      "regions": {
        "east": {
          "code": "CL",
          "text": "Cloudy"
        },
        "west": {
          "code": "CL",
          "text": "Cloudy"
        },
        "north": {
          "code": "CL",
          "text": "Cloudy"
        },
        "south": {
          "code": "CL",
          "text": "Cloudy"
        },
        "central": {
          "code": "CL",
          "text": "Cloudy"
        }
      },
      "timePeriod": {
        "text": "6 pm 20 Oct to 6 am 21 Oct",
        "start": "2026-10-20T18:00:00+08:00",
        "end": "2026-10-21T06:00:00+08:00"
      }
    },
    {
      "regions": {
        "east": {
          "code": "CL",
          "text": "Cloudy"
        },
        "west": {
          "code": "CL",
          "text": "Cloudy"
        },
        "north": {
          "code": "CL",
          "text": "Cloudy"
        },
        "south": {
          "code": "CL",
          "text": "Cloudy"
        },
        "central": {
          "code": "CL",
          "text": "Cloudy"
        }
      },
      "timePeriod": {
        "text": "6 am to Midday 21 Oct",
        "start": "2026-10-21T06:00:00+08:00",
        "end": "2026-10-21T12:00:00+08:00"
      }
    }
  ]
}
```

## Calls, range and limits

| phase | network calls |
|---|---|
| **total** | 0 |

Report regenerated from the cache (250 cache reads, 0 new calls). The figures below are from the live run:
| phase | network calls |
|---|---|
| 0 probe | 2 |
| 2 date check + bisect | 17 |
| 3 midnight probe | 5 |
| 4 sample 2023-01 to today | 215 |
| 6 sample before 2023 (1/month) | 52 |
| **total** | 291 |

**Caveat: the live-run call counts above were hand-copied from the first run's printed report, not machine-logged** (that run predates the stats file).

- Network calls: 291 (cap 300); of which retries after 429/403/5xx/connection errors: 41. HTTP status counts: {'200': 240, '404': 10, '429': 41}.
- Dates requested with `date=`: 249, from 2016-01-01 to 2026-10-20.
- Live run time: 2026-10-20 12:34 SGT (copied from the first run's printed report). No key or token was used. Stop reason: none, ran to completion.

**Not tested:**
- Whether an API key changes history depth, pagination or rate limits.
- Days not sampled: Q2 checks 4 days/month from Jan 2023 and 1 day/month before; a month listed as full can still have missing days.
- Whether past records are the originally issued forecasts or were later revised or backfilled.
- Forecast values or accuracy; the 2-hour and 4-day forecast endpoints.
- Whether the issue pattern seen on sampled days holds on other days or in the future (only ~25 days examined for Q3).
- Issue-time behaviour on days when the 21:00 forecast was late or missing beyond the sampled days.

