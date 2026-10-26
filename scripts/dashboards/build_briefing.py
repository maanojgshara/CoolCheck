"""Build src/dashboards/briefing.lvdash.json, the briefing dashboard (plan approved 23 Oct 2026).

Run from the repo root:
    .venv\\Scripts\\python scripts/dashboards/build_briefing.py

Pages: Briefing, Blocks, Observed heat, About. The Blocks page points to the CoolCheck App for the what-if refuge. The
Observed heat page shows observed values only: the stations by daily NEA category, and for a chosen planning area its
nearest station's daily peak WBGT and category. The Briefing page reads gold.area_heat_risk for its latest target_date only: a headline
table ("Heat risk for <weekday, date>, prepared <scored_at> SGT", times converted to SGT in the SQL; a notice when that
date is before today in Singapore; the tier counts; the App's "No rated area is in the High tier." when no area is High and
at least one is Medium or Low; what Medium means; how many areas are High or Medium beyond the top 10; Not-rated areas with High
heat), the planning-area point map (one dot per area at its polygon's centroid, coloured by
tier, sized by 1-2 room rental flats), the top 10 in briefing order (tier, then tier_rank as built), every other High or
Medium area below them, and the observed 30-day trend from gold.observed_heat_daily. Both area tables have "Why, in a
sentence" after the tier: the area's sentence from gold.area_tier_explanation for the same date (written by
scripts/explanations/generate.py, docs/design/tier_explanations.md), or its tier sentence when the row is missing, so the
cell is never blank; no dataset calls ai_query. The tables show #, area, tier, the sentence, 1-2 room rental flats and the
actions; "Why this tier" and "Why vulnerable" are hidden (the sentence carries both), and the datasets keep their fields.
Queries use bare names, which the bundle's dataset_catalog and
dataset_schema point at <catalog>.gold: area_heat_risk, area_vulnerability, area_tier_explanation, block_vulnerability,
planning_area_map, refuge_layer, observed_heat_daily, score_weights, tier_actions. P(High), the score, model_version and
run_id are never read (tests/dashboards/test_briefing_dashboard.py checks every dataset).
Colours are coolcheck.briefing's, checked with coolcheck.palette; the observed heat categories take the live page's.
Planning-area names have a capital after each space and hyphen ("North-Eastern Islands"), as the App writes them.
The polygon maps were dropped on 24 Oct: the render test showed the server drops the custom-geometry region key, so
both choropleths stored without a region; the maps are point maps.
"""
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from coolcheck import briefing as B  # noqa: E402
from coolcheck import plan as P  # noqa: E402

OUT = REPO / "src/dashboards/briefing.lvdash.json"
DEFAULT_AREA = "Bedok"  # the area the Blocks and Observed heat pages open on (rank 1 for V on 23 Oct 2026)
# Colour scales in legend order. NEA heat-stress categories (Low to High): the live page's colours
# (src/dashboards/live_heat_stress.lvdash.json); tiers High to Low, then the grey ones; block points near to far, then refuges.
HEAT_COLOURS = {"Low": "#2f7fc1", "Moderate": "#fab219", "High": "#d03b3b"}
TIER_MAP_COLOURS = {**B.TIER_COLOURS, "Not rated": B.NEUTRAL, "No forecast": B.NEUTRAL}
POINT_LABELS = {"Block within 400 m of a refuge": "Block within 400 m", "Block beyond 400 m of a refuge": "Block beyond 400 m",
                "Refuge": "Refuge"}  # short legend labels on the Blocks map
POINT_MAP_COLOURS = {POINT_LABELS[k]: c for k, c in B.POINT_COLOURS.items()}
WITHIN_TIER = "the chance of High heat times vulnerability"  # tier_rank's order, described in words; the number is never shown
TOP = 10
APP_URL = "https://coolcheck-7474646896364032.aws.databricksapps.com"  # window B's approval App (dev), for the what-if
_PHRASES = {r["component"]: r["reason_phrase"] for r in csv.DictReader(open(REPO / "reference/score_weights.csv", encoding="utf-8"))}
# the two 75+ components read as one thing when they are an area's two reasons, so they show as one phrase
MERGED_75 = "many residents aged 75+, who are a high share of its residents"
TOO_FEW_FLATS = "too few flats to measure"  # the 400 m shares of an area held neutral for fewer than 1,000 HDB flats
NO_HIGH = P.no_tier_sentence("High")  # the App's sentence for the whole island: "No rated area is in the High tier."


