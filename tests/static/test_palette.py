"""coolcheck.palette, the Python port of the dataviz skill's validate_palette.js, and the briefing dashboard's colours.

The port is calibrated against the figures the skill documents for its reference palette (references/palette.md); then
every colour set the briefing uses is checked: the tiers and the neutral grey as categories (every pair at least 8 under
protan, deutan and tritan, and 15 under normal vision, all pairs since on a map any two can touch), the vulnerability
thirds as a one-hue ramp (the ordinal checks) kept apart from the grey, and the three point types of the Blocks map.
"""
import pytest

from coolcheck import briefing as B
from coolcheck import palette as P

LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]


@pytest.mark.parametrize("pal,pairs,cvd,normal", [(LIGHT, "adjacent", 9.1, 19.6), (DARK, "adjacent", 8.4, 19.3),
                                                  (LIGHT[:3], "all", 9.2, 24.0), (DARK[:3], "all", 9.4, 20.9)])
def test_port_reproduces_the_documented_figures(pal, pairs, cvd, normal):
    w = P.worst_pairs(pal, pairs)
    assert round(min(w["protan"][0], w["deutan"][0]), 1) == cvd and round(w["normal"][0], 1) == normal


def test_port_reproduces_the_documented_failures():
    assert round(P.worst_pairs(LIGHT[:4], "all")["normal"][0], 1) == 13.7  # yellow and orange together
    assert round(P.worst_pairs(DARK[:4], "all")["deutan"][0], 1) == 4.8


def test_tier_colours_and_neutral_pass_every_pair_under_each_deficiency():
    pal = [*B.TIER_COLOURS.values(), B.NEUTRAL]
    w = P.worst_pairs(pal, "all")
    assert all(w[k][0] >= 8 for k in ("protan", "deutan", "tritan")) and w["normal"][0] >= 15, w
    assert P.categorical_ok(pal)


def test_the_first_proposal_failed_low_against_the_grey():
    """The proposal of 23 Oct (Low #94d2bd, Not rated #bdbdbd) failed: 1.7 under deuteranopia."""
    w = P.worst_pairs(["#9b2226", "#ee9b00", "#94d2bd", "#bdbdbd"], "all")
    assert round(w["deutan"][0], 1) == 1.7 and {w["deutan"][1], w["deutan"][2]} == {"#94d2bd", "#bdbdbd"}


def test_thirds_are_a_one_hue_ramp_apart_from_the_grey():
    ramp = [B.THIRD_COLOURS[t] for t in ("lower", "middle", "upper")]
    assert all(ok for ok, _ in P.ordinal_checks(ramp).values()), P.ordinal_checks(ramp)
    for kind in ("protan", "deutan", "tritan"):
        assert min(P.delta_e(B.NEUTRAL, c, kind) for c in ramp) >= 8
    assert min(P.delta_e(B.NEUTRAL, c) for c in ramp) >= 15


def test_point_types_pass_every_pair_under_each_deficiency():
    assert P.categorical_ok(list(B.POINT_COLOURS.values()))


def test_bad_hex_is_refused():
    with pytest.raises(ValueError):
        P.delta_e("#12345", "#ffffff")
