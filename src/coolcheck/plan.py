"""The draft outreach plan, without a model: the three agent tools called through a SQL warehouse, the per-tier template
(Guide decision 4), the notices, the plan text and the approval row (docs/design/agent_app.md).

Used by the App (src/app.py) on its own and as the fallback of the agent loop (coolcheck.agent). Every number in the text
comes from a tool result or an input: get_priority_areas allocates the calls, and nothing here re-allocates or computes a
heat value. Blocks rank vulnerability, never heat. Nothing here sends anything: the approval row is the end of the line.
Python 3.11 compatible (the Databricks Apps runtime).
"""
import datetime as dt
import json
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from coolcheck.agent_tools import CALL_TIERS, TIER_ORDER

REGIONS = ("CENTRAL", "EAST", "NORTH", "NORTH-EAST", "WEST")
STATUS = "approved_not_sent"
TEMPLATE = "template"
AGENT = "agent"

# --- masking: before a request is stored or sent to a model ---------------------------------------------------------

NRIC = re.compile(r"(?<![A-Za-z0-9])[STFGMstfgm]\d{7}[A-Za-z](?![A-Za-z0-9])")
PHONE = re.compile(r"(?<![\d+])(?:\+?65[ -]?)?[689]\d{3}[ -]?\d{4}(?!\d)")
MASK_NOTE = ("Requests are stored with the approval. NRIC-like strings (S, T, F, G or M, 7 digits and a letter) and "
             "8-digit phone-like numbers starting with 6, 8 or 9 are masked before the request is stored or sent to the model.")


def mask_personal(text):
    """(masked text, number of masks): NRIC-like strings and 8-digit phone-like numbers starting with 6, 8 or 9."""
    if not text:
        return text, 0
    out, n1 = NRIC.subn("[NRIC masked]", text)
    out, n2 = PHONE.subn("[phone masked]", out)
    return out, n1 + n2


# --- the warehouse -------------------------------------------------------------------------------------------------

class ToolError(RuntimeError):
    pass


def _split_top(s):
    """Split on commas not inside <...>."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    return out + [cur] if cur.strip() else out


def parse_type(text):
    """A SQL type text as a tree: ("ARRAY", elem), ("STRUCT", [(name, type), ...]) or a scalar name, e.g. "INT"."""
    t = text.strip()
    u = t.upper()
    if u.startswith("ARRAY<"):
        return ("ARRAY", parse_type(t[6:-1]))
    if u.startswith("STRUCT<"):
        fields = []
        for part in _split_top(t[7:-1]):
            name, _, typ = part.strip().partition(":")
            fields.append((name.strip().strip("`"), parse_type(typ.strip().split(" COMMENT ")[0])))
        return ("STRUCT", fields)
    return u.split("(")[0].split(" ")[0]


def _convert(value, typ):
    """A JSON_ARRAY value (a string, or nested JSON for arrays and structs) as Python, by its declared type."""
    if value is None:
        return None
    if isinstance(typ, tuple):
        if isinstance(value, str):
            value = json.loads(value)
        if typ[0] == "ARRAY":
            return [_convert(v, typ[1]) for v in value]
        return {name: _convert(value.get(name), t) for name, t in typ[1]}
    if typ in ("INT", "INTEGER", "LONG", "BIGINT", "SHORT", "SMALLINT", "BYTE", "TINYINT"):
        return int(value)
    if typ in ("DOUBLE", "FLOAT", "DECIMAL"):
        return float(value)
    if typ == "BOOLEAN":
        return value if isinstance(value, bool) else str(value).lower() == "true"
    return value


class Warehouse:
    """Runs one statement on a SQL warehouse (Statement Execution API) with named, typed parameters; rows as dicts."""

    def __init__(self, ws, warehouse_id, timeout_s=60):
        self.ws, self.warehouse_id, self.timeout_s = ws, warehouse_id, timeout_s

    def query(self, sql, params=None, timeout_s=None):
        from databricks.sdk.service.sql import (Disposition, ExecuteStatementRequestOnWaitTimeout, Format,
                                                StatementParameterListItem, StatementState)
        deadline = time.monotonic() + (timeout_s or self.timeout_s)
        items = [StatementParameterListItem(name=k, value=None if v is None else str(v), type=t)
                 for k, (v, t) in (params or {}).items()]
        sx = self.ws.statement_execution
        r = sx.execute_statement(statement=sql, warehouse_id=self.warehouse_id, parameters=items, wait_timeout="30s",
                                 on_wait_timeout=ExecuteStatementRequestOnWaitTimeout.CONTINUE,
                                 format=Format.JSON_ARRAY, disposition=Disposition.INLINE)
        while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
            if time.monotonic() > deadline:
                sx.cancel_execution(r.statement_id)
                raise ToolError(f"statement timed out after {timeout_s or self.timeout_s} s")
            time.sleep(1)
            r = sx.get_statement(r.statement_id)
        if r.status.state != StatementState.SUCCEEDED:
            err = r.status.error
            raise ToolError(f"{r.status.state.value}: {err.message if err else 'no message'}")
        cols = [(c.name, parse_type(c.type_text or (c.type_name.value if c.type_name else "STRING")))
                for c in r.manifest.schema.columns]
        data = list((r.result.data_array if r.result else None) or [])
        for n in range(1, r.manifest.total_chunk_count or 1):
            data += sx.get_statement_result_chunk_n(r.statement_id, n).data_array or []
        return [{name: _convert(v, t) for (name, t), v in zip(cols, row)} for row in data]


# --- tracing: MLflow spans when mlflow is installed, otherwise nothing -------------------------------------------------

class _NoSpan:
    trace_id = None

    def set_inputs(self, *_):
        pass

    def set_outputs(self, *_):
        pass

    def set_attribute(self, *_):
        pass


@contextmanager
def span(name, span_type, inputs=None, enabled=True):
    """An MLflow span (a trace when it is the outermost one); a no-op span if tracing is off or mlflow is missing."""
    mlflow = None
    if enabled:
        try:
            import mlflow
        except ImportError:
            mlflow = None
    if mlflow is None:
        yield _NoSpan()
        return
    with mlflow.start_span(name=name, span_type=span_type) as s:
        if inputs is not None:
            s.set_inputs(inputs)
        yield s


def trace_id_of(s):
    """The span's trace ID, or None for a no-op span (tracing off, or no experiment set)."""
    tid = getattr(s, "trace_id", None)
    return None if not tid or str(tid).startswith("MLFLOW_NO_OP") else tid


