"""The agent loop (Guide D13, M6; docs/design/agent_app.md): one function, draft_plan, called by the App and by window D's
evaluation scenarios.

Request text in; out a coolcheck.plan.Draft: the draft text, every tool call with the model's arguments, the SQL
arguments and the rows (a call refused before SQL with its error), the checks and the MLflow trace ID. The model is Llama 3.3 70B through the Unity Gateway
chat-completions route (system.ai.meta-llama-3-3-70b-instruct; docs/checks/free_edition_tool_calling.md, confirmed on
the trial 24 Oct). The three Unity Catalog functions are its tools, described by their own comments.

Rules, enforced in code: the allocation stays in get_priority_areas; the model only pulls values out of the request
(volunteers, calls per volunteer, calls, region, a block), a value counts only if its number is in the request, and the
arithmetic is in coolcheck.plan.capacity_from; the date comes from the App; every number in the model's summary must be
found in a tool result the model saw or an input, so the summary asks for digits, not number words (the check then works
on Malay, Tamil and Chinese text too); never P(High) or the score; no tier for a block; no claim that anything was sent
or approved; no medical advice beyond the tier actions. The plan section and the notices are written by code. If the
model does not call get_priority_areas, the code runs it with the form's values and keeps the model's reply if it
passes the checks. On any failure (model error, timeout, round or tool cap, a failed check) the summary is the per-tier
template (decision 4) and fallback_reason says why. Python 3.11 compatible.
"""
import datetime as dt
import json
import re
import time

from coolcheck import agent_tools as T
from coolcheck import plan as P

MODEL = "system.ai.meta-llama-3-3-70b-instruct"
GATEWAY_PATH = "/ai-gateway/mlflow/v1/chat/completions"
MAX_INT = 100000

SYSTEM = """You draft tomorrow's heat outreach plan for an Active Ageing Centre coordinator in Singapore.
Use the tools. Always call get_priority_areas once, with only the values the request states (volunteers, calls per
volunteer, a number of calls, a region), a stated 0 included. Leave out every value the request does not state; the app
then uses the form's values. Never compute a number of calls yourself; the app does the arithmetic. If the
request names an HDB block and asks about refuges or a new refuge, call find_refuges or what_if_add_refuge with that block.
For a what-if, copy the gain from the tool result's gain (dwelling_units_newly_within_400m); never compute it.
If the block comes from the plan (such as tomorrow's top-priority block), call get_priority_areas first, then look up a
block it returned, with its blk_no and street as written.
Then write a short summary for the coordinator, at most 120 words, plain text:
- Copy every number exactly from the tool results, written as digits, never as words. Use each block's
  refuge_distance as written and say distances are straight lines.
- Area risk tiers are Low, Medium, High. Heat levels are Low, Moderate, High. Do not mix them. The vulnerability third
  (upper, middle, lower) is separate from the tier; never call a tier a vulnerability rank.
- Tiers and heat belong to planning areas. Blocks rank vulnerability; never give a block a tier or a heat level.
- Heat is forecast per planning area, not per block. A question about a block's heat is in scope: call
  get_priority_areas and give the heat level of its planning area in a sentence about the area, not the block. Never
  say heat levels are not available.
- Never mention probabilities, percent chances or scores.
- If the tool result has no_high_tier_sentence, include it as written. Name every area in not_rated_high_heat: it has
  High heat but is Not rated, so it has no blocks or calls.
- If calls_left_over is above 0, say how many calls are left over.
- This is a draft for a person to approve. Never say anything was sent, and send nothing.
- No medical advice beyond the tier actions in the tool results.
- If the request asks for something outside this (sending messages, medical advice, other data), say you can only draft
  the plan."""

ADD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
       "eleven": 11, "twelve": 12, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}
