"""H10 v2 report: three states of the nearest-station choice computed in one session from one pinned label copy.

Run from the repo root (reads Unity Catalog through Databricks Connect; writes only local files):
    .venv\\Scripts\\python scripts/checks/h10_v2.py [--data <coolcheck-data>] [--out docs/checks/h10_v2.md]

States (all boundary mp2025, same cut-off and look-back; they differ only in method):
    v1    centroid reference point, no island rule   silver.area_station_distance VERSION AS OF --v1-version
    v1.5  block-mean reference point, no island rule silver.area_station_distance VERSION AS OF --v2-version
    v2    block-mean reference point, island rule    the same table, nearest_station_sql(island_rule=True)
silver.station_daily_label is a materialized view and cannot be time-travelled, so it is pulled once to this machine
(toPandas), saved to <data>/analysis/station_daily_label_snapshot_<timestamp>.csv, rebuilt with spark.createDataFrame and
registered as a temp view: the three states read the same rows. Fetch time, row count, last date and sha256 go in the report.
Comparisons use target dates 2025-01-17 to 2026-10-20 (642 days). Labels for sgt_date after 2026-08-31 (the final-check
window) are masked right after the states are built and are never read by the analysis below, which reports area-day counts only.
"""
import argparse
import csv
import hashlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
SGT = timezone(timedelta(hours=8))
FIRST, LAST = "2025-01-17", "2026-10-20"
LABEL_LAST = "2026-08-31"
AGES_65 = {"65_to_69", "70_to_74", "75_to_79", "80_to_84", "85_to_89", "90_and_Over"}
NEAR_TIES = [("JURONG WEST", "S180", "S132"), ("MARINE PARADE", "S129", "S127"), ("NOVENA", "S145", "S133")]
STATES = [("v1", "centroid, no island rule"), ("v15", "block mean, no island rule"), ("v2", "block mean, island rule")]


