"""create_agent_functions.py keeps each function's grants across CREATE OR REPLACE (24 Oct: the replace dropped the App's
EXECUTE on find_refuges and what_if_add_refuge). Local: a fake workspace whose CREATE OR REPLACE drops the grants, as Unity
Catalog does."""
from types import SimpleNamespace

import pytest

pytest.importorskip("databricks.sdk")
from databricks.sdk.errors import NotFound  # noqa: E402
from databricks.sdk.service.catalog import Privilege  # noqa: E402

import create_agent_functions as C  # noqa: E402

FN = "coolcheck.gold.find_refuges"
APP = "2a3eee76-0000-0000-0000-000000000000"  # a made-up application ID


class FakeGrants:
    def __init__(self, grants, page=None):
        self.grants = {k: set(v) for k, v in grants.items()}
        self.page = page  # principals per page, to test paging
        self.updates = []

    def get(self, securable_type, full_name, page_token=None):
        assert securable_type == "function" and full_name == FN
        if self.grants is None:
            raise NotFound("no such function")
        items = sorted(self.grants.items())
        start = int(page_token or 0)
        end = len(items) if not self.page else start + self.page
        return SimpleNamespace(privilege_assignments=[SimpleNamespace(principal=p, privileges=[Privilege(x) for x in v])
                                                      for p, v in items[start:end]],
                               next_page_token=str(end) if end < len(items) else None)

    def update(self, securable_type, full_name, changes):
        self.updates.append(changes)
        for c in changes:
            self.grants.setdefault(c.principal, set()).update(x.value for x in c.add)


class FakeSpark:
    """CREATE OR REPLACE drops every grant on the function, as Unity Catalog does."""

    def __init__(self, ws):
        self.ws, self.sql_run = ws, []

    def sql(self, text):
        self.sql_run.append(text)
        self.ws.grants.grants = {}


def test_the_grants_read_before_the_replace_are_put_back_exactly():
    ws = SimpleNamespace(grants=FakeGrants({APP: {"EXECUTE"}}))
    after = C.replace_function(FakeSpark(ws), ws, FN, "CREATE OR REPLACE FUNCTION ...")
    assert after == {APP: ["EXECUTE"]} and ws.grants.grants == {APP: {"EXECUTE"}}
    (changes,) = ws.grants.updates
    assert [(c.principal, [p.value for p in c.add]) for c in changes] == [(APP, ["EXECUTE"])]


def test_every_page_and_principal_is_kept():
    ws = SimpleNamespace(grants=FakeGrants({APP: {"EXECUTE"}, "analysts": {"EXECUTE", "MANAGE"}}, page=1))
    assert C.function_grants(ws, FN) == {APP: ["EXECUTE"], "analysts": ["EXECUTE", "MANAGE"]}
    C.replace_function(FakeSpark(ws), ws, FN, "CREATE OR REPLACE FUNCTION ...")
    assert ws.grants.grants == {APP: {"EXECUTE"}, "analysts": {"EXECUTE", "MANAGE"}}


def test_a_new_function_has_nothing_to_put_back():
    ws = SimpleNamespace(grants=FakeGrants({}))
    ws.grants.grants = None  # not created yet
    assert C.function_grants(ws, FN) == {}
    spark = FakeSpark(ws)
    assert C.replace_function(spark, ws, FN, "CREATE OR REPLACE FUNCTION ...") == {}
    assert ws.grants.updates == [] and len(spark.sql_run) == 1


def test_grants_that_do_not_read_back_the_same_stop_the_run():
    ws = SimpleNamespace(grants=FakeGrants({APP: {"EXECUTE"}}))
    ws.grants.update = lambda *a, **k: None  # the update is lost
    with pytest.raises(SystemExit, match="grants read back"):
        C.replace_function(FakeSpark(ws), ws, FN, "CREATE OR REPLACE FUNCTION ...")
