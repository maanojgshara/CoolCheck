# Air temperature: design note (not built)

Written 22 Oct 2026 for Day 4's "third stream" (Guide §15 Day 4, D9). Nothing here is implemented: no change to `src/`, `resources/`, `tests/`, `.github/` or `scripts/collector/`, nothing loaded, no job run. The proposal needs your decision on the three questions at the end before anyone builds it.

## 1. What the endpoint returns

One call at 2026-10-22 15:59:30 SGT: `GET https://api-open.data.gov.sg/v2/real-time/api/air-temperature?date=2026-10-22`, with the Developer key in the `x-api-key` header (read from `DATA_GOV_SG_API_KEY`, never printed or written). HTTP 200, 18,211 bytes. The response is saved, unmodified, at `coolcheck-data/air_temperature_sample/air_temperature_2026-10-22T155930_SGT.json` (outside the repo; a search of the bytes found no key in it).

| item | what the call showed |
|---|---|
| top level | `code` (0), `errorMsg` (empty), `data` |
| `data` keys | `stations`, `readings`, `readingType`, `readingUnit`, `paginationToken` |
| `readingType`, `readingUnit` | `DBT 1M F`, `deg C` |
| `stations[]` | `id`, `deviceId` (equal to `id`), `name`, `location.latitude`, `location.longitude` (numbers). 18 stations: S06, S102, S104, S106, S107, S109, S111, S115, S116, S117, S121, S23, S24, S43, S44, S50, S60, S80 |
| `readings[]` | 25 groups, each `timestamp` (ISO 8601 with `+08:00`) and `data[]` of `{stationId, value}`; `value` is a JSON number (30.2 to 33.9 in this sample) |
| order and interval | newest first; 25 consecutive groups exactly 1 minute apart, 15:54 back to 15:30 (24 gaps, all 1 minute) |
| pagination | `data.paginationToken`, a 12-character alphanumeric string; sent back as `paginationToken` with the same `date`. Only page 1 was fetched, so how the last page ends was not seen in this call (check 12 and the collector's walk assume no token on the last page) |
| rate-limit headers | none in the response (header names: `CF-RAY`, `Connection`, `Content-Encoding`, `Content-Type`, `Date`, `Server`, `Strict-Transport-Security`, `Transfer-Encoding`, `X-Content-Type-Options`, `access-control-allow-origin`, `cf-cache-status`) |

Things in this one response that matter for the design:

- **The newest minutes are incomplete.** The newest group (15:54, 5.5 minutes before the call) had 11 of 18 stations; 15:52 had 17; the other 23 groups had all 18. Late values appear to arrive after the minute. A "stations reporting now" figure on the latest minute would read low; use a window (the last hour, as the Guide says).
- **Same shape as rainfall.** The `stations` list plus `readings[].data[]` of `{stationId, value}` is the rainfall response shape (`RAINFALL_SCHEMA` in `src/coolcheck/silver.py`), so the Silver parser can be shared.
- **Station count moves.** 18 today; check 12 found 12 to 19 on nine sampled dates between 2016 and 2026. Quote the count with its date.
- **A day is about 58 pages.** 1,440 minutes at 25 a page is 57.6. The rainfall feed needs 12 and WBGT 4. This is the number that drives the collector changes below.

How a day's readings are fetched (from this call, `docs/checks/check12.md` and the collector's `walk`): `date=YYYY-MM-DD` returns the newest 25 minutes of that day; follow `paginationToken` with the same `date` until no token is returned. `date=YYYY-MM-DDTHH:MM:SS` returned a single reading in check 12 (not repeated today).

## 2. Collector change (`scripts/collector/collect.py`, `.github/workflows/collector.yml`)

The collector reads each feed newest first from today back to the window start (2 hours), then every page of yesterday in SGT hour 0. Four changes make air temperature a fourth feed, keeping `backfill.py` untouched:

