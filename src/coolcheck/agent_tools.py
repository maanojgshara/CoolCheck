"""The agent's three tools as Unity Catalog SQL functions (Guide D13 and C11; docs/design/agent_tools.md).

The functions are the SQL files in src/functions, one CREATE OR REPLACE FUNCTION each, with placeholders for the function
name and the tables it reads: the creation script fills in <catalog>.gold and <catalog>.silver names, and the tests fill
in temp views and create the same text as a TEMPORARY function. The rules are written twice on purpose, in the SQL and in
the Python twin below, and the tests compare the two on the same rows.

- get_priority_areas(target_date, call_capacity, region): the date's areas of gold.area_heat_risk in TIER_ORDER, then
  tier_rank. The call budget is filled in code, in that order and then by block priority (gold.block_vulnerability), for
  CALL_TIERS only. One call is assumed per 1-2 room rental flat in a priority block (a block with at least one); the
  block that crosses the budget gets the remainder (partial) and nothing after it is filled.
- find_refuges(blk_no, street): the NEAREST refuges of the main set (silver.refuge_points.in_main) to a confirmed block,
  in any planning area; ties by refuge_id.
- what_if_add_refuge(blk_no, street): a refuge added at a confirmed block (the site). For the site's planning area, and
  any other area with a block newly within WALK_M, the confirmed blocks' dwelling units within WALK_M before and after.
Distances are straight lines sqrt(dx^2 + dy^2) in SVY21 metres from the stored x_svy21 / y_svy21 (coolcheck.access),
unrounded, and WALK_M counts as within. A block is found by blk_key and street_key (so 'Jalan Kukoh' finds JLN KUKOH),
and only a confirmed block is used.
Nothing here reads gold.heat_forecast or returns a probability or the score.
"""
import math
import re
from pathlib import Path
from string import Template

SQL_DIR = Path(__file__).resolve().parents[1] / "functions"
FUNCTIONS = {"get_priority_areas": ("area_heat_risk", "block_vulnerability"),
             "find_refuges": ("block_access", "refuge_points"),
             "what_if_add_refuge": ("block_access", "refuge_points")}
TIER_ORDER = {"High": 1, "Medium": 2, "Low": 3, "Not rated": 4, "No forecast": 5}
CALL_TIERS = ("High", "Medium")  # the tiers whose actions name the priority blocks; Low is routine
ALL_REGIONS = ("", "ALL")
NEAREST = 5
WALK_M = 400.0
AAC_PARTIAL = "Active Ageing Centre (partial list)"
# The long forms people write, read as HDB's abbreviations. Every abbreviation here occurs in block_access's streets, and
# none of the long forms does (tested), so HDB's own spelling keys as before. The SQL files write the same map.
STREET_WORDS = {"AVENUE": "AVE", "BUKIT": "BT", "CENTRAL": "CTRL", "CLOSE": "CL", "COMMONWEALTH": "CWEALTH",
                "CRESCENT": "CRES", "DRIVE": "DR", "GARDEN": "GDN", "GARDENS": "GDNS", "HEIGHTS": "HTS", "JALAN": "JLN",
                "KAMPONG": "KG", "KAMPUNG": "KG", "LORONG": "LOR", "MARKET": "MKT", "NORTH": "NTH", "PARK": "PK",
                "PLACE": "PL", "ROAD": "RD", "SAINT": "ST", "SOUTH": "STH", "SQUARE": "SQ", "STREET": "ST",
                "TANJONG": "TG", "TANJUNG": "TG", "TERRACE": "TER", "UPPER": "UPP"}

_NAME = re.compile(r"^[A-Za-z0-9_`.]+$")


# --- the SQL files -----------------------------------------------------------------------------------------------

def function_sql(name, function, tables, temporary=False):
    """The CREATE OR REPLACE FUNCTION statement of src/functions/<name>.sql with the function name and the tables it
    reads filled in; TEMPORARY for the tests' temp views. ValueError on a bad name, a missing or extra table, or a
    placeholder the file does not expect."""
    want = set(FUNCTIONS[name])
    if set(tables) != want:
        raise ValueError(f"{name} reads {sorted(want)}, got {sorted(tables)}")
    for v in (function, *tables.values()):
        if not _NAME.match(v):
            raise ValueError(f"bad name: {v!r}")
    text = Template((SQL_DIR / f"{name}.sql").read_text(encoding="utf-8"))
    if set(text.get_identifiers()) != want | {"function", "temporary"}:
        raise ValueError(f"{name}.sql has placeholders {sorted(text.get_identifiers())}")
    return text.substitute(tables, function=function, temporary="TEMPORARY " if temporary else "")


