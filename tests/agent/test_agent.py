"""Local tests for coolcheck.agent.draft_plan with a scripted model and the fake warehouse: the arithmetic in code, the
limits, the timeout, the fallbacks (decision 4), the number check (digits, rounding, percentages, other scripts), the
banned content, masking before the model sees the request, and the stale-forecast notice.
"""
import datetime as dt
import json

import pytest

from coolcheck import agent as A
from coolcheck import plan as P
from plan_fixtures import D24, FORECAST, ROWS_23, ROWS_24, FakeWarehouse

SPECS = [{"type": "function", "function": {"name": n, "description": "d", "parameters": {"type": "object", "properties": {}}}}
         for n in ("get_priority_areas", "find_refuges", "what_if_add_refuge")]


def tool_msg(*calls):
    return {"choices": [{"message": {"content": "", "tool_calls": [
        {"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a) if isinstance(a, dict) else a}}
        for i, (n, a) in enumerate(calls)]}}]}


def text_msg(t):
    return {"choices": [{"message": {"content": t}}]}


class Script:
    def __init__(self, *responses):
        self.responses, self.seen = list(responses), []

    def __call__(self, messages, tools):
        self.seen.append([dict(m) for m in messages])
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def run(script, request="Only 8 volunteers tomorrow", rows=ROWS_24, **kw):
    wh = FakeWarehouse(rows)
    d = A.draft_plan(request, target_date=D24, default_capacity=800, calls_per_volunteer=25, runner=wh, chat=script,
                     specs=SPECS, forecast=FORECAST, trace=False, **kw)
    return d, wh


GOOD = "Toa Payoh is High. Call Blk 208A Woodleigh Link first: 312 calls. Bidadari CC is about 450 m away in a straight line."


def test_agent_path_arithmetic_in_code_and_checks_pass():
    s = Script(tool_msg(("get_priority_areas", {"volunteers": 8})), text_msg(GOOD))
    d, wh = run(s)
    assert d.source == "agent" and d.fallback_reason is None and d.summary_text == GOOD
    assert d.call_capacity == 200 and "8 volunteers x 25 calls per volunteer" in d.capacity_basis
    assert wh.statements[0][1]["call_capacity"] == (200, "INT")
    (c,) = d.tool_calls
    assert c.llm_arguments == {"volunteers": 8} and c.arguments["call_capacity"] == 200
    tool_reply = json.loads(s.seen[1][-1]["content"])
    assert tool_reply["call_capacity"] == 200 and "p_high" not in json.dumps(tool_reply)
    assert d.llm_model == A.MODEL and d.checks["rounds"] == 2


def test_request_values_override_the_form():
    s = Script(tool_msg(("get_priority_areas", {"volunteers": 4, "calls_per_volunteer": 30, "region": "north-east"})),
               text_msg("Toa Payoh is High."))
    d, wh = run(s, region="WEST")
    assert wh.statements[0][1]["call_capacity"] == (120, "INT") and d.region == "north-east"


def test_model_failure_falls_back_to_the_template_with_form_values():
    d, wh = run(Script(RuntimeError("gateway 503")))
    assert d.source == "template" and "gateway 503" in d.fallback_reason and d.llm_model is None
    assert d.call_capacity == 800 and d.summary_text == P.template_summary(ROWS_24, 800)
    assert d.notices  # the Not-rated High-heat note is code, so it survives the fallback


def test_no_get_priority_areas_call_falls_back():
    d, _ = run(Script(text_msg("Toa Payoh is High.")))
    assert d.source == "template" and "did not call get_priority_areas" in d.fallback_reason


def test_round_cap_and_tool_cap():
    loop = [tool_msg(("find_refuges", {"blk_no": "208A", "street": "WOODLEIGH LINK"}))] * 5
    d, _ = run(Script(*loop), max_rounds=3)
    assert d.source == "template" and "3 model rounds" in d.fallback_reason
    many = tool_msg(*[("find_refuges", {"blk_no": "1", "street": "X"})] * 4)
    d, _ = run(Script(many, many), max_tool_calls=6)
    assert "more than 6 tool calls" in d.fallback_reason


def test_timeout():
    d, _ = run(Script(tool_msg(("get_priority_areas", {})), text_msg(GOOD)), timeout_s=-1)
    assert d.source == "template" and "timed out" in d.fallback_reason


def test_malformed_and_unknown_arguments_go_back_to_the_model():
    s = Script(tool_msg(("get_priority_areas", "{not json"), ("get_priority_areas", {"date": "2026-10-25"}),
                        ("get_priority_areas", {"volunteers": -3})),
               tool_msg(("get_priority_areas", {})), text_msg("Toa Payoh is High."))
    d, wh = run(s)
    replies = [json.loads(m["content"]) for m in s.seen[1] if m["role"] == "tool"]
    assert [r["error"].split(":")[0] for r in replies] == ["malformed arguments", "unknown arguments", "volunteers must be between 0 and 100000"]
    assert d.source == "agent" and len(wh.statements) == 1  # only the valid call ran


@pytest.mark.parametrize("summary,why", [
    ("Call 350 seniors in Toa Payoh.", "ungrounded_numbers"),
    ("Toa Payoh has a 12% chance of High heat.", "banned"),
    ("Toa Payoh has a high risk score.", "banned"),
    ("The SMS was sent to all seniors.", "banned"),
    ("Seniors should take paracetamol.", "banned"),
    ("Call eight blocks.", "number_words"),
])
def test_failed_summary_is_withheld(summary, why):
    d, _ = run(Script(tool_msg(("get_priority_areas", {})), text_msg(summary)))
    assert d.source == "template" and why in d.fallback_reason and summary not in d.draft_text


@pytest.mark.parametrize("text", [
    "Panggil Blok 208A dahulu: 312 panggilan.",                     # Malay
    "முதலில் 208A தொகுதியை அழைக்கவும்: 312 அழைப்புகள்.",             # Tamil
    "先致电208A座：312个电话。",                                       # Chinese
    "Toa Payoh: 800 of 3,835 flats; Bidadari CC about 450 m; 2026-10-24.",
])
def test_number_check_on_other_scripts_and_rounding(text):
    sources = A.source_numbers(ROWS_24, "2026-10-24")
    ok, checks = A.check_summary(text, sources)
    assert ok, checks


def test_number_check_rounding_and_percent_rules():
    s = {448.34, 0.6017823042647995, 3835.0}
    assert A.grounded("450", s) and A.grounded("448.3", s) and not A.grounded("460", s)
    assert A.grounded("60", s, percent=True) and not A.grounded("70", s, percent=True)
    assert A.grounded("3,835", s) and not A.grounded("3836", s)


def test_unrated_high_heat_named_is_recorded_when_no_rated_area_is_high():
    s = Script(tool_msg(("get_priority_areas", {})), text_msg("No rated area is High. Southern Islands has High heat but is Not rated."))
    d, _ = run(s, rows=ROWS_23)
    assert d.source == "agent" and d.checks["names_unrated_high_heat"] is True
    assert d.notices[0].startswith("No rated area is High on 24 Oct")


def test_request_is_masked_before_the_model_and_the_store():
    s = Script(tool_msg(("get_priority_areas", {})), text_msg("Toa Payoh is High."))
    d, _ = run(s, request="8 volunteers; Mdm Tan S1234567D at 91234567")
    sent = s.seen[0][1]["content"]
    assert "S1234567D" not in sent and "91234567" not in sent and "[NRIC masked]" in sent and "[phone masked]" in sent
    assert d.request_text == "8 volunteers; Mdm Tan [NRIC masked] at [phone masked]" and d.checks["masked"] == 2


def test_tool_specs_use_the_unity_catalog_comments():
    class P_:
        def __init__(self, name, comment):
            self.name, self.comment = name, comment

    class F:
        def __init__(self, comment, params):
            self.comment = comment
            self.input_params = type("I", (), {"parameters": [P_(n, c) for n, c in params]})()

    class WS:
        class functions:
            @staticmethod
            def get(full):
                n = full.split(".")[-1]
                if n == "get_priority_areas":
                    return F("GPA comment.", [("target_date", "td"), ("call_capacity", "cap comment."), ("region", "reg comment.")])
                return F(f"{n} comment.", [("blk_no", "blk comment."), ("street", "street comment.")])

    A._SPECS.clear()
    specs = A.tool_specs(WS(), "testcat")
    g = specs[0]["function"]
    assert g["description"].startswith("GPA comment.") and "target_date" not in g["parameters"]["properties"]
    assert g["parameters"]["properties"]["call_capacity"]["description"].startswith("cap comment.")
    assert specs[1]["function"]["description"] == "find_refuges comment."
    A._SPECS.clear()


# --- the stale-forecast notice (Singapore clock) ---------------------------------------------------------------------

def test_sgt_today_uses_the_singapore_clock():
    late_utc = dt.datetime(2026, 10, 24, 17, 30, tzinfo=dt.timezone.utc)  # 01:30 on 25 Oct in Singapore
    assert P.sgt_today(late_utc) == dt.date(2026, 10, 25)
    assert P.sgt_today(dt.datetime(2026, 10, 24, 15, 59, tzinfo=dt.timezone.utc)) == dt.date(2026, 10, 24)


def test_stale_notice():
    assert P.stale_notice(dt.date(2026, 10, 24), today=dt.date(2026, 10, 25)) == \
        "No forecast for today yet; this is the plan for 24 Oct."
    assert P.stale_notice(dt.date(2026, 10, 25), today=dt.date(2026, 10, 25)) is None
    assert P.stale_notice(None) == "No forecast is available yet."


def test_number_word_from_a_tool_result_passes():
    ok, checks = A.check_summary("The AAC broadcasts an advisory in four languages.", set(), source_text="in four languages")
    assert ok, checks
    assert not A.check_summary("Call four blocks.", set(), source_text="in two languages")[0]
