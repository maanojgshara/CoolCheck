"""Small get_priority_areas results and a fake warehouse for the plan and agent tests (no workspace needed)."""
import copy
import datetime as dt
import re

D24 = dt.date(2026, 10, 24)


def block(priority, blk, street, flats, calls, partial=False, refuge="Bidadari CC", m=448.34, within=False):
    return {"priority": priority, "blk_no": blk, "street": street, "rental_1_2_room": flats, "calls_allocated": calls,
            "partial": partial, "refuge_main_name": refuge, "refuge_main_m": m, "refuge_within_400m": within}


def area(order, name, tier, heat, third, flats=0, calls=0, left=0, blocks=(), rank=1, region="CENTRAL REGION"):
    return {"area_order": order, "planning_area": name, "region": region, "heat_level": heat, "third": third,
            "tier": tier, "tier_rank": rank, "tier_sentence": f"{tier}: forecast {heat} heat, {third} third for vulnerability",
            "reason": "many 1–2 room rental flats; many residents aged 75+",
            "actions": "Phone checks before noon on flagged seniors in the priority blocks." if tier == "High" else
                       "The AAC broadcasts a hydration and heat advisory." if tier == "Medium" else "Routine.",
            "actions_status": "proposal, not yet reviewed by a practitioner", "rental_1_2_room": flats,
            "calls_allocated": calls, "calls_left": left, "blocks": list(blocks)}


# 24 Oct at 800 calls, as the warehouse returned it (Toa Payoh's three blocks), plus a Medium, a Low and two Not rated
ROWS_24 = [
    area(1, "TOA PAYOH", "High", "High", "upper", 3835, 800, 0,
         [block(1, "208A", "WOODLEIGH LINK", 312, 312),
          block(2, "170", "LOR 1 TOA PAYOH", 308, 308, refuge="Care Corner AAC (TP170)", m=0.0, within=True),
          block(3, "5", "LOR 7 TOA PAYOH", 258, 180, partial=True, refuge="Care Corner AAC (TP5)", m=0.0, within=True)]),
    area(2, "BISHAN", "Medium", "High", "lower", 900, 0, 0),
    area(3, "MARINE PARADE", "Low", "Moderate", "lower", 400, 0, 0),
    area(4, "SOUTHERN ISLANDS", "Not rated", "High", None, rank=1),
    area(5, "SUNGEI KADUT", "Not rated", "High", None, rank=2, region="NORTH REGION"),
]

# 23 Oct: no rated High area; Southern Islands has High heat but is Not rated
ROWS_23 = [
    area(1, "TOA PAYOH", "Medium", "Moderate", "upper", 3835, 500, 0,
         [block(1, "208A", "WOODLEIGH LINK", 312, 312), block(2, "170", "LOR 1 TOA PAYOH", 308, 188, partial=True)]),
    area(2, "MARINE PARADE", "Low", "Moderate", "lower", 400, 0, 0),
    area(3, "SOUTHERN ISLANDS", "Not rated", "High", None),
]

# the North-East on 24 Oct (the demo request "Only 8 volunteers tomorrow, North-East only"): no High tier there, while
# Toa Payoh (Central) is High on the dashboard
ROWS_NE = [
    area(1, "SENGKANG", "Medium", "Moderate", "upper", 1687, 200, 0,
         [block(1, "182", "RIVERVALE CRES", 438, 200, partial=True, refuge="Rivervale CC", m=120.0, within=True)],
         region="NORTH-EAST REGION"),
    area(2, "PUNGGOL", "Low", "Moderate", "lower", 900, 0, 0, region="NORTH-EAST REGION"),
]

# the North: no High tier, and Sungei Kadut has High heat but is Not rated
ROWS_N = [area(1, "WOODLANDS", "Medium", "Moderate", "middle", 2000, 0, 0, region="NORTH REGION"),
          area(2, "SUNGEI KADUT", "Not rated", "High", None, region="NORTH REGION")]

FORECAST = {"run_id": "647995027381846", "n_runs": 1, "scored_at": "2026-10-23T16:49:49.473Z",
            "scored_at_sgt": "24 Oct 2026, 00:49", "forecast_missing": False, "n_areas": 41}


class FakeWarehouse:
    """Answers the plan's statements from fixtures and records every (sql, params)."""

    def __init__(self, rows=ROWS_24, fail=None):
        self.rows, self.fail, self.statements, self.approvals = rows, fail, [], {}

    def query(self, sql, params=None, timeout_s=None):
        self.statements.append((sql, params))
        if self.fail and re.search(self.fail, sql):
            raise RuntimeError("PERMISSION_DENIED: fake")
        if ".get_priority_areas(" in sql:
            return copy.deepcopy(self.rows)
        if ".find_refuges(" in sql:
            return [{"refuge_rank": 2, "refuge_name": "B"}, {"refuge_rank": 1, "refuge_name": "A"}]
        if sql.startswith("MERGE INTO"):
            aid = params["approval_id"][0]
            self.approvals.setdefault(aid, params)
            return []
        if "FROM coolcheck.gold.pending_approval WHERE approval_id" in sql:
            aid = params["id"][0]
            return ([{"approval_id": aid, "approved_sgt": "24 Oct 2026, 18:00:00", "status": "approved_not_sent"}]
                    if aid in self.approvals else [])
        raise AssertionError(f"unexpected statement: {sql}")
