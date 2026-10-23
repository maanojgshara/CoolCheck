"""Error analysis (M1) and a calibration check (M2) of the back-test, from its saved predictions (no workspace access).
M1: at the H4 cut-off, the missed High days and false alarms by station, month and season; the misses split by High
readings, by the day before and by what the model saw; where the misses sit. M2: the reliability of P(High) in pooled
deciles, pooled and by season. Analysis only: nothing here changes the model, its features, the back-test or the cut-off.

Every dated input is filtered to dates on or before 2026-08-31 as it is read, and asserted: the final check (1 Sep to
19 Oct 2026) is not read.

Run from the repo root:
    .venv\\Scripts\\python scripts/analysis/error_analysis.py [--artifacts <dir>] [--out docs/checks/error_analysis.md]
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

from backtest_review import HIGH, PEAK, RUN, SGT, md  # noqa: E402
from coolcheck.backtest import season_period  # noqa: E402
from coolcheck.features import LATE_STARTERS, ORIGINAL_8  # noqa: E402
from eda import BLUE, GREY, INK2, ORANGE, plt, style  # noqa: E402

CUT = 0.10975585695894975  # H4: P(High) at or above it alerts (back-test design note §14)
LAST = pd.Timestamp("2026-08-31")
EXPECT = {"alerts": 1180, "tp": 355, "high": 710}  # backtest_review.md, area-days at overall recall 0.5
SETS = {"area": "area-days (41 areas)", "all": "station-days, all stations",
        "wo3": "station-days, without S142, S137 and S135", "o8": "station-days, the original 8 (7 after S130 stopped)"}
FIGS = "error_analysis_figs"
YOUNG = "in the station's first 30 days"


# ---------------------------------------------------------------- reads (dates on or before 2026-08-31 only)
def read_predictions(path):
    df = pd.read_parquet(path, filters=[("target_date", "<=", LAST)])
    assert df.target_date.max() <= LAST, f"{path.name}: a target date after {LAST:%Y-%m-%d}"
    return df


def read_labels(path):
    """The run's pinned labels; each chunk is cut to sgt_date <= 2026-08-31 before it is kept."""
    chunks = pd.read_csv(path, usecols=["station_id", "sgt_date", "label", "usable"], parse_dates=["sgt_date"],
                         chunksize=50_000)
    df = pd.concat([c[c.sgt_date <= LAST] for c in chunks], ignore_index=True)
    assert df.sgt_date.max() <= LAST, f"{path.name}: an sgt_date after {LAST:%Y-%m-%d}"
    return df


# ---------------------------------------------------------------- helpers
def of(x, n):
    x, n = int(x), int(n)
    return f"{x:,} of {n:,} ({x / n:.3f})" if n else f"{x:,} of 0 (—)"


def annotate(frame, labels):
    """Alert, miss and false alarm at the cut-off; month, season, yesterday's pinned label at the row's station, and
    whether the row is in the station's first 30 days (from its first pinned label)."""
    f = frame.copy()
    f["high"] = f.y == HIGH
    f["alert"] = f.p_high >= CUT
    f["missed"] = f.high & ~f.alert
    f["false_alarm"] = f.alert & ~f.high
    f["month"] = f.target_date.dt.strftime("%Y-%m")
    f["season_year"] = f.target_date.map(season_period)
    prev = labels.assign(target_date=labels.sgt_date + np.timedelta64(1, "D"))[["station_id", "target_date", "label",
                                                                                "usable"]]
    f = f.merge(prev, on=["station_id", "target_date"], how="left", validate="many_to_one")
    f["label_d1"] = f.label.where(f.usable.eq(True), "no usable label")
    assert not (f.high & (f.label_n_high < 1)).any(), "a High day with no High reading"
    f["readings"] = np.where(f.label_n_high >= 3, "3 or more High readings (sustained)", "1 or 2 High readings")
    f["yesterday"] = np.select([f.n_high_d1.isna(), f.n_high_d1 >= 1], ["no WBGT reading yesterday", "High yesterday"],
                               "not High yesterday")
    f["forecast"] = np.where(f.forecast_missing, "no qualifying forecast (filled)",
                             f.nea_score.map(lambda v: f"{v:g} °C"))
    age = (f.target_date - f.station_id.map(labels.groupby("station_id").sgt_date.min())).dt.days
    f["station_age"] = np.where(age < 30, YOUNG, "later")
    return f.drop(columns=["label", "usable"])


def chrono(frame, col):
    return list(frame.groupby(col).target_date.min().sort_values().index)


def errors(frame, col, order, extra=None):
    """Per group: High, alerts, the missed High of the group's High, the false alarms of its alerts (Moderate, Low)."""
    rows = []
    for k in [*order, "all"]:
        d = frame if k == "all" else frame[frame[col] == k]
        fa = d[d.false_alarm]
        rows.append({col: k, **(extra(k, d) if extra else {}), "rows": len(d), "High": int(d.high.sum()),
                     "alerts": int(d.alert.sum()), "missed High": of(d.missed.sum(), d.high.sum()),
                     "false alarms": of(len(fa), d.alert.sum()), "false alarms on Moderate": int((fa.y == 1).sum()),
                     "false alarms on Low": int((fa.y == 0).sum())})
    return pd.DataFrame(rows)