TIMES = {"dozen": 12, "hundred": 100, "thousand": 1000}
NUMBER_WORDS = re.compile(r"\b(" + "|".join([*ADD, *TIMES]) + r")\b", re.I)
TIER = r"(?:low|medium|high)[- ](?:tier|risk)"
BANNED = [("P(High), probability or score", re.compile(r"p\s*\(\s*high\s*\)|probabilit|\bscore|percent chance|% chance", re.I)),
          # tiers belong to areas (24 Oct, live: "a High-tier block"): "High-tier block", "Blk 208A ... is High tier",
          # "the block's tier"; "Blk 208A is in the High-tier area" passes
          ("a tier given to a block", re.compile(
              rf"\b{TIER}\s+(?:hdb\s+)?(?:blocks?|blks?)\b"
              rf"|\b(?:blk|block)\s+\d+[a-z]?(?:\s+[a-z0-9]+){{0,5}}\s+(?:is|are)\s+(?:a\s+|in\s+the\s+)?{TIER}\b"
              r"(?![- ](?:planning\s+)?areas?)"
              r"|\b(?:blocks?|blks?)(?:['’]s?)?\s+tiers?\b", re.I)),
          # D01 on 24 Oct, twice: "a refuge about 0 m away" for a refuge the tool result gave as "at the block" (0.0 m)
          ("a distance of 0 m (the tool says at the block)",
           re.compile(r"(?<![\d.,])0(?:\.0+)?\s*(?:m|metres?|meters?)\b", re.I))]
# A claim that something was sent or approved: a past or perfect verb group ("has been sent", "were notified", "I've
# texted", "I sent", "has been approved"). Judged per clause (25 Oct, on 4cb9c1e: "No messages were sent" failed, "I have
# sent the reminders" passed): a negation excuses only the next claim in its own clause, and only from the last finite
# verb on ("No messages were sent" and "This draft has not been sent" pass; "Nothing has been sent yet, but the SMS to
# Bedok was sent" fails), and a condition excuses only the claim inside it ("Nothing will be sent until the plan has been
# approved"). "I called get_priority_areas" is a tool call, not a claim
_SENT = (r"(?:sent|texted|messaged|e-?mailed|notified|dispatched|delivered|contacted|phoned|informed|alerted|forwarded|"
         r"broadcast|approved|called(?!\s+(?:get_priority_areas|find_refuges|what_if_add_refuge)\b))")
_ADV = r"(?:\s+(?:not|never|already|just|now|also|yet|all|successfully))*"
SEND_CLAIM = re.compile(rf"\b(?:has|have|had|was|were|got|been)(?:n['’]t)?{_ADV}\s+(?:been{_ADV}\s+)?{_SENT}\b"
                        rf"|['’](?:ve|d){_ADV}\s+(?:been{_ADV}\s+)?{_SENT}\b|['’]s{_ADV}\s+been\s+{_SENT}\b"
                        rf"|\b(?:i|we){_ADV}\s+{_SENT}\b|\b(?:is|are)\s+(?:now|already)\s+approved\b", re.I)
NEGATION = re.compile(r"\b(?:no|not|nothing|none|nobody|never|neither|nor|without|cannot|unable)\b|n['’]t\b", re.I)
FINITE = re.compile(r"\b(?:am|is|are|was|were|has|have|had|do|does|did|will|would|can|could|shall|should|may|might|must)\b"
                    r"|['’](?:re|ve|ll|d)\b", re.I)  # not 's, mostly a possessive: "None of Toa Payoh's seniors have been"
CONDITION = re.compile(r"\b(?:if|unless|until|till|once|after|before|when|whenever|whether)\b[^,]*$", re.I)
SEND_CLAUSES = re.compile(r"(?<=[.!?;:])\s+|\n|,?\s*\b(?:but|however|although|though|whereas)\b", re.I)


def send_claims(text):
    """The claims in text that something was sent or approved (see SEND_CLAIM)."""
    out = []
    for clause in SEND_CLAUSES.split(text or ""):
        start = 0
        for m in SEND_CLAIM.finditer(clause):
            before = clause[start:m.start()]
            verbs = list(FINITE.finditer(before))
            scope = before[verbs[-1].start():] if verbs else before
            if not (NEGATION.search(m.group(0)) or NEGATION.search(scope) or CONDITION.search(scope)):
                out.append(m.group(0))
            start = m.end()
    return out


