# HDB blocks to Master Plan 2025 planning areas

Script: `scripts/static/blocks_to_areas.py`. Output: `coolcheck-data/analysis/hdb_blocks_to_areas.csv` (outside the repo, one row per block). Local only: nothing is loaded to Unity Catalog.

Boundary: Master Plan 2025 Planning Area Boundary (No Sea) (`d_2cc750190544007400b2cfd5d7f53209`, file `d_2cc750190544007400b2cfd5d7f53209.geojson`, sha256 `e6ecc1743de5...`), 55 planning areas, point in polygon with shapely (WGS84 lon/lat from `geocoded_blocks.csv`). HDB attributes: HDB Property Information (`d_17f5382f26140b1fdae0ba2ef6239d2f`, sha256 `d528ea2d6fc3...`); data.gov.sg now names the HDB Existing Building dataset this way, and it is the only HDB building file in `coolcheck-data/static/`.

## Result

- Blocks: **10,817** (confirmed = Y 10,807; confirmed = N 10). Join to HDB Property Information on blk_no + street: 10,817 found, 0 not found.
- Dwelling units: 1,179,156 in total (the file's residential total is 1,179,156).
- **Assigned to a planning area: 10,817.** inside 10,812; on_boundary 5 (on an edge, or another area's polygon within 25 m; the containing polygon is kept); **outside every polygon 0** (no area given).
- Planning areas with at least one block: 32 of 55.

## Blocks per planning area

| planning_area | blocks | dwelling_units | of which confirmed N |
|---|---|---|---|
| ANG MO KIO | 392 | 52,139 | 0 |
| BEDOK | 530 | 64,414 | 0 |
| BISHAN | 238 | 21,650 | 0 |
| BUKIT BATOK | 444 | 48,116 | 0 |
| BUKIT MERAH | 426 | 53,070 | 0 |
| BUKIT PANJANG | 346 | 37,096 | 0 |
| BUKIT TIMAH | 25 | 2,388 | 0 |
| CHANGI | 3 | 166 | 0 |
| CHOA CHU KANG | 529 | 50,171 | 0 |
| CLEMENTI | 206 | 28,709 | 1 |
| DOWNTOWN CORE | 2 | 240 | 0 |
| GEYLANG | 310 | 36,014 | 0 |
| HOUGANG | 610 | 59,582 | 1 |
| JURONG EAST | 234 | 24,691 | 1 |
| JURONG WEST | 747 | 77,241 | 2 |
| KALLANG | 226 | 34,781 | 1 |
| MARINE PARADE | 59 | 7,854 | 0 |
| NOVENA | 89 | 8,450 | 0 |
| OUTRAM | 42 | 7,855 | 0 |
| PASIR RIS | 438 | 30,758 | 0 |
| PUNGGOL | 557 | 63,264 | 0 |
| QUEENSTOWN | 242 | 34,920 | 0 |
| ROCHOR | 35 | 3,902 | 0 |
| SEMBAWANG | 281 | 32,523 | 0 |
| SENGKANG | 669 | 76,265 | 0 |
| SERANGOON | 232 | 21,631 | 0 |
| TAMPINES | 924 | 87,410 | 4 |
| TANGLIN | 2 | 166 | 0 |
| TENGAH | 145 | 16,318 | 0 |
| TOA PAYOH | 386 | 48,943 | 0 |
| WOODLANDS | 741 | 76,343 | 0 |
| YISHUN | 707 | 72,086 | 0 |

Planning areas with no block: BOON LAY, CENTRAL WATER CATCHMENT, CHANGI BAY, LIM CHU KANG, MANDAI, MARINA EAST, MARINA SOUTH, MUSEUM, NEWTON, NORTH-EASTERN ISLANDS, ORCHARD, PAYA LEBAR, PIONEER, RIVER VALLEY, SELETAR, SIMPANG, SINGAPORE RIVER, SOUTHERN ISLANDS, STRAITS VIEW, SUNGEI KADUT, TUAS, WESTERN ISLANDS, WESTERN WATER CATCHMENT.

## Boundary and outside cases (5)

| blk | street | conf | hdb_town | assigned_area | assignment | other_area | other_m | town_match |
|---|---|---|---|---|---|---|---|---|
| 5 | JLN MINYAK | Y | CT | OUTRAM | on_boundary | SINGAPORE RIVER | 15.2 | Y |
| 6 | JLN MINYAK | Y | CT | OUTRAM | on_boundary | SINGAPORE RIVER | 19.1 | Y |
| 100 | C'WEALTH CRES | Y | QT | QUEENSTOWN | on_boundary | BUKIT TIMAH | 23.6 | Y |
| 101 | C'WEALTH CRES | Y | QT | QUEENSTOWN | on_boundary | BUKIT TIMAH | 23.4 | Y |
| 30A | HOLLAND CL | Y | QT | QUEENSTOWN | on_boundary | BUKIT TIMAH | 18.2 | Y |

## The 10 blocks with confirmed = N

| blk | street | hdb_town | assigned_area | assignment | other_area | other_m | town_match |
|---|---|---|---|---|---|---|---|
| 101 | TAMPINES ST 11 | TAP | TAMPINES | inside |  |  | Y |
| 327 | JURONG EAST ST 31 | JE | JURONG EAST | inside |  |  | Y |
| 350 | TAMPINES ST 33 | TAP | TAMPINES | inside |  |  | Y |
| 351 | TAMPINES ST 33 | TAP | TAMPINES | inside |  |  | Y |
| 4C | ST. GEORGE'S LANE | KWN | KALLANG | inside |  |  | Y |
| 511 | JURONG WEST ST 52 | JW | JURONG WEST | inside |  |  | Y |
| 602 | CLEMENTI WEST ST 1 | CL | CLEMENTI | inside |  |  | Y |
| 610 | JURONG WEST ST 65 | JW | JURONG WEST | inside |  |  | Y |
| 703 | TAMPINES ST 71 | TAP | TAMPINES | inside |  |  | Y |
| 926 | HOUGANG ST 91 | HG | HOUGANG | inside |  |  | Y |

## Cross-check against the HDB town

The expected planning areas per town are my judgement from the town boundaries (`TOWN_AREAS` in the script), not a data field. Blocks whose area is in the expected set for their town: **10,812**; outside the set: **5**; unassigned: 0; town with no expected set: 0.

Blocks per HDB town and planning area (only pairs with at least one block):

| hdb_town | planning_area | blocks | expected |
|---|---|---|---|
| AMK | ANG MO KIO | 392 | Y |
| BB | BUKIT BATOK | 444 | Y |
| BD | BEDOK | 530 | Y |
| BH | BISHAN | 238 | Y |
| BM | BUKIT MERAH | 426 | Y |
| BP | BUKIT PANJANG | 346 | Y |
| BT | BUKIT TIMAH | 25 | Y |
| BT | TANGLIN | 2 | N |
| CCK | CHOA CHU KANG | 529 | Y |
| CL | CLEMENTI | 206 | Y |
| CT | DOWNTOWN CORE | 2 | Y |
| CT | OUTRAM | 42 | Y |
| CT | ROCHOR | 35 | Y |
| GL | GEYLANG | 310 | Y |
| HG | HOUGANG | 610 | Y |
| JE | JURONG EAST | 234 | Y |
| JW | JURONG WEST | 747 | Y |
| KWN | KALLANG | 226 | Y |
| KWN | NOVENA | 89 | Y |
| MP | MARINE PARADE | 59 | Y |
| PG | PUNGGOL | 557 | Y |
| PRC | CHANGI | 3 | N |
| PRC | PASIR RIS | 438 | Y |
| QT | QUEENSTOWN | 242 | Y |
| SB | SEMBAWANG | 281 | Y |
| SGN | SERANGOON | 232 | Y |
| SK | SENGKANG | 669 | Y |
| TAP | TAMPINES | 924 | Y |
| TG | TENGAH | 145 | Y |
| TP | TOA PAYOH | 386 | Y |
| WL | WOODLANDS | 741 | Y |
| YS | YISHUN | 707 | Y |

### Blocks outside the expected set (5)

| blk | street | conf | hdb_town | assigned_area | assignment | other_area | other_m |
|---|---|---|---|---|---|---|---|
| 5 | FARRER RD | Y | BT | TANGLIN | inside |  |  |
| 6 | FARRER RD | Y | BT | TANGLIN | inside |  |  |
| 1 | CHANGI VILLAGE RD | Y | PRC | CHANGI | inside |  |  |
| 4 | CHANGI VILLAGE RD | Y | PRC | CHANGI | inside |  |  |
| 5 | CHANGI VILLAGE RD | Y | PRC | CHANGI | inside |  |  |

