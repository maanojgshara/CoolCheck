"""Risk score and tiers (Guide §A11 decisions 7 to 9; docs/design/risk_score.md).

The vulnerability index V of a rated planning area is a weighted sum of seven component percentiles; the tier crosses
tomorrow's heat level with the area's vulnerability third. The rules are written twice on purpose: in Python here (the
checks and the tests) and as the SQL of the three Unity Catalog views (area_vulnerability_sql, block_vulnerability_sql,
area_heat_risk_sql). The SQL does the same floating-point operations in the same order, and the tests compare the two
on the same rows. The SQL builders take table names, so the tests can point them at temp views.

- Rated: an area with at least one confirmed HDB block. Thirds by V: places 1 to 11 upper, 12 to 22 middle, the rest
  lower; a tie is broken by residents aged 75+ (more first), then by name.
- Percentile p = (mean rank - 1) / (n - 1) among the rated areas with a usable value, ranked so that a larger p is more
  vulnerable; ties share the mean rank. A missing value, or a share or rate over a small denominator (decision 9(g)),
  is held at 0.5 and left out of that component's ranking. Counts always keep their real value.
- Reason: the two components with the largest weight x p among those with a usable value and p >= 0.5.
- Heat level: High if p_high >= HIGH_CUTOFF; else Moderate if p_moderate >= p_low; else Low. A null probability gives no
  heat level and the tier "No forecast".
- Score = p_high x V orders areas within a tier only (tier_rank); neither it nor P(High) leaves the view.
"""
import csv
import math
import re
from datetime import date
from pathlib import Path

HIGH_CUTOFF = 0.10975585695894975  # decision 7, the H4 cut-off; equals coolcheck.final_check.FINAL_CUTOFF (tested)
LAST_BACKTEST_DATE = date(2026, 8, 31)  # nothing after it is read: the final check (1 Sep to 19 Oct 2026) is not scored
WALK_M = 400.0
UPPER, MIDDLE = 11, 11  # the lower third is the rest (10 of 32)
FLAG_MIN = 1000
COMPONENTS = ("aged_75_plus", "share_75_plus", "rental_1_2_room", "electricity_hot_rise", "refuge_beyond_400m",
              "refuges_per_1000_65", "park_beyond_400m")
DIRECTIONS = ("higher", "inverted")
SMALL_RULES = {"none": None, "hdb_du": ("du", "confirmed HDB dwelling units"), "residents": ("residents", "residents"),
               "aged_65": ("aged_65_plus", "residents aged 65+")}
NO_REASON = "no component above the middle of the rated areas"
HEATS = ("Low", "Moderate", "High")
THIRDS = ("lower", "middle", "upper")
TIER_MAIN = {**{("Low", t): "Low" for t in THIRDS},
             ("Moderate", "lower"): "Low", ("Moderate", "middle"): "Medium", ("Moderate", "upper"): "Medium",
             ("High", "lower"): "Medium", ("High", "middle"): "High", ("High", "upper"): "High"}
TIER_VARIANT = {**TIER_MAIN, ("Moderate", "middle"): "Low"}  # decision 9(f), the user's open choice
TIER_SEVERITY = {"Low": 1, "Medium": 2, "High": 3}
HEAT_ORDER = {"High": 1, "Moderate": 2, "Low": 3}
NO_FORECAST, NOT_RATED = "No forecast", "Not rated"


# --- reference data ----------------------------------------------------------------------------------------------

def check_weights(weights, components=COMPONENTS):
    """Raise ValueError unless the weights cover exactly these components, with valid directions and rules, summing to 1."""
    got = [w["component"] for w in weights]
    if sorted(got) != sorted(components):
        raise ValueError(f"weights cover {sorted(got)}, expected {sorted(components)}")
    for w in weights:
        if w["direction"] not in DIRECTIONS:
            raise ValueError(f"{w['component']}: direction {w['direction']!r}")
        if w["small_area_rule"] not in SMALL_RULES:
            raise ValueError(f"{w['component']}: small_area_rule {w['small_area_rule']!r}")
        if (w["small_area_rule"] != "none") != (w["small_area_min"] is not None):
            raise ValueError(f"{w['component']}: a small-area rule needs small_area_min, and only then")
    total = sum(w["weight"] for w in weights)
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"weights sum to {total!r}, not 1")