# Medical advice fails, declining it does not (G06 on 24 Oct, run 2: "I'm not able to provide medical advice ... consult a
# medical professional" was thrown away 3 times): a medicine or a dose fails anywhere; other medical words, the heat
# illnesses among them, fail only in a clause that neither declines to give advice nor sends the person to medical help;
# discouraging help fails anywhere ("There is no need to see a doctor", "no need for a clinic visit"), and a negation
# alone excuses nothing ("Heat exhaustion does not need treatment"). A decline or a referral excuses only its own clause
# (25 Oct, on 4cb9c1e: "I can't diagnose them, but dizziness and headache are symptoms of heat exhaustion" passed)
MEDICINE = re.compile(r"paracetamol|panadol|acetaminophen|ibuprofen|aspirin|\bnsaids?\b|antihistamine|"
                      r"oral rehydration salts?|electrolyte tablets?|\b\d+(?:\.\d+)?\s*(?:mg|mcg|ml)\b|"
                      r"\b\d+\s*(?:tablets?|pills?|capsules?|doses?|teaspoons?)\b", re.I)
MEDICAL_WORDS = re.compile(r"medic|\bdos(?:e|es|age|ing)\b|diagnos|symptom|prescri|\bpills?\b|tablets?|capsules?|"
                           r"\bdrugs?\b|\btreat(?:ment|ed|s|ing)?\b|\bheat[\s-]*(?:exhaustion|stroke|cramps?)\b|"
                           r"\bheatstroke\b|\bdehydrat", re.I)
_W = r"(?:[\w'’]+\s+)"  # one word and its space
_HELP_VERB = r"(?:consult|see|seek|call|contact|visit|ask|go\s+to|get|dial|phone|ring)\w*"
_HELP = (r"(?:doctors?|gps?|physicians?|medical\s+(?:professionals?|help|attention|care|advice)|healthcare|pharmacists?|"
         r"clinics?|polyclinics?|hospitals?|995|1777|ambulances?|nurses?)")
DECLINES_ADVICE = re.compile(rf"\b(?:can(?:not|['’]t)|can\s+not|unable\s+to|"
                             rf"(?:am|['’]m|is|are)\s+not\s+(?:able|qualified|allowed|permitted)\s+to|"
                             rf"won['’]t|will\s+not|do(?:n['’]t|\s+not)|must\s+not|never)\s+{_W}{{0,2}}?"
                             rf"(?:give|provide|offer|recommend|advise|suggest|prescribe|diagnose|tell|share|answer|"
                             rf"discuss|help\s+with|assist\s+with|comment\s+on)\b|"
                             rf"\bonly\s+draft", re.I)
REFERS = re.compile(rf"\b{_HELP_VERB}\s+{_W}{{0,3}}?{_HELP}\b", re.I)
DISCOURAGES_HELP = re.compile(rf"\b(?:no\s+need|not\s+necessary|(?:is|are|was|were)n['’]t\s+necessary|unnecessary|"
                              rf"needn['’]t|need\s+not|no\s+reason|(?:do|does|did|should|would|will|wo)(?:n['’]t|\s+not)|"
                              rf"never|avoid)\s+(?:to\s+|for\s+)?"
                              rf"(?!(?:hesitate|wait|delay|forget)\b){_W}{{0,2}}?{_HELP_VERB}\s+{_W}{{0,3}}?{_HELP}\b"
                              rf"|\b(?:no\s+need|not\s+necessary|unnecessary|no\s+reason)\s+(?:for|of)\s+{_W}{{0,2}}?{_HELP}\b"
                              rf"|\b(?:do|does|did|will|wo)(?:n['’]t|\s+not)\s+(?:need|require)\s+{_W}{{0,2}}?{_HELP}\b", re.I)
SENTENCES = re.compile(r"(?<=[.!?;:])\s+|\n")
CONTRAST = re.compile(r"(,?\s*\b(?:but|however|although|though|whereas)\b|,\s*\band\b)", re.I)
OPEN_CONDITION = re.compile(r"\s*(?:if|when|whenever|once|unless|until|should|in\s+case)\b[^,]*$", re.I)


