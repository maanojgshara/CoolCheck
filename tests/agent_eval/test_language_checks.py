"""The language set and the grader's language checks (docs/design/agent_eval.md, item 7), on fake translation records:
local, no workspace and no model. The fixed lines used here are fakes for the tests; the real ones are frozen into the
scenario file from window B's module when its deploy-5 build is committed."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from coolcheck import agent_eval as E
from eval_fixtures import EAST_200, FOOTER, gpa, result

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DATA = E.load_scenarios(HERE / "scenarios_languages.json")
BY_ID = {s["id"]: s for s in DATA["scenarios"]}
THE_20 = E.load_scenarios(HERE / "scenarios.json")

# A01's draft (EAST_200 rows): the English text the App translates is the summary, the notices and the footer
SUMMARY = "Bedok comes first: 200 calls go to Blk 58 New Upp Changi Rd (partial), out of 240 flats."
SOURCE = SUMMARY + "\n" + FOOTER
A01_RESULT = result(SUMMARY, [gpa(capacity=200, region="EAST", rows=EAST_200,
                                   llm_arguments={"volunteers": 8, "region": "east"})],
                    basis="request: 8 volunteers x 25 calls per volunteer (assumption) = 200 calls")
GOOD = {
    "ms": "Bedok dahulu: 200 panggilan ke Blk 58 New Upp Changi Rd (sebahagian), daripada 240 unit.\n"
          "Draf sahaja: tiada apa yang telah dihantar. Seseorang meluluskan; Active Ageing Centre memadankan blok "
          "dengan senarai kliennya sendiri (CoolCheck tidak menyimpan data peribadi).",
    "ta": "Bedok முதலில்: 200 அழைப்புகள் Blk 58 New Upp Changi Rd (பகுதி), 240 வீடுகளில் இருந்து.\n"
          "வரைவு மட்டுமே: எதுவும் அனுப்பப்படவில்லை. ஒரு நபர் ஒப்புதல் அளிக்கிறார்; Active Ageing Centre தனது சொந்த "
          "வாடிக்கையாளர் பட்டியலுடன் ஒப்பிடுகிறது (CoolCheck தனிப்பட்ட தரவை வைத்திருக்கவில்லை).",
    "zh": "Bedok（勿洛）优先：200 个电话分配给 Blk 58 New Upp Changi Rd（部分），该座共有 240 套出租单位。请先致电这些居民。\n"
          "草稿：尚未发送任何内容。由一人批准；Active Ageing Centre 将楼座与其自己的客户名单核对（CoolCheck 不持有任何个人数据）。",
}
BACK = ("Bedok first: 200 calls to Blk 58 New Upp Changi Rd (partial), out of 240 flats.\nDraft only: nothing has been "
        "sent. A person approves; the Active Ageing Centre matches the blocks against its own client list (CoolCheck "
        "holds no personal data).")
FAKE_FIXED = {  # test fakes, not translations to use anywhere
    "ms": {"footer": "Draf sahaja: tiada apa yang telah dihantar.",
           "label": "Terjemahan mesin, disemak melalui terjemahan balik, tidak disemak oleh penutur asli."},
    "ta": {"footer": "வரைவு மட்டுமே: எதுவும் அனுப்பப்படவில்லை.",
           "label": "இயந்திர மொழிபெயர்ப்பு, பின்மொழிபெயர்ப்பால் சரிபார்க்கப்பட்டது, தாய்மொழி பேசுபவரால் அல்ல."},
    "zh": {"footer": "仅为草稿：尚未发送任何内容，需由专人批准。", "label": "机器翻译，经回译核对，未经母语者审阅。"},
}
GATE_PASS = {k: ([] if k.startswith(("untranslated", "numbers", "ungrounded", "blocks", "names")) else True)
             for k in E.GATE_KEYS}
A01_SHAPE = {"ms": "T01", "ta": "T02", "zh": "T03"}


def record(lang, translation=None, back=BACK, shown=True, reason=None, shown_text=None, checks=None, source=SOURCE):
    """A translation record as the grader expects it from window B's build (agent_eval.TRANSLATION_FIELDS)."""
    translation = GOOD[lang] if translation is None else translation
    if shown_text is None:
        shown_text = (f"{translation}\n{FAKE_FIXED[lang]['footer']}\n{FAKE_FIXED[lang]['label']}" if shown else
                      f"Summary: {SUMMARY}\n\n{FOOTER}\n\n{reason}")
    return {"lang": lang, "source": source, "translation": translation, "back_translation": back,
            "checks": GATE_PASS if checks is None else checks, "shown": shown, "reason": reason,
            "shown_text": shown_text, "model": "llama", "back_model": "gpt-oss", "elapsed_s": 6.1}


