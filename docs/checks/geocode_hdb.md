# HDB block geocoding with OneMap search (21 to 22 Oct 2026)

Script: `scripts/static/geocode_hdb.py`; tests: `tests/static/test_geocode_hdb.py` (87 pass). Output: `coolcheck-data/geocode/` (outside the repo): `geocoded_blocks.csv`, `report.md`, `progress.jsonl`, `runs.jsonl`, `geocode.log`. The full run was on 21 Oct 2026, 21:34 to 22:52 SGT. On 22 Oct 2026 the postal rule and the tenant-record note (below) were added and the CSV and report rebuilt with `--report-only`, so **no OneMap call was made for them**. The token came only from `ONEMAP_TOKEN` and was never printed, logged or written; only its expiry was read. The output folder holds no token-like string.

## Result

**10,807 of the 10,817 residential HDB blocks have a confirmed coordinate (99.91%). The other 10 have a coordinate that is not confirmed.** None is ambiguous or not found.

| outcome | rental blocks | other blocks | all |
|---|---:|---:|---:|
| matched | 550 | 8,631 | 9,181 |
| matched_same_place | 83 | 1,490 | 1,573 |
| matched_postal_rule | 4 | 49 | 53 |
| matched_no_postal | 0 | 10 | 10 |
| ambiguous | 0 | 0 | 0 |
| not_found | 0 | 0 | 0 |
| total | 637 | 10,180 | 10,817 |

Confirmed (`confirmed = Y`) are matched, matched_same_place and matched_postal_rule: 9,181 + 1,573 + 53 = **10,807**, of which all 637 are rental blocks. Before the postal rule the figure was 10,754 (9,181 + 1,573), with 53 ambiguous.

## Method

