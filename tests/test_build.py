import json

import nibabel as nib
import numpy as np
import pytest

from surfaceqa.build import build_all, build_subject, load_meta
from surfaceqa.contours import unpack_slice
from surfaceqa.discover import find_subjects
from tests.synth import icosphere, write_subject


@pytest.fixture
def built(synth_subject, tmp_path):
    ref = find_subjects([synth_subject])[0]
    qa = tmp_path / "qa"
    return ref, qa, build_subject(ref, qa)


def test_build_subject_writes_run(built):
    ref, qa, res = built
    run = qa / "subjects" / "fastsurfer__sub-01" / "runs" / res.run
    assert res.status == "built"
    assert json.loads((run.parent.parent / "current.json").read_text()) == {"run": res.run}
    meta = json.loads((run / "meta.json").read_text())
    assert meta["pipeline"] == "fastsurfer" and meta["version"] == "2.6.1"
    assert meta["shape"] == [32, 48, 40]
    assert meta["planes"]["coronal"]["n_slices"] == 48
    assert meta["planes"]["coronal"]["width"] == 32 and meta["planes"]["coronal"]["height"] == 40
    assert meta["surfaces"]["rh.white"]["color"] == "#ff3b30"
    assert len(list((run / "slices" / "sagittal").glob("*.jpg"))) == 32
    for plane in ("sagittal", "coronal", "axial"):
        assert (run / f"contours_{plane}.bin").stat().st_size > 0
        assert "surfaces" in json.loads((run / f"contours_{plane}.json").read_text())


def test_built_contours_lie_on_the_sphere(built):
    ref, qa, res = built
    run = qa / "subjects" / ref.key / "runs" / res.run
    index = json.loads((run / "contours_axial.json").read_text())
    # the tkr origin is grid (15, 24, 19): cut the pial sphere through its centre
    segs = unpack_slice((run / "contours_axial.bin").read_bytes(), index, "lh.pial", 19)
    # axial screen: x = 31 - R, y = 47 - A; centre (15, 24) -> (16, 23); radius 10
    r = np.hypot(segs[:, 0] - 16.0, segs[:, 1] - 23.0)
    assert len(segs) > 0 and np.allclose(r, 10.0, atol=0.1)


def test_build_never_writes_into_the_source(built, synth_subject):
    before = {p: p.stat().st_mtime_ns for p in synth_subject.rglob("*")}
    ref, qa, _ = built
    build_subject(ref, qa)
    assert {p: p.stat().st_mtime_ns for p in synth_subject.rglob("*")} == before


def test_rebuild_unchanged_is_noop(built):
    ref, qa, res = built
    meta_path = qa / "subjects" / ref.key / "runs" / res.run / "meta.json"
    stamp = meta_path.stat().st_mtime_ns
    again = build_subject(ref, qa)
    assert again.status == "unchanged" and again.run == res.run
    assert meta_path.stat().st_mtime_ns == stamp


def test_rebuild_after_surface_change_keeps_old_run(built, synth_subject):
    ref, qa, res = built
    v, f = icosphere(9.0)
    nib.freesurfer.write_geometry(synth_subject / "surf" / "lh.pial", v, f)
    new = build_subject(ref, qa)
    runs = qa / "subjects" / ref.key / "runs"
    assert new.status == "built" and new.run != res.run
    assert {p.name for p in runs.iterdir()} == {res.run, new.run}
    assert json.loads((runs.parent / "current.json").read_text()) == {"run": new.run}


def test_build_subject_missing_files(tmp_path):
    subj = write_subject(tmp_path / "src", omit=("surf/rh.pial",))
    ref = find_subjects([subj])[0]
    res = build_subject(ref, tmp_path / "qa")
    assert res.status == "missing" and res.missing == ["surf/rh.pial"] and res.run is None
    info = json.loads((tmp_path / "qa" / "subjects" / ref.key / "missing.json").read_text())
    assert info["missing"] == ["surf/rh.pial"]


def test_interrupted_build_is_redone(built):
    ref, qa, res = built
    (qa / "subjects" / ref.key / "runs" / res.run / "meta.json").unlink()
    assert build_subject(ref, qa).status == "built"


def test_build_all_survives_a_broken_subject(synth_sources, tmp_path):
    (synth_sources[1] / "sub-01" / "surf" / "lh.white").write_bytes(b"not a surface")
    results = build_all(find_subjects(synth_sources), tmp_path / "qa", jobs=2)
    assert [r.status for r in results] == ["built", "failed"]
    assert (tmp_path / "qa" / "subjects" / "freesurfer-8.2.0__sub-01" / "error.txt").exists()


def test_load_meta(built):
    ref, qa, res = built
    assert load_meta(qa, ref.key)["run"] == res.run
    assert load_meta(qa, "nope__nobody") is None
