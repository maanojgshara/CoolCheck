"""Silver: parse every copy (<feed>_all, C8 rules as warn-only expectations plus fail_ flag columns), quarantine
unusable lines, then Auto CDC (SCD type 1) for the deduplicated tables."""
import sys

from pyspark import pipelines as dp

sys.path.insert(0, spark.conf.get("coolcheck.src_path"))  # noqa: F821
from coolcheck import silver as S  # noqa: E402

CATALOG = spark.conf.get("coolcheck.catalog")  # noqa: F821

PARSERS = {"wbgt": S.parse_wbgt, "rainfall": S.parse_rainfall, "forecast": S.parse_forecast}
NAMES = {"wbgt": "wbgt_readings", "rainfall": "rainfall_readings", "forecast": "forecast_issues"}


def _silver(feed):
    name = NAMES[feed]

    @dp.table(name=f"{name}_all", comment=f"Every parsed copy of {feed}, nothing removed; fail_<rule> flags (C8).")
    @dp.expect_all(S.RULES[feed])
    def _all():
        return PARSERS[feed](spark.readStream.table(f"{CATALOG}.bronze.{feed}_raw"))  # noqa: F821

    @dp.temporary_view(name=f"{name}_keyed")
    def _keyed():
        # Rows without a key stay in <feed>_all (flagged and counted in dq_events); they cannot be deduplicated.
        return spark.readStream.table(f"{name}_all").where("NOT fail_has_key")  # noqa: F821

    dp.create_streaming_table(name=name, comment=f"Deduplicated {feed}; keys {', '.join(S.KEYS[feed])}; "
                                                 "tie-break live > backfill, later file time, file path, content hash.")
    dp.create_auto_cdc_flow(target=name, source=f"{name}_keyed", keys=S.KEYS[feed],
                            sequence_by=S.sequence_col(), stored_as_scd_type=1)


for _feed in PARSERS:
    _silver(_feed)

dp.create_streaming_table(name="quarantine", comment="Raw lines that are not a usable page, with the reason. Never dropped.")


def _quarantine(feed):
    @dp.append_flow(target="quarantine", name=f"quarantine_{feed}")
    def _flow():
        return S.quarantine_lines(spark.readStream.table(f"{CATALOG}.bronze.{feed}_raw"), feed)  # noqa: F821


for _feed in PARSERS:
    _quarantine(_feed)
