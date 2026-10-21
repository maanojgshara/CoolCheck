"""Targeted EDA before the model (CoolCheck Guide §16). Reads Silver through Databricks Connect, writes
docs/checks/eda.md and PNG charts in docs/checks/eda_figs/. Reports numbers and flags; it does not interpret them or
choose features.

Run from the repo root:
    .venv\\Scripts\\python scripts/analysis/eda.py

Hard rule: every read is filtered to sgt_date 2025-01-16 .. 2026-08-31 (SGT) at the scan, and the script never reads
1 Sep to 19 Oct 2026. It is enforced here, not by discipline:
  * every table comes through Reader.load, which applies the date filter before anything else;
  * Reader.sql refuses any query text that names a coolcheck table (queries run on registered, filtered views only);
  * every frame brought back to pandas is checked against the window, and the audit is written into the report.
The gold.area_nearest_station_daily view is NOT read: its definition takes max(sgt_date) of all labels, which would
touch the held-out days. The same SQL (src/coolcheck/nearest.py, the view's own builder) is re-run over the
window-filtered labels, with the view's parameters. For target dates inside the window the result is identical,
because a target date uses only labels from the 7 days before it.
"""
import argparse
import math
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

C = "coolcheck"
SGT = timezone(timedelta(hours=8))
WIN_START, WIN_END = date(2025, 1, 16), date(2026, 8, 31)
HELD_OUT = (date(2026, 9, 1), date(2026, 10, 19))
assert WIN_END < HELD_OUT[0], "the analysis window must end before the held-out period starts"
WIN_START_TS, WIN_END_TS = pd.Timestamp(WIN_START), pd.Timestamp(WIN_END)
BACKTEST_FIRST = pd.Timestamp("2025-07-01")  # rolling back-test months Jul 2025 to Aug 2026
BACKTEST_MONTHS = [str(p) for p in pd.period_range("2025-07", "2026-08", freq="M")]

BOUNDARY, CUTOFF_MIN, LOOKBACK_DAYS = "mp2025", 15, 7  # the view's parameters (§14.4, H10)
ORIGINAL_8 = ("S124", "S125", "S126", "S127", "S128", "S129", "S130", "S132")
LATE_STARTERS = ("S142", "S137", "S135")
RAIN_MIN_READINGS = 216  # of 288 five-minute slots (75%): a rainfall station-day counts as reporting
LOW_HIGH_DAYS = 30  # marker for "few High station-days in a month" (the §14 count rule's number)
AUC_FLAG, BAND_FLAG_RATE, BAND_MIN_N = 0.85, 0.50, 30  # leakage-alarm rules, stated in the report
PLAN_FULL_RANGE = {"na_readings": 2_894, "wbgt_short": 21, "rainfall_short": 17, "forecast_no_data": 1}

INK, INK2, SURF, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e6e5e1"
BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#8a8984"

AUDIT = []  # (frame, column, rows, first date, last date)


# ---------------------------------------------------------------- window guard
class Reader:
    """The only way the script reads the workspace. Holds the Spark session privately."""

    def __init__(self, spark):
        self._spark = spark
        self.tables_read = []

    def load(self, table, date_col):
        from pyspark.sql import functions as F
        self.tables_read.append(f"{table} (where {date_col} between {WIN_START} and {WIN_END})")
        df = self._spark.table(f"{C}.{table}")
        return df.where((F.col(date_col) >= F.lit(WIN_START)) & (F.col(date_col) <= F.lit(WIN_END)))

    def load_static(self, table, drop):
        """A table with no day dimension (planning-area distances). Columns that carry dates are dropped."""
        self.tables_read.append(f"{table} (no date column; dropped columns: {', '.join(drop)})")
        return self._spark.table(f"{C}.{table}").drop(*drop)

    def register(self, name, df):
        df.createOrReplaceTempView(name)

    def sql(self, query):
        if re.search(rf"\b{C}\.", query, re.I):
            raise RuntimeError("Reader.sql only runs on registered, window-filtered views, never on tables")
        return self._spark.sql(query)


def collect(df, name, date_cols=()):
    """Bring a Spark frame to pandas and assert every date column sits inside the window."""
    pdf = df.toPandas()
    for c in date_cols:
        pdf[c] = pd.to_datetime(pdf[c]).astype("datetime64[ns]")
        lo, hi = pdf[c].min(), pdf[c].max()
        assert pd.isna(lo) or (lo >= WIN_START_TS and hi <= WIN_END_TS), f"{name}.{c} outside the window: {lo} .. {hi}"
        AUDIT.append((name, c, len(pdf), None if pd.isna(lo) else lo.date(), None if pd.isna(hi) else hi.date()))
    return pdf


# ---------------------------------------------------------------- statistics and formatting helpers
def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - h) / d), min(1.0, (c + h) / d)


def pct(x):
    return "—" if x is None or pd.isna(x) else f"{100 * x:.1f}%"


def ci_str(k, n):
    lo, hi = wilson(k, n)
    return "—" if n == 0 else f"{pct(lo)} to {pct(hi)}"


def num_table(df, by, hcol="high"):
    """Rate table: n, High, rate and a Wilson 95% interval, per group."""
    g = df.groupby(by, dropna=False, observed=True)[hcol].agg(n="size", high="sum").reset_index()
    g["high"] = g["high"].astype(int)
    g["rate"] = g["high"] / g["n"]
    ci = [wilson(k, n) for k, n in zip(g["high"], g["n"])]
    g["lo"], g["hi"] = [c[0] for c in ci], [c[1] for c in ci]
    return g


def fmt_rates(g, keep_lo_hi=False):
    out = g.copy()
    out["95% CI"] = [ci_str(k, n) for k, n in zip(out["high"], out["n"])]
    out["rate"] = out["rate"].map(pct)
    return out.drop(columns=[] if keep_lo_hi else ["lo", "hi"])


PLAIN_INT_COLS = ("year", "hour", "issue hour (SGT)")


def md(df):
    def cell(v, col=""):
        if v is None or v is pd.NA or (isinstance(v, float) and np.isnan(v)):
            return "—"
        if col in PLAIN_INT_COLS:
            return str(int(v))
        if isinstance(v, (bool, np.bool_)):
            return str(bool(v))
        if isinstance(v, (int, np.integer)):
            return f"{v:,}"
        if isinstance(v, (float, np.floating)):
            return f"{v:,.2f}"
        if isinstance(v, (pd.Timestamp, datetime)):
            return f"{v:%Y-%m-%d}"
        return str(v)

    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(cell(v, c) for v, c in zip(row, cols)) + " |")
    return lines


def season_of(month):
    return {12: "NE monsoon", 1: "NE monsoon", 2: "NE monsoon", 3: "Inter-monsoon 1", 4: "Inter-monsoon 1",
            5: "Inter-monsoon 1", 6: "SW monsoon", 7: "SW monsoon", 8: "SW monsoon", 9: "SW monsoon",
            10: "Inter-monsoon 2", 11: "Inter-monsoon 2"}[month]


def season_period(d):
    """Season with its year; the NE monsoon spans the new year (Dec 2025 and Jan to Feb 2026 are one period)."""
    s = season_of(d.month)
    if s == "NE monsoon":
        y0 = d.year if d.month == 12 else d.year - 1
        return f"{s} {y0}/{str(y0 + 1)[2:]}"
    return f"{s} {d.year}"


def auc(x, y):
    """Mann-Whitney AUC of x against the boolean y (average ranks); NaN x dropped."""
    m = x.notna()
    x, y = x[m], y[m].astype(bool)
    n1 = int(y.sum())
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = x.rank()
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def persistence_pairs(df, idcol, datecol):
    """Pairs (today, tomorrow) for the same id on consecutive dates; df has idcol, datecol and a boolean high."""
    a = df[[idcol, datecol, "high"]]
    b = a.assign(**{datecol: a[datecol] - pd.Timedelta(days=1)}).rename(columns={"high": "high_tmrw"})
    p = a.merge(b, on=[idcol, datecol]).rename(columns={"high": "high_today"})
    p["tmrw"] = p[datecol] + pd.Timedelta(days=1)
    p["season"] = p["tmrw"].map(lambda d: season_of(d.month))
    p["season_period"] = p["tmrw"].map(season_period)
    return p


