"""collect.py against a fake data.gov.sg: no network, no real sleeping, no Databricks."""
from datetime import date, datetime

import pytest

import backfill as bf
import collect as C
from fake_api import UTC, Clock, FakeAPI, FakeSession, Resp, feed_of

KEY = "SECRET-TEST-KEY-7f3a9c"
CLIENT_SECRET = "dose-TEST-CLIENT-SECRET-91b2"
ROOT = "/Volumes/coolcheck/bronze/raw_files"
REAL_ENV = {C.ROOT_ENV: ROOT, "DATABRICKS_HOST": "https://example.cloud.databricks.com",
            "DATABRICKS_CLIENT_ID": "client-id", "DATABRICKS_CLIENT_SECRET": CLIENT_SECRET}


def at_utc(*a):
    return datetime(*a, tzinfo=UTC)


def run(tmp_path, now, handler=None, *argv, env=None, uploader=None, clock=None):
    api = handler or FakeAPI(now)
    sess, clock = FakeSession(api), clock or Clock()
    env = {"GITHUB_RUN_ID": "777", **(env or {})}
    code = C.main(["--out-dir", str(tmp_path / "out"), *argv], session=sess, sleep=clock.sleep, clock=clock,
                  now=now, env=env, uploader=uploader)
    return code, api, sess, clock


def files(tmp_path):
    return sorted(p.relative_to(tmp_path / "out").as_posix() for p in (tmp_path / "out").rglob("*.jsonl"))


# ---- layout, SGT and the pages read ----

def test_layout_name_and_lines_unchanged(tmp_path):
    now = at_utc(2026, 10, 21, 10, 27, 18)  # 18:27:18 SGT
    code, api, sess, _ = run(tmp_path, now, None, "--dry-run")
    assert code == 0
    assert files(tmp_path) == [f"{f}/live/2026-10-21/{f}_2026-10-21T182718_777.jsonl"
                               for f in ("air_temperature", "forecast", "rainfall", "wbgt")]
    assert all("/backfill/" not in f for f in files(tmp_path))
    assert [(feed_of(u), p["date"]) for u, p in sess.calls][:3] == [("wbgt", "2026-10-21"), ("forecast", "2026-10-21"),
                                                                     ("rainfall", "2026-10-21")]
    served = api(bf.FEEDS["rainfall"][0], {"date": "2026-10-21"}, 0).content
    assert (tmp_path / "out" / files(tmp_path)[2]).read_bytes() == served + b"\n"  # the body, unchanged, one line


def test_2355_sgt_reads_today_only(tmp_path):
    now = at_utc(2026, 10, 21, 15, 55)  # 23:55 SGT on 21 Oct (still 21 Oct in UTC too)
    code, api, _, _ = run(tmp_path, now, None, "--dry-run")
    assert code == 0
    assert {d for _, d, _ in api.log} == {date(2026, 10, 21)}
    assert files(tmp_path)[1] == "forecast/live/2026-10-21/forecast_2026-10-21T235500_777.jsonl"


def test_0005_sgt_is_the_next_day_and_sweeps_every_page_of_yesterday(tmp_path):
    now = at_utc(2026, 10, 21, 16, 5)  # 00:05 SGT on 22 Oct, while UTC is still 21 Oct
    code, api, _, _ = run(tmp_path, now, None, "--dry-run")
    assert code == 0
    today, yesterday = date(2026, 10, 22), date(2026, 10, 21)
    assert files(tmp_path)[1] == "forecast/live/2026-10-22/forecast_2026-10-22T000500_777.jsonl"
    assert api.pages("wbgt", today) == [1] and api.pages("rainfall", today) == [1]
    assert api.pages("forecast", today) == [1]  # 404: no issue yet today, which is not an error
    assert api.pages("wbgt", yesterday) == [1, 2, 3, 4]  # 96 readings, all pages, though page 1 covers the window
    assert api.pages("rainfall", yesterday) == list(range(1, 13))  # 288 readings
    assert api.pages("forecast", yesterday) == [1]
    lines = (tmp_path / "out" / "rainfall/live/2026-10-22/rainfall_2026-10-22T000500_777.jsonl").read_bytes().splitlines()
    assert len(lines) == 13  # today's page, then yesterday's 12


