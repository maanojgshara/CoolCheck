"""scripts/free_edition: copy_live_free.py (selection by run stamp, order, skip, no overwrite, verification) and
compare_ws.py (the diff: exact and within a tolerance, missing values, the largest numeric difference). A fake file
store stands in for the workspaces; nothing here touches one."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "free_edition"))

import compare_ws as W  # noqa: E402
import copy_live_free as C  # noqa: E402

SRC, DST = "/Volumes/coolcheck/bronze/raw_files", "/Volumes/workspace/bronze/raw_files"


class FakeFiles:
    def __init__(self, store=None):
        self.store, self.uploads = dict(store or {}), []

    def list_directory_contents(self, path):
        path, kids = path.rstrip("/"), {}
        for key, body in self.store.items():
            if key.startswith(path + "/"):
                rest = key[len(path) + 1:]
                kids[f"{path}/{rest.split('/', 1)[0]}"] = None if "/" in rest else len(body)
        if not kids:
            raise FileNotFoundError(path)
        return [SimpleNamespace(path=p, is_directory=s is None, file_size=s) for p, s in kids.items()]

    def download(self, path):
        import io
        return SimpleNamespace(contents=io.BytesIO(self.store[path]))

    def upload(self, dest, f, overwrite=True):
        assert overwrite is False, "the copy must never overwrite"
        if dest in self.store:
            raise RuntimeError("exists")
        self.store[dest] = f.read()
        self.uploads.append(dest)


def client(store=None):
    return SimpleNamespace(files=FakeFiles(store))


def name(feed, stamp, run="1"):
    day = stamp[:10]
    return f"{feed}/live/{day}/{feed}_{stamp}_{run}.jsonl"


STAMPS = ["2026-10-24T001500", "2026-10-24T004524", "2026-10-24T010046", "2026-10-23T235900"]


def source():
    return {f"{SRC}/{name(f, s)}": f"{f}{s}".encode() for s in STAMPS for f in ("wbgt", "air_temperature")}


def test_stages_split_at_the_cutoff_and_keep_run_stamp_order():
    files = {r[len(SRC) + 1:]: 1 for r in source()}
    one = C.select(files, "1", "2026-10-24T004524")
    two = C.select(files, "2", "2026-10-24T004524")
    assert [C.sort_key(r)[0] for r in one] == ["2026-10-23T235900"] * 2 + ["2026-10-24T001500"] * 2 + ["2026-10-24T004524"] * 2
    assert [C.sort_key(r)[0] for r in two] == ["2026-10-24T010046"] * 2
    assert len(one) + len(two) == len(C.select(files, "all", None))
    with pytest.raises(ValueError):
        C.select(files, "1", None)


def test_copy_goes_in_stamp_order_one_file_at_a_time_and_verifies(tmp_path):
    src, dst = client(source()), client()
    assert C.run(src, dst, SRC, DST, "1", "2026-10-24T004524", tmp_path / "log", dry_run=False)
    stamps = [C.sort_key(p[len(DST) + 1:])[0] for p in dst.files.uploads]
    assert stamps == sorted(stamps) and len(stamps) == 6
    assert "FINISHED OK" in (tmp_path / "log").read_text()
    assert not any("010046" in p for p in dst.files.uploads)


def test_rerun_skips_files_present_and_never_overwrites(tmp_path):
    src, dst = client(source()), client()
    C.run(src, dst, SRC, DST, "all", None, tmp_path / "log")
    n = len(dst.files.uploads)
    assert C.run(src, dst, SRC, DST, "all", None, tmp_path / "log") and len(dst.files.uploads) == n


def test_a_file_with_another_size_stops_the_run_and_is_left_alone(tmp_path):
    src = client(source())
    odd = f"{DST}/{name('wbgt', '2026-10-24T001500')}"
    dst = client({odd: b"different"})
    assert not C.run(src, dst, SRC, DST, "all", None, tmp_path / "log")
    assert dst.files.store[odd] == b"different" and not dst.files.uploads


def test_dry_run_writes_nothing(tmp_path):
    dst = client()
    assert C.run(client(source()), dst, SRC, DST, "all", None, tmp_path / "log", dry_run=True)
    assert not dst.files.uploads


def test_roots_and_profiles_are_checked(tmp_path, capsys):
    def argv(src_profile="a", dst_profile="b", src_root=SRC):
        return ["--src-profile", src_profile, "--dst-profile", dst_profile, "--src-root", src_root, "--dst-root", DST,
                "--stage", "all", "--log", str(tmp_path / "l")]

    assert C.main(argv(src_root="C:/Program Files/Git/Volumes/x/y/z")) == 2  # a path Git Bash rewrote
    assert C.main(argv(dst_profile="a")) == 2                                 # same workspace on both sides


# ------------------------------------------------------------------------------------------------ the diff
def test_diff_equal_and_different():
    a = {"x": {"2026-10-24": [10, 123456789012345678901234567890], "p": 0.25}, "y": 3}
    n, diffs, largest = W.compare(a, a)
    assert (n, diffs, largest) == (4, [], None)
    b = {"x": {"2026-10-24": [10, 123456789012345678901234567891], "p": 0.2500000001}, "y": 3, "z": 1}
    n, diffs, largest = W.compare(a, b)
    paths = [d[0] for d in diffs]
    assert "x.2026-10-24[1]" in paths and "x.p" in paths and "z" in paths
    assert largest == (1, "x.2026-10-24[1]")


def test_tolerance_applies_to_numbers_only():
    a, b = {"p": 0.25, "t": "High"}, {"p": 0.2500000001, "t": "Medium"}
    _, diffs, largest = W.compare(a, b, tolerance=1e-9)
    assert [d[0] for d in diffs] == ["t"]
    assert largest[1] == "p" and largest[0] < 1e-9


def test_booleans_are_not_numbers():
    _, diffs, _ = W.compare({"f": True}, {"f": False})
    assert [d[0] for d in diffs] == ["f"]


def test_jsonable_decimals_dates_and_nested():
    import datetime as dt
    import decimal
    out = W.jsonable({"h": decimal.Decimal("12345678901234567890"), "d": dt.date(2026, 10, 24),
                      "l": [decimal.Decimal("1.5")]})
    assert out == {"h": 12345678901234567890, "d": "2026-10-24", "l": [1.5]}
