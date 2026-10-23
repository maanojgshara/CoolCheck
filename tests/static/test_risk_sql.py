"""The three views' SQL (coolcheck.risk) against the Python rules, on the same rows, through Databricks Connect
(serverless, profile coolcheck). Temp views only: nothing is written to Unity Catalog.

- A synthetic fixture with ties, small areas, a missing EMA value and an unrated area (no workspace data needed).
- The real inputs (coolcheck-data/analysis, the files the Silver tables are loaded from): area_vulnerability for the 32
  rated areas, block_vulnerability for every block, and area_heat_risk on the back-test's area-days, read with
  target_date <= 2026-08-31 and asserted (the final check is not scored yet), under both tier matrices.
The SQL repeats the Python's floating-point operations in the same order, so V and the percentiles must match exactly.
"""
import datetime as dt
from pathlib import Path

import pytest

from coolcheck import risk as R

REPO = Path(__file__).resolve().parents[2]
DATA = REPO.parent / "coolcheck-data"
ANALYSIS = DATA / "analysis"
PREDICTIONS = ANALYSIS / "backtest_run_c509ab9a" / "predictions_area_days.parquet"
EXPOSURE_SCHEMA = ("planning_area STRING, planning_area_code STRING, region STRING, residents BIGINT, aged_65_plus BIGINT, "
                   "aged_75_plus BIGINT, share_65_plus DOUBLE, share_75_plus DOUBLE")
EXPOSURE_COLS = ["planning_area", "planning_area_code", "region", "residents", "aged_65_plus", "aged_75_plus",
                 "share_65_plus", "share_75_plus"]
FORECAST_SCHEMA = ("target_date DATE, planning_area STRING, station_id STRING, p_low DOUBLE, p_moderate DOUBLE, p_high DOUBLE, "
                   "model_version STRING, run_id STRING, cutoff_ts TIMESTAMP, scored_at TIMESTAMP, forecast_missing BOOLEAN")
VULN_FIELDS = ["v", "v_rank", "third", "reason", "small_hdb", "small_residents", "small_aged_65", "electricity_missing",
               "neutral_components"]


@pytest.fixture(scope="module")
def spark():
    from databricks.connect import DatabricksSession
    s = DatabricksSession.builder.serverless().profile("coolcheck").getOrCreate()
    s.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    return s


def specs():
    import load_refuge_park_access as L
    import load_risk_tables as T
    return L, T


def schema_of(columns):
    return ", ".join(f"`{c}` {t}" for c, t, _ in columns)


def view(spark, name, rows, schema):
    spark.createDataFrame(rows, schema).createOrReplaceTempView(name)
    return name


def dicts(rows, cols):
    return [dict(zip(cols, r)) for r in rows]


def compare_vulnerability(spark, exposure, access, blocks, electricity, weights_rows, wcols):
    """Run the SQL on temp views of the given rows and compare every area with the Python result."""
    L, T = specs()
    view(spark, "t_exposure", exposure, EXPOSURE_SCHEMA)
    view(spark, "t_access", access, schema_of(L.TABLES["area_access"]["columns"]))
    view(spark, "t_blocks", blocks, schema_of(L.TABLES["block_access"]["columns"]))
    view(spark, "t_electricity", electricity, schema_of(T.TABLES["ema_area_electricity"]["columns"]))
    view(spark, "t_weights", weights_rows, schema_of(T.TABLES["score_weights"]["columns"]))
    sql_rows = spark.sql(R.area_vulnerability_sql("t_exposure", "t_access", "t_blocks", "t_electricity", "t_weights")).collect()
    acols = [c for c, _, _ in L.TABLES["area_access"]["columns"]]
    bcols = [c for c, _, _ in L.TABLES["block_access"]["columns"]]
    ecols = [c for c, _, _ in T.TABLES["ema_area_electricity"]["columns"]]
    inputs = R.area_inputs(dicts(exposure, EXPOSURE_COLS), dicts(access, acols), dicts(blocks, bcols), dicts(electricity, ecols))
    py = R.vulnerability(inputs, [dict(zip(wcols, r)) for r in weights_rows])
    assert sorted(r["planning_area"] for r in sql_rows) == sorted(py)
    for r in sql_rows:
        x = py[r["planning_area"]]
        for k in R.COMPONENTS:
            assert r[f"p_{k}"] == x["p"][k], (r["planning_area"], k)
        for f in VULN_FIELDS:
            assert r[f] == x[f], (r["planning_area"], f, r[f], x[f])
    assert [c for c, _ in R.VULN_COLUMNS] == list(sql_rows[0].asDict())
    return sql_rows, py


# --- synthetic fixture ---------------------------------------------------------------------------------------------

