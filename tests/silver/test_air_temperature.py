"""Air temperature as the fourth feed (docs/design/air_temperature.md): the shared station-series parser, its rules,
dedupe, DQ and the feed registries."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from silver_fixtures import bronze_rows, page
from coolcheck import dq
from coolcheck import silver as S
from coolcheck.bronze import FEEDS

FEED = "air_temperature"
SAMPLE = Path(__file__).resolve().parents[3] / "coolcheck-data" / "air_temperature_sample"


def air_page(readings, stations=("S109", "S106"), unit="deg C", reading_type="DBT 1M F"):
    """readings: [(timestamp, [(station_id, value), ...])]"""
    return page(FEED, {
        "stations": [{"id": s, "deviceId": s, "name": f"name {s}", "location": {"latitude": 1.3, "longitude": 103.8}}
                     for s in stations],
        "readings": [{"timestamp": ts, "data": [{"stationId": sid, "value": v} for sid, v in rs]} for ts, rs in readings],
        "readingType": reading_type, "readingUnit": unit})


def live(spark, lines, name, mtime):
    return bronze_rows(spark, lines, name, kind="live", mtime=mtime)


def test_every_registry_lists_the_same_feeds():
    assert set(FEEDS) == set(S.SCHEMAS) == set(S.RULES) == set(S.KEYS) == set(S.PARSERS) == set(S.NAMES)
    assert FEED in FEEDS and S.KEYS[FEED] == ["station_id", "reading_ts"] and S.NAMES[FEED] == "air_temperature_readings"


def test_parse_and_flags_keep_every_row(spark):
    line = air_page([("2026-10-22T15:30:00+08:00", [("S109", 31.2), ("S106", None), ("S109x", 30.0)]),
                     ("2026-10-22T15:31:00+08:00", [("S109", "abc"), ("S106", 55.0)]),
                     ("2026-10-22T15:32:30+08:00", [("S109", 31.0)]),
                     ("2026-10-22T07:33:00Z", [("S109", 31.1)])])
    rows = {(r.reading_ts_raw, r.station_id): r for r in S.parse_air_temperature(live(spark, [line], "air_temperature_a.jsonl",
            datetime(2026, 10, 22, 8, tzinfo=timezone.utc))).collect()}
    assert len(rows) == 7
    ok = rows[("2026-10-22T15:30:00+08:00", "S109")]
    assert ok.temp_c == 31.2 and ok.station_name == "name S109" and ok.sgt_date.isoformat() == "2026-10-22" and ok.sgt_minute == 930
    assert ok.reading_type == "DBT 1M F" and ok.reading_unit == "deg C"
    assert not any(getattr(ok, f"fail_{k}") for k in S.AIR_TEMPERATURE_RULES)
    assert rows[("2026-10-22T15:30:00+08:00", "S106")].fail_temp_present
    assert rows[("2026-10-22T15:30:00+08:00", "S109x")].fail_station_listed
    assert rows[("2026-10-22T15:31:00+08:00", "S109")].temp_c is None and rows[("2026-10-22T15:31:00+08:00", "S109")].fail_temp_present
    assert rows[("2026-10-22T15:31:00+08:00", "S106")].fail_temp_in_range and not rows[("2026-10-22T15:31:00+08:00", "S106")].fail_temp_present
    assert rows[("2026-10-22T15:32:30+08:00", "S109")].fail_minute_aligned
    z = rows[("2026-10-22T07:33:00Z", "S109")]
    assert z.fail_sgt_offset and z.sgt_minute == 933 and not z.fail_minute_aligned  # 15:33 SGT, offset flagged, converted right


def test_other_unit_is_flagged(spark):
    line = air_page([("2026-10-22T15:30:00+08:00", [("S109", 88.0)])], unit="deg F")
    row = S.parse_air_temperature(live(spark, [line], "air_temperature_a.jsonl", datetime(2026, 10, 22, 8, tzinfo=timezone.utc))).first()
    assert row.fail_unit_celsius and row.fail_temp_in_range  # 88 is outside 20 to 40 as well


def test_later_copy_wins_and_a_late_filled_minute_is_not_a_conflict(spark):
    t1, t2 = datetime(2026, 10, 22, 8, 0, tzinfo=timezone.utc), datetime(2026, 10, 22, 8, 15, tzinfo=timezone.utc)
    first = air_page([("2026-10-22T15:54:00+08:00", [("S109", 31.2)]), ("2026-10-22T15:53:00+08:00", [("S109", 31.0), ("S106", 30.8)])])
    second = air_page([("2026-10-22T15:54:00+08:00", [("S109", 31.2), ("S106", 31.1)]),   # 15:54 filled in late
                       ("2026-10-22T15:53:00+08:00", [("S109", 31.0), ("S106", 30.8)])])
    parsed = S.parse_air_temperature(live(spark, [first], "air_temperature_a.jsonl", t1)
                                     .unionByName(live(spark, [second], "air_temperature_b.jsonl", t2)))
    assert parsed.count() == 7 and parsed.select("station_id", "reading_ts").distinct().count() == 4
    assert dq.dq_conflicts(parsed, FEED).count() == 0
    winner = parsed.where("station_id = 'S109' AND sgt_minute = 954").orderBy(S.sequence_col().desc()).first()
    assert winner.source_file.endswith("air_temperature_b.jsonl")


def test_a_changed_value_for_the_same_station_and_minute_is_a_conflict(spark):
    t1, t2 = datetime(2026, 10, 22, 8, 0, tzinfo=timezone.utc), datetime(2026, 10, 22, 8, 15, tzinfo=timezone.utc)
    a = air_page([("2026-10-22T15:53:00+08:00", [("S109", 31.0)])])
    b = air_page([("2026-10-22T15:53:00+08:00", [("S109", 31.4)])])
    parsed = S.parse_air_temperature(live(spark, [a], "air_temperature_a.jsonl", t1).unionByName(live(spark, [b], "air_temperature_b.jsonl", t2)))
    conflicts = dq.dq_conflicts(parsed, FEED).collect()
    assert len(conflicts) == 2 and {c.n_versions for c in conflicts} == {2}


def test_quarantine_and_dq_events_know_the_feed(spark):
    good = air_page([("2026-10-22T15:30:00+08:00", [("S109", 31.2), ("S106", 55.0)])])
    bronze = bronze_rows(spark, [good, "not json", '{"code": 1, "errorMsg": "boom", "data": null}'], "air_temperature_a.jsonl", kind="live")
    quarantine = S.quarantine_lines(bronze, FEED)
    assert sorted(r.reason for r in quarantine.collect()) == ["api_code_1", "unparsable_json"]
    ev = {(r.feed, r.check_name): r.n for r in dq.dq_events({FEED: S.parse_air_temperature(bronze)}, quarantine, {}).collect()}
    assert ev[(FEED, "rule:temp_in_range")] == 1 and ev[(FEED, "copies_with_key")] == 2 and ev[(FEED, "distinct_keys")] == 2
    assert ev[(FEED, "quarantine:unparsable_json")] == 1


@pytest.mark.skipif(not list(SAMPLE.glob("*.json")), reason="the saved real response is outside the repo")
def test_the_real_response_parses_clean(spark):
    f = sorted(SAMPLE.glob("*.json"))[-1]
    body = json.loads(f.read_text(encoding="utf-8"))
    expected = sum(len(g["data"]) for g in body["data"]["readings"])
    parsed = S.parse_air_temperature(bronze_rows(spark, [f.read_text(encoding="utf-8").strip()], "air_temperature_real.jsonl", kind="live"))
    assert parsed.count() == expected > 400
    assert parsed.select("station_id", "reading_ts").distinct().count() == expected
    for rule in S.AIR_TEMPERATURE_RULES:
        assert parsed.where(f"fail_{rule}").count() == 0, rule
