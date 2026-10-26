"""The briefing dashboard (src/dashboards/briefing.lvdash.json, built by scripts/dashboards/build_briefing.py).

Structure (local): the file is exactly what the builder makes; every page is GRID_V1 with rows that fill 12 columns; field
bindings match; widget versions; no dataset names P(High), the score, gold.heat_forecast, model_version or run_id (whole
words, so gold.score_weights and scored_at are fine), nor reaches one through gold.area_tier_explanation (it holds none,
and the datasets take only its sentence); both area tables show six columns, "Why, in a sentence" after the tier (the
explanation or else the tier sentence) and no longer "Why this tier" or "Why vulnerable" (the user, 26 Oct 23:28), while
their datasets keep both fields; the note on who writes the sentences is under the top 10, and no dataset calls
ai_query; the colours are coolcheck.briefing's checked set and the live page's
heat categories; nothing calls a page "Tomorrow" and nothing reads as unfinished (no placeholder box); the Blocks page
points to the App for the what-if; the Briefing page computes today in Singapore, not with current_date().
SQL (Databricks Connect, temp views only): every dataset runs unchanged on temp views with the same bare names, built from
the files the tables are loaded from (coolcheck-data/analysis and reference/) and a made-up forecast through
coolcheck.risk.area_heat_risk_sql, with the expected rows; the Briefing page's headline (the App's "No rated area is in
the High tier." only on a day with no High area and some Medium or Low), top 10 and the rest, each with the date's
explanation or its tier sentence (never blank); the two wording fixes (the
75+ reasons as one phrase; "too few flats to measure" for areas held neutral); area names with a capital after each space
and hyphen wherever the page shows one; the filters open on Bedok; the Observed heat page's rows per area and day.
"""
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "scripts" / "dashboards", ROOT / "scripts" / "static"):
    sys.path.insert(0, str(p))

import build_briefing as BB  # noqa: E402
from coolcheck import briefing as B  # noqa: E402
from coolcheck import palette as P  # noqa: E402
from coolcheck import risk as R  # noqa: E402

DASH = json.loads((ROOT / "src/dashboards/briefing.lvdash.json").read_text(encoding="utf-8"))
LIVE = json.loads((ROOT / "src/dashboards/live_heat_stress.lvdash.json").read_text(encoding="utf-8"))
ANALYSIS = ROOT.parent / "coolcheck-data" / "analysis"
VERSIONS = {"table": 2, "symbol-map": 2, "bar": 3, "filter-single-select": 2}
NEVER_SHOWN = (*B.FORBIDDEN, "model_version", "run_id")
# the made-up forecast: High heat in three areas (one rated, two not), Moderate elsewhere; the latest date and one before
HIGH_AREAS = {"TOA PAYOH", "SOUTHERN ISLANDS", "SUNGEI KADUT"}
SCORED_AT = datetime(2026, 10, 23, 16, 49, 49)  # UTC: 24 Oct 2026 00:49:49 SGT
OBSERVED = [(date(2026, 10, 1), "S1", "One", "Moderate", 2, 30.5, "BEDOK"), (date(2026, 10, 1), "S1", "One", "Moderate", 2, 30.5, "TAMPINES"),
            (date(2026, 10, 1), "S2", "Two", "High", 3, 33.1, None), (date(2026, 10, 2), "S1", "One", "Low", 1, 28.0, "BEDOK")]
EXPECTED_ROWS = {"ds_briefing_lines": 5, "ds_area_map": 55, "ds_top_areas": 10, "ds_more_areas": None, "ds_trend": 3,
                 "ds_area_observed": 3,
                 "ds_area_facts": 32, "ds_blocks": 10_817, "ds_points": 10_817 + 206, "ds_weights": 7, "ds_actions": 4}


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
    assert [p["displayName"] for p in DASH["pages"]] == ["Briefing", "Blocks", "Observed heat", "About"]
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


