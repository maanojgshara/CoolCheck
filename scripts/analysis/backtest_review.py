"""Review tables from a back-test run's saved predictions (no workspace access): the H4 operating points, the model at
the NEA rule's alert load, sustained-High counts at persistence's load, and per month the observed High against the sum
of P(High). Every number comes from the run's artifacts (predictions_area_days.parquet, predictions_station_days.parquet).

Run from the repo root:
    .venv\\Scripts\\python scripts/analysis/backtest_review.py [--artifacts <dir>] [--out docs/checks/backtest_review.md]
"""
import argparse
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from coolcheck.backtest import season_period  # noqa: E402
from coolcheck.metrics import at_load, load_weights, pr_curve  # noqa: E402

SGT = timezone(timedelta(hours=8))
RUN = "c509ab9ad0d8464f8a1df07354b1bf98"
RECALLS = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8)
SEASON_RECALLS = (0.4, 0.5, 0.6)
PEAK = (pd.Timestamp("2026-04-01"), pd.Timestamp("2026-07-01"))  # Apr to Jun 2026
SEASONS = ("Inter-monsoon 1 2026", "SW monsoon 2026", "the rest (Jul 2025 to Feb 2026)")
LABELS = {2: "High", 1: "Moderate", 0: "Low"}
HIGH = 2


def md(df):
    def cell(v):
        if isinstance(v, (float, np.floating)):
            return "—" if np.isnan(v) else (f"{v:,.0f}" if float(v).is_integer() and abs(v) >= 10 else f"{v:,.3f}")
        if isinstance(v, (int, np.integer)):
            return f"{int(v):,}"
        return str(v)
    cols = list(df.columns)
    return ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)] + [
        "| " + " | ".join(cell(v) for v in row) + " |" for row in df.itertuples(index=False)]


def operating_points(frame, score, days, peak_days):
    """The first threshold (highest) at which pooled recall reaches each level; alerts are rows scoring at or above it."""
    curve = pr_curve(frame.y == HIGH, frame[score])
    peak = frame.target_date.between(PEAK[0], PEAK[1], inclusive="left")
    s = frame[score].to_numpy(dtype=float)
    rows = []
    for level in RECALLS:
        r = curve[curve.recall >= level - 1e-12].iloc[0]
        alert = s >= r.threshold
        rows.append({"recall at least": level, "threshold": r.threshold, "alerts": int(r.alerts),
                     "alerts per day (all 14 months)": r.alerts / days,
                     "alerts per day (Apr to Jun 2026)": int((alert & peak).sum()) / peak_days,
                     "TP": int(r.tp), "recall": r.recall, "precision": r.precision})
    return pd.DataFrame(rows)


def first_threshold(score, y, level):
    """The highest threshold at which the rows scoring at or above it catch at least `level` of the High rows."""
    curve = pr_curve(y, score)
    return float(curve[curve.recall >= level - 1e-12].iloc[0].threshold)


def union_threshold(frame, level):
    """The union rule alerts when P(High) >= t or the station was High yesterday (persistence's binary alert). The
    highest t at which the union catches at least `level` of the High rows (inf if yesterday's High alone does)."""
    y = (frame.y == HIGH).to_numpy()
    base = frame.persist_alert.to_numpy(dtype=bool)
    need = level * y.sum() - (y & base).sum()
    if need <= 1e-9:
        return float("inf")
    s, yr = frame.p_high.to_numpy(dtype=float)[~base], y[~base]
    order = np.argsort(-s, kind="mergesort")
    s_o, tp = s[order], np.cumsum(yr[order])
    last = np.r_[np.flatnonzero(np.diff(s_o) != 0), len(s_o) - 1]  # tie groups: alerts are rows at or above t
    return float(s_o[last[np.flatnonzero(tp[last] >= need - 1e-9)[0]]])