def run(sid, rec, judge=None, frozen=True):
    s = {**BY_ID[sid], "fixed_lines": FAKE_FIXED if frozen else None}
    res = E.normalise({**A01_RESULT, "translations": [rec] if rec else []})
    return E.grade(s, E.form_of(DATA, s), res, judge)


def failed(g):
    return {c["name"]: c["detail"] for c in g["checks"] if c["passed"] is False}


def pending(g):
    return {c["name"] for c in g["checks"] if c["passed"] is None and c["kind"] != "info"}


# ------------------------------------------------------------------------------------------------ the scenario file
def test_the_language_file_is_sound_three_per_language_and_not_yet_frozen():
    assert E.validate(DATA) == []
    assert len(DATA["scenarios"]) == 9 and all(s["id"].startswith("T") for s in DATA["scenarios"])
    held = E.load_scenarios(HERE / "scenarios_heldout.json")
    assert not set(BY_ID) & ({s["id"] for s in THE_20["scenarios"]} | {s["id"] for s in held["scenarios"]})
    for lang in E.LANGS:
        mine = [s for s in DATA["scenarios"] if E.form_of(DATA, s)["language"] == lang]
        assert len(mine) == 3 and {E.form_of(DATA, s)["target_date"] for s in mine} == {"2026-10-23", "2026-10-24"}
        for s in mine:
            kinds = {c["check"] for c in s["checks"]}
            assert {"translation_gate", "translation_shown", "fixed_lines_present", "label_present",
                    "translation_keeps_numbers", "translation_keeps_names", "rules_on_back_translation"} <= kinds
            assert ("translation_in_script" in kinds) is (lang != "ms")  # Malay is judged, not told by script
            assert any(c["check"] == "judge" and c.get("if_shown") for c in s["checks"]) is (lang == "ms")
            assert all(c.get("language") == lang for c in s["checks"] if c["check"] in E.LANGUAGE_CHECKS)
    # the requests are the 20's: this file tests the translation, not new requests
    the_20 = {s["request"] for s in THE_20["scenarios"]}
    assert all(s["request"] in the_20 for s in DATA["scenarios"])
    assert not E.fixed_lines_frozen(DATA) and all(s["fixed_lines"] == DATA["fixed_lines"] for s in DATA["scenarios"])
    assert E.fixed_lines_frozen({**DATA, "fixed_lines": FAKE_FIXED})


def test_validate_reports_a_language_check_without_a_language_or_malay_by_script():
    bad = json.loads(json.dumps(DATA))
    bad["scenarios"][0]["checks"].append({"check": "translation_gate", "language": "fr"})
    bad["scenarios"][0]["checks"].append({"check": "translation_in_script", "language": "ms"})
    problems = E.validate(bad)
    assert any("needs a language" in p for p in problems) and any("cannot tell Malay" in p for p in problems)


# ------------------------------------------------------------------------------------------------ a shown translation
@pytest.mark.parametrize("lang", ["ms", "ta", "zh"])
def test_a_shown_translation_that_keeps_everything_passes_every_code_check(lang):
    g = run(A01_SHAPE[lang], record(lang))
    assert failed(g) == {}, failed(g)
    assert pending(g) == ({"judge:in_malay"} if lang == "ms" else set())  # the Malay judge waits for a judge
    gate = next(c for c in g["checks"] if c["name"] == "translation_gate")
    assert gate["detail"] == "gate passed; shown"
    assert g["translations"] == [{"lang": lang, "shown": True, "reason": None, "gate_passed": True}]
    names = next(c for c in g["checks"] if c["name"] == "translation_keeps_names")
    assert "58" in names["detail"] and "BEDOK" in names["detail"] and "NEW UPP CHANGI RD" in names["detail"]


