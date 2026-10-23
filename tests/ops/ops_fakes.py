"""Fakes for the operations-script tests: a Databricks Connect session and DataFrame that record what they are
asked to do."""
from collections import defaultdict
from types import SimpleNamespace


class FirstRow:
    n = 0

    def asDict(self):
        return defaultdict(int)


class FakeDF:
    def __init__(self, rows=(), columns=()):
        self._rows, self.columns = list(rows), list(columns)

    def collect(self):
        return self._rows

    def limit(self, n):
        return self

    def show(self, *args, **kwargs):
        pass

    def first(self):
        return FirstRow()


class FakeSession:
    """Records SQL and table reads. catalogs: what SHOW CATALOGS returns; tables: name -> rows; fail_on: a SQL prefix
    that raises."""

    def __init__(self, catalogs=(), tables=None, fail_on=None):
        self.catalogs, self.tables, self.fail_on = catalogs, tables or {}, fail_on
        self.sqls, self.tables_read = [], []
        self.conf = SimpleNamespace(set=lambda key, value: None)

    def sql(self, s):
        if self.fail_on and s.startswith(self.fail_on):
            raise RuntimeError("PERMISSION_DENIED (fake)")
        self.sqls.append(s)
        if s == "SHOW CATALOGS":
            return FakeDF([(c,) for c in self.catalogs])
        return FakeDF()

    def table(self, name):
        self.tables_read.append(name)
        return FakeDF(self.tables.get(name, []))


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
