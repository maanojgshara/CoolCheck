"""Tests for src/coolcheck/risk.py and src/coolcheck/electricity.py on small fixtures (local; no workspace).

The SQL twin of these rules is compared with them in test_risk_sql.py (Databricks Connect).
"""
import datetime as dt
import math
from pathlib import Path

import pytest

from coolcheck import electricity as E
from coolcheck import risk as R

REPO = Path(__file__).resolve().parents[2]


def weights(**changes):
    """The decision 9 weights as dicts, with optional {component: {field: value}} changes."""
    base = R.load_weights(REPO / "reference/score_weights.csv")
    return [dict(w, **changes.get(w["component"], {})) for w in base]


def area(raw, du=5000, residents=50000, aged_65=8000, aged_75=None):
    full = {k: 0.5 for k in R.COMPONENTS} | raw
    return {"planning_area_code": "XX", "region": "R", "residents": residents, "aged_65_plus": aged_65,
            "aged_75_plus": int(full["aged_75_plus"]) if aged_75 is None else aged_75, "du": du, "raw": full}


# --- reference weights ---------------------------------------------------------------------------------------------

def test_repo_weights_are_decision_9_with_9g_rules():
    w = {x["component"]: x for x in weights()}
    assert {k: x["weight"] for k, x in w.items()} == {
        "aged_75_plus": 0.20, "share_75_plus": 0.15, "rental_1_2_room": 0.25, "electricity_hot_rise": 0.05,
        "refuge_beyond_400m": 0.15, "refuges_per_1000_65": 0.10, "park_beyond_400m": 0.10}
    assert {k for k, x in w.items() if x["direction"] == "inverted"} == {"electricity_hot_rise", "refuges_per_1000_65"}
    assert {k: x["small_area_rule"] for k, x in w.items()} == {
        "aged_75_plus": "none", "share_75_plus": "residents", "rental_1_2_room": "none", "electricity_hot_rise": "none",
        "refuge_beyond_400m": "hdb_du", "refuges_per_1000_65": "aged_65", "park_beyond_400m": "hdb_du"}
    assert all(x["small_area_min"] == 1000 for x in w.values() if x["small_area_rule"] != "none")


@pytest.mark.parametrize("change,msg", [({"aged_75_plus": {"weight": 0.25}}, "sum"),
                                        ({"rental_1_2_room": {"direction": "lower"}}, "direction"),
                                        ({"aged_75_plus": {"small_area_rule": "residents"}}, "small_area_min"),
                                        ({"share_75_plus": {"small_area_rule": "rooms"}}, "small_area_rule")])
def test_check_weights_rejects(change, msg):
    with pytest.raises(ValueError, match=msg):
        R.check_weights(weights(**change))


def test_check_weights_rejects_a_missing_component():
    with pytest.raises(ValueError, match="cover"):
        R.check_weights(weights()[:-1])


# --- percentiles -------------------------------------------------------------------------------------------------------

def test_percentiles_mean_rank_for_ties():
    assert R.percentiles({"a": 1.0, "b": 2.0, "c": 2.0, "d": 3.0}, "higher") == {"a": 0.0, "b": 0.5, "c": 0.5, "d": 1.0}


def test_percentiles_inverted_mirror_higher_even_with_ties():
    vals = {"a": 0.3, "b": 0.1, "c": 0.1, "d": 0.9, "e": 0.5}
    hi, inv = R.percentiles(vals, "higher"), R.percentiles(vals, "inverted")
    assert all(inv[k] == pytest.approx(1 - hi[k]) for k in vals)
    assert inv["b"] == inv["c"] == pytest.approx(0.875)  # the two smallest values tie at the vulnerable end


def test_percentiles_single_value_is_neutral():
    assert R.percentiles({"a": 7.0}, "higher") == {"a": 0.5}


# --- small-area rule (decision 9(g)), neutral values, V, thirds and the reason ------------------------------------------

def four_areas(**small):
    """Four areas with distinct values; the one named 'S' takes the small-area figures given."""
    vals = {"A": 1.0, "B": 2.0, "C": 3.0, "S": 4.0}
    return {k: area({c: v * (i + 1) for i, c in enumerate(R.COMPONENTS)}, **(small if k == "S" else {})) for k, v in vals.items()}


