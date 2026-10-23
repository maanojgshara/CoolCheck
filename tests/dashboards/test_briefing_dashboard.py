"""The briefing dashboard (src/dashboards/briefing.lvdash.json, built by scripts/dashboards/build_briefing.py).

Structure (local): the file is exactly what the builder makes; every page is GRID_V1 with rows that fill 12 columns; field
bindings match; widget versions; no dataset names P(High), the score or gold.heat_forecast (whole words, so
gold.score_weights is fine); the colours are coolcheck.briefing's checked set; nothing calls a page "Tomorrow".
SQL (Databricks Connect, temp views only): every dataset runs unchanged on temp views with the same bare names, built from
the files the tables are loaded from (coolcheck-data/analysis and reference/), with the expected rows; the maps'
geometry measure (ST_ASGEOJSON(FIRST(geometry)) per key) gives one polygon per key.
"""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "scripts" / "dashboards", ROOT / "scripts" / "static"):
    sys.path.insert(0, str(p))

import build_briefing as BB  # noqa: E402
from coolcheck import briefing as B  # noqa: E402
from coolcheck import risk as R  # noqa: E402

DASH = json.loads((ROOT / "src/dashboards/briefing.lvdash.json").read_text(encoding="utf-8"))
ANALYSIS = ROOT.parent / "coolcheck-data" / "analysis"
VERSIONS = {"table": 2, "symbol-map": 2, "choropleth-map": 1, "filter-single-select": 2}
EXPECTED_ROWS = {"ds_thirds_map": 32, "ds_area_facts": 32, "ds_blocks": 10_817, "ds_points": 10_817 + 206,
                 "ds_parks": 471, "ds_weights": 7, "ds_actions": 4}


def widgets():
    return [(p["name"], i["widget"], i["position"]) for p in DASH["pages"] for i in p["layout"]]


def sql_of(ds):
    return "".join(ds["queryLines"])


def field_names(node):
    if isinstance(node, dict):
        return ([node["fieldName"]] if "fieldName" in node else []) + [f for v in node.values() for f in field_names(v)]
    if isinstance(node, list):
        return [f for v in node for f in field_names(v)]
    return []


# --- structure ---------------------------------------------------------------------------------------------------------

def test_file_is_what_the_builder_makes():
    assert DASH == BB.build()


def test_pages_and_grid_rows_fill_twelve_columns():
    assert [p["displayName"] for p in DASH["pages"]] == ["Blocks", "About"]
    for p in DASH["pages"]:
        assert p["pageType"] == "PAGE_TYPE_CANVAS" and p["layoutVersion"] == "GRID_V1"
        rows, y = {}, 0
        for i in p["layout"]:
            rows.setdefault(i["position"]["y"], []).append(i["position"])
        for top in sorted(rows):
            assert top == y, (p["name"], top, y)
            assert sum(pos["width"] for pos in rows[top]) == 12, (p["name"], top)
            assert len({pos["height"] for pos in rows[top]}) == 1, (p["name"], top)
            assert [pos["x"] for pos in sorted(rows[top], key=lambda q: q["x"])] == \
                   [sum(q["width"] for q in sorted(rows[top], key=lambda q: q["x"])[:k]) for k in range(len(rows[top]))]
            y = top + rows[top][0]["height"]


def test_widget_names_versions_and_bindings():
    names = [w["name"] for _, w, _ in widgets()]
    assert len(names) == len(set(names)) and all(re.fullmatch(r"[A-Za-z0-9_-]+", n) for n in names)
    for _, w, _ in widgets():
        if "multilineTextboxSpec" in w:
            continue
        kind = w["spec"]["widgetType"]
        assert w["spec"]["version"] == VERSIONS[kind], w["name"]
        if kind.startswith("filter-"):
            queries = {q["name"]: q for q in w["queries"]}
            for f in w["spec"]["encodings"]["fields"]:
                assert f["fieldName"] in [x["name"] for x in queries[f["queryName"]]["query"]["fields"]]
            assert all(q["query"]["disaggregated"] is False for q in queries.values())
            assert w["spec"]["frame"]["showTitle"] is True
        else:
            fields = {f["name"] for q in w["queries"] for f in q["query"]["fields"]}
            assert set(field_names(w["spec"]["encodings"])) <= fields, w["name"]
        for q in w["queries"]:
            assert q["query"]["datasetName"] in {d["name"] for d in DASH["datasets"]}


def test_no_dataset_names_the_probability_the_score_or_the_forecast_table():
    for d in DASH["datasets"]:
        sql = sql_of(d)
        for word in B.FORBIDDEN:
            assert not re.search(rf"\b{word}\b", sql, re.I), (d["name"], word)
        assert all(line.endswith("\n") for line in d["queryLines"])
    assert re.search(r"\bscore\b", "SELECT * FROM score_weights") is None  # whole words: score_weights is allowed


