import nibabel as nib
import numpy as np
import pytest

from surfaceqa.edits import detect_edits
from surfaceqa.invocation import original_command
from tests.synth import (FASTSURFER_COMMAND, FREESURFER_COMMAND, fastsurfer_log, recon_all_log,
                         write_subject)


def write_volume(subj, rel, values=None, fill=110):
    """A small volume on the subject's grid; `values` maps a voxel index to a value."""
    orig = nib.load(subj / "mri" / "orig.mgz")
    data = np.full(orig.shape, fill, dtype=np.uint8)
    for index, value in (values or {}).items():
        data[index] = value
    nib.save(nib.MGHImage(data, orig.affine), subj / rel)


@pytest.fixture
def fast(tmp_path):
    subj = write_subject(tmp_path / "fastsurfer")
    write_volume(subj, "mri/brain.finalsurfs.mgz")
    write_volume(subj, "mri/brain.finalsurfs.manedit.mgz")  # FastSurfer writes an identical copy
    write_volume(subj, "mri/wm.mgz", {(1, 1, 1): 250})
    return subj


@pytest.fixture
def free(tmp_path):
    subj = write_subject(tmp_path / "freesurfer", pipeline="freesurfer")
    # recon-all 8 itself puts 1 (sinus) in brain.finalsurfs and 255 (entorhinal fix) in wm
    write_volume(subj, "mri/brain.finalsurfs.mgz", {(2, 2, 2): 1})
    write_volume(subj, "mri/brain.finalsurfs.manedit.mgz", {(2, 2, 2): 1})
    write_volume(subj, "mri/wm.mgz", {(1, 1, 1): 255, (3, 3, 3): 250})
    return subj


def test_unedited_subjects_have_no_evidence(fast, free):
    assert detect_edits(fast, "fastsurfer") == []
    assert detect_edits(free, "freesurfer") == []


def test_subject_without_the_optional_files_is_unedited(tmp_path):
    assert detect_edits(write_subject(tmp_path / "a"), "fastsurfer") == []
    assert detect_edits(write_subject(tmp_path / "b", pipeline="freesurfer"), "freesurfer") == []
    assert detect_edits(write_subject(tmp_path / "c"), "unknown") == []


def test_fastsurfer_edits_flag_in_the_segmentation_log(fast):
    log = fast / "scripts" / "deep-seg.log"
    log.write_text(log.read_text() + fastsurfer_log(FASTSURFER_COMMAND + " --edits"))
    (evidence,) = detect_edits(fast, "fastsurfer")
    assert "--edits" in evidence and "deep-seg.log" in evidence


def test_fastsurfer_edits_flag_in_the_surface_log(fast):
    (fast / "scripts" / "recon-surf.log").write_text(
        "Log file for recon-surf.sh\n./recon-surf.sh --sid sub-01 --sd /outputs --edits --3T\n")
    (evidence,) = detect_edits(fast, "fastsurfer")
    assert "--edits" in evidence and "recon-surf.log" in evidence


def test_fastsurfer_segmentation_edit_file(fast):
    write_volume(fast, "mri/aparc.DKTatlas+aseg.deep.manedit.mgz")
    (evidence,) = detect_edits(fast, "fastsurfer")
    assert "aparc.DKTatlas+aseg.deep.manedit.mgz" in evidence


def test_fastsurfer_changed_finalsurfs_edit_file(fast):
    write_volume(fast, "mri/brain.finalsurfs.manedit.mgz", {(4, 4, 4): 1, (5, 5, 5): 255})
    (evidence,) = detect_edits(fast, "fastsurfer")
    assert "brain.finalsurfs.manedit.mgz" in evidence and "2 voxels" in evidence


def test_recon_all_control_points(free):
    (free / "tmp").mkdir()
    (free / "tmp" / "control.dat").write_text("0 0 0\ninfo\nnumpoints 1\n")
    (evidence,) = detect_edits(free, "freesurfer")
    assert "tmp/control.dat" in evidence


def test_recon_all_segmentation_edit_file(free):
    write_volume(free, "mri/aseg.manedit.mgz")
    (evidence,) = detect_edits(free, "freesurfer")
    assert "aseg.manedit.mgz" in evidence


def test_recon_all_erased_white_matter(free):
    write_volume(free, "mri/wm.mgz", {(1, 1, 1): 255, (6, 6, 6): 1, (6, 6, 7): 1})
    (evidence,) = detect_edits(free, "freesurfer")
    assert "wm.mgz" in evidence and "2 voxels" in evidence


def test_recon_all_later_partial_rerun(free):
    log = free / "scripts" / "recon-all.log"
    log.write_text(log.read_text() + recon_all_log("/fs/bin/recon-all -s sub-01 -autorecon-pial -T2pial"))
    (evidence,) = detect_edits(free, "freesurfer")
    assert "-autorecon-pial" in evidence and "recon-all.log" in evidence


def test_recon_all_first_run_in_stages_is_not_an_edit(tmp_path):
    subj = write_subject(tmp_path / "freesurfer", pipeline="freesurfer",
                         command="/fs/bin/recon-all -s sub-01 -i a.nii -autorecon1 -autorecon2")
    assert detect_edits(subj, "freesurfer") == []


def test_a_first_run_done_in_stages_is_not_an_edit(free):
    log = free / "scripts" / "recon-all.log"
    stages = ["-autorecon1", "-autorecon2-volonly", "-autorecon-hemi lh", "-autorecon3"]
    log.write_text("".join(recon_all_log(f"/fs/bin/recon-all -s sub-01 {stage}") for stage in stages))
    assert detect_edits(free, "freesurfer") == []


def test_an_unreadable_volume_is_reported_not_raised(free):
    (free / "mri" / "wm.mgz").write_bytes(b"junk")
    (evidence,) = detect_edits(free, "freesurfer")
    assert "wm.mgz" in evidence and "could not be read" in evidence


def test_recon_all_6_writes_the_command_on_two_lines(tmp_path):
    subj = write_subject(tmp_path / "freesurfer", pipeline="freesurfer", command=None)
    (subj / "scripts" / "recon-all.log").write_text(
        "Thu May  9 08:01:50 CDT 2019\n/home/subjects/x\n/opt/fs600/bin/recon-all\n"
        "-s x -i t1.nii.gz -all -hires\nsubjid x\nrecon-all -s x finished without error at Fri\n")
    assert original_command(subj, "freesurfer") == "/opt/fs600/bin/recon-all -s x -i t1.nii.gz -all -hires"
    assert detect_edits(subj, "freesurfer") == []
