"""scripts/explanations/patch_live_briefing.py, offline: on the committed dashboard without the explanation change, the
patch gives the committed dashboard back; on one edited in the dashboard editor (pages reordered, a title restyled, a
text rewritten, catalog and schema added by the server), it keeps every edit and adds only the change; it refuses a
dashboard that already has the note."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "explanations"))

import patch_live_briefing as PL  # noqa: E402

COMMITTED = json.loads(PL.COMMITTED.read_text(encoding="utf-8"))


def without_explanations(dash):
    """The dashboard as it was before the change: other queries, no column, no note, the rows below the note one up."""
    d = copy.deepcopy(dash)
    for ds in d["datasets"]:
        if ds["name"] in PL.DATASETS:
            ds["queryLines"] = ["SELECT 'the old query' AS x\n"]
    layout = PL._layout(d)
    note = next(i for i in layout if i["widget"]["name"] == PL.NOTE)
    layout.remove(note)
    for i in layout:
        if i["position"]["y"] > note["position"]["y"]:
            i["position"]["y"] -= 1
        w = i["widget"]
        if w["name"] in PL.TABLES:
            q, spec = w["queries"][0]["query"], w["spec"]["encodings"]
            q["fields"] = [f for f in q["fields"] if f["name"] != "explanation"]
            spec["columns"] = [c for c in spec["columns"] if c["fieldName"] != "explanation"]
    return d


def test_the_patch_on_the_dashboard_before_the_change_gives_the_committed_one():
    old = without_explanations(COMMITTED)
    patched = PL.patch(old, COMMITTED)
    PL.check(old, patched, COMMITTED)
    assert patched == COMMITTED


def test_the_patch_keeps_edits_made_in_the_editor():
    live = without_explanations(COMMITTED)
    live["pages"] = live["pages"][-1:] + live["pages"][:-1]  # About first, as on 26 Oct
    for ds in live["datasets"]:
        ds.update(catalog="coolcheck", schema="gold")
    items = {i["widget"]["name"]: i for i in PL._layout(live)}
    items["top-areas"]["widget"]["spec"]["frame"]["title"] = {"value": '<span style="font-size: 24px;">Top 10</span>',
                                                              "fields": []}
    items["briefing-guide"]["widget"]["multilineTextboxSpec"]["lines"] = ["- Each dot is a planning area\n"]
    patched = PL.patch(live, COMMITTED)
    PL.check(live, patched, COMMITTED)
    new = {i["widget"]["name"]: i for i in PL._layout(patched)}
    assert [p["name"] for p in patched["pages"]] == ["about", "briefing", "blocks", "observed"]
    assert new["top-areas"]["widget"]["spec"]["frame"]["title"]["value"].startswith("<span")
    assert new["briefing-guide"]["widget"]["multilineTextboxSpec"]["lines"] == ["- Each dot is a planning area\n"]
    for name in PL.TABLES:
        assert [c["fieldName"] for c in new[name]["widget"]["spec"]["encodings"]["columns"]][2:4] == ["tier", "explanation"]
    assert all((d["catalog"], d["schema"]) == ("coolcheck", "gold") for d in patched["datasets"])
    with pytest.raises(SystemExit):
        PL.patch(patched, COMMITTED)  # already has the note
