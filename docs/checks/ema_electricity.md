# EMA electricity: the hot-month rise in 1–2 room flats

Script: `scripts/static/ema_electricity.py`; ratios: `src/coolcheck/electricity.py`. Output: `coolcheck-data/analysis/ema_area_electricity.csv` (outside the repo). Nothing was loaded to Unity Catalog.

<!-- mlflow -->
MLflow: experiment `coolcheck-risk-score` in the trial workspace (your user folder), ID `962587213821840`; `electricity` run `d025205e33f04f97ae5370c1c770da54`; logged 2026-10-23 19:37 SGT from git `05d080a` with these code files not yet committed (their sha256 are logged; a git_commit tag is added once the commit's files match).
<!-- /mlflow -->

Source: `SES_tidy.xlsx.coredownload.xlsx` (EMA, Singapore Energy Statistics 2025; sha256 `310aa7f2d3a2...`), sheet T3.5, "Average Monthly Household Electricity Consumption by Planning Area & Dwelling Type": 8,033 monthly 1-room / 2-room rows, 2005 to 2025, for 30 planning areas, 5 regions and "Overall". `Annual` rows are ignored.

## Result

- **The first reading, reproduced:** the mean over area-years of each year's April–June / November–February ratio, 1–2 room, 2015 to 2024: **1.0995 over 280 area-years** (the first reading was 1.09 over 280). EMA's "Overall" row: pooled over the same years 1.0889; the mean of its 10 yearly ratios 1.0898. At two decimals the area-year mean is 1.10 (a rise of about 10%) and "Overall" pooled 1.09 (about 9%). The area-years include areas with fewer than ten years: Bukit Timah 9 years (mean 1.1862); Tengah 1 year (mean 2.0561).
- **Coverage among the 32 rated areas:** 30 have 1-room / 2-room rows by name; **28 have all three of 2022, 2023 and 2024**, so the term has a value; 4 do not and get 0.5 in V: CHANGI, DOWNTOWN CORE, TANGLIN, TENGAH.
- **Names:** 30 EMA planning-area names, upper-cased, against Master Plan 2025 `PLN_AREA_N`: all match. EMA's areas follow the Singapore Land Authority's Aggregated Data Zone 2024, not URA's Master Plan 2025, so a boundary can differ slightly.
- **Reading:** a ratio above 1 means more electricity per account in April to June than in November to February. A smaller rise "may indicate" less air-con use in the hot months; it does not show it, and it says nothing about any one household.

## Per area (1–2 room)

| planning area | region | 2022 | 2023 | 2024 | mean 2022–2024 (V input) | mean 2015–2024 | years 2015–2024 | rated |
|---|---|---|---|---|---|---|---|---|
| ANG MO KIO | North East Region | 1.0359 | 1.1203 | 1.1383 | 1.0982 | 1.0912 | 10 | yes |
| BEDOK | East Region | 1.0945 | 1.1506 | 1.1611 | 1.1354 | 1.1178 | 10 | yes |
| BISHAN | Central Region | 1.0430 | 1.1737 | 1.2518 | 1.1562 | 1.0787 | 10 | yes |
| BUKIT BATOK | West Region | 1.0881 | 1.2362 | 1.1740 | 1.1661 | 1.1080 | 10 | yes |
| BUKIT MERAH | Central Region | 1.0201 | 1.0931 | 1.1053 | 1.0728 | 1.0645 | 10 | yes |
| BUKIT PANJANG | West Region | 0.7869 | 1.1657 | 1.1311 | 1.0279 | 1.0533 | 10 | yes |
| BUKIT TIMAH | Central Region | 1.0491 | 1.1002 | 1.1956 | 1.1149 | 1.1862 | 9 | yes |
| CHANGI | East Region |  |  |  |  |  | 0 | yes |
| CHOA CHU KANG | West Region | 1.0318 | 1.0129 | 1.1538 | 1.0662 | 1.0786 | 10 | yes |
| CLEMENTI | West Region | 1.0385 | 1.0719 | 1.1230 | 1.0778 | 1.0578 | 10 | yes |
| GEYLANG | Central Region | 1.0047 | 1.1325 | 1.1292 | 1.0888 | 1.0987 | 10 | yes |
| HOUGANG | North East Region | 1.0382 | 1.1100 | 1.1598 | 1.1027 | 1.1144 | 10 | yes |
| JURONG EAST | West Region | 1.0609 | 1.1487 | 1.1348 | 1.1148 | 1.1205 | 10 | yes |
| JURONG WEST | West Region | 1.0355 | 1.0813 | 1.1526 | 1.0898 | 1.0673 | 10 | yes |
| KALLANG | Central Region | 1.0340 | 1.1371 | 1.1297 | 1.1003 | 1.0850 | 10 | yes |
| MARINE PARADE | Central Region | 1.0274 | 1.1631 | 1.1143 | 1.1016 | 1.1365 | 10 | yes |
| NOVENA | Central Region | 1.0283 | 1.1123 | 1.1382 | 1.0929 | 1.0470 | 10 | yes |
| OUTRAM | Central Region | 1.0211 | 1.0753 | 1.0732 | 1.0565 | 1.0540 | 10 | yes |
| PASIR RIS | East Region | 1.0696 | 1.1533 | 1.1736 | 1.1322 | 1.1507 | 10 | yes |
| PUNGGOL | North East Region | 0.9903 | 1.1194 | 1.1059 | 1.0719 | 1.0842 | 10 | yes |
| QUEENSTOWN | Central Region | 1.0187 | 1.1175 | 1.1305 | 1.0889 | 1.0804 | 10 | yes |
| ROCHOR | Central Region | 1.0679 | 1.1169 | 1.1179 | 1.1009 | 1.1113 | 10 | yes |
| SEMBAWANG | North Region | 1.0284 | 1.1057 | 1.1300 | 1.0881 | 1.0480 | 10 | yes |
| SENGKANG | North East Region | 0.9907 | 1.0606 | 1.2318 | 1.0944 | 1.0905 | 10 | yes |
| SERANGOON | North East Region | 1.0619 | 1.1690 | 1.1839 | 1.1383 | 1.1413 | 10 | yes |
| TAMPINES | East Region | 1.0906 | 1.1760 | 1.1512 | 1.1393 | 1.1242 | 10 | yes |
| TENGAH | West Region |  |  | 2.0561 |  | 2.0561 | 1 | yes |
| TOA PAYOH | Central Region | 1.0558 | 1.1354 | 1.1538 | 1.1150 | 1.0988 | 10 | yes |
| WOODLANDS | North Region | 1.0468 | 1.0899 | 1.1418 | 1.0928 | 1.1091 | 10 | yes |
| YISHUN | North Region | 1.0642 | 1.1526 | 1.1287 | 1.1152 | 1.1023 | 10 | yes |

## Method

- A year's ratio is mean(Apr, May, Jun of Y) / mean(Nov and Dec of Y − 1, Jan and Feb of Y), and needs all seven months.
- An area's value (the V input, `hot_ratio_mean`) is the mean of its 2022, 2023 and 2024 ratios when all three exist; otherwise it has none, and V holds the component at 0.5.
- The first reading: every area-year ratio of 2015 to 2024 that exists (planning areas only, not regions or "Overall"), averaged with equal weight.
- "Overall" pooled: the mean of all its April to June values over 2015 to 2024 over the mean of all its November-to-February values (Nov 2014 to Feb 2024).

## EMA's notes, to quote with any figure

- Numbers may not add up because of rounding (a).
- Planning areas follow the Singapore Land Authority's Aggregated Data Zone 2024 (b).
- A missing or zero value can be nil, negligible or not applicable (c, d); "s" means suppressed.
- Solar PV statistics are excluded (e).
- "Data for 2025 is at Jun 2025." (the sheet's last line); "The information published in SES 2025 is accurate as of Sep 2025." (the workbook's contents page); "Source: Energy Market Authority (EMA)".

## Attribution (EMA's terms, clause 9: the notice carries the date of access)

> Contains information from Singapore Energy Statistics 2025, Chapter 3: Energy Consumption accessed on 21 October 2026 from Energy Market Authority which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence.

EMA is named without a hyperlink to its site, and EMA's own charts are not shown (website terms, clause 6).
