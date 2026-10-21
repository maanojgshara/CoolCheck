"""Checks after a pipeline update: row counts, Silver vs expected reading totals, rule failures, short days,
label rule effects, and the High-day counts against docs/checks/wbgt_high_days.md. Reads tables only.

Run from the repo root (Databricks Connect, serverless):
    .venv\\Scripts\\python scripts/checks/silver_check.py --update-id <id>
Writes docs/checks/silver_check.md.
"""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SGT = timezone(timedelta(hours=8))
C = "coolcheck"
TABLES = ["bronze.wbgt_raw", "bronze.rainfall_raw", "bronze.forecast_raw",
          "silver.wbgt_readings_all", "silver.wbgt_readings", "silver.rainfall_readings_all", "silver.rainfall_readings",
          "silver.forecast_issues_all", "silver.forecast_issues", "silver.quarantine", "silver.wbgt_first_arrival",
          "silver.station_daily_label", "silver.dq_day", "silver.dq_events", "silver.dq_conflicts", "silver.station_gaps",
          "silver.forecast_periods"]
EXPECTED = {"wbgt": 1_036_005, "rainfall": 11_893_198, "forecast": 4_673}  # local survey of the raw files, 21 Oct
ORIGINAL_8 = ("S124", "S125", "S126", "S127", "S128", "S129", "S130", "S132")
# docs/checks/wbgt_high_days.md (20 Oct, from the raw files)
NOTES = {"station_days": 10_834, "high_station_days": 535, "high_days": 247,
         "o8_station_days": 5_014, "o8_high_station_days": 166, "o8_high_days": 128,
         "w1": 44, "w2": 421, "w2_o8": 106, "w3": 70, "w3_o8": 16}