def _q(s):
    return "'" + s.replace("'", "\\'") + "'"


def reason_sql(col):
    a, b = _PHRASES["aged_75_plus"], _PHRASES["share_75_plus"]
    return f"CASE WHEN {col} IN ({_q(f'{a}; {b}')}, {_q(f'{b}; {a}')}) THEN {_q(MERGED_75)} ELSE {col} END"


def share_sql(col):
    return f"CASE WHEN small_hdb THEN {_q(TOO_FEW_FLATS)} ELSE concat(format_number(100 * {col}, 0), '%') END"


def area_name_sql(col):
    """A planning area's name with a capital after each space and hyphen, as str.title() and the App's plan.area_name
    write it: initcap alone capitalises only after a space ("North-eastern Islands")."""
    return f"array_join(transform(split(initcap({col}), '-'), x -> concat(upper(substr(x, 1, 1)), substr(x, 2))), '-')"


TIER_ORDER = "CASE r.tier WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 WHEN 'Not rated' THEN 4 ELSE 5 END"
LATEST = """WITH latest AS (
  SELECT target_date, planning_area, heat_level, tier, tier_rank, tier_sentence, reason, actions, scored_at
  FROM area_heat_risk WHERE target_date = (SELECT max(target_date) FROM area_heat_risk)
)"""
ORDERED = f"""{LATEST},
ordered AS (
  SELECT r.planning_area, {area_name_sql('r.planning_area')} AS area, r.tier, r.heat_level, r.tier_sentence,
    coalesce(e.explanation, r.tier_sentence) AS explanation,
    coalesce({reason_sql('r.reason')}, '') AS reason, coalesce(r.actions, '') AS actions,
    coalesce(v.rental_1_2_room, 0) AS rental_1_2_room,
    row_number() OVER (ORDER BY {TIER_ORDER}, r.tier_rank) AS briefing_order
  FROM latest r LEFT JOIN area_vulnerability v ON v.planning_area = r.planning_area
    LEFT JOIN area_tier_explanation e ON e.target_date = r.target_date AND e.planning_area = r.planning_area
)"""
# Table columns stay numbers (a text column sorts "9,000" after "10,000" if a viewer clicks a header); format_number is
# used only where nothing sorts: the map tooltip and the Blocks map's detail text.
AREA_COLUMNS = "briefing_order, area, tier, explanation, tier_sentence, reason, rental_1_2_room, actions"
EXPLANATION_NOTE = ("Each sentence is written by Llama 3.3 70B through Databricks AI Functions from the row's facts; code "
                    "checks that it states the tier, heat level, third and each measure as given, and nothing but the "
                    "facts, or shows the template sentence.")
NAMES = "CASE WHEN size(nr) = 1 THEN nr[0] ELSE concat(array_join(slice(nr, 1, size(nr) - 1), ', '), ' and ', element_at(nr, -1)) END"
LONG_DATE = "date_format(target_date, 'EEEE, d MMMM yyyy')"
NOTICES = [  # copied exactly from docs/attribution.md (register notices 1, 3, 7, 9, 12, 14, 16, 19, 22, 23)
    "Contains information from Heat stress (WBGT) real-time readings accessed on 20 October 2026 from National Environment Agency via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence.",
    "Contains information from 24-hour Weather Forecast accessed on 20 October 2026 from National Environment Agency via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence.",
    "Contains information from Singapore Residents by Planning Area/Subzone, Age Group, Sex and Floor Area of Residence, June 2026 accessed on 21 October 2026 from Singapore Department of Statistics which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence.",
    "Contains information from HDB Property Information accessed on 21 October 2026 from Housing & Development Board via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence.",
    "Contains information from Dementia Friendly Go-To-Points (GTPs) accessed on 21 October 2026 from Ministry of Health via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence.",
    "Contains information from Community Club / PAssion WaVe Outlet accessed on 21 October 2026 from People's Association via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence.",
    "Contains information from NParks Parks and Nature Reserves accessed on 21 October 2026 from National Parks Board via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence.",
    "Contains information from Master Plan 2025 Planning Area Boundary (No Sea) accessed on 21 October 2026 from Urban Redevelopment Authority via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence.",
    "Contains information from Singapore Energy Statistics 2025, Chapter 3: Energy Consumption accessed on 21 October 2026 from Energy Market Authority which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence.",
    "Contains information from OneMap Search API accessed on 21 October 2026 from Singapore Land Authority (OneMap) which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence.",
]

