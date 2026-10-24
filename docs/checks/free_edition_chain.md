# The whole chain on Free Edition, once (24 Oct 2026, window A)

Run 24 Oct 2026, about 20:15 to 22:40 SGT, from a clean worktree of `dbe5f93` (`bundle deploy -t free`, profile `freeedition`, catalog `workspace`). Nothing was written to the trial (listings, downloads and SELECTs only); no schedule was unpaused on Free Edition; the collector was not touched; no full refresh, retry or code change. Free Edition was read through Databricks Connect. Tools: `scripts/free_edition/copy_live_free.py` and `compare_ws.py` (tests in `tests/ops/test_free_edition.py`). One trial and one Free Edition run, not a track record.

## Answer

The chain works end to end on Free Edition: every step ran without error, and Free Edition's Bronze and Silver equal the trial's (the one exception is a count that depends on file arrival times, by design). **The refit model's sha256 differs** (`ae8fe0f9…`, the trial's is `715d7f88…`) although the code, the packages, the training inputs and the training counts are equal. The probabilities it gives differ by at most 0.0047 for P(High); no heat level and no tier changes on either date.

## What ran

| Step | Result |
|---|---|
| Copy stage 1 (live files the trial had ingested, run stamp up to 2026-10-24T004524) | 539 files, 52.08 MB, one at a time in name order; 0 failed; verified: 0 missing or wrong size, 0 `.partial` |
| Plan and deploy (`dbe5f93`) | plan: 2 create (`heat_forecast`, `live_model`), 2 update (`backtest`, `final_check`: only `parameters[7]`, the git sha, `60b8ab0` to `dbe5f93`), 0 delete; file sync 224 uploaded, 0 deleted (all 193 files of the earlier deploy are in `dbe5f93`). Deploy: 2 created, 2 changed, 0 deleted. `heat_forecast` and `latest_readings` read PAUSED after it and at the end |
| One incremental pipeline update | update `5b580101-416f-42f4-9ba8-0c3e30fad50c`, 13:13:14 to 13:19:12 UTC (21:13 to 21:19 SGT), 5 min 58 s, COMPLETED |
| Loaders (from the worktree, `--catalog workspace --profile freeedition`) | `area_exposure` 55, `area_station_distance` 3,410, `refuge_points` 279, `park_polygons` 888, `block_access` 10,817, `area_access` 330, `score_weights` 7, `tier_actions` 4, `ema_area_electricity` 30; every source file's sha256 equals the one recorded on the trial |
| Views | `area_vulnerability` 32, `block_vulnerability` 10,817 |
| `nearest_station` job | run 518102064493043, 62 s, SUCCESS; `area_nearest_station_daily` 35,585 rows |
| `live_model` job | run 838776039077222, 118 s, SUCCESS; registered `workspace.ml.heat_model` version 1; alias `champion` set by the job itself (read back: version 1), so nothing was set by hand |
| `heat_forecast`, task `score` only | 2026-10-23: run 732583020553316, 76 s; 2026-10-24: run 745631407862923, 69 s; each 41 rows, 41 scored, model version 1, read-back checks passed |
| `gold.area_heat_risk` | 82 rows (41 per date) |
| The three functions | `find_refuges` (5 rows), `what_if_add_refuge` (1), `get_priority_areas(2026-10-24, 800)` (41 areas, 800 calls allocated), every parameter and column commented |
| Copy stage 2 (the 356 files that arrived later) | 28.66 MB, 0 failed, verified; no pipeline update. Free Edition then held 895 live files (80.74 MB), the trial 895: none on one side only, no size differs |

The trial's Volume has one more file than Free Edition's, `_meta/backfill_end.json` (242 bytes), which the pipeline never reads; it was not copied.

## Silver against the trial

