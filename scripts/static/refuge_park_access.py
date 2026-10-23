"""Refuge and park layers and the cooling-access measures (R1, R2; decided 23 Oct 2026), computed locally; no load.

Run from the repo root (reads <catalog>.silver.area_exposure through Databricks Connect unless --seniors-csv is given):
    .venv\\Scripts\\python scripts/static/refuge_park_access.py [--data <coolcheck-data>] [--catalog coolcheck]
        [--profile coolcheck] [--seniors-csv <data>/analysis/area_exposure.csv]

The geometry and the layer rules are in src/coolcheck/access.py (SVY21, EPSG:3414; straight-line distances; 400 m).
Refuge sets: main = Community Clubs (People's Association file of 2 Oct 2026, DESCRIPTION = 'CC', clubs under
construction out) + the 93 Active Ageing Centres in MOH's Dementia Friendly Go-To-Points (partial); clubs_only;
with_sac_2016 = main + the Go-To-Points SACs + the 60 SACs of the 2016 Eldercare file. Duplicates by postal code.
Park sets: main = NParks Parks and Nature Reserves without the 7 N_RESERVE = 1 polygons and Pulau Ubin / Chek Jawa;
with_reserves = all NParks polygons; ura = the URA MP2025 SDCP park layer (permanent and interim, exact duplicates out).
Each park set is merged and pieces under 100 m2 are dropped.
Blocks: analysis/hdb_blocks_to_areas.csv (scripts/static/blocks_to_areas.py); every block gets distances, the area
shares use confirmed = Y only, and the report gives the effect of the 10 unconfirmed blocks. Each block also carries its
1room_rental and 2room_rental flats from HDB Property Information (joined on blk_no + street), for the risk score.
Writes <data>/analysis/{refuge_points,park_polygons,block_access,area_access}.csv and docs/checks/refuge_park_access.md.
Exit code 1, after the report is written, if a count differs from EXPECTED. If a point fails the coordinate check the
failing points are printed and nothing is written (no OneMap call is made).
"""
import argparse
import csv
import hashlib
import html
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import shape

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from coolcheck import access as A  # noqa: E402

CLUBS = "static/community_club_passion_wave_outlet"
CLUBS_2024 = "static/community_clubs"
GTP = "static/moh_dementia_friendly_go_to_points"
ELDERCARE = "static/eldercare_services"
NPARKS = "static/nparks_parks_and_nature_reserves"
URA_PARK = "static/ura_mp2025_sdcp_park"
BOUNDARY = "static/ura_mp2025_planning_area_boundary"
BLOCKS = "analysis/hdb_blocks_to_areas.csv"
HDB = "static/hdb_property_information"
LICENCE = "Singapore Open Data Licence v1.0"
UBIN = "PULAU UBIN AND CHEK JAWA"
RESERVOIR_PARKS = ("UPPER SELETAR RESERVOIR PARK", "LOWER PEIRCE RESERVOIR PARK", "UPPER PEIRCE RESERVOIR PARK")
PARK_SETS = ("main", "with_reserves", "ura")
SG_BOX = (1.13, 1.48, 103.59, 104.1)
EXPECTED = {"club_rows": 122, "clubs_under_construction": 4, "clubs_temp_office": 7, "aac": 93, "gtp_sac": 4,
            "sac_2016": 60, "possible_aac": 3, "sites_clubs_only": 113, "sites_main": 206, "sites_with_sac_2016": 232,
            "nparks_excluded": 8, "points_failing_coordinates": 0, "blocks": 10_817, "blocks_confirmed": 10_807,
            "aged_65_plus": 806_080}
REFUGE_COLUMNS = ["refuge_id", "layer", "name", "name_raw", "status", "address", "postal_code", "lat", "lon", "x_svy21",
                  "y_svy21", "planning_area", "planning_area_code", "in_main", "in_clubs_only", "in_with_sac_2016",
                  "duplicate_of", "excluded_reason", "note", "source_dataset_id", "source", "source_record_updated",
                  "licence"]
PARK_COLUMNS = ["park_id", "layer", "name", "status", "n_reserve", "area_m2", "in_main", "in_with_reserves", "in_ura",
                "excluded_reason", "source_dataset_id", "source", "source_record_updated", "licence", "geometry_wkt"]
BLOCK_COLUMNS = ["blk_no", "street", "planning_area", "planning_area_code", "total_dwelling_units", "rental_block",
                 "confirmed", "lat", "lon", "x_svy21", "y_svy21", "refuge_main_m", "refuge_main_id", "refuge_main_name",
                 "refuge_clubs_only_m", "refuge_with_sac_2016_m", "park_main_m", "park_main_name",
                 "park_with_reserves_m", "park_ura_m", "1room_rental", "2room_rental"]
AREA_COLUMNS = ["planning_area", "planning_area_code", "region", "measure", "layer_set", "is_main", "residents",
                "aged_65_plus", "hdb_blocks_confirmed", "hdb_dwelling_units_confirmed", "refuges_in_area",
                "refuges_per_1000_65_plus", "share_du_within_400m", "median_block_distance_m", "land_area_m2",
                "park_area_m2", "park_area_share"]
KML_TAG = re.compile(r"<th>([^<]*)</th>\s*<td>([^<]*)</td>")


def source(data, folder):
    d = data / folder
    gj = json.loads(next(d.glob("*.geojson")).read_text(encoding="utf-8"))
    return gj["features"], json.loads((d / "provenance.json").read_text(encoding="utf-8"))