DATASETS = {
    "ds_briefing_lines": ("Briefing headline", f"""
{LATEST},
d AS (
  SELECT max(target_date) AS target_date, max(scored_at) AS scored_at,
    count_if(tier = 'High') AS n_high, count_if(tier = 'Medium') AS n_medium, count_if(tier = 'Low') AS n_low,
    count_if(tier = 'Not rated') AS n_not_rated, count_if(tier = 'No forecast') AS n_no_forecast,
    count_if(tier = 'Medium' AND heat_level = 'High') AS n_medium_high_heat,
    array_sort(collect_list(CASE WHEN tier = 'Not rated' AND heat_level = 'High' THEN {area_name_sql('planning_area')} END)) AS nr
  FROM latest
),
today AS (SELECT to_date(from_utc_timestamp(current_timestamp(), 'Asia/Singapore')) AS sgt_today)
SELECT line FROM (
  SELECT 1 AS k, concat('Heat risk for ', {LONG_DATE}, ', prepared ',
    date_format(from_utc_timestamp(scored_at, 'Asia/Singapore'), 'd MMM yyyy HH:mm'), ' SGT') AS line FROM d
  UNION ALL
  SELECT 2, concat('No forecast for today yet; this is the plan for ', {LONG_DATE}, '.')
  FROM d CROSS JOIN today WHERE d.target_date < today.sgt_today
  UNION ALL
  SELECT 3, concat('Tiers: High ', n_high, ', Medium ', n_medium, ', Low ', n_low, ', Not rated ', n_not_rated,
    CASE WHEN n_no_forecast > 0 THEN concat(', No forecast ', n_no_forecast) ELSE '' END, '.') FROM d
  UNION ALL
  SELECT 4, {_q(NO_HIGH)} FROM d WHERE n_high = 0 AND n_medium + n_low > 0
  UNION ALL
  SELECT 5, concat('Medium is not an alert: heightened care where heat is Moderate in an upper- or middle-third area, or High in a lower-third one.',
    CASE WHEN n_medium_high_heat = 1 THEN ' One Medium area has High heat and is in the lower third for vulnerability.'
         WHEN n_medium_high_heat > 1 THEN concat(' ', n_medium_high_heat, ' Medium areas have High heat and are in the lower third for vulnerability.')
         ELSE '' END) FROM d WHERE n_medium > 0
  UNION ALL
  SELECT 6, concat(n_high + n_medium, ' areas are High or Medium: the top {TOP} are in the first table, the other ',
    n_high + n_medium - {TOP}, ' in the table under it.') FROM d WHERE n_high + n_medium > {TOP}
  UNION ALL
  SELECT 7, concat({NAMES}, CASE WHEN size(nr) = 1 THEN ' has High heat but is' ELSE ' have High heat but are' END,
    ' Not rated: no HDB blocks to rate, so only the heat level is shown.') FROM d WHERE size(nr) > 0
)
ORDER BY k
"""),
    "ds_area_map": ("Planning areas by tier", f"""
{ORDERED}
SELECT o.area, o.tier, o.tier_sentence, format_number(o.rental_1_2_room, 0) AS rental_1_2_room,
  greatest(o.rental_1_2_room, 1) AS marker_size,
  st_y(st_centroid(m.geometry)) AS lat, st_x(st_centroid(m.geometry)) AS lon
FROM ordered o JOIN planning_area_map m ON m.planning_area = o.planning_area
ORDER BY o.briefing_order
"""),
    "ds_top_areas": (f"Top {TOP} areas", f"""
{ORDERED}
SELECT {AREA_COLUMNS} FROM ordered WHERE briefing_order <= {TOP} ORDER BY briefing_order
"""),
    "ds_more_areas": ("Other High and Medium areas", f"""
{ORDERED}
SELECT {AREA_COLUMNS} FROM ordered WHERE briefing_order > {TOP} AND tier IN ('High', 'Medium')
UNION ALL
SELECT NULL, 'None: every High or Medium area is in the top {TOP}', NULL, NULL, NULL, NULL, NULL, NULL
WHERE NOT EXISTS (SELECT 1 FROM ordered WHERE briefing_order > {TOP} AND tier IN ('High', 'Medium'))
ORDER BY briefing_order
"""),
    "ds_trend": ("Observed heat, last 30 days", """
SELECT sgt_date, heat_category, heat_order, count(DISTINCT station_id) AS stations
FROM observed_heat_daily
GROUP BY sgt_date, heat_category, heat_order
ORDER BY sgt_date, heat_order
"""),
    "ds_area_observed": ("Observed heat per planning area", f"""
SELECT {area_name_sql('planning_area')} AS planning_area, sgt_date, station_name, round(max_wbgt, 1) AS max_wbgt, heat_category,
  heat_order
FROM observed_heat_daily
WHERE planning_area IS NOT NULL
ORDER BY planning_area, sgt_date DESC
"""),
    "ds_area_facts": ("Area facts", f"""
SELECT {area_name_sql('planning_area')} AS planning_area, initcap(third) AS third, {reason_sql('reason')} AS reason,
  aged_75_plus, rental_1_2_room, hdb_dwelling_units_confirmed, {share_sql('refuge_beyond_400m')} AS refuge_beyond,
  {share_sql('park_beyond_400m')} AS park_beyond, coalesce(neutral_components, '') AS held_neutral
FROM area_vulnerability
"""),
    "ds_blocks": ("Blocks in priority order", f"""
SELECT {area_name_sql('planning_area')} AS planning_area, priority, concat(blk_no, ' ', street) AS block,
  rental_1_2_room, total_dwelling_units,
  refuge_main_name, CAST(round(refuge_main_m) AS INT) AS refuge_m,
  CASE WHEN refuge_within_400m THEN 'yes' ELSE 'no' END AS refuge_400m,
  park_main_name, CAST(round(park_main_m) AS INT) AS park_m,
  CASE WHEN park_within_400m THEN 'yes' ELSE 'no' END AS park_400m,
  CASE WHEN confirmed THEN '' ELSE 'coordinate from a tenant record' END AS note
FROM block_vulnerability
ORDER BY planning_area, priority
"""),
    "ds_points": ("Blocks and refuges", f"""
SELECT {area_name_sql('planning_area')} AS planning_area, lat, lon,
  CASE WHEN refuge_within_400m THEN 'Block within 400 m' ELSE 'Block beyond 400 m' END AS point_type,
  CASE WHEN refuge_within_400m THEN 1 ELSE 2 END AS point_order,
  concat(blk_no, ' ', street) AS label, greatest(rental_1_2_room, 1) AS marker_size,
  concat('priority ', CAST(priority AS STRING), '; 1-2 room rental flats ', format_number(rental_1_2_room, 0)) AS detail
FROM block_vulnerability
UNION ALL
SELECT {area_name_sql('planning_area')}, lat, lon, 'Refuge', 3, name, 30, refuge_type
FROM refuge_layer
ORDER BY point_order
"""),
    "ds_weights": ("Weights", """
SELECT component, sub_index, weight, direction, small_area_rule, reason_phrase,
  replace(review_status, ' (Guide decision 9)', '') AS review_status
FROM score_weights
ORDER BY sort_order
"""),
    "ds_actions": ("Actions per tier", """
SELECT tier, actions, review_status
FROM tier_actions
ORDER BY CASE tier WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END
"""),
}


