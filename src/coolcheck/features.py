"""Station-day features for the next-day heat model (docs/design/backtest.md §3). One function serves the back-test and
the live job.

Every source is filtered by event time against the cut-off C(T) = 00:00 SGT on the target date T plus cutoff_minutes
(default 15, so 00:15): a WBGT or rainfall reading counts only if reading_ts < C(T); a forecast version only if
updated_ts <= C(T) and its issue time lies from 17:00 on T-1 to C(T). Only completed days are read: every reading used
has sgt_date before run_date, the SGT date the job runs on, because a label or an aggregate for the current day is
provisional (note §1).

Rows: one per station with a counted WBGT reading in [C(T) - 7 days, C(T)), the H10 reporting rule, so every
area-day's station has a row. A reading counts if heat_stress is Low, Moderate or High (the label table's rule).
Categories always come from the API's heat_stress field; no WBGT cut-off is coded. "Yesterday" is SGT date T-1
restricted to readings before C(T), which is the whole day at the default cut-off; earlier days in the trailing windows
are whole days.
"""
import math
from datetime import date, datetime

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

from coolcheck.timeutil import parse_ts, sgt_date, sgt_instant, sgt_minute

ORIGINAL_8 = ("S124", "S125", "S126", "S127", "S128", "S129", "S130", "S132")  # the fixed panel; 7 after S130 stopped
LATE_STARTERS = ("S142", "S137", "S135")
CATEGORIES = ("Low", "Moderate", "High")
REPORT_DAYS = 7                          # H10: a station reports if it has a counted reading in the 7 days before C
TRAIL_DAYS, TRAIL_MIN_DAYS = 7, 4        # trailing mean of daily peaks
CHAR_DAYS, CHAR_MIN_DAYS = 30, 20        # station character; missing for a station's first days
RAIN_SLOT_MIN, RAIN_MIN_SHARE = 5, 0.75  # 216 of 288 five-minute readings at the default cut-off
FC_FIRST_ISSUE_MIN = -7 * 60             # forecast issues from 17:00 on T-1 (E5 age limit)
FC_COVER_FROM_MIN, FC_COVER_TO_MIN = 6 * 60, 18 * 60
FC_VALID_HOURS = 24
EARTH_KM = 6371.0088                     # as scripts/static/area_station_distance.py

FEATURES = ["wbgt_peak_d1", "wbgt_peak_mean_7d", "station_char_30d", "n_high_d1", "panel_peak_mean_d1",
            "panel_high_count_d1", "fc_temp_high", "fc_text", "rain_d1_mm", "month", "season"]
CATEGORICAL = ["fc_text", "season"]
SEASONS = ("NE monsoon", "Inter-monsoon 1", "SW monsoon", "Inter-monsoon 2")  # calendar months, as in eda.md
DIAGNOSTICS = ["cutoff_ts", "forecast_missing", "fc_issue_ts", "fc_updated_ts", "fc_lead_h", "fc_text_agrees",
               "rain_station_id", "rain_dist_km", "rain_n_readings", "rain_inputs_max_ts", "panel_n_d1", "wbgt_n_d1",
               "n_days_7d", "n_days_30d", "inputs_max_ts", "inputs_max_day"]
TEXT_COLS = ["text_start_hour", "text_start_day", "text_start_month", "text_end_hour", "text_end_day", "text_end_month"]


def _cutoff(cutoff_minutes):
    """The cut-off must fall after the first forecast issue time (17:00 on T-1): at or before it no forecast could
    qualify and every forecast feature would be missing without warning. At exactly 17:00 only an issue stamped
    17:00:00 could, so that is refused too."""
    c = int(cutoff_minutes)
    if c >= 1440:
        raise ValueError(f"cutoff_minutes must be below 1440 (the end of the target day), got {cutoff_minutes}")
    if c <= FC_FIRST_ISSUE_MIN:
        raise ValueError(f"cutoff_minutes {cutoff_minutes} is at or before the first forecast issue time (17:00 on T-1, "
                         f"{FC_FIRST_ISSUE_MIN}): no forecast could qualify")
    return c


