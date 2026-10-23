"""The final check (docs/design/backtest.md §15 item 4 (e)) on synthetic station-days: local, no Spark and no workspace.
The lock here is an in-memory stand-in with the two calls run_final_check uses (locks, record) and the rules of
coolcheck.final_lock; the MLflow lock itself, with --override-incomplete, is tested against a local MLflow store in
test_final_check_mlflow.py."""
import importlib.util
import re
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest_fixtures import labels_of, synthetic_rows
from coolcheck import final_check as FC
from coolcheck.backtest import HOLDOUT_START, HP_CANDIDATES, LAST_BACKTEST_DATE, station_day_rows
from coolcheck.final_lock import (BACKTEST_MODEL_RUN, COMPLETE_TAG, ROLE, SCORED_TAG, AlreadyScored, is_complete,
                                  is_scored)
from coolcheck.metrics import pr_auc

JOB = Path(__file__).resolve().parents[2] / "src" / "jobs" / "final_check.py"
AREAS = ("A", "B")
KEYS = ["station_id", "target_date"]


@pytest.fixture(scope="module")
def data():
    rows = synthetic_rows(end=FC.FINAL_LAST)
    train = rows[rows.target_date <= pd.Timestamp(LAST_BACKTEST_DATE)].reset_index(drop=True)
    score = rows[rows.target_date >= pd.Timestamp(FC.FINAL_FIRST)].reset_index(drop=True)
    return train, labels_of(train), score


def area_map(dates):
    """Every date: area A on S124, B on S142, and Z (not one of the 41) on S125."""
    d = pd.to_datetime(pd.Series(dates)).drop_duplicates().to_numpy()
    return pd.concat([pd.DataFrame({"target_date": d, "planning_area": a, "station_id": s})
                      for a, s in (("A", "S124"), ("B", "S142"), ("Z", "S125"))], ignore_index=True)


def smap(score):
    return FC.area_map_41(area_map(score.target_date), AREAS, score[KEYS], FC.FINAL_FIRST, FC.FINAL_LAST)


def dated(frame, day):
    out = frame.assign(target_date=pd.Timestamp(day))
    out["target_date"] = out.target_date.astype(frame.target_date.dtype)  # the same unit, so concat needs no NaT fill
    return out


class Lock:
    """In-memory stand-in for the MLflow lock, as final_lock.write_final_run: record() first creates the run tagged
    scored, so the lock holds from then whatever follows; the complete tag is its last write, then FINISHED; a failure
    on the way leaves it FAILED, still scored and so still locking."""

    def __init__(self):
        self.runs = []

    def locks(self):
        return [(r["id"], r["status"], is_complete(r["tags"])) for r in self.runs if is_scored(r["tags"])]

    def record(self, fail=False):
        def write(result):
            run = {"id": f"run{len(self.runs)}", "status": "RUNNING", "tags": {"role": ROLE, SCORED_TAG: "true"},
                   "result": result}
            self.runs.append(run)
            if fail:
                run["status"] = "FAILED"
                raise RuntimeError("crash in writing the run")
            run["tags"][COMPLETE_TAG] = "true"
            run["status"] = "FINISHED"
            return run["id"]
        return write


def run(lock, train, labels, score, area, calls=None):
    calls = [] if calls is None else calls

    def load_training():
        calls.append("training")
        return train, labels

    def load_scoring():
        calls.append("scoring")
        return score, area

    return FC.run_final_check(lock.locks, load_training, load_scoring, lock.record())


def test_the_settings_are_those_of_section_15():
    assert FC.FINAL_CONFIG == (7, 150) == HP_CANDIDATES[0]
    assert FC.FINAL_CUTOFF == 0.10975585695894975
    assert (FC.FINAL_FIRST, FC.FINAL_LAST) == (date(2026, 9, 1), date(2026, 10, 19))
    assert HOLDOUT_START == FC.FINAL_FIRST == date(2026, 9, 1) and LAST_BACKTEST_DATE == date(2026, 8, 31)  # unchanged
    assert FC.EXPECTED_TRAIN == (9308, 465)
    assert [(last - first).days + 1 for _, first, last in FC.PERIODS] == [49, 30, 19]
    assert (FC.EQUIV_FIRST, FC.EQUIV_LAST) == (date(2026, 7, 1), date(2026, 8, 31))
    assert BACKTEST_MODEL_RUN == "c509ab9ad0d8464f8a1df07354b1bf98"  # §14


