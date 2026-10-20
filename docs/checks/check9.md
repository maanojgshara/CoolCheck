# Check 9 part A: WBGT and rainfall feeds (data.gov.sg)

Unauthenticated calls. Script: `scripts/checks/check9_wbgt_rainfall.py`. Dates are SGT unless stated.

## Endpoints

The WBGT endpoint is not stated in `DAISI.md`, `CoolCheck Project.md` or `smoke/` (grep found only the air-temperature path in `smoke/hello.py`), so candidates were tried in order until one returned readings:

| candidate | HTTP | readings on page | data keys |
|---|---|---|---|
| `https://api-open.data.gov.sg/v2/real-time/api/weather?api=wbgt` | 200 | 1 | ['records'] |

- **WBGT: `https://api-open.data.gov.sg/v2/real-time/api/weather` with `{'api': 'wbgt'}`**; **rainfall: `https://api-open.data.gov.sg/v2/real-time/api/rainfall`**.

## Response structure (latest call, no `date=`)

### wbgt

`data` keys: ['records']; readings on the first page: 1; `stations` in metadata: 30; paginationToken present: False.

| path | type | example |
|---|---|---|
| `records[].datetime` | str | `2026-10-20T14:45:00+08:00` |
| `records[].item.type` | str | `observation` |
| `records[].item.isStationData` | bool | `True` |
| `records[].item.readings[].station.id` | str | `S124` |
| `records[].item.readings[].station.name` | str | `Upper Changi Road North` |
| `records[].item.readings[].station.townCenter` | str | `Changi Meteorological Station` |
| `records[].item.readings[].location.latitude` | str | `1.36777` |
| `records[].item.readings[].location.longitude` | str | `103.982262` |
| `records[].item.readings[].wbgt` | str | `30.1` |
| `records[].item.readings[].heatStress` | str | `Low` |
| `records[].updatedTimestamp` | str | `2026-10-20T14:55:04+08:00` |

Detected fields: station id = `station.id`, value = `wbgt`, category = `data[].heatStress`.
Paths that look like thresholds/cut-offs in the response: none.

### rainfall

`data` keys: ['readingType', 'readingUnit', 'readings', 'stations']; readings on the first page: 1; `stations` in metadata: 89; paginationToken present: False.

| path | type | example |
|---|---|---|
| `readings[].timestamp` | str | `2026-10-20T14:55:00+08:00` |
| `readings[].data[].stationId` | str | `S218` |
| `readings[].data[].value` | int | `0` |
| `readingType` | str | `TB1 Rainfall 5 Minute Total F` |
| `readingUnit` | str | `mm` |
| `stations[].id` | str | `S218` |
| `stations[].deviceId` | str | `S218` |
| `stations[].name` | str | `Bukit Batok Street 34` |
| `stations[].location.latitude` | float | `1.36491` |
| `stations[].location.longitude` | float | `103.75065` |

Detected fields: station id = `stationId`, value = `value`, category = `None`.
Paths that look like thresholds/cut-offs in the response: none.

## Date check (every `date=` call, first page)

| phase | calls | OK | OK_UTC | PARTIAL | EMPTY | MISMATCH | ERROR |
|---|---|---|---|---|---|---|---|
| 1 probe | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| 2 bisect rainfall | 15 | 9 | 0 | 0 | 0 | 0 | 6 |
| 2 bisect wbgt | 15 | 8 | 0 | 0 | 0 | 0 | 7 |
| 4 stations 2023-01 to today (1/month) | 22 | 21 | 0 | 0 | 0 | 0 | 1 |
| **total** | 53 | 39 | 0 | 0 | 0 | 0 | 14 |

OK = every reading's SGT date equals the requested date. OK_UTC = all readings fall on the requested UTC date instead. PARTIAL = requested date plus others. MISMATCH = readings returned, none on the requested date (API ignoring `date=`). EMPTY = HTTP 200 with no readings. ERROR = non-200.

ERROR breakdown (feed, HTTP, message): ('wbgt', 404, 'Data not found'): 8, ('rainfall', 404, 'Data not found'): 6.

