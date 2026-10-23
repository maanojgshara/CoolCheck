"""Load the four CSVs written by scripts/static/refuge_park_access.py into <catalog>.silver through Databricks Connect,
replacing each table, with table and column comments and source and licence tags (H15).

Run from the repo root; it writes tables, so only after the user's OK:
    .venv\\Scripts\\python scripts/static/load_refuge_park_access.py [--data <coolcheck-data>] [--catalog coolcheck]
        [--profile coolcheck] [--check-only]

Tables: refuge_points, park_polygons, block_access, area_access. Before writing it checks each file's columns, its row
count and the set sizes (EXPECTED), and stops if one differs. Each table is created with CREATE OR REPLACE TABLE
(columns, types, column and table comments), then filled by an append and tagged; for a moment between the two the table
is empty. After the write it reads back the row count, the columns without a comment, the tags and the Delta version.
--check-only runs the checks and writes nothing.
"""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LICENCE = "Singapore Open Data Licence v1.0"
FOLDERS = {"clubs": "community_club_passion_wave_outlet", "gtp": "moh_dementia_friendly_go_to_points",
           "eldercare": "eldercare_services", "nparks": "nparks_parks_and_nature_reserves", "ura": "ura_mp2025_sdcp_park",
           "boundary": "ura_mp2025_planning_area_boundary", "hdb": "hdb_property_information"}
EXPECTED = {"refuge_points": 279, "park_polygons": 888, "block_access": 10_817, "area_access": 330,
            "in_main": 206, "in_clubs_only": 113, "in_with_sac_2016": 232, "areas": 55}
DIST = "straight line sqrt(dx^2 + dy^2) in SVY21 metres"