def season_lines(area):
    """Per season, alerts, TP and recall at overall recall 0.4, 0.5 and 0.6 for the model, persistence (continuous)
    and the union rule; and the labels of the model's and the union's alerts."""
    y = (area.y == HIGH).to_numpy()
    season = area.target_date.map(season_period).where(lambda s: s.isin(SEASONS[:2]), SEASONS[2]).to_numpy()
    # a missing yesterday ranks lowest in the curve and never alerts (NaN >= t is False)
    p, w = area.p_high.to_numpy(dtype=float), area.persist_score.to_numpy(dtype=float)
    base = area.persist_alert.to_numpy(dtype=bool)
    L = ["## Hot spells: alerts per season at overall recall 0.4, 0.5 and 0.6 (area-days)", "",
         "For each overall recall level on the area-days: (a) the model at the highest P(High) threshold reaching it; "
         "(b) persistence (continuous, yesterday's peak WBGT) at the highest threshold reaching the same overall recall; "
         "(c) the union rule \"P(High) at or above t, or the station was High yesterday\", with t the highest value at "
         "which the union reaches the same overall recall. Seasons as in the report: inter-monsoon 1 2026 is Mar to May "
         "2026, SW monsoon 2026 is Jun to Aug 2026 (the test months end there), the rest is Jul 2025 to Feb 2026. "
         "Recall within a season is over that season's High area-days.", "",
         "**(c) is a candidate added after the run, at your request on 22 Oct 2026. It is not in the pre-declared design "
         "(note §13 chose the model), and its t is chosen on the same pooled out-of-fold predictions it is scored on.**",
         ""]
    for level in SEASON_RECALLS:
        t_model, t_pers, t_union = first_threshold(p, y, level), first_threshold(w, y, level), union_threshold(area, level)
        rules = {"(a) model": (p >= t_model, f"P(High) ≥ {t_model:.3f}"),
                 "(b) persistence (continuous)": (w >= t_pers, f"yesterday's peak ≥ {t_pers:.1f} °C"),
                 "(c) union, added after the run": (base | (p >= t_union),
                                                    f"P(High) ≥ {t_union:.3f}, or High yesterday")}
        rows, labels = [], []
        for name, (alert, rule) in rules.items():
            for s in (*SEASONS, "all"):
                m = np.ones(len(y), dtype=bool) if s == "all" else season == s
                a_, tp, hi = int((alert & m).sum()), int((alert & m & y).sum()), int((m & y).sum())
                rows.append({"rule": name if s == SEASONS[0] else "", "season": s, "alerts": a_, "TP": tp, "High": hi,
                             "recall": tp / hi if hi else np.nan, "precision": tp / a_ if a_ else np.nan})
            if not name.startswith("(b)"):
                lab = area.y[alert].map(LABELS).value_counts()
                labels.append({"rule": name, "threshold": rule, **{v: int(lab.get(v, 0)) for v in LABELS.values()},
                               "alerts": int(alert.sum())})
        L += [f"### Overall recall at least {level}", "",
              "Thresholds: " + "; ".join(f"{n} {r}" for n, (_, r) in rules.items()) + ".", ""]
        L += md(pd.DataFrame(rows)) + ["", "Labels of the alerts (area-days):", ""] + md(pd.DataFrame(labels)) + [""]
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifacts", default=str(REPO.parent / "coolcheck-data" / "analysis" / "backtest_run_c509ab9a"))
    ap.add_argument("--out", default=str(REPO / "docs" / "checks" / "backtest_review.md"))
    a = ap.parse_args()
    art = Path(a.artifacts)
    area = pd.read_parquet(art / "predictions_area_days.parquet")
    st = pd.read_parquet(art / "predictions_station_days.parquet")
    days = area.target_date.nunique()
    peak_days = area.target_date[area.target_date.between(PEAK[0], PEAK[1], inclusive="left")].nunique()
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()
    L = ["# Back-test review tables", "",
         f"Generated {datetime.now(SGT):%Y-%m-%d %H:%M} SGT by `scripts/analysis/backtest_review.py` at git `{sha}` from the "
         f"artifacts of MLflow run `{RUN}` (the run of `docs/checks/backtest.md`), saved in `{art.name}` under "
         "`coolcheck-data/analysis/`. Numbers only; no cut-off is chosen here. Nothing after 2026-08-31 is read "
         f"(the predictions end on {area.target_date.max():%Y-%m-%d}).", ""]

    L += ["## H4 operating points, area-days over the 41 areas", "",
          f"Pooled out-of-fold predictions, {len(area):,} area-days, {int((area.y == HIGH).sum()):,} High, {days} test days "
          f"({peak_days} in Apr to Jun 2026). The model's score is P(High); persistence (continuous) is yesterday's peak "
          "WBGT at the area's station, in °C. At each recall level: the highest threshold reaching it, the alerts at or "
          "above it (area-days), and alerts per day.", ""]
    for name, score in (("Model, P(High)", "p_high"), ("Persistence (continuous), yesterday's peak WBGT", "persist_score")):
        L += [f"### {name}", ""] + md(operating_points(area, score, days, peak_days)) + [""]

    k_nea = int(area.nea_alert.sum())
    y = (area.y == HIGH).to_numpy()
    model_at_nea = at_load(y, load_weights(area.p_high.to_numpy(dtype=float), k_nea)[0])
    nea_own = at_load(y, area.nea_alert.to_numpy(dtype=float))
    L += ["## The model at the NEA rule's alert load (area-days)", "",
          f"The NEA rule at its own per-fold thresholds alerts on {k_nea:,} area-days. The model's {k_nea:,} highest P(High) "
          "(ties shared in expectation):", "",
          *md(pd.DataFrame([{"method": "model at the NEA load", "alerts": model_at_nea["alerts"], "TP": model_at_nea["tp"],
                             "High": model_at_nea["positives"], "recall": model_at_nea["recall"],
                             "precision": model_at_nea["precision"]},
                            {"method": "NEA rule at its own thresholds", "alerts": nea_own["alerts"], "TP": nea_own["tp"],
                             "High": nea_own["positives"], "recall": nea_own["recall"],
                             "precision": nea_own["precision"]}])), ""]

    L += ["## Sustained High (3 or more High readings) at persistence's load", "",
          "Persistence alerts K times (its binary rule); the model alerts on its K highest P(High), ties shared in "
          "expectation. Recall over the High days with 3 or more High readings.", ""]
    rows = []
    for name, frame in (("area-days, 41 areas", area), ("station-days, all stations", st)):
        yy = (frame.y == HIGH).to_numpy()
        sus = yy & (frame.label_n_high.to_numpy() >= 3)
        k = int(frame.persist_alert.sum())
        w = load_weights(frame.p_high.to_numpy(dtype=float), k)[0]
        for method, weights in (("model", w), ("persistence", frame.persist_alert.to_numpy(dtype=float))):
            tp = float((weights * sus).sum())
            rows.append({"set": name, "K": k, "method": method, "sustained High": int(sus.sum()),
                         "caught": tp, "recall": tp / sus.sum()})
    L += md(pd.DataFrame(rows)) + [""]

    L += ["## Per month: observed High against the sum of P(High)", ""]
    for name, frame in (("area-days, 41 areas", area), ("station-days, all stations", st)):
        g = (frame.assign(month=frame.target_date.dt.strftime("%Y-%m"), high=(frame.y == HIGH).astype(int))
             .groupby("month").agg(rows=("high", "size"), observed_high=("high", "sum"), sum_p_high=("p_high", "sum"))
             .reset_index())
        g["observed − expected"] = g.observed_high - g.sum_p_high
        tot = pd.DataFrame([{"month": "all", "rows": g.rows.sum(), "observed_high": g.observed_high.sum(),
                             "sum_p_high": g.sum_p_high.sum(), "observed − expected": g["observed − expected"].sum()}])
        L += [f"### {name}", ""] + md(pd.concat([g, tot], ignore_index=True)) + [""]
    L += season_lines(area)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    sys.stdout.reconfigure(encoding="utf-8")  # the Windows console default (cp1252) has no minus sign
    print("\n".join(L))


if __name__ == "__main__":
    main()
