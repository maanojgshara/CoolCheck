"""wording_scan.py: the user's name is read at run time (WORDING_SCAN_NAMES, else git config user.name), is not written
in the script, and a file that holds it is still flagged. The scan runs as it does from the command line."""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCAN = ROOT / "scripts" / "checks" / "wording_scan.py"


def scan(path, names=None):
    env = {k: v for k, v in os.environ.items() if k != "WORDING_SCAN_NAMES"}
    if names is not None:
        env["WORDING_SCAN_NAMES"] = names
    return subprocess.run([sys.executable, "-I", str(SCAN), str(path)], capture_output=True, encoding="utf-8",
                          env=env, cwd=ROOT, check=True).stdout


def flagged(out):
    return re.findall(r"line (\d+) \[personal data or a user name in a repo file\]", out)


def git_first_name():
    words = subprocess.run(["git", "config", "user.name"], capture_output=True, encoding="utf-8",
                           cwd=ROOT).stdout.split()
    if not words or len(words[0]) < 3:
        pytest.skip("git config user.name is not set")
    return words[0]


def test_the_git_user_name_is_flagged_in_a_file(tmp_path):
    name = git_first_name()
    f = tmp_path / "note.md"
    f.write_text(f"Ask {name} first.\nThe folder C:/Users/{name.lower()}/notes.\nNothing personal here.\n",
                 encoding="utf-8")
    assert flagged(scan(f)) == ["1", "2"]


def test_the_script_does_not_spell_out_the_name():
    assert git_first_name().lower() not in SCAN.read_text(encoding="utf-8").lower()


def test_the_environment_variable_replaces_git_and_short_names_are_skipped(tmp_path):
    f = tmp_path / "note.md"
    f.write_text("Ask Quilla first.\nquilla.tan works here.\nNothing personal here.\n", encoding="utf-8")
    assert flagged(scan(f, names="Quilla, Al")) == ["1", "2"]  # "Al" would flag "personal" in line 3


def test_with_no_name_to_look_for_the_scan_says_so(tmp_path):
    f = tmp_path / "note.md"
    f.write_text("Nothing personal here.\n", encoding="utf-8")
    assert "no user name to look for" in scan(f, names="")
