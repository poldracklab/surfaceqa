import json

import nibabel as nib
import numpy as np
import pytest

from PIL import Image

from surfaceqa.build import BUILD_FORMAT, build_all, build_subject, load_meta
from surfaceqa.contours import unpack_slice
from surfaceqa.discover import find_subjects
from surfaceqa.qa import load_findings
from tests.synth import icosphere, write_qa_files, write_subject


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


def _rewrite_t1(subject, data=None, shift_mm=0.0):
    from surfaceqa.pipelines import subject_files
    path = subject_files(subject).t1
    img = nib.load(path)
    affine = img.affine.copy()
    affine[0, 3] += shift_mm
    data = np.asarray(img.dataobj) if data is None else data
    nib.save(nib.MGHImage(data, affine, img.header), path)


def _slice_bytes(qa, key, run) -> bytes:
    return (qa / "subjects" / key / "runs" / run / "slices" / "axial" / "020.jpg").read_bytes()


def test_rebuild_after_the_t1_intensities_change_is_a_new_run_with_new_images(built, synth_subject):
    ref, qa, res = built
    _rewrite_t1(synth_subject, data=np.zeros((32, 40, 48), dtype=np.uint8))
    new = build_subject(ref, qa)
    assert new.status == "built" and new.run != res.run
    assert _slice_bytes(qa, ref.key, new.run) != _slice_bytes(qa, ref.key, res.run)
    assert load_meta(qa, ref.key)["run"] == new.run
    assert {p.name for p in (qa / "subjects" / ref.key / "runs").iterdir()} == {res.run, new.run}


def test_rebuild_after_the_t1_geometry_changes_is_a_new_run_with_new_transforms(built, synth_subject):
    ref, qa, res = built
    before = np.array(load_meta(qa, ref.key)["grid_to_scanner"])
    _rewrite_t1(synth_subject, shift_mm=5.0)
    new = build_subject(ref, qa)
    after = np.array(load_meta(qa, ref.key)["grid_to_scanner"])
    assert new.status == "built" and new.run != res.run
    assert np.abs(after[:3, 3] - before[:3, 3]).max() == pytest.approx(5.0)


def test_a_review_of_the_run_before_the_t1_changed_is_not_a_review_of_the_new_run(built, synth_subject):
    from surfaceqa.review_store import earlier_reviews, load_review, submit_review
    from tests.reviewing import make_review
    ref, qa, res = built
    submit_review(qa, make_review("ann", key=ref.key, run=res.run))
    _rewrite_t1(synth_subject, shift_mm=5.0)
    new = build_subject(ref, qa)
    assert load_review(qa, ref.key, new.run, "ann") is None
    assert [r["run"] for r in earlier_reviews(qa, ref.key, new.run, "ann")] == [res.run]


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


def test_run_from_an_older_build_format_is_rebuilt(built):
    ref, qa, res = built
    meta_path = qa / "subjects" / ref.key / "runs" / res.run / "meta.json"
    meta = json.loads(meta_path.read_text())
    assert meta["format"] == BUILD_FORMAT
    meta_path.write_text(json.dumps({**meta, "format": BUILD_FORMAT - 1}))
    assert build_subject(ref, qa).status == "built"
    assert json.loads(meta_path.read_text())["format"] == BUILD_FORMAT


def test_failed_rebuild_clears_an_earlier_missing_report(tmp_path):
    subj = write_subject(tmp_path / "src", omit=("surf/rh.pial",))
    ref = find_subjects([subj])[0]
    qa = tmp_path / "qa"
    build_all([ref], qa)
    (subj / "surf" / "rh.pial").write_bytes(b"junk")
    assert build_all([ref], qa)[0].status == "failed"
    assert not (qa / "subjects" / ref.key / "missing.json").exists()


