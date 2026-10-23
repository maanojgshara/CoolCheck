"""Planning-area boundaries and park-to-area membership for the briefing dashboard's maps; local, --load to write.

Run from the repo root:
    .venv\\Scripts\\python scripts/static/planning_area_layers.py [--data <coolcheck-data>] [--load]
        [--catalog coolcheck] [--profile coolcheck]

Inputs: static/ura_mp2025_planning_area_boundary (Master Plan 2025 Planning Area Boundary (No Sea), 55 areas) and
analysis/park_polygons.csv (scripts/static/refuge_park_access.py; parks with in_main). Areas in SVY21 (EPSG:3414) through
src/coolcheck/access.py.
Writes analysis/planning_area_boundary.csv (one row per area: names, region, its SVY21 area and its polygon as WKT in
WGS84, snapped to 7 decimals with shapely.set_precision, which keeps it valid) and analysis/park_planning_area.csv (one row per main-set park and planning
area whose intersection has a positive SVY21 area: that area and its share of the park; a park can touch several areas).
Prints the main-set parks that touch no area. Stops if the boundary does not have 55 areas.
--load then writes <catalog>.silver.planning_area_boundary and <catalog>.silver.park_planning_area through Databricks
Connect with --profile, replacing each, with column and table comments and source and licence tags; the write and the
read-back are load_refuge_park_access.write_table's. --catalog and --profile default to coolcheck (the trial).
"""
import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

import shapely
from shapely.geometry import shape

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from coolcheck import access as A  # noqa: E402

BOUNDARY = "static/ura_mp2025_planning_area_boundary"
PARKS = "analysis/park_polygons.csv"
LICENCE = "Singapore Open Data Licence v1.0"
EXPECTED_AREAS = 55
TABLES = {
    "planning_area_boundary": {
        "file": "planning_area_boundary.csv",
        "tags": {"source": "data.gov.sg: URA Master Plan 2025 Planning Area Boundary (No Sea)", "licence": LICENCE},
        "columns": [
            ("planning_area", "STRING", "Master Plan 2025 planning area (PLN_AREA_N); 55 areas."),
            ("planning_area_code", "STRING", "Master Plan 2025 planning area code (PLN_AREA_C)."),
            ("region", "STRING", "Master Plan 2025 region (REGION_N)."),
            ("area_m2", "DOUBLE", "Area of the polygon in SVY21 (EPSG:3414), m2."),
            ("geometry_wkt", "STRING", "The area's polygon in WGS84 lon/lat (EPSG:4326) as WKT: invalid source geometry repaired with make_valid, then snapped to 7 decimals (shapely.set_precision keeps it valid). gold.planning_area_map turns it into GEOMETRY(4326)."),
            ("source_dataset_id", "STRING", "data.gov.sg dataset id of the source file."),
            ("licence", "STRING", "Licence of the source data."),
        ]},
    "park_planning_area": {
        "file": "park_planning_area.csv",
        "tags": {"source": "derived: silver.park_polygons (NParks, main set) x the URA Master Plan 2025 planning areas",
                 "licence": LICENCE},
        "columns": [
            ("park_id", "STRING", "park_polygons.park_id of a main-set park (NParks without the 7 N_RESERVE = 1 areas and Pulau Ubin / Chek Jawa)."),
            ("park_name", "STRING", "NParks park name."),
            ("planning_area", "STRING", "A planning area the park touches with a positive SVY21 area."),
            ("planning_area_code", "STRING", "Master Plan 2025 planning area code."),
            ("area_in_planning_area_m2", "DOUBLE", "The part of the park inside the planning area, SVY21 m2."),
            ("share_of_park", "DOUBLE", "That part over the whole park's area."),
        ]},
}


def boundary_rows(features, dataset_id):
    """One row per planning area: names, region, SVY21 area and the WGS84 polygon as WKT (7 decimals)."""
    rows = []
    for f in features:
        p = f["properties"]
        g = shapely.set_precision(A.polygonal(shape(f["geometry"])), 1e-7)  # snapped to the WKT's 7 decimals, still valid
        rows.append({"planning_area": p["PLN_AREA_N"], "planning_area_code": p["PLN_AREA_C"], "region": p["REGION_N"],
                     "area_m2": round(A.geom_to_svy21(g).area, 1), "geometry_wkt": shapely.to_wkt(g, rounding_precision=7),
                     "source_dataset_id": dataset_id, "licence": LICENCE})
    return sorted(rows, key=lambda r: r["planning_area"])