def dataset(name):
    display, sql = DATASETS[name]
    return {"name": name, "displayName": display, "queryLines": [ln + "\n" for ln in sql.strip().splitlines()]}


def field(name):
    return {"name": name, "expression": f"`{name}`"}


def text(name, lines):
    return {"name": name, "multilineTextboxSpec": {"lines": lines}}


def table(name, ds, columns, title):
    return {"name": name,
            "queries": [{"name": "main_query", "query": {"datasetName": ds, "fields": [field(c) for c, _ in columns],
                                                         "disaggregated": True}}],
            "spec": {"version": 2, "widgetType": "table",
                     "encodings": {"columns": [{"fieldName": c, "displayName": d} for c, d in columns]},
                     "frame": {"showTitle": True, "title": title}}}


def colour_scale(colours):
    """Fixed colours per category, with the legend in the dict's order (the datasets are ordered the same way too)."""
    return {"type": "categorical", "mappings": [{"value": v, "color": c} for v, c in colours.items()],
            "sort": {"by": "custom-order", "orderedValues": list(colours)}}


def point_map(name, ds, colour_field, colour_display, colours, size_display, extra, title):
    """Symbol map over lat and lon, coloured by a category with fixed colours and sized by marker_size."""
    return {"name": name,
            "queries": [{"name": "main_query", "query": {"datasetName": ds, "fields": [
                field(c) for c in ("lat", "lon", colour_field, "marker_size", *[c for c, _ in extra])], "disaggregated": True}}],
            "spec": {"version": 2, "widgetType": "symbol-map",
                     "encodings": {"coordinates": {"latitude": {"fieldName": "lat"}, "longitude": {"fieldName": "lon"}},
                                   "color": {"fieldName": colour_field, "displayName": colour_display,
                                             "scale": colour_scale(colours)},
                                   "size": {"fieldName": "marker_size", "displayName": size_display,
                                            "scale": {"type": "quantitative"}},
                                   "extra": [{"fieldName": c, "displayName": d} for c, d in extra]},
                     "mark": {"opacity": 0.85},
                     "frame": {"showTitle": True, "title": title}}}