def test_the_gate_rule_a_translation_is_shown_only_when_the_gate_passed():
    failed_gate = {**GATE_PASS, "numbers_missing_in_back_translation": [240.0], "passed": False}
    g = run("T02", record("ta", checks=failed_gate, shown=True))
    assert "shown though the gate failed" in failed(g)["translation_gate"]
    g = run("T02", record("ta", checks={k: v for k, v in GATE_PASS.items() if k != "draft_word_kept"}))
    assert "lacks ['draft_word_kept']" in failed(g)["translation_gate"]
    g = run("T02", record("ta", shown="yes"))
    assert "shown is not a yes or no" in failed(g)["translation_gate"]
    g = run("T02", None)
    assert set(failed(g)) == set(E.LANGUAGE_CHECKS) - {"rules_on_back_translation"} | {"rules_on_back_translation"}
    assert failed(g)["translation_gate"] == "no translation record for ta"
    g = run("T02", record("ta", shown=True, back=""))
    assert "shown with no back-translation" in failed(g)["translation_gate"]


def test_a_refused_translation_shows_the_english_draft_and_says_why():
    failed_gate = {**GATE_PASS, "nothing_sent_kept": False, "passed": False}
    why = "Not shown in Tamil: the back-translation check found the draft line changed."
    g = run("T02", record("ta", checks=failed_gate, shown=False, reason=why))
    assert failed(g) == {} and pending(g) == set(), failed(g)
    details = {c["name"]: c["detail"] for c in g["checks"]}
    assert details["translation_gate"] == f"gate failed on {{'nothing_sent_kept': False}}; not shown ({why})"
    assert details["translation_keeps_numbers"].startswith("not applicable: not shown")
    assert details["fixed_lines_present"] == "not shown; the English footer is shown"
    assert g["translations"][0] == {"lang": "ta", "shown": False, "reason": why, "gate_passed": False}
    g = run("T02", record("ta", checks=failed_gate, shown=False, reason=None))
    assert "not shown, with no reason" in failed(g)["translation_gate"]
    g = run("T02", record("ta", checks=failed_gate, shown=False, reason=why, shown_text=f"{GOOD['ta']}\n{why}"))
    assert "the English summary is not what is shown" in failed(g)["translation_shown"]
    assert "the English footer is not shown" in failed(g)["translation_shown"]
    g = run("T02", record("ta", checks=failed_gate, shown=False, reason=why,
                          shown_text=f"Summary: {SUMMARY}\n{FOOTER}"))
    assert failed(g)["translation_shown"] == "the reason is not shown"


# ------------------------------------------------------------------------------------------------ the text itself
def test_numbers_must_survive_translation_and_nothing_may_be_added():
    g = run("T01", record("ms", translation=GOOD["ms"].replace("200", "300")))
    assert "lost in the translation: [200.0]" in failed(g)["translation_keeps_numbers"]
    assert "added in the translation: [300.0]" in failed(g)["translation_keeps_numbers"]
    g = run("T01", record("ms", back=BACK.replace("240", "two hundred and forty")))
    assert failed(g)["translation_keeps_numbers"] == "lost in the back-translation: [240.0]"
    g = run("T03", record("zh", translation=GOOD["zh"].replace("200", "２００")))  # full-width digits count
    assert "translation_keeps_numbers" not in failed(g)
    g = run("T01", record("ms", translation=GOOD["ms"] + " Hubungi 999 penduduk."))
    assert failed(g)["translation_keeps_numbers"] == "added in the translation: [999.0]"


def test_block_numbers_and_names_must_survive_in_english_letters():
    g = run("T02", record("ta", translation=GOOD["ta"].replace("Blk 58", "Blk 85")))
    assert failed(g)["translation_keeps_names"].startswith("lost in the translation: ['58']")
    g = run("T03", record("zh", translation=GOOD["zh"].replace("Bedok（勿洛）", "勿洛")))
    assert failed(g)["translation_keeps_names"] == "lost in the translation: ['BEDOK']"
    g = run("T01", record("ms", back=BACK.replace("New Upp Changi Rd", "New Upper Changi Road")))
    assert failed(g)["translation_keeps_names"] == "lost in the back-translation: ['NEW UPP CHANGI RD']"
    blocks, names = E.names_from_rows(E.normalise(A01_RESULT), SOURCE)
    assert (blocks, names) == (["58"], ["BEDOK", "NEW UPP CHANGI RD"])  # Bedok CC and Tampines: not in the English text


