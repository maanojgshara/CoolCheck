"""The agent loop (Guide D13, M6; docs/design/agent_app.md): one function, draft_plan, called by the App and by window D's
evaluation scenarios.

Request text in; out a coolcheck.plan.Draft: the draft text, every tool call with the model's arguments, the SQL
arguments and the rows, the checks and the MLflow trace ID. The model is Llama 3.3 70B through the Unity Gateway
chat-completions route (system.ai.meta-llama-3-3-70b-instruct; docs/checks/free_edition_tool_calling.md, confirmed on
the trial 24 Oct). The three Unity Catalog functions are its tools, described by their own comments.

Rules, enforced in code: the allocation stays in get_priority_areas; the model only pulls values out of the request
(volunteers, calls per volunteer, calls, region, a block) and the arithmetic is in coolcheck.plan.capacity_from; the date
comes from the App; every number in the model's summary must be found in a tool result or an input, so the summary asks
for digits, not number words (the check then works on Malay, Tamil and Chinese text too); never P(High) or the score;
no claim that anything was sent; no medical advice beyond the tier actions. The plan section and the notices are written
by code. On any failure (model error, timeout, round or tool cap, malformed call, no get_priority_areas call, a failed
check) the summary is the per-tier template (decision 4) and fallback_reason says why. Python 3.11 compatible.
"""
import datetime as dt
import json
import re
import time

from coolcheck import plan as P

MODEL = "system.ai.meta-llama-3-3-70b-instruct"
GATEWAY_PATH = "/ai-gateway/mlflow/v1/chat/completions"
MAX_INT = 100000

SYSTEM = """You draft tomorrow's heat outreach plan for an Active Ageing Centre coordinator in Singapore.
Use the tools. Always call get_priority_areas once, with only the values the request states: volunteers, calls per
volunteer, a number of calls, a region. Leave out any value the request does not state; never send 0 for it. Never
compute a number of calls yourself; the app does the arithmetic. If the
request names an HDB block and asks about refuges or a new refuge, call find_refuges or what_if_add_refuge with that block.
Then write a short summary for the coordinator, at most 120 words, plain text:
- Copy every number exactly from the tool results, written as digits (8, 312), never as words. Use each block's
  refuge_distance as written and say distances are straight lines.
- Area risk tiers are Low, Medium, High. Heat levels are Low, Moderate, High. Do not mix them. The vulnerability third
  (upper, middle, lower) is separate from the tier; never call a tier a vulnerability rank.
- Heat is per planning area; blocks rank vulnerability, never heat.
- Never mention probabilities, percent chances or scores.
- If no rated area is in the High tier but a Not rated area has High heat, say so plainly and name it.
- This is a draft for a person to approve. Never say anything was sent, and send nothing.
- No medical advice beyond the tier actions in the tool results.
- If the request asks for something outside this (sending messages, medical advice, other data), say you can only draft
  the plan."""

NUMBER_WORDS = re.compile(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|"
                          r"hundred|thousand|dozen)\b", re.I)
BANNED = [("P(High), probability or score", re.compile(r"p\s*\(\s*high\s*\)|probabilit|\bscore|percent chance|% chance", re.I)),
          ("claims something was sent", re.compile(r"\b(has|have|was|were) been sent\b|\bwe (have )?sent\b|\b(sms|e-?mails?|messages?) (were |was )?sent\b", re.I)),
          ("medical advice", re.compile(r"medic|\bdos(e|age)|diagnos|symptom|prescri|\bpill|tablet|paracetamol|\bdrug", re.I))]
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


# --- tools for the model, described by the Unity Catalog comments ------------------------------------------------------

_SPECS = {}


