"""The explanation column on top of the live briefing dashboard's own JSON (docs/design/tier_explanations.md, "Applying
it"). Touches no workspace: it reads a saved `databricks lakeview get` and writes a request body.

The briefing was edited in the dashboard editor on 26 Oct 2026 (draft 07:19:18 UTC, published 07:19:20 UTC): pages
reordered (About first), titles at 24 px, the guide and the About text as bullets, a new Briefing layout. None of that
is in src/dashboards/briefing.lvdash.json, so an update from that file would undo it. This takes the live draft and
changes only what the explanation needs, from the committed file:
- the queries of the datasets that read gold.area_tier_explanation (ds_area_map, ds_top_areas, ds_more_areas);
- "Why, in a sentence" right after "Tier" in the two area tables (the query field and the column), and "Why this tier"
  and "Why vulnerable" out of them (the user, 26 Oct 23:28: the sentence carries both); the datasets keep those fields;
- the note under the top-10 table, one grid row high, with every widget below it on that page one row lower.
It checks that nothing else changed, then writes the body for `databricks lakeview update ID --json @OUT` (the draft's
serialized_dashboard and warehouse_id; no etag, so the body also restores over a later version).
    .venv\\Scripts\\python scripts/explanations/patch_live_briefing.py LIVE_GET.json OUT.json
"""
import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMMITTED = REPO / "src/dashboards/briefing.lvdash.json"
DATASETS = ("ds_area_map", "ds_top_areas", "ds_more_areas")
TABLES = ("top-areas", "more-areas")
NOTE = "explanation-note"
COLUMN = {"fieldName": "explanation", "displayName": "Why, in a sentence"}
HIDDEN = ("tier_sentence", "reason")  # "Why this tier" and "Why vulnerable", out of the two tables


def _layout(dash, page="briefing"):
    return next(p for p in dash["pages"] if p["name"] == page)["layout"]


def patch(live, committed):
    """The live dashboard (a parsed serialized_dashboard) with the explanation change from the committed one."""
    out = copy.deepcopy(live)
    queries = {d["name"]: d["queryLines"] for d in committed["datasets"]}
    for d in out["datasets"]:
        if d["name"] in DATASETS:
            d["queryLines"] = queries[d["name"]]
    layout = _layout(out)
    items = {i["widget"]["name"]: i for i in layout}
    if NOTE in items:
        raise SystemExit("STOP: the live dashboard already has the note; nothing to patch")
    for name in TABLES:
        q, spec = items[name]["widget"]["queries"][0]["query"], items[name]["widget"]["spec"]["encodings"]
        q["fields"] = [f for f in q["fields"] if f["name"] not in HIDDEN]
        spec["columns"] = [c for c in spec["columns"] if c["fieldName"] not in HIDDEN]
        q["fields"].insert(next(k for k, f in enumerate(q["fields"]) if f["name"] == "tier") + 1,
                           {"name": "explanation", "expression": "`explanation`"})
        spec["columns"].insert(next(k for k, c in enumerate(spec["columns"]) if c["fieldName"] == "tier") + 1, dict(COLUMN))
    top = items["top-areas"]["position"]
    row = top["y"] + top["height"]
    for i in layout:
        if i["position"]["y"] >= row:
            i["position"]["y"] += 1
    note = next(i["widget"] for i in _layout(committed) if i["widget"]["name"] == NOTE)
    layout.insert(layout.index(items["top-areas"]) + 1,
                  {"widget": copy.deepcopy(note), "position": {"x": 0, "y": row, "width": 12, "height": 1}})
    return out


def changes(a, b, path=""):
    """Every path where b differs from a."""
    if isinstance(a, dict) and isinstance(b, dict):
        return [p for k in sorted(set(a) | set(b)) for p in (
            [f"{path}/{k}"] if (k in a) != (k in b) else changes(a[k], b[k], f"{path}/{k}"))]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [p for i, (x, y) in enumerate(zip(a, b)) for p in changes(x, y, f"{path}[{i}]")]
    return [] if a == b else [path]


def check(live, patched, committed):
    """Only the datasets, the two tables' fields and columns, the note and the moved positions changed; the datasets and
    the tables' fields and columns are now the committed ones."""
    before = {**live, "pages": [p for p in live["pages"] if p["name"] != "briefing"]}
    after = {**patched, "pages": [p for p in patched["pages"] if p["name"] != "briefing"]}
    strip = lambda ds: [{k: v for k, v in d.items() if k not in ("catalog", "schema", "queryLines")} for d in ds]  # noqa: E731
    assert changes({**before, "datasets": strip(live["datasets"])}, {**after, "datasets": strip(patched["datasets"])}) == []
    assert [d["queryLines"] for d in patched["datasets"]] == [d["queryLines"] for d in committed["datasets"]], \
        "a dataset's query differs from the committed file"
    old, new = {i["widget"]["name"]: i for i in _layout(live)}, {i["widget"]["name"]: i for i in _layout(patched)}
    assert set(new) == set(old) | {NOTE}
    row = old["top-areas"]["position"]["y"] + old["top-areas"]["position"]["height"]
    for name, i in old.items():
        moved = dict(i["position"], y=i["position"]["y"] + (i["position"]["y"] >= row))
        assert new[name]["position"] == moved, name
        widget = copy.deepcopy(i["widget"])
        if name in TABLES:
            widget["queries"][0]["query"]["fields"] = new[name]["widget"]["queries"][0]["query"]["fields"]
            widget["spec"]["encodings"]["columns"] = new[name]["widget"]["spec"]["encodings"]["columns"]
            mine = next(c["widget"] for c in _layout(committed) if c["widget"]["name"] == name)
            assert widget["spec"]["encodings"]["columns"] == mine["spec"]["encodings"]["columns"], name
            assert widget["queries"][0]["query"]["fields"] == mine["queries"][0]["query"]["fields"], name
        assert new[name]["widget"] == widget, name


def main():
    live_get, out = Path(sys.argv[1]), Path(sys.argv[2])
    got = json.loads(live_get.read_text(encoding="utf-8"))
    live = json.loads(got["serialized_dashboard"])
    committed = json.loads(COMMITTED.read_text(encoding="utf-8"))
    patched = patch(live, committed)
    check(live, patched, committed)
    body = {"serialized_dashboard": json.dumps(patched, ensure_ascii=False), "warehouse_id": got["warehouse_id"]}
    out.write_bytes(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    print(f"wrote {out}: the live draft of {got.get('update_time')} with the explanation column; nothing else changed")


if __name__ == "__main__":
    main()
