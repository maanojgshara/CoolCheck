# API key burst check: does api-open.data.gov.sg read `x-api-key`?

Script: `scripts/checks/check_apikey_burst.py` (one burst of 14 concurrent GETs per run, ThreadPoolExecutor, all sent within 0.01 s).
Endpoint: `https://api-open.data.gov.sg/v2/real-time/api/twenty-four-hr-forecast`. Run 2026-10-21, about 15:32 SGT, 15 s idle between runs.
Documented limits: 6 calls per 10 s with no key, 12 with a Developer key.

| Condition | Run | 200 | 429 | Other | Retry-After |
|---|---|---|---|---|---|
| No key | 1 | 6 | 8 | 0 | none |
| No key | 2 | 6 | 8 | 0 | none |
| Key in `x-api-key` | 1 | 12 | 2 | 0 | none |
| Key in `x-api-key` | 2 | 12 | 2 | 0 | none |

Verdict: **key accepted: yes, under the `x-api-key` header.** Successes doubled from 6 to 12, matching the documented Developer limit, and both runs of each condition agreed.

The `Authorization: Bearer` and `api-key` variants were not tried because the fallback step only applies if `x-api-key` fails.

Caveats:
- Two runs per condition on one day. The 6 and 12 match the documented limits exactly, so a coincidence is unlikely, but this is not a long-run measurement.
- Fixed 10 s windows can split a burst; every run landed whole in one window.
- The 429 responses carried no `Retry-After` header, so back-off has to be a fixed wait.
- This tests the rate-limit tier only. It does not show that the key is needed for anything else.
- The key value was never printed or written; only its presence was checked.
