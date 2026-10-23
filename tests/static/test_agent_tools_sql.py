"""The agent tools' SQL functions (src/functions) against the Python twin (coolcheck.agent_tools), through Databricks
Connect (serverless, profile coolcheck). Each SQL file is created as a TEMPORARY function over temp views of the same rows
(coolcheck-data/analysis, the files the Silver tables are loaded from), so nothing is written to Unity Catalog.

- get_priority_areas over area_heat_risk built by the view SQL (coolcheck.risk) from the back-test rows of one date,
  2025-08-07, read with target_date <= 2026-08-31 and asserted (the final check is not scored here), and over
  block_vulnerability from the real blocks, for several capacities and regions; and over the synthetic briefing of
  agent_fixtures (every tier).
- find_refuges for every block in one LATERAL query, against the twin and block_access's own nearest refuge; and the
  lookup with other spellings.
- what_if_add_refuge for a site that brings rental flats within 400 m, a site whose gain crosses into a second planning
  area, the site with the largest gain, a site at a refuge and an unconfirmed block, against the twin; and one site per
  rated area, whose before share must equal silver.area_access (main set).
Distances must match to 1e-9 m; counts, shares and everything else exactly.
"""
import collections
import datetime as dt
import itertools
from pathlib import Path

import pytest

from agent_fixtures import BLOCK_COLUMNS, BLOCK_SCHEMA, BLOCKS, RISK, RISK_COLUMNS, RISK_SCHEMA, D
from coolcheck import agent_tools as T
from coolcheck import risk as R

REPO = Path(__file__).resolve().parents[2]
ANALYSIS = REPO.parent / "coolcheck-data" / "analysis"
PREDICTIONS = ANALYSIS / "backtest_run_c509ab9a" / "predictions_area_days.parquet"
TEST_DATE = dt.date(2025, 8, 7)  # High 2 (Choa Chu Kang, Bukit Batok), Medium 15, Low 15, Not rated 9; no missing forecast
TOL_M = 1e-9
HIDDEN = {"p_low", "p_moderate", "p_high", "score", "model_version", "run_id", "cutoff_ts", "scored_at", "forecast_missing"}
EXPOSURE_SCHEMA = ("planning_area STRING, planning_area_code STRING, region STRING, residents BIGINT, aged_65_plus BIGINT, "
                   "aged_75_plus BIGINT, share_65_plus DOUBLE, share_75_plus DOUBLE")
FORECAST_SCHEMA = ("target_date DATE, planning_area STRING, station_id STRING, p_low DOUBLE, p_moderate DOUBLE, p_high DOUBLE, "
                   "model_version STRING, run_id STRING, cutoff_ts TIMESTAMP, scored_at TIMESTAMP, forecast_missing BOOLEAN")
SITES = {"rental gain": ("3", "JLN KUKOH"), "two areas": ("106B", "PUNGGOL FIELD"), "largest gain": ("333C", "YISHUN ST 31"),
         "at a refuge": ("105", "JLN BT MERAH"), "other spelling": ("Blk 3", "jln  kukoh"),
         "unconfirmed": ("4C", "ST. GEORGE'S LANE")}


@pytest.fixture(scope="module")
def spark():
    from databricks.connect import DatabricksSession
    s = DatabricksSession.builder.serverless().profile("coolcheck").getOrCreate()
    s.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    return s


def schema_of(columns):
    return ", ".join(f"`{c}` {t}" for c, t, _ in columns)


def rows_of(name):
    """(tuples, dicts) of analysis/<name>.csv with load_refuge_park_access's columns."""
    import load_refuge_park_access as L
    if not (ANALYSIS / f"{name}.csv").exists():
        pytest.skip("coolcheck-data/analysis not present")
    cols = L.TABLES[name]["columns"]
    tuples = L.read(ANALYSIS / f"{name}.csv", cols)
    return tuples, [dict(zip([c for c, _, _ in cols], r)) for r in tuples]


def same(got, want, path=""):
    """got equals want: dicts (same keys, same order) and lists recursively; a float whose key ends in _m to TOL_M."""
    if isinstance(want, dict):
        assert list(got) == list(want), (path, list(got), list(want))
        for k in want:
            same(got[k], want[k], f"{path}.{k}")
    elif isinstance(want, list):
        assert len(got) == len(want), (path, len(got), len(want))
        for i, (g, w) in enumerate(zip(got, want)):
            same(g, w, f"{path}[{i}]")
    elif isinstance(want, float) and path.endswith("_m"):
        assert abs(got - want) <= TOL_M, (path, got, want)
    else:
        assert got == want, (path, got, want)


