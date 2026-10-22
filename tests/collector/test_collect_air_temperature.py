"""The air-temperature feed in collect.py (docs/design/air_temperature.md): fourth and last, 2-hour window, no midnight
sweep, the rainfall page shape for stopping, and a window capped below the 40-page limit."""
import json
from datetime import date, datetime

import collect as C
from fake_api import UTC, FakeAPI, Resp, feed_of
from test_collect import files, run

FEED = "air_temperature"


def at_utc(*a):
    return datetime(*a, tzinfo=UTC)


def test_two_hour_window_reads_five_pages_and_writes_one_file_last(tmp_path):
    now = at_utc(2026, 10, 21, 10, 27, 18)  # 18:27:18 SGT
    code, api, sess, _ = run(tmp_path, now, None, "--dry-run")
    assert code == 0
    assert api.pages(FEED, date(2026, 10, 21)) == [1, 2, 3, 4, 5]  # 25 minutes a page; page 5 reaches back past 16:27
    assert [feed_of(u) for u, _ in sess.calls] == ["wbgt", "forecast", "rainfall"] + [FEED] * 5  # last: a stop costs no model feed
    name = f"{FEED}_2026-10-21T182718_777.jsonl"
    assert f"{FEED}/live/2026-10-21/{name}" in files(tmp_path)
    lines = (tmp_path / "out" / FEED / "live/2026-10-21" / name).read_bytes().splitlines()
    assert len(lines) == 5
    assert all(b'"readingType":"DBT 1M F"' in ln for ln in lines)  # the response bodies, unchanged


def test_instants_finds_the_timestamps_of_an_air_temperature_page():
    """Regression: bf.reading_stamps knows only 'rainfall'; any other name is read as records[], finds nothing, and the
    walk never meets its stop rule."""
    body = FakeAPI(at_utc(2026, 10, 21, 10, 27))(C.FEEDS[FEED][0], {"date": "2026-10-21"}, 0).content
    stamps = C.instants(FEED, json.loads(body)["data"])
    assert len(stamps) == 25 and all(s.tzinfo for s in stamps)
    assert stamps[0] > stamps[-1]


def test_hour_zero_sweeps_the_other_feeds_but_not_air_temperature(tmp_path):
    now = at_utc(2026, 10, 21, 16, 5)  # 00:05 SGT on 22 Oct
    code, api, _, _ = run(tmp_path, now, None, "--dry-run")
    assert code == 0
    yesterday = date(2026, 10, 21)
    assert api.pages("rainfall", yesterday) == list(range(1, 13))  # swept, as before
    assert api.pages(FEED, yesterday) == [1, 2, 3, 4, 5]           # only back to the window start (22:05), not 58 pages
    assert api.pages(FEED, date(2026, 10, 22)) == [1]


def test_plan_can_skip_the_sweep():
    sgt = C.SGT
    now = datetime(2026, 10, 22, 0, 49, tzinfo=sgt)
    start = datetime(2026, 10, 21, 22, 49, tzinfo=sgt)
    assert C.plan(now, 2, sweep=False) == [(date(2026, 10, 22), start), (date(2026, 10, 21), start)]
    assert C.plan(now, 2) == C.plan(now, 2, sweep=True)


def test_manual_catch_up_is_capped_so_the_feed_stays_under_the_page_limit(tmp_path):
    now = at_utc(2026, 10, 21, 10, 27)  # 18:27 SGT; --window-hours 48 would be 115 pages of air temperature
    code, api, _, _ = run(tmp_path, now, None, "--dry-run", "--window-hours", "48")
    assert code == 0
    assert C.AIR_TEMPERATURE_MAX_WINDOW_HOURS == 12
    pages = api.pages(FEED, date(2026, 10, 21))
    assert pages == list(range(1, 30)) and len(pages) < 40  # 12 h of 25-minute pages (28.8), today only
    assert api.pages("rainfall", date(2026, 10, 20))        # the other feeds still follow the 48 h window
    assert api.pages(FEED, date(2026, 10, 20)) == []


def test_a_429_stop_in_air_temperature_leaves_the_three_model_feeds_written(tmp_path):
    now = at_utc(2026, 10, 21, 10, 27)
    api = FakeAPI(now)
    code, _, _, _ = run(tmp_path, now, lambda u, p, n: Resp(429, b"") if feed_of(u) == FEED else api(u, p, n), "--dry-run")
    assert code == 1
    assert files(tmp_path) == [f"{f}/live/2026-10-21/{f}_2026-10-21T182700_777.jsonl" for f in ("forecast", "rainfall", "wbgt")]
    log = (tmp_path / "out" / "collector.log").read_text()
    assert f" {FEED}: " in log and "429" in log


def test_air_temperature_calls_never_put_the_key_in_the_log(tmp_path):
    code, _, _, _ = run(tmp_path, at_utc(2026, 10, 21, 10, 27), None, "--dry-run", env={"DATA_GOV_SG_API_KEY": "SECRET-TEST-KEY-7f3a9c"})
    assert code == 0
    assert "SECRET-TEST-KEY-7f3a9c" not in (tmp_path / "out" / "collector.log").read_text()
