"""Bronze: one row per line of a raw .jsonl file (one API page), kept as the string the API returned."""
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

FEEDS = ("wbgt", "rainfall", "forecast", "air_temperature")


def read_raw_stream(spark, path: str) -> DataFrame:
    """Auto Loader over <raw_root>/<feed>/ (subfolders included); only finished *.jsonl files, never .partial."""
    return (spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "text")
            .option("pathGlobFilter", "*.jsonl")
            .load(path)
            .select("value", "_metadata"))


def read_raw_batch(spark, path: str) -> DataFrame:
    """The same files read as a plain batch, independent of Auto Loader (used by the reconcile job)."""
    return (spark.read.option("recursiveFileLookup", "true").option("pathGlobFilter", "*.jsonl")
            .text(path).select("value", "_metadata"))


def bronze_columns(df: DataFrame) -> DataFrame:
    """value + _metadata -> Bronze columns. file_date is the SGT day in a backfill file name (wbgt_2025-01-16.jsonl)."""
    path = F.regexp_replace(F.col("_metadata.file_path"), "^dbfs:", "")
    name = F.col("_metadata.file_name")
    kind = F.when(path.contains("/backfill/"), F.lit("backfill")).otherwise(F.lit("live"))
    stamp = F.regexp_extract(name, r"(\d{4}-\d{2}-\d{2})", 1)
    return df.select(
        F.col("value").alias("raw"),
        path.alias("source_file"),
        name.alias("file_name"),
        F.col("_metadata.file_size").alias("file_size"),
        F.col("_metadata.file_modification_time").alias("file_mtime"),
        kind.alias("source_kind"),
        F.when((kind == "backfill") & (stamp != ""),
               F.try_to_timestamp(stamp, F.lit("yyyy-MM-dd")).cast("date")).alias("file_date"),
        F.current_timestamp().alias("ingested_at"),
    )