def test_no_dataset_names_the_probability_the_score_the_forecast_table_or_the_run():
    for d in DASH["datasets"]:
        sql = sql_of(d)
        for word in NEVER_SHOWN:
            assert not re.search(rf"\b{word}\b", sql, re.I), (d["name"], word)
        assert "select *" not in sql.lower(), d["name"]
        assert all(line.endswith("\n") for line in d["queryLines"])
    assert re.search(r"\bscore\b", "SELECT * FROM score_weights, scored_at") is None  # whole words only
    shown = {f for _, w, _ in widgets() for f in field_names(w.get("spec", {}).get("encodings", {}))}
    assert not shown & {"tier_rank", "heat_level", "v", "third_code"}


def test_the_explanation_table_gives_the_datasets_its_sentence_only():
    """Nothing never shown comes in through gold.area_tier_explanation: the table has no such column (its facts hold none,
    tests/explanations), and a dataset takes only the sentence and the join keys from it."""
    from coolcheck import explain as E
    assert not {c for c, _, _ in E.COLUMNS} & {*NEVER_SHOWN, "v", "v_rank", "tier_rank"}
    readers = [d for d in DASH["datasets"] if "area_tier_explanation" in sql_of(d)]
    assert {d["name"] for d in readers} == {"ds_area_map", "ds_top_areas", "ds_more_areas"}  # the shared ORDERED CTE
    for d in readers:
        sql = sql_of(d)
        assert set(re.findall(r"\be\.(\w+)", sql)) == {"explanation", "target_date", "planning_area"}, d["name"]
        for col in ("facts", "ai_sentence", "template_sentence", "checks_failed", "written_by"):
            assert not re.search(rf"\b{col}\b", sql), (d["name"], col)
    assert not any("ai_query" in sql_of(d).lower() for d in DASH["datasets"])


def test_both_area_tables_show_six_columns_with_why_in_a_sentence_after_the_tier():
    """"Why this tier" and "Why vulnerable" are hidden (the user, 26 Oct 23:28): the sentence begins with the tier
    sentence and names the same measures; the datasets keep both fields."""
    by = {w["name"]: w for _, w, _ in widgets()}
    for name in ("top-areas", "more-areas"):
        assert [(c["fieldName"], c["displayName"]) for c in by[name]["spec"]["encodings"]["columns"]] == [
            ("briefing_order", "#"), ("area", "Planning area"), ("tier", "Tier"), ("explanation", "Why, in a sentence"),
            ("rental_1_2_room", "1-2 room rental flats"), ("actions", "Actions (a proposal)")], name
    for name in ("ds_top_areas", "ds_more_areas"):
        sql = sql_of(next(d for d in DASH["datasets"] if d["name"] == name))
        assert "coalesce(e.explanation, r.tier_sentence) AS explanation" in sql
        assert "LEFT JOIN area_tier_explanation e ON e.target_date = r.target_date AND e.planning_area = r.planning_area" in sql
        assert "SELECT briefing_order, area, tier, explanation, tier_sentence, reason, rental_1_2_room, actions FROM ordered" in sql


def test_the_note_on_who_writes_the_sentences_is_under_the_top_ten():
    pos = {w["name"]: p for _, w, p in widgets()}
    note = next(w for _, w, _ in widgets() if w["name"] == "explanation-note")
    assert "".join(note["multilineTextboxSpec"]["lines"]).strip() == (
        "Each sentence is written by Llama 3.3 70B through Databricks AI Functions from the row's facts; code checks that "
        "it states the tier, heat level, third and each measure as given, and nothing but the facts, or shows the "
        "template sentence.")  # window D's finding 4: no more than the check does (coolcheck.explain.check)
    top = pos["top-areas"]
    assert pos["explanation-note"] == {"x": 0, "y": top["y"] + top["height"], "width": 12, "height": 1}
    assert pos["more-areas"]["y"] == top["y"] + top["height"] + 1


def test_briefing_page_reads_the_latest_date_and_today_in_singapore():
    sql = {d["name"]: sql_of(d) for d in DASH["datasets"]}
    for name in ("ds_briefing_lines", "ds_area_map", "ds_top_areas", "ds_more_areas"):
        assert "target_date = (SELECT max(target_date) FROM area_heat_risk)" in sql[name], name
        assert "current_date" not in sql[name].lower(), name
    assert "to_date(from_utc_timestamp(current_timestamp(), 'Asia/Singapore'))" in sql["ds_briefing_lines"]
    assert "from_utc_timestamp(scored_at, 'Asia/Singapore')" in sql["ds_briefing_lines"]
    assert "ORDER BY CASE r.tier WHEN 'High' THEN 1 WHEN 'Medium' THEN 2" in sql["ds_top_areas"] and "r.tier_rank)" in sql["ds_top_areas"]