# --- the tools -----------------------------------------------------------------------------------------------------

@dataclass
class ToolCall:
    name: str
    arguments: dict            # what ran in SQL; for a refused call only what the App fixes (get_priority_areas' date)
    rows: list = field(default_factory=list)
    error: str = None
    elapsed_ms: int = 0
    llm_arguments: dict = None  # what the model asked for (agent loop only; the raw text if it was not JSON)
    refused: bool = False       # refused by the agent loop before any SQL ran (Tools.refuse): nothing ran

    def summary(self):
        return {"name": self.name, "arguments": self.arguments, "llm_arguments": self.llm_arguments,
                "row_count": len(self.rows), "error": self.error, "elapsed_ms": self.elapsed_ms, "refused": self.refused}

    def line(self):
        """The call in the App's Tool calls list (Markdown): what ran in SQL and what came back, or the error a call
        refused before SQL gave the model."""
        asked = f" (the model asked for `{self.llm_arguments}`)" if self.llm_arguments is not None else ""
        if self.refused:
            return f"**{self.name or 'unnamed tool'}**, refused before SQL{asked}: {self.error}"
        return (f"**{self.name}** `{self.arguments}`{asked}: {len(self.rows)} rows in {self.elapsed_ms} ms"
                f"{'; error: ' + self.error if self.error else ''}")


def region_param(region):
    """The region for get_priority_areas: None for the whole island, otherwise as given."""
    r = (region or "").strip()
    return None if r.upper() in ("", "ALL", "WHOLE ISLAND") else r


