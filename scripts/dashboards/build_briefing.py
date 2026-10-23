"""Build src/dashboards/briefing.lvdash.json, the briefing dashboard (plan approved 23 Oct 2026).

Run from the repo root:
    .venv\\Scripts\\python scripts/dashboards/build_briefing.py

This version has the Blocks and About pages. The Briefing page (gold.area_heat_risk, headed "Heat risk for <weekday,
date>, prepared <scored_at> SGT") waits for window B's gold.heat_forecast, and the observed-heat page for the final check
to be scored. Queries use bare names, which the bundle's dataset_catalog and dataset_schema point at <catalog>.gold:
area_vulnerability, block_vulnerability, planning_area_map, refuge_layer, park_layer, score_weights, tier_actions.
P(High) and the score are never read (tests/dashboards/test_briefing_dashboard.py checks every dataset for the
forbidden words). Colours are coolcheck.briefing's, checked with coolcheck.palette. The choropleths' custom-geometry
region keys are not documented in the dashboard skill and stay unverified until the render test.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from coolcheck import briefing as B  # noqa: E402

OUT = REPO / "src/dashboards/briefing.lvdash.json"
DEFAULT_AREA = "BEDOK"  # the area the Blocks page opens on (rank 1 for V on 23 Oct 2026)
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
    "ds_thirds_map": ("Vulnerability third map", """
SELECT m.planning_area AS area_name, m.geometry, v.third,
  CASE v.third WHEN 'lower' THEN 1 WHEN 'middle' THEN 2 WHEN 'upper' THEN 3 END AS third_code
FROM planning_area_map m JOIN area_vulnerability v ON v.planning_area = m.planning_area
"""),
    "ds_area_facts": ("Area facts", """
SELECT planning_area, initcap(third) AS third, reason, aged_75_plus, rental_1_2_room, hdb_dwelling_units_confirmed,
  concat(format_number(100 * refuge_beyond_400m, 0), '%') AS refuge_beyond,
  concat(format_number(100 * park_beyond_400m, 0), '%') AS park_beyond,
  coalesce(neutral_components, '') AS held_neutral
FROM area_vulnerability
"""),
    "ds_blocks": ("Blocks in priority order", """
SELECT planning_area, priority, concat(blk_no, ' ', street) AS block, rental_1_2_room, total_dwelling_units,
  refuge_main_name, CAST(round(refuge_main_m) AS INT) AS refuge_m,
  CASE WHEN refuge_within_400m THEN 'yes' ELSE 'no' END AS refuge_400m,
  park_main_name, CAST(round(park_main_m) AS INT) AS park_m,
  CASE WHEN park_within_400m THEN 'yes' ELSE 'no' END AS park_400m,
  CASE WHEN confirmed THEN '' ELSE 'coordinate from a tenant record' END AS note
FROM block_vulnerability
ORDER BY planning_area, priority
"""),
    "ds_points": ("Blocks and refuges", """
SELECT planning_area, lat, lon,
  CASE WHEN refuge_within_400m THEN 'Block within 400 m of a refuge' ELSE 'Block beyond 400 m of a refuge' END AS point_type,
  concat(blk_no, ' ', street) AS label, greatest(rental_1_2_room, 1) AS marker_size,
  concat('priority ', CAST(priority AS STRING), '; 1-2 room rental flats ', CAST(rental_1_2_room AS STRING)) AS detail
FROM block_vulnerability
UNION ALL
SELECT planning_area, lat, lon, 'Refuge' AS point_type, name AS label, 30 AS marker_size, refuge_type AS detail
FROM refuge_layer
"""),
    "ds_parks": ("Parks", """
SELECT planning_area, park_name, geometry, 1 AS park
FROM park_layer
"""),
    "ds_weights": ("Weights", """
SELECT component, sub_index, weight, direction, small_area_rule, reason_phrase, review_status
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


def geometry_map(name, ds, key, colour_field, colour_display, start, end, title):
    """Choropleth with custom geometry: the geometry as a FIRST measure per key, coloured by a numeric measure."""
    agg = f"max({colour_field})"
    return {"name": name,
            "queries": [{"name": "main_query", "query": {"datasetName": ds, "fields": [
                field(key),
                {"name": "geojson", "expression": "ST_ASGEOJSON(FIRST(`geometry`))"},
                {"name": agg, "expression": f"MAX(`{colour_field}`)"}], "disaggregated": False}}],
            "spec": {"version": 1, "widgetType": "choropleth-map",
                     "encodings": {"region": {"regionType": "geometry", "fieldName": "geojson"},
                                   "color": {"fieldName": agg, "displayName": colour_display,
                                             "scale": {"type": "quantitative",
                                                       "colorRamp": {"mode": "custom-sequential",
                                                                     "colors": {"start": start, "end": end}}}},
                                   "extra": [{"fieldName": key, "displayName": "Name"}]},
                     "frame": {"showTitle": True, "title": title}}}


def at(widget, x, y, w, h):
    return {"widget": widget, "position": {"x": x, "y": y, "width": w, "height": h}}