def test_a_training_row_dated_2026_09_01_makes_it_fail_before_any_scoring_row_is_read(data):
    train, labels, score = data
    bad = pd.concat([train, score[score.target_date == pd.Timestamp("2026-09-01")]], ignore_index=True)
    lock, calls = Lock(), []
    with pytest.raises(AssertionError, match="after 2026-08-31"):
        run(lock, bad, labels, score, smap(score), calls)
    assert calls == ["training"] and lock.runs == []
    with pytest.raises(AssertionError, match="after 2026-08-31"):  # a training label dated 2026-09-01
        run(Lock(), train, labels_of(bad), score, smap(score))
    with pytest.raises(AssertionError, match="after 2026-08-31"):  # the back-test path's own guard, unchanged
        station_day_rows(bad.drop(columns=["y", "label_n_high"]), bad[KEYS + ["y"]].assign(n_high=0))


@pytest.mark.parametrize("day", ["2026-08-31", "2026-10-20"])
def test_a_scoring_row_outside_1_sep_to_19_oct_makes_it_fail(data, day):
    train, labels, score = data
    stray = dated(score.head(1), day)
    lock, calls = Lock(), []
    with pytest.raises(AssertionError, match="scoring rows: 1 row.*outside 2026-09-01 to 2026-10-19"):
        run(lock, train, labels, pd.concat([score, stray], ignore_index=True), smap(score), calls)
    assert calls == ["training", "scoring"] and lock.runs == []
    with pytest.raises(AssertionError, match="scoring area mapping: 1 row.*outside"):
        run(Lock(), train, labels, score, pd.concat([smap(score), area_map(stray.target_date).head(1)]))
    with pytest.raises(AssertionError, match="station-day rows: 1 row.*outside"):  # the builder's join
        FC.window_rows(stray.drop(columns=["y", "label_n_high"]), stray[KEYS + ["y"]].assign(n_high=0),
                       FC.FINAL_FIRST, FC.FINAL_LAST)
    with pytest.raises(AssertionError, match="area mapping: 3 row.*outside"):  # and its area mapping
        FC.area_map_41(area_map(stray.target_date), AREAS, stray[KEYS], FC.FINAL_FIRST, FC.FINAL_LAST)


def test_a_second_run_is_refused_once_a_scored_final_check_run_exists(data):
    train, labels, score = data
    assert (score.target_date.min(), score.target_date.max()) == (pd.Timestamp("2026-09-01"), pd.Timestamp("2026-10-19"))
    lock = Lock()
    first = run(lock, train, labels, score, smap(score))  # 1 Sep and 19 Oct themselves are scored
    assert lock.locks() == [(first, "FINISHED", True)]
    calls = []
    with pytest.raises(AlreadyScored, match=re.escape(f"{first} (FINISHED, complete). It is scored once")):
        run(lock, train, labels, score, smap(score), calls)
    assert calls == [] and len(lock.runs) == 1  # refused before anything was read


@pytest.mark.parametrize("where", ["training rows", "fit", "scoring rows", "evaluation"])
def test_a_crash_before_scoring_completes_leaves_no_lock_and_a_rerun_can_follow(data, monkeypatch, where):
    train, labels, score = data
    lock = Lock()

    def crash(*args, **kwargs):
        raise RuntimeError(f"crash in {where}")

    load_training = crash if where == "training rows" else (lambda: (train, labels))
    load_scoring = crash if where == "scoring rows" else (lambda: (score, smap(score)))
    with monkeypatch.context() as mp:
        if where == "fit":
            mp.setattr(FC, "fit_lgb", crash)
        if where == "evaluation":
            mp.setattr(FC, "evaluate_final", crash)
        with pytest.raises(RuntimeError, match=f"crash in {where}"):
            FC.run_final_check(lock.locks, load_training, load_scoring, lock.record())
    assert lock.runs == [] and lock.locks() == []
    rerun = run(lock, train, labels, score, smap(score))  # on the user's word
    assert lock.locks() == [(rerun, "FINISHED", True)]


