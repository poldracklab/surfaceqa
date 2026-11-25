import json

import numpy as np
import pytest

from surfaceqa import thresholds
from surfaceqa.pipelines import detect_pipeline
from surfaceqa.findings import Finding
from surfaceqa.qa import relabel_by_region, write_findings
from surfaceqa.scoring import suspicion_score
from surfaceqa.subjectdata import load_subject_data
from tests.synth import write_qa_files, write_subject

BLOB = ((0.0, 0.0, 16.0), 4.0)  # a ball of extra ribbon 2 mm clear of the 10 mm synthetic brain


@pytest.fixture
def planted(tmp_path):
    subj = write_subject(tmp_path / "fastsurfer", shape=(64, 64, 64))
    write_qa_files(subj, plant={"ribbon_blob": BLOB, "thick_patch": ("lh", (0.0, 10.0, 0.0), 7.0)})
    return subj


def test_clean_synthetic_subject_scores_zero(tmp_path):
    subj = write_subject(tmp_path / "fastsurfer", shape=(64, 64, 64))
    write_qa_files(subj)
    out = write_findings(load_subject_data(subj, detect_pipeline(subj)), tmp_path)
    assert out["score"] == 0.0 and out["findings"] == []
    assert {i["status"] for i in out["indicators"]} <= {"ran", "not run"}


def test_planted_errors_are_found_and_written(planted, tmp_path):
    out = write_findings(load_subject_data(planted, detect_pipeline(planted)), tmp_path)
    kinds = {f["indicator"] for f in out["findings"]}
    assert {"ribbon_outside_brain", "thick_patches"} <= kinds
    assert out["score"] > 0 and [f["id"] for f in out["findings"]] == list(range(len(out["findings"])))
    assert out["findings"] == sorted(out["findings"], key=lambda f: -f["points"])
    assert json.loads((tmp_path / "findings.json").read_text()) == out
    blob = np.frombuffer((tmp_path / "findings_voxels.bin").read_bytes(), "<u2").reshape(-1, 3)
    assert len(blob) == sum(f["voxel_count"] for f in out["findings"])
    f0 = next(f for f in out["findings"] if f["indicator"] == "ribbon_outside_brain")
    vox = blob[f0["voxel_start"]:f0["voxel_start"] + f0["voxel_count"]]
    assert tuple(f0["grid"]) in {tuple(v) for v in vox.tolist()}


def test_findings_carry_a_region_and_thresholds_are_recorded(planted, tmp_path):
    out = write_findings(load_subject_data(planted, detect_pipeline(planted)), tmp_path)
    assert all(f["region"] for f in out["findings"])
    assert out["thresholds"]["MARGIN_MM"] == 1.0
    assert set(out["defaults"]) >= {"sinus", "crossing"}


def test_skipped_indicators_are_reported(tmp_path):
    subj = write_subject(tmp_path / "fs", pipeline="freesurfer", shape=(64, 64, 64))
    write_qa_files(subj, pipeline="freesurfer")
    out = write_findings(load_subject_data(subj, detect_pipeline(subj)), tmp_path)
    skipped = {i["name"]: i["reason"] for i in out["indicators"] if i["status"] == "not run"}
    assert "ribbon_in_nonbrain_mask" in skipped and all(skipped.values())
    assert "missed_gray" not in skipped  # against an atlas segmentation it gives places to look


def test_findings_are_capped_and_the_cap_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(thresholds, "MAX_FINDINGS_PER_INDICATOR", 1)
    subj = write_subject(tmp_path / "fastsurfer", shape=(64, 64, 64))
    write_qa_files(subj, plant={"ribbon_blob": BLOB})
    data = load_subject_data(subj, detect_pipeline(subj))
    data.ribbon[2:8, 2:8, 2:8] = 3  # a second blob
    out = write_findings(data, tmp_path)
    ind = next(i for i in out["indicators"] if i["name"] == "ribbon_outside_brain")
    assert ind["n_findings"] == 1 and ind["dropped"] == 1