def _clauses(sentence):
    """A sentence's clauses for the medical check: split at but, however, although, though, whereas and a comma followed
    by and (", and heat exhaustion is treated with rest" is its own clause; "medicines and doses" and "has heat
    exhaustion and is still conscious" have no comma, so they stay whole), except inside a condition not yet closed by a
    comma ("If a senior has heat exhaustion but is still conscious, call 1777" is one clause); a clause that begins with
    although or though ends at its comma."""
    parts = CONTRAST.split(sentence)
    out, cur = [], parts[0]
    for sep, text in zip(parts[1::2], parts[2::2]):
        if OPEN_CONDITION.match(cur):
            cur += sep + text
            continue
        out.append(cur)
        if "though" in sep.lower() and "," in text:
            head, _, cur = text.partition(",")
            out.append(head)
        else:
            cur = text
    return out + [cur]


def medical_advice(text):
    """The sentences (a medicine, a dose, discouraging help) or clauses (other medical words) of text that give medical
    advice or discourage medical help (see the patterns above)."""
    out = []
    for s in SENTENCES.split(text or ""):
        if MEDICINE.search(s) or DISCOURAGES_HELP.search(s):
            out.append(s)
        else:
            out += [c for c in _clauses(s)
                    if MEDICAL_WORDS.search(c) and not (DECLINES_ADVICE.search(c) or REFERS.search(c))]
    return out


# 995 and 1777 (Singapore's emergency and non-emergency ambulance numbers) need no tool result only in a referral, as
# window D's grader reads them ("call 995", "dial 1777 or 995"); anywhere else they are numbers like any other ("Bedok
# has 995 rental flats", "Blk 1777", "call 995 seniors")
REFERRAL = re.compile(r"\b(?:call|calling|dial|dialling|dialing|phone|ring)\s+(?:on\s+|at\s+)?(?:995|1777)"
                      r"(?:\s*(?:or|and|/|,)\s*(?:995|1777))?(?![\d,.]?\d)"
                      r"(?!\s+(?:more\s+)?(?:seniors?|residents?|people|persons?|households?|homes?|flats?|calls?|"
                      r"blocks?|volunteers?|units?|of)\b)", re.I)


# "No area is in the High tier" when one is (24 Oct, spot-check of the D01 prompt line: C01, C03, R01, B03 said it), also
# scoped ("No rated area in the North-East region is in the High tier"), which in a regional plan must name the region
NO_HIGH_TIER = re.compile(r"\bno\s+(?:rated\s+)?areas?\s+(?:in\s+(?:the\s+)?[\w-]+(?:\s+(?:region|island))?\s+)?(?:is|are)\s+"
                          r"(?:in\s+the\s+)?high\b(?![- ]?\s*heat)"
                          r"|\bno\s+(?:rated\s+)?areas?\s+in\s+the\s+high\s+tier|\bno\s+high[- ]tier\s+areas?", re.I)
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# The 55 planning areas of silver.planning_area_boundary (URA Master Plan 2025), read 24 Oct: a name in the summary must
# be in a tool result the model saw or in the request, since a reply is kept without a get_priority_areas call
PLANNING_AREAS = (
    "ANG MO KIO", "BEDOK", "BISHAN", "BOON LAY", "BUKIT BATOK", "BUKIT MERAH", "BUKIT PANJANG", "BUKIT TIMAH",
    "CENTRAL WATER CATCHMENT", "CHANGI", "CHANGI BAY", "CHOA CHU KANG", "CLEMENTI", "DOWNTOWN CORE", "GEYLANG", "HOUGANG",
    "JURONG EAST", "JURONG WEST", "KALLANG", "LIM CHU KANG", "MANDAI", "MARINA EAST", "MARINA SOUTH", "MARINE PARADE",
    "MUSEUM", "NEWTON", "NORTH-EASTERN ISLANDS", "NOVENA", "ORCHARD", "OUTRAM", "PASIR RIS", "PAYA LEBAR", "PIONEER",
    "PUNGGOL", "QUEENSTOWN", "RIVER VALLEY", "ROCHOR", "SELETAR", "SEMBAWANG", "SENGKANG", "SERANGOON", "SIMPANG",
    "SINGAPORE RIVER", "SOUTHERN ISLANDS", "STRAITS VIEW", "SUNGEI KADUT", "TAMPINES", "TANGLIN", "TENGAH", "TOA PAYOH",
    "TUAS", "WESTERN ISLANDS", "WESTERN WATER CATCHMENT", "WOODLANDS", "YISHUN")


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
    integer = {"type": "integer", "minimum": 0}  # a stated 0 is sent (C01); an unstated one is dropped by _int_arg
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
        tol = 0.5  # written to the unit: 448 for 448.34 m (C03, B03 on 24 Oct); a whole-number source must match exactly
    return any(abs(v - s) <= tol for s in cands)


