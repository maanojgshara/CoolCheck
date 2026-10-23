# HDB Elderly dataset, opened once (D3, PT 12)

Opened 23 Oct 2026, 16:55 SGT (window A): one download with `scripts/checks/datagov.py` from this computer (metadata, the signed link, the file). The file was kept in the session scratchpad only, not in the repo or `coolcheck-data/`.

- Dataset: "HDB Elderly and Future Elderly Resident Population by Geographical Distribution", Housing & Development Board, `d_4180067b350bc9839a4cea487841d5d1` on data.gov.sg (the brief lists it as "HDB Elderly Population by Planning Area").
- File: CSV, 6,580 bytes, sha256 `cbfbda12b1085c16d60ac3ba0a4b9f5bd43a765268c3e6fc6bfd8eb3dae59f3f`.
- Metadata: coverage 1 Jan 2003 to 1 Jan 2018; created 25 Oct 2021; last updated 21 Oct 2026 (the rows still end in 2018); the licence field is empty, so the platform's Singapore Open Data Licence applies.

## Answer

- **Town-level: yes.** The rows are 25 HDB towns and estates (for example "Central Area" and "Kallang/Whampoa"), not blocks and not planning areas.
- **It stops at 2018.** It holds four survey years: 2003, 2008, 2013 and 2018 (the column is "SHS year", HDB's Sample Household Survey).
- So it cannot give elderly density by block or by today's planning areas, and its newest figures are eight years old. This supports D3 as decided on 19 Oct: keep it out of the build and list it under "datasets considered and not used". Closing D3 is your call.

## What the file holds

- 200 rows: 4 years × 2 groups × 25 towns. Columns: `shs_year`, `elderly_pop`, `town_estate`, `number`.
- The two groups, per the column description: "Elderly" is residents aged 65 and above; "Future Elderly" is residents aged 55 to 64.
- Every town appears in all four years. No value is missing or non-numeric.
- The 25 towns: Ang Mo Kio, Bedok, Bishan, Bukit Batok, Bukit Merah, Bukit Panjang, Bukit Timah, Central Area, Choa Chu Kang, Clementi, Geylang, Hougang, Jurong East, Jurong West, Kallang/Whampoa, Marine Parade, Pasir Ris, Punggol, Queenstown, Sembawang, Sengkang, Serangoon, Tampines, Toa Payoh and Yishun. The Round 1 Plan said 26 towns.
- All 50 values for 2018 are multiples of 100, so that year is rounded; the earlier years are not.

| Survey year | Elderly (65+), sum of 25 towns | Future elderly (55 to 64), sum of 25 towns |
|---|---|---|
| 2003 | 211,340 | 239,750 |
| 2008 | 278,263 | 327,348 |
| 2013 | 326,975 | 393,175 |
| 2018 | 484,200 | 453,000 |
