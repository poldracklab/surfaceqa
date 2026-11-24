import nibabel as nib
import numpy as np
import pytest

from surfaceqa.sphere import target_points
from surfaceqa.thickness_map import MAP_FILE, load_thickness_map, write_thickness_map
from tests.synth import write_qa_files, write_subject

CAP = ("lh", (0.0, 0.0, 10.0), 6.0)  # within 6 mm of the top of the 10 mm ball: 34.9 degrees
CAP_DEG, STEP_DEG = 34.9, 9.0  # the synthetic mesh has a vertex about every 8 degrees


def _subject(tmp_path, plant=None, **kwargs):
    subj = write_subject(tmp_path / "src")
    write_qa_files(subj, plant=plant, **kwargs)
    run = tmp_path / "run"
    run.mkdir()
    return subj, run


def _from_top() -> np.ndarray:
    return np.degrees(np.arccos(target_points()[:, 2]))


def test_map_carries_the_planted_patch_to_the_common_points(tmp_path):
    subj, run = _subject(tmp_path, plant={"thick_patch": CAP, "thickness": 2.5})
    assert write_thickness_map(subj, run) is True
    maps = load_thickness_map(run)
    assert set(maps) == {"lh", "rh"} and maps["lh"].shape == (40962,)
    angle = _from_top()
    assert np.allclose(maps["lh"][angle < CAP_DEG - STEP_DEG], 5.0)
    assert np.allclose(maps["lh"][angle > CAP_DEG + STEP_DEG], 2.5)
    assert np.allclose(maps["rh"], 2.5)


def test_points_outside_the_cortex_label_have_no_value(tmp_path):
    subj, run = _subject(tmp_path, plant={"not_cortex": CAP})
    write_thickness_map(subj, run)
    left = load_thickness_map(run)["lh"]
    angle = _from_top()
    assert np.isnan(left[angle < CAP_DEG - STEP_DEG]).all()
    assert np.allclose(left[angle > CAP_DEG + STEP_DEG], 2.0)


def _spoil_count(subj):
    nib.freesurfer.write_morph_data(subj / "surf" / "lh.thickness", np.ones(7, dtype=np.float32))


def _spoil_missing(subj):
    (subj / "surf" / "lh.sphere.reg").unlink()


def _spoil_truncated(subj):
    path = subj / "surf" / "lh.sphere.reg"
    path.write_bytes(path.read_bytes()[:40])


def _spoil_no_label(subj):
    (subj / "label" / "lh.cortex.label").unlink()


@pytest.mark.parametrize("spoil", [_spoil_count, _spoil_missing, _spoil_truncated, _spoil_no_label])
def test_a_hemisphere_that_cannot_be_mapped_is_left_out(tmp_path, spoil):
    subj, run = _subject(tmp_path)
    spoil(subj)
    write_thickness_map(subj, run)
    assert set(load_thickness_map(run)) == {"rh"}


def test_no_registration_at_all_means_no_map(tmp_path):
    subj, run = _subject(tmp_path, sphere_reg=False)
    assert write_thickness_map(subj, run) is False
    assert load_thickness_map(run) is None and not (run / MAP_FILE).exists()


def test_a_map_is_removed_when_its_inputs_go_away(tmp_path):
    subj, run = _subject(tmp_path)
    write_thickness_map(subj, run)
    for hemi in ("lh", "rh"):
        (subj / "surf" / f"{hemi}.sphere.reg").unlink()
    assert write_thickness_map(subj, run) is True
    assert load_thickness_map(run) is None


def test_unchanged_inputs_are_not_mapped_again(tmp_path):
    subj, run = _subject(tmp_path)
    write_thickness_map(subj, run)
    stamp = (run / MAP_FILE).stat().st_mtime_ns
    assert write_thickness_map(subj, run) is False
    assert (run / MAP_FILE).stat().st_mtime_ns == stamp
    nib.freesurfer.write_morph_data(subj / "surf" / "rh.thickness",
                                    np.full(642, 3.0, dtype=np.float32))
    assert write_thickness_map(subj, run) is True
    assert np.allclose(load_thickness_map(run)["rh"], 3.0)


def test_mapping_does_not_touch_the_source(tmp_path):
    subj, run = _subject(tmp_path)
    before = {p: p.stat().st_mtime_ns for p in subj.rglob("*")}
    write_thickness_map(subj, run)
    assert {p: p.stat().st_mtime_ns for p in subj.rglob("*")} == before


def test_an_unreadable_map_file_loads_as_none(tmp_path):
    (tmp_path / MAP_FILE).write_bytes(b"junk")
    assert load_thickness_map(tmp_path) is None
