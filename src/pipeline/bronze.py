"""Bronze: Auto Loader (triggered; the pipeline processes what is available, then stops) from the raw-files Volume.

pipelines.reset.allowed=false: a full refresh of the pipeline does not truncate these tables.
"""
import sys

from pyspark import pipelines as dp

sys.path.insert(0, spark.conf.get("coolcheck.src_path"))  # noqa: F821 (spark is provided by the pipeline)
from coolcheck.bronze import FEEDS, bronze_columns, read_raw_stream  # noqa: E402

CATALOG = spark.conf.get("coolcheck.catalog")  # noqa: F821
RAW_ROOT = spark.conf.get("coolcheck.raw_root")  # noqa: F821


def _bronze(feed):
    @dp.table(name=f"{CATALOG}.bronze.{feed}_raw",
              comment=f"Raw {feed} API pages, one row per line of the .jsonl files in {RAW_ROOT}/{feed}/, as received.",
              table_properties={"pipelines.reset.allowed": "false"})
    def _table():
        return bronze_columns(read_raw_stream(spark, f"{RAW_ROOT}/{feed}/"))  # noqa: F821


for _feed in FEEDS:
    _bronze(_feed)
