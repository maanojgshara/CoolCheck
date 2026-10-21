"""Day-2 step 2(a): one tool-calling call to a pay-per-token serving endpoint, asking for a Malay and a Tamil heat advisory.

Auth comes from the Databricks CLI profile through the SDK; no token is read, printed or written.
Run from the repo root: .venv/Scripts/python scripts/checks/tool_calling_model_test.py
"""
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient

PROFILE = "coolcheck"
ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"
OUT = Path("docs/checks/tool_calling_model_test.md")

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


def main():
    w = WorkspaceClient(profile=PROFILE)
    resp = w.api_client.do(
        "POST",
        f"/serving-endpoints/{ENDPOINT}/invocations",
        body={"messages": [{"role": "user", "content": PROMPT}], "tools": [TOOL], "tool_choice": "auto", "max_tokens": 600},
    )
    choice = resp["choices"][0]
    msg = choice["message"]
    calls = msg.get("tool_calls") or []
    rows, well_formed = [], bool(calls)
    for c in calls:
        try:
            args = json.loads(c["function"]["arguments"])
            ok = c["function"]["name"] == TOOL["function"]["name"] and set(args) == {"malay", "tamil"}
        except (json.JSONDecodeError, TypeError):
            args, ok = {}, False
        well_formed &= ok
        rows.append((c["function"]["name"], ok, args))
    lines = [
        "# Tool-calling model test (Day 2, step 2a)",
        "",
        f"- Endpoint: `{ENDPOINT}` (pay-per-token, workspace profile `{PROFILE}`)",
        f"- finish_reason: `{choice.get("finish_reason")}`; tool calls returned: {len(calls)}",
        f"- Tool calls well-formed (known name, valid JSON, exact argument keys): {'yes' if well_formed else 'NO'}",
        "",
    ]
    for name, ok, args in rows:
        lines.append(f"- `{name}` well-formed={ok}")
        lines.append(f"  - Malay: {args.get('malay')}")
        lines.append(f"  - Tamil: {args.get('tamil')}")
    if msg.get("content"):
        lines += ["", "Message text returned alongside:", "", msg["content"]]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