def split(named, col, order, head):
    """The High rows of each set split by `col`: missed of the group's High, and the group's share of the set's misses."""
    rows = []
    for key, f in named.items():
        h = f[f.high]
        for k in [*order, "all High"]:
            d = h if k == "all High" else h[h[col] == k]
            rows.append({"set": SETS[key] if k == order[0] else "", head: k, "High": len(d),
                         "missed": of(d.missed.sum(), len(d)), "share of the set's misses": of(d.missed.sum(),
                                                                                               h.missed.sum())})
    return pd.DataFrame(rows)


def panel(s):
    return "original 8" if s in ORIGINAL_8 else ("late starter" if s in LATE_STARTERS else "")


def station_rank(area, st, names):
    """Stations by area-day misses, with their station-day misses and the areas they served."""
    rows = []
    for s in sorted(set(area.station_id) | set(st.station_id)):
        a, t = area[area.station_id == s], st[st.station_id == s]
        if not (a.high.any() or t.high.any()):
            continue
        rows.append({"station": s, "name": names.get(s, ""), "panel": panel(s),
                     "station-days missed": of(t.missed.sum(), t.high.sum()),
                     "share of station-day misses": of(t.missed.sum(), st.missed.sum()),
                     "area-days missed": of(a.missed.sum(), a.high.sum()),
                     "share of area-day misses": of(a.missed.sum(), area.missed.sum()),
                     "areas served": a.planning_area.nunique(), "_a": int(a.missed.sum()), "_t": int(t.missed.sum())})
    return (pd.DataFrame(rows).sort_values(["_a", "_t", "station"], ascending=[False, False, True])
            .drop(columns=["_a", "_t"]).reset_index(drop=True))


def area_rank(area, top=10):
    g = area.groupby("planning_area").agg(missed=("missed", "sum"), high=("high", "sum")).reset_index()
    g = g.sort_values(["missed", "high", "planning_area"], ascending=[False, False, True]).head(top)
    rows = []
    for r in g.itertuples(index=False):
        d = area[area.planning_area == r.planning_area]
        by = d[d.missed].station_id.value_counts()
        rows.append({"planning area": r.planning_area, "area-days": len(d), "missed High": of(r.missed, r.high),
                     "share of area-day misses": of(r.missed, area.missed.sum()),
                     "stations behind its misses": ", ".join(f"{s} ({n})" for s, n in by.items())})
    return pd.DataFrame(rows)


def served_by(area, s):
    d = area[area.station_id == s]
    rows = []
    for p in sorted(d.planning_area.unique()):
        x = d[d.planning_area == p]
        rows.append({"planning area": p, f"area-days served by {s}": len(x), "of its area-days": of(len(x), (
            area.planning_area == p).sum()), "missed High": of(x.missed.sum(), x.high.sum()),
                     "false alarms": of(x.false_alarm.sum(), x.alert.sum())})
    return pd.DataFrame(rows)


def medians(named):
    rows = []
    for key, f in named.items():
        h = f[f.high]
        for name, d in (("missed", h[h.missed]), ("caught", h[~h.missed])):
            pk, fc = d.wbgt_peak_d1.dropna(), d.loc[~d.forecast_missing, "nea_score"]
            rows.append({"set": SETS[key] if name == "missed" else "", "High days": name, "rows": len(d),
                         "yesterday's peak WBGT, median °C": f"{pk.median():.1f} (n = {len(pk):,})",
                         "forecast max temperature, median °C": f"{fc.median():g} (n = {len(fc):,})"})
    return pd.DataFrame(rows)


