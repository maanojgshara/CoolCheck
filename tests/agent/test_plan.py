"""Local tests for coolcheck.plan (the App's draft without a model; docs/design/agent_app.md): masking, capacity, the
notices, the per-tier template, the plan text, the approval MERGE and the table's columns. The warehouse is a fake;
the same calls ran live against the trial on 24 Oct (docs/design/agent_app.md, "Checks").
"""
import ast
import json
import re
from pathlib import Path

import pytest

from coolcheck import plan as P
from plan_fixtures import D24, FORECAST, ROWS_23, ROWS_24, ROWS_N, ROWS_NE, FakeWarehouse

REPO = Path(__file__).resolve().parents[2]
NUMBER = re.compile(r"\d+(?:\.\d+)?")


# --- masking -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw,want", [
    ("call S1234567D today", "call [NRIC masked] today"),
    ("t7654321z and G1234567X", "[NRIC masked] and [NRIC masked]"),
    ("F0000000A, M1234567K.", "[NRIC masked], [NRIC masked]."),
    ("ring 91234567 or 6123 4567", "ring [phone masked] or [phone masked]"),
    ("+65 8123-4567 please", "[phone masked] please"),
    ("hp:98765432", "hp:[phone masked]"),
])
def test_mask_personal_masks(raw, want):
    assert P.mask_personal(raw)[0] == want
    assert P.mask_personal(raw)[1] >= 1


@pytest.mark.parametrize("raw", [
    "only 8 volunteers tomorrow, 800 calls", "Blk 208A Woodleigh Link", "postal code 367803", "12345678 is not a phone",
    "51234567", "912345678 has nine digits", "S123456D has six digits", "A1234567B is not an NRIC prefix", "",
])
def test_mask_personal_leaves_the_rest(raw):
    assert P.mask_personal(raw) == (raw, 0)


def test_mask_note_is_on_screen_text():
    assert "NRIC" in P.MASK_NOTE and "6, 8 or 9" in P.MASK_NOTE


# --- capacity --------------------------------------------------------------------------------------------------------

def test_capacity_precedence():
    assert P.capacity_from(800, 25) == (800, "form: 800 calls (placeholder: replace with your team's figure)")
    cap, basis = P.capacity_from(800, 25, volunteers=8)
    assert cap == 200 and basis.startswith("request: 8 volunteers x 25 calls per volunteer (assumption")
    assert P.capacity_from(800, 25, volunteers=8, request_calls_per_volunteer=30)[0] == 240
    assert P.capacity_from(800, 25, volunteers=8, request_capacity=150) == (150, "request: 150 calls")


def test_region_param():
    assert P.region_param(None) is None and P.region_param("Whole island") is None and P.region_param(" all ") is None
    assert P.region_param("NORTH-EAST") == "NORTH-EAST"


# --- notices -------------------------------------------------------------------------------------------------------

def test_notice_when_no_rated_area_is_high():
    (n,) = P.notices(ROWS_23, "2026-10-23")
    assert n.startswith("No rated area is High on 23 Oct. Southern Islands has High heat but is Not rated")


def test_notice_lists_unrated_high_heat_beside_a_high_area():
    (n,) = P.notices(ROWS_24, D24)
    assert n == "High heat but Not rated (no confirmed HDB blocks, so no blocks or calls): Southern Islands and Sungei Kadut."


def test_no_rated_area_sentences_name_the_plans_region():
    # the demo request "Only 8 volunteers tomorrow, North-East only": no High tier there, while Toa Payoh is High
    assert P.template_summary(ROWS_NE, 200, "NORTH-EAST").startswith(
        "No rated area in the North-East region is in the High tier. Medium tier: Sengkang.")
    assert P.template_summary(ROWS_23, 500).startswith("No rated area is in the High tier.")  # the whole island
    (n,) = P.notices(ROWS_N, D24, region="NORTH")
    assert n.startswith("No rated area in the North region is High on 24 Oct. Sungei Kadut has High heat but is Not rated")
    assert P.where_in("ALL") == "" and P.region_name("NORTH-EAST REGION") == "North-East"


def test_notices_missing_forecast_and_empty():
    assert P.notices([], D24, {"forecast_missing": True})[0].startswith("The NEA forecast issue was missing")
    assert "unknown region" in P.notices([], D24)[-1]


# --- the template and the plan text ----------------------------------------------------------------------------------

def _numbers(text):
    return set(NUMBER.findall(text))


def _source_numbers(rows, *extra):
    blob = json.dumps(rows) + " " + " ".join(str(x) for x in extra)
    return _numbers(blob)