class Tools:
    """The three Unity Catalog functions by full name, each call recorded (and traced as a TOOL span), and so is each
    call the agent loop refuses before SQL."""

    def __init__(self, runner, catalog="coolcheck", trace=True):
        if not re.fullmatch(r"\w+", catalog):
            raise ValueError(f"bad catalog name: {catalog!r}")
        self.runner, self.catalog, self.trace = runner, catalog, trace
        self.calls = []

    def fn(self, name):
        return f"{self.catalog}.gold.{name}"

    def _call(self, name, sql, params, llm_arguments=None):
        args = {k: v for k, (v, _) in params.items()}
        call = ToolCall(name=name, arguments=args, llm_arguments=llm_arguments)
        t0 = time.monotonic()
        with span(name, "TOOL", {"arguments": args, "llm_arguments": llm_arguments}, self.trace) as s:
            try:
                call.rows = self.runner.query(sql, params)
            except Exception as e:  # recorded, shown, and the caller decides
                call.error = f"{type(e).__name__}: {e}"
            call.elapsed_ms = int((time.monotonic() - t0) * 1000)
            s.set_outputs({"rows": call.rows, "error": call.error})
        self.calls.append(call)
        return call

    def refuse(self, name, llm_arguments, error, arguments=None):
        """A call the agent loop refused before any SQL ran (malformed or unknown arguments, an unknown region, no block
        number, an unknown tool, the tool-call cap): recorded with the model's arguments and the error, in its own TOOL
        span, so the calls and the trace keep every call the model made, in its order. arguments: what the App fixes
        whatever the model sends (get_priority_areas' date), which window D's date check reads on every call."""
        call = ToolCall(name=str(name or ""), arguments=dict(arguments or {}), error=error, llm_arguments=llm_arguments,
                        refused=True)
        with span(call.name or "unnamed tool", "TOOL", {"arguments": call.arguments, "llm_arguments": llm_arguments},
                  self.trace) as s:
            s.set_outputs({"rows": [], "error": error, "refused": True})
        self.calls.append(call)
        return call

    def get_priority_areas(self, target_date, call_capacity, region=None, llm_arguments=None):
        call = self._call("get_priority_areas",
                          f"SELECT * FROM {self.fn('get_priority_areas')}(:target_date, :call_capacity, :region)",
                          {"target_date": (str(target_date), "DATE"), "call_capacity": (int(call_capacity), "INT"),
                           "region": (region_param(region), "STRING")}, llm_arguments)
        call.rows.sort(key=lambda r: r["area_order"])
        return call

    def find_refuges(self, blk_no, street, llm_arguments=None):
        call = self._call("find_refuges", f"SELECT * FROM {self.fn('find_refuges')}(:blk_no, :street)",
                          {"blk_no": (str(blk_no), "STRING"), "street": (str(street), "STRING")}, llm_arguments)
        call.rows.sort(key=lambda r: r["refuge_rank"])
        return call

    def what_if_add_refuge(self, blk_no, street, llm_arguments=None):
        call = self._call("what_if_add_refuge", f"SELECT * FROM {self.fn('what_if_add_refuge')}(:blk_no, :street)",
                          {"blk_no": (str(blk_no), "STRING"), "street": (str(street), "STRING")}, llm_arguments)
        call.rows.sort(key=lambda r: (not r["is_site_area"], r["planning_area"]))
        return call


# --- reads of gold.area_heat_risk (the App's principal has SELECT on this view only) ---------------------------------

def briefing_dates(runner, catalog="coolcheck", limit=14):
    rows = runner.query(f"SELECT DISTINCT target_date FROM {catalog}.gold.area_heat_risk ORDER BY target_date DESC "
                        f"LIMIT {int(limit)}")
    return [dt.date.fromisoformat(r["target_date"]) for r in rows]


def forecast_info(runner, target_date, catalog="coolcheck"):
    """The scoring run behind a date: run ID, scored_at (as the warehouse returns it, UTC) and the missing-forecast flag."""
    rows = runner.query(
        f"SELECT max(run_id) AS run_id, count(DISTINCT run_id) AS n_runs, max(scored_at) AS scored_at, "
        f"max(date_format(from_utc_timestamp(scored_at, 'Asia/Singapore'), 'd MMM yyyy, HH:mm')) AS scored_at_sgt, "
        f"bool_or(forecast_missing) AS forecast_missing, count(*) AS n_areas "
        f"FROM {catalog}.gold.area_heat_risk WHERE target_date = :d", {"d": (str(target_date), "DATE")})
    return rows[0] if rows else {}


# --- capacity: values from the request override the form; the arithmetic is here, never in a model -------------------

def _n(x):
    """A whole number with thousands separators for code-written text ("40,309"); the number checks read both forms."""
    try:
        return f"{int(x):,}" if float(x) == int(x) else str(x)
    except (TypeError, ValueError):
        return str(x)


