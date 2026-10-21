from datetime import date, datetime, timedelta, timezone

from coolcheck.nearest import nearest_station_sql

SGT = timezone(timedelta(hours=8))
T = date(2025, 3, 10)


def _at(d, minute):
    return datetime(d.year, d.month, d.day, tzinfo=SGT) + timedelta(minutes=minute)


def test_reporting_window_is_the_7_days_before_the_cutoff(spark):
    d7 = T - timedelta(days=7)
    labels = spark.createDataFrame([
        ("A", d7, 1, _at(d7, 10), _at(d7, 10)),  # last reading 00:10 on T-7: before the window start (00:15)
        ("B", d7, 1, _at(d7, 10), _at(d7, 15)),  # a reading at 00:15 on T-7: inside
        ("C", T, 1, _at(T, 14), _at(T, 600)),    # first reading 00:14 on T: before the cut-off, inside
        ("D", T, 1, _at(T, 15), _at(T, 600)),    # first reading 00:15 on T: at the cut-off, outside
        ("E", T - timedelta(days=3), 0, None, None),  # a station-day with no counted reading
    ], "station_id STRING, sgt_date DATE, n_valid LONG, first_valid_ts TIMESTAMP, last_valid_ts TIMESTAMP")
    labels.createOrReplaceTempView("fx_labels")
    dist = spark.createDataFrame(
        [("mp2025", "X", "XX", "R", s, f"name {s}", km, False, "centroid") for s, km in
         (("E", 0.1), ("D", 0.5), ("A", 1.0), ("C", 2.0), ("B", 3.0))]
        + [("mp2019", "X", "XX", "R", "B", "name B", 0.01, False, "centroid")],
        "boundary STRING, planning_area STRING, planning_area_code STRING, region STRING, station_id STRING, "
        "station_name STRING, distance_km DOUBLE, station_inside_area BOOLEAN, ref_point STRING")
    dist.createOrReplaceTempView("fx_dist")
    rows = {r.target_date: r for r in spark.sql(nearest_station_sql("fx_labels", "fx_dist", "mp2025")).collect()}
    r = rows[T]
    assert (r.station_id, r.n_reporting, r.distance_km) == ("C", 2, 2.0)
    assert rows[T + timedelta(days=1)].station_id == "D"  # D's 00:15 reading on T counts for T+1
