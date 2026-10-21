# Check 3: Cycling Path Network (LTA): does the GeoJSON exist on data.gov.sg?

Script: `scripts/checks/check2_3_corridors.py`. Dataset `d_8f468b25193f64be8a16fa7d8f60f553` 'Cycling Path Network (GEOJSON)' (Land Transport Authority), format GEOJSON, source last updated 2026-07-14T10:06:45+08:00; file downloaded 2026-10-21 12:53 SGT (no key or token), 4,896,738 bytes, sha256 `80288a2b1e08b9af...`. Page: https://data.gov.sg/datasets/d_8f468b25193f64be8a16fa7d8f60f553/view. Licence: Singapore Open Data Licence v1.0, as stated on data.gov.sg's licence page (not in the API metadata). **Unverified until read.**

## What was tested

Found the dataset in a crawl of the data.gov.sg catalogue (4,664 datasets), downloaded it through the public download endpoint and read it: feature count, geometry types, attributes, bounding box, and the total length computed with the haversine formula on the coordinates.

## Result

- **Exists: yes.** 8,523 features; geometry types {'LineString': 8520, 'MultiLineString': 3}; file CRS member: none (GeoJSON default, WGS84 longitude/latitude).
- Attributes per feature: `AGENCY_MAINT`, `CYL_PATH`, `FMEL_UPD_D`, `INC_CRC`, `OBJECTID_1`, `SHAPE_1.LEN`.
- Bounding box (lon/lat): (103.637, 1.2654, 103.9664, 1.4674); all points inside a Singapore box: True.
- **Total length by haversine: 433.8 km.** `FMEL_UPD_D` record stamps by month: {'202407': 5139, '202606': 3384}.

Length by `AGENCY_MAINT` (km, haversine):

| AGENCY_MAINT | km |
|---|---|
| Land Transport Authority | 352.4 |
| LTA (Others) | 54.0 |
| Town Council | 18.6 |
| Jurong Town Corporation | 3.7 |
| Town Council (Others) | 2.7 |
| People's Association | 1.1 |
| Housing Development Board | 0.6 |
| Jurong Town Corporation (Others) | 0.5 |
| People's Association (Others) | 0.2 |

## Reading

- The file can give cycling path corridor length per planning area by clipping the lines to the Master Plan boundary (not done here).
- The two corridor files probably overlap (many park connectors are also cycling paths), so adding their lengths would double count; **not tested**.
- Lengths are straight-line sums between vertices, so they slightly understate real path length; they are not checked against the agency's published length.

- The guide asked whether this is data.gov.sg GeoJSON or an LTA DataMall shapefile needing an account key: **it is on data.gov.sg as GeoJSON, so no DataMall key is needed for this file.** Whether DataMall has a more complete or newer version was not checked.

## Fallback (agreed 19 Oct)

Not triggered. (The corridor datasets are stretch goals; if they fail, corridor length is dropped.)

## Could not confirm

- That the LTA file is the complete network (no independent length figure was compared).
- Whether the licence on the dataset page matches the licence page (the dataset page was not opened in a browser).
- Overlap between the two corridor files, and the planning-area clipping result.