def persistence_table(p, by):
    rows = []
    groups = [("All", p)] if by is None else list(p.groupby(by))
    for key, g in groups:
        n, nh = len(g), int(g["high_today"].sum())
        both = int((g["high_today"] & g["high_tmrw"]).sum())
        tm = int(g["high_tmrw"].sum())
        nn, hn = n - nh, tm - both
        p_hh = both / nh if nh else float("nan")
        base = tm / n if n else float("nan")
        rows.append({"group": key, "pairs": n, "High today": nh, "High tomorrow too": both,
                     "P(High tomorrow given High today)": pct(p_hh), "95% CI": ci_str(both, nh),
                     "P(High tomorrow given not High today)": f"{pct(hn / nn if nn else float('nan'))} ({hn:,}/{nn:,})",
                     "base rate P(High tomorrow)": f"{pct(base)} ({tm:,}/{n:,})",
                     "lift": (p_hh / base) if nh and base else float("nan")})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- forecast validity and selection (check 6)
def sgt_dt(sec):
    return datetime.fromtimestamp(sec, SGT)


def fix_start(issue_s, start_s):
    """Stored validity start with its year set from the issue time: the year (issue year -1, 0, +1) that puts the
    start closest to the issue time, so a 23:xx issue on 31 Dec with a 1 Jan start gets the new year."""
    issue, start = sgt_dt(issue_s), sgt_dt(start_s)
    best = None
    for y in (issue.year - 1, issue.year, issue.year + 1):
        try:
            cand = start.replace(year=y)
        except ValueError:  # 29 Feb in a non-leap year
            continue
        if best is None or abs(cand - issue) < abs(best - issue):
            best = cand
    return best


def prepare_forecasts(fc):
    """fc has issue_s, upd_s, vs_s (epoch seconds). Adds fixed_start_s and validity end (start + 24 h)."""
    fc = fc.dropna(subset=["issue_s", "upd_s", "vs_s"]).copy()
    fixed = [fix_start(i, s) for i, s in zip(fc["issue_s"], fc["vs_s"])]
    fc["fixed_start_s"] = [int(f.timestamp()) for f in fixed]
    fc["year_differs_from_stored"] = fc["fixed_start_s"] != fc["vs_s"]
    fc["year_differs_from_issue_year"] = [f.year != sgt_dt(i).year for f, i in zip(fixed, fc["issue_s"])]
    fc["valid_end_s"] = fc["fixed_start_s"] + 24 * 3600
    return fc


def pick_forecast(fc, target, cutoff_min=CUTOFF_MIN):
    """Latest issue (by updatedTimestamp, then issue time) updated at or before target 00:cutoff SGT whose 24 h
    validity covers target 06:00 to 18:00. Returns a row or None."""
    t0 = datetime(target.year, target.month, target.day, tzinfo=SGT).timestamp()
    cutoff, need_from, need_to = t0 + cutoff_min * 60, t0 + 6 * 3600, t0 + 18 * 3600
    ok = fc[(fc["upd_s"] <= cutoff) & (fc["fixed_start_s"] <= need_from) & (fc["valid_end_s"] >= need_to)]
    if ok.empty:
        return None
    return ok.sort_values(["upd_s", "issue_s"]).iloc[-1]


def forecast_features(fc, targets):
    rows = []
    for t in targets:
        r = pick_forecast(fc, t)
        t0 = datetime(t.year, t.month, t.day, tzinfo=SGT).timestamp()
        if r is None:
            rows.append({"target_date": t, "fc_temp_high": np.nan, "fc_text": None, "fc_found": False})
            continue
        assert r["upd_s"] <= t0 + CUTOFF_MIN * 60, "leakage guard: forecast updated after the cut-off"
        rows.append({"target_date": t, "fc_temp_high": r["temp_high"], "fc_text": r["forecast_text"], "fc_found": True,
                     "fc_issue_hour": sgt_dt(r["issue_s"]).hour, "fc_lead_h": (t0 + 6 * 3600 - r["upd_s"]) / 3600,
                     "fc_upd_s": r["upd_s"], "fc_cutoff_s": t0 + CUTOFF_MIN * 60})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- rainfall nearest station (check 6)
def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(a))


def rainfall_prev_day(areas, rain_st, rain_sd, targets, min_readings=RAIN_MIN_READINGS):
    """Rainfall total of the day before each target date at the planning area's nearest rainfall station that has
    at least min_readings readings that day (nearest by the area's reference point)."""
    st = rain_st.sort_values("station_id").reset_index(drop=True)
    d = haversine_km(areas["ref_lat"].values[:, None], areas["ref_lon"].values[:, None],
                     st["lat"].values[None, :], st["lon"].values[None, :])
    tot = rain_sd.pivot(index="sgt_date", columns="station_id", values="total_mm").reindex(columns=st["station_id"])
    cnt = rain_sd.pivot(index="sgt_date", columns="station_id", values="n").reindex(columns=st["station_id"])
    out = []
    for t in targets:
        prev = t - pd.Timedelta(days=1)
        if prev not in tot.index:
            continue
        row = tot.loc[prev].values
        ok = (cnt.loc[prev].fillna(0).values >= min_readings)
        dm = np.where(ok[None, :], d, np.inf)
        idx, idx_any = dm.argmin(axis=1), d.argmin(axis=1)
        has = np.isfinite(dm.min(axis=1))
        for i, a in enumerate(areas["planning_area"]):
            out.append({"target_date": t, "planning_area": a,
                        "rain_prev": float(row[idx[i]]) if has[i] else np.nan,
                        "rain_dist_km": float(dm[i, idx[i]]) if has[i] else np.nan,
                        "rain_is_nearest_any": bool(has[i] and idx[i] == idx_any[i])})
    return pd.DataFrame(out)


# ---------------------------------------------------------------- bands (check 6)
def banded(series, edges, labels):
    b = pd.cut(series, bins=edges, labels=labels, right=False)
    b = b.cat.add_categories(["missing"]).fillna("missing")
    return b


def band_table(df, band_col):
    g = num_table(df, band_col)
    base = df["high"].mean()
    g["lift vs base"] = g["rate"] / base if base else np.nan
    return g


# ---------------------------------------------------------------- charts
def style():
    plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
                         "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                         "text.color": INK, "axes.titlecolor": INK, "axes.grid": True, "axes.grid.axis": "y", "axes.axisbelow": True, "grid.color": GRID,
                         "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
                         "font.size": 9, "axes.titlesize": 10.5, "axes.titleweight": "bold",
                         "axes.titlelocation": "left"})


def save(fig, figs_dir, name):
    fig.tight_layout()
    fig.savefig(figs_dir / name, dpi=130)
    plt.close(fig)
    return f"eda_figs/{name}"


def fig_base_rate(figs_dir, ms, ma):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6.2), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    ma = ma.set_index("ym").reindex(ms["ym"]).reset_index()
    x = np.arange(len(ms))
    a1.bar(x - 0.2, ms["rate"] * 100, 0.4, color=BLUE, label="station-days")
    a1.bar(x + 0.2, ma["rate"] * 100, 0.4, color=ORANGE, label="area-days")
    a1.set_ylabel("High rate (%)")
    a1.set_title("High rate by month (n per month is in the report table)")
    a1.legend(frameon=False, loc="upper left")
    a2.bar(x - 0.2, ms["high"], 0.4, color=BLUE, label="High station-days")
    a2.bar(x + 0.2, ms["high_dates"], 0.4, color=GREY, label="distinct High dates (any station)")
    a2.set_ylabel("count")
    a2.legend(frameon=False, loc="upper left")
    first_bt = list(ms["ym"]).index("2025-07")
    for a in (a1, a2):
        a.axvspan(first_bt - 0.5, len(ms) - 0.5, color=GRID, alpha=0.35, zorder=0)
    a2.text(first_bt - 0.4, a2.get_ylim()[1] * 0.9, "rolling back-test months", color=INK2, fontsize=8)
    a2.set_xticks(x)
    a2.set_xticklabels(ms["ym"], rotation=60, ha="right")
    return save(fig, figs_dir, "fig1_base_rate_by_month.png")