def test_anisotropic_non_lia_off_centre_subject_has_contours_on_the_anatomy(tmp_path):
    """Checked against the slice images themselves, not the geometry code."""
    subj = write_subject(tmp_path / "src", orientation="PIR", voxel=(1.0, 0.7, 1.3),
                         centre=(3.0, -2.0, 2.0))
    ref = find_subjects([subj])[0]
    qa = tmp_path / "qa"
    res = build_subject(ref, qa)
    run = qa / "subjects" / ref.key / "runs" / res.run
    for plane in ("sagittal", "coronal", "axial"):
        index = json.loads((run / f"contours_{plane}.json").read_text())
        blob = (run / f"contours_{plane}.bin").read_bytes()
        counts = np.diff(index["surfaces"]["lh.pial"])
        i = int(np.argmax(counts))  # the slice through the middle of the ball
        pts = unpack_slice(blob, index, "lh.pial", i).reshape(-1, 2)
        img = np.asarray(Image.open(run / "slices" / plane / f"{i:03d}.jpg")).astype(float)
        centre = pts.mean(axis=0)

        def sample(scale):
            xy = np.round(centre + (pts - centre) * scale).astype(int)
            return img[xy[:, 1], xy[:, 0]]

        assert (sample(0.8) > 128).mean() > 0.98, plane
        assert (sample(1.2) < 128).mean() > 0.98, plane


def test_build_writes_findings(tmp_path):
    subj = write_subject(tmp_path / "fastsurfer", shape=(64, 64, 64))
    write_qa_files(subj, plant={"ribbon_blob": ((0.0, 0.0, 16.0), 4.0)})
    ref = find_subjects([subj])[0]
    qa = tmp_path / "qa"
    res = build_subject(ref, qa)
    assert load_findings(qa, ref.key)["score"] > 0
    meta = json.loads((qa / "subjects" / ref.key / "runs" / res.run / "meta.json").read_text())
    assert meta["format"] == 4  # the run folder gained grid_to_scanner in meta.json


def test_subject_without_qa_files_builds_with_indicators_not_run(built):
    ref, qa, _ = built
    found = load_findings(qa, ref.key)
    assert found["findings"] == [] and found["score"] == 0.0
    assert all(i["status"] == "not run" for i in found["indicators"])


def test_qa_failure_keeps_the_viewer(tmp_path, monkeypatch):
    subj = write_subject(tmp_path / "fastsurfer")
    write_qa_files(subj)
    monkeypatch.setattr("surfaceqa.build.write_findings", lambda *a, **k: 1 / 0)
    ref = find_subjects([subj])[0]
    qa = tmp_path / "qa"
    res = build_subject(ref, qa)
    assert res.status == "built" and load_meta(qa, ref.key) is not None
    assert load_findings(qa, ref.key) is None
    run_dir = qa / "subjects" / ref.key / "runs" / res.run
    assert "ZeroDivisionError" in (run_dir / "qa_error.txt").read_text()


def _qa_subject(tmp_path, with_files=True):
    subj = write_subject(tmp_path / "fastsurfer", shape=(64, 64, 64))
    if with_files:
        write_qa_files(subj, plant={"ribbon_blob": ((0.0, 0.0, 16.0), 4.0)})
    return subj, find_subjects([subj])[0], tmp_path / "qa"


