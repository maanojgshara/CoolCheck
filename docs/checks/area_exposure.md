# area_exposure: residents, aged 65+ and aged 75+ per Master Plan 2025 planning area

Script: `scripts/static/area_exposure.py`. Input: `static/singstat_pop_pa_age_sex_floor_area_jun2026/respopagesexfa2026.csv` (SingStat, reference period 2026; downloaded 2026-10-21 12:44 SGT). Output: `coolcheck-data/analysis/area_exposure.csv` (outside the repo). Nothing was loaded to Databricks and no network call was made.

## Method

- 63,080 rows (subzone x age group x sex x floor-area band), 332 subzones, 55 planning areas. Each `Pop` cell is rounded to the nearest 10 by SingStat, so an area's figure is a sum of rounded cells and the file's own note says it may not add up.
- 65+ = age groups 65_to_69 to 90_and_Over (5 groups plus 90_and_Over); 75+ = 75_to_79 to 90_and_Over. The 19 age groups in the file are exactly the 19 expected.
- The area names, upper-cased, equal the 55 `PLN_AREA_N` values of the Master Plan 2025 boundary file (`ura_mp2025_planning_area_boundary`); no name is in one file only. Every boundary area has a row.
- Shares are the fraction of the area's residents (not of Singapore's 65+); blank where the area has no residents.

## Totals against the Guide

| figure | Guide | this run | same |
|---|---|---|---|
| residents | 4,199,180 | 4,199,180 | yes |
| aged 65 plus | 806,080 | 806,080 | yes |
| aged 75 plus | 310,310 | 310,310 | yes |
| areas with 65 plus | 41 | 41 | yes |

All four match.

Areas with no residents (14): BOON LAY, CENTRAL WATER CATCHMENT, CHANGI BAY, LIM CHU KANG, MARINA EAST, MARINA SOUTH, NORTH-EASTERN ISLANDS, PAYA LEBAR, PIONEER, SIMPANG, STRAITS VIEW, TUAS, WESTERN ISLANDS, WESTERN WATER CATCHMENT.

Areas with residents but none aged 65+ (0): none.

## Ten areas with the most residents aged 65+

| planning area | residents | 65+ | 75+ | 65+ share | 75+ share |
|---|---|---|---|---|---|
| BEDOK | 269,740 | 65,820 | 27,590 | 24.4% | 10.2% |
| TAMPINES | 294,580 | 55,990 | 18,360 | 19.0% | 6.2% |
| HOUGANG | 223,110 | 48,040 | 17,410 | 21.5% | 7.8% |
| JURONG WEST | 250,250 | 45,650 | 15,590 | 18.2% | 6.2% |
| ANG MO KIO | 157,860 | 41,730 | 18,760 | 26.4% | 11.9% |
| YISHUN | 230,600 | 41,600 | 14,030 | 18.0% | 6.1% |
| WOODLANDS | 254,500 | 37,440 | 11,700 | 14.7% | 4.6% |
| SENGKANG | 265,470 | 36,760 | 12,260 | 13.8% | 4.6% |
| BUKIT MERAH | 143,870 | 36,570 | 17,300 | 25.4% | 12.0% |
| TOA PAYOH | 147,800 | 31,910 | 14,290 | 21.6% | 9.7% |

## Ten areas with the highest 65+ share (areas with at least 1,000 residents)

| planning area | residents | 65+ | 65+ share | 75+ share |
|---|---|---|---|---|
| OUTRAM | 16,510 | 4,640 | 28.1% | 13.2% |
| ANG MO KIO | 157,860 | 41,730 | 26.4% | 11.9% |
| JURONG EAST | 71,670 | 18,550 | 25.9% | 10.0% |
| BUKIT MERAH | 143,870 | 36,570 | 25.4% | 12.0% |
| SERANGOON | 115,310 | 28,330 | 24.6% | 9.8% |
| BEDOK | 269,740 | 65,820 | 24.4% | 10.2% |
| KALLANG | 101,100 | 24,520 | 24.3% | 10.7% |
| ROCHOR | 11,770 | 2,800 | 23.8% | 10.6% |
| BISHAN | 87,100 | 20,180 | 23.2% | 9.5% |
| QUEENSTOWN | 100,310 | 22,560 | 22.5% | 11.2% |

Small areas give noisy shares because every cell is rounded to 10; that is why the second table starts at 1,000 residents. The CSV keeps every area.