def findings(named, peak, q, first):
    """M1.4: each line states its counts (measured) and, where given, an interpretation of them (reading)."""
    area, st = named["area"], named["all"]
    ha, hs = area[area.high], st[st.high]
    m = lambda d: int(d.missed.sum())
    ofm = lambda d: of(m(d), len(d))
    by = lambda h, col, v: h[h[col] == v]
    fa_a, fa_s = area[area.false_alarm], st[st.false_alarm]
    s9 = hs[(hs.station_id == "S142") & (hs.month == "2025-09")]
    s142a, s142s = ha[ha.station_id == "S142"], hs[hs.station_id == "S142"]
    pa, ps = peak["area"][peak["area"].high], peak["all"][peak["all"].high]
    stn = lambda h, s: h[h.station_id == s]
    areas = lambda s: area.loc[area.station_id == s, "planning_area"].nunique()
    fc = lambda v: ha[~ha.forecast_missing & (ha.nea_score == v)]
    fc_med = lambda d: d.loc[~d.forecast_missing, "nea_score"].median()
    mar = lambda f: f[(f.month == "2026-03")]
    wo3, o8 = named["wo3"], named["o8"]
    big = hs.groupby("station_id").agg(n=("high", "size"), rate=("missed", "mean")).query("n >= 10").rate
    s142_rank = (f"the lowest of the {len(big)}" if big.idxmin() == "S142"
                 else f"rank {int(big.rank()['S142'])} of the {len(big)}")
    first_a, later_a = by(ha, "yesterday", "not High yesterday"), by(ha, "yesterday", "High yesterday")
    assert len(first_a) + len(later_a) == len(ha), "a High area-day with no WBGT reading the day before"
    assert area.persist_alert.eq(area.yesterday == "High yesterday").all(), "persistence is not 'High yesterday'"
    side = pd.DataFrame([{"High area-days": name, "High": len(d),
                          "caught by the model (P(High) ≥ cut-off)": of(d.alert.sum(), len(d)),
                          "caught by persistence (High yesterday)": of(d.persist_alert.sum(), len(d))}
                         for name, d in (("first day of a spell (not High yesterday)", first_a),
                                         ("later day of a spell (High yesterday)", later_a), ("all High", ha))])
    beside = ["", "   *Measured, beside persistence (area-days).* Persistence alerts when the station was High "
              "yesterday, so by construction it catches every later day of a spell and no first day. It alerts on "
              f"{int(area.persist_alert.sum()):,} area-days and the model at the cut-off on {int(area.alert.sum()):,}, "
              "so the two are not at the same load; at the same load (the model's 700 highest P(High)) the back-test "
              "found both catch 245 of 710 High area-days (`backtest.md`).", ""] + ["   " + r for r in md(side)]
    M, R = "*Measured.*", "*Reading* (an interpretation, not a measurement)."
    F = [
        ("The model misses the first day of a hot spell.",
         f"{M} On the area-days it misses {ofm(by(ha, 'yesterday', 'not High yesterday'))} first High days (not High "
         f"the day before) against {ofm(by(ha, 'yesterday', 'High yesterday'))} later days of a spell; first days are "
         f"{of(m(by(ha, 'yesterday', 'not High yesterday')), m(ha))} of the misses. Station-days, all stations: "
         f"{ofm(by(hs, 'yesterday', 'not High yesterday'))} against {ofm(by(hs, 'yesterday', 'High yesterday'))}. On "
         f"{of(m(by(ha, 'label_d1', 'Moderate')), m(ha))} missed area-days the day before was Moderate.",
         f"{R} The model leans on the day before (yesterday's peak and its High readings); a spell's first day follows "
         "a day that looks like any other Moderate day, so it scores low.", beside),
        ("Short High days are missed more often than sustained ones.",
         f"{M} Area-days with 1 or 2 High readings: {ofm(ha[ha.label_n_high < 3])} missed; with 3 or more: "
         f"{ofm(ha[ha.label_n_high >= 3])}. Short days are {of(m(ha[ha.label_n_high < 3]), m(ha))} of the misses. "
         f"Station-days, all stations: {ofm(hs[hs.label_n_high < 3])} against {ofm(hs[hs.label_n_high >= 3])}.",
         f"{R} A day that reaches High for one or two readings sits at the category boundary; some of these labels are "
         "likely noise (near-equidistant stations' daily categories differ on 22% of days, `backtest.md`)."),
        ("On a missed day, yesterday was cooler.",
         f"{M} Median yesterday's peak WBGT: {ha[ha.missed].wbgt_peak_d1.median():.1f} °C on missed against "
         f"{ha[~ha.missed].wbgt_peak_d1.median():.1f} °C on caught High area-days. Below {q[1]:.1f} °C (the median "
         f"of yesterday's peak over the High station-days) the model misses {ofm(ha[ha.wbgt_peak_d1 < q[1]])}; at "
         f"{q[2]:.1f} °C or above, {ofm(ha[ha.wbgt_peak_d1 >= q[2]])}.", ""),
        ("The NEA forecast's max temperature does not separate missed from caught High days.",
         f"{M} Median forecast {fc_med(ha[ha.missed]):g} °C on missed and {fc_med(ha[~ha.missed]):g} °C on caught High "
         f"area-days. Misses at a forecast of 33 °C: {ofm(fc(33))}; 34 °C: {ofm(fc(34))}; 35 °C: {ofm(fc(35))}. "
         f"{of(len(fc(33)) + len(fc(34)), len(ha))} High area-days had a forecast of 33 or 34 °C. Not checked: the "
         "forecast text and the rainfall the day before, which are not in the prediction files.",
         f"{R} With nearly every High day forecast at 33 or 34 °C, the forecast max temperature cannot rank one High "
         "day above another. Whether it separates High from Moderate days is not measured here."),
        ("S142's first month was missed entirely; other new stations were not worse than old ones.",
         f"{M} S142's first pinned label is {first['S142']:%d %b %Y}. In Sep 2025 the model missed {ofm(s9)} of its "
         f"High station-days, although {int((s9.yesterday == 'High yesterday').sum())} of them followed a High day; "
         f"its highest P(High) on them was {s9.p_high.max():.3f}, below the cut-off. From Oct 2025 it missed "
         f"{ofm(s142s[s142s.month >= '2025-10'])}. Over all stations, High days in a station's first 30 days: "
         f"{ofm(by(hs, 'station_age', YOUNG))} missed, later {ofm(by(hs, 'station_age', 'later'))}; without S142, "
         f"S137 and S135 the order reverses: {ofm(by(wo3[wo3.high], 'station_age', YOUNG))} against "
         f"{ofm(by(wo3[wo3.high], 'station_age', 'later'))}.",
         f"{R} The station-character input needs 20 of a station's last 30 days (`features.py`) and the folds before "
         "Sep 2025 hold no S142 rows, so the model scored S142 like an average station until it had seen it; this "
         "matters for a new station that runs hot, as S142 does, and not in general."),
        ("The start of a hot season is missed.",
         f"{M} Mar 2026: {ofm(mar(ha))} High area-days missed ({ofm(mar(hs))} station-days), with "
         f"{int(mar(area).alert.sum())} area-day alerts in the month. Sep 2025: {ofm(ha[ha.month == '2025-09'])}, "
         f"{m(s142a[s142a.month == '2025-09'])} of them S142's first month (finding 5). "
         f"NE monsoon 2025/26: {ofm(ha[ha.season_year == 'NE monsoon 2025/26'])}. Later in a hot season the share "
         f"falls: SW monsoon 2026 {ofm(ha[ha.season_year == 'SW monsoon 2026'])}, Aug 2026 "
         f"{ofm(ha[ha.month == '2026-08'])}.",
         f"{R} The Mar 2026 fold trained on 141 High of 4,769 station-days (`backtest.md`), so P(High) stays low until "
         "a season's own High days enter training."),
        ("The briefing's misses sit with central stations that serve many areas, not with S142.",
         f"{M} S142 has the most High station-days ({of(len(s142s), len(hs))}), and its miss rate ({ofm(s142s)}) is "
         f"{s142_rank} stations with 10 or more High station-days. It serves {areas('S142')} area (Southern Islands), "
         f"so it carries {of(m(s142a), m(ha))} of the area-day misses ({of(m(s142s), m(hs))} of the station-day misses); "
         f"in Apr to Jun 2026, {ofm(stn(ps, 'S142'))} of its High days were missed. S144 (Upper Pickering Street) "
         f"misses {ofm(stn(hs, 'S144'))} of its High station-days and serves {areas('S144')} areas, so it carries "
         f"{of(m(stn(ha, 'S144')), m(ha))} of the area-day misses ({of(m(stn(pa, 'S144')), m(pa))} in Apr to Jun "
         f"2026). S128 (Bishan Street): {ofm(stn(hs, 'S128'))}, {areas('S128')} areas, "
         f"{of(m(stn(ha, 'S128')), m(ha))}. S137 (Sakra Road) misses {ofm(stn(hs, 'S137'))} but serves no area, so "
         "none of its misses reach the briefing.",
         f"{R} One missed station-day at S144 is up to {areas('S144')} missed area-days; an error at a station that "
         "serves many areas costs the briefing most."),
        ("Outside the three late starters the model misses more than half of the High days.",
         f"{M} Without S142, S137 and S135: {ofm(wo3[wo3.high])} missed, and {of(wo3.false_alarm.sum(), wo3.alert.sum())} "
         f"alerts were false alarms. The original 8: {ofm(o8[o8.high])} missed, "
         f"{of(o8.false_alarm.sum(), o8.alert.sum())} false alarms. All stations: {ofm(hs)}; the back-test's own "
         "PR-AUC for the set without the three is 0.179 against 0.340 for all stations (`backtest.md`).",
         f"{R} At this cut-off much of the model's skill on High days comes from the hot late starters."),
        ("Most false alarms are warm days, not cool ones.",
         f"{M} {of(len(fa_a), area.alert.sum())} area-day alerts were not High: "
         f"{of((fa_a.y == 1).sum(), len(fa_a))} Moderate and {of((fa_a.y == 0).sum(), len(fa_a))} Low. Station-days, "
         f"all stations: {of(len(fa_s), st.alert.sum())}, of which {of((fa_s.y == 1).sum(), len(fa_s))} Moderate.", ""),
    ]
    L = []
    for i, (head, meas, read, *extra) in enumerate(F, 1):  # extra: lines indented under the finding
        L += [f"{i}. **{head}** {meas}" + (f" {read}" if read else ""), *(extra[0] if extra else []), ""]
    return L


