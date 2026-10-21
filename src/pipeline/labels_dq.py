"""Daily station labels and the data-quality tables (materialized views over Silver)."""
import sys

from pyspark import pipelines as dp

sys.path.insert(0, spark.conf.get("coolcheck.src_path"))  # noqa: F821
from coolcheck import dq, labels  # noqa: E402
from coolcheck.silver import first_arrival  # noqa: E402


def _read(name):
    return spark.read.table(name)  # noqa: F821


@dp.materialized_view(name="wbgt_first_arrival", comment="First live arrival per WBGT reading and the 1-hour late flag.")
def wbgt_first_arrival():
    return first_arrival(_read("wbgt_readings_all"))


@dp.materialized_view(name="station_daily_label", comment=labels.__doc__)
@dp.expect_all(labels.LABEL_RULES)
def station_daily_label():
    return labels.station_daily_label(_read("wbgt_readings"), _read("wbgt_first_arrival"))


@dp.materialized_view(name="dq_day", comment="One row per feed and SGT day: ok, short or no_data. Nothing dropped.")
def dq_day():
    return dq.dq_day(_read("wbgt_readings"), _read("rainfall_readings"), _read("forecast_issues"))


@dp.materialized_view(name="dq_conflicts", comment="Every copy of each key whose copies differ in content.")
def dq_conflicts():
    return (dq.dq_conflicts(_read("wbgt_readings_all"), "wbgt")
            .unionByName(dq.dq_conflicts(_read("rainfall_readings_all"), "rainfall"))
            .unionByName(dq.dq_conflicts(_read("forecast_issues_all"), "forecast")))


@dp.materialized_view(name="dq_events", comment="Counts per feed and check: rule failures, duplicates, quarantine, late, moved stations.")
def dq_events():
    return dq.dq_events({"wbgt": _read("wbgt_readings_all"), "rainfall": _read("rainfall_readings_all"),
                         "forecast": _read("forecast_issues_all")},
                        _read("quarantine"), {"wbgt": _read("wbgt_first_arrival")})


@dp.materialized_view(name="station_gaps", comment="Gaps over 60 minutes between a station's consecutive usable readings.")
def station_gaps():
    return (dq.station_gaps(_read("wbgt_readings"), "wbgt", "heat_stress IN ('Low', 'Moderate', 'High')")
            .unionByName(dq.station_gaps(_read("rainfall_readings"), "rainfall", "rainfall_mm IS NOT NULL")))


@dp.materialized_view(name="forecast_periods", comment="Forecast issues exploded to period and region.")
def forecast_periods():
    return dq.forecast_periods(_read("forecast_issues"))
