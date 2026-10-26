"""Tier explanations (docs/design/tier_explanations.md): one plain-English sentence per rated planning area saying why it
has its tier on a target date, for the briefing dashboard's two area tables (column "Why, in a sentence").

Facts by code (facts): the area's name as the dashboard shows it, the tier, the forecast heat level, the vulnerability
third, the components the area's reason names with their values as a coordinator reads them (counts as counts, shares as
whole percentages, refuges as a count for the area's residents aged 65+) and their ranks among the rated areas with a
usable value (the percentile's own set and direction, risk.neutral_reason, from the same values), and the peak WBGT
observed at the area's station on the day before the target date with its NEA category, when gold.observed_heat_daily
has a usable row. That peak is an observation, never presented as what the model used: its wbgt_peak_d1 is built by the
same rule, but the nightly job keeps its features in memory only, so the stored observation may hold readings that came
later. NEVER_READ (P(High), p_moderate, p_low, V, its rank, tier_rank, model_version, run_id) is in no SQL here (tested).
Words by the model: Llama 3.3 70B through Databricks AI Functions (ai_query on the SQL warehouse) at temperature 0.
Checked by code (check): the tier word first; the heat level and the third said, and right; each measure's value given;
every number in the facts (the App's coolcheck.agent.check_summary), and each date, temperature and rank its own fact;
at most 35 words in one sentence; the banned words; and window D's four rules: each measure's text as given, each
bracket its own fact, nothing but the facts and FRAME words, the observation in its own clause after the first
semicolon. A sentence that fails, or a failed call, is replaced by template(), written by code from the same facts in
the dashboard's wording; both are kept, with who wrote the one shown and the checks it failed. It explains the tier from
its inputs, not the model's own reasoning.
"""
import json
import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from coolcheck import agent as A
from coolcheck import plan as P
from coolcheck import risk as R

MODEL = "system.ai.meta-llama-3-3-70b-instruct"  # the App's model; ai_query on the warehouse takes the same name (26 Oct)
TEMPERATURE = 0.0  # the lowest the call allows
MAX_TOKENS = 120
MAX_WORDS = 35
AI, TEMPLATE = "AI, checked", "Template"
TABLE = "area_tier_explanation"
NEVER_READ = ("p_high", "p_moderate", "p_low", "v", "v_rank", "tier_rank", "model_version", "run_id", "score",
              "heat_forecast")
# component: its column in gold.area_vulnerability, and the rank's word (rank 1 is the most vulnerable)
MEASURES = {
    "aged_75_plus": ("aged_75_plus", "most"),
    "share_75_plus": ("share_75_plus", "highest"),
    "rental_1_2_room": ("rental_1_2_room", "most"),
    "electricity_hot_rise": ("electricity_hot_ratio", "smallest"),
    "refuge_beyond_400m": ("refuge_beyond_400m", "highest"),
    "refuges_per_1000_65": ("refuges_per_1000_65_plus", "fewest per resident"),
    "park_beyond_400m": ("park_beyond_400m", "highest"),
}

# The examples' facts are made up; a copied example date, temperature or rank fails the check
PROMPT = """You write one sentence that tells a community care coordinator in Singapore why a planning area has its \
heat-risk tier for the day, using only the facts given.

Rules:
- One natural sentence in plain English, at most 35 words.
- Begin with the tier, exactly "<<tier>>:", then say the forecast heat level and the vulnerability third in words: the \
tier comes from these two.
- Then give each measure in vulnerable_because in full, with all its numbers and words as written; never shorten one. \
Add a measure's rank in brackets after it only while the sentence stays within 35 words.
- If there is no vulnerable_because, give vulnerability_note and the observed peak instead.
- The observed peak is what the area's WBGT station observed on the date given. Give it only if it fits, as an \
observation; never say or suggest that it explains the tier or the forecast.
- Copy every number exactly from the facts, in digits; write no other number and no number in words.
- Tiers are Low, Medium or High; heat levels are Low, Moderate or High; do not mix them.
- No advice. Do not mention probability, chance, likelihood, a score or a model, or today, tomorrow or yesterday.
- Say nothing about the residents beyond the facts: not alone, poor, low-income or without air-con.

Three examples, with made-up facts:
Facts: {"area": "Example A", "tier": "Medium", "forecast_heat_level": "Moderate", "vulnerability_third": "upper", \
"vulnerable_because": [{"measure": "1,234 1-2 room rental flats", "rank": "5th most of 32 rated areas"}, {"measure": \
"a 12% share of residents aged 75+", "rank": "8th highest of 31 rated areas measured"}], "observed_heat": {"date": \
"1 Jan", "where": "the area's WBGT station", "peak_wbgt": "30.9 °C", "nea_category": "Low"}}
Sentence: Medium: forecast Moderate heat and the upper third for vulnerability, with 1,234 1-2 room rental flats (5th \
most of 32 rated areas) and a 12% share of residents aged 75+.
Facts: {"area": "Example B", "tier": "Low", "forecast_heat_level": "Low", "vulnerability_third": "lower", \
"vulnerable_because": [{"measure": "7 refuges in the area for 12,345 residents aged 65+", "rank": "9th fewest per \
resident of 30 rated areas measured"}, {"measure": "61% of HDB flats beyond 400 m of a park", "rank": "6th highest of \
29 rated areas measured"}], "observed_heat": {"date": "1 Jan", "where": "the area's WBGT station", "peak_wbgt": \
"29.8 °C", "nea_category": "Low"}}
Sentence: Low: forecast Low heat and the lower third for vulnerability, with 7 refuges in the area for 12,345 residents \
aged 65+ and 61% of HDB flats beyond 400 m of a park.
Facts: {"area": "Example C", "tier": "Low", "forecast_heat_level": "Moderate", "vulnerability_third": "lower", \
"vulnerability_note": "no component above the middle of the rated areas", "observed_heat": {"date": "1 Jan", "where": \
"the area's WBGT station", "peak_wbgt": "31.0 °C", "nea_category": "Moderate"}}
Sentence: Low: forecast Moderate heat and the lower third for vulnerability, with no component above the middle of the \
rated areas; its station observed a peak WBGT of 31.0 °C (Moderate) on 1 Jan.

Now the real facts. Reply with the sentence only.
Facts:
<<facts>>"""