def capacity_from(default_capacity, calls_per_volunteer, volunteers=None, request_calls_per_volunteer=None,
                  request_capacity=None):
    """(call_capacity, basis). A capacity stated in the request wins; else volunteers x calls per volunteer (the request's
    figure if stated, otherwise the App's assumption); else the form's capacity."""
    if request_capacity is not None:
        return int(request_capacity), f"request: {_n(request_capacity)} calls"
    if volunteers is not None:
        if request_calls_per_volunteer is not None:
            cpv, note = int(request_calls_per_volunteer), "calls per volunteer from the request"
        else:
            cpv, note = int(calls_per_volunteer), "calls per volunteer (assumption: replace with your team's figure)"
        cap = int(volunteers) * cpv
        return cap, f"request: {_n(volunteers)} volunteers x {_n(cpv)} {note} = {_n(cap)} calls"
    return int(default_capacity), f"form: {_n(default_capacity)} calls (placeholder: replace with your team's figure)"


# --- the text ------------------------------------------------------------------------------------------------------

def area_name(name):
    """A planning area or region with a capital after each space and hyphen: "Ang Mo Kio", "North-Eastern Islands",
    "North-East" (as the dashboard writes them)."""
    return " ".join("-".join(p.capitalize() for p in w.split("-")) for w in (name or "").split())


def region_name(region):
    return area_name((region or "").replace(" REGION", ""))


def where_in(region):
    """' in the North-East region' for a region, '' for the whole island: the scope of a "no rated area" sentence."""
    r = region_param(region)
    return f" in the {region_name(r)} region" if r else ""


def no_tier_sentence(tier, region=None):
    return f"No rated area{where_in(region)} is in the {tier} tier."


def metres(m):
    """A straight-line distance rounded to 10 m, for speaking; under 10 m is "at the block" (5.0 rounds to even, which
    gave "about 0 m": D01 on 24 Oct)."""
    if m is None:
        return "unknown distance"
    return "at the block" if m < 10 else f"about {_n(round(m, -1))} m"


