"""Planning-area to WBGT-station distance matrix (H10), computed locally with shapely; no API calls.

Run from the repo root:
    .venv\\Scripts\\python scripts/static/area_station_distance.py [--data <coolcheck-data>] [--load]

Boundaries: Master Plan 2025 (default, decision C1) and Master Plan 2019 (comparison only); each is a parameter.
Reference point per area: the polygon centroid, or a point on the surface where the centroid falls outside the area
(flagged in ref_point). To be replaced by the mean of the geocoded block coordinates per area (D5).
Stations: every WBGT station in the raw backfill files, at its most recent location. Distances are haversine km;
at Singapore's latitude lon/lat degrees are nearly square (cos 1.3° = 0.9997), so the centroid in degrees is fine.
Writes <data>/analysis/area_station_distance.csv; --load also writes coolcheck.silver.area_station_distance
through Databricks Connect (overwrite).
"""
import argparse
import csv
import json
import math
from pathlib import Path

from shapely.geometry import Point, shape

REPO = Path(__file__).resolve().parents[2]
BOUNDARIES = {"mp2025": "static/ura_mp2025_planning_area_boundary", "mp2019": "static/ura_mp2019_planning_area_boundary"}
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO.parent / "coolcheck-data"))
    ap.add_argument("--boundary", action="append", help="label=folder under <data>; default mp2025 and mp2019")
    ap.add_argument("--load", action="store_true")
    a = ap.parse_args()
    data = Path(a.data)
    bounds = dict(b.split("=", 1) for b in a.boundary) if a.boundary else BOUNDARIES
    st = stations(data / "raw")
    rows, nearest = [], {}
    for label, folder in bounds.items():
        for ar in areas(data / folder):
            best = None
            for sid, s in sorted(st.items()):
                d = haversine_km(ar["ref"].y, ar["ref"].x, s["lat"], s["lon"])
                rows.append([label, ar["name"], ar["code"], ar["region"], ar["ref_point"], round(ar["ref"].y, 6),
                             round(ar["ref"].x, 6), sid, s["name"], s["lat"], s["lon"], s["first"], s["last"], round(d, 4),
                             ar["geom"].contains(Point(s["lon"], s["lat"]))])
                if best is None or d < best[1]:
                    best = (sid, d)
            nearest[(label, ar["name"])] = (best[0], ar["ref_point"])
    out = data / "analysis" / "area_station_distance.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        w.writerows(rows)
    print(f"{len(st)} stations; {len(rows)} rows -> {out}")
    for label in bounds:
        n = sum(1 for k in nearest if k[0] == label)
        pos = sum(1 for k, v in nearest.items() if k[0] == label and v[1] == "point_on_surface")
        print(f"{label}: {n} areas, {pos} use a point on the surface (centroid outside the area)")
    if {"mp2025", "mp2019"} <= set(bounds):
        names = {k[1] for k in nearest}
        diff = sorted(n for n in names if nearest.get(("mp2025", n), (None,))[0] != nearest.get(("mp2019", n), (None,))[0])
        print(f"areas whose nearest station (all {len(st)} stations, any date) differs mp2019 vs mp2025: {len(diff)}"
              + (": " + ", ".join(f"{n} ({nearest.get(('mp2019', n), ('-',))[0]} -> {nearest.get(('mp2025', n), ('-',))[0]})" for n in diff) if diff else ""))
    if a.load:
        from databricks.connect import DatabricksSession
        spark = DatabricksSession.builder.serverless().profile("coolcheck").getOrCreate()
        schema = ("boundary STRING, planning_area STRING, planning_area_code STRING, region STRING, ref_point STRING, "
                  "ref_lat DOUBLE, ref_lon DOUBLE, station_id STRING, station_name STRING, station_lat DOUBLE, "
                  "station_lon DOUBLE, station_first_day STRING, station_last_day STRING, distance_km DOUBLE, "
                  "station_inside_area BOOLEAN")
        df = spark.createDataFrame(rows, schema)
        df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("coolcheck.silver.area_station_distance")
        spark.sql("COMMENT ON TABLE coolcheck.silver.area_station_distance IS 'H10 distance matrix from "
                  "scripts/static/area_station_distance.py: planning-area reference point (polygon centroid; to be replaced "
                  "by the mean of geocoded blocks) to each WBGT station, haversine km. boundary mp2025 (default) or mp2019.'")
        print("loaded", spark.table("coolcheck.silver.area_station_distance").count(), "rows")


if __name__ == "__main__":
    main()
