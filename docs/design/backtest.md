# Back-test: design note

Written 22 Oct 2026 for Day 3, window B, step 2: features, model, baselines and the rolling back-test (Guide §15 Day 3). **Approved 22 Oct with one change** (hyper-parameters chosen per fold from earlier folds only, §5.2) **and your decisions** (§12). It applies Guide §14.4, D6, D7, H2 to H4, §14.7 (E1 to E5), §14.8 and your fixed list for this step. Where I had to choose, the choice is marked and listed in §12.

**Read for it:** `docs/checks/eda.md`, `forecast_validity.md`, `h10_v2.md`, `area_exposure.md`; `src/coolcheck/silver.py`, `labels.py`, `nearest.py`, `timeutil.py`; `src/pipeline/`; `src/jobs/nearest_station.py`; `scripts/analysis/eda.py` (its forecast and rainfall rules). **Looked at, metadata only (no compute, no rows read):** the table types in `coolcheck.silver` and `coolcheck.gold`; the definition of `gold.area_nearest_station_daily`, which has the island rule (v2); the Volume, which holds no static files. **Not read:** the forecast Silver tables (window C's refresh); what this note says about them comes from `silver.py`. The three "start a year off" forecast records in §8.2 were found in the raw backfill files on disk.

## At a glance

- One pooled LightGBM (Low / Moderate / High) on usable station-days; 11 features from one PySpark function with the cut-off as a parameter (default T 00:15 SGT); no station ID.
- 14 monthly folds, Jul 2025 to Aug 2026; each fold's hyper-parameters are chosen from earlier folds only. Nothing reads, fits on or scores 1 Sep to 19 Oct 2026.
- Persistence (binary and continuous), same month last year and an NEA-forecast rule, on exactly the model's rows; three ablations.
- Pooled PR curve and PR-AUC for P(High), counts at persistence's alert load, 7-day block bootstrap. Headline on area-days over the 41 areas with residents aged 65+.
- Only completed days are used (§1).
- One bundle job logs everything to one MLflow experiment; its only Unity Catalog input to be loaded first is `silver.area_exposure` (decision 1). About 10 to 20 minutes and under US$1.5 a run (estimate).
- Your three decisions and the six choices are recorded in §12.

## 1. Completed days only (your addition, 22 Oct)

A label for the current SGT date is provisional. The coverage rule (`src/coolcheck/labels.py`) looks only at 10:00 to 17:59, so a pipeline update in the afternoon can give an unfinished day a label that looks usable; window A saw this for 22 Oct at 17:30. Training, evaluation and live scoring therefore use only completed days: every label row, and every day of readings that feeds a feature, has `sgt_date` strictly before `run_date`, the SGT date on which the job runs (taken from the wall clock at UTC+08:00, not from the Spark session).

- **In code, twice.** The loaders filter `sgt_date < run_date` at the scan, and `assert_completed_days(frame, run_date)` fails the run if any frame brought to pandas, or any day a feature row aggregated, is on or after `run_date`. The feature function takes `run_date` as an argument, so the live job (Day 4) gets the same rule.
- **Back-test.** The window filter (up to 2026-08-31) is stricter, so the rule removes nothing there. It is asserted anyway, and a test plants a usable-looking label on `run_date`.
- **Live job, for Day 4.** The target date equals the run date (it is the day being predicted), and none of its readings feed a feature. The H10 view still reads the target day's first reading to decide whether a station reported before 00:15. That is a reporting test on readings before the cut-off, not a label, and the view is not mine to change. A station whose only recent reading falls between 00:00 and 00:15 would be mapped by the view but have no feature row; the live job must flag it, not score it.

## 2. Tables and columns

### 2.1 Inputs

| Input | Type in UC | Columns used | Back-test scan filter |
|---|---|---|---|
| `silver.wbgt_readings` | streaming table | `station_id`, `reading_ts`, `sgt_date`, `wbgt`, `heat_stress`, `station_lat`, `station_lon` | `sgt_date <= 2026-08-31` and `< run_date` |
| `silver.rainfall_readings` | streaming table | `station_id`, `reading_ts`, `sgt_date`, `rainfall_mm`, `station_lat`, `station_lon` | as above |
| `silver.forecast_issues` | streaming table | `issue_ts`, `updated_ts`, `issue_sgt_date`, `valid_start_raw`, `temp_high`, `forecast_text`; `text_start_*` and `text_end_*` for the text check only | `issue_sgt_date <= 2026-08-31`; read only after you say window C is done |
| `silver.station_daily_label` | materialized view | `station_id`, `sgt_date`, `label`, `usable`, `n_high`; `n_valid`, `first_valid_ts`, `last_valid_ts` for the H10 SQL | `sgt_date <= 2026-08-31` and `< run_date` |
| `silver.area_station_distance` | Delta table | the columns `nearest_station_sql` reads | `boundary = 'mp2025'` |
| `gold.area_nearest_station_daily` | view (v2) | its definition only (§4) | none: no rows read |
| `silver.area_exposure` (to be loaded, decision 1) | Delta table | `planning_area`, `aged_65_plus` | `aged_65_plus > 0` (41 areas) |

`silver.dq_day` is not needed: a missing forecast is found by the selection rule itself (§3.3).

### 2.2 Pinning each read (MLflow lineage)

- **Streaming tables and the Delta table:** the version from `DESCRIBE HISTORY … LIMIT 1` at job start; every read then uses `VERSION AS OF` that version, so the run sees one snapshot even if the pipeline updates meanwhile. If time travel is refused on a streaming table, that table falls back to the next rule (checked on the first Connect run).
- **The materialized view** (no time travel), as in `h10_v2.md`: pulled once with the scan filter, saved as a canonical CSV (sorted by `station_id`, `sgt_date`), its row count and sha256 logged and the CSV logged as an artifact, then rebuilt with `spark.createDataFrame` as a temp view for the H10 SQL; the rebuilt copy's count and sums are checked against the pull.
- **The view:** the sha256 of its definition and its `updated_at`.
- **Code:** the git SHA (`${bundle.git.commit}`) and a sha256 of the job's own source files, which I compare with the same hash computed from the commit, so a deploy from an edited tree would show.

### 2.3 Outputs

The job writes nothing to Unity Catalog. Everything goes to one MLflow experiment (§7): metrics, parameters and artifacts. The artifacts are the out-of-fold predictions for station-days and area-days (station IDs, area names, dates, labels and scores only; no personal data), per-month counts, PR-curve points, the forecast fills, the fold models as LightGBM text, feature importances, the input lineage, the window audit and a generated `report.md`. After the run I copy `report.md` unchanged to `docs/checks/backtest.md`, with your OK.

## 3. The feature function

`station_day_features(wbgt, rain, fc, targets, run_date, cutoff_minutes=15, panel=ORIGINAL_8)` in `src/coolcheck/features.py`: PySpark, DataFrames in and out, so the tests pass fixtures and the job passes the pinned tables. The back-test calls it once for every target date from 2025-01-17 (the first with a yesterday) to 2026-08-31; the live job will call it for one date.

### 3.1 Rows and the cut-off

- **Cut-off** `C(T)` = T 00:00 SGT + `cutoff_minutes`, built with `timeutil.sgt_instant`, so the session time zone does not matter. Default 15 (00:15). Any value above −1,440 and below 1,440 works (−180 would be 21:00 the day before); only the default is run (§14.4: a sensitivity run is not promised).
- **Row set:** one row per station with at least one counted WBGT reading (`heat_stress` Low, Moderate or High) in `[C − 7 days, C)`. This is the H10 reporting rule, so every area-day's station has a row by construction. A station's first day (or first day back after more than 7 days without a counted reading) has no row and is not scored; the run lists those station-days.
- **Event time** (§14.8 C): a WBGT or rainfall reading counts only if `reading_ts < C(T)` (and `sgt_date < run_date`); a forecast version only if `updated_ts <= C(T)` and its `issue_ts` lies from T−1 17:00 to `C(T)`. **Yesterday** is SGT date T−1 restricted to readings before `C(T)`; with the default cut-off that is the whole of T−1. Days before T−1 in the trailing windows are whole days. Each row carries the latest input time it used (`inputs_max_ts`, `rain_inputs_max_ts`, `fc_updated_ts`), and the job asserts each against the row's cut-off.

### 3.2 The 11 features

| # | Column | Definition | Missing when |
|---|---|---|---|
| 1 | `wbgt_peak_d1` | highest `wbgt` among s's counted readings yesterday (the label table's `max_wbgt` rule) | s has no counted reading yesterday |
| 2 | `wbgt_peak_mean_7d` | mean of s's daily peaks over T−7 to T−1 | fewer than 4 of the 7 days have a peak |
| 3 | `station_char_30d` | mean over T−30 to T−1 of (s's daily peak − the panel's mean peak that day) | fewer than 20 of the 30 days have both: a station's first days |
| 4 | `n_high_d1` | s's readings yesterday with `heat_stress` = High | s has no counted reading yesterday (missing, not 0) |
| 5 | `panel_peak_mean_d1` | mean of yesterday's peaks over the panel stations that reported yesterday | no panel station reported |
| 6 | `panel_high_count_d1` | panel stations whose highest category yesterday was High | no panel station reported |
| 7 | `fc_temp_high` | `temp_high` of the selected forecast (§3.3) | no forecast selected; filled inside the fold (§5.1) |
| 8 | `fc_text` | `forecast_text` of the selected forecast, categorical | as 7 |
| 9 | `rain_d1_mm` | sum of `rainfall_mm` yesterday at the rainfall station nearest to s among those with at least 216 of 288 readings yesterday | no station qualifies |
| 10 | `month` | month of T, 1 to 12, numeric | never |
| 11 | `season` | season of T as in `eda.md` (NE monsoon Dec–Feb, inter-monsoon 1 Mar–May, SW monsoon Jun–Sep, inter-monsoon 2 Oct–Nov), categorical | never |