def load_weights(path):
    """The weights file (reference/score_weights.csv) as a list in sort_order, checked."""
    with Path(path).open(encoding="utf-8", newline="") as fh:
        rows = [dict(r, weight=float(r["weight"]), sort_order=int(r["sort_order"]),
                     small_area_min=int(r["small_area_min"]) if r["small_area_min"] else None) for r in csv.DictReader(fh)]
    check_weights(rows)
    return sorted(rows, key=lambda w: w["sort_order"])


# --- the vulnerability index ---------------------------------------------------------------------------------------

def _num(v):
    return None if v is None or v == "" else float(v)


def area_inputs(exposure, access, blocks, electricity, refuge_set="main", park_set="main", age="75"):
    """{area: inputs} for the rated areas, from the rows of area_exposure, area_access, block_access and
    ema_area_electricity (CSV dicts or the same values). age = '65' swaps the 75+ count and share for the 65+ pair."""
    exp = {r["planning_area"]: r for r in exposure}
    acc = {(r["planning_area"], r["measure"], r["layer_set"]): r for r in access}
    elec = {r["planning_area"]: _num(r["hot_ratio_mean"]) for r in electricity}
    rental = {}
    for b in blocks:
        if str(b["confirmed"]).lower() == "true":
            rental[b["planning_area"]] = rental.get(b["planning_area"], 0) + int(b["1room_rental"]) + int(b["2room_rental"])
    out = {}
    for (area, measure, layer), r in sorted(acc.items()):
        if measure != "refuge" or layer != "main" or int(r["hdb_blocks_confirmed"]) <= 0:
            continue
        e, ref, park = exp[area], acc[(area, "refuge", refuge_set)], acc[(area, "park", park_set)]
        share_refuge, share_park = _num(ref["share_du_within_400m"]), _num(park["share_du_within_400m"])
        out[area] = {
            "planning_area_code": e["planning_area_code"], "region": e["region"], "residents": int(e["residents"]),
            "aged_65_plus": int(e["aged_65_plus"]), "aged_75_plus": int(e["aged_75_plus"]),
            "du": int(r["hdb_dwelling_units_confirmed"]),
            "raw": {"aged_75_plus": float(e[f"aged_{age}_plus"]), "share_75_plus": _num(e[f"share_{age}_plus"]),
                    "rental_1_2_room": float(rental.get(area, 0)), "electricity_hot_rise": elec.get(area),
                    "refuge_beyond_400m": None if share_refuge is None else 1.0 - share_refuge,
                    "refuges_per_1000_65": _num(ref["refuges_per_1000_65_plus"]),
                    "park_beyond_400m": None if share_park is None else 1.0 - share_park}}
    return out


def percentiles(values, direction):
    """{key: p} for usable values: p = (mean rank - 1) / (n - 1), ranked so that a larger p is more vulnerable."""
    sign = -1.0 if direction == "inverted" else 1.0
    keys = sorted(values, key=lambda k: sign * values[k])
    n, out, i = len(keys), {}, 0
    while i < n:
        j = i
        while j + 1 < n and sign * values[keys[j + 1]] == sign * values[keys[i]]:
            j += 1
        p = (i + (j - i) / 2) / (n - 1) if n > 1 else 0.5
        for k in keys[i:j + 1]:
            out[k] = p
        i = j + 1
    return out


def neutral_reason(inputs, w):
    """Why a component is held at 0.5 for an area ('no value' or a small denominator), or None if it is usable."""
    if inputs["raw"][w["component"]] is None:
        return "no value"
    rule = SMALL_RULES[w["small_area_rule"]]
    if rule and inputs[rule[0]] < w["small_area_min"]:
        return f"fewer than {w['small_area_min']:,} {rule[1]}"
    return None


