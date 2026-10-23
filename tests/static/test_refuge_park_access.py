"""Tests for src/coolcheck/access.py (refuge and park layers, R1 and R2) on small fixtures.

The geometry runs in plain Python, so most tests are local. test_sql_distance_matches_python runs through Databricks
Connect (serverless, profile coolcheck): it checks that SQL on the stored x_svy21 / y_svy21 gives the same nearest
distances, the rule what_if_add_refuge will use.
"""
import math

import pytest
from shapely.geometry import Polygon, box

from coolcheck import access as A


# --- projection ---------------------------------------------------------------------------------------------------

def test_svy21_origin_maps_to_false_easting_and_northing():
    x, y = A.to_svy21(103 + 50 / 60, 1 + 22 / 60)
    assert x == pytest.approx(28001.642, abs=1e-3) and y == pytest.approx(38744.572, abs=1e-3)


def test_svy21_matches_a_go_to_points_record():
    # Geylang East Active Ageing Centre (AAC), MOH Go-To-Points: lon/lat and the file's own X_ADDR / Y_ADDR
    x, y = A.to_svy21(103.8856973658133, 1.3208652560069727)
    assert x == pytest.approx(33829.24171, abs=1e-3) and y == pytest.approx(33680.14758, abs=1e-3)


def test_geom_to_svy21_drops_z():
    g = A.geom_to_svy21(Polygon([(103.8, 1.3, 0), (103.81, 1.3, 0), (103.81, 1.31, 0)]))
    assert not g.has_z and g.area > 0


def test_polygonal_repairs_a_bow_tie():
    bow = Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])
    fixed = A.polygonal(bow)
    assert fixed.is_valid and fixed.geom_type in ("Polygon", "MultiPolygon") and fixed.area == pytest.approx(50)


# --- distances and shares -----------------------------------------------------------------------------------------

def test_nearest_points_straight_line_and_index():
    d, i = A.nearest_points([0, 300, 1000], [0, 0, 0], [0, 1000], [400, 0])
    assert list(d) == pytest.approx([400, 500, 0]) and list(i) == [0, 0, 1]


def test_nearest_polygons_zero_inside_and_edge_distance_outside():
    d, i = A.nearest_polygons([50, 150, 50], [50, 50, 260], [box(0, 0, 100, 100), box(0, 200, 100, 250)])
    assert list(d) == pytest.approx([0, 50, 10]) and list(i) == [0, 0, 1]


def test_share_within_counts_400_m_as_within_and_weights_by_units():
    assert A.share_within([399.9, 400.0, 400.1], [10, 20, 70]) == pytest.approx(0.3)


def test_share_within_is_none_without_units():
    assert A.share_within([], []) is None and A.share_within([10], [0]) is None


def test_merge_layer_counts_overlap_once_and_drops_isolated_slivers():
    big, overlap = box(0, 0, 100, 100), box(50, 0, 150, 100)
    touching = box(150, 0, 155, 5)          # 25 m2, touches the merged park: kept as part of it
    isolated = box(500, 500, 505, 505)      # 25 m2 on its own: dropped
    kept, dropped = A.merge_layer([big, overlap, touching, isolated])
    assert len(kept) == 1 and kept[0].area == pytest.approx(15000 + 25)
    assert len(dropped) == 1 and dropped[0].area == pytest.approx(25)


def test_merge_layer_keeps_a_piece_of_exactly_100_m2():
    kept, dropped = A.merge_layer([box(0, 0, 10, 10)])
    assert len(kept) == 1 and not dropped


def test_area_share_only_counts_park_inside_the_area():
    area = box(0, 0, 100, 100)
    kept, _ = A.merge_layer([box(50, 0, 150, 100), box(60, 0, 80, 50)])
    m2, share = A.area_share(kept, area)
    assert m2 == pytest.approx(5000) and share == pytest.approx(0.5)


def test_assign_areas_inside_tolerance_and_outside():
    areas = [("A", box(0, 0, 100, 100)), ("B", box(200, 0, 300, 100))]
    got = A.assign_areas([50, 110, 150, 100], [50, 50, 50, 50], areas)
    assert got[0] == ("A", 0.0) and got[1] == ("A", pytest.approx(10))
    assert got[2][0] is None and got[2][1] == pytest.approx(50)
    assert got[3] == ("A", 0.0)                 # on the edge counts as inside