def test_colours_are_the_checked_set_and_no_page_says_tomorrow():
    by = {w["name"]: w for _, w, _ in widgets()}
    ramp = by["thirds-map"]["spec"]["encodings"]["color"]["scale"]["colorRamp"]["colors"]
    assert ramp == {"start": B.THIRD_COLOURS["lower"], "end": B.THIRD_COLOURS["upper"]}
    maps = by["points-map"]["spec"]["encodings"]["color"]["scale"]["mappings"]
    assert {m["value"]: m["color"] for m in maps} == B.POINT_COLOURS
    assert by["parks-map"]["spec"]["encodings"]["color"]["scale"]["colorRamp"]["colors"] == {"start": B.PARK_COLOUR, "end": B.PARK_COLOUR}
    assert "tomorrow" not in json.dumps(DASH).lower()
    assert "what_if_add_refuge" in json.dumps(by["what-if"])


def test_about_carries_every_notice():
    about = json.dumps([w for page, w, _ in widgets() if page == "about"], ensure_ascii=False)
    assert all(n in about for n in BB.NOTICES) and "Not official advice" in about


# --- every dataset's SQL on temp views with the same bare names ----------------------------------------------------------

@pytest.fixture(scope="module")
def views(spark):
    if not (ANALYSIS / "planning_area_boundary.csv").exists():
        pytest.skip("coolcheck-data/analysis not present")
    import load_area_exposure as AE
    import load_refuge_park_access as L
    import load_risk_tables as T
    import planning_area_layers as PAL

    def view(name, rows, columns):
        spark.createDataFrame(rows, ", ".join(f"`{c}` {t}" for c, t, _ in columns)).createOrReplaceTempView(name)

    spark.createDataFrame(AE.read_rows(ANALYSIS / "area_exposure.csv"), AE.SCHEMA).createOrReplaceTempView("t_exposure")
    for name, file in (("area_access", "area_access.csv"), ("block_access", "block_access.csv"),
                       ("refuge_points", "refuge_points.csv"), ("park_polygons", "park_polygons.csv")):
        view(f"t_{name}", L.read(ANALYSIS / file, L.TABLES[name]["columns"]), L.TABLES[name]["columns"])
    view("t_electricity", T.read(ANALYSIS / "ema_area_electricity.csv", T.TABLES["ema_area_electricity"]["columns"]),
         T.TABLES["ema_area_electricity"]["columns"])
    for name in ("score_weights", "tier_actions"):
        view(name, T.read(ROOT / "reference" / f"{name}.csv", T.TABLES[name]["columns"]), T.TABLES[name]["columns"])
    for name in ("planning_area_boundary", "park_planning_area"):
        view(f"t_{name}", L.read(ANALYSIS / PAL.TABLES[name]["file"], PAL.TABLES[name]["columns"]), PAL.TABLES[name]["columns"])
    spark.sql(R.area_vulnerability_sql("t_exposure", "t_area_access", "t_block_access", "t_electricity", "score_weights")) \
        .createOrReplaceTempView("area_vulnerability")
    spark.sql(R.block_vulnerability_sql("t_block_access", "area_vulnerability")).createOrReplaceTempView("block_vulnerability")
    spark.sql(B.planning_area_map_sql("t_planning_area_boundary")).createOrReplaceTempView("planning_area_map")
    spark.sql(B.refuge_layer_sql("t_refuge_points")).createOrReplaceTempView("refuge_layer")
    spark.sql(B.park_layer_sql("t_park_polygons", "t_park_planning_area")).createOrReplaceTempView("park_layer")
    return spark


def test_every_dataset_runs_unchanged_with_the_expected_rows(views):
    for d in DASH["datasets"]:
        df = views.sql(sql_of(d))
        assert df.count() == EXPECTED_ROWS[d["name"]], d["name"]
        cols = set(df.columns)
        for _, w, _ in widgets():
            for q in w.get("queries", []):
                if q["query"]["datasetName"] != d["name"]:
                    continue
                for f in q["query"]["fields"]:
                    for col in re.findall(r"`([^`]+)`", f["expression"]):
                        assert col in cols, (w["name"], col)


def test_default_area_exists(views):
    areas = {r["planning_area"] for r in views.sql(sql_of(next(d for d in DASH["datasets"] if d["name"] == "ds_area_facts"))).collect()}
    assert BB.DEFAULT_AREA in areas and len(areas) == 32


@pytest.mark.parametrize("ds,key,colour,n", [("ds_thirds_map", "area_name", "third_code", 32), ("ds_parks", "park_name", "park", None)])
def test_geometry_measure_gives_one_polygon_per_key(views, ds, key, colour, n):
    sql = sql_of(next(d for d in DASH["datasets"] if d["name"] == ds))
    got = views.sql(f"SELECT {key}, ST_ASGEOJSON(FIRST(geometry)) AS gj, MAX({colour}) AS c FROM ({sql}) GROUP BY {key}").collect()
    assert all(json.loads(r["gj"])["type"] in ("Polygon", "MultiPolygon") for r in got)
    if n:
        assert len(got) == n
        from collections import Counter
        assert Counter(r["c"] for r in got) == {3: 11, 2: 11, 1: 10}