def _join(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


SGT = dt.timezone(dt.timedelta(hours=8), "Asia/Singapore")  # Singapore has no daylight saving; no tz database needed


def sgt_today(now=None):
    """Today's date on the Singapore clock (not the warehouse's current_date(), which may run in UTC)."""
    return (now or dt.datetime.now(dt.timezone.utc)).astimezone(SGT).date()


def stale_notice(latest_date, today=None):
    """The top-of-page notice when the newest forecast is for a date before today in Singapore; else None."""
    if latest_date is None:
        return "No forecast is available yet."
    today = today or sgt_today()
    return f"No forecast for today yet; this is the plan for {_day(latest_date)}." if latest_date < today else None


def notices(rows, target_date, forecast=None, region=None):
    """Notices that are always shown, whatever wrote the summary; a "no rated area" sentence names the plan's region."""
    out = []
    if forecast and forecast.get("forecast_missing"):
        out.append("The NEA forecast issue was missing for this date; heat levels were scored without it.")
    if not rows:
        out.append("No areas came back for this date and region (an unknown region gives no rows).")
        return out
    rated_high = [r for r in rows if r["tier"] == "High"]
    unrated_hot = [area_name(r["planning_area"]) for r in rows
                   if r["heat_level"] == "High" and r["tier"] in ("Not rated", "No forecast")]
    day = _day(target_date)
    if unrated_hot and not rated_high:
        out.append(f"No rated area{where_in(region)} is High on {day}. {_join(unrated_hot)} "
                   f"{'has' if len(unrated_hot) == 1 else 'have'} High heat but "
                   f"{'is' if len(unrated_hot) == 1 else 'are'} Not rated (no confirmed HDB blocks), so CoolCheck has no "
                   f"blocks or calls there; check with the local team.")
    elif unrated_hot:
        out.append(f"High heat but Not rated (no confirmed HDB blocks, so no blocks or calls): {_join(unrated_hot)}.")
    elif not rated_high and region_param(region):  # a regional plan; the dashboard shows the whole island
        out.append(no_tier_sentence("High", region))
    no_fc = [area_name(r["planning_area"]) for r in rows if r["tier"] == "No forecast"]
    if no_fc:
        out.append(f"No forecast for {_join(no_fc)}.")
    return out


BLOCK_NO = re.compile(r"\s*(?:blk|block)?[.\s]*(\d+[a-z]?)\s*", re.I)


def lookup_notices(tool_calls):
    """A block lookup that found no confirmed HDB block: find_refuges or what_if_add_refuge with no rows and no error."""
    out = []
    for c in tool_calls:
        m = BLOCK_NO.fullmatch(str(c.arguments.get("blk_no") or ""))
        if c.name not in ("find_refuges", "what_if_add_refuge") or c.error or c.rows or not m:
            continue  # not a block number, nothing to correct (24 Oct, B03: "to be determined by get_priority_areas")
        what = "no refuges are listed for it" if c.name == "find_refuges" else "the what-if for a refuge there did not run"
        n = (f"Blk {m.group(1).upper()} {str(c.arguments.get('street') or '').strip()} was not found among CoolCheck's "
             f"confirmed HDB blocks, so {what}; check the block number and street.")
        if n not in out:
            out.append(n)
    return out


def whatif_gain(rows):
    """A what_if_add_refuge result per area with the gain computed in code (24 Oct, run 2: the model wrote 8,021, 8,031
    and 8,030 for W01's 8,011): HDB dwelling units newly within 400 m of a refuge, before and after, the blocks newly
    within, the 1-2 room rental flats beyond 400 m before and after."""
    return [{"planning_area": area_name(r["planning_area"]), "is_site_area": r["is_site_area"],
             "dwelling_units_newly_within_400m": r["du_within_400m_after"] - r["du_within_400m_before"],
             "dwelling_units_within_400m_before": r["du_within_400m_before"],
             "dwelling_units_within_400m_after": r["du_within_400m_after"],
             "blocks_newly_within_400m": r["blocks_newly_within"],
             "rental_flats_beyond_400m_before": r["rental_flats_beyond_400m_before"],
             "rental_flats_beyond_400m_after": r["rental_flats_beyond_400m_after"]} for r in rows]


def whatif_notices(tool_calls):
    """The result of each what-if that found its block, in the function's own terms, whoever writes the summary."""
    out = []
    for c in (c for c in tool_calls if c.name == "what_if_add_refuge" and not c.error and c.rows):
        parts = [f"{g['planning_area']}: {_n(g['dwelling_units_newly_within_400m'])} more HDB dwelling units within 400 m of a "
                 f"refuge ({_n(g['dwelling_units_within_400m_before'])} to {_n(g['dwelling_units_within_400m_after'])}), "
                 f"{_n(g['blocks_newly_within_400m'])} block{'' if g['blocks_newly_within_400m'] == 1 else 's'} newly within "
                 f"400 m, 1-2 room rental flats beyond 400 m {_n(g['rental_flats_beyond_400m_before'])} to "
                 f"{_n(g['rental_flats_beyond_400m_after'])}" for g in whatif_gain(c.rows)]
        site = c.rows[0]  # the site's area first (the function's order, kept by Tools)
        n = (f"What if a refuge opened at Blk {site['site_blk_no']} {site['site_street']}: {'; '.join(parts)}. "
             f"Straight-line distances, confirmed blocks only.")
        if n not in out:
            out.append(n)
    return out


def leftover_notice(rows, capacity, summary=""):
    """The calls left over once every block in the High- and Medium-tier areas has its calls; None when there are none or the
    summary already gives the number (the template does)."""
    left = min((r["calls_left"] for r in rows), default=0)
    if not capacity or left <= 0 or left in {int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", summary or "")}:
        return None
    if any(r["calls_allocated"] > 0 for r in rows):
        return f"{_n(left)} of the {_n(capacity)} calls are left over: every block in this plan's High- and Medium-tier areas has its calls."
    return f"All {_n(capacity)} calls are left over: no block in a High- or Medium-tier area of this plan takes calls."


def _day(d):
    d = d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d))
    return f"{d.day} {d:%b}"


def template_summary(rows, capacity, region=None):
    """The per-tier template (decision 4): names and numbers from get_priority_areas only."""
    by_tier = {t: [r for r in rows if r["tier"] == t] for t in TIER_ORDER}
    parts = []
    for tier in ("High", "Medium"):
        areas = by_tier[tier]
        if not areas:
            parts.append(no_tier_sentence(tier, region))
            continue
        names = [area_name(r["planning_area"]) for r in areas]
        lead = _join(names) if len(names) <= 3 else f"{len(names)} areas, led by {_join(names[:3])}"
        parts.append(f"{tier} tier: {lead}.")
    low = len(by_tier["Low"])
    if low:
        parts.append(f"{low} area{'s are' if low != 1 else ' is'} Low: routine, no calls.")
    given = [r for r in rows if r["calls_allocated"] > 0]
    allocated = sum(r["calls_allocated"] for r in given)
    if given:
        n_blocks = sum(len(r["blocks"]) for r in given)
        parts.append(f"Of {_n(capacity)} calls, {_n(allocated)} go to {_n(n_blocks)} block{'s' if n_blocks != 1 else ''} in "
                     f"{_join(area_name(r['planning_area']) for r in given)}; {_n(given[-1]['calls_left'])} left.")
    elif capacity > 0:
        parts.append(f"None of the {_n(capacity)} calls are allocated: no block in a High- or Medium-tier area takes calls.")
    else:
        parts.append("No call capacity was given, so no blocks are allocated.")
    return " ".join(parts)


