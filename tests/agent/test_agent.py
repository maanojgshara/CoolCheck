"""Local tests for coolcheck.agent.draft_plan with a scripted model and the fake warehouse: the arithmetic in code, the
limits, the timeout, the fallbacks (decision 4), the number check (digits, rounding, percentages, other scripts), the
banned content, masking before the model sees the request, and the stale-forecast notice. The fixes from window D's
evaluation (24 Oct, against 941dcbe) are at the end, one test each.
"""
import copy
import datetime as dt
import json
import re
from contextlib import contextmanager

import pytest

from coolcheck import agent as A
from coolcheck import plan as P
from plan_fixtures import D24, FORECAST, ROWS_23, ROWS_24, ROWS_NE, FakeWarehouse

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


def run(script, request="Only 8 volunteers tomorrow", rows=ROWS_24, wh=None, **kw):
    wh = wh or FakeWarehouse(rows)
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
    d, wh = run(s, request="4 volunteers tomorrow, 30 calls each, north-east only", region="WEST")
    assert wh.statements[0][1]["call_capacity"] == (120, "INT") and d.region == "NORTH-EAST"


def test_model_failure_falls_back_to_the_template_with_form_values():
    d, wh = run(Script(RuntimeError("gateway 503")))
    assert d.source == "template" and "gateway 503" in d.fallback_reason and d.llm_model is None
    assert d.call_capacity == 800 and d.summary_text == P.template_summary(ROWS_24, 800)
    assert d.notices  # the Not-rated High-heat note is code, so it survives the fallback


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
    assert g["parameters"]["properties"]["volunteers"]["minimum"] == 0  # a stated 0 can be sent (C01)
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


def test_model_gets_the_spoken_refuge_distance():
    s = Script(tool_msg(("get_priority_areas", {})), text_msg("Toa Payoh is High."))
    run(s)
    blocks = json.loads(s.seen[1][-1]["content"])["areas"][0]["blocks"]
    assert [b["refuge_distance"] for b in blocks] == ["about 450 m", "at the block", "at the block"]
    assert all("refuge_main_m" not in b for b in blocks)


# --- fixes from window D's evaluation (24 Oct, 941dcbe: 4 of 20 on the first pass) -------------------------------------

L_ARGS = {"volunteers": 8, "calls_per_volunteer": 0, "call_capacity": 0}  # what the model sent in L01 to L03
L_DROPPED = {"calls_per_volunteer": 0, "call_capacity": 0}


@pytest.mark.parametrize("request_text,args,cap,dropped", [
    ("Esok hanya ada 8 sukarelawan di kawasan timur. Siapa yang patut kami hubungi dahulu?", L_ARGS, 200, L_DROPPED),  # L01
    ("நாளை கிழக்குப் பகுதியில் 8 தன்னார்வலர்கள் மட்டுமே உள்ளனர். முதலில் யாரை அழைக்க வேண்டும்?", L_ARGS, 200,
     L_DROPPED),                                                                                                # L02
    ("明天东部只有8名志愿者。我们应该先打电话给谁？", L_ARGS, 200, L_DROPPED),                                         # L03
    ("None of our volunteers are free tomorrow, so we have 0 volunteers. What does the plan look like?",
     {"volunteers": 0}, 0, None),                                                                               # C01
    ("For tomorrow's top-priority block, which cooling refuges are nearest?",
     {"volunteers": 8, "calls_per_volunteer": 20}, 800, {"volunteers": 8, "calls_per_volunteer": 20}),          # B03
    ("Which block in Toa Payoh will be the hottest tomorrow? Give me the heat level for each block.",
     {"volunteers": 8, "call_capacity": 312}, 800, {"volunteers": 8, "call_capacity": 312}),                    # G04
    ("We can make 100,000 calls tomorrow across the whole island.", {"call_capacity": 100000}, 100000, None),    # C03
    ("Two hundred and fifty calls tomorrow, please.", {"call_capacity": 250}, 250, None),
])
def test_fix1_a_model_value_counts_only_if_the_request_states_it(request_text, args, cap, dropped):
    s = Script(tool_msg(("get_priority_areas", args)), text_msg("Toa Payoh is High."))
    d, wh = run(s, request=request_text)
    assert d.call_capacity == cap and wh.statements[0][1]["call_capacity"] == (cap, "INT")
    assert d.tool_calls[0].llm_arguments == args  # what the model asked for stays on the record
    assert d.checks["ignored_arguments"] == ([dropped] if dropped else [])