def md(df, limit=200):
    rows = df.limit(limit).collect()
    cols = df.columns
    return ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)] + \
           ["| " + " | ".join("" if r[c] is None else f"{r[c]:,}" if isinstance(r[c], int) else str(r[c]) for c in cols) + " |" for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-id", default="")
    ap.add_argument("--out", default=str(REPO / "docs" / "checks" / "silver_check.md"))
    a = ap.parse_args()
    from databricks.connect import DatabricksSession
    spark = DatabricksSession.builder.serverless().profile("coolcheck").getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    q = spark.sql
    L = ["# Silver check after the first full pipeline update", "",
         f"Generated {datetime.now(SGT):%Y-%m-%d %H:%M} SGT by `scripts/checks/silver_check.py`"
         + (f"; pipeline update `{a.update_id}`" if a.update_id else "") + ". Tables read only.", "", "## Row counts", ""]
    counts = {t: q(f"SELECT count(*) AS n FROM {C}.{t}").first().n for t in TABLES}
    L += ["| table | rows |", "|---|---|"] + [f"| `{t}` | {n:,} |" for t, n in counts.items()]

    L += ["", "## Silver readings against the raw-file totals", "",
          "| feed | expected (raw files) | `_all` (every copy) | deduplicated | removed as duplicates | rows without a key |", "|---|---|---|---|---|---|"]
    for feed, all_t, dd in (("wbgt", "wbgt_readings_all", "wbgt_readings"), ("rainfall", "rainfall_readings_all", "rainfall_readings"),
                            ("forecast", "forecast_issues_all", "forecast_issues")):
        nk = q(f"SELECT count(*) AS n FROM {C}.silver.{all_t} WHERE fail_has_key").first().n
        na, nd = counts[f"silver.{all_t}"], counts[f"silver.{dd}"]
        L.append(f"| {feed} | {EXPECTED[feed]:,} | {na:,} {'(matches)' if na == EXPECTED[feed] else '(DIFFERS)'} | {nd:,} | {na - nk - nd:,} | {nk:,} |")

    L += ["", "## dq_events (rule failures and other checks)", "",
          "A rule failure flags the row; nothing is removed. Rules are in `src/coolcheck/silver.py`.", ""]
    L += md(q(f"SELECT feed, check_name, n, detail FROM {C}.silver.dq_events ORDER BY feed, check_name"))

    L += ["", "## Days that are not ok (dq_day)", ""]
    L += md(q(f"""SELECT feed, status, count(*) AS days, concat_ws(', ', sort_array(collect_list(concat(CAST(sgt_date AS STRING), ' (', note, ')')))) AS dates
                 FROM {C}.silver.dq_day WHERE status <> 'ok' GROUP BY feed, status ORDER BY feed, status"""))

    L += ["", "## Label rule effects (station_daily_label)", ""]
    L += md(q(f"""SELECT count(*) AS station_days_with_rows,
                   count_if(n_valid > 0) AS station_days_labelled,
                   count_if(label IS NULL) AS no_label,
                   count_if(low_coverage AND n_valid > 0) AS low_coverage,
                   count_if(low_coverage AND label = 'Low') AS low_coverage_low,
                   count_if(low_coverage AND label = 'Moderate') AS low_coverage_moderate,
                   count_if(low_coverage AND label = 'High') AS low_coverage_high_kept,
                   count_if(usable) AS usable,
                   count_if(label IS DISTINCT FROM label_if_out_of_range_excluded) AS changed_if_out_of_range_excluded,
                   count_if(label IS DISTINCT FROM label_if_late_excluded) AS changed_if_late_excluded,
                   sum(n_out_of_range) AS out_of_range_readings
                 FROM {C}.silver.station_daily_label"""))
    L += ["", "How the out-of-range exclusion would change labels:", ""]
    L += md(q(f"""SELECT label, label_if_out_of_range_excluded, count(*) AS station_days FROM {C}.silver.station_daily_label
                 WHERE label IS DISTINCT FROM label_if_out_of_range_excluded GROUP BY 1, 2 ORDER BY 3 DESC"""))
    L += ["", "Station-days with a WBGT gap over 60 minutes that overlaps 10:00 to 18:00 SGT (the silent rule), by label:", ""]
    L += md(q(f"""WITH g AS (
                   SELECT DISTINCT l.station_id, l.sgt_date, l.label FROM {C}.silver.station_gaps g
                   JOIN {C}.silver.station_daily_label l ON l.station_id = g.station_id
                    AND g.gap_start < timestamp_seconds(CAST(unix_date(l.sgt_date) AS BIGINT) * 86400 - 28800 + 18 * 3600)
                    AND g.gap_end > timestamp_seconds(CAST(unix_date(l.sgt_date) AS BIGINT) * 86400 - 28800 + 10 * 3600)
                   WHERE g.feed = 'wbgt')
                 SELECT coalesce(label, '(none)') AS label, count(*) AS station_days FROM g GROUP BY 1 ORDER BY 1"""))

    L += ["", "## High-day counts against docs/checks/wbgt_high_days.md", "",
          "Definitions as in that file: station-day = at least one counted reading; High station-day = label High; "
          "High day = a day on which any station (or any of the original 8) is High.", ""]
    o8 = "('" + "', '".join(ORIGINAL_8) + "')"
    r = q(f"""SELECT count_if(n_valid > 0) AS station_days, count_if(label = 'High') AS high_station_days,
                     count(DISTINCT CASE WHEN label = 'High' THEN sgt_date END) AS high_days,
                     count_if(n_valid > 0 AND station_id IN {o8}) AS o8_station_days,
                     count_if(label = 'High' AND station_id IN {o8}) AS o8_high_station_days,
                     count(DISTINCT CASE WHEN label = 'High' AND station_id IN {o8} THEN sgt_date END) AS o8_high_days,
                     count_if(label = 'High' AND sgt_date BETWEEN '2025-01-01' AND '2025-06-30') AS w1,
                     count_if(label = 'High' AND sgt_date BETWEEN '2025-07-01' AND '2026-08-31') AS w2,
                     count_if(label = 'High' AND sgt_date BETWEEN '2025-07-01' AND '2026-08-31' AND station_id IN {o8}) AS w2_o8,
                     count_if(label = 'High' AND sgt_date BETWEEN '2026-09-01' AND '2026-10-31') AS w3,
                     count_if(label = 'High' AND sgt_date BETWEEN '2026-09-01' AND '2026-10-31' AND station_id IN {o8}) AS w3_o8
              FROM {C}.silver.station_daily_label""").first().asDict()
    names = {"station_days": "station-days", "high_station_days": "High station-days", "high_days": "High days",
             "o8_station_days": "station-days, original 8", "o8_high_station_days": "High station-days, original 8",
             "o8_high_days": "High days, original 8", "w1": "High station-days Jan–Jun 2025",
             "w2": "High station-days Jul 2025–Aug 2026", "w2_o8": "… original 8", "w3": "High station-days Sep–19 Oct 2026",
             "w3_o8": "… original 8"}
    L += ["| measure | notes (20 Oct) | Silver labels | same? |", "|---|---|---|---|"]
    L += [f"| {names[k]} | {NOTES[k]:,} | {r[k]:,} | {'yes' if r[k] == NOTES[k] else 'NO'} |" for k in NOTES]
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