COLUMNS = [
    ("target_date", "DATE", "The date the tier is for (gold.area_heat_risk.target_date)."),
    ("planning_area", "STRING", "Master Plan 2025 planning area, upper case as in gold.area_heat_risk; rated areas only."),
    ("facts", "STRING", "The facts given to the model, as JSON: the area's name as the dashboard shows it, the tier, the "
                        "forecast heat level, the vulnerability third, the components the area's reason names with their "
                        "values and ranks among the rated areas with a usable value, and the peak WBGT observed at the "
                        "area's station on the day before the target date with its NEA category (gold.observed_heat_daily), "
                        "left out without a usable row. No P(High), score, V or rank of V."),
    ("template_sentence", "STRING", "The sentence code writes from the same facts in the dashboard's wording; shown when "
                                    "the model's sentence fails a check."),
    ("ai_sentence", "STRING", "The model's sentence as returned, kept whether or not it passed; null if the call failed."),
    ("explanation", "STRING", "The sentence the dashboard shows: the model's (trimmed) if it passed every check, else "
                              "template_sentence."),
    ("written_by", "STRING", "'AI, checked': the model's sentence passed every check; 'Template': it failed one, or the "
                             "call failed."),
    ("checks_failed", "STRING", "The checks the model's sentence failed, '; '-separated; null when it passed."),
    ("model", "STRING", "The model ai_query called (temperature 0, at most 120 output tokens)."),
    ("generated_at", "TIMESTAMP", "When the row was written (an instant; SGT is UTC+8)."),
]
COMMENT = ("Why each rated planning area has its tier, in one sentence per area and target date "
           "(docs/design/tier_explanations.md): written by Llama 3.3 70B through Databricks AI Functions (ai_query) from "
           "facts code builds, checked by code (the tier, heat and third words; each measure as given; every number in "
           "the facts and each date, temperature, rank and bracket its own; nothing but the facts and joining words; the "
           "observation in its own clause; at most 35 words; banned words), else the template sentence. It explains the "
           "tier from its inputs, not the model's own reasoning. P(High), the score and V are never read. A date's rows "
           "are replaced by scripts/explanations/generate.py.")
TAGS = {"source": "gold.area_heat_risk; gold.area_vulnerability; gold.observed_heat_daily; "
                  "Llama 3.3 70B through Databricks AI Functions (ai_query)",
        "licence": "Singapore Open Data Licence v1.0 (source data); CoolCheck text and Llama 3.3 70B output "
                   "(Llama 3.3 Community License)"}

_NAME = re.compile(r"^\w+$")


def _c(catalog):
    if not _NAME.match(catalog):
        raise ValueError(f"bad catalog name: {catalog!r}")
    return catalog


def _lit(s):
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


# --- facts --------------------------------------------------------------------------------------------------------------

def _pct(x):
    """A share as a whole percentage, half to even, as the dashboard's format_number(100 * x, 0)."""
    return round(100 * x)