def test_colours_are_the_checked_set_and_no_page_says_tomorrow():
    by = {w["name"]: w for _, w, _ in widgets()}
    mappings = lambda name: {m["value"]: m["color"] for m in by[name]["spec"]["encodings"]["color"]["scale"]["mappings"]}  # noqa: E731
    assert mappings("area-map") == {**B.TIER_COLOURS, "Not rated": B.NEUTRAL, "No forecast": B.NEUTRAL}
    assert P.categorical_ok([*B.TIER_COLOURS.values(), B.NEUTRAL])
    assert mappings("points-map") == {BB.POINT_LABELS[k]: c for k, c in B.POINT_COLOURS.items()}
    assert all(len(label) <= 20 for label in BB.POINT_LABELS.values())  # short legend labels
    live = {m["value"]: m["color"] for p in LIVE["pages"] for i in p["layout"]
            for m in i["widget"].get("spec", {}).get("encodings", {}).get("color", {}).get("scale", {}).get("mappings", [])}
    for name in ("trend-chart", "observed-trend-chart", "area-observed-chart"):
        assert mappings(name) == BB.HEAT_COLOURS == {k: live[k] for k in ("Low", "Moderate", "High")}, name
    assert not any(w.get("spec", {}).get("widgetType") == "choropleth-map" for _, w, _ in widgets())
    assert "tomorrow" not in json.dumps(DASH).lower()


def test_legends_in_a_logical_order():
    want = {"area-map": ["High", "Medium", "Low", "Not rated", "No forecast"],
            "points-map": ["Block within 400 m", "Block beyond 400 m", "Refuge"],
            **{n: ["Low", "Moderate", "High"] for n in ("trend-chart", "observed-trend-chart", "area-observed-chart")}}
    scales = {w["name"]: w["spec"]["encodings"]["color"]["scale"] for _, w, _ in widgets()
              if "color" in w.get("spec", {}).get("encodings", {})}
    assert set(scales) == set(want)
    for name, order in want.items():
        assert [m["value"] for m in scales[name]["mappings"]] == order, name
        assert scales[name]["sort"] == {"by": "custom-order", "orderedValues": order}, name


def test_more_areas_table_is_tall_enough_for_13_rows():
    """Height 8 showed 12 of the 13 rows on 24 Oct 2026; the table is now 10 rows of the grid tall."""
    pos = next(p for _, w, p in widgets() if w["name"] == "more-areas")
    assert pos["height"] >= 10


def test_within_tier_order_is_said_in_words_never_as_a_number():
    by = {w["name"]: w for _, w, _ in widgets()}
    title = by["top-areas"]["spec"]["frame"]["title"]
    about = "".join(by["about-method"]["multilineTextboxSpec"]["lines"])
    for text_ in (title, about):
        assert "the chance of High heat times vulnerability" in text_ and "never shown" in text_
    assert "probability" not in json.dumps(DASH["pages"]).lower()


def test_nothing_reads_as_unfinished():
    unfinished = r"not built|reserved for|placeholder|\btbd\b|\btodo\b|coming soon|\bwindow [a-e]\b|what_if"
    assert not re.findall(unfinished, json.dumps(DASH, ensure_ascii=False), re.I)


def test_blocks_page_points_to_the_app_for_the_what_if():
    lines = [w["multilineTextboxSpec"]["lines"] for page, w, _ in widgets() if w["name"] == "app-pointer"]
    assert len(lines) == 1 and re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", "".join(lines[0])).strip() == (
        "To test a new refuge near a block, open the CoolCheck App (https://coolcheck-7474646896364032.aws.databricksapps.com) "
        "and use 'What if a refuge opened here?'")


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
    spark.createDataFrame(OBSERVED, ", ".join(f"{c} {t}" for c, t in zip(
        [c for c, _ in B.OBSERVED_COLUMNS], ["DATE", "STRING", "STRING", "STRING", "INT", "DOUBLE", "STRING"]))) \
        .createOrReplaceTempView("observed_heat_daily")
    spark.createDataFrame(EXPLANATIONS, "target_date DATE, planning_area STRING, explanation STRING") \
        .createOrReplaceTempView("area_tier_explanation")
    heat_risk_view(spark, LATEST)
    return spark