def test_small_hdb_holds_only_the_two_400m_shares():
    res = R.vulnerability(four_areas(du=999), weights())
    assert set(res["S"]["neutral"]) == {"refuge_beyond_400m", "park_beyond_400m"}
    assert res["S"]["neutral"]["park_beyond_400m"] == "fewer than 1,000 confirmed HDB dwelling units"
    assert res["S"]["p"]["refuge_beyond_400m"] == 0.5 and res["S"]["p"]["rental_1_2_room"] == 1.0  # a count stays real
    assert res["S"]["small_hdb"] and not res["S"]["small_residents"]


def test_small_residents_holds_only_the_75_share():
    res = R.vulnerability(four_areas(residents=999), weights())
    assert set(res["S"]["neutral"]) == {"share_75_plus"} and res["S"]["p"]["aged_75_plus"] == 1.0
    assert res["S"]["neutral"]["share_75_plus"] == "fewer than 1,000 residents"


def test_small_aged_65_holds_only_refuges_per_1000():
    res = R.vulnerability(four_areas(aged_65=999), weights())
    assert set(res["S"]["neutral"]) == {"refuges_per_1000_65"} and res["S"]["small_aged_65"]
    assert res["S"]["neutral"]["refuges_per_1000_65"] == "fewer than 1,000 residents aged 65+"


def test_at_the_threshold_the_value_is_real():
    res = R.vulnerability(four_areas(du=1000, residents=1000, aged_65=1000), weights())
    assert res["S"]["neutral"] == {}


def test_neutral_area_is_left_out_of_the_ranking():
    res = R.vulnerability(four_areas(du=10), weights())
    assert [res[k]["p"]["refuge_beyond_400m"] for k in "ABCS"] == [0.0, 0.5, 1.0, 0.5]  # ranked among A, B, C only


def test_missing_electricity_is_neutral_and_flagged():
    areas = four_areas()
    areas["B"]["raw"]["electricity_hot_rise"] = None
    res = R.vulnerability(areas, weights())
    assert res["B"]["p"]["electricity_hot_rise"] == 0.5 and res["B"]["electricity_missing"]
    assert res["B"]["neutral_components"] == "electricity_hot_rise (no value)"


def test_v_is_the_weighted_sum_and_neutral_list_follows_sort_order():
    res = R.vulnerability(four_areas(du=10, residents=10), weights())
    w = {x["component"]: x["weight"] for x in weights()}
    for r in res.values():
        assert r["v"] == pytest.approx(sum(w[k] * r["p"][k] for k in R.COMPONENTS))
    assert res["S"]["neutral_components"] == ("share_75_plus (fewer than 1,000 residents); refuge_beyond_400m (fewer than "
                                              "1,000 confirmed HDB dwelling units); park_beyond_400m (fewer than 1,000 "
                                              "confirmed HDB dwelling units)")


def test_thirds_split_11_11_rest_and_tie_break():
    areas = {f"A{i:02d}": area({c: float(i) for c in R.COMPONENTS}) for i in range(32)}
    res = R.vulnerability(areas, weights())
    thirds = [res[f"A{i:02d}"]["third"] for i in range(31, -1, -1)]
    assert thirds == ["upper"] * 11 + ["middle"] * 11 + ["lower"] * 10
    # equal V: more residents aged 75+ first, then the name
    tied = {"X": area({}, aged_75=10), "Y": area({}, aged_75=20), "Z": area({}, aged_75=20)}
    res = R.vulnerability(tied, weights(), upper=1, middle=1)
    assert [k for k in sorted(res, key=lambda k: res[k]["v_rank"])] == ["Y", "Z", "X"]
    assert (res["Y"]["third"], res["Z"]["third"], res["X"]["third"]) == ("upper", "middle", "lower")


def test_reason_names_two_largest_eligible_and_never_a_neutral_one():
    areas = four_areas(du=10)
    res = R.vulnerability(areas, weights())
    assert res["S"]["reason"] == "many 1–2 room rental flats; many residents aged 75+"  # 0.25 and 0.20 at p = 1
    assert "refuge" not in res["S"]["reason"]
    # A is lowest everywhere: only the two inverted components are at the vulnerable end, the 0.10 one first
    assert res["A"]["reason"] == "few refuges per resident aged 65+; a small hot-month rise in 1–2 room electricity use (may indicate less air-con use)"
    one = {"P": area({c: 1.0 for c in R.COMPONENTS}), "Q": area({c: 2.0 for c in R.COMPONENTS} | {"aged_75_plus": 0.5})}
    res = R.vulnerability(one, weights())
    assert res["P"]["reason"] == "many residents aged 75+; few refuges per resident aged 65+"  # 0.20, then 0.10 (0.05 is third)
    none = {"P": area({c: 1.0 for c in R.COMPONENTS} | {"electricity_hot_rise": 2.0, "refuges_per_1000_65": 2.0}),
            "Q": area({c: 2.0 for c in R.COMPONENTS} | {"electricity_hot_rise": 1.0, "refuges_per_1000_65": 1.0})}
    assert R.vulnerability(none, weights())["P"]["reason"] == R.NO_REASON


