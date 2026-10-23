"""The briefing dashboard's four gold views (coolcheck.briefing) on fixture rows in temp views, through Databricks Connect
(serverless, profile coolcheck). Nothing is written, and no real label is read: observed_heat_daily runs on fixture labels
dated relative to today's SGT date, since the final check (1 Sep to 19 Oct 2026) is not yet scored.
"""
import datetime as dt
import json

import pytest
import shapely
from shapely.geometry import box

from coolcheck import briefing as B

SGT = dt.timezone(dt.timedelta(hours=8))


@pytest.fixture(scope="module")
def spark():
    from databricks.connect import DatabricksSession
    s = DatabricksSession.builder.serverless().profile("coolcheck").getOrCreate()
    s.conf.set("spark.sql.session.timeZone", "UTC")  # the dashboards' warehouse runs in UTC
    return s


def specs():
    import load_refuge_park_access as L
    import planning_area_layers as PAL
    return L, PAL


def schema_of(columns):
    return ", ".join(f"`{c}` {t}" for c, t, _ in columns)


def rows_for(columns, dicts):
    return [tuple(d.get(c) for c, _, _ in columns) for d in dicts]


def test_planning_area_map_is_geometry_4326(spark):
    _, PAL = specs()
    cols = PAL.TABLES["planning_area_boundary"]["columns"]
    poly = shapely.MultiPolygon([box(103.80, 1.30, 103.81, 1.31), box(103.82, 1.30, 103.83, 1.31)])
    data = [{"planning_area": "A", "planning_area_code": "AA", "region": "R", "geometry_wkt": box(103.7, 1.3, 103.71, 1.31).wkt},
            {"planning_area": "B", "planning_area_code": "BB", "region": "R", "geometry_wkt": poly.wkt}]
    spark.createDataFrame(rows_for(cols, data), schema_of(cols)).createOrReplaceTempView("t_boundary")
    got = spark.sql(f"SELECT *, st_srid(geometry) AS srid, st_geometrytype(geometry) AS kind, st_isvalid(geometry) AS valid, "
                    f"st_asgeojson(geometry) AS gj FROM ({B.planning_area_map_sql('t_boundary')})").collect()
    assert [r["planning_area"] for r in sorted(got, key=lambda r: r["planning_area"])] == ["A", "B"]
    assert all(r["srid"] == 4326 and r["valid"] for r in got)
    assert {r["planning_area"]: r["kind"] for r in got} == {"A": "ST_Polygon", "B": "ST_MultiPolygon"}
    assert json.loads(next(r["gj"] for r in got if r["planning_area"] == "B"))["type"] == "MultiPolygon"
    assert list(spark.sql(B.planning_area_map_sql("t_boundary")).columns) == [c for c, _ in B.MAP_COLUMNS]


def test_refuge_layer_keeps_the_main_set_with_plain_types(spark):
    L, _ = specs()
    cols = L.TABLES["refuge_points"]["columns"]
    data = [{"refuge_id": "cc_1", "name": "A CC", "layer": "community_club", "status": "open", "in_main": True, "lat": 1.3, "lon": 103.8},
            {"refuge_id": "cc_2", "name": "B CC (Temp Office)", "layer": "community_club", "status": "temp_office", "in_main": True},
            {"refuge_id": "cc_3", "name": "C CC (U/C)", "layer": "community_club", "status": "under_construction", "in_main": False},
            {"refuge_id": "cc_4", "name": "Limbang CO c/o A CC", "layer": "community_club", "status": "open", "in_main": False},
            {"refuge_id": "gtp_1", "name": "An AAC", "layer": "aac_partial", "status": "open", "in_main": True},
            {"refuge_id": "eld_1", "name": "A SAC", "layer": "eldercare_sac_2016", "status": "open", "in_main": False}]
    spark.createDataFrame(rows_for(cols, data), schema_of(cols)).createOrReplaceTempView("t_refuges")
    got = {r["refuge_id"]: r["refuge_type"] for r in spark.sql(B.refuge_layer_sql("t_refuges")).collect()}
    assert got == {"cc_1": "Community club", "cc_2": "Community club (temporary office)",
                   "gtp_1": "Active Ageing Centre (partial list)"}
    assert list(spark.sql(B.refuge_layer_sql("t_refuges")).columns) == [c for c, _ in B.REFUGE_LAYER_COLUMNS]


