"""upload_raw.py: the trial defaults, another Volume root, resume, batches with --include, the profile, the detached
launch and the Volume-root check. A fake file store stands in for the workspace."""
from types import SimpleNamespace

import pytest

import upload_raw as U

R = "/Volumes/workspace/bronze/raw_files"


class FakeFiles:
    def __init__(self, fail=()):
        self.store, self.fail = {}, set(fail)

    def list_directory_contents(self, path):
        path, kids = path.rstrip("/"), {}
        for key, size in self.store.items():
            if key.startswith(path + "/"):
                rest = key[len(path) + 1:]
                head = rest.split("/", 1)[0]
                kids[f"{path}/{head}"] = None if "/" in rest else size
        if not kids:
            raise FileNotFoundError(path)
        return [SimpleNamespace(path=p, is_directory=s is None, file_size=s) for p, s in kids.items()]

    def upload(self, dest, f, overwrite=True):
        if dest in self.fail:
            raise RuntimeError("upload refused (fake)")
        self.store[dest] = len(f.read())


class FakeClient:
    def __init__(self, fail=()):
        self.files = FakeFiles(fail)


def tree(tmp_path):
    src = tmp_path / "raw"
    for rel, body in (("wbgt/backfill/wbgt_2025-01-16.jsonl", b"a\nb\n"), ("wbgt/backfill/wbgt_2025-02-01.jsonl", b"c\n"),
                      ("rainfall/backfill/rainfall_2025-01-16.jsonl", b"d\ne\nf\n"), ("_meta/backfill_end.json", b"{}")):
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
    return src


def last_lines(log, n):
    return log.read_text(encoding="utf-8").splitlines()[-n:]


def test_the_defaults_are_the_trial():
    a = U.parse([])
    assert (a.src, a.profile, a.volume_root, a.include) == (
        "../coolcheck-data/raw", "coolcheck", "/Volumes/coolcheck/bronze/raw_files", None)


def test_uploads_to_the_given_volume_root_and_a_rerun_skips_everything(tmp_path):
    src, fake, log = tree(tmp_path), FakeClient(), tmp_path / "u.log"
    assert U.run(src, log, remote=R, client=fake)
    assert set(fake.files.store) == {f"{R}/wbgt/backfill/wbgt_2025-01-16.jsonl", f"{R}/wbgt/backfill/wbgt_2025-02-01.jsonl",
                                     f"{R}/rainfall/backfill/rainfall_2025-01-16.jsonl", f"{R}/_meta/backfill_end.json"}
    assert U.run(src, log, remote=R, client=fake)
    text = log.read_text(encoding="utf-8")
    assert "SKIP 4 already present with the same size; UPLOAD 0" in text
    assert text.count("FINISHED OK") == 2


def test_include_uploads_one_batch_at_a_time_and_each_batch_verifies(tmp_path):
    src, fake, log = tree(tmp_path), FakeClient(), tmp_path / "u.log"
    assert U.run(src, log, remote=R, include="*_2025-01-*", client=fake)
    assert set(fake.files.store) == {f"{R}/wbgt/backfill/wbgt_2025-01-16.jsonl", f"{R}/rainfall/backfill/rainfall_2025-01-16.jsonl"}
    assert U.run(src, log, remote=R, include="*_2025-02-*", client=fake)  # the wbgt folder already holds batch one
    assert f"{R}/wbgt/backfill/wbgt_2025-02-01.jsonl" in fake.files.store
    assert last_lines(log, 1)[0].endswith("FINISHED OK")


def test_a_failed_upload_is_reported_and_the_run_is_not_ok(tmp_path):
    src, log = tree(tmp_path), tmp_path / "u.log"
    fake = FakeClient(fail={f"{R}/rainfall/backfill/rainfall_2025-01-16.jsonl"})
    assert not U.run(src, log, remote=R, client=fake)
    assert "FINISHED WITH PROBLEMS" in last_lines(log, 1)[0]


def test_the_profile_reaches_the_client(tmp_path, monkeypatch):
    seen = []

    def client(profile):
        seen.append(profile)
        return FakeClient()
    monkeypatch.setattr(U, "WorkspaceClient", client)
    U.run(tree(tmp_path), tmp_path / "u.log", profile="freeedition", remote=R)
    assert seen == ["freeedition"]


def test_the_detached_run_gets_every_option():
    a = U.parse(["--log", "x.log", "--profile", "freeedition", "--volume-root", R, "--include", "*_2025-0[1-3]-*",
                 "--launch"])
    assert U.child_argv(a)[2:] == ["--src", "../coolcheck-data/raw", "--log", "x.log", "--profile", "freeedition",
                                   "--volume-root", R, "--include", "*_2025-0[1-3]-*"]


def test_the_detached_run_of_the_defaults_is_unchanged_apart_from_the_explicit_defaults():
    assert U.child_argv(U.parse(["--launch"]))[2:] == [
        "--src", "../coolcheck-data/raw", "--log", "../coolcheck-data/upload_raw.log", "--profile", "coolcheck",
        "--volume-root", "/Volumes/coolcheck/bronze/raw_files"]


@pytest.mark.parametrize("bad", ["/tmp/raw", "/Volumes/workspace/bronze", f"{R}/wbgt", "Volumes/workspace/bronze/raw_files"])
def test_a_volume_root_that_is_not_a_volume_is_refused_before_connecting(bad, capsys):
    assert U.main(["--volume-root", bad]) == 2
    assert "must look like /Volumes/<catalog>/<schema>/<volume>" in capsys.readouterr().err
