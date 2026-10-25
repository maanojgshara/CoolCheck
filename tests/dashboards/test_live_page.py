"""The live heat-stress page (src/dashboards/live_heat_stress.lvdash.json): its structure, and every dataset's SQL run
unchanged on fixture rows in a temporary view named latest_readings (a temporary view wins over a table of the same
name, and the page's queries use the bare name).

Rules tested: a reading is recent when it is in the hour before the table's last refresh (the newest loaded_at); when
that refresh is more than 90 minutes before now, the page says "Live data is stale: last refresh <time>" and every
station shows "no recent reading"; a missing value never shows as 0; times are SGT text whatever the session time zone.
Fixture times are relative to the real current time, because the queries use current_timestamp().
"""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from coolcheck import latest as L

PAGE = Path(__file__).resolve().parents[2] / "src" / "dashboards" / "live_heat_stress.lvdash.json"
DASH = json.loads(PAGE.read_text(encoding="utf-8"))
SQL = {d["name"]: "".join(d["queryLines"]) for d in DASH["datasets"]}
WIDGETS = [item["widget"] for page in DASH["pages"] for item in page["layout"]]
SGT = timezone(timedelta(hours=8))


def now():
    """This minute in UTC, read when a test runs: a time read when pytest collects the file is minutes old once the
    briefing tests before it have run."""
    return datetime.now(timezone.utc).replace(second=0, microsecond=0)


def sgt(t):
    s = t.astimezone(SGT)
    return f"{s.day} {s:%b %H:%M}"


# ---------------------------------------------------------------- structure (no Spark)

def test_widgets_bind_to_existing_datasets_and_fields():
    for w in WIDGETS:
        if "queries" not in w:
            assert "multilineTextboxSpec" in w, w["name"]
            continue
        q = w["queries"][0]["query"]
        assert q["datasetName"] in SQL, w["name"]
        names = {f["name"] for f in q["fields"]}
        enc = w["spec"]["encodings"]
        if w["spec"]["widgetType"] == "table":
            assert w["spec"]["version"] == 2
            used = {c["fieldName"] for c in enc["columns"]}
        else:
            assert (w["spec"]["widgetType"], w["spec"]["version"]) == ("symbol-map", 2)
            used = {enc["coordinates"]["latitude"]["fieldName"], enc["coordinates"]["longitude"]["fieldName"],
                    enc["color"]["fieldName"], *(e["fieldName"] for e in enc.get("extra", []))}
        assert used <= names, (w["name"], used - names)


def test_query_lines_end_with_whitespace_and_read_only_latest_readings():
    for d in DASH["datasets"]:
        assert all(line.endswith(("\n", " ")) for line in d["queryLines"]), d["name"]
        sql = re.sub(r"--[^\n]*", "", SQL[d["name"]])
        sources = set(re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_][\w.]*)", sql))
        ctes = set(re.findall(r"\b([a-z]\w*)\s+AS\s*\(", sql))
        assert sources - ctes - {"VALUES"} == {"latest_readings"}, (d["name"], sources)


def test_layout_rows_fit_the_grid_without_overlap():
    cells = set()
    for page in DASH["pages"]:
        for item in page["layout"]:
            p = item["position"]
            assert 0 <= p["x"] and p["x"] + p["width"] <= 12, item["widget"]["name"]
            for x in range(p["x"], p["x"] + p["width"]):
                for y in range(p["y"], p["y"] + p["height"]):
                    assert (x, y) not in cells, item["widget"]["name"]
                    cells.add((x, y))


def test_map_colours_cover_the_three_nea_categories_and_no_recent_reading():
    m = next(w for w in WIDGETS if w["name"] == "wbgt-map")
    values = {x["value"] for x in m["spec"]["encodings"]["color"]["scale"]["mappings"]}
    assert values == {"Low", "Moderate", "High", "No recent reading"}


