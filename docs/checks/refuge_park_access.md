# Refuge and park layers and the cooling-access measures (R1, R2)

Script: `scripts/static/refuge_park_access.py`; geometry and layer rules: `src/coolcheck/access.py`; tests: `tests/static/test_refuge_park_access.py`. Outputs (outside the repo): `coolcheck-data/analysis/refuge_points.csv`, `park_polygons.csv`, `block_access.csv`, `area_access.csv`. Nothing was loaded to Unity Catalog by this script and no OneMap call was made.

Seniors: `coolcheck.silver.area_exposure`, Delta version 1, through Databricks Connect (profile coolcheck). Blocks: `analysis/hdb_blocks_to_areas.csv` (geocoded HDB blocks with their Master Plan 2025 planning area).

## Inputs

| dataset | agency | id | last updated | downloaded | sha256 | role |
|---|---|---|---|---|---|---|
| Community Club / PAssion WaVe Outlet | People's Association | `d_9de02d3fb33d96da1855f4fbef549a0f` | 2026-10-02 | 2026-10-21 12:43 SGT | `e35b40883132` | used |
| Community Clubs | People's Association | `d_f706de1427279e61fe41e89e24d440fa` | 2024-06-06 | 2026-10-21 12:43 SGT | `d6acbfc863db` | compared only |
| Dementia Friendly Go-To-Points (GTPs) | Ministry of Health | `d_e2d10e591bc8560b8946a0da24790fa5` | 2026-08-20 | 2026-10-21 22:49 SGT | `8ece10b8c30f` | used |
| Eldercare Services | Ministry of Health | `d_f0fd1b3643ed8bd34bd403dedd7c1533` | 2024-06-06 | 2026-10-21 12:43 SGT | `0db8209b8672` | used |
| NParks Parks and Nature Reserves | National Parks Board | `d_77d7ec97be83d44f61b85454f844382f` | 2026-10-21 | 2026-10-21 22:44 SGT | `032a96ae1cde` | used |
| Master Plan 2025 SDCP Park layer | Urban Redevelopment Authority | `d_3fad8acbb848e6a3aad053cc438815da` | 2026-01-30 | 2026-10-21 22:49 SGT | `9a3ec1af8932` | used |

All under the Singapore Open Data Licence v1.0 (data.gov.sg). Planning areas: Master Plan 2025 Planning Area Boundary (No Sea).

## Checks

| figure | expected | this run | same |
|---|---|---|---|
| club rows | 122 | 122 | yes |
| clubs under construction | 4 | 4 | yes |
| clubs temp office | 7 | 7 | yes |
| aac | 93 | 93 | yes |
| gtp sac | 4 | 4 | yes |
| sac 2016 | 60 | 60 | yes |
| possible aac | 3 | 3 | yes |
| sites clubs only | 113 | 113 | yes |
| sites main | 206 | 206 | yes |
| sites with sac 2016 | 232 | 232 | yes |
| nparks excluded | 8 | 8 | yes |
| points failing coordinates | 0 | 0 | yes |
| blocks | 10,817 | 10,817 | yes |
| blocks confirmed | 10,807 | 10,807 | yes |
| aged 65 plus | 806,080 | 806,080 | yes |

All match.

## R1, refuges

### Community Clubs: the People's Association file of 2 Oct 2026