def calibration_summary(named, edges, seasons):
    L = []
    for key in ("area", "all"):
        f, e = named[key], edges[key]
        top = f[f.p_high >= e[9]]
        L.append(f"- {SETS[key]}: mean P(High) {f.p_high.mean():.3f} against an observed {of(f.high.sum(), len(f))}; "
                 f"top decile mean {top.p_high.mean():.3f} against {of(top.high.sum(), len(top))}; by season, mean "
                 "against observed: " + "; ".join(
                     f"{s} {f.loc[f.season_year == s, 'p_high'].mean():.3f} against "
                     f"{of(f.loc[f.season_year == s, 'high'].sum(), (f.season_year == s).sum())}" for s in seasons) + ".")
    a, e = named["area"], edges["area"]
    low = a[a.p_high < e[1]]
    alerts = {k: named[k][named[k].alert] for k in ("area", "all")}
    L += [f"- Area-days in the lowest decile (P(High) below {e[1]:.4f}) hold {of(low.high.sum(), len(low))} High, "
          f"{int(low[low.season_year == 'SW monsoon 2025'].high.sum())} of them in SW monsoon 2025.",
          f"- {of((a.alert & (a.p_high >= e[9])).sum(), a.alert.sum())} area-day alerts fall in the top decile, so the "
          "deciles alone do not resolve P(High) above the cut-off; \"The top decile in five equal-count bins\" splits "
          "it. Rows at or above the cut-off: " + "; ".join(
              f"{SETS[k]}, mean P(High) {d.p_high.mean():.3f} against an observed {of(d.high.sum(), len(d))}"
              for k, d in alerts.items()) + "."]
    gaps, top_bin = [], []
    for k in ("area", "all"):
        top, _, b = top_bins(named[k], edges[k])
        g = top.assign(b=b).groupby("b").agg(p=("p_high", "mean"), n=("high", "size"), h=("high", "sum"))
        gaps.append(f"{SETS[k]} " + ", ".join(f"{r.h / r.n - r.p:+.3f}" for r in g.itertuples()))
        r = g.iloc[-1]
        top_bin.append(f"{SETS[k]} {r.p:.3f} against {of(r.h, r.n)}")
    L += ["- In the top decile's five equal-count bins, observed rate minus mean P(High), lowest bin to highest: "
          + "; ".join(gaps) + ". The highest bin, mean P(High) against observed: " + "; ".join(top_bin) + ".", "",
          "*Reading* (an interpretation, not a measurement). Over its alerts P(High) is about right on average but too "
          "spread out: its highest values over-state the chance of High and the lower values in the alert range "
          "under-state it. It is too low over Inter-monsoon 1 2026, the season with most High days. Quoted as a rate on "
          "the briefing, P(High) would over-state the chance at its highest values and under-state it at the start of a "
          "hot season. The rows are not independent (area-days repeat station-days, and days in a spell are "
          "correlated), so the bins are noisier than their counts suggest and gaps of this size could come from noise; "
          "no interval is given.", ""]
    return L