def _words(s):
    """' WORDS ' in upper case with HDB's street abbreviations (agent_tools.STREET_WORDS), to compare names: 'Bukit
    Batok' and 'BT BATOK ST 21' share ' BT BATOK '."""
    return " " + " ".join(T.STREET_WORDS.get(w, w) for w in re.sub(r"[^A-Z0-9]+", " ", (s or "").upper()).split()) + " "


def unseen_areas(text, seen_text):
    """Planning areas named in text that appear nowhere in seen_text (the tool results the model saw, and the request)."""
    t, seen = _words(text), _words(seen_text)
    return [P.area_name(a) for a in PLANNING_AREAS if _words(a) in t and _words(a) not in seen]


def _names(text, name):
    """Whether text names name as a whole, ignoring case, spaces and hyphens: 'East' is not named in 'North-East'."""
    pat = r"[\s-]*".join(map(re.escape, re.split(r"[\s-]+", name.strip())))
    return re.search(rf"(?<![\w-]){pat}(?![\w-])", text, re.I) is not None


def check_summary(text, sources, unrated_hot=(), rated_high=True, source_text="", region=None, seen_text=None):
    """(passed, checks): digits only (a number word passes only if source_text uses it: draft_plan gives the tool results
    the model saw, e.g. "four languages" in the tier actions, and the request, e.g. "within 400 m of one?"), every
    number grounded (995 and 1777 in a referral need no source), no banned content, no "no area is in the High tier"
    when one is or, in a plan for a region (its display name), without naming it, and, given seen_text, no planning area
    the model never saw. Records whether Not-rated High heat is named when no rated area is High (the code notice is
    shown either way)."""
    used = {w.lower() for w in NUMBER_WORDS.findall(source_text or "")}
    checks = {"ungrounded_numbers": [], "number_words": [w for w in NUMBER_WORDS.findall(text) if w.lower() not in used],
              "banned": []}
    unreferred = REFERRAL.sub(lambda m: re.sub(r"\d", " ", m.group(0)), text)
    for m in re.finditer(r"(\d+(?:[.,]\d+)*)(\s*%)?", unreferred):
        if not grounded(m.group(1), sources, percent=bool(m.group(2))):
            checks["ungrounded_numbers"].append(m.group(0).strip())
    checks["banned"] = [name for name, rx in BANNED if rx.search(text)]
    if send_claims(text):
        checks["banned"].append("claims something was sent")
    if medical_advice(text):
        checks["banned"].append("medical advice")
    for sentence in (s for s in re.split(r"(?<=[.!?;])\s+|\n", text) if NO_HIGH_TIER.search(s)):
        if rated_high:
            checks["banned"].append("says no area is in the High tier, but one is")
        elif region and not _names(sentence, region):  # the dashboard shows the whole island (24 Oct: Toa Payoh is High)
            checks["banned"].append(f"says no area is in the High tier without naming the region ({region})")
        break
    if seen_text is not None:
        checks["unseen_areas"] = unseen_areas(text, seen_text)
    if unrated_hot and not rated_high:
        checks["names_unrated_high_heat"] = all(a.lower() in text.lower() for a in unrated_hot)
    ok = (not (checks["ungrounded_numbers"] or checks["number_words"] or checks["banned"] or checks.get("unseen_areas"))
          and bool(text.strip()))
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


def _unrated_hot(rows):
    """Areas with High heat that are Not rated (no confirmed HDB blocks, so no blocks or calls)."""
    return [P.area_name(r["planning_area"]) for r in rows
            if r["heat_level"] == "High" and r["tier"] in ("Not rated", "No forecast")]


