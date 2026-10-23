"""Planning-area to WBGT-station distance matrix (H10), computed locally with shapely; no API calls.

Run from the repo root:
    .venv\\Scripts\\python scripts/static/area_station_distance.py [--data <coolcheck-data>] [--load]
        [--catalog coolcheck] [--profile coolcheck]

Boundaries: Master Plan 2025 (default, decision C1) and Master Plan 2019 (comparison only); each is a parameter.
Reference point per area (ref_point column): mp2025 uses 'hdb_block_mean', the dwelling-unit-weighted mean of the
confirmed geocoded residential HDB blocks assigned to the area (analysis/hdb_blocks_to_areas.csv, from
scripts/static/blocks_to_areas.py; section 14.8 B); an area with no block keeps the polygon centroid, or a point on the
surface where the centroid falls outside the area ('centroid', 'point_on_surface'). mp2019 stays on the centroid, for
comparison only. Use --no-blocks for the v1 table (centroid for both boundaries).
Island rule: a station inside SOUTHERN ISLANDS, WESTERN ISLANDS or NORTH-EASTERN ISLANDS (mp2025) is offshore; the script
prints them and stops with exit code 1 if the set is not S142, S137 and S151 (--expect-offshore).
Stations: every WBGT station in the raw backfill files, at its most recent location. Distances are haversine km;
at Singapore's latitude lon/lat degrees are nearly square (cos 1.3° = 0.9997), so the centroid in degrees is fine.
Writes <data>/analysis/area_station_distance_v2.csv (the v1 file area_station_distance.csv is not touched; --out to change); --load also writes <catalog>.silver.area_station_distance
through Databricks Connect with --profile (overwrite; both default to coolcheck, the trial; Free Edition: --catalog workspace --profile freeedition).
"""
import argparse
import csv
import json
import math
import re
from collections import Counter
from pathlib import Path

from shapely.geometry import Point, shape

REPO = Path(__file__).resolve().parents[2]
BOUNDARIES = {"mp2025": "static/ura_mp2025_planning_area_boundary", "mp2019": "static/ura_mp2019_planning_area_boundary"}
BLOCKS = "analysis/hdb_blocks_to_areas.csv"
ISLAND_AREAS = ("SOUTHERN ISLANDS", "WESTERN ISLANDS", "NORTH-EASTERN ISLANDS")
EXPECTED_OFFSHORE = ("S137", "S142", "S151")
COLUMNS = ["boundary", "planning_area", "planning_area_code", "region", "ref_point", "ref_lat", "ref_lon", "station_id",
           "station_name", "station_lat", "station_lon", "station_first_day", "station_last_day", "distance_km",
           "station_inside_area"]


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def stations(raw):
    st = {}
    for f in sorted((raw / "wbgt").rglob("*.jsonl")):
        day = f.stem.split("_")[-1]
        for ln in f.read_text(encoding="utf-8").splitlines():
            for rec in (json.loads(ln).get("data") or {}).get("records") or []:
                for r in rec["item"]["readings"]:
                    s = r["station"]
                    e = st.setdefault(s["id"], {"first": day, "last": day})
                    e.update(name=s["name"], lat=float(r["location"]["latitude"]), lon=float(r["location"]["longitude"]),
                             last=max(e["last"], day), first=min(e["first"], day))
    return st


def areas(path):
    gj = json.loads(next(path.glob("*.geojson")).read_text(encoding="utf-8"))
    out = []
    for f in gj["features"]:
        g = shape(f["geometry"])
        c = g.centroid
        ref, kind = (c, "centroid") if g.contains(c) else (g.representative_point(), "point_on_surface")
        p = f["properties"]
        out.append({"name": p["PLN_AREA_N"], "code": p["PLN_AREA_C"], "region": p["REGION_N"], "geom": g,
                    "ref": ref, "ref_point": kind})
    return out