def test_a_crash_after_the_run_is_created_locks_and_names_the_run_as_incomplete(data):
    train, labels, score = data
    lock = Lock()
    with pytest.raises(RuntimeError, match="crash in writing the run"):
        FC.run_final_check(lock.locks, lambda: (train, labels), lambda: (score, smap(score)), lock.record(fail=True))
    assert lock.locks() == [("run0", "FAILED", False)]  # scored when created, so it locks whatever its status
    calls = []
    with pytest.raises(AlreadyScored, match=re.escape("run0 (FAILED, incomplete: its record is not whole; a rerun past "
                                                      "it needs --override-incomplete run0, on the user's word)")):
        run(lock, train, labels, score, smap(score), calls)
    assert calls == [] and len(lock.runs) == 1


def test_scoring_rows_are_requested_only_after_the_fit_and_change_no_fitted_object(data, monkeypatch):
    train, labels, score = data
    order, fit = [], FC.fit_final

    def spy_fit(*args):
        order.append("fit")
        return fit(*args)

    monkeypatch.setattr(FC, "fit_final", spy_fit)
    a = Lock()
    run(a, train, labels, score, smap(score), order)
    assert order == ["training", "fit", "scoring"]
    changed = score.copy()
    changed["y"] = 2 - changed.y                            # every label changed
    changed["fc_temp_high"] = changed.fc_temp_high + 3
    changed.loc[changed.index[:5], "fc_text"] = "Haze"      # a text never seen in training
    b = Lock()
    run(b, train, labels, changed, smap(changed))
    fa, fb = a.runs[0]["result"]["fitted"], b.runs[0]["result"]["fitted"]
    assert fa.booster.model_to_string() == fb.booster.model_to_string()
    assert (fa.fill, fa.categories, fa.theta, fa.theta_f1, fa.used) == (fb.fill, fb.categories, fb.theta, fb.theta_f1,
                                                                        fb.used)
    assert "Haze" not in fb.categories and b.runs[0]["result"]["unseen_text_rows"] == 5
    assert not a.runs[0]["result"]["results"]["counts"].equals(b.runs[0]["result"]["results"]["counts"])


def test_every_fitted_object_uses_nothing_after_2026_08_31(data):
    train, labels, score = data
    f = FC.fit_final(train, labels)
    assert set(f.used) == {"forecast fill", "text categories", "LightGBM model", "NEA rule threshold",
                           "same month last year (labels)"}
    assert all(pd.Timestamp(d) <= pd.Timestamp(LAST_BACKTEST_DATE) for d in f.used.values())
    assert (f.train_rows, f.train_high) == (len(train), int((train.y == 2).sum()))
    assert {9, 10} <= set(f.fill["by_month"])  # Sep and Oct filled from the training dates of those months
    assert f.booster.current_iteration() == 150 and f.booster.params["num_leaves"] == 7
    pred, _, _ = FC.score_final(f, score)
    assert pred.same_month_score.notna().all() and len(pred) == len(score)


