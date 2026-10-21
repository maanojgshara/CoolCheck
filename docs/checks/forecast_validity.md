# Forecast validity recount (Day 2 step 3)

Generated 2026-10-21 17:27 SGT by `scripts/checks/forecast_validity.py` from the raw backfill files (`coolcheck-data/raw/forecast/`, 641 files, 2025-01-16 to 2026-10-19; no file for 2025-07-20, NEA returned no data). 4,673 records (4,673 distinct issue time and updatedTimestamp pairs). Issue time = `timestamp` (§14.4).

## 1. The notes' definition: validity end before the start

**6 records** in these files have `validPeriod.end` before `validPeriod.start`.
| file | issue time (SGT) | updatedTimestamp | validPeriod.start | validPeriod.end | text |
|---|---|---|---|---|---|
| forecast_2025-12-30.jsonl | 2025-12-30 23:00 | 2025-12-30T23:10:47+08:00 | 2025-12-31 00:00 | 2025-01-02 00:00 | 0 AM 31 Dec to 0 AM 1 Jan |
| forecast_2025-12-31.jsonl | 2025-12-31 05:31 | 2025-12-31T05:40:47+08:00 | 2025-12-31 06:00 | 2025-01-01 06:00 | 6 AM 31 Dec to 6 AM 1 Jan |
| forecast_2025-12-31.jsonl | 2025-12-31 09:00 | 2025-12-31T09:11:01+08:00 | 2025-12-31 06:00 | 2025-01-01 06:00 | 6 AM 31 Dec to 6 AM 1 Jan |
| forecast_2025-12-31.jsonl | 2025-12-31 11:32 | 2025-12-31T11:40:58+08:00 | 2025-12-31 12:00 | 2025-01-01 12:00 | 12 PM 31 Dec to 12 PM 1 Jan |
| forecast_2025-12-31.jsonl | 2025-12-31 14:07 | 2025-12-31T14:10:52+08:00 | 2025-12-31 12:00 | 2025-01-01 12:00 | 12 PM 31 Dec to 12 PM 1 Jan |
| forecast_2025-12-31.jsonl | 2025-12-31 15:54 | 2025-12-31T16:00:41+08:00 | 2025-12-31 12:00 | 2025-01-01 12:00 | 12 PM 31 Dec to 12 PM 1 Jan |

By month of issue: 2025-12 6.

The notes' 12 are placed on 31 Dec 2023 and 31 Dec 2025 (§12.6 item 10, from check 10's API sample since Jan 2023). These files start on 2025-01-16, so they can confirm or refute only the 31 Dec 2025 part; the 31 Dec 2023 part (and any other day before 2025-01-16) cannot be checked from them.

## 2. Wider rule classes (the Silver rules)