def vulnerability(inputs, weights, upper=UPPER, middle=MIDDLE):
    """{area: result} with the percentiles, V, its rank, the third, the reason, the flags and the neutral components."""
    res = {a: {"p": {}, "neutral": {}} for a in inputs}
    for w in weights:
        k = w["component"]
        usable = {}
        for a, x in inputs.items():
            why = neutral_reason(x, w)
            if why is None:
                usable[a] = x["raw"][k]
            else:
                res[a]["neutral"][k] = why
        ps = percentiles(usable, w["direction"])
        for a in inputs:
            res[a]["p"][k] = ps.get(a, 0.5)
    wmap = {w["component"]: w for w in weights}
    for a, x in inputs.items():
        r = res[a]
        v = 0.0
        for k in COMPONENTS:
            if k in wmap:
                v = v + wmap[k]["weight"] * r["p"][k]
        r["v"] = v
        cands = sorted(((wmap[k]["weight"] * r["p"][k], wmap[k]["sort_order"], wmap[k]["reason_phrase"])
                        for k in wmap if k not in r["neutral"] and r["p"][k] >= 0.5), key=lambda c: (-c[0], c[1]))
        r["reason"] = "; ".join(c[2] for c in cands[:2]) or NO_REASON
        r["neutral_components"] = "; ".join(f"{k} ({r['neutral'][k]})" for k in sorted(r["neutral"], key=lambda k: wmap[k]["sort_order"])) or None
        r.update(small_hdb=x["du"] < FLAG_MIN, small_residents=x["residents"] < FLAG_MIN,
                 small_aged_65=x["aged_65_plus"] < FLAG_MIN, electricity_missing=x["raw"]["electricity_hot_rise"] is None)
    order = sorted(inputs, key=lambda a: (-res[a]["v"], -inputs[a]["aged_75_plus"], a))
    for i, a in enumerate(order, start=1):
        res[a]["v_rank"] = i
        res[a]["third"] = "upper" if i <= upper else "middle" if i <= upper + middle else "lower"
    return res


# --- heat level, tier and order --------------------------------------------------------------------------------------

def _missing(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def heat_level(p_low, p_moderate, p_high, cutoff=HIGH_CUTOFF):
    """High, Moderate or Low (decision 8(d)), or None when a probability is missing."""
    if _missing(p_low) or _missing(p_moderate) or _missing(p_high):
        return None
    if p_high >= cutoff:
        return "High"
    return "Moderate" if p_moderate >= p_low else "Low"


def tier(heat, third, matrix=TIER_MAIN):
    """The area's tier: 'No forecast' without a heat level, 'Not rated' without a third, else the 3x3 matrix."""
    if heat is None:
        return NO_FORECAST
    if third is None:
        return NOT_RATED
    return matrix[(heat, third)]


def tier_sentence(t, heat, third):
    if t == NO_FORECAST:
        return "No forecast: no heat forecast for this area and date"
    if t == NOT_RATED:
        return f"Not rated: forecast {heat} heat; no HDB blocks to rate"
    return f"{t}: forecast {heat} heat, {third} third for vulnerability"


def heat_risk(forecast, vuln, matrix=TIER_MAIN, cutoff=HIGH_CUTOFF):
    """Rows of area_heat_risk from forecast rows (dicts with target_date, planning_area, p_low, p_moderate, p_high)."""
    out = []
    for f in forecast:
        heat = heat_level(f["p_low"], f["p_moderate"], f["p_high"], cutoff)
        v = vuln.get(f["planning_area"])
        third = v["third"] if v else None
        t = tier(heat, third, matrix)
        score = f["p_high"] * v["v"] if v is not None and heat is not None else None
        out.append({**f, "heat_level": heat, "rated": v is not None, "third": third, "tier": t, "score": score,
                    "tier_sentence": tier_sentence(t, heat, third), "reason": v["reason"] if v else None})
    groups = {}
    for r in out:
        groups.setdefault((r["target_date"], r["tier"]), []).append(r)
    for rows in groups.values():
        rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0.0), HEAT_ORDER.get(r["heat_level"], 4), r["planning_area"]))
        for i, r in enumerate(rows, start=1):
            r["tier_rank"] = i
    return out


def block_priority(blocks, rated):
    """{(blk_no, street): priority} within each rated area: 1-2 room rental flats, most first; then distance to the
    nearest refuge, farthest first; then blk_no and street."""
    by_area = {}
    for b in blocks:
        if b["planning_area"] in rated:
            by_area.setdefault(b["planning_area"], []).append(b)
    out = {}
    for rows in by_area.values():
        rows.sort(key=lambda b: (-(int(b["1room_rental"]) + int(b["2room_rental"])), -float(b["refuge_main_m"]),
                                 b["blk_no"], b["street"]))
        for i, b in enumerate(rows, start=1):
            out[(b["blk_no"], b["street"])] = i
    return out


# --- the back-test rows (hard rule) ------------------------------------------------------------------------------------

def assert_on_or_before(dates, last=LAST_BACKTEST_DATE):
    """Raise ValueError if any date is after last (nothing from the final check's window may be read)."""
    late = [d for d in dates if d > last]
    if late:
        raise ValueError(f"{len(late)} rows dated after {last}, first {min(late)}: the final check's window must not be read")


