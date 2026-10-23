# Attribution notices

What each surface of CoolCheck must show for the datasets it uses. Built 23 Oct 2026 by window E from:
- the dataset register, `docs/datasets.md` (section "Attribution notice per dataset", `926e186`), the source of every notice text below;
- the licence duties in the project Guide §A13, read from the terms saved in `../Docs/`;
- the refuge and park report, `docs/checks/refuge_park_access.md` (`de2a16f`), for which refuge and park files are used and how;
- data.gov.sg's dataset metadata for the NEA feed titles (calls recorded below).

My reading of the terms, not legal advice.

## Duties that apply to every dataset

- **Singapore Open Data Licence v1.0** covers every data.gov.sg dataset, and by their own terms EMA's and OneMap's datasets too. It requires, "in your products, applications or websites that Use the datasets, a conspicuous notice acknowledging the source of the datasets and including a link to the most recent version of this Licence". The "Contains information from … accessed on …" wording is the licence's example notice, not a required form. Link: https://data.gov.sg/open-data-licence.
- **No official status or endorsement:** every surface and every advisory says it is not official advice, and no agency logo is shown (the licence grants no rights over trademarks).
- **No personal data** is used, as the licence requires.
- **SingStat** (Terms of Use, "Last updated: 01 Oct 2026"): clause 11 puts its datasets under the Open Data Licence, which prevails. Clause 10 requires credit to the source (c), no analysis presented as the Government's (e), accurate reproduction (g; the counts are rounded to the nearest 10), removal on request (f), and no suggested association or endorsement (h). **Clause 25 requires written permission before hyperlinking to any SingStat page or content, so SingStat datasets are named by title and date, without links.**
- **EMA** (Terms of Use): the "Terms of Use of Datasets" are the Open Data Licence v1.0 with EMA as licensor (clause 20). **Clause 9 requires the notice to carry the date of access.** Clause 7 bars any suggestion of EMA endorsement. The website terms (clause 6) bar commercial reuse of the site without written permission, so EMA's figures are re-plotted from the workbook, and EMA's charts and the saved screenshots are never shown. EMA is named without hyperlinks to its site. Any EMA figure carries the workbook's notes: "Data for 2025 is as at Jun 2025"; the publication is "accurate as of Sep 2025"; planning areas follow the Singapore Land Authority's Aggregated Data Zone 2024; solar PV is excluded.
- **OneMap** (API Terms of Service, saved 21 Oct): **the saved terms have no attribution clause of their own; they say that use of the datasets is governed by the Singapore Open Data Licence.** Use is allowed commercially or not, and the access credentials must be kept secure and confidential. CoolCheck uses only the Search API, once, to geocode the HDB blocks, and shows no OneMap basemap (the AI/BI maps draw their own). The register offers notice 23 for the geocodes because they are Open Data Licence material.

## Where notices go

- **Dashboard:** the briefing dashboard (planning-area map and tiers, the top 10, the block drill-down, the refuge and park layers). The agent App shows areas and advisories derived from the same data, so it carries the dashboard's notices (§A13 names "the App").
- **Live page:** the live heat-stress page (`src/dashboards/live_heat_stress.lvdash.json`), which reads only `gold.latest_readings`: WBGT, rainfall and air temperature.
- **README:** the repository's front page. The repository holds code that uses the datasets and reports with figures derived from them.
- **Write-up:** the Devpost text, and the deck and video made from it.

A dataset's notice goes on a surface when the surface shows its data or anything derived from it. README and write-up carry every dataset in use; a dataset used in a sensitivity run only is reported there and not on the dashboard, unless the dashboard shows that run.

## Datasets in use (23 Oct 2026)

Numbers are the register's row and notice numbers. "Score" means the dataset feeds the area risk score or its cooling-access measures; "dashboard layer" means it is drawn or shown on the dashboard. The date of access is the register's; **only EMA's licence requires it** (clause 9). For the other rows it is the date in the register's notice.

