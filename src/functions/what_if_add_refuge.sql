-- what_if_add_refuge: the agent's third tool (Guide D13 and C11; docs/design/agent_tools.md).
-- A refuge added at a confirmed HDB block (the site). For the planning area of the site, and any other area with a block
-- newly within 400 m, the confirmed blocks' dwelling units within 400 m of a refuge before and after, the 1-2 room rental
-- flats beyond 400 m before and after, and the blocks newly within 400 m. Before: each block's distance to the nearest
-- refuge of the main set, recomputed from the stored x_svy21 / y_svy21 with sqrt(dx^2 + dy^2), unrounded, as
-- silver.area_access was built (coolcheck.access); after: the lesser of that and the distance to the site. 400 m counts
-- as within. The site is looked up as in find_refuges: case, spaces, punctuation and a leading Blk or Block ignored, and on
-- both sides the street's long forms read as HDB's abbreviations (the map in words, = coolcheck.agent_tools.STREET_WORDS),
-- so Yishun Street 31 finds YISHUN ST 31. An unknown or unconfirmed block gives no rows.
-- Placeholders, filled by coolcheck.agent_tools.function_sql: function, block_access, refuge_points, and temporary
-- (empty, or TEMPORARY in the tests). Python twin: coolcheck.agent_tools.what_if_add_refuge.
CREATE OR REPLACE ${temporary}FUNCTION ${function}(
  blk_no STRING COMMENT 'Block number of the site, an existing HDB block, e.g. 52 or 101A; case, spaces and a leading Blk or Block are ignored.',
  street STRING COMMENT 'Street of the site as people write it or as HDB abbreviates it, e.g. Yishun Street 31 or YISHUN ST 31, Ang Mo Kio Avenue 10 or ANG MO KIO AVE 10; case, extra spaces and punctuation are ignored, and long forms such as Street, Road, Avenue, Drive, Jalan, Lorong, Bukit, Upper, North and Central are read as HDB''s abbreviations.'
)
RETURNS TABLE (
  planning_area STRING COMMENT 'Master Plan 2025 planning area: the area of the site first, then any other area with a block newly within 400 m.',
  is_site_area BOOLEAN COMMENT 'True for the planning area of the site.',
  site_blk_no STRING COMMENT 'Block number of the site as HDB writes it.',
  site_street STRING COMMENT 'Street of the site as HDB writes it.',
  hdb_dwelling_units BIGINT COMMENT 'HDB dwelling units of the confirmed blocks in the area, as in silver.area_access.',
  du_within_400m_before BIGINT COMMENT 'Of these, the dwelling units within 400 m of a refuge of the main set today.',
  du_within_400m_after BIGINT COMMENT 'The same with the new refuge at the site.',
  share_within_400m_before DOUBLE COMMENT 'du_within_400m_before / hdb_dwelling_units; equals the main-set share in silver.area_access.',
  share_within_400m_after DOUBLE COMMENT 'du_within_400m_after / hdb_dwelling_units.',
  rental_flats_beyond_400m_before BIGINT COMMENT '1-room plus 2-room rental flats in the confirmed blocks of the area beyond 400 m of a refuge today.',
  rental_flats_beyond_400m_after BIGINT COMMENT 'The same with the new refuge at the site.',
  blocks_newly_within BIGINT COMMENT 'Blocks of the area beyond 400 m of a refuge today and within 400 m of the site.',
  newly_within ARRAY<STRUCT<blk_no: STRING, street: STRING, total_dwelling_units: BIGINT, rental_1_2_room: BIGINT, distance_before_m: DOUBLE, distance_after_m: DOUBLE>> COMMENT 'Those blocks, nearest the site first: block number, street, dwelling units, 1-2 room rental flats, and the straight-line distance in m (unrounded) to the nearest refuge today and with the new one.'
)
COMMENT 'What if a cooling refuge opened at an existing HDB block (for example at its void deck): for the planning area of the block, and any other area that gains, the HDB dwelling units within 400 m of a refuge and their share before and after, the 1-2 room rental flats beyond 400 m before and after, and the blocks newly within 400 m. Straight-line distances in metres from the stored SVY21 coordinates, not walking distances; refuges are the main set (Community Clubs and the partial Active Ageing Centre list); confirmed blocks only, as in silver.area_access. No rows if the block is not found or its coordinate is not confirmed. No personal data.'
RETURN
WITH words AS (
  SELECT map('AVENUE', 'AVE', 'BUKIT', 'BT', 'CENTRAL', 'CTRL', 'CLOSE', 'CL', 'COMMONWEALTH', 'CWEALTH',
             'CRESCENT', 'CRES', 'DRIVE', 'DR', 'GARDEN', 'GDN', 'GARDENS', 'GDNS', 'HEIGHTS', 'HTS', 'JALAN', 'JLN',
             'KAMPONG', 'KG', 'KAMPUNG', 'KG', 'LORONG', 'LOR', 'MARKET', 'MKT', 'NORTH', 'NTH', 'PARK', 'PK',
             'PLACE', 'PL', 'ROAD', 'RD', 'SAINT', 'ST', 'SOUTH', 'STH', 'SQUARE', 'SQ', 'STREET', 'ST',
             'TANJONG', 'TG', 'TANJUNG', 'TG', 'TERRACE', 'TER', 'UPPER', 'UPP') AS m
),
args AS (
  SELECT d.m,
         regexp_replace(regexp_replace(upper(blk_no), '^\\s*(BLK|BLOCK)[.\\s]*', ''), '[^A-Z0-9]', '') AS bk,
         array_join(transform(split(trim(regexp_replace(regexp_replace(upper(street), '[^A-Z0-9\\s]', ''), '\\s+', ' ')), ' '),
                              w -> coalesce(try_element_at(d.m, w), w)), ' ') AS sk
  FROM words d
),
site AS (
  SELECT b.blk_no AS site_blk_no, b.street AS site_street, b.planning_area AS site_area, b.x_svy21 AS sx, b.y_svy21 AS sy
  FROM ${block_access} b CROSS JOIN args a
  WHERE b.confirmed
    AND regexp_replace(regexp_replace(upper(b.blk_no), '^\\s*(BLK|BLOCK)[.\\s]*', ''), '[^A-Z0-9]', '') = a.bk
    AND array_join(transform(split(trim(regexp_replace(regexp_replace(upper(b.street), '[^A-Z0-9\\s]', ''), '\\s+', ' ')), ' '),
                             w -> coalesce(try_element_at(a.m, w), w)), ' ') = a.sk
),
-- the areas that can change: the area of the site, and the areas of the confirmed blocks within 400 m of it
areas AS (
  SELECT s.site_area AS planning_area FROM site s
  UNION
  SELECT b.planning_area FROM ${block_access} b CROSS JOIN site s
  WHERE b.confirmed AND sqrt(pow(b.x_svy21 - s.sx, 2) + pow(b.y_svy21 - s.sy, 2)) <= 400.0D
),
blks AS (
  SELECT b.blk_no, b.street, b.planning_area, b.total_dwelling_units, b.`1room_rental` + b.`2room_rental` AS rental_1_2_room,
         b.x_svy21, b.y_svy21, sqrt(pow(b.x_svy21 - s.sx, 2) + pow(b.y_svy21 - s.sy, 2)) AS d_site
  FROM ${block_access} b JOIN areas a ON a.planning_area = b.planning_area CROSS JOIN site s
  WHERE b.confirmed
),
dist AS (
  SELECT k.blk_no, k.street, k.planning_area, k.total_dwelling_units, k.rental_1_2_room, k.d_site,
         min(sqrt(pow(k.x_svy21 - r.x_svy21, 2) + pow(k.y_svy21 - r.y_svy21, 2))) AS d_before
  FROM blks k CROSS JOIN ${refuge_points} r
  WHERE r.in_main
  GROUP BY k.blk_no, k.street, k.planning_area, k.total_dwelling_units, k.rental_1_2_room, k.d_site
),
flagged AS (
  SELECT dist.*, least(d_before, d_site) AS d_after,
         d_before > 400.0D AND least(d_before, d_site) <= 400.0D AS newly
  FROM dist
),
per_area AS (
  SELECT planning_area,
         sum(total_dwelling_units) AS du,
         sum(CASE WHEN d_before <= 400.0D THEN total_dwelling_units ELSE 0 END) AS du_before,
         sum(CASE WHEN d_after <= 400.0D THEN total_dwelling_units ELSE 0 END) AS du_after,
         sum(CASE WHEN d_before > 400.0D THEN rental_1_2_room ELSE 0 END) AS rental_before,
         sum(CASE WHEN d_after > 400.0D THEN rental_1_2_room ELSE 0 END) AS rental_after,
         count_if(newly) AS n_new,
         transform(array_sort(collect_list(CASE WHEN newly THEN named_struct(
           'k', d_after, 'b', blk_no, 's', street,
           'v', named_struct('blk_no', blk_no, 'street', street, 'total_dwelling_units', total_dwelling_units,
                             'rental_1_2_room', rental_1_2_room, 'distance_before_m', d_before,
                             'distance_after_m', d_after)) END)), x -> x.v) AS newly_within
  FROM flagged GROUP BY planning_area
)
SELECT p.planning_area, p.planning_area = s.site_area AS is_site_area, s.site_blk_no, s.site_street,
       p.du AS hdb_dwelling_units, p.du_before AS du_within_400m_before, p.du_after AS du_within_400m_after,
       CAST(p.du_before AS DOUBLE) / CAST(p.du AS DOUBLE) AS share_within_400m_before,
       CAST(p.du_after AS DOUBLE) / CAST(p.du AS DOUBLE) AS share_within_400m_after,
       p.rental_before AS rental_flats_beyond_400m_before, p.rental_after AS rental_flats_beyond_400m_after,
       p.n_new AS blocks_newly_within, p.newly_within
FROM per_area p CROSS JOIN site s
WHERE p.planning_area = s.site_area OR p.n_new > 0
ORDER BY is_site_area DESC, planning_area
