"""backfill.py against a fake HTTP session: no network, no real sleeping."""
import json
from datetime import date, datetime, time, timedelta

import pytest
import requests

import backfill as bf
from backfill import SGT

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=SGT)
KEY = "SECRET-TEST-KEY-7f3a9c"


class Resp:
    def __init__(self, status, content=b"", headers=None):
        self.status_code, self.content, self.headers = status, content, headers or {}


class FakeSession:
    """handler(url, params, n) -> Resp or an exception to raise; n counts calls from 1."""

    def __init__(self, handler):
        self.handler, self.calls, self.headers = handler, [], {}

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        r = self.handler(url, params or {}, len(self.calls))
        if isinstance(r, Exception):
            raise r
        return r


class Clock:
    def __init__(self):
        self.t, self.sleeps = 0.0, []

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s

    def __call__(self):
        return self.t


def wbgt_body(day, first, n, token=None, stations=("S124",)):
    recs = []
    for i in range(first, first + n):
        dt = datetime.combine(day, time(0), SGT) + timedelta(minutes=15 * i)
        recs.append({"datetime": dt.isoformat(), "updatedTimestamp": dt.isoformat(),
                     "item": {"type": "observation", "isStationData": True,
                              "readings": [{"station": {"id": s, "name": s, "townCenter": "x"},
                                            "location": {"latitude": 1.3, "longitude": 103.8},
                                            "wbgt": "30.1", "heatStress": "Low"} for s in stations]}})
    data = {"records": recs}
    if token:
        data["paginationToken"] = token
    return json.dumps({"code": 0, "data": data, "errorMsg": ""}, separators=(",", ":")).encode()


def full_day(url, params, n):
    """Two pages per day: 50 + 46 = 96 timestamps."""
    day = date.fromisoformat(params["date"])
    if "paginationToken" not in params:
        return Resp(200, wbgt_body(day, 0, 50, token="t2"))
    return Resp(200, wbgt_body(day, 50, 46))


def run(tmp_path, handler, *argv, env=None, now=NOW):
    sess, clock = FakeSession(handler), Clock()
    code = bf.main(["--out-dir", str(tmp_path / "out"), "--feeds", "wbgt", *argv],
                   session=sess, sleep=clock.sleep, clock=clock, now=now, env=env or {})
    return code, sess, clock, bf.State(tmp_path / "out")


def day_lines(state):
    return [json.loads(l) for l in state.progress.read_text(encoding="utf-8").splitlines() if '"event": "day"' in l]


def test_full_days_written_and_resume_skips(tmp_path):
    code, sess, clock, state = run(tmp_path, full_day, "--start", "2025-01-16", "--end", "2025-01-17")
    assert code == 0 and len(sess.calls) == 4
    assert sess.calls[1][1]["paginationToken"] == "t2" and sess.calls[1][1]["date"] == "2025-01-16"
    f = state.day_file("wbgt", date(2025, 1, 16))
    lines = f.read_bytes().splitlines()
    assert len(lines) == 2 and lines[0] == wbgt_body(date(2025, 1, 16), 0, 50, token="t2")
    recs = day_lines(state)
    assert [r["status"] for r in recs] == ["done", "done"] and recs[0]["distinct_on_day"] == 96
    assert recs[0]["sha256"] == __import__("hashlib").sha256(f.read_bytes()).hexdigest()
    assert all(s >= 1.0 - 1e-9 for s in clock.sleeps)  # only the 1 s gaps, no back-off
    code, sess, _, _ = run(tmp_path, full_day, "--start", "2025-01-16", "--end", "2025-01-17")
    assert code == 0 and sess.calls == []
    marker = json.loads((state.out / "raw" / "_meta" / "backfill_end.json").read_text())
    assert marker["wbgt"] == "2025-01-17"


def test_leftover_partial_is_deleted_and_day_refetched(tmp_path):
    state = bf.State(tmp_path / "out")
    part = state.raw_dir("wbgt") / "wbgt_2025-01-16.jsonl.partial"
    part.parent.mkdir(parents=True)
    part.write_bytes(b'{"half":')
    code, sess, _, _ = run(tmp_path, full_day, "--end", "2025-01-16")
    assert code == 0 and not part.exists() and len(sess.calls) == 2
    assert state.day_file("wbgt", date(2025, 1, 16)).exists()