def block_means(path):
    """Dwelling-unit-weighted mean (lat, lon) of the confirmed blocks per planning area: {area: (lat, lon, blocks, units)}."""
    acc = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            du = int(r["total_dwelling_units"] or 0)
            if r["confirmed"] != "Y" or not r["planning_area"] or du <= 0:
                continue
            e = acc.setdefault(r["planning_area"], [0.0, 0.0, 0, 0])
            e[0] += du * float(r["lat"])
            e[1] += du * float(r["lon"])
            e[2] += 1
            e[3] += du
    return {k: (v[0] / v[3], v[1] / v[3], v[2], v[3]) for k, v in acc.items()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO.parent / "coolcheck-data"))
    ap.add_argument("--out", help="default <data>/analysis/area_station_distance_v2.csv")
    ap.add_argument("--no-blocks", action="store_true", help="v1: centroid reference point for every area")
    ap.add_argument("--expect-offshore", default=",".join(EXPECTED_OFFSHORE))
    ap.add_argument("--boundary", action="append", help="label=folder under <data>; default mp2025 and mp2019")
    ap.add_argument("--load", action="store_true")
    ap.add_argument("--catalog", default="coolcheck", help="catalog --load writes to")
    ap.add_argument("--profile", default="coolcheck", help="Databricks CLI profile --load connects with")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"\w+", a.catalog):
        raise SystemExit(f"bad catalog name: {a.catalog!r}")
    data = Path(a.data)
    bounds = dict(b.split("=", 1) for b in a.boundary) if a.boundary else BOUNDARIES
    st = stations(data / "raw")
    means = {} if a.no_blocks else block_means(data / BLOCKS)
    rows, nearest = [], {}
    offshore = set()
    for label, folder in bounds.items():
        for ar in areas(data / folder):
            if label == "mp2025" and ar["name"] in means:
                lat, lon, _, _ = means[ar["name"]]
                ar.update(ref=Point(lon, lat), ref_point="hdb_block_mean")
            best = None
            for sid, s in sorted(st.items()):
                d = haversine_km(ar["ref"].y, ar["ref"].x, s["lat"], s["lon"])
                rows.append([label, ar["name"], ar["code"], ar["region"], ar["ref_point"], round(ar["ref"].y, 6),
                             round(ar["ref"].x, 6), sid, s["name"], s["lat"], s["lon"], s["first"], s["last"], round(d, 4),
                             ar["geom"].contains(Point(s["lon"], s["lat"]))])
                if label == "mp2025" and ar["name"] in ISLAND_AREAS and rows[-1][-1]:
                    offshore.add(sid)
                if best is None or d < best[1]:
                    best = (sid, d)
            nearest[(label, ar["name"])] = (best[0], ar["ref_point"])
    out = Path(a.out) if a.out else data / "analysis" / "area_station_distance_v2.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        w.writerows(rows)
    print(f"{len(st)} stations; {len(rows)} rows -> {out}")
    for label in bounds:
        n = sum(1 for k in nearest if k[0] == label)
        pos = sum(1 for k, v in nearest.items() if k[0] == label and v[1] == "point_on_surface")
        print(f"{label}: {n} areas, {pos} use a point on the surface (centroid outside the area)")
        if label == "mp2025":
            kinds = Counter(v[1] for k, v in nearest.items() if k[0] == label)
            print(f"mp2025 reference points: {dict(sorted(kinds.items()))}")
    for name, (lat, lon, nb, du) in sorted(means.items()):
        ar = next(x for x in areas(data / bounds["mp2025"]) if x["name"] == name)
        if not ar["geom"].contains(Point(lon, lat)):
            print(f"note: the block mean of {name} ({nb} blocks, {du} units) lies outside its polygon")
    print("offshore stations (inside an island area, mp2025): "
          + ", ".join(f"{s} {st[s]['name']} (in {next(r[1] for r in rows if r[0] == 'mp2025' and r[7] == s and r[1] in ISLAND_AREAS and r[-1])})"
                      for s in sorted(offshore)))
    expected = set(a.expect_offshore.split(","))
    if offshore != expected:
        print(f"STOP: offshore set {sorted(offshore)} differs from the expected {sorted(expected)}")
        raise SystemExit(1)
    if {"mp2025", "mp2019"} <= set(bounds):
        names = {k[1] for k in nearest}
        diff = sorted(n for n in names if nearest.get(("mp2025", n), (None,))[0] != nearest.get(("mp2019", n), (None,))[0])
        print(f"areas whose nearest station (all {len(st)} stations, any date) differs mp2019 vs mp2025"
              + ("" if a.no_blocks else " (the boundary and the reference point both differ: block mean vs centroid)") + f": {len(diff)}"
              + (": " + ", ".join(f"{n} ({nearest.get(('mp2019', n), ('-',))[0]} -> {nearest.get(('mp2025', n), ('-',))[0]})" for n in diff) if diff else ""))
    if a.load:
        from databricks.connect import DatabricksSession
        spark = DatabricksSession.builder.serverless().profile(a.profile).getOrCreate()
        table = f"{a.catalog}.silver.area_station_distance"
        schema = ("boundary STRING, planning_area STRING, planning_area_code STRING, region STRING, ref_point STRING, "
                  "ref_lat DOUBLE, ref_lon DOUBLE, station_id STRING, station_name STRING, station_lat DOUBLE, "
                  "station_lon DOUBLE, station_first_day STRING, station_last_day STRING, distance_km DOUBLE, "
                  "station_inside_area BOOLEAN")
        df = spark.createDataFrame(rows, schema)
        df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(table)
        files = []
        for label, folder in bounds.items():
            prov = json.loads((data / folder / "provenance.json").read_text(encoding="utf-8"))
            files.append(f"{label}: {prov['name']} ({prov['dataset_id']}, file {prov['file']}, sha256 {prov['sha256']})")
        comment = ("H10 distance matrix from scripts/static/area_station_distance.py. Boundaries: " + "; ".join(files)
                   + ". The nearest-station view defaults to mp2025 (decision C1); mp2019 is for comparison only. "
                   "Reference point (ref_point column): mp2025 the dwelling-unit-weighted mean of the confirmed geocoded HDB blocks "
                   "in the area (hdb_block_mean); an area with no block, and mp2019, the polygon centroid or a point on the "
                   "surface where the centroid falls outside the area. Stations: every WBGT station in "
                   "the raw backfill at its latest location. Distance: haversine km.")
        spark.sql(f"COMMENT ON TABLE {table} IS '{comment.replace(chr(39), '')}'")
        print("loaded", spark.table(table).count(), "rows into", table)


if __name__ == "__main__":
    main()
