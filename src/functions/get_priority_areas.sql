-- get_priority_areas: the agent's first tool (Guide D13 and C11; docs/design/agent_tools.md).
-- The date's areas from gold.area_heat_risk in tier order (High, Medium, Low, Not rated, No forecast), then tier_rank,
-- each with its tier sentence, reason and actions; and the call budget filled in code: High- and Medium-tier areas only,
-- in that order, block by block in gold.block_vulnerability's priority. One call is assumed per 1-2 room rental flat in
-- a priority block (a block with at least one); the block that crosses the budget gets the remainder (partial) and
-- nothing after it is filled. Reads only the two gold views; returns no probability and no score.
-- Placeholders, filled by coolcheck.agent_tools.function_sql: function, area_heat_risk, block_vulnerability, and
-- temporary (empty, or TEMPORARY in the tests). Python twin: coolcheck.agent_tools.priority_areas.
CREATE OR REPLACE ${temporary}FUNCTION ${function}(
  target_date DATE COMMENT 'The date the heat forecast is for (the briefing date), as a DATE, e.g. 2026-10-24.',
  call_capacity INT COMMENT 'Calls the team can make for the date (volunteers times calls per volunteer, an assumption the app shows). One call is assumed per 1-2 room rental flat in a priority block. NULL, 0 or less gives the areas without blocks.',
  region STRING DEFAULT NULL COMMENT 'Optional region: CENTRAL, EAST, NORTH, NORTH-EAST or WEST; case, spaces, hyphens and the word REGION are ignored. NULL, empty or ALL for the whole island; an unknown region gives no rows.'
)
RETURNS TABLE (
  area_order INT COMMENT 'Order of the area in the briefing, 1 first: tier (High, Medium, Low, Not rated, No forecast), then tier_rank, then name.',
  planning_area STRING COMMENT 'Master Plan 2025 planning area.',
  region STRING COMMENT 'Master Plan 2025 region.',
  heat_level STRING COMMENT 'Forecast heat stress for the date in the NEA categories Low, Moderate or High, per planning area; null without a forecast.',
  third STRING COMMENT 'Vulnerability third among the rated areas: upper, middle or lower; null if not rated.',
  tier STRING COMMENT 'Area risk tier: High, Medium or Low (heat level crossed with the third); Not rated; No forecast.',
  tier_rank INT COMMENT 'Order within the tier on the date, 1 first.',
  tier_sentence STRING COMMENT 'The tier in one sentence, e.g. High: forecast High heat, upper third for vulnerability.',
  reason STRING COMMENT 'Why the area is vulnerable, in plain words (its two largest components); null if not rated.',
  actions STRING COMMENT 'The actions for the tier (gold.tier_actions).',
  actions_status STRING COMMENT 'Review status of the actions: a proposal, not yet reviewed by a practitioner.',
  rental_1_2_room BIGINT COMMENT '1-room plus 2-room rental flats in the HDB blocks of the area: the calls needed to cover the whole area under the one-call-per-flat assumption; 0 if not rated.',
  calls_allocated BIGINT COMMENT 'Calls given to blocks of the area within the budget.',
  calls_left BIGINT COMMENT 'Calls of the budget still unallocated after this area, in area_order.',
  blocks ARRAY<STRUCT<priority: INT, blk_no: STRING, street: STRING, rental_1_2_room: BIGINT, calls_allocated: BIGINT, partial: BOOLEAN, refuge_main_name: STRING, refuge_main_m: DOUBLE, refuge_within_400m: BOOLEAN>> COMMENT 'Blocks of the area given calls, in priority order: priority (1 = most 1-2 room rental flats), blk_no, street, rental_1_2_room, calls_allocated, partial (fewer calls than flats: the budget ran out in this block), the nearest refuge of the main set and its straight-line distance in m, and whether it is within 400 m. Vulnerability only, never heat. Empty if none.'
)
COMMENT 'Priority planning areas for heat outreach on a date: the areas of gold.area_heat_risk in tier order (High, Medium, Low, Not rated, No forecast), then by rank within the tier, each with its tier sentence, vulnerability reason and tier actions (a proposal, not yet reviewed by a practitioner). The call budget is filled in code, not by a model: High- and Medium-tier areas only, in that order, block by block from gold.block_vulnerability (most 1-2 room rental flats first); the block that crosses the budget gets the remainder and is marked partial. Assumption: one call per 1-2 room rental flat in a priority block. CoolCheck holds no personal data: the Active Ageing Centre matches each block against its own client list. Heat is forecast per planning area; blocks rank vulnerability, never heat.'
RETURN
WITH args AS (
  SELECT target_date AS d,
         greatest(coalesce(call_capacity, 0), 0) AS cap,
         regexp_replace(regexp_replace(upper(region), '[^A-Z]', ''), 'REGIONS?\\z', '') AS rk
),
areas AS (
  SELECT r.planning_area, r.region, r.heat_level, r.third, r.tier, r.tier_rank, r.tier_sentence, r.reason, r.actions,
         r.actions_status,
         row_number() OVER (ORDER BY CASE r.tier WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3
                                                 WHEN 'Not rated' THEN 4 ELSE 5 END,
                                     r.tier_rank, r.planning_area) AS area_order
  FROM ${area_heat_risk} r CROSS JOIN args a
  WHERE r.target_date = a.d
    AND (a.rk IS NULL OR a.rk IN ('', 'ALL')
         OR regexp_replace(regexp_replace(upper(r.region), '[^A-Z]', ''), 'REGIONS?\\z', '') = a.rk)
),
-- blocks that can take calls: at least one 1-2 room rental flat, in a High- or Medium-tier area; briefing order
eligible AS (
  SELECT o.area_order, v.planning_area, v.priority, v.blk_no, v.street, v.rental_1_2_room, v.refuge_main_name,
         v.refuge_main_m, v.refuge_within_400m,
         sum(v.rental_1_2_room) OVER (ORDER BY o.area_order, v.priority
                                      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) - v.rental_1_2_room AS needed_before
  FROM areas o JOIN ${block_vulnerability} v ON v.planning_area = o.planning_area
  WHERE o.tier IN ('High', 'Medium') AND v.rental_1_2_room > 0
),
filled AS (
  SELECT e.*, greatest(least(e.rental_1_2_room, a.cap - e.needed_before), 0) AS calls
  FROM eligible e CROSS JOIN args a
),
per_area AS (
  SELECT planning_area, sum(calls) AS calls_allocated,
         array_sort(collect_list(CASE WHEN calls > 0 THEN named_struct(
           'priority', priority, 'blk_no', blk_no, 'street', street, 'rental_1_2_room', rental_1_2_room,
           'calls_allocated', calls, 'partial', calls < rental_1_2_room, 'refuge_main_name', refuge_main_name,
           'refuge_main_m', refuge_main_m, 'refuge_within_400m', refuge_within_400m) END)) AS blocks
  FROM filled GROUP BY planning_area
),
area_rental AS (
  SELECT planning_area, sum(rental_1_2_room) AS rental_1_2_room FROM ${block_vulnerability} GROUP BY planning_area
)
SELECT CAST(o.area_order AS INT) AS area_order, o.planning_area, o.region, o.heat_level, o.third, o.tier,
       CAST(o.tier_rank AS INT) AS tier_rank, o.tier_sentence, o.reason, o.actions, o.actions_status,
       coalesce(t.rental_1_2_room, 0) AS rental_1_2_room,
       coalesce(p.calls_allocated, 0) AS calls_allocated,
       a.cap - sum(coalesce(p.calls_allocated, 0)) OVER (ORDER BY o.area_order
                                                         ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS calls_left,
       coalesce(p.blocks, array()) AS blocks
FROM areas o CROSS JOIN args a
LEFT JOIN per_area p ON p.planning_area = o.planning_area
LEFT JOIN area_rental t ON t.planning_area = o.planning_area
ORDER BY area_order
