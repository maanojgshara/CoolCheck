# Service principal and raw-files Volume (Day 2, step 2b)

- Check: the trial workspace allows creating a service principal (the user is in `admins`; `service-principals list` worked, then `create` succeeded).
- Created: service principal `coolcheck-collector` (application id `4871a171-49bc-443f-9601-f16df5e68a99`). No token, secret or OAuth secret was created or printed.
- Volume: `coolcheck.bronze.raw_files` (managed), path `/Volumes/coolcheck/bronze/raw_files`.
- Grants to the service principal: `WRITE_VOLUME` and `READ_VOLUME` on that Volume only, plus `USE_CATALOG` on `coolcheck` and `USE_SCHEMA` on `coolcheck.bronze` (needed to reach the Volume; they give no table access).
- Not yet done: a credential for the principal (an OAuth secret) for the GitHub Actions collector, and a test write as the principal. Both need the user's hands (§14.6).
