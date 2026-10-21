"""Data-quality tables: short and no-data days, rule counts, conflicting copies, silent stations."""
from functools import reduce

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

from coolcheck.silver import KEYS, RULES

EXPECTED_TIMESTAMPS = {"wbgt": 96, "rainfall": 288}  # every 15 and every 5 minutes (§12.6 item 8)
SILENT_MINUTES = 60


def _union(dfs):
    return reduce(lambda a, b: a.unionByName(b), dfs)


def dq_day(wbgt: DataFrame, rainfall: DataFrame, forecast: DataFrame) -> DataFrame:
    """One row per feed and SGT day from the first to the last day seen in any feed. Nothing is dropped:
    days with no data appear with status no_data."""
    per = []
    for feed, df in (("wbgt", wbgt), ("rainfall", rainfall)):
        per.append(df.groupBy("sgt_date").agg(
            F.count(F.lit(1)).alias("n_rows"), F.count_distinct("reading_ts").alias("n_timestamps"),
            F.count_distinct("station_id").alias("n_stations")).withColumn("feed", F.lit(feed)))
    per.append(forecast.groupBy(F.col("issue_sgt_date").alias("sgt_date")).agg(
        F.count(F.lit(1)).alias("n_rows"), F.count_distinct("issue_ts").alias("n_timestamps"))
        .withColumns({"n_stations": F.lit(None).cast("long"), "feed": F.lit("forecast")}))
    seen = _union(per)
    bounds = seen.agg(F.min("sgt_date").alias("d0"), F.max("sgt_date").alias("d1"))
    cal = (bounds.select(F.explode(F.sequence("d0", "d1")).alias("sgt_date"))
           .crossJoin(seen.sparkSession.createDataFrame([(f,) for f in ("wbgt", "rainfall", "forecast")], "feed STRING")))
    exp = F.when(F.col("feed") == "wbgt", EXPECTED_TIMESTAMPS["wbgt"]).when(F.col("feed") == "rainfall", EXPECTED_TIMESTAMPS["rainfall"])
    out = (cal.join(seen, ["feed", "sgt_date"], "left")
           .withColumns({"n_rows": F.coalesce("n_rows", F.lit(0)), "n_timestamps": F.coalesce("n_timestamps", F.lit(0)),
                         "expected_timestamps": exp}))
    status = (F.when(F.col("n_rows") == 0, "no_data")
              .when(F.col("expected_timestamps").isNotNull() & (F.col("n_timestamps") < F.col("expected_timestamps")), "short")
              .otherwise("ok"))
    note = F.when(F.col("expected_timestamps").isNotNull(), F.format_string("%d of %d timestamps", "n_timestamps", "expected_timestamps")) \
            .otherwise(F.format_string("%d issues", "n_timestamps"))
    return out.withColumn("status", status).withColumn("note", note).select(
        "feed", "sgt_date", "status", "n_timestamps", "expected_timestamps", "n_stations", "n_rows", "note")


def dq_conflicts(all_copies: DataFrame, feed: str) -> DataFrame:
    """Every copy of every key whose copies differ in content (more than one distinct content_hash)."""
    keys = KEYS[feed]
    keyed = all_copies.where("NOT fail_has_key")
    bad = keyed.groupBy(*keys).agg(F.count_distinct("content_hash").alias("n_versions")).where("n_versions > 1")
    value_cols = [c for c in keyed.columns if not c.startswith("fail_") and c not in ("periods",)]
    return (keyed.join(bad, keys).select(
        F.lit(feed).alias("feed"), F.to_json(F.struct(*keys)).alias("key"), "n_versions", "source_kind", "source_file",
        "file_mtime", "content_hash", F.to_json(F.struct(*value_cols)).alias("copy_json")))


