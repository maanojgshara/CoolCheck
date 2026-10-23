"""The electricity term of the can't-cool-down index, from EMA table T3.5 (docs/design/risk_score.md §8); local, no load.

Run from the repo root:
    .venv\\Scripts\\python scripts/static/ema_electricity.py [--data <coolcheck-data>] [--workbook <SES_tidy.xlsx>]

Input: ../Docs/EMA/SES_tidy.xlsx.coredownload.xlsx, sheet T3.5 (Average Monthly Household Electricity Consumption by
Planning Area & Dwelling Type), the 1-room / 2-room rows only; the Master Plan 2025 boundary for the area names; and
analysis/area_access.csv for the 32 rated areas (at least one confirmed HDB block). Ratios as in
src/coolcheck/electricity.py. Also reproduces the first reading: the mean over area-years of each year's ratio, 2015 to
2024, with the number of area-years, beside EMA's "Overall" row pooled over the same years.
Writes <data>/analysis/ema_area_electricity.csv, <data>/analysis/ema_electricity_run.json (parameters, metrics and
artifacts for scripts/analysis/log_risk_runs.py) and docs/checks/ema_electricity.md.
"""
import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from coolcheck import electricity as E  # noqa: E402

SHEET = "T3.5"
DWELLING = "1-room / 2-room"
BOUNDARY = "static/ura_mp2025_planning_area_boundary"
ACCESS = "analysis/area_access.csv"
NOTICE = ("Contains information from Singapore Energy Statistics 2025, Chapter 3: Energy Consumption accessed on 21 October "
          "2026 from Energy Market Authority which is made available under the terms of the Singapore Open Data Licence "
          "version 1.0 https://data.gov.sg/open-data-licence.")
FOOTNOTES = [
    "Numbers may not add up because of rounding (a).",
    "Planning areas follow the Singapore Land Authority's Aggregated Data Zone 2024 (b).",
    "A missing or zero value can be nil, negligible or not applicable (c, d); \"s\" means suppressed.",
    "Solar PV statistics are excluded (e).",
    "\"Data for 2025 is at Jun 2025.\" (the sheet's last line); \"The information published in SES 2025 is accurate as of "
    "Sep 2025.\" (the workbook's contents page); \"Source: Energy Market Authority (EMA)\".",
]
COLUMNS = ["planning_area", "ema_name", "ema_region", "ratio_2022", "ratio_2023", "ratio_2024", "years_2022_2024",
           "hot_ratio_mean", "mean_ratio_2015_2024", "years_2015_2024"]
MARK = ("<!-- mlflow -->", "<!-- /mlflow -->")


