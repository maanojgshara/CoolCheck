"""scripts/static/planning_area_layers.py: the boundary rows, the park-to-area membership and the --load path.

The load runs against a fake databricks.connect that records the statements and answers the read-back queries, so
nothing touches a workspace.
"""
import csv
import json
import re
import sys
import types
from types import SimpleNamespace

import pytest
import shapely
from shapely.geometry import box, mapping

import planning_area_layers as PAL


def area(name, code, geom):
    return {"properties": {"PLN_AREA_N": name, "PLN_AREA_C": code, "REGION_N": "R"}, "geometry": mapping(geom)}


def test_boundary_rows_round_and_stay_valid():
    bow = shapely.Polygon([(103.80, 1.30), (103.81, 1.31), (103.81, 1.30), (103.80, 1.31)])  # invalid bow-tie
    rows = PAL.boundary_rows([area("B AREA", "BA", box(103.80, 1.30, 103.81, 1.31)), area("A AREA", "AA", bow)], "d_x")
    assert [r["planning_area"] for r in rows] == ["A AREA", "B AREA"]
    for r in rows:
        g = shapely.from_wkt(r["geometry_wkt"])
        assert g.is_valid and r["area_m2"] > 0 and r["source_dataset_id"] == "d_x"
        assert all(len(f"{c:.10f}".rstrip("0").split(".")[1]) <= 7 for c in shapely.get_coordinates(g).ravel())


def test_park_areas_shares_edges_and_parks_outside():
    areas = [("WEST", "W", box(0, 0, 100, 100)), ("EAST", "E", box(100, 0, 200, 100))]
    parks = [("p_cross", "Across", box(50, 0, 150, 10)),      # half in each
             ("p_edge", "Edge", box(80, 50, 100, 60)),        # inside WEST, touching EAST only along x = 100
             ("p_out", "Offshore", box(500, 500, 510, 510))]  # in no area
    rows, alone = PAL.park_areas(parks, areas)
    got = {(r["park_id"], r["planning_area"]): r for r in rows}
    assert set(got) == {("p_cross", "EAST"), ("p_cross", "WEST"), ("p_edge", "WEST")}
    assert got[("p_cross", "WEST")]["share_of_park"] == 0.5 and got[("p_cross", "EAST")]["area_in_planning_area_m2"] == 500.0
    assert got[("p_edge", "WEST")]["share_of_park"] == 1.0
    assert alone == ["p_out"]


class FakeSession:
    """Answers write_table's statements: records the tables written, their tags and every SQL statement."""

    def __init__(self):
        self.saved, self.sqls, self.tags = {}, [], {}

    def sql(self, s):
        self.sqls.append(s)
        rows = []
        m = re.match(r"ALTER TABLE (\S+) SET TAGS \((.*)\)$", s)
        if m:
            self.tags[m.group(1)] = re.findall(r"'([^']+)' = '", m.group(2))
        m = re.search(r"table_tags WHERE schema_name = '(\w+)' AND table_name = '(\w+)'", s)
        if m:
            t = next(k for k in self.tags if k.endswith(f".{m.group(1)}.{m.group(2)}"))
            rows = [{"tag_name": k, "tag_value": "v"} for k in self.tags[t]]
        return SimpleNamespace(collect=lambda: rows, first=lambda: {"version": 1})

    def createDataFrame(self, rows, schema):
        session = self

        class Frame:
            write = SimpleNamespace(mode=lambda m: SimpleNamespace(saveAsTable=lambda t: session.saved.__setitem__(t, rows)))
        return Frame()

    def table(self, t):
        return SimpleNamespace(count=lambda: len(self.saved[t]))


@pytest.fixture
def fake_connect(monkeypatch):
    session = FakeSession()
    builder = SimpleNamespace(profile_used=None)
    builder.serverless = lambda: builder

    def profile(name):
        builder.profile_used = name
        return builder
    builder.profile, builder.getOrCreate = profile, lambda: session
    mod = types.ModuleType("databricks.connect")
    mod.DatabricksSession = SimpleNamespace(builder=builder)
    monkeypatch.setitem(sys.modules, "databricks.connect", mod)
    return builder, session


@pytest.fixture
def layer_data(tmp_path):
    bnd = tmp_path / "static" / "ura_mp2025_planning_area_boundary"
    bnd.mkdir(parents=True)
    feats = [area(f"AREA {i:02d}", f"A{i:02d}", box(103.6 + 0.01 * i, 1.30, 103.61 + 0.01 * i, 1.31)) for i in range(55)]
    (bnd / "b.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
    (bnd / "provenance.json").write_text(json.dumps({"name": "test boundary", "agency": "URA", "dataset_id": "d_test",
                                                     "sha256": "0" * 64, "downloaded": "2026-10-21"}), encoding="utf-8")
    (tmp_path / "analysis").mkdir()
    with (tmp_path / "analysis" / "park_polygons.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["park_id", "name", "in_main", "geometry_wkt"])
        w.writerow(["np_A", "Across", "true", box(103.605, 1.301, 103.615, 1.302).wkt])
        w.writerow(["np_R", "Reserve", "false", box(103.60, 1.30, 103.61, 1.31).wkt])
    return tmp_path


def test_local_run_writes_both_csvs_and_never_connects(layer_data, fake_connect):
    builder, session = fake_connect
    PAL.main(["--data", str(layer_data)])
    assert builder.profile_used is None and not session.sqls
    with (layer_data / "analysis" / "park_planning_area.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [(r["park_id"], r["planning_area"]) for r in rows] == [("np_A", "AREA 00"), ("np_A", "AREA 01")]
    with (layer_data / "analysis" / "planning_area_boundary.csv").open(encoding="utf-8") as fh:
        assert sum(1 for _ in csv.DictReader(fh)) == 55


@pytest.mark.parametrize("args,catalog,profile", [([], "coolcheck", "coolcheck"),
                                                  (["--catalog", "workspace", "--profile", "freeedition"], "workspace", "freeedition")])
def test_load_writes_both_tables_with_comments_and_tags(layer_data, fake_connect, args, catalog, profile):
    builder, session = fake_connect
    PAL.main(["--data", str(layer_data), "--load", *args])
    assert builder.profile_used == profile
    assert set(session.saved) == {f"{catalog}.silver.planning_area_boundary", f"{catalog}.silver.park_planning_area"}
    assert len(session.saved[f"{catalog}.silver.planning_area_boundary"]) == 55
    creates = [s for s in session.sqls if s.startswith("CREATE OR REPLACE TABLE")]
    assert len(creates) == 2 and all(" COMMENT '" in s for s in creates)
    assert all(set(v) == {"source", "licence"} for v in session.tags.values())
    if catalog != "coolcheck":
        assert not any("coolcheck." in s for s in session.sqls)


def test_stops_unless_55_areas(layer_data, fake_connect):
    f = next((layer_data / "static" / "ura_mp2025_planning_area_boundary").glob("*.geojson"))
    gj = json.loads(f.read_text(encoding="utf-8"))
    gj["features"] = gj["features"][:54]
    f.write_text(json.dumps(gj), encoding="utf-8")
    with pytest.raises(SystemExit, match="54 planning areas"):
        PAL.main(["--data", str(layer_data)])
