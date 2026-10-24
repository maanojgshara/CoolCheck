"""Malay, Tamil and Chinese versions of a draft, with the back-translation check (Guide §14.2; docs/design/agent_app.md).

A draft's readable part (the summary, the notices and the footer) is translated by a model through the Unity Gateway,
then translated back into English by a model of another family, and checked in code:
- numbers: every number of the English text is in the translation and the back-translation (a lost or changed number
  is drift), and every number in the translation is found in the tool results or the inputs (coolcheck.agent's check);
- blocks and places: every block number, planning area, street and refuge name the English text uses is in the
  translation (kept in English letters, as Singapore addresses are written) and in the back-translation;
- the "nothing sent" line: the back-translation still says it is a draft and nothing has been sent.
This catches lost or changed facts, not unnatural wording or errors both models share; the label is "machine-translated,
checked by back-translation, not reviewed by a native speaker", never "verified". Python 3.11 compatible.
"""
import re

from coolcheck import agent as A
from coolcheck import plan as P

LANGUAGES = {"ms": "Malay (Bahasa Melayu, as used in Singapore)", "ta": "Tamil (as used in Singapore)",
             "zh": "Simplified Chinese (as used in Singapore)"}
LABEL = "Machine-translated, checked by back-translation, not reviewed by a native speaker."
BACK_MODEL = "system.ai.gpt-oss-120b"

TRANSLATE = """Translate the text below from English into {language}, for a community care team in Singapore.
Rules:
- Translate every sentence faithfully, including the last lines: add nothing, leave nothing out, no notes.
- The line saying the plan is a draft and nothing has been sent must keep exactly that meaning: a draft, and nothing
  has been sent.
- Write every number with the same digits 0-9 as the English text; never write a number as a word.
- Keep block numbers (for example 208A), street names, planning area names and refuge names in English letters exactly
  as written. You may add the name in {language} in brackets after the English name.
- Plain text only."""

BACK = """Translate the text below into English, faithfully and literally. Keep every block number and name as written
and write every number as digits. Plain text only, no notes."""

THINK = re.compile(r"<think>.*?</think>", re.S)
NOTHING_SENT = re.compile(r"(nothing|not|no)\b[^.]{0,40}\bsent|\bunsent\b|\bnot yet (been )?sent", re.I)
DRAFT = re.compile(r"\bdraft", re.I)


def message_text(resp):
    """The reply's text: a string, or the text parts of a list (reasoning models), without <think> blocks."""
    content = resp["choices"][0]["message"].get("content")
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") in ("text", None))
    return THINK.sub("", content or "").strip()


# Thinking models (checked 24 Oct): Qwen 3.5 spent 4,000 tokens thinking about one line with no setting, and returns
# straight away with reasoning_effort "none"; GPT-OSS finishes back-translations at "low".
EFFORT = {"qwen35": "none", "gpt-oss": "low"}


def chat_text(ws, model, system, text, max_tokens=4000):
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}],
            "max_tokens": max_tokens, "temperature": 0}
    effort = next((v for k, v in EFFORT.items() if k in model), None)
    if effort:
        body.update(reasoning_effort=effort, max_tokens=max(max_tokens, 8000))
    resp = ws.api_client.do("POST", A.GATEWAY_PATH, body=body)
    if resp["choices"][0].get("finish_reason") == "length":
        raise RuntimeError(f"{model} hit max_tokens before finishing")
    return message_text(resp)


def readable_text(d):
    """The part of a draft that is translated: the summary, the notices and the footer."""
    return "\n".join([d.summary_text] + [f"Note: {n}" for n in d.notices] + [P.FOOTER])


def _present(token, text):
    return re.search(rf"(?<![0-9A-Za-z]){re.escape(token)}(?![0-9A-Za-z])", text, re.I) is not None


def names_in(source, rows):
    """Block numbers and names (planning areas, streets, refuges) of the tool rows that the English text uses."""
    blocks, names = set(), set()
    for r in rows:
        names.add(P.area_name(r["planning_area"]))
        for b in r.get("blocks") or []:
            blocks.add(b["blk_no"])
            names.update({b["street"], b.get("refuge_main_name") or ""})
    return (sorted(b for b in blocks if _present(b, source)),
            sorted(n for n in names if n and re.search(re.escape(n), source, re.I)))


def _multiset_missing(source_nums, other_nums):
    left = list(other_nums)
    missing = []
    for n in source_nums:
        if n in left:
            left.remove(n)
        else:
            missing.append(n)
    return missing


def numbers_of(text):
    return [v for v in (A._num(m) for m in A.NUMBER.findall(text)) if v is not None]


def untranslated(source, translation):
    """English sentences of four words or more copied unchanged into the translation."""
    parts = [s.strip() for s in re.split(r"(?<=[.;])\s+|\n", source)]
    return [s for s in parts if len(s.split()) >= 4 and s in translation]


def drift_check(source, translation, back, rows, sources):
    """The checks on one translation; 'passed' is False on any drift. sources: the numbers of the tool results and inputs."""
    src_nums = numbers_of(source)
    blocks, names = names_in(source, rows)
    ok_grounded, grounding = A.check_summary(translation, sources)
    out = {
        "untranslated_sentences": untranslated(source, translation),
        "numbers_missing_in_translation": _multiset_missing(src_nums, numbers_of(translation)),
        "numbers_missing_in_back_translation": _multiset_missing(src_nums, numbers_of(back)),
        "ungrounded_numbers_in_translation": grounding["ungrounded_numbers"],
        "blocks_missing_in_translation": [b for b in blocks if not _present(b, translation)],
        "blocks_missing_in_back_translation": [b for b in blocks if not _present(b, back)],
        "names_missing_in_translation": [n for n in names if not re.search(re.escape(n), translation, re.I)],
        "names_missing_in_back_translation": [n for n in names if not re.search(re.escape(n), back, re.I)],
        "nothing_sent_kept": bool(NOTHING_SENT.search(back)),
        "draft_word_kept": bool(DRAFT.search(back)),
    }
    out["passed"] = (not any(v for k, v in out.items()
                             if k.startswith(("untranslated_", "numbers_", "ungrounded_", "blocks_", "names_")))
                     and out["nothing_sent_kept"] and out["draft_word_kept"])
    return out


def draft_sources(d):
    """The numbers a translation of draft d may use: the tool results, the inputs, the date and the English text."""
    return A.source_numbers([c.rows for c in d.tool_calls], d.target_date.isoformat(), d.target_date.strftime("%d %m %Y"),
                            d.call_capacity, d.capacity_basis, d.forecast.get("scored_at_sgt"), 400, readable_text(d))


def translate_text(ws, source, lang, rows, sources, model=A.MODEL, back_model=BACK_MODEL):
    """One language for one English text: the translation, its back-translation and the checks."""
    translation = chat_text(ws, model, TRANSLATE.format(language=LANGUAGES[lang]), source)
    masked, _ = P.mask_personal(translation)  # a model must never add personal data; masked like a request if it did
    back = chat_text(ws, back_model, BACK, masked)
    return {"lang": lang, "model": model, "back_model": back_model, "source": source, "translation": masked,
            "back_translation": back, "checks": drift_check(source, masked, back, rows, sources)}


def translate_draft(ws, d, lang, model=A.MODEL, back_model=BACK_MODEL):
    return translate_text(ws, readable_text(d), lang, d.rows, draft_sources(d), model, back_model)