def read_t35(path):
    """{description: {(year, month): kWh}} and {description: region} for the 1-room / 2-room monthly rows."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = wb[SHEET].iter_rows(values_only=True)
    header = next(rows)
    if list(header[:6]) != ["Dwelling Type", "Year", "Month", "Region", "Description", "Kwh Per Acc"]:
        raise SystemExit(f"unexpected T3.5 header: {header}")
    monthly, region, seen = defaultdict(dict), {}, 0
    for r in rows:
        if r[0] != DWELLING or not isinstance(r[1], int) or not isinstance(r[2], int):
            continue
        key = (r[1], r[2])
        if key in monthly[r[4]]:
            raise SystemExit(f"duplicate T3.5 row: {r[4]} {key}")
        if not isinstance(r[5], (int, float)):
            raise SystemExit(f"non-numeric T3.5 value: {r}")
        monthly[r[4]][key] = float(r[5])
        region[r[4]] = r[3]
        seen += 1
    return monthly, region, seen


def md_table(header, rows):
    return ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"] + \
           ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


def fmt(v, nd=4):
    return "" if v is None else f"{v:.{nd}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO.parent / "coolcheck-data"))
    ap.add_argument("--workbook", default=str(REPO.parent / "Docs/EMA/SES_tidy.xlsx.coredownload.xlsx"))
    a = ap.parse_args()
    data, wbp = Path(a.data), Path(a.workbook)
    sha = hashlib.sha256(wbp.read_bytes()).hexdigest()
    monthly, region, nrows = read_t35(wbp)
    regions = {v for v in region.values()}
    areas = sorted(d for d in monthly if d not in regions and d != "Overall")
    gj = json.loads(next((data / BOUNDARY).glob("*.geojson")).read_text(encoding="utf-8"))
    mp2025 = {f["properties"]["PLN_AREA_N"] for f in gj["features"]}
    with (data / ACCESS).open(encoding="utf-8", newline="") as fh:
        rated = sorted(r["planning_area"] for r in csv.DictReader(fh)
                       if r["measure"] == "refuge" and r["layer_set"] == "main" and int(r["hdb_blocks_confirmed"]) > 0)
    unmatched = [d for d in areas if d.upper() not in mp2025]

    rows, by_area = [], {}
    for d in areas:
        rv = E.ratios(monthly[d], E.VALUE_YEARS)
        r15 = E.ratios(monthly[d], E.FIRST_READING_YEARS)
        by_area[d] = r15
        m15 = (sum(r15.values()) / len(r15)) if r15 else None
        hm = E.three_year_mean(rv)
        rows.append({"planning_area": d.upper(), "ema_name": d, "ema_region": region[d],
                     **{f"ratio_{y}": (round(rv[y], 6) if y in rv else None) for y in E.VALUE_YEARS},
                     "years_2022_2024": len(rv), "hot_ratio_mean": None if hm is None else round(hm, 6),
                     "mean_ratio_2015_2024": None if m15 is None else round(m15, 6), "years_2015_2024": len(r15)})
    first_mean, first_n = E.mean_over_area_years(by_area)
    overall_pooled = E.pooled_ratio(monthly["Overall"])
    overall_years = E.ratios(monthly["Overall"], E.FIRST_READING_YEARS)
    overall_mean = sum(overall_years.values()) / len(overall_years)
    partial = [(d, len(r15), sum(r15.values()) / len(r15)) for d, r15 in sorted(by_area.items())
               if 0 < len(r15) < len(E.FIRST_READING_YEARS)]
    have = {r["planning_area"]: r for r in rows}
    rated_named = [x for x in rated if x in have]
    rated_value = [x for x in rated if x in have and have[x]["hot_ratio_mean"] is not None]
    rated_missing = [x for x in rated if x not in rated_value]
    years_seen = sorted({y for d in monthly.values() for y, _ in d})

    out = data / "analysis" / "ema_area_electricity.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        w.writerows([["" if r[c] is None else r[c] for c in COLUMNS] for r in rows])

    L = ["# EMA electricity: the hot-month rise in 1–2 room flats", "",
         "Script: `scripts/static/ema_electricity.py`; ratios: `src/coolcheck/electricity.py`. Output: "
         "`coolcheck-data/analysis/ema_area_electricity.csv` (outside the repo). Nothing was loaded to Unity Catalog.", "",
         MARK[0], "MLflow: not logged yet.", MARK[1], "",
         f"Source: `SES_tidy.xlsx.coredownload.xlsx` (EMA, Singapore Energy Statistics 2025; sha256 `{sha[:12]}...`), sheet {SHEET}, "
         f"\"Average Monthly Household Electricity Consumption by Planning Area & Dwelling Type\": {nrows:,} monthly "
         f"{DWELLING} rows, {years_seen[0]} to {years_seen[-1]}, for {len(areas)} planning areas, 5 regions and \"Overall\". "
         "`Annual` rows are ignored.", "",
         "## Result", "",
         f"- **The first reading, reproduced:** the mean over area-years of each year's April–June / November–February ratio, "
         f"1–2 room, 2015 to 2024: **{first_mean:.4f} over {first_n} area-years** (the first reading was 1.09 over 280). "
         f"EMA's \"Overall\" row: pooled over the same years {overall_pooled:.4f}; the mean of its {len(overall_years)} yearly "
         f"ratios {overall_mean:.4f}. At two decimals the area-year mean is {first_mean:.2f} (a rise of about "
         f"{round(100 * (first_mean - 1))}%) and \"Overall\" pooled {overall_pooled:.2f} (about {round(100 * (overall_pooled - 1))}%). "
         "The area-years include areas with fewer than ten years: "
         + "; ".join(f"{d} {n} year{'s' if n > 1 else ''} (mean {m:.4f})" for d, n, m in partial) + ".",
         f"- **Coverage among the 32 rated areas:** {len(rated_named)} have {DWELLING} rows by name; **{len(rated_value)} have all "
         f"three of 2022, 2023 and 2024**, so the term has a value; {len(rated_missing)} do not and get 0.5 in V: "
         f"{', '.join(rated_missing) or 'none'}.",
         f"- **Names:** {len(areas)} EMA planning-area names, upper-cased, against Master Plan 2025 `PLN_AREA_N`: "
         f"{'all match' if not unmatched else 'not matched: ' + ', '.join(unmatched)}. EMA's areas follow the Singapore Land "
         "Authority's Aggregated Data Zone 2024, not URA's Master Plan 2025, so a boundary can differ slightly.",
         "- **Reading:** a ratio above 1 means more electricity per account in April to June than in November to February. "
         "A smaller rise \"may indicate\" less air-con use in the hot months; it does not show it, and it says nothing about "
         "any one household.", "",
         "## Per area (1–2 room)", ""]
    L += md_table(["planning area", "region", "2022", "2023", "2024", "mean 2022–2024 (V input)", "mean 2015–2024", "years 2015–2024", "rated"],
                  [[r["planning_area"], r["ema_region"], fmt(r["ratio_2022"]), fmt(r["ratio_2023"]), fmt(r["ratio_2024"]),
                    fmt(r["hot_ratio_mean"]), fmt(r["mean_ratio_2015_2024"]), r["years_2015_2024"],
                    "yes" if r["planning_area"] in rated else "no"] for r in rows])
    L += ["", "## Method", "",
          "- A year's ratio is mean(Apr, May, Jun of Y) / mean(Nov and Dec of Y − 1, Jan and Feb of Y), and needs all seven months.",
          "- An area's value (the V input, `hot_ratio_mean`) is the mean of its 2022, 2023 and 2024 ratios when all three exist; "
          "otherwise it has none, and V holds the component at 0.5.",
          "- The first reading: every area-year ratio of 2015 to 2024 that exists (planning areas only, not regions or "
          "\"Overall\"), averaged with equal weight.",
          "- \"Overall\" pooled: the mean of all its April to June values over 2015 to 2024 over the mean of all its "
          "November-to-February values (Nov 2014 to Feb 2024).", "",
          "## EMA's notes, to quote with any figure", ""]
    L += [f"- {x}" for x in FOOTNOTES]
    L += ["", "## Attribution (EMA's terms, clause 9: the notice carries the date of access)", "", f"> {NOTICE}", "",
          "EMA is named without a hyperlink to its site, and EMA's own charts are not shown (website terms, clause 6).", ""]
    (REPO / "docs/checks/ema_electricity.md").write_text("\n".join(L), encoding="utf-8")

    run = {"run_name": "electricity", "role": "electricity",
           "params": {"workbook": wbp.name, "workbook_sha256": sha, "sheet": SHEET, "dwelling_type": DWELLING,
                      "value_years": "2022,2023,2024", "first_reading_years": "2015-2024",
                      "ratio": "mean(Apr,May,Jun of Y) / mean(Nov,Dec of Y-1, Jan,Feb of Y); all seven months required",
                      "date_of_access": "2026-10-21"},
           "metrics": {"first_reading_mean_ratio": first_mean, "first_reading_area_years": first_n,
                       "overall_pooled_ratio_2015_2024": overall_pooled, "overall_mean_yearly_ratio_2015_2024": overall_mean,
                       "ema_planning_areas": len(areas), "rated_areas_named": len(rated_named),
                       "rated_areas_with_value": len(rated_value), "names_unmatched": len(unmatched)},
           "artifacts": [str(out), str(REPO / "docs/checks/ema_electricity.md")],
           "report": str(REPO / "docs/checks/ema_electricity.md"),
           "code_files": ["src/coolcheck/electricity.py", "scripts/static/ema_electricity.py"]}
    (data / "analysis" / "ema_electricity_run.json").write_text(json.dumps(run, indent=1), encoding="utf-8")
    print(f"{len(areas)} EMA areas; rated with a value {len(rated_value)} of 32 (missing: {', '.join(rated_missing)}); "
          f"names unmatched {len(unmatched)}")
    print(f"first reading: {first_mean:.4f} over {first_n} area-years; Overall pooled {overall_pooled:.4f}, "
          f"mean of yearly {overall_mean:.4f}")
    print(f"wrote {out} and docs/checks/ema_electricity.md")


if __name__ == "__main__":
    main()