LATEST = date(2999, 12, 31)  # after any real today, so no "no forecast for today" notice unless a test asks for one
# gold.area_tier_explanation: Toa Payoh has the latest date's sentence; Bedok only the day before's
EXPLANATIONS = [(LATEST, "TOA PAYOH", "High: a checked sentence."), (date(2999, 12, 30), "BEDOK", "An older sentence.")]


def heat_risk_view(spark, latest, high=None, missing=False):
    """area_heat_risk over a made-up forecast for every planning area: on `latest`, High heat in `high` (by default
    HIGH_AREAS and the first lower-third area, a Medium with High heat) and Moderate elsewhere, or no forecast for any
    area if `missing`; the day before, High heat everywhere (so a dataset that missed the latest-date filter would count
    differently)."""
    from datetime import timedelta, timezone
    areas = sorted(r["planning_area"] for r in spark.table("t_exposure").select("planning_area").collect())
    lower = min(r["planning_area"] for r in spark.sql("SELECT planning_area FROM area_vulnerability WHERE third = 'lower'").collect())
    at = SCORED_AT.replace(tzinfo=timezone.utc)
    days = ((latest, HIGH_AREAS | {lower} if high is None else set(high)), (latest - timedelta(days=1), set(areas)))
    rows = [(d, a, "S00", *((None,) * 3 if missing and d == latest else (0.1, 0.4, 0.5) if a in hi else (0.2, 0.7, 0.1)),
             "m", "r", at, at, False) for d, hi in days for a in areas]
    spark.createDataFrame(rows, "target_date DATE, planning_area STRING, station_id STRING, p_low DOUBLE, p_moderate DOUBLE, "
                                "p_high DOUBLE, model_version STRING, run_id STRING, cutoff_ts TIMESTAMP, scored_at TIMESTAMP, "
                                "forecast_missing BOOLEAN").createOrReplaceTempView("t_forecast")
    spark.sql(R.area_heat_risk_sql("t_forecast", "area_vulnerability", "t_exposure", "tier_actions")) \
        .createOrReplaceTempView("area_heat_risk")
    return lower


def rows_of(spark, name):
    return [r.asDict() for r in spark.sql(sql_of(next(d for d in DASH["datasets"] if d["name"] == name))).collect()]


def tier_counts(spark):
    return {r["tier"]: r["n"] for r in spark.sql(
        f"SELECT tier, count(*) AS n FROM area_heat_risk WHERE target_date = DATE'{LATEST}' GROUP BY tier").collect()}


def test_every_dataset_runs_unchanged_with_the_expected_rows(views):
    n = tier_counts(views)
    expected = {**EXPECTED_ROWS, "ds_more_areas": n.get("High", 0) + n.get("Medium", 0) - 10}
    for d in DASH["datasets"]:
        df = views.sql(sql_of(d))
        assert df.count() == expected[d["name"]], d["name"]
        cols = set(df.columns)
        for _, w, _ in widgets():
            for q in w.get("queries", []):
                if q["query"]["datasetName"] != d["name"]:
                    continue
                for f in q["query"]["fields"]:
                    for col in re.findall(r"`([^`]+)`", f["expression"]):
                        assert col in cols, (w["name"], col)


def test_default_area_exists(views):
    """The Blocks and Observed heat pages open on Bedok: each filter's default is a name in every dataset it filters."""
    areas = {r["planning_area"] for r in views.sql(sql_of(next(d for d in DASH["datasets"] if d["name"] == "ds_area_facts"))).collect()}
    assert BB.DEFAULT_AREA == "Bedok" and BB.DEFAULT_AREA in areas and len(areas) == 32
    filters = [(page, w) for page, w, _ in widgets() if w.get("spec", {}).get("widgetType") == "filter-single-select"]
    assert [page for page, _ in filters] == ["blocks", "observed"]
    for _, w in filters:
        assert w["spec"]["selection"]["defaultSelection"]["values"]["values"] == [{"value": BB.DEFAULT_AREA}]
        for q in w["queries"]:
            assert BB.DEFAULT_AREA in {r["planning_area"] for r in rows_of(views, q["query"]["datasetName"])}, q["name"]


