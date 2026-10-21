# Checks 4 and 13: EMA household electricity by planning area

Script: `scripts/checks/check4_13_ema.py`; run 2026-10-21 12:53 SGT. **Unverified until read. Check 4 is NOT answered; check 13 is answered only for an old stand-in file.**

## Check 4: terms of use for the EMA Excel download

### What was tested

Three unauthenticated GET requests to the EMA website, one each (no retries, no attempt to bypass any protection):

| URL | HTTP | bytes | what came back |
|---|---|---|---|
| https://www.ema.gov.sg/resources/singapore-energy-statistics | 200 | 845 | bot-protection (Incapsula) page, no content |
| https://www.ema.gov.sg/resources/singapore-energy-statistics/chapter3 | 200 | 839 | bot-protection (Incapsula) page, no content |
| https://www.ema.gov.sg/terms-of-use | 200 | 839 | bot-protection (Incapsula) page, no content |

### Result

- The EMA site answered every request with a short page that loads an Incapsula bot-protection script, not the content. From a script on this computer the Singapore Energy Statistics page, its Chapter 3 page and the terms of use page could not be read, so **the Excel download link, the period it covers and the terms of use were not read. Check 4 is not answered.**
- Claude in Chrome (a real browser) was tried and was not connected, so no browser read was made either.
- Search results (not opened pages) say EMA's Chapter 3 has an 'Average Monthly Household Electricity Consumption by Planning Area' section with data as at June 2025 and that the FAQ places it in Tables 3.4 and 3.5. This comes from a search snippet and is **not confirmed**.

### Fallback if the terms or the file are not available (agreed 19 Oct)
Drop electricity from the can't-cool-down index and say so. A stand-in exists on data.gov.sg (below) but it is a 2013 snapshot.

### What you need to do (user-only; needs a browser)
Open the EMA Singapore Energy Statistics Chapter 3 page, find the planning-area table, note the Excel link, the latest period, and the terms of use / copyright wording in the page footer; paste them here.

## Check 13: do 1-2 room values exist for every planning area?

### What was tested

The only EMA planning-area files reachable are on data.gov.sg (Singapore Open Data Licence), one per year 2009 to 2013. Tested: `d_47db177174ba5899aa9cee08797d9171` 'Average Monthly Household Electricity Consumption by URA Planning Area & Dwelling Type, 2013' (EMA, 55 features, records stamped ['20140731']). Columns: `TOTAL`, `ONE_TO_TWO_RM`, `THREE_RM`, `FOUR_RM`, `FIVE_RM_EXEC_FLATS`. Units are not stated in the file (kWh per month is my reading; not confirmed).

### Result (2013 file only)

- Planning areas in the file: 55. In the Master Plan 2019 boundary file: 55. In the boundary file but not in this file: none. In this file but not in the boundary file: none.
- Areas with a TOTAL above 0: **29**. Areas with TOTAL = 0 in every column (26): BOON LAY, CENTRAL WATER CATCHMENT, CHANGI, CHANGI BAY, DOWNTOWN CORE, LIM CHU KANG, MANDAI, MARINA EAST, MARINA SOUTH, MUSEUM, NEWTON, NORTH-EASTERN ISLANDS, ORCHARD, PAYA LEBAR, PIONEER, RIVER VALLEY, SELETAR, SIMPANG, SINGAPORE RIVER, SOUTHERN ISLANDS, STRAITS VIEW, SUNGEI KADUT, TENGAH, TUAS, WESTERN ISLANDS, WESTERN WATER CATCHMENT.
- **Areas with TOTAL above 0 but a 1-2 room value of 0 or missing: 2** (BUKIT TIMAH, TANGLIN).
- Other zero cells among populated areas: THREE_RM: PASIR RIS.
- Implausible-looking cells (by comparison with the other columns; not confirmed errors): CHOA CHU KANG ONE_TO_TWO_RM = 160.4, WOODLANDS ONE_TO_TWO_RM = 147.7, SEMBAWANG THREE_RM = 31.2, BISHAN ONE_TO_TWO_RM = 135.6, PASIR RIS ONE_TO_TWO_RM = 147.2, HOUGANG ONE_TO_TWO_RM = 155.5, SERANGOON ONE_TO_TWO_RM = 157.9.