def dq_events(all_by_feed: dict, quarantine: DataFrame, arrivals: dict) -> DataFrame:
    """Counts per feed and check: each rule's failures, copies and duplicates, quarantined lines, late readings,
    station location changes."""
    rows = []
    for feed, df in all_by_feed.items():
        rule_counts = df.agg(*[F.count(F.when(F.col(f"fail_{r}"), 1)).alias(r) for r in RULES[feed]],
                             F.count(F.lit(1)).alias("_rows"))
        stack = ", ".join(f"'rule:{r}', `{r}`" for r in RULES[feed])
        rows.append(rule_counts.select(F.lit(feed).alias("feed"),
                                       F.expr(f"stack({len(RULES[feed])}, {stack}) AS (check_name, n)"),
                                       F.format_string("of %d rows (all copies)", "_rows").alias("detail")))
        keys = KEYS[feed]
        keyed = df.where("NOT fail_has_key")
        per_key = keyed.groupBy(*keys).agg(F.count(F.lit(1)).alias("copies"),
                                           F.count_distinct("content_hash").alias("versions"))
        c = per_key.agg(F.sum("copies").alias("copies"), F.count(F.lit(1)).alias("keys"),
                        F.count(F.when(F.col("copies") > 1, 1)).alias("dup_keys"),
                        F.count(F.when(F.col("versions") > 1, 1)).alias("conflict_keys"))
        rows.append(c.select(F.lit(feed).alias("feed"), F.expr(
            "stack(4, 'copies_with_key', copies, 'distinct_keys', keys, 'keys_with_duplicate_copies', dup_keys, "
            "'keys_with_conflicting_copies', conflict_keys) AS (check_name, n)"),
            F.lit("dedupe keys: " + ", ".join(keys)).alias("detail")))
        if "station_lat" in df.columns:
            loc = (keyed.where("station_lat IS NOT NULL").groupBy("station_id")
                   .agg(F.count_distinct(F.round("station_lat", 3), F.round("station_lon", 3)).alias("n_loc"))
                   .where("n_loc > 1"))
            rows.append(loc.agg(F.count(F.lit(1)).alias("n"),
                                F.concat_ws(", ", F.sort_array(F.collect_list("station_id"))).alias("ids"))
                        .select(F.lit(feed).alias("feed"), F.lit("stations_moved_over_about_100m").alias("check_name"), "n",
                                F.concat(F.lit("location differs at 3 decimal places: "), F.col("ids")).alias("detail")))
    for feed, arr in arrivals.items():
        rows.append(arr.agg(F.count(F.when(F.col("late_over_1h"), 1)).alias("n"),
                            F.count(F.when(F.col("first_live_arrival").isNotNull(), 1)).alias("live"))
                    .select(F.lit(feed).alias("feed"), F.lit("readings_first_arrived_over_1h_late").alias("check_name"), "n",
                            F.format_string("of %d readings seen in live files (backfill readings are never late)", "live").alias("detail")))
    rows.append(quarantine.groupBy("feed", "reason").agg(F.count(F.lit(1)).alias("n"))
                .select("feed", F.concat(F.lit("quarantine:"), "reason").alias("check_name"), "n",
                        F.lit("lines kept in silver.quarantine").alias("detail")))
    return _union([r.select("feed", "check_name", F.col("n").cast("long").alias("n"), "detail") for r in rows])


def station_gaps(readings: DataFrame, feed: str, value_ok: str) -> DataFrame:
    """Gaps over 60 minutes between consecutive usable readings of a station (C8 'silent for over an hour')."""
    w = Window.partitionBy("station_id").orderBy("reading_ts")
    r = readings.where(value_ok).select("station_id", "reading_ts").withColumn("prev_ts", F.lag("reading_ts").over(w))
    gap = (F.unix_seconds("reading_ts") - F.unix_seconds("prev_ts")) / 60
    return (r.withColumn("gap_minutes", gap).where(F.col("gap_minutes") > SILENT_MINUTES)
            .select(F.lit(feed).alias("feed"), "station_id", F.col("prev_ts").alias("gap_start"),
                    F.col("reading_ts").alias("gap_end"), "gap_minutes"))


def forecast_periods(issues: DataFrame) -> DataFrame:
    p = issues.select("issue_ts", "updated_ts", "issue_sgt_date", F.explode("periods").alias("p"))
    return p.select("issue_ts", "updated_ts", "issue_sgt_date",
                    F.col("p.timePeriod.start").alias("period_start_raw"), F.col("p.timePeriod.end").alias("period_end_raw"),
                    F.col("p.timePeriod.text").alias("period_text"), F.explode("p.regions").alias("region", "r")) \
            .select("issue_ts", "updated_ts", "issue_sgt_date", "period_start_raw", "period_end_raw", "period_text",
                    "region", F.col("r.code").alias("code"), F.col("r.text").alias("text"))