def test_qa_is_retried_after_a_failure(tmp_path, monkeypatch):
    subj, ref, qa = _qa_subject(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr("surfaceqa.build.write_findings", lambda *a, **k: 1 / 0)
        first = build_subject(ref, qa)
    run_dir = qa / "subjects" / ref.key / "runs" / first.run
    assert (run_dir / "qa_error.txt").exists() and load_findings(qa, ref.key) is None
    second = build_subject(ref, qa)
    assert second.status == "updated" and load_findings(qa, ref.key)["score"] > 0
    assert not (run_dir / "qa_error.txt").exists()


def test_qa_reruns_when_its_input_files_appear(tmp_path):
    subj, ref, qa = _qa_subject(tmp_path, with_files=False)
    build_subject(ref, qa)
    assert load_findings(qa, ref.key)["findings"] == []
    write_qa_files(subj, plant={"ribbon_blob": ((0.0, 0.0, 16.0), 4.0)})
    assert build_subject(ref, qa).status == "updated"
    assert load_findings(qa, ref.key)["score"] > 0


def test_unchanged_subject_does_not_recompute_findings(tmp_path):
    subj, ref, qa = _qa_subject(tmp_path)
    first = build_subject(ref, qa)
    path = qa / "subjects" / ref.key / "runs" / first.run / "findings.json"
    stamp = path.stat().st_mtime_ns
    assert build_subject(ref, qa).status == "unchanged" and path.stat().st_mtime_ns == stamp


def test_findings_are_recomputed_when_the_indicator_code_version_changes(tmp_path, monkeypatch):
    subj, ref, qa = _qa_subject(tmp_path)
    build_subject(ref, qa)
    monkeypatch.setattr("surfaceqa.qa.QA_VERSION", 10_000)
    assert build_subject(ref, qa).status == "updated"
    assert load_findings(qa, ref.key)["qa_version"] == 10_000


def test_meta_records_grid_to_tkr_that_inverts_the_display_transform(tmp_path):
    from surfaceqa.geometry import load_display_volume, to_grid, to_tkr

    subj = write_subject(tmp_path / "fastsurfer", voxel=(0.8, 1.0, 1.2), orientation="RAS",
                         cras=(3.0, -2.0, 5.0), centre=(2.0, 1.0, -3.0))
    ref = find_subjects([subj])[0]
    build_subject(ref, tmp_path / "qa")
    grid_to_tkr = np.array(load_meta(tmp_path / "qa", ref.key)["grid_to_tkr"])
    assert grid_to_tkr.shape == (4, 4)
    verts, _ = nib.freesurfer.read_geometry(subj / "surf" / "lh.pial")
    grid = to_grid(verts, load_display_volume(subj / "mri" / "orig.mgz").tkr_to_grid)
    assert np.allclose(to_tkr(grid, grid_to_tkr), verts, atol=1e-4)


def test_meta_records_grid_to_scanner(tmp_path):
    subj = write_subject(tmp_path / "fastsurfer", cras=(3.0, -2.0, 5.0))
    ref = find_subjects([subj])[0]
    build_subject(ref, tmp_path / "qa")
    meta = load_meta(tmp_path / "qa", ref.key)
    to_scanner, to_tkr = np.array(meta["grid_to_scanner"]), np.array(meta["grid_to_tkr"])
    assert to_scanner.shape == (4, 4) and np.allclose(to_scanner[:3, :3], to_tkr[:3, :3])
    # a conformed (LIA) volume: scanner coordinates are surface coordinates moved by c_ras
    assert np.allclose(to_scanner[:3, 3] - to_tkr[:3, 3], [3.0, -2.0, 5.0], atol=1e-4)


def _stages(events):
    return list(dict.fromkeys(stage for stage, _, _ in events))


@pytest.mark.parametrize("jobs", [1, 2])
def test_build_all_reports_progress(synth_sources, tmp_path, jobs):
    events = []
    refs = find_subjects(synth_sources)
    results = build_all(refs, tmp_path / "qa", jobs=jobs, progress=lambda *event: events.append(event))
    assert [r.status for r in results] == ["built", "built"]
    assert _stages(events) == ["render", "cohort", "indicators"]
    assert [e for e in events if e[0] == "render"] == [("render", 0, 2), ("render", 1, 2), ("render", 2, 2)]
    assert [e for e in events if e[0] == "cohort"] == [("cohort", 0, 1), ("cohort", 1, 1)]
    assert [e for e in events if e[0] == "indicators"] == [("indicators", 0, 2), ("indicators", 1, 2),
                                                           ("indicators", 2, 2)]


def test_build_all_without_progress_gives_the_same_results(synth_sources, tmp_path):
    refs = find_subjects(synth_sources)
    quiet = build_all(refs, tmp_path / "a")
    told = build_all(refs, tmp_path / "b", progress=lambda *event: None)
    assert quiet == told
