"""Write gold.area_tier_explanation for one target date (coolcheck.explain; docs/design/tier_explanations.md).

Run from the repo root; it calls the model and writes a table, so only on the user's word:
    .venv\\Scripts\\python scripts/explanations/generate.py [--target-date 2026-10-26] [--catalog coolcheck]
        [--profile coolcheck] [--warehouse-id 7aa1dc56400d5b33] [--dry-run] [--only "TOA PAYOH" ...] [--out FILE]

On the SQL warehouse, through the statement API: reads gold.area_heat_risk for the date (the rated areas with a tier),
gold.area_vulnerability (the rated areas' values, for the ranks) and gold.observed_heat_daily (each station's day before);
builds the facts and the template sentence in Python; calls ai_query once per area in one statement (Llama 3.3 70B,
temperature 0); checks each sentence; replaces the date's rows (INSERT INTO ... REPLACE WHERE, one Delta write) with
the table's comments and tags; reads them back. The default date is the latest in gold.area_heat_risk. --dry-run calls
the model and prints, writing nothing; --only limits the areas (dry runs only). --out saves every row as JSON. Prints the
git commit, the counts, every sentence with its checks, and the characters sent and received (tokens are not returned
by ai_query; system.ai_gateway.usage has them a few hours later).
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from coolcheck import explain as E  # noqa: E402
from coolcheck import risk as R  # noqa: E402

WAREHOUSE = "7aa1dc56400d5b33"  # the Serverless Starter Warehouse the dashboards use
INTS, FLOATS = {"INT", "LONG", "SHORT", "BYTE"}, {"DOUBLE", "FLOAT", "DECIMAL"}


def _cast(v, t):
    if v is None:
        return None
    if t in INTS:
        return int(v)
    if t in FLOATS:
        return float(v)
    if t == "BOOLEAN":
        return v == "true"
    if t == "DATE":
        return date.fromisoformat(v)
    return v


def run(ws, warehouse, sql, **params):
    """Rows of one statement as dicts, typed from the result's schema; stops the script on a failed statement."""
    from databricks.sdk.service.sql import Disposition, Format, StatementParameterListItem, StatementState

    r = ws.statement_execution.execute_statement(
        statement=sql, warehouse_id=warehouse, wait_timeout="50s", disposition=Disposition.INLINE, format=Format.JSON_ARRAY,
        parameters=[StatementParameterListItem(name=k, value=v) for k, v in params.items()] or None)
    while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(3)
        r = ws.statement_execution.get_statement(r.statement_id)
    if r.status.state != StatementState.SUCCEEDED:
        error = r.status.error.message if r.status.error else ""
        raise SystemExit(f"STOP: statement {r.status.state.value}: {error}\n{sql.strip()[:400]}")
    columns = r.manifest.schema.columns if r.manifest and r.manifest.schema and r.manifest.schema.columns else []
    types = [(c.name, c.type_name.value if c.type_name else "STRING") for c in columns]
    data, chunk = list(r.result.data_array or []) if r.result else [], r.result
    while chunk is not None and chunk.next_chunk_index is not None:
        chunk = ws.statement_execution.get_statement_result_chunk_n(r.statement_id, chunk.next_chunk_index)
        data += chunk.data_array or []
    return [{n: _cast(v, t) for (n, t), v in zip(types, row)} for row in data]


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True).stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-date", type=date.fromisoformat, default=None)
    ap.add_argument("--catalog", default="coolcheck")
    ap.add_argument("--profile", default="coolcheck")
    ap.add_argument("--warehouse-id", default=WAREHOUSE)
    ap.add_argument("--dry-run", action="store_true", help="call the model and print; write nothing")
    ap.add_argument("--only", nargs="+", default=None, help="planning areas, upper case (dry runs only)")
    ap.add_argument("--out", type=Path, default=None, help="save every row as JSON")
    a = ap.parse_args()
    if a.only and not a.dry_run:
        raise SystemExit("--only writes part of a date, so it needs --dry-run")

    from databricks.sdk import WorkspaceClient

    ws, wh = WorkspaceClient(profile=a.profile), a.warehouse_id
    commit, dirty = git("rev-parse", "HEAD"), git("status", "--porcelain", "--", "src/coolcheck", "scripts/explanations",
                                                  "reference")
    print(f"commit {commit}; files this run uses {'changed: ' + dirty if dirty else 'unchanged from it'}")
    target = a.target_date or run(ws, wh, E.latest_date_sql(a.catalog))[0]["target_date"]
    heat = [h for h in run(ws, wh, E.heat_sql(a.catalog, target)) if h["tier"] in R.TIER_SEVERITY]
    vulnerability = run(ws, wh, E.vulnerability_sql(a.catalog))
    observed = {o["station_id"]: o for o in run(ws, wh, E.observed_sql(a.catalog, target))}
    if a.only:
        heat = [h for h in heat if h["planning_area"] in a.only]
    by_area = {v["planning_area"]: v for v in vulnerability}
    if not heat or any(h["planning_area"] not in by_area for h in heat):
        raise SystemExit(f"STOP: {len(heat)} rated areas with a tier on {target}, or one without a vulnerability row")
    weights = R.load_weights(REPO / "reference/score_weights.csv")
    rank_of = E.ranks(vulnerability, weights)
    facts = {h["planning_area"]: E.facts(h, by_area[h["planning_area"]], rank_of, len(vulnerability), weights,
                                         observed.get(h["station_id"])) for h in heat}
    requests = [{"planning_area": k, "request": E.request(f)} for k, f in facts.items()]
    print(f"target date {target}: {len(heat)} rated areas with a tier, {len(vulnerability)} rated areas in all, "
          f"{sum('observed_heat' in f for f in facts.values())} with an observed peak for the day before")

    t0 = time.time()
    answers = {r["planning_area"]: r for r in run(ws, wh, E.ai_sql(), requests=json.dumps(requests, ensure_ascii=False))}
    print(f"ai_query: {len(answers)} answers in {time.time() - t0:.0f} s, model {E.MODEL}")
    rows = []
    for k, f in facts.items():
        ans = answers.get(k, {})
        error = ans.get("error") or (None if ans else "no answer")
        rows.append({"planning_area": k, "facts": json.dumps(f, ensure_ascii=False),
                     **E.choose(f, ans.get("sentence"), error), "model": E.MODEL})
    for r in rows:
        print(f"\n{r['planning_area']} [{r['written_by']}]\n  shown:    {r['explanation']}")
        if r["written_by"] == E.TEMPLATE:
            print(f"  model:    {r['ai_sentence']}\n  failed:   {r['checks_failed']}")
    sent, got = sum(len(q["request"]) for q in requests), sum(len(r["ai_sentence"] or "") for r in rows)
    print(f"\n{sum(r['written_by'] == E.AI for r in rows)} {E.AI}, {sum(r['written_by'] == E.TEMPLATE for r in rows)} "
          f"{E.TEMPLATE}; characters sent {sent:,}, received {got:,}")
    if a.out:
        a.out.write_bytes(json.dumps({"commit": commit, "dirty": dirty, "target_date": str(target), "model": E.MODEL,
                                      "rows": rows}, ensure_ascii=False, indent=1).encode("utf-8"))
        print(f"saved {a.out}")
    if a.dry_run:
        print("dry run: nothing written")
        return

    table = f"{a.catalog}.gold.{E.TABLE}"
    run(ws, wh, E.create_sql(a.catalog))
    for sql in E.comment_sqls(a.catalog):
        run(ws, wh, sql)
    fields = [c for c, _, _ in E.COLUMNS if c not in ("target_date", "generated_at")]
    run(ws, wh, E.write_sql(a.catalog, target), rows=json.dumps([{c: r[c] for c in fields} for r in rows], ensure_ascii=False))
    back = run(ws, wh, f"SELECT written_by, count(*) AS n, count(DISTINCT planning_area) AS areas FROM {table} "
                       f"WHERE target_date = DATE'{target}' GROUP BY written_by ORDER BY written_by")
    bare = [r["col_name"] for r in run(ws, wh, f"DESCRIBE TABLE {table}")
            if r["col_name"] and not r["col_name"].startswith("#") and not r["comment"]]
    tags = {r["tag_name"] for r in run(ws, wh, f"SELECT tag_name FROM {a.catalog}.information_schema.table_tags "
                                               f"WHERE schema_name = 'gold' AND table_name = '{E.TABLE}'")}
    n, counts = sum(r["n"] for r in back), ", ".join(f"{r['written_by']} {r['n']}" for r in back)
    print(f"{table}: {n} rows for {target} ({counts}), columns without a comment: {bare or 'none'}, tags: {sorted(tags)}")
    if n != len(rows) or sum(r["areas"] for r in back) != len(rows) or bare or tags != set(E.TAGS):
        raise SystemExit(f"STOP: {table} does not read back as written")


if __name__ == "__main__":
    main()
