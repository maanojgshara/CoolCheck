"""Compare the URA Master Plan 2019 and 2025 planning-area boundary files (names, geometry, area, grid-sampled overlap).

Reads the two GeoJSON files from ../coolcheck-data/static; writes nothing but stdout and a JSON summary to .cache/.
The overlap test labels a 0.001-degree grid (about 110 m) with each file's planning area and counts cells whose label differs;
it is a sample, not an exact polygon difference (no shapely in the venv). Run from the repo root.
"""
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

from check5_onemap import point_in_ring

STATIC = Path("../coolcheck-data/static")
F19 = STATIC / "ura_mp2019_planning_area_boundary/d_4765db0e87b9c86336792efe8a1f7a66.geojson"
F25 = STATIC / "ura_mp2025_planning_area_boundary/d_2cc750190544007400b2cfd5d7f53209.geojson"
STEP = 0.001
CELL_KM2 = (STEP * 111.32 * math.cos(math.radians(1.35))) * (STEP * 110.57)


def load(p):
    j = json.loads(p.read_text(encoding="utf-8"))
    return j["features"], j


def name_of(props):
    return props.get("PLN_AREA_N") or props.get("pln_area_n") or props.get("Name")


def polys(g):
    return [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]


def ring_area_km2(ring):
    a = 0.0
    for (x1, y1, *_), (x2, y2, *_) in zip(ring, ring[1:]):
        a += x1 * y2 - x2 * y1
    return abs(a) / 2 * 111.32 * math.cos(math.radians(1.35)) * 110.57


def area_km2(g):
    return sum(ring_area_km2(p[0]) - sum(ring_area_km2(h) for h in p[1:]) for p in polys(g))


def vertices(g):
    return sum(len(r) for p in polys(g) for r in p)


def index(features):
    out = []
    for ft in features:
        g = ft["geometry"]
        for p in polys(g):
            xs = [c[0] for c in p[0]]
            ys = [c[1] for c in p[0]]
            out.append((min(xs), max(xs), min(ys), max(ys), name_of(ft["properties"]), p))
    return out


def label(x, y, idx):
    for x0, x1, y0, y1, n, p in idx:
        if x0 <= x <= x1 and y0 <= y <= y1 and point_in_ring(x, y, p[0]) and not any(point_in_ring(x, y, h) for h in p[1:]):
            return n
    return None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    f19, j19 = load(F19)
    f25, j25 = load(F25)
    print("features:", len(f19), len(f25))
    print("property fields 2019:", sorted(f19[0]["properties"]))
    print("property fields 2025:", sorted(f25[0]["properties"]))
    print("crs/top-level keys:", sorted(j19), sorted(j25))
    n19 = {name_of(f["properties"]) for f in f19}
    n25 = {name_of(f["properties"]) for f in f25}
    print("names only in 2019:", sorted(n19 - n25))
    print("names only in 2025:", sorted(n25 - n19))
    print("duplicate names:", [k for k, v in Counter(name_of(f["properties"]) for f in f25).items() if v > 1])
    print("geometry types 2019:", dict(Counter(f["geometry"]["type"] for f in f19)), "2025:", dict(Counter(f["geometry"]["type"] for f in f25)))
    a19 = {name_of(f["properties"]): area_km2(f["geometry"]) for f in f19}
    a25 = {name_of(f["properties"]): area_km2(f["geometry"]) for f in f25}
    v19 = {name_of(f["properties"]): vertices(f["geometry"]) for f in f19}
    v25 = {name_of(f["properties"]): vertices(f["geometry"]) for f in f25}
    print(f"total area km2 (planar approx): 2019 {sum(a19.values()):.1f}, 2025 {sum(a25.values()):.1f}")
    rows = sorted(((n, a19[n], a25[n], (a25[n] - a19[n]) / a19[n] * 100) for n in n19 & n25), key=lambda r: -abs(r[3]))
    print("largest area changes (name, 2019 km2, 2025 km2, % change):")
    for r in rows[:12]:
        print(f"  {r[0]:<24}{r[1]:8.2f}{r[2]:8.2f}{r[3]:+8.2f}%")
    print("areas whose area changed by more than 1%:", sum(abs(r[3]) > 1 for r in rows), "of", len(rows),
          "| identical vertex counts:", sum(v19[n] == v25[n] for n in n19 & n25), "of", len(n19 & n25))
    i19, i25 = index(f19), index(f25)
    xs = [b for b in (min(r[0] for r in i19 + i25), max(r[1] for r in i19 + i25))]
    ys = [b for b in (min(r[2] for r in i19 + i25), max(r[3] for r in i19 + i25))]
    diff = defaultdict(float)
    same = only19 = only25 = swapped = 0
    x = xs[0]
    while x <= xs[1]:
        y = ys[0]
        while y <= ys[1]:
            a, b = label(x, y, i19), label(x, y, i25)
            if a is None and b is None:
                pass
            elif a == b:
                same += 1
            elif b is None:
                only19 += 1
                diff[f"{a} -> (outside 2025)"] += 1
            elif a is None:
                only25 += 1
                diff[f"(outside 2019) -> {b}"] += 1
            else:
                swapped += 1
                diff[f"{a} -> {b}"] += 1
            y += STEP
        x += STEP
    tot = same + only19 + only25 + swapped
    print(f"grid cells inside either file: {tot}; same area {same} ({same / tot:.2%}); in 2019 only {only19} ({only19 * CELL_KM2:.2f} km2); "
          f"in 2025 only {only25} ({only25 * CELL_KM2:.2f} km2); different area {swapped} ({swapped * CELL_KM2:.2f} km2)")
    for k, v in sorted(diff.items(), key=lambda kv: -kv[1])[:15]:
        print(f"  {k}: {v} cells = {v * CELL_KM2:.2f} km2")


if __name__ == "__main__":
    main()
