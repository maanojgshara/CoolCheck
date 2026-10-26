"""Tier explanations (coolcheck.explain; docs/design/tier_explanations.md), offline (about 1 s, no workspace).

The facts from four made-up gold.area_vulnerability rows (the values of Toa Payoh, Bedok, Tanglin and Changi on 26 Oct
2026) and the real reference/score_weights.csv: the ranks use the percentile's own set and direction, values read as a
coordinator reads them, nothing never shown is in them. The template: the dashboard's tier sentence first, the longest
form that fits in 35 words. The check: a correct sentence passes; a wrong number, a wrong tier, a banned word or a long
sentence falls back, and so do a missing value, a wrong heat level, third, date, temperature or rank, a number in words,
an observation tied to the forecast and another area's name. Window D's three rules (each measure as given, each bracket
its own fact, nothing but the facts and frame words): its 3 controls pass, and its wrong sentences that the earlier
checks let through fall back, at least one from each of its 13 groups, on the stored 26 Oct facts. The 31 stored AI
sentences of 26 Oct and the 32 templates (stored_26oct.json, a read-only SELECT of the table) pass, and the prompt's own
examples do. No SQL here reads P(High), p_moderate, p_low, V, its rank, tier_rank, model_version or run_id.
"""
import json
import re
from datetime import date
from pathlib import Path

import pytest

from coolcheck import agent as A
from coolcheck import explain as E
from coolcheck import risk as R

ROOT = Path(__file__).resolve().parents[2]
WEIGHTS = R.load_weights(ROOT / "reference/score_weights.csv")
PHRASE = {w["component"]: w["reason_phrase"] for w in WEIGHTS}
COLS = ("residents", "aged_65_plus", "aged_75_plus", "share_75_plus", "hdb_dwelling_units_confirmed", "rental_1_2_room",
        "electricity_hot_ratio", "refuge_beyond_400m", "refuges_per_1000_65_plus", "park_beyond_400m")
VULN = [dict(planning_area=a, **dict(zip(COLS, v))) for a, v in (
    ("TOA PAYOH", (147800, 31910, 14290, 0.096685, 48943, 3835, 1.11499, 0.16509, 0.4701, 0.670106)),
    ("BEDOK", (269740, 65820, 27590, 0.102284, 64414, 4155, 1.135415, 0.436831, 0.1823, 0.510898)),
    ("TANGLIN", (24670, 4070, 1840, 0.074585, 166, 0, None, 1.0, 0.0, 0.0)),    # fewer than 1,000 flats
    ("CHANGI", (660, 170, 60, 0.090909, 166, 0, None, 1.0, 0.0, 0.0)))]           # and few residents, few aged 65+
BY_AREA = {v["planning_area"]: v for v in VULN}
RANKS = E.ranks(VULN, WEIGHTS)
TARGET = date(2026, 10, 26)


def heat(area, tier, level, third, components):
    return {"target_date": TARGET, "planning_area": area, "tier": tier, "heat_level": level, "third": third,
            "reason": "; ".join(PHRASE[k] for k in components) or R.NO_REASON}


def facts_of(area, tier, level, third, components, observed=None):
    return E.facts(heat(area, tier, level, third, components), BY_AREA[area], RANKS, len(VULN), WEIGHTS, observed)


TP = facts_of("TOA PAYOH", "Medium", "Moderate", "upper", ["rental_1_2_room", "aged_75_plus"],
              {"max_wbgt": 30.5, "heat_category": "Low"})
GOOD = ("Medium: forecast Moderate heat and the upper third for vulnerability, with 3,835 1-2 room rental flats (2nd most "
        "of 4 rated areas) and 14,290 residents aged 75+.")
# two measures with different ranks, and a 31 among the facts (for a copied example temperature)
TWO = {"area": "Toa Payoh", "tier": "Medium", "forecast_heat_level": "Moderate", "vulnerability_third": "upper",
       "vulnerable_because": [{"measure": "3,835 1-2 room rental flats", "rank": "5th most of 32 rated areas"},
                              {"measure": "an 11% share of residents aged 75+", "rank": "7th highest of 31 rated areas measured"}],
       "observed_heat": {"date": "25 Oct", "where": "the area's WBGT station", "peak_wbgt": "30.5 °C", "nea_category": "Low"}}
