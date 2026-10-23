"""--catalog and --profile for the two static loaders (load_area_exposure.py, area_station_distance.py --load).

Nothing here touches a workspace: databricks.connect is replaced by a fake session that records the profile, the tables
written and read, and every SQL statement. The defaults stay the trial (catalog and profile coolcheck).
"""
import csv
import json
import sys
import types
from types import SimpleNamespace

import pytest

import area_station_distance as ASD
import load_area_exposure as LAE


class FakeFrame:
    def __init__(self, session, rows):
        self.session, self.rows = session, rows
        self.write = self

    def mode(self, m):
        return self

    def option(self, k, v):
        return self

    def saveAsTable(self, name):
        self.session.saved[name] = self.rows

    def count(self):
        return len(self.rows)


class FakeSession:
    def __init__(self):
        self.saved, self.sqls, self.read = {}, [], []

    def createDataFrame(self, rows, schema):
        return FakeFrame(self, list(rows))

    def sql(self, s):
        self.sqls.append(s)
        return SimpleNamespace(first=lambda: {"version": 7})

    def table(self, name):
        self.read.append(name)
        return FakeFrame(self, self.saved.get(name, []))


class FakeBuilder:
    def __init__(self, session):
        self.session, self.profile_used = session, None

    def serverless(self):
        return self

    def profile(self, name):
        self.profile_used = name
        return self

    def getOrCreate(self):
        return self.session


@pytest.fixture
def fake_connect(monkeypatch):
    session = FakeSession()
    builder = FakeBuilder(session)
    mod = types.ModuleType("databricks.connect")
    mod.DatabricksSession = SimpleNamespace(builder=builder)
    monkeypatch.setitem(sys.modules, "databricks.connect", mod)
    return builder, session


# --- load_area_exposure.py --------------------------------------------------------------------------------------------

@pytest.fixture
def exposure_data(tmp_path):
    """An area_exposure.csv that passes the loader's checks: 55 areas, the Guide's totals, 41 areas with residents 65+."""
    rows = []
    for i in range(55):
        n, a65, a75 = (100, 1, 1) if 0 < i < 41 else (100, 0, 0)
        rows.append([f"AREA {i:02d}", f"A{i:02d}", "R", n, a65, a75])
    rows[0][3:] = [4_199_180 - 100 * 54, 806_080 - 40, 310_310 - 40]
    (tmp_path / "analysis").mkdir()
    with (tmp_path / "analysis" / "area_exposure.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(LAE.COLUMNS)
        w.writerows([r + [round(r[4] / r[3], 6), round(r[5] / r[3], 6)] for r in rows])
    return tmp_path


def test_area_exposure_defaults_are_the_trial(exposure_data, fake_connect):
    builder, session = fake_connect
    LAE.main(["--data", str(exposure_data)])
    assert builder.profile_used == "coolcheck"
    assert list(session.saved) == ["coolcheck.silver.area_exposure"] and len(session.saved["coolcheck.silver.area_exposure"]) == 55
    assert session.read == ["coolcheck.silver.area_exposure"]
    assert all("coolcheck.silver.area_exposure" in s for s in session.sqls) and len(session.sqls) == 2


def test_area_exposure_free_edition_catalog_and_profile(exposure_data, fake_connect):
    builder, session = fake_connect
    LAE.main(["--data", str(exposure_data), "--catalog", "workspace", "--profile", "freeedition"])
    assert builder.profile_used == "freeedition"
    assert list(session.saved) == ["workspace.silver.area_exposure"] and session.read == ["workspace.silver.area_exposure"]
    assert all("workspace.silver.area_exposure" in s for s in session.sqls)
    assert not any("coolcheck." in s for s in session.sqls)


def test_area_exposure_check_only_never_connects(exposure_data, fake_connect):
    builder, session = fake_connect
    LAE.main(["--data", str(exposure_data), "--catalog", "workspace", "--check-only"])
    assert builder.profile_used is None and not session.saved and not session.sqls


@pytest.mark.parametrize("bad", ["work-space", "coolcheck.silver", "x; DROP TABLE y", ""])
def test_area_exposure_rejects_a_bad_catalog(exposure_data, fake_connect, bad):
    builder, session = fake_connect
    with pytest.raises(SystemExit, match="bad catalog"):
        LAE.main(["--data", str(exposure_data), "--catalog", bad])
    assert builder.profile_used is None and not session.saved


# --- area_station_distance.py --load ---------------------------------------------------------------------------------

def square(x0, y0, size=0.02):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x0 + size, y0], [x0 + size, y0 + size], [x0, y0 + size], [x0, y0]]]}