1. **Feed table.** In `collect.py`, extend the feed table and the order locally: `FEEDS = {**bf.FEEDS, "air_temperature": (bf.BASE + "air-temperature", {}, 1440, 58)}` and `ORDER = [*bf.ORDER, "air_temperature"]`. It goes last, so a stop (3 HTTP 429s or the 180 s budget) never costs a model feed.
2. **Timestamps (a trap).** `instants()` calls `bf.reading_stamps(feed, data)`, which handles only `rainfall`, and treats every other name as a WBGT or forecast `records[]` page. For `air_temperature` it would return no timestamps, so the walk's stop rule (`min(stamps) <= reach`) would never fire and every run would read up to 40 pages and then fail with "more than 40 pages". The fix is to pass `"rainfall"` to `bf.reading_stamps` for this feed (the response shapes match). A test must pin this.
3. **No midnight sweep for this feed.** The hour-0 sweep reads every page of yesterday; for air temperature that is 58 pages, above `bf.MAX_PAGES` (40), so the feed would fail every night in hour 0 and turn the run red. The live panel does not need complete days, so skip the sweep for this feed.
4. **File naming and upload.** Unchanged in form: `air_temperature/live/<YYYY-MM-DD>/air_temperature_<YYYY-MM-DD>T<HHMMSS>_<run id>.jsonl`, one response body per line, uploaded by the same Files API PUT with `overwrite=false`. The service principal already has write on the Volume. The workflow only needs its header comment to say four feeds.

**Cost per run.** With the same 2-hour window, page 1 covers 25 minutes, so 5 pages reach back past 120 minutes: **+5 calls** (3 calls now, 8 after). At the collector's 1 call a second, that is about +5 to +8 seconds of fetching; the 3-call dry runs took 2.1 s each, and the run limits are 180 s of fetching and a 5-minute job timeout. Files grow by about 91 KB a run (5 pages at about 18 KB) on about 226 KB for the three feeds now, about 9 MB a day at the roughly 100 runs a day the Guide plans. Billed Actions minutes are rounded per job: the extra seconds change the bill only if a run is near a minute boundary, and I could not check the real job durations (the Actions tab). The 429 risk is low: 8 calls in about 8 seconds is inside the 12 per 10 s a Developer key allows.

## 3. Bronze and Silver change

**Bronze.** Add `"air_temperature"` to `FEEDS` in `src/coolcheck/bronze.py`. The loop in `src/pipeline/bronze.py` then creates `bronze.air_temperature_raw` from `<raw_root>/air_temperature/` with the same columns and `pipelines.reset.allowed=false`. Existing Bronze tables are not touched. The reconcile job should be checked for a hard-coded feed list.

**Silver.** A new `silver.air_temperature_readings_all` (every parsed copy, flags kept) and `silver.air_temperature_readings` (deduplicated), by the same pattern as rainfall. To avoid copying the rainfall parser, rename it to a parser that takes the value column's name and use it for both; the existing rainfall tests are the safety net, and I would run them before and after. Columns: `station_id`, `station_name`, `station_lat`, `station_lon`, `reading_ts_raw`, `reading_ts`, `temp_raw`, `temp_c` (`try_cast` to double), `reading_type`, `reading_unit`, `sgt_date`, `sgt_minute`, `content_hash` and the Bronze metadata columns. `sgt_date` is derived explicitly from `reading_ts`, as for the other feeds.

**Quality rules** (warn-only expectations plus `fail_` flags, like C8):

| rule | condition |
|---|---|
| `has_key` | `station_id IS NOT NULL AND reading_ts IS NOT NULL` |
| `sgt_offset` | `reading_ts_raw LIKE '%+08:00'` |
| `temp_present` | `temp_c IS NOT NULL` |
| `temp_in_range` | `temp_c IS NULL OR temp_c BETWEEN 20 AND 40` (a gross-error screen; the sample ran 30.2 to 33.9; tune it after a week of data) |
| `unit_celsius` | `reading_unit = 'deg C'` |
| `station_listed` | `station_lat IS NOT NULL` |
| `minute_aligned` | the timestamp's seconds are 0 (every sampled stamp was) |

**Dedupe key:** `(station_id, reading_ts)`, with the same tie-break as rainfall (live over backfill, later file time, later path, content hash). Late values do not create conflicts: a station's value for 15:54 that arrives in a later copy is a new `(station, minute)` key, not a changed one. A changed value for an existing key shows in `dq_conflicts`, as for the other feeds.

**DQ tables.** Add `air_temperature` to `dq_events`, `dq_conflicts` and `station_gaps` (gaps over 60 minutes), and to `quarantine` (the loop picks it up). Leave `dq_day` alone for now: it spans the calendar from the first day any feed has data, so air temperature would show `no_data` for every day before the collector started it.

**Volume of rows.** Each run re-reads 5 pages, up to 450 values a page, so 2,250 copies a run and about 225,000 copies a day in `_all` at about 100 runs a day, against about 25,900 deduplicated values a day (1,440 minutes by 18 stations). Over the 13 days to the finale that is under 3 million copies. Fine for serverless, but it is the reason to keep the window at 2 hours rather than longer.