NONE = {"area": "Changi", "tier": "Low", "forecast_heat_level": "Moderate", "vulnerability_third": "lower",
        "vulnerability_note": R.NO_REASON,
        "observed_heat": {"date": "25 Oct", "where": "the area's WBGT station", "peak_wbgt": "32.1 °C", "nea_category": "Moderate"}}


# --- facts -------------------------------------------------------------------------------------------------------------

def test_ranks_use_the_percentiles_set_and_direction():
    """Rank 1 is the most vulnerable; a held value (a share over fewer than 1,000, no value) is in no ranking; ties
    share the best rank."""
    assert RANKS[("BEDOK", "aged_75_plus")] == (1, False, 4) and RANKS[("CHANGI", "aged_75_plus")] == (4, False, 4)
    assert RANKS[("TANGLIN", "rental_1_2_room")] == RANKS[("CHANGI", "rental_1_2_room")] == (3, True, 4)
    assert RANKS[("BEDOK", "share_75_plus")] == (1, False, 3) and ("CHANGI", "share_75_plus") not in RANKS
    assert RANKS[("TANGLIN", "refuges_per_1000_65")] == (1, False, 3)  # inverted: no refuge is the fewest
    assert RANKS[("TOA PAYOH", "electricity_hot_rise")] == (1, False, 2)  # inverted: the smaller rise
    assert ("TANGLIN", "refuge_beyond_400m") not in RANKS and RANKS[("BEDOK", "refuge_beyond_400m")] == (1, False, 2)


def test_rank_text():
    assert E.rank_text(2, False, 32, "most", 32) == "2nd most of 32 rated areas"
    assert E.rank_text(1, False, 29, "highest", 32) == "the highest of 29 rated areas measured"
    assert E.rank_text(3, True, 32, "most", 32) == "joint 3rd most of 32 rated areas"
    assert [E.ordinal(k) for k in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 32)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "32nd"]


def test_values_read_as_a_coordinator_reads_them():
    tp, bedok, tanglin = BY_AREA["TOA PAYOH"], BY_AREA["BEDOK"], BY_AREA["TANGLIN"]
    assert E.measure_text("aged_75_plus", tp) == "14,290 residents aged 75+"
    assert E.measure_text("rental_1_2_room", tp) == "3,835 1-2 room rental flats"
    assert E.measure_text("share_75_plus", tp) == "a 10% share of residents aged 75+"
    assert E.measure_text("refuge_beyond_400m", tp) == "17% of HDB flats beyond 400 m of a refuge"
    assert E.measure_text("park_beyond_400m", tp) == "67% of HDB flats beyond 400 m of a park"
    assert E.measure_text("electricity_hot_rise", tp) == (
        "an 11% rise in 1-2 room electricity use from November-February to April-June")
    assert E.measure_text("refuges_per_1000_65", bedok) == "12 refuges in the area for 65,820 residents aged 65+"
    assert E.measure_text("refuges_per_1000_65", tanglin) == "no refuges in the area for 4,070 residents aged 65+"
    assert E.measure_text("refuges_per_1000_65", {"refuges_per_1000_65_plus": 0.5, "aged_65_plus": 2000}) == (
        "1 refuge in the area for 2,000 residents aged 65+")
    assert E.measure_text("refuges_per_1000_65", {"refuges_per_1000_65_plus": 0.3333, "aged_65_plus": 1000}) == (
        "0.33 refuges per 1,000 residents aged 65+")  # not a whole count: the rate
    assert [E.measure_text("share_75_plus", {"share_75_plus": s}).split()[0] for s in (0.08, 0.11, 0.18, 0.85, 0.10)] == [
        "an", "an", "an", "an", "a"]


