# Static data download (21 Oct 2026)

Files are in `coolcheck-data/static/` beside the repo (one folder per dataset, each with `provenance.json`; the folder also has `SOURCES.md`). Nothing was uploaded to Databricks. Script: `scripts/checks/download_static.py`. All calls were unauthenticated, from this computer, on 2026-10-21 between 12:43 and 12:44 SGT. **Unverified until read.**

## What was downloaded

| folder | what it is | source | agency | source last updated | bytes | rows or features |
|---|---|---|---|---|---|---|
| `census2020_pop_planning_area_age_sex` | Resident population by planning area/subzone, age group and sex, Census 2020 (CSV) | https://data.gov.sg/datasets/d_d95ae740c0f8961a0b10435836660ce0/view | SingStat | 2021-06-18 | 85,943 | 388 rows; 61 columns (a name column plus 5-year age bands for total, males and females); first row is the island total, 4,044,210 |
| `singstat_pop_pa_age_sex_floor_area_jun2026` | Residents by planning area/subzone, age group, sex and floor area, **June 2026** (CSV in a zip, extracted) | https://www.singstat.gov.sg/files/a2b9150d-9ed4-4c0b-ab20-a26035f95065.zip | SingStat | file dated 25 Sep 2026 (HTTP header) | 235,166 | 63,080 rows; 55 planning areas, 332 subzones; total 4,199,180 and 65+ 806,080 (my sums, rounded to 10 in the source) |
| `ura_mp2019_planning_area_boundary` | Master Plan 2019 Planning Area Boundary (No Sea), GeoJSON | https://data.gov.sg/datasets/d_4765db0e87b9c86336792efe8a1f7a66/view | URA | 2025-12-05 | 2,092,229 | 55 polygons (46 Polygon, 9 MultiPolygon); fields `PLN_AREA_N`, `PLN_AREA_C`, `REGION_N` |
| `eldercare_services` | Eldercare Services, GeoJSON | https://data.gov.sg/datasets/d_f0fd1b3643ed8bd34bd403dedd7c1533/view | MOH | 2024-06-06 | 176,532 | 133 points (see `check1.md`) |
| `community_clubs` | Community Clubs, GeoJSON | https://data.gov.sg/datasets/d_f706de1427279e61fe41e89e24d440fa/view | People's Association | 2024-06-06 | 167,626 | 125 points |
| `community_club_passion_wave_outlet` | Community Club / PAssion WaVe Outlet, GeoJSON (a newer, similar dataset I found in the catalogue; **not asked for**, kept because the guide's "Community Clubs" file is from 2024) | https://data.gov.sg/datasets/d_9de02d3fb33d96da1855f4fbef549a0f/view | People's Association | 2026-10-02 | 93,712 | 128 points |
| `parks` | Parks (NParks), GeoJSON | https://data.gov.sg/datasets/d_0542d48f0991541706b58059381a6eca/view | NParks | 2026-10-21 | 168,423 | 462 points (fields `NAME`, `X`, `Y`); points, not polygons, so "park share" by area cannot come from this file |
| `hdb_property_information` | HDB Property Information, CSV | https://data.gov.sg/datasets/d_17f5382f26140b1fdae0ba2ef6239d2f/view | HDB | 2026-10-08 | 948,464 | 13,392 rows; `blk_no`, `street`, `bldg_contract_town`, `total_dwelling_units`, `1room_rental`, `2room_rental`, `3room_rental`, `other_room_rental` and sold-flat counts; no coordinates or planning area |

Downloaded for inspection only and kept in scratch, not in the static folder: Park Connector Loop (`d_a69ef89737379f231d2ae93fd1c5707f`), Cycling Path Network (`d_8f468b25193f64be8a16fa7d8f60f553`), the 2013 EMA planning-area file (`d_47db177174ba5899aa9cee08797d9171`) and SingStat's yearly Senior Activity Centre / Active Ageing Centre counts (`d_0f70d7095a527be4ea443a7e30597896`).

## Licence and attribution

- **data.gov.sg datasets: Singapore Open Data Licence v1.0.** The licence page (https://data.gov.sg/open-data-licence, read 21 Oct) permits using, copying, distributing, modifying and adapting the data, commercially or not, and asks for a notice of the form "Contains information from {dataset name} accessed on {date}, which is made available under the terms of the Singapore Open Data Licence version 1.0" with a link to the licence. I read the licence page; I did **not** open the page of each dataset, and the licence is not in the API metadata. Only the Eldercare dataset page was seen to state it (in a search snippet). Treat the licence on the other seven as expected, not confirmed per dataset.
- **SingStat June 2026 file: licence not confirmed.** The SingStat terms-of-use page is built by JavaScript and its text could not be read by script; the file page states no licence or attribution. If the licence cannot be confirmed, use the data.gov.sg Census 2020 file (Open Data Licence) for the write-up, or read https://www.singstat.gov.sg/terms-of-use in a browser.

## Does SingStat have newer yearly planning-area figures? Yes

The SingStat "geographic distribution" page (read through a fetch tool that summarised it; the file links were then checked with HEAD requests, one file downloaded) lists "Singapore Residents by Planning Area / Subzone, Age Group, Sex and Floor Area of Residence" for **June 2011 to 2019, June 2020 to 2024, June 2025 and June 2026**, and a similar series by type of dwelling (June 2021 to June 2026). Details of the June 2026 file I downloaded:

- Same structure as Census 2020 in long form: planning area (`PA`), subzone (`SZ`), 5-year age group (`AG`, 0_to_4 up to 90_and_Over), `Sex`, floor area band (`FA`), `Pop`, `Time`. Counts are rounded to the nearest 10 (note 3 in the file). Date generated 25/9/2026.
- Island total 4,199,180 residents for June 2026 (my sum), against 4,044,210 in Census 2020, and residents aged 65 and over 806,080 (my sum).
- **Boundary caveat:** the file's own note says that for June 2026 planning areas refer to the URA **Master Plan 2025**. Its 55 planning-area names match the 55 names in the Master Plan 2019 boundary file I downloaded exactly, but the polygons may differ between the two master plans (not tested). A Master Plan 2025 planning-area boundary exists in the catalogue (`d_2cc750190544007400b2cfd5d7f53209`, 2026-02-27) and was **not downloaded**.
- Reading (mine): for "seniors per planning area" the June 2026 file is five years more recent than Census 2020 and gives the same age bands, so it is the better source for the exposure term. That is a decision for you (C1), because it also changes which boundary file to use, and because Census 2020 is the figure named in the brief and the deck.

## Other things found while searching the catalogue (not downloaded)

- URA Master Plan 2025 planning-area boundary (above).
- SingStat dataset "Senior Activity Centres And Active Ageing Centres, Annual" (counts only; used in check 1).
- NEA "Historical Air Temperature across Singapore" yearly CSVs for 2016 to 2024 (relevant to check 6's fallback).
- EMA household electricity by planning area on data.gov.sg exists only for 2009 to 2013 (check 13).

## Could not confirm

- The licence of each individual dataset page, and the licence of the SingStat file (above).
- That the Eldercare, Community Clubs and Parks files are complete and current (the first two were last updated in June 2024; Eldercare records are stamped 2016).
- Which Community Clubs file to use: the 2024 one (125 points) or the 2026-10-02 one (128 points). Not compared.
- Whether the Parks file is the right NParks file: the catalogue also has "NParks Parks and Nature Reserves" (`d_77d7ec97be83d44f61b85454f844382f`) and "Parks@SG" (HPB); I took the one called "Parks".
