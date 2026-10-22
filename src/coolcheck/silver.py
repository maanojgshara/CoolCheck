"""Silver: parse Bronze pages into readings and forecast issues, add the C8 flags, prepare the dedupe order.

Every rule is a SQL condition that is TRUE when a row passes. The same strings are the pipeline's expectations
(warn only: violations are logged and the row is kept) and the row-level flag columns `fail_<rule>`.
"""
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from coolcheck.timeutil import parse_ts, sgt_date, sgt_minute

# Column types follow the raw files (survey of all backfill files, 21 Oct): WBGT values and coordinates are strings,
# rainfall coordinates and values are numbers. Strings are cast with try_cast so a bad value becomes NULL and is flagged.
WBGT_SCHEMA = """code INT, errorMsg STRING, data STRUCT<paginationToken: STRING, records: ARRAY<STRUCT<
    datetime: STRING, updatedTimestamp: STRING, item: STRUCT<type: STRING, isStationData: BOOLEAN, readings: ARRAY<STRUCT<
        station: STRUCT<id: STRING, name: STRING, townCenter: STRING>,
        location: STRUCT<latitude: STRING, longitude: STRING>, wbgt: STRING, heatStress: STRING>>>>>>"""

RAINFALL_SCHEMA = """code INT, errorMsg STRING, data STRUCT<paginationToken: STRING, readingType: STRING, readingUnit: STRING,
    stations: ARRAY<STRUCT<id: STRING, deviceId: STRING, name: STRING, location: STRUCT<latitude: DOUBLE, longitude: DOUBLE>>>,
    readings: ARRAY<STRUCT<timestamp: STRING, data: ARRAY<STRUCT<stationId: STRING, value: STRING>>>>>"""

FORECAST_SCHEMA = """code INT, errorMsg STRING, data STRUCT<records: ARRAY<STRUCT<
    date: STRING, timestamp: STRING, updatedTimestamp: STRING,
    general: STRUCT<temperature: STRUCT<low: DOUBLE, high: DOUBLE, unit: STRING>,
        relativeHumidity: STRUCT<low: DOUBLE, high: DOUBLE, unit: STRING>,
        forecast: STRUCT<code: STRING, text: STRING>,
        validPeriod: STRUCT<start: STRING, end: STRING, text: STRING>,
        wind: STRUCT<speed: STRUCT<low: DOUBLE, high: DOUBLE>, direction: STRING>>,
    periods: ARRAY<STRUCT<timePeriod: STRUCT<start: STRING, end: STRING, text: STRING>,
        regions: MAP<STRING, STRUCT<code: STRING, text: STRING>>>>>>>"""

# Air temperature (1-minute, live panel only) has the rainfall response shape: stations plus readings[].data[] of
# {stationId, value}. Its values are JSON numbers, which from_json reads into the STRING field as rainfall's are.
SCHEMAS = {"wbgt": WBGT_SCHEMA, "rainfall": RAINFALL_SCHEMA, "forecast": FORECAST_SCHEMA,
           "air_temperature": RAINFALL_SCHEMA}

META = ["source_file", "file_name", "file_mtime", "file_size", "source_kind", "file_date", "ingested_at"]

WBGT_RULES = {
    "has_key": "station_id IS NOT NULL AND reading_ts IS NOT NULL",
    "sgt_offset": "reading_ts_raw LIKE '%+08:00'",
    "heat_stress_known": "heat_stress IN ('Low', 'Moderate', 'High')",
    "wbgt_present": "wbgt IS NOT NULL",
    "wbgt_in_range": "wbgt IS NULL OR wbgt BETWEEN 20 AND 36",
    "file_date_matches": "file_date IS NULL OR sgt_date = file_date",
}

RAINFALL_RULES = {
    "has_key": "station_id IS NOT NULL AND reading_ts IS NOT NULL",
    "sgt_offset": "reading_ts_raw LIKE '%+08:00'",
    "rain_present": "rainfall_mm IS NOT NULL",
    "rain_non_negative": "rainfall_mm IS NULL OR rainfall_mm >= 0",
    "station_listed": "station_lat IS NOT NULL",
    "file_date_matches": "file_date IS NULL OR sgt_date = file_date",
}

AIR_TEMPERATURE_RULES = {
    "has_key": "station_id IS NOT NULL AND reading_ts IS NOT NULL",
    "sgt_offset": "reading_ts_raw LIKE '%+08:00'",
    "temp_present": "temp_c IS NOT NULL",
    # a gross-error screen: the 22 Oct 2026 sample ran 30.2 to 33.9; tune after a week of data
    "temp_in_range": "temp_c IS NULL OR temp_c BETWEEN 20 AND 40",
    "unit_celsius": "reading_unit = 'deg C'",
    "station_listed": "station_lat IS NOT NULL",
    "minute_aligned": "second(reading_ts) = 0",
}