def _a(n):
    """The article before a number read aloud: "an 8%", "an 11%", "an 18%", "an 80%" to "an 89%"; else "a"."""
    return "an" if n in (8, 11, 18) or 80 <= n <= 89 or 800 <= n <= 899 else "a"


def ordinal(k):
    return f"{k}{'th' if 10 <= k % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(k % 10, 'th')}"


def components(reason, weights):
    """The components the area's reason names, in its order ([] for risk.NO_REASON)."""
    if not reason or reason == R.NO_REASON:
        return []
    by_phrase = {w["reason_phrase"]: w["component"] for w in weights}
    return [by_phrase[p] for p in reason.split("; ")]


def _inputs(row):
    """A gold.area_vulnerability row as risk.neutral_reason reads an area's inputs."""
    return {"raw": {k: (None if row[col] is None else float(row[col])) for k, (col, _) in MEASURES.items()},
            "du": row["hdb_dwelling_units_confirmed"], "residents": row["residents"], "aged_65_plus": row["aged_65_plus"]}


def ranks(vulnerability, weights):
    """{(area, component): (rank, tied, n)} among the n rated areas with a usable value for the component (the set and
    direction its percentile uses): rank 1 is the most vulnerable, and ties share the best rank."""
    inputs = {r["planning_area"]: _inputs(r) for r in vulnerability}
    out = {}
    for w in weights:
        k, sign = w["component"], -1.0 if w["direction"] == "inverted" else 1.0
        usable = {a: sign * x["raw"][k] for a, x in inputs.items() if R.neutral_reason(x, w) is None}
        for a, o in usable.items():
            out[(a, k)] = (1 + sum(b > o for b in usable.values()), sum(b == o for b in usable.values()) > 1, len(usable))
    return out


def rank_text(rank, tied, n, word, n_rated):
    where = f"of {n} rated areas" + ("" if n == n_rated else " measured")
    if rank == 1 and not tied:
        return f"the {word} {where}"
    return f"{'joint ' if tied else ''}{ordinal(rank)} {word} {where}"


def measure_text(component, row):
    """The component's value for the area as a coordinator reads it."""
    x = row[MEASURES[component][0]]
    if component == "aged_75_plus":
        return f"{int(x):,} residents aged 75+"
    if component == "share_75_plus":
        return f"{_a(_pct(x))} {_pct(x)}% share of residents aged 75+"
    if component == "rental_1_2_room":
        return f"{int(x):,} 1-2 room rental flats"
    if component == "electricity_hot_rise":
        d = _pct(x - 1.0)
        return (f"{_a(abs(d))} {abs(d)}% {'rise' if d >= 0 else 'fall'} in 1-2 room electricity use from "
                f"November-February to April-June")
    if component in ("refuge_beyond_400m", "park_beyond_400m"):
        return f"{_pct(x)}% of HDB flats beyond 400 m of {'a refuge' if component == 'refuge_beyond_400m' else 'a park'}"
    aged = int(row["aged_65_plus"])  # refuges_per_1000_65: the area's refuges, from the rate and its residents aged 65+
    n = x * aged / 1000
    if abs(n - round(n)) > 0.05:
        return f"{x:.2f} refuges per 1,000 residents aged 65+"
    n = round(n)
    return f"{'no' if n == 0 else n} refuge{'' if n == 1 else 's'} in the area for {aged:,} residents aged 65+"


def facts(heat, vulnerability_row, rank_of, n_rated, weights, observed=None):
    """The facts for one rated area: heat is its gold.area_heat_risk row (target_date, planning_area, tier, heat_level,
    third, reason), vulnerability_row its gold.area_vulnerability row, observed its station's gold.observed_heat_daily
    row for the day before the target date (max_wbgt, heat_category) or None."""
    area = heat["planning_area"]
    f = {"area": P.area_name(area), "tier": heat["tier"], "forecast_heat_level": heat["heat_level"],
         "vulnerability_third": heat["third"]}
    measures = []
    for k in components(heat["reason"], weights):
        rank, tied, n = rank_of[(area, k)]
        measures.append({"measure": measure_text(k, vulnerability_row),
                         "rank": rank_text(rank, tied, n, MEASURES[k][1], n_rated)})
    if measures:
        f["vulnerable_because"] = measures
    else:
        f["vulnerability_note"] = R.NO_REASON
    if observed is not None and observed.get("max_wbgt") is not None:
        d = heat["target_date"] - timedelta(days=1)
        peak = Decimal(repr(float(observed["max_wbgt"]))).quantize(Decimal("0.1"), ROUND_HALF_UP)  # as round(x, 1)
        f["observed_heat"] = {"date": f"{d.day} {d:%b}", "where": "the area's WBGT station", "peak_wbgt": f"{peak} °C",
                              "nea_category": observed["heat_category"]}
    return f