def kml(props):
    """Attributes of a KML-derived GeoJSON feature, held in the HTML table of its Description."""
    return {html.unescape(k).strip(): html.unescape(v).strip() for k, v in KML_TAG.findall(props.get("Description") or "")}


def ymd(stamp):
    s = str(stamp or "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else ""


def refuge(layer, rid, raw_name, status, address, postal_raw, coords, prov, updated):
    lon, lat = coords[0], coords[1]
    x, y = A.to_svy21(lon, lat)
    postal = A.pad_postal(postal_raw)
    notes = [f"postal code padded from {postal_raw}"] if postal != str(postal_raw).strip() else []
    if status == "temp_office":
        notes.append("temporary office")
    return {"refuge_id": rid, "layer": layer, "name": A.clean_name(raw_name), "name_raw": raw_name, "status": status,
            "address": address, "postal_code": postal, "lat": round(lat, 7), "lon": round(lon, 7),
            "x_svy21": round(x, 3), "y_svy21": round(y, 3),
            "excluded_reason": "under construction (U/C)" if status == "under_construction" else "",
            "note": "; ".join(notes), "source_dataset_id": prov["dataset_id"], "source": f"{prov['name']} ({prov['agency']})",
            "source_record_updated": ymd(updated), "licence": LICENCE}


def build_refuges(data, facts):
    rows = []
    feats, prov = source(data, CLUBS)
    facts["clubs_file"] = {"rows": len(feats), "desc": Counter(f["properties"]["DESCRIPTION"] for f in feats), "prov": prov}
    for f in feats:
        p = f["properties"]
        if p["DESCRIPTION"] != "CC":
            continue
        addr = " ".join(str(v) for v in (p["ADDRESSBLOCKHOUSENUMBER"], p["ADDRESSSTREETNAME"]) if v)
        rows.append(refuge("community_club", f"cc_{p['OBJECTID']}", p["NAME"], A.club_status(p["NAME"]), addr,
                           p["ADDRESSPOSTALCODE"], f["geometry"]["coordinates"], prov, p["FMEL_UPD_D"]))
    old, oprov = source(data, CLUBS_2024)
    oa = [kml(f["properties"]) for f in old]
    facts["clubs_2024"] = {"rows": len(oa), "desc": Counter(a.get("DESCRIPTION") for a in oa), "prov": oprov,
                           "uc": sum(bool(re.search(r"U/C|relocation|Till", a.get("NAME", ""))) for a in oa
                                     if a.get("DESCRIPTION") == "CC")}

    feats, prov = source(data, GTP)
    facts["gtp"] = {"rows": len(feats), "prov": prov, "possible_aac": [], "aac_years": Counter()}
    dmax = 0.0
    for f in feats:
        p = f["properties"]
        x, y = A.to_svy21(*f["geometry"]["coordinates"][:2])
        dmax = max(dmax, float(np.hypot(x - float(p["X_ADDR"]), y - float(p["Y_ADDR"]))))
        kind = A.gtp_kind(A.clean_name(p["NAME"]))
        if kind == "possible_aac":
            facts["gtp"]["possible_aac"].append((A.clean_name(p["NAME"]), A.pad_postal(p["POSTAL_CODE"])))
        elif kind:
            if kind == "aac":
                facts["gtp"]["aac_years"][str(p["FMEL_UPD_D"])[:4]] += 1
            rows.append(refuge("aac_partial" if kind == "aac" else "gtp_sac", f"gtp_{p['OBJECTID']}", p["NAME"], "open",
                               p["ADDRESS"], p["POSTAL_CODE"], f["geometry"]["coordinates"], prov, p["FMEL_UPD_D"]))
    facts["gtp"]["max_xy_diff_m"] = dmax

    feats, prov = source(data, ELDERCARE)
    kinds = Counter()
    for f in feats:
        a = kml(f["properties"])
        k = A.eldercare_kind(a["NAME"])
        kinds[k] += 1
        if k == "sac":
            rows.append(refuge("eldercare_sac_2016", f"eld_{a['INC_CRC']}", a["NAME"], "open", a["ADDRESSSTREETNAME"],
                               a["ADDRESSPOSTALCODE"], f["geometry"]["coordinates"], prov, a["FMEL_UPD_D"]))
    facts["eldercare"] = {"rows": len(feats), "kinds": kinds, "prov": prov}
    return A.dedupe(rows)


def check_coordinates(rows, areas, codes):
    lo_lat, hi_lat, lo_lon, hi_lon = SG_BOX
    placed = A.assign_areas([r["x_svy21"] for r in rows], [r["y_svy21"] for r in rows], areas)
    failing, tolerance = [], []
    for r, (area, d) in zip(rows, placed):
        r["planning_area"], r["planning_area_code"] = area or "", codes.get(area, "")
        in_box = lo_lat <= r["lat"] <= hi_lat and lo_lon <= r["lon"] <= hi_lon
        if not in_box or area is None:
            failing.append((r, "outside the box" if not in_box else f"{d:.0f} m outside every planning area"))
        elif d > 0:
            tolerance.append((r, area, d))
    return failing, tolerance


def build_parks(data, facts):
    rows, geoms = [], []
    feats, prov = source(data, NPARKS)
    facts["nparks"] = {"rows": len(feats), "invalid": 0, "prov": prov}
    for f in feats:
        p = f["properties"]
        g0 = shape(f["geometry"])
        facts["nparks"]["invalid"] += not g0.is_valid
        g = A.polygonal(g0)
        reason = ("nature reserve (N_RESERVE = 1); in with_reserves only" if p["N_RESERVE"] == 1 else
                  "Pulau Ubin and Chek Jawa (by name); in with_reserves only" if p["NAME"] == UBIN else "")
        rows.append({"park_id": f"np_{p['L_CODE']}", "layer": "nparks", "name": p["NAME"], "status": "",
                     "n_reserve": p["N_RESERVE"], "excluded_reason": reason, "elig": {"main": not reason, "with_reserves": True},
                     "source_dataset_id": prov["dataset_id"], "source": f"{prov['name']} ({prov['agency']})",
                     "source_record_updated": ymd(p["FMEL_UPD_D"]), "licence": LICENCE, "wgs": g})
    feats, prov = source(data, URA_PARK)
    facts["ura"] = {"rows": len(feats), "invalid": 0, "prov": prov, "status": Counter()}
    first = {}
    for f in feats:
        p = f["properties"]
        g0 = shape(f["geometry"])
        facts["ura"]["invalid"] += not g0.is_valid
        facts["ura"]["status"][p["PRP_STATUS"]] += 1
        g = A.polygonal(g0)
        pid = f"ura_{p['OBJECTID']}"
        dup = first.setdefault(g0.wkb, pid)
        reason = f"exact duplicate of {dup}" if dup != pid else ""
        rows.append({"park_id": pid, "layer": "ura", "name": "", "status": p["PRP_STATUS"], "n_reserve": "",
                     "excluded_reason": reason, "elig": {"ura": not reason}, "source_dataset_id": prov["dataset_id"],
                     "source": f"{prov['name']} ({prov['agency']})", "source_record_updated": ymd(p["FMEL_UPD_D"]),
                     "licence": LICENCE, "wgs": g})
    for r in rows:
        r["svy"] = A.geom_to_svy21(r["wgs"])
        r["area_m2"] = round(r["svy"].area, 1)
        r["geometry_wkt"] = shapely.to_wkt(r["wgs"], rounding_precision=7)

    layers = {}
    for s in PARK_SETS:
        members = [r for r in rows if r["elig"].get(s)]
        kept, dropped = A.merge_layer([r["svy"] for r in members])
        tree_k, tree_m = shapely.STRtree(kept), shapely.STRtree([r["svy"] for r in members])
        for r in rows:
            r[f"in_{s}"] = False
        for r in members:
            r[f"in_{s}"] = any(kept[j].intersection(r["svy"]).area > 0 for j in tree_k.query(r["svy"], predicate="intersects"))
            if not r[f"in_{s}"]:
                r["excluded_reason"] = "; ".join(x for x in (r["excluded_reason"], f"sliver under 100 m2 after merging ({s})") if x)
        sources = [[members[j] for j in tree_m.query(k, predicate="intersects") if members[j]["svy"].intersection(k).area > 0]
                   for k in kept]
        slivers = [(round(d.area, 1), [members[j]["park_id"] for j in tree_m.query(d, predicate="intersects")]) for d in dropped]
        layers[s] = {"members": members, "kept": kept, "sources": sources, "slivers": slivers,
                     "sum_m2": sum(r["svy"].area for r in members), "union_m2": sum(k.area for k in kept) + sum(d.area for d in dropped)}
    facts["ura"]["permanent_m2"] = shapely.unary_union(
        [r["svy"] for r in layers["ura"]["members"] if r["status"] == "PERMANENT"]).area
    facts["ura"]["interim_m2"] = shapely.unary_union(
        [r["svy"] for r in layers["ura"]["members"] if r["status"] == "INTERIM"]).area
    return rows, layers


def read_seniors(a):
    if a.seniors_csv:
        p = Path(a.seniors_csv)
        with p.open(encoding="utf-8", newline="") as fh:
            got = {r["planning_area"]: (int(r["residents"]), int(r["aged_65_plus"])) for r in csv.DictReader(fh)}
        return got, f"`{p.name}` read from disk (offline run; sha256 {hashlib.sha256(p.read_bytes()).hexdigest()[:12]}...)"
    if not re.fullmatch(r"\w+", a.catalog):
        raise SystemExit(f"bad catalog name: {a.catalog!r}")
    from databricks.connect import DatabricksSession

    spark = DatabricksSession.builder.serverless().profile(a.profile).getOrCreate()
    t = f"{a.catalog}.silver.area_exposure"
    got = {r["planning_area"]: (r["residents"], r["aged_65_plus"])
           for r in spark.table(t).select("planning_area", "residents", "aged_65_plus").collect()}
    version = spark.sql(f"DESCRIBE HISTORY {t} LIMIT 1").first()["version"]
    return got, f"`{t}`, Delta version {version}, through Databricks Connect (profile {a.profile})"


def block_measures(blocks, refuges, layers):
    bx, by = np.array([b["x_svy21"] for b in blocks]), np.array([b["y_svy21"] for b in blocks])
    for s in A.REFUGE_SETS:
        rs = [r for r in refuges if r[f"in_{s}"]]
        d, i = A.nearest_points(bx, by, [r["x_svy21"] for r in rs], [r["y_svy21"] for r in rs])
        for b, dd, ii in zip(blocks, d, i):
            b[f"_refuge_{s}"] = float(dd)
            b[f"refuge_{s}_m"] = round(float(dd), 2)
            if s == "main":
                b["refuge_main_id"], b["refuge_main_name"] = rs[ii]["refuge_id"], rs[ii]["name"]
    for s in PARK_SETS:
        L = layers[s]
        d, i = A.nearest_polygons(bx, by, L["kept"])
        for b, dd, ii in zip(blocks, d, i):
            b[f"_park_{s}"] = float(dd)
            b[f"park_{s}_m"] = round(float(dd), 2)
            if s == "main":
                pt = shapely.Point(b["x_svy21"], b["y_svy21"])
                near = min(L["sources"][ii], key=lambda r: (r["svy"].distance(pt), r["name"]), default=None)
                b["park_main_name"] = near["name"] if near else ""


def area_measures(areas, codes, regions, seniors, blocks, refuges, layers, use_all=False):
    rows = []
    for name, poly in areas:
        bs = [b for b in blocks if b["planning_area"] == name and (use_all or b["confirmed"])]
        du = [b["total_dwelling_units"] for b in bs]
        res, a65 = seniors[name]
        base = {"planning_area": name, "planning_area_code": codes[name], "region": regions[name], "residents": res,
                "aged_65_plus": a65, "hdb_blocks_confirmed": len(bs), "hdb_dwelling_units_confirmed": sum(du),
                "land_area_m2": round(poly.area, 1)}
        for measure, sets in (("refuge", list(A.REFUGE_SETS)), ("park", list(PARK_SETS))):
            for s in sets:
                dist = [b[f"_{measure}_{s}"] for b in bs]
                r = dict(base, measure=measure, layer_set=s, is_main=s == "main",
                         share_du_within_400m=A.share_within(dist, du),
                         median_block_distance_m=round(statistics.median(dist), 1) if dist else None)
                if measure == "refuge":
                    n = sum(1 for x in refuges if x[f"in_{s}"] and x["planning_area"] == name)
                    r.update(refuges_in_area=n, refuges_per_1000_65_plus=round(1000 * n / a65, 4) if a65 else None)
                else:
                    m2, share = A.area_share(layers[s]["kept"], poly)
                    r.update(park_area_m2=round(m2, 1), park_area_share=round(share, 6))
                if r["share_du_within_400m"] is not None:
                    r["share_du_within_400m"] = round(r["share_du_within_400m"], 6)
                rows.append(r)
    return rows


def write_csv(path, columns, rows):
    def cell(v):
        return "" if v is None else ("true" if v is True else "false" if v is False else v)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(columns)
        w.writerows([[cell(r.get(c)) for c in columns] for r in rows])


def md_table(header, rows):
    return ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"] + \
           ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


def pct(v):
    return "" if v is None else f"{v:.1%}"


def ranking_section(area_rows, seniors):
    by = {(r["planning_area"], r["measure"], r["layer_set"]): r for r in area_rows}
    names = sorted({r["planning_area"] for r in area_rows})
    with65 = [n for n in names if seniors[n][1] > 0]
    with_du = [n for n in names if by[(n, "refuge", "main")]["hdb_dwelling_units_confirmed"] > 0]
    measures = [("Refuges per 1,000 residents aged 65+", "refuge", "refuges_per_1000_65_plus", with65, "clubs_only", "with_sac_2016"),
                ("Share of HDB dwelling units within 400 m of a refuge", "refuge", "share_du_within_400m", with_du, "clubs_only", "with_sac_2016"),
                ("Share of HDB dwelling units within 400 m of a park", "park", "share_du_within_400m", with_du, "with_reserves", "ura"),
                ("Park share of the area (context only)", "park", "park_area_share", with65, "with_reserves", "ura")]
    out, summary = [], []
    for title, measure, col, keys, *sens in measures:
        main = {n: by[(n, measure, "main")][col] for n in keys}
        rm = A.rank_worst_first(main)
        worst = [n for _, n in sorted((v, n) for n, v in main.items())[:10]]
        out += [f"### {title} ({len(keys)} areas; rank 1 = lowest value, worst access)", ""]
        for s in sens:
            other = {n: by[(n, measure, s)][col] for n in keys}
            ro = A.rank_worst_first(other)
            rho = A.spearman(main, other)
            w2 = [n for _, n in sorted((v, n) for n, v in other.items())[:10]]
            movers = sorted(((ro[n] - rm[n], n) for n in keys if abs(ro[n] - rm[n]) >= 5), key=lambda t: (-abs(t[0]), t[1]))
            summary.append([title, s, len(keys), "n/a" if rho is None else f"{rho:.3f}", f"{len(set(worst) & set(w2))} of 10", len(movers)])
            out += [f"- **main vs {s}:** Spearman rho {'n/a' if rho is None else f'{rho:.3f}'}; worst 10 kept: "
                    f"{len(set(worst) & set(w2))} of 10"
                    + (f" (out: {', '.join(sorted(set(worst) - set(w2)))}; in: {', '.join(sorted(set(w2) - set(worst)))})" if set(worst) != set(w2) else "")
                    + f"; areas moving 5 or more places: {len(movers)}"
                    + (": " + ", ".join(f"{n} {rm[n]:g} -> {ro[n]:g}" for _, n in movers) if movers else "") + "."]
        out.append("")
    return md_table(["measure", "sensitivity set", "areas", "Spearman rho", "worst 10 kept", "areas moving 5+"], summary) + [""] + out


def report(facts, refuges, parks, layers, blocks, area_rows, area_rows_all, failing, tolerance, seniors_src, got, ok, seniors):
    cf, c24, gtp, eld = facts["clubs_file"], facts["clubs_2024"], facts["gtp"], facts["eldercare"]
    clubs = [r for r in refuges if r["layer"] == "community_club"]
    by_layer = Counter(r["layer"] for r in refuges)
    sites = {s: sum(r[f"in_{s}"] for r in refuges) for s in A.REFUGE_SETS}
    dups = [r for r in refuges if r["duplicate_of"]]
    idname = {r["refuge_id"]: r["name"] for r in refuges}
    np_rows = [r for r in parks if r["layer"] == "nparks"]
    L = ["# Refuge and park layers and the cooling-access measures (R1, R2)", "",
         "Script: `scripts/static/refuge_park_access.py`; geometry and layer rules: `src/coolcheck/access.py`; tests: "
         "`tests/static/test_refuge_park_access.py`. Outputs (outside the repo): `coolcheck-data/analysis/refuge_points.csv`, "
         "`park_polygons.csv`, `block_access.csv`, `area_access.csv`. Nothing was loaded to Unity Catalog by this script and no "
         "OneMap call was made.", "",
         f"Seniors: {seniors_src}. Blocks: `{BLOCKS}` (geocoded HDB blocks with their Master Plan 2025 planning area).", "",
         "## Inputs", ""]
    rows = []
    for key in ("clubs_file", "clubs_2024", "gtp", "eldercare", "nparks", "ura"):
        p = facts[key]["prov"]
        rows.append([p["name"], p["agency"], f"`{p['dataset_id']}`", p["last_updated_at"][:10], p["downloaded"], f"`{p['sha256'][:12]}`",
                     "used" if key != "clubs_2024" else "compared only"])
    L += md_table(["dataset", "agency", "id", "last updated", "downloaded", "sha256", "role"], rows) + [
        "", f"All under the {LICENCE} (data.gov.sg). Planning areas: Master Plan 2025 Planning Area Boundary (No Sea).", "",
        "## Checks", ""]
    L += md_table(["figure", "expected", "this run", "same"],
                  [[k.replace("_", " "), f"{EXPECTED[k]:,}", f"{got[k]:,}", "yes" if got[k] == EXPECTED[k] else "**NO**"] for k in EXPECTED])
    L += ["", "All match." if ok else "**At least one figure differs; the measures below are not to be used until it is explained.**", ""]

    L += ["## R1, refuges", "", "### Community Clubs: the People's Association file of 2 Oct 2026", "",
          f"- **Used:** `{cf['prov']['dataset_id']}` (last updated {cf['prov']['last_updated_at']}): {cf['rows']} rows, `DESCRIPTION` "
          + ", ".join(f"'{k}' {v}" for k, v in cf["desc"].most_common()) + ". The field has exactly these two values and every "
          "non-'CC' row is named 'PAssion WaVe @ ...', so the filter `DESCRIPTION = 'CC'` is reliable.",
          f"- **Not used:** the 2024 file (`{c24['prov']['dataset_id']}`, last updated {c24['prov']['last_updated_at'][:10]}): "
          f"{c24['rows']} rows = " + ", ".join(f"'{k}' {v}" for k, v in c24["desc"].most_common())
          + f"; {c24['uc']} of its club names are marked U/C, Pending U/C, pending relocation or 'Till 1Q 2022'. Its '125 points' are not 125 clubs.",
          f"- **Under construction, in no set** (kept in `refuge_points` with `status = under_construction`): "
          + "; ".join(f"{r['name']} ({r['postal_code']})" for r in clubs if r["status"] == "under_construction") + ".",
          f"- **Temporary offices, kept and flagged** (`status = temp_office`): "
          + "; ".join(f"{r['name']} ({r['postal_code']})" for r in clubs if r["status"] == "temp_office") + ".",
          "- **Postal codes padded** (the field is numeric in the newer file and lost the leading zero; the 2024 file has the "
          "6-digit codes): " + "; ".join(f"{r['name']} {re.search(r'padded from (\d+)', r['note']).group(1)} -> {r['postal_code']}"
                                         for r in clubs if "padded" in r["note"]) + ".",
          "- **Rows named '... CO c/o / @ ... CC'**: " + "; ".join(
              f"{r['name']} ({'duplicate of ' + idname[r['duplicate_of']] if r['duplicate_of'] else 'kept: the only row at ' + r['postal_code']})"
              for r in clubs if A.CO_RX.search(r["name"])) + ".",
          f"- Club sites after removing postal-code duplicates and the clubs under construction: **{sites['clubs_only']}**.", "",
          "### Active Ageing Centres: the partial layer", "",
          f"- MOH Dementia Friendly Go-To-Points: {gtp['rows']} rows. **{by_layer['aac_partial']} AACs**, identified by name with "
          f"`AAC_RX` (`{A.AAC_RX.pattern}`, case-insensitive; the pattern of `scripts/checks/static_data_2.py`), "
          f"{len({r['postal_code'] for r in refuges if r['layer'] == 'aac_partial'})} distinct postal codes. Record update year: "
          + ", ".join(f"{k} {v}" for k, v in sorted(gtp["aac_years"].items())) + ". Partial: 93 of about 223 AACs (SingStat, 2024).",
          f"- Names with the broken character U+FFFD replaced by a space: {sum(r['name'] != r['name_raw'] for r in refuges if r['layer'] in ('aac_partial', 'gtp_sac'))} "
          "(the source name is kept in `name_raw`).",
          f"- **Possible AACs the pattern misses, not used** ({len(gtp['possible_aac'])}): "
          + "; ".join(f"{n} ({p})" for n, p in gtp["possible_aac"]) + ".",
          f"- **SACs in the Go-To-Points file** ({by_layer['gtp_sac']}), out of main, in `with_sac_2016`: " + "; ".join(
              f"{r['name']} ({r['postal_code']}" + (f", duplicate of {idname[r['duplicate_of']]}" if r["duplicate_of"] else "") + ")"
              for r in refuges if r["layer"] == "gtp_sac") + f". Sharing a postal code with an AAC: "
          f"{sum(1 for r in refuges if r['layer'] == 'gtp_sac' and r['duplicate_of'].startswith('gtp_'))}.",
          "", "### Eldercare Services, 2016 (sensitivity only)", "",
          f"- {eld['rows']} rows, all stamped 2016: SAC by name {eld['kinds']['sac']}, Silver ACE {eld['kinds']['silver_ace']} (left out), "
          f"AAC by name {eld['kinds']['aac']}, other {eld['kinds']['other']}. The {by_layer['eldercare_sac_2016']} SACs go into `with_sac_2016` only.", "",
          "### Postal-code duplicates and the sets", "",
          "Kept first by layer (club, AAC, Go-To-Points SAC, 2016 SAC), then open before temporary office, then a club's own row "
          "before a CO row housed in it. Duplicates stay in `refuge_points` with `duplicate_of`.", ""]
    pair = Counter((r["layer"], next(x["layer"] for x in refuges if x["refuge_id"] == r["duplicate_of"])) for r in dups)
    L += md_table(["duplicate row's layer", "kept row's layer", "rows"], [[k[0], k[1], v] for k, v in sorted(pair.items())]) + [""]
    L += md_table(["set", "layers", "rows (U/C out)", "sites"],
                  [[s, " + ".join(ls), sum(1 for r in refuges if r["layer"] in ls and r["status"] != "under_construction"), sites[s]]
                   for s, ls in A.REFUGE_SETS.items()]) + [""]
    L += ["### Coordinates", "",
          f"- {len(refuges)} points checked (every row of `refuge_points`): inside {SG_BOX[0]} to {SG_BOX[1]} N and {SG_BOX[2]} to "
          f"{SG_BOX[3]} E, and inside a Master Plan 2025 planning area (or within 25 m of one). **Failing: {len(failing)}.**"
          + (" No OneMap call is needed." if not failing else " **Listed below; nothing is geocoded without your OK.**"),
          f"- Points outside their polygon but within 25 m: {len(tolerance)}"
          + (": " + "; ".join(f"{r['name']} -> {ar} ({d:.1f} m)" for r, ar, d in tolerance) if tolerance else "") + "."]
    L += [f"- FAIL: {r['layer']} {r['name']} ({r['postal_code']}), lat {r['lat']}, lon {r['lon']}: {why}" for r, why in failing]
    L += ["", f"Projection check: pyproj's EPSG:4326 to EPSG:3414 of the {gtp['rows']} Go-To-Points lon/lat against the file's own "
          f"SVY21 `X_ADDR` / `Y_ADDR`: largest difference {gtp['max_xy_diff_m']:.4f} m.", ""]

    L += ["## R2, parks", "", "### NParks Parks and Nature Reserves", "",
          f"{facts['nparks']['rows']} polygons ({facts['nparks']['invalid']} invalid in the source, repaired with `make_valid`). "
          "Excluded from main (kept in `with_reserves`):", ""]
    L += md_table(["name", "L_CODE", "N_RESERVE", "area (km2, SVY21)"],
                  [[r["name"], r["park_id"][3:], r["n_reserve"], f"{r['area_m2'] / 1e6:.2f}"]
                   for r in sorted((r for r in np_rows if r["excluded_reason"].startswith(("nature", "Pulau"))), key=lambda r: -r["area_m2"])])
    kept_nature = sorted(r["name"] for r in np_rows if "NATURE PARK" in r["name"] and r["in_main"])
    L += ["", f"Nature parks with `N_RESERVE = 0` stay in main ({len(kept_nature)}): {', '.join(kept_nature)}. Three of the seven "
          "`N_RESERVE = 1` polygons are reservoir parks; see 'Reservoir parks' below.", "",
          "### URA Master Plan 2025 SDCP Park layer", "",
          f"{facts['ura']['rows']} polygons ({facts['ura']['invalid']} invalid, repaired): "
          + ", ".join(f"{k} {v}" for k, v in facts["ura"]["status"].most_common())
          + f". Merged area: permanent {facts['ura']['permanent_m2'] / 1e6:.2f} km2, interim {facts['ura']['interim_m2'] / 1e6:.2f} km2; "
          f"both are used. Exact duplicate geometries dropped: {sum(r['excluded_reason'].startswith('exact') for r in parks)}. "
          "The layer has no name field.", "", "### Park sets", ""]
    L += md_table(["set", "polygons", "sum of areas (km2)", "merged (km2)", "pieces under 100 m2 dropped", "their area (m2)", "polygons wholly in them"],
                  [[s, len(layers[s]["members"]), f"{layers[s]['sum_m2'] / 1e6:.2f}", f"{layers[s]['union_m2'] / 1e6:.2f}",
                    len(layers[s]["slivers"]), f"{sum(a for a, _ in layers[s]['slivers']):.1f}",
                    sum(1 for r in layers[s]["members"] if not r[f"in_{s}"])] for s in PARK_SETS])
    pname = {r["park_id"]: r["name"] for r in parks}
    for s in PARK_SETS:
        groups = defaultdict(list)
        for area, ids in layers[s]["slivers"]:
            groups[tuple(sorted(ids))].append(area)
        if groups:
            L += ["", f"Pieces dropped from `{s}`, by the source polygons they come from (pieces, total m2): " + "; ".join(
                f"{', '.join(i + (' ' + pname[i] if pname[i] else '') for i in ids)} ({len(v)}, {sum(v):.1f})"
                for ids, v in sorted(groups.items(), key=lambda kv: (-sum(kv[1]), kv[0])))]
    nearer = sum(1 for b in blocks if b["_park_with_reserves"] < b["_park_main"])
    L += ["", f"Blocks nearer to a park once the reserves are added: {nearer} of {len(blocks):,}, so `with_reserves` changes no block "
          "distance and no 400 m share; it changes only the park share of the areas that hold the reserves." if not nearer else
          f"Blocks nearer to a park once the reserves are added: {nearer} of {len(blocks):,}."]
    L += ["", "`static_data_2.md` gave 65.72 and 21.65 km2 from a flat approximation; the SVY21 figures above match the files' own "
          "`SHAPE_1.AREA` and are the ones to quote.", ""]

    res_polys = {r["name"]: r["svy"] for r in np_rows if r["name"] in RESERVOIR_PARKS}
    conf = [b for b in blocks if b["confirmed"]]
    near = [b for b in conf if any(g.distance(shapely.Point(b["x_svy21"], b["y_svy21"])) <= A.WALK_M for g in res_polys.values())]
    flip = [b for b in near if b["_park_main"] > A.WALK_M]
    tot_du = sum(b["total_dwelling_units"] for b in conf)
    per_area = Counter()
    for b in flip:
        per_area[b["planning_area"]] += b["total_dwelling_units"]
    L += ["## Reservoir parks (excluded as decided)", "",
          f"Confirmed HDB blocks within 400 m of Upper Seletar, Lower Peirce or Upper Peirce Reservoir Park: {len(near)} blocks, "
          f"{sum(b['total_dwelling_units'] for b in near):,} dwelling units ({sum(b['total_dwelling_units'] for b in near) / tot_du:.2%} of "
          f"{tot_du:,}). Of these, not within 400 m of a main-set park: {len(flip)} blocks, {sum(b['total_dwelling_units'] for b in flip):,} "
          "dwelling units; only these would change the park measure if the three were included"
          + (" (" + ", ".join(f"{k} {v:,}" for k, v in per_area.most_common()) + ")." if per_area else "."), ""]

    by = {(r["planning_area"], r["measure"], r["layer_set"]): r for r in area_rows}
    names = sorted({r["planning_area"] for r in area_rows if r["aged_65_plus"] > 0})
    L += ["## Measures per planning area", "",
          "Distances are straight lines in SVY21 from each block to the nearest refuge (anywhere, not only in its own area) and "
          "to the nearest edge of the merged park set (0 inside a park). Shares are of the HDB dwelling units of the confirmed "
          "blocks; 400 m counts as within. Refuges per 1,000 aged 65+ counts the refuges inside the area. Park share is the "
          "merged park area inside the area over the area's land; context only.", "",
          f"{len(names)} areas with residents aged 65+ (blank: no HDB block in the area):", ""]
    L += md_table(["planning area", "65+", "DU", "refuges (main)", "per 1,000: main", "clubs", "+SAC", "400 m refuge: main", "clubs", "+SAC",
                   "400 m park: main", "+reserves", "URA", "park share (main)"],
                  [[n, f"{by[(n, 'refuge', 'main')]['aged_65_plus']:,}", f"{by[(n, 'refuge', 'main')]['hdb_dwelling_units_confirmed']:,}",
                    by[(n, "refuge", "main")]["refuges_in_area"]]
                   + [f"{by[(n, 'refuge', s)]['refuges_per_1000_65_plus']:.2f}" for s in A.REFUGE_SETS]
                   + [pct(by[(n, "refuge", s)]["share_du_within_400m"]) for s in A.REFUGE_SETS]
                   + [pct(by[(n, "park", s)]["share_du_within_400m"]) for s in PARK_SETS]
                   + [pct(by[(n, "park", "main")]["park_area_share"])] for n in names])
    allsh = {s: A.share_within([b[f"_refuge_{s}"] for b in conf], [b["total_dwelling_units"] for b in conf]) for s in A.REFUGE_SETS}
    allpk = {s: A.share_within([b[f"_park_{s}"] for b in conf], [b["total_dwelling_units"] for b in conf]) for s in PARK_SETS}
    L += ["", "Singapore-wide share of the confirmed blocks' dwelling units within 400 m: refuge "
          + ", ".join(f"{s} {pct(v)}" for s, v in allsh.items()) + "; park " + ", ".join(f"{s} {pct(v)}" for s, v in allpk.items()) + ".", "",
          "## How the area ranking moves between the main and the sensitivity layers", "",
          "No risk score yet: each access measure is ranked on its own, worst access first.", ""]
    L += ranking_section(area_rows, seniors)

    by_all = {(r["planning_area"], r["measure"], r["layer_set"]): r for r in area_rows_all}
    diffs = [(abs((by_all[k]["share_du_within_400m"] or 0) - (r["share_du_within_400m"] or 0)), k) for k, r in by.items()
             if r["share_du_within_400m"] is not None]
    changed = sorted((d, k) for d, k in diffs if d > 0)
    unconf = [b for b in blocks if not b["confirmed"]]
    L += ["## Effect of the 10 unconfirmed blocks", "",
          f"The shares above use the {len(conf):,} confirmed blocks. With all {len(blocks):,} blocks ({len(unconf)} unconfirmed, "
          f"{sum(b['total_dwelling_units'] for b in unconf):,} dwelling units, in "
          f"{', '.join(sorted({b['planning_area'] for b in unconf}))}), {len(changed)} of {len(diffs)} area x set shares change; "
          f"the largest change is {max((d for d, _ in changed), default=0):.2%} points"
          + (f" ({changed[-1][1][0]}, {changed[-1][1][1]} {changed[-1][1][2]})." if changed else "."), "",
          "## Limits", "",
          "- Straight-line distance, not walking distance; a park distance is to its edge, not to an entrance.",
          "- The AAC layer is partial (93 of about 223), so distances overstate the gap where AACs are missing; `with_sac_2016` "
          "adds 2016 SACs that may have closed or been renamed. Both sensitivity sets bound the effect, they do not remove it.",
          "- Refuges per 1,000 aged 65+ counts refuges inside the area only; residents near a boundary also use the next area's.",
          "- The temporary club offices may be small premises; they are open, so they count, and are flagged.", ""]
    (REPO / "docs/checks/refuge_park_access.md").write_text("\n".join(L), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO.parent / "coolcheck-data"))
    ap.add_argument("--catalog", default="coolcheck")
    ap.add_argument("--profile", default="coolcheck")
    ap.add_argument("--seniors-csv", help="read seniors from this area_exposure.csv instead of <catalog>.silver.area_exposure")
    a = ap.parse_args()
    data = Path(a.data)
    facts = {}

    bfeats, _ = source(data, BOUNDARY)
    areas = [(f["properties"]["PLN_AREA_N"], A.geom_to_svy21(A.polygonal(shape(f["geometry"])))) for f in bfeats]
    codes = {f["properties"]["PLN_AREA_N"]: f["properties"]["PLN_AREA_C"] for f in bfeats}
    regions = {f["properties"]["PLN_AREA_N"]: f["properties"]["REGION_N"] for f in bfeats}
    refuges = build_refuges(data, facts)
    failing, tolerance = check_coordinates(refuges, areas, codes)
    parks, layers = build_parks(data, facts)
    seniors, seniors_src = read_seniors(a)
    if set(seniors) != set(codes):
        raise SystemExit(f"planning areas differ between the seniors and the boundary: {sorted(set(seniors) ^ set(codes))}")

    with next((data / HDB).glob("*.csv")).open(encoding="utf-8", newline="") as fh:
        rental = {(r["blk_no"], r["street"]): (int(r["1room_rental"]), int(r["2room_rental"])) for r in csv.DictReader(fh)}
    with (data / BLOCKS).open(encoding="utf-8", newline="") as fh:
        blocks = []
        for r in csv.DictReader(fh):
            lon, lat = float(r["lon"]), float(r["lat"])
            x, y = A.to_svy21(lon, lat)
            blocks.append({"blk_no": r["blk_no"], "street": r["street"], "planning_area": r["planning_area"],
                           "planning_area_code": r["planning_area_code"], "total_dwelling_units": int(r["total_dwelling_units"]),
                           "rental_block": r["rental_block"] == "Y", "confirmed": r["confirmed"] == "Y",
                           "lat": round(lat, 7), "lon": round(lon, 7), "x_svy21": round(x, 3), "y_svy21": round(y, 3),
                           "1room_rental": rental[(r["blk_no"], r["street"])][0],
                           "2room_rental": rental[(r["blk_no"], r["street"])][1]})
    if not failing:
        block_measures(blocks, refuges, layers)
        area_rows = area_measures(areas, codes, regions, seniors, blocks, refuges, layers)
        area_rows_all = area_measures(areas, codes, regions, seniors, blocks, refuges, layers, use_all=True)

    by_layer = Counter(r["layer"] for r in refuges)
    clubs = [r for r in refuges if r["layer"] == "community_club"]
    got = {"club_rows": len(clubs), "clubs_under_construction": sum(r["status"] == "under_construction" for r in clubs),
           "clubs_temp_office": sum(r["status"] == "temp_office" for r in clubs), "aac": by_layer["aac_partial"],
           "gtp_sac": by_layer["gtp_sac"], "sac_2016": by_layer["eldercare_sac_2016"],
           "possible_aac": len(facts["gtp"]["possible_aac"]),
           **{f"sites_{s}": sum(r[f"in_{s}"] for r in refuges) for s in A.REFUGE_SETS},
           "nparks_excluded": sum(1 for r in parks if r["layer"] == "nparks" and not r["elig"]["main"]),
           "points_failing_coordinates": len(failing), "blocks": len(blocks),
           "blocks_confirmed": sum(b["confirmed"] for b in blocks), "aged_65_plus": sum(v[1] for v in seniors.values())}
    ok = got == EXPECTED
    for k in EXPECTED:
        print(f"  {k}: expected {EXPECTED[k]:,}, this run {got[k]:,} {'same' if got[k] == EXPECTED[k] else 'DIFFERENT'}")
    if failing:
        for r, why in failing:
            print(f"  FAIL {r['layer']} {r['name']} ({r['postal_code']}): {why}")
        print("STOP: points fail the coordinate check; no measures computed and nothing written (no OneMap call made)")
        return 1

    out = data / "analysis"
    write_csv(out / "refuge_points.csv", REFUGE_COLUMNS, refuges)
    write_csv(out / "park_polygons.csv", PARK_COLUMNS, parks)
    write_csv(out / "block_access.csv", BLOCK_COLUMNS, blocks)
    write_csv(out / "area_access.csv", AREA_COLUMNS, area_rows)
    report(facts, refuges, parks, layers, blocks, area_rows, area_rows_all, failing, tolerance, seniors_src, got, ok, seniors)
    print(f"wrote {len(refuges)} refuge rows, {len(parks)} park rows, {len(blocks)} blocks, {len(area_rows)} area rows to {out}; "
          "docs/checks/refuge_park_access.md")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