FORECAST_RULES = {
    "has_key": "issue_ts IS NOT NULL AND updated_ts IS NOT NULL",
    "sgt_offset": "issue_ts_raw LIKE '%+08:00'",
    "record_date_matches": "record_date = CAST(issue_sgt_date AS STRING)",
    "file_date_matches": "file_date IS NULL OR issue_sgt_date = file_date",
    "validity_parsed": "valid_start IS NOT NULL AND valid_end IS NOT NULL",
    "validity_end_after_start": "valid_end > valid_start",
    "validity_24h": "valid_hours = 24",
    # observed spread (21 Oct survey): -5 h to +24 h apart from year errors; the rule catches the year errors
    "validity_start_near_issue": "issue_to_start_hours BETWEEN -6 AND 24",
    "validity_text_parsed": "text_start_hour IS NOT NULL",
    "validity_text_agrees": ("text_start_hour = valid_start_hour AND text_start_day = day(valid_start_sgt_date)"
                             " AND text_start_month = month(valid_start_sgt_date) AND text_end_hour = valid_end_hour"
                             " AND text_end_day = day(valid_end_sgt_date) AND text_end_month = month(valid_end_sgt_date)"),
    "temp_present": "temp_low IS NOT NULL AND temp_high IS NOT NULL",
    "temp_in_range": "(temp_low IS NULL OR temp_low BETWEEN 15 AND 40) AND (temp_high IS NULL OR temp_high BETWEEN 15 AND 40)",
}

RULES = {"wbgt": WBGT_RULES, "rainfall": RAINFALL_RULES, "forecast": FORECAST_RULES,
         "air_temperature": AIR_TEMPERATURE_RULES}
KEYS = {"wbgt": ["station_id", "reading_ts"], "rainfall": ["station_id", "reading_ts"],
        "forecast": ["issue_ts", "updated_ts"], "air_temperature": ["station_id", "reading_ts"]}

# Auto CDC keeps the copy with the highest value: live over backfill, then the later file time, then the later file
# path, then the content hash (copies with equal hashes are identical, so that last tie cannot change the result).
SEQUENCE_COLS = ["source_rank", "file_mtime", "source_file", "content_hash"]


def sequence_col():
    return F.struct(*SEQUENCE_COLS)


def with_flags(df: DataFrame, rules: dict) -> DataFrame:
    """Add fail_<rule> = NOT rule (a NULL result counts as a failure)."""
    return df.withColumns({f"fail_{k}": ~F.coalesce(F.expr(v), F.lit(False)) for k, v in rules.items()})


def _content_hash(*cols):
    return F.sha2(F.concat_ws("|", *[F.coalesce(F.col(c).cast("string"), F.lit("<null>")) for c in cols]), 256)


def _with_meta_order(df: DataFrame) -> DataFrame:
    return df.withColumn("source_rank", F.when(F.col("source_kind") == "live", 1).otherwise(0))


def _pages(bronze: DataFrame, feed: str) -> DataFrame:
    j = bronze.withColumn("j", F.from_json("raw", SCHEMAS[feed]))
    return j.where("j IS NOT NULL AND j.code = 0 AND j.data IS NOT NULL")


def quarantine_lines(bronze: DataFrame, feed: str) -> DataFrame:
    """Lines that are not a usable page: unparsable JSON, code != 0, or no data. Kept with the reason, never dropped."""
    # from_json gives a struct of NULLs (not NULL) for a malformed line, so test for a JSON object separately
    j = bronze.withColumn("j", F.from_json("raw", SCHEMAS[feed]))
    reason = (F.when(F.json_object_keys("raw").isNull(), "unparsable_json")
              .when(F.col("j.code").isNull() | (F.col("j.code") != 0), F.concat(F.lit("api_code_"), F.coalesce(F.col("j.code").cast("string"), F.lit("null"))))
              .when(F.col("j.data").isNull(), "no_data_field"))
    return (j.withColumn("reason", reason).where("reason IS NOT NULL")
            .select(F.lit(feed).alias("feed"), "reason", F.col("j.errorMsg").alias("error_msg"), "raw", *META))