def test_area_names_are_title_case_in_every_dataset_that_shows_them(views):
    """The headline's Not-rated names are checked in its own tests (North-Eastern Islands in the no-High one)."""
    for name, col in (("ds_area_map", "area"), ("ds_top_areas", "area"), ("ds_more_areas", "area"),
                      ("ds_area_facts", "planning_area"), ("ds_blocks", "planning_area"), ("ds_points", "planning_area"),
                      ("ds_area_observed", "planning_area")):
        areas = {r[col] for r in rows_of(views, name)}
        assert areas and all(a == a.title() for a in areas), name
    assert "Downtown Core" in {r["planning_area"] for r in rows_of(views, "ds_area_facts")}


def test_all_55_area_names_have_a_capital_after_each_space_and_hyphen(views):
    """Spark's initcap alone capitalises only after a space ("North-eastern Islands"); each name on the map is
    str.title() of its upper-case name."""
    raw = {r["planning_area"] for r in views.sql(
        f"SELECT planning_area FROM area_heat_risk WHERE target_date = DATE'{LATEST}'").collect()}
    shown = {r["area"] for r in rows_of(views, "ds_area_map")}
    assert len(raw) == len(shown) == 55 and all(a.isupper() for a in raw)
    assert shown == {a.title() for a in raw} and {"North-Eastern Islands", "Ang Mo Kio"} <= shown


def test_table_counts_and_distances_are_numbers_so_a_header_click_sorts_them_right(views):
    """A text column would put "9,000" after "10,000". Whether a table shows thousands separators by itself is for the
    deployed page to show; the SQL keeps the columns numeric and in its own order."""
    from numbers import Number
    tables = {"ds_top_areas": ["rental_1_2_room"], "ds_more_areas": ["rental_1_2_room"],
              "ds_area_facts": ["aged_75_plus", "rental_1_2_room", "hdb_dwelling_units_confirmed"],
              "ds_blocks": ["rental_1_2_room", "total_dwelling_units", "refuge_m", "park_m"]}
    for name, cols in tables.items():
        rows = rows_of(views, name)
        for col in cols:
            values = [r[col] for r in rows if r[col] is not None]
            assert values and all(isinstance(v, Number) and not isinstance(v, bool) for v in values), (name, col, values[:3])
    assert [r["briefing_order"] for r in rows_of(views, "ds_top_areas")] == list(range(1, 11))  # the SQL order is kept
    assert any(r["aged_75_plus"] >= 1000 for r in rows_of(views, "ds_area_facts"))


def test_map_tooltips_and_detail_text_carry_the_thousands_separators(views):
    """Nothing sorts in a tooltip or in the Blocks map's detail text, so format_number stays there."""
    tooltip = {r["area"]: r["rental_1_2_room"] for r in rows_of(views, "ds_area_map")}
    assert tooltip["Toa Payoh"] == "3,835"
    assert all(re.fullmatch(r"\d{1,3}(,\d{3})*", v) for v in tooltip.values())
    details = [r["detail"] for r in rows_of(views, "ds_points") if r["point_type"] != "Refuge"]
    assert all(re.fullmatch(r"priority \d+; 1-2 room rental flats \d{1,3}(,\d{3})*", d) for d in details)


def test_weights_status_drops_the_guide_reference(views):
    status = {r["review_status"] for r in rows_of(views, "ds_weights")}
    assert status == {"judgement, not yet reviewed by a practitioner"}