- **Used:** `d_9de02d3fb33d96da1855f4fbef549a0f` (last updated 2026-10-02T10:06:45+08:00): 128 rows, `DESCRIPTION` 'CC' 122, 'PAssionWave' 6. The field has exactly these two values and every non-'CC' row is named 'PAssion WaVe @ ...', so the filter `DESCRIPTION = 'CC'` is reliable.
- **Not used:** the 2024 file (`d_f706de1427279e61fe41e89e24d440fa`, last updated 2024-06-06): 125 rows = 'CC' 119, 'PAssion WaVe' 6; 35 of its club names are marked U/C, Pending U/C, pending relocation or 'Till 1Q 2022'. Its '125 points' are not 125 clubs.
- **Under construction, in no set** (kept in `refuge_points` with `status = under_construction`): Kim Seng CC (U/C) (169640); Bukit Batok CC (U/C) (659959); Gek Poh Ville CC (U/C) (649149); Sembawang Central CO @ Sembawang CC (U/C) (758528).
- **Temporary offices, kept and flagged** (`status = temp_office`): Bukit Batok CC (Temp office) (650119); Marsiling CC (Temp Office) (730002); Marine Parade CC (Temp Office) (440067); Kampong Kembangan CC (Temp Office) (410109); Gek Poh Ville CC (Temp office) (640760); Sembawang Central CO @ Sembawang CC (Temp Office) (752117); Chong Pang CC (Temp Office) (760126).
- **Postal codes padded** (the field is numeric in the newer file and lost the leading zero; the 2024 file has the 6-digit codes): imPAct@Hong Lim Green 58284 -> 058284; Kreta Ayer CC 88995 -> 088995; Radin Mas CC 98917 -> 098917; Tanjong Pagar CC 89774 -> 089774.
- **Rows named '... CO c/o / @ ... CC'**: Limbang CO c/o Yew Tee CC (duplicate of Yew Tee CC); Buangkok-Fernvale South CO c/o Fernvale CC (duplicate of Fernvale CC); Changi CO c/o Pasir Ris East CC (duplicate of Pasir Ris East CC); Naval Base CO @ Canberra CC (duplicate of Canberra CC); Punggol Coast CO @ One Punggol CC (kept: the only row at 828629); Tampines Boulevard CO c/o Tampines Central CC (duplicate of Tampines Central CC); Sembawang Central CO @ Sembawang CC (Temp Office) (kept: the only row at 752117); Sembawang Central CO @ Sembawang CC (U/C) (kept: the only row at 758528).
- Club sites after removing postal-code duplicates and the clubs under construction: **113**.

### Active Ageing Centres: the partial layer

- MOH Dementia Friendly Go-To-Points: 831 rows. **93 AACs**, identified by name with `AAC_RX` (`active ageing (centre|hub|center)|\bAAC\b|\bAAH\b`, case-insensitive; the pattern of `scripts/checks/static_data_2.py`), 93 distinct postal codes. Record update year: 2024 64, 2025 10, 2026 19. Partial: 93 of about 223 AACs (SingStat, 2024).
- Names with the broken character U+FFFD replaced by a space: 19 (the source name is kept in `name_raw`).
- **Possible AACs the pattern misses, not used** (3): REACH Senior Centre @ Jalan Membina (165026); Active Global Active Care Centre @ Fernvale Glades (790460); Anglican Senior Centre (Yishun) (761426).
- **SACs in the Go-To-Points file** (4), out of main, in `with_sac_2016`: AWWA Senior Activity Centre (SAC) @ Yio Chu Kang (560123); CARElderly Senior Activity Centre (SAC) (370035); REACH Senior Centre (SAC) @ Bukit Gombak Vista (651377); MWS Senior Activity Centre (SAC) - Fernvale Rivergrove (791473). Sharing a postal code with an AAC: 0.

### Eldercare Services, 2016 (sensitivity only)

- 133 rows, all stamped 2016: SAC by name 60, Silver ACE 6 (left out), AAC by name 0, other 67. The 60 SACs go into `with_sac_2016` only.

### Postal-code duplicates and the sets

Kept first by layer (club, AAC, Go-To-Points SAC, 2016 SAC), then open before temporary office, then a club's own row before a CO row housed in it. Duplicates stay in `refuge_points` with `duplicate_of`.

| duplicate row's layer | kept row's layer | rows |
|---|---|---|
| community_club | community_club | 5 |
| eldercare_sac_2016 | aac_partial | 36 |
| eldercare_sac_2016 | gtp_sac | 2 |

| set | layers | rows (U/C out) | sites |
|---|---|---|---|
| main | community_club + aac_partial | 211 | 206 |
| clubs_only | community_club | 118 | 113 |
| with_sac_2016 | community_club + aac_partial + gtp_sac + eldercare_sac_2016 | 275 | 232 |