def parse_wbgt(bronze: DataFrame) -> DataFrame:
    recs = _pages(bronze, "wbgt").select(*META, F.explode("j.data.records").alias("r"))
    rd = recs.select(*META, F.col("r.datetime").alias("reading_ts_raw"), F.col("r.updatedTimestamp").alias("updated_ts_raw"),
                     F.explode("r.item.readings").alias("x"))
    out = rd.select(
        F.col("x.station.id").alias("station_id"),
        F.col("x.station.name").alias("station_name"),
        F.col("x.station.townCenter").alias("town_center"),
        F.expr("try_cast(x.location.latitude AS DOUBLE)").alias("station_lat"),
        F.expr("try_cast(x.location.longitude AS DOUBLE)").alias("station_lon"),
        "reading_ts_raw",
        parse_ts("reading_ts_raw").alias("reading_ts"),
        "updated_ts_raw",
        parse_ts("updated_ts_raw").alias("updated_ts"),
        F.col("x.wbgt").alias("wbgt_raw"),
        F.expr("try_cast(x.wbgt AS DOUBLE)").alias("wbgt"),
        F.col("x.heatStress").alias("heat_stress"),
        *META,
    )
    out = out.withColumns({"sgt_date": sgt_date("reading_ts"), "sgt_minute": sgt_minute("reading_ts"),
                           "content_hash": _content_hash("station_name", "town_center", "station_lat", "station_lon",
                                                         "wbgt_raw", "heat_stress", "updated_ts_raw")})
    return with_flags(_with_meta_order(out), WBGT_RULES)


def _parse_station_series(bronze: DataFrame, feed: str, raw_col: str, value_col: str, rules: dict) -> DataFrame:
    """Pages of stations plus readings[].data[] of {stationId, value} -> one row per station and timestamp.
    Rainfall and air temperature share this response shape."""
    pages = _pages(bronze, feed).select(
        *META, F.col("j.data.readingType").alias("reading_type"), F.col("j.data.readingUnit").alias("reading_unit"),
        F.map_from_entries(F.transform("j.data.stations", lambda s: F.struct(s["id"], s))).alias("stations"),
        F.explode("j.data.readings").alias("r"))
    rd = pages.select(*META, "reading_type", "reading_unit", "stations",
                      F.col("r.timestamp").alias("reading_ts_raw"), F.explode("r.data").alias("x"))
    st = F.element_at("stations", F.col("x.stationId"))
    out = rd.select(
        F.col("x.stationId").alias("station_id"),
        st["name"].alias("station_name"),
        st["location"]["latitude"].alias("station_lat"),
        st["location"]["longitude"].alias("station_lon"),
        "reading_ts_raw",
        parse_ts("reading_ts_raw").alias("reading_ts"),
        F.col("x.value").alias(raw_col),
        F.expr("try_cast(x.value AS DOUBLE)").alias(value_col),
        "reading_type", "reading_unit",
        *META,
    )
    out = out.withColumns({"sgt_date": sgt_date("reading_ts"), "sgt_minute": sgt_minute("reading_ts"),
                           "content_hash": _content_hash("station_name", "station_lat", "station_lon", raw_col,
                                                         "reading_type", "reading_unit")})
    return with_flags(_with_meta_order(out), rules)


def parse_rainfall(bronze: DataFrame) -> DataFrame:
    return _parse_station_series(bronze, "rainfall", "rainfall_raw", "rainfall_mm", RAINFALL_RULES)


def parse_air_temperature(bronze: DataFrame) -> DataFrame:
    return _parse_station_series(bronze, "air_temperature", "temp_raw", "temp_c", AIR_TEMPERATURE_RULES)


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _month_number(c):
    # a CASE chain, not element_at on a literal map (see labels._label: its NULL handling was wrong on serverless)
    out = F.when(c == _MONTHS[0], 1)
    for i, m in enumerate(_MONTHS[1:], 2):
        out = out.when(c == m, i)
    return out

# validPeriod.text, e.g. "0 AM 18 Jan to 0 AM 19 Jan" or "6 PM 17 Jan to 6 PM 18 Jan"
_TEXT_RE = r"^\s*(\d{1,2}) (AM|PM) (\d{1,2}) ([A-Za-z]{3}) to (\d{1,2}) (AM|PM) (\d{1,2}) ([A-Za-z]{3})\s*$"


def _text_part(i):
    s = F.regexp_extract("valid_text", _TEXT_RE, i)
    return F.when(s != "", s)


def _text_hour(h, ampm):
    hh = _text_part(h).cast("int") % 12
    return F.when(_text_part(ampm) == "PM", hh + 12).otherwise(hh)


def _periods_for_hash(col):
    """periods with each period's regions as (key, value) entries sorted by key. The API sends the regions in no fixed
    order and a map's JSON keeps the order it arrived in, so hashing the map itself called reordered copies different."""
    return F.transform(col, lambda p: F.struct(p["timePeriod"].alias("timePeriod"),
                                               F.array_sort(F.map_entries(p["regions"])).alias("regions")))