def plan_section(rows):
    """The areas given calls, in order: tier sentence, reason, actions, blocks and calls (all as returned)."""
    lines = []
    for r in (r for r in rows if r["calls_allocated"] > 0):
        lines.append(f"{r['area_order']}. {area_name(r['planning_area'])} ({region_name(r['region'])}): {r['tier_sentence']}")
        lines.append(f"   Why: {r['reason']}")
        lines.append(f"   Actions: {r['actions']} ({r['actions_status']})")
        lines.append(f"   Calls: {_n(r['calls_allocated'])} of the area's {_n(r['rental_1_2_room'])} 1-2 room rental flats; "
                     f"{_n(r['calls_left'])} calls left after this area.")
        for b in r["blocks"]:
            dist = metres(b["refuge_main_m"])
            refuge = (f"nearest refuge {b['refuge_main_name']}, {dist}{'' if dist == 'at the block' else ' in a straight line'}"
                      f"{' (within 400 m)' if b['refuge_within_400m'] else ''}") if b.get("refuge_main_name") else "no refuge found"
            lines.append(f"   - Blk {b['blk_no']} {b['street']}: {_n(b['calls_allocated'])} calls of {_n(b['rental_1_2_room'])} "
                         f"flats{' (partial)' if b['partial'] else ''}; {refuge}")
    return "\n".join(lines) if lines else "No blocks are allocated calls."


def header(target_date, basis, region, forecast=None):
    scored = f" Forecast scored {forecast['scored_at_sgt']} SGT." if forecast and forecast.get("scored_at_sgt") else ""
    where = region_name(region_param(region)) if region_param(region) else "the whole island"
    return f"CoolCheck draft outreach plan for {_day(target_date)} {target_date:%Y}, {where}.{scored} Call capacity: {basis}."


FOOTER = ("Draft only: nothing has been sent. A person approves; the Active Ageing Centre matches the blocks against its "
          "own client list (CoolCheck holds no personal data). Heat is forecast per planning area; blocks rank "
          "vulnerability, never heat. Distances are straight lines, not walking distances.")


@dataclass
class Draft:
    target_date: dt.date
    region: Any
    call_capacity: int
    capacity_basis: str
    rows: list
    tool_calls: list
    forecast: dict
    summary_text: str
    source: str = TEMPLATE
    fallback_reason: str = None
    request_text: str = None
    llm_model: str = None
    trace_id: str = None
    checks: dict = field(default_factory=dict)
    approval_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    notes: list = field(default_factory=list)  # the agent loop's: a region not among the five, values not used

    @property
    def notices(self):
        """Every note on the draft, all written by code: the loop's, the areas', the block lookups' and the calls left."""
        left = leftover_notice(self.rows, self.call_capacity, self.summary_text)
        out = (list(self.notes) + notices(self.rows, self.target_date, self.forecast, self.region)
               + lookup_notices(self.tool_calls) + whatif_notices(self.tool_calls) + ([left] if left else []))
        return [n for n in out if n not in (self.summary_text or "")]  # a sentence the summary already has, once

    @property
    def calls_allocated(self):
        return sum(r["calls_allocated"] for r in self.rows)

    @property
    def draft_text(self):
        parts = [header(self.target_date, self.capacity_basis, self.region, self.forecast), "",
                 ("Summary: " if self.source == AGENT else "Summary (template): ") + self.summary_text]
        if self.notices:
            parts += [""] + [f"Note: {n}" for n in self.notices]
        parts += ["", "Plan:", plan_section(self.rows), "", FOOTER]
        return "\n".join(parts)


