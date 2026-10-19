"""Create the coolcheck catalog and its schemas. Safe to re-run (IF NOT EXISTS)."""
import sys

from databricks.connect import DatabricksSession

CATALOG = "coolcheck"
SCHEMAS = ["bronze", "silver", "gold", "ml"]

spark = DatabricksSession.builder.serverless().profile("coolcheck").getOrCreate()

try:
    spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
except Exception as e:
    # No workaround: do not create storage locations or credentials.
    print(f"CREATE CATALOG failed:\n{e}", file=sys.stderr)
    sys.exit(1)

for schema in SCHEMAS:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{schema}")

spark.sql("SHOW CATALOGS").show(truncate=False)