# ---------------------------------------------------------------- SQL on fixture rows (Databricks Connect)

def rows(r):
    """The fixture table, refreshed at r (the newest loaded_at). Old rows keep the loaded_at of their own run."""
    m = timedelta(minutes=1)

    def row(measure, sid, name, ts, value, heat=None, n=None, loaded=r, end=None, unit="deg C"):
        return (measure, sid, name, 1.3, 103.8, ts, value, unit, heat, n, loaded, end)
    end = r - 15 * m
    return [
        row("wbgt", "W1", "Alpha", r - 20 * m, 27.0, "Low"),
        row("wbgt", "W2", "Bravo", r - 20 * m, 33.1, "High"),
        row("wbgt", "W3", "Charlie", r - 61 * m, 29.9, "Moderate", loaded=r - 60 * m),
        row("wbgt", "W4", "Delta", r - 30 * m, 30.2, "Moderate"),
        row("rainfall", "P1", "Papa", r - 15 * m, 0.2, unit="mm"),
        row("rainfall", "P2", "Quebec", r - 180 * m, 0.0, unit="mm", loaded=r - 170 * m),
        row("rainfall", "P3", "Romeo", r - 10 * m, 0.0, unit="mm"),
        row(L.LAST_HOUR, "P1", "Papa", end, 2.4, n=12, end=end, unit="mm"),
        row(L.LAST_HOUR, "P2", "Quebec", None, None, n=0, end=end, unit="mm"),
        row(L.LAST_HOUR, "P3", "Romeo", end, 0.0, n=11, end=end, unit="mm"),
        row("air_temperature", "A1", "Alfa", r - 12 * m, 31.2),
        row("air_temperature", "A2", "Bravo air", r - 26 * 60 * m, 30.0, loaded=r - 26 * 60 * m),
    ]


@pytest.fixture
def table(spark):
    """Returns a function that installs the given rows as the temporary view latest_readings."""
    def install(data):
        spark.createDataFrame(data, L.LATEST_DDL).createOrReplaceTempView("latest_readings")
    return install


def run(spark, name):
    return [r.asDict() for r in spark.sql(SQL[name]).collect()]


def test_fresh_table(spark, table):
    r = now() - timedelta(minutes=10)
    table(rows(r))
    (banner,) = run(spark, "ds_banner")
    assert banner["state"] == "live"
    assert re.fullmatch(rf"Live data: last refresh {sgt(r)} SGT, (9|10|11) min ago\.", banner["message"])

    streams = {s["stream"]: s for s in run(spark, "ds_streams")}
    assert [s["stream"] for s in run(spark, "ds_streams")] == ["WBGT", "Rainfall", "Air temperature"]
    assert streams["WBGT"]["last_updated"] == f"{sgt(r - timedelta(minutes=20))} SGT"
    assert streams["WBGT"]["reporting_text"] == "3 of 4"  # Charlie's reading is 61 minutes before the refresh
    assert streams["Rainfall"]["last_updated"] == f"{sgt(r - timedelta(minutes=10))} SGT"
    assert streams["Rainfall"]["reporting_text"] == "2 of 3"
    assert streams["Air temperature"]["reporting_text"] == "1 of 1"  # A2 is over 24 hours old

    wbgt = run(spark, "ds_wbgt")
    assert [w["station_name"] for w in wbgt] == ["Bravo", "Delta", "Alpha", "Charlie"]
    assert [(w["heat_category"], w["wbgt_text"]) for w in wbgt] == [
        ("High", "33.1 °C"), ("Moderate", "30.2 °C"), ("Low", "27.0 °C"), ("No recent reading", "no recent reading")]
    assert wbgt[3]["wbgt"] is None

    air = run(spark, "ds_air")
    assert [(a["station_name"], a["temp_text"]) for a in air] == [("Alfa", "31.2 °C"), ("Bravo air", "no recent reading")]

    rain = run(spark, "ds_rain")
    assert [(x["station_name"], x["rain_text"], x["readings_text"]) for x in rain] == [
        ("Papa", "2.4 mm", "12 of 12"), ("Romeo", "0.0 mm", "11 of 12"), ("Quebec", "no recent reading", None)]
    assert rain[2]["rain_mm"] is None  # NULL stays NULL, never 0
    (label,) = run(spark, "ds_rain_label")
    assert label["label"] == (f"Rain in the hour to {sgt(r - timedelta(minutes=15))} SGT: "
                              "1 of 2 stations with a reading recorded rain, up to 2.4 mm")


