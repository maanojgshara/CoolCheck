# Collector catch-up: what a run re-fetches after missed runs, and what is lost after a longer gap (PT 14)

Read 23 Oct 2026 (window A) from `scripts/collector/collect.py` and `.github/workflows/collector.yml`; no code was changed. Evidence: the collector's own `plan()` on gap scenarios (no network); the 34 collector tests, which pass (`tests/collector/test_collect.py`, `test_collect_air_temperature.py`); and the live files of 22 and 23 Oct, copied read-only for `docs/checks/live_completeness.md`.

## Answer

- **A run keeps no state.** It does not know which runs were missed. It re-fetches a fixed window, the last 2 hours (`WINDOW_HOURS`), and the API's page size sets how far back it really reaches: about 6 hours for WBGT, the whole day for the forecast, and about 2 hours for rainfall and air temperature.
- **Once a night the model feeds are re-read in full.** Every run that starts between 00:00 and 00:59 SGT also reads every page of the previous day for WBGT, rainfall and the forecast (the midnight sweep). Four runs fall in that hour, so one success is enough.
- **Air temperature has no sweep.** It is for the live panel only, by design.
- **The manual catch-up cap is 48 hours.** A manual run (`workflow_dispatch` with `window_hours`) re-fetches up to 48 hours back (`MAX_WINDOW_HOURS`), and air temperature up to 12 hours (`AIR_TEMPERATURE_MAX_WINDOW_HOURS`, to stay under 40 pages per date).
- **Beyond 48 hours only the backfill refills.** `scripts/backfill/backfill.py` from the laptop refills WBGT, rainfall and the forecast; nothing in the repo refills air temperature.
- Nothing is lost at the source: data.gov.sg serves every feed by date (the backfill read WBGT back to 16 Jan 2025). "Lost" below means missing from the Volume until someone runs a catch-up.

## How far a normal run reaches (measured)