| # | dataset | agency | where used | date of access | dashboard | live page | README | write-up |
|---|---|---|---|---|---|---|---|---|
| 1 | WBGT heat stress (real-time API) | National Environment Agency | score (the model's label and its P(High) heat term); live page readings | 20 October 2026 (see flag 4 on live dates) | yes | yes | yes | yes |
| 2 | Rainfall (real-time API); data.gov.sg title "Rainfall across Singapore" | National Environment Agency | score (model input); live page ("rain in the hour to …") | 20 October 2026 | yes | yes | yes | yes |
| 3 | 24-hour Weather Forecast (API); data.gov.sg title "24-hour Weather Forecast" | National Environment Agency | score (model input) | 20 October 2026 | yes | no | yes | yes |
| 4 | Air temperature (real-time API); data.gov.sg title "Air Temperature across Singapore" | National Environment Agency | live page only (D9) | 22 October 2026 | no | yes | yes | yes |
| 7 | Singapore Residents by Planning Area/Subzone, Age Group, Sex and Floor Area of Residence, June 2026 | Singapore Department of Statistics | score (residents aged 65+ and 75+ per area); dashboard figures | 21 October 2026 | yes, no link | no | yes, no link | yes, no link |
| 8 | Senior Activity Centres and Active Ageing Centres, Annual (counts only) | Singapore Department of Statistics | cited figure: "93 of about 223 AACs" on the dashboard's refuge layer and in the limitations (decision 8a, 23 Oct) | 21 October 2026 | yes | no | yes | yes |
| 9 | HDB Property Information | Housing & Development Board | score (blocks, dwelling units, rental flats); dashboard block drill-down | 21 October 2026 | yes | no | yes | yes |
| 11 | Eldercare Services (2016-stamped SAC layer) | Ministry of Health | sensitivity run only (refuges with the 2016 SACs added) | 21 October 2026 | no | no | yes | yes |
| 12 | Dementia Friendly Go-To-Points (GTPs) | Ministry of Health | score (the 93 AACs, a labelled partial refuge layer); dashboard layer | 21 October 2026 | yes | no | yes | yes |
| 14 | Community Club / PAssion WaVe Outlet (2026 file, filtered to clubs) | People's Association | score (the complete refuge layer, 113 club sites); dashboard layer | 21 October 2026 | yes | no | yes | yes |
| 16 | NParks Parks and Nature Reserves | National Parks Board | score (share of HDB dwelling units within 400 m of a park, nature reserves out); dashboard layer (area park share as context); sensitivity run with the reserves in | 21 October 2026 | yes | no | yes | yes |
| 19 | Master Plan 2025 Planning Area Boundary (No Sea) | Urban Redevelopment Authority | score (every area join and the block-to-area assignment); dashboard layer (the planning-area map) | 21 October 2026 | yes | no | yes | yes |
| 20 | Master Plan 2025 SDCP Park layer | Urban Redevelopment Authority | sensitivity run only (the park measure on URA's layer) | 21 October 2026 | no | no | yes | yes |
| 22 | Singapore Energy Statistics 2025, Chapter 3: Energy Consumption | Energy Market Authority | score (secondary, hedged term of the can't-cool-down index, shown with and without it) | 21 October 2026, **required** | yes, no link to EMA's site | no | yes, no link to EMA's site | yes, no link to EMA's site |
| 23 | OneMap Search API (address to coordinates) | Singapore Land Authority | score (the block coordinates behind the 400 m measures and each area's station reference point); dashboard block drill-down | 21 October 2026 | yes | no | yes | yes |

Every notice carries the same licence link: https://data.gov.sg/open-data-licence. Every dataset in use has a notice in the register, so nothing had to be written here.

## Notice texts (copied exactly from `docs/datasets.md`)

1. "Contains information from Heat stress (WBGT) real-time readings accessed on 20 October 2026 from National Environment Agency via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
2. "Contains information from Rainfall real-time readings accessed on 20 October 2026 from National Environment Agency via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
3. "Contains information from 24-hour Weather Forecast accessed on 20 October 2026 from National Environment Agency via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
4. "Contains information from Air temperature real-time readings accessed on 22 October 2026 from National Environment Agency via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
7. "Contains information from Singapore Residents by Planning Area/Subzone, Age Group, Sex and Floor Area of Residence, June 2026 accessed on 21 October 2026 from Singapore Department of Statistics which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
8. "Contains information from Senior Activity Centres and Active Ageing Centres, Annual accessed on 21 October 2026 from Singapore Department of Statistics via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
9. "Contains information from HDB Property Information accessed on 21 October 2026 from Housing & Development Board via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
11. "Contains information from Eldercare Services accessed on 21 October 2026 from Ministry of Health via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
12. "Contains information from Dementia Friendly Go-To-Points (GTPs) accessed on 21 October 2026 from Ministry of Health via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
14. "Contains information from Community Club / PAssion WaVe Outlet accessed on 21 October 2026 from People's Association via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
16. "Contains information from NParks Parks and Nature Reserves accessed on 21 October 2026 from National Parks Board via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
19. "Contains information from Master Plan 2025 Planning Area Boundary (No Sea) accessed on 21 October 2026 from Urban Redevelopment Authority via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
20. "Contains information from Master Plan 2025 SDCP Park layer accessed on 21 October 2026 from Urban Redevelopment Authority via data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
22. "Contains information from Singapore Energy Statistics 2025, Chapter 3: Energy Consumption accessed on 21 October 2026 from Energy Market Authority which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."
23. "Contains information from OneMap Search API accessed on 21 October 2026 from Singapore Land Authority (OneMap) which is made available under the terms of the Singapore Open Data Licence version 1.0 https://data.gov.sg/open-data-licence."

The register's note on combined notices also applies: "A short combined notice for the dashboard footer may be easier to read, but each dataset must still be named. One notice per page listing the datasets shown on it, with the one link, is my reading of what the licence asks, not a ruling."

## Not in use today (each has a register notice if it comes into use)

- **5, Meteorological Service Singapore historical daily records:** no notice in the register (no open licence stated, flag D). Not needed: M9 is not run (decided 23 Oct, 13:57).
- **6, Census 2020:** comparison only, superseded by row 7 under C1.
- **10, HDB Existing Building:** not fetched; its register notice has the date still to fill.
- **13, Community Clubs (2024 file):** compared only (`refuge_park_access.md`); the 2026 file (row 14) is used.
- **15, Parks (points):** superseded by the polygons (row 16).
- **17, Park Connector Loop:** the optional low-weight corridor term (M7) is not built.
- **18, Master Plan 2019 boundary:** comparison only.
- **21, Cycling Path Network:** cited only, kept in scratch.

If the write-up quotes a comparison that uses one of these, for example Census 2020 against June 2026, that dataset's register notice goes in the write-up and the README too.

## NEA feed titles (data.gov.sg metadata, read-only, no key)

The register's notices 1, 2 and 4 use descriptive names, and the register asks for the official titles to be copied from each dataset page before shipping. Lookups made on 23 Oct 2026 with `GET https://api-production.data.gov.sg/v2/public/api/datasets/<id>/metadata`, no `x-api-key` header, one call per dataset, about 2 s apart. The full IDs of rows 2 and 4 come from the project notes (`DAISI - Info.txt`, `To Do.md`); row 3's is in the register. The raw responses were kept outside the repository.

| # | dataset ID | called (SGT) | HTTP | title on data.gov.sg | managed by | last updated |
|---|---|---|---|---|---|---|
| 2 | `d_6580738cdd7db79374ed3152159fbd69` | 17:05:15 | 200 | Rainfall across Singapore | National Environment Agency | 2025-12-16 |
| 3 | `d_ce2eb1e307bda31993c533285834ef2b` | 17:05:17 | 200 | 24-hour Weather Forecast | National Environment Agency | 2025-12-16 |
| 4 | `d_66b77726bbae1b33f218db60ff5861f0` | 17:05:19 | 200 | Air Temperature across Singapore | National Environment Agency | 2025-12-16 |
| 1 | not recorded | not looked up | - | not found | - | - |

For WBGT (row 1), one more read-only call was made at 17:05:33 to `GET https://api-production.data.gov.sg/v2/public/api/collections/1459/metadata`, the collection that rows 2 and 4 belong to (HTTP 200, "Realtime Weather Readings across Singapore", National Environment Agency). It lists five datasets: rows 4 and 2, and `d_2d3b0c4da128a9a59efca806441e1429`, `d_534cf203023b51f51f879145ccc56ff9` and `d_7677738484067741bf3b56ab5d69c7e9`, which were not looked up. No catalogue crawl was made (about 470 calls).

## Flags

1. **data.gov.sg API terms not saved.** The real-time API rows (1 to 4) rely on the data.gov.sg API terms (https://data.gov.sg/privacy-and-terms), which are not in `../Docs/` (checked 23 Oct; only the Open Data Licence and the SingStat terms are in its root).
2. **EMA's page footer and Excel download link never captured.** The saved Chapter 3 page ends before the footer's terms or copyright wording, and the download box (screenshot 7) shows no URL (§A13 items 1 and 4). Record both from the browser when the page is next opened.
3. **WBGT's official title and dataset ID are not found** (table above). Notice 1 keeps its descriptive name until the title is copied from the dataset page, or found with a catalogue crawl or by looking up the three unchecked datasets of collection 1459.
4. **Register notices 2 and 4 use descriptive names**, now known to differ from the data.gov.sg titles "Rainfall across Singapore" and "Air Temperature across Singapore"; notice 3's name already matches. This file copies the register as it stands; updating the register is for its owner. The register also says a live feed's notice should use the date of the data shown, its "last updated" time, rather than the first pull.
5. **The live page's notice is not the register's text.** `src/dashboards/live_heat_stress.lvdash.json` carries one combined notice: "Contains information from NEA's WBGT, Rainfall and Air Temperature real-time datasets, accessed continuously from data.gov.sg, which is made available under the terms of the [Singapore Open Data Licence version 1.0](https://data.gov.sg/open-data-licence)." It names the three datasets by description and gives no date. It fits the register's note on combined notices, but should use the official titles once flag 3 is settled.