def test_facts_of_an_area():
    assert E.components(PHRASE["rental_1_2_room"] + "; " + PHRASE["aged_75_plus"], WEIGHTS) == ["rental_1_2_room",
                                                                                                  "aged_75_plus"]
    assert E.components(R.NO_REASON, WEIGHTS) == []
    assert TP == {"area": "Toa Payoh", "tier": "Medium", "forecast_heat_level": "Moderate", "vulnerability_third": "upper",
                  "vulnerable_because": [{"measure": "3,835 1-2 room rental flats", "rank": "2nd most of 4 rated areas"},
                                         {"measure": "14,290 residents aged 75+", "rank": "2nd most of 4 rated areas"}],
                  "observed_heat": {"date": "25 Oct", "where": "the area's WBGT station", "peak_wbgt": "30.5 °C",
                                    "nea_category": "Low"}}
    changi = facts_of("CHANGI", "Low", "Moderate", "lower", [])
    assert changi["vulnerability_note"] == R.NO_REASON and "vulnerable_because" not in changi
    assert "observed_heat" not in changi  # no usable observed row: left out
    peak = facts_of("BEDOK", "Low", "Low", "upper", ["aged_75_plus"], {"max_wbgt": 30.45, "heat_category": "Low"})
    assert peak["observed_heat"]["peak_wbgt"] == "30.5 °C"  # as Spark's round(x, 1), half up
    assert E.facts({**heat("BEDOK", "Low", "Low", "upper", []), "target_date": date(2026, 11, 1)}, BY_AREA["BEDOK"], RANKS,
                   4, WEIGHTS, {"max_wbgt": 31.0, "heat_category": "Low"})["observed_heat"]["date"] == "31 Oct"


def test_no_fact_carries_what_is_never_shown():
    for area, comps in (("TOA PAYOH", list(E.MEASURES)), ("TANGLIN", ["refuges_per_1000_65"]), ("CHANGI", [])):
        text = json.dumps(facts_of(area, "Low", "Low", "lower", comps, {"max_wbgt": 30.0, "heat_category": "Low"}))
        for word in (*E.NEVER_READ, "probability", "chance", "p(high)", "percentile"):
            assert not re.search(rf"(?<![\w(]){re.escape(word)}(?![\w)])", text, re.I), (area, word)


# --- the template ------------------------------------------------------------------------------------------------------

def test_template_is_the_dashboards_tier_sentence_then_the_facts():
    assert E.template(TP) == ("Medium: forecast Moderate heat, upper third for vulnerability, with 3,835 1-2 room rental "
                              "flats (2nd most of 4 rated areas) and 14,290 residents aged 75+ (2nd most of 4 rated areas).")
    assert E.template(NONE) == ("Low: forecast Moderate heat, lower third for vulnerability, with no component above the "
                                "middle of the rated areas; peak WBGT observed at its station on 25 Oct: 32.1 °C (Moderate).")


def test_template_takes_the_longest_form_that_fits(monkeypatch):
    full = E._template(TP, True, True)
    assert full.endswith("; peak WBGT observed at its station on 25 Oct: 30.5 °C (Low).") and len(full.split()) == 43
    assert E._template(TP, False, True) == ("Medium: forecast Moderate heat, upper third for vulnerability, with 3,835 1-2 "
                                            "room rental flats and 14,290 residents aged 75+; peak WBGT observed at its "
                                            "station on 25 Oct: 30.5 °C (Low).")
    monkeypatch.setattr(E, "MAX_WORDS", 43)
    assert E.template(TP) == full
    monkeypatch.setattr(E, "MAX_WORDS", 30)
    assert E.template(TP) == E._template(TP, False, False)  # ranks only and values with the peak are 31 words each


def test_template_passes_its_own_check():
    for f in (TP, TWO, NONE, facts_of("TANGLIN", "Low", "Low", "lower", ["refuges_per_1000_65"])):
        assert E.check(E.template(f), f) == [], f["area"]


# --- the check ---------------------------------------------------------------------------------------------------------

def test_a_correct_sentence_passes():
    assert E.check(GOOD, TP) == []
    assert E.check(f'"{GOOD}"', TP) == []  # surrounding quotes are trimmed
    assert E.check("Medium: forecast Moderate heat and the upper third for vulnerability, with 3,835 1-2 room rental "
                   "flats and 14,290 residents aged 75+; its station observed a peak WBGT of 30.5 °C (Low) on 25 Oct.", TP) == []
    assert E.check("Medium: forecast Moderate heat and the upper third for vulnerability, with 3,835 1-2 room rental "
                   "flats (5th most of 32 rated areas) and an 11% share of residents aged 75+.", TWO) == []
    assert E.check("Low: forecast Moderate heat and the lower third for vulnerability, with no component above the middle "
                   "of the rated areas; its station observed a peak WBGT of 32.1 °C on 25 Oct.", NONE) == []