def read_backtest_area_days(path, last=LAST_BACKTEST_DATE, columns=None):
    """The back-test's area-day predictions with target dates on or before last: filtered at read time (pyarrow), then
    asserted. target_date comes back as a date."""
    import datetime as dt

    import pyarrow.parquet as pq

    table = pq.read_table(path, columns=columns, filters=[("target_date", "<=", dt.datetime(last.year, last.month, last.day))])
    frame = table.to_pandas()
    frame["target_date"] = frame["target_date"].dt.date
    assert_on_or_before(frame["target_date"], last)
    return frame


# --- SQL for the views -----------------------------------------------------------------------------------------------

_NAME = re.compile(r"^[A-Za-z0-9_`.]+$")


def _t(name):
    if not _NAME.match(name):
        raise ValueError(f"bad table name: {name!r}")
    return name


def _lit(s):
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


VULN_COLUMNS = [
    ("planning_area", "Master Plan 2025 planning area; one row per rated area (at least one confirmed HDB block)."),
    ("planning_area_code", "Master Plan 2025 planning area code."),
    ("region", "Master Plan 2025 region."),
    ("residents", "Residents (silver.area_exposure, SingStat June 2026)."),
    ("aged_65_plus", "Residents aged 65+ (silver.area_exposure)."),
    ("aged_75_plus", "Residents aged 75+ (silver.area_exposure); component aged_75_plus, and the tie-break for the thirds."),
    ("share_75_plus", "Share of residents aged 75+ (silver.area_exposure); component share_75_plus."),
    ("hdb_dwelling_units_confirmed", "HDB dwelling units of the confirmed blocks (silver.area_access)."),
    ("rental_1_2_room", "1-room plus 2-room rental flats over the confirmed blocks (silver.block_access); component rental_1_2_room."),
    ("electricity_hot_ratio", "1-2 room hot-month electricity ratio, mean of 2022 to 2024 (silver.ema_area_electricity); a smaller rise may indicate less air-con use; null where EMA has no value."),
    ("refuge_beyond_400m", "Share of HDB dwelling units beyond 400 m (straight line) of a refuge, main set (1 - silver.area_access share)."),
    ("refuges_per_1000_65_plus", "Refuges in the area per 1,000 residents aged 65+, main set (silver.area_access)."),
    ("park_beyond_400m", "Share of HDB dwelling units beyond 400 m of a park edge, main set (1 - silver.area_access share)."),
    *[(f"p_{k}", f"Percentile of {k} among the rated areas with a usable value, 1 = most vulnerable; 0.5 when held neutral.") for k in COMPONENTS],
    ("v", "Vulnerability index V = sum of weight x percentile (gold.score_weights), 0 to 1."),
    ("v_rank", "Rank of V, 1 = most vulnerable; ties by residents aged 75+ (more first), then name."),
    ("third", "upper (ranks 1 to 11), middle (12 to 22) or lower (the rest)."),
    ("reason", "The two components with the largest weight x percentile, among those with a usable value and percentile >= 0.5, in plain words."),
    ("small_hdb", "Fewer than 1,000 confirmed HDB dwelling units: the two 400 m shares are held at 0.5 (decision 9(g))."),
    ("small_residents", "Fewer than 1,000 residents: the 75+ share is held at 0.5 (decision 9(g))."),
    ("small_aged_65", "Fewer than 1,000 residents aged 65+: refuges per 1,000 aged 65+ is held at 0.5 (decision 9(g))."),
    ("electricity_missing", "EMA has no 2022 to 2024 value for the area: the electricity component is held at 0.5."),
    ("neutral_components", "Each component held at 0.5, with the reason; null if none."),
]
BLOCK_COLUMNS = [
    ("planning_area", "Master Plan 2025 planning area (rated areas only)."),
    ("planning_area_code", "Master Plan 2025 planning area code."),
    ("blk_no", "HDB block number."),
    ("street", "HDB street name; blk_no + street is unique."),
    ("confirmed", "True if the block's OneMap coordinate is confirmed (10,807 of 10,817)."),
    ("total_dwelling_units", "HDB dwelling units in the block."),
    ("1room_rental", "1-room rental flats in the block (HDB Property Information)."),
    ("2room_rental", "2-room rental flats in the block (HDB Property Information)."),
    ("rental_1_2_room", "1-room plus 2-room rental flats in the block."),
    ("refuge_main_m", "Straight-line distance in m to the nearest refuge of the main set."),
    ("refuge_main_name", "Name of that refuge."),
    ("refuge_within_400m", "refuge_main_m <= 400."),
    ("park_main_m", "Straight-line distance in m to the nearest park edge of the main set, 0 inside."),
    ("park_main_name", "Name of that park."),
    ("park_within_400m", "park_main_m <= 400."),
    ("lat", "WGS84 latitude (OneMap)."),
    ("lon", "WGS84 longitude (OneMap)."),
    ("priority", "Order within the area, 1 first: 1-2 room rental flats, most first; then distance to the nearest refuge, farthest first; then blk_no, street. Vulnerability only, never heat."),
]
RISK_COLUMNS = [
    ("target_date", "The date forecast (gold.heat_forecast)."),
    ("planning_area", "Master Plan 2025 planning area."),
    ("planning_area_code", "Master Plan 2025 planning area code."),
    ("region", "Master Plan 2025 region."),
    ("station_id", "The WBGT station whose forecast the area takes (gold.heat_forecast)."),
    ("heat_level", "Tomorrow's heat: High if P(High) >= 0.10975585695894975 (decision 7), else Moderate if p_moderate >= p_low, else Low; null without a forecast."),
    ("rated", "True if the area has a vulnerability third (at least one confirmed HDB block)."),
    ("third", "The area's vulnerability third (gold.area_vulnerability); null if not rated."),
    ("tier", "High, Medium or Low by the 3x3 rule of heat level and third; Not rated; No forecast."),
    ("tier_rank", "Order within the tier on the date, 1 first: P(High) x V (never shown), then heat level, then name."),
    ("tier_sentence", "The tier in one sentence, e.g. High: forecast High heat, upper third for vulnerability."),
    ("reason", "The area's vulnerability reason (gold.area_vulnerability)."),
    ("actions", "The tier's actions (gold.tier_actions)."),
    ("actions_status", "Review status of the actions: a proposal, not yet reviewed by a practitioner."),
    ("small_hdb", "Small-area flag (gold.area_vulnerability)."),
    ("small_residents", "Small-area flag (gold.area_vulnerability)."),
    ("small_aged_65", "Small-area flag (gold.area_vulnerability)."),
    ("forecast_missing", "The forecast issue was missing for the date (gold.heat_forecast); a data-quality flag."),
    ("model_version", "Model version (gold.heat_forecast)."),
    ("run_id", "Scoring run (gold.heat_forecast)."),
    ("cutoff_ts", "Information cut-off of the scoring run (gold.heat_forecast)."),
    ("scored_at", "When the row was scored (gold.heat_forecast)."),
]