def test_the_scoring_builder_gives_the_backtest_path_rows_on_jul_aug_2026(data):
    train, labels, score = data
    first, last = pd.Timestamp(FC.EQUIV_FIRST), pd.Timestamp(FC.EQUIV_LAST)
    feats = train.drop(columns=["y", "label_n_high"])
    labs = train[KEYS + ["y", "label_n_high"]].rename(columns={"label_n_high": "n_high"})
    amap = area_map(train.target_date)
    # the back-test path: station_day_rows over all training dates; area-days as src/jobs/backtest.py builds them
    bt = station_day_rows(feats, labs)
    bt_rows = bt[bt.target_date >= first]
    amap41 = amap[amap.planning_area.isin(set(AREAS))]
    bt_area = amap41[amap41.target_date >= first].merge(bt_rows, on=KEYS, how="inner")

    def window(d):
        return d[(d.target_date >= first) & (d.target_date <= last)]

    # the scoring builder on the same dates
    w_rows = FC.window_rows(window(feats), window(labs), FC.EQUIV_FIRST, FC.EQUIV_LAST)
    w_area = FC.area_days(FC.area_map_41(window(amap), AREAS, window(feats)[KEYS], FC.EQUIV_FIRST, FC.EQUIV_LAST),
                          w_rows)
    summary = FC.check_builder_equivalence(bt_rows, bt_area, w_rows, w_area)
    assert summary["station-day rows"]["rows"] == 3 * 62 and summary["area-day rows"]["rows"] == 2 * 62
    # float rounding (Spark may add the same values in another order) passes; anything else stops
    FC.check_builder_equivalence(bt_rows, bt_area, w_rows.assign(wbgt_peak_d1=w_rows.wbgt_peak_d1 + 1e-12), w_area)
    other_station = w_area.copy()
    other_station.loc[0, "station_id"] = "S125"
    bad = {"rain_d1_mm": w_rows.assign(rain_d1_mm=np.where(w_rows.index == 7, w_rows.rain_d1_mm + 0.1,
                                                           w_rows.rain_d1_mm)),
           "fc_temp_high": w_rows.assign(fc_temp_high=w_rows.fc_temp_high.where(w_rows.index != 2)),
           "y": w_rows.assign(y=np.where(w_rows.index == 3, (w_rows.y + 1) % 3, w_rows.y)),
           "fc_text": w_rows.assign(fc_text=w_rows.fc_text.where(w_rows.index != 4, "Haze"))}
    for column, rows in bad.items():
        with pytest.raises(AssertionError, match=re.escape(f"station-day rows: values differ: {column} (1 rows")):
            FC.check_builder_equivalence(bt_rows, bt_area, rows, w_area)
    with pytest.raises(AssertionError, match="station-day rows: 186 rows on the back-test path, 185 from the builder"):
        FC.check_builder_equivalence(bt_rows, bt_area, w_rows.drop(index=5), w_area)
    with pytest.raises(AssertionError, match=re.escape("area-day rows: values differ: station_id (1 rows")):
        FC.check_builder_equivalence(bt_rows, bt_area, w_rows, other_station)
    with pytest.raises(AssertionError, match="area-day rows: keys differ"):
        FC.check_builder_equivalence(bt_rows, bt_area, w_rows, w_area.assign(planning_area=w_area.planning_area
                                                                            .replace({"B": "C"})))
    with pytest.raises(AssertionError, match="area-day rows: duplicate keys on the builder"):
        FC.check_builder_equivalence(bt_rows, bt_area, w_rows, w_area.assign(planning_area="C"))


def hand_frame():
    """Four station-days by hand; S124 is one of the original 8, S142 a late starter. The first scores exactly the
    cut-off."""
    return pd.DataFrame({"station_id": ["S124", "S124", "S124", "S142"],
                         "target_date": pd.to_datetime(["2026-09-01", "2026-09-02", "2026-10-01", "2026-10-19"]),
                         "y": [2, 0, 2, 0], "p_high": [FC.FINAL_CUTOFF, 0.5, 0.05, 0.01],
                         "persist_alert": [True, False, False, False], "persist_score": [33.0, 30.0, 32.0, 29.0],
                         "nea_score": [34.0, 33.0, 33.0, 32.0], "nea_alert": [True, False, False, False],
                         "same_month_score": [0.2, 0.1, np.nan, 0.1]})


