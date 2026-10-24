"""Create the agent's three tools as Unity Catalog SQL functions in <catalog>.gold through Databricks Connect (Guide D13
and C11; docs/design/agent_tools.md).

Run from the repo root; it creates functions, so only after the user's OK:
    .venv\\Scripts\\python scripts/static/create_agent_functions.py [--catalog coolcheck] [--profile coolcheck]
        [--functions find_refuges what_if_add_refuge get_priority_areas] [--block 3 "JLN KUKOH"]
        [--date YYYY-MM-DD] [--capacity 500] [--print-sql]

The SQL is src/functions/<name>.sql (coolcheck.agent_tools.function_sql), the same text the tests create as TEMPORARY
functions over temp views. find_refuges and what_if_add_refuge read <catalog>.silver.block_access and refuge_points;
get_priority_areas reads <catalog>.gold.area_heat_risk and block_vulnerability, and is skipped while gold.area_heat_risk
does not exist (a function cannot be created over a missing view). The session time zone is Asia/Singapore, since a
function keeps the settings of the session that created it.
Read-back for each function: its comment and any parameter or result column without one (Unity Catalog's function
metadata, through the SDK with --profile); then one call: find_refuges and what_if_add_refuge on --block, and
get_priority_areas on --date with --capacity. --date must be after 2026-10-19, so nothing from the final check's window
(1 Sep to 19 Oct 2026) is read; without --date that call is skipped. --print-sql prints the statements and touches nothing.
Grants: CREATE OR REPLACE drops a function's grants (24 Oct: the App's EXECUTE on find_refuges and what_if_add_refuge, put
back by hand). So each function's grants are read before it is replaced and exactly those are re-applied after; the run
stops unless they read back the same.
"""
import argparse
import datetime as dt
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from coolcheck import agent_tools as T  # noqa: E402

ORDER = ["find_refuges", "what_if_add_refuge", "get_priority_areas"]
LAST_HELD_OUT = dt.date(2026, 10, 19)  # the final check's window ends here; the read-back reads later dates only


def tables(cat):
    s, g = f"{cat}.silver", f"{cat}.gold"
    return {"get_priority_areas": {"area_heat_risk": f"{g}.area_heat_risk", "block_vulnerability": f"{g}.block_vulnerability"},
            "find_refuges": {"block_access": f"{s}.block_access", "refuge_points": f"{s}.refuge_points"},
            "what_if_add_refuge": {"block_access": f"{s}.block_access", "refuge_points": f"{s}.refuge_points"}}


def create_sql(name, cat):
    return T.function_sql(name, f"{cat}.gold.{name}", tables(cat)[name])


def function_grants(ws, full_name):
    """{principal: sorted privileges} on a function, every page; {} when it does not exist yet."""
    from databricks.sdk.errors import NotFound
    out, token = {}, None
    try:
        while True:
            r = ws.grants.get("function", full_name, page_token=token)
            for a in r.privilege_assignments or []:
                out.setdefault(a.principal, set()).update(getattr(p, "value", p) for p in a.privileges or [])
            token = r.next_page_token
            if not token:
                break
    except NotFound:
        return {}
    return {k: sorted(v) for k, v in out.items() if v}


def restore_grants(ws, full_name, before):
    """Re-apply exactly the grants read before CREATE OR REPLACE; stop unless they read back the same."""
    from databricks.sdk.service.catalog import PermissionsChange, Privilege
    now = function_grants(ws, full_name)
    changes = [PermissionsChange(principal=p, add=[Privilege(x) for x in privs if x not in now.get(p, [])])
               for p, privs in sorted(before.items())]
    changes = [c for c in changes if c.add]
    if changes:
        ws.grants.update("function", full_name, changes=changes)
    after = function_grants(ws, full_name)
    print(f"{full_name}: grants before {before or 'none'}; re-applied {sum(len(c.add) for c in changes)}; "
          f"after {after or 'none'}")
    if after != before:
        raise SystemExit(f"STOP: {full_name} grants read back {after}, not {before}")
    return after


def replace_function(spark, ws, full_name, sql):
    """CREATE OR REPLACE with the function's grants kept: read before, re-applied after."""
    before = function_grants(ws, full_name)
    spark.sql(sql)
    return restore_grants(ws, full_name, before)


def check_comments(ws, full_name):
    """Stop unless the function, every parameter and every result column has a comment; print what was read."""
    f = ws.functions.get(full_name)
    params = f.input_params.parameters if f.input_params else []
    columns = f.return_params.parameters if f.return_params else []
    bare = [p.name for p in params + columns if not (p.comment or "").strip()]
    print(f"{full_name}: {f.data_type.value if f.data_type else '?'}, {len(params)} parameters, {len(columns)} result "
          f"columns, function comment {len(f.comment or '')} characters, without a comment: {bare or 'none'}")
    if not (f.comment or "").strip() or bare:
        raise SystemExit(f"STOP: {full_name} does not read back with every comment")


def call(spark, sql, **args):
    return [r.asDict(recursive=True) for r in spark.sql(sql, args=args or None).collect()]