def tool_specs(ws, catalog="coolcheck"):
    """The three tools in chat-completions form. Descriptions are the functions' comments in Unity Catalog. For
    get_priority_areas the model gives the request's raw values; the date is fixed by the App."""
    if catalog in _SPECS:
        return _SPECS[catalog]
    info = {n: ws.functions.get(f"{catalog}.gold.{n}") for n in ("get_priority_areas", "find_refuges", "what_if_add_refuge")}

    def pcomment(f, name):
        return next((p.comment for p in (f.input_params.parameters if f.input_params else []) if p.name == name), "")

    g = info["get_priority_areas"]
    integer = {"type": "integer", "minimum": 1}
    specs = [
        {"type": "function", "function": {"name": "get_priority_areas", "description": g.comment + " The date is set by the app.",
         "parameters": {"type": "object", "properties": {
             "volunteers": dict(integer, description="Number of volunteers, only if the request states it. The app multiplies "
                                                     "it by calls per volunteer; do not compute calls yourself."),
             "calls_per_volunteer": dict(integer, description="Calls each volunteer can make, only if the request states it; "
                                                              "otherwise the app's stated assumption is used."),
             "call_capacity": dict(integer, description=pcomment(g, "call_capacity") + " Only if the request states a "
                                                        "number of calls; otherwise omit it."),
             "region": {"type": "string", "description": pcomment(g, "region") + " Only if the request names a region."}},
             "required": []}}}]
    for name in ("find_refuges", "what_if_add_refuge"):
        f = info[name]
        specs.append({"type": "function", "function": {"name": name, "description": f.comment, "parameters": {
            "type": "object", "properties": {"blk_no": {"type": "string", "description": pcomment(f, "blk_no")},
                                             "street": {"type": "string", "description": pcomment(f, "street")}},
            "required": ["blk_no", "street"]}}})
    _SPECS[catalog] = specs
    return specs


class Gateway:
    """Chat completions on the Unity Gateway path with the workspace client's own authentication."""

    def __init__(self, ws, model=MODEL):
        self.ws, self.model = ws, model

    def __call__(self, messages, tools):
        return self.ws.api_client.do("POST", GATEWAY_PATH, body={"model": self.model, "messages": messages, "tools": tools,
                                                                  "tool_choice": "auto", "max_tokens": 600,
                                                                  "temperature": 0})


# --- the number check ------------------------------------------------------------------------------------------------

def _num(s):
    s = s.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s) else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:  # e.g. Unicode digits Python's float accepts anyway; anything else is ungrounded
        return None


def source_numbers(*objs):
    """Every number written in the tool results and inputs (inside strings too: LOR 1, 208A, 00:49)."""
    out = set()
    for o in objs:
        for m in NUMBER.findall(json.dumps(o, default=str, ensure_ascii=False)):
            v = _num(m)
            if v is not None:
                out.add(v)
    return out


def grounded(token, sources, percent=False):
    v = _num(token)
    if v is None:
        return False
    cands = {s * 100 for s in sources if 0 <= s <= 1} if percent else set(sources)
    if v in cands:
        return True
    if "." in token.replace(",", "") or percent:
        dec = len(token.split(".")[-1]) if "." in token else 0
        tol = 0.5 * 10 ** -dec
    elif v >= 100 and v % 100 == 0:
        tol = 50
    elif v >= 10 and v % 10 == 0:
        tol = 5
    else:
        tol = 0
    return any(abs(v - s) <= tol for s in cands)


def check_summary(text, sources, unrated_hot=(), rated_high=True, source_text=""):
    """(passed, checks): digits only (a number word passes only if a tool result uses it, e.g. "four languages" in the
    tier actions), every number grounded, no banned content. Records whether Not-rated High heat is named when no rated
    area is High (the code notice is shown either way)."""
    used = {w.lower() for w in NUMBER_WORDS.findall(source_text or "")}
    checks = {"ungrounded_numbers": [], "number_words": [w for w in NUMBER_WORDS.findall(text) if w.lower() not in used],
              "banned": []}
    for m in re.finditer(r"(\d+(?:[.,]\d+)*)(\s*%)?", text):
        if not grounded(m.group(1), sources, percent=bool(m.group(2))):
            checks["ungrounded_numbers"].append(m.group(0).strip())
    checks["banned"] = [name for name, rx in BANNED if rx.search(text)]
    if unrated_hot and not rated_high:
        checks["names_unrated_high_heat"] = all(a.lower() in text.lower() for a in unrated_hot)
    ok = not (checks["ungrounded_numbers"] or checks["number_words"] or checks["banned"]) and bool(text.strip())
    return ok, checks