def _template(f, with_ranks, with_observed):
    s = f"{f['tier']}: forecast {f['forecast_heat_level']} heat, {f['vulnerability_third']} third for vulnerability, with "
    ms = f.get("vulnerable_because")
    s += " and ".join(m["measure"] + (f" ({m['rank']})" if with_ranks else "") for m in ms) if ms else f["vulnerability_note"]
    o = f.get("observed_heat") if with_observed else None
    if o:
        s += f"; peak WBGT observed at its station on {o['date']}: {o['peak_wbgt']} ({o['nea_category']})"
    return s + "."


def template(f):
    """The sentence code writes from the facts: the dashboard's tier sentence, then the reason's measures with their
    values (or risk.NO_REASON), their ranks, then the observed peak; the first of these that fits in MAX_WORDS words,
    in the order the prompt gives the model: with ranks and the peak, ranks only, values and the peak, values only."""
    for with_ranks, with_observed in ((True, True), (True, False), (False, True), (False, False)):
        s = _template(f, with_ranks, with_observed)
        if len(s.split()) <= MAX_WORDS:
            break
    return s


def request(f):
    return PROMPT.replace("<<tier>>", f["tier"]).replace("<<facts>>", json.dumps(f, ensure_ascii=False, indent=2))


# --- the check ----------------------------------------------------------------------------------------------------------

TIER_WORD = re.compile(r"\b(low|medium|high)[- ]tier\b|\btier\s+(?:is\s+|of\s+)?(low|medium|high)\b", re.I)
HEAT_WORD = re.compile(r"\b(low|moderate|high|medium)[- ]heat\b", re.I)
FORECAST_WORD = re.compile(r"\bforecast(?:s|ed)?\s+(?:heat\s+(?:level\s+)?)?(?:is\s+|of\s+|to\s+be\s+|as\s+)?"
                           r"(low|moderate|high|medium)\b|\b(low|moderate|high|medium)[- ]heat\s+forecast", re.I)
THIRD_WORD = re.compile(r"\b(upper|middle|lower|top|bottom)[- ](?:vulnerability[- ])?third\b", re.I)
THIRDS = {"top": "upper", "bottom": "lower"}
VULNERABILITY_THIRD = re.compile(r"\b(?:upper|middle|lower|top|bottom)[- ](?:vulnerability[- ])?third\b"
                                 r"|\bvulnerability\s+third\b", re.I)
ORDINALS = re.compile(r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|"
                      r"(?:thir|four|fif|six|seven|eigh|nine)teenth|twentieth|thirtieth|half|halves|quarters?|twice|"
                      r"thrice|double|triple)\b", re.I)
# the brief's list with their inflections, then three more: no sentence relative to the day it is read, no model, no advice;
# each fails unless a fact holds a match (the electricity reason's "may indicate less air-con use")
BANNED = [
    ("probability", r"\bprobab\w*"), ("chance", r"\bchances?\b"), ("likelihood", r"\b(?:un)?likel(?:y|ihood)\b"),
    ("alone", r"\balone\b"), ("poor", r"\bpoor(?:er|est|ly)?\b|\bpoverty\b"), ("low-income", r"\blow[- ]?income\b"),
    ("air-con", r"\bair[- ]?con\w*"), ("die", r"\b(?:die|dies|died|dying)\b"), ("death", r"\bdeath\w*|\bdeadly\b|\bfatal\w*"),
    ("guarantee", r"\bguarant\w*"),
    ("today, tomorrow or yesterday", r"\b(?:today|tonight|tomorrow|yesterday)\b"),
    ("the model", r"\bmodel\w*|\bpredict\w*|\balgorithm\w*"),
    ("advice", r"\b(?:should|must|ought\s+to|needs?\s+to|recommend\w*|advis\w*|ensure|make\s+sure|prioriti[sz]\w*|"
               r"check\s+on|reach\s+out)\b"),
]
# the observed peak may not be tied to the forecast or the tier: within one clause (no semicolon), a causal word after
# the forecast or tier and at most six words before the observation ("forecast Moderate heat after a 31.4 °C peak"), or
# after the observation and at most six words before them ("31.4 °C was observed, so the forecast"). "From" and "since"
# are left out: the electricity measure says "from November-February"
_OBS = r"(?:observ\w*|wbgt|°\s*c|peak\w*)"
_FC = r"(?:forecast\w*|tier\w*)"
_CAUSE = (r"(?:because|due\s+to|driven\s+by|drive[sn]?|drove|based\s+on|owing\s+to|given|after|so|hence|therefore|thus|"
          r"lead(?:s|ing)?\s+to|led\s+to|reflect\w*|explain\w*|caus\w*|why|us(?:e|es|ed|ing)|indicat\w*|suggest\w*|"
          r"signal\w*|points?\s+to)")