@pytest.mark.parametrize("sentence, failed", [
    (GOOD.replace("3,835", "3,853"), ["facts: does not give 3,835", "numbers not in the facts: 3,853",
                                      "rank: 2nd most comes before any measure"]),
    (GOOD.replace("Medium:", "High:"), ["tier: does not begin with Medium"]),
    (GOOD.replace("vulnerability,", "vulnerability, a High-tier area"), ["tier: names High"]),
    (GOOD[:-1] + ", many of them living alone.", ["banned: alone"]),
    (GOOD[:-1] + " in a planning area of Singapore with many older residents nearby.", ["length: 38 words"]),
    (GOOD.replace("(2nd most", "(second most"), ["numbers in words: second"]),
    (GOOD.replace("forecast Moderate heat", "forecast High heat"), ["heat: does not say Moderate heat", "heat: names High"]),
    (GOOD.replace("upper third", "middle third"), ["third: does not say the upper third", "third: names middle"]),
    (GOOD.replace(" and 14,290 residents aged 75+", ""), ["facts: does not give 14,290"]),
    (GOOD.replace("(2nd most", "(3rd most"), ["numbers not in the facts: 3",
                                              "rank: 3rd most is not the rank of 3,835 1-2 room rental flats"]),
    (GOOD.replace("vulnerability,", "vulnerability. It has"), ["length: more than one sentence"]),
    (GOOD[:-1] + ", as in Bedok.", ["areas not in the facts: Bedok"]),
    (GOOD[:-1] + "; volunteers should check on them.", ["banned: advice"]),
    (GOOD.replace("forecast Moderate heat", "the model's forecast Moderate heat"), ["banned: the model"]),
    (GOOD[:-1] + "; its station observed 30.5 °C yesterday.", ["banned: today, tomorrow or yesterday"]),
    (GOOD.replace("Medium:", "Medium: with a 10% chance of High heat,"),
     ["heat: names High", "numbers not in the facts: 10%", "App check: P(High), probability or score", "banned: chance"]),
    ("Medium: forecast Moderate heat after a 30.5 °C peak at its station on 25 Oct, the upper third for vulnerability, "
     "3,835 1-2 room rental flats and 14,290 residents aged 75+.", ["observation tied to the forecast or the tier"]),
    (GOOD[:-1] + "; its station observed 30.5 °C on 25 Oct, so the tier is Medium.",
     ["length: 40 words", "observation tied to the forecast or the tier"]),
    ("", ["empty"]),
])
def test_a_wrong_sentence_falls_back(sentence, failed):
    got = E.check(sentence, TP)
    assert set(failed) <= set(got), got  # at least these; window D's rules may add their own
    row = E.choose(TP, sentence)
    assert row["written_by"] == E.TEMPLATE and row["explanation"] == E.template(TP) and row["checks_failed"]


def test_dates_temperatures_and_ranks_must_be_their_own_fact():
    """A number in the facts can still be the wrong fact: the prompt example's "1 Jan" (1 is in "1-2 room"), a copied
    "31.0 °C" (31 is in "of 31 rated areas"), two ranks swapped."""
    s = ("Medium: forecast Moderate heat and the upper third for vulnerability, with 3,835 1-2 room rental flats and an "
         "11% share of residents aged 75+; its station observed 30.5 °C on 1 Jan.")
    assert "date: 1 Jan" in E.check(s, TWO)
    assert "temperature: 31.0 °C" in E.check(s.replace("30.5 °C on 1 Jan", "31.0 °C on 25 Oct"), TWO)
    swapped = ("Medium: forecast Moderate heat and the upper third for vulnerability, with 3,835 1-2 room rental flats (7th "
               "highest of 31 rated areas measured) and an 11% share of residents aged 75+ (5th most of 32 rated areas).")
    assert {"rank: 7th highest is not the rank of 3,835 1-2 room rental flats",
            "rank: 5th most is not the rank of an 11% share of residents aged 75+",
            "bracket: (7th highest of 31 rated areas measured) is not the rank of 3,835 1-2 room rental flats"
            } <= set(E.check(swapped, TWO))
    no_peak = {k: v for k, v in TWO.items() if k != "observed_heat"}
    assert E.check(s.replace("; its station observed 30.5 °C on 1 Jan", ""), no_peak) == []
    assert {"numbers not in the facts: 30.5", "date: 1 Jan", "temperature: 30.5 °C"} <= set(E.check(s, no_peak))


