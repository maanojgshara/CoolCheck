"""Local tests for the language checks (coolcheck.languages) and, per language, the number check and the masking that
run on every language: Malay, Tamil and Chinese text, no model needed.
"""
import pytest

from coolcheck import agent as A
from coolcheck import languages as L
from coolcheck import plan as P
from plan_fixtures import ROWS_24

SRC = ("Toa Payoh is High. Call Blk 208A Woodleigh Link first: 200 calls of 312 flats. Bidadari CC is about 450 m away "
       "in a straight line.\nDraft only: nothing has been sent.")
SOURCES = A.source_numbers(ROWS_24, "2026-10-24", "24 10 2026", 200, SRC)

GOOD = {
    "ms": "Toa Payoh adalah Tinggi. Hubungi Blk 208A Woodleigh Link dahulu: 200 panggilan daripada 312 flat. Bidadari CC "
          "kira-kira 450 m jauhnya dalam garis lurus.\nDraf sahaja: tiada apa-apa yang telah dihantar.",
    "ta": "Toa Payoh உயர் நிலையில் உள்ளது. முதலில் Blk 208A Woodleigh Link-ஐ அழைக்கவும்: 312 வீடுகளில் 200 அழைப்புகள். "
          "Bidadari CC நேர்கோட்டில் சுமார் 450 மீ தொலைவில் உள்ளது.\nவரைவு மட்டும்: எதுவும் அனுப்பப்படவில்லை.",
    "zh": "Toa Payoh为高级。先致电Blk 208A Woodleigh Link：312个单位中的200个电话。Bidadari CC直线距离约450米。\n仅为草稿：尚未发送任何内容。",
}
BACK = ("Toa Payoh is High. First call Blk 208A Woodleigh Link: 200 calls out of 312 flats. Bidadari CC is about 450 m "
        "away in a straight line.\nDraft only: nothing has been sent.")


@pytest.mark.parametrize("lang", ["ms", "ta", "zh"])
def test_good_translation_passes(lang):
    c = L.drift_check(SRC, GOOD[lang], BACK, ROWS_24, SOURCES)
    assert c["passed"], c


@pytest.mark.parametrize("lang,bad,field", [
    ("ms", GOOD["ms"].replace("200", "300"), "numbers_missing_in_translation"),
    ("ta", GOOD["ta"].replace("208A", "208"), "blocks_missing_in_translation"),
    ("zh", GOOD["zh"].replace("Bidadari CC", "比达达利民众俱乐部"), "names_missing_in_translation"),
    ("zh", GOOD["zh"].replace("200个", "两百个"), "numbers_missing_in_translation"),  # a number written in Chinese words
])
def test_drift_is_caught(lang, bad, field):
    c = L.drift_check(SRC, bad, BACK, ROWS_24, SOURCES)
    assert not c["passed"] and c[field], c


def test_lost_nothing_sent_line_is_caught():
    c = L.drift_check(SRC, GOOD["ms"], BACK.replace("Draft only: nothing has been sent.", "Plan approved."), ROWS_24, SOURCES)
    assert not c["passed"] and c["nothing_sent_kept"] is False and c["draft_word_kept"] is False


def test_proposal_for_draft_is_reported_apart_from_nothing_sent():
    c = L.drift_check(SRC, GOOD["ta"], BACK.replace("Draft only: nothing has been sent.", "Proposal only: Nothing is sent."),
                      ROWS_24, SOURCES)
    assert c["nothing_sent_kept"] is True and c["draft_word_kept"] is False and not c["passed"]


def test_untranslated_english_sentence_is_caught():
    bad = GOOD["ms"].replace("Draf sahaja: tiada apa-apa yang telah dihantar.", "Draft only: nothing has been sent.")
    c = L.drift_check(SRC, bad, BACK, ROWS_24, SOURCES)
    assert c["untranslated_sentences"] == ["Draft only: nothing has been sent."] and not c["passed"]


@pytest.mark.parametrize("lang", ["ms", "ta", "zh"])
def test_number_check_per_language(lang):
    assert A.check_summary(GOOD[lang], SOURCES)[0]
    ok, checks = A.check_summary(GOOD[lang].replace("312", "321"), SOURCES)
    assert not ok and "321" in checks["ungrounded_numbers"]


def test_full_width_digits_count_as_numbers():
    assert A.check_summary("先致电208A座：３１２个电话。", SOURCES)[0]
    assert not A.check_summary("先致电208A座：３２１个电话。", SOURCES)[0]


@pytest.mark.parametrize("text,want", [
    ("Hubungi S1234567D di 91234567 esok.", "Hubungi [NRIC masked] di [phone masked] esok."),
    ("S1234567D என்பவரை 91234567 இல் அழைக்கவும்.", "[NRIC masked] என்பவரை [phone masked] இல் அழைக்கவும்."),
    ("请致电陈女士S1234567D，电话91234567。", "请致电陈女士[NRIC masked]，电话[phone masked]。"),
])
def test_masking_per_language(text, want):
    assert P.mask_personal(text)[0] == want


def test_message_text_handles_reasoning_parts_and_think_blocks():
    assert L.message_text({"choices": [{"message": {"content": [{"type": "reasoning", "summary": "x"},
                                                                 {"type": "text", "text": "Hai"}]}}]}) == "Hai"
    assert L.message_text({"choices": [{"message": {"content": "<think>hmm</think>\nHello"}}]}) == "Hello"
