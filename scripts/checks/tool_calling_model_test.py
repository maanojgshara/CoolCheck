"""One tool-calling request to a pay-per-token model, asking for a Malay and a Tamil heat advisory (Day-2 step 2(a);
re-used on 23 Oct for Free Edition with --profile freeedition).

Auth comes from the Databricks CLI profile through the SDK; no token is read, printed or written.
Two request paths, both with the same chat-completions body and tools list:
  --api serving-endpoints  POST /serving-endpoints/<model>/invocations, <model> a databricks-* endpoint name (default)
  --api gateway            POST /ai-gateway/mlflow/v1/chat/completions with model=<model>, a Unity Gateway model
                           service; Databricks-hosted models are system.ai.<name>
A request that fails is reported (error type and the first 300 characters of its message), not raised.

Run from the repo root: .venv/Scripts/python scripts/checks/tool_calling_model_test.py
    [--profile freeedition] [--api gateway] [--model system.ai.meta-llama-3-3-70b-instruct] [--out <file>]
"""
import argparse
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient

PROFILE = "coolcheck"
ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"
OUT = Path("docs/checks/tool_calling_model_test.md")
TITLE = "Tool-calling model test (Day 2, step 2a)"

TOOL = {
    "type": "function",
    "function": {
        "name": "save_advisory",
        "description": "Save the Malay and Tamil one-sentence heat advisories (dummy tool, stores nothing).",
        "parameters": {
            "type": "object",
            "properties": {
                "malay": {"type": "string", "description": "One-sentence heat advisory in Malay."},
                "tamil": {"type": "string", "description": "One-sentence heat advisory in Tamil."},
            },
            "required": ["malay", "tamil"],
        },
    },
}
PROMPT = (
    "Tomorrow's heat stress in Singapore is forecast to be High. Write one one-sentence heat advisory "
    "for seniors in Malay and one in Tamil. Save both by calling save_advisory once."
)


def request(w, api, model, body):
    if api == "gateway":
        return w.api_client.do("POST", "/ai-gateway/mlflow/v1/chat/completions", body={"model": model, **body})
    return w.api_client.do("POST", f"/serving-endpoints/{model}/invocations", body=body)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--profile", default=PROFILE)
    ap.add_argument("--api", choices=("serving-endpoints", "gateway"), default="serving-endpoints")
    ap.add_argument("--model", default=ENDPOINT, help="endpoint name (serving-endpoints) or model service (gateway)")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--title", default=TITLE)
    args = ap.parse_args(argv)

    w = WorkspaceClient(profile=args.profile)
    body = {"messages": [{"role": "user", "content": PROMPT}], "tools": [TOOL], "tool_choice": "auto", "max_tokens": 600}
    where = (f"- Endpoint: `{args.model}` (pay-per-token, workspace profile `{args.profile}`)"
             if args.api == "serving-endpoints" else
             f"- Model service: `{args.model}` through Unity Gateway `/ai-gateway/mlflow/v1/chat/completions` "
             f"(pay-per-token, workspace profile `{args.profile}`)")
    lines = [f"# {args.title}", "", where]
    try:
        resp = request(w, args.api, args.model, body)
    except Exception as e:  # the error is the result
        lines += [f"- Request failed: {type(e).__name__}: {str(e)[:300]}"]
        args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 1
    choice = resp["choices"][0]
    msg = choice["message"]
    calls = msg.get("tool_calls") or []
    rows, well_formed = [], bool(calls)
    for c in calls:
        try:
            fargs = json.loads(c["function"]["arguments"])
            ok = c["function"]["name"] == TOOL["function"]["name"] and set(fargs) == {"malay", "tamil"}
        except (json.JSONDecodeError, TypeError):
            fargs, ok = {}, False
        well_formed &= ok
        rows.append((c["function"]["name"], ok, fargs))
    lines += [
        f"- finish_reason: `{choice.get("finish_reason")}`; tool calls returned: {len(calls)}",
        f"- Tool calls well-formed (known name, valid JSON, exact argument keys): {'yes' if well_formed else 'NO'}",
        "",
    ]
    for name, ok, fargs in rows:
        lines.append(f"- `{name}` well-formed={ok}")
        lines.append(f"  - Malay: {fargs.get('malay')}")
        lines.append(f"  - Tamil: {fargs.get('tamil')}")
    content = msg.get("content")
    if content:
        lines += ["", "Message text returned alongside:", "",
                  content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)]
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
