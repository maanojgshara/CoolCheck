"""Overlap check for two collector runs (Day 2 step 5 acceptance): the readings both runs carried, how many are
identical copies (duplicates) and how many differ (conflicts), with the differing fields of every conflict.

Keys as in Silver: WBGT and rainfall (station, reading time), forecast (issue time, updated time). The fields compared
are the ones in Silver's content_hash (src/coolcheck/silver.py); WBGT coordinates are compared as numbers, as Silver
casts them. Silver's own count after a pipeline update is silver.dq_events / silver.dq_conflicts.

    .venv\\Scripts\\python scripts/checks/collector_overlap.py --dir ..\\coolcheck-data\\collector_dryrun
    .venv\\Scripts\\python scripts/checks/collector_overlap.py --volume /Volumes/coolcheck/bronze/raw_files [RUN_A RUN_B]

A run is named by its file names after the feed: <YYYY-MM-DD>T<HHMMSS>_<run id>. Without RUN_A and RUN_B the two
latest runs found are compared. --volume reads the Volume as your CLI profile `coolcheck` (not the collector's
principal), so it is a Databricks call. --report also writes the Markdown to a file.
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

FEEDS = ("wbgt", "rainfall", "forecast")
NAME_RE = re.compile(r"^(wbgt|rainfall|forecast)_(\d{4}-\d{2}-\d{2}T\d{6}_[A-Za-z0-9-]+)\.jsonl$")
SHOW = 50  # conflicts listed per feed (all are counted)


def _instant(s):
    try:
        dt = datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return s
    return dt.isoformat() if dt.tzinfo else s


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return s


def wbgt_records(data):
    for r in data.get("records") or []:
        for x in (r.get("item") or {}).get("readings") or []:
            st, loc = x.get("station") or {}, x.get("location") or {}
            yield ((st.get("id"), _instant(r.get("datetime"))),
                   {"station_name": st.get("name"), "town_center": st.get("townCenter"),
                    "latitude": _num(loc.get("latitude")), "longitude": _num(loc.get("longitude")),
                    "wbgt": x.get("wbgt"), "heatStress": x.get("heatStress"), "updatedTimestamp": r.get("updatedTimestamp")})


def rainfall_records(data):
    stations = {s.get("id"): s for s in data.get("stations") or [] if isinstance(s, dict)}
    for r in data.get("readings") or []:
        for x in r.get("data") or []:
            st = stations.get(x.get("stationId")) or {}
            loc = st.get("location") or {}
            yield ((x.get("stationId"), _instant(r.get("timestamp"))),
                   {"station_name": st.get("name"), "latitude": loc.get("latitude"), "longitude": loc.get("longitude"),
                    "value": x.get("value"), "readingType": data.get("readingType"), "readingUnit": data.get("readingUnit")})


def forecast_records(data):
    for r in data.get("records") or []:
        g = r.get("general") or {}
        yield ((_instant(r.get("timestamp")), _instant(r.get("updatedTimestamp"))),
               {"date": r.get("date"), "validPeriod": g.get("validPeriod"), "temperature": g.get("temperature"),
                "relativeHumidity": g.get("relativeHumidity"), "forecast": g.get("forecast"), "wind": g.get("wind"),
                "periods": r.get("periods")})


PARSE = {"wbgt": wbgt_records, "rainfall": rainfall_records, "forecast": forecast_records}


def readings(feed, content):
    """key -> set of versions (canonical JSON of the compared fields) for one file."""
    out = {}
    for line in content.splitlines():
        if not line.strip():
            continue
        body = json.loads(line)
        data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), dict) else {}
        for key, fields in PARSE[feed](data):
            out.setdefault(key, set()).add(json.dumps(fields, sort_keys=True))
    return out


class LocalSource:
    def __init__(self, root):
        self.root = Path(root)

    def files(self):
        return [(p.name, p) for p in self.root.glob("*/live/*/*.jsonl")]

    def read(self, ref):
        return ref.read_bytes()


class VolumeSource:
    def __init__(self, root, profile="coolcheck"):
        from databricks.sdk import WorkspaceClient
        self.w, self.root = WorkspaceClient(profile=profile), root.rstrip("/")

    def _walk(self, path):
        for e in self.w.files.list_directory_contents(path):
            if e.is_directory:
                yield from self._walk(e.path)
            else:
                yield e.path

    def files(self):
        out = []
        for feed in FEEDS:
            try:
                out += [(p.rsplit("/", 1)[1], p) for p in self._walk(f"{self.root}/{feed}/live")]
            except Exception:  # no live folder for this feed yet
                pass
        return out

    def read(self, ref):
        return self.w.files.download(ref).contents.read()


def compare(a, b):
    both = sorted(set(a) & set(b), key=str)
    dup = [k for k in both if a[k] == b[k] and len(a[k]) == 1]
    conflicts = [k for k in both if len(a[k] | b[k]) > 1]
    return {"a": len(a), "b": len(b), "both": len(both), "only_a": len(set(a) - set(b)), "only_b": len(set(b) - set(a)),
            "duplicates": len(dup), "conflicts": conflicts}


def differing_fields(va, vb):
    """{field: (values in A, values in B)} for the fields that differ between the versions of one key."""
    da, db = [json.loads(v) for v in sorted(va)], [json.loads(v) for v in sorted(vb)]
    out = {}
    for f in sorted({k for d in da + db for k in d}):
        xa = sorted({json.dumps(d.get(f), sort_keys=True) for d in da})
        xb = sorted({json.dumps(d.get(f), sort_keys=True) for d in db})
        if xa != xb or len(xa) > 1:
            out[f] = (xa, xb)
    return out


def report(src, run_a=None, run_b=None):
    by_run = {}
    for name, ref in src.files():
        m = NAME_RE.match(name)
        if m:
            by_run.setdefault(m.group(2), {})[m.group(1)] = ref
    runs = sorted(by_run)
    if run_a is None or run_b is None:
        if len(runs) < 2:
            raise SystemExit(f"need two runs; found {runs}")
        run_a, run_b = runs[-2], runs[-1]
    for r in (run_a, run_b):
        if r not in by_run:
            raise SystemExit(f"run {r} not found; runs: {runs}")
    lines = [f"# Collector overlap: run {run_a} vs run {run_b}", "",
             "| feed | readings A | readings B | in both | only A | only B | duplicates (identical) | conflicts |",
             "|---|---|---|---|---|---|---|---|"]
    detail, totals = [], {"duplicates": 0, "conflicts": 0}
    for feed in FEEDS:
        fa, fb = by_run[run_a].get(feed), by_run[run_b].get(feed)
        if fa is None or fb is None:
            lines.append(f"| {feed} | {'-' if fa is None else 'file'} | {'-' if fb is None else 'file'} | no file in one run |||||")
            continue
        a, b = readings(feed, src.read(fa)), readings(feed, src.read(fb))
        c = compare(a, b)
        totals["duplicates"] += c["duplicates"]
        totals["conflicts"] += len(c["conflicts"])
        lines.append(f"| {feed} | {c['a']} | {c['b']} | {c['both']} | {c['only_a']} | {c['only_b']} | {c['duplicates']} | "
                     f"{len(c['conflicts'])} |")
        for k in c["conflicts"][:SHOW]:
            for f, (xa, xb) in differing_fields(a[k], b[k]).items():
                detail.append(f"| {feed} | {' '.join(map(str, k))} | {f} | {', '.join(xa)} | {', '.join(xb)} |")
        if len(c["conflicts"]) > SHOW:
            detail.append(f"| {feed} | ... {len(c['conflicts']) - SHOW} more conflicts not listed | | | |")
    lines += ["", f"Duplicates {totals['duplicates']}, conflicts {totals['conflicts']}."]
    if detail:
        lines += ["", "## Conflicts: fields that differ", "", "| feed | key | field | A | B |", "|---|---|---|---|---|"] + detail
    return "\n".join(lines) + "\n", totals


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dir", help="a local root holding <feed>/live/<date>/*.jsonl")
    g.add_argument("--volume", help="the Volume root, read with the CLI profile coolcheck")
    ap.add_argument("runs", nargs="*", help="RUN_A RUN_B, e.g. 2026-10-21T182718_local")
    ap.add_argument("--report", help="also write the Markdown here")
    args = ap.parse_args(argv)
    if len(args.runs) not in (0, 2):
        ap.error("give both RUN_A and RUN_B, or neither")
    src = LocalSource(args.dir) if args.dir else VolumeSource(args.volume)
    md, _ = report(src, *(args.runs or (None, None)))
    print(md)
    if args.report:
        Path(args.report).write_text(md, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