| class | records | by month of issue |
|---|---|---|
| end before start (the notes' definition) | 6 | 2025-12 6 |
| end equal to start | 0 | — |
| window not 24 h | 527 | 2025-01 23, 2025-02 33, 2025-03 44, 2025-04 54, 2025-05 57, 2025-06 48, 2025-07 39, 2025-08 43, 2025-09 42, 2025-10 42, 2025-11 55, 2025-12 47 |
|   of which 48 h | 521 | 2025-01 23, 2025-02 33, 2025-03 44, 2025-04 54, 2025-05 57, 2025-06 48, 2025-07 39, 2025-08 43, 2025-09 42, 2025-10 42, 2025-11 55, 2025-12 41 |
| start more than 6 h before or 24 h after the issue | 3 | 2025-12 1, 2026-01 2 |
| text does not parse | 0 | — |
| text disagrees with start/end (day, month, hour; the text has no year) | 522 | 2025-01 23, 2025-02 33, 2025-03 44, 2025-04 54, 2025-05 57, 2025-06 48, 2025-07 39, 2025-08 43, 2025-09 42, 2025-10 42, 2025-11 55, 2025-12 42 |
| record `date` differs from the issue's SGT date | 0 | — |

Window lengths other than 24 and 48 h: -8736 h × 5, -8712 h × 1.

## 3. The 521 records with a 48-hour window

By issue slot (SGT time of `timestamp`; 05:30 = 05:25–05:44, 11:30 = 11:25–11:44, 17:30 = 17:25–17:44, 23:xx = 23:00–23:59, else ad-hoc):

| slot | 48-h records | all records in the slot | share |
|---|---|---|---|
| 05:30 | 3 | 624 | 0% |
| 11:30 | 0 | 593 | 0% |
| 17:30 | 0 | 479 | 0% |
| 23:xx | 358 | 653 | 55% |
| ad-hoc | 160 | 2324 | 7% |

By month of issue:

| month | 48-h records | all records |
|---|---|---|
| 2025-01 | 23 | 126 |
| 2025-02 | 33 | 209 |
| 2025-03 | 44 | 266 |
| 2025-04 | 54 | 278 |
| 2025-05 | 57 | 282 |
| 2025-06 | 48 | 227 |
| 2025-07 | 39 | 220 |
| 2025-08 | 43 | 244 |
| 2025-09 | 42 | 237 |
| 2025-10 | 42 | 235 |
| 2025-11 | 55 | 243 |
| 2025-12 | 41 | 235 |
| 2026-01 | 0 | 193 |
| 2026-02 | 0 | 204 |
| 2026-03 | 0 | 155 |
| 2026-04 | 0 | 173 |
| 2026-05 | 0 | 186 |
| 2026-06 | 0 | 174 |
| 2026-07 | 0 | 212 |
| 2026-08 | 0 | 225 |
| 2026-09 | 0 | 230 |
| 2026-10 | 0 | 119 |

What validPeriod.text says for them:

| text | records |
|---|---|
| text says 24 h; start agrees; end differs | 521 |

Text forms (digits as N): `N AM N May to N AM N May` × 56, `N AM N Apr to N AM N Apr` × 54, `N AM N Nov to N AM N Nov` × 54, `N AM N Mar to N AM N Mar` × 42, `N AM N Dec to N AM N Dec` × 42, `N AM N Aug to N AM N Aug` × 41.

First five, as examples:

| file | issue (SGT) | start | end | text |
|---|---|---|---|---|
| forecast_2025-01-16.jsonl | 2025-01-16 03:33 | 2025-01-17 00:00 | 2025-01-19 00:00 | 0 AM 17 Jan to 0 AM 18 Jan |
| forecast_2025-01-16.jsonl | 2025-01-16 23:08 | 2025-01-17 00:00 | 2025-01-19 00:00 | 0 AM 17 Jan to 0 AM 18 Jan |
| forecast_2025-01-17.jsonl | 2025-01-17 23:03 | 2025-01-18 00:00 | 2025-01-20 00:00 | 0 AM 18 Jan to 0 AM 19 Jan |
| forecast_2025-01-17.jsonl | 2025-01-17 23:11 | 2025-01-18 00:00 | 2025-01-20 00:00 | 0 AM 18 Jan to 0 AM 19 Jan |
| forecast_2025-01-18.jsonl | 2025-01-18 23:11 | 2025-01-19 00:00 | 2025-01-21 00:00 | 0 AM 19 Jan to 0 AM 20 Jan |
## 4. Effect on the 00:15 cut-off rule (§14.4 option B)

Rule: for target day T, the latest issue at or before T 00:15 SGT whose validity covers T 06:00 to 18:00. Target days 2025-01-17 to 2026-10-20 (642 days).

- With the stated validPeriod: no issue on 0 days (none).
- With the validity read from the text: no issue on 1 days.
- The chosen issue is a 48-hour record on 345 days; 345 of those are 23:xx issues.
- The choice differs between stated and text validity on 2 days.

| target day | chosen with stated validity | chosen with text validity |
|---|---|---|
| 2025-07-21 | 07-19 23:02 (48 h) | None |
| 2025-12-31 | 12-30 17:44 (24 h) | 12-30 23:00 |
