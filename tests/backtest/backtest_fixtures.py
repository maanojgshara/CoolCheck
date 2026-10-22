"""Synthetic station-days for the back-test tests, shaped like coolcheck.backtest.station_day_rows."""
import numpy as np
import pandas as pd

from coolcheck.backtest import LAST_BACKTEST_DATE

SEASON = {12: "NE monsoon", 1: "NE monsoon", 2: "NE monsoon", 3: "Inter-monsoon 1", 4: "Inter-monsoon 1",
          5: "Inter-monsoon 1", 6: "SW monsoon", 7: "SW monsoon", 8: "SW monsoon", 9: "SW monsoon",
          10: "Inter-monsoon 2", 11: "Inter-monsoon 2"}
MISSING_FC = (pd.Timestamp("2025-03-03"), pd.Timestamp("2025-07-21"), pd.Timestamp("2026-04-29"))


def synthetic_rows(seed=0, stations=("S124", "S125", "S142"), end=LAST_BACKTEST_DATE):
    """A seasonal, persistent daily peak per station (S142 runs 2 degrees hotter), its label, and one forecast per
    date shared by all stations (missing on MISSING_FC)."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-17", end, freq="D")
    fc = {d: (33.0 + float(rng.random() < 0.5), "Thundery Showers" if rng.random() < 0.7 else "Showers") for d in dates}
    out = []
    for s in stations:
        hot, prev = (2.0 if s == "S142" else 0.0), 31.0
        for d in dates:
            peak = 30.5 + hot + 1.5 * np.sin(2 * np.pi * (d.dayofyear - 60) / 365) + 0.5 * (prev - 31) + rng.normal(0, 1)
            y = 2 if peak >= 33 else 1 if peak >= 31 else 0
            missing = d in MISSING_FC
            out.append({"station_id": s, "target_date": d, "wbgt_peak_d1": prev, "wbgt_peak_mean_7d": prev,
                        "station_char_30d": hot, "n_high_d1": float(prev >= 33), "panel_peak_mean_d1": 31.0,
                        "panel_high_count_d1": 0.0, "fc_temp_high": np.nan if missing else fc[d][0],
                        "fc_text": None if missing else fc[d][1], "rain_d1_mm": float(rng.exponential(3)),
                        "month": d.month, "season": SEASON[d.month], "forecast_missing": missing, "y": y,
                        "label_n_high": 3 if y == 2 else 0})
            prev = peak
    return pd.DataFrame(out)


def labels_of(rows):
    return rows[["station_id", "target_date", "y"]]