def rain_min_readings(cutoff_minutes=15):
    """75% of yesterday's 5-minute slots before the cut-off: 216 of 288 at the default."""
    c = _cutoff(cutoff_minutes)
    return math.ceil(RAIN_MIN_SHARE * ((1440 + min(c, 0)) // RAIN_SLOT_MIN))


def _haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = F.radians(lat1), F.radians(lat2)
    a = F.sin((p2 - p1) / 2) ** 2 + F.cos(p1) * F.cos(p2) * F.sin(F.radians(F.col(lon2) - F.col(lon1)) / 2) ** 2
    return 2 * EARTH_KM * F.asin(F.sqrt(a))


def _corrected_start():
    """The stored validPeriod.start with its year replaced by the issue year -1, 0 or +1, whichever puts it closest to
    the issue time (E5 (1)). Done on the string, so no time-zone arithmetic; 29 Feb in another year does not parse."""
    year = F.year(sgt_date("issue_ts"))

    def candidate(dy):
        s = parse_ts(F.concat(F.lpad((year + dy).cast("string"), 4, "0"), F.substring("valid_start_raw", 5, 64)))
        gap = F.abs(F.unix_seconds(s) - F.unix_seconds("issue_ts"))
        return F.when(s.isNotNull(), F.struct(gap.alias("gap"), s.alias("start")))

    return F.array_min(F.array(candidate(-1), candidate(0), candidate(1)))["start"]


def forecast_for_targets(fc: DataFrame, targets: DataFrame, cutoff_minutes=15) -> DataFrame:
    """The forecast version each target date may use (note §3.3); one row per target date, forecast_missing when none.

    A candidate is a version (a row of silver.forecast_issues) issued from 17:00 on T-1 to the cut-off, updated at or
    before the cut-off, whose corrected validity (start as in _corrected_start, end = start + 24 h; the stored end is
    never used) covers T 06:00 to 18:00. The latest updated_ts wins, then the latest issue_ts. fc_text_agrees compares
    validPeriod.text with the corrected start and end (day, month and hour; the text has no year)."""
    c = _cutoff(cutoff_minutes)
    t = targets.select("target_date").distinct().withColumns({
        "_cut": sgt_instant("target_date", c),
        "_first_issue": sgt_instant("target_date", FC_FIRST_ISSUE_MIN),
        "_from": sgt_instant("target_date", FC_COVER_FROM_MIN),
        "_to": sgt_instant("target_date", FC_COVER_TO_MIN)})
    f = (fc.select("issue_ts", "updated_ts", "valid_start_raw", "temp_high", "forecast_text", *TEXT_COLS)
         .withColumn("fc_start", _corrected_start())
         .withColumn("fc_end", F.timestamp_seconds(F.unix_seconds("fc_start") + FC_VALID_HOURS * 3600)))
    cand = t.join(f, (F.col("issue_ts") >= F.col("_first_issue")) & (F.col("issue_ts") <= F.col("_cut"))
                  & (F.col("updated_ts") <= F.col("_cut"))
                  & (F.col("fc_start") <= F.col("_from")) & (F.col("fc_end") >= F.col("_to")))
    w = Window.partitionBy("target_date").orderBy(F.col("updated_ts").desc(), F.col("issue_ts").desc())
    sd, ed = sgt_date("fc_start"), sgt_date("fc_end")
    agrees = ((F.col("text_start_hour") == (sgt_minute("fc_start") / 60).cast("int"))
              & (F.col("text_start_day") == F.dayofmonth(sd)) & (F.col("text_start_month") == F.month(sd))
              & (F.col("text_end_hour") == (sgt_minute("fc_end") / 60).cast("int"))
              & (F.col("text_end_day") == F.dayofmonth(ed)) & (F.col("text_end_month") == F.month(ed)))
    best = (cand.withColumn("_rn", F.row_number().over(w)).where(F.col("_rn") == 1)
            .select("target_date", F.col("temp_high").alias("fc_temp_high"), F.col("forecast_text").alias("fc_text"),
                    F.col("issue_ts").alias("fc_issue_ts"), F.col("updated_ts").alias("fc_updated_ts"),
                    ((F.unix_seconds("_from") - F.unix_seconds("updated_ts")) / 3600).alias("fc_lead_h"),
                    F.coalesce(agrees, F.lit(False)).alias("fc_text_agrees")))
    return (t.select("target_date").join(best, "target_date", "left")
            .withColumn("forecast_missing", F.col("fc_updated_ts").isNull()))


def forecast_gaps(fc: DataFrame, targets: DataFrame, cutoff_minutes=15) -> DataFrame:
    """Diagnostic for target dates without a forecast (not a model input): every version known by the cut-off (issued
    or updated at or before it, issued from 00:00 two days before) with the rules of forecast_for_targets it fails.
    gap_reason turns one target date's rows into a sentence."""
    c = _cutoff(cutoff_minutes)
    t = targets.select("target_date").distinct().withColumns({
        "_cut": sgt_instant("target_date", c),
        "_first_issue": sgt_instant("target_date", FC_FIRST_ISSUE_MIN),
        "_from": sgt_instant("target_date", FC_COVER_FROM_MIN),
        "_to": sgt_instant("target_date", FC_COVER_TO_MIN),
        "_window": sgt_instant(F.date_sub("target_date", 2), 0)})
    f = (fc.select("issue_ts", "updated_ts", "valid_start_raw")
         .withColumn("fc_start", _corrected_start())
         .withColumn("fc_end", F.timestamp_seconds(F.unix_seconds("fc_start") + FC_VALID_HOURS * 3600)))
    known = (F.least("issue_ts", "updated_ts") <= F.col("_cut")) & (F.col("issue_ts") >= F.col("_window"))
    return t.join(f, known, "left").select(
        "target_date", F.col("issue_ts").alias("fc_issue_ts"), F.col("updated_ts").alias("fc_updated_ts"),
        F.coalesce((F.col("fc_start") <= F.col("_from")) & (F.col("fc_end") >= F.col("_to")), F.lit(False)).alias("covers"),
        (F.col("issue_ts") < F.col("_first_issue")).alias("before_first_issue"),
        (F.col("issue_ts") > F.col("_cut")).alias("issued_after_cutoff"),
        (F.col("updated_ts") > F.col("_cut")).alias("updated_after_cutoff"),
        (sgt_date("issue_ts") == F.date_sub("target_date", 1)).alias("issued_day_before"))


def gap_reason(rows):
    """One sentence for one target date from its forecast_gaps rows (pandas; timestamps as SGT wall-clock times)."""
    import pandas as pd

    rows = rows[rows.fc_issue_ts.notna()]
    covering = rows[rows.covers.astype(bool)]
    if covering.empty:
        reason = "no issue known by the cut-off has a corrected validity covering 06:00 to 18:00"
        if not rows.issued_day_before.astype(bool).any():
            reason += " (no forecast was issued at all the day before)"
        return reason
    parts = []
    for r in covering.sort_values("fc_issue_ts").itertuples():
        issue, upd = pd.Timestamp(r.fc_issue_ts), pd.Timestamp(r.fc_updated_ts)
        why = []
        if r.before_first_issue:
            why.append(f"the issue of {issue:%H:%M on %d %b} is before 17:00 the day before (age limit)")
        if r.issued_after_cutoff:
            why.append(f"the issue stamped {issue:%H:%M on %d %b} is after the cut-off, although its updated time "
                       f"is {upd:%H:%M on %d %b}")
        if r.updated_after_cutoff:
            why.append(f"the issue of {issue:%H:%M on %d %b} was updated after the cut-off ({upd:%H:%M on %d %b})")
        parts.append("; ".join(why))
    return "covering issue(s) rejected: " + "; ".join(dict.fromkeys(p for p in parts if p))


def _wbgt_days(wbgt, run_date, c):
    """Per station and completed SGT day D: aggregates over all counted readings (first_ts, last_ts, peak_full,
    loc_full) and over those before the cut-off of target D+1, i.e. D seen as yesterday (the _y columns). The two
    differ only for a cut-off before midnight. loc_* is (reading_ts, lat, lon) of the latest located reading."""
    r = (wbgt.where((F.col("sgt_date") < F.lit(run_date)) & F.col("heat_stress").isin(*CATEGORIES))
         .withColumn("_y", F.col("reading_ts") < sgt_instant(F.date_add("sgt_date", 1), c)))
    y = F.col("_y")
    located = F.col("station_lat").isNotNull() & F.col("station_lon").isNotNull()
    loc = F.struct("reading_ts", "station_lat", "station_lon")
    return r.groupBy("station_id", "sgt_date").agg(
        F.min("reading_ts").alias("first_ts"),
        F.max("reading_ts").alias("last_ts"),
        F.max("wbgt").alias("peak_full"),
        F.max(F.when(located, loc)).alias("loc_full"),
        F.count(F.when(y, 1)).alias("n_y"),
        F.max(F.when(y, F.col("reading_ts"))).alias("last_ts_y"),
        F.max(F.when(y, F.col("wbgt"))).alias("peak_y"),
        F.count(F.when(y & (F.col("heat_stress") == "High"), 1)).alias("n_high_y"),
        F.max(F.when(y & located, loc)).alias("loc_y"),
    )


def _panel_days(days, panel):
    """Per day: the panel's mean peak (whole day, and as yesterday) and, as yesterday, how many panel stations
    reported and how many reached High. A station counts only on days it reported."""
    has_y = F.col("n_y") > 0
    return days.where(F.col("station_id").isin(*panel)).groupBy("sgt_date").agg(
        F.avg("peak_full").alias("panel_peak_full"),
        F.avg(F.when(has_y, F.col("peak_y"))).alias("panel_peak_y"),
        F.count(F.when(has_y, 1)).alias("panel_n_y"),
        F.count(F.when(F.col("n_high_y") > 0, 1)).alias("panel_high_y"))


def _station_rows(days, panel_days, t):
    """One row per reporting station and target date with the WBGT features. Each station-day is offered to the
    targets k = 0..30 days later: k = 0 (the target day) only for the reporting test, k = 1 is yesterday (the _y
    aggregates), k >= 2 are whole days."""
    ex = (days.withColumn("k", F.explode(F.sequence(F.lit(0), F.lit(CHAR_DAYS))))
          .withColumn("target_date", F.expr("date_add(sgt_date, k)"))
          .join(t, "target_date")
          .join(panel_days, "sgt_date", "left"))
    k = F.col("k")
    yd, earlier = k == 1, k >= 2
    peak = F.when(yd, F.col("peak_y")).when(earlier, F.col("peak_full"))
    panel_peak = F.when(yd, F.col("panel_peak_y")).when(earlier, F.col("panel_peak_full"))
    used_ts = F.when(yd, F.col("last_ts_y")).when(earlier, F.col("last_ts"))
    loc = F.when(yd, F.col("loc_y")).when(earlier, F.col("loc_full"))
    # exact from day aggregates (as nearest.py): the day holding the window start needs a reading at or after it,
    # the day holding the cut-off a reading before it
    reports = (F.col("last_ts") >= F.col("report_from_ts")) & (F.col("first_ts") < F.col("cutoff_ts"))
    in7, in30 = k.between(1, TRAIL_DAYS), k.between(1, CHAR_DAYS)
    diff = peak - panel_peak
    g = ex.groupBy("station_id", "target_date", "cutoff_ts").agg(
        F.max(F.when(reports, 1)).alias("_reports"),
        F.max(F.when(yd, F.col("peak_y"))).alias("wbgt_peak_d1"),
        F.max(F.when(yd & (F.col("n_y") > 0), F.col("n_high_y"))).alias("n_high_d1"),
        F.coalesce(F.max(F.when(yd, F.col("n_y"))), F.lit(0)).alias("wbgt_n_d1"),
        F.avg(F.when(in7, peak)).alias("_mean7"),
        F.count(F.when(in7, peak)).alias("n_days_7d"),
        F.avg(F.when(in30, diff)).alias("_char"),
        F.count(F.when(in30, diff)).alias("n_days_30d"),
        F.max(used_ts).alias("inputs_max_ts"),
        F.max(loc).alias("_loc"),
    )
    return (g.where(F.col("_reports") == 1)
            .withColumn("wbgt_peak_mean_7d", F.when(F.col("n_days_7d") >= TRAIL_MIN_DAYS, F.col("_mean7")))
            .withColumn("station_char_30d", F.when(F.col("n_days_30d") >= CHAR_MIN_DAYS, F.col("_char")))
            .drop("_reports", "_mean7", "_char"))


def _panel_for_targets(panel_days, t):
    has = F.col("panel_n_y") > 0
    p = panel_days.select(F.date_add("sgt_date", 1).alias("target_date"), "panel_peak_y", "panel_n_y", "panel_high_y")
    return t.select("target_date").join(p, "target_date", "left").select(
        "target_date",
        F.when(has, F.col("panel_peak_y")).alias("panel_peak_mean_d1"),
        F.when(has, F.col("panel_high_y")).alias("panel_high_count_d1"),
        F.coalesce(F.col("panel_n_y"), F.lit(0)).alias("panel_n_d1"))


def _rain_days(rain, run_date, c):
    """Per rainfall station and completed SGT day D, the readings before the cut-off of target D+1: count of values,
    total, latest reading time and the latest location (the station's location by date)."""
    r = rain.where((F.col("sgt_date") < F.lit(run_date))
                   & (F.col("reading_ts") < sgt_instant(F.date_add("sgt_date", 1), c)))
    located = F.col("station_lat").isNotNull() & F.col("station_lon").isNotNull()
    return r.groupBy("station_id", "sgt_date").agg(
        F.count("rainfall_mm").alias("n"),
        F.sum("rainfall_mm").alias("total_mm"),
        F.max("reading_ts").alias("last_ts"),
        F.max(F.when(located, F.struct("reading_ts", "station_lat", "station_lon"))).alias("loc"))


def _rain_for_rows(rows, rain_days, need):
    """Yesterday's total at the rainfall station nearest to the WBGT station (its latest location before the cut-off)
    among stations with at least `need` readings; ties go to the lower station_id."""
    st = rows.select("station_id", "target_date", F.col("_loc.station_lat").alias("_s_lat"),
                     F.col("_loc.station_lon").alias("_s_lon"))
    rd = (rain_days.where((F.col("n") >= need) & F.col("loc").isNotNull())
          .select(F.date_add("sgt_date", 1).alias("target_date"), F.col("station_id").alias("rain_station_id"),
                  F.col("n").alias("rain_n_readings"), F.col("total_mm").alias("rain_d1_mm"),
                  F.col("last_ts").alias("rain_inputs_max_ts"), F.col("loc.station_lat").alias("_r_lat"),
                  F.col("loc.station_lon").alias("_r_lon")))
    j = (st.join(rd, "target_date").withColumn("rain_dist_km", _haversine_km("_s_lat", "_s_lon", "_r_lat", "_r_lon"))
         .where(F.col("rain_dist_km").isNotNull()))
    w = Window.partitionBy("station_id", "target_date").orderBy("rain_dist_km", "rain_station_id")
    return (j.withColumn("_rn", F.row_number().over(w)).where(F.col("_rn") == 1)
            .select("station_id", "target_date", "rain_d1_mm", "rain_station_id", "rain_dist_km", "rain_n_readings",
                    "rain_inputs_max_ts"))


def station_day_features(wbgt: DataFrame, rain: DataFrame, fc: DataFrame, targets: DataFrame, run_date: date,
                         cutoff_minutes=15, panel=ORIGINAL_8) -> DataFrame:
    """wbgt, rain, fc: silver.wbgt_readings, silver.rainfall_readings, silver.forecast_issues (or fixtures with their
    columns); targets: a frame of target_date. One row per reporting station and target date: station_id,
    target_date, FEATURES, then DIAGNOSTICS (not model inputs). Refuses a target date after run_date."""
    c = _cutoff(cutoff_minutes)
    if not isinstance(run_date, date) or isinstance(run_date, datetime):
        raise TypeError(f"run_date must be a date, got {type(run_date).__name__}")
    t = targets.select("target_date").distinct()
    if t.where(F.col("target_date") > F.lit(run_date)).limit(1).count():
        raise ValueError(f"a target date after run_date {run_date}: nothing is predicted beyond the day the job runs")
    t = t.withColumns({"cutoff_ts": sgt_instant("target_date", c),
                       "report_from_ts": sgt_instant(F.date_sub("target_date", REPORT_DAYS), c)})
    days = _wbgt_days(wbgt, run_date, c)
    pdays = _panel_days(days, panel)
    rows = _station_rows(days, pdays, t)
    m = F.month("target_date")
    season = (F.when(m.isin(12, 1, 2), SEASONS[0]).when(m.isin(3, 4, 5), SEASONS[1])
              .when(m.isin(6, 7, 8, 9), SEASONS[2]).otherwise(SEASONS[3]))
    return (rows.join(_panel_for_targets(pdays, t), "target_date", "left")
            .join(forecast_for_targets(fc, t, c), "target_date", "left")
            .join(_rain_for_rows(rows, _rain_days(rain, run_date, c), rain_min_readings(c)),
                  ["station_id", "target_date"], "left")
            .withColumns({"month": m, "season": season, "inputs_max_day": sgt_date("inputs_max_ts")})
            .select("station_id", "target_date", *FEATURES, *DIAGNOSTICS))


def usable_labels(labels: DataFrame, run_date: date, last_date: date = None) -> DataFrame:
    """Usable station-day labels (silver.station_daily_label) from completed days only: sgt_date < run_date, and
    <= last_date when given. A label for the current day is provisional (its coverage rule looks at 10:00 to 17:59
    only), so it is never used. y codes Low, Moderate, High as 0, 1, 2."""
    df = labels.where(F.col("sgt_date") < F.lit(run_date))
    if last_date is not None:
        df = df.where(F.col("sgt_date") <= F.lit(last_date))
    y = (F.when(F.col("label") == "Low", 0).when(F.col("label") == "Moderate", 1)
         .when(F.col("label") == "High", 2))  # a CASE, as in labels.py
    return df.where(F.col("usable")).select("station_id", F.col("sgt_date").alias("target_date"), "label",
                                             y.alias("y"), "n_high")


def assert_completed_days(frame, run_date: date, cols):
    """Fail if any value of the given date columns of a pandas frame is on or after run_date (note §1)."""
    import pandas as pd

    for c in cols:
        days = pd.to_datetime(frame[c].dropna()).dt.date
        late = days[days >= run_date]
        if len(late):
            raise AssertionError(f"{len(late)} value(s) of {c} on or after run_date {run_date} (first {min(late)}): "
                                 "only completed days may be used")