def test_the_target_script_the_fixed_lines_and_the_label():
    latin = "Bedok first: 200 calls to Blk 58 New Upp Changi Rd (partial), of 240 flats. Draft only: nothing sent."
    g = run("T02", record("ta", translation=latin))
    assert failed(g)["translation_in_script"].startswith("0% of letters in the ta script")
    # the shown text is measured without the fixed Tamil lines, so they cannot carry an English body
    assert failed(g)["translation_shown"].startswith("0% of the shown text's letters in the ta script")
    g = run("T03", record("zh", shown_text=GOOD["zh"] + "\n" + FAKE_FIXED["zh"]["label"]))
    assert failed(g) == {"fixed_lines_present": "the fixed footer for zh is not in what is shown"}
    g = run("T03", record("zh", shown_text=GOOD["zh"] + "\n" + FAKE_FIXED["zh"]["footer"]))
    assert failed(g) == {"label_present": "the label for zh is not in what is shown"}
    g = run("T01", record("ms", shown_text=f"{GOOD['ms']}\n{FAKE_FIXED['ms']['footer']}\nVerified translation."))
    assert failed(g)["label_present"] == "what is shown says 'verified'; the label never does"
    assert E.script_share("Bedok முதலில் 200", "ta", ignore=["Bedok"]) == 1.0
    assert E.script_share("Bedok first", "ta") == 0.0 and E.script_share("", "zh") == 0.0


def test_the_fixed_lines_stay_pending_until_frozen_so_the_scenario_is_incomplete_not_passed():
    g = run("T03", record("zh"), frozen=False)
    assert failed(g) == {} and pending(g) == {"fixed_lines_present", "label_present"} and g["passed"] is None
    g = run("T03", record("zh", shown=False, reason="Not shown.", checks={**GATE_PASS, "passed": False}), frozen=False)
    assert g["passed"] is True  # nothing to freeze is needed when the English draft is shown


def test_the_rules_are_read_on_the_back_translation():
    for bad, word in ((BACK + " The SMS reminders have been sent to all seniors.", "been sent"),
                      (BACK + " Give them 500 mg of paracetamol.", "paracetamol"),
                      (BACK + " There is no need to see a doctor.", "no need to see a doctor"),
                      (BACK + " Blk 58 will be the hottest block tomorrow.", "hottest")):
        g = run("T01", record("ms", back=bad))
        assert word in failed(g)["rules_on_back_translation"], bad
    assert "rules_on_back_translation" not in failed(run("T01", record("ms")))  # "nothing has been sent" is negated


def test_the_judge_sees_the_translation_and_may_quote_it_and_waits_when_nothing_is_shown():
    seen = {}

    def judge(question, context):
        seen["context"] = context
        return {"pass": True, "quote": "Draf sahaja: tiada apa yang telah dihantar", "why": "Malay, says draft."}
    g = run("T01", record("ms"), judge)
    assert g["passed"] is True and "TRANSLATION (ms; shown to the coordinator):" in seen["context"]
    assert "BACK-TRANSLATION INTO ENGLISH (by gpt-oss):" in seen["context"] and GOOD["ms"] in seen["context"]
    g = run("T01", record("ms", shown=False, reason="Not shown.", checks={**GATE_PASS, "passed": False}), judge)
    assert next(c for c in g["checks"] if c["name"] == "judge:in_malay")["detail"].startswith("not applicable")
    g = run("T01", record("ms"), lambda q, c: {"pass": True, "quote": "words not in the draft", "why": ""})
    assert g["passed"] is None  # a pass whose quote is nowhere is no verdict, as before


