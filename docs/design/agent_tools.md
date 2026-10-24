# The agent's three tools as Unity Catalog SQL functions: design note

Written 23 Oct 2026 for window D. It turns Guide D13 and C11 into three SQL functions that the agent (window B, Saturday) and the briefing dashboard can call. **Status: approved 23 Oct 2026** with the four recommended options: one call per 1–2 room rental flat, High- and Medium-tier areas only, the last block partly filled; the what-if site is an existing HDB block; `get_priority_areas` returns one row per area with its blocks as an array; `find_refuges` returns the 5 nearest refuges of the main set.

## Where

- SQL: `src/functions/get_priority_areas.sql`, `find_refuges.sql`, `what_if_add_refuge.sql`, one `CREATE OR REPLACE FUNCTION` each. Placeholders for the function name and the tables it reads are filled by `coolcheck.agent_tools.function_sql`, so the tests run the same text as TEMPORARY functions over temp views.
- Created in `<catalog>.gold` by `scripts/static/create_agent_functions.py` (`--catalog`, `--profile`, default `coolcheck`), only on the user's word. `get_priority_areas` is skipped while `gold.area_heat_risk` does not exist.
- Python twin of each rule: `src/coolcheck/agent_tools.py`. Tests: `tests/static/test_agent_tools.py` (local) and `tests/static/test_agent_tools_sql.py` (Databricks Connect).
- The function comment is the tool description the agent sees; every parameter and result column has a comment.

## What they read, and what they never return

- `get_priority_areas` reads `gold.area_heat_risk` and `gold.block_vulnerability`; the other two read `silver.block_access` and `silver.refuge_points`.
- None reads `gold.heat_forecast`. No result column holds P(High), the score, `model_version`, `run_id`, `cutoff_ts`, `scored_at` or `forecast_missing` (a test checks every result schema, nested fields included).
- Heat is per planning area; blocks rank vulnerability, never heat. No personal data.

## get_priority_areas(target_date DATE, call_capacity INT, region STRING DEFAULT NULL)

