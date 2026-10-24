"""Local tests for coolcheck.agent_tools (the agent's three tools; docs/design/agent_tools.md): the Python twin's rules on
small fixtures, the lookup keys and the SQL files' placeholders. The SQL itself runs in test_agent_tools_sql.py through
Databricks Connect, against the same twin.
"""
import re
from pathlib import Path

import pytest

from agent_fixtures import BLOCKS, RISK, D
from coolcheck import agent_tools as T

REPO = Path(__file__).resolve().parents[2]
BLOCK_CSV = REPO.parent / "coolcheck-data" / "analysis" / "block_access.csv"


# --- lookup keys ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw,want", [("north-east", "NORTHEAST"), ("NORTH-EAST REGION", "NORTHEAST"), ("East Region", "EAST"),
                                      (" west ", "WEST"), ("All regions", "ALL"), ("", ""), (None, None)])
def test_region_key(raw, want):
    assert T.region_key(raw) == want


@pytest.mark.parametrize("raw,want", [("101A", "101A"), ("Blk 101 a", "101A"), ("BLOCK 52", "52"), ("blk.52", "52"),
                                      (" 4C ", "4C"), (None, None)])
def test_blk_key(raw, want):
    assert T.blk_key(raw) == want


@pytest.mark.parametrize("raw,want", [("ST. GEORGE'S LANE", "ST GEORGES LANE"), ("st george's  lane ", "ST GEORGES LANE"),
                                      ("Ang Mo Kio\tAve 10", "ANG MO KIO AVE 10"), ("C'WEALTH CL", "CWEALTH CL"),
                                      ("Jalan Kukoh", "JLN KUKOH"), ("JLN KUKOH", "JLN KUKOH"), ("jln kukoh", "JLN KUKOH"),
                                      ("Yishun Street 31", "YISHUN ST 31"), ("Upper Boon Keng Road", "UPP BOON KENG RD"),
                                      ("Commonwealth Close", "CWEALTH CL"), ("Saint George's Lane", "ST GEORGES LANE"),
                                      ("Lorong 99 Toa Payoh", "LOR 99 TOA PAYOH"), ("Bukit Batok West Avenue 6", "BT BATOK WEST AVE 6"),
                                      ("  ", ""), (None, None)])
def test_street_key(raw, want):
    assert T.street_key(raw) == want


def block_rows():
    if not BLOCK_CSV.exists():
        pytest.skip("coolcheck-data/analysis not present")
    import load_refuge_park_access as L
    cols = [c for c, _, _ in L.TABLES["block_access"]["columns"]]
    return [dict(zip(cols, r)) for r in L.read(BLOCK_CSV, L.TABLES["block_access"]["columns"])]


def test_keys_are_unique_over_every_block():
    rows = block_rows()
    keys = {(T.blk_key(b["blk_no"]), T.street_key(b["street"])) for b in rows}
    assert len(rows) == len(keys) == 10_817


def test_street_words_are_hdbs_own_abbreviations():
    """Every abbreviation occurs in HDB's streets and no long form does, so HDB's spelling keys as it did without the map."""
    words = {w for b in block_rows() for w in re.sub(r"[^A-Z0-9\s]", "", b["street"].upper()).split()}
    assert set(T.STREET_WORDS.values()) <= words and not set(T.STREET_WORDS) & words
    assert len(set(T.STREET_WORDS.values())) == 24