From the runs between 22 Oct 15:00 and 23 Oct 15:15 SGT, without the 00:xx sweep runs: 94 runs for WBGT and rainfall, 78 for air temperature (live from 20:15) and the forecast (no file before a day's first issue).

| Feed | Pages per run | Reach back from the run start: median (range) | Newest reading behind the run start: median (max) |
|---|---|---|---|
| WBGT | 1 | 6.3 h (2.0 to 8.0 h) | 15.6 min (21.6 min) |
| Rainfall | 1 | 2.1 h (2.0 to 3.8 h) | 5.5 min (10.8 min) |
| Air temperature | 5 | 2.2 h (2.0 to 2.4 h) | 5.6 min (10.8 min) |
| Forecast | 1 | every issue of the day | n/a |

A page holds 25 readings: 6 hours of WBGT, 2 hours of rainfall, 25 minutes of air temperature. A run reads pages newest first and stops at the first page that reaches the window start. A date's pages hold that date only, so WBGT reaches less in the first hours after midnight; the plan still reads yesterday when the window crosses midnight, so every run reaches at least 2 hours back.

## What is lost after missed runs

| Gap between two successful runs | WBGT | Rainfall | Forecast | Air temperature |
|---|---|---|---|---|
| Up to about 1 h 45 min (up to six missed runs in a row) | nothing | nothing | nothing | nothing |
| Longer, within the day | nothing up to about 6 h (less soon after midnight); beyond that, missing until the night's sweep | readings more than about 2 h before the next run: missing until the night's sweep | nothing: every run reads the whole day | readings more than about 2 h before the next run: lost unless a manual run (up to 12 h) starts in time |
| All four runs of 00:00 to 00:59 missed | the previous day's holes stay | the previous day's holes stay | nothing if a run succeeds by 01:59 (it still reads the previous day's page); otherwise the day's late issues stay missing | as above |
| Hole older than 48 h | backfill only | backfill only | backfill only | no path in the repo |

Why about 1 h 45 min: a reading is safe if the next run's window reaches back to the newest reading the previous run fetched. That holds while the gap is under 2 hours minus the feed's lag, about 1 h 49 to 1 h 54 min for rainfall. With runs every 15 minutes, six missed runs in a row (1 h 45 min between successes) lose nothing; seven (2 h) can cost the oldest 5 to 10 minutes of rainfall and air temperature.

## 22 Oct as a worked example

Before the 15-minute trigger started at 15:00, and during the 16:15 to 17:45 pause, the gaps between runs were 04:04 to 07:15 (3.2 h), 07:15 to 09:37 (2.4 h), 09:37 to 14:39 (5.0 h) and 16:15 to 17:45 (1.5 h).

- **WBGT:** a 22 Oct run fetched every reading time except 23:45, which the 00:00 run of 23 Oct fetched (normal lag). The 5-hour gap lost nothing.
- **Rainfall:** 79 reading times were fetched by no 22 Oct run: 00:00 to 01:55 (before the first run at 04:04, whose window reached back to 02:00); 04:05 to 05:05 (the 3.2 h gap); 07:15 to 07:25 (the 2.4 h gap); 09:35 to 12:30 (the 5.0 h gap); and 23:45 to 23:55 (lag, fetched at 00:00). The 1.5 h gap lost nothing.
- **The sweep filled them.** The four runs at 00:00, 00:15, 00:30 and 00:45 on 23 Oct each re-read all of 22 Oct (WBGT 4 pages, rainfall 12, forecast 1, plus the new day's first page from 00:15), so 22 Oct is complete in the Volume (`docs/checks/live_completeness.md`).

## What `plan()` reads in each case

| Case | Dates read, and how far back |
|---|---|
| Scheduled run 23 Oct 10:15 | 23 Oct to 08:15 |
| Scheduled run 23 Oct 00:15 (sweep) | 23 Oct to 22 Oct 22:15; 22 Oct every page |
| Scheduled run 23 Oct 00:45 (sweep) | 23 Oct to 22 Oct 22:45; 22 Oct every page |
| Scheduled run 23 Oct 01:00 (no sweep) | 23 Oct to 22 Oct 23:00; 22 Oct to 23:00 |
| Air temperature at 00:15 (never sweeps) | 23 Oct to 22 Oct 22:15; 22 Oct to 22:15 |
| Manual 48-hour catch-up at 23 Oct 10:00 | 23 Oct, 22 Oct and 21 Oct, back to 21 Oct 10:00 |
| The same, air temperature (capped at 12 h) | 23 Oct and 22 Oct, back to 22 Oct 22:00 |

## Limits a run works within (from the code)

- One call a second. A 429 is retried at most twice, 11 s apart. The run stops fetching after 3 HTTP 429s, when a call runs out of retries, after a 401 or 403 with the key, or after 180 s. Feeds already fetched are still written and uploaded, and air temperature is fetched last.
- At most 40 pages per date. A rainfall day is 12 or 13 pages; an air-temperature day is 58, hence its 12-hour cap.
- From 01:00 SGT, a 404 on page 1 of today's WBGT, rainfall or air temperature fails that feed. For the forecast, and before 01:00, a 404 means "no data yet".
- The workflow lets one run work and one wait; further queued runs are dropped (`collector.yml`). A dropped or stopped run counts as a missed run, and the next run's window covers it.
- A 48-hour catch-up is about 65 calls (my estimate: WBGT 9, rainfall 24, forecast 3, air temperature 29), about 65 to 75 s without 429s, inside the 180-s budget. Each 429 adds 11 s and the third stops the run.

## Risks the catch-up depends on (from the setup; not tested)

- Every recovery depends on runs starting. GitHub's own schedule fired in about 4 of 72 slots on 21 to 22 Oct. Without the cron-job.org trigger (its GitHub token expires 5 Nov), the 00:xx sweep runs would mostly not happen and holes would stay until someone runs a manual catch-up.
- During an upload outage (for example when the service principal's OAuth secret expires, about 20 Nov), each run's files stay on the runner and are lost. After the fix the next run fetches only its window, so a manual catch-up of up to 48 hours is needed.
- Readings the API adds for a day after about 02:00 the next day are never fetched by the live collector. Nothing re-reads a day after its sweep, and the runs up to 01:59 read only the day's last hour or two.