def collect(spark, sql, **args):
    return [r.asDict(recursive=True) for r in spark.sql(sql, args=args or None).collect()]


@pytest.fixture(scope="module")
def silver(spark):
    """Temp views of block_access and refuge_points, and find_refuges and what_if_add_refuge over them (TEMPORARY)."""
    import load_refuge_park_access as L
    blocks, block_dicts = rows_of("block_access")
    refuges, refuge_dicts = rows_of("refuge_points")
    spark.createDataFrame(blocks, schema_of(L.TABLES["block_access"]["columns"])).createOrReplaceTempView("at_block_access")
    spark.createDataFrame(refuges, schema_of(L.TABLES["refuge_points"]["columns"])).createOrReplaceTempView("at_refuge_points")
    for name in ("find_refuges", "what_if_add_refuge"):
        spark.sql(T.function_sql(name, name, {"block_access": "at_block_access", "refuge_points": "at_refuge_points"},
                                 temporary=True))
    return block_dicts, refuge_dicts


@pytest.fixture(scope="module")
def briefing(spark, silver):
    """area_heat_risk for TEST_DATE and block_vulnerability as temp views, built by coolcheck.risk's view SQL from the real
    inputs, and get_priority_areas over them (TEMPORARY); their rows as dicts, for the twin."""
    if not PREDICTIONS.exists():
        pytest.skip("back-test predictions not present")
    import load_area_exposure as AE
    import load_refuge_park_access as L
    import load_risk_tables as LR

    def view(name, rows, schema):
        spark.createDataFrame(rows, schema).createOrReplaceTempView(name)

    view("at_exposure", AE.read_rows(ANALYSIS / "area_exposure.csv"), EXPOSURE_SCHEMA)
    view("at_access", L.read(ANALYSIS / "area_access.csv", L.TABLES["area_access"]["columns"]),
         schema_of(L.TABLES["area_access"]["columns"]))
    for name, path in (("ema_area_electricity", ANALYSIS / "ema_area_electricity.csv"),
                       ("score_weights", REPO / "reference/score_weights.csv"),
                       ("tier_actions", REPO / "reference/tier_actions.csv")):
        view(f"at_{name}", LR.read(path, LR.TABLES[name]["columns"]), schema_of(LR.TABLES[name]["columns"]))
    spark.sql(R.area_vulnerability_sql("at_exposure", "at_access", "at_block_access", "at_ema_area_electricity",
                                       "at_score_weights")).createOrReplaceTempView("at_vuln")
    spark.sql(R.block_vulnerability_sql("at_block_access", "at_vuln")).createOrReplaceTempView("at_block_vuln")
    bt = R.read_backtest_area_days(PREDICTIONS, columns=["target_date", "planning_area", "station_id", "p_low", "p_moderate",
                                                         "p_high", "forecast_missing"])
    day = bt[bt["target_date"] == TEST_DATE]
    R.assert_on_or_before(day["target_date"])
    assert TEST_DATE <= R.LAST_BACKTEST_DATE and len(day) == 41 and not day["forecast_missing"].any()
    view("at_forecast", [(r.target_date, r.planning_area, r.station_id, float(r.p_low), float(r.p_moderate), float(r.p_high),
                          "backtest c509ab9a", "c509ab9a", None, None, bool(r.forecast_missing)) for r in day.itertuples()],
         FORECAST_SCHEMA)
    spark.sql(R.area_heat_risk_sql("at_forecast", "at_vuln", "at_exposure", "at_tier_actions")).createOrReplaceTempView(
        "at_area_heat_risk")
    spark.sql(T.function_sql("get_priority_areas", "get_priority_areas",
                             {"area_heat_risk": "at_area_heat_risk", "block_vulnerability": "at_block_vuln"}, temporary=True))
    return ([r.asDict() for r in spark.table("at_area_heat_risk").collect()],
            [r.asDict() for r in spark.table("at_block_vuln").collect()])


def priority(spark, fn, date, cap, region):
    cap_sql = "NULL" if cap is None else str(int(cap))
    rows = collect(spark, f"SELECT * FROM {fn}(DATE'{date.isoformat()}', {cap_sql}, :region)", region=region)
    return sorted(rows, key=lambda r: r["area_order"])


# --- get_priority_areas ------------------------------------------------------------------------------------------

