"""Local tests for the operations scripts (catalog setup, raw upload, reconcile report, Silver check). Nothing here
touches a workspace: Databricks Connect is replaced by a fake session that records what it is asked to do."""
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops_fakes import FakeBuilder

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "scripts" / "upload", ROOT / "scripts" / "reconcile", ROOT / "scripts" / "checks"):
    sys.path.insert(0, str(p))


@pytest.fixture
def fake_connect(monkeypatch):
    """Returns a function that installs a fake databricks.connect around the given session and returns its builder."""
    def install(session):
        builder = FakeBuilder(session)
        mod = types.ModuleType("databricks.connect")
        mod.DatabricksSession = SimpleNamespace(builder=builder)
        monkeypatch.setitem(sys.modules, "databricks.connect", mod)
        return builder
    return install