# ---------------------------------------------------------------- M2
def deciles(p):
    e = np.quantile(p, np.linspace(0, 1, 11))
    assert (np.diff(e) > 0).all(), "tied decile edges"
    return e


def reliability(frame, edges, total="all"):
    """A row per bin of P(High) between consecutive edges, then the total; marks the bin that holds the cut-off when
    the edges span it."""
    n = len(edges) - 1
    b = np.searchsorted(edges[1:-1], frame.p_high.to_numpy(), side="right")  # an edge value goes to the bin above it
    cut_bin = int(np.searchsorted(edges[1:-1], CUT, side="right")) if edges[0] <= CUT <= edges[-1] else None
    rows = []
    for i in [*range(n), None]:
        d = frame if i is None else frame[b == i]
        hi = "]" if i == n - 1 else ")"
        rows.append({"bin": total if i is None else i + 1,
                     "P(High) range": "" if i is None else f"[{edges[i]:.4f}, {edges[i + 1]:.4f}{hi}",
                     "rows": len(d), "mean P(High)": f"{d.p_high.mean():.4f}" if len(d) else "—",
                     "observed High": of(d.high.sum(), len(d)),
                     "cut-off": (f"{CUT:.3f} in this bin; {of((d.p_high >= CUT).sum(), len(d))} rows at or above it"
                                 if i is not None and i == cut_bin else "")})
    return pd.DataFrame(rows)


def reliability_by_season(frame, edges, seasons):
    out = []
    for s in seasons:
        t = reliability(frame[frame.season_year == s], edges)
        t.insert(0, "season", [s] + [""] * (len(t) - 1))
        out.append(t)
    return pd.concat(out, ignore_index=True)


def top_bins(frame, e):
    """The top decile's rows, its five equal-count edges (from its own rows), and each row's bin (0 to 4)."""
    top = frame[frame.p_high >= e[9]]
    sub = np.r_[e[9], np.quantile(top.p_high, [0.2, 0.4, 0.6, 0.8]), e[10]]
    assert (np.diff(sub) > 0).all(), "tied edges in the top decile"
    return top, sub, np.searchsorted(sub[1:-1], top.p_high.to_numpy(), side="right")


def top_decile_split(named, edges):
    """Each set's top decile in five equal-count bins."""
    out = []
    for key in ("area", "all"):
        top, sub, _ = top_bins(named[key], edges[key])
        t = reliability(top, sub, total="top decile")
        t.insert(0, "set", [SETS[key]] + [""] * (len(t) - 1))
        out.append(t)
    return pd.concat(out, ignore_index=True)


