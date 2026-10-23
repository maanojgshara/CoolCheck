"""silver_check.py: every query reads the given catalog, and main passes the profile; the defaults are the trial."""
import silver_check as SCK
from ops_fakes import FakeDF, FakeSession


def test_every_query_reads_the_given_catalog():
    seen = []

    def q(sql):
        seen.append(sql)
        return FakeDF()
    lines = SCK.report(q, "workspace", "abc123")
    assert len(seen) == len(SCK.TABLES) + 3 + 6  # row counts, the three key checks, six report queries
    assert all("workspace." in s for s in seen)
    assert not any("coolcheck." in s for s in seen)
    assert "; pipeline update `abc123`; catalog `workspace`. Tables read only." in lines[2]


def test_the_defaults_are_the_trial(tmp_path, fake_connect):
    session = FakeSession()
    builder = fake_connect(session)
    SCK.main(["--out", str(tmp_path / "s.md")])
    assert builder.profile_used == "coolcheck"
    assert session.sqls and all("coolcheck." in s for s in session.sqls)


def test_free_edition_profile_and_catalog(tmp_path, fake_connect):
    session = FakeSession()
    builder = fake_connect(session)
    out = tmp_path / "silver_check_free.md"
    SCK.main(["--catalog", "workspace", "--profile", "freeedition", "--out", str(out)])
    assert builder.profile_used == "freeedition"
    assert all("workspace." in s for s in session.sqls)
    assert "catalog `workspace`" in out.read_text(encoding="utf-8")