def fig_calendar_month(figs_dir, tab):
    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    x = np.arange(1, 13)
    for yr, colr, off in ((2025, BLUE, -0.2), (2026, ORANGE, 0.2)):
        t = tab[tab["year"] == yr].set_index("month").reindex(x)
        ax.bar(x + off, t["rate"].fillna(0) * 100, 0.4, color=colr, label=str(yr))
        for xi, r, n in zip(x, t["rate"], t["n"]):
            if not pd.isna(n):
                ax.text(xi + off, (0 if pd.isna(r) else r * 100) + 0.15, f"{int(n):,}", ha="center", fontsize=6.5, color=INK2)
    ax.set_xticks(x)
    ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    ax.set_ylabel("High station-day rate (%)")
    ax.set_title("High rate by calendar month (labels: station-days)")
    ax.legend(frameon=False)
    return save(fig, figs_dir, "fig2_high_by_calendar_month.png")


def fig_persistence(figs_dir, ps, pa):
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    for ax, p, title in ((axes[0], ps, "station-days"), (axes[1], pa, "area-days")):
        t = p.copy()
        t["sort"] = t["group"].map(lambda s: 0 if s == "All" else 1)
        t = t.sort_values(["sort", "group"]).reset_index(drop=True)
        x = np.arange(len(t))
        cond = t["P(High tomorrow given High today)"].str.rstrip("%").astype(float)
        base = t["base rate P(High tomorrow)"].str.extract(r"([\d.]+)%")[0].astype(float)
        ax.bar(x - 0.2, cond, 0.4, color=BLUE, label="P(High tomorrow given High today)")
        for xi, c_, k, n in zip(x, cond, t["High tomorrow too"], t["High today"]):
            ax.text(xi - 0.2, c_ + 0.6, f"{k}/{n}", ha="center", fontsize=7, color=INK2)
        ax.bar(x + 0.2, base, 0.4, color=GREY, label="base rate")
        ax.set_xticks(x)
        ax.set_xticklabels(t["group"], rotation=35, ha="right", fontsize=7.5)
        ax.set_title(title)
    axes[0].set_ylabel("%")
    axes[0].legend(frameon=False, fontsize=8)
    return save(fig, figs_dir, "fig3_persistence_by_season.png")


def fig_robustness(figs_dir, hist, hours):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.6))
    a1.bar(hist["bin"].astype(str), hist["share"] * 100, color=BLUE)
    for i, (s, n) in enumerate(zip(hist["share"], hist["n"])):
        a1.text(i, s * 100 + 0.8, f"{n:,}", ha="center", fontsize=8, color=INK2)
    a1.set_xlabel("High readings in the station-day")
    a1.set_ylabel("share of High station-days (%)")
    a1.set_title("High readings behind each High label (labels: station-days)")
    a2.bar(hours["hour"], hours["n"], color=BLUE)
    a2.set_xlabel("hour of day (SGT) of the first High reading")
    a2.set_ylabel("High station-days")
    a2.set_title("When the first High reading arrives")
    return save(fig, figs_dir, "fig4_label_robustness.png")


def fig_stations(figs_dir, st):
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.scatter(st["first_date"], st["o8_rate"] * 100, s=st["days"] / 4, facecolors="none", edgecolors=GREY,
               label="original 8, same dates")
    ax.scatter(st["first_date"], st["rate"] * 100, s=st["days"] / 4, color=BLUE, alpha=0.85, label="station")
    for _, r in st.iterrows():
        if r["station_id"] in LATE_STARTERS or r["rate"] >= 0.12:
            ax.annotate(r["station_id"], (r["first_date"], r["rate"] * 100), xytext=(4, 4), textcoords="offset points",
                        fontsize=8, color=INK)
    ax.set_xlabel("first reporting date (marker area = labelled days)")
    ax.set_ylabel("High station-day rate (%)")
    ax.set_title("High rate per station against its first reporting date")
    ax.legend(frameon=False, loc="upper right")
    return save(fig, figs_dir, "fig5_station_rate_vs_first_date.png")


def fig_features(figs_dir, tables):
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    for ax, (title, g, base) in zip(axes.ravel(), tables):
        x = np.arange(len(g))
        ax.bar(x, g["rate"] * 100, color=BLUE)
        ax.axhline(base * 100, color=GREY, ls="--", lw=1)
        for xi, r, n in zip(x, g["rate"], g["n"]):
            ax.text(xi, r * 100 + 0.3, f"{n:,}", ha="center", fontsize=7, color=INK2)
        ax.set_xticks(x)
        ax.set_xticklabels(g.iloc[:, 0].astype(str), rotation=40, ha="right", fontsize=7.5)
        ax.set_title(title, fontsize=9.5)
        ax.set_ylabel("High rate (%)")
    fig.suptitle("High area-day rate across feature bands (labels: area-days; dashed: base rate)", x=0.01, ha="left",
                 fontsize=10.5, fontweight="bold")
    return save(fig, figs_dir, "fig6_feature_bands.png")


