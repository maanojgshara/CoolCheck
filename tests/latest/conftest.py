"""Fixtures for the latest-readings tests. They run through Databricks Connect on serverless (profile coolcheck)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "silver"))  # silver_fixtures: page and Bronze-row builders, read-only


@pytest.fixture(scope="session")
def spark():
    from databricks.connect import DatabricksSession
    s = DatabricksSession.builder.serverless().profile("coolcheck").getOrCreate()
    s.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    return s