def test_0105_sgt_reads_yesterday_back_to_the_window_only(tmp_path):
    now = at_utc(2026, 10, 21, 17, 5)  # 01:05 SGT on 22 Oct: window back to 23:05 on 21 Oct, no sweep
    code, api, _, _ = run(tmp_path, now, None, "--dry-run")
    assert code == 0
    yesterday = date(2026, 10, 21)
    assert api.pages("wbgt", yesterday) == [1] and api.pages("rainfall", yesterday) == [1]
    assert api.pages("forecast", yesterday) == [1]


def test_plan_hour_zero_and_catch_up():
    sgt = C.SGT
    assert C.plan(datetime(2026, 10, 22, 0, 49, tzinfo=sgt), 2) == [
        (date(2026, 10, 22), datetime(2026, 10, 21, 22, 49, tzinfo=sgt)), (date(2026, 10, 21), None)]
    assert C.plan(datetime(2026, 10, 22, 1, 0, tzinfo=sgt), 0.5) == [
        (date(2026, 10, 22), datetime(2026, 10, 22, 0, 30, tzinfo=sgt))]
    assert [d for d, _ in C.plan(datetime(2026, 10, 22, 10, 0, tzinfo=sgt), 48)] == [
        date(2026, 10, 22), date(2026, 10, 21), date(2026, 10, 20)]


def test_wider_window_follows_tokens_until_covered(tmp_path):
    now = at_utc(2026, 10, 21, 10, 27)  # 18:27 SGT, window back to 12:27
    code, api, _, _ = run(tmp_path, now, None, "--dry-run", "--window-hours", "6")
    assert code == 0
    assert api.pages("wbgt", date(2026, 10, 21)) == [1]  # 25 x 15 min reaches 12:15
    assert api.pages("rainfall", date(2026, 10, 21)) == [1, 2, 3]  # 25 x 5 min per page


# ---- throttle and stops ----

def test_429_waits_a_fixed_11_s_then_succeeds(tmp_path):
    now = at_utc(2026, 10, 21, 10, 27)
    api = FakeAPI(now)
    seq = iter([Resp(429), Resp(429)])
    code, _, sess, clock = run(tmp_path, now, lambda u, p, n: next(seq, None) or api(u, p, n), "--dry-run")
    assert code == 0 and len(sess.calls) == 10  # 3 feeds + 5 air-temperature pages + the 2 retried calls
    assert [s for s in clock.sleeps if s > 1.0] == [11, 11]
    assert all(s <= 1.0 for s in clock.sleeps if s not in (11,))  # the rest is the 1 s gap


def test_persistent_429_stops_the_run_and_keeps_what_was_fetched(tmp_path):
    now = at_utc(2026, 10, 21, 10, 27)
    api = FakeAPI(now)
    handler = lambda u, p, n: Resp(429) if feed_of(u) == "forecast" else api(u, p, n)  # noqa: E731
    code, _, sess, _ = run(tmp_path, now, handler, "--dry-run")
    assert code == 1
    assert [feed_of(u) for u, _ in sess.calls] == ["wbgt"] + ["forecast"] * 3  # 2 retries, rainfall never called
    assert files(tmp_path) == ["wbgt/live/2026-10-21/wbgt_2026-10-21T182700_777.jsonl"]
    assert "STOPPED: HTTP 429 persisted through 2 retries" in (tmp_path / "out" / "collector.log").read_text()


def test_three_429s_in_a_run_stop_before_the_next_call(tmp_path):
    now = at_utc(2026, 10, 21, 10, 27)
    api = FakeAPI(now)
    seq = {1: Resp(429), 2: Resp(429), 4: Resp(429)}  # wbgt: 429, 429, ok; forecast: 429, ok
    code, _, sess, _ = run(tmp_path, now, lambda u, p, n: seq.get(n) or api(u, p, n), "--dry-run")
    assert code == 1
    assert [feed_of(u) for u, _ in sess.calls] == ["wbgt"] * 3 + ["forecast"] * 2
    assert "3 HTTP 429s this run" in (tmp_path / "out" / "collector.log").read_text()