def park_areas(parks, areas):
    """Rows (park_id, park_name, planning_area, planning_area_code, area m2, share) for every park and area whose
    intersection has a positive area, and the ids of parks touching no area. parks: (id, name, SVY21 polygon);
    areas: (name, code, SVY21 polygon)."""
    tree = shapely.STRtree([g for _, _, g in areas])
    rows, alone = [], []
    for pid, name, g in parks:
        hits = []
        for j in tree.query(g, predicate="intersects"):
            part = g.intersection(areas[j][2]).area
            if part > 0:
                hits.append({"park_id": pid, "park_name": name, "planning_area": areas[j][0],
                             "planning_area_code": areas[j][1], "area_in_planning_area_m2": round(part, 1),
                             "share_of_park": round(part / g.area, 6) if g.area else None})
        rows += sorted(hits, key=lambda r: r["planning_area"])
        if not hits:
            alone.append(pid)
    return rows, alone


def write_csv(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([c for c, _, _ in columns])
        w.writerows([["" if r[c] is None else r[c] for c, _, _ in columns] for r in rows])


def table_comment(name, prov, sha):
    src = (f"{prov['name']} ({prov['agency']}; data.gov.sg {prov['dataset_id']}; sha256 {prov['sha256'][:12]}; "
           f"downloaded {prov['downloaded']})")
    body = {"planning_area_boundary": f"The 55 Master Plan 2025 planning-area polygons for the briefing dashboard's maps. Source: {src}.",
            "park_planning_area": "Which planning areas each main-set park touches (positive SVY21 intersection), so the "
                                  f"dashboard's park layer follows its area filter. Parks: silver.park_polygons; areas: {src}."}[name]
    return (f"{body} Built and loaded by scripts/static/planning_area_layers.py from {TABLES[name]['file']}, sha256 {sha}. "
            f"Licence: {LICENCE}.")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO.parent / "coolcheck-data"))
    ap.add_argument("--load", action="store_true", help="also write the two Silver tables")
    ap.add_argument("--catalog", default="coolcheck")
    ap.add_argument("--profile", default="coolcheck")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"\w+", a.catalog):
        raise SystemExit(f"bad catalog name: {a.catalog!r}")
    data = Path(a.data)
    feats = json.loads(next((data / BOUNDARY).glob("*.geojson")).read_text(encoding="utf-8"))["features"]
    prov = json.loads((data / BOUNDARY / "provenance.json").read_text(encoding="utf-8"))
    brows = boundary_rows(feats, prov["dataset_id"])
    if len(brows) != EXPECTED_AREAS:
        raise SystemExit(f"STOP: {len(brows)} planning areas, expected {EXPECTED_AREAS}")
    csv.field_size_limit(2 ** 31 - 1)
    with (data / PARKS).open(encoding="utf-8", newline="") as fh:
        parks = [(r["park_id"], r["name"], A.geom_to_svy21(A.polygonal(shapely.from_wkt(r["geometry_wkt"]))))
                 for r in csv.DictReader(fh) if r["in_main"] == "true"]
    areas = [(r["planning_area"], r["planning_area_code"], A.geom_to_svy21(shapely.from_wkt(r["geometry_wkt"]))) for r in brows]
    mrows, alone = park_areas(parks, areas)
    out = data / "analysis"
    write_csv(out / TABLES["planning_area_boundary"]["file"], TABLES["planning_area_boundary"]["columns"], brows)
    write_csv(out / TABLES["park_planning_area"]["file"], TABLES["park_planning_area"]["columns"], mrows)
    invalid = sum(not shapely.from_wkt(r["geometry_wkt"]).is_valid for r in brows)
    multi = len(mrows) - len({r["park_id"] for r in mrows})
    print(f"{len(brows)} planning areas ({invalid} invalid after rounding to 7 decimals); {len(parks)} main-set parks -> "
          f"{len(mrows)} park-area rows ({multi} extra rows for parks touching more than one area); "
          f"parks touching no area: {len(alone)}" + (f" ({', '.join(alone)})" if alone else ""))
    if not a.load:
        return
    from load_refuge_park_access import read, write_table
    from databricks.connect import DatabricksSession

    spark = DatabricksSession.builder.serverless().profile(a.profile).getOrCreate()
    for name, spec in TABLES.items():
        path = out / spec["file"]
        rows = read(path, spec["columns"])
        write_table(spark, f"{a.catalog}.silver.{name}", spec["columns"], rows,
                    table_comment(name, prov, hashlib.sha256(path.read_bytes()).hexdigest()), spec["tags"])


if __name__ == "__main__":
    main()