- **Areas:** the rows of `area_heat_risk` for the date, in tier order (High, Medium, Low, Not rated, No forecast), then `tier_rank`, then name: `area_order` 1, 2, ….
- **Region:** NULL, empty or ALL is the whole island. Otherwise matched ignoring case, spaces, hyphens and a trailing REGION, so `north-east` finds NORTH-EAST REGION; an unknown region gives no rows.
- **One call = one 1–2 room rental flat in a priority block** (a block with at least one), an assumption stated in the comments. CoolCheck holds no personal data; the Active Ageing Centre matches each block against its own client list, so the count is an upper bound per block. 357 blocks hold all 61,748 such flats, a median of 176 per block (`block_access.csv`), so a few hundred calls covers one or two blocks.
- **Fill, in code:** only High- and Medium-tier areas take calls (their actions name the priority blocks; Low is "Routine"; Not rated has no blocks; No forecast has no heat level). Blocks are taken in `area_order`, then block `priority`. The block that crosses the budget gets the remainder and is marked `partial`; nothing after it is filled, so the order stays strict (D13: optimal when capacity is counted in calls). NULL, 0 or a negative capacity gives no blocks.
- **Result, one row per area:** `area_order`, `planning_area`, `region`, `heat_level`, `third`, `tier`, `tier_rank`, `tier_sentence`, `reason`, `actions`, `actions_status`, `rental_1_2_room` (the area's total: the calls to cover it all), `calls_allocated`, `calls_left` (after this area), and `blocks`: an array of {`priority`, `blk_no`, `street`, `rental_1_2_room`, `calls_allocated`, `partial`, `refuge_main_name`, `refuge_main_m`, `refuge_within_400m`} for the blocks given calls. A dashboard explodes the array for a block table.

## find_refuges(blk_no STRING, street STRING)

- **Lookup:** case, extra spaces, punctuation and a leading Blk or Block are ignored (`blk 7`, `st george's lane` finds 7 ST. GEORGE'S LANE). On both sides, the street's long forms are read as HDB's abbreviations (`STREET_WORDS`, written as a map in both SQL files): 27 long forms to the 24 abbreviations that occur in HDB's street names, for example Jalan to JLN, Lorong to LOR, Street and Saint to ST, Avenue to AVE, Bukit to BT, Upper to UPP. So `Jalan Kukoh` finds 3 JLN KUKOH. None of the long forms occurs in HDB's streets (tested), so HDB's own spelling keys as before. The 10,817 blocks keep distinct keys (tested). Word order is not changed: `Toa Payoh Lorong 1` does not find LOR 1 TOA PAYOH. (Added 24 Oct after the agent evaluation: Llama passed `JALAN KUKOH` and `Yishun Street 31` in all six attempts, `docs/checks/agent_eval.md` finding 2.) Confirmed blocks only (`docs/checks/geocode_hdb.md`); an unknown or unconfirmed block gives no rows.
- **Rule:** the 5 nearest refuges with `in_main` (Community Clubs, their temporary offices flagged, and the Active Ageing Centres, a partial list of 93 of about 223), in any planning area, by `sqrt(pow(dx, 2) + pow(dy, 2))` on the stored `x_svy21` / `y_svy21`; ties by `refuge_id`.
- **Result:** `refuge_rank`, the block's `blk_no`, `street` and `planning_area` as HDB writes them, `refuge_name`, `refuge_type` (Community Club; Community Club (temporary office); Active Ageing Centre (partial list)), `address`, `postal_code`, `refuge_planning_area`, `distance_m` (unrounded), `within_400m`.

## what_if_add_refuge(blk_no STRING, street STRING)

- **Site:** a confirmed HDB block (for example its void deck), looked up as in `find_refuges`. `ST_Point` and `ST_Transform` (WGS84 to EPSG:3414) exist on the SQL warehouse (DBSQL 2026.42) and on serverless, and equal pyproj to 7e-12 m (checked 23 Oct), but a block was chosen: its planning area comes from `block_access` without a boundary table, the agent cannot invent coordinates, and a block list is an easy dashboard parameter.
- **Rule:** each confirmed block's distance to its nearest main-set refuge, recomputed from the stored x/y and unrounded, as `silver.area_access` was built; after = the lesser of that and the distance to the site. Newly within: beyond 400 m before and at most 400 m after (400 m counts as within).
- **Result, one row for the site's area plus one for any other area with a newly covered block:** `planning_area`, `is_site_area`, `site_blk_no`, `site_street`, `hdb_dwelling_units`, `du_within_400m_before` / `_after`, `share_within_400m_before` / `_after`, `rental_flats_beyond_400m_before` / `_after` (D8(d)), `blocks_newly_within`, and `newly_within`: an array of {`blk_no`, `street`, `total_dwelling_units`, `rental_1_2_room`, `distance_before_m`, `distance_after_m`}, nearest the site first.

## Tests (23 Oct 2026: 35 local, 16 through Connect, all passed)

- **Local:** the fill (strict order, the partial block, capacity 0, NULL, negative and larger than all; no calls for Low, Not rated, No forecast or a block without such flats; region filter); the keys; `find_refuges` ties and labels; the what-if on a small grid (exactly 400 m, the site's own block, a second area, a site at a refuge, an unconfirmed site); the SQL files' placeholders, and no forbidden name in them.
- **Connect:**
  - `get_priority_areas` on `area_heat_risk` built by `coolcheck.risk`'s view SQL from the back-test rows of 2025-08-07 only (read with `read_backtest_area_days` and asserted on or before 2026-08-31): 41 areas, High 2 (Choa Chu Kang, Bukit Batok), Medium 15, Low 15, Not rated 9. Capacities 0, 500, 3,200 and 100,000 with regions all, `west`, `East Region` and `nowhere` equal the twin; at 500 all calls go to Choa Chu Kang with the last block partial; at 3,200 the High areas take 3,081 and Medium 119. A synthetic briefing covers every tier.
  - `find_refuges` for every block in one `LATERAL` query: 54,035 rows for the 10,807 confirmed blocks equal the twin (distances to 1e-9 m), the nearest equals `block_access`'s stored refuge, and no two nearest refuges are equally far.
  - `what_if_add_refuge` equals the twin for 3 JLN KUKOH (Outram: 16 blocks, 3,001 dwelling units and 2,190 rental flats newly within 400 m), 106B PUNGGOL FIELD (Punggol and Sengkang), 333C YISHUN ST 31 (8,011 dwelling units), 105 JLN BT MERAH (at a refuge: no gain) and an unconfirmed block (no rows); for one site in each of the 32 rated areas the before share equals `silver.area_access` (main set, 6 decimals).

## For window B (the agent loop)

- Call the functions by full name (`coolcheck.gold.get_priority_areas`, `coolcheck.gold.find_refuges`, `coolcheck.gold.what_if_add_refuge`).
- Pass the `blk_no` and `street` that `get_priority_areas` returns to the other two.
- The allocation is done: the agent reports `calls_allocated`, `partial` and `calls_left` as given and never re-allocates.
- `call_capacity` is volunteers × calls per volunteer, an assumption the app shows (Guide §14.2).
- Distances are straight lines, not walking distances; say so, and round them when speaking.