def test_get_priority_areas_on_a_backtest_date(spark, briefing):
    risk, blocks = briefing
    got = {}
    for cap, region in itertools.product([0, 500, 3200, 100_000], [None, "west", "East Region", "nowhere"]):
        got[cap, region] = priority(spark, "get_priority_areas", TEST_DATE, cap, region)
        same(got[cap, region], T.priority_areas(risk, blocks, TEST_DATE, cap, region), f"capacity {cap}, region {region}")
    rows = got[0, None]
    assert collections.Counter(r["tier"] for r in rows) == {"High": 2, "Medium": 15, "Low": 15, "Not rated": 9}
    assert [r["planning_area"] for r in rows[:2]] == ["CHOA CHU KANG", "BUKIT BATOK"]
    assert all(r["blocks"] == [] and r["calls_left"] == 0 for r in rows)
    at500 = [r for r in got[500, None] if r["calls_allocated"]]
    assert [r["planning_area"] for r in at500] == ["CHOA CHU KANG"] and at500[0]["calls_allocated"] == 500
    assert at500[0]["blocks"][-1]["partial"] and not any(b["partial"] for b in at500[0]["blocks"][:-1])
    by_tier = collections.Counter()
    for r in got[3200, None]:
        by_tier[r["tier"]] += r["calls_allocated"]
    assert by_tier == {"High": 3081, "Medium": 119, "Low": 0, "Not rated": 0}
    full = got[100_000, None]
    assert sum(r["calls_allocated"] for r in full) == sum(r["rental_1_2_room"] for r in full if r["tier"] in T.CALL_TIERS)
    assert {r["region"] for r in got[500, "west"]} == {"WEST REGION"} and got[500, "nowhere"] == []
    omitted = sorted(collect(spark, f"SELECT * FROM get_priority_areas(DATE'{TEST_DATE.isoformat()}', 500)"),
                     key=lambda r: r["area_order"])
    assert omitted == got[500, None]


def test_get_priority_areas_on_the_synthetic_briefing(spark):
    spark.createDataFrame([tuple(r[c] for c in RISK_COLUMNS) for r in RISK], RISK_SCHEMA).createOrReplaceTempView("at_syn_risk")
    spark.createDataFrame([tuple(b[c] for c in BLOCK_COLUMNS) for b in BLOCKS], BLOCK_SCHEMA).createOrReplaceTempView(
        "at_syn_blocks")
    spark.sql(T.function_sql("get_priority_areas", "gpa_synthetic",
                             {"area_heat_risk": "at_syn_risk", "block_vulnerability": "at_syn_blocks"}, temporary=True))
    for cap, region in itertools.product([None, -5, 0, 120, 230, 10_000], [None, "east", "nowhere"]):
        same(priority(spark, "gpa_synthetic", D, cap, region), T.priority_areas(RISK, BLOCKS, D, cap, region),
             f"capacity {cap}, region {region}")


# --- find_refuges ------------------------------------------------------------------------------------------------

def test_find_refuges_for_every_block(spark, silver):
    blocks, refuges = silver
    got = collect(spark, "SELECT f.* FROM at_block_access b, LATERAL find_refuges(b.blk_no, b.street) f")
    by_block = collections.defaultdict(list)
    for r in got:
        by_block[r["blk_no"], r["street"]].append(r)
    conf = [b for b in blocks if b["confirmed"]]
    assert len(conf) == len(by_block) == 10_807 and len(got) == 5 * 10_807     # the 10 unconfirmed blocks give no rows
    ties = 0
    for b in conf:
        rows = sorted(by_block[b["blk_no"], b["street"]], key=lambda r: r["refuge_rank"])
        same(rows, T.nearest_refuges(b, refuges), f"{b['blk_no']} {b['street']}")
        assert abs(rows[0]["distance_m"] - b["refuge_main_m"]) <= 0.005 + TOL_M     # block_access stores 2 decimals
        if rows[1]["distance_m"] - rows[0]["distance_m"] > TOL_M:
            assert rows[0]["refuge_name"] == b["refuge_main_name"]
        else:
            ties += 1
    print(f"\nfind_refuges: {len(got):,} rows for {len(by_block):,} confirmed blocks; blocks whose two nearest refuges "
          f"are equally far (name not compared): {ties}")


@pytest.mark.parametrize("blk,street,want", [("blk 7", "st george's lane", ("7", "ST. GEORGE'S LANE")),
                                             ("106 a", "canberra  st", ("106A", "CANBERRA ST")),
                                             ("1a", "Eunos Cres", ("1A", "EUNOS CRES")),
                                             ("4C", "ST. GEORGE'S LANE", None), ("99999", "NOWHERE RD", None)])