def test_an_area_with_no_measure_gives_its_observed_peak():
    s = "Low: forecast Moderate heat and the lower third for vulnerability, with no component above the middle of the rated areas."
    assert E.required(NONE) == ["32.1"] and E.check(s, NONE) == ["facts: does not give 32.1"]
    assert E.required(TP) == ["3,835", "14,290"]  # the values, not the labels' 1-2 or 75


def test_a_banned_word_passes_only_when_a_fact_holds_it():
    f = {**TWO, "vulnerable_because": [{"measure": "3,835 1-2 room rental flats (may indicate less air-con use)",
                                        "rank": "5th most of 32 rated areas"}]}
    s = ("Medium: forecast Moderate heat and the upper third for vulnerability, with 3,835 1-2 room rental flats (may "
         "indicate less air-con use).")
    assert E.check(s, f) == [] and "banned: air-con" in E.check(s, TWO)


def test_percentages_are_grounded_as_the_app_grounds_them():
    assert {0.11, 11.0} <= E.sources(TWO) and A.grounded("11", E.sources(TWO), percent=True)
    s = ("Medium: forecast Moderate heat and the upper third for vulnerability, with 3,835 1-2 room rental flats and an "
         "11.4% share of residents aged 75+.")
    assert {"facts: does not give 11", "numbers not in the facts: 11.4%"} <= set(E.check(s, TWO))


def test_choose_keeps_both_sentences_and_who_wrote_the_one_shown():
    assert E.choose(TP, f"  {GOOD} ") == {"template_sentence": E.template(TP), "ai_sentence": f"  {GOOD} ",
                                          "explanation": GOOD, "written_by": "AI, checked", "checks_failed": None}
    assert E.choose(TP, None, error="timed out") == {"template_sentence": E.template(TP), "ai_sentence": None,
                                                     "explanation": E.template(TP), "written_by": "Template",
                                                     "checks_failed": "model error: timed out"}


# --- window D's rules, on the stored 26 Oct facts ----------------------------------------------------------------------

