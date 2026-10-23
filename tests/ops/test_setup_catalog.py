"""setup_catalog.py: the trial defaults, Free Edition's existing catalog, the Volume, refused names, the dry run."""
import sys

import pytest

import setup_catalog as SC
from ops_fakes import FakeSession

SCHEMAS = ["bronze", "silver", "gold", "ml"]


def test_trial_defaults_keep_the_schemas_and_add_the_volume():
    assert SC.statements("coolcheck", catalog_exists=False) == (
        ["CREATE CATALOG IF NOT EXISTS coolcheck"]
        + [f"CREATE SCHEMA IF NOT EXISTS coolcheck.{s}" for s in SCHEMAS]
        + ["CREATE VOLUME IF NOT EXISTS coolcheck.bronze.raw_files"])


def test_an_existing_catalog_is_not_created():
    assert SC.statements("workspace", catalog_exists=True) == (
        [f"CREATE SCHEMA IF NOT EXISTS workspace.{s}" for s in SCHEMAS]
        + ["CREATE VOLUME IF NOT EXISTS workspace.bronze.raw_files"])


@pytest.mark.parametrize("bad", ["work-space", "coolcheck; DROP SCHEMA x", "", "1abc", "a.b"])
def test_a_name_that_is_not_a_plain_identifier_is_refused(bad):
    with pytest.raises(ValueError):
        SC.statements(bad, catalog_exists=True)


def test_dry_run_prints_the_statements_and_connects_to_nothing(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "databricks.connect", None)  # any import of it would now fail
    assert SC.main(["--dry-run", "--catalog", "workspace"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "CREATE CATALOG IF NOT EXISTS workspace;  -- only if the catalog is missing"
    assert out[-1] == "CREATE VOLUME IF NOT EXISTS workspace.bronze.raw_files;"


def test_the_defaults_are_the_trial(fake_connect):
    session = FakeSession(catalogs=("coolcheck", "system"))
    builder = fake_connect(session)
    assert SC.main([]) == 0
    assert builder.profile_used == "coolcheck"
    assert [s for s in session.sqls if s.startswith("CREATE")] == SC.statements("coolcheck", catalog_exists=True)


def test_free_edition_uses_its_profile_and_skips_the_existing_catalog(fake_connect):
    session = FakeSession(catalogs=("system", "samples", "workspace"))
    builder = fake_connect(session)
    assert SC.main(["--catalog", "workspace", "--profile", "freeedition"]) == 0
    assert builder.profile_used == "freeedition"
    created = [s for s in session.sqls if s.startswith("CREATE")]
    assert created == SC.statements("workspace", catalog_exists=True)
    assert not any(s.startswith("CREATE CATALOG") for s in session.sqls)


def test_a_missing_catalog_is_created_first(fake_connect):
    session = FakeSession(catalogs=("system",))
    fake_connect(session)
    assert SC.main(["--catalog", "newcat"]) == 0
    assert [s for s in session.sqls if s.startswith("CREATE")][0] == "CREATE CATALOG IF NOT EXISTS newcat"


def test_a_failed_statement_stops_the_run_with_exit_1(fake_connect, capsys):
    session = FakeSession(catalogs=("workspace",), fail_on="CREATE VOLUME")
    fake_connect(session)
    assert SC.main(["--catalog", "workspace", "--profile", "freeedition"]) == 1
    assert "CREATE VOLUME IF NOT EXISTS workspace.bronze.raw_files failed" in capsys.readouterr().err