NO_CALLS = [dict(r, calls_allocated=0, calls_left=0, blocks=[]) for r in ROWS_24]


@pytest.mark.parametrize("rows,capacity", [(ROWS_24, 800), (ROWS_23, 500), (NO_CALLS, 0)])
def test_template_numbers_come_from_the_tool_result(rows, capacity):
    s = P.template_summary(rows, capacity)
    assert _numbers(s) <= _source_numbers(rows, capacity, len(rows), 3)  # 3: the blocks counted from the rows


def test_leftover_notice_unless_the_summary_gives_the_number():
    rows = [dict(r, calls_left=40309) for r in ROWS_24]
    assert P.leftover_notice(rows, 100000, "Toa Payoh is High.") == \
        "40309 of the 100000 calls are left over: every High- and Medium-tier block in this plan has its calls."
    assert P.leftover_notice(rows, 100000, P.template_summary(rows, 100000)) is None  # the template says "40309 left"
    assert P.leftover_notice([dict(r, calls_left=800) for r in NO_CALLS], 800, "") == \
        "All 800 calls are left over: no High- or Medium-tier block in this plan takes calls."
    assert P.leftover_notice(ROWS_24, 800, "") is None and P.leftover_notice(NO_CALLS, 0, "") is None


def test_lookup_notices_only_for_a_block_number_with_no_rows():
    calls = [P.ToolCall("find_refuges", {"blk_no": "blk 5a", "street": "LOR 7 TOA PAYOH"}),
             P.ToolCall("find_refuges", {"blk_no": "5A", "street": "LOR 7 TOA PAYOH"}),            # the same note once
             P.ToolCall("find_refuges", {"blk_no": "170", "street": "X"}, rows=[{"refuge_rank": 1}]),
             P.ToolCall("what_if_add_refuge", {"blk_no": "9", "street": "Y"}, error="RuntimeError: x"),
             P.ToolCall("get_priority_areas", {"target_date": "2026-10-24", "call_capacity": 800, "region": None})]
    assert P.lookup_notices(calls) == ["Blk 5A LOR 7 TOA PAYOH was not found among CoolCheck's confirmed HDB blocks, "
                                       "so no refuges are listed for it; check the block number and street."]


def test_template_summary_24_oct():
    s = P.template_summary(ROWS_24, 800)
    assert s == ("High tier: Toa Payoh. Medium tier: Bishan. 1 area is Low: routine, no calls. Of 800 calls, 800 go to "
                 "3 blocks in Toa Payoh; 0 left.")
    assert "None of the 800 calls" in P.template_summary(NO_CALLS, 800)
    assert "No call capacity" in P.template_summary(NO_CALLS, 0)


def test_plan_section_partial_rounding_and_refuge_at_block():
    text = P.plan_section(ROWS_24)
    assert "Blk 5 LOR 7 TOA PAYOH: 180 calls of 258 flats (partial)" in text
    assert "nearest refuge Bidadari CC, about 450 m in a straight line" in text
    assert "Care Corner AAC (TP170), at the block (within 400 m)" in text
    assert "Bishan" not in text  # no calls, so not in the plan section


def test_draft_text_has_footer_and_no_forbidden_terms():
    tools = P.Tools(FakeWarehouse(), trace=False)
    d = P.draft_direct(tools, D24, 800, P.capacity_from(800, 25)[1], None, FORECAST, trace=False)
    t = d.draft_text
    assert t.startswith("CoolCheck draft outreach plan for 24 Oct 2026, the whole island. Forecast scored 24 Oct 2026, 00:49 SGT.")
    assert "Draft only: nothing has been sent." in t and "Summary (template):" in t
    assert "Note: High heat but Not rated" in t
    assert not re.search(r"p_high|P\(High\)|probabilit|score\b", t, re.I)


def test_draft_direct_calls_the_function_with_typed_parameters():
    wh = FakeWarehouse()
    d = P.draft_direct(P.Tools(wh, trace=False), D24, 800, "b", "north-east", FORECAST, trace=False)
    sql, params = wh.statements[0]
    assert sql == "SELECT * FROM coolcheck.gold.get_priority_areas(:target_date, :call_capacity, :region)"
    assert params == {"target_date": ("2026-10-24", "DATE"), "call_capacity": (800, "INT"), "region": ("north-east", "STRING")}
    assert [c.name for c in d.tool_calls] == ["get_priority_areas"] and d.calls_allocated == 800


def test_draft_direct_raises_when_the_tool_fails():
    with pytest.raises(P.ToolError, match="get_priority_areas failed"):
        P.draft_direct(P.Tools(FakeWarehouse(fail="get_priority_areas"), trace=False), D24, 800, "b", trace=False)