def area_vulnerability_sql(exposure, access, blocks, electricity, weights, upper=UPPER, middle=MIDDLE, flag_min=FLAG_MIN):
    """SELECT for gold.area_vulnerability over the Silver tables and gold.score_weights (names passed in)."""
    exposure, access, blocks, electricity, weights = map(_t, (exposure, access, blocks, electricity, weights))
    stack = ", ".join(f"'{k}', CAST(b.{k} AS DOUBLE)" for k in COMPONENTS)
    p_cols = ",\n    ".join(f"max(CASE WHEN component = '{k}' THEN p END) AS p_{k}" for k in COMPONENTS)
    c_cols = ",\n    ".join(f"max(CASE WHEN component = '{k}' THEN contribution END) AS c_{k}" for k in COMPONENTS)
    v_sum = " + ".join(f"coalesce(g.c_{k}, 0.0D)" for k in COMPONENTS)
    small = "\n".join(f"    WHEN g.small_area_rule = '{rule}' AND l.{col} < g.small_area_min THEN "
                      f"concat('fewer than ', format_number(g.small_area_min, 0), ' {label}')"
                      for rule, spec in SMALL_RULES.items() if spec for col, label in [spec])
    out_cols = ", ".join(c for c, _ in VULN_COLUMNS)
    return f"""
WITH base AS (
  SELECT a.planning_area, e.planning_area_code, e.region, e.residents, e.aged_65_plus, e.aged_75_plus, e.share_75_plus,
         a.hdb_dwelling_units_confirmed AS du, r.rental_1_2_room, el.hot_ratio_mean AS electricity_hot_rise,
         1.0D - a.share_du_within_400m AS refuge_beyond_400m, a.refuges_per_1000_65_plus AS refuges_per_1000_65,
         1.0D - k.share_du_within_400m AS park_beyond_400m
  FROM {access} a
  JOIN {exposure} e ON e.planning_area = a.planning_area
  JOIN {access} k ON k.planning_area = a.planning_area AND k.measure = 'park' AND k.layer_set = 'main'
  LEFT JOIN (SELECT planning_area, SUM(`1room_rental` + `2room_rental`) AS rental_1_2_room
             FROM {blocks} WHERE confirmed GROUP BY planning_area) r ON r.planning_area = a.planning_area
  LEFT JOIN {electricity} el ON el.planning_area = a.planning_area
  WHERE a.measure = 'refuge' AND a.layer_set = 'main' AND a.hdb_blocks_confirmed > 0
),
long AS (
  SELECT b.planning_area, b.du, b.residents, b.aged_65_plus, s.component, s.raw
  FROM base b LATERAL VIEW stack({len(COMPONENTS)}, {stack}) s AS component, raw
),
w AS (
  SELECT l.planning_area, l.component, l.raw, g.weight, g.direction, g.reason_phrase, g.sort_order,
    CASE WHEN l.raw IS NULL THEN 'no value'
{small}
    END AS neutral_reason,
    CASE WHEN g.direction = 'inverted' THEN -l.raw ELSE l.raw END AS oriented
  FROM long l JOIN {weights} g ON g.component = l.component
),
r AS (
  SELECT w.*, neutral_reason IS NULL AS usable,
    rank() OVER (PARTITION BY component, neutral_reason IS NULL ORDER BY oriented) AS rank_min,
    count(*) OVER (PARTITION BY component, neutral_reason IS NULL, oriented) AS ties,
    count(*) OVER (PARTITION BY component, neutral_reason IS NULL) AS n_usable
  FROM w
),
p AS (
  SELECT r.*,
    CASE WHEN NOT usable THEN 0.5D
         WHEN n_usable > 1 THEN (CAST(rank_min - 1 AS DOUBLE) + CAST(ties - 1 AS DOUBLE) / 2.0D) / CAST(n_usable - 1 AS DOUBLE)
         ELSE 0.5D END AS p
  FROM r
),
c AS (
  SELECT p.*, weight * p AS contribution, usable AND p >= 0.5D AS eligible,
    row_number() OVER (PARTITION BY planning_area
                       ORDER BY CASE WHEN usable AND p >= 0.5D THEN 0 ELSE 1 END, weight * p DESC, sort_order) AS reason_rank
  FROM p
),
g AS (
  SELECT planning_area,
    {p_cols},
    {c_cols},
    concat_ws('; ', max(CASE WHEN reason_rank = 1 AND eligible THEN reason_phrase END),
                    max(CASE WHEN reason_rank = 2 AND eligible THEN reason_phrase END)) AS reason_raw,
    array_join(transform(array_sort(collect_list(CASE WHEN NOT usable THEN
      named_struct('o', sort_order, 't', concat(component, ' (', neutral_reason, ')')) END)), x -> x.t), '; ') AS neutral_raw
  FROM c GROUP BY planning_area
),
scored AS (
  SELECT b.planning_area, b.planning_area_code, b.region, b.residents, b.aged_65_plus, b.aged_75_plus, b.share_75_plus,
         b.du AS hdb_dwelling_units_confirmed, b.rental_1_2_room, b.electricity_hot_rise AS electricity_hot_ratio,
         b.refuge_beyond_400m, b.refuges_per_1000_65 AS refuges_per_1000_65_plus, b.park_beyond_400m,
         {", ".join(f"g.p_{k}" for k in COMPONENTS)},
         {v_sum} AS v,
         coalesce(nullif(g.reason_raw, ''), {_lit(NO_REASON)}) AS reason,
         b.du < {int(flag_min)} AS small_hdb, b.residents < {int(flag_min)} AS small_residents,
         b.aged_65_plus < {int(flag_min)} AS small_aged_65, b.electricity_hot_rise IS NULL AS electricity_missing,
         nullif(g.neutral_raw, '') AS neutral_components
  FROM base b JOIN g ON g.planning_area = b.planning_area
),
ranked AS (
  SELECT scored.*, row_number() OVER (ORDER BY v DESC, aged_75_plus DESC, planning_area) AS v_rank FROM scored
)
SELECT {out_cols} FROM (
  SELECT ranked.*, CASE WHEN v_rank <= {int(upper)} THEN 'upper' WHEN v_rank <= {int(upper) + int(middle)} THEN 'middle'
                        ELSE 'lower' END AS third
  FROM ranked)
"""


