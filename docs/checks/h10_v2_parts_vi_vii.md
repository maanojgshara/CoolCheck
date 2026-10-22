# H10 v2 parts (vi) and (vii): HDB share and cluster check

Script: `scripts/static/h10_v2_parts_vi_vii.py`, local only (no Databricks calls). To be merged into `h10_v2.md`. Blocks: the 10,807 confirmed (confirmed = Y) blocks of `hdb_blocks_to_areas.csv` in 32 planning areas (the 10 unconfirmed blocks are left out, as for the reference point). Residents: SingStat June 2026 (MP2025 areas; rounded to the nearest 10 by SingStat, so sums differ slightly). Stations: 31, at their latest locations.

## (vi) Low-HDB areas: how much of each area the HDB blocks represent

HDB residents are estimated as dwelling units x 2.8. **The 2.8 is an assumption** (an assumed persons per dwelling unit, not a measured figure, and the real value differs by area and flat type), so the share is rough and can pass 100% where the assumption is too high or where SingStat rounds down (Bukit Merah, Tengah and Outram do here). SingStat 'residents' are citizens and permanent residents living in Singapore; the HDB units include rental and flats not occupied by residents.

| planning_area | blocks | dwelling_units | est_HDB_residents | SingStat_residents | rough_HDB_share | residents_65+ |
|---|---|---|---|---|---|---|
| TANGLIN | 2 | 166 | 465 | 24,670 | 2% | 4,070 |
| BUKIT TIMAH | 25 | 2,388 | 6,686 | 86,240 | 8% | 15,970 |
| DOWNTOWN CORE | 2 | 240 | 672 | 5,520 | 12% | 420 |
| NOVENA | 89 | 8,450 | 23,660 | 52,190 | 45% | 9,760 |
| MARINE PARADE | 59 | 7,854 | 21,991 | 47,890 | 46% | 10,420 |
| SERANGOON | 232 | 21,631 | 60,567 | 115,310 | 53% | 28,330 |
| PASIR RIS | 438 | 30,758 | 86,122 | 144,240 | 60% | 24,320 |
| BEDOK | 530 | 64,414 | 180,359 | 269,740 | 67% | 65,820 |
| BISHAN | 238 | 21,650 | 60,620 | 87,100 | 70% | 20,180 |
| CHANGI | 3 | 166 | 465 | 660 | 70% | 170 |
| HOUGANG | 609 | 59,490 | 166,572 | 223,110 | 75% | 48,040 |
| CHOA CHU KANG | 529 | 50,171 | 140,479 | 185,340 | 76% | 29,710 |
| BUKIT PANJANG | 346 | 37,096 | 103,869 | 135,020 | 77% | 25,690 |
| CLEMENTI | 205 | 28,493 | 79,780 | 103,460 | 77% | 22,080 |
| SEMBAWANG | 281 | 32,523 | 91,064 | 114,500 | 80% | 14,080 |
| SENGKANG | 669 | 76,265 | 213,542 | 265,470 | 80% | 36,760 |
| BUKIT BATOK | 444 | 48,116 | 134,725 | 165,260 | 82% | 31,490 |
| TAMPINES | 920 | 87,010 | 243,628 | 294,580 | 83% | 55,990 |
| WOODLANDS | 741 | 76,343 | 213,760 | 254,500 | 84% | 37,440 |
| GEYLANG | 310 | 36,014 | 100,839 | 119,050 | 85% | 25,980 |
| JURONG WEST | 745 | 76,915 | 215,362 | 250,250 | 86% | 45,650 |
| PUNGGOL | 557 | 63,264 | 177,139 | 204,390 | 87% | 21,450 |
| YISHUN | 707 | 72,086 | 201,841 | 230,600 | 88% | 41,600 |
| ANG MO KIO | 392 | 52,139 | 145,989 | 157,860 | 92% | 41,730 |
| ROCHOR | 35 | 3,902 | 10,926 | 11,770 | 93% | 2,800 |
| TOA PAYOH | 386 | 48,943 | 137,040 | 147,800 | 93% | 31,910 |
| JURONG EAST | 233 | 24,615 | 68,922 | 71,670 | 96% | 18,550 |
| KALLANG | 225 | 34,691 | 97,135 | 101,100 | 96% | 24,520 |
| QUEENSTOWN | 242 | 34,920 | 97,776 | 100,310 | 97% | 22,560 |
| BUKIT MERAH | 426 | 53,070 | 148,596 | 143,870 | 103% | 36,570 |
| TENGAH | 145 | 16,318 | 45,690 | 34,490 | 132% | 2,650 |
| OUTRAM | 42 | 7,855 | 21,994 | 16,510 | 133% | 4,640 |

Sorted from the lowest share up. Where the share is low (Tanglin, Bukit Timah, Downtown Core), the area label represents the HDB residents, not the whole area. No rule change.

Areas with blocks but no SingStat row under the same name: none.

## (vii) Cluster check: the station that serves the blocks best

For each area with blocks, `cluster_station` is the one of all 31 stations (including the three offshore ones and stations that have stopped) with the smallest dwelling-unit-weighted mean haversine distance from the area's confirmed blocks. `mean_station` is the nearest station to the area's block-mean point, which is the H10 v2 reference point. Both are judged on the same measure, the weighted mean distance to the blocks (km). A check only; it changes nothing.

The two stations agree in **32 of 32** areas and differ in **0**:

None.

Areas with 65+ residents among those that differ: none.

Near ties: the areas where the runner-up station is within 0.5 km of the best on the same measure, so the choice is fragile even where the two methods agree.

| planning_area | cluster_station | weighted_km | runner_up | runner_up_gap_km |
|---|---|---|---|---|
| JURONG WEST | S180 | 1.80 | S132 | 0.02 |
| MARINE PARADE | S129 | 3.82 | S127 | 0.05 |
| NOVENA | S145 | 3.09 | S133 | 0.10 |
| BUKIT MERAH | S138 | 2.78 | S144 | 0.15 |
| TOA PAYOH | S128 | 2.40 | S145 | 0.29 |
| ANG MO KIO | S141 | 1.59 | S128 | 0.41 |
| SERANGOON | S131 | 2.04 | S128 | 0.44 |
| TANGLIN | S187 | 0.94 | S150 | 0.48 |