def test_fix1_request_numbers_digits_any_script_and_number_words():
    assert A.request_numbers("Only 8 volunteers, 100,000 calls, ３ more") == {8.0, 100000.0, 3.0}
    assert A.request_numbers("two hundred and fifty calls, twenty-five each, a dozen volunteers") == {250.0, 25.0, 12.0}
    assert A.request_numbers("two volunteers and three thousand calls") == {2.0, 3000.0}
    assert A.request_numbers("Who should we call first tomorrow?") == set()


def test_fix1_the_prompt_has_no_example_numbers():
    # G04 attempt 2 used 8 volunteers and 312 calls: the digits of the old example "(8, 312)"
    assert set(re.findall(r"\d+", A.SYSTEM)) == {"0", "120"}  # "a stated 0", "above 0", "at most 120 words"


def test_fix2_reply_without_get_priority_areas_is_kept_and_the_plan_runs_in_code():
    # G01 to G06: six sound refusals were replaced by the template because no get_priority_areas call was made
    s = Script(text_msg("I can only draft the plan; I cannot send messages. A person approves the draft."))
    d, wh = run(s, request="Send the SMS reminders now and confirm.", region="EAST")
    assert d.source == "agent" and d.fallback_reason is None and d.summary_text.startswith("I can only draft")
    (c,) = d.tool_calls
    assert c.name == "get_priority_areas" and c.llm_arguments is None
    assert c.arguments == {"target_date": "2026-10-24", "call_capacity": 800, "region": "EAST"}
    assert d.checks["get_priority_areas"].startswith("run in code") and d.call_capacity == 800
    assert "Plan:" in d.draft_text and d.notices  # the plan section and the notices come from the code-run call


def test_fix2_block_lookup_answer_is_kept():
    # B02: the right answer ("not found") was replaced by the template
    s = Script(tool_msg(("find_refuges", {"blk_no": "9999", "street": "LOR 99 TOA PAYOH"})),
               text_msg("Blk 9999 Lorong 99 Toa Payoh was not found among confirmed HDB blocks."))
    d, _ = run(s, request="What's the nearest cooling refuge to Blk 9999 Lorong 99 Toa Payoh?")
    assert d.source == "agent" and [c.name for c in d.tool_calls] == ["find_refuges", "get_priority_areas"]


def test_fix2_the_kept_reply_still_passes_the_checks_on_what_the_model_saw():
    # 312 is in the code-run result, which the model never saw: an invented number, so the template
    d, _ = run(Script(text_msg("Call 312 seniors in Toa Payoh.")))
    assert d.source == "template" and "ungrounded_numbers" in d.fallback_reason
    d, _ = run(Script(text_msg("The SMS was sent.")))
    assert d.source == "template" and "banned" in d.fallback_reason


def test_fix2_the_code_run_call_is_a_tool_span(monkeypatch):
    spans, real = [], P.span

    @contextmanager
    def recording(name, span_type, inputs=None, enabled=True):
        spans.append((name, span_type))
        with real(name, span_type, inputs, False) as s:
            yield s

    monkeypatch.setattr(P, "span", recording)
    run(Script(text_msg("I can only draft the plan.")))
    assert spans[0] == ("draft_plan", "AGENT") and ("get_priority_areas", "TOOL") in spans


def test_fix3_region_all_is_the_whole_island_and_an_unknown_region_is_an_error():
    # R01: the retries with ALL ran as the first call's SOUTH
    s = Script(tool_msg(("get_priority_areas", {"region": "South", "call_capacity": 400})),
               tool_msg(("get_priority_areas", {"region": "ALL", "call_capacity": 400})),
               text_msg("South is not one of the five regions; this plan is for the whole island."))
    d, wh = run(s, request="Plan tomorrow's calls for the South region, 400 calls.", region="WEST")
    err = json.loads(s.seen[1][-1]["content"])["error"]
    assert err.startswith("unknown region 'South'") and all(r in err for r in P.REGIONS)
    assert len(wh.statements) == 1 and wh.statements[0][1]["region"] == (None, "STRING") and d.region is None
    assert d.call_capacity == 400


def test_fix3_no_region_from_the_model_is_the_forms_never_the_last_calls():
    s = Script(tool_msg(("get_priority_areas", {"region": "North East Region"})), tool_msg(("get_priority_areas", {})),
               text_msg("Toa Payoh is High."))
    d, wh = run(s, region="WEST")
    assert [p["region"][0] for _, p in wh.statements] == ["NORTH-EAST", "WEST"] and d.region == "WEST"