def block_vulnerability_sql(blocks, vulnerability):
    """SELECT for gold.block_vulnerability: every HDB block in a rated area, with its priority within the area."""
    blocks, vulnerability = _t(blocks), _t(vulnerability)
    out_cols = ", ".join(f"`{c}`" if c[0].isdigit() else c for c, _ in BLOCK_COLUMNS)
    return f"""
SELECT {out_cols} FROM (
  SELECT b.planning_area, b.planning_area_code, b.blk_no, b.street, b.confirmed, b.total_dwelling_units,
         b.`1room_rental`, b.`2room_rental`, b.`1room_rental` + b.`2room_rental` AS rental_1_2_room,
         b.refuge_main_m, b.refuge_main_name, b.refuge_main_m <= {WALK_M!r}D AS refuge_within_400m,
         b.park_main_m, b.park_main_name, b.park_main_m <= {WALK_M!r}D AS park_within_400m, b.lat, b.lon,
         row_number() OVER (PARTITION BY b.planning_area
                            ORDER BY b.`1room_rental` + b.`2room_rental` DESC, b.refuge_main_m DESC, b.blk_no, b.street) AS priority
  FROM {blocks} b JOIN (SELECT planning_area FROM {vulnerability}) v ON v.planning_area = b.planning_area)
"""


