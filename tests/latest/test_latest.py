"""D9 latest readings (src/coolcheck/latest.py): folders and files across midnight, newest usable value per station,
last-hour rainfall edges, the merge, the stream status and the 90-minute alarm."""
from datetime import date, datetime, timedelta, timezone

import pytest
from pyspark.sql import functions as F

from silver_fixtures import bronze_rows, page, wbgt_page
from coolcheck import latest as L
from coolcheck import silver as S

SGT = L.SGT
NOW = datetime(2026, 10, 22, 16, 30, tzinfo=SGT)


def at(h, m, day=22):
    return datetime(2026, 10, day, h, m, tzinfo=SGT)


def iso(h, m, day=22):
    return f"2026-10-{day:02d}T{h:02d}:{m:02d}:00+08:00"


def station_page(feed, readings, stations, unit):
    """readings: [(timestamp, [(station_id, value), ...])]; the rainfall and air temperature response shape."""
    return page(feed, {
        "stations": [{"id": s, "deviceId": s, "name": f"name {s}", "location": {"latitude": 1.3, "longitude": 103.8}}
                     for s in stations],
        "readings": [{"timestamp": ts, "data": [{"stationId": sid, "value": v} for sid, v in rs]} for ts, rs in readings],
        "readingType": "X", "readingUnit": unit})


def live(spark, lines, name, mtime):
    return bronze_rows(spark, lines, name, kind="live", mtime=mtime)


def mtime(h, m):
    return datetime(2026, 10, 22, h, m, tzinfo=SGT).astimezone(timezone.utc)


def hhmm(df):
    return df.withColumn("t", F.date_format("reading_ts", "HH:mm"))


# ---- folders and files across midnight ----

def test_folders_are_yesterday_and_today_even_just_after_midnight():
    assert L.window_dates(datetime(2026, 10, 23, 0, 10, tzinfo=SGT)) == [date(2026, 10, 22), date(2026, 10, 23)]
    # the same instant given in UTC is still 23 Oct in Singapore
    assert L.window_dates(datetime(2026, 10, 22, 16, 10, tzinfo=timezone.utc)) == [date(2026, 10, 22), date(2026, 10, 23)]
    assert L.window_dates(at(15, 0)) == [date(2026, 10, 21), date(2026, 10, 22)]
    assert L.live_folders("/V", "wbgt", datetime(2026, 10, 23, 0, 10, tzinfo=SGT)) == [
        "/V/wbgt/live/2026-10-22", "/V/wbgt/live/2026-10-23"]


def test_parsed_live_asks_for_both_folders_and_returns_none_when_neither_exists(spark):
    asked = []

    def exists(path):
        asked.append(path)
        return False

    now = datetime(2026, 10, 23, 0, 10, tzinfo=SGT)
    assert L.parsed_live(spark, "/V", "air_temperature", now, 3, exists) is None
    assert asked == ["/V/air_temperature/live/2026-10-22", "/V/air_temperature/live/2026-10-23"]


def test_recent_files_keep_the_last_three_hours_across_midnight(spark):
    now = datetime(2026, 10, 23, 0, 10, tzinfo=SGT)
    names = ["wbgt_2026-10-22T210900_1.jsonl",   # 3 h 01 min before now: out
             "wbgt_2026-10-22T211100_2.jsonl",   # 2 h 59 min before: in (yesterday's folder)
             "wbgt_2026-10-22T235000_3.jsonl",   # in (yesterday's folder)
             "wbgt_2026-10-23T000500_4.jsonl",   # in (today's folder)
             "notes.jsonl"]                       # no run time in the name: out
    df = None
    for n in names:
        part = live(spark, ["{}"], n, mtime(23, 0))
        df = part if df is None else df.unionByName(part)
    kept = {r.file_name for r in L.recent_files(df, now, 3).collect()}
    assert kept == set(names[1:4])


# ---- newest usable value per station ----

