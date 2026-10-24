"""For each line of a draft, find the numbers and check each appears in a file the line cites (or the line
introducing its bullet list). Prints only numbers not found, for a person to check. Usage, from the repo root:
python -I scripts/checks/check_citations.py docs/submission/writeup.md [more files]"""
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
CITE = re.compile(r"`((?:checks|design|submission)/[\w./-]+\.md|datasets\.md|attribution\.md|build-log\.md|README\.md|"
                  r"scripts/[\w./-]+\.py)`")
NUM = re.compile(r"(?<![\w.§/-])(?:US\$)?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(%)?(?![\w/])")
SKIP_LINE = re.compile(r"^\s*(\d+\.\s+\"Contains information|>|#)")


def resolve(c):
    if c in ("README.md",) or c.startswith("scripts/"):
        return Path(c)
    return Path("docs") / c


cache = {}


def text_of(p):
    if p not in cache:
        cache[p] = p.read_text(encoding="utf-8") if p.exists() else ""
    return cache[p]


def found(num, files):
    plain = num.replace(",", "")
    for f in files:
        t = text_of(f)
        if num in t or (plain != num and plain in t):
            return True
        # 81.672 vs 81.67 etc. are not accepted; exact strings only
    return False


for draft in sys.argv[1:]:
    print(f"=== {draft}")
    inherited = []
    misses = 0
    for i, line in enumerate(Path(draft).read_text(encoding="utf-8").split("\n"), 1):
        if not line.strip():
            continue
        if line.startswith("#"):
            inherited = []
            continue
        if SKIP_LINE.match(line):
            continue
        cites = [resolve(c) for c in CITE.findall(line)]
        is_bullet = bool(re.match(r"^\s*[-*]\s", line))
        if not is_bullet:
            inherited = cites  # a paragraph or a list's lead line sets the context for the bullets after it
        files = cites or (inherited if is_bullet else [])
        body = re.sub(r"`[^`]*`", "", line)  # numbers inside code spans are file names, not claims
        body = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", body)  # list markers
        for m in NUM.finditer(body):
            num = m.group(1)
            if not files:
                print(f"  line {i}: {num} has no citation  | {line.strip()[:110]}")
                misses += 1
            elif not found(num, files):
                print(f"  line {i}: {num} not in {[str(f) for f in files]}  | {line.strip()[:90]}")
                misses += 1
    print(f"  flagged: {misses}")
