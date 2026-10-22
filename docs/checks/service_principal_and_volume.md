# Service principal and raw-files Volume (Day 2, steps 2b and 5)

- Check: the trial workspace allows creating a service principal (the user is in `admins`; `service-principals list` worked, then `create` succeeded).
- Service principal: `coolcheck-collector` (application id `4871a171-49bc-443f-9601-f16df5e68a99`). It is the identity the GitHub Actions collector uploads as.
- Volume: `coolcheck.bronze.raw_files` (managed), path `/Volumes/coolcheck/bronze/raw_files`.

## Current state (21 Oct 2026)

| What | Setting | Checked |
|---|---|---|
| Volume grants | `READ_VOLUME` and `WRITE_VOLUME` on `coolcheck.bronze.raw_files` (this Volume only); `READ_VOLUME` re-granted at 19:15 SGT, one minute before the first real upload run | `databricks grants get volume`, 21 Oct; the 19:15 time as reported by the user |
| Schema grant | `USE_SCHEMA` on `coolcheck.bronze` | `databricks grants get schema`, 21 Oct |
| Catalog grant | `USE_CATALOG` on `coolcheck` | `databricks grants get catalog`, 21 Oct |
| Workspace entitlement | Consumer access (`workspace-consume` in the API) | `service-principals list`, 21 Oct |
| OAuth secret | scope `all-apis`, lifetime 30 days, expires about 20 Nov 2026 | as set by the user; the secret value was never seen or printed, and the secret itself was not re-read |

The grants give no table access. Nothing else is granted to the principal.

## Why each item is needed

GitHub Actions runs, in order (outcomes and causes as reported by the user; the run logs were not read in this session). Dry run `39588791785` succeeded first, so it did not use the credentials. The next three runs were the first three real dispatches, and each failed for a different reason:

| Run | Result | Cause |
|---|---|---|
| `39588791785` | succeeded | dry run, nothing uploaded |
| `39589083284` | failed | OAuth secret scope `all-apis` not assigned |
| `39589832036` | failed | principal had no workspace entitlement |
| `39590361248` | failed | principal lacked `READ_VOLUME` |
| `39590724749` | succeeded | first real upload run, 19:16:40 SGT, after the three fixes below |

- **Scope `all-apis`** (run `39589083284`): the Databricks SDK requests the `all-apis` scope when it logs in with an OAuth secret, so the secret has that scope.
- **Consumer access** (run `39589832036`): the Files API needs the principal to have a workspace entitlement.
- **`READ_VOLUME` as well as `WRITE_VOLUME`** (run `39590361248`): the upload needs both. The design note assumed `WRITE_VOLUME` alone would do and planned to drop `READ_VOLUME` before the first real run; with `READ_VOLUME` missing the run failed. It was re-granted at 19:15 SGT on 21 Oct and the next run (`39590724749`, 19:16:40 SGT) uploaded. (The collector never lists or reads the Volume itself, so the read need comes from the Files API upload.)

## Limits of this setup

- `WRITE_VOLUME` also lets the principal delete and overwrite files in this Volume, and Unity Catalog has no append-only grant. The collector uploads with `overwrite=false`. The backups are Bronze and the local `coolcheck-data`.
- The OAuth secret expires about 20 Nov 2026, after the trial ends (30 Oct) and the finale (4 Nov), so it should not need renewal before then. If the collector is re-pointed at the Free Edition workspace (Day 7), the principal, grants, entitlement and secret must be created again there; whether Free Edition allows a service principal is not verified.