def test_park_layer_one_row_per_park_and_area_main_set_only(spark):
    L, PAL = specs()
    pcols, mcols = L.TABLES["park_polygons"]["columns"], PAL.TABLES["park_planning_area"]["columns"]
    parks = [{"park_id": "np_A", "name": "Across", "in_main": True, "area_m2": 1000.0, "geometry_wkt": box(103.8, 1.3, 103.81, 1.301).wkt},
             {"park_id": "np_R", "name": "A reserve", "in_main": False, "area_m2": 9.0, "geometry_wkt": box(103.9, 1.3, 103.91, 1.31).wkt}]
    member = [{"park_id": "np_A", "park_name": "Across", "planning_area": "WEST", "area_in_planning_area_m2": 600.0},
              {"park_id": "np_A", "park_name": "Across", "planning_area": "EAST", "area_in_planning_area_m2": 400.0},
              {"park_id": "np_R", "park_name": "A reserve", "planning_area": "EAST", "area_in_planning_area_m2": 9.0}]
    spark.createDataFrame(rows_for(pcols, parks), schema_of(pcols)).createOrReplaceTempView("t_parks")
    spark.createDataFrame(rows_for(mcols, member), schema_of(mcols)).createOrReplaceTempView("t_member")
    sql = B.park_layer_sql("t_parks", "t_member")
    got = spark.sql(f"SELECT park_id, planning_area, st_srid(geometry) AS srid FROM ({sql})").collect()
    assert sorted((r["park_id"], r["planning_area"]) for r in got) == [("np_A", "EAST"), ("np_A", "WEST")]
    assert {r["srid"] for r in got} == {4326}
    assert list(spark.sql(sql).columns) == [c for c, _ in B.PARK_LAYER_COLUMNS]


def test_observed_heat_daily_last_30_completed_days_stations_counted_once(spark):
    today = dt.datetime.now(SGT).date()
    d = lambda n: today - dt.timedelta(days=n)  # noqa: E731
    labels = [(d(1), "S1", "One", "High", 33.4, True), (d(0), "S1", "One", "High", 33.9, True),   # today: provisional
              (d(1), "S2", "Two", "Low", 29.0, True), (d(1), "S3", "Three", "Moderate", 31.0, False),  # S3 not usable
              (d(30), "S1", "One", "Moderate", 31.5, True), (d(31), "S1", "One", "Moderate", 31.6, True)]
    nearest = [(d(1), "AREA X", "S1"), (d(1), "AREA Y", "S1"), (d(30), "AREA X", "S1"), (d(0), "AREA X", "S1")]
    spark.createDataFrame(labels, "sgt_date DATE, station_id STRING, station_name STRING, label STRING, max_wbgt DOUBLE, "
                                  "usable BOOLEAN").createOrReplaceTempView("t_labels")
    spark.createDataFrame(nearest, "target_date DATE, planning_area STRING, station_id STRING").createOrReplaceTempView("t_nearest")
    sql = B.observed_heat_daily_sql("t_labels", "t_nearest")
    got = sorted((r["sgt_date"], r["station_id"], r["planning_area"], r["heat_order"]) for r in spark.sql(sql).collect())
    assert got == sorted([(d(1), "S1", "AREA X", 3), (d(1), "S1", "AREA Y", 3), (d(1), "S2", None, 1), (d(30), "S1", "AREA X", 2)])
    per_day = {r["sgt_date"]: r["n"] for r in spark.sql(f"SELECT sgt_date, count(DISTINCT station_id) AS n FROM ({sql}) GROUP BY sgt_date").collect()}
    assert per_day == {d(1): 2, d(30): 1}  # a station serving two areas counts once
    assert list(spark.sql(sql).columns) == [c for c, _ in B.OBSERVED_COLUMNS]
