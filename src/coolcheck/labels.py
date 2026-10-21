"""Daily station label: the highest NEA heat-stress category a station reached on an SGT day (§14.4).

Only the API's own heatStress field decides the category; no WBGT cut-off is coded. A reading counts if its
heatStress is exactly Low, Moderate or High; NA and any other value are counted and left out.
Coverage: a station-day is low_coverage if fewer than 24 of the 32 15-minute slots from 10:00 to 17:59 SGT hold a
counted reading. A High label always stands (one High reading proves it); a Low or Moderate label on a low-coverage
day may undercount the heat, so it is not usable for training or scoring by default.
"""
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

CATEGORIES = ("Low", "Moderate", "High")
PEAK_START_MIN, PEAK_END_MIN = 10 * 60, 18 * 60  # 10:00 to 17:59 SGT
SLOT_MIN = 15
MIN_PEAK_SLOTS = 24  # of 32

LABEL_RULES = {
    "label_present": "label IS NOT NULL",
    "peak_coverage_ok": "NOT low_coverage",
}


def _rank():
    return (F.when(F.col("heat_stress") == "Low", 1).when(F.col("heat_stress") == "Moderate", 2)
            .when(F.col("heat_stress") == "High", 3))


def _label(rank_col):
    # A CASE, not element_at on a literal array: on serverless, isNull() of element_at(array, NULL) came back false.
    return F.when(rank_col == 1, "Low").when(rank_col == 2, "Moderate").when(rank_col == 3, "High")


def station_daily_label(readings: DataFrame, arrival: DataFrame) -> DataFrame:
    """readings: deduplicated silver.wbgt_readings; arrival: silver.first_arrival(wbgt_readings_all)."""
    r = readings.join(arrival.select("station_id", "reading_ts", "late_over_1h"), ["station_id", "reading_ts"], "left")
    valid = F.col("heat_stress").isin(*CATEGORIES)
    rank = _rank()
    in_peak = valid & (F.col("sgt_minute") >= PEAK_START_MIN) & (F.col("sgt_minute") < PEAK_END_MIN)
    late = F.coalesce(F.col("late_over_1h"), F.lit(False))
    g = r.groupBy("station_id", "sgt_date").agg(
        F.max("station_name").alias("station_name"),
        F.count(F.lit(1)).alias("n_readings"),
        F.count(F.when(valid, 1)).alias("n_valid"),
        F.count(F.when(F.col("heat_stress") == "NA", 1)).alias("n_na"),
        F.count(F.when(~valid & (F.coalesce(F.col("heat_stress"), F.lit("")) != "NA"), 1)).alias("n_other"),
        F.count(F.when(F.col("heat_stress") == "Low", 1)).alias("n_low"),
        F.count(F.when(F.col("heat_stress") == "Moderate", 1)).alias("n_moderate"),
        F.count(F.when(F.col("heat_stress") == "High", 1)).alias("n_high"),
        F.max(F.when(valid, F.col("wbgt"))).alias("max_wbgt"),
        F.count(F.when(F.col("fail_wbgt_in_range"), 1)).alias("n_out_of_range"),
        F.count(F.when(late, 1)).alias("n_late"),
        F.count_distinct(F.when(in_peak, F.floor(F.col("sgt_minute") / SLOT_MIN))).alias("peak_slots"),
        F.min(F.when(valid, F.col("reading_ts"))).alias("first_valid_ts"),
        F.max(F.when(valid, F.col("reading_ts"))).alias("last_valid_ts"),
        F.max(F.when(valid, rank)).alias("_rank"),
        F.max(F.when(valid & ~F.col("fail_wbgt_in_range"), rank)).alias("_rank_in_range"),
        F.max(F.when(valid & ~late, rank)).alias("_rank_on_time"),
    )
    low_cov = F.col("peak_slots") < MIN_PEAK_SLOTS
    return (g.withColumns({
        "label": _label(F.col("_rank")),
        "label_if_out_of_range_excluded": _label(F.col("_rank_in_range")),
        "label_if_late_excluded": _label(F.col("_rank_on_time")),
        "coverage": F.col("n_valid") / 96,
        "low_coverage": low_cov,
    }).withColumn("usable", F.col("label").isNotNull() & ((F.col("label") == "High") | ~F.col("low_coverage")))
     .withColumn("no_label_reason", F.when(F.col("label").isNull(), F.lit("no_valid_reading")))
     .drop("_rank", "_rank_in_range", "_rank_on_time"))