@pytest.mark.parametrize("name", ["find_refuges", "what_if_add_refuge"])
def test_sql_street_map_is_the_twins(name):
    text = (T.SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
    body = re.search(r"SELECT map\((.*?)\) AS m", text, re.S).group(1)
    pairs = re.findall(r"'([A-Z]+)'", body)
    assert dict(zip(pairs[::2], pairs[1::2])) == T.STREET_WORDS and len(pairs) == 2 * len(T.STREET_WORDS)


# --- get_priority_areas (the synthetic briefing in agent_fixtures) -------------------------------------------------

def _calls(rows):
    return {r["planning_area"]: [(b["priority"], b["calls_allocated"], b["partial"]) for b in r["blocks"]] for r in rows}


def test_areas_in_tier_order_then_rank_for_the_date_only():
    rows = T.priority_areas(RISK, BLOCKS, D, 0)
    assert [(r["area_order"], r["planning_area"]) for r in rows] == [(1, "A1"), (2, "A2"), (3, "A3"), (4, "A4"), (5, "A5"),
                                                                    (6, "A6")]
    assert [r["rental_1_2_room"] for r in rows] == [150, 80, 60, 500, 0, 40]


def test_budget_fills_in_order_and_the_crossing_block_is_partial():
    rows = T.priority_areas(RISK, BLOCKS, D, 120)
    assert _calls(rows) == {"A1": [(1, 100, False), (3, 20, True)], "A2": [], "A3": [], "A4": [], "A5": [], "A6": []}
    assert [r["calls_left"] for r in rows] == [0] * 6


def test_budget_that_ends_on_a_block_boundary_has_no_partial_block():
    rows = T.priority_areas(RISK, BLOCKS, D, 230)
    assert _calls(rows)["A2"] == [(1, 80, False)] and _calls(rows)["A3"] == []


@pytest.mark.parametrize("cap", [0, None, -5])
def test_no_budget_gives_the_areas_without_blocks(cap):
    rows = T.priority_areas(RISK, BLOCKS, D, cap)
    assert len(rows) == 6 and all(r["blocks"] == [] and r["calls_allocated"] == 0 and r["calls_left"] == 0 for r in rows)


def test_large_budget_never_reaches_low_no_forecast_or_blocks_without_rental_flats():
    rows = T.priority_areas(RISK, BLOCKS, D, 10_000)
    assert _calls(rows) == {"A1": [(1, 100, False), (3, 50, False)], "A2": [(1, 80, False)],
                            "A3": [(1, 30, False), (2, 30, False)], "A4": [], "A5": [], "A6": []}
    assert rows[-1]["calls_left"] == 10_000 - 290


def test_region_filter_and_renumbered_order():
    rows = T.priority_areas(RISK, BLOCKS, D, 170, region="east")
    assert [r["planning_area"] for r in rows] == ["A1", "A3", "A4", "A5", "A6"]
    assert [r["area_order"] for r in rows] == [1, 2, 3, 4, 5]
    assert _calls(rows)["A3"] == [(1, 20, True)]
    assert T.priority_areas(RISK, BLOCKS, D, 170, region="ALL") == T.priority_areas(RISK, BLOCKS, D, 170)
    assert T.priority_areas(RISK, BLOCKS, D, 170, region="nowhere") == []


# --- find_refuges --------------------------------------------------------------------------------------------------

def _b(blk, street, x, y, area="X", confirmed=True, du=100, r1=0, r2=0):
    return {"blk_no": blk, "street": street, "planning_area": area, "confirmed": confirmed, "x_svy21": x, "y_svy21": y,
            "total_dwelling_units": du, "1room_rental": r1, "2room_rental": r2}


def _r(rid, x, y, layer="community_club", status="open", in_main=True):
    return {"refuge_id": rid, "name": f"name {rid}", "layer": layer, "status": status, "address": "a", "postal_code": "000000",
            "planning_area": "X", "x_svy21": x, "y_svy21": y, "in_main": in_main}


def test_find_refuges_nearest_five_ties_by_id_labels_and_400_m():
    refuges = [_r("cc_9", 400, 0), _r("cc_1", 0, 400), _r("gtp_1", 300, 0, layer="aac_partial"),
               _r("cc_2", 0, 100, status="temp_office"), _r("cc_3", 1000, 0), _r("cc_4", 2000, 0),
               _r("eld_1", 1, 0, layer="eldercare_sac_2016", in_main=False)]
    rows = T.find_refuges([_b("7", "ST. GEORGE'S LANE", 0, 0)], refuges, "blk 7", "st george's lane")
    assert [(r["refuge_rank"], r["refuge_name"], r["distance_m"], r["within_400m"]) for r in rows] == [
        (1, "name cc_2", 100.0, True), (2, "name gtp_1", 300.0, True), (3, "name cc_1", 400.0, True),
        (4, "name cc_9", 400.0, True), (5, "name cc_3", 1000.0, False)]
    assert [r["refuge_type"] for r in rows][:3] == ["Community Club (temporary office)", T.AAC_PARTIAL, "Community Club"]


def test_find_refuges_unknown_or_unconfirmed_block_gives_nothing():
    blocks = [_b("4C", "ST. GEORGE'S LANE", 0, 0, confirmed=False)]
    assert T.find_refuges(blocks, [_r("cc_1", 0, 0)], "4C", "ST. GEORGE'S LANE") == []
    assert T.find_refuges(blocks, [_r("cc_1", 0, 0)], "99", "NOWHERE RD") == []


# --- what_if_add_refuge ----------------------------------------------------------------------------------------------

def test_what_if_newly_within_exactly_400_m_the_site_itself_and_a_second_area():
    blocks = [_b("S", "SITE RD", 0, 0, du=100, r1=10), _b("B1", "SITE RD", 300, 0, du=200, r2=5),
              _b("B3", "SITE RD", -300, 0, du=50), _b("B2", "OTHER RD", 0, 400, area="Y", du=80, r1=3),
              _b("B4", "OTHER RD", 0, 2000, area="Y", du=20), _b("U", "SITE RD", 10, 0, du=999, confirmed=False)]
    # cc_2 covers B3 only (350 m; 461 m from the site); cc_4 at the site is not in the main set
    refuges = [_r("cc_1", 900, 0), _r("cc_2", -300, -350), _r("cc_3", 0, 900), _r("cc_4", 0, 0, in_main=False)]
    rows = T.what_if_add_refuge(blocks, refuges, "s", "site  rd")
    x, y = rows
    assert (x["planning_area"], x["is_site_area"], y["planning_area"], y["is_site_area"]) == ("X", True, "Y", False)
    assert (x["hdb_dwelling_units"], x["du_within_400m_before"], x["du_within_400m_after"]) == (350, 50, 350)
    assert (x["rental_flats_beyond_400m_before"], x["rental_flats_beyond_400m_after"]) == (15, 0)
    assert [(b["blk_no"], b["distance_after_m"]) for b in x["newly_within"]] == [("S", 0.0), ("B1", 300.0)]
    assert x["newly_within"][1]["distance_before_m"] == 600.0
    assert (y["hdb_dwelling_units"], y["du_within_400m_before"], y["du_within_400m_after"], y["blocks_newly_within"]) == (100, 0, 80, 1)
    assert y["newly_within"][0]["distance_after_m"] == 400.0      # 400 m counts as within
    assert x["share_within_400m_after"] == 1.0 and y["share_within_400m_after"] == 0.8


def test_what_if_at_a_refuge_gains_nothing_and_unconfirmed_site_gives_nothing():
    blocks = [_b("S", "SITE RD", 0, 0), _b("B1", "SITE RD", 390, 0), _b("U", "SITE RD", 5, 0, confirmed=False)]
    rows = T.what_if_add_refuge(blocks, [_r("cc_1", 0, 0)], "S", "SITE RD")
    assert len(rows) == 1 and rows[0]["blocks_newly_within"] == 0 and rows[0]["newly_within"] == []
    assert rows[0]["share_within_400m_before"] == rows[0]["share_within_400m_after"] == 1.0
    assert T.what_if_add_refuge(blocks, [_r("cc_1", 0, 0)], "U", "SITE RD") == []


# --- the SQL files ---------------------------------------------------------------------------------------------------

FORBIDDEN = ("heat_forecast", "p_low", "p_moderate", "p_high", "model_version", "run_id", "cutoff_ts", "scored_at")


@pytest.mark.parametrize("name", list(T.FUNCTIONS))
def test_sql_file_placeholders_and_names(name):
    tables = {t: f"t_{t}" for t in T.FUNCTIONS[name]}
    temp = T.function_sql(name, name, tables, temporary=True)
    assert temp.count(f"CREATE OR REPLACE TEMPORARY FUNCTION {name}(") == 1
    assert all(f"t_{t}" in temp for t in tables) and "$" not in temp
    full = T.function_sql(name, f"coolcheck.gold.{name}", {t: f"coolcheck.x.{t}" for t in tables})
    assert f"CREATE OR REPLACE FUNCTION coolcheck.gold.{name}(" in full
    text = (T.SQL_DIR / f"{name}.sql").read_text(encoding="utf-8").lower()
    assert not [w for w in FORBIDDEN if re.search(rf"\b{w}\b", text)]


def test_function_sql_refuses_wrong_tables_and_bad_names():
    with pytest.raises(ValueError):
        T.function_sql("find_refuges", "find_refuges", {"block_access": "t_b"})
    with pytest.raises(ValueError):
        T.function_sql("find_refuges", "find_refuges; DROP", {"block_access": "t_b", "refuge_points": "t_r"})