TABLES = {
    "refuge_points": {
        "tags": {"source": "data.gov.sg: People's Association Community Club / PAssion WaVe Outlet; MOH Dementia Friendly "
                           "Go-To-Points; MOH Eldercare Services (2016)", "licence": LICENCE},
        "columns": [
            ("refuge_id", "STRING", "Row id: cc_<OBJECTID> (People's Association), gtp_<OBJECTID> (MOH Go-To-Points), eld_<INC_CRC> (2016 Eldercare Services)."),
            ("layer", "STRING", "community_club (complete layer); aac_partial (Active Ageing Centres in the Go-To-Points file, 93 of about 223, partial); gtp_sac (Senior Activity Centres in the Go-To-Points file); eldercare_sac_2016 (SACs in the 2016 Eldercare Services file)."),
            ("name", "STRING", "Name as published, with the broken character U+FFFD replaced by a space and spaces collapsed."),
            ("name_raw", "STRING", "Name exactly as in the source file."),
            ("status", "STRING", "open; temp_office (a club temporary office, counted, flagged); under_construction (a club marked (U/C), in no set)."),
            ("address", "STRING", "Address as published (block and street for clubs)."),
            ("postal_code", "STRING", "6-digit postal code, the key for removing duplicates; four club codes that lost the leading zero in the source are padded (see note)."),
            ("lat", "DOUBLE", "WGS84 latitude from the source GeoJSON."),
            ("lon", "DOUBLE", "WGS84 longitude from the source GeoJSON."),
            ("x_svy21", "DOUBLE", "SVY21 (EPSG:3414) easting in metres from lon/lat with pyproj, rounded to 1 mm; block distances are computed from it."),
            ("y_svy21", "DOUBLE", "SVY21 (EPSG:3414) northing in metres from lon/lat with pyproj, rounded to 1 mm; block distances are computed from it."),
            ("planning_area", "STRING", "Master Plan 2025 planning area containing the point."),
            ("planning_area_code", "STRING", "Master Plan 2025 planning area code."),
            ("in_main", "BOOLEAN", "Counted in the main refuge set (Community Clubs + Active Ageing Centres): not under construction and not a duplicate."),
            ("in_clubs_only", "BOOLEAN", "Counted in the clubs_only sensitivity set."),
            ("in_with_sac_2016", "BOOLEAN", "Counted in the with_sac_2016 sensitivity set (main + Go-To-Points SACs + 2016 SACs)."),
            ("duplicate_of", "STRING", "refuge_id of the row kept at the same postal code (club, then AAC, then Go-To-Points SAC, then 2016 SAC; open before temp_office; a club before a CO row housed in it); empty if this row is kept."),
            ("excluded_reason", "STRING", "Why the row is in no set (under construction); empty otherwise."),
            ("note", "STRING", "Postal code padded from the source value; temporary office."),
            ("source_dataset_id", "STRING", "data.gov.sg dataset id of the source file."),
            ("source", "STRING", "Source dataset name and agency."),
            ("source_record_updated", "STRING", "Update date of the record in the source (FMEL_UPD_D), YYYY-MM-DD."),
            ("licence", "STRING", "Licence of the source data."),
        ]},
    "park_polygons": {
        "tags": {"source": "data.gov.sg: NParks Parks and Nature Reserves; URA Master Plan 2025 SDCP Park layer", "licence": LICENCE},
        "columns": [
            ("park_id", "STRING", "np_<L_CODE> (NParks) or ura_<OBJECTID> (URA)."),
            ("layer", "STRING", "nparks or ura."),
            ("name", "STRING", "NParks park name; empty for URA (the layer has no name field)."),
            ("status", "STRING", "URA PRP_STATUS (PERMANENT or INTERIM); empty for NParks."),
            ("n_reserve", "INT", "NParks N_RESERVE flag (1 = nature reserve); null for URA."),
            ("area_m2", "DOUBLE", "Polygon area in SVY21 (EPSG:3414), m2, after repairing invalid geometry."),
            ("in_main", "BOOLEAN", "In the main park set: NParks without the 7 N_RESERVE = 1 polygons and Pulau Ubin and Chek Jawa, and not wholly inside pieces under 100 m2 after merging."),
            ("in_with_reserves", "BOOLEAN", "In the with_reserves sensitivity set: every NParks polygon not wholly inside pieces under 100 m2 after merging."),
            ("in_ura", "BOOLEAN", "In the ura sensitivity set: URA permanent and interim parks, exact duplicates out, not wholly inside pieces under 100 m2 after merging."),
            ("excluded_reason", "STRING", "Why the polygon is out of a set (nature reserve, Pulau Ubin and Chek Jawa, exact duplicate, sliver); empty otherwise."),
            ("source_dataset_id", "STRING", "data.gov.sg dataset id of the source file."),
            ("source", "STRING", "Source dataset name and agency."),
            ("source_record_updated", "STRING", "Update date of the record in the source (FMEL_UPD_D), YYYY-MM-DD."),
            ("licence", "STRING", "Licence of the source data."),
            ("geometry_wkt", "STRING", "Polygon in WGS84 lon/lat (EPSG:4326) as WKT, 7 decimals; invalid source geometry repaired with make_valid."),
        ]},
    "block_access": {
        "tags": {"source": "HDB Property Information; OneMap search geocodes (SLA); URA MP2025 planning areas; PA Community Clubs; "
                           "MOH Go-To-Points; MOH Eldercare Services; NParks Parks and Nature Reserves; URA MP2025 SDCP Park",
                 "licence": LICENCE},
        "columns": [
            ("blk_no", "STRING", "HDB block number (HDB Property Information)."),
            ("street", "STRING", "HDB street name (HDB Property Information); blk_no + street is unique."),
            ("planning_area", "STRING", "Master Plan 2025 planning area of the block (scripts/static/blocks_to_areas.py)."),
            ("planning_area_code", "STRING", "Master Plan 2025 planning area code."),
            ("total_dwelling_units", "BIGINT", "HDB dwelling units in the block (HDB Property Information)."),
            ("rental_block", "BOOLEAN", "True if the block has any rental flat (HDB Property Information)."),
            ("confirmed", "BOOLEAN", "True if the OneMap coordinate is confirmed (10,807 of 10,817); area shares use confirmed blocks only."),
            ("lat", "DOUBLE", "WGS84 latitude from OneMap search (scripts/static/geocode_hdb.py)."),
            ("lon", "DOUBLE", "WGS84 longitude from OneMap search (scripts/static/geocode_hdb.py)."),
            ("x_svy21", "DOUBLE", f"SVY21 (EPSG:3414) easting in metres, rounded to 1 mm; every distance here is a {DIST} from x_svy21/y_svy21, and what_if_add_refuge must use the same."),
            ("y_svy21", "DOUBLE", "SVY21 (EPSG:3414) northing in metres, rounded to 1 mm; see x_svy21."),
            ("refuge_main_m", "DOUBLE", f"Distance in m to the nearest refuge of the main set (refuge_points.in_main), {DIST}, to a refuge in any planning area; 2 decimals."),
            ("refuge_main_id", "STRING", "refuge_id of that nearest main-set refuge."),
            ("refuge_main_name", "STRING", "Name of that nearest main-set refuge."),
            ("refuge_clubs_only_m", "DOUBLE", f"Distance in m to the nearest refuge of the clubs_only set, {DIST}."),
            ("refuge_with_sac_2016_m", "DOUBLE", f"Distance in m to the nearest refuge of the with_sac_2016 set, {DIST}."),
            ("park_main_m", "DOUBLE", "Distance in m to the nearest edge of the merged main park set (pieces under 100 m2 dropped), 0 inside a park; straight line in SVY21."),
            ("park_main_name", "STRING", "Name of the nearest NParks park of the main set."),
            ("park_with_reserves_m", "DOUBLE", "Distance in m to the nearest edge of the merged with_reserves park set, 0 inside."),
            ("park_ura_m", "DOUBLE", "Distance in m to the nearest edge of the merged URA park set, 0 inside."),
        ]},
    "area_access": {
        "tags": {"source": "SingStat population June 2026 (silver.area_exposure); HDB Property Information; OneMap geocodes (SLA); "
                           "URA MP2025 planning areas and SDCP Park; PA Community Clubs; MOH Go-To-Points and Eldercare; NParks Parks",
                 "licence": LICENCE},
        "columns": [
            ("planning_area", "STRING", "Master Plan 2025 planning area (all 55)."),
            ("planning_area_code", "STRING", "Master Plan 2025 planning area code."),
            ("region", "STRING", "Master Plan 2025 region."),
            ("measure", "STRING", "refuge or park."),
            ("layer_set", "STRING", "refuge: main (clubs + AACs), clubs_only, with_sac_2016; park: main (NParks without reserves and Pulau Ubin), with_reserves, ura."),
            ("is_main", "BOOLEAN", "True for the main layer of the measure; the others are sensitivity runs."),
            ("residents", "BIGINT", "Residents (silver.area_exposure, SingStat June 2026)."),
            ("aged_65_plus", "BIGINT", "Residents aged 65+ (silver.area_exposure, SingStat June 2026)."),
            ("hdb_blocks_confirmed", "BIGINT", "Confirmed geocoded HDB blocks in the area."),
            ("hdb_dwelling_units_confirmed", "BIGINT", "HDB dwelling units of those blocks."),
            ("refuges_in_area", "BIGINT", "Refuges of this set inside the area; null on park rows."),
            ("refuges_per_1000_65_plus", "DOUBLE", "refuges_in_area x 1000 / aged_65_plus; null where no resident is 65+ and on park rows."),
            ("share_du_within_400m", "DOUBLE", f"Share of hdb_dwelling_units_confirmed at most 400 m ({DIST}) from the nearest refuge, or park edge, of this set; null where the area has no confirmed block."),
            ("median_block_distance_m", "DOUBLE", "Median over the area's confirmed blocks (unweighted) of the distance to this set, m; null where none."),
            ("land_area_m2", "DOUBLE", "Planning-area polygon area in SVY21, m2 (Master Plan 2025, no sea)."),
            ("park_area_m2", "DOUBLE", "Merged park area of this set inside the area, m2; null on refuge rows."),
            ("park_area_share", "DOUBLE", "park_area_m2 / land_area_m2; context only, not for the score; null on refuge rows."),
        ]},
}