- **Panel** = the original 8 (S124, S125, S126, S127, S128, S129, S130, S132). A station counts on a day only if it reported that day, so the panel is 7 after S130 stopped on 24 Jun 2026, with no date in the code. Nothing is computed over all reporting stations (Pending Tasks item 14).
- **Categories** come from the API's `heat_stress` field; no WBGT cut-off is coded anywhere.
- **Not features:** the station ID, its coordinates (they would act as the ID), distances and `forecast_missing`.
- **Rainfall, location by date:** s sits where its latest counted reading before the cut-off says; a rainfall station where its latest reading yesterday says. Haversine km with the distance script's radius (6,371.0088 km); ties go to the lower `station_id`. 216 of 288 is 75% of yesterday's 5-minute slots before the cut-off, so it is 216 at the default and scales with a sensitivity cut-off. The total is a plain sum, as in the EDA.
- **Station character (choice 1, §12):** decision 3 (§16) named "the station's mean WBGT (or share of High readings) over the 30 days before the cut-off" as examples. I propose the difference from the panel's same-day mean: a raw 30-day mean moves with the season at every station, and a High share is near zero at most stations, while the difference measures how hot the station runs. S142's 36.7% High rate against the panel's 3.4% on the same dates (`eda.md` §5) is that character.
- **`month` is numeric,** so a month the fold has not seen (July in the first fold) is treated like the nearest month seen, not as an unknown category.

