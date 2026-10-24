"""Digest one workspace's tables into a JSON file, and diff two digests (trial vs Free Edition). Read-only on both.

    .venv\\Scripts\\python scripts/free_edition/compare_ws.py digest --profile coolcheck --catalog coolcheck --out a.json
    .venv\\Scripts\\python scripts/free_edition/compare_ws.py digest --profile freeedition --catalog workspace --out b.json
    .venv\\Scripts\\python scripts/free_edition/compare_ws.py diff a.json b.json [--tolerance 1e-9] [--show 40]

One digest per process, because Databricks Connect keeps one session per process. Parts (--parts, default all):
  bronze     lines and distinct files per feed and source kind, and a checksum of the lines
  silver     per feed and SGT day: rows and a checksum of the content, for each deduplicated table and its _all table;
             daily labels (without the arrival-dependent n_late and label_if_late_excluded); dq_day; dq_events;
             quarantine, dq_conflicts, station_gaps and wbgt_first_arrival (row counts only: they depend on file times)
  static     row count and checksum of every loaded table
  views      area_vulnerability, block_vulnerability (count and checksum), area_nearest_station_daily per target date
  forecast   gold.heat_forecast and gold.area_heat_risk rows for --dates, and the tier counts
  functions  the three agent functions called with --block, --dates (last) and --capacity
Checksums are sums of xxhash64 over the columns named, so row order does not matter. Digests keep no run id, no
scored_at and no file time. The diff compares every leaf; numbers differ only beyond --tolerance, and it reports the
largest numeric difference. Exit code 1 when anything differs. The session time zone is Asia/Singapore.
"""
import argparse
import datetime as dt
import decimal
import json
import re
import sys
from pathlib import Path

FEEDS = ("wbgt", "rainfall", "forecast", "air_temperature")
PARTS = ("bronze", "silver", "static", "views", "forecast", "functions")
# (table, day column, columns hashed). Content hash plus the key; file times never.
# source_file holds the catalog (/Volumes/<catalog>/bronze/raw_files/...), so it is hashed relative to the Volume root.
REL = "regexp_replace(source_file, '^/Volumes/[^/]+/[^/]+/[^/]+/', '')"
DAILY = {
    "wbgt_readings": ("sgt_date", "station_id, reading_ts, content_hash"),
    "wbgt_readings_all": ("sgt_date", f"content_hash, {REL}"),
    "rainfall_readings": ("sgt_date", "station_id, reading_ts, content_hash"),
    "rainfall_readings_all": ("sgt_date", f"content_hash, {REL}"),
    "forecast_issues": ("issue_sgt_date", "issue_ts, updated_ts, content_hash"),
    "forecast_issues_all": ("issue_sgt_date", f"content_hash, {REL}"),
    "air_temperature_readings": ("sgt_date", "station_id, reading_ts, content_hash"),
    "air_temperature_readings_all": ("sgt_date", f"content_hash, {REL}"),
}
LABEL_COLS = ("station_id, sgt_date, label, usable, n_readings, n_valid, n_na, n_other, n_low, n_moderate, n_high, "
              "max_wbgt, n_out_of_range, peak_slots, first_valid_ts, last_valid_ts, label_if_out_of_range_excluded, "
              "coverage, low_coverage, no_label_reason")
STATIC = ("silver.area_exposure", "silver.area_station_distance", "silver.refuge_points", "silver.park_polygons",
          "silver.block_access", "silver.area_access", "silver.ema_area_electricity", "gold.score_weights",
          "gold.tier_actions")
FORECAST_COLS = "target_date, planning_area, station_id, p_low, p_moderate, p_high, model_version, forecast_missing, cutoff_ts"
RISK_COLS = ("target_date, planning_area, heat_level, rated, third, tier, tier_rank, forecast_missing, model_version, "
             "station_id")


def hsum(cols):
    return f"sum(CAST(xxhash64({cols}) AS DECIMAL(38,0)))"