def fig_reliability(figs_dir, curves):
    style()
    fig, ax = plt.subplots(figsize=(6.4, 5.2))
    top = max(max(t["mean P(High)"].max(), t["rate"].max()) for t, _, _ in curves) * 1.08
    ax.plot([0, top], [0, top], color=GREY, lw=1, ls="--", zorder=1)
    ax.text(top * 0.62, top * 0.56, "predicted = observed", color=INK2, fontsize=8, ha="left", va="top")
    ax.axvline(CUT, color=GREY, lw=1, ls=":", zorder=1)
    ax.text(CUT + top * 0.01, top * 0.02, f"cut-off {CUT:.3f}", color=INK2, fontsize=8)
    for t, colr, name in curves:
        ax.plot(t["mean P(High)"], t["rate"], color=colr, lw=1.6, marker="o", ms=6, mec="white", mew=1.2,
                label=name, zorder=3)
        ax.annotate(name, (t["mean P(High)"].iloc[-1], t["rate"].iloc[-1]), xytext=(-6, 6),
                    textcoords="offset points", ha="right", fontsize=8.5, color=INK2)
    ax.set_xlim(0, top)
    ax.set_ylim(0, top)
    ax.set_xlabel("mean P(High) in the decile")
    ax.set_ylabel("observed High rate in the decile")
    ax.set_title("Reliability of P(High), pooled deciles, Jul 2025 to Aug 2026")
    ax.grid(axis="both")
    ax.legend(loc="upper left", frameon=False, fontsize=8.5)
    fig.tight_layout()
    figs_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(figs_dir / "reliability.png", dpi=130)
    plt.close(fig)
    return f"{FIGS}/reliability.png"


