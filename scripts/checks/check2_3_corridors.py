"""Day-2 checks 2 and 3: do the NParks Park Connector Loop and the LTA Cycling Path Network exist on data.gov.sg as GeoJSON?

Reads two files already on disk, no network. Standard library only:
  .venv\\Scripts\\python -I scripts/checks/check2_3_corridors.py --pcl <geojson> --pcl-meta <provenance.json> --cyc <geojson> --cyc-meta <provenance.json>
"""
import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

R = 6371.0088


def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def length_km(geom):
    lines = [geom["coordinates"]] if geom["type"] == "LineString" else geom["coordinates"]
    return sum(hav(l[i], l[i + 1]) for l in lines for i in range(len(l) - 1))


def points(geom):
    lines = [geom["coordinates"]] if geom["type"] == "LineString" else geom["coordinates"]
    return [p for l in lines for p in l]


def table(headers, rows):
    return ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"] + ["| " + " | ".join(map(str, r)) + " |" for r in rows]


def summarise(path, meta_path, group_key):
    g = json.loads(Path(path).read_text(encoding="utf-8"))
    meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    F = g["features"]
    by = defaultdict(float)
    tot = 0.0
    xs, ys = [], []
    for f in F:
        k = length_km(f["geometry"])
        tot += k
        by[str(f["properties"].get(group_key))] += k
        for p in points(f["geometry"]):
            xs.append(p[0])
            ys.append(p[1])
    in_sg = all(103.5 <= x <= 104.15 for x in xs) and all(1.1 <= y <= 1.5 for y in ys)
    return {"meta": meta, "F": F, "geom": Counter(f["geometry"]["type"] for f in F), "total": tot, "by": by, "in_sg": in_sg,
            "bbox": (min(xs), min(ys), max(xs), max(ys)), "keys": sorted(F[0]["properties"]), "crs": g.get("crs"),
            "upd": Counter(str(f["properties"].get("FMEL_UPD_D"))[:6] for f in F)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pcl", required=True)
    ap.add_argument("--pcl-meta", required=True)
    ap.add_argument("--cyc", required=True)
    ap.add_argument("--cyc-meta", required=True)
    ap.add_argument("--out2", default="docs/checks/check2.md")
    ap.add_argument("--out3", default="docs/checks/check3.md")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    jobs = [("2", "Park Connector Loop (NParks)", a.pcl, a.pcl_meta, "PCN_LOOP", a.out2,
             "NParks", "Park connector loop corridor length per planning area"),
            ("3", "Cycling Path Network (LTA)", a.cyc, a.cyc_meta, "AGENCY_MAINT", a.out3,
             "LTA", "Cycling path corridor length per planning area")]
    for num, title, path, meta_path, key, out, agency, use in jobs:
        s = summarise(path, meta_path, key)
        m = s["meta"]
        L = [f"# Check {num}: {title}: does the GeoJSON exist on data.gov.sg?", "",
             f"Script: `scripts/checks/check2_3_corridors.py`. Dataset `{m['dataset_id']}` '{m['name']}' ({m['agency']}), format {m['format']}, "
             f"source last updated {m['last_updated_at']}; file downloaded {m['downloaded']} (no key or token), {m['bytes']:,} bytes, sha256 `{m['sha256'][:16]}...`. "
             f"Page: {m['source_page']}. Licence: Singapore Open Data Licence v1.0, as stated on data.gov.sg's licence page (not in the API metadata). "
             "**Unverified until read.**", "",
             "## What was tested", "",
             "Found the dataset in a crawl of the data.gov.sg catalogue (4,664 datasets), downloaded it through the public download endpoint and read it: "
             "feature count, geometry types, attributes, bounding box, and the total length computed with the haversine formula on the coordinates.", "",
             "## Result", "",
             f"- **Exists: yes.** {len(s['F']):,} features; geometry types {dict(s['geom'])}; file CRS member: {s['crs'] or 'none (GeoJSON default, WGS84 longitude/latitude)'}.",
             f"- Attributes per feature: {', '.join('`' + k + '`' for k in s['keys'])}.",
             f"- Bounding box (lon/lat): {tuple(round(v, 4) for v in s['bbox'])}; all points inside a Singapore box: {s['in_sg']}.",
             f"- **Total length by haversine: {s['total']:,.1f} km.** `FMEL_UPD_D` record stamps by month: {dict(sorted(s['upd'].items())[:6])}"
             f"{' ...' if len(s['upd']) > 6 else ''}.", "",
             f"Length by `{key}` (km, haversine):", ""]
        L += table([key, "km"], [(k, f"{v:,.1f}") for k, v in sorted(s["by"].items(), key=lambda kv: -kv[1])[:15]])
        L += ["", "## Reading", "",
              f"- The file can give {use.lower()} by clipping the lines to the Master Plan boundary (not done here).",
              "- The two corridor files probably overlap (many park connectors are also cycling paths), so adding their lengths would double count; **not tested**.",
              "- Lengths are straight-line sums between vertices, so they slightly understate real path length; they are not checked against the agency's published length.", ""]
        if num == "3":
            L += ["- The guide asked whether this is data.gov.sg GeoJSON or an LTA DataMall shapefile needing an account key: **it is on data.gov.sg as GeoJSON, so no DataMall key is needed for this file.** "
                  "Whether DataMall has a more complete or newer version was not checked.", ""]
        L += ["## Fallback (agreed 19 Oct)", "",
              "Not triggered. (The corridor datasets are stretch goals; if they fail, corridor length is dropped.)", "",
              "## Could not confirm", "",
              f"- That the {agency} file is the complete network (no independent length figure was compared).",
              "- Whether the licence on the dataset page matches the licence page (the dataset page was not opened in a browser).",
              "- Overlap between the two corridor files, and the planning-area clipping result.", ""]
        o = Path(out)
        o.parent.mkdir(parents=True, exist_ok=True)
        o.write_text("\n".join(L) + "\n", encoding="utf-8")
        print("\n".join(L[:20]), "\n")


if __name__ == "__main__":
    main()