def parse_forecast(bronze: DataFrame) -> DataFrame:
    recs = _pages(bronze, "forecast").select(*META, F.explode("j.data.records").alias("r"))
    g = "r.general"
    out = recs.select(
        F.col("r.date").alias("record_date"),
        F.col("r.timestamp").alias("issue_ts_raw"),
        F.col("r.updatedTimestamp").alias("updated_ts_raw"),
        parse_ts("r.timestamp").alias("issue_ts"),
        parse_ts("r.updatedTimestamp").alias("updated_ts"),
        F.col(f"{g}.validPeriod.start").alias("valid_start_raw"),
        F.col(f"{g}.validPeriod.end").alias("valid_end_raw"),
        F.col(f"{g}.validPeriod.text").alias("valid_text"),
        parse_ts(f"{g}.validPeriod.start").alias("valid_start"),
        parse_ts(f"{g}.validPeriod.end").alias("valid_end"),
        F.col(f"{g}.temperature.low").alias("temp_low"),
        F.col(f"{g}.temperature.high").alias("temp_high"),
        F.col(f"{g}.relativeHumidity.low").alias("rh_low"),
        F.col(f"{g}.relativeHumidity.high").alias("rh_high"),
        F.col(f"{g}.forecast.code").alias("forecast_code"),
        F.col(f"{g}.forecast.text").alias("forecast_text"),
        F.col(f"{g}.wind.speed.low").alias("wind_low"),
        F.col(f"{g}.wind.speed.high").alias("wind_high"),
        F.col(f"{g}.wind.direction").alias("wind_direction"),
        F.col("r.periods").alias("periods"),
        *META,
    )
    out = out.withColumns({
        "issue_sgt_date": sgt_date("issue_ts"),
        "valid_hours": (F.unix_seconds("valid_end") - F.unix_seconds("valid_start")) / 3600,
        "issue_to_start_hours": (F.unix_seconds("valid_start") - F.unix_seconds("issue_ts")) / 3600,
        "valid_start_sgt_date": sgt_date("valid_start"),
        "valid_end_sgt_date": sgt_date("valid_end"),
        "valid_start_hour": (sgt_minute("valid_start") / 60).cast("int"),
        "valid_end_hour": (sgt_minute("valid_end") / 60).cast("int"),
        "text_start_hour": _text_hour(1, 2),
        "text_start_day": _text_part(3).cast("int"),
        "text_start_month": _month_number(_text_part(4)),
        "text_end_hour": _text_hour(5, 6),
        "text_end_day": _text_part(7).cast("int"),
        "text_end_month": _month_number(_text_part(8)),
        "content_hash": F.sha2(F.to_json(F.struct(
            "record_date", "valid_start_raw", "valid_end_raw", "valid_text", "temp_low", "temp_high", "rh_low",
            "rh_high", "forecast_code", "forecast_text", "wind_low", "wind_high", "wind_direction",
            _periods_for_hash("periods").alias("periods"))), 256),
    })
    return with_flags(_with_meta_order(out), FORECAST_RULES)


def first_arrival(all_copies: DataFrame) -> DataFrame:
    """Per reading (station_id, reading_ts): when a live file first carried it, and whether that was over 1 h late.

    Judged on the first copy, because the collector re-fetches the last 2 hours and later copies arrive later by design.
    Backfill file times say nothing about when a reading was available live, so backfill-only readings are never late.
    Readings timed before the first live file landed (before_first_live) are never late either: that first file
    carries the history on its pages (about 6 h of WBGT), which says nothing about the collector's timeliness.
    """
    live_mtime = F.when(F.col("source_kind") == "live", F.col("file_mtime"))
    keyed = all_copies.where("NOT fail_has_key")
    start = keyed.agg(F.min(live_mtime).alias("first_live_file"))
    return (keyed.groupBy("station_id", "reading_ts").agg(F.min(live_mtime).alias("first_live_arrival"))
            .crossJoin(start)
            .withColumn("before_first_live", F.coalesce(F.col("reading_ts") < F.col("first_live_file"), F.lit(False)))
            .withColumn("late_over_1h", ~F.col("before_first_live") & F.coalesce(
                F.unix_seconds("first_live_arrival") - F.unix_seconds("reading_ts") > 3600, F.lit(False))))


# One place for the feed -> parser and feed -> Silver table name maps (the pipeline and the reconcile job both use them).
PARSERS = {"wbgt": parse_wbgt, "rainfall": parse_rainfall, "forecast": parse_forecast, "air_temperature": parse_air_temperature}
NAMES = {"wbgt": "wbgt_readings", "rainfall": "rainfall_readings", "forecast": "forecast_issues",
         "air_temperature": "air_temperature_readings"}
