"""Create the risk score's three views in <catalog>.gold through Databricks Connect (docs/design/risk_score.md §9).

Run from the repo root; it creates views, so only after the user's OK:
    .venv\\Scripts\\python scripts/static/create_risk_views.py [--catalog coolcheck] [--profile coolcheck]
        [--views area_vulnerability block_vulnerability area_heat_risk] [--matrix main|variant] [--print-sql]

gold.area_vulnerability over silver.area_exposure, silver.area_access, silver.block_access, silver.ema_area_electricity
and gold.score_weights; gold.block_vulnerability over silver.block_access and gold.area_vulnerability;
gold.area_heat_risk over window B's gold.heat_forecast (created only if that table exists), gold.area_vulnerability,
silver.area_exposure and gold.tier_actions. The SQL is coolcheck.risk's, the same the tests compare with the Python rules.
--matrix picks the tier matrix (decision 9(f): main, or the variant where Moderate heat in a middle-third area gives Low).
Each view gets column comments, a comment and source and licence tags. Read-back: the rows of area_vulnerability (32)
and block_vulnerability (10,817); for area_heat_risk only rows with target_date after 2026-10-19, so nothing from the
final check's window (1 Sep to 19 Oct 2026) is read. --print-sql prints the statements and touches nothing.
"""
import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from coolcheck import risk as R  # noqa: E402

LICENCE = "Singapore Open Data Licence v1.0 (source data); CoolCheck weights and actions"
EXPECT = {"area_vulnerability": 32, "block_vulnerability": 10_817}


def lit(s):
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def views(cat, matrix):
    s, g = f"{cat}.silver", f"{cat}.gold"
    return {
        "area_vulnerability": {
            "sql": R.area_vulnerability_sql(f"{s}.area_exposure", f"{s}.area_access", f"{s}.block_access",
                                            f"{s}.ema_area_electricity", f"{g}.score_weights"),
            "columns": R.VULN_COLUMNS,
            "comment": "Vulnerability index V of the 32 rated planning areas (Guide §A11 decision 9, small-area rule 9(g); "
                       "docs/design/risk_score.md): seven component percentiles, V, its rank, the third, a plain reason and "
                       "the flags. Weights from gold.score_weights (a judgement, not yet reviewed by a practitioner).",
            "tags": {"source": "SingStat June 2026; HDB Property Information; OneMap geocodes; PA, MOH, NParks and URA layers; "
                               "EMA SES 2025 T3.5; gold.score_weights", "licence": LICENCE}},
        "block_vulnerability": {
            "sql": R.block_vulnerability_sql(f"{s}.block_access", f"{g}.area_vulnerability"),
            "columns": R.BLOCK_COLUMNS,
            "comment": "Every HDB block in a rated area with its 1-2 room rental flats, nearest refuge and park, the 400 m "
                       "flags and its priority within the area (rental flats, most first; then distance to the nearest refuge, "
                       "farthest first). Blocks rank vulnerability only, never heat. No personal data.",
            "tags": {"source": "HDB Property Information; OneMap geocodes; silver.block_access", "licence": LICENCE}},
        "area_heat_risk": {
            "sql": R.area_heat_risk_sql(f"{g}.heat_forecast", f"{g}.area_vulnerability", f"{s}.area_exposure",
                                        f"{g}.tier_actions", matrix=matrix),
            "columns": R.RISK_COLUMNS,
            "comment": "Tomorrow's heat level and tier per planning area and target date (decisions 7, 8(d) and 9): the 3x3 "
                       "rule of heat level and vulnerability third, the order within the tier, the reason and the actions. "
                       "P(High) and the score stay in gold.heat_forecast and are never shown here. Actions are a proposal, "
                       "not yet reviewed by a practitioner.",
            "tags": {"source": "gold.heat_forecast (window B); gold.area_vulnerability; gold.tier_actions", "licence": LICENCE}},
    }


def create_sql(name, cat, spec):
    cols = ",\n  ".join(f"`{c}` COMMENT {lit(cm)}" for c, cm in spec["columns"])
    return f"CREATE OR REPLACE VIEW {cat}.gold.{name} (\n  {cols}\n) COMMENT {lit(spec['comment'])} AS {spec['sql']}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="coolcheck")
    ap.add_argument("--profile", default="coolcheck")
    ap.add_argument("--views", nargs="+", choices=list(EXPECT) + ["area_heat_risk"],
                    default=["area_vulnerability", "block_vulnerability", "area_heat_risk"])
    ap.add_argument("--matrix", choices=["main", "variant"], default="main")
    ap.add_argument("--print-sql", action="store_true", help="print the statements and touch nothing")
    a = ap.parse_args()
    if not re.fullmatch(r"\w+", a.catalog):
        raise SystemExit(f"bad catalog name: {a.catalog!r}")
    specs = views(a.catalog, R.TIER_MAIN if a.matrix == "main" else R.TIER_VARIANT)
    if a.print_sql:
        for name in a.views:
            print(create_sql(name, a.catalog, specs[name]), end=";\n\n")
        return

    from databricks.connect import DatabricksSession

    spark = DatabricksSession.builder.serverless().profile(a.profile).getOrCreate()
    for name in a.views:
        if name == "area_heat_risk" and not spark.catalog.tableExists(f"{a.catalog}.gold.heat_forecast"):
            print(f"{a.catalog}.gold.heat_forecast does not exist yet (window B's table): area_heat_risk not created")
            continue
        v = f"{a.catalog}.gold.{name}"
        spark.sql(create_sql(name, a.catalog, specs[name]))
        tags = ", ".join(f"{lit(k)} = {lit(x)}" for k, x in specs[name]["tags"].items())
        spark.sql(f"ALTER VIEW {v} SET TAGS ({tags})")
        bare = [r["col_name"] for r in spark.sql(f"DESCRIBE TABLE {v}").collect()
                if r["col_name"] and not r["col_name"].startswith("#") and not r["comment"]]
        if name in EXPECT:
            n = spark.table(v).count()
            print(f"{v}: {n:,} rows (expected {EXPECT[name]:,}), columns without a comment: {bare or 'none'}")
            if n != EXPECT[name] or bare:
                raise SystemExit(f"STOP: {v} does not read back as expected")
        else:
            n = spark.sql(f"SELECT count(*) AS n FROM {v} WHERE target_date > DATE'2026-10-19'").first()["n"]
            print(f"{v}: {n:,} rows with target_date after 2026-10-19, columns without a comment: {bare or 'none'}")
            if bare:
                raise SystemExit(f"STOP: {v} has columns without a comment")


if __name__ == "__main__":
    main()