- **Input:** `d_17f5382f26140b1fdae0ba2ef6239d2f.csv`, rows with `residential = Y` and `total_dwelling_units` above 0: 10,817 blocks (`blk_no` plus street is unique). The 637 blocks with any rental flat go first, then the rest, each in file order.
- **Query:** `<blk_no> <street>`, `returnGeom=Y`, `getAddrDetails=Y`, page 1. One call per block. If page 1 had no candidate and `totalNumPages` was above 1, pages 2 to 5 would be read in turn until a candidate; this never happened (below).
- **Candidate:** a result whose `BLK_NO` equals the block number and whose `ROAD_NAME` equals the street once both are normalised (upper case; full stops and apostrophes dropped; HDB abbreviations such as ST, RD, C'WEALTH expanded; a leading ST. read as SAINT).
- **Pace and safety:** at most 3 calls a second. HTTP 429: a fixed 30 s wait, at most 2 retries, and a stop at the 3rd 429 in a row. A 401 or 403 stops the run at once, and the 401 message gives the token's expiry. Every finished block is one line in an append-only `progress.jsonl` (key, query, found, pages read, every result seen), so a rerun skips finished blocks.

## The six outcomes

1. **matched:** one candidate, with a 6-digit postal code. Confirmed.
2. **matched_same_place:** several candidates at one place (at most one postal code among them, all within 50 m); the one with the postal code is kept. Typically the block plus a facility listed at it with postal NIL (for example a childcare centre 4 m away). Confirmed.
3. **matched_postal_rule (new):** several candidates at different places, and exactly one distinct postal code among them ends in the block number. That candidate is kept; the others are listed in the report beside it as rejected. Confirmed. If no postal code, or more than one distinct code, fits, the block stays **ambiguous**.
4. **matched_no_postal:** the only candidate, or all candidates at one place, have postal NIL. The first record is kept with its coordinates, but `confirmed = N` and the CSV `note` column reads "address match through a tenant record" (see the caveat).
5. **ambiguous:** several candidates at different places and the postal rule does not resolve them. Nothing is kept. Now 0.
6. **not_found:** no candidate on the pages read. 0.

### The postal rule (G1)

The suffix is the block number's leading digits, zero-padded to three: 5 gives 005, 18C gives 018, 187 gives 187. A candidate fits when its 6-digit postal code ends in that suffix.

- **Why it can be trusted:** HDB postal codes end in the block number. Among the 10,754 blocks matched without the rule, **10,746 (99.93%) have a postal code that ends in their block number**. The 8 that do not are known and none was changed by the rule: 1 TOH YI DR (591501, Toh Yi Gardens) and 1A to 1G CANTONMENT RD (The Pinnacle@Duxton, 085101, 085201 and so on to 085701).
- **Applied to the 53 blocks that were ambiguous:** in all 53, exactly one distinct postal code fits, so all 53 were resolved and none was left ambiguous. Checked on the 53: the kept postal code ends in the block number in 53 of 53; 4 are rental blocks. None of the 8 exceptions is among them. The other 10,764 blocks are unchanged in outcome and in every earlier column.
- **Typical rejected candidates** are other records at the same address: a hotel or post office listed at the block number (for example 1 BEACH RD keeps 190001, Beach Road Gardens, and rejects two Raffles Hotel records), a dialysis centre, a police post. The report lists the rejected candidates with each of the 53.

### The 10 matched_no_postal blocks (G2 caveat)

For each of these OneMap returned one record at the block's address and road, but its building is a tenant (for example Saint Luke's ElderCare centres at 101 TAMPINES ST 11, 327 JURONG EAST ST 31, 350 and 351 TAMPINES ST 33 and 602 CLEMENTI WEST ST 1; child-care records at 511 JURONG WEST ST 52, 610 JURONG WEST ST 65 and 926 HOUGANG ST 91; an education centre at 703 TAMPINES ST 71; HDB public shelters at 4C ST. GEORGE'S LANE) and its postal code is NIL. Decision G2: **keep the coordinates, flagged `confirmed = N` with the note "address match through a tenant record"; no re-query.**

- The point is a tenant's position inside or beside the block, so it can be some metres off the block's own point. It was not checked against the block's real position.
- For 703 TAMPINES ST 71 the building name reads "SHERWINN EDUCATION CENTRE (TAMPINES ST 33)" while the road is TAMPINES STREET 71; that coordinate is the one to look at first before it is used for anything finer than a planning area.
- Any use that needs a confirmed block coordinate must filter on `confirmed = Y` and treat these 10 as unconfirmed. This is 0.09% of the blocks.

## Checks

- Latitude and longitude of the confirmed records: 0 outside 1.13 to 1.48 N and 103.59 to 104.1 E.
- Blocks with more than one page of results: 2 (1 THOMSON RD, 35 results over 4 pages; 678 WOODLANDS AVE 6, 12 results over 2 pages). Both had a candidate on page 1, so no later page was read. **Pages 2 to 5 were never read on the real API**; that code is tested only against the fake API.
- Lines in `progress.jsonl` that could not be read: 0. Finished blocks not in the input: 0.
- Tests: 87 pass in `tests/static`. They cover the matching, the postal rule (one fitting code resolves; no fitting code stays ambiguous; two different fitting codes stay ambiguous; zero padding with block 5, 18C and 12; matched_no_postal stays `confirmed = N` with its note), resume, back-off, the stop rules, the extra pages and token handling. A mutation check of the new rule (8 deliberate breaks, such as no zero padding, any trailing digit, more than one fitting code allowed, rule not confirmed) was caught by the tests in all 8.

## Run log summary (`runs.jsonl`)

| started (SGT) | blocks | calls | pages 2 to 5 | retries | HTTP statuses | seconds | result |
|---|---:|---:|---:|---:|---|---:|---|
| 2026-10-21 21:34:19 | 700 | 700 | 0 | 0 | 200: 700 | 233.5 | finished (`--limit 700`) |
| 2026-10-21 21:56:33 | 10,117 | 10,117 | 0 | 0 | 200: 10,117 | 3,380.2 | finished |
| all 2 runs | 10,817 | 10,817 | 0 | 0 | 200: 10,817 | 3,613.7 | |

- 10,817 calls in about 60 minutes (3 a second), one per block, all HTTP 200. No 429, no 401 or 403, no retry, no 5xx, and no stop. The rate limit was not reached at 3 a second.
- Two dry runs of 20 blocks, with 20 calls each, are in their own folders `coolcheck-data/geocode/dryrun_20` and `dryrun_20b`; they are not part of the table.
- The report is rebuilt without calls with `.venv\Scripts\python scripts/static/geocode_hdb.py --report-only`; the rebuilt report's Runs table is the table above.

## Token

The OneMap token in `ONEMAP_TOKEN` **expires on 24 Oct 2026 at 12:58 SGT** (from the JWT `exp` claim). Tokens last 3 days and do not renew; a new one comes from a POST of the account email and password to `/api/auth/post/getToken`. Nothing in this run needs a token any more; a later re-query (for example of the 10 matched_no_postal blocks, or of pages 2 to 5) would. The token is never printed, logged or written by the script; the CSV, report, log and progress files were scanned for token-like strings and hold none.

## Next steps

Join the confirmed coordinates to the planning-area boundary file (point-in-polygon, as in check 5) and use `confirmed = Y` as the filter. Whether OneMap's terms allow storing the coordinates is still open from check 5.