def request_numbers(text):
    """The numbers a request states: digits in any script, and the number words the check knows, alone or combined
    ("two hundred and fifty", "twenty-five", "a dozen")."""
    out = {v for v in (_num(m) for m in NUMBER.findall(text or "")) if v is not None}
    run, cur, prev = 0, None, ""
    for w in re.findall(r"[a-z]+", (text or "").lower()) + [""]:
        if w in ADD:
            cur = (cur or 0) + ADD[w]
        elif w in TIMES:
            cur = (cur or 1) * TIMES[w]
            if w == "thousand":
                run, cur = run + cur, 0
        elif not (w == "and" and prev in TIMES and cur is not None):  # "two hundred and fifty" is one number
            if cur is not None:
                out.add(float(run + cur))
            run, cur = 0, None
        prev = w
    return out


def _int_arg(args, name, stated):
    """A whole number from the model's arguments, or None for the form's value: None when absent, and also when the
    number is not in the request (stated: request_numbers), since the model was seen filling in numbers the request never
    gave (24 Oct, window D's evaluation: 0 for unstated values in L01 to L03; 8 x 20 = 160 calls in B03; 8 and 312, the
    prompt's example digits, in G04). A stated 0 counts: "0 volunteers" gives 0 calls (C01)."""
    v = args.get(name)
    if v is None or v == "":
        return None
    try:
        v = int(v)  # ValueError for a malformed value; reported to the model
    except TypeError:  # a list or an object
        raise ValueError(f"{name} must be a whole number") from None
    if not 0 <= v <= MAX_INT:
        raise ValueError(f"{name} must be between 0 and {MAX_INT}")
    return v if v in stated else None


REGION_KEYS = {re.sub(r"[^A-Z]", "", r): r for r in P.REGIONS}  # compared as get_priority_areas does: NORTHEAST


def _region_arg(args, form_region):
    """The region for get_priority_areas: the model's when it sends one (ALL for the whole island), the form's when it
    sends none, never an earlier call's (24 Oct, R01: three retries with ALL ran as the first call's SOUTH). An unknown
    region goes back to the model as an error naming the five."""
    raw = args.get("region")
    if raw is None or not str(raw).strip():
        return form_region
    key = re.sub(r"REGIONS?$", "", re.sub(r"[^A-Z]", "", str(raw).upper()))
    if key in ("ALL", "WHOLEISLAND"):
        return None
    if key not in REGION_KEYS:
        raise ValueError(f"unknown region {raw!r}: use one of {', '.join(P.REGIONS)}, or ALL for the whole island")
    return REGION_KEYS[key]


# --- notes on the draft, written by code (a prompt line got D01 right 3 times in 4) ------------------------------------

NOT_A_REGION = re.compile(r"\b(south(?:[- ]?(?:east|west))?|north[- ]?west)\s+regions?\b", re.I)
ARG_WORDS = {"volunteers": "{} volunteers", "calls_per_volunteer": "{} calls per volunteer",
             "call_capacity": "a capacity of {} calls"}


def _region_notes(request, sent, region):
    """'South is not one of the five regions; this plan covers the whole island.' for a region the model sent that is not
    one of the five, or one the request names ("the South region"; R01 on 24 Oct: the model sent ALL and said nothing).
    A code of two capitals or fewer that the model sent stays as written ("SE is not one of the five regions")."""
    found = {}
    for raw in [m.group(1) for m in NOT_A_REGION.finditer(request or "")] + list(sent):
        words = re.sub(r"[\s-]*regions?\s*$", "", str(raw).strip(), flags=re.I).split()
        name = " ".join(w if w.isupper() and len(w) <= 2 else P.area_name(w) for w in words)
        found.setdefault(re.sub(r"[^A-Z]", "", name.upper()), name)
    where = f"the {P.region_name(region)} region" if region else "the whole island"
    return [f"{n} is not one of the five regions; this plan covers {where}." for n in found.values() if n]