# --- lookup keys (the SQL repeats these regular expressions) -------------------------------------------------------

def region_key(s):
    """Upper case, letters only, without a trailing REGION or REGIONS: 'north-east' and 'NORTH-EAST REGION' both give
    'NORTHEAST'. None stays None. (The SQL writes the end of input as \\z, Java's form of \\Z, since $ marks a placeholder.)"""
    if s is None:
        return None
    return re.sub(r"REGIONS?\Z", "", re.sub(r"[^A-Z]", "", s.upper()))


def blk_key(s):
    """Upper case, without a leading Blk or Block, letters and digits only: 'Blk 101 a' gives '101A'."""
    if s is None:
        return None
    return re.sub(r"[^A-Z0-9]", "", re.sub(r"^\s*(BLK|BLOCK)[.\s]*", "", s.upper(), flags=re.ASCII))


def street_key(s):
    """Upper case, punctuation dropped, spaces collapsed, and each long form read as HDB's abbreviation (STREET_WORDS):
    "St. George's  Lane" gives 'ST GEORGES LANE', 'Jalan Kukoh' gives 'JLN KUKOH'."""
    if s is None:
        return None
    words = re.sub(r"[^A-Z0-9\s]", "", s.upper(), flags=re.ASCII).split()
    return " ".join(STREET_WORDS.get(w, w) for w in words)


def lookup(blocks, blk_no, street):
    """The confirmed blocks (block_access rows as dicts) whose keys match; at most one, since the keys are unique."""
    bk, sk = blk_key(blk_no), street_key(street)
    return [b for b in blocks if b["confirmed"] and blk_key(b["blk_no"]) == bk and street_key(b["street"]) == sk]


def distance(ax, ay, bx, by):
    """Straight line in SVY21 metres, as the SQL's sqrt(pow(dx, 2) + pow(dy, 2))."""
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


# --- get_priority_areas ------------------------------------------------------------------------------------------

def priority_areas(risk, blocks, target_date, call_capacity, region=None):
    """Rows of get_priority_areas from rows of area_heat_risk and block_vulnerability (dicts), in area_order."""
    cap = max(call_capacity or 0, 0)
    rk = region_key(region)
    areas = sorted((r for r in risk if r["target_date"] == target_date
                    and (rk is None or rk in ALL_REGIONS or region_key(r["region"]) == rk)),
                   key=lambda r: (TIER_ORDER.get(r["tier"], 5), r["tier_rank"], r["planning_area"]))
    by_area = {}
    for b in blocks:
        by_area.setdefault(b["planning_area"], []).append(b)
    needed_before, used, out = 0, 0, []
    for order, a in enumerate(areas, start=1):
        own = sorted(by_area.get(a["planning_area"], []), key=lambda b: b["priority"])
        given = []
        if a["tier"] in CALL_TIERS:
            for b in own:
                need = b["rental_1_2_room"]
                if need <= 0:
                    continue
                calls = max(min(need, cap - needed_before), 0)
                needed_before += need
                if calls > 0:
                    given.append({"priority": b["priority"], "blk_no": b["blk_no"], "street": b["street"],
                                  "rental_1_2_room": need, "calls_allocated": calls, "partial": calls < need,
                                  "refuge_main_name": b["refuge_main_name"], "refuge_main_m": b["refuge_main_m"],
                                  "refuge_within_400m": b["refuge_within_400m"]})
        allocated = sum(g["calls_allocated"] for g in given)
        used += allocated
        out.append({"area_order": order, "planning_area": a["planning_area"], "region": a["region"],
                    "heat_level": a["heat_level"], "third": a["third"], "tier": a["tier"], "tier_rank": a["tier_rank"],
                    "tier_sentence": a["tier_sentence"], "reason": a["reason"], "actions": a["actions"],
                    "actions_status": a["actions_status"], "rental_1_2_room": sum(b["rental_1_2_room"] for b in own),
                    "calls_allocated": allocated, "calls_left": cap - used, "blocks": given})
    return out


