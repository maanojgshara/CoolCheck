# Check 2: Park Connector Loop (NParks): does the GeoJSON exist on data.gov.sg?

Script: `scripts/checks/check2_3_corridors.py`. Dataset `d_a69ef89737379f231d2ae93fd1c5707f` 'Park Connector Loop' (National Parks Board), format GEOJSON, source last updated 2026-07-15T10:06:55+08:00; file downloaded 2026-10-21 12:53 SGT (no key or token), 2,008,356 bytes, sha256 `83c1838bea9ee355...`. Page: https://data.gov.sg/datasets/d_a69ef89737379f231d2ae93fd1c5707f/view. Licence: Singapore Open Data Licence v1.0, as stated on data.gov.sg's licence page (not in the API metadata). **Unverified until read.**

## What was tested

Found the dataset in a crawl of the data.gov.sg catalogue (4,664 datasets), downloaded it through the public download endpoint and read it: feature count, geometry types, attributes, bounding box, and the total length computed with the haversine formula on the coordinates.

## Result

- **Exists: yes.** 878 features; geometry types {'LineString': 784, 'MultiLineString': 94}; file CRS member: none (GeoJSON default, WGS84 longitude/latitude).
- Attributes per feature: `FMEL_UPD_D`, `INC_CRC`, `MORE_INFO`, `OBJECTID`, `PARK`, `PCN_LOOP`, `SHAPE.LEN`.
- Bounding box (lon/lat): (103.6932, 1.2729, 104.0316, 1.4629); all points inside a Singapore box: True.
- **Total length by haversine: 336.1 km.** `FMEL_UPD_D` record stamps by month: {'202501': 871, '202502': 2, '202605': 5}.

Length by `PCN_LOOP` (km, haversine):

| PCN_LOOP | km |
|---|---|
| Eastern Coastal Loop | 91.9 |
| Northern Explorer Loop | 57.2 |
| Western Adventure Loop | 54.0 |
| Central Urban Loop | 46.5 |
| North Eastern Riverine Loop | 44.9 |
| Southern Ridges Loop | 40.7 |
| Urban Central Loop | 1.0 |

## Reading

- The file can give park connector loop corridor length per planning area by clipping the lines to the Master Plan boundary (not done here).
- The two corridor files probably overlap (many park connectors are also cycling paths), so adding their lengths would double count; **not tested**.
- Lengths are straight-line sums between vertices, so they slightly understate real path length; they are not checked against the agency's published length.

## Fallback (agreed 19 Oct)

Not triggered. (The corridor datasets are stretch goals; if they fail, corridor length is dropped.)

## Could not confirm

- That the NParks file is the complete network (no independent length figure was compared).
- Whether the licence on the dataset page matches the licence page (the dataset page was not opened in a browser).
- Overlap between the two corridor files, and the planning-area clipping result.