STORED = json.loads((Path(__file__).parent / "stored_26oct.json").read_text(encoding="utf-8"))["rows"]
FACTS = {r["planning_area"]: r["facts"] for r in STORED}
SAID = {r["planning_area"]: r["ai_sentence"] for r in STORED}
TOA_PAYOH, TENGAH, AMK = FACTS["TOA PAYOH"], FACTS["TENGAH"], FACTS["ANG MO KIO"]
BASE = SAID["TOA PAYOH"]
HIGH_TP = {**TOA_PAYOH, "tier": "High", "forecast_heat_level": "High"}  # D's made-up High tier and High heat
# (group in D's "Passed, though wrong" table, facts, sentence, what the new rules say); the earlier checks let D's
# versions of these through
D_CASES = [
    ("values swapped", TOA_PAYOH, BASE.replace("3,835 1-2 room rental flats and 14,290 residents",
                                               "14,290 1-2 room rental flats and 3,835 residents"), "not as given"),
    ("values swapped", TENGAH, SAID["TENGAH"].replace("64% of HDB flats beyond 400 m of a refuge and 55%",
                                                      "55% of HDB flats beyond 400 m of a refuge and 64%"), "not as given"),
    ("labels dropped or changed", TOA_PAYOH, BASE.replace("3,835 1-2 room rental flats and 14,290 residents aged 75+",
                                               "3,835 and 14,290"), "not as given"),
    ("labels dropped or changed", TOA_PAYOH, BASE.replace("3,835 1-2 room rental flats and 14,290 residents aged 75+",
                                               "3,835 rental flats and 14,290 seniors"), "not as given"),
    ("ranks in other words", TOA_PAYOH, BASE.replace("flats and", "flats, ranked 2nd of 32 rated areas, and"), "beyond the facts"),
    ("ranks in other words", TOA_PAYOH, BASE.replace("flats and", "flats (2nd largest number of 32 rated areas) and"), "bracket"),
    ("ranks in other words", TOA_PAYOH, BASE.replace("flats and", "flats, the most 1-2 room rental flats of any rated area, and"),
     "beyond the facts"),
    ("residents", TOA_PAYOH, BASE[:-1] + ", many of whom live on their own.", "beyond the facts"),
    ("residents", TOA_PAYOH, BASE[:-1] + ", frail and isolated.", "beyond the facts"),
    ("residents", TOA_PAYOH, BASE[:-1] + " who cannot afford to cool their homes.", "beyond the facts"),
    ("residents", TOA_PAYOH, BASE[:-1] + " in needy households.", "beyond the facts"),
    ("superlatives", TOA_PAYOH, BASE[:-1] + ", the most vulnerable area.", "beyond the facts"),
    ("superlatives", TOA_PAYOH, BASE[:-1] + ", in the hottest part of Singapore.", "beyond the facts"),
    ("reassurance", AMK, SAID["ANG MO KIO"][:-1] + ", so no action is needed.", "beyond the facts"),
    ("reassurance", AMK, SAID["ANG MO KIO"][:-1] + ", so it is safe.", "beyond the facts"),
    ("the peak as the cause", TOA_PAYOH, BASE.replace("heat and", "heat as its station reached 30.5 °C, and"), "beyond the facts"),
    ("the peak as the cause", TOA_PAYOH, BASE[:-1] + ", in line with the 30.5 °C peak on 25 Oct.", "beyond the facts"),
    ("the peak as the cause", TOA_PAYOH, BASE.replace("forecast Moderate heat",
                                                      "its 30.5 °C peak on 25 Oct points to forecast Moderate heat"),
     "beyond the facts"),
    ("the peak as the cause", TOA_PAYOH, BASE.replace("heat and", "heat on the back of a 30.5 °C peak, and"), "beyond the facts"),
    ("confidence in words", TOA_PAYOH, BASE.replace("forecast Moderate", "almost certainly forecast Moderate"),
     "beyond the facts"),
    ("confidence in words", TOA_PAYOH, BASE[:-1] + ", with long odds of anything worse.", "beyond the facts"),
    ("confidence in words", TOA_PAYOH, BASE[:-1] + ", though it could turn High.", "beyond the facts"),
    ("confidence in words", HIGH_TP, BASE.replace("Medium: forecast Moderate heat", "High: a near-certain High-heat day"),
     "beyond the facts"),
    ("tier and heat words mixed", TOA_PAYOH, BASE.replace("vulnerability,", "vulnerability, a High-risk area"),
     "beyond the facts"),
    ("tier and heat words mixed", TOA_PAYOH, BASE.replace("vulnerability,", "vulnerability, a Moderate-tier area"),
     "beyond the facts"),
    ("advice", TOA_PAYOH, BASE[:-1] + "; call the rental blocks.", "beyond the facts"),
    ("advice", TOA_PAYOH, BASE[:-1] + "; consider visiting the rental blocks.", "beyond the facts"),
    ("advice", TOA_PAYOH, BASE[:-1] + "; keep an eye on its seniors.", "beyond the facts"),
    ("numbers in words outside the App's list", TOA_PAYOH, BASE.replace("75+.", "75+ in fifteen blocks."), "beyond the facts"),
    ("numbers in words outside the App's list", TOA_PAYOH, BASE.replace("75+.", "75+, sixty of them in rental blocks."),
     "beyond the facts"),
    ("observed values", TOA_PAYOH, BASE[:-1] + "; its station observed a peak WBGT of 32 on 25 Oct.", "beyond the facts"),
    ("observed values", TOA_PAYOH, BASE[:-1] + "; its station observed a peak WBGT of 30.5 °C (High) on 25 Oct.", "bracket"),
    ("other", TOA_PAYOH, BASE[:-1] + "; its station observed a peak WBGT of 30.5 °C on Saturday.", "beyond the facts"),
    ("other", TOA_PAYOH, BASE[:-1] + ", around Tiong Bahru.", "beyond the facts"),
    ("other", TOA_PAYOH, BASE[:-1] + ", near Jurong.", "beyond the facts"),
    ("other", TOA_PAYOH, BASE.replace("for vulnerability,", "for vulnerability, High vulnerability,"), "beyond the facts"),
]