# --- find_refuges ------------------------------------------------------------------------------------------------

def refuge_type(layer, status):
    if layer == "aac_partial":
        return AAC_PARTIAL
    if layer == "community_club":
        return "Community Club (temporary office)" if status == "temp_office" else "Community Club"
    return layer


def nearest_refuges(block, refuges, n=NEAREST):
    """Rows of find_refuges for one block (dict with x_svy21 / y_svy21): the n nearest main-set refuges, ties by id."""
    d = sorted(((distance(block["x_svy21"], block["y_svy21"], r["x_svy21"], r["y_svy21"]), r["refuge_id"], r)
                for r in refuges if r["in_main"]), key=lambda t: t[:2])
    return [{"refuge_rank": rank, "blk_no": block["blk_no"], "street": block["street"],
             "planning_area": block["planning_area"], "refuge_name": r["name"],
             "refuge_type": refuge_type(r["layer"], r["status"]), "address": r["address"],
             "postal_code": r["postal_code"], "refuge_planning_area": r["planning_area"], "distance_m": dist,
             "within_400m": dist <= WALK_M}
            for rank, (dist, _, r) in enumerate(d[:n], start=1)]


def find_refuges(blocks, refuges, blk_no, street, n=NEAREST):
    """Rows of find_refuges from rows of block_access and refuge_points (dicts)."""
    return [row for b in lookup(blocks, blk_no, street) for row in nearest_refuges(b, refuges, n)]


# --- what_if_add_refuge ------------------------------------------------------------------------------------------

def what_if_add_refuge(blocks, refuges, blk_no, street, walk_m=WALK_M):
    """Rows of what_if_add_refuge from rows of block_access and refuge_points (dicts): the site's area first."""
    found = lookup(blocks, blk_no, street)
    if not found:
        return []
    s = found[0]
    conf = [b for b in blocks if b["confirmed"]]
    main = [r for r in refuges if r["in_main"]]
    d_site = [distance(b["x_svy21"], b["y_svy21"], s["x_svy21"], s["y_svy21"]) for b in conf]
    areas = {s["planning_area"]} | {b["planning_area"] for b, d in zip(conf, d_site) if d <= walk_m}
    rows = []
    for area in areas:
        recs = []
        for b, ds in zip(conf, d_site):
            if b["planning_area"] == area:
                before = min(distance(b["x_svy21"], b["y_svy21"], r["x_svy21"], r["y_svy21"]) for r in main)
                recs.append((b, before, min(before, ds), b["1room_rental"] + b["2room_rental"]))
        new = sorted(((after, b["blk_no"], b["street"], b, before, rent) for b, before, after, rent in recs
                      if before > walk_m and after <= walk_m), key=lambda t: t[:3])
        if area != s["planning_area"] and not new:
            continue
        du = sum(b["total_dwelling_units"] for b, _, _, _ in recs)
        du_before = sum(b["total_dwelling_units"] for b, before, _, _ in recs if before <= walk_m)
        du_after = sum(b["total_dwelling_units"] for b, _, after, _ in recs if after <= walk_m)
        rows.append({"planning_area": area, "is_site_area": area == s["planning_area"], "site_blk_no": s["blk_no"],
                     "site_street": s["street"], "hdb_dwelling_units": du, "du_within_400m_before": du_before,
                     "du_within_400m_after": du_after, "share_within_400m_before": float(du_before) / float(du),
                     "share_within_400m_after": float(du_after) / float(du),
                     "rental_flats_beyond_400m_before": sum(rent for _, before, _, rent in recs if before > walk_m),
                     "rental_flats_beyond_400m_after": sum(rent for _, _, after, rent in recs if after > walk_m),
                     "blocks_newly_within": len(new),
                     "newly_within": [{"blk_no": b["blk_no"], "street": b["street"],
                                       "total_dwelling_units": b["total_dwelling_units"], "rental_1_2_room": rent,
                                       "distance_before_m": before, "distance_after_m": after}
                                      for after, _, _, b, before, rent in new]})
    rows.sort(key=lambda r: (not r["is_site_area"], r["planning_area"]))
    return rows
