"""Fixture builders for the Silver tests (raw API pages and Bronze-shaped rows)."""
import json
from datetime import date, datetime, timezone

BRONZE_SCHEMA = ("raw STRING, source_file STRING, file_name STRING, file_mtime TIMESTAMP, file_size LONG, "
                 "source_kind STRING, file_date DATE, ingested_at TIMESTAMP")


def page(feed, body):
    return json.dumps({"code": 0, "errorMsg": "", "data": body})


def wbgt_page(*records):
    """records: (datetime, [(station_id, wbgt, heatStress), ...])"""
    return page("wbgt", {"records": [
        {"datetime": dt, "updatedTimestamp": dt, "item": {"type": "observation", "isStationData": True, "readings": [
            {"station": {"id": sid, "name": f"name {sid}", "townCenter": "t"}, "location": {"latitude": "1.3", "longitude": "103.8"},
             "wbgt": w, "heatStress": hs} for sid, w, hs in rs]}} for dt, rs in records]})


def bronze_rows(spark, lines, file_name="wbgt_2025-03-01.jsonl", kind="backfill",
                mtime=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc), file_date=date(2025, 3, 1)):
    folder = "backfill" if kind == "backfill" else "live"
    rows = [(ln, f"/Volumes/coolcheck/bronze/raw_files/x/{folder}/{file_name}", file_name, mtime, len(ln), kind,
             file_date if kind == "backfill" else None, mtime) for ln in lines]
    return spark.createDataFrame(rows, BRONZE_SCHEMA)
