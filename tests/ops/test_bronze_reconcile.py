"""bronze_reconcile.py: the report names the given catalog, the trial's wording is unchanged, a differing file is listed,
and main reads <catalog>.silver.dq_reconcile with the given profile."""
import hashlib
import json
from types import SimpleNamespace

import bronze_reconcile as BR
from ops_fakes import FakeSession

NAME = "wbgt_2025-01-16.jsonl"
BODY = b"p1\np2\np3\np4\n"


def row(lines=4, size=len(BODY)):
    return SimpleNamespace(stage="bronze", checked_at="2026-10-23 20:00:00", feed="wbgt", file_name=NAME,
                           source_file=f"/Volumes/x/bronze/raw_files/wbgt/backfill/{NAME}", vol_size=size,
                           vol_lines=lines, bronze_rows=lines, bronze_distinct_lines=lines)


def sample(remote_lines=4):
    sha = hashlib.sha256(BODY).hexdigest()
    loc = {("wbgt", NAME): {"lines": 4, "bytes": len(BODY), "sha256": sha, "jsonl": True}}
    prog = {("wbgt", NAME): {"status": "done", "pages": 4, "bytes": len(BODY), "sha256": sha, "date": "2025-01-16"}}
    return loc, prog, [row(remote_lines)]


def test_the_report_names_the_given_catalog():
    text = "\n".join(BR.report(*sample(), "workspace"))
    assert "`workspace.silver.dq_reconcile`" in text
    assert "`/Volumes/workspace/bronze/raw_files`, and the Bronze tables `workspace.bronze.<feed>_raw`." in text
    assert "coolcheck.silver" not in text and "/Volumes/coolcheck" not in text
    assert "**No file differs:**" in text


def test_the_trial_wording_is_unchanged():
    text = "\n".join(BR.report(*sample(), "coolcheck"))
    assert "Volume and Bronze figures come from `coolcheck.silver.dq_reconcile` (reconcile job, stage bronze" in text
    assert "the Volume `/Volumes/coolcheck/bronze/raw_files`, and the Bronze tables `coolcheck.bronze.<feed>_raw`." in text


def test_a_differing_file_is_listed():
    text = "\n".join(BR.report(*sample(remote_lines=3), "workspace"))
    assert "## Files that differ" in text
    assert f"| wbgt | {NAME} | lines local=4, progress=4, volume=3, bronze=3 |" in text


def test_main_reads_the_catalog_with_the_profile(tmp_path, fake_connect):
    data = tmp_path / "data"
    (data / "raw" / "wbgt" / "backfill").mkdir(parents=True)
    (data / "raw" / "wbgt" / "backfill" / NAME).write_bytes(BODY)
    (data / "backfill").mkdir()
    (data / "backfill" / "progress.jsonl").write_text(json.dumps(
        {"event": "day", "feed": "wbgt", "date": "2025-01-16", "status": "done", "pages": 4, "bytes": len(BODY),
         "sha256": hashlib.sha256(BODY).hexdigest()}) + "\n", encoding="utf-8")
    session = FakeSession(tables={"workspace.silver.dq_reconcile": [row()]})
    builder = fake_connect(session)
    out = tmp_path / "bronze_reconcile_free.md"
    BR.main(["--data", str(data), "--out", str(out), "--catalog", "workspace", "--profile", "freeedition"])
    assert builder.profile_used == "freeedition"
    assert session.tables_read == ["workspace.silver.dq_reconcile"]
    assert "**No file differs:**" in out.read_text(encoding="utf-8")


def test_the_defaults_are_the_trial(tmp_path, fake_connect):
    data = tmp_path / "data"
    (data / "raw").mkdir(parents=True)
    (data / "backfill").mkdir()
    (data / "backfill" / "progress.jsonl").write_text("", encoding="utf-8")
    session = FakeSession(tables={"coolcheck.silver.dq_reconcile": [row()]})
    builder = fake_connect(session)
    BR.main(["--data", str(data), "--out", str(tmp_path / "out.md")])
    assert builder.profile_used == "coolcheck"
    assert session.tables_read == ["coolcheck.silver.dq_reconcile"]