def test_the_stored_26_oct_sentences_and_templates_pass():
    """The 31 AI sentences and 32 templates of 26 Oct, from a read-only SELECT of gold.area_tier_explanation."""
    ai = [r for r in STORED if r["written_by"] == E.AI]
    assert len(STORED) == 32 and len(ai) == 31
    assert [r["planning_area"] for r in ai if E.check(r["ai_sentence"], r["facts"])] == []
    assert [r["planning_area"] for r in STORED if E.check(r["template_sentence"], r["facts"])] == []
    clementi = next(r for r in STORED if r["written_by"] == E.TEMPLATE)
    assert "not as given: 10,410 residents aged 75+" in E.check(clementi["ai_sentence"], clementi["facts"])


def test_window_ds_controls_pass():
    """The stored sentence, the same with its true rank, and the same with the peak in the prompt's form."""
    assert BASE == ("Medium: forecast Moderate heat and the upper third for vulnerability, with 3,835 1-2 room rental flats "
                    "and 14,290 residents aged 75+.")
    for s in (BASE, BASE.replace("flats and", "flats (5th most of 32 rated areas) and"),
              BASE[:-1] + "; its station observed a peak WBGT of 30.5 °C (Low) on 25 Oct."):
        assert E.check(s, TOA_PAYOH) == [], s


@pytest.mark.parametrize("group, facts, sentence, said", D_CASES, ids=[f"{c[0]}-{i}" for i, c in enumerate(D_CASES)])
def test_window_ds_wrong_sentences_fall_back(group, facts, sentence, said):
    failed = E.check(sentence, facts)
    assert any(f.startswith(said) for f in failed), failed
    assert E.choose(facts, sentence)["written_by"] == E.TEMPLATE


def test_every_group_of_window_ds_table_is_covered_by_a_case_only_the_new_rules_catch():
    assert {c[0] for c in D_CASES} == {
        "values swapped", "labels dropped or changed", "ranks in other words", "residents", "superlatives",
        "reassurance", "the peak as the cause", "confidence in words", "tier and heat words mixed", "advice",
        "numbers in words outside the App's list", "observed values", "other"}
    new = ("not as given", "bracket", "beyond the facts", "observation")  # rules (a) to (d)
    only_new = {g for g, f, s, _ in D_CASES if all(x.startswith(new) for x in E.check(s, f))}
    assert only_new == {c[0] for c in D_CASES}


# Rule (d), window D's re-review 2: its six misses (the first six, on Toa Payoh's facts: the forecast is Moderate, for 26
# Oct; the station observed 30.5 °C, Low, on 25 Oct), each of facts and frame words only, then similar swaps
NO_PEAK_TP = {k: v for k, v in TOA_PAYOH.items() if k != "observed_heat"}
SWAPS = [
    (TOA_PAYOH, BASE.replace("forecast Moderate heat", "its station observed Moderate heat")),
    (TOA_PAYOH, BASE.replace("forecast Moderate heat", "forecast Moderate heat on 25 Oct")),
    (TOA_PAYOH, BASE.replace("forecast Moderate heat", "forecast Moderate heat with a peak of 30.5 °C on 25 Oct")),
    (TOA_PAYOH, BASE[:-1] + "; forecast peak WBGT of 30.5 °C on 25 Oct."),
    (TOA_PAYOH, BASE[:-1] + "; its station observed 30.5 °C on 25 Oct with Moderate heat."),
    (TOA_PAYOH, BASE.replace("forecast Moderate heat", "forecast Moderate heat on 25 Oct: 30.5 °C (Low),")),
    (TOA_PAYOH, BASE[:-1] + "; its station observed a peak WBGT of 30.5 °C (Low) on 25 Oct, Moderate heat."),
    (TOA_PAYOH, BASE.replace("Medium: forecast Moderate heat", "Medium: a peak WBGT of 30.5 °C on 25 Oct; forecast Moderate heat")),
    (TOA_PAYOH, BASE.replace("forecast Moderate heat", "forecast Moderate heat at its station")),
    (TOA_PAYOH, BASE[:-1] + "; its station observed a peak WBGT of 30.5 °C on 25 Oct, as forecast."),
    (TOA_PAYOH, BASE[:-1] + "; its station observed High heat, a peak WBGT of 30.5 °C on 25 Oct."),
    (HIGH_TP, BASE.replace("Medium: forecast Moderate heat", "High: forecast High heat")[:-1]
     + "; its station observed High heat, a peak WBGT of 30.5 °C on 25 Oct."),
    (NO_PEAK_TP, BASE[:-1] + "; its station observed a peak."),
]