def synthetic():
    L, T = specs()
    names = ["AA", "BB", "CC", "DD", "EE", "FF", "GG", "HH"]
    # residents, aged 65+, aged 75+, share 75+ (BB small residents, CC small aged 65+, a tie in the 75+ share)
    exp = {"AA": (40000, 8000, 3000, 0.075), "BB": (900, 300, 80, 0.088), "CC": (5000, 700, 400, 0.08),
           "DD": (60000, 9000, 4000, 0.075), "EE": (20000, 5000, 2500, 0.125), "FF": (30000, 6000, 2000, 0.0667),
           "GG": (25000, 4000, 1500, 0.06), "HH": (10000, 2000, 900, 0.09)}
    exposure = [(a, a, "R", *exp[a][:3], exp[a][1] / exp[a][0], exp[a][3]) for a in names]
    # blocks, DU, refuge share, refuges per 1,000, park share (DD small HDB, HH unrated, ties at 1.0 and 0.0)
    acc = {"AA": (3, 4000, 0.5, 0.25, 0.4), "BB": (2, 1500, 0.9, 0.0, 1.0), "CC": (4, 2500, 1.0, 0.0, 1.0),
           "DD": (1, 300, 1.0, 1.0, 1.0), "EE": (5, 6000, 0.5, 0.4, 0.2), "FF": (6, 7000, 0.3, 0.25, 0.6),
           "GG": (2, 3000, 0.7, 0.1, 0.4), "HH": (0, 0, None, 0.0, None)}
    acols = [c for c, _, _ in L.TABLES["area_access"]["columns"]]
    access = []
    for a in names:
        nb, du, sr, per, sp = acc[a]
        for m, sets in (("refuge", ("main", "clubs_only", "with_sac_2016")), ("park", ("main", "with_reserves", "ura"))):
            for s in sets:
                row = dict.fromkeys(acols)
                row.update(planning_area=a, planning_area_code=a, region="R", measure=m, layer_set=s, is_main=s == "main",
                           residents=exp[a][0], aged_65_plus=exp[a][1], hdb_blocks_confirmed=nb,
                           hdb_dwelling_units_confirmed=du, share_du_within_400m=sr if m == "refuge" else sp)
                if m == "refuge":
                    row.update(refuges_in_area=0, refuges_per_1000_65_plus=per)
                access.append(tuple(row[c] for c in acols))
    bcols = [c for c, _, _ in L.TABLES["block_access"]["columns"]]
    rent = {"AA": [(10, 5, True)], "BB": [(0, 3, True)], "CC": [(8, 0, True), (50, 50, False)], "DD": [(2, 2, True)],
            "EE": [(7, 8, True)], "FF": [(0, 0, True)], "GG": [(3, 0, True), (3, 0, True)], "HH": [(9, 9, False)]}
    blocks = []
    for a in names:
        for i, (r1, r2, conf) in enumerate(rent[a]):
            row = dict.fromkeys(bcols)
            row.update({"blk_no": str(i), "street": f"{a} ST", "planning_area": a, "planning_area_code": a,
                        "total_dwelling_units": 100, "rental_block": r1 + r2 > 0, "confirmed": conf,
                        "refuge_main_m": 100.0 * (i + 1), "park_main_m": 50.0, "1room_rental": r1, "2room_rental": r2})
            blocks.append(tuple(row[c] for c in bcols))
    ecols = [c for c, _, _ in T.TABLES["ema_area_electricity"]["columns"]]
    elec = {"AA": 1.10, "BB": 1.05, "CC": 1.10, "EE": 1.20, "FF": 1.00, "GG": None}  # DD and HH have no row, GG a null
    electricity = [tuple(dict(dict.fromkeys(ecols), planning_area=a, ema_name=a, hot_ratio_mean=v)[c] for c in ecols)
                   for a, v in elec.items()]
    return exposure, access, blocks, electricity


def weight_rows():
    _, T = specs()
    cols = [c for c, _, _ in T.TABLES["score_weights"]["columns"]]
    return T.read(REPO / "reference/score_weights.csv", T.TABLES["score_weights"]["columns"]), cols


def test_synthetic_area_vulnerability_sql_matches_python(spark):
    exposure, access, blocks, electricity = synthetic()
    w, wcols = weight_rows()
    sql_rows, py = compare_vulnerability(spark, exposure, access, blocks, electricity, w, wcols)
    assert len(sql_rows) == 7  # HH has no confirmed block
    assert py["DD"]["neutral"].keys() == {"electricity_hot_rise", "refuge_beyond_400m", "park_beyond_400m"}
    assert py["BB"]["neutral"].keys() == {"share_75_plus", "refuges_per_1000_65"}
    assert py["CC"]["neutral"].keys() == {"refuges_per_1000_65"}


# --- the real inputs ------------------------------------------------------------------------------------------------

