"""Run the agent evaluation (docs/design/agent_eval.md): the 20 scenarios of tests/agent_eval/scenarios.json through
coolcheck.agent.draft_plan (window B, 941dcbe), graded by coolcheck.agent_eval. Only on the user's word: it calls the
model and the SQL warehouse.

- Refuses unless the scenario file and the grader are committed and unchanged since HEAD, so the criteria can't move
  after the results are seen, and unless the agent code (coolcheck/agent.py and plan.py) is too, so the commit it ran
  against is the one recorded. Both commits, HEAD and the files' sha256 go into the results.
- draft_plan gets what the App gives it: the form (the date always from here), the catalog, workspace_client,
  warehouse_id and the date's forecast row (coolcheck.plan.forecast_info).
- Pass 1 runs every scenario once: the headline. Each scenario that fails it runs twice more and is reported x/3.
- Traces go to a separate experiment, /Users/<the user running it>/coolcheck-agent-eval (resolved at run time; no name
  is in the repository), and every trace is tagged eval=true, scenario and attempt, in case draft_plan writes to the
  demo's experiment. One MLflow run in the eval experiment holds the parameters, the metrics and the graded results.
- The LLM judge (--judge-model, a Unity Gateway model service from another family than the agent's Llama) grades only
  the scenarios' judge checks; without it, or without a readable verdict, they stay pending.
- Results: <out-dir>/<UTC stamp>.json (no user names, no URLs).

The shared .venv has no mlflow, so run it from a throwaway venv (PowerShell, from the repo root):
    .venv\\Scripts\\python -m venv $env:TEMP\\coolcheck-eval-venv
    & $env:TEMP\\coolcheck-eval-venv\\Scripts\\python -m pip install mlflow-skinny==3.16.1 databricks-sdk==0.154.0
    & $env:TEMP\\coolcheck-eval-venv\\Scripts\\python scripts/eval/run_agent_eval.py --warehouse-id <id> --judge-model system.ai.gpt-oss-120b
    & $env:TEMP\\coolcheck-eval-venv\\Scripts\\python scripts/eval/run_agent_eval.py --dry-run   # no workspace
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from coolcheck import agent_eval as E  # noqa: E402

SCENARIOS = "tests/agent_eval/scenarios.json"
GRADER = "src/coolcheck/agent_eval.py"
LOCKED = (SCENARIOS, GRADER)
AGENT_CODE = ("src/coolcheck/agent.py", "src/coolcheck/plan.py")


def _git(*args, root=ROOT):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def lock(paths, root=ROOT):
    """The last commit of the paths and their sha256; refuses if any is untracked or changed since HEAD (the criteria
    can't move after the results are seen, and the recorded agent commit is what ran)."""
    for p in paths:
        if _git("ls-files", "--error-unmatch", p, root=root).returncode:
            raise SystemExit(f"{p} is not committed: commit it before a live run")
        if _git("diff", "--quiet", "HEAD", "--", p, root=root).returncode:
            raise SystemExit(f"{p} has changed since HEAD: commit it before a live run")
    return {"commit": _git("log", "-1", "--format=%H", "--", *paths, root=root).stdout.strip(),
            "sha256": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths}}


def draft_kwargs(form, **workspace):
    """draft_plan's keyword arguments: the App's form (the date always from here) and what the App passes besides
    (catalog, workspace_client, warehouse_id, forecast)."""
    return {"target_date": dt.date.fromisoformat(form["target_date"]), "default_capacity": form["default_capacity"],
            "calls_per_volunteer": form["calls_per_volunteer"], "region": form["region"], **workspace}


def read_trace(client, trace_id, tries=10, wait_s=3.0):
    """{"found", "tool_spans", "experiment_id"} for a trace, read back from MLflow; retried, as the export can lag."""
    if not trace_id:
        return None
    error = None
    for _ in range(tries):
        try:
            t = client.get_trace(trace_id)
        except Exception as e:  # noqa: BLE001 - not exported yet, or a real failure: recorded if it lasts
            t, error = None, f"{type(e).__name__}: {e}"
        if t is not None:
            spans = getattr(t.data, "spans", []) or []
            info = t.info
            exp = getattr(info, "experiment_id", None)
            if exp is None and getattr(info, "trace_location", None) is not None:
                exp = getattr(getattr(info.trace_location, "mlflow_experiment", None), "experiment_id", None)
            return {"found": True, "tool_spans": sum(str(getattr(s, "span_type", "")) == "TOOL" for s in spans),
                    "experiment_id": exp}
        time.sleep(wait_s)
    return {"found": False, "error": error}