def test_finished_file_without_progress_line_is_recorded_without_calls(tmp_path):
    state = bf.State(tmp_path / "out")
    f = state.day_file("wbgt", date(2025, 1, 16))
    f.parent.mkdir(parents=True)
    f.write_bytes(wbgt_body(date(2025, 1, 16), 0, 50, token="t2") + b"\n" + wbgt_body(date(2025, 1, 16), 50, 46) + b"\n")
    code, sess, _, _ = run(tmp_path, full_day, "--end", "2025-01-16")
    assert code == 0 and sess.calls == []
    (rec,) = day_lines(state)
    assert rec["status"] == "done" and rec["recovered"] is True and rec["calls"] == 0


def test_unfinished_file_without_progress_line_is_refetched(tmp_path):
    state = bf.State(tmp_path / "out")
    f = state.day_file("wbgt", date(2025, 1, 16))
    f.parent.mkdir(parents=True)
    f.write_bytes(wbgt_body(date(2025, 1, 16), 0, 50, token="t2") + b"\n")  # last page still has a token
    code, sess, _, _ = run(tmp_path, full_day, "--end", "2025-01-16")
    assert code == 0 and len(sess.calls) == 2 and day_lines(state)[0]["calls"] == 2


def test_short_day_and_first_partial_day(tmp_path):
    code, _, _, state = run(tmp_path, lambda u, p, n: Resp(200, wbgt_body(date(2025, 1, 16), 74, 22)), "--end", "2025-01-16")
    (rec,) = day_lines(state)
    assert code == 0 and rec["status"] == "short" and rec["distinct_on_day"] == 22


def test_429_backs_off_and_honours_retry_after(tmp_path):
    seq = [Resp(429), Resp(429, headers={"Retry-After": "7"}), None]

    def h(url, params, n):
        return seq[n - 1] if n <= 2 else Resp(200, wbgt_body(date.fromisoformat(params["date"]), 0, 96))

    code, sess, clock, state = run(tmp_path, h, "--end", "2025-01-16")
    assert code == 0 and len(sess.calls) == 3
    assert 5 in clock.sleeps and 7.0 in clock.sleeps
    assert day_lines(state)[0]["status"] == "done"


def test_persistent_429_stops_without_writing_the_day(tmp_path):
    code, sess, clock, state = run(tmp_path, lambda u, p, n: Resp(429), "--end", "2025-01-16")
    assert code == 1 and len(sess.calls) == 6
    assert [s for s in clock.sleeps if s > 1] == [5, 10, 20, 40, 80]
    assert not state.day_file("wbgt", date(2025, 1, 16)).exists()
    assert not list(state.raw_dir("wbgt").glob("*.partial"))
    end = [json.loads(l) for l in state.progress.read_text().splitlines() if '"run_end"' in l][-1]
    assert "429 persisted" in end["stopped"]


def test_429_on_most_recent_calls_stops(tmp_path):
    def h(url, params, n):  # two 429s, then success, for every day
        return Resp(429) if n % 3 else Resp(200, wbgt_body(date.fromisoformat(params["date"]), 0, 96))

    code, sess, _, state = run(tmp_path, h, "--end", "2025-03-31")
    end = [json.loads(l) for l in state.progress.read_text().splitlines() if '"run_end"' in l][-1]
    assert code == 1 and "of the last" in end["stopped"] and len(sess.calls) < 100


@pytest.mark.parametrize("statuses,env,reason", [
    ([401], {}, "401"),
    ([403, 403], {}, "403 twice"),
    ([403], {bf.KEY_ENV: KEY}, "key rejected"),
])
def test_auth_stops(tmp_path, statuses, env, reason):
    code, sess, _, state = run(tmp_path, lambda u, p, n: Resp(statuses[min(n, len(statuses)) - 1]), "--end", "2025-01-16", env=env)
    end = [json.loads(l) for l in state.progress.read_text().splitlines() if '"run_end"' in l][-1]
    assert code == 1 and reason in end["stopped"] and len(sess.calls) == len(statuses)


