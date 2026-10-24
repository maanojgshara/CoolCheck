"""Create <catalog>.gold.pending_approval, the table the App's Approve button writes to (Guide D13, M6;
docs/design/agent_app.md), through the existing SQL warehouse (looked up by name, never created).

Run from the repo root; it creates a table, so only after the user's OK:
    .venv\\Scripts\\python scripts/static/create_pending_approval.py [--catalog coolcheck] [--profile coolcheck]
        [--warehouse "Serverless Starter Warehouse"] [--print-sql]

The DDL is src/tables/pending_approval.sql (CREATE TABLE IF NOT EXISTS, so a rerun changes nothing). Read-back: the
columns with their comments, the row count, and that every column of coolcheck.plan.APPROVAL_COLUMNS exists.
--print-sql prints the statement and touches nothing.
"""
import argparse
import re
import sys
from pathlib import Path
from string import Template

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from coolcheck import plan as P  # noqa: E402

DDL = REPO / "src" / "tables" / "pending_approval.sql"


def create_sql(catalog):
    if not re.fullmatch(r"\w+", catalog):
        raise SystemExit(f"bad catalog name: {catalog!r}")
    return Template(DDL.read_text(encoding="utf-8")).substitute(table=f"{catalog}.gold.pending_approval")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="coolcheck")
    ap.add_argument("--profile", default="coolcheck")
    ap.add_argument("--warehouse", default="Serverless Starter Warehouse", help="name of the existing SQL warehouse")
    ap.add_argument("--print-sql", action="store_true", help="print the statement and touch nothing")
    a = ap.parse_args()
    sql = create_sql(a.catalog)
    if a.print_sql:
        print(sql)
        return

    from databricks.sdk import WorkspaceClient

    ws = WorkspaceClient(profile=a.profile)
    ids = [w.id for w in ws.warehouses.list() if w.name == a.warehouse]
    if len(ids) != 1:
        raise SystemExit(f"STOP: {len(ids)} warehouses named {a.warehouse!r}")
    wh = P.Warehouse(ws, ids[0], timeout_s=300)
    wh.query(sql)
    table = f"{a.catalog}.gold.pending_approval"
    cols = wh.query(f"DESCRIBE TABLE {table}")
    cols = [c for c in cols if c["col_name"] and not c["col_name"].startswith("#")]
    for c in cols:
        print(f"  {c['col_name']} {c['data_type']}: {c['comment']}")
    missing = set(P.APPROVAL_COLUMNS) - {c["col_name"] for c in cols}
    bare = [c["col_name"] for c in cols if not (c["comment"] or "").strip()]
    n = wh.query(f"SELECT count(*) AS n FROM {table}")[0]["n"]
    print(f"{table}: {len(cols)} columns, {n} rows; missing {sorted(missing) or 'none'}; without a comment {bare or 'none'}")
    if missing or bare:
        raise SystemExit("STOP: the table does not match coolcheck.plan.APPROVAL_COLUMNS or lacks comments")


if __name__ == "__main__":
    main()