OBSERVATION_AS_CAUSE = re.compile(rf"\b{_FC}\b[^;]*?\b{_CAUSE}\b(?:[^\w;]+\w+){{0,6}}?[^\w;]+{_OBS}"
                                  rf"|{_OBS}[^;]*?\b{_CAUSE}\b(?:[^\w;]+\w+){{0,6}}?[^\w;]+{_FC}\b", re.I)
QUOTES = "\"'“”‘’"
LABELS = re.compile(r"1-2 room|aged (?:75|65)\+|400 m|per 1,000")  # numbers that name a measure, not its value
# a number can be in the facts and still be the wrong fact (an example's "1 Jan" or "31.0 °C" for an area whose facts
# hold a 1 or a 31): dates, temperatures and ranks are matched to their own fact
MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
DATE = re.compile(rf"\b(\d{{1,2}})\s+({MONTHS})[a-z]*\.?|\b({MONTHS})[a-z]*\.?\s+(\d{{1,2}})\b", re.I)
DEGREES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:°\s*C?|degrees?\b|deg\b)", re.I)
RANK = re.compile(r"\b(?:(\d+)(?:st|nd|rd|th)|the)\s+(most|highest|fewest|smallest)\b(?:\s+per\s+resident)?"
                  r"(?(1)|(?=(?:\s+\w+){0,3}?\s+of\s+\d))", re.I)


def clean(text):
    """The model's sentence as shown: whitespace collapsed, and one pair of surrounding quotes removed."""
    t = " ".join((text or "").split())
    if len(t) > 1 and t[0] in QUOTES and t[-1] in QUOTES:
        t = t[1:-1].strip()
    return t


def sources(f):
    """The numbers of the facts as the App's check reads them (coolcheck.agent.source_numbers), with each whole
    percentage also as its share, so "13%" is grounded the way the App grounds a percentage."""
    text = json.dumps(f, ensure_ascii=False)
    pct = {A._num(m) for m in re.findall(r"(\d+(?:[.,]\d+)*)\s*%", text)}
    return A.source_numbers(f) | {v / 100 for v in pct if v is not None}


def required(f):
    """The numbers that make the sentence the area's own: each measure's value (its numbers but the labels'), or, for an
    area with no measure, the observed peak. A sentence without them could read the same for two areas with different
    facts."""
    texts = [LABELS.sub(" ", m["measure"]) for m in f.get("vulnerable_because", [])]
    if not texts and f.get("observed_heat"):
        texts = [f["observed_heat"]["peak_wbgt"]]
    return [n for t in texts for n in A.NUMBER.findall(t)]


def _rank(m):
    """(rank, word) of a RANK match: "5th most" is (5, "most"), "the most of 32" (1, "most")."""
    return (int(m.group(1) or 1), m.group(2).lower()) if m else None


def _same_day(m, date_text):
    """Whether a DATE match is the facts' date ("25 Oct"), however written ("25 October", "Oct 25")."""
    day, mon = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
    return f"{int(day)} {mon[:3].lower()}" == date_text.lower()


def wrong_facts(t, f):
    """The dates, temperatures and ranks in the sentence that are not their own fact: a date must be the observed day,
    a temperature the observed peak, and a rank the rank of the measure whose value comes last before it."""
    o, out = f.get("observed_heat"), []
    for m in DATE.finditer(t):
        if not o or not _same_day(m, o["date"]):
            out.append(f"date: {m.group(0).strip().rstrip('.')}")
    for m in DEGREES.finditer(t):
        if not o or abs(float(m.group(1)) - float(o["peak_wbgt"].split()[0])) > 1e-9:
            out.append(f"temperature: {m.group(0).strip()}")
    measures = f.get("vulnerable_because", [])
    values = [{A._num(n) for n in A.NUMBER.findall(LABELS.sub(" ", m["measure"]))} for m in measures]
    marks = []  # (position, measure index or None when two measures share the value)
    for m in A.NUMBER.finditer(t):
        if re.match(r"(?:st|nd|rd|th)\b", t[m.end():]) or re.search(r"\bof\s+$", t[:m.start()]):
            continue  # a rank's own number, or a rank's "of 32"
        hits = [i for i, v in enumerate(values) if A._num(m.group(0)) in v]
        if hits:
            marks.append((m.start(), hits[0] if len(hits) == 1 else None))
    for m in RANK.finditer(t):
        before = [i for pos, i in marks if pos < m.start()]
        if not before:
            out.append(f"rank: {m.group(0)} comes before any measure")
        elif before[-1] is not None and _rank(m) != _rank(RANK.search(measures[before[-1]]["rank"])):
            out.append(f"rank: {m.group(0)} is not the rank of {measures[before[-1]]['measure']}")
    return out


