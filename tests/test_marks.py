import shutil

import nibabel as nib
import numpy as np
import pytest

from surfaceqa.build import build_subject, load_meta
from surfaceqa.discover import find_subjects
from surfaceqa.geometry import load_display_volume, to_grid
from surfaceqa.marks import locate_mark, locate_marks


@pytest.fixture
def subject(synth_subject, tmp_path):
    ref = find_subjects([synth_subject])[0]
    build_subject(ref, tmp_path / "qa")
    return synth_subject, load_meta(tmp_path / "qa", ref.key)


def _mark_at_vertex(subj, surface: str, index: int) -> tuple[dict, np.ndarray]:
    verts, _ = nib.freesurfer.read_geometry(subj / "surf" / surface)
    grid = to_grid(verts[index:index + 1], load_display_volume(subj / "mri" / "orig.mgz").tkr_to_grid)[0]
    mark = {"region": "sinus", "kind": "pial_out", "grid": [float(v) for v in grid],
            "surface": surface, "finding": None, "note": ""}
    return mark, verts[index]


def test_mark_on_a_vertex_gets_that_vertex_and_its_tkr_coordinate(subject):
    subj, meta = subject
    mark, vertex = _mark_at_vertex(subj, "lh.pial", 17)
    located = locate_mark(mark, meta)
    assert located["vertex"] == 17
    assert np.allclose(located["tkr"], vertex, atol=0.01)
    assert located["region"] == "sinus" and "vertex" not in mark


def test_mark_near_a_vertex_of_another_surface_uses_its_own_surface(subject):
    subj, meta = subject
    mark, _ = _mark_at_vertex(subj, "rh.white", 40)
    assert locate_mark(mark, meta)["vertex"] == 40


def test_mark_without_a_surface_has_no_vertex_but_has_tkr(subject):
    subj, meta = subject
    mark, vertex = _mark_at_vertex(subj, "lh.pial", 17)
    located = locate_mark({**mark, "surface": None}, meta)
    assert located["vertex"] is None
    assert np.allclose(located["tkr"], vertex, atol=0.01)


def test_mark_is_located_without_the_source_folder(subject):
    subj, meta = subject
    mark, vertex = _mark_at_vertex(subj, "lh.pial", 17)
    shutil.rmtree(subj)
    located = locate_mark(mark, meta)
    assert located["vertex"] is None
    assert np.allclose(located["tkr"], vertex, atol=0.01)


def test_locate_marks_locates_every_mark_of_a_review(subject):
    subj, meta = subject
    first, _ = _mark_at_vertex(subj, "lh.pial", 3)
    second, _ = _mark_at_vertex(subj, "lh.white", 9)
    review = locate_marks({"marks": [first, second], "grade": "B"}, meta)
    assert [m["vertex"] for m in review["marks"]] == [3, 9]
    assert review["grade"] == "B"