@pytest.fixture
def distance_data(tmp_path):
    """Two areas (one an island holding station S1) and two stations: enough for main() to run end to end."""
    bnd = tmp_path / "bnd"
    bnd.mkdir()
    feats = [{"type": "Feature", "properties": {"PLN_AREA_N": "SOUTHERN ISLANDS", "PLN_AREA_C": "SI", "REGION_N": "C"},
              "geometry": square(103.80, 1.20)},
             {"type": "Feature", "properties": {"PLN_AREA_N": "AREA B", "PLN_AREA_C": "AB", "REGION_N": "C"},
              "geometry": square(103.90, 1.35)}]
    (bnd / "b.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
    (bnd / "provenance.json").write_text(json.dumps({"name": "test boundary", "dataset_id": "d_test", "file": "b.geojson",
                                                     "sha256": "0" * 64}), encoding="utf-8")
    raw = tmp_path / "raw" / "wbgt"
    raw.mkdir(parents=True)
    readings = [{"station": {"id": "S1", "name": "Island"}, "location": {"latitude": "1.21", "longitude": "103.81"}},
                {"station": {"id": "S2", "name": "Town"}, "location": {"latitude": "1.36", "longitude": "103.91"}}]
    (raw / "wbgt_2026-01-01.jsonl").write_text(json.dumps({"data": {"records": [{"item": {"readings": readings}}]}}) + "\n",
                                               encoding="utf-8")
    return tmp_path


def distance_args(data, *extra):
    return ["--data", str(data), "--out", str(data / "out.csv"), "--no-blocks", "--boundary", "mp2025=bnd",
            "--expect-offshore", "S1", *extra]


def test_area_station_distance_load_defaults_are_the_trial(distance_data, fake_connect):
    builder, session = fake_connect
    ASD.main(distance_args(distance_data, "--load"))
    assert builder.profile_used == "coolcheck"
    assert list(session.saved) == ["coolcheck.silver.area_station_distance"]
    assert len(session.saved["coolcheck.silver.area_station_distance"]) == 4  # 2 areas x 2 stations
    assert session.read == ["coolcheck.silver.area_station_distance"]
    assert len(session.sqls) == 1 and session.sqls[0].startswith("COMMENT ON TABLE coolcheck.silver.area_station_distance IS")


def test_area_station_distance_load_free_edition(distance_data, fake_connect):
    builder, session = fake_connect
    ASD.main(distance_args(distance_data, "--load", "--catalog", "workspace", "--profile", "freeedition"))
    assert builder.profile_used == "freeedition"
    assert list(session.saved) == ["workspace.silver.area_station_distance"]
    assert session.read == ["workspace.silver.area_station_distance"]
    assert session.sqls[0].startswith("COMMENT ON TABLE workspace.silver.area_station_distance IS")
    assert not any("coolcheck." in s for s in session.sqls)


def test_area_station_distance_without_load_never_connects(distance_data, fake_connect):
    builder, session = fake_connect
    ASD.main(distance_args(distance_data, "--catalog", "workspace"))
    assert builder.profile_used is None and not session.saved
    assert (distance_data / "out.csv").read_text(encoding="utf-8").count("\n") == 5  # header and four rows


def test_area_station_distance_rejects_a_bad_catalog(distance_data, fake_connect):
    builder, _ = fake_connect
    with pytest.raises(SystemExit, match="bad catalog"):
        ASD.main(distance_args(distance_data, "--load", "--catalog", "coolcheck.silver"))
    assert builder.profile_used is None