# --- heat level, tier, order -----------------------------------------------------------------------------------------

def test_heat_level_edges():
    c = R.HIGH_CUTOFF
    assert R.heat_level(0.5, 0.4, c) == "High"
    assert R.heat_level(0.5, 0.4, math.nextafter(c, 0)) == "Low"
    assert R.heat_level(0.4, 0.4, 0.05) == "Moderate"  # a tie between Moderate and Low is Moderate
    assert R.heat_level(None, 0.4, 0.05) is None and R.heat_level(0.5, float("nan"), 0.2) is None


@pytest.mark.parametrize("heat,third,main,variant", [
    ("Low", "lower", "Low", "Low"), ("Low", "middle", "Low", "Low"), ("Low", "upper", "Low", "Low"),
    ("Moderate", "lower", "Low", "Low"), ("Moderate", "middle", "Medium", "Low"), ("Moderate", "upper", "Medium", "Medium"),
    ("High", "lower", "Medium", "Medium"), ("High", "middle", "High", "High"), ("High", "upper", "High", "High")])
def test_tier_matrix(heat, third, main, variant):
    assert R.tier(heat, third) == main and R.tier(heat, third, R.TIER_VARIANT) == variant


def test_tier_not_rated_and_no_forecast():
    assert R.tier("High", None) == "Not rated" and R.tier(None, "upper") == "No forecast" and R.tier(None, None) == "No forecast"


def test_heat_risk_rank_within_tier_and_sentences():
    vuln = {"A": {"v": 0.8, "third": "upper", "reason": "r"}, "B": {"v": 0.6, "third": "middle", "reason": "r"},
            "C": {"v": 0.9, "third": "lower", "reason": "r"}}
    d = dt.date(2026, 10, 24)
    fc = [{"target_date": d, "planning_area": "A", "p_low": 0.2, "p_moderate": 0.5, "p_high": 0.3},
          {"target_date": d, "planning_area": "B", "p_low": 0.2, "p_moderate": 0.3, "p_high": 0.5},
          {"target_date": d, "planning_area": "C", "p_low": 0.1, "p_moderate": 0.6, "p_high": 0.3},
          {"target_date": d, "planning_area": "N2", "p_low": 0.6, "p_moderate": 0.3, "p_high": 0.1},
          {"target_date": d, "planning_area": "N1", "p_low": 0.2, "p_moderate": 0.3, "p_high": 0.5},
          {"target_date": d, "planning_area": "X", "p_low": None, "p_moderate": 0.3, "p_high": 0.5}]
    out = {r["planning_area"]: r for r in R.heat_risk(fc, vuln)}
    assert (out["B"]["tier"], out["B"]["tier_rank"], out["A"]["tier_rank"]) == ("High", 1, 2)  # 0.5 x 0.6 > 0.3 x 0.8
    assert out["C"]["tier"] == "Medium" and out["C"]["tier_sentence"] == "Medium: forecast High heat, lower third for vulnerability"
    assert (out["N1"]["tier_rank"], out["N2"]["tier_rank"]) == (1, 2)  # unrated: heat level first, then name
    assert out["N2"]["tier_sentence"] == "Not rated: forecast Low heat; no HDB blocks to rate"
    assert out["X"]["tier"] == "No forecast" and out["X"]["score"] is None


def test_block_priority():
    rows = [{"planning_area": "A", "blk_no": b, "street": "S", "1room_rental": r1, "2room_rental": r2, "refuge_main_m": m}
            for b, r1, r2, m in [("1", 10, 0, 100.0), ("2", 5, 5, 300.0), ("3", 0, 0, 900.0), ("4", 0, 0, 900.0), ("5", 20, 0, 1.0)]]
    rows.append({"planning_area": "Z", "blk_no": "9", "street": "S", "1room_rental": 99, "2room_rental": 0, "refuge_main_m": 1.0})
    got = R.block_priority(rows, {"A"})
    assert [b for b, _ in sorted(got, key=got.get)] == ["5", "2", "1", "3", "4"] and ("9", "S") not in got


# --- constants and the hard rule ------------------------------------------------------------------------------------------

