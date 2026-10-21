"""H10 checks on gold.area_nearest_station_daily, and the distinct High dates in the final-check window (step 4).

Run from the repo root after the nearest_station job (Databricks Connect, serverless; reads tables only):
    .venv\\Scripts\\python scripts/checks/h10_high_days.py [--data <coolcheck-data>]

- For one target date (default 2026-10-20): the view's nearest reporting station per area against the nearest of all
  31 stations (no reporting window), with the last counted reading of the all-stations nearest where they differ.
- Per back-test month (Jul 2025 to Aug 2026; the final check Sep to 20 Oct 2026 shown separately): median and maximum
  distance over area-days, for areas with residents aged 65+ in the SingStat June 2026 file (planning areas per
  Master Plan 2025, matched on upper-cased names).
- Area-days with no station.
- Distinct High dates 1 Sep to 19 Oct 2026 (any station; without S142) and High station-days per station.
Writes docs/checks/h10_nearest_station.md.
"""
import argparse
import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SGT = timezone(timedelta(hours=8))
AGES_65 = {"65_to_69", "70_to_74", "75_to_79", "80_to_84", "85_to_89", "90_and_Over"}
V = "coolcheck.gold.area_nearest_station_daily"
LBL = "coolcheck.silver.station_daily_label"
DIST = "coolcheck.silver.area_station_distance"