def draft_direct(tools, target_date, call_capacity, capacity_basis, region=None, forecast=None, reason=None,
                 trace=True):
    """The plan from get_priority_areas with the per-tier template; traced as one AGENT span when mlflow is present."""
    with span("draft_plan_direct", "AGENT", {"target_date": str(target_date), "call_capacity": call_capacity,
                                              "region": region_param(region)}, trace) as s:
        call = tools.get_priority_areas(target_date, call_capacity, region)
        if call.error:
            raise ToolError(f"get_priority_areas failed: {call.error}")
        d = Draft(target_date=target_date, region=region_param(region), call_capacity=int(call_capacity),
                  capacity_basis=capacity_basis, rows=call.rows, tool_calls=list(tools.calls), forecast=forecast or {},
                  summary_text=template_summary(call.rows, int(call_capacity), region), fallback_reason=reason)
        s.set_outputs({"draft_text": d.draft_text})
        d.trace_id = trace_id_of(s)
    return d


# --- the approval row ----------------------------------------------------------------------------------------------

APPROVAL_COLUMNS = ("approval_id", "approved_at", "approved_sgt_date", "target_date", "region", "call_capacity",
                    "capacity_basis", "calls_allocated", "source", "fallback_reason", "request_text", "draft_text",
                    "plan_json", "tool_calls_json", "llm_model", "mlflow_trace_id", "forecast_run_id",
                    "forecast_scored_at", "approved_by", "app_commit", "status")


def approval_sql(catalog="coolcheck"):
    """One MERGE per Approve, matched on approval_id, so a second press writes nothing. The time is the warehouse's."""
    if not re.fullmatch(r"\w+", catalog):
        raise ValueError(f"bad catalog name: {catalog!r}")
    values = ", ".join("current_timestamp()" if c == "approved_at"
                       else "to_date(convert_timezone('Asia/Singapore', current_timestamp()))" if c == "approved_sgt_date"
                       else f":{c}" for c in APPROVAL_COLUMNS)
    return (f"MERGE INTO {catalog}.gold.pending_approval AS t USING (SELECT :approval_id AS approval_id) AS s "
            f"ON t.approval_id = s.approval_id WHEN NOT MATCHED THEN INSERT ({', '.join(APPROVAL_COLUMNS)}) "
            f"VALUES ({values})")


def approval_params(d, approved_by, app_commit=None):
    """The MERGE's typed parameters for a draft. Refuses without an approver (the Apps sign-in header)."""
    if not (approved_by or "").strip():
        raise ValueError("no approver: approval needs the Databricks Apps sign-in (X-Forwarded-User)")
    plan = [{k: r[k] for k in ("area_order", "planning_area", "tier", "calls_allocated", "calls_left", "blocks")}
            for r in d.rows if r["calls_allocated"] > 0]
    return {"approval_id": (d.approval_id, "STRING"), "target_date": (str(d.target_date), "DATE"),
            "region": (d.region, "STRING"), "call_capacity": (d.call_capacity, "INT"),
            "capacity_basis": (d.capacity_basis, "STRING"), "calls_allocated": (d.calls_allocated, "INT"),
            "source": (d.source, "STRING"), "fallback_reason": (d.fallback_reason, "STRING"),
            "request_text": (d.request_text, "STRING"), "draft_text": (d.draft_text, "STRING"),
            "plan_json": (json.dumps(plan), "STRING"),
            "tool_calls_json": (json.dumps([c.summary() for c in d.tool_calls], default=str), "STRING"),
            "llm_model": (d.llm_model, "STRING"), "mlflow_trace_id": (d.trace_id, "STRING"),
            "forecast_run_id": (d.forecast.get("run_id"), "STRING"),
            "forecast_scored_at": (d.forecast.get("scored_at"), "TIMESTAMP"),
            "approved_by": (approved_by.strip(), "STRING"), "app_commit": (app_commit, "STRING"),
            "status": (STATUS, "STRING")}


def approve(runner, d, approved_by, catalog="coolcheck", app_commit=None):
    """Write the approval row (or nothing, if this draft was approved already); returns the stored row."""
    runner.query(approval_sql(catalog), approval_params(d, approved_by, app_commit))
    rows = runner.query(f"SELECT approval_id, date_format(from_utc_timestamp(approved_at, 'Asia/Singapore'), "
                        f"'d MMM yyyy, HH:mm:ss') AS approved_sgt, status FROM {catalog}.gold.pending_approval "
                        f"WHERE approval_id = :id", {"id": (d.approval_id, "STRING")})
    if len(rows) != 1:
        raise ToolError(f"approval read-back found {len(rows)} rows for {d.approval_id}")
    return rows[0]