def test_tools_sort_and_reject_bad_catalog():
    call = P.Tools(FakeWarehouse(), trace=False).find_refuges("208A", "WOODLEIGH LINK")
    assert [r["refuge_rank"] for r in call.rows] == [1, 2]
    with pytest.raises(ValueError):
        P.Tools(FakeWarehouse(), catalog="x; DROP TABLE y")


# --- warehouse value conversion ------------------------------------------------------------------------------------

def test_struct_array_values_are_typed():
    typ = P.parse_type("ARRAY<STRUCT<priority: INT, blk_no: STRING, refuge_main_m: DOUBLE, partial: BOOLEAN>>")
    raw = '[{"priority":"1","blk_no":"208A","refuge_main_m":"448.34","partial":"false"}]'
    assert P._convert(raw, typ) == [{"priority": 1, "blk_no": "208A", "refuge_main_m": 448.34, "partial": False}]
    assert P._convert("12", "INT") == 12 and P._convert(None, "INT") is None and P._convert("x", "STRING") == "x"


# --- approval ------------------------------------------------------------------------------------------------------

def test_approval_sql_is_an_insert_only_merge():
    sql = P.approval_sql()
    assert sql.startswith("MERGE INTO coolcheck.gold.pending_approval AS t USING (SELECT :approval_id AS approval_id)")
    assert "WHEN NOT MATCHED THEN INSERT" in sql and "WHEN MATCHED" not in sql.replace("WHEN NOT MATCHED", "")
    assert not re.search(r"\b(UPDATE|DELETE)\b", sql)
    with pytest.raises(ValueError):
        P.approval_sql("bad name")


def test_table_ddl_matches_the_merge_columns():
    ddl = (REPO / "src" / "tables" / "pending_approval.sql").read_text(encoding="utf-8")
    cols = re.findall(r"^\s+(\w+) (?:STRING|TIMESTAMP|DATE|INT)\b", ddl, re.M)
    assert tuple(cols) == P.APPROVAL_COLUMNS
    assert ddl.count("COMMENT '") == len(cols) + 1  # every column and the table


def test_approve_writes_one_row_per_draft():
    wh = FakeWarehouse()
    d = P.draft_direct(P.Tools(wh, trace=False), D24, 800, "b", None, FORECAST, trace=False)
    row1 = P.approve(wh, d, "1234567890@7474646896364032", app_commit="abc")
    row2 = P.approve(wh, d, "1234567890@7474646896364032", app_commit="abc")
    assert row1 == row2 and len(wh.approvals) == 1
    p = wh.approvals[d.approval_id]
    assert p["status"] == ("approved_not_sent", "STRING") and p["source"] == ("template", "STRING")
    assert p["forecast_run_id"][0] == "647995027381846" and p["calls_allocated"] == (800, "INT")
    assert [a["planning_area"] for a in json.loads(p["plan_json"][0])] == ["TOA PAYOH"]
    assert json.loads(p["tool_calls_json"][0])[0]["name"] == "get_priority_areas"
    assert set(p) == set(P.APPROVAL_COLUMNS) - {"approved_at", "approved_sgt_date"}


@pytest.mark.parametrize("who", ["", "   ", None])
def test_approve_refuses_without_an_approver(who):
    d = P.draft_direct(P.Tools(FakeWarehouse(), trace=False), D24, 800, "b", trace=False)
    with pytest.raises(ValueError, match="no approver"):
        P.approval_params(d, who)


def test_create_script_fills_the_table_name():
    import create_pending_approval as C
    assert C.create_sql("workspace").startswith("CREATE TABLE IF NOT EXISTS workspace.gold.pending_approval (")
    with pytest.raises(SystemExit):
        C.create_sql("a-b")


# --- nothing is sent -----------------------------------------------------------------------------------------------

SENDERS = {"smtplib", "email", "twilio", "sendgrid", "slack_sdk", "telegram", "requests", "httpx", "urllib", "socket",
           "boto3", "http"}


@pytest.mark.parametrize("path", ["src/app.py", "src/coolcheck/plan.py", "src/coolcheck/agent.py"])
def test_no_messaging_or_raw_network_imports(path):
    tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not names & SENDERS, names & SENDERS


def test_no_op_trace_id_is_none():
    class S:
        trace_id = "MLFLOW_NO_OP_SPAN_TRACE_ID"
    assert P.trace_id_of(S()) is None and P.trace_id_of(P._NoSpan()) is None
    S.trace_id = "tr-abc"
    assert P.trace_id_of(S()) == "tr-abc"