def build():
    area_filter = {
        "name": "area-filter",
        "queries": [{"name": f"{ds}_area", "query": {"datasetName": ds, "fields": [field("planning_area")],
                                                     "disaggregated": False}}
                    for ds in ("ds_area_facts", "ds_blocks", "ds_points", "ds_parks")],
        "spec": {"version": 2, "widgetType": "filter-single-select",
                 "encodings": {"fields": [{"fieldName": "planning_area", "displayName": "Planning area", "queryName": f"{ds}_area"}
                                          for ds in ("ds_area_facts", "ds_blocks", "ds_points", "ds_parks")]},
                 "selection": {"defaultSelection": {"values": {"dataType": "STRING", "values": [{"value": DEFAULT_AREA}]}}},
                 "frame": {"showTitle": True, "title": "Planning area"}}}
    points = {
        "name": "points-map",
        "queries": [{"name": "main_query", "query": {"datasetName": "ds_points", "fields": [
            field(c) for c in ("lat", "lon", "point_type", "marker_size", "label", "detail")], "disaggregated": True}}],
        "spec": {"version": 2, "widgetType": "symbol-map",
                 "encodings": {"coordinates": {"latitude": {"fieldName": "lat"}, "longitude": {"fieldName": "lon"}},
                               "color": {"fieldName": "point_type", "displayName": "Point",
                                         "scale": {"type": "categorical",
                                                   "mappings": [{"value": v, "color": c} for v, c in B.POINT_COLOURS.items()]}},
                               "size": {"fieldName": "marker_size", "displayName": "1-2 room rental flats (refuges fixed)",
                                        "scale": {"type": "quantitative"}},
                               "extra": [{"fieldName": "label", "displayName": "Block or refuge"},
                                         {"fieldName": "detail", "displayName": "Detail"}]},
                 "mark": {"opacity": 0.85},
                 "frame": {"showTitle": True, "title": "Blocks (size: 1-2 room rental flats) and refuges in the area"}}}
    blocks_page = {
        "name": "blocks", "displayName": "Blocks", "pageType": "PAGE_TYPE_CANVAS", "layoutVersion": "GRID_V1",
        "layout": [
            at(text("blocks-title", ["## Blocks: where to start in an area\n"]), 0, 0, 12, 1),
            at(text("blocks-subtitle", [
                "Blocks rank vulnerability only, never heat: heat is forecast per planning area. Pick an area; the list puts "
                "the blocks with the most 1-2 room rental flats first, then those farthest from a refuge. CoolCheck holds no "
                "personal data: match the blocks against your own client list.\n"]), 0, 1, 12, 2),
            at(area_filter, 0, 3, 4, 3),
            at(table("area-facts", "ds_area_facts", [
                ("planning_area", "Planning area"), ("third", "Vulnerability third"), ("reason", "Why"),
                ("aged_75_plus", "Residents 75+"), ("rental_1_2_room", "1-2 room rental flats"),
                ("hdb_dwelling_units_confirmed", "HDB flats"), ("refuge_beyond", "Flats beyond 400 m of a refuge"),
                ("park_beyond", "Flats beyond 400 m of a park"), ("held_neutral", "Held at the middle (0.5)")],
                "The area"), 4, 3, 8, 3),
            at(geometry_map("thirds-map", "ds_thirds_map", "area_name", "third_code", "Vulnerability third (1 lower, 3 upper)",
                            B.THIRD_COLOURS["lower"], B.THIRD_COLOURS["upper"],
                            "Vulnerability third by planning area (rated areas; the others have no HDB blocks)"), 0, 6, 6, 9),
            at(points, 6, 6, 6, 9),
            at(table("blocks-table", "ds_blocks", [
                ("priority", "Priority"), ("block", "Block"), ("rental_1_2_room", "1-2 room rental flats"),
                ("total_dwelling_units", "Flats"), ("refuge_main_name", "Nearest refuge"), ("refuge_m", "Refuge (m)"),
                ("refuge_400m", "Refuge within 400 m"), ("park_main_name", "Nearest park"), ("park_m", "Park (m)"),
                ("park_400m", "Park within 400 m"), ("note", "Note")],
                "Blocks in priority order (straight-line distances)"), 0, 15, 12, 9),
            at(geometry_map("parks-map", "ds_parks", "park_name", "park", "Park", B.PARK_COLOUR, B.PARK_COLOUR,
                            "Parks in the area (NParks, without the nature reserves)"), 0, 24, 6, 7),
            at(text("what-if", ["### What if a refuge were added here?\n",
                                "Reserved for the what-if refuge result (window B's `what_if_add_refuge`, Saturday). Not built yet.\n"]),
               6, 24, 6, 7),
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
                "The forecast's probability only orders areas inside a tier and is never shown.\n", "\n",
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
        "pages": [blocks_page, about_page],
        "uiSettings": {"theme": {
            "canvasBackgroundColor": {"light": "#FCFCFC", "dark": "#1F272D"},
            "widgetBackgroundColor": {"light": "#FFFFFF", "dark": "#11171C"},
            "widgetBorderColor": {"light": "#FFFFFF", "dark": "#11171C"},
            "fontColor": {"light": "#11171C", "dark": "#E8ECF0"},
            "selectionColor": {"light": "#2272B4", "dark": "#8ACAFF"},
            "visualizationColors": [*B.TIER_COLOURS.values(), B.NEUTRAL, *B.THIRD_COLOURS.values(), B.PARK_COLOUR],
            "widgetHeaderAlignment": "LEFT"}},
    }


def main():
    OUT.write_bytes((json.dumps(build(), indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    print(f"wrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