def md(df, floatfmt=2):
    head = list(df.columns)
    rows = [[(f"{c:.{floatfmt}f}" if isinstance(c, float) else ("" if c is None or (isinstance(c, float) and pd.isna(c)) else str(c)))
             for c in r] for r in df.itertuples(index=False)]
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO.parent / "coolcheck-data"))
    ap.add_argument("--out", default=str(REPO / "docs" / "checks" / "h10_v2.md"))
    ap.add_argument("--v1-version", type=int, default=1)
    ap.add_argument("--v2-version", type=int, default=3)
    a = ap.parse_args()
    data = Path(a.data)

    import sys
    sys.path.insert(0, str(REPO / "src"))
    from databricks.connect import DatabricksSession
    from coolcheck.nearest import nearest_station_sql

    spark = DatabricksSession.builder.serverless().profile("coolcheck").getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")

    # --- pin the labels: pull once, save, rebuild from the local copy
    fetched = datetime.now(SGT)
    src = spark.table("coolcheck.silver.station_daily_label")
    lab = src.toPandas().sort_values(["station_id", "sgt_date"]).reset_index(drop=True)
    stamp = fetched.strftime("%Y%m%d_%H%M%S")
    snap = data / "analysis" / f"station_daily_label_snapshot_{stamp}.csv"
    lab.to_csv(snap, index=False, quoting=csv.QUOTE_MINIMAL)
    sha = hashlib.sha256(snap.read_bytes()).hexdigest()
    need = ["station_id", "sgt_date", "n_valid", "first_valid_ts", "last_valid_ts"]
    pinned = spark.createDataFrame(lab[need], schema=src.select(*need).schema)
    pinned.createOrReplaceTempView("labels_pinned")
    # the rebuilt copy must equal the view it came from (timestamps round-trip exactly)
    chk_p = spark.sql("SELECT count(*) n, sum(unix_timestamp(first_valid_ts)) f, sum(unix_timestamp(last_valid_ts)) l, sum(n_valid) v FROM labels_pinned").first()
    chk_s = src.selectExpr("count(*) n", "sum(unix_timestamp(first_valid_ts)) f", "sum(unix_timestamp(last_valid_ts)) l", "sum(n_valid) v").first()
    roundtrip_ok = tuple(chk_p) == tuple(chk_s)

    spark.sql(f"CREATE OR REPLACE TEMP VIEW dist_v1 AS SELECT * FROM coolcheck.silver.area_station_distance VERSION AS OF {a.v1_version}")
    spark.sql(f"CREATE OR REPLACE TEMP VIEW dist_v2 AS SELECT * FROM coolcheck.silver.area_station_distance VERSION AS OF {a.v2_version}")
    sql = {"v1": nearest_station_sql("labels_pinned", "dist_v1", "mp2025", island_rule=False),
           "v15": nearest_station_sql("labels_pinned", "dist_v2", "mp2025", island_rule=False),
           "v2": nearest_station_sql("labels_pinned", "dist_v2", "mp2025", island_rule=True)}
    st = {}
    for k, q in sql.items():
        df = spark.sql(q).toPandas()
        df["target_date"] = df["target_date"].astype(str)
        st[k] = df[(df.target_date >= FIRST) & (df.target_date <= LAST)].set_index(["target_date", "planning_area"]).sort_index()
    offshore = sorted(r.station_id for r in spark.sql(
        "SELECT DISTINCT station_id FROM dist_v2 WHERE boundary='mp2025' AND station_inside_area AND planning_area IN "
        "('SOUTHERN ISLANDS','WESTERN ISLANDS','NORTH-EASTERN ISLANDS')").collect())
    areas = sorted(r.planning_area for r in spark.sql("SELECT DISTINCT planning_area FROM dist_v2 WHERE boundary='mp2025'").collect())
    days = pd.date_range(FIRST, LAST).strftime("%Y-%m-%d")

    # --- labels, masked after the final-check cut: only target dates up to LABEL_LAST keep a label
    lab["sgt_date"] = lab["sgt_date"].astype(str)
    lab["label_m"] = lab["label"].where(lab["sgt_date"] <= LABEL_LAST)
    lab["usable_m"] = lab["usable"].where(lab["sgt_date"] <= LABEL_LAST)
    lab_by = lab.set_index(["station_id", "sgt_date"])[["label_m", "usable_m"]]

    def label_of(frame):
        k = pd.MultiIndex.from_arrays([frame["station_id"].values, frame.index.get_level_values("target_date").values])
        return lab_by.reindex(k)["label_m"].values

    for k in st:
        st[k]["label"] = label_of(st[k])
    v1s = pd.read_csv(data / "analysis" / "h10_v1_snapshot.csv").set_index(["target_date", "planning_area"])
    both = st["v1"].join(v1s, how="inner", rsuffix="_snap")
    snap_diff = int((both["station_id"] != both["station_id_snap"]).sum())

    def changed(x, y):
        j = st[x][["station_id", "distance_km", "label"]].join(st[y][["station_id", "distance_km", "label"]], how="outer", lsuffix="_x", rsuffix="_y")
        return j[j["station_id_x"] != j["station_id_y"]].reset_index()

    L = ["# H10 v2: block-mean reference point and the island rule", "",
         f"Generated {datetime.now(SGT):%Y-%m-%d %H:%M} SGT by `scripts/checks/h10_v2.py` through Databricks Connect (serverless, profile coolcheck). "
         "Local analysis; nothing written to Unity Catalog by this script. Decisions: `../CoolCheck Guide.md` §14.8 A and B.", "",
         "## Inputs, pinned", "",
         f"- **Distance table `coolcheck.silver.area_station_distance`:** v1 reads `VERSION AS OF {a.v1_version}` (centroid reference point, loaded 21 Oct 2026 17:44); "
         f"v1.5 and v2 read `VERSION AS OF {a.v2_version}` (block-mean reference point, loaded 22 Oct 2026 16:55). Boundary mp2025 throughout.",
         f"- **Labels `coolcheck.silver.station_daily_label`:** a materialized view, which cannot be time-travelled. Pulled once at **{fetched:%Y-%m-%d %H:%M:%S} SGT**: "
         f"**{len(lab):,} rows**, last sgt_date **{lab.sgt_date.max()}**, sha256 `{sha}` of `{snap.relative_to(data.parent).as_posix()}`. "
         "The temp view `labels_pinned` was rebuilt from that local copy with `spark.createDataFrame`, so v1, v1.5 and v2 read the same rows. "
         f"Round trip checked against the view (row count, sum of first and last valid timestamps, sum of n_valid): {'identical' if roundtrip_ok else 'DIFFERENT, see below ' + str(tuple(chk_p)) + ' vs ' + str(tuple(chk_s))}.",
         f"- **Code:** `nearest_station_sql(..., island_rule=False)` for v1 and v1.5, `island_rule=True` for v2 (`src/coolcheck/nearest.py`, commit b353801). Cut-off 00:15 SGT, 7-day look-back.",
         f"- **Date range:** target dates {FIRST} to {LAST}, {len(days)} days (the same as `h10_nearest_station.md`; the live view now runs past 20 Oct). "
         f"Planning areas: {len(areas)}.",
         f"- **Offshore stations** (inside an island area in the distance table): {', '.join(offshore)}.",
         f"- **Labels:** an area-day's label is the daily label of its station on the target date. Labels after {LABEL_LAST} (the final-check window) are masked in the "
         "analysis; for those dates this report gives area-day counts only. The saved label copy outside the repo does contain them.",
         f"- **Sanity:** v1 recomputed here against the restore snapshot `h10_v1_snapshot.csv` (taken from the live view before the reload): {len(both):,} shared area-days, "
         f"**{snap_diff} differ in station**.", ""]

    # (i)
    ci = changed("v1", "v15")
    on = ci[ci.target_date == LAST]
    L += ["## (i) Reference point: v1 (centroid) against v1.5 (block mean)", "",
          f"Area-days whose station changes: **{len(ci):,}** of {len(days) * len(areas):,}, in {ci.planning_area.nunique()} areas.", "",
          f"On target date {LAST}: **{len(on)} areas** change.", ""]
    if len(on):
        L += [md(on.assign(v1_km=on.distance_km_x, v15_km=on.distance_km_y)[["planning_area", "station_id_x", "v1_km", "station_id_y", "v15_km"]]
                 .rename(columns={"station_id_x": "v1_station", "station_id_y": "v15_station"}).sort_values("planning_area")), ""]
    g = (ci.groupby("planning_area").agg(area_days=("target_date", "size"), first_date=("target_date", "min"), last_date=("target_date", "max"),
                                          v1_stations=("station_id_x", lambda s: ", ".join(sorted(set(s)))),
                                          v15_stations=("station_id_y", lambda s: ", ".join(sorted(set(s))))).reset_index().sort_values("area_days", ascending=False))
    L += ["Over the whole window, by area:", "", md(g), ""]
    hi = ci[(ci.target_date <= LABEL_LAST)]
    h_lost = int(((hi.label_x == "High") & (hi.label_y != "High")).sum())
    h_gain = int(((hi.label_x != "High") & (hi.label_y == "High")).sum())
    L += [f"High area-day labels that change with the reference point alone (target dates up to {LABEL_LAST}): High under v1 and not under v1.5: **{h_lost}**; "
          f"High under v1.5 and not under v1: **{h_gain}**. (Not High includes Low, Moderate and no label.) Area-days after {LABEL_LAST} that change: "
          f"{int((ci.target_date > LABEL_LAST).sum()):,}.", ""]

    # residents of the island areas, for the S151 note in (ii)
    res, res65 = defaultdict(int), defaultdict(int)
    with (data / "static" / "singstat_pop_pa_age_sex_floor_area_jun2026" / "respopagesexfa2026.csv").open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            k = r["PA"].strip().upper()
            res[k] += int(r["Pop"] or 0)
            res65[k] += int(r["Pop"] or 0) if r["AG"] in AGES_65 else 0
    resident_note = (f"North-Eastern Islands has {res['NORTH-EASTERN ISLANDS']:,} residents in the SingStat June 2026 file ({res65['NORTH-EASTERN ISLANDS']:,} aged 65+), "
                     f"as do Western Islands ({res['WESTERN ISLANDS']:,}) and Tuas ({res['TUAS']:,}); Southern Islands has {res['SOUTHERN ISLANDS']:,} residents "
                     f"({res65['SOUTHERN ISLANDS']:,} aged 65+).")

    # (ii)
    cj = changed("v15", "v2")
    cj["month"] = cj.target_date.str[:7]
    off_ok = bool(cj.station_id_x.isin(offshore).all()) if len(cj) else True
    L += ["## (ii) Island rule: v1.5 against v2", "",
          f"Area-days whose station changes: **{len(cj):,}** in {cj.planning_area.nunique()} areas. In every one the v1.5 station is offshore: {off_ok}. "
          f"v1.5 stations replaced: {', '.join(sorted(set(cj.station_id_x))) or 'none'}.", ""]
    if len(cj):
        s = (cj.groupby("planning_area").agg(area_days=("target_date", "size"), first_date=("target_date", "min"), last_date=("target_date", "max"),
                                              v15_stations=("station_id_x", lambda s: ", ".join(sorted(set(s)))),
                                              v2_stations=("station_id_y", lambda s: ", ".join(sorted(set(s))))).reset_index().sort_values("area_days", ascending=False))
        L += ["By area:", "", md(s), "", "By area and month (area-days):", ""]
        pv = cj.pivot_table(index="planning_area", columns="month", values="target_date", aggfunc="size", fill_value=0)
        pv["total"] = pv.sum(axis=1)
        L += [md(pv.reset_index().sort_values("total", ascending=False)), ""]
    isl = st["v2"].reset_index()
    isl = isl[isl.planning_area.isin(["SOUTHERN ISLANDS", "WESTERN ISLANDS", "NORTH-EASTERN ISLANDS"])]
    L += ["Island areas under v2 (area-days per station):", "",
          md(isl.groupby(["planning_area", "station_id"]).size().reset_index(name="area_days")), "",
          "S151 (Pulau Ubin) is never chosen: it is eligible only for North-Eastern Islands, whose centroid is 11.87 km from S151 and 6.95 km from S124, "
          "so the area uses S124 on all 642 days. No rule change (decided 22 Oct 2026). It moves no area-level metric: " + resident_note, ""]

    # (iii)
    cl = cj[cj.target_date <= LABEL_LAST]
    lost = cl[(cl.label_x == "High") & (cl.label_y != "High")]
    gain = cl[(cl.label_x != "High") & (cl.label_y == "High")]
    tot = {k: int((st[k][st[k].index.get_level_values(0) <= LABEL_LAST]["label"] == "High").sum()) for k in ("v1", "v15", "v2")}
    n_la = int((pd.Index(st["v2"].index.get_level_values(0)) <= LABEL_LAST).sum())
    L += ["## (iii) High area-day labels that change with the island rule", "",
          f"Target dates up to {LABEL_LAST} only ({n_la:,} area-days); area-day High counts: v1 {tot['v1']:,}, v1.5 {tot['v15']:,}, v2 {tot['v2']:,}.", "",
          f"Of the {len(cl):,} area-days whose station changes in that range: High under v1.5 and not under v2 **{len(lost)}**; High under v2 and not under v1.5 **{len(gain)}**; "
          f"label missing at either station on {int((cl.label_x.isna() | cl.label_y.isna()).sum())}.", ""]
    if len(lost) or len(gain):
        t = pd.concat([lost.assign(change="High -> not High"), gain.assign(change="not High -> High")])
        L += [md(t.groupby(["planning_area", "change"]).agg(area_days=("target_date", "size"), first_date=("target_date", "min"), last_date=("target_date", "max")).reset_index()), ""]
    late = cj[cj.target_date > LABEL_LAST]
    L += [f"After {LABEL_LAST} (final-check window), counts only: **{len(late)}** area-days change station with the island rule"
          + (" (" + ", ".join(f"{k} {v}" for k, v in late.groupby('planning_area').size().sort_values(ascending=False).items()) + ")" if len(late) else "") + ". No labels are shown for them.", ""]

    # (iv)
    sing = data / "static" / "singstat_pop_pa_age_sex_floor_area_jun2026" / "respopagesexfa2026.csv"
    pop65 = defaultdict(int)
    with sing.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["AG"] in AGES_65:
                pop65[r["PA"].strip().upper()] += int(r["Pop"] or 0)
    with65 = sorted(k for k, v in pop65.items() if v > 0)
    L += ["## (iv) Distance to the nearest reporting station per month (areas with residents 65+)", "",
          f"{len(with65)} areas with residents aged 65+ in the SingStat June 2026 file. Over area-days; median and maximum km under each state. Back-test months Jul 2025 to Aug 2026; "
          "the final check (Sep to 20 Oct 2026) and the training-only months (Jan to Jun 2025) are shown separately.", ""]
    rows = []
    d = {k: st[k].reset_index() for k in st}
    for k in d:
        d[k] = d[k][d[k].planning_area.isin(with65)].assign(month=lambda x: x.target_date.str[:7])
    for m in sorted(d["v2"].month.unique()):
        x = {k: d[k][d[k].month == m] for k in d}
        mx = x["v2"].loc[x["v2"].distance_km.idxmax()]
        period = "training only" if m < "2025-07" else ("back-test" if m <= "2026-08" else "final check")
        rows.append([period, m, x["v2"].planning_area.nunique(), len(x["v2"]),
                     *[round(float(x[k].distance_km.median()), 2) for k in ("v1", "v15", "v2")],
                     *[round(float(x[k].distance_km.max()), 2) for k in ("v1", "v15", "v2")],
                     mx.planning_area, mx.station_id, int(x["v2"].n_reporting.min()), int(x["v2"].n_reporting.max())])
    L += [md(pd.DataFrame(rows, columns=["period", "month", "areas", "area_days", "median_v1", "median_v1.5", "median_v2", "max_v1", "max_v1.5", "max_v2",
                                         "v2_area_at_max", "v2_station_at_max", "min_stations_reporting", "max_stations_reporting"])), ""]

    # (v)
    L += ["## (v) Area-days without a station", "", f"Expected: {len(days)} target days × {len(areas)} areas = {len(days) * len(areas):,} area-days per state.", ""]
    exp = pd.MultiIndex.from_product([days, areas], names=["target_date", "planning_area"])
    vrows = []
    for k, desc in STATES:
        miss = exp.difference(st[k].index)
        vrows.append([k, desc, len(st[k]), len(miss)])
        if len(miss):
            L += [f"{k} missing (first 20): " + ", ".join(f"{a_} {d_}" for d_, a_ in list(miss)[:20]), ""]
    L += [md(pd.DataFrame(vrows, columns=["state", "method", "area_days_with_station", "area_days_without_station"])), ""]

    # (vi) and (vii), merged from the committed interim file
    part = (REPO / "docs" / "checks" / "h10_v2_parts_vi_vii.md").read_text(encoding="utf-8")
    body = part.split("\n## (vi)", 1)[1]
    L += ["## (vi)" + body.rstrip(), ""]

    # (viii)
    L += ["## (viii) Near-ties: how much the runner-up station would change", "",
          f"Areas with a gap under 0.1 km in (vii). Days: target dates up to {LABEL_LAST}, on which the v2 station is the best-station of the pair and both stations have a usable label that day "
          "(`usable`: a High label always stands; a Low or Moderate label on a low-coverage day is not usable). 'Differ' compares the two stations' daily categories on the target date; "
          "'High lost / gained' are the High area-days that would change if the runner-up were used in place of the v2 station. A check only; no rule change.", ""]
    v2 = st["v2"].reset_index()
    nrows = []
    for area, best, runner in NEAR_TIES:
        x = v2[(v2.planning_area == area) & (v2.target_date <= LABEL_LAST)]
        n_best = int((x.station_id == best).sum())
        x = x[x.station_id == best].copy()
        key_b = pd.MultiIndex.from_arrays([[runner] * len(x), x.target_date.values])
        rb = lab_by.reindex(key_b)
        x["lab_best"], x["use_best"] = x["label"].values, lab_by.reindex(pd.MultiIndex.from_arrays([[best] * len(x), x.target_date.values]))["usable_m"].values
        x["lab_run"], x["use_run"] = rb["label_m"].values, rb["usable_m"].values
        okd = x[(x.use_best == True) & (x.use_run == True)]  # noqa: E712
        nrows.append([area, best, runner, n_best, len(okd), int((okd.lab_best != okd.lab_run).sum()),
                      f"{(okd.lab_best != okd.lab_run).mean():.1%}" if len(okd) else "n/a",
                      int(((okd.lab_best == "High") & (okd.lab_run != "High")).sum()), int(((okd.lab_best != "High") & (okd.lab_run == "High")).sum()),
                      int((x.lab_best == "High").sum())])
    L += [md(pd.DataFrame(nrows, columns=["planning_area", "v2_station", "runner_up", "area_days_on_v2_station", "days_both_usable", "days_differ", "share_differ",
                                          "High_lost", "High_gained", "High_area_days_on_v2_station"])), ""]
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"labels: {len(lab):,} rows, last {lab.sgt_date.max()}, sha256 {sha}, roundtrip_ok={roundtrip_ok}")
    print(f"v1 vs snapshot station differences: {snap_diff} of {len(both):,}")
    print(f"changed area-days: ref point {len(ci):,}; island rule {len(cj):,}; offshore set {offshore}")
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()
