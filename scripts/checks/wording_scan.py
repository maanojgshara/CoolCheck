"""Forbidden-wording scan for the submission drafts and the README. Prints each hit with its line, for a person to judge.
Rules come from the user's wording rules of 24 Oct 2026 and Guide A11. Usage, from the repo root:
python -I scripts/checks/wording_scan.py README.md docs/submission/writeup.md docs/submission/deck_outline.md"""
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

RULES = {
    "P(High) or a class probability as a number": [
        r"\bp_(high|low|moderate)\b",
        r"P\(\s*(High|Moderate|Low)\s*\)[^.\n]{0,30}\d",
        r"probabilit(y|ies) of (High|Moderate|Low)[^.\n]{0,60}\d\.\d",
        r"\bscore\b[^.\n]{0,30}= ?\d",
    ],
    "heat scale mixed with the tier scale": [
        r"\bMedium (heat|level|category|WBGT)",
        r"(heat|WBGT)[ -](level|category)?\s*(is|of|=)? ?Medium",
        r"\bModerate (tier|risk)\b",
        r"(tier|risk)( is| of)? Moderate\b",
        r"\bHigh[- ]risk heat",
        r"\bLow[- ]risk heat",
    ],
    "heat claimed for a block": [
        r"\bblocks?\b[^.\n]{0,50}\b(hottest|hotter|heat level|heat stress|WBGT)\b",
        r"\b(hottest|hotter|heat level|WBGT)\b[^.\n]{0,50}\bblocks?\b",
    ],
    "track record / overclaim": [
        r"track record", r"\blives? saved\b", r"\bsaves? lives\b", r"\bprevents?\b", r"\bavert", r"guarantee",
        r"proven", r"\bvalidated\b", r"practitioner[- ]reviewed", r"reviewed by a practitioner",
    ],
    "the briefing presented as ready, or sent automatically": [
        r"briefing (was|is) ready", r"sent automatically", r"automatically sent", r"auto-?send",
    ],
    "coverage overclaim": [r"every planning area", r"all 55 planning areas"],
    "Medium described as only a Moderate-day tier (High heat in a lower-third area is Medium too)": [
        r"heightened care (on|for) Moderate", r"Medium[^.\n]{0,40}(only|just) (on|for) Moderate",
    ],
    "old lead-time claim": [r"24-hour lead", r"evening before"],
    "personal data or a user name in a repo file": [
        r"[\w.+-]+@[\w-]+\.[\w.]+", r"maanoj", r"\[dev (?!<user>)[a-z]+\]",
    ],
}

for path in sys.argv[1:]:
    print(f"=== {path}")
    n = 0
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").split("\n"), 1):
        for rule, pats in RULES.items():
            for p in pats:
                if re.search(p, line, re.I if rule != "heat scale mixed with the tier scale" else 0):
                    print(f"  line {i} [{rule}] /{p}/ | {line.strip()[:170]}")
                    n += 1
                    break
    print(f"  hits: {n}")
