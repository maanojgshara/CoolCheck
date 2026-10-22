"""D9 latest-readings job: refresh gold.latest_readings and gold.stream_status from the collector's live files, then
fail when the newest WBGT reading is older than --max-age-minutes (the job's failure e-mail is the freshness alarm).

Reads today's and yesterday's live folders in the raw-files Volume (files started in the last --hours hours), not
Bronze: Bronze only moves when the pipeline runs. Both tables are written before the check, so the panel still shows
the stale times when the alarm fires.
"""
import argparse
import os
import sys
from datetime import datetime

ap = argparse.ArgumentParser()
ap.add_argument("--catalog", required=True)
ap.add_argument("--src", required=True)
ap.add_argument("--hours", type=float, default=3, help="read live files whose run started within this many hours")
ap.add_argument("--max-age-minutes", type=float, default=90)
ap.add_argument("--now", help="ISO time with offset, for a rerun or a test (default: the current time)")
args = ap.parse_args()
sys.path.insert(0, args.src)

from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

spark = SparkSession.builder.getOrCreate()
from coolcheck import latest as L  # noqa: E402

spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
cat = args.catalog
root = f"/Volumes/{cat}/bronze/raw_files"
now = datetime.fromisoformat(args.now) if args.now else datetime.now(L.SGT)
if now.tzinfo is None:
    raise SystemExit("--now needs a UTC offset, for example 2026-10-22T16:30:00+08:00")
latest_t, status_t = f"{cat}.gold.latest_readings", f"{cat}.gold.stream_status"
spark.sql(f"CREATE TABLE IF NOT EXISTS {latest_t} ({L.LATEST_DDL})")
spark.sql(f"CREATE TABLE IF NOT EXISTS {status_t} ({L.STATUS_DDL})")
# tables created before a column was added to LATEST_DDL get it here, at the end, so the positional insert below fits
have = set(spark.table(latest_t).columns)
for col in L.LATEST_DDL.split(", "):
    if col.split()[0] not in have:
        spark.sql(f"ALTER TABLE {latest_t} ADD COLUMNS ({col})")

# everything stays in Spark (no collect and rebuild, which could shift timestamps between the Python and session
# time zones); Delta reads a snapshot, so the overwrite below can replace the table this plan reads
existing = spark.table(latest_t)
parsed = {feed: L.parsed_live(spark, root, feed, now, args.hours, os.path.isdir) for feed in L.MEASURES}
new = spark.createDataFrame([], L.LATEST_DDL)
for feed, df in parsed.items():
    if df is not None:
        new = new.unionByName(L.latest_rows(df, feed, now))
merged = L.merge_latest(existing, new)
stations = merged.where("measure = 'rainfall'").select("station_id", "station_name", "lat", "lon")
merged = L.merge_latest(merged, L.rainfall_last_hour_rows(parsed["rainfall"], stations, now))
merged.write.insertInto(latest_t, overwrite=True)
L.stream_status(spark.table(latest_t), now).write.insertInto(status_t, overwrite=True)

# times are formatted in Spark (session time zone Asia/Singapore), so the log shows SGT, not the driver's UTC clock
status = spark.table(status_t).withColumn("newest_sgt", F.date_format("last_reading_ts", "yyyy-MM-dd HH:mm"))
for r in status.collect():
    print(f"{r.measure}: newest {r.newest_sgt} SGT, reporting in the last hour {r.stations_reporting_1h} of "
          f"{r.stations_known_24h}, age {r.age_minutes if r.age_minutes is None else round(r.age_minutes, 1)} min")
end = (spark.table(latest_t).where(f"measure = '{L.LAST_HOUR}'")
       .agg(F.date_format(F.max("window_end"), "yyyy-MM-dd HH:mm").alias("end")).collect()[0].end)
print(f"{L.LAST_HOUR}: window ends {end} SGT (the newest time at least half of the stations reporting in the last "
      f"hour have reached)" if end else f"{L.LAST_HOUR}: no window (no rainfall station reported in the last hour)")
wbgt = status.where("measure = 'wbgt'").collect()[0]
problem = L.freshness_problem(wbgt.age_minutes, args.max_age_minutes, wbgt.newest_sgt)
if problem:
    raise RuntimeError(f"FRESHNESS ALARM: {problem}")
print("fresh")
