"""H10: the nearest reporting WBGT station per planning area for each target date.

A station is reporting for target date T if it has at least one counted WBGT reading in the 7 days before the
cut-off (T 00:15 SGT, §14.4): [cut-off - 7 days, cut-off). Nothing from after the cut-off is used, so the target day's
own readings cannot leak into the 00:15 run. Distances come from silver.area_station_distance (computed locally with
shapely; the reference point is the polygon centroid, to be replaced by the mean of geocoded block coordinates).

Exactness from day aggregates: a station-day inside the window counts if it has any counted reading; the first day
counts only if its last reading is at or after the window start, and the target day only if its first reading is
before the cut-off.
"""
from coolcheck.timeutil import SGT_OFFSET_S


def _instant(date_sql: str, minutes: int) -> str:
    return f"timestamp_seconds(CAST(unix_date({date_sql}) AS BIGINT) * 86400 - {SGT_OFFSET_S} + {minutes * 60})"


def nearest_station_sql(labels: str, distance: str, boundary: str, cutoff_minutes: int = 15, lookback_days: int = 7) -> str:
    """SELECT statement over the label table and the distance table (both given by name)."""
    if not boundary.replace("_", "").isalnum():
        raise ValueError(f"bad boundary label: {boundary!r}")
    cutoff = _instant("t.target_date", int(cutoff_minutes))
    start = _instant(f"date_sub(t.target_date, {int(lookback_days)})", int(cutoff_minutes))
    return f"""
WITH targets AS (
  SELECT explode(sequence(date_add(min(sgt_date), 1), date_add(max(sgt_date), 1))) AS target_date FROM {labels}
),
reporting AS (
  SELECT t.target_date, l.station_id
  FROM targets t
  JOIN {labels} l
    ON l.sgt_date BETWEEN date_sub(t.target_date, {int(lookback_days)}) AND t.target_date
   AND l.n_valid > 0
   AND l.last_valid_ts >= {start}
   AND l.first_valid_ts < {cutoff}
  GROUP BY t.target_date, l.station_id
),
counts AS (SELECT target_date, count(*) AS n_reporting FROM reporting GROUP BY target_date),
ranked AS (
  SELECT r.target_date, d.planning_area, d.planning_area_code, d.region, d.station_id, d.station_name,
         d.distance_km, d.station_inside_area, d.ref_point,
         row_number() OVER (PARTITION BY r.target_date, d.planning_area ORDER BY d.distance_km, d.station_id) AS rn
  FROM reporting r
  JOIN {distance} d ON d.station_id = r.station_id AND d.boundary = '{boundary}'
)
SELECT k.target_date, k.planning_area, k.planning_area_code, k.region, k.station_id, k.station_name,
       k.distance_km, k.station_inside_area, k.ref_point, c.n_reporting,
       '{boundary}' AS boundary, {int(cutoff_minutes)} AS cutoff_minutes, {int(lookback_days)} AS lookback_days
FROM ranked k JOIN counts c USING (target_date)
WHERE k.rn = 1
"""