def test_rank_worst_first_mean_rank_for_ties_and_none_left_out():
    assert A.rank_worst_first({"a": 0.1, "b": 0.5, "c": 0.5, "d": 0.9, "e": None}) == {"a": 1, "b": 2.5, "c": 2.5, "d": 4}


def test_spearman_same_order_reversed_and_constant():
    a = {"p": 1, "q": 2, "r": 3, "s": 4}
    assert A.spearman(a, {k: v * 10 for k, v in a.items()}) == pytest.approx(1)
    assert A.spearman(a, {k: -v for k, v in a.items()}) == pytest.approx(-1)
    assert A.spearman(a, {k: 1 for k in a}) is None


# --- layer rules --------------------------------------------------------------------------------------------------

def test_clean_name_replaces_the_broken_character():
    assert A.clean_name("THK�Active Ageing Centre�@ Toa Payoh 15") == "THK Active Ageing Centre @ Toa Payoh 15"
    assert A.clean_name("Allkin Singapore -�Allkin  AAC") == "Allkin Singapore - Allkin AAC"


@pytest.mark.parametrize("raw,want", [("58284", "058284"), (89774, "089774"), ("828815", "828815"), (828815, "828815"),
                                      ("828815.0", "828815"), ("", ""), (None, "")])
def test_pad_postal(raw, want):
    assert A.pad_postal(raw) == want


@pytest.mark.parametrize("name,want", [("Kim Seng CC (U/C)", "under_construction"),
                                       ("Bukit Batok CC (Temp office)", "temp_office"),
                                       ("Marine Parade CC (Temp Office)", "temp_office"),
                                       ("Sembawang Central CO @ Sembawang CC (U/C)", "under_construction"),
                                       ("Braddell Heights CC (Pending U/C)", "open"), ("Punggol 21 CC", "open")])
def test_club_status(name, want):
    assert A.club_status(name) == want


@pytest.mark.parametrize("name,want", [("Geylang East Active Ageing Centre (AAC)", "aac"),
                                       ("Lions Befrienders Active Ageing Hub (Bedok)", "aac"),
                                       ("NTUC Health AAH @ Kampung Admiralty", "aac"),
                                       ("AWWA Senior Activity Centre (SAC) @ Yio Chu Kang", "sac"),
                                       ("REACH Senior Centre (SAC) @ Bukit Gombak Vista", "sac"),
                                       ("REACH Senior Centre @ Jalan Membina", "possible_aac"),
                                       ("Anglican Senior Centre (Yishun)", "possible_aac"),
                                       ("Active Global Active Care Centre @ Fernvale Glades", "possible_aac"),
                                       ("Lentor Health Senior Care Centre", None), ("St Luke's ElderCare (Clementi Centre)", None),
                                       ("NTUC FairPrice", None)])
def test_gtp_kind(name, want):
    assert A.gtp_kind(name) == want


@pytest.mark.parametrize("name,want", [("THK SAC @ Kaki Bukit", "sac"), ("Yuhua Senior Activity Centre", "sac"),
                                       ("Silver Ace@Redhill", "silver_ace"), ("Silver ACE @ Bukit Merah", "silver_ace"),
                                       ("Econ Health and Wellness Centre", "other")])
def test_eldercare_kind(name, want):
    assert A.eldercare_kind(name) == want


def _r(rid, layer, name, postal, status="open"):
    return {"refuge_id": rid, "layer": layer, "name": name, "postal_code": postal, "status": status}


