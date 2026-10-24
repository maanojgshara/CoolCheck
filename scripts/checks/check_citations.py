"""For each line of a draft, find the numbers and check each appears in a file the line cites (or, for a bullet, the
nearest bullet it is nested under that cites one, else the line introducing its list). Prints only numbers not found,
for a person to check. Usage, from the repo root:
python -I scripts/checks/check_citations.py docs/submission/writeup.md [more files]

Flags a person has judged are in citations_allowlist.tsv beside this script, one per (draft, number, line): the line is
keyed by the sha1 of its stripped text, so an edited line is flagged again. Allowed flags are counted, not printed, and
allowlist entries that no longer match a line are listed as stale."""
import csv
import hashlib
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ALLOWLIST = Path(__file__).with_name("citations_allowlist.tsv")


def line_key(line):
    return hashlib.sha1(line.strip().encode("utf-8")).hexdigest()[:12]


allowed = {}
if ALLOWLIST.exists():
    with ALLOWLIST.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            allowed[(row["draft"], row["number"], row["line_sha1"])] = row["reason"]
used = set()
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
    draft_key = Path(draft).as_posix()
    inherited = []
    parents = []
    misses = 0
    n_allowed = 0
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
            parents = []
            files = cites
        else:
            # a bullet with citations sets the context for the bullets nested under it
            indent = len(line) - len(line.lstrip())
            parents = [(n, c) for n, c in parents if n < indent]
            ancestor = next((c for n, c in reversed(parents) if c), [])
            files = cites or ancestor or inherited
            parents.append((indent, cites))
        body = re.sub(r"`[^`]*`", "", line)  # numbers inside code spans are file names, not claims
        body = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", body)  # list markers
        for m in NUM.finditer(body):
            num = m.group(1)
            key = (draft_key, num, line_key(line))
            if (not files or not found(num, files)) and key in allowed:
                used.add(key)
                n_allowed += 1
                continue
            if not files:
                print(f"  line {i}: {num} has no citation  | {line.strip()[:110]}")
                misses += 1
            elif not found(num, files):
                print(f"  line {i}: {num} not in {[str(f) for f in files]}  | {line.strip()[:90]}")
                misses += 1
    print(f"  flagged: {misses}, allowed: {n_allowed}")
drafts = {Path(d).as_posix() for d in sys.argv[1:]}
stale = sorted(k for k in allowed if k[0] in drafts and k not in used)
for d, num, sha in stale:
    print(f"stale allowlist entry: {d} {num} {sha} ({allowed[(d, num, sha)]})")
