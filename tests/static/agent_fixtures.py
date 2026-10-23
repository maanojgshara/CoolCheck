"""A synthetic briefing for the get_priority_areas tests (local and SQL): rows of gold.area_heat_risk on D with every tier,
one row on another date, and gold.block_vulnerability rows with a block that has no 1-2 room rental flat."""
import datetime as dt

D = dt.date(2026, 10, 24)
RISK_COLUMNS = ["target_date", "planning_area", "region", "heat_level", "third", "tier", "tier_rank", "tier_sentence",
                "reason", "actions", "actions_status"]
RISK_SCHEMA = ("target_date DATE, planning_area STRING, region STRING, heat_level STRING, third STRING, tier STRING, "
               "tier_rank INT, tier_sentence STRING, reason STRING, actions STRING, actions_status STRING")
BLOCK_COLUMNS = ["planning_area", "priority", "blk_no", "street", "rental_1_2_room", "refuge_main_name", "refuge_main_m",
                 "refuge_within_400m"]
BLOCK_SCHEMA = ("planning_area STRING, priority INT, blk_no STRING, street STRING, rental_1_2_room BIGINT, "
                "refuge_main_name STRING, refuge_main_m DOUBLE, refuge_within_400m BOOLEAN")


def area(name, tier, rank, region="EAST REGION", heat="High", third="upper", date=D):
    return {"target_date": date, "planning_area": name, "region": region, "heat_level": heat, "third": third, "tier": tier,
            "tier_rank": rank, "tier_sentence": f"{tier}: {name}", "reason": f"reason {name}", "actions": f"do {tier}",
            "actions_status": "proposal"}


def block(name, priority, rental):
    return {"planning_area": name, "priority": priority, "blk_no": f"{priority}", "street": f"{name} ST",
            "rental_1_2_room": rental, "refuge_main_name": "R", "refuge_main_m": 500.0, "refuge_within_400m": False}


RISK = [area("A3", "Medium", 1, heat="Moderate"), area("A1", "High", 1), area("A2", "High", 2, region="WEST REGION"),
        area("A4", "Low", 1, heat="Low"), area("A5", "Not rated", 1, third=None), area("A6", "No forecast", 1, heat=None),
        area("A1", "Low", 1, heat="Low", date=D + dt.timedelta(days=1))]
BLOCKS = [block("A1", 1, 100), block("A1", 2, 0), block("A1", 3, 50), block("A2", 1, 80), block("A3", 1, 30),
          block("A3", 2, 30), block("A4", 1, 500), block("A6", 1, 40)]