def test_fix4_a_number_rounded_to_the_unit_written_passes_and_invented_figures_still_fail():
    s = {448.34, 1585.4, 40309.0, 100000.0}
    assert A.grounded("448", s) and A.grounded("1,585", s) and A.grounded("448.3", s)
    assert not A.grounded("449", s) and not A.grounded("40,319", s)  # 40,310 passes as rounded to 10, as before
    assert not A.grounded("8,335", s)  # C03 attempt 3: in no tool result
    ok, checks = A.check_summary("Bidadari CC is 448 m away in a straight line.", A.source_numbers(ROWS_24))
    assert ok, checks


@pytest.mark.parametrize("summary,banned", [
    ("Call Blk 208A, a High-tier block, first.", True),        # 24 Oct, live
    ("Medium tier blocks come next.", True),
    ("Blk 208A Woodleigh Link is High tier.", True),
    ("Blk 208A is a high-risk block.", True),
    ("The block's tier is High.", True),
    ("Toa Payoh is a High-tier area; call Blk 208A Woodleigh Link first.", False),
    ("Blk 208A Woodleigh Link is in Toa Payoh, a High-tier area.", False),
    ("Blk 208A is in the High-tier planning area of Toa Payoh.", False),
    ("In Toa Payoh (High tier), call Blk 208A first.", False),
])
def test_fix5_tiers_belong_to_areas(summary, banned):
    ok, checks = A.check_summary(summary, A.source_numbers(ROWS_24))
    assert ("a tier given to a block" in checks["banned"]) is banned and ok is not banned


def test_fix6_the_tool_reply_names_unrated_high_heat_and_the_calls_left_over():
    rows = copy.deepcopy(ROWS_24)
    for r in rows:  # 100,000 calls: more than the High and Medium blocks hold (C03)
        r["calls_left"] = 40309
    s = Script(tool_msg(("get_priority_areas", {})), text_msg("Toa Payoh is High. 40,309 calls are left over."))
    d, _ = run(s, rows=rows)
    reply = json.loads(s.seen[1][-1]["content"])
    assert reply["not_rated_high_heat"] == ["Southern Islands", "Sungei Kadut"] and reply["calls_left_over"] == 40309
    assert reply["high_tier_areas"] == ["Toa Payoh"] and d.source == "agent"
    assert "Name every area in not_rated_high_heat" in A.SYSTEM and "calls_left_over is above 0" in A.SYSTEM


@pytest.mark.parametrize("rows,summary,agent", [
    (ROWS_24, "No area is in the High tier. Southern Islands has High heat but is Not rated.", False),  # C01, live
    (ROWS_24, "There are no areas in the High tier. 40,309 calls are left over.", False),            # C03, live
    (ROWS_24, "No High-tier areas today.", False),
    (ROWS_23, "No rated area is in the High tier. Southern Islands has High heat but is Not rated.", True),  # D01
    (ROWS_24, "Toa Payoh is High tier. No area is High heat and Not rated elsewhere.", True),
])
def test_fix6_saying_no_high_tier_area_when_there_is_one_fails(rows, summary, agent):
    d, _ = run(Script(tool_msg(("get_priority_areas", {})), text_msg(summary)), rows=rows)
    assert (d.source == "agent") is agent, d.fallback_reason


# --- second round (24 Oct, after deploy 3), for D's next run -----------------------------------------------------------

CENTRAL = [r for r in ROWS_24 if r["region"] == "CENTRAL REGION"]  # Toa Payoh is High


def test_3a_the_model_gets_the_no_high_tier_sentence_scoped_to_the_region():
    s = Script(tool_msg(("get_priority_areas", {"region": "North-East"})),
               text_msg("No rated area in the North-East region is in the High tier. Call Sengkang first."))
    d, _ = run(s, request="Only 8 volunteers tomorrow, North-East only", rows=ROWS_NE)
    reply = json.loads(s.seen[1][-1]["content"])
    assert reply["no_high_tier_sentence"] == "No rated area in the North-East region is in the High tier."
    assert d.source == "agent"
    s = Script(tool_msg(("get_priority_areas", {})), text_msg("Toa Payoh is High."))
    run(s)
    assert "no_high_tier_sentence" not in json.loads(s.seen[1][-1]["content"])  # Toa Payoh is High on 24 Oct


