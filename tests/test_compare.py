import nibabel as nib
import pytest

from surfaceqa.build import build_all
from surfaceqa.compare import candidates, subject_label
from surfaceqa.discover import find_subjects
from surfaceqa.layout import current_run_dir
from surfaceqa.site import subject_records, write_site
from tests.synth import icosphere, write_subject

FAST, RECON = "fastsurfer__sub-01", "freesurfer-8.2.0__sub-01"


@pytest.mark.parametrize("name,label", [
    ("sub-07", "7"), ("subj07", "7"), ("sub-07_ses-nsdanat", "7"), ("sub-007", "7"),
    ("sub07", "7"), ("sub-17", "17"), ("sub-s03", "s03"), ("sub-0", "0"), ("control_12", "control_12"),
    ("SUB-07", "7"),
])
def test_subject_label(name, label):
    assert subject_label(name) == label


def _record(qa, key):
    return next(r for r in subject_records(qa) if r["key"] == key)


def test_the_same_subject_in_another_source_folder_is_offered(qa):
    run = current_run_dir(qa, RECON).name
    assert _record(qa, FAST)["compare"] == [{
        "group": "other", "label": "freesurfer-8.2.0 · sub-01",
        "href": f"../{RECON}/runs/{run}/viewer.html"}]
    assert [c["label"] for c in _record(qa, RECON)["compare"]] == ["fastsurfer · sub-01"]


def test_a_subject_that_could_not_be_built_is_not_offered_and_offers_nothing(qa, synth_sources):
    write_subject(synth_sources[1], name="sub-02", pipeline="freesurfer")
    build_all(find_subjects(synth_sources), qa)
    assert _record(qa, "freesurfer-8.2.0__sub-02")["compare"] == []
    assert _record(qa, "fastsurfer__sub-02")["compare"] == []


def test_sessions_of_one_person_in_the_same_folder_are_offered(tmp_path):
    for name in ("sub-07", "sub-07_ses-nsd01", "sub-08"):
        write_subject(tmp_path / "fs", name=name, pipeline="freesurfer")
    qa = tmp_path / "qa"
    build_all(find_subjects([tmp_path / "fs"]), qa)
    assert [c["label"] for c in _record(qa, "fs__sub-07")["compare"]] == ["fs · sub-07_ses-nsd01"]
    assert _record(qa, "fs__sub-08")["compare"] == []


def _rebuild_with_new_surface(qa, sources):
    vertices, faces = icosphere(9.0)
    nib.freesurfer.write_geometry(sources[0] / "sub-01" / "surf" / "lh.pial", vertices, faces)
    build_all(find_subjects(sources), qa)
    write_site(qa)


def test_an_earlier_run_is_offered_after_the_other_reconstructions(qa, synth_sources):
    old = current_run_dir(qa, FAST).name
    _rebuild_with_new_surface(qa, synth_sources)
    assert current_run_dir(qa, FAST).name != old
    other, earlier = _record(qa, FAST)["compare"]
    assert other["group"] == "other"
    assert earlier["group"] == "previous" and earlier["href"] == f"runs/{old}/viewer.html"
    assert earlier["label"].startswith("earlier run, built 20")


def test_a_run_folder_without_a_finished_render_is_not_offered(qa):
    (qa / "subjects" / FAST / "runs" / "0123456789ab").mkdir()
    assert [c["group"] for c in _record(qa, FAST)["compare"]] == ["other"]


def test_candidates_of_a_key_that_needs_quoting(tmp_path):
    record = {"key": "a b__sub-1", "name": "sub-1", "source": "a b", "has_run": True, "run": "x"}
    other = {"key": "c d__sub-01", "name": "sub-01", "source": "c d", "has_run": True, "run": "abc"}
    (found,) = candidates(tmp_path, record, [record, other])
    assert found["href"] == "../c%20d__sub-01/runs/abc/viewer.html"