# --- the loop --------------------------------------------------------------------------------------------------------

def _compact(rows):
    keep = ("area_order", "planning_area", "region", "heat_level", "third", "tier", "tier_sentence", "reason", "actions",
            "rental_1_2_room", "calls_allocated", "calls_left")
    out = []
    for r in rows:
        a = {k: r[k] for k in keep}
        a["blocks"] = [dict({k: b[k] for k in ("blk_no", "street", "rental_1_2_room", "calls_allocated", "partial",
                                               "refuge_main_name", "refuge_within_400m")},
                            refuge_distance=P.metres(b["refuge_main_m"])) for b in r["blocks"]]
        out.append(a)
    return out


def _int_arg(args, name):
    """A whole number from the model's arguments; None when absent, and also when 0, since the model was seen sending 0
    for a value the request did not state (24 Oct: calls_per_volunteer 0 gave 8 x 0 = 0 calls). A team with no capacity
    sets 0 in the form, where the capacity basis line shows it."""
    v = args.get(name)
    if v is None or v == "":
        return None
    v = int(v)  # ValueError for a malformed value; reported to the model
    if not 0 <= v <= MAX_INT:
        raise ValueError(f"{name} must be between 0 and {MAX_INT}")
    return v or None


def draft_plan(request, *, target_date, default_capacity, calls_per_volunteer, region=None, catalog="coolcheck",
               runner=None, workspace_client=None, warehouse_id=None, chat=None, specs=None, model=MODEL, forecast=None,
               max_rounds=4, max_tool_calls=6, timeout_s=90.0, trace=True):
    """Draft the plan for a request. Returns a coolcheck.plan.Draft with source 'agent' (the model's summary passed the
    checks) or 'template' (fallback_reason says why). Give runner (a coolcheck.plan.Warehouse) or warehouse_id, and
    workspace_client for the model and the tool descriptions; chat and specs replace them in tests."""
    t0 = time.monotonic()
    ws = workspace_client
    runner = runner or P.Warehouse(ws, warehouse_id)
    chat = chat or Gateway(ws, model)
    masked, n_masked = P.mask_personal(request or "")
    form_region = P.region_param(region)
    form_cap, form_basis = P.capacity_from(default_capacity, calls_per_volunteer)
    with P.span("draft_plan", "AGENT", {"request": masked, "target_date": str(target_date), "default_capacity": default_capacity,
                                        "calls_per_volunteer": calls_per_volunteer, "region": form_region, "model": model},
                trace) as root:
        tools = P.Tools(runner, catalog, trace)
        state = {"gpa": None, "cap": None, "basis": None, "region": form_region}
        summary, reason, checks, rounds = None, None, {}, 0
        try:
            specs = specs or tool_specs(ws, catalog)
            messages = [{"role": "system", "content": SYSTEM},
                        {"role": "user", "content": f"Briefing date (fixed by the app): {target_date:%d %b %Y}. "
                                                    f"Region chosen in the form: {form_region or 'whole island'}.\n"
                                                    f"Request: {masked or '(none: draft the plan for the form values)'}"}]
            n_calls = 0
            while True:
                if rounds >= max_rounds:
                    raise RuntimeError(f"no final answer within {max_rounds} model rounds")
                if time.monotonic() - t0 > timeout_s:
                    raise TimeoutError(f"timed out after {timeout_s:.0f} s")
                rounds += 1
                with P.span(f"model round {rounds}", "CHAT_MODEL", {"messages": messages}, trace) as s:
                    resp = chat(messages, specs)
                    s.set_outputs(resp)
                msg = resp["choices"][0]["message"]
                calls = msg.get("tool_calls") or []
                if not calls:
                    summary = (msg.get("content") or "").strip()
                    break
                messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
                for c in calls:
                    n_calls += 1
                    if n_calls > max_tool_calls:
                        raise RuntimeError(f"more than {max_tool_calls} tool calls")
                    result = _run_tool(c, tools, target_date, default_capacity, calls_per_volunteer, state)
                    messages.append({"role": "tool", "tool_call_id": c.get("id"), "content": json.dumps(result, default=str)})
            if state["gpa"] is None:
                raise RuntimeError("the model did not call get_priority_areas")
            rows = state["gpa"].rows
            sources = source_numbers([c.rows for c in tools.calls], target_date.isoformat(), target_date.strftime("%d %m %Y"),
                                     state["cap"], state["basis"], default_capacity, calls_per_volunteer, masked,
                                     (forecast or {}).get("scored_at_sgt"), 400)
            unrated = [P.area_name(r["planning_area"]) for r in rows
                       if r["heat_level"] == "High" and r["tier"] in ("Not rated", "No forecast")]
            ok, checks = check_summary(summary, sources, unrated, any(r["tier"] == "High" for r in rows),
                                       json.dumps([c.rows for c in tools.calls], default=str, ensure_ascii=False))
            if not ok:
                reason = "the model's summary failed the checks: " + "; ".join(
                    f"{k}: {v}" for k, v in checks.items() if v and k != "names_unrated_high_heat")
        except Exception as e:
            reason = reason or f"{type(e).__name__}: {e}"
        if reason:
            summary = None
        if state["gpa"] is None or state["gpa"].error:
            call = tools.get_priority_areas(target_date, form_cap, form_region)
            if call.error:
                raise P.ToolError(f"get_priority_areas failed: {call.error}")
            state.update(gpa=call, cap=form_cap, basis=form_basis, region=form_region)
        rows = state["gpa"].rows
        d = P.Draft(target_date=target_date, region=state["region"], call_capacity=state["cap"], capacity_basis=state["basis"],
                    rows=rows, tool_calls=list(tools.calls), forecast=forecast or {},
                    summary_text=summary or P.template_summary(rows, state["cap"]),
                    source=P.AGENT if summary else P.TEMPLATE, fallback_reason=reason, request_text=masked or None,
                    llm_model=model if summary else None,
                    checks=dict(checks, rounds=rounds, masked=n_masked, elapsed_s=round(time.monotonic() - t0, 1)))
        root.set_outputs({"draft_text": d.draft_text, "source": d.source, "fallback_reason": reason, "checks": d.checks})
        d.trace_id = P.trace_id_of(root)
    return d


