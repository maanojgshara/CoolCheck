"""Create the view <catalog>.gold.area_nearest_station_daily (H10) from the labels and the distance table."""
import argparse
import sys

ap = argparse.ArgumentParser()
ap.add_argument("--catalog", required=True)
ap.add_argument("--src", required=True)
ap.add_argument("--boundary", default="mp2025")
ap.add_argument("--cutoff-minutes", type=int, default=15)
ap.add_argument("--lookback-days", type=int, default=7)
ap.add_argument("--island-rule", action=argparse.BooleanOptionalAction, default=True)
ap.add_argument("--profile", help="run through Databricks Connect (serverless) with this CLI profile instead of the job's own session")
args = ap.parse_args()
sys.path.insert(0, args.src)

if args.profile:
    from databricks.connect import DatabricksSession  # noqa: E402

    spark = DatabricksSession.builder.serverless().profile(args.profile).getOrCreate()
else:
    from pyspark.sql import SparkSession  # noqa: E402

    spark = SparkSession.builder.getOrCreate()

from coolcheck.nearest import nearest_station_sql  # noqa: E402

spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
cat = args.catalog
body = nearest_station_sql(f"{cat}.silver.station_daily_label", f"{cat}.silver.area_station_distance",
                           args.boundary, args.cutoff_minutes, args.lookback_days, args.island_rule)
comment = (f"H10: nearest WBGT station per planning area and target date, among stations with a counted reading in the "
           f"{args.lookback_days} days before the cut-off ({args.cutoff_minutes} min after 00:00 SGT on the target date). "
           f"Boundary {args.boundary}; reference point = the dwelling-unit-weighted mean of the geocoded HDB blocks in the area "
           f"(ref_point column; polygon centroid or a point on the surface for an area with no block). "
           + ("Island rule on: a station inside an island planning area serves only that area." if args.island_rule
              else "Island rule off."))
comment = comment.replace("'", "")  # a quote would end the SQL string literal
spark.sql(f"CREATE OR REPLACE VIEW {cat}.gold.area_nearest_station_daily COMMENT '{comment}' AS {body}")
spark.sql(f"""SELECT count(*) AS rows, count(DISTINCT planning_area) AS areas, min(target_date) AS first_date,
              max(target_date) AS last_date FROM {cat}.gold.area_nearest_station_daily""").show(truncate=False)
spark.sql(f"""SELECT station_id, count(DISTINCT planning_area) AS areas, count(*) AS area_days
              FROM {cat}.gold.area_nearest_station_daily GROUP BY station_id ORDER BY area_days DESC""").show(50, truncate=False)