### Coordinates

- 279 points checked (every row of `refuge_points`): inside 1.13 to 1.48 N and 103.59 to 104.1 E, and inside a Master Plan 2025 planning area (or within 25 m of one). **Failing: 0.** No OneMap call is needed.
- Points outside their polygon but within 25 m: 0.

Projection check: pyproj's EPSG:4326 to EPSG:3414 of the 831 Go-To-Points lon/lat against the file's own SVY21 `X_ADDR` / `Y_ADDR`: largest difference 0.0001 m.

## R2, parks

### NParks Parks and Nature Reserves

462 polygons (2 invalid in the source, repaired with `make_valid`). Excluded from main (kept in `with_reserves`):

| name | L_CODE | N_RESERVE | area (km2, SVY21) |
|---|---|---|---|
| CENTRAL CATCHMENT NATURE RESERVE | NRNP04 | 1 | 30.40 |
| PULAU UBIN AND CHEK JAWA | NRNP21 | 0 | 10.03 |
| BUKIT TIMAH NATURE RESERVE | NRNP03 | 1 | 1.62 |
| SUNGEI BULOH WETLAND RESERVE | NRNP02 | 1 | 1.31 |
| UPPER SELETAR RESERVOIR PARK | NRNP05 | 1 | 0.13 |
| LOWER PEIRCE RESERVOIR PARK | NRNP07 | 1 | 0.10 |
| LABRADOR NATURE RESERVE | NRNP01 | 1 | 0.10 |
| UPPER PEIRCE RESERVOIR PARK | NRNP06 | 1 | 0.07 |

Nature parks with `N_RESERVE = 0` stay in main (11): BUKIT BATOK NATURE PARK, CHESTNUT NATURE PARK, DAIRY FARM NATURE PARK, HINDHEDE NATURE PARK, KRANJI COASTAL NATURE PARK, LABRADOR NATURE PARK, RIFLE RANGE NATURE PARK, SPRINGLEAF NATURE PARK, THOMSON NATURE PARK, WINDSOR NATURE PARK, ZHENGHUA NATURE PARK. Three of the seven `N_RESERVE = 1` polygons are reservoir parks; see 'Reservoir parks' below.

### URA Master Plan 2025 SDCP Park layer

426 polygons (4 invalid, repaired): PERMANENT 309, INTERIM 117. Merged area: permanent 13.66 km2, interim 5.85 km2; both are used. Exact duplicate geometries dropped: 17. The layer has no name field.

### Park sets

| set | polygons | sum of areas (km2) | merged (km2) | pieces under 100 m2 dropped | their area (m2) | polygons wholly in them |
|---|---|---|---|---|---|---|
| main | 454 | 21.51 | 21.51 | 62 | 885.1 | 0 |
| with_reserves | 462 | 65.28 | 64.90 | 62 | 885.1 | 0 |
| ura | 409 | 19.52 | 19.52 | 36 | 385.2 | 25 |

