r"""The final check's lock (coolcheck.final_lock) against a local MLflow file store.

mlflow is not in the shared .venv: mlflow-skinny 2.22.0, the version the back-test job ran on serverless environment 4,
needs protobuf < 7, and .venv keeps protobuf 7.36.2 for Databricks Connect. So these tests skip in .venv and run in a
throwaway venv holding only mlflow-skinny and pytest (PowerShell, from the repo root):

    .venv\Scripts\python -m venv $env:TEMP\coolcheck-mlflow-venv
    & $env:TEMP\coolcheck-mlflow-venv\Scripts\python -m pip install mlflow-skinny==2.22.0 pytest==9.1.1
    $env:PYTHONDONTWRITEBYTECODE = "1"
    & $env:TEMP\coolcheck-mlflow-venv\Scripts\python -m pytest tests/backtest/test_final_check_mlflow.py -p no:cacheprovider -v
    Remove-Item -Recurse -Force $env:TEMP\coolcheck-mlflow-venv

They import only mlflow, pytest and coolcheck.final_lock (standard library at import). The real, read-only test of the
lock query against the workspace is the job's stage lock.
"""
import hashlib
import re
from pathlib import Path

import pytest

mlflow = pytest.importorskip("mlflow")

from mlflow import MlflowClient  # noqa: E402

from coolcheck.final_lock import (COMPLETE_TAG, OVERRIDE_TAG, ROLE, SCORED_TAG, AlreadyScored, MlflowLock,  # noqa: E402
                                  refuse_if_scored, write_final_run)

NAME = "/Workspace/Users/someone@example.com/[dev someone] coolcheck-backtest"
SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture
def store(tmp_path):
    """A local store with the back-test experiment and one FINISHED role = model run (the probe)."""
    client = MlflowClient(tracking_uri=(tmp_path / "mlruns").as_uri())
    exp = client.create_experiment(NAME)
    model = client.create_run(exp, tags={"role": "model"}, run_name="model").info.run_id
    client.set_terminated(model, "FINISHED")
    return client, exp, model, tmp_path


