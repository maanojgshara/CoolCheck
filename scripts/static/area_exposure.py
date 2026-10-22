"""Residents, aged 65+ and aged 75+ per Master Plan 2025 planning area (senior exposure, D3), computed locally; no load.

Run from the repo root:
    .venv\\Scripts\\python scripts/static/area_exposure.py [--data <coolcheck-data>]

Input: static/singstat_pop_pa_age_sex_floor_area_jun2026/respopagesexfa2026.csv (SingStat, June 2026; planning areas are
the Master Plan 2025 areas per the file's notes). One row per subzone, age group, sex and floor-area band; Pop is rounded
to the nearest 10 in each row, so an area's figure is a sum of rounded cells.
Ages: 65+ is the age groups 65_to_69 up to 90_and_Over; 75+ is 75_to_79 up to 90_and_Over.
The 55 area names are matched, upper-cased, to PLN_AREA_N in the Master Plan 2025 boundary file; the script stops if the
two sets differ. Every boundary area gets a row, with 0 residents where the file has none. Shares are fractions of the
area's residents (blank where residents is 0).
Checks the totals against the figures in the Guide (section 14: 4,199,180 residents, 806,080 aged 65+, 310,310 aged 75+,
41 areas with any resident aged 65+); exit code 1 if any differs. The check write-up is written either way.
Writes <data>/analysis/area_exposure.csv and docs/checks/area_exposure.md.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
POP = "static/singstat_pop_pa_age_sex_floor_area_jun2026"
BOUNDARY = "static/ura_mp2025_planning_area_boundary"
AGE_GROUPS = ["0_to_4", "5_to_9", "10_to_14", "15_to_19", "20_to_24", "25_to_29", "30_to_34", "35_to_39", "40_to_44",
              "45_to_49", "50_to_54", "55_to_59", "60_to_64", "65_to_69", "70_to_74", "75_to_79", "80_to_84", "85_to_89",
              "90_and_Over"]
AGED_65 = set(AGE_GROUPS[AGE_GROUPS.index("65_to_69"):])
AGED_75 = set(AGE_GROUPS[AGE_GROUPS.index("75_to_79"):])
EXPECTED = {"residents": 4_199_180, "aged_65_plus": 806_080, "aged_75_plus": 310_310, "areas_with_65_plus": 41}
COLUMNS = ["planning_area", "planning_area_code", "region", "residents", "aged_65_plus", "aged_75_plus",
           "share_65_plus", "share_75_plus"]


def read_population(path):
    """{area name: [residents, 65+, 75+]} summed over subzone, sex and floor-area band; the subzone count and file facts."""
    acc = defaultdict(lambda: [0, 0, 0])
    seen_ag, times, subzones, rows = set(), set(), set(), 0
    with path.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            pop = int(r["Pop"])
            if pop < 0:
                raise SystemExit(f"negative Pop in row {rows + 2}")
            seen_ag.add(r["AG"])
            times.add(r["Time"])
            subzones.add((r["PA"], r["SZ"]))
            e = acc[r["PA"]]
            e[0] += pop
            if r["AG"] in AGED_65:
                e[1] += pop
            if r["AG"] in AGED_75:
                e[2] += pop
            rows += 1
    if seen_ag != set(AGE_GROUPS):
        raise SystemExit(f"age groups differ from the expected 19: {sorted(seen_ag ^ set(AGE_GROUPS))}")
    return acc, {"rows": rows, "times": sorted(times), "subzones": len(subzones)}


def boundary_areas(path):
    gj = json.loads(next(path.glob("*.geojson")).read_text(encoding="utf-8"))
    return {f["properties"]["PLN_AREA_N"]: (f["properties"]["PLN_AREA_C"], f["properties"]["REGION_N"])
            for f in gj["features"]}


def share(n, d):
    return round(n / d, 6) if d else ""


def md_table(header, rows):
    return ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"] + \
           ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO.parent / "coolcheck-data"))
    ap.add_argument("--out", help="default <data>/analysis/area_exposure.csv")
    args = ap.parse_args()
    data = Path(args.data)
    out = Path(args.out) if args.out else data / "analysis/area_exposure.csv"

    pop, facts = read_population(data / POP / "respopagesexfa2026.csv")
    areas = boundary_areas(data / BOUNDARY)
    by_upper = {name.upper(): vals for name, vals in pop.items()}
    if len(by_upper) != len(pop):
        raise SystemExit("two population area names are equal once upper-cased")
    only_pop, only_map = sorted(set(by_upper) - set(areas)), sorted(set(areas) - set(by_upper))
    if only_pop or only_map:
        raise SystemExit(f"area names differ: only in the population file {only_pop}; only in the boundary file {only_map}")

    rows = []
    for name in sorted(areas):
        n, a65, a75 = by_upper[name]
        code, region = areas[name]
        rows.append({"planning_area": name, "planning_area_code": code, "region": region, "residents": n,
                     "aged_65_plus": a65, "aged_75_plus": a75, "share_65_plus": share(a65, n), "share_75_plus": share(a75, n)})
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

    got = {"residents": sum(r["residents"] for r in rows), "aged_65_plus": sum(r["aged_65_plus"] for r in rows),
           "aged_75_plus": sum(r["aged_75_plus"] for r in rows),
           "areas_with_65_plus": sum(1 for r in rows if r["aged_65_plus"] > 0)}
    ok = got == EXPECTED
    empty = [r["planning_area"] for r in rows if r["residents"] == 0]
    no_senior = [r["planning_area"] for r in rows if r["residents"] > 0 and r["aged_65_plus"] == 0]
    with_res = [r for r in rows if r["residents"] > 0]

    prov = json.loads((data / POP / "provenance.json").read_text(encoding="utf-8"))
    lines = [
        "# area_exposure: residents, aged 65+ and aged 75+ per Master Plan 2025 planning area", "",
        f"Script: `scripts/static/area_exposure.py`. Input: `{POP}/respopagesexfa2026.csv` (SingStat, reference period "
        f"{', '.join(facts['times'])}; downloaded {prov['downloaded']}). Output: `coolcheck-data/analysis/area_exposure.csv` "
        "(outside the repo). Nothing was loaded to Databricks and no network call was made.", "",
        "## Method", "",
        f"- {facts['rows']:,} rows (subzone x age group x sex x floor-area band), {facts['subzones']} subzones, "
        f"{len(pop)} planning areas. Each `Pop` cell is rounded to the nearest 10 by SingStat, so an area's figure is a sum of "
        "rounded cells and the file's own note says it may not add up.",
        "- 65+ = age groups 65_to_69 to 90_and_Over (5 groups plus 90_and_Over); 75+ = 75_to_79 to 90_and_Over. The 19 age "
        "groups in the file are exactly the 19 expected.",
        "- The area names, upper-cased, equal the 55 `PLN_AREA_N` values of the Master Plan 2025 boundary file "
        "(`ura_mp2025_planning_area_boundary`); no name is in one file only. Every boundary area has a row.",
        "- Shares are the fraction of the area's residents (not of Singapore's 65+); blank where the area has no residents.", "",
        "## Totals against the Guide", "",
        *md_table(["figure", "Guide", "this run", "same"],
                  [[k.replace("_", " "), f"{EXPECTED[k]:,}", f"{got[k]:,}", "yes" if got[k] == EXPECTED[k] else "**NO**"]
                   for k in EXPECTED]), "",
        ("All four match." if ok else "**At least one figure differs from the Guide; the Guide's figure was not changed.**"), "",
        f"Areas with no residents ({len(empty)}): {', '.join(empty) or 'none'}.", "",
        f"Areas with residents but none aged 65+ ({len(no_senior)}): {', '.join(no_senior) or 'none'}.", "",
        "## Ten areas with the most residents aged 65+", "",
        *md_table(["planning area", "residents", "65+", "75+", "65+ share", "75+ share"],
                  [[r["planning_area"], f"{r['residents']:,}", f"{r['aged_65_plus']:,}", f"{r['aged_75_plus']:,}",
                    f"{r['share_65_plus']:.1%}", f"{r['share_75_plus']:.1%}"]
                   for r in sorted(rows, key=lambda r: -r["aged_65_plus"])[:10]]), "",
        "## Ten areas with the highest 65+ share (areas with at least 1,000 residents)", "",
        *md_table(["planning area", "residents", "65+", "65+ share", "75+ share"],
                  [[r["planning_area"], f"{r['residents']:,}", f"{r['aged_65_plus']:,}", f"{r['share_65_plus']:.1%}",
                    f"{r['share_75_plus']:.1%}"]
                   for r in sorted((r for r in with_res if r["residents"] >= 1000), key=lambda r: -r["share_65_plus"])[:10]]), "",
        "Small areas give noisy shares because every cell is rounded to 10; that is why the second table starts at 1,000 "
        "residents. The CSV keeps every area.", "",
    ]
    (REPO / "docs/checks/area_exposure.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({len(rows)} areas) and docs/checks/area_exposure.md")
    for k in EXPECTED:
        print(f"  {k}: Guide {EXPECTED[k]:,}, this run {got[k]:,} {'same' if got[k] == EXPECTED[k] else 'DIFFERENT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