def test_404_is_no_data_and_retry_missing_refetches(tmp_path):
    code, _, _, state = run(tmp_path, lambda u, p, n: Resp(404, b'{"code":1,"errorMsg":"Data not found"}'), "--end", "2025-01-16")
    assert code == 0 and day_lines(state)[0]["status"] == "no_data"
    assert not state.day_file("wbgt", date(2025, 1, 16)).exists()
    code, sess, _, _ = run(tmp_path, full_day, "--end", "2025-01-16")
    assert sess.calls == []
    code, sess, _, _ = run(tmp_path, full_day, "--end", "2025-01-16", "--retry-missing")
    assert len(sess.calls) == 2 and day_lines(state)[-1]["status"] == "done"


def test_body_with_a_line_break_stops_before_writing(tmp_path):
    body = json.dumps({"code": 0, "data": {"records": []}}, indent=1).encode()
    code, _, _, state = run(tmp_path, lambda u, p, n: Resp(200, body), "--end", "2025-01-16")
    assert code == 1
    assert not state.raw_dir("wbgt").exists() or not any(state.raw_dir("wbgt").iterdir())
    assert "line break" in state.progress.read_text()


def test_single_trailing_newline_is_kept_unchanged(tmp_path):
    body = wbgt_body(date(2025, 1, 16), 0, 96) + b"\n"
    code, _, _, state = run(tmp_path, lambda u, p, n: Resp(200, body), "--end", "2025-01-16")
    assert code == 0 and state.day_file("wbgt", date(2025, 1, 16)).read_bytes() == body


def test_three_date_mismatches_in_a_row_stop(tmp_path):
    code, sess, _, state = run(tmp_path, lambda u, p, n: Resp(200, wbgt_body(date(2024, 1, 1), 0, 96)), "--end", "2025-01-25")
    assert code == 1 and len(sess.calls) == 3
    assert [r["status"] for r in day_lines(state)] == ["date_mismatch"] * 3


def test_dry_run_makes_no_calls(tmp_path, capsys):
    code, sess, _, _ = run(tmp_path, full_day, "--dry-run")
    assert code == 0 and sess.calls == []
    assert "642 days" in capsys.readouterr().out  # 2025-01-16 .. 2026-10-19


def test_end_date_rule():
    assert bf.default_end(datetime(2026, 10, 20, 0, 30, tzinfo=SGT)) == date(2026, 10, 18)
    assert bf.default_end(datetime(2026, 10, 20, 1, 0, tzinfo=SGT)) == date(2026, 10, 19)
    assert bf.default_end(datetime(2026, 10, 19, 17, 30, tzinfo=bf.ZoneInfo("UTC"))) == date(2026, 10, 19)  # 01:30 SGT on the 20th


def test_end_after_last_complete_day_is_refused(tmp_path):
    code, sess, _, _ = run(tmp_path, full_day, "--end", "2026-10-20")
    assert code == 2 and sess.calls == []


def test_out_dir_inside_repo_is_refused():
    assert bf.main(["--out-dir", str(bf.REPO / "data"), "--dry-run"], env={}) == 2


def test_key_is_sent_as_header_and_never_leaks(tmp_path, capsys):
    s = bf.make_session(KEY)
    assert s.headers[bf.KEY_HEADER] == KEY and bf.make_session(None).headers.get(bf.KEY_HEADER) is None

    def h(url, params, n):
        if n == 1:
            return requests.ConnectionError(f"failed while sending {KEY}")
        if params["date"] == "2025-01-17":
            return Resp(403, f'{{"errorMsg":"bad key {KEY}"}}'.encode())
        return Resp(200, wbgt_body(date.fromisoformat(params["date"]), 0, 96))

    code, _, _, state = run(tmp_path, h, "--end", "2025-01-17", env={bf.KEY_ENV: KEY})
    out = capsys.readouterr()
    assert code == 1 and "key rejected" in out.out and "key present" in out.out
    assert KEY not in out.out and KEY not in out.err
    for p in state.out.rglob("*"):
        if p.is_file():
            assert KEY.encode() not in p.read_bytes(), p


def test_log_scrubs_the_key(tmp_path, capsys):
    log = bf.Log(tmp_path / "x.log", secret=KEY)
    log(f"oops {KEY}")
    assert KEY not in capsys.readouterr().out and KEY not in (tmp_path / "x.log").read_text()
