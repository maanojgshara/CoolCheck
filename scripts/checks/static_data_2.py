"""Profile the second round of static downloads: AAC candidates and park polygons. Reads only files already in static/.

No network, no geocoding, no OneMap. Prints every number used in docs/checks/static_data_2.md.
Run from the repo root: .venv\\Scripts\\python scripts/checks/static_data_2.py [static_dir]
"""
import collections
import json
import math
import re
import sys
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.validation import make_valid

STATIC = Path(sys.argv[1] if len(sys.argv) > 1 else "../coolcheck-data/static")
KM_LON = 111.32 * math.cos(math.radians(1.35))  # km per degree of longitude at Singapore's latitude
KM_LAT = 111.32


def features(folder):
    f = next((STATIC / folder).glob("*.geojson"))
    return json.loads(f.read_text(encoding="utf-8"))["features"]


def table_props(f):
    """Properties, plus the key/value pairs inside an HTML Description table when there is one."""
    pr = dict(f["properties"])
    pr.update(dict(re.findall(r"<th>(.*?)</th>\s*<td>(.*?)</td>", pr.get("Description", "") or "", flags=re.S)))
    return pr


def clean(s):
    return re.sub(r"[� ]+", " ", s or "").strip()


def km2(g):
    return g.area * KM_LON * KM_LAT


def aac_section():
    print("== AAC candidates ==")
    gtp = [table_props(f) for f in features("moh_dementia_friendly_go_to_points")]
    print("GTP rows", len(gtp), "| fields", sorted({k for p in gtp for k in p}))
    print("GTP FMEL_UPD_D year", dict(collections.Counter(str(p["FMEL_UPD_D"])[:4] for p in gtp)))
    aac_rx = re.compile(r"active ageing (centre|hub|center)|\bAAC\b|\bAAH\b", re.I)
    sac_rx = re.compile(r"senior activity|\bSAC\b|silver ace", re.I)
    aac = [p for p in gtp if aac_rx.search(clean(p["NAME"]))]
    sac = [p for p in gtp if sac_rx.search(clean(p["NAME"])) and p not in aac]
    print("GTP named Active Ageing Centre/Hub/AAC:", len(aac), "| distinct postal codes", len({p["POSTAL_CODE"] for p in aac}),
          "| 6-digit postal codes", sum(bool(re.fullmatch(r"\d{6}", p["POSTAL_CODE"].strip())) for p in aac))
    print("GTP AAC FMEL_UPD_D year", dict(collections.Counter(str(p["FMEL_UPD_D"])[:4] for p in aac)))
    print("GTP named Senior Activity Centre / Silver ACE (not AAC by name):", len(sac))
    print("GTP names containing U+FFFD (encoding damage in the source):", sum("�" in p["NAME"] for p in gtp), "of", len(gtp))

    eld = [table_props(f) for f in features("eldercare_services")]
    eld_rx = re.compile(r"senior activity|\bSAC\b|silver ace|active ageing|\bAAC\b", re.I)
    eld_sel = [p for p in eld if eld_rx.search(clean(p.get("NAME", "")))]
    eld_post = {p["ADDRESSPOSTALCODE"].strip() for p in eld_sel}
    gtp_post = {p["POSTAL_CODE"].strip() for p in aac + sac}
    print("Eldercare points named SAC / Silver ACE / AAC:", len(eld_sel), "| distinct postal codes", len(eld_post))
    print("overlap by postal code with GTP AAC+SAC:", len(eld_post & gtp_post), "| union", len(eld_post | gtp_post))
    print("SingStat 2024 Active Ageing Centres: 223 (check1.md); GTP AAC share of 223: %.0f%%" % (100 * len(aac) / 223))