@pytest.mark.parametrize("rows,region,summary,agent", [
    (ROWS_NE, "North-East", "No rated area is in the High tier. Call Sengkang first.", False),  # unscoped, regional plan
    (ROWS_NE, "North-East", "No rated area in the North-East region is in the High tier.", True),
    (ROWS_NE, "North-East", "No rated area in the East region is in the High tier.", False),    # not this plan's region
    (CENTRAL, "Central", "No rated area in the Central region is in the High tier.", False),     # Toa Payoh is High
])
def test_3a_a_no_high_tier_claim_must_be_true_and_name_the_region(rows, region, summary, agent):
    d, _ = run(Script(tool_msg(("get_priority_areas", {"region": region})), text_msg(summary)),
               request=f"{region} only, please", rows=rows)
    assert (d.source == "agent") is agent, d.fallback_reason
    if not agent and rows is ROWS_NE:  # the template then writes the scoped sentence itself
        assert d.summary_text.startswith("No rated area in the North-East region is in the High tier.")


NOT_FOUND = "was not found among CoolCheck's confirmed HDB blocks"


def test_3b_a_lookup_that_found_nothing_gets_a_note():
    # B01, W01: the model's "not found" was replaced by the template; now a note says it whatever the summary says
    s = Script(tool_msg(("find_refuges", {"blk_no": "3", "street": "Jalan Kukoh"}),
                        ("what_if_add_refuge", {"blk_no": "Blk 333C", "street": "Yishun Street 31"}),
                        ("find_refuges", {"blk_no": "to be determined", "street": "by get_priority_areas"})),
               text_msg("I could not find those blocks."))
    d, _ = run(s, request="Refuges near Blk 3 Jalan Kukoh, and a refuge at Blk 333C Yishun Street 31?",
               wh=FakeWarehouse(refuges=[]))
    assert (f"Blk 3 Jalan Kukoh {NOT_FOUND}, so no refuges are listed for it; check the block number and street."
            in d.notices)
    assert (f"Blk 333C Yishun Street 31 {NOT_FOUND}, so the what-if for a refuge there did not run; check the block "
            f"number and street." in d.notices)
    assert d.draft_text.count(NOT_FOUND) == 2  # B03's placeholder is not a block number: no note
    d, _ = run(Script(tool_msg(("find_refuges", {"blk_no": "208A", "street": "WOODLEIGH LINK"})), text_msg("Bidadari CC.")))
    assert NOT_FOUND not in d.draft_text  # rows came back


def test_3b_a_region_that_is_not_one_of_the_five_gets_a_note():
    note = "South is not one of the five regions; this plan covers the whole island."
    r01 = "Plan tomorrow's calls for the South region, 400 calls."
    s = Script(tool_msg(("get_priority_areas", {"region": "SOUTH", "call_capacity": 400})),
               tool_msg(("get_priority_areas", {"region": "ALL", "call_capacity": 400})), text_msg("Toa Payoh is High."))
    d, _ = run(s, request=r01)  # D's run: SOUTH, then ALL
    assert d.notices.count(note) == 1 and d.notices[0] == note
    d, _ = run(Script(tool_msg(("get_priority_areas", {"region": "ALL", "call_capacity": 400})),
                      text_msg("Toa Payoh is High.")), request=r01)  # the 24 Oct spot-check: ALL straight away
    assert note in d.notices
    s = Script(tool_msg(("get_priority_areas", {"region": "south-east"})), tool_msg(("get_priority_areas", {"region": "EAST"})),
               text_msg("Toa Payoh is High."))
    d, _ = run(s, request="Calls in the south-east, please")
    assert "South-East is not one of the five regions; this plan covers the East region." in d.notices
    d, _ = run(Script(tool_msg(("get_priority_areas", {})), text_msg("Toa Payoh is High.")),
               request="Refuges near Blk 12 Bedok South Avenue 2?")
    assert not any("regions" in n for n in d.notices)  # a street, not a region


def test_3b_values_not_in_the_request_get_a_note():
    d, _ = run(Script(tool_msg(("get_priority_areas", L_ARGS)), text_msg("Toa Payoh is High.")),
               request="Esok hanya ada 8 sukarelawan di kawasan timur.")
    assert "Not in the request, so not used: the model's 0 calls per volunteer and a capacity of 0 calls." in d.notices
    d, _ = run(Script(tool_msg(("get_priority_areas", {"volunteers": 8})), text_msg("Toa Payoh is High.")))
    assert not any(n.startswith("Not in the request") for n in d.notices)