def md(df):
    rows, cols = df.collect(), df.columns
    return ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)] + \
           ["| " + " | ".join("" if r[c] is None else str(r[c]) for c in cols) + " |" for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO.parent / "coolcheck-data"))
    ap.add_argument("--date", default="2026-10-20")
    ap.add_argument("--out", default=str(REPO / "docs" / "checks" / "h10_nearest_station.md"))
    a = ap.parse_args()
    seniors = defaultdict(int)
    with open(Path(a.data) / "static" / "singstat_pop_pa_age_sex_floor_area_jun2026" / "respopagesexfa2026.csv", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["AG"] in AGES_65:
                seniors[r["PA"].strip().upper()] += int(r["Pop"] or 0)

    from databricks.connect import DatabricksSession
    spark = DatabricksSession.builder.serverless().profile("coolcheck").getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    q = spark.sql
    spark.createDataFrame(sorted(seniors.items()), "planning_area STRING, pop_65_plus LONG").createOrReplaceTempView("seniors")
    areas = {r.planning_area for r in q(f"SELECT DISTINCT planning_area FROM {DIST} WHERE boundary = 'mp2025'").collect()}
    with65 = sorted(k for k, v in seniors.items() if v > 0)
    unmatched = sorted(set(seniors) - areas)

    L = ["# H10 nearest reporting station, and the final-check High dates", "",
         f"Generated {datetime.now(SGT):%Y-%m-%d %H:%M} SGT by `scripts/checks/h10_high_days.py` from `{V}` "
         "(boundary mp2025, cut-off 00:15 SGT, reporting = at least one counted WBGT reading in the 7 days before the cut-off), "
         f"`{DIST}` and `{LBL}`.", "",
         f"SingStat June 2026: {len(seniors)} planning areas, {len(with65)} with residents aged 65+ "
         f"({sum(seniors.values()):,} residents 65+, figures rounded to 10 by SingStat); names not found in the MP2025 "
         f"boundary: {', '.join(unmatched) or 'none'}.", ""]

    L += [f"## 1. Target date {a.date}: view against the nearest of all 31 stations", ""]
    cmp = q(f"""
      WITH allnear AS (
        SELECT planning_area, min_by(station_id, distance_km) AS all_station, min(distance_km) AS all_km
        FROM {DIST} WHERE boundary = 'mp2025' GROUP BY planning_area),
      v AS (SELECT * FROM {V} WHERE target_date = DATE'{a.date}'),
      lastseen AS (SELECT station_id, max(last_valid_ts) AS last_counted_reading FROM {LBL}
                   WHERE n_valid > 0 AND sgt_date <= DATE'{a.date}' GROUP BY station_id)
      SELECT a.planning_area, v.station_id AS view_station, round(v.distance_km, 2) AS view_km,
             a.all_station, round(a.all_km, 2) AS all_km, CAST(l.last_counted_reading AS STRING) AS all_station_last_counted_reading
      FROM allnear a LEFT JOIN v USING (planning_area) LEFT JOIN lastseen l ON l.station_id = a.all_station
      WHERE v.station_id IS DISTINCT FROM a.all_station ORDER BY a.planning_area""")
    n_cmp = cmp.count()
    nv = q(f"SELECT count(*) AS n, max(n_reporting) AS rep FROM {V} WHERE target_date = DATE'{a.date}'").first()
    L += [f"{nv.n} areas in the view for {a.date}; {nv.rep} stations reporting. Areas where the view differs from the "
          f"all-stations nearest: **{n_cmp}**.", ""]
    if n_cmp:
        L += md(cmp)
    L += [""]

    L += ["## 2. Distance to the nearest reporting station per month (areas with residents 65+)", "",
          "Over area-days (each area once per target day). Back-test months Jul 2025 to Aug 2026; the final check "
          "(Sep to 20 Oct 2026) and the training-only months (Jan to Jun 2025) are shown separately.", ""]
    L += md(q(f"""
      SELECT CASE WHEN target_date < DATE'2025-07-01' THEN 'training only'
                  WHEN target_date < DATE'2026-09-01' THEN 'back-test' ELSE 'final check' END AS period,
             date_format(target_date, 'yyyy-MM') AS month, count(DISTINCT v.planning_area) AS areas, count(*) AS area_days,
             round(median(distance_km), 2) AS median_km, round(max(distance_km), 2) AS max_km,
             max_by(v.planning_area, distance_km) AS area_at_max, max_by(station_id, distance_km) AS station_at_max,
             min(n_reporting) AS min_stations_reporting, max(n_reporting) AS max_stations_reporting
      FROM {V} v JOIN seniors s ON s.planning_area = v.planning_area AND s.pop_65_plus > 0
      GROUP BY 1, 2 ORDER BY 2"""))

    L += ["", "## 3. Area-days with no station", ""]
    g = q(f"""WITH t AS (SELECT explode(sequence(DATE'2025-01-17', DATE'{a.date}')) AS target_date),
                   x AS (SELECT t.target_date, d.planning_area FROM t CROSS JOIN (SELECT DISTINCT planning_area FROM {DIST} WHERE boundary = 'mp2025') d)
              SELECT count(*) AS expected_area_days, count(v.station_id) AS with_station,
                     count(*) - count(v.station_id) AS without_station
              FROM x LEFT JOIN {V} v USING (target_date, planning_area)""").first()
    L += [f"Target days 2025-01-17 to {a.date} × 55 areas = {g.expected_area_days:,} area-days; with a station "
          f"{g.with_station:,}; **without a station {g.without_station}**.", ""]

    L += ["## 4. Distinct High dates, 1 Sep to 19 Oct 2026 (from `silver.station_daily_label`)", ""]
    w = "label = 'High' AND sgt_date BETWEEN DATE'2026-09-01' AND DATE'2026-10-19'"
    r = q(f"""SELECT count(*) AS high_station_days, count(DISTINCT sgt_date) AS any_station,
                     count(DISTINCT CASE WHEN station_id <> 'S142' THEN sgt_date END) AS without_s142,
                     count_if(station_id <> 'S142') AS high_station_days_without_s142
              FROM {LBL} WHERE {w}""").first()
    L += [f"High station-days {r.high_station_days} ({r.high_station_days_without_s142} without S142). "
          f"**Distinct High dates: {r.any_station} with any station; {r.without_s142} without S142.**", ""]
    L += md(q(f"""SELECT sgt_date, count(*) AS high_stations, concat_ws(', ', sort_array(collect_list(station_id))) AS stations,
                         max(station_id = 'S142') AND count(*) = 1 AS s142_only
                  FROM {LBL} WHERE {w} GROUP BY sgt_date ORDER BY sgt_date"""))
    L += ["", "High station-days per station in the window:", ""]
    L += md(q(f"""SELECT l.station_id, max(l.station_name) AS name, count(*) AS high_station_days
                  FROM {LBL} l WHERE {w} GROUP BY l.station_id ORDER BY high_station_days DESC, station_id"""))
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
