"""Assign each geocoded residential HDB block to a Master Plan 2025 planning area (point in polygon, shapely); local only.

Run from the repo root:
    .venv\\Scripts\\python scripts/static/blocks_to_areas.py [--data <coolcheck-data>] [--near-m 25]

Input: coolcheck-data/geocode/geocoded_blocks.csv (all 10,817 blocks, confirmed = Y and the 10 with confirmed = N) joined on
blk_no + street to HDB Property Information (the file data.gov.sg now calls "HDB Property Information"; it is the HDB
Existing Building dataset) for total_dwelling_units and bldg_contract_town. Boundary: mp2025 (decision C1).
Assignment: the polygon that contains the point. A block is 'outside' when no polygon contains or touches it (no area
is given; the nearest area and its distance are recorded), 'on_boundary' when it lies on an edge or another polygon is
within --near-m metres of it (the containing polygon is kept), else 'inside'. Distances use 1 degree = 111.0 km, good
to 0.1% across Singapore.
Cross-check: the HDB town of the block against the planning areas the town is expected to fall in (TOWN_AREAS below, a
judgement from the town boundaries, not a data file); a block outside the expected set is listed, not changed.
Writes <data>/analysis/hdb_blocks_to_areas.csv and docs/checks/hdb_blocks_to_areas.md.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from shapely import STRtree
from shapely.geometry import Point, shape

REPO = Path(__file__).resolve().parents[2]
BOUNDARY = "static/ura_mp2025_planning_area_boundary"
HDB = "static/hdb_property_information/d_17f5382f26140b1fdae0ba2ef6239d2f.csv"
M_PER_DEG = 111_000.0
COLUMNS = ["blk_no", "street", "rental_block", "confirmed", "outcome", "lat", "lon", "total_dwelling_units", "hdb_town",
           "planning_area", "planning_area_code", "assignment", "nearest_other_area", "nearest_other_m",
           "town_expected_areas", "town_match"]
# Planning areas each HDB town (bldg_contract_town) can fall in. Central Area (CT) is the old town for the Central
# planning areas; Bukit Merah town includes Outram's Tanjong Pagar and Outram Park; Kallang/Whampoa runs into Rochor and
# Novena; Geylang into Paya Lebar and Kallang; Jurong West into Boon Lay and Pioneer; Toa Payoh into Novena and Bishan.
TOWN_AREAS = {
    "AMK": ["ANG MO KIO"], "BB": ["BUKIT BATOK"], "BD": ["BEDOK"], "BH": ["BISHAN"],
    "BM": ["BUKIT MERAH", "OUTRAM"], "BP": ["BUKIT PANJANG"], "BT": ["BUKIT TIMAH"], "CCK": ["CHOA CHU KANG"],
    "CL": ["CLEMENTI"],
    "CT": ["DOWNTOWN CORE", "OUTRAM", "ROCHOR", "MUSEUM", "RIVER VALLEY", "SINGAPORE RIVER", "ORCHARD", "NEWTON",
           "MARINA SOUTH"],
    "GL": ["GEYLANG", "PAYA LEBAR", "KALLANG"], "HG": ["HOUGANG"], "JE": ["JURONG EAST"],
    "JW": ["JURONG WEST", "BOON LAY", "PIONEER"], "KWN": ["KALLANG", "ROCHOR", "NOVENA"], "MP": ["MARINE PARADE"],
    "PG": ["PUNGGOL"], "PRC": ["PASIR RIS"], "QT": ["QUEENSTOWN"], "SB": ["SEMBAWANG"], "SGN": ["SERANGOON"],
    "SK": ["SENGKANG"], "TAP": ["TAMPINES"], "TG": ["TENGAH"], "TP": ["TOA PAYOH", "NOVENA", "BISHAN"],
    "WL": ["WOODLANDS"], "YS": ["YISHUN"],
}


def load_areas(path):
    gj = json.loads(next(path.glob("*.geojson")).read_text(encoding="utf-8"))
    return [(f["properties"]["PLN_AREA_N"], f["properties"]["PLN_AREA_C"], shape(f["geometry"])) for f in gj["features"]]


def assign(points, areas, near_m):
    """points: [(lat, lon)]; returns one dict per point."""
    geoms = [a[2] for a in areas]
    tree = STRtree(geoms)
    near_deg = near_m / M_PER_DEG
    out = []
    for lat, lon in points:
        pt = Point(lon, lat)
        cover = [i for i in tree.query(pt, predicate="intersects")]
        inside = [i for i in cover if geoms[i].contains(pt)]
        res = {"area": None, "code": None, "assignment": "outside", "other": None, "other_m": None}
        if cover:
            # a point on a shared edge is covered by several polygons: keep the first in name order, flag it
            pick = inside[0] if inside else sorted(cover, key=lambda i: areas[i][0])[0]
            res.update(area=areas[pick][0], code=areas[pick][1], assignment="inside")
            if not inside or len(cover) > 1:
                res["assignment"] = "on_boundary"
            others = [i for i in tree.query(pt, predicate="dwithin", distance=near_deg) if i != pick]
            if others:
                d = {i: geoms[i].distance(pt) * M_PER_DEG for i in others}
                j = min(d, key=d.get)
                res.update(other=areas[j][0], other_m=round(d[j], 1))
                if d[j] <= near_m:
                    res["assignment"] = "on_boundary"
        else:
            cand = tree.query(pt, predicate="dwithin", distance=0.05)
            d = {i: geoms[i].distance(pt) * M_PER_DEG for i in (cand if len(cand) else range(len(geoms)))}
            j = min(d, key=d.get)
            res.update(other=areas[j][0], other_m=round(d[j], 1))
        out.append(res)
    return out


def md_table(head, rows):
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO.parent / "coolcheck-data"))
    ap.add_argument("--near-m", type=float, default=25.0)
    a = ap.parse_args()
    data = Path(a.data)
    hdb = {}
    with (data / HDB).open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            hdb[(r["blk_no"], r["street"])] = r
    blocks = list(csv.DictReader((data / "geocode/geocoded_blocks.csv").open(encoding="utf-8", newline="")))
    areas = load_areas(data / BOUNDARY)
    missing = [b for b in blocks if (b["blk_no"], b["street"]) not in hdb]
    pts = [(float(b["onemap_latitude"]), float(b["onemap_longitude"])) for b in blocks]
    res = assign(pts, areas, a.near_m)
    rows = []
    for b, r in zip(blocks, res):
        h = hdb.get((b["blk_no"], b["street"]), {})
        town = h.get("bldg_contract_town", "")
        exp = TOWN_AREAS.get(town)
        match = "no_town" if not exp else ("unassigned" if not r["area"] else ("Y" if r["area"] in exp else "N"))
        rows.append([b["blk_no"], b["street"], b["rental_block"], b["confirmed"], b["outcome"], pts[len(rows)][0],
                     pts[len(rows)][1], h.get("total_dwelling_units", ""), town, r["area"] or "", r["code"] or "",
                     r["assignment"], r["other"] or "", "" if r["other_m"] is None else r["other_m"],
                     "|".join(exp or []), match])
    out = data / "analysis" / "hdb_blocks_to_areas.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        w.writerows(rows)
    report(rows, missing, areas, data, out, a.near_m)
    print(f"{len(rows)} blocks -> {out}")


def report(rows, missing, areas, data, out, near_m):
    ix = {c: i for i, c in enumerate(COLUMNS)}
    n = len(rows)
    ass = Counter(r[ix["assignment"]] for r in rows)
    du = lambda r: int(r[ix["total_dwelling_units"]] or 0)
    conf_n = [r for r in rows if r[ix["confirmed"]] == "N"]
    by_area = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        if r[ix["planning_area"]]:
            e = by_area[r[ix["planning_area"]]]
            e[0] += 1
            e[1] += du(r)
            e[2] += r[ix["confirmed"]] == "N"
    prov = json.loads((data / BOUNDARY / "provenance.json").read_text(encoding="utf-8"))
    hprov = json.loads((data / HDB).parent.joinpath("provenance.json").read_text(encoding="utf-8"))
    mism = [r for r in rows if r[ix["town_match"]] == "N"]
    cross = Counter((r[ix["hdb_town"]], r[ix["planning_area"]] or "(none)") for r in rows)
    towns = sorted({r[ix["hdb_town"]] for r in rows})
    lines = [
        "# HDB blocks to Master Plan 2025 planning areas",
        "",
        f"Script: `scripts/static/blocks_to_areas.py`. Output: `{out.relative_to(data.parent).as_posix()}` (outside the repo, one row per block). "
        "Local only: nothing is loaded to Unity Catalog.",
        "",
        f"Boundary: {prov['name']} (`{prov['dataset_id']}`, file `{prov['file']}`, sha256 `{prov['sha256'][:12]}...`), {len(areas)} planning areas, "
        "point in polygon with shapely (WGS84 lon/lat from `geocoded_blocks.csv`). "
        f"HDB attributes: {hprov['name']} (`{hprov['dataset_id']}`, sha256 `{hprov['sha256'][:12]}...`); data.gov.sg now names the "
        "HDB Existing Building dataset this way, and it is the only HDB building file in `coolcheck-data/static/`.",
        "",
        "## Result",
        "",
        f"- Blocks: **{n:,}** (confirmed = Y {n - len(conf_n):,}; confirmed = N {len(conf_n)}). Join to HDB Property Information on blk_no + street: "
        f"{n - len(missing):,} found, {len(missing)} not found.",
        f"- Dwelling units: {sum(du(r) for r in rows):,} in total (the file's residential total is 1,179,156).",
        f"- **Assigned to a planning area: {n - ass['outside']:,}.** inside {ass['inside']:,}; on_boundary {ass['on_boundary']:,} "
        f"(on an edge, or another area's polygon within {near_m:g} m; the containing polygon is kept); **outside every polygon {ass['outside']:,}** (no area given).",
        f"- Planning areas with at least one block: {len(by_area)} of {len(areas)}.",
        "",
        "## Blocks per planning area",
        "",
        md_table(["planning_area", "blocks", "dwelling_units", "of which confirmed N"],
                 [[k, v[0], f"{v[1]:,}", v[2]] for k, v in sorted(by_area.items())]),
        "",
        "Planning areas with no block: " + (", ".join(sorted(x[0] for x in areas if x[0] not in by_area)) or "none") + ".",
        "",
        f"## Boundary and outside cases ({ass['on_boundary'] + ass['outside']})",
        "",
    ]
    bl = sorted((r for r in rows if r[ix["assignment"]] != "inside"),
                key=lambda r: (r[ix["assignment"]], r[ix["planning_area"]], r[ix["street"]], r[ix["blk_no"]]))
    if bl:
        lines += [md_table(["blk", "street", "conf", "hdb_town", "assigned_area", "assignment", "other_area", "other_m", "town_match"],
                           [[r[ix["blk_no"]], r[ix["street"]], r[ix["confirmed"]], r[ix["hdb_town"]], r[ix["planning_area"]] or "(none)",
                             r[ix["assignment"]], r[ix["nearest_other_area"]], r[ix["nearest_other_m"]], r[ix["town_match"]]] for r in bl]), ""]
    else:
        lines += ["None.", ""]
    lines += [
        "## The 10 blocks with confirmed = N",
        "",
        md_table(["blk", "street", "hdb_town", "assigned_area", "assignment", "other_area", "other_m", "town_match"],
                 [[r[ix["blk_no"]], r[ix["street"]], r[ix["hdb_town"]], r[ix["planning_area"]] or "(none)", r[ix["assignment"]],
                   r[ix["nearest_other_area"]], r[ix["nearest_other_m"]], r[ix["town_match"]]] for r in conf_n]),
        "",
        "## Cross-check against the HDB town",
        "",
        "The expected planning areas per town are my judgement from the town boundaries (`TOWN_AREAS` in the script), not a data field. "
        f"Blocks whose area is in the expected set for their town: **{sum(r[ix['town_match']] == 'Y' for r in rows):,}**; "
        f"outside the set: **{len(mism)}**; unassigned: {sum(r[ix['town_match']] == 'unassigned' for r in rows)}; town with no expected set: "
        f"{sum(r[ix['town_match']] == 'no_town' for r in rows)}.",
        "",
        "Blocks per HDB town and planning area (only pairs with at least one block):",
        "",
        md_table(["hdb_town", "planning_area", "blocks", "expected"],
                 [[t, p, c, "Y" if p in TOWN_AREAS.get(t, []) else "N"] for (t, p), c in sorted(cross.items())]),
        "",
        f"### Blocks outside the expected set ({len(mism)})",
        "",
    ]
    if mism:
        lines += [md_table(["blk", "street", "conf", "hdb_town", "assigned_area", "assignment", "other_area", "other_m"],
                           [[r[ix["blk_no"]], r[ix["street"]], r[ix["confirmed"]], r[ix["hdb_town"]], r[ix["planning_area"]],
                             r[ix["assignment"]], r[ix["nearest_other_area"]], r[ix["nearest_other_m"]]]
                            for r in sorted(mism, key=lambda r: (r[ix["hdb_town"]], r[ix["planning_area"]], r[ix["street"]], r[ix["blk_no"]]))]), ""]
    else:
        lines += ["None.", ""]
    (REPO / "docs/checks/hdb_blocks_to_areas.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
