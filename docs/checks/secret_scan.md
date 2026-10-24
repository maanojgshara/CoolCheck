# Secret scan of the git history

Scan of 23 Oct 2026, 17:01 SGT, by window E (Claude Code), on the refs as they stood then (HEAD `6ca1d98`). Read-only: nothing in the repository was changed, rewritten or fetched. No value is shown in this report: each match is given by its file, the commit that added it, its first four characters and its length.

## Result

**No credential was found in any commit.** Nowhere in the history is there:
- a Databricks personal access token (`dapi…`) or OAuth secret (`dose` followed by 20 or more letters and digits);
- a GitHub token (`ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`, `github_pat_`);
- a JWT (the OneMap token is one), a private key, an AWS or Google API key, a Slack token, or credentials inside a URL;
- a literal value for `DATA_GOV_SG_API_KEY`, `ONEMAP_TOKEN`, `ONEMAP_EMAIL`, `ONEMAP_PASSWORD`, `DATABRICKS_CLIENT_SECRET`, `DATABRICKS_TOKEN`, `GITHUB_TOKEN` or `GH_TOKEN`;
- a file with a credential-type name (`.env`, `.databrickscfg`, `.netrc`, `.git-credentials`, `*.pem`, `*.key`, `id_rsa` and similar).

Six distinct values matched the named rules. All six are test fixtures, references or names (table below). The generic high-entropy pass found 79 distinct strings, each explained: hashes, IDs, UUIDs, dataset IDs and long identifiers. Nothing is left unexplained.

## Scope

| item | value |
|---|---|
| refs scanned | `refs/heads/main` at `6ca1d98`; `refs/remotes/origin/main` at `bff0577`; no other branches, no tags, no stash |
| commits | 86 (from `git rev-list --all`); the reflog adds none; no merge commits |
| on GitHub | `git ls-remote origin` (read-only) lists one branch, `main`, at `bff0577`, which is in the local history; the local `main` is 6 commits ahead and those were scanned too |
| file versions | 259 distinct blobs, 8 of them binary (PNG charts in `docs/checks/eda_figs/` and `docs/checks/error_analysis_figs/`) |
| paths ever tracked | 163 |
| patch lines | 23,216 added lines across all commits |

## Method

Git only (git 2.56.0.windows.2), with a masking script run by the project's `.venv` Python, nothing installed. The script keeps every match as its first four characters, its length and an 8-character fingerprint (a SHA-256 prefix, used only to compare a match with an expected literal), so no full value reached the screen or any file. The script is kept outside the repository, since this task adds only this report; the rules below are enough to repeat the scan.

Passes:
1. **Every patch:** `git log --all -p -m`, added lines of every commit's diff.
2. **Every commit message:** `git log --all --format=%B`.
3. **Every commit's tree:** `git grep -I -n -i -E <union of the rules>` over each of the 86 commits from `git rev-list --all` (text files).
4. **Every binary file version:** the 8 PNG blobs read with `git cat-file` and checked with the named rules.
5. **Every path ever tracked:** `git log --all --name-only`, checked against credential-type file names.

Named rules:

| rule | pattern (summary) |
|---|---|
| Databricks PAT | `dapi` + 32 hex |
| Databricks OAuth secret | `dose` + 20 or more letters and digits |
| GitHub token | `ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_` + 30 or more; `github_pat_` + 20 or more |
| JWT | `eyJ…` with three dot-separated parts; also any `eyJ` + 15 or more characters |
| private key | `-----BEGIN … PRIVATE KEY-----` |
| other providers | AWS `AKIA…`, Google `AIza…`, Slack `xox…` |
| credentials in a URL | a user name and password between `://` and `@` |
| bearer literal | `Bearer` followed by 12 or more token characters |
| `x-api-key` literal | the header name followed by a quoted value |
| credential environment variables | the eight names listed under Result, assigned a value of 6 or more characters |
| password, secret, token, key assignments | a name containing password, passwd, pwd, secret, token, api key or access key, assigned a quoted value of 6 or more characters |

Generic high-entropy rule, in text files: hex runs of 32 or more characters with letters and digits and at least 3.0 bits of entropy per character; base64 or base64url runs of 32 or more characters, either with upper case, lower case and digits and at least 4.0 bits per character, or, in a wider tier, with letters and digits and at least 3.5 bits per character.

## Matches of the named rules (all reviewed)