# Window D's three rules (its review of 26 Oct, finding 3): the sentence states each fact as given, and nothing more. In
# D's scratch test the checks above let 36 of 54 wrong sentences through: values swapped between measures, labels
# dropped, ranks in other words, claims about residents, reassurance, the peak as a cause, confidence, advice.
# FRAME is D's list of joining words without its tier, heat and third words: beyond_frame takes the area's own out
# where they belong (the tier first, "<level> heat", "<third> third", "(<category>)"), so any other use of one, as in
# "High vulnerability" (D's prototype let it through), is left over and fails.
FRAME = frozenset("and the third for vulnerability with its station observed a peak wbgt of on forecast heat in at".split())
BRACKET = re.compile(r"\(([^()]*)\)")


def _peak(o):
    """The observed peak as a pattern: its value, with or without a space before °C."""
    return re.escape(o["peak_wbgt"].split()[0]) + r"\s*°\s*C\b"


def not_verbatim(t, f):
    """Rule (a): each measure's text (or the note, for an area with no measure) is in the sentence exactly as given."""
    want = [m["measure"] for m in f.get("vulnerable_because", [])] or [f.get("vulnerability_note") or ""]
    return [p for p in want if p not in t]


def wrong_brackets(t, f):
    """Rule (b): a bracket comes right after a measure and holds that measure's rank as given, or right after the
    observed peak and holds its NEA category; a bracket anywhere else fails."""
    measures, o, out = f.get("vulnerable_because", []), f.get("observed_heat"), []
    own = [(k, k + len(x["measure"])) for x in measures for k in range(len(t)) if t.startswith(x["measure"], k)]
    for m in BRACKET.finditer(t):
        if any(a <= m.start() and m.end() <= b for a, b in own):
            continue  # a bracket inside a measure's own text
        before, inside = t[:m.start()].rstrip(), m.group(1).strip()
        owner = next((x for x in measures if before.endswith(x["measure"])), None)
        if owner is not None:
            if inside != owner["rank"]:
                out.append(f"bracket: ({inside}) is not the rank of {owner['measure']}")
        elif o and re.search(_peak(o) + "$", before):
            if inside != o["nea_category"]:
                out.append(f"bracket: ({inside}) after the peak is not its category, {o['nea_category']}")
        else:
            out.append(f"bracket: ({inside}) is not right after a measure or the peak")
    return out


def beyond_frame(t, f):
    """Rule (c): what is left of the sentence once the facts' own phrases are taken out (the measures, the ranks, the
    note, the observed peak, its date and its category in brackets; the tier as the first word, the heat level before
    "heat", the observed category before "heat", the third before "third"): every word not in FRAME, and every number."""
    s = " " + t + " "
    phrases = [m[k] for m in f.get("vulnerable_because", []) for k in ("measure", "rank")]
    phrases += [f["vulnerability_note"]] if f.get("vulnerability_note") else []
    for p in sorted(phrases, key=len, reverse=True):
        s = s.replace(p, " ")
    o = f.get("observed_heat")
    if o:
        s = re.sub(_peak(o), " ", s)
        s = DATE.sub(lambda m: " " if _same_day(m, o["date"]) else m.group(0), s)
        s = re.sub(rf"\(\s*{re.escape(o['nea_category'])}\s*\)", " ", s)
    s = re.sub(rf"^\W*{re.escape(f['tier'])}\b", " ", s, flags=re.I)
    heat_words = "|".join(map(re.escape, {f["forecast_heat_level"], *([o["nea_category"]] if o else [])}))
    s = re.sub(rf"\b(?:{heat_words})(?=[- ]heat\b)", " ", s, flags=re.I)
    s = re.sub(rf"\b{re.escape(f['vulnerability_third'])}(?=[- ](?:vulnerability[- ])?third\b)", " ", s, flags=re.I)
    return [w for w in re.findall(r"[A-Za-z]+|\d+(?:[.,]\d+)*", s) if w.lower() not in FRAME]


# Rule (d), window D's re-review 2: a sentence of facts and frame words alone could still swap the forecast and the
# observation ("forecast Moderate heat on 25 Oct", "its station observed Moderate heat"), so each keeps to its clause
OBSERVATION_WORDS = re.compile(r"\b(?:observ\w*|peak\w*|wbgt|station\w*)\b", re.I)
FORECAST_OR_LEVEL = re.compile(r"\b(?:forecast\w*|low|moderate|high)\b", re.I)