def reply_text(r):
    """The text of a chat-completions reply; a reasoning model's content may come as parts (the reasoning is dropped)."""
    content = ((r.get("choices") or [{}])[0].get("message") or {}).get("content")
    if isinstance(content, list):
        return "".join(p.get("text") or "" for p in content if isinstance(p, dict) and p.get("type") == "text")
    return content or ""


def make_judge(ws, model):
    """The LLM judge on the Unity Gateway chat-completions path, called as coolcheck.agent.Gateway calls the agent's
    model. A failed call is no verdict: the check stays pending."""
    from coolcheck.agent import GATEWAY_PATH

    def judge(question, context):
        try:
            r = ws.api_client.do("POST", GATEWAY_PATH, body={
                "model": model, "temperature": 0, "max_tokens": 2000,
                "messages": [{"role": "user", "content": E.judge_prompt(question, context)}]})
        except Exception as e:  # noqa: BLE001 - recorded with the check
            return {"pass": None, "why": f"judge call failed: {type(e).__name__}: {e}"}
        return E.parse_verdict(reply_text(r))
    return judge


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="coolcheck")
    ap.add_argument("--catalog", default="coolcheck")
    ap.add_argument("--warehouse-id", default=os.environ.get("DATABRICKS_WAREHOUSE_ID"))
    ap.add_argument("--only", help="comma-separated scenario ids")
    ap.add_argument("--experiment-name", default="coolcheck-agent-eval")
    ap.add_argument("--judge-model", help="Unity Gateway model service for the judge checks, from another family than "
                                          "the agent's; none: they stay pending")
    ap.add_argument("--reruns", type=int, default=2)
    ap.add_argument("--out-dir", default="docs/checks/agent_eval")
    ap.add_argument("--dry-run", action="store_true", help="validate and list the runs; no workspace, no lock")
    a = ap.parse_args()

    data = E.load_scenarios(ROOT / SCENARIOS)
    problems = E.validate(data)
    if problems:
        raise SystemExit("scenario file: " + "; ".join(problems))
    chosen = [s for s in data["scenarios"] if not a.only or s["id"] in a.only.split(",")]
    if a.dry_run:
        for s in chosen:
            print(f"{s['id']} [{s['group']}; expects {s['expected_source']}] form {E.form_of(data, s)}: {s['title']}")
        print(f"{len(chosen)} scenarios; nothing run")
        return
    criteria, agent_code = lock(LOCKED), lock(AGENT_CODE)
    head = _git("rev-parse", "HEAD").stdout.strip()
    if not a.warehouse_id:
        raise SystemExit("--warehouse-id (or DATABRICKS_WAREHOUSE_ID) is needed for the tools")
    if a.judge_model and "llama" in a.judge_model.lower():
        raise SystemExit("the judge must come from another model family than the agent's Llama")

    import mlflow
    from databricks.sdk import WorkspaceClient
    from mlflow import MlflowClient

    from coolcheck import agent as A
    from coolcheck import plan as P

    os.environ["DATABRICKS_CONFIG_PROFILE"] = a.profile
    os.environ.pop("MLFLOW_EXPERIMENT_ID", None)  # the App's experiment must not catch the eval traces
    ws = WorkspaceClient(profile=a.profile)
    mlflow.set_tracking_uri("databricks")
    exp = mlflow.set_experiment(f"/Users/{ws.current_user.me().user_name}/{a.experiment_name}")
    client = MlflowClient()
    flush = getattr(mlflow, "flush_trace_async_logging", None)
    judge = make_judge(ws, a.judge_model) if a.judge_model else None
    wh = P.Warehouse(ws, a.warehouse_id)
    forecasts = {d: P.forecast_info(wh, dt.date.fromisoformat(d), a.catalog)  # as the App reads it
                 for d in sorted({E.form_of(data, s)["target_date"] for s in chosen})}
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def attempt(s, n):
        form = E.form_of(data, s)
        kw = draft_kwargs(form, catalog=a.catalog, workspace_client=ws, warehouse_id=a.warehouse_id,
                          forecast=forecasts[form["target_date"]])
        t0 = time.monotonic()
        try:
            res = E.normalise(A.draft_plan(s["request"], **kw))
        except Exception as e:  # noqa: BLE001 - graded as a failure, with the error
            res = E.normalise(None, f"{type(e).__name__}: {e}")
        if res.elapsed_s is None:
            res.elapsed_s = round(time.monotonic() - t0, 1)
        if flush:
            flush()
        trace = read_trace(client, res.trace_id)
        if trace and trace.get("found"):
            for k, v in {"eval": "true", "eval_scenario": s["id"], "eval_attempt": str(n), "eval_pass": stamp}.items():
                try:
                    client.set_trace_tag(res.trace_id, k, v)
                except Exception as e:  # noqa: BLE001 - recorded, not graded
                    trace.setdefault("tag_errors", []).append(f"{k}: {type(e).__name__}: {e}")
        try:
            g = E.grade(s, form, res, judge, trace, exp.experiment_id, check_traces=True)
        except Exception as e:  # noqa: BLE001 - a grader bug: recorded, the scenario incomplete (never passed)
            g = {"id": s["id"], "group": s["group"], "passed": None, "expected_source": s["expected_source"],
                 "source": res.source, "fallback_reason": res.fallback_reason, "trace_id": res.trace_id,
                 "model": res.model, "rounds": res.rounds, "elapsed_s": res.elapsed_s,
                 "tools": [c.name for c in res.tool_calls], "summary_text": res.summary_text, "checks": [],
                 "grader_error": f"{type(e).__name__}: {e}"}
        g.update(attempt=n, trace=trace)
        print(f"{s['id']} attempt {n}: {g['passed']} ({g['source']}, {res.elapsed_s} s, trace {res.trace_id}) "
              + "; ".join(f"{c['name']}: {c['detail']}" for c in g["checks"] if c["passed"] is False), flush=True)
        return g

    first = [attempt(s, 1) for s in chosen]
    reruns = {g["id"]: [attempt(next(s for s in chosen if s["id"] == g["id"]), n) for n in range(2, 2 + a.reruns)]
              for g in first if g["passed"] is False}
    summary = E.summarise(first, reruns)
    out = {"stamp": stamp, "head": head, "agent_code": agent_code, "criteria": criteria, "agent_model": A.MODEL,
           "judge_model": a.judge_model, "experiment_id": exp.experiment_id,
           "forecasts": {d: {k: f.get(k) for k in ("run_id", "scored_at_sgt", "forecast_missing")}
                         for d, f in forecasts.items()},
           "summary": summary, "first_pass": first, "reruns": reruns}
    path = ROOT / a.out_dir / f"{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, default=str, ensure_ascii=False, indent=1), encoding="utf-8")  # before MLflow
    try:
        with mlflow.start_run(experiment_id=exp.experiment_id, run_name=f"agent-eval {stamp}",
                              tags={"eval": "true"}) as run:
            mlflow.log_params({"agent_commit": agent_code["commit"], "criteria_commit": criteria["commit"],
                               "head": head, "scenarios": len(first), "agent_model": A.MODEL,
                               "judge_model": a.judge_model or "none"})
            mlflow.log_metrics({"first_pass_passed": summary["first_pass_passed"],
                                "first_pass_failed": len(summary["first_pass_failed"]),
                                "first_pass_incomplete": len(summary["first_pass_incomplete"])})
            mlflow.log_dict(json.loads(json.dumps(out, default=str)), "agent_eval_results.json")
        out["mlflow_run_id"] = run.info.run_id
    except Exception as e:  # noqa: BLE001 - the results file stands; the error is recorded in it
        out["mlflow_run_error"] = f"{type(e).__name__}: {e}"
    path.write_text(json.dumps(out, default=str, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    print(f"results: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