def test_404_on_page_two_fails_that_feed_only(tmp_path):
    now = at_utc(2026, 10, 21, 10, 27)
    api = FakeAPI(now)
    handler = lambda u, p, n: (Resp(404, b"{}") if feed_of(u) == "rainfall" and "paginationToken" in p  # noqa: E731
                               else api(u, p, n))
    code, _, _, _ = run(tmp_path, now, handler, "--dry-run", "--window-hours", "6")
    assert code == 1
    assert len(files(tmp_path)) == 4  # rainfall keeps its first page; the run is marked failed
    log = (tmp_path / "out" / "collector.log").read_text()
    assert "rainfall 2026-10-21: HTTP 404 on page 2" in log


def _today_missing(api, feeds, today):
    """404 on today's date for `feeds`, as if NEA had published nothing today."""
    return lambda u, p, n: (Resp(404, b'{"code":17,"data":null,"errorMsg":"Data not found"}')
                            if feed_of(u) in feeds and p["date"] == today else api(u, p, n))


def test_0030_sgt_404_on_today_is_no_data_for_every_feed(tmp_path):
    now = at_utc(2026, 10, 21, 16, 30)  # 00:30 SGT on 22 Oct
    code, _, _, _ = run(tmp_path, now, _today_missing(FakeAPI(now), {"wbgt", "rainfall", "forecast", "air_temperature"}, "2026-10-22"),
                        "--dry-run")
    assert code == 0
    log = (tmp_path / "out" / "collector.log").read_text()
    assert log.count("no data ['2026-10-22']") == 4 and "failed" not in log


@pytest.mark.parametrize("feed", ["wbgt", "rainfall", "air_temperature"])
def test_0300_sgt_404_on_today_fails_wbgt_rainfall_or_air_temperature(tmp_path, feed):
    now = at_utc(2026, 10, 21, 19, 0)  # 03:00 SGT on 22 Oct; the fake forecast's first issue is 05:30, so it 404s too
    api = FakeAPI(now)
    code, _, _, _ = run(tmp_path, now, _today_missing(api, {feed}, "2026-10-22"), "--dry-run")
    assert code == 1
    log = (tmp_path / "out" / "collector.log").read_text()
    assert f"failed: {feed} 2026-10-22: HTTP 404 on page 1" in log
    assert log.count("failed:") == 1  # the forecast's 404 today is still no data, and the other feed is fine
    forecast = next(ln for ln in log.splitlines() if " forecast: " in ln)
    assert "no data ['2026-10-22']" in forecast and forecast.endswith(": ok")
    other = "rainfall" if feed == "wbgt" else "wbgt"
    assert api.pages(other, date(2026, 10, 22)) == [1]


def test_time_budget_stops_the_run(tmp_path):
    now = at_utc(2026, 10, 21, 10, 27)
    api, clock = FakeAPI(now), Clock()

    def slow(u, p, n):
        clock.t += 200
        return api(u, p, n)
    code, _, sess, _ = run(tmp_path, now, slow, "--dry-run", clock=clock)
    assert code == 1 and len(sess.calls) == 1
    assert "time budget of 180 s spent" in (tmp_path / "out" / "collector.log").read_text()


# ---- upload, dry run, usage ----

def test_real_run_uploads_each_file_to_the_volume_root(tmp_path):
    sent = []
    code, _, _, _ = run(tmp_path, at_utc(2026, 10, 21, 10, 27), None, env=REAL_ENV,
                        uploader=lambda dest, data: sent.append((dest, len(data))))
    assert code == 0
    assert [d for d, _ in sent] == [f"{ROOT}/{f}/live/2026-10-21/{f}_2026-10-21T182700_777.jsonl"
                                    for f in ("wbgt", "forecast", "rainfall", "air_temperature")]
    assert all(n > 0 for _, n in sent)


