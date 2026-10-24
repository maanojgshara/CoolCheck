"""Malay, Tamil and Chinese on three real drafts, with the back-translation check (Guide §14.2; coolcheck.languages).

Three drafts are made by the agent loop (coolcheck.agent.draft_plan) on three requests, one language each, and kept in
--drafts so a second model translates the same three texts. Each translation is translated back into English by
--back-model (another model family) and checked in code: numbers, blocks, places and the "nothing sent" line.
Reads only (the warehouse, the model gateway); writes the report --out and the drafts file.

    .venv\\Scripts\\python scripts/checks/language_check.py --profile coolcheck --models system.ai.meta-llama-3-3-70b-instruct
        [--back-model system.ai.gpt-oss-120b] [--drafts <file.json>] [--out <report.md>]
On Windows set PYTHONIOENCODING=utf-8 so the Tamil and Chinese text prints.
"""
import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from coolcheck import agent as A  # noqa: E402
from coolcheck import languages as L  # noqa: E402
from coolcheck import plan as P  # noqa: E402

DRAFTS = [  # (language, request, briefing date, region)
    ("ms", "Only 8 volunteers tomorrow. Which blocks should we call first?", "2026-10-24", None),
    ("ta", "We have 500 calls for tomorrow.", "2026-10-23", None),
    ("zh", "Only 8 volunteers tomorrow, North-East only.", "2026-10-24", None),
]


def make_drafts(ws, wh, path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    out = []
    for lang, request, day, region in DRAFTS:
        date = dt.date.fromisoformat(day)
        d = A.draft_plan(request, target_date=date, default_capacity=800, calls_per_volunteer=25, region=region,
                         runner=wh, workspace_client=ws, forecast=P.forecast_info(wh, date), trace=False)
        out.append({"lang": lang, "request": request, "date": day, "source_kind": d.source, "fallback_reason": d.fallback_reason,
                    "text": L.readable_text(d), "rows": d.rows, "sources": sorted(L.draft_sources(d)),
                    "tool_calls": [c.summary() for c in d.tool_calls]})
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="coolcheck")
    ap.add_argument("--warehouse", default="Serverless Starter Warehouse")
    ap.add_argument("--models", nargs="+", default=[A.MODEL])
    ap.add_argument("--back-model", default=L.BACK_MODEL)
    ap.add_argument("--drafts", type=Path, required=True, help="JSON file of the three drafts (made once, then reused)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    from databricks.sdk import WorkspaceClient

    ws = WorkspaceClient(profile=a.profile)
    wh = P.Warehouse(ws, next(w.id for w in ws.warehouses.list() if w.name == a.warehouse))
    drafts = make_drafts(ws, wh, a.drafts)
    started = dt.datetime.now(P.SGT)
    lines = [f"# Languages: three drafts, back-translation check ({started:%d %b %Y, %H:%M} SGT)", "",
             f"- Translators: {', '.join(f'`{m}`' for m in a.models)}; back-translation: `{a.back_model}`, through the "
             f"Unity Gateway chat-completions route, temperature 0, profile `{a.profile}`.",
             f"- Label: {L.LABEL}", ""]
    for d in drafts:
        lines += [f"## {L.LANGUAGES[d['lang']]}: \"{d['request']}\" ({d['date']})", "",
                  f"Draft source: {d['source_kind']}{'; ' + d['fallback_reason'] if d['fallback_reason'] else ''}. "
                  f"Tool calls: {json.dumps(d['tool_calls'], default=str)}", "", "English:", "", "```", d["text"], "```", ""]
        for model in a.models:
            t0 = time.monotonic()
            try:
                r = L.translate_text(ws, d["text"], d["lang"], d["rows"], set(d["sources"]), model, a.back_model)
            except Exception as e:  # one failed call is reported, the rest still run
                lines += [f"### `{model}`: ERROR after {time.monotonic() - t0:.0f} s", "", f"{type(e).__name__}: {e}", ""]
                print(f"{d['lang']} {model}: ERROR {type(e).__name__}: {str(e)[:200]}")
                continue
            c = r["checks"]
            lines += [f"### `{model}`: {'PASSED' if c['passed'] else 'DRIFT'} ({time.monotonic() - t0:.0f} s)", "",
                      "Translation:", "", "```", r["translation"], "```", "", "Back-translation:", "", "```",
                      r["back_translation"], "```", "", "Checks: " + json.dumps(c, ensure_ascii=False), ""]
            print(f"{d['lang']} {model}: {'PASSED' if c['passed'] else 'DRIFT'} {json.dumps(c, ensure_ascii=False)}")
    a.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"report: {a.out}")


if __name__ == "__main__":
    main()