def test_the_evaluation_on_a_hand_worked_case():
    pred = hand_frame()
    area = pred.assign(planning_area=["A", "A", "A", "B"])
    res = FC.evaluate_final(pred, area)
    c = res["counts"].set_index(["set", "period", "method", "point"])
    cut = c.loc[("station_all", "all", "model", "cutoff")]
    assert (cut.alerts, cut.tp, cut.high, cut.recall, cut.precision) == (2, 1, 2, 0.5, 0.5)  # the cut-off itself alerts
    assert cut.alerts_per_day == pytest.approx(2 / 49) and (cut.recall_lo, cut.recall_hi) == pytest.approx(FC.wilson(1, 2))
    sep, oct_ = c.loc[("station_all", "2026-09", "model", "cutoff")], c.loc[("station_all", "2026-10", "model", "cutoff")]
    assert (sep.tp, sep.high, sep.alerts, sep.days) == (1, 1, 2, 30) and (oct_.tp, oct_.high, oct_.alerts, oct_.days) == (
        0, 1, 0, 19)
    load = c.loc[("station_all", "all", "model", "persistence_load")]
    assert (load.alerts, load.tp) == (1, 0)  # K = 1: the top score, 0.5, is not High
    assert np.isnan(c.loc[("area41", "all", "model", "cutoff")].recall_lo)  # no intervals on area-days
    assert res["sets"]["station_wo3"]["rows"] == 3 and res["sets"]["station_o8"]["rows"] == 3
    # the functions behind the back-test report: whole-window counts equal metrics.evaluate's, PR-AUC equals sklearn's
    ev = res["sets"]["station_all"]["evaluate"]
    for method, point in FC.POINTS:
        if point == "persistence_load" or method == "persistence_binary":
            e = ev["reference" if method == "persistence_binary" else method]
            got = c.loc[("station_all", "all", method, point)]
            assert (got.alerts, got.tp) == pytest.approx((e["alerts"], e["tp"]))
    for method, col in FC.SCORES.items():
        assert res["sets"]["station_all"]["pr_auc"][method] == pytest.approx(pr_auc(pred.y == 2, pred[col]), abs=1e-12)
    # the pre-declared reading: model 7/12 against persistence 1, so not above
    rd = res["reading"]
    assert (rd["model"], rd["persistence_continuous"], rd["agrees"]) == (pytest.approx(7 / 12), 1.0, False)
    assert FC.evaluate_final(pred, area.assign(persist_score=[29.0, 33.0, 30.0, 32.0]))["reading"]["agrees"] is True
    tie = FC.evaluate_final(pred, area.assign(persist_score=area.p_high))["reading"]
    assert tie["model"] == tie["persistence_continuous"] and tie["agrees"] is False  # equal is not above
    vb = res["versus_backtest"]
    assert vb["backtest"]["alerts_per_day"] == pytest.approx(1180 / 427) and vb["backtest"]["recall"] == 0.5
    assert (vb["final"]["all"]["alerts"], vb["final"]["all"]["days"]) == (2, 49)


def test_wilson_against_a_hand_worked_value():
    lo, hi = FC.wilson(5, 10)
    assert (round(lo, 4), round(hi, 4)) == (0.2366, 0.7634)
    assert all(np.isnan(FC.wilson(0, 0)))


def _job():
    spec = importlib.util.spec_from_file_location("final_check_job", JOB)
    job = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(job)
    return job


def test_the_job_refuses_a_missing_commit_and_an_early_run_date():
    job = _job()
    for sha in ("unknown", "", "not-a-sha"):
        with pytest.raises(SystemExit, match="not a commit hash"):
            job.check_git_sha(sha)
    assert job.check_git_sha("bff0577") == "bff0577"
    with pytest.raises(SystemExit, match="runs from 2026-10-20"):
        job.check_run_date(date(2026, 10, 19))
    job.check_run_date(date(2026, 10, 20))
    assert job.check_override("") is None and job.check_override("ab" * 16) == "ab" * 16
    for bad in ("run0", "AB" * 16, "ab" * 15):
        with pytest.raises(SystemExit, match="is not an MLflow run id"):
            job.check_override(bad)


def test_every_stage_starts_with_the_commit_and_the_code_sha256():
    job = _job()
    sha = job.code_sha256()
    assert re.fullmatch(r"[0-9a-f]{64}", sha)
    for stage in job.STAGES:
        line = job.start_line(stage, "bff0577", date(2026, 10, 23), None)
        assert line.startswith(f"stage {stage}; git bff0577; code sha256 {sha};") and "override-incomplete none" in line
    assert {"coolcheck/final_check.py", "coolcheck/final_lock.py", "jobs/final_check.py", "jobs/backtest.py",
            "coolcheck/backtest.py", "coolcheck/features.py"} <= set(job.CODE_FILES)