def test_dry_run_never_uploads(tmp_path):
    def boom(dest, data):
        raise AssertionError("dry run uploaded")
    code, _, _, _ = run(tmp_path, at_utc(2026, 10, 21, 10, 27), None, "--dry-run", uploader=boom)
    assert code == 0


def test_upload_failure_marks_the_run_failed_and_the_other_feeds_still_upload(tmp_path):
    sent = []

    def flaky(dest, data):
        if "/forecast/" in dest:
            raise RuntimeError("RESOURCE_ALREADY_EXISTS")
        sent.append(dest)
    code, _, _, _ = run(tmp_path, at_utc(2026, 10, 21, 10, 27), None, env=REAL_ENV, uploader=flaky)
    assert code == 1 and len(sent) == 3


@pytest.mark.parametrize("argv, env, why", [
    ([], {**REAL_ENV, C.ROOT_ENV: "/Volumes/coolcheck/bronze/raw_files/"}, None),  # a trailing slash is trimmed
    ([], {**REAL_ENV, C.ROOT_ENV: "/tmp/raw_files"}, "must look like /Volumes"),
    ([], {k: v for k, v in REAL_ENV.items() if k != "DATABRICKS_CLIENT_SECRET"}, "not set: DATABRICKS_CLIENT_SECRET"),
    (["--dry-run", "--window-hours", "0"], {}, "--window-hours"),
    (["--dry-run", "--window-hours", "49"], {}, "--window-hours"),
])
def test_usage_checks(tmp_path, capsys, argv, env, why):
    code = C.main(["--out-dir", str(tmp_path / "out"), *argv], session=FakeSession(FakeAPI(at_utc(2026, 10, 21, 10, 27))),
                  sleep=Clock().sleep, clock=Clock(), now=at_utc(2026, 10, 21, 10, 27), env=env,
                  uploader=(lambda d, b: None) if why is None else None)
    if why is None:
        assert code == 0
    else:
        assert code == 2 and why in capsys.readouterr().err


@pytest.mark.parametrize("out", [bf.REPO / "tmp_collector", bf.DEFAULT_OUT / "raw" / "collector"])
def test_out_dir_inside_the_repo_or_coolcheck_data_raw_is_refused(out, capsys):
    assert C.main(["--dry-run", "--out-dir", str(out)], env={}) == 2
    assert "--out-dir must be outside" in capsys.readouterr().err
    assert not out.exists()


def test_secrets_never_reach_the_log_or_summary(tmp_path, capsys):
    summary = tmp_path / "summary.md"

    def leaky(dest, data):
        raise RuntimeError(f"denied for {CLIENT_SECRET} with {KEY}")
    env = {**REAL_ENV, bf.KEY_ENV: KEY, "GITHUB_STEP_SUMMARY": str(summary)}
    code, _, _, _ = run(tmp_path, at_utc(2026, 10, 21, 10, 27), None, env=env, uploader=leaky)
    assert code == 1
    text = capsys.readouterr().out + (tmp_path / "out" / "collector.log").read_text() + summary.read_text()
    assert KEY not in text and CLIENT_SECRET not in text
    assert "key present" in text and "***" in text
    assert "| wbgt |" in summary.read_text()


def test_files_api_uploader_sends_one_put_with_overwrite_false(monkeypatch):
    import databricks.sdk as sdk
    calls = []

    class FakeApiClient:
        _cfg = type("Cfg", (), {"workspace_id": None})()

        def do(self, method, path, query=None, headers=None, data=None, **kw):
            calls.append((method, path, query, data.read()))

    class FakeWorkspaceClient:
        def __init__(self, **kw):
            assert kw["auth_type"] == "oauth-m2m" and kw["client_secret"] == CLIENT_SECRET
            self.api_client = FakeApiClient()
    monkeypatch.setattr(sdk, "WorkspaceClient", FakeWorkspaceClient)
    C.files_api_uploader(REAL_ENV)(f"{ROOT}/wbgt/live/2026-10-21/x.jsonl", b"line\n")
    assert calls == [("PUT", f"/api/2.0/fs/files{ROOT}/wbgt/live/2026-10-21/x.jsonl", {"overwrite": False}, b"line\n")]