def write(client, exp, tmp_path, name="out", tags=None, build=None, override=None):
    out = tmp_path / name
    out.mkdir()
    (out / "predictions.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    def default_build(rid):
        return (f"# Final check report\n\nMLflow run `{rid}`. Model above persistence: yes. ≥ °C\n",
                {"git_sha": SHA, **{f"p{i}": i for i in range(250)}}, {f"m/{i}": i / 3 for i in range(1500)}, out)

    return write_final_run(client, exp, {"git_sha": SHA} if tags is None else tags, build or default_build,
                           override=override)


def crashing_build(rid):
    raise RuntimeError("crash in build")


class Crashing:
    """The client, except that one of its calls raises."""

    def __init__(self, client, at):
        self._client, self._at = client, at

    def __getattr__(self, name):
        if name == self._at:
            def crash(*args, **kwargs):
                raise RuntimeError(f"crash in {name}")
            return crash
        return getattr(self._client, name)


def test_only_a_scored_final_check_run_locks(store):
    client, exp, model, tmp = store
    lock = MlflowLock(client, exp)
    for status, tags in (("FAILED", {}), (None, {}), ("FINISHED", {COMPLETE_TAG: "true"})):  # final_check, not scored
        rid = client.create_run(exp, tags={"role": ROLE, **tags}).info.run_id
        if status:
            client.set_terminated(rid, status)
    other = client.create_run(exp, tags={"role": "baseline", SCORED_TAG: "true", COMPLETE_TAG: "true"}).info.run_id
    client.set_terminated(other, "FINISHED")
    assert lock.locks() == []
    lines = lock.check(probe_run=model)
    assert f"{ROLE} runs: 3" in lines and any(f"including {model} (FINISHED)" in s for s in lines)
    rid, _, _ = write(client, exp, tmp)
    assert lock.locks() == [(rid, "FINISHED", True)]
    with pytest.raises(AlreadyScored, match=re.escape(f"{rid} (FINISHED, complete). It is scored once")):
        refuse_if_scored(lock.locks)
    with pytest.raises(AlreadyScored, match=rid):
        lock.check(probe_run=model)


def test_a_deleted_scored_run_still_locks(store):
    client, exp, model, tmp = store
    rid, _, _ = write(client, exp, tmp)
    client.delete_run(rid)
    assert MlflowLock(client, exp).locks() == [(rid, "FINISHED", True)]


@pytest.mark.parametrize("at", ["build", "log_batch", "set_tag", "log_artifacts"])
def test_a_crash_after_the_run_is_created_locks_and_only_an_explicit_override_passes_it(store, at):
    client, exp, model, tmp = store
    with pytest.raises(RuntimeError, match=f"crash in {at}"):
        if at == "build":
            write(client, exp, tmp, build=crashing_build)
        else:
            write(Crashing(client, at), exp, tmp)
    lock = MlflowLock(client, exp)
    [(rid, status, complete)] = lock.locks()
    assert (status, complete) == ("FAILED", False)
    with pytest.raises(AlreadyScored, match=re.escape(f"{rid} (FAILED, incomplete: its record is not whole; a rerun "
                                                      f"past it needs --override-incomplete {rid}, on the user's word)")):
        lock.check(probe_run=model)
    # on the user's word: a rerun past it, recorded on the new run
    past = MlflowLock(client, exp, override=rid)
    assert past.locks() == [] and past.check(probe_run=model)[-1].startswith(f"override: a rerun past the incomplete "
                                                                             f"scored run {rid}")
    new, _, _ = write(client, exp, tmp, name="rerun", override=rid)
    assert client.get_run(new).data.tags[OVERRIDE_TAG] == rid
    assert past.locks() == [(new, "FINISHED", True)]  # the override passes only the run it names
    with pytest.raises(AlreadyScored, match=new):
        past.check(probe_run=model)


def test_a_run_left_running_locks_and_a_complete_run_cannot_be_overridden(store):
    client, exp, model, tmp = store
    killed = client.create_run(exp, tags={"role": ROLE, SCORED_TAG: "true"}).info.run_id  # killed after create_run
    with pytest.raises(RuntimeError, match="crash in set_terminated"):  # killed after the complete tag, before FINISHED
        write(Crashing(client, "set_terminated"), exp, tmp)
    locks = {rid: (status, complete) for rid, status, complete in MlflowLock(client, exp).locks()}
    whole = next(rid for rid, (_, complete) in locks.items() if complete)
    assert locks == {killed: ("RUNNING", False), whole: ("RUNNING", True)}
    with pytest.raises(SystemExit, match="is complete .* so it cannot be overridden"):
        MlflowLock(client, exp, override=whole).locks()
    with pytest.raises(SystemExit, match=f"no scored {ROLE} run has that id"):
        MlflowLock(client, exp, override="f" * 32).locks()
    with pytest.raises(AlreadyScored, match=re.escape(f"{whole} (RUNNING, complete)")):  # the other run still locks
        MlflowLock(client, exp, override=killed).check(probe_run=model)


def test_the_run_holds_the_lock_the_report_its_sha256_the_commit_params_and_metrics(store):
    client, exp, model, tmp = store
    rid, report, sha = write(client, exp, tmp)
    run = client.get_run(rid)
    assert run.info.status == "FINISHED" and run.data.tags["role"] == ROLE
    assert run.data.tags[SCORED_TAG] == "true" and run.data.tags[COMPLETE_TAG] == "true"
    assert OVERRIDE_TAG not in run.data.tags
    assert run.data.tags["git_sha"] == SHA and run.data.params["git_sha"] == SHA
    assert len(run.data.params) == 251 and len(run.data.metrics) == 1500  # batched under MLflow's limits
    (tmp / "download").mkdir()
    got = Path(client.download_artifacts(rid, "report.md", str(tmp / "download")))
    assert hashlib.sha256(got.read_bytes()).hexdigest() == sha == run.data.tags["report_sha256"]
    assert got.read_bytes() == report.encode("utf-8") and rid in report
    assert sorted(a.path for a in client.list_artifacts(rid)) == ["predictions.csv", "report.md"]


def test_the_lock_check_refuses_another_experiment_a_blind_query_and_reserved_tags(store):
    client, exp, model, tmp = store
    other = client.create_experiment("/Workspace/Users/someone@example.com/scratch")
    with pytest.raises(SystemExit, match="not the back-test's"):
        MlflowLock(client, other).check(probe_run=model)
    with pytest.raises(SystemExit, match="cannot be trusted"):
        MlflowLock(client, exp).check(probe_run="0" * 32)  # a query that does not see the model run
    for i, tag in enumerate(("role", SCORED_TAG, COMPLETE_TAG, OVERRIDE_TAG)):
        with pytest.raises(ValueError, match="tags may not set"):
            write(client, exp, tmp, name=f"out{i}", tags={tag: "x"})
    assert MlflowLock(client, exp).runs(ROLE) == []