### 3.3 Forecast selection (features 7 and 8)

For target T, a candidate is a version (a row of `forecast_issues`, key `issue_ts`, `updated_ts`) with:

1. **Age limit (E5 (3)):** `issue_ts` from T−1 17:00 to `C(T)`, inclusive.
2. **Version rule:** `updated_ts <= C(T)`.
3. **Corrected validity covers T 06:00 to 18:00:** start = the stored `valid_start_raw` with its year replaced by the issue year −1, 0 or +1, whichever is closest to `issue_ts` (done on the string, so no time-zone arithmetic; a 29 Feb in a non-leap year does not parse and drops out); end = start + 24 h. The stored end is never used.

The selected version has the latest `updated_ts` (then `issue_ts`). With none, `forecast_missing` is true and features 7 and 8 are null; `forecast_missing` is a data-quality flag, never a model input (E5). Kept on the row, not as features: `fc_issue_ts`, `fc_updated_ts`, the lead time to T 06:00, and `fc_text_agrees`, the text check (E5 (4)) of the selected version's `validPeriod.text` against the corrected start and end (day, month and hour; the text has no year). The run counts disagreements, expected 0, and lists any.

In the EDA (before window C's refresh), 3 target dates had no forecast (2025-06-09, 2025-07-21, 2026-04-29), and the age limit adds the one whose selected issue was 27 hours old. The run lists what it finds; no date is coded.

## 4. Labels, rows and the area mapping

- **Label:** `label` of `silver.station_daily_label` for (s, T), as 0, 1, 2 for Low, Moderate, High; `usable` rows only (a High always stands; a Low or Moderate on a low-coverage day is dropped, §14.4).
- **Station-day rows** = feature rows joined to usable labels. They are built once for all target dates: no feature uses anything fitted across rows (no scaling, no target encoding), so building once equals building per fold. The fold-dependent steps are the forecast fill and the text categories (§5.1).
- **Area-days:** the 41 planning areas with residents aged 65+ (`area_exposure.md`) on the test dates. Each takes its station from `gold.area_nearest_station_daily` for (area, T), and that station's prediction and label for T. An area-day whose station-day is not usable is dropped and counted.
- **How the mapping is read:** the job reads the view's definition (metadata) and asserts that, whitespace aside, it equals the SQL `nearest_station_sql` builds for the live table names with the island rule on, cut-off 15 minutes, look-back 7 days and mp2025 (`src/coolcheck/nearest.py`, imported, not edited). It then runs that SQL over the pinned labels and the pinned distance version, keeping target dates 2025-01-17 to 2026-08-31. Same definition, same inputs: the view's mapping, reproducible from logged inputs (the `h10_v2.md` method), and no query of the view, whose `targets` step would scan the held-out labels.
- **Sizes to expect** (`eda.md`, before the usable filter and the island rule): 8,040 labelled station-days with 421 High in the back-test months, 106 of them at the original 8. The run reports its own counts and explains any gap beyond the known causes (usable filter, first days, island rule, window C's refresh).

## 5. The fold loop

### 5.1 Folds and the steps in each

14 folds, M = Jul 2025 to Aug 2026. Fold M trains on rows with target dates from 2025-01-17 to the day before M starts and predicts the rows in M: from about 1,300 training station-days (44 High) for Jul 2025 to about 8,500 (about 420 High) for Aug 2026 (`eda.md` counts).

In fold M:

1. **Split;** assert the latest training target date is before M's first day and every test row lies in M.
2. **Forecast fill** for rows with `forecast_missing`, training and test alike: `fc_temp_high` = the median over the fold's training rows in the row's calendar month, taken once per date (a date's forecast is shared by all its stations, so counting rows would weight later months by their larger station count), when at least 10 such dates exist, else over all training dates; `fc_text` = the most common text over the same dates (ties alphabetical). The filled dates, values and rule go to `forecast_fills.csv` for the write-up (§14.8 condition 2).
3. **Text categories** from the training rows after the fill; a test text unseen in training becomes missing (LightGBM's missing branch) and is counted.
4. **Fit** each of the four LightGBM candidates (§5.2) on the training rows and predict P(Low), P(Moderate), P(High) for the test rows; the fold's model is the candidate chosen from the folds before M.
5. **Baselines** on the test rows (§5.3); the NEA rule's threshold is fit on the training rows here.
6. **Ablations** (§5.4): separate fits with the configuration the model chose for fold M, same steps.

Every fitted object (fill values, categories, threshold, weights, booster, the fold's hyper-parameter choice) records the latest target date it used, and `assert_fitted_before(obj, M)` checks it is before M. The equal-load thresholds (§6) and the best-overall configuration (§5.2) are asserted to use nothing after 2026-08-31. After the loop the 14 test sets are pooled: each row is predicted once, by the model trained before its month.

### 5.2 Hyper-parameters

LightGBM `multiclass`, 3 classes. **Fixed:** learning rate 0.05, `min_data_in_leaf` 40, `lambda_l2` 1.0, `feature_fraction` 0.9, `bagging_fraction` 0.8 with `bagging_freq` 1, `max_bin` 63, categorical `min_data_per_group` 50 and `cat_smooth` 10, no class weights, seed 42, deterministic, row-wise, 4 threads. **Candidates:** `num_leaves` {7, 15} × rounds {150, 400}, four configurations, no early stopping; every candidate is fitted in every fold (56 fits). "Smaller" means fewer leaves × rounds: (7, 150), (15, 150), (7, 400), (15, 400).

**Chosen per fold, from earlier folds only (your change, 22 Oct):**
- Fold M uses the candidate with the highest pooled station-level PR-AUC for High over the folds before M (ties to the smaller); the first fold (Jul 2025) uses the smallest, (7, 150). The choice for Aug 2025 therefore rests on July's 12 High station-days alone; that is the honest procedure, and the per-fold choices are reported.
- **Headline:** the pooled result of those per-fold choices; no optimism from the choice reaches it.
- **Secondary line:** the single candidate with the best pooled result over all 14 folds, labelled "chosen on the same folds".
- **Day 4:** the final model's configuration is chosen on all 14 folds.

**Why these candidates:** the training sets are small and High is rare (44 in the first fold), so trees stay shallow with at least 40 rows a leaf; capacity (leaves × rounds) is the one setting worth searching at this size, and fixing the learning rate lets the rounds carry it; no class weights keeps P(High) near calibrated for the risk score (M2 tests calibration later); `max_bin` 63 because the inputs are coarse (WBGT to 0.1 °C, whole-degree forecasts); `min_data_per_group` 50 so rare texts (1 to 5 dates) are not split on alone.

### 5.3 Baselines (same rows, same cut-off)

- **Persistence, "same as today" (E3):** binary, alert if s's highest API category yesterday was High (`n_high_d1 ≥ 1`); continuous, `wbgt_peak_d1` as the score (missing ranks lowest). One baseline, two scorings, one run; nothing fitted.
- **Same month last year (D7's seasonal baseline, D6 rule 5):** score = s's High share over its usable days in the same calendar month a year earlier if it had at least 15 such days, else the panel's pooled share in that month a year earlier. Defined for Feb to Aug 2026 only and compared with the model on those months only; it reads labels from a year before M (asserted).
- **NEA-forecast rule ("forecast APIs" alone, D7; choice 2):** score = `fc_temp_high` after the fold's fill; binary rule, alert if `fc_temp_high ≥ θ`, with θ the observed value that maximises F1 for High on the fold's training rows (ties to the higher θ).

### 5.4 Ablations

(a) Without `station_char_30d`. (b) Trained without S142, S137 and S135, scored on the same rows as the model in every set. (c) Optional and last, dropped first if time is short: recency weights 0.5^(age / 180 days), where age = days from the row's target date to M's first day. One fixed half-life, not tuned: 180 days keeps last year's same season at about a quarter weight (two half-lives) while the latest months dominate.

## 6. Evaluation, pooled over the 14 folds

Every rate is shown with its counts ("X of Y"). The score is P(High).

**Sets:** area-days over the 41 areas (the headline, E1); station-days for all stations, without S142, S137 and S135, and for the original 8 as a fixed set (7 after 24 Jun 2026); and, for the same-month-last-year comparison, Feb to Aug 2026 (area-days and all station-days).

**Measures, per method and set:**

1. **PR curve and PR-AUC:** average precision (the step-wise area, `sklearn.metrics.average_precision_score`), with the base rate as the no-skill reference. The curve table (threshold, alerts, recall, precision) is what you choose the H4 cut-off from; I do not pick one.
2. **Recall and precision at persistence's alert load:** K = persistence's alerts in that set; every other method alerts on its K highest scores. Ties at the K-th score are resolved in expectation (random tie-breaking, linear inside the tied group), so coarse scores (same month last year, the forecast rule) are compared at exactly K.
3. **Per-month counts, not rates:** rows, High, alerts, TP, FP and FN at the equal-load threshold, and the sum of P(High) beside the observed High count (a plain check that the probability scale holds across folds).
4. **Season by year** (E1 (2)), counts at the equal-load threshold. **Inter-monsoon 1 (decision 2):** 2026 for every method; 2025 for persistence and the base rate only, labelled as such, because no fold predicts Mar to May 2025.
5. **Sustained High (E4):** recall on rows labelled High with 3 or more High readings (`n_high ≥ 3`), at the equal-load threshold; and the counts of test High rows on 1, 2, and 3 or more readings, for the limitations.
6. **Three classes (D6 rule 3), model only, secondary:** pooled 3×3 counts (label × most probable class) and multiclass log loss.
7. **95% intervals:** a 7-day block bootstrap over target dates. The 427 test dates (2025-07-01 to 2026-08-31) make 61 consecutive 7-day blocks; 2,000 resamples with replacement, fixed seed; a sampled block brings all its rows, so heat spells and the areas sharing a station stay together; percentile intervals. Paired: the same resamples for every method, so model minus each baseline, and model minus each ablation, get their own intervals. Thresholds stay at their full-sample values. The Feb to Aug 2026 comparisons resample the blocks inside those dates. A resample with no High row in a set is skipped and counted.
8. **Label-noise reference** beside the area-level scores, quoted from `h10_v2.md` (viii): near-equidistant stations' daily categories differ on 22.1% (29 of 131 days, Jurong West) and 22.0% (128 of 582, Marine Parade).

The report states numbers and does not interpret them, like `eda.md`; a weak result is reported as it is.

## 7. MLflow

- **One experiment,** a bundle resource in `resources/backtest.job.yml`, passed to the job by ID (`${resources.experiments.backtest.id}`; `bundle validate` will confirm the reference).
- **Runs,** each tagged with the job run's `backtest_id` and a `role`:
  - `model` (the per-fold choices, all 11 features; the headline), `baseline_persistence`, `baseline_same_month_last_year` and `baseline_nea_forecast_rule`: the four runs on the same split and metrics (H3, E3). The `model` run also logs the choice for each fold (`hp_choices.csv`);
  - `ablation_no_station_char`, `ablation_without_S142_S137_S135`, `ablation_recency_hl180`;
  - `hp_candidate_1` to `hp_candidate_4`: parameters, the pooled selection metric over all 14 folds and the folds where each was chosen. The best-overall candidate also logs the full metric set and is tagged `secondary = chosen on the same folds`.
- **Same metric names in every run** (for example `area41/pr_auc` and `area41/recall_at_persistence_load`, each with `_lo` and `_hi`), so MLflow's compare view lines them up.
- **Parameters on every run:** git SHA, code hash, `run_date`, cut-off, folds, feature list, panel, thresholds (216 of 288, 4 of 7, 20 of 30, 15 days), hyper-parameters and seeds; per input: table, type, Delta version or row count and sha256, scan filter; the view's definition hash and the result of the definition check.
- **Logged at the end** of a successful run only, so a failure leaves no partial set.
- **Development runs** through Databricks Connect do not log to this experiment; numbers for the write-up come only from the job's runs.

## 8. Guards and tests

### 8.1 Guards in code (any failure stops the run)

1. **Held-out window:** every source is filtered at the scan to dates up to 2026-08-31 (forecast: issue date); `HOLDOUT_START = 2026-09-01` is a constant, not a parameter; every frame brought to pandas is asserted inside the window and listed with its first and last date in the report's window audit, as in `eda.md`.
2. **Completed days** (§1).
3. **Cut-off per row:** `inputs_max_ts < cutoff_ts`, `rain_inputs_max_ts < cutoff_ts`, `fc_updated_ts <= cutoff_ts`, `fc_issue_ts >= T−1 17:00`.
4. **Folds:** exactly 14; no training row on or after M; test rows inside M.
5. **Fitted objects:** before M, including each fold's hyper-parameter choice (the latest target date among the predictions it ranked is before M); nothing fitted or chosen after 2026-08-31 (§5.1).
6. **Area mapping:** the view's definition equals the SQL the job runs (§4), and every area-day's station has a feature row.
7. **Pinning:** versions read once at start; the rebuilt label copy matches the pull.

### 8.2 Tests

Written before the code; through Databricks Connect on small fixtures where Spark is involved, with the output shown as evidence. The forecast tests use fixtures only, so they can run before window C finishes.

`tests/features/test_forecast_pick.py` (the known bad records, `forecast_validity.md`):

- **End before start:** the 2025-12-30 23:00 issue (stored end 2025-01-02) is selected for 2025-12-31, where the stored validity picked 12-30 17:44; the five 31 Dec issues from 05:31 to 15:54 are never selected, for 31 Dec or 1 Jan.
- **48-hour windows:** the 2025-01-16 23:08 issue (stored end 2025-01-19) is selected for 2025-01-17 and not for 2025-01-18; target 2025-07-21 gets no forecast (the stored validity picked the 07-19 23:02 48-hour issue); a synthetic record that only the 24-hour correction rejects (issue T−1 17:05, stored start T−1 12:00, stored end T+1 12:00).
- **Start a year off** (found in the raw files): the 2025-12-31 23:04 issue, stored start 2025-01-01 00:00, is corrected to 2026-01-01 and selected for 2026-01-01; the 2026-01-01 05:35 and 11:15 issues (stored start 2025-01-01 06:00) are never selected.
- **Age limit:** with only the 2025-01-16 03:33 issue present (validity 17 Jan), 2025-01-17 gets no forecast; synthetic issues at T−1 16:59:59 (rejected) and 17:00:00 (accepted).
- **Version rule:** a version updated at T 00:16 with another temperature is ignored; 00:15:00 is accepted, 00:15:01 is not.
- **Text check** true for the corrected real records and false for a planted mismatch; **no candidate** gives `forecast_missing` and null features.

`tests/features/test_station_features.py`:

- **Planted after the cut-off:** WBGT readings at T 00:20 and T 10:00 (High, 36.0) at s and at a panel station, a rainfall reading at T 00:20, a forecast version updated at T 00:20, and a new station whose only reading is at T 00:20: every feature for target T is unchanged, and the new station has no row. Repeated with cut-off −180 and a reading at T−1 22:00.
- **Midnight:** a reading at T−1 23:45 is in yesterday, one at T 00:00 is not; a UTC session gives identical features.
- **Missing versus zero:** NA readings ignored; `n_high_d1` missing (not 0) with no counted reading; the 7-day mean with 3 and with 4 days; the character missing below 20 days.
- **Panel:** a High at a non-panel station changes no panel feature; with S130 absent the panel counts 7; a reading of 33.5 marked Moderate does not count as High (the category comes from the API field).
- **Rainfall:** a nearer station with 215 readings is skipped; a moved station uses that day's location; ties go to the lower ID; none qualifying gives missing.
- **Rows and completed days:** a station with no counted reading in the 7 days before the cut-off has no row; a usable-looking label on `run_date` is dropped by the loader, and with the filter removed the assertion raises.

`tests/backtest/` (pandas, local; decision 3):

- `test_folds.py`: 14 folds with the right boundaries; a training row injected on M's first day, and a row dated 2026-09-01, each make a guard raise; the fill uses training dates only (changing test-month forecast values leaves it unchanged) and falls back as described; θ does not move when test labels change; same month last year starts in Feb 2026 and falls back to the panel; the per-fold choice takes (7, 150) in the first fold, moves when an earlier fold's predictions change and does not move when fold M's or a later fold's do, and ties go to the smaller candidate; a two-fold LightGBM fit on a toy frame repeats exactly with the seed.
- `test_metrics.py`: average precision and the PR curve against a hand-worked example; equal-load recall with ties against a hand-worked example; the blocks are 7 consecutive dates, and the resamples repeat with the seed and keep a block's rows together.

## 9. Run time and cost (estimates)

| Part | Time |
|---|---|
| Job start and environment install (lightgbm, scikit-learn, mlflow) | 2–4 min |
| Spark: pin; aggregate about 0.9 million WBGT and 11 million rainfall readings; forecast selection; H10 SQL; pull about 9,400 station-day and 32,600 area-day rows | 2–4 min |
| 14 folds × (4 configurations + 3 ablations) = 98 LightGBM fits on at most about 8,500 rows × 11 features | 2–5 min |
| Evaluation and 2,000 bootstrap resamples (about 8 methods × 4 to 5 sets) | 2–4 min |
| MLflow logging | under 1 min |
| **One job run** | **10–20 min, about US$0.5 to 1.5 at list price** |
| **Development and tests through Databricks Connect, over the day** | **about US$3 to 6** |

Basis: `docs/checks/cost_since_19_oct.md` (list price about US$0.39 per DBU for serverless jobs and US$0.83 for interactive serverless; all jobs on 21 Oct used 1.46 DBU). Well inside the trial's 50 DBU/hr cap. I'll read the real cost from `system.billing.usage` the day after the run; it lags a day.

## 10. Files and order of work

New files only; nothing existing is edited (`databricks.yml` already includes `resources/*.yml`; `nearest.py`, `labels.py` and `timeutil.py` are imported, not changed).

| File | Contents |
|---|---|
| `src/coolcheck/features.py` | the feature function and the forecast selection (PySpark); constants (panel, the three late starters, 216 of 288, minimum days) |
| `src/coolcheck/backtest.py` | folds, fills, categories, baselines, LightGBM fits, guards (pandas) |
| `src/coolcheck/metrics.py` | PR curve, average precision, equal-load comparison, block bootstrap (numpy) |
| `src/jobs/backtest.py` | the job: pin inputs, features, the view definition check, folds, evaluation, MLflow, report; `--profile` for Connect, as in `nearest_station.py` |
| `resources/backtest.job.yml.draft` | the experiment and the serverless job: environment 4 with pinned lightgbm, scikit-learn and mlflow; `max_retries: 0`; one concurrent run; 1-hour timeout; no schedule. Kept as `.draft` (which the bundle does not include) until my own deploy, so another window's deploy cannot pick up a half-written job (your rule, 22 Oct) |
| `scripts/static/load_area_exposure.py` | loads `coolcheck-data/analysis/area_exposure.csv` into `coolcheck.silver.area_exposure` (decision 1); run only after you OK the write |
| `tests/features/` | `conftest.py`, `feature_fixtures.py`, `test_forecast_pick.py`, `test_station_features.py` |
| `tests/backtest/` | `test_folds.py`, `test_metrics.py` |
| `requirements-backtest.txt` | local pins for lightgbm and scikit-learn (decision 3) |
| `docs/checks/backtest.md` | the job's report, copied unchanged after the run |

Order, with a diff and your OK before each commit:

1. The feature tests, then `features.py` until they pass through Connect (fixtures only).
2. `backtest.py`, `metrics.py` and their tests, after the dry-run check of the local install (decision 3).
3. The loader script; ask before it writes `silver.area_exposure`.
4. The job and `resources/backtest.job.yml.draft`.
5. Once you say window C is done: a Connect dry run on two folds (Jul and Aug 2025), nothing logged, to check pinning, counts against `eda.md` and timing.
6. Ask to deploy (one deploy across windows, from a clean tree: a bundle deploy uploads every file in the shared folder, other windows' uncommitted edits included). In my deploy slot: rename the `.draft` to `resources/backtest.job.yml`, run `databricks bundle validate -t dev` (the bundle reads only `*.yml`, so this is the first point it can be validated), then deploy. Then ask to run.
7. Copy the report to `docs/checks/backtest.md` and show it. You then choose the H4 cut-off from the pooled curve; the final check waits for that.

**Durable record.** The MLflow runs live in the trial workspace, which ends on 30 Oct. `docs/checks/backtest.md` in git is the durable record, and the back-test is rerun on Free Edition at the Day 6 redeploy.

## 11. What I will not do

- Read, score or look at 1 Sep to 19 Oct 2026; pick the H4 cut-off; change the split, the months or the label.
- Read the forecast Silver tables before you say window C is done.
- Register a model, set an alias, or write `gold.heat_forecast` or any other table (Day 4), except `silver.area_exposure` (decision 1), after asking.
- Edit files other windows own, or the H10 view.
- Add features beyond the 11; use the station ID or coordinates; compute a network feature over all reporting stations; use air temperature; code a WBGT category cut-off.
- Tune beyond the four configurations or the half-life; add class weights; calibrate (M2 comes later).
- Run the sensitivity cut-off.
- Deploy, run a job, write a table, commit or push without your OK, or deploy while another window does.
- Quote a number that is not in the job's logged run.

## 12. Decisions (decided by you, 22 Oct)

1. **Where the 41 areas come from: (a).** A new loader script writes `coolcheck-data/analysis/area_exposure.csv` to `coolcheck.silver.area_exposure`, asking before the write; Day 4's risk score needs it in Unity Catalog anyway, and the job reads it by Delta version.
2. **Inter-monsoon 1, 2025 against 2026: as proposed.** The folds start in Jul 2025, so Mar to May 2025 has no model, NEA-rule or same-month-last-year prediction: inter-monsoon 1 of 2026 for every method, and for 2025 persistence (nothing fitted) and the base rate only, labelled as such.
3. **Local packages: yes, with the dry-run check.** lightgbm and scikit-learn go into the shared `.venv` only if `pip install --dry-run` shows no change to numpy, pandas, pyarrow or databricks-connect.

**My six choices: accepted as written** (each is fixed before any model runs, and logged):

1. Station character = the 30-day mean difference from the panel's same-day peak (§3.2).
2. The NEA rule uses the forecast high temperature alone, θ by F1 on training rows; the text stays out to keep it a one-number rule.
3. Same month last year: the station's own share with at least 15 usable days, else the panel's.
4. Minimum days: 4 of 7 for the trailing mean, 20 of 30 for the character.
5. The hyper-parameter grid and selection rule (§5.2), the 180-day half-life, 2,000 resamples.
6. Whether the station-character feature stays in the final model (Day 4): I suggest fixing the rule now (keep it if the pooled station-level PR-AUC is higher with it); both results are reported either way (decision 3, §16).