def park_section():
    print("\n== Park polygons ==")
    bnd = features("ura_mp2025_planning_area_boundary")
    areas = []
    for f in bnd:
        pr = table_props(f)
        areas.append((pr.get("PLN_AREA_N"), make_valid(shape(f["geometry"]))))
    print("planning areas", len(areas), "| land km2 %.1f" % sum(km2(g) for _, g in areas))

    def profile(folder, label, keep=lambda p: True):
        fs = [f for f in features(folder) if keep(f["properties"])]
        gs = [make_valid(shape(f["geometry"])) for f in fs]
        u = unary_union(gs)
        tot = sum(km2(g) for g in gs)
        print(f"-- {label}: {len(fs)} features", dict(collections.Counter(f["geometry"]["type"] for f in fs)),
              "| invalid before repair", sum(not shape(f["geometry"]).is_valid for f in fs),
              "| sum km2 %.2f, union km2 %.2f" % (tot, km2(u)))
        share = {}
        for name, g in areas:
            share[name] = km2(g.intersection(u)) / km2(g)
        v = sorted(share.values())
        print("   park share by planning area: min %.3f, median %.3f, max %.3f; areas with no park: %d"
              % (v[0], v[len(v) // 2], v[-1], sum(x == 0 for x in v)))
        print("   top 5:", [(n, round(s, 3)) for n, s in sorted(share.items(), key=lambda kv: -kv[1])[:5]])
        return fs, share

    nparks, s_all = profile("nparks_parks_and_nature_reserves", "NParks Parks and Nature Reserves (all)")
    pr = [f["properties"] for f in nparks]
    print("   fields", sorted({k for p in pr for k in p}), "| N_RESERVE", dict(collections.Counter(p["N_RESERVE"] for p in pr)),
          "| FMEL_UPD_D year", dict(collections.Counter(str(p["FMEL_UPD_D"])[:4] for p in pr)))
    big = sorted(((km2(shape(f["geometry"])), f["properties"]["NAME"]) for f in nparks), reverse=True)[:4]
    print("   largest:", [(round(a, 2), n) for a, n in big])
    f0 = nparks[0]  # one-polygon check of the flat-area approximation against the file's own SHAPE_1.AREA (m2)
    stated, measured = float(f0["properties"]["SHAPE_1.AREA"]), km2(shape(f0["geometry"])) * 1e6
    print("   flat-area check on %r: SHAPE_1.AREA %.0f m2, measured %.0f m2, difference %.1f%%"
          % (f0["properties"]["NAME"], stated, measured, 100 * (measured - stated) / stated))
    pts = features("parks")
    print("   names identical to the 462-point Parks file:",
          {table_props(f).get("NAME") for f in pts} == {f["properties"]["NAME"] for f in nparks})
    _, s_town = profile("nparks_parks_and_nature_reserves", "NParks without nature reserves (N_RESERVE=1) and the two largest",
                        keep=lambda p: p["N_RESERVE"] == 0 and p["NAME"] not in ("PULAU UBIN AND CHEK JAWA",))
    sdcp, s_sdcp = profile("ura_mp2025_sdcp_park", "URA Master Plan 2025 SDCP Park layer")
    print("   fields", sorted({k for f in sdcp for k in f["properties"]}), "| PRP_STATUS",
          dict(collections.Counter(f["properties"]["PRP_STATUS"] for f in sdcp)),
          "| FMEL_UPD_D year", dict(collections.Counter(str(f["properties"]["FMEL_UPD_D"])[:4] for f in sdcp)))
    names = list(s_all)
    for a, b, la, lb in ((s_town, s_sdcp, "NParks town-parks", "SDCP Park"), (s_all, s_sdcp, "NParks all", "SDCP Park")):
        x = [a[n] for n in names]; y = [b[n] for n in names]
        mx, my = sum(x) / len(x), sum(y) / len(y)
        r = sum((i - mx) * (j - my) for i, j in zip(x, y)) / math.sqrt(sum((i - mx) ** 2 for i in x) * sum((j - my) ** 2 for j in y))
        print(f"   correlation of area-level park share, {la} vs {lb}: {r:.2f}")

    print("-- Park Connector Loop")
    pcl = features("nparks_park_connector_loop")
    print("   features", len(pcl), dict(collections.Counter(f["geometry"]["type"] for f in pcl)),
          "| fields", sorted({k for f in pcl for k in f["properties"]}),
          "| approx km %.1f" % sum(shape(f["geometry"]).length * KM_LAT for f in pcl),
          "| FMEL_UPD_D year", dict(collections.Counter(str(f["properties"]["FMEL_UPD_D"])[:4] for f in pcl)))
    print("   segments by PCN_LOOP:", dict(collections.Counter(f["properties"]["PCN_LOOP"] for f in pcl).most_common()))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    aac_section()
    park_section()