Pieces dropped from `main`, by the source polygons they come from (pieces, total m2): np_ST528 ISTANA PK (45, 397.4); np_NA503 BISHAN-ANG MO KIO PARK (RIVER PLAINS) (1, 96.7); np_PKWR013 CHESTNUT CLOSE PARK (1, 90.3); np_CO154 CONNAUGHT DRIVE (3, 86.1); np_SO503 EMPRESS PLACE (2, 78.4); np_NRNP25 RAILWAY CORRIDOR RIFLE RANGE CONNECTOR (1, 70.9); np_PKWBP(101472 BULIM PARK (PHASE 1)  (1, 44.2); np_NW500 MARSILING PARK (1, 17.5); np_PKCSAP01237 SILAT AVENUE PARK (1, 1.9); np_WB550 HOLLAND GREEN LINEAR PARK (1, 0.8); np_WT502 MOUNT FABER PARK (1, 0.7); np_NA551 CHUAN LANE PARK (1, 0.2); np_EE505 EAST COAST PARK AREA F (1, 0.0); np_MWJH018 TAMAN JURONG OASIS INTERIM PARK (1, 0.0); np_WB549 MAPLE LANE PARK (1, 0.0)

Pieces dropped from `with_reserves`, by the source polygons they come from (pieces, total m2): np_ST528 ISTANA PK (45, 397.4); np_NA503 BISHAN-ANG MO KIO PARK (RIVER PLAINS) (1, 96.7); np_PKWR013 CHESTNUT CLOSE PARK (1, 90.3); np_CO154 CONNAUGHT DRIVE (3, 86.1); np_SO503 EMPRESS PLACE (2, 78.4); np_NRNP25 RAILWAY CORRIDOR RIFLE RANGE CONNECTOR (1, 70.9); np_PKWBP(101472 BULIM PARK (PHASE 1)  (1, 44.2); np_NW500 MARSILING PARK (1, 17.5); np_PKCSAP01237 SILAT AVENUE PARK (1, 1.9); np_WB550 HOLLAND GREEN LINEAR PARK (1, 0.8); np_WT502 MOUNT FABER PARK (1, 0.7); np_NA551 CHUAN LANE PARK (1, 0.2); np_EE505 EAST COAST PARK AREA F (1, 0.0); np_MWJH018 TAMAN JURONG OASIS INTERIM PARK (1, 0.0); np_WB549 MAPLE LANE PARK (1, 0.0)

Pieces dropped from `ura`, by the source polygons they come from (pieces, total m2): ura_345 (1, 95.5); ura_191 (1, 88.2); ura_186 (1, 72.7); ura_158 (1, 47.7); ura_219 (1, 19.1); ura_218 (1, 18.9); ura_124 (1, 15.0); ura_407 (1, 12.7); ura_215 (1, 5.0); ura_209 (1, 3.0); ura_217 (1, 2.0); ura_17, ura_250 (1, 1.8); ura_252, ura_56 (1, 1.3); ura_13, ura_178 (2, 0.7); ura_198 (1, 0.7); ura_232 (1, 0.4); ura_52, ura_99 (1, 0.2); ura_149, ura_35 (1, 0.1); ura_242 (1, 0.1); ura_243 (1, 0.1); ura_107, ura_4 (2, 0.0); ura_214 (1, 0.0); ura_233 (1, 0.0); ura_234, ura_237, ura_238 (1, 0.0); ura_234, ura_237, ura_241 (1, 0.0); ura_234, ura_241 (1, 0.0); ura_235 (1, 0.0); ura_236, ura_237, ura_238 (1, 0.0); ura_236, ura_238 (1, 0.0); ura_239 (1, 0.0); ura_24, ura_94 (2, 0.0); ura_240 (1, 0.0); ura_79 (1, 0.0)

Blocks nearer to a park once the reserves are added: 0 of 10,817, so `with_reserves` changes no block distance and no 400 m share; it changes only the park share of the areas that hold the reserves.

`static_data_2.md` gave 65.72 and 21.65 km2 from a flat approximation; the SVY21 figures above match the files' own `SHAPE_1.AREA` and are the ones to quote.

## Reservoir parks (excluded as decided)

Confirmed HDB blocks within 400 m of Upper Seletar, Lower Peirce or Upper Peirce Reservoir Park: 0 blocks, 0 dwelling units (0.00% of 1,177,956). Of these, not within 400 m of a main-set park: 0 blocks, 0 dwelling units; only these would change the park measure if the three were included.

## Measures per planning area

Distances are straight lines in SVY21 from each block to the nearest refuge (anywhere, not only in its own area) and to the nearest edge of the merged park set (0 inside a park). Shares are of the HDB dwelling units of the confirmed blocks; 400 m counts as within. Refuges per 1,000 aged 65+ counts the refuges inside the area. Park share is the merged park area inside the area over the area's land; context only.

41 areas with residents aged 65+ (blank: no HDB block in the area):

| planning area | 65+ | DU | refuges (main) | per 1,000: main | clubs | +SAC | 400 m refuge: main | clubs | +SAC | 400 m park: main | +reserves | URA | park share (main) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ANG MO KIO | 41,730 | 52,139 | 15 | 0.36 | 0.12 | 0.38 | 81.2% | 46.1% | 86.5% | 80.5% | 80.5% | 22.9% | 6.7% |
| BEDOK | 65,820 | 64,414 | 12 | 0.18 | 0.12 | 0.23 | 56.3% | 45.4% | 72.7% | 48.9% | 48.9% | 13.7% | 7.1% |
| BISHAN | 20,180 | 21,650 | 6 | 0.30 | 0.15 | 0.35 | 61.5% | 34.7% | 67.2% | 75.6% | 75.6% | 6.7% | 17.3% |
| BUKIT BATOK | 31,490 | 48,116 | 7 | 0.22 | 0.13 | 0.25 | 52.3% | 33.3% | 52.8% | 36.1% | 36.1% | 6.4% | 8.5% |
| BUKIT MERAH | 36,570 | 53,070 | 18 | 0.49 | 0.14 | 0.57 | 83.9% | 46.4% | 84.4% | 83.7% | 83.7% | 25.4% | 8.5% |
| BUKIT PANJANG | 25,690 | 37,096 | 5 | 0.19 | 0.12 | 0.19 | 65.5% | 50.7% | 65.5% | 43.2% | 43.2% | 23.9% | 20.3% |
| BUKIT TIMAH | 15,970 | 2,388 | 2 | 0.13 | 0.06 | 0.13 | 71.7% | 48.3% | 71.7% | 83.7% | 83.7% | 71.7% | 1.7% |
| CHANGI | 170 | 166 | 0 | 0.00 | 0.00 | 0.00 | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 100.0% | 0.8% |
| CHOA CHU KANG | 29,710 | 50,171 | 7 | 0.24 | 0.13 | 0.24 | 44.8% | 35.0% | 44.8% | 31.8% | 31.8% | 32.4% | 1.9% |
| CLEMENTI | 22,080 | 28,493 | 6 | 0.27 | 0.09 | 0.27 | 63.7% | 30.4% | 63.7% | 38.2% | 38.2% | 24.6% | 1.8% |
| DOWNTOWN CORE | 420 | 240 | 0 | 0.00 | 0.00 | 0.00 | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 100.0% | 1.8% |
| GEYLANG | 25,980 | 36,014 | 10 | 0.38 | 0.15 | 0.50 | 66.8% | 40.4% | 79.3% | 50.8% | 50.8% | 69.8% | 0.5% |
| HOUGANG | 48,040 | 59,490 | 7 | 0.15 | 0.10 | 0.19 | 47.8% | 33.5% | 48.9% | 48.8% | 48.8% | 16.6% | 1.6% |
| JURONG EAST | 18,550 | 24,615 | 2 | 0.11 | 0.11 | 0.16 | 27.9% | 26.0% | 44.9% | 9.6% | 9.6% | 28.5% | 4.8% |
| JURONG WEST | 45,650 | 76,915 | 12 | 0.26 | 0.15 | 0.26 | 56.9% | 49.7% | 56.9% | 33.9% | 33.9% | 20.3% | 0.9% |
| KALLANG | 24,520 | 34,691 | 9 | 0.37 | 0.29 | 0.53 | 72.9% | 71.4% | 86.7% | 51.8% | 51.8% | 54.2% | 0.7% |
| MANDAI | 350 | 0 | 0 | 0.00 | 0.00 | 0.00 |  |  |  |  |  |  | 0.1% |
| MARINE PARADE | 10,420 | 7,854 | 2 | 0.19 | 0.19 | 0.19 | 48.2% | 48.2% | 48.2% | 97.2% | 97.2% | 0.0% | 12.2% |
| MUSEUM | 20 | 0 | 0 | 0.00 | 0.00 | 0.00 |  |  |  |  |  |  | 31.4% |
| NEWTON | 1,440 | 0 | 1 | 0.69 | 0.69 | 0.69 |  |  |  |  |  |  | 1.2% |
| NOVENA | 9,760 | 8,450 | 4 | 0.41 | 0.20 | 0.41 | 75.9% | 53.2% | 75.9% | 39.1% | 39.1% | 47.7% | 0.4% |
| ORCHARD | 190 | 0 | 0 | 0.00 | 0.00 | 0.00 |  |  |  |  |  |  | 0.5% |
| OUTRAM | 4,640 | 7,855 | 2 | 0.43 | 0.43 | 1.08 | 60.2% | 60.2% | 100.0% | 100.0% | 100.0% | 16.9% | 7.7% |
| PASIR RIS | 24,320 | 30,758 | 5 | 0.21 | 0.12 | 0.21 | 52.9% | 37.2% | 52.9% | 48.2% | 48.2% | 46.5% | 5.4% |
| PUNGGOL | 21,450 | 63,264 | 6 | 0.28 | 0.19 | 0.28 | 39.9% | 21.3% | 39.9% | 27.6% | 27.6% | 17.2% | 12.2% |
| QUEENSTOWN | 22,560 | 34,920 | 10 | 0.44 | 0.18 | 0.44 | 84.3% | 34.7% | 84.3% | 44.2% | 44.2% | 16.7% | 6.7% |
| RIVER VALLEY | 1,770 | 0 | 0 | 0.00 | 0.00 | 0.00 |  |  |  |  |  |  | 0.5% |
| ROCHOR | 2,800 | 3,902 | 1 | 0.36 | 0.00 | 0.36 | 40.9% | 0.0% | 40.9% | 69.4% | 69.4% | 82.3% | 0.0% |
| SELETAR | 20 | 0 | 0 | 0.00 | 0.00 | 0.00 |  |  |  |  |  |  | 0.3% |
| SEMBAWANG | 14,080 | 32,523 | 3 | 0.21 | 0.14 | 0.21 | 40.7% | 28.4% | 40.7% | 55.4% | 55.4% | 14.3% | 2.2% |
| SENGKANG | 36,760 | 76,265 | 6 | 0.16 | 0.14 | 0.19 | 45.9% | 35.6% | 49.2% | 40.7% | 40.7% | 7.2% | 2.2% |
| SERANGOON | 28,330 | 21,631 | 3 | 0.11 | 0.11 | 0.11 | 54.2% | 54.2% | 54.2% | 45.5% | 45.5% | 0.0% | 2.3% |
| SINGAPORE RIVER | 430 | 0 | 1 | 2.33 | 2.33 | 2.33 |  |  |  |  |  |  | 1.4% |
| SOUTHERN ISLANDS | 330 | 0 | 0 | 0.00 | 0.00 | 0.00 |  |  |  |  |  |  | 2.0% |
| SUNGEI KADUT | 180 | 0 | 0 | 0.00 | 0.00 | 0.00 |  |  |  |  |  |  | 1.0% |
| TAMPINES | 55,990 | 87,010 | 10 | 0.18 | 0.11 | 0.18 | 49.0% | 33.4% | 49.0% | 30.1% | 30.1% | 34.3% | 3.5% |
| TANGLIN | 4,070 | 166 | 0 | 0.00 | 0.00 | 0.00 | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% | 0.0% | 11.1% |
| TENGAH | 2,650 | 16,318 | 1 | 0.38 | 0.38 | 0.38 | 36.1% | 36.1% | 36.1% | 44.8% | 44.8% | 22.6% | 0.1% |
| TOA PAYOH | 31,910 | 48,943 | 15 | 0.47 | 0.19 | 0.50 | 83.5% | 57.1% | 83.6% | 33.0% | 33.0% | 36.7% | 2.3% |
| WOODLANDS | 37,440 | 76,343 | 8 | 0.21 | 0.16 | 0.27 | 42.4% | 36.3% | 47.3% | 23.4% | 23.4% | 12.6% | 3.9% |
| YISHUN | 41,600 | 72,086 | 10 | 0.24 | 0.12 | 0.24 | 44.9% | 33.3% | 44.9% | 37.4% | 37.4% | 16.5% | 2.5% |

Singapore-wide share of the confirmed blocks' dwelling units within 400 m: refuge main 55.9%, clubs_only 39.4%, with_sac_2016 59.2%; park main 43.6%, with_reserves 43.6%, ura 23.1%.

## How the area ranking moves between the main and the sensitivity layers

No risk score yet: each access measure is ranked on its own, worst access first.

| measure | sensitivity set | areas | Spearman rho | worst 10 kept | areas moving 5+ |
|---|---|---|---|---|---|
| Refuges per 1,000 residents aged 65+ | clubs_only | 41 | 0.838 | 9 of 10 | 14 |
| Refuges per 1,000 residents aged 65+ | with_sac_2016 | 41 | 0.989 | 10 of 10 | 1 |
| Share of HDB dwelling units within 400 m of a refuge | clubs_only | 32 | 0.718 | 7 of 10 | 16 |
| Share of HDB dwelling units within 400 m of a refuge | with_sac_2016 | 32 | 0.946 | 9 of 10 | 3 |
| Share of HDB dwelling units within 400 m of a park | with_reserves | 32 | 1.000 | 10 of 10 | 0 |
| Share of HDB dwelling units within 400 m of a park | ura | 32 | 0.082 | 3 of 10 | 25 |
| Park share of the area (context only) | with_reserves | 41 | 0.952 | 9 of 10 | 1 |
| Park share of the area (context only) | ura | 41 | 0.260 | 3 of 10 | 30 |

### Refuges per 1,000 residents aged 65+ (41 areas; rank 1 = lowest value, worst access)

- **main vs clubs_only:** Spearman rho 0.838; worst 10 kept: 9 of 10 (out: TANGLIN; in: ROCHOR); areas moving 5 or more places: 14: ROCHOR 30 -> 6, MARINE PARADE 18 -> 35, CLEMENTI 27 -> 13, BUKIT MERAH 39 -> 26, ANG MO KIO 31 -> 19, SENGKANG 15 -> 25, WOODLANDS 22 -> 31, SEMBAWANG 21 -> 27, JURONG EAST 12 -> 17, KALLANG 32 -> 37, PUNGGOL 28 -> 33, QUEENSTOWN 37 -> 32, TENGAH 33 -> 38, YISHUN 25 -> 20.
- **main vs with_sac_2016:** Spearman rho 0.989; worst 10 kept: 10 of 10; areas moving 5 or more places: 1: KALLANG 32 -> 37.

### Share of HDB dwelling units within 400 m of a refuge (32 areas; rank 1 = lowest value, worst access)

- **main vs clubs_only:** Spearman rho 0.718; worst 10 kept: 7 of 10 (out: CHOA CHU KANG, TENGAH, WOODLANDS; in: BUKIT BATOK, CLEMENTI, YISHUN); areas moving 5 or more places: 16: QUEENSTOWN 32 -> 14, CLEMENTI 23 -> 8, TENGAH 5 -> 17, SERANGOON 18 -> 29, MARINE PARADE 14 -> 24, OUTRAM 21 -> 31, BISHAN 22 -> 13, WOODLANDS 9 -> 18, BUKIT MERAH 31 -> 23, ANG MO KIO 29 -> 22, BUKIT BATOK 16 -> 9, JURONG WEST 20 -> 26, ROCHOR 8 -> 2.5, CHOA CHU KANG 10 -> 15, GEYLANG 25 -> 20, KALLANG 27 -> 32.
- **main vs with_sac_2016:** Spearman rho 0.946; worst 10 kept: 9 of 10 (out: WOODLANDS; in: YISHUN); areas moving 5 or more places: 3: OUTRAM 21 -> 32, JURONG EAST 4 -> 10, BEDOK 19 -> 24.

### Share of HDB dwelling units within 400 m of a park (32 areas; rank 1 = lowest value, worst access)

- **main vs with_reserves:** Spearman rho 1.000; worst 10 kept: 10 of 10; areas moving 5 or more places: 0.
- **main vs ura:** Spearman rho 0.082; worst 10 kept: 3 of 10 (out: CHOA CHU KANG, CLEMENTI, JURONG EAST, JURONG WEST, PUNGGOL, TAMPINES, TOA PAYOH; in: BEDOK, BISHAN, MARINE PARADE, SEMBAWANG, SENGKANG, SERANGOON, TANGLIN); areas moving 5 or more places: 25: TANGLIN 30.5 -> 2, MARINE PARADE 28 -> 2, JURONG EAST 1 -> 21, BISHAN 24 -> 5, TAMPINES 4 -> 23, TOA PAYOH 6 -> 24, OUTRAM 30.5 -> 13, CHOA CHU KANG 5 -> 22, NOVENA 11 -> 26, SERANGOON 16 -> 2, SEMBAWANG 22 -> 9, BEDOK 19 -> 8, PUNGGOL 3 -> 14, CLEMENTI 10 -> 19, ANG MO KIO 25 -> 17, GEYLANG 20 -> 28, JURONG WEST 7 -> 15, PASIR RIS 17 -> 25, BUKIT MERAH 27 -> 20, HOUGANG 18 -> 11, ROCHOR 23 -> 30, KALLANG 21 -> 27, SENGKANG 12 -> 6, BUKIT PANJANG 13 -> 18, WOODLANDS 2 -> 7.

### Park share of the area (context only) (41 areas; rank 1 = lowest value, worst access)

- **main vs with_reserves:** Spearman rho 0.952; worst 10 kept: 9 of 10 (out: MANDAI; in: JURONG WEST); areas moving 5 or more places: 1: MANDAI 2 -> 25.
- **main vs ura:** Spearman rho 0.260; worst 10 kept: 3 of 10 (out: GEYLANG, KALLANG, NOVENA, ORCHARD, RIVER VALLEY, ROCHOR, TENGAH; in: BUKIT BATOK, HOUGANG, JURONG WEST, OUTRAM, SEMBAWANG, SERANGOON, SINGAPORE RIVER); areas moving 5 or more places: 30: BUKIT BATOK 35 -> 5, OUTRAM 33 -> 4, ROCHOR 1 -> 29, TANGLIN 36 -> 11, SUNGEI KADUT 12 -> 34, SOUTHERN ISLANDS 20 -> 41, NOVENA 5 -> 25, BUKIT MERAH 34 -> 15, KALLANG 9 -> 28, ORCHARD 8 -> 26, RIVER VALLEY 6 -> 24, TENGAH 3 -> 21, SERANGOON 24 -> 7, BEDOK 32 -> 16, QUEENSTOWN 30 -> 14, MARINE PARADE 37 -> 22, GEYLANG 7 -> 20, DOWNTOWN CORE 18 -> 30, SEMBAWANG 22 -> 10, SENGKANG 21 -> 33, SINGAPORE RIVER 14 -> 2, JURONG EAST 28 -> 17, NEWTON 13 -> 23, HOUGANG 15 -> 6, PASIR RIS 29 -> 36, ANG MO KIO 31 -> 37, CHOA CHU KANG 19 -> 13, CLEMENTI 17 -> 12, TAMPINES 26 -> 31, WOODLANDS 27 -> 32.

## Effect of the 10 unconfirmed blocks

The shares above use the 10,807 confirmed blocks. With all 10,817 blocks (10 unconfirmed, 1,200 dwelling units, in CLEMENTI, HOUGANG, JURONG EAST, JURONG WEST, KALLANG, TAMPINES), 36 of 192 area x set shares change; the largest change is 0.52% points (CLEMENTI, refuge clubs_only).

## Limits

- Straight-line distance, not walking distance; a park distance is to its edge, not to an entrance.
- The AAC layer is partial (93 of about 223), so distances overstate the gap where AACs are missing; `with_sac_2016` adds 2016 SACs that may have closed or been renamed. Both sensitivity sets bound the effect, they do not remove it.
- Refuges per 1,000 aged 65+ counts refuges inside the area only; residents near a boundary also use the next area's.
- The temporary club offices may be small premises; they are open, so they count, and are flagged.