## 4. D9 latest readings and the live panel

The panel is air temperature in degrees Celsius, nothing else. It never feeds the model, the labels, the tiers or the agent, and it carries no heat category: Low / Moderate / High belongs to WBGT only and must not appear beside an air-temperature value.

- **Source.** The 15-minute D9 job cannot wait for the nightly pipeline, and Bronze moves only when the pipeline runs, so it reads the live files in the Volume (`<raw_root>/air_temperature/live/`) for the last 3 hours and parses them with the same shared parser (`coolcheck.silver.parse_air_temperature`). The files overlap by design (each run re-reads 2 hours), so the job keeps the newest copy of each station and minute before it takes the latest reading. How it lists and reads the files is Window A's job; this note fixes only the interface.
- **Latest-readings table.** One row per station and measure, as the Guide says (D9, §11.3): `measure = 'air_temperature'`, `station_id`, `station_name`, `lat`, `lon`, `reading_ts`, `value`, `unit`, `loaded_at`. The row is the station's newest reading with a non-null value, so a partly filled newest minute does not blank a station.
- **Stream summary.** Last reading time (the newest `reading_ts`); **stations reporting in the last hour** (distinct stations with a reading at or after job time minus 60 minutes, counted against the stations known that day); age of each station's latest value, so a stale station can be greyed on the map. Reported as "stations reporting in the last hour: N of M", never as a count for the latest minute.
- **Panel content.** The latest value per station on the map or table, plus the island minimum, mean and maximum of those latest values with their time. No sparkline in the first version.
- **Labels on the page.** "Air temperature, 1-minute readings, panel only", with the Open Data Licence notice for row 4 of `docs/datasets.md`.

## 5. Tests (written first, run through Databricks Connect where Spark is involved; output shown as evidence)

1. **Collector (`tests/collector`).** Extend the fake API with an air-temperature endpoint that serves 25 groups a page and a token chain. Assert: the call parameters; the stop after 5 pages for a 2-hour window; the file name and upload path; no hour-0 sweep for this feed while the other three still sweep; the feed runs last and a 429 stop leaves the first three files written; **the timestamp regression** (`instants()` returns 25 stamps for an air-temperature page).
2. **Silver parser (`tests/silver`).** A fixture cut from the saved real response (25 minutes by 18 stations, public data, no personal data) plus hand-made bad rows: a null value, a non-numeric value, 55 °C, an offset other than `+08:00`, a station missing from the list, a second copy of the same `(station, minute)` from a later live file, and a late-filled minute. Assert each flag, the deduplicated count, that the later copy wins and that the late minute raises no conflict. Run the existing rainfall tests unchanged after the parser is shared.
3. **Latest readings.** With a fixed job time: the newest non-null value per station, a station whose newest minute is missing, a station silent for over an hour, the "N of M" count, and the last-reading time.

## 6. What I will not do

- Build any of it before your decisions below.
- Backfill air temperature. A full day is 58 pages, so 2025-01-16 to 2026-10-19 (642 days) is about 37,000 calls, about 17 to 18 hours at the backfill's observed 1.7 s a call. That is a separate decision and belongs with M9/M10, not with the live panel.
- Use the collector's air-temperature files for M9. They will have gaps, no midnight sweep and a start date of the day the feed goes live; the M9 daily maxima come from a source with history (the NEA yearly CSVs on data.gov.sg, the same API with `date=`, or Meteorological Service records if permission comes: `docs/checks/check6.md`).
- Put air temperature, or any category beside it, into the model, labels, tiers, planning-area risk or the agent.
- Add per-feed windows, a new scheduler or a second workflow.
- Change the dedupe order, thresholds or DQ tables of the existing feeds.
- Guess the official dataset title or ID (`d_66b77726…` is truncated in the Guide): copy them from the data.gov.sg page before the notice ships.

## 7. Decisions for you

1. **Window.** Same 2 hours as the other feeds (5 pages, recommended: one rule for all feeds and the runs have been irregular, with 2-hour gaps seen on 21 to 22 Oct), or 1 hour for this feed (3 pages, fewer copies, but per-feed window code and tests).
2. **Sweep.** Skip the midnight sweep for air temperature (recommended), or raise the page cap to about 70 and accept 58 extra calls in each hour-0 run, 4 or more runs a night.
3. **Parser.** Share the rainfall parser (recommended; the rainfall tests guard it) or copy it and leave rainfall untouched.
