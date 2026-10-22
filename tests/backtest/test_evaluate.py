"""The evaluation sets (note §6) and the job's report on synthetic folds: local, no Spark and no workspace."""
import importlib.util
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest_fixtures import labels_of, synthetic_rows
from coolcheck.backtest import FOLDS, best_overall, evaluate_all, run_folds, season_period

JOB = Path(__file__).resolve().parents[2] / "src" / "jobs" / "backtest.py"


@pytest.fixture(scope="module")
def folds_run():
    rows = synthetic_rows()
    folds = FOLDS[6:9]  # Jan to Mar 2026, so the Feb to Aug 2026 sets exist
    pooled, records, fills, boosters = run_folds(rows, labels_of(rows), folds=folds)
    best, best_aps = best_overall(pooled)
    # two areas: one on S124, one on S142
    area = pd.concat([pooled[pooled.station_id == s].assign(planning_area=a) for a, s in (("A", "S124"), ("B", "S142"))])
    im1 = {"station": rows[(rows.target_date >= "2025-03-01") & (rows.target_date < "2025-06-01")]
           .assign(persist_alert=lambda d: d.n_high_d1 >= 1)}
    res = evaluate_all(pooled, area, best, n_boot=50, seed=1, im1_2025=im1)
    return rows, folds, pooled, records, fills, best, best_aps, area, res


def test_season_period_names():
    assert [season_period(d) for d in ("2025-12-05", "2026-02-01", "2026-04-29", "2025-07-01", "2025-10-31")] == [
        "NE monsoon 2025/26", "NE monsoon 2025/26", "Inter-monsoon 1 2026", "SW monsoon 2025", "Inter-monsoon 2 2025"]


def test_every_set_and_method_is_evaluated(folds_run):
    rows, folds, pooled, records, fills, best, best_aps, area, res = folds_run
    assert set(res["sets"]) == {"area41", "station_all", "station_wo3", "station_o8", "area41_feb_aug_2026",
                                "station_all_feb_aug_2026"}
    s = res["sets"]["station_all"]
    assert s["K"] == int(pooled.persist_alert.sum()) and s["rows"] == len(pooled)
    assert {"model", "reference", "persistence_continuous", "nea_rule", "best_overall",
            "ablation_no_station_char"} <= set(s["methods"])
    assert "same_month_last_year" in res["sets"]["station_all_feb_aug_2026"]["methods"]
    assert "same_month_last_year" not in s["methods"]
    assert res["sets"]["station_wo3"]["rows"] == int((pooled.station_id != "S142").sum())
    assert s["methods"]["model"]["alerts"] == pytest.approx(s["K"])
    assert ("model", "reference") in s["diffs"] and ("model", "same_month_last_year") in res["sets"][
        "station_all_feb_aug_2026"]["diffs"]


def test_counts_tables(folds_run):
    rows, folds, pooled, records, fills, best, best_aps, area, res = folds_run
    pm = res["per_month"]["station_all"]
    assert list(pm.group) == ["2026-01", "2026-02", "2026-03"] and pm.rows.sum() == len(pooled)
    assert pm.alerts_persistence.sum() == pooled.persist_alert.sum()
    assert res["three_class"].to_numpy().sum() == len(pooled) and np.isfinite(res["log_loss"])
    assert res["im1_2025"]["station"]["rows"] == len(rows[(rows.target_date >= "2025-03-01")
                                                           & (rows.target_date < "2025-06-01")])


def _job():
    spec = importlib.util.spec_from_file_location("backtest_job", JOB)
    job = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(job)
    return job


@pytest.mark.filterwarnings("error")
def test_the_job_cutoff_check_passes_good_rows_and_stops_a_late_input():
    job = _job()
    f = pd.DataFrame({"target_date": [date(2025, 7, 1), date(2025, 7, 2)],
                      "cutoff_ts": pd.to_datetime(["2025-07-01 00:15", "2025-07-02 00:15"]),
                      "inputs_max_ts": pd.to_datetime(["2025-06-30 16:00", None]),
                      "rain_inputs_max_ts": pd.to_datetime(["2025-06-30 23:55", "2025-07-01 23:55"]),
                      "fc_updated_ts": pd.to_datetime(["2025-06-30 23:10", None]),
                      "fc_issue_ts": pd.to_datetime(["2025-06-30 23:00", None])})
    job.check_feature_cutoffs(f)  # no warning, no stop
    late = f.assign(fc_issue_ts=pd.to_datetime(["2025-06-30 16:59", None]))  # before 17:00 on T-1
    with pytest.raises(SystemExit, match="outside the cut-off rules"):
        job.check_feature_cutoffs(late)


def test_the_job_report_renders(folds_run):
    rows, folds, pooled, records, fills, best, best_aps, area, res = folds_run
    job = _job()
    ctx = {"results": res, "records": records, "fills": fills, "folds": list(folds), "best": best, "best_aps": best_aps,
           "lineage_rows": [{"input": "x", "type": "t", "pinned": "p", "filter": "f"}],
           "view_check": {"view": "v", "definition_sha256": "0" * 64, "equals_nearest_station_sql": True},
           "audit": pd.DataFrame([{"frame": "f", "column": "c", "rows": 1, "first": pd.Timestamp("2026-01-01"),
                                   "last": pd.Timestamp("2026-03-31")}]),
           "n_rows": len(rows), "no_feature_row": pd.DataFrame(), "n_area": len(area), "area_dropped": 0,
           "text_disagree": 0, "git_sha": "abc", "code_sha256": "f" * 64, "run_date": "2026-10-23", "cutoff": 15,
           "bootstrap": 50, "seed": 1, "finished": datetime(2026, 10, 23, tzinfo=timezone.utc), "mode": "test"}
    text = job.render_report(ctx)
    for heading in ("# Rolling back-test report", "## Headline: area-days over the 41 areas", "Label-noise reference",
                    "## Hyper-parameters chosen per fold", "## Inter-monsoon 1, 2025", "## Three classes",
                    "| persistence (binary) |", f"persistence alerts K = {res['sets']['area41']['K']:,}"):
        assert heading in text