def test_findings_record_how_the_score_was_computed(planted, tmp_path):
    out = write_findings(load_subject_data(planted, detect_pipeline(planted)), tmp_path)
    assert out["scoring"]["WEIGHT"]["topology"] == 0.2 and out["scoring"]["UNIT"] == 100.0
    assert out["scoring"]["CAP"] == 10.0 and isinstance(out["qa_version"], int)


def test_score_of_no_findings_is_a_float():
    assert isinstance(suspicion_score([]), float)


def test_places_to_look_come_after_findings_and_leave_the_score_alone(tmp_path):
    subj = write_subject(tmp_path / "fs6", pipeline="freesurfer", shape=(64, 64, 64))
    write_qa_files(subj, pipeline="freesurfer",
                   plant={"ribbon_blob": BLOB, "seg_blob": ((0.0, 16.0, 0.0), 4.0)})
    out = write_findings(load_subject_data(subj, detect_pipeline(subj)), tmp_path)
    kinds = [f["kind"] for f in out["findings"]]
    assert kinds == ["pial_out", "look_here"]
    assert out["score"] == round(out["findings"][0]["points"], 1) and out["findings"][1]["points"] == 0


@pytest.mark.parametrize("region,kind", [
    ("sinus", "look_here"), ("cerebellum", "look_here"), ("outer_edge", "look_here"),
    ("frontal_midline", "look_here"),
    ("orbitofrontal", "gray_missed"), ("inferior_temporal", "gray_missed"),
    ("medial_temporal", "gray_missed"),
])
def test_cortex_label_beyond_the_pial_surface_is_named_by_where_it_is(region, kind):
    # Next to the sinus or the edge of the brain, a segmentation's "cortex" outside the pial
    # surface is usually sinus or dura that the surface was right to leave out (seen on the
    # recon-all 8.2 reconstruction of NSD subject 07). Calling it "gray matter missed" there
    # is wrong. Under the frontal and temporal lobes it is where gray matter does get missed.
    f = Finding("missed_gray", "gray_missed", (1, 2, 3), 79.0, 79, region=region)
    relabel_by_region([f])
    assert f.kind == kind


def test_other_kinds_are_left_alone_by_relabelling():
    f = Finding("ribbon_outside_brain", "pial_out", (1, 2, 3), 79.0, 79, region="sinus")
    relabel_by_region([f])
    assert f.kind == "pial_out"


def test_cohort_indicator_is_listed_as_off_without_a_cohort(tmp_path):
    subj = write_subject(tmp_path / "fastsurfer", shape=(64, 64, 64))
    write_qa_files(subj)
    data = load_subject_data(subj, detect_pipeline(subj))
    found = write_findings(data, tmp_path)
    (listed,) = [i for i in found["indicators"] if i["name"] == "cohort_thickness"]
    assert listed["status"] == "not run" and "there are 0" in listed["reason"]


def test_cohort_finding_is_written_with_a_region(tmp_path, monkeypatch):
    import numpy as np
    from surfaceqa.cohort import Cohort

    monkeypatch.setattr("surfaceqa.thresholds.MIN_COHORT_VERTICES", 20)
    subj = write_subject(tmp_path / "fastsurfer", shape=(64, 64, 64))
    write_qa_files(subj, plant={"thick_patch": ("lh", (0.0, 0.0, 10.0), 6.0, 4.0)})
    flat = {h: np.full(40962, 2.0, dtype=np.float32) for h in ("lh", "rh")}
    cohort = Cohort("fastsurfer", 30, "sig", flat, {h: v * 0.05 for h, v in flat.items()})
    data = load_subject_data(subj, detect_pipeline(subj), cohort=cohort)
    found = write_findings(data, tmp_path)
    (finding,) = [f for f in found["findings"] if f["indicator"] == "cohort_thickness"]
    assert finding["region"] and finding["hemi"] == "lh" and finding["kind"] == "thickness"
    assert found["qa_version"] == 11
    assert found["thresholds"]["MIN_COHORT"] == 30
