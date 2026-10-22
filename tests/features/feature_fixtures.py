"""Fixture builders for the feature tests: WBGT and rainfall rows shaped like the Silver tables, and forecast versions
built through the real Silver parser (so valid_start_raw and the parsed text columns are exactly what Silver stores)."""
import json
from datetime import datetime, timedelta, timezone

from coolcheck import silver as S

SGT = timezone(timedelta(hours=8))
WBGT_SCHEMA = ("station_id STRING, reading_ts TIMESTAMP, sgt_date DATE, wbgt DOUBLE, heat_stress STRING, "
               "station_lat DOUBLE, station_lon DOUBLE")
RAIN_SCHEMA = ("station_id STRING, reading_ts TIMESTAMP, sgt_date DATE, rainfall_mm DOUBLE, station_lat DOUBLE, "
               "station_lon DOUBLE")
LABEL_SCHEMA = "station_id STRING, sgt_date DATE, label STRING, usable BOOLEAN, n_high LONG"
BRONZE_SCHEMA = ("raw STRING, source_file STRING, file_name STRING, file_mtime TIMESTAMP, file_size LONG, "
                 "source_kind STRING, file_date DATE, ingested_at TIMESTAMP")


def at(d, hh, mm=0, ss=0):
    """The instant hh:mm:ss SGT on date d."""
    return datetime(d.year, d.month, d.day, tzinfo=SGT) + timedelta(hours=hh, minutes=mm, seconds=ss)


def fixture_category(wbgt):
    """A plausible API category for a fixture value, for convenience only: the code under test never derives a
    category from a value; it reads heat_stress."""
    return "High" if wbgt >= 33 else "Moderate" if wbgt >= 31 else "Low"


class Readings:
    """Collects WBGT and rainfall rows, then builds the two DataFrames."""

    def __init__(self):
        self.wbgt, self.rain = [], []

    def w(self, station, ts, wbgt, heat_stress=None, lat=1.30, lon=103.80):
        hs = heat_stress if heat_stress is not None else fixture_category(wbgt)
        self.wbgt.append((station, ts, ts.astimezone(SGT).date(), wbgt, hs, lat, lon))
        return self

    def day(self, station, d, peak, lat=1.30, lon=103.80):
        """Three counted readings on day d (10:00, 13:00, 16:00); the highest is peak."""
        for hh, v in ((10, peak - 1.0), (13, peak), (16, peak - 0.5)):
            self.w(station, at(d, hh), v, lat=lat, lon=lon)
        return self

    def rain_day(self, station, d, n=288, wet=10, mm=0.5, lat=1.31, lon=103.80, after=None):
        """n five-minute readings from 00:00 on day d; the first `wet` hold mm each, the rest 0. after=(minute, mm)
        gives every reading at or after that minute of the day mm instead."""
        for i in range(n):
            v = mm if i < wet else 0.0
            if after is not None and 5 * i >= after[0]:
                v = after[1]
            self.rain.append((station, at(d, 0, 5 * i), d, v, lat, lon))
        return self

    def frames(self, spark):
        return spark.createDataFrame(self.wbgt, WBGT_SCHEMA), spark.createDataFrame(self.rain, RAIN_SCHEMA)


def fc_record(issue, start, end, text, updated=None, high=33, forecast_text="Thundery Showers"):
    """One forecast record in the API's shape (the fields Silver reads)."""
    return {"date": issue[:10], "timestamp": issue, "updatedTimestamp": updated or issue,
            "general": {"temperature": {"low": 25, "high": high, "unit": "Degrees Celsius"},
                        "relativeHumidity": {"low": 60, "high": 95, "unit": "Percentage"},
                        "forecast": {"code": "TL", "text": forecast_text},
                        "validPeriod": {"start": start, "end": end, "text": text},
                        "wind": {"speed": {"low": 10, "high": 20}, "direction": "NNE"}},
            "periods": []}


def forecast_versions(spark, *records):
    """Silver forecast rows (coolcheck.silver.parse_forecast) for the given records; none gives an empty frame."""
    line = json.dumps({"code": 0, "errorMsg": "", "data": {"records": list(records)}})
    mtime = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
    bronze = spark.createDataFrame([(line, "/Volumes/coolcheck/bronze/raw_files/forecast/backfill/fixture.jsonl",
                                     "fixture.jsonl", mtime, len(line), "backfill", None, mtime)], BRONZE_SCHEMA)
    return S.parse_forecast(bronze)
