"""Window D's review of the live model and the nightly job (docs/checks/review_live_model_nightly.md): finding 2 (one
retry per task, 5 minutes apart), finding 1 (the completeness log lines, which can never fail the night) and finding 3
(the alias recovery written beside the job's run command). Local: no Spark and no workspace."""
import importlib.util
import re
from datetime import date
from pathlib import Path

import pandas as pd

from coolcheck import live_model as LM
from coolcheck import live_registry as LR

ROOT = Path(__file__).resolve().parents[2]


def _tasks(job_file):
    """{task_key: the task's lines} from a bundle job file, without a YAML library (the .venv has none)."""
    text = (ROOT / "resources" / job_file).read_text(encoding="utf-8")
    body = text.split("\n      tasks:", 1)[1]
    parts = re.split(r"\n {8}- task_key: ", body)[1:]  # the tasks list itself, not depends_on's task_key
    return {p.split("\n", 1)[0].strip(): p for p in parts}


def test_finding_2_each_nightly_task_retries_once_five_minutes_later():
    tasks = _tasks("heat_forecast.job.yml")
    assert set(tasks) == {"refresh", "score"}
    for key, block in tasks.items():
        assert re.search(r"^\s+max_retries: 1$", block, re.M), key
        assert re.search(r"^\s+min_retry_interval_millis: 300000$", block, re.M), key
    assert "full_refresh: false" in tasks["refresh"]
    # a second score is safe only because the write is a MERGE on (target_date, planning_area)
    assert "ON t.target_date = s.target_date AND t.planning_area = s.planning_area" in LM.merge_sql("t", "s")


def _feats():
    return pd.DataFrame({
        "station_id": ["S100", "S101", "S102", "S103"],
        "inputs_max_ts": pd.to_datetime(["2026-10-24 00:15", "2026-10-24 00:15", "2026-10-24 00:15", "2026-10-23 22:30"]),
        "rain_inputs_max_ts": pd.to_datetime(["2026-10-24 00:15", None, "2026-10-24 00:10", "2026-10-24 00:15"]),
    })


DQ = [{"feed": "wbgt", "status": "ok", "n_timestamps": 96, "expected_timestamps": 96, "n_stations": 30, "n_rows": 2880,
       "note": None},
      {"feed": "rainfall", "status": "short", "n_timestamps": 270, "expected_timestamps": 288, "n_stations": 62,
       "n_rows": 16740, "note": "18 slots missing"}]


def test_finding_1_the_day_before_and_the_latest_input_per_station():
    t = date(2026, 10, 24)
    assert "WHERE sgt_date = DATE'2026-10-23'" in LM.previous_day_sql("c.silver.dq_day", t)
    lines = LM.completeness_lines(DQ, _feats(), t)
    assert lines[0] == ("silver.dq_day for 2026-10-23 (the day before the target date): wbgt ok (96 of 96 times, "
                        "30 stations, 2,880 rows); rainfall short (270 of 288 times, 62 stations, 16,740 rows; "
                        "18 slots missing); forecast no row")
    assert lines[1] == ("latest WBGT and forecast input per station: 2026-10-24 00:15 3 stations (S100, S101, S102); "
                        "2026-10-23 22:30 1 station (S103)")
    assert lines[2] == ("latest rainfall input per station: none 1 station (S101); 2026-10-24 00:15 2 stations "
                        "(S100, S103); 2026-10-24 00:10 1 station (S102)")


def test_finding_1_many_stations_are_counted_not_listed():
    f = pd.DataFrame({"station_id": [f"S{i}" for i in range(8)], "inputs_max_ts": pd.Timestamp("2026-10-24 00:15"),
                      "rain_inputs_max_ts": pd.Timestamp("2026-10-24 00:15")})
    assert LM.completeness_lines([], f, date(2026, 10, 24))[1] == (
        "latest WBGT and forecast input per station: 2026-10-24 00:15 8 stations")


def _nightly():
    spec = importlib.util.spec_from_file_location("heat_forecast_job", ROOT / "src" / "jobs" / "heat_forecast.py")
    job = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(job)
    return job


class _Row:
    def __init__(self, d):
        self.d = d

    def asDict(self):
        return self.d


class _Spark:
    def __init__(self, rows=None, error=None):
        self.rows, self.error, self.sql_seen = rows, error, []

    def sql(self, q):
        self.sql_seen.append(q)
        if self.error:
            raise self.error
        return type("R", (), {"collect": lambda _self: [_Row(r) for r in self.rows]})()


def test_finding_1_the_log_lines_are_printed_and_an_error_in_them_never_fails_the_night(capsys):
    job = _nightly()
    spark = _Spark(rows=DQ)
    job.log_completeness(spark, "c.silver.dq_day", _feats(), date(2026, 10, 24))
    out = capsys.readouterr().out
    assert "silver.dq_day for 2026-10-23" in out and "latest rainfall input per station" in out
    assert "c.silver.dq_day" in spark.sql_seen[0]
    job.log_completeness(_Spark(error=RuntimeError("table not found")), "c.silver.dq_day", _feats(), date(2026, 10, 24))
    assert "completeness lines not written (RuntimeError: table not found); the score goes on" in capsys.readouterr().out
    job.log_completeness(_Spark(rows=DQ), "c.silver.dq_day", _feats().drop(columns="rain_inputs_max_ts"), date(2026, 10, 24))
    assert "completeness lines not written (KeyError" in capsys.readouterr().out


def test_finding_1_the_score_task_calls_it_after_the_feature_checks_and_before_the_model_predicts():
    src = (ROOT / "src" / "jobs" / "heat_forecast.py").read_text(encoding="utf-8")
    main = src.split("def main():", 1)[1]
    assert main.index('FC.assert_in_window(feats, target, target, "features")') < main.index(
        'log_completeness(spark, t["dq"], feats, target)') < main.index("model.predict(")


def test_finding_3_the_alias_recovery_is_written_beside_the_jobs_run_command():
    text = (ROOT / "resources" / "live_model.job.yml").read_text(encoding="utf-8")
    assert f"databricks registered-models set-alias <catalog>.ml.heat_model {LR.ALIAS} <version> -p <profile>" in text
    assert "databricks registered-models get <catalog>.ml.heat_model --include-aliases -p <profile>" in text
    assert "databricks bundle run heat_forecast -t <target> -p <profile> --params target_date=<YYYY-MM-DD>" in text
    assert "Do not refit" in text
    # what the recovery note says the nightly job does without the tags
    job = _nightly()
    assert job.trained_to(type("V", (), {"tags": {}})()) == LM.LIVE_LAST == date(2026, 10, 22)