def fig_missingness(figs_dir, stn, na_month):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    x = np.arange(len(stn))
    a1.fill_between(x, stn["min_per_day"], stn["max_per_day"], color=GRID, label="min to max per day")
    a1.plot(x, stn["median_per_day"], color=BLUE, lw=2, label="median per day")
    a1.plot(x, stn["stations"], color=ORANGE, lw=2, ls="--", label="distinct in month")
    a1.set_ylabel("stations with a labelled day")
    a1.set_title("Station count by month")
    a1.legend(frameon=False, loc="upper left")
    na = na_month.set_index("ym").reindex(stn["ym"])["na_readings"].fillna(0)
    a2.bar(x, na.values, color=BLUE)
    a2.set_ylabel("NA readings")
    a2.set_title("NA WBGT readings by month")
    a2.set_xticks(x)
    a2.set_xticklabels(stn["ym"], rotation=60, ha="right")
    return save(fig, figs_dir, "fig7_missingness_and_station_count.png")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="coolcheck")
    ap.add_argument("--out", default=str(REPO / "docs" / "checks" / "eda.md"))
    ap.add_argument("--figs", default=str(REPO / "docs" / "checks" / "eda_figs"))
    a = ap.parse_args()
    out_path, figs_dir = Path(a.out), Path(a.figs)
    figs_dir.mkdir(parents=True, exist_ok=True)
    style()

    from databricks.connect import DatabricksSession
    from pyspark.sql import functions as F
    from coolcheck.nearest import nearest_station_sql

    spark = DatabricksSession.builder.serverless().profile(a.profile).getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "Asia/Singapore")
    R = Reader(spark)
    FLAGS = []

    # ---- load (every read below goes through R.load)
    labels_df = R.load("silver.station_daily_label", "sgt_date")
    R.register("eda_labels", labels_df)
    R.register("eda_distance", R.load_static("silver.area_station_distance", ["station_first_day", "station_last_day"])
               .where(F.col("boundary") == BOUNDARY))
    labels = collect(labels_df.select("station_id", "sgt_date", "n_valid", "n_na", "n_high", "max_wbgt", "label",
                                      "label_if_out_of_range_excluded", "label_if_late_excluded", "usable",
                                      "low_coverage"), "station_daily_label", ["sgt_date"])
    lab = labels[labels["label"].notna()].copy()
    lab["high"] = lab["label"] == "High"
    lab["ym"] = lab["sgt_date"].dt.to_period("M").astype(str)
    lab["month"], lab["year"] = lab["sgt_date"].dt.month, lab["sgt_date"].dt.year
    lab["o8"] = lab["station_id"].isin(ORIGINAL_8)

    nearest_q = (f"SELECT target_date, planning_area, station_id, distance_km, n_reporting FROM ("
                 f"{nearest_station_sql('eda_labels', 'eda_distance', BOUNDARY, CUTOFF_MIN, LOOKBACK_DAYS)}) "
                 f"WHERE target_date <= DATE'{WIN_END}'")
    area = collect(R.sql(nearest_q), "area_nearest_station (rebuilt on window labels)", ["target_date"])
    ad = area.merge(lab[["station_id", "sgt_date", "label", "high", "usable", "ym", "month", "year", "o8"]],
                    left_on=["station_id", "target_date"], right_on=["station_id", "sgt_date"], how="left")
    ad = ad.drop(columns="sgt_date")
    ad_lab = ad[ad["label"].notna()].copy()
    ad_lab["high"] = ad_lab["high"].astype(bool)
    ad_lab[["year", "month"]] = ad_lab[["year", "month"]].astype(int)
    n_area_days_total = len(ad)

    # ---- readings aggregates (Spark, window-filtered)
    wb = R.load("silver.wbgt_readings", "sgt_date")
    wb_cat = collect(wb.groupBy("heat_stress").agg(F.count(F.lit(1)).alias("readings"), F.min("wbgt").alias("min_wbgt"),
                                                  F.max("wbgt").alias("max_wbgt")), "wbgt_by_category")
    wb_na = collect(wb.where(F.col("heat_stress") == "NA").groupBy("station_id", "sgt_date",
                    (F.floor(F.col("sgt_minute") / 60)).alias("hour")).agg(F.count(F.lit(1)).alias("n")),
                    "wbgt_na_readings", ["sgt_date"])
    first_high = collect(wb.where(F.col("heat_stress") == "High").groupBy("station_id", "sgt_date").agg(
        F.min("sgt_minute").alias("first_min"), F.count(F.lit(1)).alias("n_high_readings")),
        "wbgt_first_high_reading", ["sgt_date"])
    wb_total = int(wb_cat["readings"].sum())

    rd = R.load("silver.rainfall_readings", "sgt_date")
    rain_sd = collect(rd.groupBy("station_id", "sgt_date").agg(F.sum("rainfall_mm").alias("total_mm"),
                                                               F.count("rainfall_mm").alias("n")),
                      "rainfall_station_day", ["sgt_date"])
    rain_st = collect(rd.groupBy("station_id").agg(F.max("station_lat").alias("lat"), F.max("station_lon").alias("lon")),
                      "rainfall_stations")
    areas_ref = collect(R.sql("SELECT DISTINCT planning_area, ref_lat, ref_lon FROM eda_distance"), "area_ref_points")

    fc_raw = collect(R.load("silver.forecast_issues", "issue_sgt_date").select(
        F.unix_seconds("issue_ts").alias("issue_s"), F.unix_seconds("updated_ts").alias("upd_s"),
        F.unix_seconds("valid_start").alias("vs_s"), "temp_high", "forecast_text", "issue_sgt_date"),
        "forecast_issues", ["issue_sgt_date"])
    dq = collect(R.load("silver.dq_day", "sgt_date"), "dq_day", ["sgt_date"])

    # ================================================================= report
    L = []
    L += ["# Targeted EDA before the model", "",
          f"**Analysis window: {WIN_START} to {WIN_END} (SGT dates), inclusive.** The script reads nothing from "
          f"{HELD_OUT[0]} to {HELD_OUT[1]}: every table is filtered to the window at the scan, queries run only on "
          f"filtered views, and the window audit at the end shows the first and last date of every frame read "
          f"(asserted inside the window).", "",
          f"Generated {datetime.now(SGT):%Y-%m-%d %H:%M} SGT by `scripts/analysis/eda.py` at git "
          f"`{subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True, cwd=REPO).stdout.strip()}`"
          f" (script not committed). Numbers are counts from Silver as read in this run. This report states numbers "
          f"and flags; it does not interpret them or choose features.", ""]
    body = []  # sections 1-7, flags are collected as we go and placed first

    # ---- definitions
    body += ["## Definitions used", "",
             "- **Station-day:** a row of `silver.station_daily_label` with a label (the highest API `heatStress` of the "
             "day: Low, Moderate or High). **High** means that label is High. A High label always stands.",
             f"- **Area-day:** planning area x target date, labelled with the label of the area's nearest reporting "
             f"station on that date (the H10 rule: boundary {BOUNDARY}, reference point = polygon centroid, a station "
             f"reports if it has a counted reading in the {LOOKBACK_DAYS} days before the 00:{CUTOFF_MIN:02d} cut-off). "
             f"The nearest station can change from day to day. Area-days are not independent: {ad['planning_area'].nunique()} areas share {ad['station_id'].nunique()} "
             f"stations, so one station-day appears in many area-days and the area-day intervals are too narrow.",
             f"- `gold.area_nearest_station_daily` was **not read**; its SQL was re-run on the window-filtered labels "
             f"(see the script header). Area-days with a target date in the window: {n_area_days_total:,}; with a label: "
             f"{len(ad_lab):,}.",
             "- 95% intervals are Wilson intervals. Month and season names follow calendar months (NE monsoon Dec to Feb, "
             "Inter-monsoon Mar to May, SW monsoon Jun to Sep, Inter-monsoon Oct to Nov), an approximation of NEA's.",
             f"- **Original 8:** {', '.join(ORIGINAL_8)}. Late starters examined in check 5: {', '.join(LATE_STARTERS)}.",
             ""]

    # ---- check 1
    st_all = num_table(lab, "ym")
    ar_all = num_table(ad_lab, "ym")
    hd_s = lab[lab["high"]].groupby("ym")["sgt_date"].nunique()
    hd_a = ad_lab[ad_lab["high"]].groupby("ym")["target_date"].nunique()
    o8 = lab[lab["o8"]]
    o8_m = num_table(o8, "ym").set_index("ym")
    o8_hd = o8[o8["high"]].groupby("ym")["sgt_date"].nunique()
    days_lab = lab.groupby("ym")["sgt_date"].nunique()
    ms = st_all.set_index("ym").join(days_lab.rename("days_labelled")).join(hd_s.rename("high_dates")).fillna({"high_dates": 0})
    ms["high_dates"] = ms["high_dates"].astype(int)
    ms = ms.reset_index()
    ma = ar_all.set_index("ym").join(hd_a.rename("high_dates")).fillna({"high_dates": 0}).reset_index()
    ma["high_dates"] = ma["high_dates"].astype(int)

    t1 = fmt_rates(ms.assign(**{"backtest month": ms["ym"].isin(BACKTEST_MONTHS).map({True: "yes", False: ""})}))
    t1["High station-days (original 8)"] = [f"{int(o8_m['high'].get(m, 0))}/{int(o8_m['n'].get(m, 0))}" for m in t1["ym"]]
    t1["High dates (original 8)"] = [int(o8_hd.get(m, 0)) for m in t1["ym"]]
    t1 = t1.rename(columns={"ym": "month", "n": "station-days", "high": "High station-days", "high_dates": "High dates (any station)"})
    ta = fmt_rates(ma.assign(**{"backtest month": ma["ym"].isin(BACKTEST_MONTHS).map({True: "yes", False: ""})}))
    ta = ta.rename(columns={"ym": "month", "n": "area-days", "high": "High area-days", "high_dates": "High dates (any area)"})

    by_year_s = fmt_rates(num_table(lab, "year")).rename(columns={"n": "station-days", "high": "High station-days"})
    by_year_a = fmt_rates(num_table(ad_lab, "year")).rename(columns={"n": "area-days", "high": "High area-days"})
    tot_s, tot_a = len(lab), len(ad_lab)
    usable_n = int(lab["usable"].sum())
    usable_high = int((lab["usable"] & lab["high"]).sum())
    bt = ms[ms["ym"].isin(BACKTEST_MONTHS)]
    bt_dates_union = lab[lab["high"] & (lab["sgt_date"] >= BACKTEST_FIRST)]["sgt_date"].nunique()

    body += ["## 1. High base rate (per station-day and per area-day), by month and year", "",
             f"Overall: **{int(lab['high'].sum()):,} High of {tot_s:,}** labelled station-days "
             f"({pct(lab['high'].mean())}; {ci_str(int(lab['high'].sum()), tot_s)}), on {lab['sgt_date'].nunique():,} "
             f"dates, {lab[lab['high']]['sgt_date'].nunique():,} of which have a High at any station. "
             f"**{int(ad_lab['high'].sum()):,} High of {tot_a:,}** labelled area-days ({pct(ad_lab['high'].mean())}), "
             f"{ad_lab[ad_lab['high']]['target_date'].nunique():,} High dates. "
             f"Counting only `usable` station-days (a Low or Moderate label on a low-coverage day is not usable): "
             f"{usable_high:,} High of {usable_n:,} ({pct(usable_high / usable_n)}); {tot_s - usable_n:,} labelled "
             f"station-days are not usable.", "",
             "### By year", "", "Station-days:", ""] + md(by_year_s) + ["", "Area-days:", ""] + md(by_year_a)

    body += ["", "### By month: station-days", "",
             "`High dates` = distinct SGT dates with at least one High station-day. The original-8 columns are counts "
             "(High/labelled station-days). 2025-01 starts on 16 Jan.", ""] + md(
        t1[["month", "backtest month", "days_labelled", "station-days", "High station-days", "rate", "95% CI",
            "High dates (any station)", "High station-days (original 8)", "High dates (original 8)"]].rename(
            columns={"days_labelled": "dates labelled"}))
    body += ["", "### By month: area-days", ""] + md(
        ta[["month", "backtest month", "area-days", "High area-days", "rate", "95% CI", "High dates (any area)"]])

    body += ["", "### High days in the rolling back-test months (Jul 2025 to Aug 2026)", "",
             f"{len(bt)} months. High station-days per month: min {int(bt['high'].min())}, median "
             f"{bt['high'].median():.0f}, max {int(bt['high'].max())} (total {int(bt['high'].sum()):,}). Distinct High dates "
             f"per month: min {int(bt['high_dates'].min())}, median {bt['high_dates'].median():.0f}, max "
             f"{int(bt['high_dates'].max())}; {bt_dates_union:,} distinct High dates across the {len(bt)} months. "
             f"Months with fewer than {LOW_HIGH_DAYS} High station-days: "
             f"{', '.join(bt[bt['high'] < LOW_HIGH_DAYS]['ym']) or 'none'}. Months with 0 High dates: "
             f"{', '.join(bt[bt['high_dates'] == 0]['ym']) or 'none'}. Months with at most 5 High dates: "
             f"{', '.join(f'{m} ({d})' for m, d in zip(bt[bt['high_dates'] <= 5]['ym'], bt[bt['high_dates'] <= 5]['high_dates'])) or 'none'}.", "",
             f"![]({fig_base_rate(figs_dir, ms, ma)})", ""]
    missing_bt = [m for m in BACKTEST_MONTHS if m not in set(ms["ym"])]
    if missing_bt:
        FLAGS.append(f"Back-test months with no labelled station-days: {', '.join(missing_bt)}.")
    low_bt = bt[bt["high"] < LOW_HIGH_DAYS]
    if len(low_bt):
        FLAGS.append(f"{len(low_bt)} of {len(bt)} back-test months have fewer than {LOW_HIGH_DAYS} High station-days "
                     f"({', '.join(f'{m} {n}' for m, n in zip(low_bt['ym'], low_bt['high']))}); "
                     f"{int((bt['high_dates'] == 0).sum())} month(s) with no High date at any station.")

    # ---- check 2
    cal = []
    for kind, df, dcol in (("station-days", lab, "month"), ("area-days", ad_lab, "month")):
        for yr in (2025, 2026):
            g = num_table(df[df["year"] == yr], "month")
            g["year"] = yr
            g["kind"] = kind
            cal.append(g)
    cal = pd.concat(cal)
    cal_s = cal[cal["kind"] == "station-days"]
    pooled_s = num_table(lab, "month")
    pooled_a = num_table(ad_lab, "month")
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    rows = []
    for m in range(1, 13):
        r = {"month": names[m - 1]}
        for yr in (2025, 2026):
            q = cal_s[(cal_s["year"] == yr) & (cal_s["month"] == m)]
            r[f"{yr} station-days (High)"] = "—" if q.empty else f"{int(q['n'].iloc[0]):,} ({int(q['high'].iloc[0]):,}, {pct(q['rate'].iloc[0])})"
        p = pooled_s[pooled_s["month"] == m].iloc[0]
        r["pooled station-days (High, rate)"] = f"{int(p['n']):,} ({int(p['high']):,}, {pct(p['rate'])})"
        r["pooled 95% CI"] = ci_str(int(p["high"]), int(p["n"]))
        pa_ = pooled_a[pooled_a["month"] == m].iloc[0]
        r["pooled area-days (High, rate)"] = f"{int(pa_['n']):,} ({int(pa_['high']):,}, {pct(pa_['rate'])})"
        rows.append(r)
    body += ["## 2. High rate by calendar month", "",
             "Calendar months pooled over the window, with each year shown. Jan 2025 is from 16 Jan; Sep to Dec appear "
             "for 2025 only because the window ends 31 Aug 2026.", ""] + md(pd.DataFrame(rows)) + [
        "", f"![]({fig_calendar_month(figs_dir, cal_s)})", ""]

    # ---- check 3
    ps_pairs = persistence_pairs(lab, "station_id", "sgt_date")
    pa_pairs = persistence_pairs(ad_lab, "planning_area", "target_date")
    ps_all, pa_all = persistence_table(ps_pairs, None), persistence_table(pa_pairs, None)
    ps_season, pa_season = persistence_table(ps_pairs, "season"), persistence_table(pa_pairs, "season")
    ps_period, pa_period = persistence_table(ps_pairs, "season_period"), persistence_table(pa_pairs, "season_period")
    body += ["## 3. Persistence: P(High tomorrow given High today) against the base rate", "",
             "A pair is the same station (or planning area) on two consecutive dates, both labelled. Season is the "
             "season of the second day. For area-days the nearest station can differ between the two days. `lift` = "
             "P(High tomorrow given High today) / base rate. The base rate is over the same pairs.", "",
             "### Station-days", ""] + md(pd.concat([ps_all, ps_season])) + ["", "By season and year:", ""] + md(ps_period) + [
        "", "### Area-days", ""] + md(pd.concat([pa_all, pa_season])) + ["", "By season and year:", ""] + md(pa_period)
    ps_chart = pd.concat([ps_all, ps_season])
    pa_chart = pd.concat([pa_all, pa_season])
    body += ["", f"![]({fig_persistence(figs_dir, ps_chart, pa_chart)})", ""]

    # ---- check 4
    hl = lab[lab["high"]].merge(first_high, on=["station_id", "sgt_date"], how="left", suffixes=("", "_rd"))
    mismatch = int((hl["n_high"] != hl["n_high_readings"]).sum())
    if mismatch:
        FLAGS.append(f"{mismatch} High station-days have a label n_high that differs from the High readings counted in "
                     f"silver.wbgt_readings.")
    hl["bin"] = pd.cut(hl["n_high"], [0, 1, 2, 4, 8, np.inf], labels=["1", "2", "3-4", "5-8", "9+"])
    hist = hl.groupby("bin", observed=False).size().rename("n").reset_index()
    hist["share"] = hist["n"] / len(hl)
    n12 = int((hl["n_high"] <= 2).sum())
    hl["first_hour"] = (hl["first_min"] // 60).astype("Int64")
    hours = hl.groupby("first_hour").size().rename("n").reset_index().rename(columns={"first_hour": "hour"})
    hours["hour"] = hours["hour"].astype(int)
    hours = hours.set_index("hour").reindex(range(0, 24), fill_value=0).reset_index()

    def hhmm(m):
        return f"{int(m) // 60:02d}:{int(m) % 60:02d}"

    def tod_row(name, g):
        q = g["first_min"].quantile([0, 0.1, 0.5, 0.9, 1.0])
        return {"group": name, "High station-days": len(g), "earliest": hhmm(q[0]), "p10": hhmm(q[0.1]),
                "median": hhmm(q[0.5]), "p90": hhmm(q[0.9]), "latest": hhmm(q[1.0]),
                "before 10:00": f"{int((g['first_min'] < 600).sum()):,}", "18:00 or later": f"{int((g['first_min'] >= 1080).sum()):,}"}

    tod = pd.DataFrame([tod_row("all", hl), tod_row("1 or 2 High readings", hl[hl["n_high"] <= 2]),
                        tod_row("3 or more High readings", hl[hl["n_high"] >= 3])])
    by_year_rob = hl.groupby("year").apply(lambda g: pd.Series({"High station-days": len(g), "on 1 or 2 readings": int((g["n_high"] <= 2).sum()),
                                                                 "share": pct((g["n_high"] <= 2).mean())}), include_groups=False).reset_index()
    by_o8_rob = hl.groupby("o8").apply(lambda g: pd.Series({"High station-days": len(g), "on 1 or 2 readings": int((g["n_high"] <= 2).sum()),
                                                             "share": pct((g["n_high"] <= 2).mean())}), include_groups=False).reset_index()
    by_o8_rob["o8"] = by_o8_rob["o8"].map({True: "original 8", False: "other stations"})
    by_o8_rob = by_o8_rob.rename(columns={"o8": "stations"})
    n_oor = int((hl["label_if_out_of_range_excluded"] != "High").sum())
    n_late = int((hl["label_if_late_excluded"] != "High").sum())
    hist_t = hist.assign(share=hist["share"].map(pct)).rename(columns={"bin": "High readings in the day", "n": "High station-days"})
    cat_t = wb_cat.copy()
    cat_t = cat_t.rename(columns={"heat_stress": "heatStress (API field)", "min_wbgt": "lowest WBGT seen", "max_wbgt": "highest WBGT seen"})
    cat_t["order"] = cat_t["heatStress (API field)"].map({"Low": 0, "Moderate": 1, "High": 2, "NA": 3}).fillna(4)
    cat_t = cat_t.sort_values("order").drop(columns="order")
    body += ["## 4. Label robustness: how many readings back a High label, and when the first one arrives", "",
             f"Of {len(hl):,} High station-days, **{n12:,} ({pct(n12 / len(hl))}; {ci_str(n12, len(hl))}) rest on 1 or 2 "
             f"High readings** (one reading = one 15-minute slot).", ""] + md(hist_t) + [
             "", "By year:", ""] + md(by_year_rob) + ["", "Original 8 and others:", ""] + md(by_o8_rob) + [
             "", f"Sensitivity of the label (counts among the {len(hl):,} High station-days, from the table's own "
             f"alternative labels): {n_oor:,} would not be High if out-of-range readings were excluded; {n_late:,} would not be "
             f"High if readings that arrived over 1 h late were excluded. The High-always-stands rule is unchanged.", "",
             "### Time of day of the first High reading (SGT)", ""] + md(tod) + [
             "", "### The API's categories against the WBGT values seen (observed, not coded)", ""] + md(cat_t) + [
             "", f"![]({fig_robustness(figs_dir, hist, hours)})", ""]

    # ---- check 5
    first_last = lab.groupby("station_id")["sgt_date"].agg(first_date="min", last_date="max", days="nunique").reset_index()
    sd = num_table(lab, "station_id").rename(columns={"n": "days_n"})
    st = first_last.merge(sd[["station_id", "high", "rate"]], on="station_id")
    o8_dates = o8.groupby("sgt_date")["high"].agg(o8_n="size", o8_high="sum").reset_index()
    lab_o = lab.merge(o8_dates, on="sgt_date", how="left")
    o8_same = lab_o.groupby("station_id").agg(o8_n=("o8_n", "sum"), o8_high=("o8_high", "sum")).reset_index()
    st = st.merge(o8_same, on="station_id")
    st["o8_rate"] = st["o8_high"] / st["o8_n"].where(st["o8_n"] > 0)
    st = st.sort_values(["first_date", "station_id"]).reset_index(drop=True)
    st_t = st.assign(**{"first date": st["first_date"].dt.date.astype(str)
                        + st["first_date"].eq(WIN_START_TS).map({True: " (window start)", False: ""}),
                        "last date": st["last_date"].dt.date.astype(str),
                        "High rate": st["rate"].map(pct), "95% CI": [ci_str(int(k), int(n)) for k, n in zip(st["high"], st["days"])],
                        "original-8 rate, same dates": [f"{pct(r)} ({int(h):,}/{int(n):,})" for r, h, n in zip(st["o8_rate"], st["o8_high"], st["o8_n"])]})
    st_t = st_t.rename(columns={"station_id": "station", "days": "labelled days", "high": "High days"})[
        ["station", "first date", "last date", "labelled days", "High days", "High rate", "95% CI", "original-8 rate, same dates"]]
    short_hist = st[st["days"] < 30]
    if len(short_hist):
        FLAGS.append("Stations with fewer than 30 labelled days in the window: " + ", ".join(
            f"{r.station_id} ({r.days} days from {r.first_date:%Y-%m-%d})" for r in short_hist.itertuples()) + ".")
    outliers = st[(st["days"] >= 60) & (st["o8_rate"] > 0) & ((st["rate"] >= 2 * st["o8_rate"]) | (st["rate"] <= 0.5 * st["o8_rate"]))]
    if len(outliers):
        FLAGS.append("Stations (60+ labelled days) whose High rate is at least double or at most half the original-8 rate on the "
                     "same dates: " + ", ".join(f"{r.station_id} ({pct(r.rate)} vs {pct(r.o8_rate)})" for r in outliers.itertuples()) + ".")

    def scope_rows(scope, smask_lab, smask_ad):
        rows = []
        sets = [("all stations", lambda d, c: d), (f"without {', '.join(LATE_STARTERS)}", lambda d, c: d[~d[c].isin(LATE_STARTERS)]),
                (f"only {', '.join(LATE_STARTERS)}", lambda d, c: d[d[c].isin(LATE_STARTERS)]),
                ("original 8 only", lambda d, c: d[d[c].isin(ORIGINAL_8)])]
        for name, f in sets:
            s = f(lab[smask_lab], "station_id")
            a_ = f(ad_lab[smask_ad], "station_id")
            rows.append({"scope": scope, "set": name,
                         "station-days": len(s), "High station-days": int(s["high"].sum()),
                         "station-day rate": pct(s["high"].mean()), "High dates (stations)": s[s["high"]]["sgt_date"].nunique(),
                         "area-days": len(a_), "High area-days": int(a_["high"].sum()),
                         "area-day rate": pct(a_["high"].mean()), "High dates (areas)": a_[a_["high"]]["target_date"].nunique()})
        return rows

    swc = pd.DataFrame(scope_rows("whole window", lab["sgt_date"].notna(), ad_lab["target_date"].notna())
                       + scope_rows("back-test months", lab["sgt_date"] >= BACKTEST_FIRST, ad_lab["target_date"] >= BACKTEST_FIRST))
    swc_y = pd.DataFrame(scope_rows("2025", lab["year"] == 2025, ad_lab["year"] == 2025)
                         + scope_rows("2026", lab["year"] == 2026, ad_lab["year"] == 2026))
    body += ["## 5. High rate per station against its first reporting date", "",
             "First date = the station's first labelled day inside the window; stations that already reported on 16 Jan 2025 "
             "are marked `(window start)`, so their real start may be earlier. The last column is the High rate of the "
             "original 8 on the dates this station reported (a same-dates comparison, not an adjustment).", ""] + md(st_t) + [
             "", f"![]({fig_stations(figs_dir, st)})", "",
             f"### With and without {', '.join(LATE_STARTERS)}", "",
             "Area-day rows drop (or keep) the area-days whose nearest station is in the set; the nearest station is not "
             "recomputed without them. `High dates` = distinct dates with a High at any station (or any area) in the set.", ""] + md(swc) + [
             "", "By year:", ""] + md(swc_y) + [""]

    # ---- check 6
    targets = sorted(ad["target_date"].unique())
    targets = [pd.Timestamp(t) for t in targets]
    prev = labels[["station_id", "sgt_date", "max_wbgt"]].assign(target_date=lambda d: d["sgt_date"] + pd.Timedelta(days=1))
    prev = prev.rename(columns={"max_wbgt": "wbgt_prev"})[["station_id", "target_date", "wbgt_prev"]]
    f = ad_lab.merge(prev, on=["station_id", "target_date"], how="left")
    rainf = rainfall_prev_day(areas_ref, rain_st, rain_sd, targets)
    f = f.merge(rainf, on=["planning_area", "target_date"], how="left")
    fcp = prepare_forecasts(fc_raw)
    fcf = forecast_features(fcp, targets)
    f = f.merge(fcf[["target_date", "fc_temp_high", "fc_text", "fc_found"]], on="target_date", how="left")

    wedges, wlabels = [-np.inf, 27, 28, 29, 30, 31, 32, 33, 34, np.inf], ["<27", "27-28", "28-29", "29-30", "30-31", "31-32", "32-33", "33-34", ">=34"]
    f["b_wbgt"] = banded(f["wbgt_prev"], wedges, wlabels)
    f["b_rain"] = banded(f["rain_prev"], [0, 1e-9, 1, 5, 10, 25, np.inf], ["0 mm", ">0 to <1", "1 to <5", "5 to <10", "10 to <25", ">=25"])
    f["b_temp"] = banded(f["fc_temp_high"], [-np.inf, 31, 32, 33, 34, 35, np.inf], ["<=30", "31", "32", "33", "34", ">=35"])
    f["b_text"] = f["fc_text"].fillna("missing")
    own = lab.merge(prev, left_on=["station_id", "sgt_date"], right_on=["station_id", "target_date"], how="left")
    own["b_wbgt"] = banded(own["wbgt_prev"], wedges, wlabels)

    tables = [("Yesterday's peak WBGT at the nearest station (area-days)", band_table(f, "b_wbgt")),
              ("Yesterday's rainfall, nearest rainfall station (area-days)", band_table(f, "b_rain")),
              ("Forecast high temperature (area-days)", band_table(f, "b_temp")),
              ("Forecast text (area-days)", band_table(f, "b_text").sort_values("n", ascending=False))]
    own_t = band_table(own, "b_wbgt")

    # date-level view for the forecast (one forecast per date, shared by all areas)
    dates = f.groupby("target_date").agg(high=("high", "max")).reset_index()
    dates = dates.merge(fcf[["target_date", "fc_temp_high", "fc_text"]], on="target_date", how="left")
    dates["b_temp"] = banded(dates["fc_temp_high"], [-np.inf, 31, 32, 33, 34, 35, np.inf], ["<=30", "31", "32", "33", "34", ">=35"])
    dates["b_text"] = dates["fc_text"].fillna("missing")
    d_temp, d_text = band_table(dates, "b_temp"), band_table(dates, "b_text").sort_values("n", ascending=False)

    def feature_stats(name, x, df, gtab, numeric=True):
        base = df["high"].mean()
        if numeric:
            a_ = auc(x, df["high"])
            note = "AUC of the raw value"
        else:  # in-sample: each band replaced by its own High rate (optimistic)
            enc = df[gtab.columns[0]].map(dict(zip(gtab.iloc[:, 0], gtab["rate"]))).astype(float)
            a_ = auc(enc, df["high"])
            note = "in-sample AUC of the band High rates (optimistic)"
        ok = gtab[gtab["n"] >= BAND_MIN_N]
        top = ok.sort_values("rate").iloc[-1] if len(ok) else None
        flags = []
        if not pd.isna(a_) and (a_ >= AUC_FLAG or a_ <= 1 - AUC_FLAG):
            flags.append(f"AUC {a_:.3f}")
        if top is not None and top["rate"] >= BAND_FLAG_RATE:
            flags.append(f"band '{top.iloc[0]}' High rate {pct(top['rate'])} (n={int(top['n']):,})")
        return {"feature": name, "rows used": int(x.notna().sum()) if numeric else int(df['b_text'].ne('missing').sum()),
                "missing": int(x.isna().sum()) if numeric else int(df['b_text'].eq('missing').sum()),
                "AUC": a_, "AUC kind": note, "lowest band rate": pct(ok["rate"].min()) if len(ok) else "—",
                "highest band rate": pct(ok["rate"].max()) if len(ok) else "—",
                "flag": "; ".join(flags) if flags else "—"}, flags

    stats, flagged = [], []
    for name, x, df_, g, num in (("yesterday's peak WBGT, nearest station (area-days)", f["wbgt_prev"], f, tables[0][1], True),
                                 ("yesterday's peak WBGT, own station (station-days)", own["wbgt_prev"], own, own_t, True),
                                 ("yesterday's rainfall total (area-days)", f["rain_prev"], f, tables[1][1], True),
                                 ("forecast high temperature (area-days)", f["fc_temp_high"], f, tables[2][1], True),
                                 ("forecast text (area-days)", f["fc_text"], f, tables[3][1], False)):
        s, fl = feature_stats(name, x, df_, g, num)
        stats.append(s)
        if fl:
            FLAGS.append(f"Feature flagged as possibly too strong: {name}: {'; '.join(fl)}. Rules: AUC at or above {AUC_FLAG} or "
                         f"at or below {1 - AUC_FLAG:.2f}, or a band with at least {BAND_MIN_N} rows and High rate at or above "
                         f"{pct(BAND_FLAG_RATE)} (base rate {pct(df_['high'].mean())}). Trace before use.")

    def band_md(g, title):
        out = fmt_rates(g).rename(columns={g.columns[0]: "band", "n": "rows", "high": "High"})
        out["lift vs base"] = out["lift vs base"].map(lambda v: f"{v:.2f}")
        return [f"**{title}**", ""] + md(out) + [""]

    lead = fcf[fcf["fc_found"]]["fc_lead_h"]
    n_missing_fc = int((~fcf["fc_found"]).sum())
    slots = fcf[fcf["fc_found"]].groupby("fc_issue_hour").size().rename("targets").reset_index().rename(columns={"fc_issue_hour": "issue hour (SGT)"})
    rain_fb = f["rain_is_nearest_any"].dropna()
    pairs_fc = (fcp["year_differs_from_stored"].sum(), fcp["year_differs_from_issue_year"].sum(), len(fcp))
    body += ["## 6. Signal and leakage: candidate features against High", "",
             f"Target = High at the area's nearest station on the target date (area-days, {len(f):,} labelled; base rate "
             f"{pct(f['high'].mean())}). All features use only data before the 00:{CUTOFF_MIN:02d} cut-off on the target date.", "",
             "- **Yesterday's peak WBGT:** `max_wbgt` of the area's nearest station (as chosen for the target date) on the day "
             "before the target date, over that day's counted readings.",
             f"- **Yesterday's rainfall:** sum of the 5-minute rainfall over the SGT day before the target date at the rainfall "
             f"station nearest to the area's reference point among stations with at least {RAIN_MIN_READINGS} of 288 readings "
             f"that day. The nearest station overall was used in {pct(rain_fb.mean())} of {len(rain_fb):,} area-days "
             f"({int((~rain_fb).sum()):,} used a farther one with a fuller day).",
             f"- **Forecast:** the issue with the latest `updatedTimestamp` at or before the target date's 00:{CUTOFF_MIN:02d} SGT "
             f"whose validity covers the target date 06:00 to 18:00. Validity = the stored `validPeriod.start` with its year set "
             f"from the issue time (the year that puts it closest to the issue time), plus 24 h; the stored end is not used. "
             f"Of {pairs_fc[2]:,} issues in the window, {int(pairs_fc[0]):,} have a stored start whose year differs from the "
             f"corrected one, and {int(pairs_fc[1]):,} end up in a year other than the issue's own year. No matching issue for "
             f"{n_missing_fc} of {len(fcf)} target dates"
             + (f" ({', '.join(str(d.date()) for d in fcf[~fcf['fc_found']]['target_date'])})" if 0 < n_missing_fc <= 12 else "")
             + f". For the dates with one: lead time from `updatedTimestamp` to 06:00 on the target date min {lead.min():.1f} h, "
             f"median {lead.median():.1f} h, max {lead.max():.1f} h; every selected `updatedTimestamp` is at or before its cut-off "
             f"(asserted).", "",
             "### Summary", ""] + md(pd.DataFrame(stats)) + [""]
    for title, g in tables:
        body += band_md(g, title)
    body += band_md(own_t, "Yesterday's peak WBGT, own station (station-days)")
    body += ["Forecast features by date (one forecast per date, shared by all areas; High = a High at any area that date):", ""]
    body += band_md(d_temp, "Forecast high temperature (dates)") + band_md(d_text, "Forecast text (dates)")
    body += ["Issue hour (SGT) of the selected forecasts:", ""] + md(slots) + ["", f"![]({fig_features(figs_dir, [(t, g.sort_values('n', ascending=False) if 'text' in t else g, f['high'].mean()) for t, g in tables])})", ""]

    # ---- check 7
    short = dq[dq["status"] != "ok"].sort_values(["feed", "sgt_date"])
    short_counts = short.groupby(["feed", "status"]).size().rename("days").reset_index()
    short_t = short[["feed", "sgt_date", "status", "n_timestamps", "expected_timestamps", "n_stations", "n_rows", "note"]].rename(
        columns={"sgt_date": "date", "n_timestamps": "timestamps", "expected_timestamps": "expected timestamps",
                 "n_stations": "stations", "n_rows": "rows"})
    na_total = int(wb_na["n"].sum())
    na_label_total = int(labels["n_na"].sum())
    na_month = wb_na.assign(ym=wb_na["sgt_date"].dt.to_period("M").astype(str)).groupby("ym")["n"].sum().rename("na_readings").reset_index()
    na_stn = wb_na.groupby("station_id")["n"].sum().sort_values(ascending=False).rename("NA readings").reset_index().head(10)
    na_hour = wb_na.groupby("hour")["n"].sum().reindex(range(24), fill_value=0).rename("NA readings").reset_index()
    na_days = wb_na.groupby(["station_id", "sgt_date"]).ngroups
    na_in_peak = int(wb_na[(wb_na["hour"] >= 10) & (wb_na["hour"] < 18)]["n"].sum())
    n_unlab = int(labels["label"].isna().sum())
    per_day = labels[labels["n_valid"] > 0].groupby("sgt_date")["station_id"].nunique().rename("n").reset_index()
    per_day["ym"] = per_day["sgt_date"].dt.to_period("M").astype(str)
    stn_m = per_day.groupby("ym")["n"].agg(min_per_day="min", median_per_day="median", max_per_day="max").reset_index()
    stn_m["stations"] = stn_m["ym"].map(labels[labels["n_valid"] > 0].assign(ym=lambda d: d["sgt_date"].dt.to_period("M").astype(str)).groupby("ym")["station_id"].nunique())
    new_m = st.assign(ym=st["first_date"].dt.to_period("M").astype(str)).groupby("ym")["station_id"].apply(lambda s: ", ".join(sorted(s)))
    last_m = st[st["last_date"] < WIN_END_TS].assign(ym=lambda d: d["last_date"].dt.to_period("M").astype(str)).groupby("ym")["station_id"].apply(lambda s: ", ".join(sorted(s)))
    stn_m["first labelled in month"] = stn_m["ym"].map(new_m).fillna("")
    stn_m["last labelled in month"] = stn_m["ym"].map(last_m).fillna("")
    for c_ in ("expected timestamps", "stations"):
        short_t[c_] = short_t[c_].astype("Int64")
    wb_short = int(short[(short["feed"] == "wbgt")].shape[0])
    rain_short = int(short[(short["feed"] == "rainfall")].shape[0])
    fc_short = int(short[(short["feed"] == "forecast")].shape[0])
    if na_total != PLAN_FULL_RANGE["na_readings"]:
        FLAGS.append(f"NA WBGT readings in the window: {na_total:,}, against the plan's {PLAN_FULL_RANGE['na_readings']:,}. "
                     f"The EDA window is 16 Jan 2025 to 31 Aug 2026 only; the plan's figures run to 19 Oct 2026. "
                     f"This window difference, not an error, explains the gap.")
    if wb_short != PLAN_FULL_RANGE["wbgt_short"]:
        FLAGS.append(f"WBGT short days in the window: {wb_short}, against the plan's {PLAN_FULL_RANGE['wbgt_short']}. "
                     f"The EDA window is 16 Jan 2025 to 31 Aug 2026 only; the plan's figures run to 19 Oct 2026. "
                     f"This window difference, not an error, explains the gap.")
    body += ["## 7. Missingness and shift", "",
             "### Short days (silver.dq_day, status other than ok, inside the window)", "",
             f"WBGT short days: {wb_short}; rainfall short days: {rain_short}; forecast no-data days: {fc_short}. The plan quotes "
             f"{PLAN_FULL_RANGE['wbgt_short']}, {PLAN_FULL_RANGE['rainfall_short']} and {PLAN_FULL_RANGE['forecast_no_data']}. "
             f"The EDA window is 16 Jan 2025 to 31 Aug 2026 only and the plan's figures run to 19 Oct 2026; "
             f"this window difference, not an error, explains any gap.", ""] + md(short_counts) + [""] + md(short_t) + [
             "", "### NA readings (heatStress = NA)", "",
             f"**{na_total:,} NA readings** of {wb_total:,} deduplicated WBGT readings in the window ({pct(na_total / wb_total)}), on "
             f"{na_days:,} station-days. Station-day table (`n_na` summed): {na_label_total:,}"
             f"{' (matches)' if na_label_total == na_total else ' (DIFFERS)'}. {na_in_peak:,} fall between 10:00 and 17:59. "
             f"{n_unlab} station-days in the window have no label at all (no valid reading). "
             f"Labelled station-days: {len(lab):,}; `usable`: {usable_n:,}; labelled but not usable (low-coverage Low or Moderate): "
             f"{tot_s - usable_n:,}.", "", "Top stations:", ""] + md(na_stn) + ["", "By month:", ""] + md(na_month.rename(columns={"ym": "month", "na_readings": "NA readings"})) + [
             "", "By hour of day (SGT):", ""] + md(na_hour.rename(columns={"hour": "hour"})) + [
             "", "### Station count by month", "",
             "Stations with at least one labelled day, and the number reporting per day (min, median, max over the month's days). "
             "`first labelled` lists stations whose first labelled day in the window falls in that month (all 8 in 2025-01 "
             "are the window start). `last labelled` lists stations whose last labelled day falls in that month; stations "
             "still reporting on 31 Aug 2026 are not listed.", ""] + md(
        stn_m[["ym", "stations", "min_per_day", "median_per_day", "max_per_day", "first labelled in month", "last labelled in month"]].rename(
            columns={"ym": "month", "min_per_day": "min per day", "median_per_day": "median per day", "max_per_day": "max per day"})) + [
             "", f"![]({fig_missingness(figs_dir, stn_m, na_month)})", ""]

    # ---- assemble: flags first
    L += ["## Flags (rule-based; numbers only)", ""]
    L += [f"- {x}" for x in FLAGS] if FLAGS else ["- none raised by the rules"]
    L += [""] + body
    L += ["## Window audit", "",
          f"Tables read: {len(R.tables_read)}. Every frame brought to pandas was asserted to lie in {WIN_START} to {WIN_END}.", ""]
    L += [f"- `{t}`" for t in dict.fromkeys(R.tables_read)]
    L += [""] + md(pd.DataFrame(AUDIT, columns=["frame", "date column", "rows", "first date", "last date"]))
    assert all(lo is None or (lo >= WIN_START and hi <= WIN_END) for _, _, _, lo, hi in AUDIT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {out_path} and {len(list(figs_dir.glob('*.png')))} charts in {figs_dir}")


if __name__ == "__main__":
    main()