def test_stale_table_greys_every_station(spark, table):
    r = now() - timedelta(minutes=100)
    table(rows(r))
    (banner,) = run(spark, "ds_banner")
    assert banner["state"] == "stale"
    assert banner["message"] == (f"Live data is stale: last refresh {sgt(r)} SGT. "
                                 "Every station shows no recent reading until the next refresh.")
    streams = run(spark, "ds_streams")
    assert [s["reporting_text"] for s in streams] == ["0 of 4", "0 of 3", "0 of 1"]
    assert streams[0]["last_updated"] == f"{sgt(r - timedelta(minutes=20))} SGT"  # the newest reading is still shown
    wbgt = run(spark, "ds_wbgt")
    assert {w["heat_category"] for w in wbgt} == {"No recent reading"}
    assert {w["wbgt_text"] for w in wbgt} == {"no recent reading"} and {w["wbgt"] for w in wbgt} == {None}
    assert {a["temp_text"] for a in run(spark, "ds_air")} == {"no recent reading"}
    rain = run(spark, "ds_rain")
    assert {x["rain_text"] for x in rain} == {"no recent reading"} and {x["rain_mm"] for x in rain} == {None}
    (label,) = run(spark, "ds_rain_label")
    assert label["label"] == "Rain in the last hour: no recent reading (live data is stale)"


@pytest.mark.parametrize("age, stale", [(85, False), (95, True)])
def test_stale_starts_after_90_minutes(spark, table, age, stale):
    table(rows(now() - timedelta(minutes=age)))
    (banner,) = run(spark, "ds_banner")
    assert (banner["state"] == "stale") is stale


def test_no_rainfall_window(spark, table):
    r = now() - timedelta(minutes=10)
    data = [x if x[0] != L.LAST_HOUR else (*x[:5], None, None, x[7], None, 0, x[10], None) for x in rows(r)]
    table(data)
    (label,) = run(spark, "ds_rain_label")
    assert label["label"] == ("Rain in the last hour: no recent reading "
                              "(no rainfall station reported in the hour before the last refresh)")
    assert {x["rain_text"] for x in run(spark, "ds_rain")} == {"no recent reading"}


def test_empty_table(spark, table):
    table([])
    (banner,) = run(spark, "ds_banner")
    assert banner["message"] == "Live data is stale: no refresh yet. Every station shows no recent reading."
    streams = run(spark, "ds_streams")
    assert [(s["last_updated"], s["age_now"], s["reporting_text"]) for s in streams] == [
        ("no recent reading", "no recent reading", "0 of 0")] * 3
    assert run(spark, "ds_wbgt") == [] and run(spark, "ds_rain") == []


def test_times_are_sgt_whatever_the_session_time_zone(spark, table):
    r = now() - timedelta(minutes=10)
    table(rows(r))
    before = spark.conf.get("spark.sql.session.timeZone")
    try:
        spark.conf.set("spark.sql.session.timeZone", "America/New_York")
        assert run(spark, "ds_streams")[0]["last_updated"] == f"{sgt(r - timedelta(minutes=20))} SGT"
        assert run(spark, "ds_wbgt")[0]["reading_time"] == f"{sgt(r - timedelta(minutes=20))} SGT"
    finally:
        spark.conf.set("spark.sql.session.timeZone", before)
