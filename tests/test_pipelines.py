from surfaceqa.pipelines import PipelineInfo, detect_pipeline, subject_files
from tests.synth import write_subject


def test_detects_fastsurfer_with_version(synth_subject):
    assert detect_pipeline(synth_subject) == PipelineInfo("fastsurfer", "2.6.1")


def test_detects_freesurfer_with_version(tmp_path):
    subj = write_subject(tmp_path / "fs", pipeline="freesurfer")
    assert detect_pipeline(subj) == PipelineInfo("freesurfer", "8.2.0")


def test_freesurfer_6_build_stamp(tmp_path):
    subj = write_subject(tmp_path / "fs", pipeline="freesurfer")
    (subj / "scripts" / "build-stamp.txt").write_text(
        "freesurfer-Linux-centos6_x86_64-stable-pub-v6.0.0-2beb96c\n")
    assert detect_pipeline(subj).version == "6.0.0"


def test_no_logs_is_unknown(tmp_path):
    subj = write_subject(tmp_path / "x", omit=("scripts/deep-seg.log", "scripts/build-stamp.txt"))
    assert detect_pipeline(subj) == PipelineInfo("unknown", None)


def test_subject_files_complete(synth_subject):
    files = subject_files(synth_subject)
    assert files.missing == []
    assert files.t1 == synth_subject / "mri" / "orig.mgz"
    assert set(files.surfaces) == {"lh.pial", "rh.pial", "lh.white", "rh.white"}


def test_subject_files_reports_missing(tmp_path):
    subj = write_subject(tmp_path / "s", omit=("surf/rh.white", "mri/orig.mgz"))
    assert subject_files(subj).missing == ["mri/orig.mgz", "surf/rh.white"]


def test_pial_falls_back_to_pial_t1(tmp_path):
    subj = write_subject(tmp_path / "s")
    (subj / "surf" / "lh.pial").rename(subj / "surf" / "lh.pial.T1")
    files = subject_files(subj)
    assert files.missing == []
    assert files.surfaces["lh.pial"].name == "lh.pial.T1"