def observation_out_of_place(t, f):
    """Rule (d): the observation keeps to its own clause. The observed peak, its date, its category in brackets and the
    words observed, peak, WBGT and station appear only after the sentence's first semicolon (and only when the facts
    hold an observation); that clause holds no forecast word and no heat-level word, but the category in the bracket
    right after the peak."""
    head, _, tail = t.partition(";")
    o, out = f.get("observed_heat"), []
    seen = [m.group(0) for m in OBSERVATION_WORDS.finditer(head)]
    if o:
        seen += [m.group(0) for m in re.finditer(_peak(o), head)]
        seen += [m.group(0).strip().rstrip(".") for m in DATE.finditer(head) if _same_day(m, o["date"])]
        seen += [m.group(0) for m in re.finditer(rf"\(\s*{re.escape(o['nea_category'])}\s*\)", head)]
        tail = re.sub(_peak(o) + rf"\s*\(\s*{re.escape(o['nea_category'])}\s*\)", " ", tail)
    elif OBSERVATION_WORDS.search(tail):
        out.append("observation: none in the facts, but the sentence gives one")
    if seen:
        out.append("observation before the first semicolon: " + ", ".join(dict.fromkeys(seen)))
    words = [m.group(0) for m in FORECAST_OR_LEVEL.finditer(tail)]
    if words:
        out.append("observation clause holds a forecast or heat-level word: " + ", ".join(dict.fromkeys(words)))
    return out


def check(text, f):
    """The checks the sentence fails ([] if none): it begins with the tier, says the forecast heat level and the third
    in words, and every tier, heat level and third it names is the area's (a heat word may also be the observed
    category); it gives every required() number; every number is in the facts, and every date, temperature and rank is
    its own fact (wrong_facts); numbers are digits, and the App's other checks pass (coolcheck.agent.check_summary:
    P(High) or a score, a send claim, medical advice, a planning area not in the facts); at most MAX_WORDS words in one
    sentence; no banned word that no fact holds; the observed peak is not tied to the forecast or the tier. Then window
    D's four rules: each measure as given (not_verbatim), each bracket its own fact (wrong_brackets), nothing but the
    facts and frame words (beyond_frame), and the observation in its own clause (observation_out_of_place)."""
    t = clean(text)
    if not t:
        return ["empty"]
    ft = json.dumps(f, ensure_ascii=False)
    tier, heat, third = f["tier"], f["forecast_heat_level"], f["vulnerability_third"]
    observed = f.get("observed_heat", {}).get("nea_category")
    failed = []
    first = re.match(r"[^A-Za-z]*([A-Za-z]+)", t)
    if not first or first.group(1).lower() != tier.lower():
        failed.append(f"tier: does not begin with {tier}")
    named = {(m.group(1) or m.group(2)).title() for m in TIER_WORD.finditer(t)}
    named |= {"Medium"} if re.search(r"\bmedium\b", t, re.I) else set()
    if named - {tier}:
        failed.append("tier: names " + ", ".join(sorted(named - {tier})))
    forecast = {(m.group(1) or m.group(2)).title() for m in FORECAST_WORD.finditer(t)}
    heat_words = {m.group(1).title() for m in HEAT_WORD.finditer(t)}
    if heat not in forecast | heat_words:
        failed.append(f"heat: does not say {heat} heat")
    if (heat_words - {heat, observed}) | (forecast - {heat}):
        failed.append("heat: names " + ", ".join(sorted((heat_words - {heat, observed}) | (forecast - {heat}))))
    thirds = {THIRDS.get(m.group(1).lower(), m.group(1).lower()) for m in THIRD_WORD.finditer(t)}
    if third not in thirds:
        failed.append(f"third: does not say the {third} third")
    if thirds - {third}:
        failed.append("third: names " + ", ".join(sorted(thirds - {third})))
    have = {A._num(n) for n in A.NUMBER.findall(t)}
    missing = [n for n in required(f) if A._num(n) not in have]
    if missing:
        failed.append("facts: does not give " + ", ".join(missing))
    _, app = A.check_summary(t, sources(f), source_text=ft, seen_text=ft)
    if app["ungrounded_numbers"]:
        failed.append("numbers not in the facts: " + ", ".join(app["ungrounded_numbers"]))
    failed += wrong_facts(t, f)
    words = app["number_words"] + [w for w in ORDINALS.findall(VULNERABILITY_THIRD.sub(" ", t))
                                   if not re.search(rf"\b{w}\b", ft, re.I)]
    if words:
        failed.append("numbers in words: " + ", ".join(words))
    failed += [f"App check: {b}" for b in app["banned"]]
    if app.get("unseen_areas"):
        failed.append("areas not in the facts: " + ", ".join(app["unseen_areas"]))
    n = len(t.split())
    if n > MAX_WORDS:
        failed.append(f"length: {n} words")
    if re.search(r"[.!?]\s+\S", t):
        failed.append("length: more than one sentence")
    failed += [f"banned: {name}" for name, rx in BANNED if re.search(rx, t, re.I) and not re.search(rx, ft, re.I)]
    if observed and OBSERVATION_AS_CAUSE.search(t):
        failed.append("observation tied to the forecast or the tier")
    failed += [f"not as given: {p}" for p in not_verbatim(t, f)]
    failed += wrong_brackets(t, f)
    extra = beyond_frame(t, f)
    if extra:
        failed.append("beyond the facts: " + ", ".join(dict.fromkeys(extra)))
    failed += observation_out_of_place(t, f)
    return failed