def test_the_report_and_the_run_content(data, tmp_path):
    train, labels, score = data
    score = score.copy()
    gap = score.target_date == pd.Timestamp("2026-09-15")
    score.loc[gap, "fc_temp_high"] = np.nan
    score.loc[gap, "fc_text"] = None
    score.loc[gap, "forecast_missing"] = True
    lock = Lock()
    run(lock, train, labels, score, smap(score))
    job = _job()
    audit = pd.DataFrame([{"frame": "features", "column": "target_date", "rows": 1, "first": pd.Timestamp("2025-01-17"),
                           "last": pd.Timestamp("2026-08-31")}])
    lineage = [{"phase": "training", "input": "t", "type": "streaming table", "pinned": "p", "filter": "f"}]
    tr = {"audit": audit.assign(phase="training"), "lineage": lineage}
    win = {"audit": audit.assign(phase="scoring"), "lineage": lineage, "no_row": pd.DataFrame(),
           "gap_reasons": {pd.Timestamp("2026-09-15"): "planted reason"}, "text_disagree": 0, "lab_csv": b"a\n"}
    sha = "0123456789abcdef0123456789abcdef01234567"
    meta = {"git_sha": sha, "code_sha256": "c" * 64, "run_date": date(2026, 10, 23), "experiment": "x/coolcheck-backtest",
            "packages": {"python": "3.12.3", "lightgbm": "4.6.0", "mlflow": "2.22.0"}, "stages_seconds": {},
            "view_check": {"view": "v", "definition_sha256": "0" * 64, "equals_nearest_station_sql": True},
            "finished": datetime(2026, 10, 23, 12, tzinfo=timezone.utc), "override": None}
    ctx = job.final_context(lock.runs[0]["result"], tr, win, meta)
    text = job.render_final_report({**ctx, "run_id": "r" * 32})
    assert "--override-incomplete" not in text
    assert "allowed past the incomplete scored run `" + "f" * 32 + "`" in job.render_final_report(
        {**ctx, "run_id": "r" * 32, "override": "f" * 32})
    for s in ("# Final check report", f"Git `{sha}`", "MLflow run `" + "r" * 32 + "`",
              "Packages this run used: python 3.12.3, lightgbm 4.6.0, mlflow 2.22.0.", "## Pre-declared reading (§15)",
              "Model above persistence: ", "alert when P(High) ≥ 0.10975585695894975",
              "1,180 alerts over 427 days, 2.76 a day; recall 0.500, 355 of 710 High area-days", "too narrow",
              "7 weekly blocks", "## Area-days over the 41 areas", "## Station-days: without S142, S137 and S135",
              "## Station-days: the original 8", "recall (Wilson 95%)", "| planted reason |", "num_leaves 7, 150 rounds"):
        assert s in text, s
    assert re.search(r"\| \d+ of \d+ High days \|", text)
    params, metrics = job.run_params(ctx), job.run_metrics(ctx["results"])
    assert params["git_sha"] == sha and params["high_cutoff"] == "0.10975585695894975"
    assert (params["num_leaves"], params["rounds"]) == (7, 150) and params["train_rows"] == len(train)
    assert all(job.KEY.match(k) for k in [*params, *metrics]) and all(len(str(v)) <= 6000 for v in params.values())
    assert {"area41/all/model_at_cutoff/recall", "station_all/2026-09/model_at_cutoff/recall_lo",
            "area41/model/pr_auc", "area41/reading_model_above_persistence"} <= set(metrics)
    assert "area41/all/model_at_cutoff/recall_lo" not in metrics
    job.write_artifacts(ctx, tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {
        "predictions_station_days.parquet", "predictions_area_days.parquet", "counts.csv", "forecast_fills.csv",
        "usable_station_days_without_feature_row.csv", "window_audit.csv", "labels_pulled_scoring_window.csv",
        "final_model.txt", "lineage.json"}