def jsonable(v):
    if isinstance(v, decimal.Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    return v


def rows(spark, sql):
    return [jsonable(r.asDict(recursive=True)) for r in spark.sql(sql).collect()]


def check_ident(*names):
    for n in names:
        if not re.fullmatch(r"[A-Za-z0-9_]+", n):
            raise SystemExit(f"bad name: {n!r}")


# ------------------------------------------------------------------------------------------------ the digest
def part_bronze(spark, c):
    out = {}
    for feed in FEEDS:
        r = rows(spark, f"SELECT source_kind, count(*) AS n, count(DISTINCT source_file) AS files, "
                        f"{hsum(f'raw, {REL}')} AS h FROM {c}.bronze.{feed}_raw GROUP BY source_kind")
        out[feed] = {x["source_kind"]: [x["n"], x["files"], x["h"]] for x in r}
    return out


def part_silver(spark, c):
    out = {}
    for t, (day, cols) in DAILY.items():
        r = rows(spark, f"SELECT {day} AS d, count(*) AS n, {hsum(cols)} AS h FROM {c}.silver.{t} GROUP BY {day}")
        out[t] = {str(x["d"]): [x["n"], x["h"]] for x in r}
    r = rows(spark, f"SELECT sgt_date AS d, count(*) AS n, count_if(usable) AS usable, count_if(usable AND label = 'High') "
                    f"AS high, {hsum(LABEL_COLS)} AS h FROM {c}.silver.station_daily_label GROUP BY sgt_date")
    out["station_daily_label"] = {str(x["d"]): [x["n"], x["usable"], x["high"], x["h"]] for x in r}
    r = rows(spark, f"SELECT feed, status, count(*) AS n, {hsum('feed, sgt_date, status, n_timestamps, expected_timestamps, n_stations, n_rows, note')} AS h "
                    f"FROM {c}.silver.dq_day GROUP BY feed, status")
    out["dq_day"] = {f"{x['feed']}|{x['status']}": [x["n"], x["h"]] for x in r}
    r = rows(spark, f"SELECT feed, check_name, n FROM {c}.silver.dq_events")
    out["dq_events"] = {f"{x['feed']}|{x['check_name']}": x["n"] for x in r}
    for t in ("quarantine", "dq_conflicts", "station_gaps", "wbgt_first_arrival"):
        out[f"{t}_rows"] = rows(spark, f"SELECT count(*) AS n FROM {c}.silver.{t}")[0]["n"]
    return out


def part_static(spark, c):
    out = {}
    for t in STATIC:
        sch, name = t.split(".")
        out[t] = rows(spark, f"SELECT count(*) AS n, {hsum('*')} AS h FROM {c}.{sch}.{name}")[0]
    return out


def part_views(spark, c):
    out = {}
    for v in ("area_vulnerability", "block_vulnerability"):
        out[v] = rows(spark, f"SELECT count(*) AS n, {hsum('*')} AS h FROM {c}.gold.{v}")[0]
    r = rows(spark, f"SELECT target_date AS d, count(*) AS n, {hsum('*')} AS h FROM {c}.gold.area_nearest_station_daily "
                    f"GROUP BY target_date")
    out["area_nearest_station_daily"] = {str(x["d"]): [x["n"], x["h"]] for x in r}
    return out


def date_list(dates):
    ds = [d.strip() for d in dates.split(",") if d.strip()]
    for d in ds:
        dt.date.fromisoformat(d)
    return ds


def part_forecast(spark, c, dates):
    ins = ", ".join(f"DATE'{d}'" for d in dates)
    out = {"heat_forecast": {}, "area_heat_risk": {}, "tier_counts": {}}
    for x in rows(spark, f"SELECT {FORECAST_COLS} FROM {c}.gold.heat_forecast WHERE target_date IN ({ins})"):
        out["heat_forecast"][f"{x['target_date']}|{x['planning_area']}"] = x
    for x in rows(spark, f"SELECT {RISK_COLS} FROM {c}.gold.area_heat_risk WHERE target_date IN ({ins})"):
        out["area_heat_risk"][f"{x['target_date']}|{x['planning_area']}"] = x
    for x in rows(spark, f"SELECT target_date, tier, count(*) AS n FROM {c}.gold.area_heat_risk "
                         f"WHERE target_date IN ({ins}) GROUP BY target_date, tier"):
        out["tier_counts"].setdefault(str(x["target_date"]), {})[x["tier"]] = x["n"]
    return out


def part_functions(spark, c, dates, block, capacity):
    def call(sql, **args):
        r = [jsonable(x.asDict(recursive=True)) for x in spark.sql(sql, args=args or None).collect()]
        return sorted(r, key=lambda x: json.dumps(x, sort_keys=True))

    g = f"{c}.gold"
    return {"find_refuges": call(f"SELECT * FROM {g}.find_refuges(:blk, :street)", blk=block[0], street=block[1]),
            "what_if_add_refuge": call(f"SELECT * FROM {g}.what_if_add_refuge(:blk, :street)", blk=block[0], street=block[1]),
            f"get_priority_areas|{dates[-1]}|{capacity}":
                call(f"SELECT * FROM {g}.get_priority_areas(DATE'{dates[-1]}', {int(capacity)})")}


def digest(a):
    check_ident(a.catalog)
    dates = date_list(a.dates)
    from databricks.connect import DatabricksSession

    spark = DatabricksSession.builder.serverless().profile(a.profile).getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    c = a.catalog
    out = {"meta": {"catalog": c, "taken_at": dt.datetime.now(dt.timezone.utc).isoformat(), "parts": a.parts,
                    "dates": dates}}
    for p in a.parts:
        print(f"digest {p} ...", flush=True)
        if p == "forecast":
            out[p] = part_forecast(spark, c, dates)
        elif p == "functions":
            out[p] = part_functions(spark, c, dates, a.block, a.capacity)
        else:
            out[p] = globals()[f"part_{p}"](spark, c)
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
    print(f"wrote {a.out}")
    return 0


# ------------------------------------------------------------------------------------------------ the diff
def flatten(obj, prefix=""):
    if isinstance(obj, dict):
        for k in sorted(obj):
            yield from flatten(obj[k], f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from flatten(v, f"{prefix}[{i}]")
    else:
        yield prefix, obj


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def compare(a, b, tolerance=0.0):
    """-> (n leaves compared, differences [(path, a, b)], largest numeric difference as (diff, path) or None)."""
    fa, fb = dict(flatten(a)), dict(flatten(b))
    diffs, largest = [], None
    for path in sorted(set(fa) | set(fb)):
        if path not in fa or path not in fb:
            diffs.append((path, fa.get(path, "<missing>"), fb.get(path, "<missing>")))
            continue
        x, y = fa[path], fb[path]
        if is_num(x) and is_num(y):
            d = abs(x - y)
            if d > 0 and (largest is None or d > largest[0]):
                largest = (d, path)
            if d > tolerance:
                diffs.append((path, x, y))
        elif x != y:
            diffs.append((path, x, y))
    return len(set(fa) | set(fb)), diffs, largest


def diff(a):
    da, db = (json.loads(Path(p).read_text(encoding="utf-8")) for p in (a.a, a.b))
    print(f"A: {a.a} ({da['meta']['catalog']}, {da['meta']['taken_at']})\nB: {a.b} ({db['meta']['catalog']}, {db['meta']['taken_at']})")
    sections = [s for s in da if s != "meta" and s in db]
    only = sorted((set(da) ^ set(db)) - {"meta"})
    if only:
        print(f"sections in one digest only: {only}")
    total = 0
    for s in sections:
        n, diffs, largest = compare(da[s], db[s], a.tolerance)
        total += len(diffs)
        big = f"; largest numeric difference {largest[0]!r} at {largest[1]}" if largest else ""
        print(f"\n[{s}] {n} values compared, {len(diffs)} differ (tolerance {a.tolerance}){big}")
        for path, x, y in diffs[:a.show]:
            print(f"  {path}: A {str(x)[:90]} | B {str(y)[:90]}")
        if len(diffs) > a.show:
            print(f"  ... {len(diffs) - a.show} more")
    print(f"\nTOTAL differences: {total}")
    return 1 if total else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("digest", help="write one workspace's digest")
    d.add_argument("--profile", required=True)
    d.add_argument("--catalog", required=True)
    d.add_argument("--out", required=True)
    d.add_argument("--parts", nargs="+", choices=PARTS, default=list(PARTS))
    d.add_argument("--dates", default="2026-10-23,2026-10-24", help="target dates for forecast and functions")
    d.add_argument("--block", nargs=2, metavar=("BLK_NO", "STREET"), default=["3", "JLN KUKOH"])
    d.add_argument("--capacity", type=int, default=800)
    f = sub.add_parser("diff", help="compare two digests")
    f.add_argument("a")
    f.add_argument("b")
    f.add_argument("--tolerance", type=float, default=0.0, help="numbers differ only beyond this absolute difference")
    f.add_argument("--show", type=int, default=40, help="differences listed per section")
    a = ap.parse_args(argv)
    return digest(a) if a.cmd == "digest" else diff(a)


if __name__ == "__main__":
    sys.exit(main())
