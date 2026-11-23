import json

import numpy as np
import pytest

from surfaceqa import thresholds
from surfaceqa.pipelines import detect_pipeline
from surfaceqa.qa import write_findings
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
    assert "missed_gray" not in skipped  # one cortex class per hemisphere is enough to compare


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
