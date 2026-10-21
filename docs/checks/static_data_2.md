# Static data 2: Active Ageing Centres and park polygons (21 Oct 2026)

The two items still open in `CoolCheck Guide.md` §16. Script: `scripts/checks/static_data_2.py` (reads only files already in `static/`; its output is `coolcheck-data/analysis/static_data_2_run.log`). Downloads were made from this computer, unauthenticated, between 22:44 and 22:49 SGT, with the helpers in `scripts/checks/datagov.py`. No geocoding, no OneMap call, nothing uploaded to Databricks, nothing committed. **Unverified until read.**

How I searched: I pulled the whole data.gov.sg catalogue listing (4,664 datasets, 467 pages) and searched dataset names (and, for AAC wording, descriptions) with keyword patterns. A dataset with an unrelated name could have been missed.

## Verdicts

| item | verdict |
|---|---|
| (a) Current list of Active Ageing Centres | **No complete list exists as open data that I could find.** One official open file holds a partial list: **93 AACs** (about 42% of SingStat's 223 for 2024) with name, address, 6-digit postal code and coordinates. Usable as a partial list only, with the gap stated. The complete listing sits on AIC / Age Well SG / SupportGoWhere pages whose terms do not allow copying (below), so I did not scrape. |
| (b) Park polygons | **Yes.** NParks "Parks and Nature Reserves": 462 polygons, Open Data Licence. Usable. The park share is very sensitive to what counts as a park (below). |
| (b) Park Connector Loop | **Yes, available** (878 line features, about 336.5 km). Downloaded and usable. |

## (a) Active Ageing Centres

### What was found

| source | what it is | rows | AAC content | licence | use? |
|---|---|---|---|---|---|
| **MOH Dementia Friendly Go-To-Points (GTPs)**, data.gov.sg `d_e2d10e591bc8560b8946a0da24790fa5` | Places that act as dementia go-to points (MRT stations, community clubs, care homes, AACs, others), GeoJSON points | 831 | **93 named Active Ageing Centre / Hub / AAC**; 4 more named Senior Activity Centre (SAC) | Open Data Licence (below) | **Yes, as a partial list** |
| Eldercare Services (MOH), `d_f0fd1b36...` (already held) | 133 points stamped 2016 | 133 | 0 named AAC; 60 SAC + 6 Silver ACE (`check1.md`) | Open Data Licence | Keep as the older SAC layer only |
| SingStat "Senior Activity Centres And Active Ageing Centres, Annual", `d_0f70d709...` | Counts per year, no locations | 4 series | 223 AACs for 2024 | Open Data Licence | Count for the gap statement only |
| AIC "Active Ageing Centres" page (aic.sg) | Interactive locator; shows no centres until a location is given | n/a | full list, behind the locator | Terms: see below | **No** |
| Age Well SG (agewellsg.gov.sg), run by MOH | Information page; links its locator to `go.gov.sg/aacgowhere`, which redirects to SupportGoWhere | n/a | none on the page | Terms: see below | **No** |
| SupportGoWhere (supportgowhere.life.gov.sg) | JavaScript-only app | n/a | holds the locator | **Terms could not be read** (the page needs JavaScript and the browser extension was not connected) | **No**: terms unconfirmed, not tried |
| MSF "Social Service Agencies" `d_736e30b5...` | Directory of NCSS member organisations, not centres | not downloaded | no | Open Data Licence expected | Read from metadata only; not an AAC list |
| Operator sites (THK, NTUC Health, MWS and others) | Each lists its own centres | not attempted | partial each | each has its own terms | Not attempted: dozens of sites with separate terms |

### The Go-To-Points file in detail

- File: `coolcheck-data/static/moh_dementia_friendly_go_to_points/d_e2d10e591bc8560b8946a0da24790fa5.geojson`, 451,501 bytes, source last updated 2026-08-20, downloaded 2026-10-21 22:49 SGT, sha256 in `provenance.json`.
- Fields: `NAME`, `ADDRESS`, `POSTAL_CODE`, `DESCRIPTION` (opening hours and phone), `X_ADDR`, `Y_ADDR`, `OBJECTID`, `INC_CRC`, `FMEL_UPD_D`. Geometry is a Point on all 831 rows (coordinate range not checked), so no geocoding is needed for these rows.
- AAC rows (by name pattern in the script, a heuristic): **93**, with 93 distinct names, 93 distinct postal codes, and all 93 postal codes are 6 digits. Record update stamps for those 93: 2024 (64), 2025 (10), 2026 (19). The 4 SAC rows are extra.
- **Why it is partial:** the file lists sites that serve as dementia go-to points, not every AAC. The 93 are a self-selected subset; I do not know how they were chosen, so I cannot say whether they are biased towards certain towns or operators. 93 of 223 is 42%.
- **Overlap with the old file:** Eldercare has 66 points named SAC / Silver ACE / AAC (66 distinct postal codes). 43 of those share a postal code with the GTP AAC and SAC rows; the union is 120 distinct postal codes. 120 is not a count of AACs: the Eldercare rows are stamped 2016, and SingStat's page says SACs converted to AACs, so some of the 43 matches are the same centre under a new name, and some Eldercare-only rows may have closed or moved (not checked).
- **Data defects:** 22 of 831 names contain the Unicode replacement character U+FFFD where a space or apostrophe was lost in the source (for example "Pearl?s Hill Care Home"). Clean before display.

### Terms read (from saved HTML of the pages, 21 Oct 2026)

- **AIC** (https://www.aic.sg/terms-of-use): clause 7.2, "no part of the Website may be modified or reproduced without obtaining our prior written permission"; clause 5.1, "Caching or framing of or linking to this Website or any of its contents thereof, is strictly prohibited." No clause on robots and none on data reuse or an open licence. The locator page has no download or API. **Not usable without AIC's written permission.**
- **Age Well SG** (https://www.agewellsg.gov.sg/terms-of-use/): maintained by and belongs to the Ministry of Health; contents "shall not be reproduced, republished, uploaded, posted, transmitted or otherwise distributed in any way, without the prior written permission of the Ministry of Health"; caching, linking and framing prohibited without permission; "the use of Datasets (as defined in the Singapore Open Data Licence ...) contained in this Website is subject to the Singapore Open Data Licence". The page I fetched has no dataset and no list, so the permission to reuse datasets does not help here.
- I did not open the SupportGoWhere API or any backend behind the locators.

### What I recommend (for you to decide)

1. Use the 93 GTP AACs plus the 4 GTP SACs as the working AAC layer, labelled "partial: 93 of 223 AACs in SingStat's 2024 count". Keep Eldercare's 66 as a separate layer, flagged 2016, and deduplicate by postal code. Keep Community Clubs as refuges too.
2. State the gap: nearest-refuge distances computed from a partial list overstate distances in towns where the AACs are missing. This should show up in the limitations and, if time allows, as a sensitivity run (with and without the Eldercare layer).
3. Ask for the full list. The cheap route is a written request to MOH or AIC for the AAC list under the Open Data Licence, or via the mentor's AAC contact. I did not send anything.

## (b) Park polygons and the Park Connector Loop

### NParks Parks and Nature Reserves (polygons)

- `coolcheck-data/static/nparks_parks_and_nature_reserves/d_77d7ec97be83d44f61b85454f844382f.geojson`, 3,095,917 bytes, GeoJSON, source last updated 2026-10-21 (data.gov.sg metadata), downloaded 2026-10-21 22:44 SGT.
- **462 features**: 384 Polygon, 78 MultiPolygon. Fields: `OBJECTID_1`, `L_CODE`, `NAME`, `N_RESERVE`, `INC_CRC`, `FMEL_UPD_D`, `SHAPE_1.AREA`, `SHAPE_1.LEN`. All record stamps are 2026. 2 polygons are invalid as supplied (HortPark, Mount Faber Park); the script repairs them with `make_valid`.
- **The 462 names are identical to the 462 names in the Parks point file we already hold**, so this is the polygon version of the same layer; the points file is not needed for the park share.
- Described by NParks as "indicative Managed Areas of Parks" under NParks' purview. It is not all green space: it leaves out housing-estate greenery and anything not managed by NParks.
- Sum of polygon areas 65.72 km2, union 65.34 km2, so a small overlap of 0.38 km2 (65.72 minus 65.34); compute shares on the union. 7 features have `N_RESERVE = 1`; the largest are Central Catchment Nature Reserve 30.6 km2 and Pulau Ubin and Chek Jawa 10.09 km2.
- Areas above use a flat approximation at one fixed latitude (a constant in the script) (one polygon, Tai Keng Gardens PG, the first in the file: 9,134 m2 measured against 9,073 in `SHAPE_1.AREA`, 0.7% off; printed in the run log). Use a projected CRS (SVY21) for the real feature.
- **Licence:** I read the dataset page's HTML: "Free forever for personal or commercial use, under the Open Data Licence." Contact listed in the metadata is an NParks officer. The page text said the data is refreshed about every 6 months and shows November 2025 data (from a page summary, not checked); the metadata stamp of 2026-10-21 looks like the portal's own refresh date, because the Parks point file carries the same stamp.

### The park share depends on the definition (a real result, not a footnote)

Park share = park area / planning-area land area, Master Plan 2025 boundaries (55 areas, 802.3 km2 land):

| park layer | features | union km2 | area share: median, max | areas with no park | top areas |
|---|---|---|---|---|---|
| NParks, all 462 | 462 | 65.34 | 0.019, 0.835 | 10 | Central Water Catchment 0.835, Bukit Panjang 0.384, Museum 0.315, Bishan 0.173 |
| NParks without the 7 nature reserves and Pulau Ubin / Chek Jawa | 454 | 21.65 | 0.018, 0.315 | 10 | Museum 0.315, Bukit Panjang 0.203, Bishan 0.173, Punggol 0.122 |
| URA Master Plan 2025 SDCP Park layer | 426 | 19.65 | 0.005, 0.258 | 7 | Southern Islands 0.258, Bukit Panjang 0.149, North-Eastern Islands 0.138, Straits View 0.134 |

- With the reserves in, Central Water Catchment scores 0.835 because of a reserve few seniors can use for cooling. I recommend excluding `N_RESERVE = 1` (and Pulau Ubin / Chek Jawa, which is not in the flag) for a refuge-style park share. That is a modelling decision for you.
- The correlation of area-level park share between NParks (without reserves) and the URA layer is **0.30** (NParks all: 0.24). The two sources disagree on which areas are green, so the choice of source moves the ranking. If park share goes into the score, run the sensitivity with both and report it.
- The URA SDCP Park layer is a plan, not a survey: 117 of its 426 polygons are `PRP_STATUS = INTERIM` (planned) and 309 `PERMANENT`. I downloaded it for comparison only (`static/ura_mp2025_sdcp_park/`, 2,106,052 bytes, source last updated 2026-01-30). I would not use it as the main park layer.
- **Not downloaded:** URA "Master Plan 2025 Land Use Layer" (`d_a8c3546b26712e35021f3a681d0353ae`, about 190 MB, updated 2026-03-27; fields include `LU_DESC`) and the newer "Amendment to Master Plan 2025 Land Use Layer" (`d_7a03324b...`, about 190 MB, updated 2026-09-21). Size and dates are from the data.gov.sg metadata, read on 21 Oct 2026. Zoning "park" / "open space" in this layer is the usual basis for green share and would be a third definition. Download only if you want it; say which.

### Park Connector Loop: available

- `coolcheck-data/static/nparks_park_connector_loop/d_a69ef89737379f231d2ae93fd1c5707f.geojson`, 2,008,356 bytes, GeoJSON, source last updated 2026-07-15, downloaded 2026-10-21 22:45 SGT.
- **878 features** (784 LineString, 94 MultiLineString), about **336.5 km** (flat approximation; `check2.md` has 336.1 km by haversine). Fields: `OBJECTID`, `PARK`, `PCN_LOOP`, `MORE_INFO`, `INC_CRC`, `FMEL_UPD_D`, `SHAPE.LEN`. Record stamps: 2025 (873), 2026 (5). Seven loop names (Northern Explorer 250 segments, Central Urban 188, Western Adventure 164, Southern Ridges 147, Eastern Coastal 72, North Eastern Riverine 49, Urban Central 8 — "Central Urban" and "Urban Central" look like one loop under two spellings; not checked).
- Licence: same statement on the dataset page. Usable. The Cycling Path Network (`check3.md`) was not asked for here and was not downloaded.

## Licences (read this session)

I opened the dataset page for each of these and found the same sentence in the HTML: "Free forever for personal or commercial use, under the Open Data Licence." — NParks Parks and Nature Reserves, Park Connector Loop, URA MP2025 SDCP Park, MOH Dementia Friendly Go-To-Points, MOH Eldercare Services, SingStat Senior Activity Centres And Active Ageing Centres, URA MP2025 Land Use. The licence terms themselves are in `static_data.md` (Singapore Open Data Licence v1.0, attribution notice, no endorsement, no personal data). The Go-To-Points rows hold organisation addresses and phone numbers of places, not people.

The attribution line for the product, per dataset: "Contains information from {dataset name} accessed on 21 Oct 2026 from data.gov.sg which is made available under the terms of the Singapore Open Data Licence version 1.0 (https://data.gov.sg/open-data-licence)."

## Files added

| folder under `coolcheck-data/static/` | bytes | `provenance.json` | `SOURCES.md` row |
|---|---|---|---|
| `nparks_parks_and_nature_reserves` | 3,095,917 | yes | yes |
| `nparks_park_connector_loop` | 2,008,356 | yes | yes |
| `ura_mp2025_sdcp_park` | 2,106,052 | yes | yes |
| `moh_dementia_friendly_go_to_points` | 451,501 | yes | yes |

`SOURCES.md` was regenerated from all `provenance.json` files (same method as `download_static.py`); the diff against the old file is the four new rows only. The licence text in these four provenance files is the sentence read on each page. The rows from the first download still carry the older "page not read" wording.

## Could not confirm

- Whether the 93 GTP AACs are a random or a biased subset of the 223, and how many of the 223 are missing in each town.
- Whether any Eldercare-only SAC is closed or now an AAC under another name.
- The SupportGoWhere terms, and whether it exposes the AAC list in any form (JavaScript page; browser extension not connected).
- The AAC name matching is a keyword pattern; a centre without those words in its name would be missed (it can only lower the 93).
- The update date of the NParks content (portal stamp 2026-10-21; page summary said November 2025).
- Whether the catalogue holds an AAC list under a name my patterns missed.

## Left uncommitted

New: `docs/checks/static_data_2.md`, `scripts/checks/static_data_2.py`. Outside git: the four folders, `SOURCES.md`, and `coolcheck-data/analysis/static_data_2_run.log`.
