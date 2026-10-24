"""Copy the collector's live/ files from one raw-files Volume to another (trial -> Free Edition), one file at a time in
the order Silver ranks them. Only the source is read; the destination gets new files and nothing is overwritten.

    .venv\\Scripts\\python scripts/free_edition/copy_live_free.py --src-profile coolcheck --dst-profile freeedition
        --src-root /Volumes/coolcheck/bronze/raw_files --dst-root /Volumes/workspace/bronze/raw_files
        --stage 1 --cutoff 2026-10-24T004524 --log <log file> [--dry-run]

Why one at a time, in name order: Silver keeps the copy with the latest file time (source_rank, file_mtime, source_file,
content_hash), and the destination's file time is the upload time. On the source, file time order equals name order for
every feed; uploading sequentially in (run stamp, feed) order keeps that, which matters where two live copies of a
reading disagree (air temperature). Run MSYS_NO_PATHCONV=1 in Git Bash so /Volumes paths are not rewritten.

--stage 1 copies the files whose run stamp (the YYYY-MM-DDTHHMMSS in the name) is at or before --cutoff, stage 2 those
after it, all both. A file already at the destination with the same size is skipped; with another size it is reported and
left alone. The log ends with a check that every selected file is at the destination with the source's size.
"""
import argparse
import io
import re
import sys
import time
from pathlib import Path

FEEDS = ("wbgt", "rainfall", "forecast", "air_temperature")
ROOT_RE = re.compile(r"^/Volumes(/[A-Za-z0-9_-]+){3}$")  # /Volumes/<catalog>/<schema>/<volume>
NAME_RE = re.compile(r"^(?P<feed>[a-z_]+)_(?P<stamp>\d{4}-\d{2}-\d{2}T\d{6})_(?P<run>[^.]+)\.jsonl$")


def log(fh, msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    fh.write(line + "\n")
    fh.flush()
    print(line, flush=True)


def list_files(w, path, out):
    """Every file under path as {path: size}; a missing folder is empty."""
    try:
        entries = list(w.files.list_directory_contents(path))
    except Exception:  # noqa: BLE001 - a folder that does not exist yet
        return out
    for e in entries:
        if e.is_directory:
            list_files(w, e.path.rstrip("/"), out)
        else:
            out[e.path] = e.file_size
    return out


def live_files(w, root):
    """{path relative to root: size} for <root>/<feed>/live/** of every feed."""
    out = {}
    for feed in FEEDS:
        found = list_files(w, f"{root}/{feed}/live", {})
        out.update({p[len(root) + 1:]: s for p, s in found.items()})
    return out


def sort_key(rel):
    m = NAME_RE.match(rel.rsplit("/", 1)[-1])
    if not m:
        raise ValueError(f"not a collector file name: {rel}")
    return (m["stamp"], m["feed"], m["run"])


def select(files, stage, cutoff):
    """The relative paths of this stage, in copy order. Stage 1: stamp <= cutoff; 2: stamp > cutoff; all: everything."""
    if stage != "all" and not cutoff:
        raise ValueError("--cutoff is required for stage 1 and 2")
    keep = [r for r in files if r.endswith(".jsonl")]
    if stage == "1":
        keep = [r for r in keep if sort_key(r)[0] <= cutoff]
    elif stage == "2":
        keep = [r for r in keep if sort_key(r)[0] > cutoff]
    return sorted(keep, key=sort_key)


def run(src_w, dst_w, src_root, dst_root, stage, cutoff, logfile, dry_run=False):
    with open(logfile, "a", encoding="utf-8") as fh:
        src = live_files(src_w, src_root)
        have = live_files(dst_w, dst_root)
        todo_all = select(src, stage, cutoff)
        todo = [r for r in todo_all if have.get(r) != src[r]]
        clash = [r for r in todo_all if r in have and have[r] != src[r]]
        mb = sum(src[r] for r in todo_all) / 1e6
        log(fh, f"START stage {stage}, cutoff {cutoff or '-'}: {len(todo_all)} files, {mb:.2f} MB selected from {src_root} "
                f"({len(src)} live files there); {len(todo_all) - len(todo)} already at {dst_root} with the same size; "
                f"copy {len(todo)}" + ("; DRY RUN, nothing written" if dry_run else ""))
        if clash:
            log(fh, f"STOP: {len(clash)} file(s) at the destination with another size, left alone: {clash[:5]}")
            return False
        if dry_run:
            for r in todo[:3] + todo[-3:]:
                log(fh, f"  would copy {r} ({src[r]} bytes)")
            return True
        done, failed = 0, []
        for r in todo:
            try:
                body = src_w.files.download(f"{src_root}/{r}").contents.read()
                if len(body) != src[r]:
                    raise RuntimeError(f"downloaded {len(body)} bytes, listing says {src[r]}")
                dst_w.files.upload(f"{dst_root}/{r}", io.BytesIO(body), overwrite=False)
                done += 1
                if done % 50 == 0:
                    log(fh, f"PROGRESS {done}/{len(todo)} copied, {len(failed)} failed")
            except Exception as e:  # noqa: BLE001 - recorded, and the run stops: order matters
                failed.append(r)
                log(fh, f"FAIL {r}: {type(e).__name__}: {str(e)[:200]}")
                break
        log(fh, f"COPY DONE {done} copied, {len(failed)} failed")
        after = live_files(dst_w, dst_root)
        bad = [r for r in todo_all if after.get(r) != src[r]]
        partial = [p for p in after if p.endswith(".partial")]
        log(fh, f"VERIFY selected {len(todo_all)}, missing or wrong size {len(bad)}, .partial {len(partial)}, "
                f"live files at the destination {len(after)}")
        ok = not bad and not partial and not failed
        log(fh, "FINISHED OK" if ok else f"FINISHED WITH PROBLEMS: {bad[:5]}")
        return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--src-profile", required=True, help="CLI profile of the workspace read from")
    ap.add_argument("--dst-profile", required=True, help="CLI profile of the workspace written to")
    ap.add_argument("--src-root", required=True, help="/Volumes/<catalog>/<schema>/<volume> to read")
    ap.add_argument("--dst-root", required=True, help="/Volumes/<catalog>/<schema>/<volume> to write")
    ap.add_argument("--stage", choices=["1", "2", "all"], required=True)
    ap.add_argument("--cutoff", help="run stamp YYYY-MM-DDTHHMMSS: stage 1 is at or before it, stage 2 after it")
    ap.add_argument("--log", required=True)
    ap.add_argument("--dry-run", action="store_true", help="list and count only; nothing is written")
    a = ap.parse_args(argv)
    for r in (a.src_root, a.dst_root):
        if not ROOT_RE.match(r.rstrip("/")):
            print("roots must look like /Volumes/<catalog>/<schema>/<volume>", file=sys.stderr)
            return 2
    if a.src_profile == a.dst_profile:
        print("source and destination profiles are the same", file=sys.stderr)
        return 2
    if a.cutoff and not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{6}", a.cutoff):
        print("--cutoff must look like 2026-10-24T004524", file=sys.stderr)
        return 2
    from databricks.sdk import WorkspaceClient

    ok = run(WorkspaceClient(profile=a.src_profile), WorkspaceClient(profile=a.dst_profile), a.src_root.rstrip("/"),
             a.dst_root.rstrip("/"), a.stage, a.cutoff, Path(a.log), a.dry_run)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