# ---------------------------------------------------------------- report
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifacts", default=str(REPO.parent / "coolcheck-data" / "analysis" / "backtest_run_c509ab9a"))
    ap.add_argument("--out", default=str(REPO / "docs" / "checks" / "error_analysis.md"))
    a = ap.parse_args()
    art, out = Path(a.artifacts), Path(a.out)
    labels = read_labels(art / "labels_pinned.csv")
    area = annotate(read_predictions(art / "predictions_area_days.parquet"), labels)
    st = annotate(read_predictions(art / "predictions_station_days.parquet"), labels)
    names = pd.read_csv(art.parent / "wbgt_stations.csv", usecols=["station", "name"]).set_index("station").name
    names = names.to_dict()  # station names only; the file's dates are not read into anything
    last_read = max(area.target_date.max(), st.target_date.max(), labels.sgt_date.max())
    assert last_read <= LAST
    got = {"alerts": int(area.alert.sum()), "tp": int((area.alert & area.high).sum()), "high": int(area.high.sum())}
    assert got == EXPECT, f"area-days at the cut-off {got} differ from backtest_review.md {EXPECT}"
    hp = st.loc[st.high, "wbgt_peak_d1"].dropna().to_numpy()
    q = np.quantile(hp, [0.25, 0.5, 0.75], method="lower")  # observed values, so a band edge is a real reading
    band_names = [f"below {q[0]:.1f} °C", f"{q[0]:.1f} to below {q[1]:.1f} °C", f"{q[1]:.1f} to below {q[2]:.1f} °C",
                  f"{q[2]:.1f} °C or above"]
    for f in (area, st):
        f["peak_band"] = (pd.cut(f.wbgt_peak_d1, [-np.inf, *q, np.inf], right=False, labels=band_names)
                          .astype(object).fillna("no WBGT reading yesterday"))
    named = {"area": area, "all": st, "wo3": st[~st.station_id.isin(LATE_STARTERS)],
             "o8": st[st.station_id.isin(ORIGINAL_8)]}
    months, seasons = sorted(st.month.unique()), chrono(st, "season_year")
    peak = {k: f[f.target_date.between(PEAK[0], PEAK[1], inclusive="left")] for k, f in named.items()}
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()

    L = ["# Back-test error analysis (M1) and calibration check (M2)", "",
         f"Generated {datetime.now(SGT):%Y-%m-%d %H:%M} SGT by `scripts/analysis/error_analysis.py` at git `{sha}` from the "
         f"artifacts of MLflow run `{RUN}` (the run of `docs/checks/backtest.md`), saved in `{art.name}` under "
         "`coolcheck-data/analysis/`: `predictions_area_days.parquet`, `predictions_station_days.parquet` and "
         "`labels_pinned.csv` (the run's pinned labels, for yesterday's category), plus the station names in "
         "`wbgt_stations.csv`. Analysis only: the model, its features, the back-test and the cut-off are unchanged.", "",
         f"**Dates.** Every dated input is filtered to dates on or before {LAST:%Y-%m-%d} as it is read (a parquet filter; "
         f"the CSV chunk by chunk), and the script asserts it. The latest date read is {last_read:%Y-%m-%d}. The final "
         "check (1 Sep to 19 Oct 2026) is not read, counted or plotted.", "",
         f"**Cut-off.** H4: an alert is P(High) ≥ {CUT!r} (note §14). Check against `backtest_review.md`: the area-days "
         f"give {got['alerts']:,} alerts and {got['tp']:,} TP of {got['high']:,} High, as there. Station-days use the "
         "same cut-off on their own P(High); it was chosen on the area-days, so their recall differs.", "",
         "**Terms.** A *miss* is a High day without an alert. A *false alarm* is an alert on a day that was not High "
         "(Moderate or Low). Rates are written \"X of Y (rate)\": misses of the High days, false alarms of the alerts. "
         "An area-day repeats its station's station-day once per area the station serves that day, so the area-day "
         "counts weight a station by the number of areas it serves.", "",
         "**Not available.** The NEA forecast text and the rainfall the day before (`rain_d1_mm`) are model features but "
         "are not in the prediction files, and no local file has them for the test rows (`forecast_fills.csv` has the "
         "text for the 4 filled dates only). They are not rebuilt here. What the model saw of the forecast is covered by "
         "its max temperature (`nea_score`, the forecast's `fc_temp_high` after the fill).", ""]

    L += ["## Overview at the cut-off", ""]
    rows = []
    for key, f in named.items():
        fa = f[f.false_alarm]
        rows.append({"set": SETS[key], "rows": len(f), "High": int(f.high.sum()), "alerts": int(f.alert.sum()),
                     "caught": of((f.alert & f.high).sum(), f.high.sum()), "missed": of(f.missed.sum(), f.high.sum()),
                     "false alarms": of(len(fa), f.alert.sum()), "on Moderate": int((fa.y == 1).sum()),
                     "on Low": int((fa.y == 0).sum())})
    L += md(pd.DataFrame(rows)) + [""]

    # M1.1
    L += ["## M1.1 Misses and false alarms by station, month and season", "",
          "Seasons are the run's season by year (`season_period`); within the test months SW monsoon 2025 is Jul to Sep "
          "2025 and SW monsoon 2026 is Jun to Aug 2026.", ""]
    area_extra = lambda s, d: {"name": names.get(s, "") if s != "all" else "", "panel": panel(s) if s != "all" else "",
                               "areas served": d.planning_area.nunique()}
    st_extra = lambda s, d: {"name": names.get(s, "") if s != "all" else "", "panel": panel(s) if s != "all" else ""}
    season_extra = lambda s, d: {"months": f"{d.target_date.min():%b %Y} to {d.target_date.max():%b %Y}"}
    L += ["### By station", "", f"#### {SETS['area']}, by the station serving the area", ""]
    L += md(errors(area, "station_id", sorted(area.station_id.unique()), area_extra)) + [""]
    L += [f"#### {SETS['all']}", "", "The sets without S142, S137 and S135 and the original 8 are these rows "
          "(see the panel column).", ""]
    L += md(errors(st, "station_id", sorted(st.station_id.unique()), st_extra)) + [""]
    for col, title, order, extra in (("month", "By month", months, None),
                                     ("season_year", "By season", seasons, season_extra)):
        L += [f"### {title}", ""]
        for key, f in named.items():
            L += [f"#### {SETS[key]}", ""] + md(errors(f, col, [o for o in order if o in set(f[col])], extra)) + [""]

    # M1.2
    L += ["## M1.2 The misses split", "",
          "High days only. Each block is one set; \"missed\" is of the group's High days, \"share\" of the set's misses.",
          ""]
    L += ["### High readings that day (`label_n_high`)", ""]
    L += md(split(named, "readings", ["1 or 2 High readings", "3 or more High readings (sustained)"], "High readings"))
    L += ["", "### First day of a spell or a later day: yesterday as the model saw it (`n_high_d1`)", "",
          "\"High yesterday\" (a later day of a spell) is one or more High readings at the row's station on the day "
          "before (persistence's rule); \"not High yesterday\" is the first High day; \"no WBGT reading yesterday\" is a "
          "station with no reading that day (the model saw a missing value).", ""]
    L += md(split(named, "yesterday", ["not High yesterday", "High yesterday", "no WBGT reading yesterday"],
                  "yesterday")) + [""]
    lab_order = ["Low", "Moderate", "High", "no usable label"]
    L += ["### Yesterday's label (the run's pinned labels, same station)", ""]
    L += md(split(named, "label_d1", lab_order, "yesterday's label")) + [""]
    agree = pd.crosstab(st.yesterday, st.label_d1)
    L += ["Station-days, all rows: yesterday as the model saw it against yesterday's pinned label (a check that the two "
          "agree):", ""] + md(agree.reset_index().rename(columns={"yesterday": "as the model saw it"})) + [""]
    fc_order = sorted([v for v in area.forecast.unique() if v.endswith("°C")], key=lambda v: float(v.split()[0]))
    fc_order += [v for v in area.forecast.unique() if not v.endswith("°C")]
    L += ["### What the model saw: the NEA forecast's max temperature (`nea_score`)", ""]
    L += md(split(named, "forecast", fc_order, "forecast max temperature")) + [""]
    L += ["### What the model saw: yesterday's peak WBGT (`wbgt_peak_d1`)", "",
          f"Bands are the quartiles of yesterday's peak over the {len(hp):,} High station-days with a reading (all "
          f"stations): {q[0]:.1f}, {q[1]:.1f} and {q[2]:.1f} °C, taken from the data. They are not heat-category "
          "cut-offs.", ""]
    L += md(split(named, "peak_band", [*band_names, "no WBGT reading yesterday"], "yesterday's peak")) + [""]
    L += ["### Medians: missed against caught High days", "",
          "Yesterday's peak over the rows with a reading; the forecast over the rows with a qualifying forecast.", ""]
    L += md(medians(named)) + [""]
    L += ["### A station's first 30 days", "",
          "Days since the station's first pinned label (the labels start on 16 Jan 2025, so a station reporting before "
          "then is past its first 30 days in every test month). Not one of the planned splits: added to explain S142's "
          "first month (M1.3).", ""]
    L += md(split(named, "station_age", [YOUNG, "later"], "station age")) + [""]

    # M1.3
    L += ["## M1.3 Where the misses sit", "", "### Stations, Jul 2025 to Aug 2026", "",
          "Sorted by area-day misses. Stations with no High day in either set are left out.", ""]
    L += md(station_rank(area, st, names)) + [""]
    L += ["### Planning areas with the most misses, Jul 2025 to Aug 2026 (top 10)", "",
          "\"Stations behind its misses\": the stations that served the area on its missed days, with the count.", ""]
    L += md(area_rank(area)) + [""]
    L += ["### The areas S142 served, Jul 2025 to Aug 2026", "",
          "\"Of its area-days\": the share of the area's test days on which S142 was its station.", ""]
    L += md(served_by(area, "S142")) + [""]
    s142 = st[st.station_id == "S142"]
    top_p = lambda k, d: {"highest P(High) on its High days": f"{d.loc[d.high, 'p_high'].max():.3f}" if d.high.any()
                          else "—", "High days after a High day": int((d.high & (d.yesterday == "High yesterday")).sum())}
    L += ["### S142 by month (station-days)", "",
          f"S142's first pinned label is {labels.loc[labels.station_id == 'S142', 'sgt_date'].min():%Y-%m-%d}.", ""]
    L += md(errors(s142, "month", sorted(s142.month.unique()), top_p)) + [""]
    L += ["### Stations, Apr to Jun 2026", ""] + md(station_rank(peak["area"], peak["all"], names)) + [""]
    L += ["### Planning areas with the most misses, Apr to Jun 2026 (top 10)", ""] + md(area_rank(peak["area"])) + [""]
    L += ["### The areas S142 served, Apr to Jun 2026", ""] + md(served_by(peak["area"], "S142")) + [""]

    L += ["## M1.4 Findings", "",
          "For a limitations slide. Each finding gives its counts (*measured*: from the tables above, or from the same "
          "predictions where a finding shows its own table); an explanation, where given, is labelled *reading*: an "
          "interpretation of the counts, not a measurement.", ""]
    L += findings(named, peak, q, labels.groupby("station_id").sgt_date.min())

    # M2
    edges = {key: deciles(named[key].p_high.to_numpy()) for key in ("area", "all")}
    L += ["## M2 Reliability of P(High)", "",
          "Ten equal-count bins (deciles) of P(High), edges from the pooled rows of each set; the per-season tables use "
          "the same pooled edges so the seasons are comparable. Each bin: the rows, the mean P(High) and the observed "
          "High rate as X of Y. A value on an edge goes to the bin above it; the last bin includes its top edge. "
          "No recalibration.", "", "### Summary", ""]
    L += calibration_summary(named, edges, seasons)
    curves = []
    for key, colr in (("area", ORANGE), ("all", BLUE)):
        f, e = named[key], edges[key]
        b = np.searchsorted(e[1:-1], f.p_high.to_numpy(), side="right")
        curves.append((f.assign(b=b).groupby("b").agg(**{"mean P(High)": ("p_high", "mean"), "rate": ("high", "mean")})
                       .reset_index(drop=True), colr, SETS[key].split(" (")[0].split(",")[0]))
    rel = fig_reliability(out.parent / FIGS, curves)
    L += [f"![Reliability of P(High), pooled deciles]({rel})", "",
          "Orange: area-days; blue: station-days, all stations. Dashed: predicted equals observed. Dotted: the cut-off.",
          ""]
    for key in ("area", "all"):
        L += [f"### {SETS[key]}, pooled", ""] + md(reliability(named[key], edges[key])) + [""]
    L += ["### The top decile in five equal-count bins (pooled)", "",
          "Each set's top decile (bin 10 above) split at the 20th, 40th, 60th and 80th percentiles of its own P(High), "
          "so calibration above the cut-off shows. " + " ".join(
              f"{SETS[k].capitalize()}: the top decile starts at {edges[k][9]:.4f}, "
              f"{'above' if edges[k][9] > CUT else 'below'} the cut-off, and holds "
              f"{of((named[k].alert & (named[k].p_high >= edges[k][9])).sum(), named[k].alert.sum())} of the alerts."
              for k in ("area", "all")), ""]
    L += md(top_decile_split(named, edges)) + [""]
    for key in ("area", "all"):
        L += [f"### {SETS[key]}, by season (pooled edges)", ""]
        L += md(reliability_by_season(named[key], edges[key], seasons)) + [""]

    out.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