def real_inputs():
    if not (ANALYSIS / "block_access.csv").exists():
        pytest.skip("coolcheck-data/analysis not present")
    import load_area_exposure as AE
    L, T = specs()
    exposure = AE.read_rows(ANALYSIS / "area_exposure.csv")
    access = L.read(ANALYSIS / "area_access.csv", L.TABLES["area_access"]["columns"])
    blocks = L.read(ANALYSIS / "block_access.csv", L.TABLES["block_access"]["columns"])
    electricity = T.read(ANALYSIS / "ema_area_electricity.csv", T.TABLES["ema_area_electricity"]["columns"])
    return exposure, access, blocks, electricity


def test_real_area_vulnerability_sql_matches_python(spark):
    w, wcols = weight_rows()
    sql_rows, py = compare_vulnerability(spark, *real_inputs(), w, wcols)
    assert len(sql_rows) == 32
    assert [py[r["planning_area"]]["third"] for r in sql_rows].count("lower") == 10


def test_real_block_vulnerability_sql_matches_python(spark):
    L, _ = specs()
    exposure, access, blocks, electricity = real_inputs()
    w, wcols = weight_rows()
    compare_vulnerability(spark, exposure, access, blocks, electricity, w, wcols)
    spark.sql(R.area_vulnerability_sql("t_exposure", "t_access", "t_blocks", "t_electricity", "t_weights")).createOrReplaceTempView("t_vuln")
    got = spark.sql(R.block_vulnerability_sql("t_blocks", "t_vuln")).collect()
    bcols = [c for c, _, _ in L.TABLES["block_access"]["columns"]]
    bd = dicts(blocks, bcols)
    rated = {r["planning_area"] for r in spark.table("t_vuln").collect()}
    want = R.block_priority(bd, rated)
    assert len(got) == len(want) == 10_817
    by_key = {(b["blk_no"], b["street"]): b for b in bd}
    for r in got:
        b = by_key[(r["blk_no"], r["street"])]
        assert r["priority"] == want[(r["blk_no"], r["street"])]
        assert r["rental_1_2_room"] == b["1room_rental"] + b["2room_rental"]
        assert r["refuge_within_400m"] == (b["refuge_main_m"] <= 400.0) and r["park_within_400m"] == (b["park_main_m"] <= 400.0)
    assert [c for c, _ in R.BLOCK_COLUMNS] == list(got[0].asDict())


@pytest.mark.parametrize("matrix_name", ["main", "variant"])
def test_backtest_area_heat_risk_sql_matches_python(spark, matrix_name):
    if not PREDICTIONS.exists():
        pytest.skip("back-test predictions not present")
    _, T = specs()
    matrix = R.TIER_MAIN if matrix_name == "main" else R.TIER_VARIANT
    exposure, access, blocks, electricity = real_inputs()
    w, wcols = weight_rows()
    _, py_v = compare_vulnerability(spark, exposure, access, blocks, electricity, w, wcols)
    spark.sql(R.area_vulnerability_sql("t_exposure", "t_access", "t_blocks", "t_electricity", "t_weights")).createOrReplaceTempView("t_vuln")
    view(spark, "t_actions", T.read(REPO / "reference/tier_actions.csv", T.TABLES["tier_actions"]["columns"]),
         schema_of(T.TABLES["tier_actions"]["columns"]))
    bt = R.read_backtest_area_days(PREDICTIONS, columns=["target_date", "planning_area", "station_id", "p_low", "p_moderate",
                                                         "p_high", "forecast_missing"])
    assert max(bt["target_date"]) <= dt.date(2026, 8, 31)
    rows = [(r.target_date, r.planning_area, r.station_id, float(r.p_low), float(r.p_moderate), float(r.p_high),
             "backtest c509ab9a", "c509ab9a", None, None, bool(r.forecast_missing)) for r in bt.itertuples()]
    view(spark, "t_forecast", rows, FORECAST_SCHEMA)
    got = spark.sql(R.area_heat_risk_sql("t_forecast", "t_vuln", "t_exposure", "t_actions", matrix=matrix)).collect()
    fc = [{"target_date": r[0], "planning_area": r[1], "p_low": r[3], "p_moderate": r[4], "p_high": r[5]} for r in rows]
    want = {(r["target_date"], r["planning_area"]): r for r in R.heat_risk(fc, py_v, matrix)}
    actions = {r[0]: r[1] for r in T.read(REPO / "reference/tier_actions.csv", T.TABLES["tier_actions"]["columns"])}
    assert len(got) == len(want) == len(rows) == 17_438
    for r in got:
        x = want[(r["target_date"], r["planning_area"])]
        for f in ("heat_level", "rated", "third", "tier", "tier_rank", "tier_sentence", "reason"):
            assert r[f] == x[f], (r["target_date"], r["planning_area"], f, r[f], x[f])
        assert r["actions"] == actions.get(x["tier"])
    assert [c for c, _ in R.RISK_COLUMNS] == list(got[0].asDict())