def area_heat_risk_sql(forecast, vulnerability, exposure, actions, matrix=TIER_MAIN, cutoff=HIGH_CUTOFF):
    """SELECT for gold.area_heat_risk: window B's gold.heat_forecast joined with the vulnerability and the actions."""
    forecast, vulnerability, exposure, actions = map(_t, (forecast, vulnerability, exposure, actions))
    cases = "\n".join(f"         WHEN heat_level = '{h}' AND third = '{t}' THEN '{matrix[(h, t)]}'" for h in HEATS for t in THIRDS)
    out_cols = ", ".join(c for c, _ in RISK_COLUMNS)
    return f"""
WITH f AS (
  SELECT target_date, planning_area, station_id, p_low, p_moderate, p_high, model_version, run_id, cutoff_ts, scored_at,
         forecast_missing,
    CASE WHEN p_low IS NULL OR p_moderate IS NULL OR p_high IS NULL OR isnan(p_low) OR isnan(p_moderate) OR isnan(p_high) THEN NULL
         WHEN p_high >= {cutoff!r}D THEN 'High'
         WHEN p_moderate >= p_low THEN 'Moderate'
         ELSE 'Low' END AS heat_level
  FROM {forecast}
),
j AS (
  SELECT f.*, e.planning_area_code, e.region, v.v, v.third, v.reason, v.small_hdb, v.small_residents, v.small_aged_65,
         v.planning_area IS NOT NULL AS rated
  FROM f LEFT JOIN {exposure} e ON e.planning_area = f.planning_area
         LEFT JOIN {vulnerability} v ON v.planning_area = f.planning_area
),
t AS (
  SELECT j.*,
    CASE WHEN heat_level IS NULL THEN '{NO_FORECAST}'
         WHEN NOT rated THEN '{NOT_RATED}'
{cases}
    END AS tier,
    CASE WHEN rated AND heat_level IS NOT NULL THEN p_high * v END AS score,
    CASE heat_level WHEN 'High' THEN 1 WHEN 'Moderate' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END AS heat_order
  FROM j
),
o AS (
  SELECT t.*,
    row_number() OVER (PARTITION BY target_date, tier ORDER BY score DESC NULLS LAST, heat_order, planning_area) AS tier_rank,
    CASE WHEN tier = '{NO_FORECAST}' THEN 'No forecast: no heat forecast for this area and date'
         WHEN NOT rated THEN concat('Not rated: forecast ', heat_level, ' heat; no HDB blocks to rate')
         ELSE concat(tier, ': forecast ', heat_level, ' heat, ', third, ' third for vulnerability') END AS tier_sentence
  FROM t
)
SELECT {out_cols} FROM (
  SELECT o.*, a.actions, a.review_status AS actions_status FROM o LEFT JOIN {actions} a ON a.tier = o.tier)
"""
