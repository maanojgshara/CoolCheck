"""Day-2 check 1: does the Eldercare Services file (MOH, data.gov.sg) include Active Ageing Centres?

Reads files already on disk, no network. Standard library only, so it can run isolated:
  .venv\\Scripts\\python -I scripts/checks/check1_refuges.py --eldercare <geojson> --counts <SingStat csv> --out docs/checks/check1.md
"""
import argparse
import csv
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path


def attrs(desc):
    return {html.unescape(k).strip(): html.unescape(v).strip()
            for k, v in re.findall(r"<th>([^<]*)</th>\s*<td>([^<]*)</td>", desc or "")}


def kind(name):
    n = name.lower()
    if re.search(r"active ageing|\baac\b", n):
        return "Active Ageing Centre (name says so)"
    if "senior activity" in n or re.search(r"\bsac\b", n):
        return "Senior Activity Centre (name or 'SAC')"
    if re.search(r"silver|\bace\b", n):
        return "Silver ACE (not AAC by name)"
    if "cluster support" in n or "cluster operator" in n:
        return "Cluster Support (by name)"
    if re.search(r"health and wellness|activity centres? pte|moral charities|welfare services|community services|goodlife", n):
        return "Operator or programme name (by name)"
    if re.search(r"nursing|day care|dementia|home|villa|senior care|eldercare", n):
        return "Home / care service (by name)"
    return "Other / unclassified"


def table(headers, rows):
    return ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"] + ["| " + " | ".join(map(str, r)) + " |" for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eldercare", required=True)
    ap.add_argument("--counts", required=True)
    ap.add_argument("--out", default="docs/checks/check1.md")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    g = json.loads(Path(a.eldercare).read_text(encoding="utf-8"))
    F = g["features"]
    rows = []
    for f in F:
        at = attrs(f["properties"].get("Description"))
        x, y = f["geometry"]["coordinates"][:2]
        rows.append({"name": at.get("NAME", ""), "kind": kind(at.get("NAME", "")), "postal": at.get("ADDRESSPOSTALCODE", ""),
                     "upd": at.get("FMEL_UPD_D", "")[:8], "x": x, "y": y, "street": at.get("ADDRESSSTREETNAME", "")})
    kinds = Counter(r["kind"] for r in rows)
    upd = Counter(r["upd"][:4] for r in rows)
    names = Counter(r["name"] for r in rows)
    xy = Counter((round(r["x"], 6), round(r["y"], 6)) for r in rows)
    in_sg = sum(1.15 <= r["y"] <= 1.50 and 103.55 <= r["x"] <= 104.10 for r in rows)
    prop_keys = sorted(set().union(*[set(attrs(f["properties"].get("Description"))) for f in F]))
    counts = list(csv.DictReader(Path(a.counts).read_text(encoding="utf-8").splitlines()))
    L = ["# Check 1: does Eldercare Services include Active Ageing Centres?", "",
         "Dataset `d_f0fd1b3643ed8bd34bd403dedd7c1533` (MOH, GeoJSON, source last updated 2024-06-06). Script: `scripts/checks/check1_refuges.py`; "
         "file downloaded 2026-10-21 by `download_static.py` (no key). **Unverified until read.**", "",
         "## What was tested", "",
         "Every feature's `NAME` (parsed from the HTML `Description` attribute table) was classified by keyword, and the file was compared "
         "with SingStat's published yearly counts of Senior Activity Centres and Active Ageing Centres (dataset `d_0f70d7095a527be4ea443a7e30597896`).", "",
         "## Result", "",
         f"- Features: **{len(F)}**, all `Point` geometry. Valid coordinates inside a Singapore bounding box: {in_sg} of {len(F)}. "
         f"Distinct names: {len(names)}; distinct coordinate pairs: {len(xy)}.",
         f"- Attribute keys in the Description table: {', '.join(f'`{k}`' for k in prop_keys)}.",
         f"- The `FMEL_UPD_D` stamp (record update date) by year: {dict(sorted(upd.items()))}.", "",
         "Classification by name (keyword rules in the script; a heuristic, not an official category):", ""]
    L += table(["kind (by name)", "features"], sorted(kinds.items(), key=lambda kv: -kv[1]))
    L += ["", "Examples per kind (first 4):", ""]
    for k in kinds:
        L.append(f"- {k}: " + "; ".join([r["name"] for r in rows if r["kind"] == k][:4]))
    L += ["", "SingStat counts (from the CSV):", ""]
    yrs = [c for c in counts[0] if c != "DataSeries"][:5]
    L += table(["series", *yrs], [(r["DataSeries"], *[r[y] for y in yrs]) for r in counts])
    aac_name = kinds.get("Active Ageing Centre (name says so)", 0)
    sac = kinds.get("Senior Activity Centre (name or 'SAC')", 0)
    silver = kinds.get("Silver ACE (not AAC by name)", 0)
    by = {r["DataSeries"]: r for r in counts}
    aac_n = by["Number Of Active Ageing Centres"]
    sac_n = by["Number Of Senior Activity Centres"]
    L += ["", "## Reading", "",
          f"- **Verdict: {'the file names Active Ageing Centres' if aac_name else 'no feature is named an Active Ageing Centre, so by name the answer is NO and the agreed fallback applies'}.** "
          f"{silver} features are named 'Silver ACE'; whether those are Active Ageing Centres under another name is **not confirmed** (not stated in the file).",
          f"- **Active Ageing Centres by name in the file: {aac_name}.** Senior Activity Centres by name: {sac}. "
          f"SingStat reports {aac_n['2024']} Active Ageing Centres for 2024 and {sac_n['2023']} Senior Activity Centres for 2023 "
          f"(Senior Activity Centres peaked at {sac_n['2019']} in 2019). The file has {len(F)} points in total.",
          "- The file's records are stamped 2016 and the address-point coordinate fields are 0, so the file looks like an old extract of "
          "Senior Activity Centres and similar services (inference from the names and stamps, not stated by MOH).", "",
          "## Fallback (agreed 19 Oct): if the file does not include Active Ageing Centres",
          "Use the MSF Senior Activity Centre data or the Agency for Integrated Care (AIC) listing of Active Ageing Centres "
          "(https://www.aic.sg/Care-Services/Active-Ageing-Centres). Community Clubs (check on `community_clubs`) and Parks remain as refuges.", "",
          "## Could not confirm", "",
          "- Whether the AIC listing can be downloaded or only browsed, and its terms of use (not opened).",
          "- Whether the keyword classification matches MOH's own service categories.",
          "- Whether any point in this file is a closed or moved centre.", ""]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
