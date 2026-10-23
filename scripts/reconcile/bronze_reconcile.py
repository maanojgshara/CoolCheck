"""Four-way reconciliation of the backfill: local files, backfill/progress.jsonl, the Volume and Bronze.

Run from the repo root after the reconcile job (stage=bronze) has written <catalog>.silver.dq_reconcile:
    .venv\\Scripts\\python scripts/reconcile/bronze_reconcile.py [--data <coolcheck-data>]
Free Edition: add --catalog workspace --profile freeedition --out <another file>.

Per file it compares lines (local count, pages in progress.jsonl, Volume lines, Bronze rows) and bytes (local,
progress.jsonl, Volume), and the local sha256 with the one progress.jsonl recorded. Writes docs/checks/bronze_reconcile.md.
"""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FEEDS = ("wbgt", "rainfall", "forecast")


def local_files(raw):
    out = {}
    for feed in FEEDS:
        for p in sorted((raw / feed).rglob("*")):
            if p.is_file():
                b = p.read_bytes()
                out[(feed, p.name)] = {"lines": sum(1 for ln in b.splitlines() if ln.strip()), "bytes": len(b),
                                       "sha256": hashlib.sha256(b).hexdigest(), "jsonl": p.suffix == ".jsonl"}
    return out


def progress(path):
    last = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        e = json.loads(ln)
        if e.get("event") == "day":
            last[(e["feed"], e["date"])] = e
    return {(f, f"{f}_{d}.jsonl"): e for (f, d), e in last.items()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO.parent / "coolcheck-data"))
    ap.add_argument("--out", default=str(REPO / "docs" / "checks" / "bronze_reconcile.md"))
    ap.add_argument("--catalog", default="coolcheck")
    ap.add_argument("--profile", default="coolcheck")
    a = ap.parse_args(argv)
    data = Path(a.data)
    loc = local_files(data / "raw")
    prog = progress(data / "backfill" / "progress.jsonl")

    from databricks.connect import DatabricksSession
    spark = DatabricksSession.builder.serverless().profile(a.profile).getOrCreate()
    rows = spark.table(f"{a.catalog}.silver.dq_reconcile").collect()
    L = report(loc, prog, rows, a.catalog)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


def report(loc, prog, rows, catalog):
    """The report's lines, from the local files, progress.jsonl and the rows of <catalog>.silver.dq_reconcile."""
    stage = {r.stage for r in rows}
    checked = max(r.checked_at for r in rows)
    remote = {(r.feed, r.file_name or Path(r.source_file).name): r for r in rows}

    keys = sorted(set(loc) | set(remote) | {k for k, e in prog.items() if e["status"] != "no_data"})
    diffs, per_feed = [], {f: Counter() for f in FEEDS}
    for k in keys:
        feed, name = k
        l, p, r = loc.get(k), prog.get(k), remote.get(k)
        c = per_feed[feed]
        c["files_local"] += bool(l)
        c["files_progress"] += bool(p and p["status"] != "no_data")
        c["files_volume"] += bool(r and r.vol_size is not None)
        c["files_bronze"] += bool(r and r.bronze_rows)
        c["lines_local"] += l["lines"] if l else 0
        c["pages_progress"] += p["pages"] if p else 0
        c["lines_volume"] += (r.vol_lines or 0) if r else 0
        c["rows_bronze"] += (r.bronze_rows or 0) if r else 0
        c["bytes_local"] += l["bytes"] if l else 0
        c["bytes_volume"] += (r.vol_size or 0) if r else 0
        c["distinct_lines_bronze"] += (r.bronze_distinct_lines or 0) if r else 0
        problems = []
        if not (l and l["jsonl"]):
            problems.append("not a local .jsonl" if l else "missing locally")
        line_counts = {"local": l and l["lines"], "progress": p and p["pages"], "volume": r and r.vol_lines,
                       "bronze": r and r.bronze_rows}
        if len(set(line_counts.values())) != 1:
            problems.append("lines " + ", ".join(f"{s}={v}" for s, v in line_counts.items()))
        sizes = {"local": l and l["bytes"], "progress": p and p.get("bytes"), "volume": r and r.vol_size}
        if len(set(sizes.values())) != 1:
            problems.append("bytes " + ", ".join(f"{s}={v}" for s, v in sizes.items()))
        if l and p and p.get("sha256") and l["sha256"] != p["sha256"]:
            problems.append("sha256 differs from progress.jsonl")
        if r and r.bronze_rows and r.bronze_distinct_lines != r.bronze_rows:
            problems.append(f"bronze has {r.bronze_rows - r.bronze_distinct_lines} repeated identical lines")
        if problems:
            diffs.append((feed, name, "; ".join(problems)))
            c["files_differing"] += 1

    no_data = sorted(f"{f} {e['date']}" for (f, _), e in prog.items() if e["status"] == "no_data")
    status = Counter((f, e["status"]) for (f, _), e in prog.items())

    L = ["# Bronze reconciliation (backfill)", "",
         f"Generated {datetime.now().astimezone():%Y-%m-%d %H:%M %Z} by `scripts/reconcile/bronze_reconcile.py`. "
         f"Volume and Bronze figures come from `{catalog}.silver.dq_reconcile` (reconcile job, stage {', '.join(sorted(stage))}, "
         f"checked {checked}); the Volume line count is a plain batch read of each file, independent of Auto Loader.", "",
         "Four sources per file: local files in `coolcheck-data/raw`, the last `day` record per feed and date in "
         "`coolcheck-data/backfill/progress.jsonl` (pages = API calls that returned a page = lines written), the Volume "
         f"`/Volumes/{catalog}/bronze/raw_files`, and the Bronze tables `{catalog}.bronze.<feed>_raw`.", "",
         "| feed | files local | files progress | files Volume | files Bronze | lines local | pages progress | lines Volume | rows Bronze | distinct lines Bronze | bytes local | bytes Volume | files differing |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for f in FEEDS:
        c = per_feed[f]
        L.append(f"| {f} | {c['files_local']} | {c['files_progress']} | {c['files_volume']} | {c['files_bronze']} | "
                 f"{c['lines_local']:,} | {c['pages_progress']:,} | {c['lines_volume']:,} | {c['rows_bronze']:,} | "
                 f"{c['distinct_lines_bronze']:,} | {c['bytes_local']:,} | {c['bytes_volume']:,} | {c['files_differing']} |")
    L += ["", "Backfill day statuses in progress.jsonl: " +
          ", ".join(f"{f} {s} {n}" for (f, s), n in sorted(status.items())) + ".",
          f"Days with no data (no file expected): {', '.join(no_data) or 'none'}.",
          "`_meta/backfill_end.json` is outside the feed folders and is not loaded into Bronze.", ""]
    if diffs:
        L += ["## Files that differ", "", "| feed | file | difference |", "|---|---|---|"]
        L += [f"| {f} | {n} | {d} |" for f, n, d in diffs]
    else:
        L += ["**No file differs:** for every file, the line counts agree across all four sources, the byte sizes agree "
              "across local, progress.jsonl and the Volume, and the local sha256 equals the one progress.jsonl recorded."]
    return L


if __name__ == "__main__":
    main()
