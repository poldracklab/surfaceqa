import json

import numpy as np
import pytest

from surfaceqa.cohort import load_cohort, update_cohorts
from surfaceqa.thickness_map import MAP_FILE, save_thickness_map

N = 40962
RUN = "0123456789ab"


@pytest.fixture(autouse=True)
def small_cohorts(monkeypatch):
    monkeypatch.setattr("surfaceqa.thresholds.MIN_COHORT", 5)


def _flat(value: float) -> np.ndarray:
    return np.full(N, value, dtype=np.float32)


def _add(qa, source, name, maps, run=RUN, stamp="v1"):
    """A built subject (its source folder exists) whose current run holds the given maps (or none)."""
    run_dir = qa / "subjects" / f"{source}__{name}" / "runs" / run
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir.parent.parent / "current.json").write_text(json.dumps({"run": run}))
    origin = qa / "sources" / source / name
    origin.mkdir(parents=True, exist_ok=True)
    (run_dir / "meta.json").write_text(json.dumps({"source": source, "name": name, "path": str(origin), "run": run}))
    if maps is not None:
        save_thickness_map(run_dir, maps, stamp)
    return run_dir


def _cohort(qa, values, source="fs"):
    for i, value in enumerate(values):
        _add(qa, source, f"sub-{i:02d}", {"lh": _flat(value), "rh": _flat(value + 1)})


def test_median_and_spread_per_point(tmp_path):
    values = [2.0, 2.2, 2.4, 2.6, 3.5, 2.1]
    _cohort(tmp_path, values)
    assert update_cohorts(tmp_path) == {"fs"}
    cohort = load_cohort(tmp_path, "fs")
    median = np.median(values)
    spread = 1.4826 * np.median(np.abs(np.array(values) - median))
    assert cohort.n == 6 and cohort.source == "fs"
    assert np.allclose(cohort.median["lh"], median) and np.allclose(cohort.spread["lh"], spread)
    assert np.allclose(cohort.median["rh"], median + 1)
    assert cohort.median["lh"].shape == (N,)


def test_points_with_too_few_subjects_have_no_statistics(tmp_path):
    _cohort(tmp_path, [2.0, 2.1, 2.2, 2.3])
    holed = _flat(2.4)
    holed[:100] = np.nan
    for name in ("sub-90", "sub-91"):
        _add(tmp_path, "fs", name, {"lh": holed, "rh": _flat(3.0)})
    update_cohorts(tmp_path)
    cohort = load_cohort(tmp_path, "fs")
    assert np.isnan(cohort.median["lh"][:100]).all() and np.isnan(cohort.spread["lh"][:100]).all()
    assert np.isfinite(cohort.median["lh"][100:]).all()


def test_a_subject_with_one_hemisphere_counts_for_that_hemisphere_only(tmp_path):
    _cohort(tmp_path, [2.0, 2.1, 2.2, 2.3])
    _add(tmp_path, "fs", "sub-90", {"rh": _flat(3.0)})
    update_cohorts(tmp_path)
    cohort = load_cohort(tmp_path, "fs")
    assert cohort.n == 5
    assert np.isnan(cohort.median["lh"]).all() and np.isfinite(cohort.median["rh"]).all()


def test_too_few_subjects_is_off_and_says_how_many(tmp_path):
    _cohort(tmp_path, [2.0, 2.1, 2.2, 2.3])
    _add(tmp_path, "fs", "sub-nomap", None)
    assert update_cohorts(tmp_path) == {"fs"}
    cohort = load_cohort(tmp_path, "fs")
    assert cohort.n == 4 and cohort.median is None and cohort.spread is None
    assert not (tmp_path / "cohort" / "fs.npz").exists()


def test_never_computed_is_none(tmp_path):
    assert load_cohort(tmp_path, "fs") is None
    assert update_cohorts(tmp_path) == set()


def test_unchanged_cohort_is_not_recomputed(tmp_path):
    _cohort(tmp_path, [2.0, 2.1, 2.2, 2.3, 2.4])
    update_cohorts(tmp_path)
    first = load_cohort(tmp_path, "fs").signature
    stamp = (tmp_path / "cohort" / "fs.npz").stat().st_mtime_ns
    assert update_cohorts(tmp_path) == set()
    assert (tmp_path / "cohort" / "fs.npz").stat().st_mtime_ns == stamp
    assert load_cohort(tmp_path, "fs").signature == first


