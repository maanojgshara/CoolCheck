"""H10 v2 parts (vi) and (vii): how much of each area the HDB blocks represent, and a cluster check on the station choice.

Run from the repo root:
    .venv\\Scripts\\python scripts/static/h10_v2_parts_vi_vii.py [--data <coolcheck-data>] [--out <md>]

Local only; no Databricks calls. Inputs: analysis/hdb_blocks_to_areas.csv (confirmed = Y blocks only, as for the reference
point), the SingStat June 2026 file (residents by planning area, MP2025 names; rounded to 10 by SingStat), the WBGT
stations at their latest locations (every station in the raw backfill, 31) and analysis/area_station_distance_v2.csv.

(vi) per area with blocks: HDB dwelling units x 2.8 (an assumed persons per dwelling unit, not a measured figure)
     against all SingStat residents and against residents aged 65+.
(vii) per area with blocks: the station (all 31) that minimises the dwelling-unit-weighted mean haversine distance from the
     area's blocks, against the nearest station to the block-mean point (the H10 v2 choice). A check only; nothing changes.
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path

from area_station_distance import BLOCKS, haversine_km, stations

REPO = Path(__file__).resolve().parents[2]
PERSONS_PER_UNIT = 2.8
AGES_65 = {"65_to_69", "70_to_74", "75_to_79", "80_to_84", "85_to_89", "90_and_Over"}


def md_table(head, rows):
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO.parent / "coolcheck-data"))
    ap.add_argument("--out", default=str(REPO / "docs" / "checks" / "h10_v2_parts_vi_vii.md"))
    a = ap.parse_args()
    data = Path(a.data)
    blocks = defaultdict(list)  # area -> [(lat, lon, units)]
    n_conf_n = 0
    with (data / BLOCKS).open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            du = int(r["total_dwelling_units"] or 0)
            if r["confirmed"] != "Y":
                n_conf_n += 1
            elif r["planning_area"] and du > 0:
                blocks[r["planning_area"]].append((float(r["lat"]), float(r["lon"]), du))
    pop, pop65 = defaultdict(int), defaultdict(int)
    sing = data / "static" / "singstat_pop_pa_age_sex_floor_area_jun2026"
    with (sing / "respopagesexfa2026.csv").open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            k = r["PA"].strip().upper()
            pop[k] += int(r["Pop"] or 0)
            if r["AG"] in AGES_65:
                pop65[k] += int(r["Pop"] or 0)
    st = stations(data / "raw")
    # nearest station to the block-mean point, as in the v2 distance table (mp2025 rows, ref_point hdb_block_mean)
    near = {}
    with (data / "analysis" / "area_station_distance_v2.csv").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["boundary"] == "mp2025" and r["ref_point"] == "hdb_block_mean":
                d = float(r["distance_km"])
                if r["planning_area"] not in near or d < near[r["planning_area"]][1]:
                    near[r["planning_area"]] = (r["station_id"], d)
    missing = sorted(k for k in blocks if k not in pop)

    six, seven = [], []
    for area in sorted(blocks):
        bl = blocks[area]
        units = sum(b[2] for b in bl)
        est = units * PERSONS_PER_UNIT
        six.append([area, len(bl), f"{units:,}", f"{est:,.0f}", f"{pop[area]:,}", f"{est / pop[area]:.0%}" if pop[area] else "n/a",
                    f"{pop65[area]:,}"])
        wmean = {sid: sum(b[2] * haversine_km(b[0], b[1], s["lat"], s["lon"]) for b in bl) / units for sid, s in st.items()}
        ranked = sorted(wmean, key=lambda k: (wmean[k], k))
        best, second = ranked[0], ranked[1]
        ns, nd = near[area]
        seven.append([area, len(bl), units, pop65[area], ns, nd, wmean[ns], best, wmean[best], second, wmean[second] - wmean[best]])

    diff = [r for r in seven if r[4] != r[7]]
    L = [
        "# H10 v2 parts (vi) and (vii): HDB share and cluster check",
        "",
        "Script: `scripts/static/h10_v2_parts_vi_vii.py`, local only (no Databricks calls). To be merged into `h10_v2.md`. "
        f"Blocks: the {sum(len(b) for b in blocks.values()):,} confirmed (confirmed = Y) blocks of `hdb_blocks_to_areas.csv` "
        f"in {len(blocks)} planning areas (the {n_conf_n} unconfirmed blocks are left out, as for the reference point). "
        "Residents: SingStat June 2026 (MP2025 areas; rounded to the nearest 10 by SingStat, so sums differ slightly). "
        f"Stations: {len(st)}, at their latest locations.",
        "",
        "## (vi) Low-HDB areas: how much of each area the HDB blocks represent",
        "",
        f"HDB residents are estimated as dwelling units x {PERSONS_PER_UNIT}. **The {PERSONS_PER_UNIT} is an assumption** (an assumed "
        "persons per dwelling unit, not a measured figure, and the real value differs by area and flat type), so the share is rough "
        "and can pass 100% where the assumption is too high or where SingStat rounds down (Bukit Merah, Tengah and Outram do here). SingStat 'residents' are citizens and "
        "permanent residents living in Singapore; the HDB units include rental and flats not occupied by residents.",
        "",
        md_table(["planning_area", "blocks", "dwelling_units", "est_HDB_residents", "SingStat_residents", "rough_HDB_share", "residents_65+"],
                 sorted(six, key=lambda r: (float(r[5].rstrip("%")) / 100 if r[5] != "n/a" else 9, r[0]))),
        "",
        "Sorted from the lowest share up. Where the share is low (Tanglin, Bukit Timah, Downtown Core), the area label represents "
        "the HDB residents, not the whole area. No rule change.",
        "",
        f"Areas with blocks but no SingStat row under the same name: {', '.join(missing) or 'none'}.",
        "",
        "## (vii) Cluster check: the station that serves the blocks best",
        "",
        "For each area with blocks, `cluster_station` is the one of all 31 stations (including the three offshore ones and stations "
        "that have stopped) with the smallest dwelling-unit-weighted mean haversine distance from the area's confirmed blocks. "
        "`mean_station` is the nearest station to the area's block-mean point, which is the H10 v2 reference point. Both are "
        "judged on the same measure, the weighted mean distance to the blocks (km). A check only; it changes nothing.",
        "",
        f"The two stations agree in **{len(seven) - len(diff)} of {len(seven)}** areas and differ in **{len(diff)}**:",
        "",
    ]
    L += [md_table(["planning_area", "blocks", "dwelling_units", "residents_65+", "mean_station", "mean_station_km_from_block_mean_point",
                    "mean_station_weighted_km", "cluster_station", "cluster_station_weighted_km", "gain_km"],
                   [[r[0], r[1], f"{r[2]:,}", f"{r[3]:,}", r[4], f"{r[5]:.2f}", f"{r[6]:.2f}", r[7], f"{r[8]:.2f}", f"{r[6] - r[8]:.2f}"]
                    for r in sorted(diff, key=lambda r: r[6] - r[8], reverse=True)])] if diff else ["None."]
    L += ["", "Areas with 65+ residents among those that differ: "
          + (", ".join(r[0] for r in diff if r[3] > 0) or "none") + ".", "",
          "Near ties: the areas where the runner-up station is within 0.5 km of the best on the same measure, so the choice is fragile "
          "even where the two methods agree.", "",
          md_table(["planning_area", "cluster_station", "weighted_km", "runner_up", "runner_up_gap_km"],
                   [[r[0], r[7], f"{r[8]:.2f}", r[9], f"{r[10]:.2f}"] for r in sorted(seven, key=lambda r: r[10]) if r[10] < 0.5]), ""]
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{len(six)} areas; stations agree {len(seven) - len(diff)}, differ {len(diff)} -> {a.out}")


if __name__ == "__main__":
    main()