def _ignored_notes(ignored):
    """The model's values that are not in the request, so were not used (checks.ignored_arguments)."""
    items = list(dict.fromkeys(ARG_WORDS[k].format(P._n(v)) for d in ignored for k, v in d.items()))
    return [f"From the model but not in the request, so not used: {P._join(items)}."] if items else []


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
        state = {"gpa": None, "cap": None, "basis": None, "region": form_region, "form_region": form_region,
                 "stated": request_numbers(masked), "ignored": [], "unknown_regions": []}
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
                    if n_calls > max_tool_calls:  # recorded, not run; the draft falls back to the template below
                        name, args, _ = _parse(c)
                        _refuse(tools, name, args, f"not run: more than {max_tool_calls} tool calls", target_date)
                        continue
                    result = _run_tool(c, tools, target_date, default_capacity, calls_per_volunteer, state)
                    messages.append({"role": "tool", "tool_call_id": c.get("id"), "content": json.dumps(result, default=str)})
                if n_calls > max_tool_calls:
                    raise RuntimeError(f"more than {max_tool_calls} tool calls")
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
        # the tool results the model saw: its summary may take numbers and names from these only (a call that failed or
        # was refused before SQL gave it an error, no rows)
        seen = [c for c in tools.calls if not c.error]
        by_model = state["gpa"] is not None
        if not by_model:  # no get_priority_areas call from the model (or it failed): run in code with the form's values
            call = tools.get_priority_areas(target_date, form_cap, form_region)
            if call.error:
                raise P.ToolError(f"get_priority_areas failed: {call.error}")
            state.update(gpa=call, cap=form_cap, basis=form_basis, region=form_region)
        rows = state["gpa"].rows
        if not reason:  # the model's reply is kept if it passes the checks, whoever called get_priority_areas
            sources = source_numbers([c.rows for c in seen],
                                     [P.whatif_gain(c.rows) for c in seen if c.name == "what_if_add_refuge"],
                                     target_date.isoformat(), target_date.strftime("%d %m %Y"),
                                     state["cap"], state["basis"], default_capacity, calls_per_volunteer, masked,
                                     (forecast or {}).get("scored_at_sgt"), 400)
            # what the model saw: the tool results and the request. A number word passes if either uses it (run 3, H06:
            # the request's "within 400 m of one?" made the answer "... within 400 m of one." fall back to the template)
            seen_text = json.dumps([c.rows for c in seen], default=str, ensure_ascii=False) + "\n" + masked
            ok, checks = check_summary(summary, sources, _unrated_hot(rows), any(r["tier"] == "High" for r in rows),
                                       seen_text, P.region_name(state["region"]) if state["region"] else None,
                                       seen_text=seen_text)
            if not ok:
                reason = "the model's summary failed the checks: " + ("; ".join(
                    f"{k}: {v}" for k, v in checks.items() if v and k != "names_unrated_high_heat") or "empty")
        if reason:
            summary = None
        checks = dict(checks, get_priority_areas="called by the model" if by_model else
                      "run in code with the form's values (the model did not call it)",
                      ignored_arguments=state["ignored"], rounds=rounds, masked=n_masked,
                      elapsed_s=round(time.monotonic() - t0, 1))
        notes = _region_notes(masked, state["unknown_regions"], state["region"]) + _ignored_notes(state["ignored"])
        d = P.Draft(target_date=target_date, region=state["region"], call_capacity=state["cap"], capacity_basis=state["basis"],
                    rows=rows, tool_calls=list(tools.calls), forecast=forecast or {},
                    summary_text=summary or P.template_summary(rows, state["cap"], state["region"]),
                    source=P.AGENT if summary else P.TEMPLATE, fallback_reason=reason, request_text=masked or None,
                    llm_model=model if summary else None, checks=checks, notes=notes)
        root.set_outputs({"draft_text": d.draft_text, "source": d.source, "fallback_reason": reason, "checks": d.checks})
        d.trace_id = P.trace_id_of(root)
    return d


def _parse(c):
    """(name, arguments, error): the tool the model called and its arguments as an object, or, when they are not one,
    the raw arguments and why."""
    fn = c.get("function") or {}
    name, raw = fn.get("name"), fn.get("arguments") or "{}"
    try:
        args = json.loads(raw) if isinstance(raw, str) else dict(raw)
        if not isinstance(args, dict):
            raise ValueError("arguments are not an object")
    except Exception as e:
        return name, raw, f"malformed arguments: {e}"
    return name, args, None