def prov(data, key):
    p = json.loads((data / "static" / FOLDERS[key] / "provenance.json").read_text(encoding="utf-8"))
    return f"{p['name']} ({p['agency']}; data.gov.sg {p['dataset_id']}; sha256 {p['sha256'][:12]}; downloaded {p['downloaded']})"


def table_comment(name, data, sha):
    refuges = "; ".join(prov(data, k) for k in ("clubs", "gtp", "eldercare"))
    parks = "; ".join(prov(data, k) for k in ("nparks", "ura"))
    blocks = (f"Blocks: {prov(data, 'hdb')}, geocoded with OneMap search (SLA) by scripts/static/geocode_hdb.py; planning areas: "
              f"{prov(data, 'boundary')}.")
    tail = (f"Built by scripts/static/refuge_park_access.py (rules in src/coolcheck/access.py; report docs/checks/refuge_park_access.md), "
            f"loaded by scripts/static/load_refuge_park_access.py from {name}.csv, sha256 {sha}. Licence: {LICENCE}.")
    body = {
        "refuge_points": "Cooling refuge points (R1, decided 23 Oct 2026), every source row with its set flags: main = Community "
                         "Clubs (complete; clubs under construction out) + Active Ageing Centres (partial: 93 of about 223); "
                         "sensitivity sets clubs_only and with_sac_2016. Duplicates by postal code. Sources: " + refuges + ".",
        "park_polygons": "Park polygons (R2, decided 23 Oct 2026), every source polygon with its set flags: main = NParks without "
                         "the 7 N_RESERVE = 1 polygons and Pulau Ubin and Chek Jawa; sensitivity sets with_reserves and ura "
                         "(URA permanent and interim, exact duplicates out). Each set is merged and pieces under 100 m2 dropped "
                         "before distances. Sources: " + parks + ".",
        "block_access": "One row per residential HDB block (10,817): straight-line distances in SVY21 to the nearest refuge and "
                        "park edge for the main and each sensitivity set. " + blocks + " Refuges: " + refuges + ". Parks: " + parks + ".",
        "area_access": "One row per Master Plan 2025 planning area and layer set (55 x 6): refuges per 1,000 residents aged 65+, "
                       "share of HDB dwelling units within 400 m of a refuge or a park (confirmed blocks only), park share as "
                       "context. Seniors from silver.area_exposure (SingStat June 2026). " + blocks,
    }[name]
    return f"{body} {tail}"