def read_back(spark, cat, name, a):
    fn = f"{cat}.gold.{name}"
    if name == "find_refuges":
        rows = sorted(call(spark, f"SELECT * FROM {fn}(:blk, :street)", blk=a.block[0], street=a.block[1]),
                      key=lambda r: r["refuge_rank"])
        print(f"  find_refuges({a.block[0]!r}, {a.block[1]!r}): {len(rows)} rows")
        for r in rows:
            print(f"    {r['refuge_rank']}. {r['refuge_name']} ({r['refuge_type']}, {r['refuge_planning_area']}): "
                  f"{r['distance_m']:.1f} m, within 400 m {r['within_400m']}")
        if len(rows) != T.NEAREST:
            raise SystemExit(f"STOP: find_refuges gave {len(rows)} rows for the read-back block, expected {T.NEAREST}")
    elif name == "what_if_add_refuge":
        rows = sorted(call(spark, f"SELECT * FROM {fn}(:blk, :street)", blk=a.block[0], street=a.block[1]),
                      key=lambda r: (not r["is_site_area"], r["planning_area"]))
        print(f"  what_if_add_refuge({a.block[0]!r}, {a.block[1]!r}): {len(rows)} rows")
        for r in rows:
            print(f"    {r['planning_area']}{' (site)' if r['is_site_area'] else ''}: dwelling units within 400 m "
                  f"{r['du_within_400m_before']:,} -> {r['du_within_400m_after']:,} of {r['hdb_dwelling_units']:,} "
                  f"(share {r['share_within_400m_before']:.4f} -> {r['share_within_400m_after']:.4f}); 1-2 room rental "
                  f"flats beyond 400 m {r['rental_flats_beyond_400m_before']:,} -> {r['rental_flats_beyond_400m_after']:,}; "
                  f"blocks newly within {r['blocks_newly_within']}")
            for b in r["newly_within"][:3]:
                print(f"      e.g. {b['blk_no']} {b['street']}: {b['distance_before_m']:.1f} m -> {b['distance_after_m']:.1f} m, "
                      f"{b['total_dwelling_units']} units, {b['rental_1_2_room']} rental flats")
        if not rows:
            raise SystemExit("STOP: what_if_add_refuge gave no rows for the read-back block")
    elif a.date is None:
        print("  get_priority_areas: no --date, call skipped")
    else:
        rows = sorted(call(spark, f"SELECT * FROM {fn}(DATE'{a.date.isoformat()}', {int(a.capacity)})"),
                      key=lambda r: r["area_order"])
        print(f"  get_priority_areas({a.date}, {a.capacity}): {len(rows)} areas, calls allocated "
              f"{sum(r['calls_allocated'] for r in rows):,}")
        for r in rows:
            blocks = "; ".join(f"{b['blk_no']} {b['street']} {b['calls_allocated']}/{b['rental_1_2_room']}"
                               f"{' partial' if b['partial'] else ''}" for b in r["blocks"])
            print(f"    {r['area_order']}. {r['planning_area']} ({r['region']}): {r['tier']} #{r['tier_rank']}, heat "
                  f"{r['heat_level']}, third {r['third']}; calls {r['calls_allocated']:,}, left {r['calls_left']:,}"
                  f"{'; blocks ' + blocks if blocks else ''}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="coolcheck")
    ap.add_argument("--profile", default="coolcheck")
    ap.add_argument("--functions", nargs="+", choices=ORDER, default=ORDER)
    ap.add_argument("--block", nargs=2, metavar=("BLK_NO", "STREET"), default=["3", "JLN KUKOH"],
                    help="the block for the find_refuges and what_if_add_refuge read-back")
    ap.add_argument("--date", type=dt.date.fromisoformat, help="target date for the get_priority_areas read-back")
    ap.add_argument("--capacity", type=int, default=500, help="call capacity for the get_priority_areas read-back")
    ap.add_argument("--print-sql", action="store_true", help="print the statements and touch nothing")
    a = ap.parse_args()
    if not re.fullmatch(r"\w+", a.catalog):
        raise SystemExit(f"bad catalog name: {a.catalog!r}")
    if a.date is not None and a.date <= LAST_HELD_OUT:
        raise SystemExit(f"--date must be after {LAST_HELD_OUT}: the final check's window (1 Sep to 19 Oct 2026) is not read")
    names = [n for n in ORDER if n in a.functions]
    if a.print_sql:
        for name in names:
            print(create_sql(name, a.catalog), end=";\n\n")
        return

    from databricks.connect import DatabricksSession
    from databricks.sdk import WorkspaceClient

    spark = DatabricksSession.builder.serverless().profile(a.profile).getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    ws = WorkspaceClient(profile=a.profile)
    for name in names:
        if name == "get_priority_areas" and not spark.catalog.tableExists(f"{a.catalog}.gold.area_heat_risk"):
            print(f"{a.catalog}.gold.area_heat_risk does not exist yet: get_priority_areas not created")
            continue
        replace_function(spark, ws, f"{a.catalog}.gold.{name}", create_sql(name, a.catalog))
        check_comments(ws, f"{a.catalog}.gold.{name}")
        read_back(spark, a.catalog, name, a)


if __name__ == "__main__":
    main()