def test_a_new_subject_a_new_run_or_a_new_map_changes_the_signature(tmp_path):
    _cohort(tmp_path, [2.0, 2.1, 2.2, 2.3, 2.4])
    update_cohorts(tmp_path)
    seen = {load_cohort(tmp_path, "fs").signature}
    _add(tmp_path, "fs", "sub-new", {"lh": _flat(9.0), "rh": _flat(9.0)})
    assert update_cohorts(tmp_path) == {"fs"}
    seen.add(load_cohort(tmp_path, "fs").signature)
    _add(tmp_path, "fs", "sub-new", {"lh": _flat(9.0), "rh": _flat(9.0)}, run="ba9876543210")
    assert update_cohorts(tmp_path) == {"fs"}
    seen.add(load_cohort(tmp_path, "fs").signature)
    _add(tmp_path, "fs", "sub-new", {"lh": _flat(1.0), "rh": _flat(1.0)}, run="ba9876543210", stamp="v2")
    assert update_cohorts(tmp_path) == {"fs"}
    seen.add(load_cohort(tmp_path, "fs").signature)
    assert len(seen) == 4


def test_a_cohort_that_shrinks_below_the_minimum_is_switched_off(tmp_path):
    _cohort(tmp_path, [2.0, 2.1, 2.2, 2.3, 2.4])
    update_cohorts(tmp_path)
    (tmp_path / "subjects" / "fs__sub-00" / "runs" / RUN / MAP_FILE).unlink()
    assert update_cohorts(tmp_path) == {"fs"}
    assert load_cohort(tmp_path, "fs").median is None
    assert not (tmp_path / "cohort" / "fs.npz").exists()


def test_source_folders_are_separate_cohorts(tmp_path):
    _cohort(tmp_path, [2.0] * 5, source="fs")
    _cohort(tmp_path, [4.0] * 3, source="fast")
    assert update_cohorts(tmp_path) == {"fs", "fast"}
    assert np.allclose(load_cohort(tmp_path, "fs").median["lh"], 2.0)
    assert load_cohort(tmp_path, "fast").n == 3 and load_cohort(tmp_path, "fast").median is None
    _add(tmp_path, "fast", "sub-new", {"lh": _flat(4.0), "rh": _flat(4.0)})
    assert update_cohorts(tmp_path) == {"fast"}


def test_statistics_lost_from_disk_read_as_off(tmp_path):
    _cohort(tmp_path, [2.0] * 5)
    update_cohorts(tmp_path)
    (tmp_path / "cohort" / "fs.npz").write_bytes(b"junk")
    assert load_cohort(tmp_path, "fs").median is None


# ---- who belongs to a cohort --------------------------------------------------------------

def test_a_subject_removed_from_its_source_folder_leaves_the_cohort(tmp_path):
    _cohort(tmp_path, [2.0, 2.1, 2.2, 2.3, 2.4, 9.0])
    update_cohorts(tmp_path)
    (tmp_path / "sources" / "fs" / "sub-05").rmdir()
    assert update_cohorts(tmp_path) == {"fs"}
    cohort = load_cohort(tmp_path, "fs")
    assert cohort.n == 5 and np.allclose(cohort.median["lh"], 2.2)


@pytest.mark.parametrize("flag", ["missing.json", "error.txt"])
def test_a_subject_whose_latest_build_did_not_succeed_is_not_a_member(tmp_path, flag):
    _cohort(tmp_path, [2.0, 2.1, 2.2, 2.3, 2.4, 9.0])
    (tmp_path / "subjects" / "fs__sub-05" / flag).write_text("{}")
    update_cohorts(tmp_path)
    assert load_cohort(tmp_path, "fs").n == 5


def test_the_source_is_the_one_recorded_for_the_run_not_a_piece_of_the_key(tmp_path):
    _cohort(tmp_path, [2.0] * 5, source="my__fs")
    _cohort(tmp_path, [4.0] * 5, source="my__other")
    assert update_cohorts(tmp_path) == {"my__fs", "my__other"}
    assert np.allclose(load_cohort(tmp_path, "my__fs").median["lh"], 2.0)
    assert np.allclose(load_cohort(tmp_path, "my__other").median["lh"], 4.0)
    assert load_cohort(tmp_path, "my") is None


def test_a_run_without_a_readable_meta_is_not_a_member(tmp_path):
    _cohort(tmp_path, [2.0] * 6)
    (tmp_path / "subjects" / "fs__sub-05" / "runs" / RUN / "meta.json").write_text("junk")
    update_cohorts(tmp_path)
    assert load_cohort(tmp_path, "fs").n == 5


def test_unreadable_statistics_are_computed_again(tmp_path):
    _cohort(tmp_path, [2.0] * 5)
    update_cohorts(tmp_path)
    (tmp_path / "cohort" / "fs.npz").write_bytes(b"junk")
    assert update_cohorts(tmp_path) == {"fs"}
    assert np.allclose(load_cohort(tmp_path, "fs").median["lh"], 2.0)