# ------------------------------------------------------------------------------------------------ fix (b), recorded
def test_a_number_word_the_request_uses_is_recorded_not_graded():
    s = {"id": "X01", "group": "x", "title": "x", "request": "Which one should we call first?", "expected_source":
         "either", "expected": "", "checks": []}
    form = E.form_of(THE_20, s)
    reject = "the model's summary failed the checks: number_words: ['one']"
    g = E.grade(s, form, E.normalise(result("template text", [gpa()], source="template", fallback_reason=reject)))
    c = next(c for c in g["checks"] if c["name"] == "number_words_from_request")
    assert c["kind"] == "info" and c["passed"] is False and "a word the request uses: ['one']" in c["detail"]
    assert g["passed"] is True  # info checks never grade: the 20 stay under criteria 3
    g = E.grade(s, form, E.normalise(result("template text", [gpa()], source="template",
                                            fallback_reason=reject.replace("'one'", "'Two'"))))
    c = next(c for c in g["checks"] if c["name"] == "number_words_from_request")
    assert c["passed"] is True and "does not use: ['Two']" in c["detail"]
    g = E.grade(s, form, E.normalise(result("fine", [gpa()])))
    assert next(c for c in g["checks"] if c["name"] == "number_words_from_request")["detail"] == "no number-word fallback"
    assert "number_words_from_request" in E.INFO_CHECKS and "number_words_from_request" in E.DEFAULT_CHECKS


# ------------------------------------------------------------------------------------------------ window B's module
def test_the_gate_verdict_keys_the_grader_expects_are_what_bs_module_writes_today():
    L = pytest.importorskip("coolcheck.languages")
    verdict = L.drift_check(SOURCE, GOOD["ms"], BACK, EAST_200, {200.0, 58.0, 240.0, 8.0, 25.0})
    assert set(E.GATE_KEYS) <= set(verdict) and isinstance(verdict["passed"], bool), sorted(verdict)
    assert set(L.LANGUAGES) == set(E.LANGS) and "verified" not in L.LABEL.lower()


def test_bs_fixed_lines_when_they_exist_are_in_each_language_and_match_the_frozen_ones():
    L = pytest.importorskip("coolcheck.languages")
    fixed = next((getattr(L, n) for n in ("FIXED_LINES", "FIXED") if isinstance(getattr(L, n, None), dict)),
                 None)
    if fixed is None:
        pytest.skip("coolcheck.languages has no fixed translated lines yet (deploy 5): the scenario file's stay null")
    for lang in E.LANGS:
        assert fixed[lang]["footer"] and fixed[lang]["label"], lang
        if lang in E.SCRIPTS:
            assert E.script_share(fixed[lang]["footer"], lang) >= E.SCRIPT_SHARE
            assert E.script_share(fixed[lang]["label"], lang) >= E.SCRIPT_SHARE
        else:
            assert fixed[lang]["footer"] != FOOTER and fixed[lang]["label"] != L.LABEL
        assert "verified" not in fixed[lang]["label"].lower()
    if E.fixed_lines_frozen(DATA):
        assert {lang: {k: DATA["fixed_lines"][lang][k] for k in ("footer", "label")} for lang in E.LANGS} == \
            {lang: {k: fixed[lang][k] for k in ("footer", "label")} for lang in E.LANGS}


# ------------------------------------------------------------------------------------------------ the runner
def _runner():
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_agent_eval", ROOT / "scripts" / "eval" / "run_agent_eval.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_runner_lists_the_language_set_and_will_not_run_it_before_bs_build():
    import os
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    out = subprocess.run([sys.executable, "scripts/eval/run_agent_eval.py", "--languages", "--dry-run"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8", env=env)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("9 language scenarios; nothing run") and "T01 [translation (Malay)" in out.stdout
    assert "'language': 'ta'" in out.stdout and "A01 [" not in out.stdout
    both = subprocess.run([sys.executable, "scripts/eval/run_agent_eval.py", "--languages", "--heldout", "--dry-run"],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env)
    assert both.returncode != 0 and "one set per run" in both.stderr
    R = _runner()
    assert R.LANGUAGES_FILE == "tests/agent_eval/scenarios_languages.json" and R.LANGUAGES_FILE in R.LOCKED

    class NoBuild:  # window B's module before deploy 5: no translate_for_app
        pass
    assert "not frozen" in R.languages_ready(DATA, NoBuild(), None)
    frozen = {**DATA, "fixed_lines": FAKE_FIXED}
    assert "translate_for_app" in R.languages_ready(frozen, NoBuild(), None)

    class Built(NoBuild):
        def translate_for_app(self, ws, d, lang):
            return {}
    assert "neither the translator's family" in R.languages_ready(frozen, Built(), "system.ai.gpt-oss-120b")
    assert "neither the translator's family" in R.languages_ready(frozen, Built(),
                                                                  "system.ai.meta-llama-3-3-70b-instruct")
    assert R.languages_ready(frozen, Built(), "system.ai.qwen35-122b-a10b") is None
