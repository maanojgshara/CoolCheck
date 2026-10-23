"""Fixtures for the live-page tests. The SQL tests run through Databricks Connect on serverless (profile coolcheck)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(scope="session")
def spark():
    from databricks.connect import DatabricksSession
    s = DatabricksSession.builder.serverless().profile("coolcheck").getOrCreate()
    # the dashboard's warehouse runs in UTC; the queries must give SGT text whatever the session time zone
    s.conf.set("spark.sql.session.timeZone", "UTC")
    return s
