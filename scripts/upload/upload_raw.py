"""Resumable upload of coolcheck-data/raw/ to the raw-files Volume (Day 2, step 2c).

Skips files already on the Volume with the same size, so a rerun resumes. Writes a log; the last
lines are a verification of the file counts per folder against the local files and a check for .partial
files. No token is read or printed: auth comes from the CLI profile through the SDK.
Run detached: .venv/Scripts/python scripts/upload/upload_raw.py --launch
Free Edition: add --profile freeedition --volume-root /Volumes/workspace/bronze/raw_files (and a separate --log).
--include <glob> uploads only the files whose path under --src matches (for example "*_2025-0[1-3]-*" for one batch);
with it, the verification checks that every selected file is on the Volume with its size, and the per-folder counts
are reported but not required to match, since earlier batches are in the same folders.
"""
import argparse
import fnmatch
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from databricks.sdk import WorkspaceClient

PROFILE = "coolcheck"
REMOTE = "/Volumes/coolcheck/bronze/raw_files"
WORKERS = 6
ROOT_RE = re.compile(r"^/Volumes(/[A-Za-z0-9_-]+){3}$")  # /Volumes/<catalog>/<schema>/<volume>


def log(fh, msg):
    fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    fh.flush()


def remote_sizes(w, path, out):
    try:
        entries = list(w.files.list_directory_contents(path))
    except Exception:
        return
    for e in entries:
        if e.is_directory:
            remote_sizes(w, e.path, out)
        else:
            out[e.path] = e.file_size


def selected(src, include=None):
    """The local files under src, sorted; with include, only those whose path relative to src matches the glob."""
    files = sorted(p for p in src.rglob("*") if p.is_file())
    if include:
        files = [p for p in files if fnmatch.fnmatch(p.relative_to(src).as_posix(), include)]
    return files


def run(src, logfile, profile=PROFILE, remote=REMOTE, include=None, client=None):
    with open(logfile, "a", encoding="utf-8") as fh:
        w = client or WorkspaceClient(profile=profile)
        files = selected(src, include)
        log(fh, f"START {len(files)} local files, {sum(p.stat().st_size for p in files) / 1e6:.0f} MB, to {remote}"
            + (f", include {include}" if include else ""))
        have = {}
        remote_sizes(w, remote, have)
        todo = [p for p in files if have.get(f"{remote}/{p.relative_to(src).as_posix()}") != p.stat().st_size]
        log(fh, f"SKIP {len(files) - len(todo)} already present with the same size; UPLOAD {len(todo)}")
        done, failed, lock = [0], [0], threading.Lock()

        def one(p):
            dest = f"{remote}/{p.relative_to(src).as_posix()}"
            try:
                with open(p, "rb") as f:
                    w.files.upload(dest, f, overwrite=True)
                with lock:
                    done[0] += 1
                    if done[0] % 100 == 0:
                        log(fh, f"PROGRESS {done[0]}/{len(todo)} uploaded, {failed[0]} failed")
            except Exception as e:
                with lock:
                    failed[0] += 1
                    log(fh, f"FAIL {dest}: {type(e).__name__}: {str(e)[:200]}")

        with ThreadPoolExecutor(WORKERS) as ex:
            list(ex.map(one, todo))
        log(fh, f"UPLOAD DONE {done[0]} uploaded, {failed[0]} failed")
        have = {}
        remote_sizes(w, remote, have)
        # Expected counts come from the local files, per folder. Remote files in other folders (the collector's
        # live/ files) are not counted.
        expected = {}
        for p in files:
            folder = p.relative_to(src).parent.as_posix()
            expected[folder] = expected.get(folder, 0) + 1
        counts = {k: sum(1 for r in have if r.rsplit("/", 1)[0] == f"{remote}/{k}") for k in expected}
        partial = [p for p in have if p.endswith(".partial")]
        size_bad = [p for p in files if have.get(f"{remote}/{p.relative_to(src).as_posix()}") != p.stat().st_size]
        ok = (counts == expected or include is not None) and not partial and not size_bad and not failed[0]
        log(fh, f"VERIFY counts={counts} expected={expected}"
            + (" (with --include, counts may include earlier batches)" if include else "")
            + f" partial={len(partial)} size_mismatch_or_missing={len(size_bad)}")
        log(fh, "FINISHED OK" if ok else "FINISHED WITH PROBLEMS: rerun the same command to resume")
        return ok


def parse(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="../coolcheck-data/raw")
    ap.add_argument("--log", default="../coolcheck-data/upload_raw.log")
    ap.add_argument("--profile", default=PROFILE, help="Databricks CLI profile of the target workspace")
    ap.add_argument("--volume-root", default=REMOTE, help="/Volumes/<catalog>/<schema>/<volume> to upload into")
    ap.add_argument("--include", help="upload only files whose path under --src matches this glob")
    ap.add_argument("--launch", action="store_true", help="start this script detached and return")
    return ap.parse_args(argv)


def child_argv(a):
    """The command the detached process runs: every option except --launch."""
    argv = [sys.executable, __file__, "--src", a.src, "--log", a.log, "--profile", a.profile,
            "--volume-root", a.volume_root]
    return argv + (["--include", a.include] if a.include else [])


def main(argv=None):
    a = parse(argv)
    a.volume_root = a.volume_root.rstrip("/")
    if not ROOT_RE.match(a.volume_root):
        print("--volume-root must look like /Volumes/<catalog>/<schema>/<volume>", file=sys.stderr)
        return 2
    if a.launch:
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        subprocess.Popen(child_argv(a), creationflags=flags,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        print(f"launched; log: {a.log}")
        return 0
    return 0 if run(Path(a.src), a.log, a.profile, a.volume_root, a.include) else 1


if __name__ == "__main__":
    sys.exit(main())
