"""Create the catalog's schemas and the raw-files Volume. Safe to re-run (IF NOT EXISTS).

The trial (the defaults):  .venv\\Scripts\\python setup_catalog.py
Free Edition:              .venv\\Scripts\\python setup_catalog.py --catalog workspace --profile freeedition
--dry-run prints the statements and connects to nothing. The catalog itself is created only when it is missing:
Free Edition's built-in catalog `workspace` already exists.
"""
import argparse
import re
import sys

CATALOG = "coolcheck"
PROFILE = "coolcheck"
SCHEMAS = ["bronze", "silver", "gold", "ml"]
VOLUME = "bronze.raw_files"  # the Volume the collector and the backfill upload write to
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def statements(catalog, catalog_exists):
    """The SQL to run, in order."""
    if not NAME_RE.match(catalog):
        raise ValueError(f"not a plain catalog name: {catalog!r}")
    out = [] if catalog_exists else [f"CREATE CATALOG IF NOT EXISTS {catalog}"]
    out += [f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}" for schema in SCHEMAS]
    out.append(f"CREATE VOLUME IF NOT EXISTS {catalog}.{VOLUME}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--catalog", default=CATALOG)
    ap.add_argument("--profile", default=PROFILE)
    ap.add_argument("--dry-run", action="store_true", help="print the statements; connect to nothing")
    a = ap.parse_args(argv)
    if a.dry_run:
        for s in statements(a.catalog, catalog_exists=False):
            print(s + (";  -- only if the catalog is missing" if s.startswith("CREATE CATALOG") else ";"))
        return 0

    from databricks.connect import DatabricksSession
    spark = DatabricksSession.builder.serverless().profile(a.profile).getOrCreate()
    exists = a.catalog in {r[0] for r in spark.sql("SHOW CATALOGS").collect()}
    for s in statements(a.catalog, exists):
        try:
            spark.sql(s)
        except Exception as e:
            # No workaround: do not create storage locations or credentials.
            print(f"{s} failed:\n{e}", file=sys.stderr)
            return 1
        print(s)
    spark.sql("SHOW CATALOGS").show(truncate=False)
    spark.sql(f"SHOW SCHEMAS IN {a.catalog}").show(truncate=False)
    spark.sql(f"SHOW VOLUMES IN {a.catalog}.bronze").show(truncate=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