| file | added in | present in (commits) | rule | first four | length | verdict |
|---|---|---|---|---|---|---|
| `tests/collector/test_collect.py` | `fd559b5` | 52 | password, secret, token assignment (`CLIENT_SECRET = "…"`) | `dose` | 28 | Test fixture. Its shape is four hyphen-separated words and a short suffix, not the format of a Databricks OAuth secret; the test asserts it never reaches the collector's log (line 249). |
| `tests/collector/test_collect.py` | `fd559b5` | 52 | credential environment variable (`DATABRICKS_CLIENT_SECRET`) | `CLIE` | 14 | A reference to the test constant above, not a literal. |
| `tests/collector/test_collect_air_temperature.py` | `241da68` | 32 | credential environment variable and assignment (`DATA_GOV_SG_API_KEY`) | `SECR` | 22 | Test fixture: three upper-case words and a short suffix. |
| `scripts/static/geocode_hdb.py` | `917e39a` | 45 | password, secret, token assignment (`TOKEN_ENV`) | `ONEM` | 12 | The name of the environment variable that holds the OneMap token (the fingerprint matches the name), not a token. |
| `scripts/static/geocode_hdb.py` | `917e39a` | 45 | password, secret, token assignment (`GET_TOKEN`) | `http` | 48 | OneMap's token endpoint URL (the fingerprint matches it), not a credential. |
| `scripts/checks/check_apikey_burst.py` | `6d86623` | 61 | `x-api-key` literal | `bear` | 6 | The name of the bearer-token header mode, one of the script's `--mode` choices (the fingerprint matches it). |

## Generic high-entropy pass

| class | distinct values | where | first four |
|---|---|---|---|
| GitHub Action commit pins | 2 | `.github/workflows/collector.yml` (added `fd559b5`) | `3d3c`, `5fda` |
| SHA-256 digests (64 hex) | 4 | `docs/checks/h10_v2.md` (the pinned label copy), `docs/checks/backtest.md` (2), `docs/checks/boundary_mp2019_vs_mp2025.md` | `4de4`, `b95f`, `bddb`, `e6ec` |
| git object ID of this repo | 1 | `docs/checks/backtest.md` | `678a` |
| MLflow run ID (the back-test run) | 1 | 5 files and one commit message | `c509` |
| UUIDs | 4 | pipeline update IDs in `docs/checks/silver_check.md` and `docs/checks/live_completeness.md`; the collector service principal's application ID in `docs/checks/service_principal_and_volume.md` (an identifier, not a secret: it grants nothing without the OAuth secret, which is held in GitHub Actions secrets); a SingStat download file name in `scripts/checks/download_static.py` | `284d`, `4110`, `4871`, `a2b9` |
| data.gov.sg dataset IDs (`d_` + 32 hex) | 16 | `docs/datasets.md` and the check reports and scripts | `d_…` |
| long identifiers and file names made of word segments (test names, a model endpoint name, file names) | 51 | 27 files, mostly under `tests/` | `test` and others |

## What this scan does not cover

- **Files never committed:** untracked or ignored files in the working tree (`.venv`, the data folders and notes outside the repository), user environment variables and the password manager.
- **Copies outside git:** GitHub Actions run logs and step summaries; the deleted `collector-test` branch on GitHub's side (it was pushed from `main`'s commits, and `ls-remote` no longer lists it); cron-job.org; Databricks workspace files, job run output and MLflow artifacts.
- **Formats no rule covers:** a secret shorter than 32 characters with no recognisable prefix and no credential-type name beside it, or one split across lines.
- **Later commits:** other windows were committing during this session, so anything after `6ca1d98` is not covered. Rerun the scan before the repository is made public or shared with the judges.

Earlier, narrower checks recorded in the project notes: 21 Oct, about 18:20 (the history searched for `dapi` and `eyJ`); 22 Oct, 01:25 (no secrets in the diff since `56d5425`); 23 Oct, 03:15 (no secret in the repository, file by file). This scan is the first to cover every commit with every rule above.

## Accepted on purpose: the user's name as a search pattern in `887d0a6`

The push check of 25 Oct 2026, 01:41 SGT, covered the 50 commits after `origin/main` (`dbe5f93`..`f8a81e5`): this scan in range mode (`--since origin/main --tip main`), its values compared with those of the scan to `dbe5f93`, and a search of every patch and commit message for the user's e-mail and user name. It found no credential and no credential-type file name. It found the user's first name once, in a line added by `887d0a6`: the personal-data rule of `scripts/checks/wording_scan.py` (line 42) spelled the name out as a search pattern. No other added line or commit message held it, and `origin/main` held none.

- **Fixed forward** in `aebe170`: the scan reads the name at run time, from `WORDING_SCAN_NAMES` or `git config user.name`, and `tests/ops/test_wording_scan.py` checks that a file holding the name is still flagged.
- **Accepted:** the line stays in `887d0a6`'s patch. The history was not rewritten and nothing was force-pushed. The same name is in the author line of every commit, including the 107 already on GitHub (`origin/main` at `dbe5f93`; all 107 checked on 25 Oct with `git log --format=%an`), so the pattern exposes nothing new. A rewrite would also have changed the hash of every commit after `887d0a6`, which the README, the write-up and the check notes cite.
- **Later push checks** allow this one match and stop on any other.
