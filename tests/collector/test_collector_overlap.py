"""collector_overlap.py on two collector runs made against the fake API, 15 minutes apart."""
from datetime import datetime

import collect as C
import collector_overlap as O
from fake_api import UTC, Clock, FakeAPI, FakeSession

T1 = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)   # 18:00 SGT
T2 = datetime(2026, 10, 21, 10, 15, tzinfo=UTC)  # 18:15 SGT
CHANGED = datetime(2026, 10, 21, 17, 0, tzinfo=C.SGT)  # a WBGT reading both runs carry


def two_runs(tmp_path, revise):
    out = tmp_path / "out"
    for i, now in enumerate((T1, T2), 1):
        value = (lambda f, ts: "31.0" if revise and i == 2 and f == "wbgt" and ts == CHANGED else
                 ("30.1" if f == "wbgt" else 0))
        clock = Clock()
        assert C.main(["--dry-run", "--out-dir", str(out)], session=FakeSession(FakeAPI(now, value)), sleep=clock.sleep,
                      clock=clock, now=now, env={"GITHUB_RUN_ID": str(i)}) == 0
    return out


def test_identical_overlap_is_all_duplicates(tmp_path):
    md, totals = O.report(O.LocalSource(two_runs(tmp_path, revise=False)))
    assert totals["conflicts"] == 0
    assert "| wbgt | 25 | 25 | 24 | 1 | 1 | 24 | 0 |" in md  # one new reading at 18:15, one dropped at 12:00
    assert "| rainfall | 25 | 25 | 22 | 3 | 3 | 22 | 0 |" in md
    assert "| forecast | 3 | 3 | 3 | 0 | 0 | 3 | 0 |" in md


def test_a_revised_value_is_a_conflict_with_the_field_shown(tmp_path):
    md, totals = O.report(O.LocalSource(two_runs(tmp_path, revise=True)), "2026-10-21T180000_1", "2026-10-21T181500_2")
    assert totals["conflicts"] == 1
    assert "| wbgt | 25 | 25 | 24 | 1 | 1 | 23 | 1 |" in md
    assert '| wbgt | S124 2026-10-21T17:00:00+08:00 | wbgt | "30.1" | "31.0" |' in md