def _run_tool(c, tools, target_date, default_capacity, calls_per_volunteer, state):
    """Run one tool call; the result (or the error) goes back to the model."""
    name = (c.get("function") or {}).get("name")
    raw = (c.get("function") or {}).get("arguments") or "{}"
    try:
        args = json.loads(raw) if isinstance(raw, str) else dict(raw)
        if not isinstance(args, dict):
            raise ValueError("arguments are not an object")
    except Exception as e:
        return {"error": f"malformed arguments: {e}"}
    try:
        if name == "get_priority_areas":
            unknown = set(args) - {"volunteers", "calls_per_volunteer", "call_capacity", "region"}
            if unknown:
                return {"error": f"unknown arguments: {sorted(unknown)}"}
            cap, basis = P.capacity_from(default_capacity, calls_per_volunteer, _int_arg(args, "volunteers"),
                                         _int_arg(args, "calls_per_volunteer"), _int_arg(args, "call_capacity"))
            region = P.region_param(args.get("region")) or state["region"]
            call = tools.get_priority_areas(target_date, cap, region, llm_arguments=args)
            if call.error:
                return {"error": call.error}
            state.update(gpa=call, cap=cap, basis=basis, region=region)
            return {"call_capacity": cap, "capacity_basis": basis, "region": region or "whole island",
                    "areas": _compact(call.rows)}
        if name in ("find_refuges", "what_if_add_refuge"):
            if not (args.get("blk_no") and args.get("street")):
                return {"error": "blk_no and street are required"}
            call = getattr(tools, name)(args["blk_no"], args["street"], llm_arguments=args)
            return {"error": call.error} if call.error else {"rows": call.rows or "no rows: block not found or not confirmed"}
        return {"error": f"unknown tool {name!r}"}
    except ValueError as e:
        return {"error": str(e)}