def test_wbgt_newest_usable_reading_per_station(spark):
    old = wbgt_page((iso(16, 0), [("S1", 30.0, "Low"), ("S2", 34.1, "High"), ("S4", 33.0, "Moderate")]))
    new = wbgt_page((iso(16, 15), [("S1", 32.0, "Moderate"), ("S2", None, "N/A"), ("S4", 99.0, "High")]),
                    (iso(16, 0), [("S1", 30.0, "Low")]),           # a second copy of an older reading
                    (iso(16, 45), [("S3", 31.0, "Low")]))          # timed after now: not a reading yet
    bronze = live(spark, [old], "wbgt_2026-10-22T160100_1.jsonl", mtime(16, 1)).unionByName(
        live(spark, [new], "wbgt_2026-10-22T161600_2.jsonl", mtime(16, 16)))
    out = {r.station_id: r for r in hhmm(L.latest_rows(S.PARSERS["wbgt"](bronze), "wbgt", NOW)).collect()}
    assert sorted(out) == ["S1", "S2", "S4"]
    assert (out["S1"].t, out["S1"].value, out["S1"].heat_stress) == ("16:15", 32.0, "Moderate")
    # the newest reading has no value: the station keeps its previous one rather than going blank
    assert (out["S2"].t, out["S2"].value, out["S2"].heat_stress) == ("16:00", 34.1, "High")
    # an out-of-range newest value is not a candidate either
    assert (out["S4"].t, out["S4"].value) == ("16:00", 33.0)
    assert {r.unit for r in out.values()} == {"deg C"} and {r.measure for r in out.values()} == {"wbgt"}
    assert all(r.n_readings is None for r in out.values())


def test_air_temperature_partly_filled_newest_minute_does_not_blank_a_station(spark):
    pg = station_page("air_temperature", [(iso(16, 30), [("S109", 31.2), ("S106", None)]),
                                          (iso(16, 29), [("S109", 31.0), ("S106", 31.5)])], ["S109", "S106"], "deg C")
    bronze = live(spark, [pg], "air_temperature_2026-10-22T162800_1.jsonl", mtime(16, 28))
    out = {r.station_id: r for r in hhmm(L.latest_rows(S.PARSERS["air_temperature"](bronze), "air_temperature", NOW)).collect()}
    assert (out["S109"].t, out["S109"].value) == ("16:30", 31.2)
    assert (out["S106"].t, out["S106"].value) == ("16:29", 31.5)
    assert out["S106"].unit == "deg C" and out["S106"].heat_stress is None   # no heat category on air temperature


# ---- last-hour rainfall ----

def stations(spark, ids):
    return spark.createDataFrame([(i, f"name {i}", 1.3, 103.8) for i in ids],
                                 "station_id STRING, station_name STRING, lat DOUBLE, lon DOUBLE")


def test_rainfall_last_hour_window_edges_copies_and_empty_stations(spark):
    older = station_page("rainfall", [(iso(16, 0), [("S1", 2.0)])], ["S1"], "mm")
    newer = station_page("rainfall", [
        (iso(16, 35), [("S1", 9.0)]),                    # after now: out
        (iso(16, 30), [("S1", 0.5)]),                    # exactly now: in
        (iso(16, 20), [("S3", None)]),                   # no value: not counted
        (iso(16, 0), [("S1", 2.0)]),                     # the same reading again in a later file: counted once
        (iso(15, 35), [("S1", 1.0)]),                    # in
        (iso(15, 30), [("S1", 7.0), ("S2", 4.0)]),       # exactly now - 60 min: out
        (iso(15, 0), [("S2", 3.0)])], ["S1", "S2", "S3"], "mm")
    bronze = live(spark, [older], "rainfall_2026-10-22T160100_1.jsonl", mtime(16, 1)).unionByName(
        live(spark, [newer], "rainfall_2026-10-22T163100_2.jsonl", mtime(16, 31)))
    out = {r.station_id: r for r in hhmm(L.rainfall_last_hour_rows(
        S.PARSERS["rainfall"](bronze), stations(spark, ["S1", "S2", "S3"]), at(16, 30))).collect()}
    assert (out["S1"].value, out["S1"].n_readings, out["S1"].t) == (3.5, 3, "16:30")
    assert (out["S2"].value, out["S2"].n_readings, out["S2"].t) == (None, 0, None)
    assert (out["S3"].value, out["S3"].n_readings) == (None, 0)
    assert {r.measure for r in out.values()} == {L.LAST_HOUR} and {r.unit for r in out.values()} == {"mm"}