Datetime form `date=YYYY-MM-DDT13:00:00` (WBGT, yesterday): status OK, 25 readings, first 07:00 last 13:00 SGT, closest to 13:00 by 0 min → **usable as a point query, used for station sampling**.

## Q1. Earliest date with WBGT history

- Earliest date with readings: **2025-01-16** (days 1, 7 and 30 before it are absent (consistent with a clean start)).
- Bisect probes: 2021-05-11: ERROR, 2024-01-15: ERROR, 2025-05-18: OK, 2024-09-15: ERROR, 2025-01-15: ERROR, 2025-03-17: OK, 2025-02-14: OK, 2025-01-30: OK, 2025-01-22: OK, 2025-01-18: OK, 2025-01-16: OK
- Neighbour probes before it: 2025-01-15: ERROR, 2025-01-09: ERROR, 2024-12-17: ERROR
- On 2025-01-16 the page holds all of that day's 2 reading(s), 18:30 to 18:45 SGT, so the first day is partial.

## Q2. WBGT station count over time

Method: point query at 13:00 SGT (the page returned is the 25 readings up to 13:00, newest first), 1 call per sampled day. Stations are counted from the station values inside the readings (distinct IDs). The WBGT response has no separate station list, so 'stations in metadata' is derived from the same readings. Full-day pulls show 0 timestamp(s) split across pages, so one page holds every station for a timestamp.

| sampled day | date check | readings on page | stations at the chosen timestamp | stations on the page | stations in metadata | first seen here |
|---|---|---|---|---|---|---|
| 2025-01-16 | ERROR | 0 | 0 | 0 | 0 | 0 |
| 2025-02-15 | OK | 25 | 8 | 8 | 8 | 8 |
| 2025-03-15 | OK | 25 | 8 | 8 | 8 | 0 |
| 2025-04-15 | OK | 25 | 8 | 8 | 8 | 0 |
| 2025-05-15 | OK | 25 | 8 | 8 | 8 | 0 |
| 2025-06-15 | OK | 25 | 8 | 8 | 8 | 0 |
| 2025-07-15 | OK | 25 | 9 | 9 | 9 | 1 |
| 2025-08-15 | OK | 25 | 9 | 9 | 9 | 0 |
| 2025-09-15 | OK | 25 | 15 | 15 | 15 | 6 |
| 2025-10-15 | OK | 25 | 15 | 15 | 15 | 0 |
| 2025-11-15 | OK | 25 | 15 | 15 | 15 | 0 |
| 2025-12-15 | OK | 25 | 15 | 15 | 15 | 0 |
| 2026-01-15 | OK | 25 | 15 | 15 | 15 | 0 |
| 2026-02-15 | OK | 25 | 20 | 20 | 20 | 5 |
| 2026-03-15 | OK | 25 | 20 | 20 | 20 | 0 |
| 2026-04-15 | OK | 25 | 20 | 20 | 20 | 0 |
| 2026-05-15 | OK | 25 | 27 | 27 | 27 | 7 |
| 2026-06-15 | OK | 25 | 27 | 27 | 27 | 0 |
| 2026-07-15 | OK | 25 | 26 | 26 | 26 | 0 |
| 2026-08-15 | OK | 25 | 26 | 26 | 26 | 0 |
| 2026-09-15 | OK | 25 | 29 | 29 | 29 | 4 |
| 2026-10-15 | OK | 25 | 30 | 30 | 30 | 0 |

Stations at the chosen timestamp over 21 sampled days: min 8, max 30, latest 30; distinct IDs seen in total: 31.
Seen at some point but absent from the latest sampled page: S130 (West Coast Road). The 'first seen here' column counts IDs new to the monthly samples only; the first-seen table below also uses the bisect probes and full-day pulls.
Sampled days without data (2025-01-16: ERROR Data not found): the day's data starts after 13:00, so the point query found nothing.

First date each station appears in any dated WBGT page fetched (accurate only to the sampling gap of about a month; a station may have appeared earlier between samples):

