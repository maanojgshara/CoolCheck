# Check 5: OneMap terms, rate limit, token and geocoding (21 Oct 2026)

Script: `scripts/checks/check5_onemap.py`. Run 21 Oct 2026, about 13:20 to 13:35 SGT, from this computer. The token came only from `ONEMAP_TOKEN` and was not printed, logged or written; only its expiry was read. **30 of 30 permitted calls to onemap.gov.sg were used** (2 page fetches, 26 search calls, 2 planning-area calls), 3 seconds apart. **Unverified until read.**

## Terms of use and rate limit: not read

- `https://www.onemap.gov.sg/legal/termsofuse` returned HTTP 200 but only a 113-character shell ("OneMap | V2 We have moved! Visit us at our new site"). `https://www.onemap.gov.sg/apidocs/` returned an empty shell (1 visible character). Both are built by JavaScript, so a script cannot read them.
- I did not try more pages, because each page fetch counts against the 30 calls. **So I cannot quote the terms or the rate limit.** The "250 calls a minute" in the guide (§4) is still the user's recollection, unconfirmed.
- The 26 search calls (one per 3 s, about 20 a minute) returned no `X-RateLimit-*`, `RateLimit-*` or `Retry-After` header and no HTTP 429, so they say nothing about the limit.
- **To read in a browser:** the terms of use and the API documentation's rate-limit and token sections on onemap.gov.sg. Questions to answer there: the rate limit; whether storing geocoded coordinates is allowed; whether the data may be used in a competition entry and a public repository; the attribution wording; and the token lifetime.

## Token

- The Search and planning-area calls returned HTTP 200 with the token on all 28 API calls, so **the token works**.
- Expiry decoded from the JWT `exp` claim (no other claim read): **24 Oct 2026, 12:58 SGT**, 3 days after the time of the check (13:30 SGT on 21 Oct). That matches the 3 days in the guide, now seen on the token itself. It expires before Demo Day (27 Oct), so the geocoding must run before then, or a new token needs the account email and password (guide §16).

## Geocoding sample (20 blocks)

- **Sample:** 20 residential HDB blocks from `coolcheck-data/static/hdb_property_information` (rows with `residential = Y` and dwelling units above 0), one block in each of 20 different towns, chosen with a fixed seed (`random.Random(0)`). Query: `"<blk_no> <street>"` with `returnGeom=Y&getAddrDetails=Y`.
- **Endpoint:** `GET https://www.onemap.gov.sg/api/common/elastic/search`, token in the `Authorization` header. It accepted the request in the form `searchVal`, `returnGeom`, `getAddrDetails`, `pageNum`.
- **Fields returned** per result: `SEARCHVAL`, `BLK_NO`, `ROAD_NAME`, `BUILDING`, `ADDRESS`, `POSTAL`, `X`, `Y`, `LATITUDE`, `LONGITUDE`. Top level: `found`, `totalNumPages`, `pageNum`, `results`. `X` and `Y` look like SVY21 metres (Bishan block: 30028.3, 36852.0). Coordinates are returned as strings.
- **Hit rate:** **20 of 20 queries returned HTTP 200 and a result whose block number and road match the query** (after expanding HDB's abbreviations: ST to STREET, AVE to AVENUE and so on). Each had `found` of 1 or 2. For three queries `found` was 2; the first result was the right block each time (checked by address). The first run's own matcher compared the roads without expanding abbreviations and scored 1 of 20; that was a bug in my matcher, not a failure of the search (I had not saved the raw responses, and the cap did not allow 20 more calls). I scored the 20 by the `ADDRESS` string that the run saved (block and expanded road at the start of the address, 20 of 20), and I re-queried 6 blocks with raw results saved to check the coordinates (below). So the 20 of 20 rests on address strings, with coordinates seen for 6 of them.
- **Caveats:** a sample of 20 in different towns cannot show the hit rate for all 13,392 rows; blocks with a letter suffix (for example 635B) matched in this sample; I did not test commercial-only rows, demolished blocks or duplicates.
- **Two calls per block are not needed.** Each block takes one search call. At 13,392 rows that is 13,392 calls; at the unconfirmed 250 a minute that is about 54 minutes, at 20 a minute about 11 hours. Read the real limit before the run. Many rows are not residential (`residential = N`) and need no call.

## Assigning a planning area

Two options were tried on the same Bishan block:

1. **Local, by coordinates (recommended; matches D5):** point-in-polygon of `LONGITUDE`/`LATITUDE` against the URA planning-area boundary file (pure Python ray casting in the script, no extra calls). For the 6 re-queried blocks the result was BISHAN, KALLANG (54 Geylang Bahru), GEYLANG, PASIR RIS, BUKIT PANJANG and ANG MO KIO, the same with the Master Plan 2019 and the Master Plan 2025 file (`boundary_mp2019_vs_mp2025.md`). I did not check by map that these are right; the town names for Bishan, Pasir Ris and Ang Mo Kio agree with the HDB town of the block.
2. **OneMap `getPlanningarea` (1 call per block):** `GET /api/public/popapi/getPlanningarea?latitude=..&longitude=..&year=2019` returned HTTP 200 and a list with one item holding `pln_area_n` (BISHAN for the Bishan block, the same as the local result) and a `geojson` field of about 10 kB (the polygon). Costs one extra call per block, so it is not worth it. I tried only the year 2019 and one block, and did not test 2025 as the `year` value.

## What this does not show

- The terms and rate limit (above).
- The hit rate on all blocks, or the rate of wrong matches (a block number can exist on two roads; I matched on both, but only for 20 queries).
- Whether OneMap's coordinates are for the block's centre or its entrance.

## Next

- User reads the terms and the rate limit in a browser and tells me the limit and whether storing coordinates is allowed.
- The geocoding script (Day 3) must save every raw response, take the rate limit from the terms, run before 24 Oct 12:58 SGT, and write only block address, postal code and coordinates (no personal data).