def sql_str(s):
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def parse(value, typ):
    if value == "":
        return None
    if typ == "BOOLEAN":
        if value not in ("true", "false"):
            raise SystemExit(f"not a boolean: {value!r}")
        return value == "true"
    return {"DOUBLE": float, "BIGINT": int, "INT": int}.get(typ, str)(value)


def read(path, columns):
    csv.field_size_limit(2 ** 31 - 1)  # park WKT fields run to about 90,000 characters
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        if header != [c for c, _, _ in columns]:
            raise SystemExit(f"{path.name}: columns {header} differ from the expected {[c for c, _, _ in columns]}")
        return [tuple(parse(v, t) for v, (_, t, _) in zip(row, columns)) for row in reader]


def check(data):
    out, got = {}, {}
    for name, spec in TABLES.items():
        path = data / "analysis" / f"{name}.csv"
        rows = read(path, spec["columns"])
        out[name] = (rows, hashlib.sha256(path.read_bytes()).hexdigest())
        got[name] = len(rows)
    cols = [c for c, _, _ in TABLES["refuge_points"]["columns"]]
    for s in ("in_main", "in_clubs_only", "in_with_sac_2016"):
        got[s] = sum(1 for r in out["refuge_points"][0] if r[cols.index(s)])
    got["areas"] = len({r[0] for r in out["area_access"][0]})
    if len({(r[0], r[1]) for r in out["block_access"][0]}) != got["block_access"]:
        raise SystemExit("STOP: a block (blk_no + street) appears more than once")
    for k, v in EXPECTED.items():
        print(f"{k}: {got[k]:,} (expected {v:,}) {'ok' if got[k] == v else 'DIFFERS'}")
    if got != EXPECTED:
        raise SystemExit("STOP: the files differ from the expected figures; nothing written")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO.parent / "coolcheck-data"))
    ap.add_argument("--catalog", default="coolcheck")
    ap.add_argument("--profile", default="coolcheck")
    ap.add_argument("--check-only", action="store_true", help="run the checks and write nothing")
    a = ap.parse_args()
    if not re.fullmatch(r"\w+", a.catalog):
        raise SystemExit(f"bad catalog name: {a.catalog!r}")
    data = Path(a.data)
    files = check(data)
    for name, (_, sha) in files.items():
        print(f"{name}.csv sha256 {sha}")
    if a.check_only:
        print("check only: nothing written")
        return

    from databricks.connect import DatabricksSession

    spark = DatabricksSession.builder.serverless().profile(a.profile).getOrCreate()
    for name, spec in TABLES.items():
        rows, sha = files[name]
        t = f"{a.catalog}.silver.{name}"
        cols = ", ".join(f"{c} {typ} COMMENT {sql_str(cm)}" for c, typ, cm in spec["columns"])
        spark.sql(f"CREATE OR REPLACE TABLE {t} ({cols}) COMMENT {sql_str(table_comment(name, data, sha))}")
        schema = ", ".join(f"{c} {typ}" for c, typ, _ in spec["columns"])
        spark.createDataFrame(rows, schema).write.mode("append").saveAsTable(t)
        spark.sql(f"ALTER TABLE {t} SET TAGS ({', '.join(f'{sql_str(k)} = {sql_str(v)}' for k, v in spec['tags'].items())})")
        n = spark.table(t).count()
        bare = [r["col_name"] for r in spark.sql(f"DESCRIBE TABLE {t}").collect()
                if r["col_name"] and not r["col_name"].startswith("#") and not r["comment"]]
        tags = {r["tag_name"]: r["tag_value"] for r in spark.sql(
            f"SELECT tag_name, tag_value FROM {a.catalog}.information_schema.table_tags "
            f"WHERE schema_name = 'silver' AND table_name = '{name}'").collect()}
        version = spark.sql(f"DESCRIBE HISTORY {t} LIMIT 1").first()["version"]
        print(f"{t}: {n:,} rows (file {len(rows):,}), Delta version {version}, columns without a comment: {bare or 'none'}, "
              f"tags: {sorted(tags)}")
        if n != len(rows) or bare or set(tags) != set(spec["tags"]):
            raise SystemExit(f"STOP: {t} does not read back as written")


if __name__ == "__main__":
    main()