def _refuse(tools, name, args, error, target_date):
    """A call refused before any SQL ran: recorded with the model's arguments in its own TOOL span (Tools.refuse), with
    the date the App fixes for get_priority_areas; the error goes back to the model."""
    fixed = {"target_date": str(target_date)} if name == "get_priority_areas" else None
    return {"error": tools.refuse(name, args, error, fixed).error}


def _run_tool(c, tools, target_date, default_capacity, calls_per_volunteer, state):
    """Run one tool call; the result (or the error) goes back to the model. A call refused before any SQL runs
    (malformed or unknown arguments, an unknown region, a block lookup without a block number or a street, an unknown
    tool) is recorded too, so the draft, the App and the trace show every call the model made, in its order (since
    e1291d9 the refused first call of B03 was missing: run 2 failed B03 on the order find_refuges, get_priority_areas,
    find_refuges)."""
    name, args, error = _parse(c)
    if error:
        return _refuse(tools, name, args, error, target_date)
    if name == "get_priority_areas":
        unknown = set(args) - {"volunteers", "calls_per_volunteer", "call_capacity", "region"}
        if unknown:
            return _refuse(tools, name, args, f"unknown arguments: {sorted(unknown)}", target_date)
        try:
            vals = {k: _int_arg(args, k, state["stated"]) for k in ("volunteers", "calls_per_volunteer", "call_capacity")}
        except ValueError as e:
            return _refuse(tools, name, args, str(e), target_date)
        try:
            region = _region_arg(args, state["form_region"])
        except ValueError as e:  # the draft gets a note
            state["unknown_regions"].append(args["region"])
            return _refuse(tools, name, args, str(e), target_date)
        ignored = {k: args[k] for k, v in vals.items() if v is None and args.get(k) not in (None, "")}
        if ignored:  # numbers not in the request: the form's values are used, and the trace shows what was dropped
            state["ignored"].append(ignored)
        cap, basis = P.capacity_from(default_capacity, calls_per_volunteer, vals["volunteers"],
                                     vals["calls_per_volunteer"], vals["call_capacity"])
        call = tools.get_priority_areas(target_date, cap, region, llm_arguments=args)
        if call.error:
            return {"error": call.error}
        state.update(gpa=call, cap=cap, basis=basis, region=region)
        rows = call.rows
        high = [P.area_name(r["planning_area"]) for r in rows if r["tier"] == "High"]
        reply = {"call_capacity": cap, "capacity_basis": basis, "region": region or "whole island",
                 "calls_left_over": rows[-1]["calls_left"] if rows else None, "high_tier_areas": high}
        if rows and not high:  # the sentence the template writes, scoped to the region, for the model to copy
            reply["no_high_tier_sentence"] = P.no_tier_sentence("High", region)
        return dict(reply, not_rated_high_heat=_unrated_hot(rows), areas=_compact(rows))
    if name in ("find_refuges", "what_if_add_refuge"):
        if not (args.get("blk_no") and args.get("street")):
            return _refuse(tools, name, args, "blk_no and street are required", target_date)
        if not re.search(r"\d", str(args["blk_no"])):  # B03, 24 Oct: "to be determined by get_priority_areas"
            return _refuse(tools, name, args, f"blk_no {args['blk_no']!r} is not a block number (it has no digit), so "
                                              f"nothing was looked up; if the block comes from the plan, call "
                                              f"get_priority_areas first", target_date)
        call = getattr(tools, name)(args["blk_no"], args["street"], llm_arguments=args)
        if call.error:
            return {"error": call.error}
        if not call.rows:
            return {"rows": "no rows: block not found or not confirmed"}
        if name == "what_if_add_refuge":  # the gain, computed here, as calls_left_over is
            return {"gain": P.whatif_gain(call.rows), "rows": call.rows}
        return {"rows": call.rows}
    return _refuse(tools, name, args, f"unknown tool {name!r}", target_date)