def trend_chart(name):
    return {"name": name,
            "queries": [{"name": "main_query", "query": {"datasetName": "ds_trend", "fields": [
                {"name": "daily(sgt_date)", "expression": 'DATE_TRUNC("DAY", `sgt_date`)'},
                {"name": "sum(stations)", "expression": "SUM(`stations`)"},
                field("heat_category")], "disaggregated": False}}],
            "spec": {"version": 3, "widgetType": "bar",
                     "encodings": {"x": {"fieldName": "daily(sgt_date)", "displayName": "Day (SGT)", "scale": {"type": "temporal"}},
                                   "y": {"fieldName": "sum(stations)", "displayName": "WBGT stations",
                                         "scale": {"type": "quantitative"}},
                                   "color": {"fieldName": "heat_category", "displayName": "Observed heat (NEA)",
                                             "scale": colour_scale(HEAT_COLOURS)}},
                     "frame": {"showTitle": True,
                               "title": "Observed heat, last 30 completed days: WBGT stations by their daily NEA category"}}}


def area_observed_chart():
    return {"name": "area-observed-chart",
            "queries": [{"name": "main_query", "query": {"datasetName": "ds_area_observed", "fields": [
                {"name": "daily(sgt_date)", "expression": 'DATE_TRUNC("DAY", `sgt_date`)'},
                {"name": "max(max_wbgt)", "expression": "MAX(`max_wbgt`)"},
                field("heat_category")], "disaggregated": False}}],
            "spec": {"version": 3, "widgetType": "bar",
                     "encodings": {"x": {"fieldName": "daily(sgt_date)", "displayName": "Day (SGT)", "scale": {"type": "temporal"}},
                                   "y": {"fieldName": "max(max_wbgt)", "displayName": "Peak WBGT (°C)",
                                         "scale": {"type": "quantitative"}},
                                   "color": {"fieldName": "heat_category", "displayName": "Observed heat (NEA)",
                                             "scale": colour_scale(HEAT_COLOURS)}},
                     "frame": {"showTitle": True,
                               "title": "The area's nearest WBGT station: the day's peak WBGT, coloured by its NEA category"}}}


