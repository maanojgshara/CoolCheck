"""Load coolcheck-data/analysis/area_exposure.csv (written by scripts/static/area_exposure.py) into
coolcheck.silver.area_exposure through Databricks Connect, overwriting it. Decision 1 of docs/design/backtest.md: the
back-test reads the 41 planning areas with residents aged 65+ from this table, by Delta version.

Run from the repo root; it writes a table, so only after the user's OK:
    .venv\\Scripts\\python scripts/static/load_area_exposure.py [--data <coolcheck-data>] [--check-only]

Before writing it checks, and stops if one fails: the eight columns in order, 55 distinct planning areas, and the
Guide's totals (4,199,180 residents, 806,080 aged 65+, 310,310 aged 75+, 41 areas with any resident aged 65+).
--check-only runs the checks and writes nothing. After the write it prints the row count and the Delta version.
"""
import argparse
import csv
import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TABLE = "coolcheck.silver.area_exposure"
COLUMNS = ["planning_area", "planning_area_code", "region", "residents", "aged_65_plus", "aged_75_plus",
           "share_65_plus", "share_75_plus"]
SCHEMA = ("planning_area STRING, planning_area_code STRING, region STRING, residents BIGINT, aged_65_plus BIGINT, "
          "aged_75_plus BIGINT, share_65_plus DOUBLE, share_75_plus DOUBLE")
EXPECTED = {"areas": 55, "residents": 4_199_180, "aged_65_plus": 806_080, "aged_75_plus": 310_310,
            "areas_with_65_plus": 41}


def read_rows(path):
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != COLUMNS:
            raise SystemExit(f"columns {reader.fieldnames} differ from the expected {COLUMNS}")
        rows = [(r["planning_area"], r["planning_area_code"], r["region"], int(r["residents"]), int(r["aged_65_plus"]),
                 int(r["aged_75_plus"]), float(r["share_65_plus"]) if r["share_65_plus"] else None,
                 float(r["share_75_plus"]) if r["share_75_plus"] else None) for r in reader]
    return rows


def check(rows):
    got = {"areas": len({r[0] for r in rows}), "residents": sum(r[3] for r in rows),
           "aged_65_plus": sum(r[4] for r in rows), "aged_75_plus": sum(r[5] for r in rows),
           "areas_with_65_plus": sum(1 for r in rows if r[4] > 0)}
    if len(rows) != got["areas"]:
        raise SystemExit("a planning area appears more than once")
    for k, v in EXPECTED.items():
        print(f"{k}: {got[k]:,} (expected {v:,}) {'ok' if got[k] == v else 'DIFFERS'}")
    if got != EXPECTED:
        raise SystemExit("STOP: the file differs from the expected figures; nothing written")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO.parent / "coolcheck-data"))
    ap.add_argument("--profile", default="coolcheck")
    ap.add_argument("--check-only", action="store_true", help="run the checks and write nothing")
    a = ap.parse_args()
    path = Path(a.data) / "analysis" / "area_exposure.csv"
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    rows = read_rows(path)
    print(f"{path}: {len(rows)} rows, sha256 {sha}")
    check(rows)
    if a.check_only:
        print("check only: nothing written")
        return

    from databricks.connect import DatabricksSession

    spark = DatabricksSession.builder.serverless().profile(a.profile).getOrCreate()
    spark.createDataFrame(rows, SCHEMA).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(TABLE)
    comment = ("Residents, aged 65+ and aged 75+ per Master Plan 2025 planning area (55 areas; 41 with residents aged "
               "65+), from the SingStat file respopagesexfa2026.csv (reference period June 2026, downloaded 2026-10-21; "
               "Singapore Department of Statistics, Singapore Open Data Licence v1.0) via scripts/static/area_exposure.py. "
               "Each SingStat cell is rounded to 10, so an area is a sum of rounded cells; shares are blank where an area "
               f"has no residents. Loaded by scripts/static/load_area_exposure.py from area_exposure.csv, sha256 {sha}.")
    spark.sql(f"COMMENT ON TABLE {TABLE} IS '{comment.replace(chr(39), '')}'")
    n = spark.table(TABLE).count()
    version = spark.sql(f"DESCRIBE HISTORY {TABLE} LIMIT 1").first()["version"]
    print(f"loaded {n} rows into {TABLE}, Delta version {version}")


if __name__ == "__main__":
    main()