def test_dedupe_keeps_host_club_aac_over_sac_and_skips_under_construction():
    rows = A.dedupe([
        _r("cc_2", "community_club", "Limbang CO c/o Yew Tee CC", "689286"),
        _r("cc_1", "community_club", "Yew Tee CC", "689286"),
        _r("cc_3", "community_club", "Kim Seng CC (U/C)", "169640", "under_construction"),
        _r("cc_4", "community_club", "Bukit Batok CC (Temp office)", "650119", "temp_office"),
        _r("gtp_1", "aac_partial", "Some AAC", "380098"),
        _r("eld_1", "eldercare_sac_2016", "Some SAC", "380098"),
        _r("gtp_2", "gtp_sac", "AWWA SAC", "560123"),
        _r("eld_2", "eldercare_sac_2016", "AWWA SAC old", "560123"),
        _r("eld_3", "eldercare_sac_2016", "Lone SAC", "111111"),
    ])
    by = {r["refuge_id"]: r for r in rows}
    assert by["cc_2"]["duplicate_of"] == "cc_1" and by["cc_1"]["duplicate_of"] == ""
    assert [by["cc_1"][f"in_{s}"] for s in ("clubs_only", "main", "with_sac_2016")] == [True, True, True]
    assert not any(by["cc_2"][f"in_{s}"] for s in A.REFUGE_SETS)
    assert not any(by["cc_3"][f"in_{s}"] for s in A.REFUGE_SETS) and by["cc_3"]["duplicate_of"] == ""
    assert by["cc_4"]["in_main"]
    assert (by["gtp_1"]["in_clubs_only"], by["gtp_1"]["in_main"], by["gtp_1"]["in_with_sac_2016"]) == (False, True, True)
    assert by["eld_1"]["duplicate_of"] == "gtp_1" and not by["eld_1"]["in_with_sac_2016"]
    assert by["eld_2"]["duplicate_of"] == "gtp_2" and by["gtp_2"]["in_with_sac_2016"] and not by["gtp_2"]["in_main"]
    assert by["eld_3"]["in_with_sac_2016"] and not by["eld_3"]["in_main"]
    sites = {s: sum(r[f"in_{s}"] for r in rows) for s in A.REFUGE_SETS}
    assert sites == {"clubs_only": 2, "main": 3, "with_sac_2016": 5}


def test_dedupe_open_club_kept_before_temp_office_at_the_same_postal_code():
    rows = A.dedupe([_r("cc_9", "community_club", "A CC (Temp Office)", "100001", "temp_office"),
                     _r("cc_8", "community_club", "Z CC", "100001")])
    assert {r["refuge_id"]: r["duplicate_of"] for r in rows} == {"cc_9": "cc_8", "cc_8": ""}


def test_dedupe_under_construction_row_never_absorbs_an_open_one():
    rows = A.dedupe([_r("cc_1", "community_club", "A CC (U/C)", "100001", "under_construction"),
                     _r("gtp_1", "aac_partial", "An AAC", "100001")])
    by = {r["refuge_id"]: r for r in rows}
    assert by["gtp_1"]["in_main"] and by["gtp_1"]["duplicate_of"] == ""


# --- SQL gives the same distances (Databricks Connect) -------------------------------------------------------------

@pytest.fixture(scope="module")
def spark():
    from databricks.connect import DatabricksSession
    return DatabricksSession.builder.serverless().profile("coolcheck").getOrCreate()


def test_sql_distance_matches_python(spark):
    blocks = [("b1", 30000.125, 35000.5), ("b2", 31234.567, 36789.012), ("b3", 28001.642, 38744.572)]
    refuges = [("r1", 30100.0, 35100.0), ("r2", 31000.25, 37000.75), ("r3", 28400.0, 38744.572)]
    d, i = A.nearest_points([b[1] for b in blocks], [b[2] for b in blocks], [r[1] for r in refuges], [r[2] for r in refuges])
    spark.createDataFrame(blocks, "blk STRING, x_svy21 DOUBLE, y_svy21 DOUBLE").createOrReplaceTempView("t_blocks")
    spark.createDataFrame(refuges, "refuge_id STRING, x_svy21 DOUBLE, y_svy21 DOUBLE").createOrReplaceTempView("t_refuges")
    got = {r["blk"]: (r["d"], r["refuge_id"]) for r in spark.sql("""
        SELECT blk, min_by(refuge_id, d) AS refuge_id, min(d) AS d FROM (
          SELECT b.blk, r.refuge_id, sqrt(pow(b.x_svy21 - r.x_svy21, 2) + pow(b.y_svy21 - r.y_svy21, 2)) AS d
          FROM t_blocks b CROSS JOIN t_refuges r) GROUP BY blk""").collect()}
    for (blk, _, _), dd, ii in zip(blocks, d, i):
        assert math.isclose(got[blk][0], dd, abs_tol=1e-9) and got[blk][1] == refuges[ii][0]
