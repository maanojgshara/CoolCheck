# CoolCheck

Next-day heat briefing for community care teams in Singapore (DAISI Round 2, team AIsenal, problem B1 HeatGuard).

## How the collector is scheduled

The live collector (`scripts/collector/collect.py`, run by `.github/workflows/collector.yml`) fetches the WBGT, rainfall and 24-hour forecast feeds and uploads raw files to the raw-files Volume. Two things start it:

- **GitHub's own schedule** (`schedule:` in the workflow). It is best effort: GitHub starts only a fraction of the slots, so it cannot be relied on alone.
- **An external scheduler** that calls the workflow's `workflow_dispatch` API every 15 minutes (at :00, :15, :30 and :45) with `dry_run=false`. It uses a fine-grained token limited to this repository's Actions. Only the scheduler holds that token; it is not stored in the repository or in the Actions secrets.

The repository variable `COLLECTOR_ENABLED` is the off switch. Both kinds of start run only while it is `true`; set it to `false` to stop them. A manual dispatch with `dry_run=true` (the default) always runs, writes files on the runner only and uploads nothing.