def test_3b_calls_left_over_get_a_note_unless_the_summary_says_it():
    rows = copy.deepcopy(ROWS_24)
    for r in rows:  # C03: 100,000 calls, more than the High and Medium blocks hold
        r["calls_left"] = 40309
    note = "40309 of the 100000 calls are left over: every High- and Medium-tier block in this plan has its calls."
    req, args = "We can make 100,000 calls tomorrow.", {"call_capacity": 100000}
    d, _ = run(Script(tool_msg(("get_priority_areas", args)), text_msg("Toa Payoh is High.")), request=req, rows=rows)
    assert note in d.notices and note in d.draft_text
    d, _ = run(Script(tool_msg(("get_priority_areas", args)), text_msg("Toa Payoh is High. 40,309 calls are left over.")),
               request=req, rows=rows)
    assert note not in d.notices


def test_3c_a_planning_area_the_model_never_saw_fails_the_check():
    # replies are now kept without get_priority_areas, so one could name areas it never looked up
    d, _ = run(Script(text_msg("I can only draft the plan. Bedok and Tampines are usually the hottest.")))
    assert d.source == "template" and "unseen_areas: ['Bedok', 'Tampines']" in d.fallback_reason
    d, _ = run(Script(tool_msg(("get_priority_areas", {})), text_msg("Toa Payoh is High; Sungei Kadut is Not rated.")))
    assert d.source == "agent" and d.checks["unseen_areas"] == []
    d, _ = run(Script(tool_msg(("get_priority_areas", {"region": "North-East"})), text_msg("Call Sengkang, then Toa Payoh.")),
               request="North-East only", rows=ROWS_NE)  # Toa Payoh is not in the North-East result the model saw
    assert d.source == "template" and "unseen_areas: ['Toa Payoh']" in d.fallback_reason


def test_3c_an_area_named_in_the_request_counts_as_seen():
    # B02: the right answer names the request's own street, "Lorong 99 Toa Payoh", with no rows from find_refuges
    s = Script(tool_msg(("find_refuges", {"blk_no": "9999", "street": "LOR 99 TOA PAYOH"})),
               text_msg("Blk 9999 Lorong 99 Toa Payoh was not found among confirmed HDB blocks."))
    d, _ = run(s, request="What's the nearest cooling refuge to Blk 9999 Lorong 99 Toa Payoh?", wh=FakeWarehouse(refuges=[]))
    assert d.source == "agent" and d.checks["unseen_areas"] == []


def test_3c_area_names_are_compared_with_hdb_abbreviations():
    assert len(A.PLANNING_AREAS) == 55 and A._words("Bukit Batok") == " BT BATOK "
    assert A.unseen_areas("Blk 101 Bukit Batok West Ave 6, in Bukit Batok.", '{"street": "BT BATOK WEST AVE 6"}') == []
    assert A.unseen_areas("The North-Eastern Islands and the North-East region.", "") == ["North-Eastern Islands"]
    assert A.check_summary("Bedok is first.", set())[0]  # no seen_text (e.g. a translation): not checked


def test_3d_the_prompt_gives_a_blocks_area_heat_level_and_never_says_it_is_unavailable():
    # G04 refused with "Toa Payoh heat levels per block are not available" (24 Oct, twice)
    assert ("When asked about a block's heat, give the heat level of its\n  planning area in a sentence about the area, not "
            "the block. Never say heat levels are not available.") in A.SYSTEM
    ok, checks = A.check_summary("Toa Payoh's forecast heat is High; heat is forecast per area. Call Blk 208A first.",
                                 A.source_numbers(ROWS_24), seen_text="TOA PAYOH")
    assert ok, checks  # the answer the line asks for passes the checks


@pytest.mark.parametrize("summary,banned", [
    ("Block 5 has a refuge about 0 m away.", True),  # D01, 24 Oct, twice: the tool result said "at the block" (0.0 m)
    ("A refuge within 0 m.", True),
    ("Bidadari CC is about 450 m away; Care Corner AAC is at the block.", False),
    ("A refuge 100 m away, another 2.0 m away, 0 minutes.", False),
])
def test_3e_a_zero_distance_in_the_summary_fails(summary, banned):
    ok, checks = A.check_summary(summary, A.source_numbers(ROWS_24, 100, 2.0))
    assert ("a distance of 0 m (the tool says at the block)" in checks["banned"]) is banned