| station id | name | first seen (any dated page fetched) |
|---|---|---|
| S124 | Upper Changi Road North | 2025-01-16 |
| S125 | Woodlands Street 13 | 2025-01-16 |
| S126 | Old Chua Chu Kang Road | 2025-01-16 |
| S127 | Stadium Road | 2025-01-16 |
| S128 | Bishan Street | 2025-01-16 |
| S129 | Bedok North Street 2 | 2025-01-16 |
| S130 | West Coast Road | 2025-01-16 |
| S132 | Jurong West Street 93 | 2025-01-16 |
| S137 | Sakra Road | 2025-07-15 |
| S139 | Tuas Terminal Gateway | 2025-09-15 |
| S140 | Choa Chu Kang Stadium | 2025-09-15 |
| S141 | Yio Chu Kang Stadium | 2025-09-15 |
| S142 | Sentosa Palawan Green | 2025-09-15 |
| S143 | Punggol North | 2025-09-15 |
| S187 | Bukit Timah(West) | 2025-09-15 |
| S144 | Upper Pickering Street | 2026-02-15 |
| S149 | Tampines Walk | 2026-02-15 |
| S150 | Evans Road | 2026-02-15 |
| S153 | Bukit Batok Street 22 | 2026-02-15 |
| S184 | Sengkang East Avenue | 2026-02-15 |
| S135 | Mandai Wildlife Reserve | 2026-05-15 |
| S145 | MacRitchie Reservoir | 2026-05-15 |
| S146 | Jalan Bahar | 2026-05-15 |
| S147 | Marina Barrage | 2026-05-15 |
| S148 | Pasir Ris Walk | 2026-05-15 |
| S151 | Outward Bound Singapore(Pulau ubin) | 2026-05-15 |
| S180 | Taman Jurong Greens | 2026-05-15 |
| S131 | Hougang Stadium | 2026-09-15 |
| S133 | Cathay Green | 2026-09-15 |
| S138 | Stirling Road | 2026-09-15 |
| S910 | Outward Bound Singapore(East Coast) | 2026-09-15 |


## Q3. Calls and records per day (full-day pulls, following pagination)

| feed | day | calls (pages) | readings per page (first 3) | readings (timestamps) | station values | first–last SGT | gap min/median/max (min) | stations per timestamp min/median/max | timestamps on >1 page |
|---|---|---|---|---|---|---|---|---|---|
| wbgt | 2026-10-19 | 4 | 25/25/25… | 96 | 2880 | 00:00–23:45 | 15/15/15 | 30/30/30 | 0 |
| wbgt | 2025-01-30 | 4 | 25/25/25… | 96 | 768 | 00:00–23:45 | 15/15/15 | 8/8/8 | 0 |
| rainfall | 2026-10-19 | 12 | 25/25/25… | 288 | 25884 | 00:00–23:55 | 5/5/5 | 88/90/90 | 0 |
| rainfall | 2024-06-12 | 12 | 25/25/25… | 288 | 17979 | 00:00–23:55 | 5/5/5 | 61/62/63 | 0 |

- wbgt 2026-10-19: `date=` returned the SGT day; union of stations over the day 30, metadata stations 30; pages come back newest first; last page still had a pagination token: False; expected about 96 readings at a 15-minute interval, got 96.
- wbgt 2025-01-30: `date=` returned the SGT day; union of stations over the day 8, metadata stations 8; pages come back newest first; last page still had a pagination token: False; expected about 96 readings at a 15-minute interval, got 96.
- rainfall 2026-10-19: `date=` returned the SGT day; union of stations over the day 90, metadata stations 90; pages come back newest first; last page still had a pagination token: False; expected about 288 readings at a 5-minute interval, got 288.
- rainfall 2024-06-12: `date=` returned the SGT day; union of stations over the day 63, metadata stations 63; pages come back newest first; last page still had a pagination token: False; expected about 288 readings at a 5-minute interval, got 288.

## Q4. WBGT category field and values at the boundaries

Category field detected by name: `data[].heatStress`.
String fields inside readings with at most 12 distinct values (all pages fetched, first pages and full days): `readings[].data[].heatStress` = {'Moderate': 825, 'Low': 14443, 'High': 36, 'NA': 15}; `readings[].item.type` = {'observation': 920}.

Station readings recorded: 14369 distinct (timestamp, station) pairs from every WBGT page fetched (14 without a numeric value; their category values: {'NA': 14}). Written to `wbgt_readings.csv` in the cache directory.

