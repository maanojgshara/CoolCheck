"""Fake draft_plan results for the grader's tests: tool rows shaped like the three functions' results (no workspace)."""
import copy

FOOTER = ("Draft only: nothing has been sent. A person approves; the Active Ageing Centre matches the blocks against its "
          "own client list (CoolCheck holds no personal data).")


def block(priority, blk, street, flats, calls, partial=False, refuge="Bidadari CC", m=448.34, within=False):
    return {"priority": priority, "blk_no": blk, "street": street, "rental_1_2_room": flats, "calls_allocated": calls,
            "partial": partial, "refuge_main_name": refuge, "refuge_main_m": m, "refuge_within_400m": within}


def area(order, name, tier, heat, flats=0, calls=0, left=0, blocks=(), region="CENTRAL REGION"):
    return {"area_order": order, "planning_area": name, "region": region, "heat_level": heat, "third": "upper",
            "tier": tier, "tier_rank": 1, "tier_sentence": f"{tier}: forecast {heat} heat",
            "reason": "many 1–2 room rental flats; many residents aged 75+", "actions": "Phone checks before noon.",
            "actions_status": "proposal", "rental_1_2_room": flats, "calls_allocated": calls, "calls_left": left,
            "blocks": list(blocks)}


EAST_200 = [area(1, "BEDOK", "Medium", "Moderate", 2100, 200, 0,
                 [block(1, "58", "NEW UPP CHANGI RD", 240, 200, partial=True, refuge="Bedok CC", m=212.7, within=True)],
                 region="EAST REGION"),
            area(2, "TAMPINES", "Medium", "Moderate", 900, 0, 0, region="EAST REGION")]

ISLAND_800 = [area(1, "TOA PAYOH", "High", "High", 3835, 800, 0,
                   [block(1, "208A", "WOODLEIGH LINK", 312, 312), block(2, "170", "LOR 1 TOA PAYOH", 308, 308),
                    block(3, "5", "LOR 7 TOA PAYOH", 258, 180, partial=True)]),
              area(2, "BISHAN", "Medium", "High", 900, 0, 0),
              area(3, "SOUTHERN ISLANDS", "Not rated", "High")]

REFUGES = [{"refuge_rank": r, "blk_no": "208A", "street": "WOODLEIGH LINK", "planning_area": "TOA PAYOH",
            "refuge_name": n, "refuge_type": "Community Club", "address": "x", "postal_code": "000000",
            "refuge_planning_area": "TOA PAYOH", "distance_m": d, "within_400m": d <= 400}
           for r, n, d in ((1, "Bidadari CC", 448.34), (2, "Potong Pasir CC", 912.05))]

WHAT_IF = [{"planning_area": "OUTRAM", "is_site_area": True, "site_blk_no": "3", "site_street": "JLN KUKOH",
            "hdb_dwelling_units": 5000, "du_within_400m_before": 3000, "du_within_400m_after": 6001,
            "share_within_400m_before": 0.6, "share_within_400m_after": 0.98, "rental_flats_beyond_400m_before": 2190,
            "rental_flats_beyond_400m_after": 0, "blocks_newly_within": 16, "newly_within": []}]


def call(name, arguments, rows=(), error=None, llm_arguments=None):
    return {"name": name, "arguments": arguments, "rows": copy.deepcopy(list(rows)), "error": error,
            "llm_arguments": llm_arguments, "elapsed_ms": 900}


def gpa(date="2026-10-24", capacity=800, region=None, rows=ISLAND_800, **kw):
    return call("get_priority_areas", {"target_date": date, "call_capacity": capacity, "region": region}, rows, **kw)


def result(summary, calls, source="agent", basis="form: 800 calls (placeholder)", fallback_reason=None,
           draft_extra="", request_text=None):
    return {"summary_text": summary, "draft_text": f"CoolCheck draft.\n\nSummary: {summary}\n{draft_extra}\n\n{FOOTER}",
            "source": source, "fallback_reason": fallback_reason, "tool_calls": calls, "capacity_basis": basis,
            "checks": {"numbers": "ok"}, "trace_id": "tr-1", "model": "llama", "rounds": 2, "elapsed_s": 4.2,
            "request_text": request_text}
