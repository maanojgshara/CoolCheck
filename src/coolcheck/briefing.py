"""The briefing dashboard's gold views and colours (Guide §14.1, decision 9; plan approved 23 Oct 2026).

Four views give the dashboard bare names under <catalog>.gold, so the same JSON deploys to any catalog:
planning_area_map (the Master Plan 2025 polygons as GEOMETRY, SRID 4326, the only SRID the AI/BI maps draw),
refuge_layer (the main refuge set), park_layer (main-set parks, one row per park and planning area it touches) and
observed_heat_daily (usable daily WBGT labels of the last 30 completed SGT days, with the planning areas each station
serves that day). The SQL builders take table names, so the tests can point them at temp views.

Colours were checked with coolcheck.palette (the dataviz validator's port): every pair at least 8 under protan, deutan
and tritan, and at least 15 under normal vision (all pairs, since on a map any two can touch); the vulnerability thirds
are a one-hue ramp checked with the ordinal checks, and the neutral grey stands apart from each step.
"""
import re

TIER_COLOURS = {"High": "#9b2226", "Medium": "#ee9b00", "Low": "#3a8f8a"}
NEUTRAL = "#dcdcdc"  # not rated, or no data
THIRD_COLOURS = {"lower": "#a9a3d6", "middle": "#7262b8", "upper": "#45207f"}
POINT_COLOURS = {"Block within 400 m of a refuge": "#2a78d6", "Block beyond 400 m of a refuge": "#eb6834",
                 "Refuge": "#1baf7a"}
PARK_COLOUR = "#5aa469"
# never in a dashboard dataset, matched as whole words (gold.score_weights is fine; a column named score is not)
FORBIDDEN = ("heat_forecast", "p_low", "p_moderate", "p_high", "score")
OBSERVED_DAYS = 30

_NAME = re.compile(r"^[A-Za-z0-9_`.]+$")


def _t(name):
    if not _NAME.match(name):
        raise ValueError(f"bad table name: {name!r}")
    return name


MAP_COLUMNS = [
    ("planning_area", "Master Plan 2025 planning area (all 55)."),
    ("planning_area_code", "Master Plan 2025 planning area code."),
    ("region", "Master Plan 2025 region."),
    ("geometry", "The area's polygon as GEOMETRY(4326) (WGS84), from silver.planning_area_boundary; for the AI/BI maps."),
]
REFUGE_LAYER_COLUMNS = [
    ("refuge_id", "refuge_points.refuge_id."),
    ("name", "Refuge name."),
    ("refuge_type", "Community club; Community club (temporary office); or Active Ageing Centre (partial list: 93 of about 223)."),
    ("postal_code", "6-digit postal code."),
    ("planning_area", "Master Plan 2025 planning area containing the refuge."),
    ("planning_area_code", "Master Plan 2025 planning area code."),
    ("lat", "WGS84 latitude."),
    ("lon", "WGS84 longitude."),
]
PARK_LAYER_COLUMNS = [
    ("park_id", "park_polygons.park_id (NParks main set)."),
    ("park_name", "NParks park name."),
    ("planning_area", "A planning area the park touches with a positive area (one row per park and area)."),
    ("planning_area_code", "Master Plan 2025 planning area code."),
    ("geometry", "The whole park's polygon as GEOMETRY(4326), from silver.park_polygons."),
    ("park_area_m2", "The whole park's area in SVY21, m2."),
    ("area_in_planning_area_m2", "The part of the park inside this planning area, SVY21 m2."),
]
OBSERVED_COLUMNS = [
    ("sgt_date", f"A completed SGT day among the last {OBSERVED_DAYS} (today's provisional label is left out)."),
    ("station_id", "WBGT station."),
    ("station_name", "WBGT station name."),
    ("heat_category", "The station's observed daily NEA heat-stress category (Low, Moderate or High), usable labels only."),
    ("heat_order", "1 Low, 2 Moderate, 3 High, for ordering and colour."),
    ("max_wbgt", "The day's highest valid WBGT reading at the station, deg C."),
    ("planning_area", "A planning area that took this station that day (gold.area_nearest_station_daily); null if none, so every station counts once in the station counts."),
]


def planning_area_map_sql(boundary):
    return f"""
SELECT planning_area, planning_area_code, region, st_geomfromwkt(geometry_wkt, 4326) AS geometry
FROM {_t(boundary)}
"""


def refuge_layer_sql(refuges):
    return f"""
SELECT refuge_id, name,
  CASE WHEN layer = 'aac_partial' THEN 'Active Ageing Centre (partial list)'
       WHEN status = 'temp_office' THEN 'Community club (temporary office)'
       ELSE 'Community club' END AS refuge_type,
  postal_code, planning_area, planning_area_code, lat, lon
FROM {_t(refuges)}
WHERE in_main
"""


def park_layer_sql(parks, membership):
    return f"""
SELECT p.park_id, p.name AS park_name, m.planning_area, m.planning_area_code,
       st_geomfromwkt(p.geometry_wkt, 4326) AS geometry, p.area_m2 AS park_area_m2, m.area_in_planning_area_m2
FROM {_t(parks)} p JOIN {_t(membership)} m ON m.park_id = p.park_id
WHERE p.in_main
"""


def observed_heat_daily_sql(labels, nearest, days=OBSERVED_DAYS):
    """Usable labels of the last `days` completed SGT days; today (provisional) is left out. SGT through
    convert_timezone, so the result does not depend on the session time zone (the warehouse runs in UTC)."""
    return f"""
WITH today AS (SELECT to_date(convert_timezone('Asia/Singapore', current_timestamp())) AS d),
s AS (
  SELECT l.sgt_date, l.station_id, l.station_name, l.label AS heat_category, l.max_wbgt
  FROM {_t(labels)} l CROSS JOIN today
  WHERE l.usable AND l.sgt_date < today.d AND l.sgt_date >= date_sub(today.d, {int(days)})
)
SELECT s.sgt_date, s.station_id, s.station_name, s.heat_category,
  CASE s.heat_category WHEN 'Low' THEN 1 WHEN 'Moderate' THEN 2 WHEN 'High' THEN 3 END AS heat_order,
  s.max_wbgt, n.planning_area
FROM s LEFT JOIN {_t(nearest)} n ON n.target_date = s.sgt_date AND n.station_id = s.station_id
"""