def choose(f, sentence, error=None):
    """The row's sentences: the model's if it passed every check, else the template, with who wrote the one shown."""
    tpl = template(f)
    failed = [f"model error: {error}"] if error else check(sentence, f)
    return {"template_sentence": tpl, "ai_sentence": sentence, "explanation": tpl if failed else clean(sentence),
            "written_by": TEMPLATE if failed else AI, "checks_failed": "; ".join(failed) or None}


# --- SQL (warehouse) ----------------------------------------------------------------------------------------------------

def latest_date_sql(catalog):
    return f"SELECT max(target_date) AS target_date FROM {_c(catalog)}.gold.area_heat_risk"


def heat_sql(catalog, target_date):
    return f"""
SELECT target_date, planning_area, tier, heat_level, third, reason, station_id
FROM {_c(catalog)}.gold.area_heat_risk
WHERE target_date = DATE'{date.fromisoformat(str(target_date))}' AND rated
ORDER BY planning_area
"""


def vulnerability_sql(catalog):
    cols = ", ".join(["planning_area", "residents", "aged_65_plus", "hdb_dwelling_units_confirmed",
                      *dict.fromkeys(c for c, _ in MEASURES.values())])
    return f"SELECT {cols} FROM {_c(catalog)}.gold.area_vulnerability ORDER BY planning_area"


def observed_sql(catalog, target_date):
    """Each station's usable observed day before the target date (one row per station: the view repeats a station for
    each area that took it that day)."""
    d = date.fromisoformat(str(target_date)) - timedelta(days=1)
    return f"""
SELECT DISTINCT station_id, max_wbgt, heat_category
FROM {_c(catalog)}.gold.observed_heat_daily
WHERE sgt_date = DATE'{d}'
"""


def ai_sql(model=MODEL):
    """One ai_query per request; :requests is a JSON array of {planning_area, request}."""
    return f"""
SELECT planning_area, response.result AS sentence, response.errorMessage AS error
FROM (
  SELECT planning_area, ai_query({_lit(model)}, request,
    modelParameters => named_struct('temperature', {TEMPERATURE!r}D, 'max_tokens', {MAX_TOKENS}),
    failOnError => false) AS response
  FROM (SELECT inline(from_json(:requests, 'ARRAY<STRUCT<planning_area: STRING, request: STRING>>')))
)
ORDER BY planning_area
"""


def create_sql(catalog):
    cols = ",\n  ".join(f"{c} {t} COMMENT {_lit(cm)}" for c, t, cm in COLUMNS)
    return f"CREATE TABLE IF NOT EXISTS {_c(catalog)}.gold.{TABLE} (\n  {cols}\n) COMMENT {_lit(COMMENT)}"


def comment_sqls(catalog):
    """The comments again, so a table made by an earlier version carries this one's."""
    t = f"{_c(catalog)}.gold.{TABLE}"
    return [f"COMMENT ON TABLE {t} IS {_lit(COMMENT)}",
            *[f"ALTER TABLE {t} ALTER COLUMN {c} COMMENT {_lit(cm)}" for c, _, cm in COLUMNS],
            f"ALTER TABLE {t} SET TAGS ({', '.join(f'{_lit(k)} = {_lit(v)}' for k, v in TAGS.items())})"]


def write_sql(catalog, target_date):
    """Replace the target date's rows (one atomic Delta write); :rows is a JSON array of the other columns."""
    d = date.fromisoformat(str(target_date))
    fields = [c for c, _, _ in COLUMNS if c not in ("target_date", "generated_at")]
    schema = "ARRAY<STRUCT<" + ", ".join(f"{c}: STRING" for c in fields) + ">>"
    return f"""
INSERT INTO {_c(catalog)}.gold.{TABLE} REPLACE WHERE target_date = DATE'{d}'
SELECT DATE'{d}' AS target_date, {", ".join(fields)}, current_timestamp() AS generated_at
FROM (SELECT inline(from_json(:rows, '{schema}')))
"""