def at(widget, x, y, w, h):
    return {"widget": widget, "position": {"x": x, "y": y, "width": w, "height": h}}


# "Why this tier" and "Why vulnerable" hidden (the user, 26 Oct 23:28): the sentence begins with the tier sentence and names
# the same measures with their values, and the two columns made the table scroll sideways; the datasets keep both fields
AREA_TABLE = [("briefing_order", "#"), ("area", "Planning area"), ("tier", "Tier"), ("explanation", "Why, in a sentence"),
              ("rental_1_2_room", "1-2 room rental flats"), ("actions", "Actions (a proposal)")]


def build():
    lines = table("briefing-lines", "ds_briefing_lines", [("line", "Briefing")], "Briefing")
    briefing_page = {
        "name": "briefing", "displayName": "Briefing", "pageType": "PAGE_TYPE_CANVAS", "layoutVersion": "GRID_V1",
        "layout": [
            at(lines, 0, 0, 12, 5),
            at(point_map("area-map", "ds_area_map", "tier", "Tier", TIER_MAP_COLOURS, "1-2 room rental flats",
                         [("area", "Planning area"), ("tier_sentence", "Tier"), ("rental_1_2_room", "1-2 room rental flats")],
                         "Planning areas by tier (dot size: 1-2 room rental flats; grey: not rated)"), 0, 5, 7, 10),
            at(text("briefing-guide", [
                "### How to read this\n", "\n",
                "Each dot is a planning area, coloured by its tier: the forecast heat level for the day (NEA's Low, Moderate "
                "or High) crossed with how vulnerable the area is. Grey areas have no HDB blocks to rate and show the heat "
                "level only. The About page has the full rule.\n", "\n",
                "Heat is forecast per planning area; blocks rank vulnerability only, never heat.\n", "\n",
                "**Blocks to call first.** Open the **Blocks** page and pick the area: it lists the blocks with the most 1-2 "
                "room rental flats first, then those farthest from a refuge, with the nearest refuge and park. CoolCheck holds "
                "no personal data: match the blocks against your own client list.\n", "\n",
                "Actions are a proposal, not yet reviewed by a practitioner. Not official advice.\n"]), 7, 5, 5, 10),
            at(table("top-areas", "ds_top_areas", AREA_TABLE,
                     f"Top {TOP} areas: by tier, then within a tier by {WITHIN_TIER} (the number is never shown)"),
               0, 15, 12, 9),
            at(text("explanation-note", [EXPLANATION_NOTE + "\n"]), 0, 24, 12, 1),
            # height 8 showed 12 of the 13 rows on 24 Oct; 10 leaves room for a few more
            at(table("more-areas", "ds_more_areas", AREA_TABLE, f"Every other High or Medium area, after the top {TOP}, in the same order"),
               0, 25, 12, 10),
            at(trend_chart("trend-chart"), 0, 35, 12, 6),
        ]}
    area_filter = {
        "name": "area-filter",
        "queries": [{"name": f"{ds}_area", "query": {"datasetName": ds, "fields": [field("planning_area")],
                                                     "disaggregated": False}}
                    for ds in ("ds_area_facts", "ds_blocks", "ds_points")],
        "spec": {"version": 2, "widgetType": "filter-single-select",
                 "encodings": {"fields": [{"fieldName": "planning_area", "displayName": "Planning area", "queryName": f"{ds}_area"}
                                          for ds in ("ds_area_facts", "ds_blocks", "ds_points")]},
                 "selection": {"defaultSelection": {"values": {"dataType": "STRING", "values": [{"value": DEFAULT_AREA}]}}},
                 "frame": {"showTitle": True, "title": "Planning area"}}}
    points = point_map("points-map", "ds_points", "point_type", "Distance to the nearest refuge", POINT_MAP_COLOURS,
                       "1-2 room rental flats (refuges fixed)", [("label", "Block or refuge"), ("detail", "Detail")],
                       "Blocks by distance to the nearest refuge (size: 1-2 room rental flats), and the refuges")
    blocks_page = {
        "name": "blocks", "displayName": "Blocks", "pageType": "PAGE_TYPE_CANVAS", "layoutVersion": "GRID_V1",
        "layout": [
            at(text("blocks-title", ["## Blocks: where to start in an area\n"]), 0, 0, 12, 1),
            at(text("blocks-subtitle", [
                "Blocks rank vulnerability only, never heat: heat is forecast per planning area. Pick an area; the list puts "
                "the blocks with the most 1-2 room rental flats first, then those farthest from a refuge. CoolCheck holds no "
                "personal data: match the blocks against your own client list.\n"]), 0, 1, 12, 2),
            at(text("app-pointer", [f"To test a new refuge near a block, open the CoolCheck App ([{APP_URL}]({APP_URL})) "
                                    "and use 'What if a refuge opened here?'\n"]), 0, 3, 12, 1),
            at(area_filter, 0, 4, 4, 3),
            at(table("area-facts", "ds_area_facts", [
                ("planning_area", "Planning area"), ("third", "Vulnerability third"), ("reason", "Why"),
                ("aged_75_plus", "Residents 75+"), ("rental_1_2_room", "1-2 room rental flats"),
                ("hdb_dwelling_units_confirmed", "HDB flats"), ("refuge_beyond", "Flats beyond 400 m of a refuge"),
                ("park_beyond", "Flats beyond 400 m of a park"), ("held_neutral", "Held at the middle (0.5)")],
                "The area"), 4, 4, 8, 3),
            at(points, 0, 7, 12, 9),
            at(table("blocks-table", "ds_blocks", [
                ("priority", "Priority"), ("block", "Block"), ("rental_1_2_room", "1-2 room rental flats"),
                ("total_dwelling_units", "Flats"), ("refuge_main_name", "Nearest refuge"), ("refuge_m", "Refuge (m)"),
                ("refuge_400m", "Refuge within 400 m"), ("park_main_name", "Nearest park"), ("park_m", "Park (m)"),
                ("park_400m", "Park within 400 m"), ("note", "Note")],
                "Blocks in priority order (straight-line distances)"), 0, 16, 12, 9),
        ]}
    observed_filter = {
        "name": "observed-area-filter",
        "queries": [{"name": "ds_area_observed_area", "query": {"datasetName": "ds_area_observed",
                                                                "fields": [field("planning_area")], "disaggregated": False}}],
        "spec": {"version": 2, "widgetType": "filter-single-select",
                 "encodings": {"fields": [{"fieldName": "planning_area", "displayName": "Planning area",
                                           "queryName": "ds_area_observed_area"}]},
                 "selection": {"defaultSelection": {"values": {"dataType": "STRING", "values": [{"value": DEFAULT_AREA}]}}},
                 "frame": {"showTitle": True, "title": "Planning area"}}}
    observed_page = {
        "name": "observed", "displayName": "Observed heat", "pageType": "PAGE_TYPE_CANVAS", "layoutVersion": "GRID_V1",
        "layout": [
            at(text("observed-title", ["## Observed heat: the last 30 completed days\n"]), 0, 0, 12, 1),
            at(text("observed-subtitle", [
                "Observed values only, never forecasts; the forecast is on the Briefing page. Each WBGT station's observed "
                "daily heat-stress category (NEA's Low, Moderate or High) for the last 30 completed days in Singapore time; "
                "today's readings are still coming in and are left out.\n"]), 0, 1, 12, 2),
            at(trend_chart("observed-trend-chart"), 0, 3, 12, 7),
            at(observed_filter, 0, 10, 4, 2),
            at(text("observed-area-guide", [
                "Pick a planning area to see the WBGT station nearest to it each day, the day's highest reading and its "
                "category. Heat is measured at stations and shown per planning area, never per block.\n"]), 4, 10, 8, 2),
            at(area_observed_chart(), 0, 12, 7, 7),
            at(table("area-observed-table", "ds_area_observed", [
                ("sgt_date", "Day (SGT)"), ("station_name", "Station"), ("max_wbgt", "Peak WBGT (°C)"),
                ("heat_category", "Observed heat (NEA)")], "Day by day, latest first"), 7, 12, 5, 7),
        ]}
    matrix = ["| Forecast heat (NEA) / vulnerability | Lower third | Middle third | Upper third |\n", "|---|---|---|---|\n",
              "| Low | Low | Low | Low |\n", "| Moderate | Low | Medium | Medium |\n", "| High | Medium | High | High |\n"]
    about_page = {
        "name": "about", "displayName": "About", "pageType": "PAGE_TYPE_CANVAS", "layoutVersion": "GRID_V1",
        "layout": [
            at(text("about-title", ["## About this briefing\n"]), 0, 0, 12, 1),
            at(text("about-method", [
                "**What a tier means.** Each planning area's tier crosses the forecast heat level for the day (NEA's heat-stress "
                "categories: Low, Moderate, High) with how vulnerable the area is, its third among the 32 rated areas:\n", "\n",
                *matrix, "\n",
                "Heat is forecast per planning area, from its nearest WBGT station; blocks rank vulnerability only, never heat. "
                f"Within a tier, areas are ordered by {WITHIN_TIER}: the forecast's chance of High heat for the area times "
                "its vulnerability index. That number only sets the order and is never shown.\n", "\n",
                "**How vulnerability is measured.** Seven measures, each turned into a percentile among the rated areas (higher "
                "means more vulnerable) and weighted as in the table below: residents aged 75+ and their share of residents; 1-2 "
                "room rental flats; a small hot-month rise in 1-2 room electricity use (may indicate less air-con use); HDB flats "
                "beyond 400 m of a refuge; refuges per 1,000 residents aged 65+; HDB flats beyond 400 m of a park. A share or a "
                "rate over fewer than 1,000 people or flats is held at the middle (0.5); counts keep their value. The top 11 "
                "areas are the upper third, the next 11 the middle, the last 10 the lower. Areas without HDB blocks are not "
                "rated and show the heat level only.\n"]), 0, 1, 12, 10),
            at(table("weights-table", "ds_weights", [
                ("component", "Measure"), ("sub_index", "Part"), ("weight", "Weight"), ("direction", "More vulnerable when"),
                ("small_area_rule", "Held at 0.5 when small"), ("reason_phrase", "In plain words"), ("review_status", "Status")],
                "Weights of the vulnerability index"), 0, 11, 12, 6),
            at(table("actions-table", "ds_actions", [("tier", "Tier"), ("actions", "Actions"), ("review_status", "Status")],
                     "Actions per tier"), 0, 17, 12, 4),
            at(text("about-limits", [
                "**Limits.** The weights are a judgement, not fitted (there is no open outcome data to fit them to), and like the "
                "actions they are not yet reviewed by a practitioner. The Active Ageing Centre list is partial (93 of about 223), "
                "so distances overstate the gap where centres are missing. Distances are straight lines, not walking routes. "
                "Not official advice. CoolCheck holds no personal data.\n"]), 0, 21, 12, 3),
            at(text("about-sources", ["**Sources.**\n", "\n", *[f"- {n}\n" for n in NOTICES]]), 0, 24, 12, 9),
        ]}
    return {
        "datasets": [dataset(n) for n in DATASETS],
        "pages": [briefing_page, blocks_page, observed_page, about_page],
        "uiSettings": {"theme": {
            "canvasBackgroundColor": {"light": "#FCFCFC", "dark": "#1F272D"},
            "widgetBackgroundColor": {"light": "#FFFFFF", "dark": "#11171C"},
            "widgetBorderColor": {"light": "#FFFFFF", "dark": "#11171C"},
            "fontColor": {"light": "#11171C", "dark": "#E8ECF0"},
            "selectionColor": {"light": "#2272B4", "dark": "#8ACAFF"},
            "visualizationColors": [*B.TIER_COLOURS.values(), B.NEUTRAL, *B.POINT_COLOURS.values()],
            "widgetHeaderAlignment": "LEFT"}},
    }


def main():
    OUT.write_bytes((json.dumps(build(), indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    print(f"wrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
