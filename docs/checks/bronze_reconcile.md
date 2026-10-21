# Bronze reconciliation (backfill)

Generated 2026-10-21 17:21 Malay Peninsula Standard Time by `scripts/reconcile/bronze_reconcile.py`. Volume and Bronze figures come from `coolcheck.silver.dq_reconcile` (reconcile job, stage bronze, checked 2026-10-21 17:19:16.189794); the Volume line count is a plain batch read of each file, independent of Auto Loader.

Four sources per file: local files in `coolcheck-data/raw`, the last `day` record per feed and date in `coolcheck-data/backfill/progress.jsonl` (pages = API calls that returned a page = lines written), the Volume `/Volumes/coolcheck/bronze/raw_files`, and the Bronze tables `coolcheck.bronze.<feed>_raw`.

| feed | files local | files progress | files Volume | files Bronze | lines local | pages progress | lines Volume | rows Bronze | distinct lines Bronze | bytes local | bytes Volume | files differing |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| wbgt | 642 | 642 | 642 | 642 | 2,563 | 2,563 | 2,563 | 2,563 | 2,563 | 198,292,106 | 198,292,106 | 0 |
| rainfall | 642 | 642 | 642 | 642 | 7,687 | 7,687 | 7,687 | 7,687 | 7,687 | 429,984,947 | 429,984,947 | 0 |
| forecast | 641 | 641 | 641 | 641 | 641 | 641 | 641 | 641 | 641 | 7,749,722 | 7,749,722 | 0 |

Backfill day statuses in progress.jsonl: forecast done 641, forecast no_data 1, rainfall done 625, rainfall short 17, wbgt done 621, wbgt short 21.
Days with no data (no file expected): forecast 2025-07-20.
`_meta/backfill_end.json` is outside the feed folders and is not loaded into Bronze.

**No file differs:** for every file, the line counts agree across all four sources, the byte sizes agree across local, progress.jsonl and the Volume, and the local sha256 equals the one progress.jsonl recorded.
