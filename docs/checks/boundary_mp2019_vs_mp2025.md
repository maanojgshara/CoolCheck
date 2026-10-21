# URA Master Plan 2025 planning-area boundary: download and comparison with 2019 (21 Oct 2026)

Downloaded 21 Oct 2026, 13:32 SGT, from data.gov.sg dataset `d_2cc750190544007400b2cfd5d7f53209` ("Master Plan 2025 Planning Area Boundary (No Sea)", URA, source last updated 2026-02-27, coverage start 2025-12-29), no key. Folder `coolcheck-data/static/ura_mp2025_planning_area_boundary/` with `provenance.json` (2,191,270 bytes, sha256 `e6ecc1743de5c39ec154a30b3b8037896fbc6c5f863e10c7dbfd77de12706c9c`). Added to `scripts/checks/download_static.py`; the comparison is `scripts/checks/compare_boundaries.py`. The licence is expected, not confirmed on the dataset page: Singapore Open Data Licence v1.0, as for the other data.gov.sg files. **Unverified until read.**

## Names: identical

Both files have 55 features, with the same 55 `PLN_AREA_N` names, no duplicates and the same property fields (`OBJECTID`, `PLN_AREA_N`, `PLN_AREA_C`, `CA_IND`, `REGION_N`, `REGION_C`, `INC_CRC`, `FMEL_UPD_D`, `SHAPE.AREA`, `SHAPE.LEN`). So the join to the SingStat June 2026 names works with either file.

## Polygons: nearly the same, with one real change

| | 2019 | 2025 |
|---|---|---|
| Polygon / MultiPolygon features | 46 / 9 | 48 / 7 |
| Total area, km² (planar approximation from degrees, not an official figure) | 784.9 | 796.9 |

- **Only 12 of 55 areas have the same vertex count** in both files, so most polygons were re-drawn or re-digitised, but almost all by small amounts: **52 of 55 areas changed in area by 1% or less** (planar approximation).
- **Changes above 1%:** CHANGI BAY from 1.97 to 11.63 km² (+490%, +9.7 km² of sea or reclaimed area added: the "No Sea" file now includes a larger Changi Bay), CHANGI +4.6% (41.47 to 43.36), PASIR RIS +1.0%. Next: WESTERN ISLANDS +0.8%, YISHUN −0.65%, SUNGEI KADUT −0.5%, LIM CHU KANG +0.5%.
- **Grid sample** (0.001° cells, about 110 m, 64,763 cells inside either file; a sample, not an exact polygon difference): **98.4% of cells carry the same planning area in both files.** In 2025 only: 12.2 km² (mostly CHANGI BAY 9.65, CHANGI 1.87, WESTERN ISLANDS 0.44, PASIR RIS 0.17). In 2019 only: 0.16 km² (YISHUN, 13 cells). Moved from one area to another: **0.12 km²** (SUNGEI KADUT to LIM CHU KANG 0.10 km², and 4 single cells: BUKIT PANJANG to BUKIT TIMAH, OUTRAM to DOWNTOWN CORE and others).
- **For this project:** the residential areas are essentially the same. A block near a boundary could change planning area (SUNGEI KADUT / LIM CHU KANG, YISHUN edge, PASIR RIS and CHANGI edges); the geocoded sample of 6 blocks gave the same area under both files. Not tested: all 13,392 blocks, which will say how many change.

## Recommendation (mine; decision C1 is the user's)

Use the Master Plan 2025 file with the SingStat June 2026 figures, as the SingStat file's own note says its areas refer to Master Plan 2025. The names are identical, and the polygon differences are small. Keep the 2019 file in `static/` for the comparison.

## Not tested

- The exact polygon difference (no shapely in the venv; the grid is coarse, so slivers narrower than about 110 m are missed).
- Whether the 2025 `year` value works in OneMap's `getPlanningarea`.
- The dataset page's licence text.
