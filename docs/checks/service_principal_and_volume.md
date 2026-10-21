# Service principal and raw-files Volume (Day 2, steps 2b and 5)

- Check: the trial workspace allows creating a service principal (the user is in `admins`; `service-principals list` worked, then `create` succeeded).
- Service principal: `coolcheck-collector` (application id `4871a171-49bc-443f-9601-f16df5e68a99`). It is the identity the GitHub Actions collector uploads as.
- Volume: `coolcheck.bronze.raw_files` (managed), path `/Volumes/coolcheck/bronze/raw_files`.

## Current state (21 Oct 2026)

| What | Setting | Checked |
|---|---|---|
| Volume grants | `READ_VOLUME` and `WRITE_VOLUME` on `coolcheck.bronze.raw_files` (this Volume only) | `databricks grants get volume`, 21 Oct |
| Schema grant | `USE_SCHEMA` on `coolcheck.bronze` | `databricks grants get schema`, 21 Oct |
| Catalog grant | `USE_CATALOG` on `coolcheck` | `databricks grants get catalog`, 21 Oct |
| Workspace entitlement | Consumer access (`workspace-consume` in the API) | `service-principals list`, 21 Oct |
| OAuth secret | scope `all-apis`, lifetime 30 days, expires about 20 Nov 2026 | as set by the user; the secret value was never seen or printed, and the secret itself was not re-read |

The grants give no table access. Nothing else is granted to the principal.

## Why each item is needed

The first three collector dispatches failed and the fourth succeeded (GitHub Actions runs, outcome as reported by the user; the run logs were not read in this session):

- **Scope `all-apis`:** the Databricks SDK requests the `all-apis` scope when it logs in with an OAuth secret, so the secret has that scope.
- **Consumer access:** the Files API needs the principal to have a workspace entitlement.
- **`READ_VOLUME` as well as `WRITE_VOLUME`:** the upload needs both. The design note assumed `WRITE_VOLUME` alone would do, and planned to revoke `READ_VOLUME` before the first real run; that was wrong and the revoke was not done. (The collector never lists or reads the Volume itself, so the read need comes from the Files API upload.)

Runs `39589083284`, `39589832036` and `39590361248` failed for these reasons (the user did not say which run hit which); run `39590724749` succeeded.

## Limits of this setup

- `WRITE_VOLUME` also lets the principal delete and overwrite files in this Volume, and Unity Catalog has no append-only grant. The collector uploads with `overwrite=false`. The backups are Bronze and the local `coolcheck-data`.
- The OAuth secret expires about 20 Nov 2026, after the trial ends (30 Oct) and the finale (4 Nov), so it should not need renewal before then. If the collector is re-pointed at the Free Edition workspace (Day 7), the principal, grants, entitlement and secret must be created again there; whether Free Edition allows a service principal is not verified.