def test_headline_lines_in_order(views):
    n = tier_counts(views)
    lines = [r["line"] for r in rows_of(views, "ds_briefing_lines")]
    assert lines == [
        f"Heat risk for {LATEST.strftime('%A')}, 31 December 2999, prepared 24 Oct 2026 00:49 SGT",
        f"Tiers: High {n['High']}, Medium {n['Medium']}, Low {n['Low']}, Not rated {n['Not rated']}.",
        "Medium is not an alert: heightened care where heat is Moderate in an upper- or middle-third area, or High in a "
        "lower-third one. One Medium area has High heat and is in the lower third for vulnerability.",
        f"{n['High'] + n['Medium']} areas are High or Medium: the top 10 are in the first table, the other "
        f"{n['High'] + n['Medium'] - 10} in the table under it.",
        "Southern Islands and Sungei Kadut have High heat but are Not rated: no HDB blocks to rate, so only the heat level is shown."]


def test_no_high_line_right_after_the_tier_counts_only_when_no_area_is_high_and_some_are_rated(views):
    """The App's sentence for the whole island; not on the fixture day (Toa Payoh is High), nor on a day with no forecast."""
    assert BB.NO_HIGH == "No rated area is in the High tier."
    assert BB.NO_HIGH not in [r["line"] for r in rows_of(views, "ds_briefing_lines")]
    head = f"Heat risk for {LATEST.strftime('%A')}, 31 December 2999, prepared 24 Oct 2026 00:49 SGT"
    try:
        heat_risk_view(views, LATEST, high={"NORTH-EASTERN ISLANDS", "SOUTHERN ISLANDS"})  # High heat only where Not rated
        n = tier_counts(views)
        assert "High" not in n and n["Medium"] + n["Low"] == 32
        assert [r["line"] for r in rows_of(views, "ds_briefing_lines")] == [
            head, f"Tiers: High 0, Medium {n['Medium']}, Low {n['Low']}, Not rated {n['Not rated']}.",
            "No rated area is in the High tier.",
            "Medium is not an alert: heightened care where heat is Moderate in an upper- or middle-third area, or High in a "
            "lower-third one.",
            f"{n['Medium']} areas are High or Medium: the top 10 are in the first table, the other {n['Medium'] - 10} in the "
            "table under it.",
            "North-Eastern Islands and Southern Islands have High heat but are Not rated: no HDB blocks to rate, so only the "
            "heat level is shown."]
        heat_risk_view(views, LATEST, missing=True)
        assert tier_counts(views) == {"No forecast": 55}
        assert [r["line"] for r in rows_of(views, "ds_briefing_lines")] == [
            head, "Tiers: High 0, Medium 0, Low 0, Not rated 0, No forecast 55."]
    finally:
        heat_risk_view(views, LATEST)


def test_notice_when_the_latest_date_is_before_today_in_singapore(views):
    try:
        heat_risk_view(views, date(2026, 10, 1))
        lines = [r["line"] for r in rows_of(views, "ds_briefing_lines")]
        assert lines[1] == "No forecast for today yet; this is the plan for Thursday, 1 October 2026."
    finally:
        heat_risk_view(views, LATEST)


def test_top_ten_then_every_other_high_or_medium_area_in_tier_then_tier_rank_order(views):
    lower = min(r["planning_area"] for r in views.sql("SELECT planning_area FROM area_vulnerability WHERE third = 'lower'").collect())
    want = [r.asDict() for r in views.sql(f"""
        SELECT {BB.area_name_sql('planning_area')} AS area, tier FROM area_heat_risk WHERE target_date = DATE'{LATEST}'
        ORDER BY CASE tier WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 WHEN 'Not rated' THEN 4 ELSE 5 END, tier_rank""").collect()]
    top, more = rows_of(views, "ds_top_areas"), rows_of(views, "ds_more_areas")
    assert [r["briefing_order"] for r in top + more] == list(range(1, len(top) + len(more) + 1))
    assert [(r["area"], r["tier"]) for r in top + more] == [(w["area"], w["tier"]) for w in want[:len(top) + len(more)]]
    assert {r["tier"] for r in more} <= {"High", "Medium"} and want[len(top) + len(more)]["tier"] not in ("High", "Medium")
    assert top[0]["area"] == "Toa Payoh" and lower.title() in [r["area"] for r in top + more]
    assert all(r["actions"] for r in top + more)