def test_find_refuges_lookup(spark, silver, blk, street, want):
    blocks, refuges = silver
    got = sorted(collect(spark, "SELECT * FROM find_refuges(:blk, :street)", blk=blk, street=street),
                 key=lambda r: r["refuge_rank"])
    same(got, T.find_refuges(blocks, refuges, blk, street), f"{blk} {street}")
    assert {(r["blk_no"], r["street"]) for r in got} == ({want} if want else set())


# --- what_if_add_refuge ------------------------------------------------------------------------------------------

def what_if(spark, blk, street):
    return sorted(collect(spark, "SELECT * FROM what_if_add_refuge(:blk, :street)", blk=blk, street=street),
                  key=lambda r: (not r["is_site_area"], r["planning_area"]))


@pytest.mark.parametrize("label", list(SITES))
def test_what_if_against_the_twin(spark, silver, label):
    blocks, refuges = silver
    blk, street = SITES[label]
    got = what_if(spark, blk, street)
    same(got, T.what_if_add_refuge(blocks, refuges, blk, street), label)
    gain = {k: sum(r[f"{k}_after"] - r[f"{k}_before"] for r in got) for k in ("du_within_400m", "rental_flats_beyond_400m")}
    new = sum(r["blocks_newly_within"] for r in got)
    if label in ("rental gain", "other spelling"):
        assert got[0]["planning_area"] == "OUTRAM" and (gain["du_within_400m"], gain["rental_flats_beyond_400m"], new) == (3001, -2190, 16)
    elif label == "two areas":
        assert [r["planning_area"] for r in got] == ["PUNGGOL", "SENGKANG"] and all(r["blocks_newly_within"] for r in got)
    elif label == "largest gain":
        assert [r["planning_area"] for r in got] == ["YISHUN"] and gain["du_within_400m"] == 8011
    elif label == "at a refuge":
        assert len(got) == 1 and new == 0 and got[0]["share_within_400m_after"] == got[0]["share_within_400m_before"]
    else:
        assert got == []


def test_what_if_before_share_equals_area_access_for_every_rated_area(spark, silver):
    blocks, refuges = silver
    _, access = rows_of("area_access")
    stored = {r["planning_area"]: (r["share_du_within_400m"], r["hdb_dwelling_units_confirmed"]) for r in access
              if r["measure"] == "refuge" and r["layer_set"] == "main" and r["hdb_blocks_confirmed"] > 0}
    first = {}
    for b in sorted((b for b in blocks if b["confirmed"]), key=lambda b: (b["planning_area"], b["blk_no"], b["street"])):
        first.setdefault(b["planning_area"], b)
    spark.createDataFrame([(b["blk_no"], b["street"]) for b in first.values()], "blk_no STRING, street STRING") \
        .createOrReplaceTempView("at_sites")
    got = collect(spark, "SELECT s.blk_no AS s_blk, s.street AS s_street, w.* "
                         "FROM at_sites s, LATERAL what_if_add_refuge(s.blk_no, s.street) w")
    site_rows = {r["planning_area"]: r for r in got if r["is_site_area"]}
    assert sorted(site_rows) == sorted(stored) and len(stored) == 32
    for a, r in site_rows.items():
        assert (round(r["share_within_400m_before"], 6), r["hdb_dwelling_units"]) == stored[a], a
    for b in first.values():
        mine = sorted(({k: v for k, v in r.items() if k not in ("s_blk", "s_street")} for r in got
                       if (r["s_blk"], r["s_street"]) == (b["blk_no"], b["street"])),
                      key=lambda r: (not r["is_site_area"], r["planning_area"]))
        same(mine, T.what_if_add_refuge(blocks, refuges, b["blk_no"], b["street"]), f"{b['blk_no']} {b['street']}")


# --- the contract ------------------------------------------------------------------------------------------------

def field_names(struct):
    out = set()
    for f in struct.fields:
        out.add(f.name)
        t = getattr(f.dataType, "elementType", f.dataType)
        if hasattr(t, "fields"):
            out |= field_names(t)
    return out


def test_outputs_hold_no_probability_score_or_model_fields(spark, silver, briefing):
    for sql in (f"SELECT * FROM get_priority_areas(DATE'{TEST_DATE.isoformat()}', 500)",
                "SELECT * FROM find_refuges('3', 'JLN KUKOH')", "SELECT * FROM what_if_add_refuge('3', 'JLN KUKOH')"):
        assert not field_names(spark.sql(sql).schema) & HIDDEN, sql
