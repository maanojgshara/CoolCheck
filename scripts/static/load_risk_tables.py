"""Load the risk score's two reference tables and the EMA electricity table through Databricks Connect, replacing each,
with table and column comments and source and licence tags (docs/design/risk_score.md §8, §9).

Run from the repo root; it writes tables, so only after the user's OK:
    .venv\\Scripts\\python scripts/static/load_risk_tables.py [--data <coolcheck-data>] [--catalog coolcheck]
        [--profile coolcheck] [--tables score_weights tier_actions ema_area_electricity] [--check-only]

Tables: <catalog>.gold.score_weights (reference/score_weights.csv), <catalog>.gold.tier_actions
(reference/tier_actions.csv) and <catalog>.silver.ema_area_electricity (analysis/ema_area_electricity.csv, written by
scripts/static/ema_electricity.py). Before writing it checks, and stops if one fails: the weights pass
coolcheck.risk.check_weights (the seven components, valid directions and small-area rules, summing to 1); the four tiers;
30 EMA areas, all Master Plan 2025 names. --check-only runs the checks and writes nothing. The write and the read-back
are those of load_refuge_park_access.write_table.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from coolcheck import risk as R  # noqa: E402
from load_refuge_park_access import read, write_table  # noqa: E402

LICENCE = "Singapore Open Data Licence v1.0"
OWN = "CoolCheck project reference data (no third-party data)"
REVIEW = "judgement (Guide decision 9), not yet reviewed by a practitioner"
NOTICE = ("Contains information from Singapore Energy Statistics 2025, Chapter 3: Energy Consumption accessed on 21 October "
          "2026 from Energy Market Authority which is made available under the terms of the Singapore Open Data Licence "
          "version 1.0 https://data.gov.sg/open-data-licence.")
TIERS = {"High", "Medium", "Low", "Not rated"}
EMA_AREAS = 30

TABLES = {
    "score_weights": {
        "schema": "gold", "file": "reference/score_weights.csv", "in_repo": True,
        "tags": {"source": "CoolCheck design, Guide decision 9 and 9(g); reference/score_weights.csv", "licence": OWN},
        "columns": [
            ("component", "STRING", "Component key of the vulnerability index V (one row each, seven in all)."),
            ("sort_order", "INT", "Display order; also the tie-break between equal contributions in the reason."),
            ("sub_index", "STRING", "senior_exposure (0.35), cant_cool_down (0.30) or cooling_access_gap (0.35)."),
            ("weight", "DOUBLE", "Weight in V; the weights sum to 1. A judgement, not fitted (no open outcome data)."),
            ("direction", "STRING", "higher: a larger value is more vulnerable; inverted: a smaller value is."),
            ("source_column", "STRING", "Where the raw value comes from."),
            ("small_area_rule", "STRING", "Decision 9(g): hdb_du (fewer than small_area_min confirmed HDB dwelling units), residents, aged_65 (residents aged 65+), or none; the component is then held at 0.5."),
            ("small_area_min", "INT", "Threshold of the small-area rule (1,000); null when the rule is none."),
            ("reason_phrase", "STRING", "Plain words for the component when it is one of an area's two largest contributors."),
            ("review_status", "STRING", "Review status of the weights."),
        ]},
    "tier_actions": {
        "schema": "gold", "file": "reference/tier_actions.csv", "in_repo": True,
        "tags": {"source": "CoolCheck design, Guide §14.1 and decision 9; reference/tier_actions.csv", "licence": OWN},
        "columns": [
            ("tier", "STRING", "High, Medium, Low or Not rated."),
            ("actions", "STRING", "What the tier asks of the care team; CoolCheck supplies areas, blocks and counts, the AACs' own client lists supply the people."),
            ("review_status", "STRING", "A proposal, not yet reviewed by a practitioner."),
            ("source", "STRING", "Where the actions are written down."),
        ]},
    "ema_area_electricity": {
        "schema": "silver", "file": "analysis/ema_area_electricity.csv", "in_repo": False,
        "tags": {"source": "EMA Singapore Energy Statistics 2025, Chapter 3, table T3.5 (SES_tidy.xlsx)", "licence": LICENCE,
                 "date_of_access": "2026-10-21"},
        "columns": [
            ("planning_area", "STRING", "Master Plan 2025 planning area (EMA's name upper-cased; all match)."),
            ("ema_name", "STRING", "EMA's planning-area name (Aggregated Data Zone 2024)."),
            ("ema_region", "STRING", "EMA's region."),
            ("ratio_2022", "DOUBLE", "1-room / 2-room kWh per account: mean(Apr, May, Jun 2022) / mean(Nov, Dec 2021, Jan, Feb 2022); null unless all seven months exist."),
            ("ratio_2023", "DOUBLE", "The same for 2023."),
            ("ratio_2024", "DOUBLE", "The same for 2024."),
            ("years_2022_2024", "INT", "How many of 2022 to 2024 have a ratio."),
            ("hot_ratio_mean", "DOUBLE", "Mean of the 2022 to 2024 ratios when all three exist, else null: the V input (inverted; a smaller rise may indicate less air-con use, never more)."),
            ("mean_ratio_2015_2024", "DOUBLE", "Mean of the area's yearly ratios over 2015 to 2024 (the years that exist)."),
            ("years_2015_2024", "INT", "How many of 2015 to 2024 have a ratio."),
        ]},
}


def table_comment(name, path, sha):
    if name == "score_weights":
        return ("Weights of the vulnerability index V (Guide §A11 decision 9; small-area rule 9(g)), read by "
                f"gold.area_vulnerability: component, weight, direction, small-area rule and reason phrase. {REVIEW}. "
                f"Loaded by scripts/static/load_risk_tables.py from reference/score_weights.csv, sha256 {sha}.")
    if name == "tier_actions":
        return ("Actions per tier (Guide §14.1, decision 9), read by gold.area_heat_risk; a proposal, not yet reviewed by a "
                "practitioner. No personal data: the AACs' own client lists supply the people. Loaded by "
                f"scripts/static/load_risk_tables.py from reference/tier_actions.csv, sha256 {sha}.")
    wb = REPO.parent / "Docs/EMA/SES_tidy.xlsx.coredownload.xlsx"
    wsha = hashlib.sha256(wb.read_bytes()).hexdigest() if wb.exists() else "not checked"
    return ("Hot-month rise in 1-room / 2-room household electricity use per planning area, the secondary term of the "
            "can't-cool-down index (docs/design/risk_score.md §8; docs/checks/ema_electricity.md). A smaller rise may "
            "indicate less air-con use, never more. From EMA Singapore Energy Statistics 2025, table T3.5 (SES_tidy.xlsx, "
            f"sha256 {wsha}). {NOTICE} EMA's notes: numbers may not add up because of rounding; planning areas follow the "
            "Singapore Land Authority's Aggregated Data Zone 2024; a missing or zero value can be nil, negligible or not "
            "applicable; s means suppressed; solar PV is excluded; data for 2025 is at Jun 2025; accurate as of Sep 2025. "
            f"Loaded by scripts/static/load_risk_tables.py from ema_area_electricity.csv, sha256 {sha}.")


def path_of(name, data):
    spec = TABLES[name]
    return (REPO if spec["in_repo"] else data) / spec["file"]


def check(data):
    out = {}
    for name, spec in TABLES.items():
        path = path_of(name, data)
        out[name] = (read(path, spec["columns"]), hashlib.sha256(path.read_bytes()).hexdigest())
    cols = [c for c, _, _ in TABLES["score_weights"]["columns"]]
    R.check_weights([dict(zip(cols, r)) for r in out["score_weights"][0]])
    print(f"score_weights: {len(out['score_weights'][0])} components, sum "
          f"{sum(r[cols.index('weight')] for r in out['score_weights'][0]):.2f} ok")
    tiers = {r[0] for r in out["tier_actions"][0]}
    if tiers != TIERS or len(out["tier_actions"][0]) != len(TIERS):
        raise SystemExit(f"STOP: tiers {sorted(tiers)} differ from {sorted(TIERS)}")
    print(f"tier_actions: {len(tiers)} tiers ok")
    gj = json.loads(next((data / "static/ura_mp2025_planning_area_boundary").glob("*.geojson")).read_text(encoding="utf-8"))
    names = {f["properties"]["PLN_AREA_N"] for f in gj["features"]}
    ema = out["ema_area_electricity"][0]
    bad = [r[0] for r in ema if r[0] not in names]
    if len(ema) != EMA_AREAS or bad:
        raise SystemExit(f"STOP: {len(ema)} EMA rows (expected {EMA_AREAS}); not Master Plan 2025 names: {bad}")
    print(f"ema_area_electricity: {len(ema)} areas, all Master Plan 2025 names ok")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO.parent / "coolcheck-data"))
    ap.add_argument("--catalog", default="coolcheck")
    ap.add_argument("--profile", default="coolcheck")
    ap.add_argument("--tables", nargs="+", choices=list(TABLES), default=list(TABLES), help="load only these tables")
    ap.add_argument("--check-only", action="store_true", help="run the checks and write nothing")
    a = ap.parse_args()
    if not re.fullmatch(r"\w+", a.catalog):
        raise SystemExit(f"bad catalog name: {a.catalog!r}")
    data = Path(a.data)
    files = check(data)
    for name, (_, sha) in files.items():
        print(f"{name} sha256 {sha}")
    if a.check_only:
        print("check only: nothing written")
        return

    from databricks.connect import DatabricksSession

    spark = DatabricksSession.builder.serverless().profile(a.profile).getOrCreate()
    for name in a.tables:
        rows, sha = files[name]
        spec = TABLES[name]
        write_table(spark, f"{a.catalog}.{spec['schema']}.{name}", spec["columns"], rows,
                    table_comment(name, path_of(name, data), sha), spec["tags"])


if __name__ == "__main__":
    main()