def test_rainfall_last_hour_without_any_live_files(spark):
    out = L.rainfall_last_hour_rows(None, stations(spark, ["S1", "S2"]), NOW).collect()
    assert sorted((r.station_id, r.value, r.n_readings) for r in out) == [("S1", None, 0), ("S2", None, 0)]


# ---- merge and status ----

def latest_df(spark, rows):
    return spark.createDataFrame(rows, L.LATEST_DDL)


def row(measure, sid, ts, value, loaded, n=None):
    return (measure, sid, f"name {sid}", 1.3, 103.8, ts, value, "u", None, n, loaded)


def test_merge_keeps_the_newest_reading_and_always_replaces_last_hour(spark):
    existing = latest_df(spark, [
        row("wbgt", "S1", at(16, 0), 1.0, at(16, 5)), row("wbgt", "S2", at(15, 0), 2.0, at(16, 5)),
        row(L.LAST_HOUR, "S1", at(15, 55), 5.0, at(16, 5), 4)])
    new = latest_df(spark, [
        row("wbgt", "S1", at(16, 15), 3.0, at(16, 20)), row("wbgt", "S2", at(14, 0), 9.0, at(16, 20)),
        row("wbgt", "S3", at(16, 10), 4.0, at(16, 20)), row(L.LAST_HOUR, "S1", None, None, at(16, 20), 0)])
    out = {(r.measure, r.station_id): r for r in hhmm(L.merge_latest(existing, new)).collect()}
    assert sorted(out) == [("rainfall_last_hour", "S1"), ("wbgt", "S1"), ("wbgt", "S2"), ("wbgt", "S3")]
    assert (out["wbgt", "S1"].t, out["wbgt", "S1"].value) == ("16:15", 3.0)        # newer reading wins
    assert (out["wbgt", "S2"].t, out["wbgt", "S2"].value) == ("15:00", 2.0)        # an older copy never wins
    assert (out["wbgt", "S3"].t, out["wbgt", "S3"].value) == ("16:10", 4.0)
    assert (out[L.LAST_HOUR, "S1"].value, out[L.LAST_HOUR, "S1"].n_readings) == (None, 0)  # recomputed, replaces


def test_stream_status_counts_stations_by_reading_age(spark):
    def ago(minutes):
        return NOW - timedelta(minutes=minutes)

    latest = latest_df(spark, [
        row("wbgt", "S1", ago(10), 1.0, NOW), row("wbgt", "S2", ago(70), 1.0, NOW), row("wbgt", "S3", ago(30 * 60), 1.0, NOW),
        row("rainfall", "S1", ago(5), 0.0, NOW), row(L.LAST_HOUR, "S1", ago(5), 1.0, NOW, 3)])
    out = {r.measure: r for r in hhmm(L.stream_status(latest, NOW).withColumnRenamed("last_reading_ts", "reading_ts")).collect()}
    assert sorted(out) == ["air_temperature", "rainfall", "wbgt"]
    assert (out["wbgt"].t, out["wbgt"].stations_reporting_1h, out["wbgt"].stations_known_24h, out["wbgt"].age_minutes) == ("16:20", 1, 2, 10.0)
    assert (out["rainfall"].stations_reporting_1h, out["rainfall"].stations_known_24h, out["rainfall"].age_minutes) == (1, 1, 5.0)
    assert (out["air_temperature"].t, out["air_temperature"].stations_reporting_1h, out["air_temperature"].age_minutes) == (None, 0, None)


# ---- the alarm ----

@pytest.mark.parametrize("age, alarm", [(0, False), (89.9, False), (90.0, False), (90.1, True), (91, True), (300, True)])
def test_alarm_fires_only_when_the_newest_wbgt_is_more_than_90_minutes_old(age, alarm):
    msg = L.freshness_problem(age, 90, "2026-10-22 15:00:00")
    assert (msg is not None) is alarm
    if alarm:
        assert "minutes old" in msg and "90" in msg


def test_alarm_fires_when_there_is_no_wbgt_reading_at_all():
    assert "no WBGT reading" in L.freshness_problem(None)
