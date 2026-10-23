"""The final check's lock (docs/design/backtest.md §15 item 4 (c)): the final check is scored once.

The lock is set the moment scoring completes: write_final_run is called only then, and its first act creates the run
tagged role = final_check and final_check_scored = true. From then on any final_check run with that tag refuses a new
run, whatever its status (a crash, a kill or a run left RUNNING included), deleted runs included (the search includes
them). final_check_complete = true, written last, marks the record (report, metrics, artifacts) as whole. The refusal
names a scored run that is not complete; a rerun past it needs --override-incomplete <run_id>, which works only for a
run without final_check_complete, is recorded as a tag on the new run, and is used only on the user's word.

Standard library only at import (mlflow is imported where it is used), so its tests can run in a venv of their own
(tests/backtest/test_final_check_mlflow.py).
"""
import hashlib
import time
from pathlib import Path

ROLE = "final_check"
SCORED_TAG = "final_check_scored"                 # set when the run is created, once scoring has completed: the lock
COMPLETE_TAG = "final_check_complete"             # set last: the record is whole
OVERRIDE_TAG = "final_check_override_incomplete"  # the incomplete scored run a rerun was allowed past
RESERVED_TAGS = ("role", SCORED_TAG, COMPLETE_TAG, OVERRIDE_TAG)
EXPERIMENT_SUFFIX = "coolcheck-backtest"
BACKTEST_MODEL_RUN = "c509ab9ad0d8464f8a1df07354b1bf98"  # the full back-test's model run (§14); the lock query must see it


class AlreadyScored(RuntimeError):
    """The experiment already holds a scored final_check run."""


def is_scored(tags):
    return tags.get(SCORED_TAG) == "true"


def is_complete(tags):
    return tags.get(COMPLETE_TAG) == "true"


def refuse_if_scored(find_locks):
    """Stop if find_locks() lists any scored final_check run, as (run_id, status, complete); an incomplete one is named
    with what a rerun past it needs."""
    locks = list(find_locks())
    if locks:
        named = [f"{rid} ({status}, complete)" if complete else
                 f"{rid} ({status}, incomplete: its record is not whole; a rerun past it needs --override-incomplete "
                 f"{rid}, on the user's word)" for rid, status, complete in locks]
        raise AlreadyScored(f"the final check has been scored: {ROLE} run(s) {'; '.join(named)}. It is scored once "
                            "(docs/design/backtest.md §15 item 4 (c))")


class MlflowLock:
    """The lock query on the back-test experiment, through an MlflowClient (read-only). override: the run id given with
    --override-incomplete, or None."""

    def __init__(self, client, experiment_id, override=None):
        self.client, self.experiment_id, self.override = client, str(experiment_id), override or None

    def runs(self, role):
        from mlflow.entities import ViewType

        return self.client.search_runs([self.experiment_id], filter_string=f"tags.role = '{role}'",
                                       run_view_type=ViewType.ALL, max_results=1000)

    def _locks(self, runs):
        scored = [(r.info.run_id, r.info.status, is_complete(r.data.tags)) for r in runs if is_scored(r.data.tags)]
        if self.override:
            named = [s for s in scored if s[0] == self.override]
            if not named:
                raise SystemExit(f"--override-incomplete {self.override}: no scored {ROLE} run has that id; stop")
            if named[0][2]:
                raise SystemExit(f"--override-incomplete {self.override}: that run is complete ({COMPLETE_TAG} = true), "
                                 "so it cannot be overridden; stop")
        return [s for s in scored if s[0] != self.override]

    def locks(self):
        """The scored final_check runs that refuse a new run, whatever their status, deleted runs included: all of them
        less the incomplete run the override names."""
        return self._locks(self.runs(ROLE))

    def check(self, probe_run=BACKTEST_MODEL_RUN):
        """Before anything is read: the experiment is the back-test's; the query sees the back-test's model run as
        FINISHED (so a query that sees nothing cannot pass for "no lock"); no scored final_check run locks. Returns
        lines describing what it found."""
        name = self.client.get_experiment(self.experiment_id).name
        if not name.rstrip("/").endswith(EXPERIMENT_SUFFIX):
            raise SystemExit(f"experiment {self.experiment_id} is {name!r}, not the back-test's ({EXPERIMENT_SUFFIX})")
        probe = {r.info.run_id: r.info.status for r in self.runs("model")}
        if probe.get(probe_run) != "FINISHED":
            raise SystemExit(f"the lock query does not see the back-test's model run {probe_run} as FINISHED (it found "
                             f"{len(probe)} role = model run(s)): the lock cannot be trusted; stop")
        runs = self.runs(ROLE)
        lines = [f"experiment {self.experiment_id}: {name}",
                 f"probe: {len(probe)} role = model run(s), including {probe_run} (FINISHED)",
                 f"{ROLE} runs: {len(runs)}"]
        lines += [f"  {r.info.run_id}: status {r.info.status}, {SCORED_TAG} = {r.data.tags.get(SCORED_TAG, 'absent')}, "
                  f"{COMPLETE_TAG} = {r.data.tags.get(COMPLETE_TAG, 'absent')}, lifecycle {r.info.lifecycle_stage}"
                  for r in runs]
        if self.override:
            lines.append(f"override: a rerun past the incomplete scored run {self.override}, on the user's word")
        refuse_if_scored(lambda: self._locks(runs))
        return lines


def write_final_run(client, experiment_id, tags, build, override=None):
    """The lock, then the record. Called only once scoring has completed; its first act creates the run tagged role =
    final_check and final_check_scored = true, so from that moment the final check is locked, whatever happens next.
    build(run_id) then gives (report, params, metrics, out_dir): the report is saved as report.md in out_dir as UTF-8
    bytes (so a copy can be compared by sha256); params, metrics and every file in out_dir are logged;
    final_check_complete = true is the last write (the record is whole), then the run ends FINISHED. A failure on the
    way ends it FAILED: it still locks, and the refusal names it as incomplete. override: the incomplete scored run this
    rerun was allowed past, recorded as a tag. Returns (run_id, report, report sha256)."""
    from mlflow.entities import Metric, Param

    reserved = sorted(set(RESERVED_TAGS) & set(tags))
    if reserved:
        raise ValueError(f"tags may not set {reserved}")
    lock_tags = {"role": ROLE, SCORED_TAG: "true", **({OVERRIDE_TAG: override} if override else {})}
    rid = client.create_run(str(experiment_id), tags={**tags, **lock_tags}, run_name=ROLE).info.run_id
    try:
        report, params, metrics, out_dir = build(rid)
        data = report.encode("utf-8")
        (Path(out_dir) / "report.md").write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        ps = [Param(k, str(v)) for k, v in params.items()]
        for i in range(0, len(ps), 100):
            client.log_batch(rid, params=ps[i:i + 100])
        now = int(time.time() * 1000)
        ms = [Metric(k, float(v), now, 0) for k, v in metrics.items()]
        for i in range(0, len(ms), 1000):
            client.log_batch(rid, metrics=ms[i:i + 1000])
        client.set_tag(rid, "report_sha256", sha)
        client.log_artifacts(rid, str(out_dir))
        client.set_tag(rid, COMPLETE_TAG, "true")
        client.set_terminated(rid, "FINISHED")
    except BaseException:
        client.set_terminated(rid, "FAILED")
        raise
    return rid, report, sha