Populated areas, as in the file:

| planning area | TOTAL | ONE_TO_TWO_RM | THREE_RM | FOUR_RM | FIVE_RM_EXEC_FLATS |
|---|---|---|---|---|---|
| ANG MO KIO | 318.1 | 164.6 | 280.7 | 376.7 | 437.8 |
| BEDOK | 349.6 | 156.3 | 278.5 | 385 | 471.4 |
| BISHAN | 403.9 | 135.6 | 268.4 | 396 | 474.6 |
| BUKIT BATOK | 362.2 | 148 | 267.5 | 380.3 | 465 |
| BUKIT MERAH | 319.3 | 154.3 | 285.7 | 379.2 | 445.5 |
| BUKIT PANJANG | 380.9 | 158.4 | 262.7 | 360.8 | 434.8 |
| BUKIT TIMAH | 395.2 | 0 | 280 | 373.7 | 463.5 |
| CHOA CHU KANG | 406.5 | 160.4 | 275.5 | 378.1 | 459.9 |
| CLEMENTI | 318.2 | 135.3 | 267.1 | 361 | 447.2 |
| GEYLANG | 341.8 | 168.1 | 283.3 | 406.1 | 489.2 |
| HOUGANG | 397.2 | 155.5 | 279.4 | 396 | 493.4 |
| JURONG EAST | 361.5 | 150.6 | 271.7 | 371.1 | 444.2 |
| JURONG WEST | 393.9 | 188.7 | 278.7 | 387.9 | 461.6 |
| KALLANG | 316.2 | 141 | 292.5 | 388 | 455 |
| MARINE PARADE | 324.4 | 192.8 | 289.5 | 360.3 | 436.4 |
| NOVENA | 350.4 | 187.7 | 302.4 | 372.9 | 484 |
| OUTRAM | 270.7 | 139.8 | 285.6 | 380.7 | 441.9 |
| PASIR RIS | 481 | 147.2 | 0 | 424 | 521.9 |
| PUNGGOL | 363.8 | 155.5 | 211.6 | 327.8 | 435.6 |
| QUEENSTOWN | 298.4 | 164.1 | 263.8 | 346.5 | 442.5 |
| ROCHOR | 329.6 | 186.6 | 298.4 | 373.6 | 487.7 |
| SEMBAWANG | 408.9 | 163.8 | 31.2 | 365.5 | 448.1 |
| SENGKANG | 395 | 165.9 | 226 | 363.7 | 447 |
| SERANGOON | 397.1 | 157.9 | 271.1 | 396.4 | 502.3 |
| TAMPINES | 422 | 171.2 | 297.5 | 418.5 | 509.6 |
| TANGLIN | 415.9 | 0 | 335.3 | 396.7 | 451.8 |
| TOA PAYOH | 326.3 | 158.8 | 290.1 | 370.3 | 443.7 |
| WOODLANDS | 402.5 | 147.7 | 271.5 | 377.2 | 476.3 |
| YISHUN | 387.2 | 174.7 | 284.8 | 402.9 | 505.3 |

### Reading

- In the 2013 file, **26 of 55 areas carry zeros in every column** (my inference, not stated in the file: the columns are flat types, so areas with no flats of those types show zeros) and 2 populated areas have no 1-2 room value. So the answer for this file is **no, not for every planning area**. Whether the current EMA Excel (to 1H 2025) behaves the same is **not known** because that file could not be reached.
- The file uses 2013-era area names; the boundary comparison above shows whether they match Master Plan 2019 names.

### Fallback (agreed 19 Oct)
If the current file also lacks 1-2 room values, the proxy cannot cover every area: drop it from the can't-cool-down index and say so, or use the 3-room column (and say that). Rental flats per block (HDB Property Information) already cover block-level vulnerability.

## Could not confirm

- Everything about the current EMA Excel: link, period, units, columns, terms of use (blocked from scripts; needs your browser).
- Whether EMA's current table has the same dwelling-type columns as the 2009 to 2013 data.gov.sg files.
- The units and the cause of the zeros in the 2013 file.