def test_why_in_a_sentence_is_the_dates_explanation_or_else_the_tier_sentence(views):
    """An area with a row for the date shows its sentence; any other, Bedok's row for the day before included, shows its
    tier sentence, so no cell is blank."""
    rows = rows_of(views, "ds_top_areas") + rows_of(views, "ds_more_areas")
    by = {r["area"]: r for r in rows}
    assert by["Toa Payoh"]["explanation"] == "High: a checked sentence."
    assert by["Bedok"]["explanation"] == by["Bedok"]["tier_sentence"]
    assert all(r["explanation"] == r["tier_sentence"] for a, r in by.items() if a != "Toa Payoh")
    assert all(r["explanation"] for r in rows) and len(by) == len(rows)


def test_no_more_areas_says_so(views):
    """With 10 or fewer High or Medium areas, the second table shows one plain row instead of an empty table."""
    sql = sql_of(next(d for d in DASH["datasets"] if d["name"] == "ds_more_areas")).replace("> 10 AND", "> 100 AND")
    assert [r["area"] for r in views.sql(sql).collect()] == ["None: every High or Medium area is in the top 10"]


def test_area_map_one_dot_per_area_inside_singapore_coloured_by_tier(views):
    rows = rows_of(views, "ds_area_map")
    assert len({r["area"] for r in rows}) == len(rows) == 55
    assert all(1.15 < r["lat"] < 1.48 and 103.6 < r["lon"] < 104.1 for r in rows)
    assert {r["tier"] for r in rows} <= set(BB.TIER_MAP_COLOURS)
    order = list(BB.TIER_MAP_COLOURS)
    assert [order.index(r["tier"]) for r in rows] == sorted(order.index(r["tier"]) for r in rows)  # legend order in the data too
    assert all(r["marker_size"] == max(int(r["rental_1_2_room"].replace(",", "")), 1) for r in rows)


def test_the_two_75_plus_reasons_read_as_one_phrase(views):
    a, b = BB._PHRASES["aged_75_plus"], BB._PHRASES["share_75_plus"]
    raw = {r["planning_area"]: r["reason"] for r in views.sql("SELECT planning_area, reason FROM area_vulnerability").collect()}
    both = {k for k, v in raw.items() if v in (f"{a}; {b}", f"{b}; {a}")}
    assert {"SERANGOON", "CLEMENTI"} <= both  # one order each in the fixture
    facts = {r["planning_area"].upper(): r["reason"] for r in rows_of(views, "ds_area_facts")}
    shown = [r["reason"] for name in ("ds_top_areas", "ds_more_areas") for r in rows_of(views, name)] + list(facts.values())
    assert all(facts[k] == BB.MERGED_75 for k in both)
    assert not any(a in s and b in s for s in shown if s)
    assert all(facts[k] == v for k, v in raw.items() if k not in both)  # every other reason unchanged


def test_areas_held_neutral_show_too_few_flats_not_a_share(views):
    small = {r["planning_area"] for r in views.sql("SELECT planning_area FROM area_vulnerability WHERE small_hdb").collect()}
    assert small == {"TANGLIN", "CHANGI", "DOWNTOWN CORE"}
    for r in rows_of(views, "ds_area_facts"):
        if r["planning_area"].upper() in small:
            assert r["refuge_beyond"] == r["park_beyond"] == "too few flats to measure", r
        else:
            assert re.fullmatch(r"\d{1,3}%", r["refuge_beyond"]) and re.fullmatch(r"\d{1,3}%", r["park_beyond"]), r


def test_trend_counts_each_station_once_per_day_and_category(views):
    got = {(str(r["sgt_date"]), r["heat_category"]): r["stations"] for r in rows_of(views, "ds_trend")}
    assert got == {("2026-10-01", "Moderate"): 1, ("2026-10-01", "High"): 1, ("2026-10-02", "Low"): 1}


def test_area_observed_is_one_row_per_area_and_day_latest_first(views):
    got = [(r["planning_area"], str(r["sgt_date"]), r["station_name"], r["max_wbgt"], r["heat_category"])
           for r in rows_of(views, "ds_area_observed")]
    assert got == [("Bedok", "2026-10-02", "One", 28.0, "Low"), ("Bedok", "2026-10-01", "One", 30.5, "Moderate"),
                   ("Tampines", "2026-10-01", "One", 30.5, "Moderate")]  # station S2 served no area that day