@pytest.mark.parametrize("facts, sentence", SWAPS, ids=[f"swap-{i}" for i in range(len(SWAPS))])
def test_the_forecast_and_the_observation_swapped_fall_back(facts, sentence):
    failed = E.check(sentence, facts)
    assert any(f.startswith("observation") for f in failed), failed
    assert E.choose(facts, sentence)["written_by"] == E.TEMPLATE


def test_window_ds_six_misses_were_caught_by_rule_d_alone():
    for facts, sentence in SWAPS[:6]:
        assert E.check(sentence, facts) == E.observation_out_of_place(sentence, facts) != [], sentence


def test_rule_d_costs_two_true_wordings():
    """True, but outside the rule: the observation after a comma, not a semicolon; and the category as a heat word
    rather than in the bracket after the peak (window D's prototype let Changi's pass). Both fall back to the template."""
    assert E.observation_out_of_place(BASE[:-1] + ", and its station observed a peak WBGT of 30.5 °C (Low) on 25 Oct.",
                                      TOA_PAYOH)
    changi = FACTS["CHANGI"]
    true = SAID["CHANGI"].replace("its station observed a peak", "its station observed Moderate heat, a peak")
    assert changi["observed_heat"]["nea_category"] == "Moderate"
    assert E.check(true, changi) == ["observation clause holds a forecast or heat-level word: Moderate"]


def test_every_stored_template_keeps_the_observation_in_its_own_clause():
    assert [r["planning_area"] for r in STORED if E.observation_out_of_place(r["template_sentence"], r["facts"])] == []
    assert sum("observed_heat" in r["facts"] for r in STORED) == 32  # every row has the clause to test


# --- the prompt and the SQL --------------------------------------------------------------------------------------------

def test_the_prompt_carries_the_rules_and_its_examples_pass_the_check():
    for rule in ("using only the facts given", "at most 35 words", 'Begin with the tier, exactly "<<tier>>:"',
                 "plain English", "No advice", "probability, chance, likelihood", "no number in words",
                 "not alone, poor, low-income or without air-con", "never say or suggest that it explains the tier"):
        assert rule in E.PROMPT, rule
    examples = re.findall(r"^Facts: (\{.*\})\nSentence: (.*)$", E.PROMPT, re.M)
    assert len(examples) == 3
    for facts, sentence in examples:
        f = json.loads(facts)
        assert E.check(sentence, f) == [], sentence
        assert f["area"].upper() not in A.PLANNING_AREAS
    req = E.request(TP)
    assert 'exactly "Medium:"' in req and req.endswith(json.dumps(TP, ensure_ascii=False, indent=2))


def test_no_sql_reads_what_is_never_shown():
    reads = [E.latest_date_sql("coolcheck"), E.heat_sql("coolcheck", "2026-10-26"), E.vulnerability_sql("coolcheck"),
             E.observed_sql("coolcheck", "2026-10-26"), E.ai_sql(), E.write_sql("coolcheck", "2026-10-26")]
    for sql in reads:
        for word in E.NEVER_READ:
            assert not re.search(rf"\b{word}\b", sql, re.I), (word, sql)
    assert not {c for c, _, _ in E.COLUMNS} & set(E.NEVER_READ)
    assert "DATE'2026-10-25'" in E.observed_sql("coolcheck", "2026-10-26")  # the day before
    assert "REPLACE WHERE target_date = DATE'2026-10-26'" in E.write_sql("coolcheck", date(2026, 10, 26))
    assert "'temperature', 0.0D" in E.ai_sql() and "failOnError => false" in E.ai_sql() and E.MODEL in E.ai_sql()
    with pytest.raises(ValueError):
        E.heat_sql("coolcheck; DROP", "2026-10-26")
    with pytest.raises(ValueError):
        E.heat_sql("coolcheck", "2026-10-26' OR '1")
