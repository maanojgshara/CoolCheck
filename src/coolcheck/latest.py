"""D9 latest readings: the newest value per station and measure for the live panel, and the freshness alarm.

The 15-minute and hourly jobs cannot wait for the nightly pipeline, so they read the collector's live files in the
Volume (today's and yesterday's SGT folders, so a run just after midnight still sees the last hours) and parse them
with the Silver parsers (silver.PARSERS), read-only. Heat categories come from the API field and are carried for WBGT
only; air temperature and rainfall rows have none.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

from coolcheck import silver as S
from coolcheck.bronze import bronze_columns

SGT = ZoneInfo("Asia/Singapore")
MEASURES = ("wbgt", "rainfall", "air_temperature")
LAST_HOUR = "rainfall_last_hour"
# value column in the parsed frame, and the flags that make a reading usable for the panel
VALUE_COL = {"wbgt": "wbgt", "rainfall": "rainfall_mm", "air_temperature": "temp_c"}
USABLE_RULES = {
    "wbgt": ("has_key", "sgt_offset", "wbgt_present", "wbgt_in_range"),
    "rainfall": ("has_key", "sgt_offset", "rain_present", "rain_non_negative"),
    "air_temperature": ("has_key", "sgt_offset", "temp_present", "temp_in_range", "unit_celsius"),
}
LATEST_DDL = ("measure STRING, station_id STRING, station_name STRING, lat DOUBLE, lon DOUBLE, reading_ts TIMESTAMP, "
              "value DOUBLE, unit STRING, heat_stress STRING, n_readings INT, loaded_at TIMESTAMP")
STATUS_DDL = ("measure STRING, last_reading_ts TIMESTAMP, stations_reporting_1h INT, stations_known_24h INT, "
              "age_minutes DOUBLE, loaded_at TIMESTAMP")
LATEST_COLS = [c.split()[0] for c in LATEST_DDL.split(", ")]


def window_dates(now: datetime):
    """The SGT dates whose live folders are read: yesterday and today."""
    today = now.astimezone(SGT).date()
    return [today - timedelta(days=1), today]


def live_folders(root: str, feed: str, now: datetime):
    return [f"{root}/{feed}/live/{d:%Y-%m-%d}" for d in window_dates(now)]


def _instant(ts: datetime):
    return F.timestamp_seconds(F.lit(int(ts.timestamp())))


def read_live(spark, paths) -> DataFrame:
    """Bronze-shaped lines of the finished *.jsonl files in the given folders."""
    df = spark.read.option("pathGlobFilter", "*.jsonl").text(list(paths)).select("value", "_metadata")
    return bronze_columns(df)


def recent_files(bronze: DataFrame, now: datetime, hours: float) -> DataFrame:
    """Keep files whose run started (the SGT time in the file name) at or after now - hours; a name without a run time
    is dropped."""
    started = F.try_to_timestamp(F.regexp_extract("file_name", r"_(\d{4}-\d{2}-\d{2}T\d{6})_", 1),
                                  F.lit("yyyy-MM-dd'T'HHmmss"))
    return bronze.where(started >= _instant(now - timedelta(hours=hours)))


def _usable(parsed: DataFrame, feed: str, now: datetime) -> DataFrame:
    ok = F.lit(True)
    for rule in USABLE_RULES[feed]:
        ok = ok & ~F.col(f"fail_{rule}")
    return parsed.where(ok & (F.col("reading_ts") <= _instant(now)))


def dedupe_copies(usable: DataFrame) -> DataFrame:
    """One copy per (station_id, reading_ts), chosen as Silver does (live over backfill, later file time, path, hash)."""
    order = [F.col(c).desc() for c in S.SEQUENCE_COLS]
    w = Window.partitionBy("station_id", "reading_ts").orderBy(*order)
    return usable.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")


def _rows(df: DataFrame, measure: str, value: str, unit, heat, now: datetime) -> DataFrame:
    return df.select(
        F.lit(measure).alias("measure"), "station_id", "station_name",
        F.col("station_lat").alias("lat"), F.col("station_lon").alias("lon"), "reading_ts",
        F.col(value).alias("value"), unit.alias("unit"), heat.alias("heat_stress"),
        F.lit(None).cast("int").alias("n_readings"), _instant(now).alias("loaded_at"))


def latest_rows(parsed: DataFrame, feed: str, now: datetime) -> DataFrame:
    """The newest usable reading per station. A newest minute that is only partly filled cannot blank a station,
    because a reading with no usable value is not a candidate."""
    deduped = dedupe_copies(_usable(parsed, feed, now))
    w = Window.partitionBy("station_id").orderBy(F.col("reading_ts").desc())
    newest = deduped.withColumn("_rn", F.row_number().over(w)).where("_rn = 1")
    heat = F.col("heat_stress") if feed == "wbgt" else F.lit(None).cast("string")
    unit = F.lit("deg C") if feed == "wbgt" else F.col("reading_unit")
    return _rows(newest, feed, VALUE_COL[feed], unit, heat, now)


def rainfall_last_hour_rows(parsed_rain: DataFrame, stations: DataFrame, now: datetime) -> DataFrame:
    """Per station: the sum of rainfall over readings with reading_ts in (now - 60 min, now], and how many readings it
    used. A station with no reading in the hour gets value NULL and n_readings 0. Copies of a reading in several files
    count once. `stations` has station_id, station_name, lat, lon. parsed_rain is None when there are no live files."""
    start = _instant(now - timedelta(hours=1))
    if parsed_rain is None:
        agg = (stations.select("station_id").limit(0).withColumn("value", F.lit(None).cast("double"))
               .withColumn("n_readings", F.lit(None).cast("int")).withColumn("reading_ts", F.lit(None).cast("timestamp")))
    else:
        in_hour = dedupe_copies(_usable(parsed_rain, "rainfall", now)).where(F.col("reading_ts") > start)
        agg = in_hour.groupBy("station_id").agg(
            F.sum("rainfall_mm").alias("value"), F.count("rainfall_mm").cast("int").alias("n_readings"),
            F.max("reading_ts").alias("reading_ts"))
    st = stations.select("station_id", "station_name", "lat", "lon").dropDuplicates(["station_id"])
    return (st.join(agg, "station_id", "left")
            .select(F.lit(LAST_HOUR).alias("measure"), "station_id", "station_name", "lat", "lon", "reading_ts", "value",
                    F.lit("mm").alias("unit"), F.lit(None).cast("string").alias("heat_stress"),
                    F.coalesce("n_readings", F.lit(0)).cast("int").alias("n_readings"), _instant(now).alias("loaded_at")))


def merge_latest(existing: DataFrame, new: DataFrame) -> DataFrame:
    """The table after this run. A station keeps its newest reading, so an outage leaves the old values in place (the
    stream status shows their age). The last-hour rainfall rows are recomputed every run and always replace the old ones."""
    both = existing.select(*LATEST_COLS).unionByName(new.select(*LATEST_COLS))
    newest = F.when(F.col("measure") == LAST_HOUR, F.lit(0)).otherwise(F.unix_seconds("reading_ts"))
    w = Window.partitionBy("measure", "station_id").orderBy(F.coalesce(newest, F.lit(0)).desc(), F.col("loaded_at").desc())
    return both.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")


def parsed_live(spark, root: str, feed: str, now: datetime, hours: float, exists):
    """The feed's recent live lines, parsed with the Silver parser; None when neither folder exists yet (for example
    air temperature before its collector change is live). `exists` takes a folder path."""
    paths = [p for p in live_folders(root, feed, now) if exists(p)]
    if not paths:
        return None
    return S.PARSERS[feed](recent_files(read_live(spark, paths), now, hours))


def stream_status(latest: DataFrame, now: datetime) -> DataFrame:
    """One row per measure: newest reading, stations reporting in the last hour, stations known (a reading in the last
    24 hours) and the age of the newest reading. A measure with no rows still gets a row, with NULLs."""
    spark = latest.sparkSession
    base = spark.createDataFrame([(m,) for m in MEASURES], "measure STRING")
    hour, day = _instant(now - timedelta(hours=1)), _instant(now - timedelta(hours=24))
    agg = latest.where(F.col("measure").isin(*MEASURES)).groupBy("measure").agg(
        F.max("reading_ts").alias("last_reading_ts"),
        F.count(F.when(F.col("reading_ts") > hour, 1)).cast("int").alias("stations_reporting_1h"),
        F.count(F.when(F.col("reading_ts") > day, 1)).cast("int").alias("stations_known_24h"))
    return (base.join(agg, "measure", "left")
            .select("measure", "last_reading_ts",
                    F.coalesce("stations_reporting_1h", F.lit(0)).cast("int").alias("stations_reporting_1h"),
                    F.coalesce("stations_known_24h", F.lit(0)).cast("int").alias("stations_known_24h"),
                    ((_instant(now).cast("long") - F.col("last_reading_ts").cast("long")) / 60).alias("age_minutes"),
                    _instant(now).alias("loaded_at")))


def freshness_problem(age_minutes, max_age_minutes: float = 90, newest=None):
    """None when the newest WBGT reading is at most max_age_minutes old (age_minutes comes from stream_status);
    otherwise the message the job fails with."""
    if age_minutes is None:
        return "no WBGT reading in the latest-readings table"
    if age_minutes > max_age_minutes:
        when = f" (reading time {newest} SGT)" if newest else ""
        return f"newest WBGT reading is {age_minutes:.0f} minutes old, over the {max_age_minutes:g}-minute limit{when}"
    return None
