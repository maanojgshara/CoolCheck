# Check 12: NEA air temperature (data.gov.sg)

Endpoint `https://api-open.data.gov.sg/v2/real-time/api/air-temperature`, unauthenticated. Script: `scripts/checks/check12_air_temperature.py`. Run 2026-10-21 12:51 SGT.

## Latest call

HTTP 200; data keys ['readingType', 'readingUnit', 'readings', 'stations']; station metadata count 18; reading groups 1.

Leaf paths of the first reading group:

| path | type | example |
|---|---|---|
| `timestamp` | str | `2026-10-21T12:43:00+08:00` |
| `data[].stationId` | str | `S109` |
| `data[].value` | float | `30.5` |

## Interval and stations per sampled day

Three calls per date. (1) `date=YYYY-MM-DD`, first page only: the API returns 25 readings, newest first, from the end of that day. (2) and (3) `date=` with a time, 12:00:00 and 12:01:00: one reading each. Interval = gaps between consecutive reading timestamps on the first page, and the 12:00 to 12:01 pair. Stations = stations with a value in that reading; 'listed' = stations in the response's station list.

| date | HTTP | timestamps on page 1 | span (SGT) | gaps between timestamps | stations with a value | 12:00 to 12:01 | note |
|---|---|---|---|---|---|---|---|
| 2016-12-02 | 200 | 1 | 00:00-00:00 |  | first page 19-19; at 12:00 19, at 12:01 19; listed 19 | 0 min |  |
| 2018-06-15 | 200 | 25 | 23:35-23:59 | 1 min: 24 | first page 16-16; at 12:00 16, at 12:01 16; listed 16 | 1 min |  |
| 2020-06-15 | 200 | 25 | 23:35-23:59 | 1 min: 24 | first page 14-16; at 12:00 16, at 12:01 16; listed 16 | 1 min |  |
| 2022-06-15 | 200 | 25 | 23:35-23:59 | 1 min: 24 | first page 13-14; at 12:00 14, at 12:01 14; listed 14 | 1 min |  |
| 2024-06-12 | 200 | 25 | 23:35-23:59 | 1 min: 24 | first page 13-14; at 12:00 13, at 12:01 13; listed 14 | 0 min |  |
| 2025-01-16 | 200 | 25 | 23:35-23:59 | 1 min: 24 | first page 13-14; at 12:00 12, at 12:01 12; listed 14 | 1 min |  |
| 2025-06-15 | 200 | 25 | 23:35-23:59 | 1 min: 24 | first page 11-12; at 12:00 12, at 12:01 12; listed 12 | 1 min |  |
| 2026-03-15 | 200 | 25 | 23:35-23:59 | 1 min: 24 | first page 15-15; at 12:00 15, at 12:01 15; listed 15 | 1 min |  |
| 2026-10-19 | 200 | 25 | 23:35-23:59 | 1 min: 24 | first page 17-18; at 12:00 18, at 12:01 18; listed 18 | 1 min |  |

### Reading

- **Reading interval: 1 minute** on the 8 of 9 sampled dates with a page of 25 readings (all 24 gaps were 1 minute); the 12:00 to 12:01 pair was 1 minute apart on 7 dates and returned the same reading on 2 (2016-12-02, 2024-06-12), so on those dates a reading at 12:01 was not found by `date=` (cause not determined).
- **Station count: 12 to 19 across the sampled dates; 18 listed on 2026-10-19.** It is not constant, so quote a count with its date. The Plan's 'about 18' matches the latest date only.
- History: the earliest sampled date (2016-12-02) has a reading, so `date=` history reaches at least back to then; the exact start was not searched.

## Calls

Network calls 0 (cap 120), retries 0, cache hits 28, HTTP status counts {}. No key or token was used. Stop reason: none.

**Not tested:** whether a key changes history depth or limits; whether stations missing from a day's readings were offline or absent from the feed; the values themselves.

