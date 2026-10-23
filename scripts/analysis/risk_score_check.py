"""Back-test tier counts, reach and sensitivity runs for the risk score (docs/design/risk_score.md §10); local, no load.

Run from the repo root:
    .venv\\Scripts\\python scripts/analysis/risk_score_check.py [--data <coolcheck-data>]

Inputs, the same files the Silver tables are loaded from (sha256 recorded): analysis/area_exposure.csv, area_access.csv,
block_access.csv and ema_area_electricity.csv; reference/score_weights.csv; and the back-test's area-day predictions
(analysis/backtest_run_c509ab9a/predictions_area_days.parquet), read with target_date <= 2026-08-31 and asserted, since
the final check (1 Sep to 19 Oct 2026) is not scored yet. V and the thirds use today's layers on every back-test day.
Stops unless the heat level over all 41 areas gives the back-test's 1,180 High alerts, 355 of them observed High, of 710
observed High area-days, over 427 days.
Writes <data>/analysis/risk_score_check/ (CSV artifacts, and run.json for scripts/analysis/log_risk_runs.py) and
docs/checks/risk_score.md. The rules are those of src/coolcheck/risk.py, whose SQL twin the tests compare row by row.
"""
import argparse
import csv
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from coolcheck import risk as R  # noqa: E402
from coolcheck.access import spearman  # noqa: E402
from coolcheck.backtest import LAST_BACKTEST_DATE, season_period  # noqa: E402
from coolcheck.final_check import BACKTEST_AT_CUTOFF  # noqa: E402

BACKTEST_RUN = "backtest_run_c509ab9a"
INPUTS = {"area_exposure": "analysis/area_exposure.csv", "area_access": "analysis/area_access.csv",
          "block_access": "analysis/block_access.csv", "ema_area_electricity": "analysis/ema_area_electricity.csv"}
WEIGHTS = REPO / "reference/score_weights.csv"
SEVERITY = R.TIER_SEVERITY
TIERS = ("High", "Medium", "Low")
MARK = ("<!-- mlflow -->", "<!-- /mlflow -->")
CODE_FILES = ["src/coolcheck/risk.py", "src/coolcheck/access.py", "scripts/analysis/risk_score_check.py",
              "reference/score_weights.csv", "reference/tier_actions.csv"]


def rows_of(path):
    with Path(path).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def variants(weights):
    """(name, description, weights, area_inputs keyword arguments) for the main design and the seven sensitivity runs."""
    equal = [dict(w, weight=1 / len(weights)) for w in weights]
    no_elec = [dict(w, weight=w["weight"] / 0.95) for w in weights if w["component"] != "electricity_hot_rise"]
    return [("main", "decision 9 and 9(g)", weights, {}),
            ("equal_weights", "each of the seven components weighted 1/7", equal, {}),
            ("no_electricity", "electricity dropped; the other six weights scaled by 1/0.95", no_elec, {}),
            ("refuges_clubs_only", "both refuge components from the clubs-only set", weights, {"refuge_set": "clubs_only"}),
            ("refuges_with_sac_2016", "both refuge components with the 2016 SACs added", weights, {"refuge_set": "with_sac_2016"}),
            ("parks_ura", "the park component from the URA layer", weights, {"park_set": "ura"}),
            ("parks_with_reserves", "the park component with the reserves in", weights, {"park_set": "with_reserves"}),
            ("aged_65", "the 65+ count and share in place of the 75+ pair, same weights and residents rule", weights, {"age": "65"})]


def md_table(header, rows):
    return ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"] + \
           ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