`compare_ws.py digest` on each side (taken while the trial's last pipeline update was still the 00:45 one of 24 Oct, `910b793c`), then `diff`:

| Part | Values compared | Differ |
|---|---|---|
| Bronze: lines, distinct files and a checksum, per feed and source kind | 21 | 0 |
| Silver: rows and a content checksum per feed and SGT day for the four deduplicated tables and their `_all` tables, 16 Jan 2025 to 24 Oct; daily labels (rows, usable, High, checksum); `dq_day`; `dq_events`; counts of `quarantine`, `dq_conflicts`, `station_gaps`, `wbgt_first_arrival` | 10,423 | 1 |
| Static tables (nine) | 18 | 1 |
| Views: `area_vulnerability`, `block_vulnerability`, `area_nearest_station_daily` per target date | 1,298 | 0 |

The two differences:

- **`dq_events`, `wbgt|readings_first_arrived_over_1h_late`: 1,860 on the trial, 0 on Free Edition.** By design: the count is about when a live file landed, and every live file on Free Edition landed within the last hours (its file time is the copy time). Readings from before the first live file are never counted late. The labels (`n_late` and `label_if_late_excluded` are left out of the label checksum) do not depend on it.
- **`silver.area_station_distance.station_last_day`:** the trial has 2026-10-19 for 30 stations, Free Edition 2026-10-21. The loader reads the last day each station appears in the local raw backfill, which now reaches 21 Oct; the trial's table was loaded when it ended at 19 Oct. No view reads this column: the nearest-station view is equal for every target date.

The trial's counts that Free Edition now equals: Bronze 2,747 / 7,943 / 771 / 612 lines (WBGT / rainfall / forecast / air temperature) plus the backfill; Silver 1,047,615 WBGT, 11,996,549 rainfall, 4,699 forecast, 32,719 air temperature rows; 10,986 label rows, 10,892 usable, 541 usable High; 1,941 `dq_day` rows; 0 quarantined.

## The model

| | Trial (run e6189b13…, 23 Oct) | Free Edition (run 13c8ac43…, 24 Oct) |
|---|---|---|
| Model sha256 | `715d7f887dced8282c42ec59fb1938e3ff0de73c3ffe00ec21c37b4d34b53060` | `ae8fe0f9307ae16a100ec0c322bb2bff538466b43f7cc39879be23711e2db273` |
| Code sha256 (job's own, over the code files) | `a7e9c1f6dcfdb55552932c1edebeb9578c095e8a6031b7c4a5506a2c197af223` | the same |
| Packages | Python 3.12.3, pandas 2.2.3, numpy 2.1.3, scikit-learn 1.6.1, LightGBM 4.6.0, MLflow 2.22.0, SciPy 1.15.1, PyArrow 19.0.1 | the same |
| Back-test path to 31 Aug | 9,308 station-days, 465 High | the same |
| Training rows | 10,861 station-days, 538 High (4.954%) | the same |
| Builder equal to the back-test path to 31 Aug | largest difference 0.0 | the same |
| Training inputs (rows and checksums of WBGT 895,135 / 1,044,645, rainfall 10,644,768 / 11,970,215, forecast 4,324 / 4,693, and the label pull) | recorded in `lineage.json` | equal; only the Delta versions (11, 10, 12 against 3) and the run-date filter (before 23 Oct against before 24 Oct) differ |
| `dq_day` 20 to 22 Oct, view definition check | recorded | equal |

So the code, the packages and the inputs the job fingerprints are the same, and the booster text still differs. Two explanations, neither tested: LightGBM is not bit-reproducible across hardware or thread counts; or the order of the rows entering the fit differs although their content is equal. The model was not refit again.

### What the other model does to the outputs (24 Oct, 41 areas)

`compare_ws.py diff --tolerance 1e-9`, then the figures below from the two digests:

| | 23 Oct | 24 Oct |
|---|---|---|
| Largest difference in P(High) | 0.0011 (Sungei Kadut) | 0.0047 (Sungei Kadut) |
| Largest difference in P(Low) | 0.0050 (Choa Chu Kang) | 0.0123 (Singapore River) |
| Largest difference in P(Moderate) | 0.0053 (Choa Chu Kang) | 0.0118 (Singapore River) |
| Mean difference in P(High) | 0.00024 | 0.00071 |
| Areas whose probabilities differ by more than 1e-9 | 41 of 41 | 41 of 41 |
| Station, model version, `forecast_missing`, `cutoff_ts` | equal on all 41 | equal on all 41 |
| Heat levels, rated flags, vulnerability thirds, tiers that change | none | none |
| Tier counts (trial and Free Edition) | Low 19, Medium 13, Not rated 9 | High 1, Medium 22, Low 9, Not rated 9 |
| Rank swaps inside a tier | Hougang and Sembawang (Medium, 8 and 7 swap), Bukit Panjang and Outram (Low, 13 and 14 swap) | Choa Chu Kang and Tampines (Medium, 14 and 15 swap) |

The P(High) values nearest the High cut-off (0.10975585695894975) stay on the same side: 23 Oct Southern Islands 0.1185 on the trial, 0.1175 here (High both); 24 Oct Bishan and Toa Payoh 0.1430 and 0.1441 (High heat both; Toa Payoh is the High tier, Bishan Medium). The three functions give equal `find_refuges` and `what_if_add_refuge` rows; `get_priority_areas` allocates the same 800 calls (all in Toa Payoh) and differs only in positions 15 and 16 (Choa Chu Kang and Tampines swapped).

## Cost and time

- **The pilot (`c119681e`, 23 Oct, 225 files, 4 min 6 s):** 0.5163 DBU (0.4162 tagged with the update, 0.1001 on the same pipeline in the hour before without an update id), about US$0.18 at list price (pipeline SKU).
- **Today's update (5 min 58 s):** not in `system.billing.usage` yet. At the last read Free Edition's billing ended at 19:00 SGT on 24 Oct and the update ran 21:13 to 21:19. The estimate given before the run was about 3 DBU (2 to 5); the wall time of 6 minutes is inside the 5 to 10 minutes expected. The jobs of the chain (nearest station 62 s, live model 118 s, two scores 76 s and 69 s) are not read either. Read it later with:

```sql
SELECT usage_metadata.dlt_update_id, billing_origin_product, min(usage_start_time), max(usage_end_time), sum(usage_quantity)
FROM system.billing.usage
WHERE usage_metadata.dlt_pipeline_id = '0b6e55e9-e41e-4137-819f-806307665b48' OR usage_date >= DATE'2026-10-24'
GROUP BY ALL ORDER BY 3
```

- **No quota stopped any compute** during the chain. The quota is unpublished; this is one day's evidence, not a limit.

## Unpausing on Free Edition (not done; Sunday's decision)

Both schedules are overridden to PAUSED under `targets.free` in `databricks.yml` (`latest_readings`, `heat_forecast`). Unpausing is a commit that removes the two `pause_status: PAUSED` overrides and their comments (also the sentence in `resources/heat_forecast.job.yml`), a plan, and a redeploy from a clean worktree.

- **`heat_forecast`** would run at 00:45 SGT every night: a refresh-only pipeline update, then the score. Until the collector writes to Free Edition no new live file arrives there, so the score would fail every night (no features for the new date) and e-mail the deploying user; the update itself still costs compute.
- **`latest_readings`** would run every hour at :05 and fail its freshness alarm every hour without new files; on the trial one run costs 0.363 DBU (`docs/checks/latest_readings_cost.md`), about 8.7 DBU a day at hourly.
- A champion model now exists there (`workspace.ml.heat_model` version 1), which was the stated reason for keeping the forecast paused.
- Both depend on the collector decision (Guide §A4 row 6), planned for 28 or 29 Oct.

## For Sunday's redeploy

Run in this order, from a clean worktree of the final commit; each of the scripts takes every path as an argument:

1. `copy_live_free.py --stage all` (only what is missing is copied), then `compare_ws.py` before and after.
2. `bundle plan -t free` (stop on any delete or recreate), `bundle deploy -t free`.
3. One pipeline update only if the Volume holds files Bronze has not seen.
4. `compare_ws.py digest` on both sides, then `diff`: Silver must differ only in the lateness count.
5. The model: expect a different sha256 if the live model were refit again; it is not refit (the job refuses when a version exists).

## Corrected on the way

My first Silver digest hashed `source_file`, which contains the catalog name (`/Volumes/coolcheck/...` against `/Volumes/workspace/...`), so every `_all` and Bronze checksum differed while all counts matched. The digest now hashes the path relative to the Volume root; both digests were taken again and the figures above are from those.
