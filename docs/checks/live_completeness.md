# Live files for 22 and 23 Oct 2026: runs per slot and reading coverage

Checked 23 Oct 2026, 15:30 to 15:45 SGT, read-only (window A). Source: the live folders of the four feeds, `/Volumes/coolcheck/bronze/raw_files/<feed>/live/2026-10-22` and `.../2026-10-23`, copied at 15:30 SGT with `databricks fs cp` (no compute) and counted with `scripts/checks/live_completeness.py --now 2026-10-23T15:30:00+08:00`. Silver was read at about 15:40 SGT through the Serverless Starter Warehouse.

A slot is the 15-minute window that holds a run's start time (SGT, from the file name). Reading coverage counts the reading times that have a value in any file of the day's folder or the next day's, because the next day's 00:00 to 00:45 runs re-read every page of the day for WBGT, rainfall and the forecast (the midnight sweep).

## Answer

- **22 Oct is complete in the Volume for WBGT, rainfall and the forecast**, at the level of readings: every WBGT and rainfall reading time is present, and the 7 forecast issues of the day. Runs cover only 36 of 96 slots, but the midnight sweep on 23 Oct holds the whole day.
- **Air temperature for 22 Oct starts at 18:05.** The feed went live with the 20:15 run, whose 2-hour window reached back to 18:05. It has no midnight sweep by design (live panel only, D9).
- **Silver is not yet complete for 22 Oct.** The pipeline last loaded the file of the 20:31 run on 22 Oct (Bronze ingest 20:39 SGT). `silver.wbgt_readings` holds 82 of 96 reading times for 22 Oct (00:00 to 20:15) and `silver.rainfall_readings` 171 of 288. A pipeline update is needed before window B trains on days to 22 Oct.
- **23 Oct so far is complete**: a run in every one of the 62 slots to 15:15, and every reading time to the newest one.

## Runs and files per slot

| Day | Slots | Slots with a run | Runs | WBGT files | Rainfall files | Forecast files | Air temperature files |
|---|---|---|---|---|---|---|---|
| 22 Oct | 96 | 36 | 37 | 37 | 37 | 36 | 16 |
| 23 Oct, to 15:30 | 62 | 62 | 66 | 66 | 66 | 50 | 66 |

**22 Oct, slots with no run (60):** 00:00 to 03:45; 04:15 to 07:00; 07:30 to 09:15; 09:45 to 14:15; 16:30 to 17:30. Before 15:00 only GitHub's own schedule started runs (04:04, 07:15, 09:37 and 14:39; the 14:58 run was a manual test); the cron-job.org trigger began at 15:00. The collector was paused from 16:15 to 17:45 for the gap backfill of 20 and 21 Oct (`docs/build-log.md`, Day 3, window A). The 20:30 slot has two runs (20:30:35 and 20:31:51).

**23 Oct, slots with two runs:** 01:30, 04:45, 07:45 and 12:30, each a GitHub-schedule run 6 to 12 minutes after the cron-job.org run. Duplicates are harmless; Silver dedupes.

**Slots with a run but no file for one feed, all expected:**
- Forecast, 22 Oct 04:00 and 23 Oct 02:00 to 05:30: no forecast for the day had been issued yet (first issues 05:36 on 22 Oct and 05:30 on 23 Oct), so page 1 returned "no data" and no file was written. From 02:00 the 2-hour window no longer reaches the previous day.
- Air temperature, 22 Oct before 20:15: the feed was not live yet.

## Reading coverage

| Feed | 22 Oct: times with a value | 22 Oct: stations | 23 Oct to 15:30: times with a value |
|---|---|---|---|
| WBGT (every 15 min) | 96 of 96 | 30, all at every time | 61 (00:00 to 15:00), 30 stations at every time |
| Rainfall (every 5 min) | 288 of 288 | 89; 73 at every time | 183 (00:00 to 15:10), 89 stations at 181 times |
| Forecast (issues) | 7: 05:36, 08:15, 11:30, 15:15, 16:45, 17:57, 23:32 | n/a | 3: 05:30, 11:31, 13:01 |
| Air temperature (every min) | 354 of 1,440 (18:05 to 23:59) | 18 | 909 (00:00 to 15:10) |

- **Rainfall 22 Oct:** 16 stations miss 1 to 10 of the 288 times: S114, S902, S905 and S909 have 278; S78 279; S904 280; S69 281; S117 282; S180 and S92 283; S88 284; S106, S107, S129, S223 and S307 287. These readings are in no file, including the four sweep runs, so the API did not return them. 79 of the 288 times are only in the 23 Oct sweep files; the sparse runs before 15:00 never fetched them.
- **WBGT 22 Oct:** 1 time (23:45) is only in a 23 Oct file.
- **Rainfall 23 Oct:** of 183 times, one has 88 stations and the newest (15:10) has 6, because it was still filling at the copy.
- **Air temperature:** the minute 23:12 on 22 Oct and the minutes 03:12 and 13:12 on 23 Oct have no reading from any station in any file, although several runs' windows covered them. S107 has fewer minutes than the other stations (311 of 354 on 22 Oct; 798 of 909 on 23 Oct), the gap already open since 22 Oct.

## Silver, for window B (read 15:40 SGT)

| Table | 21 Oct: times, stations, rows | 22 Oct: times, stations, rows |
|---|---|---|
| `silver.wbgt_readings` | 96, 30, 2,880 | 82, 30, 2,460 (00:00 to 20:15) |
| `silver.rainfall_readings` | 288, 90, 25,729 | 171, 89, 14,882 |

Newest live WBGT file in `bronze.wbgt_raw`: `wbgt_2026-10-22T203151_39779064006.jsonl`, ingested 22 Oct 20:39 SGT; 27 live files loaded. No pipeline update has loaded a file since, so the 23 Oct sweep files are not in Bronze or Silver yet.

## After the pipeline update of 23 Oct (read 16:05 SGT)

One refresh-only update (no full refresh), started by window A on your word: update `4110575e-4b77-4515-a66a-e584702526ef`, completed at 16:01 SGT. Bronze then held 108 live WBGT files, the newest from the 15:45 run on 23 Oct.

| Table, 22 Oct | Reading times | Stations | Rows |
|---|---|---|---|
| `silver.wbgt_readings` | 96 of 96 | 30 | 2,880 |
| `silver.rainfall_readings` | 288 of 288 | 89 | 25,543 |
| `silver.forecast_issues` | 7 issues | n/a | 7 |

- `silver.dq_day` marks all three feeds `ok` for 22 Oct. The 89 rainfall rows short of 288 × 89 are the 16 stations' missing readings listed above (10 + 10 + 10 + 10 + 9 + 8 + 7 + 6 + 5 + 5 + 4 + 5 × 1).
- **`silver.station_daily_label`, 22 Oct: complete.** 30 stations, all labelled and all usable; none low-coverage; 31 or 32 of the 32 peak slots per station; 93 to 96 valid readings per station; 7 readings with heat stress `NA`. Labels: 18 Moderate, 12 Low, 0 High. 1,470 readings are flagged late (first live arrival over an hour after the reading), the readings that only the midnight sweep fetched; the flag does not affect `usable`.
- 23 Oct is partial (63 WBGT times at 16:05) and its labels are provisional, as expected for the current day.
