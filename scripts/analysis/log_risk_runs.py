r"""Log the electricity run and the risk-score check run to the trial workspace's MLflow tracking server
(docs/design/risk_score.md §10).

mlflow is not in the shared .venv (mlflow-skinny 2.22.0 needs protobuf below 7, and .venv pins 7.36.2 for Databricks
Connect), so this script imports only mlflow, databricks-sdk and the standard library, and runs from a throwaway venv
that is removed afterwards (PowerShell, from the repo root):

    .venv\Scripts\python -m venv $env:TEMP\coolcheck-risk-mlflow-venv
    & $env:TEMP\coolcheck-risk-mlflow-venv\Scripts\python -m pip install mlflow-skinny==2.22.0
    & $env:TEMP\coolcheck-risk-mlflow-venv\Scripts\python scripts/analysis/log_risk_runs.py --profile coolcheck
    Remove-Item -Recurse -Force $env:TEMP\coolcheck-risk-mlflow-venv

Tracking URI databricks://<profile>; experiment /Users/<workspace user>/coolcheck-risk-score, created if missing. If the
venv cannot authenticate, it stops: there is no local fallback. Inputs: <data>/analysis/ema_electricity_run.json and
<data>/analysis/risk_score_check/run.json, written by scripts/static/ema_electricity.py and
scripts/analysis/risk_score_check.py. Each run logs its parameters, metrics and artifacts, the git SHA, whether the code
files are committed, and the sha256 of every code file it names. The experiment ID and the run IDs are written into the
two reports (between the <!-- mlflow --> markers) before each report is logged as an artifact, and saved to
<data>/analysis/risk_mlflow_runs.json (no user name is written anywhere in the repo).

--tag-commit <sha> instead tags both runs in that file with git_commit = <sha>, after checking that every code file in
the commit has the sha256 the run logged (as stored, or with CRLF line endings, since git stores LF and a Windows working
copy can hold CRLF); it stops if one differs.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SGT = timezone(timedelta(hours=8))
MARK = ("<!-- mlflow -->", "<!-- /mlflow -->")
EXPERIMENT = "coolcheck-risk-score"
RUN_FILES = ("ema_electricity_run.json", "risk_score_check/run.json")


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def key(s):
    """An MLflow-safe parameter or metric key."""
    return re.sub(r"[^A-Za-z0-9_\-. /]", "_", s)


def set_marker(path, text):
    p = Path(path)
    s = p.read_text(encoding="utf-8")
    a, b = s.index(MARK[0]) + len(MARK[0]), s.index(MARK[1])
    p.write_text(s[:a] + "\n" + text + "\n" + s[b:], encoding="utf-8")


def tag_commit(mlflow, data, sha):
    saved = json.loads((data / "analysis/risk_mlflow_runs.json").read_text(encoding="utf-8"))
    client = mlflow.MlflowClient()
    for role, run in saved["runs"].items():
        for path, logged in run["code_sha256"].items():
            blob = subprocess.run(["git", "show", f"{sha}:{path}"], cwd=REPO, capture_output=True, check=True).stdout
            # git stores LF (.gitattributes eol=lf); a file logged from a Windows working copy may have had CRLF
            if logged not in (sha256_bytes(blob), sha256_bytes(blob.replace(b"\n", b"\r\n"))):
                raise SystemExit(f"STOP: {path} in {sha[:7]} differs from what run {role} logged; no tag set")
        client.set_tag(run["run_id"], "git_commit", sha)
        print(f"run {role} ({run['run_id']}): tagged git_commit = {sha}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO.parent / "coolcheck-data"))
    ap.add_argument("--profile", default="coolcheck")
    ap.add_argument("--tag-commit", metavar="SHA", help="tag the logged runs with this commit after checking the code hashes")
    a = ap.parse_args()
    data = Path(a.data)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # mlflow prints an emoji link when a run ends

    import mlflow
    from databricks.sdk import WorkspaceClient

    try:
        user = WorkspaceClient(profile=a.profile).current_user.me().user_name
    except Exception as e:  # authentication or network: stop, never fall back to a local store
        raise SystemExit(f"STOP: cannot authenticate to the workspace with profile {a.profile!r} ({type(e).__name__}); "
                         "nothing logged")
    mlflow.set_tracking_uri(f"databricks://{a.profile}")
    if a.tag_commit:
        tag_commit(mlflow, data, a.tag_commit)
        return
    name = f"/Users/{user}/{EXPERIMENT}"
    exp = mlflow.get_experiment_by_name(name)
    exp_id = exp.experiment_id if exp else mlflow.create_experiment(name)
    head = git("rev-parse", "HEAD").strip()
    when = datetime.now(SGT).strftime("%Y-%m-%d %H:%M SGT")
    specs = [json.loads((data / "analysis" / f).read_text(encoding="utf-8")) for f in RUN_FILES]
    saved = {"experiment_id": exp_id, "experiment": EXPERIMENT, "logged": when, "git_head": head, "runs": {}}
    for spec in specs:
        files = spec["code_files"]
        hashes = {f: sha256_bytes((REPO / f).read_bytes()) for f in files}
        dirty = bool(git("status", "--porcelain", "--", *files).strip())
        tags = {"role": spec["role"], "git_sha": head, "git_dirty_code": str(dirty).lower()}
        with mlflow.start_run(experiment_id=exp_id, run_name=spec["run_name"], tags=tags) as run:
            params = {key(k): str(v)[:500] for k, v in spec["params"].items()}
            params.update({key(f"code_sha256_{Path(f).name}"): h for f, h in hashes.items()})
            params.update({"git_sha": head, "git_dirty_code": str(dirty).lower()})
            mlflow.log_params(params)
            mlflow.log_metrics({key(k): float(v) for k, v in spec["metrics"].items() if v is not None})
            saved["runs"][spec["role"]] = {"run_id": run.info.run_id, "code_sha256": hashes, "git_dirty_code": dirty}
            ids = "; ".join(f"`{r}` run `{v['run_id']}`" for r, v in saved["runs"].items())
            state = ("with these code files not yet committed (their sha256 are logged; a git_commit tag is added once "
                     "the commit's files match)" if dirty else "with the code files as committed")
            set_marker(spec["report"], f"MLflow: experiment `{EXPERIMENT}` in the trial workspace (your user folder), "
                                       f"ID `{exp_id}`; {ids}; logged {when} from git `{head[:7]}` {state}.")
            for art in spec["artifacts"]:
                mlflow.log_artifact(art)
        print(f"logged {spec['run_name']}: run {run.info.run_id}, {len(params)} parameters, "
              f"{len(spec['metrics'])} metrics, {len(spec['artifacts'])} artifacts")
    (data / "analysis/risk_mlflow_runs.json").write_text(json.dumps(saved, indent=1), encoding="utf-8")
    print(f"experiment {EXPERIMENT}: ID {exp_id}; runs saved to {data / 'analysis/risk_mlflow_runs.json'}")


if __name__ == "__main__":
    sys.exit(main())
