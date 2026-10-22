"""Fixtures for the back-test tests. Most run locally on pandas frames; a test that asks for `spark` runs through
Databricks Connect on serverless (profile coolcheck)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


@pytest.fixture(scope="session")
def spark():
    from databricks.connect import DatabricksSession
    s = DatabricksSession.builder.serverless().profile("coolcheck").getOrCreate()
    s.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    return s
