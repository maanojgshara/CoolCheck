"""Create the briefing dashboard's four gold views through Databricks Connect (coolcheck.briefing).

Run from the repo root; it creates views, so only after the user's OK:
    .venv\\Scripts\\python scripts/static/create_briefing_views.py [--catalog coolcheck] [--profile coolcheck]
        [--views planning_area_map refuge_layer park_layer observed_heat_daily] [--print-sql]

gold.planning_area_map over silver.planning_area_boundary; gold.refuge_layer over silver.refuge_points; gold.park_layer
over silver.park_polygons and silver.park_planning_area; gold.observed_heat_daily over silver.station_daily_label and
gold.area_nearest_station_daily. Each view gets column comments, a comment and source and licence tags (the statement is
create_risk_views.create_sql's). Read-back: the row counts of the first three (55, 206, and the park-area rows), the
columns without a comment and the tags; for observed_heat_daily the rows and their date range (the final check was scored
on 23 Oct 2026, so its window is no longer held back). --print-sql touches nothing.
"""
import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from coolcheck import briefing as B  # noqa: E402
from create_risk_views import create_sql, lit  # noqa: E402

LICENCE = "Singapore Open Data Licence v1.0"
EXPECT = {"planning_area_map": 55, "refuge_layer": 206}


def views(cat):
    s, g = f"{cat}.silver", f"{cat}.gold"
    return {
        "planning_area_map": {
            "sql": B.planning_area_map_sql(f"{s}.planning_area_boundary"), "columns": B.MAP_COLUMNS,
            "comment": "The 55 Master Plan 2025 planning areas as GEOMETRY(4326), for the briefing dashboard's maps.",
            "tags": {"source": "data.gov.sg: URA Master Plan 2025 Planning Area Boundary (No Sea); silver.planning_area_boundary",
                     "licence": LICENCE}},
        "refuge_layer": {
            "sql": B.refuge_layer_sql(f"{s}.refuge_points"), "columns": B.REFUGE_LAYER_COLUMNS,
            "comment": "The main refuge set (decision R1): community clubs, complete, and Active Ageing Centres, a partial list "
                       "(93 of about 223), with a plain type for the dashboard.",
            "tags": {"source": "data.gov.sg: People's Association clubs; MOH Dementia Friendly Go-To-Points; silver.refuge_points",
                     "licence": LICENCE}},
        "park_layer": {
            "sql": B.park_layer_sql(f"{s}.park_polygons", f"{s}.park_planning_area"), "columns": B.PARK_LAYER_COLUMNS,
            "comment": "Main-set parks (decision R2) as GEOMETRY(4326), one row per park and planning area it touches, so the "
                       "dashboard's park layer follows its area filter.",
            "tags": {"source": "data.gov.sg: NParks Parks and Nature Reserves; silver.park_polygons, silver.park_planning_area",
                     "licence": LICENCE}},
        "observed_heat_daily": {
            "sql": B.observed_heat_daily_sql(f"{s}.station_daily_label", f"{g}.area_nearest_station_daily"),
            "columns": B.OBSERVED_COLUMNS,
            "comment": f"Observed daily WBGT heat-stress categories (NEA) of the last {B.OBSERVED_DAYS} completed SGT days, usable "
                       "labels only, with the planning areas each station served that day: the briefing's observed trend. "
                       "Observed values only, never forecasts.",
            "tags": {"source": "data.gov.sg: NEA WBGT readings; silver.station_daily_label; gold.area_nearest_station_daily",
                     "licence": LICENCE}},
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="coolcheck")
    ap.add_argument("--profile", default="coolcheck")
    ap.add_argument("--views", nargs="+", choices=list(views("x")), default=list(views("x")))
    ap.add_argument("--print-sql", action="store_true", help="print the statements and touch nothing")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"\w+", a.catalog):
        raise SystemExit(f"bad catalog name: {a.catalog!r}")
    specs = views(a.catalog)
    if a.print_sql:
        for name in a.views:
            print(create_sql(name, a.catalog, specs[name]), end=";\n\n")
        return

    from databricks.connect import DatabricksSession

    spark = DatabricksSession.builder.serverless().profile(a.profile).getOrCreate()
    for name in a.views:
        v = f"{a.catalog}.gold.{name}"
        spark.sql(create_sql(name, a.catalog, specs[name]))
        spark.sql(f"ALTER VIEW {v} SET TAGS ({', '.join(f'{lit(k)} = {lit(x)}' for k, x in specs[name]['tags'].items())})")
        bare = [r["col_name"] for r in spark.sql(f"DESCRIBE TABLE {v}").collect()
                if r["col_name"] and not r["col_name"].startswith("#") and not r["comment"]]
        tags = {r["tag_name"] for r in spark.sql(f"SELECT tag_name FROM {a.catalog}.information_schema.table_tags "
                                                f"WHERE schema_name = 'gold' AND table_name = '{name}'").collect()}
        if name == "observed_heat_daily":
            r = spark.sql(f"SELECT count(*) AS n, min(sgt_date) AS d0, max(sgt_date) AS d1 FROM {v}").first()
            n, what = r["n"], f"rows, {r['d0']} to {r['d1']}"
        else:
            n = spark.table(v).count()
            what = f"rows (expected {EXPECT[name]:,})" if name in EXPECT else "rows"
        print(f"{v}: {n:,} {what}, columns without a comment: {bare or 'none'}, tags: {sorted(tags)}")
        if bare or tags != set(specs[name]["tags"]) or (name in EXPECT and n != EXPECT[name]):
            raise SystemExit(f"STOP: {v} does not read back as expected")


if __name__ == "__main__":
    main()
