-- find_refuges: the agent's second tool (Guide D13 and C11; docs/design/agent_tools.md).
-- The 5 nearest refuges of the main set (silver.refuge_points.in_main: Community Clubs with their temporary offices, and
-- the partial Active Ageing Centre list) to a confirmed HDB block, in any planning area, by the straight line
-- sqrt(dx^2 + dy^2) in SVY21 metres from the stored x_svy21 / y_svy21 (coolcheck.access); ties by refuge_id. The block is
-- looked up ignoring case, spaces, punctuation and a leading Blk or Block; an unknown or unconfirmed block gives no rows.
-- Placeholders, filled by coolcheck.agent_tools.function_sql: function, block_access, refuge_points, and temporary
-- (empty, or TEMPORARY in the tests). Python twin: coolcheck.agent_tools.find_refuges.
CREATE OR REPLACE ${temporary}FUNCTION ${function}(
  blk_no STRING COMMENT 'HDB block number, e.g. 52 or 101A; case, spaces and a leading Blk or Block are ignored.',
  street STRING COMMENT 'Street name as HDB writes it, with its abbreviations (AVE, ST, RD, DR, CRES, CTRL, CL, NTH, STH, BT, JLN, LOR, UPP), e.g. ANG MO KIO AVE 10; case, extra spaces and punctuation are ignored.'
)
RETURNS TABLE (
  refuge_rank INT COMMENT '1 = the nearest refuge.',
  blk_no STRING COMMENT 'The block number as HDB writes it.',
  street STRING COMMENT 'The street as HDB writes it.',
  planning_area STRING COMMENT 'Master Plan 2025 planning area of the block.',
  refuge_name STRING COMMENT 'Name of the refuge as published.',
  refuge_type STRING COMMENT 'Community Club; Community Club (temporary office); or Active Ageing Centre (partial list): the open AAC list covers 93 of about 223 centres, so a nearer AAC may be missing.',
  address STRING COMMENT 'Address of the refuge as published.',
  postal_code STRING COMMENT '6-digit postal code of the refuge.',
  refuge_planning_area STRING COMMENT 'Master Plan 2025 planning area of the refuge; it may differ from the block.',
  distance_m DOUBLE COMMENT 'Straight-line distance in metres in SVY21 (EPSG:3414) from the stored coordinates, unrounded; not a walking distance.',
  within_400m BOOLEAN COMMENT 'distance_m is at most 400 m, the walking distance used for cooling access.'
)
COMMENT 'The 5 nearest cooling refuges to an HDB block: Community Clubs (temporary offices flagged) and Active Ageing Centres (a partial list, 93 of about 223), in any planning area, with the straight-line distance in metres from the stored SVY21 coordinates, not a walking distance. No rows if the block is not found or its coordinate is not confirmed. No personal data.'
RETURN
WITH args AS (
  SELECT regexp_replace(regexp_replace(upper(blk_no), '^\\s*(BLK|BLOCK)[.\\s]*', ''), '[^A-Z0-9]', '') AS bk,
         trim(regexp_replace(regexp_replace(upper(street), '[^A-Z0-9\\s]', ''), '\\s+', ' ')) AS sk
),
blk AS (
  SELECT b.blk_no, b.street, b.planning_area, b.x_svy21, b.y_svy21
  FROM ${block_access} b CROSS JOIN args a
  WHERE b.confirmed
    AND regexp_replace(regexp_replace(upper(b.blk_no), '^\\s*(BLK|BLOCK)[.\\s]*', ''), '[^A-Z0-9]', '') = a.bk
    AND trim(regexp_replace(regexp_replace(upper(b.street), '[^A-Z0-9\\s]', ''), '\\s+', ' ')) = a.sk
),
ranked AS (
  SELECT k.blk_no, k.street, k.planning_area, r.name AS refuge_name, r.layer, r.status, r.address, r.postal_code,
         r.planning_area AS refuge_planning_area,
         sqrt(pow(k.x_svy21 - r.x_svy21, 2) + pow(k.y_svy21 - r.y_svy21, 2)) AS distance_m,
         row_number() OVER (PARTITION BY k.blk_no, k.street
                            ORDER BY sqrt(pow(k.x_svy21 - r.x_svy21, 2) + pow(k.y_svy21 - r.y_svy21, 2)),
                                     r.refuge_id) AS refuge_rank
  FROM blk k CROSS JOIN ${refuge_points} r
  WHERE r.in_main
)
SELECT CAST(refuge_rank AS INT) AS refuge_rank, blk_no, street, planning_area, refuge_name,
       CASE WHEN layer = 'aac_partial' THEN 'Active Ageing Centre (partial list)'
            WHEN layer = 'community_club' AND status = 'temp_office' THEN 'Community Club (temporary office)'
            WHEN layer = 'community_club' THEN 'Community Club'
            ELSE layer END AS refuge_type,
       address, postal_code, refuge_planning_area, distance_m, distance_m <= 400.0D AS within_400m
FROM ranked
WHERE refuge_rank <= 5
ORDER BY refuge_rank