| category (exact value) | readings | min WBGT | max WBGT |
|---|---|---|---|
| 'Low' | 13594 | 18.9 | 30.9 |
| 'Moderate' | 730 | 31.0 | 32.9 |
| 'High' | 31 | 33.0 | 35.1 |

- Boundary 'Low' → 'Moderate': highest 'Low' = 30.9, lowest 'Moderate' = 31.0 (gap of 0.1)
- Boundary 'Moderate' → 'High': highest 'Moderate' = 32.9, lowest 'High' = 33.0 (gap of 0.1)

`High` observed 31 times; lowest High value 33.0; highest value in the category below ('Moderate') 32.9. Against the project assumption (High ≥ 33.0): lowest High ≥ 33.0 and highest lower-category value < 33.0. The cut-off is taken from these observed pairs, not coded; observed only on the days fetched.

No High-day counts are given: those need the full backfill (estimate below).

## Q5. Rainfall: earliest date (records per day are in Q3)

- Earliest date with readings: **2016-12-02** (days 1, 7 and 30 before it are absent (consistent with a clean start)).
- Bisect probes: 2021-05-11: OK, 2018-09-05: OK, 2017-05-04: OK, 2016-09-01: ERROR, 2017-01-01: OK, 2016-11-01: ERROR, 2016-12-01: ERROR, 2016-12-16: OK, 2016-12-08: OK, 2016-12-04: OK, 2016-12-02: OK
- Neighbour probes before it: 2016-12-01: ERROR, 2016-11-25: ERROR, 2016-11-02: ERROR
- On 2016-12-02 only the first page was fetched (25 readings, 21:59 to 23:59 SGT, newest first), so whether that first day is complete was not checked.

## Backfill size (D12)

| feed | calls on the measured days | calls/day used (yesterday) | all feeds from the WBGT start (2025-01-16) | from 2024-01-01, or the feed's own start if later | each feed's full history |
|---|---|---|---|---|---|
| wbgt | 4/4 | 4 | 2,568 | 2,568 | 2,568 |
| rainfall | 12/12 | 12 | 7,704 | 12,276 | 43,308 |
| 24-h forecast | 1 (check 10: one request per date) | 1 | 642 | 1,023 | 3,870 |
| **total** |  |  | **10,914** | **15,867** | **49,746** |

WBGT has no readings before its start date, so the Plan's 'WBGT from January 2024' would spend calls on 404s; the model's labels cannot start before the WBGT start. At 1 call/s with this run's 429 rate (14% of calls, each costing at least 5 s of back-off) the three scenarios take roughly 5.1 h, 7.4 h and 23.2 h. Assumes pages per day stay as measured and that a key does not change the limits; rainfall could be dropped if MSS daily records are cleared (M10).

## Calls, range and limits

Report regenerated from the cache (87 cache reads, 0 new calls); figures below are from the live run.

| phase | network calls |
|---|---|
| 1 probe | 6 |
| 2 bisect rainfall | 18 |
| 2 bisect wbgt | 17 |
| 3 full day rainfall | 28 |
| 3 full day wbgt | 8 |
| 4 stations 2023-01 to today (1/month) | 26 |
| **total** | 103 |

- Network calls: 103 (cap 300); retries after 429/403/5xx/connection errors: 14. HTTP status counts: {'200': 72, '404': 17, '429': 14}. Includes 4 calls from a first attempt that stopped after probing, because the parser did not yet recognise the WBGT response shape.
- Dated first-page calls: 53, from 2016-01-01 to 2026-10-19.
- Live run time: 2026-10-20 15:04 SGT. No key or token was used. Stop reason: none, ran to completion.

**Not tested:**
- High-day counts per month, and whether the three-class target is supportable: needs the full backfill (D6, §14.4).
- Whether a key changes history depth, page size or rate limits.
- Rainfall station counts over time, and rainfall values or categories.
- Days not sampled: station counts use 1 day per month from 2023 and at most 1 per quarter before; stations that appear and disappear between samples are missed, and first-seen dates are only as precise as the sampling gap.
- Station metadata beyond ID and name (locations, device types).
- Whether history was revised after the original readings.
- Whether the High boundary holds on days other than those fetched (see Q4 for what was observed).

