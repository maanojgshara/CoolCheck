"""Reconcile the raw-files Volume against Bronze (and, with --stage all, against Silver's <feed>_all tables).

Per file: size and modification time from the Volume listing, line count from a plain batch read of the file
(independent of Auto Loader), Bronze rows, and with --stage all the readings parsed from the Volume lines versus the
rows in <feed>_all. Writes <catalog>.silver.dq_reconcile (overwritten each run); the local script
scripts/reconcile/bronze_reconcile.py adds the local files and backfill/progress.jsonl and writes the report.
"""
import argparse
import os
import sys
from datetime import datetime, timezone

ap = argparse.ArgumentParser()
ap.add_argument("--catalog", required=True)
ap.add_argument("--src", required=True)
ap.add_argument("--stage", choices=("bronze", "all"), default="bronze")
args = ap.parse_args()
sys.path.insert(0, args.src)

from pyspark.sql import SparkSession  # noqa: E402

spark = SparkSession.builder.getOrCreate()
from pyspark.sql import functions as F  # noqa: E402

from coolcheck.bronze import FEEDS, bronze_columns, read_raw_batch  # noqa: E402
from coolcheck import silver as S  # noqa: E402

spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
cat = args.catalog
raw_root = f"/Volumes/{cat}/bronze/raw_files"
PARSE = {"wbgt": S.parse_wbgt, "rainfall": S.parse_rainfall, "forecast": S.parse_forecast}
ALL = {"wbgt": "wbgt_readings_all", "rainfall": "rainfall_readings_all", "forecast": "forecast_issues_all"}

listing = []
for feed in FEEDS:
    for root, _dirs, files in os.walk(f"{raw_root}/{feed}"):
        for f in files:
            p = f"{root}/{f}"
            st = os.stat(p)
            listing.append((feed, p, f, st.st_size, datetime.fromtimestamp(st.st_mtime, timezone.utc), f.endswith(".jsonl")))
vol = spark.createDataFrame(listing, "feed STRING, source_file STRING, file_name STRING, vol_size LONG, vol_mtime TIMESTAMP, is_jsonl BOOLEAN")

parts = []
for feed in FEEDS:
    lines = bronze_columns(read_raw_batch(spark, f"{raw_root}/{feed}/"))
    v = lines.groupBy("source_file").agg(F.count(F.lit(1)).alias("vol_lines"))
    b = (spark.table(f"{cat}.bronze.{feed}_raw").groupBy("source_file")
         .agg(F.count(F.lit(1)).alias("bronze_rows"), F.count_distinct("raw").alias("bronze_distinct_lines")))
    part = v.join(b, "source_file", "full_outer").withColumn("feed", F.lit(feed))
    if args.stage == "all":
        pv = PARSE[feed](lines).groupBy("source_file").agg(F.count(F.lit(1)).alias("vol_parsed_rows"))
        ps = spark.table(f"{cat}.silver.{ALL[feed]}").groupBy("source_file").agg(F.count(F.lit(1)).alias("silver_all_rows"))
        part = part.join(pv, "source_file", "full_outer").join(ps, "source_file", "full_outer")
    else:
        part = part.withColumns({"vol_parsed_rows": F.lit(None).cast("long"), "silver_all_rows": F.lit(None).cast("long")})
    parts.append(part.select("feed", "source_file", "vol_lines", "bronze_rows", "bronze_distinct_lines",
                             "vol_parsed_rows", "silver_all_rows"))

counts = parts[0].unionByName(parts[1]).unionByName(parts[2])
out = (vol.join(counts, ["feed", "source_file"], "full_outer")
       .withColumn("stage", F.lit(args.stage)).withColumn("checked_at", F.current_timestamp()))
out.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{cat}.silver.dq_reconcile")

summary = out.groupBy("feed").agg(
    F.count(F.when(F.col("is_jsonl"), 1)).alias("vol_jsonl_files"),
    F.count(F.when(~F.col("is_jsonl"), 1)).alias("vol_other_files"),
    F.sum("vol_lines").alias("vol_lines"), F.sum("bronze_rows").alias("bronze_rows"),
    F.count(F.when(F.coalesce(F.col("vol_lines"), F.lit(-1)) != F.coalesce(F.col("bronze_rows"), F.lit(-1)), 1)).alias("files_lines_differ"),
    F.sum("vol_parsed_rows").alias("vol_parsed_rows"), F.sum("silver_all_rows").alias("silver_all_rows"))
summary.orderBy("feed").show(truncate=False)