def test_constants_match_the_back_test_and_the_final_check():
    from coolcheck.backtest import LAST_BACKTEST_DATE
    from coolcheck.final_check import FINAL_CUTOFF
    assert R.HIGH_CUTOFF == FINAL_CUTOFF and R.LAST_BACKTEST_DATE == LAST_BACKTEST_DATE


def test_backtest_reader_filters_the_final_check_window(tmp_path):
    import pandas as pd
    path = tmp_path / "p.parquet"
    pd.DataFrame({"target_date": pd.to_datetime(["2026-08-30", "2026-08-31", "2026-09-01"]), "planning_area": ["A"] * 3,
                  "p_high": [0.1, 0.2, 0.3]}).to_parquet(path)
    frame = R.read_backtest_area_days(path)
    assert list(frame["target_date"]) == [dt.date(2026, 8, 30), dt.date(2026, 8, 31)]


def test_assertion_fires_on_a_planted_row():
    with pytest.raises(ValueError, match="final check"):
        R.assert_on_or_before([dt.date(2026, 8, 31), dt.date(2026, 9, 1)])


# --- area_inputs ---------------------------------------------------------------------------------------------------------

def test_area_inputs_rated_rental_shares_and_swaps():
    exposure = [{"planning_area": a, "planning_area_code": a, "region": "R", "residents": "2000", "aged_65_plus": "400",
                 "aged_75_plus": "150", "share_65_plus": "0.2", "share_75_plus": "0.075"} for a in ("A", "B")]
    acc = []
    for a, blocks in (("A", "2"), ("B", "0")):
        for m, sets in (("refuge", ("main", "clubs_only", "with_sac_2016")), ("park", ("main", "with_reserves", "ura"))):
            for s in sets:
                acc.append({"planning_area": a, "measure": m, "layer_set": s, "hdb_blocks_confirmed": blocks,
                            "hdb_dwelling_units_confirmed": "1500", "share_du_within_400m": "0.25" if s == "main" else "0.75",
                            "refuges_per_1000_65_plus": "2.5" if s == "main" else "5.0"})
    blocks = [{"planning_area": "A", "confirmed": "true", "1room_rental": "3", "2room_rental": "4"},
              {"planning_area": "A", "confirmed": "false", "1room_rental": "100", "2room_rental": "0"}]
    elec = [{"planning_area": "A", "hot_ratio_mean": ""}]
    got = R.area_inputs(exposure, acc, blocks, elec)
    assert list(got) == ["A"]  # B has no confirmed block
    raw = got["A"]["raw"]
    assert raw["rental_1_2_room"] == 7.0 and raw["refuge_beyond_400m"] == 0.75 and raw["electricity_hot_rise"] is None
    assert raw["aged_75_plus"] == 150.0 and raw["share_75_plus"] == 0.075
    alt = R.area_inputs(exposure, acc, blocks, elec, refuge_set="clubs_only", park_set="ura", age="65")["A"]["raw"]
    assert (alt["refuge_beyond_400m"], alt["park_beyond_400m"], alt["refuges_per_1000_65"]) == (0.25, 0.25, 5.0)
    assert (alt["aged_75_plus"], alt["share_75_plus"]) == (400.0, 0.2)


# --- electricity -----------------------------------------------------------------------------------------------------------

def monthly(year, cool=100.0, hot=110.0):
    m = {(year - 1, 11): cool, (year - 1, 12): cool, (year, 1): cool, (year, 2): cool}
    m.update({(year, 4): hot, (year, 5): hot, (year, 6): hot})
    return m


def test_year_ratio_needs_all_seven_months():
    m = monthly(2022)
    assert E.year_ratio(m, 2022) == pytest.approx(1.1)
    del m[(2021, 12)]
    assert E.year_ratio(m, 2022) is None


def test_three_year_mean_needs_all_three_years():
    m = monthly(2022) | monthly(2023, hot=120.0) | monthly(2024, hot=130.0)
    r = E.ratios(m, E.VALUE_YEARS)
    assert E.three_year_mean(r) == pytest.approx(1.2)
    assert E.three_year_mean({2022: 1.1, 2024: 1.3}) is None


def test_mean_over_area_years_and_pooled():
    by_area = {"A": {2015: 1.0, 2016: 1.2}, "B": {2016: 1.4}, "C": {}}
    assert E.mean_over_area_years(by_area) == (pytest.approx(1.2), 3)
    m = monthly(2015, cool=100.0, hot=120.0) | monthly(2016, cool=200.0, hot=200.0)
    assert E.pooled_ratio(m, (2015, 2016)) == pytest.approx(160.0 / 150.0)