def pct(n, d):
    return f"{n / d:.1%}" if d else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(REPO.parent / "coolcheck-data"))
    a = ap.parse_args()
    data = Path(a.data)
    if R.LAST_BACKTEST_DATE != LAST_BACKTEST_DATE:
        raise SystemExit("risk.LAST_BACKTEST_DATE differs from backtest.LAST_BACKTEST_DATE")
    src = {k: rows_of(data / v) for k, v in INPUTS.items()}
    weights = R.load_weights(WEIGHTS)
    exposure = {r["planning_area"]: r for r in src["area_exposure"]}
    aged75 = {k: int(r["aged_75_plus"]) for k, r in exposure.items()}

    # --- V for the main design and the sensitivity runs
    vs, ins = {}, {}
    for name, _, w, kw in variants(weights):
        ins[name] = R.area_inputs(src["area_exposure"], src["area_access"], src["block_access"], src["ema_area_electricity"], **kw)
        vs[name] = R.vulnerability(ins[name], w)
    main_v, main_in = vs["main"], ins["main"]
    near = sum(1 for b in src["block_access"] if any(abs(float(b[c]) - R.WALK_M) < 0.01 for c in ("refuge_main_m", "park_main_m")))
    rated = sorted(main_v)
    if len(rated) != 32:
        raise SystemExit(f"STOP: {len(rated)} rated areas, expected 32")

    # --- back-test rows (hard rule: target_date <= 2026-08-31, filtered at read and asserted)
    pq_path = data / "analysis" / BACKTEST_RUN / "predictions_area_days.parquet"
    bt = R.read_backtest_area_days(pq_path, columns=["target_date", "planning_area", "station_id", "y", "forecast_missing",
                                                     "p_low", "p_moderate", "p_high"])
    first_day, last_day, n_rows = min(bt["target_date"]), max(bt["target_date"]), len(bt)
    days = sorted(set(bt["target_date"]))
    fc = bt.to_dict("records")
    heat_all = [R.heat_level(f["p_low"], f["p_moderate"], f["p_high"]) for f in fc]
    gate = {"alerts": sum(h == "High" for h in heat_all), "tp": sum(h == "High" and f["y"] == 2 for h, f in zip(heat_all, fc)),
            "high": sum(f["y"] == 2 for f in fc), "days": len(days)}
    for k in gate:
        print(f"gate {k}: {gate[k]:,} (back-test {BACKTEST_AT_CUTOFF[k]:,}) {'ok' if gate[k] == BACKTEST_AT_CUTOFF[k] else 'DIFFERS'}")
    if gate != BACKTEST_AT_CUTOFF:
        raise SystemExit("STOP: the heat level does not reproduce the back-test's counts at the cut-off")

    risk = {"main": R.heat_risk(fc, main_v, R.TIER_MAIN), "variant": R.heat_risk(fc, main_v, R.TIER_VARIANT)}
    rated_rows = {m: [r for r in rs if r["rated"]] for m, rs in risk.items()}
    n_rated, n_not = len(rated_rows["main"]), sum(not r["rated"] for r in risk["main"])
    counts = {m: Counter(r["tier"] for r in rs) for m, rs in risk.items()}
    per_day = {m: {t: Counter(r["target_date"] for r in rated_rows[m] if r["tier"] == t) for t in TIERS} for m in risk}
    cells = Counter((r["heat_level"], r["third"]) for r in rated_rows["main"])
    heat_rated = Counter(r["heat_level"] for r in rated_rows["main"])
    by_season = defaultdict(lambda: {"days": set(), "rated": 0, **{(m, t): 0 for m in risk for t in TIERS}})
    for m, rs in rated_rows.items():
        for r in rs:
            s = by_season[season_period(pd.Timestamp(r["target_date"]))]
            if m == "main":
                s["days"].add(r["target_date"])
                s["rated"] += 1
            s[(m, r["tier"])] += 1
    seasons = sorted(by_season, key=lambda s: min(by_season[s]["days"]))

    # --- reach (the variant changes only Moderate x middle, so High-tier reach is the same under both)
    high_by_day = defaultdict(int)
    for r in rated_rows["main"]:
        if r["tier"] == "High":
            high_by_day[r["target_date"]] += aged75[r["planning_area"]]
    daily = [high_by_day.get(d, 0) for d in days]
    reach = {
        "tier_high_75_per_day_mean": statistics.mean(daily), "tier_high_75_per_day_median": statistics.median(daily),
        "tier_high_75_per_day_max": max(daily), "tier_high_75_senior_days": sum(daily),
        "tier_high_area_days": counts["main"]["High"],
        "tier_high_observed_high_75_senior_days": sum(aged75[r["planning_area"]] for r in rated_rows["main"] if r["tier"] == "High" and r["y"] == 2),
        "tier_high_observed_high_area_days": sum(1 for r in rated_rows["main"] if r["tier"] == "High" and r["y"] == 2),
        "observed_high_rated_75_senior_days": sum(aged75[r["planning_area"]] for r in rated_rows["main"] if r["y"] == 2),
        "observed_high_rated_area_days": sum(1 for r in rated_rows["main"] if r["y"] == 2),
        "heat_high_observed_high_75_senior_days_all41": sum(aged75[r["planning_area"]] for r in risk["main"] if r["heat_level"] == "High" and r["y"] == 2),
        "heat_high_observed_high_area_days_all41": sum(1 for r in risk["main"] if r["heat_level"] == "High" and r["y"] == 2),
        "observed_high_75_senior_days_all41": sum(aged75[r["planning_area"]] for r in risk["main"] if r["y"] == 2),
        "heat_high_observed_high_75_senior_days_rated": sum(aged75[r["planning_area"]] for r in rated_rows["main"] if r["heat_level"] == "High" and r["y"] == 2),
        "heat_high_observed_high_area_days_rated": sum(1 for r in rated_rows["main"] if r["heat_level"] == "High" and r["y"] == 2),
    }

    # --- sensitivity: V against the main design, thirds, and back-test tier changes (main matrix)
    sens = []
    matrices = {"main": R.TIER_MAIN, "variant": R.TIER_VARIANT}
    base_tier = {m: {(r["target_date"], r["planning_area"]): r["tier"] for r in rated_rows[m]} for m in matrices}
    for name, desc, _, _ in variants(weights)[1:]:
        v = vs[name]
        rho = spearman({k: main_v[k]["v"] for k in rated}, {k: v[k]["v"] for k in rated})
        moved = [(k, main_v[k]["third"], v[k]["third"]) for k in rated if v[k]["third"] != main_v[k]["third"]]
        changes = {}
        for m, matrix in matrices.items():
            up = down = 0
            for r in R.heat_risk(fc, v, matrix):
                if not r["rated"]:
                    continue
                b = base_tier[m][(r["target_date"], r["planning_area"])]
                if r["tier"] != b:
                    up += SEVERITY[r["tier"]] > SEVERITY[b]
                    down += SEVERITY[r["tier"]] < SEVERITY[b]
            changes[m] = (up, down)
        sens.append({"name": name, "desc": desc, "rho": rho, "moved": moved, "changes": changes})

    # --- artifacts
    out = data / "analysis" / "risk_score_check"
    out.mkdir(parents=True, exist_ok=True)
    comp_cols = list(R.COMPONENTS)
    with (out / "area_vulnerability.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["planning_area", "v", "v_rank", "third", "reason", "neutral_components"]
                   + [f"raw_{k}" for k in comp_cols] + [f"p_{k}" for k in comp_cols])
        for k in sorted(rated, key=lambda k: main_v[k]["v_rank"]):
            x = main_v[k]
            w.writerow([k, repr(x["v"]), x["v_rank"], x["third"], x["reason"], x["neutral_components"] or ""]
                       + ["" if main_in[k]["raw"][c] is None else repr(main_in[k]["raw"][c]) for c in comp_cols]
                       + [repr(x["p"][c]) for c in comp_cols])
    with (out / "sensitivity_v.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        names = [n for n, *_ in variants(weights)]
        w.writerow(["planning_area"] + [f"v_{n}" for n in names] + [f"third_{n}" for n in names])
        for k in rated:
            w.writerow([k] + [repr(vs[n][k]["v"]) for n in names] + [vs[n][k]["third"] for n in names])
    with (out / "tier_counts.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["matrix", "season", "tier", "area_days"])
        for m in risk:
            for t in (*TIERS, R.NOT_RATED, R.NO_FORECAST):
                w.writerow([m, "all", t, counts[m].get(t, 0)])
            for s in seasons:
                for t in TIERS:
                    w.writerow([m, s, t, by_season[s][(m, t)]])
    with (out / "sensitivity.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["variant", "description", "spearman_v", "areas_changing_third", "main_area_days_up", "main_area_days_down",
                    "variant_area_days_up", "variant_area_days_down"])
        for s in sens:
            w.writerow([s["name"], s["desc"], repr(s["rho"]), len(s["moved"]), *s["changes"]["main"], *s["changes"]["variant"]])

    # --- report
    nd = len(days)
    L = ["# Risk score and tiers: back-test tier counts, reach and sensitivity", "",
         "Script: `scripts/analysis/risk_score_check.py`; rules: `src/coolcheck/risk.py` (the same rules as the SQL of the "
         "three views, compared row by row in `tests/static/test_risk_sql.py`); design: `docs/design/risk_score.md`. "
         "Artifacts: `coolcheck-data/analysis/risk_score_check/` (outside the repo). Nothing was loaded to Unity Catalog.", "",
         MARK[0], "MLflow: not logged yet.", MARK[1], "",
         f"Back-test rows: `{BACKTEST_RUN}/predictions_area_days.parquet`, read with `target_date <= {LAST_BACKTEST_DATE}` "
         f"and asserted: {n_rows:,} area-days, {first_day} to {last_day}, {nd} days, 41 areas. Of these, {n_rated:,} are in the "
         f"32 rated areas and {n_not:,} in the 9 not rated. The thirds use today's layers (population June 2026, refuges and "
         "parks October 2026) on every back-test day, a stated simplification.", "",
         "## 1. Tier counts in the back-test months, under both matrices", "",
         "Main matrix: decision 9 (Moderate heat gives Low in the lower third, Medium in the middle and upper thirds). "
         "Variant: Moderate heat in a middle-third area gives Low (decision 9(f), yours to decide). The High tier is the same "
         "under both.", ""]
    rows = []
    for t in TIERS:
        cm, cv = counts["main"].get(t, 0), counts["variant"].get(t, 0)
        rows.append([t, f"{cm:,}", pct(cm, n_rated), f"{cm / nd:.2f}", sum(1 for d in days if per_day['main'][t].get(d)),
                     max(per_day["main"][t].values(), default=0),
                     f"{cv:,}", pct(cv, n_rated), f"{cv / nd:.2f}", sum(1 for d in days if per_day['variant'][t].get(d)),
                     max(per_day["variant"][t].values(), default=0)])
    L += md_table(["tier", "main: area-days", "share of rated", "areas per day", "days with any", "most in a day",
                   "variant: area-days", "share of rated", "areas per day", "days with any", "most in a day"], rows)
    L += ["", f"Not rated: {counts['main'].get(R.NOT_RATED, 0):,} area-days (heat level only). No forecast: "
          f"{counts['main'].get(R.NO_FORECAST, 0):,} (every back-test row has its three probabilities). {nd} days; rated area-days "
          f"{n_rated:,}.", "",
          "Heat level by vulnerability third, rated area-days (the variant moves only the Moderate × middle cell from Medium to Low):", ""]
    L += md_table(["heat level", "lower third", "middle third", "upper third", "all"],
                  [[h] + [f"{cells.get((h, t), 0):,}" for t in R.THIRDS] + [f"{heat_rated.get(h, 0):,}"] for h in ("High", "Moderate", "Low")])
    L += ["", "By season and year (rated area-days):", ""]
    L += md_table(["season", "days", "rated area-days", "High", "Medium (main)", "Low (main)", "Medium (variant)", "Low (variant)"],
                  [[s, len(by_season[s]["days"]), f"{by_season[s]['rated']:,}", f"{by_season[s][('main', 'High')]:,}",
                    f"{by_season[s][('main', 'Medium')]:,}", f"{by_season[s][('main', 'Low')]:,}",
                    f"{by_season[s][('variant', 'Medium')]:,}", f"{by_season[s][('variant', 'Low')]:,}"] for s in seasons])
    L += ["", "## 2. Reach (residents aged 75+, June 2026; the same under both matrices)", "",
          f"- **Residents aged 75+ in High-tier areas per day:** mean {reach['tier_high_75_per_day_mean']:,.0f}, median "
          f"{reach['tier_high_75_per_day_median']:,.0f}, most {reach['tier_high_75_per_day_max']:,}; "
          f"{reach['tier_high_75_senior_days']:,} senior-days over {nd} days ({reach['tier_high_area_days']:,} High-tier area-days).",
          f"- **Headline: 75+ senior-days in areas correctly flagged High a day ahead** (tier High and an observed High day): "
          f"**{reach['tier_high_observed_high_75_senior_days']:,}** of {reach['observed_high_rated_75_senior_days']:,} 75+ "
          f"senior-days on observed High days in the rated areas "
          f"({pct(reach['tier_high_observed_high_75_senior_days'], reach['observed_high_rated_75_senior_days'])}); "
          f"{reach['tier_high_observed_high_area_days']:,} of {reach['observed_high_rated_area_days']:,} observed High area-days.",
          f"- **Beside it, heat level High and an observed High day:** rated areas {reach['heat_high_observed_high_75_senior_days_rated']:,} "
          f"senior-days ({reach['heat_high_observed_high_area_days_rated']:,} area-days); all 41 areas {reach['heat_high_observed_high_75_senior_days_all41']:,} of "
          f"{reach['observed_high_75_senior_days_all41']:,} ({reach['heat_high_observed_high_area_days_all41']:,} area-days, "
          f"the back-test's 355 caught). The gap to the tier figure is the High-heat days in lower-third areas, which are Medium.", "",
          "## 3. The vulnerability index (32 rated areas)", "",
          "Weights (`reference/score_weights.csv`): " + "; ".join(f"{w['component']} {w['weight']:.2f}" for w in weights)
          + ". Percentiles among the rated areas with a usable value; 0.5 when missing or over a small denominator (9(g)).", ""]
    L += md_table(["rank", "planning area", "third", "V", "reason", "75+", "75+ share", "1–2 room rental", "elec. ratio",
                   "beyond 400 m refuge", "refuges /1,000 65+", "beyond 400 m park", "held at 0.5"],
                  [[main_v[k]["v_rank"], k, main_v[k]["third"], f"{main_v[k]['v']:.3f}", main_v[k]["reason"],
                    f"{main_in[k]['aged_75_plus']:,}", "" if main_in[k]["raw"]["share_75_plus"] is None else f"{main_in[k]['raw']['share_75_plus']:.1%}",
                    f"{main_in[k]['raw']['rental_1_2_room']:,.0f}",
                    "" if main_in[k]["raw"]["electricity_hot_rise"] is None else f"{main_in[k]['raw']['electricity_hot_rise']:.3f}",
                    f"{main_in[k]['raw']['refuge_beyond_400m']:.1%}", f"{main_in[k]['raw']['refuges_per_1000_65']:.2f}",
                    f"{main_in[k]['raw']['park_beyond_400m']:.1%}",
                    ", ".join(c for c in main_v[k]["neutral"]) or ""] for k in sorted(rated, key=lambda k: main_v[k]["v_rank"])])
    flags = [k for k in rated if main_v[k]["neutral"]]
    L += ["", "Held at 0.5: " + "; ".join(f"{k}: {main_v[k]['neutral_components']}" for k in sorted(flags)) + ".", "",
          "## 4. Sensitivity runs", "",
          "Each against the main design: Spearman's rho of V over the 32 areas, the areas that change third, and the "
          "back-test's rated area-days that change tier (up = more severe), under each matrix. Under the main matrix the middle "
          "and upper thirds give the same tier, so only a move across the lower-third boundary (ranks 22 and 23) changes a "
          "tier; under the variant, Moderate heat separates the middle third from the upper too.", ""]
    L += md_table(["run", "what changes", "Spearman rho", "areas changing third", "main: up / down", "variant: up / down"],
                  [[s["name"], s["desc"], f"{s['rho']:.3f}", f"{len(s['moved'])}"
                    + (": " + ", ".join(f"{k} {f}→{t}" for k, f, t in s["moved"]) if s["moved"] else ""),
                    "{:,} / {:,}".format(*s["changes"]["main"]), "{:,} / {:,}".format(*s["changes"]["variant"])] for s in sens])
    L += ["", "## 5. Checks", "",
          f"- **Hard rule:** the back-test rows were read with `target_date <= {LAST_BACKTEST_DATE}` (pyarrow filter) and "
          f"asserted after the read; the latest date read is {last_day}. Nothing else read here is a dated observation.",
          f"- **Consistency with the back-test:** over all 41 areas the heat level gives {gate['alerts']:,} High area-days, "
          f"{gate['tp']:,} of them observed High, of {gate['high']:,} observed High, over {gate['days']} days, as in "
          "`backtest_review.md` (1,180, 355, 710, 427).",
          f"- **Weights:** {len(weights)} components summing to {sum(w['weight'] for w in weights):.2f}; thirds 11 / 11 / 10.",
          f"- **400 m flags:** blocks whose stored distance (2 decimals) to the nearest refuge or park lies within 0.01 m of "
          f"400 m: {near}, so the flags `gold.block_vulnerability` reads from the stored distance cannot differ from the "
          "unrounded distance the area shares used." if near == 0 else
          f"- **400 m flags:** {near} blocks lie within 0.01 m of 400 m, so their flag may differ from the area shares' rule.",
          "- **SQL against Python:** the views' SQL is compared with these rules on the same rows in "
          "`tests/static/test_risk_sql.py` (Databricks Connect, temp views only).", "",
          "## 6. Limits", "",
          "- The weights are a judgement (decision 9(b)), not fitted: there is no open outcome data to fit them to. Section 4 "
          "shows how much they matter. They are not yet reviewed by a practitioner, nor are the actions.",
          "- The AAC layer is partial (93 of about 223), so the refuge components overstate the gap where AACs are missing; "
          "`refuges_with_sac_2016` bounds the effect.",
          "- The electricity term is weak (a smaller rise may indicate less air-con use, no more) and missing for 4 rated areas.",
          "- Back-test tiers apply today's vulnerability thirds to every day from July 2025.", ""]
    report = REPO / "docs/checks/risk_score.md"
    report.write_text("\n".join(L), encoding="utf-8")

    metrics = {**{f"gate_{k}": v for k, v in gate.items()}, "rated_area_days": n_rated, "not_rated_area_days": n_not,
               "days": nd, "rated_areas": len(rated), "blocks_within_1cm_of_400m": near}
    for m in risk:
        for t in (*TIERS, R.NOT_RATED, R.NO_FORECAST):
            metrics[f"tier_{m}_{t.replace(' ', '_')}_area_days"] = counts[m].get(t, 0)
        for t in TIERS:
            metrics[f"tier_{m}_{t}_days_with_any"] = sum(1 for d in days if per_day[m][t].get(d))
    metrics.update(reach)
    for s in sens:
        metrics[f"sens_{s['name']}_spearman_v"] = s["rho"]
        metrics[f"sens_{s['name']}_areas_changing_third"] = len(s["moved"])
        for m, (up, down) in s["changes"].items():
            metrics[f"sens_{s['name']}_{m}_area_days_up"] = up
            metrics[f"sens_{s['name']}_{m}_area_days_down"] = down
    params = {"weights": ";".join(f"{w['component']}={w['weight']}" for w in weights),
              "high_cutoff": repr(R.HIGH_CUTOFF), "thirds": f"{R.UPPER}/{R.MIDDLE}/rest", "small_area_min": str(R.FLAG_MIN),
              "small_area_rule": "9(g): 400 m shares by confirmed HDB DU, 75+ share by residents, refuges per 1,000 by aged 65+",
              "matrix_variant": "Moderate x middle -> Low", "backtest_run": BACKTEST_RUN,
              "last_backtest_date": str(LAST_BACKTEST_DATE), "backtest_rows": str(n_rows),
              **{f"sha256_{k}": sha256(data / v) for k, v in INPUTS.items()},
              "sha256_predictions_area_days": sha256(pq_path), "sha256_score_weights": sha256(WEIGHTS)}
    run = {"run_name": "risk_score_check", "role": "risk_score_check", "params": params, "metrics": metrics,
           "artifacts": [str(p) for p in sorted(out.glob("*.csv"))] + [str(report)], "report": str(report),
           "code_files": CODE_FILES}
    (out / "run.json").write_text(json.dumps(run, indent=1, default=str), encoding="utf-8")
    print(f"rated area-days {n_rated:,}; main {dict(counts['main'])}; variant {dict(counts['variant'])}")
    print(f"wrote {out} and docs/checks/risk_score.md")


if __name__ == "__main__":
    main()
