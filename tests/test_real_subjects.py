"""The three real reconstructions of subject 07; skipped when their volume is not mounted."""

from pathlib import Path

import pytest

from surfaceqa.edits import detect_edits
from surfaceqa.invocation import original_command, rerun_commands
from surfaceqa.pipelines import detect_pipeline

DERIVATIVES = Path("/Volumes/extdata1/NSD/BIDS/derivatives")
FASTSURFER = DERIVATIVES / "fastsurfer" / "sub-07"
RECON_ALL_8 = DERIVATIVES / "freesurfer-8.2.0" / "sub-07"
RECON_ALL_6 = DERIVATIVES / "freesurfer-NSD" / "subj07"

pytestmark = pytest.mark.skipif(not FASTSURFER.is_dir(), reason="the example data is not mounted")


def test_fastsurfer_subject_command_and_edit_state():
    command = original_command(FASTSURFER, "fastsurfer")
    assert command.startswith("/fastsurfer/run_fastsurfer.sh ") and command.endswith("--3T --threads 8")
    assert rerun_commands("fastsurfer", command, "sub-07")["surf"] == command + " --edits --surf_only"
    assert detect_edits(FASTSURFER, "fastsurfer") == []


def test_recon_all_8_subject_command_and_edit_state():
    assert detect_pipeline(RECON_ALL_8).version == "8.2.0"
    command = original_command(RECON_ALL_8, "freesurfer")
    assert command.endswith("-T2pial -3T -all -parallel -openmp 8")
    assert rerun_commands("freesurfer", command, "sub-07")["pial"] == (
        "recon-all -s sub-07 -autorecon-pial -T2pial -3T -parallel -openmp 8")
    # its wm.mgz holds 255 written by recon-all itself, which is not an edit
    assert detect_edits(RECON_ALL_8, "freesurfer") == []


def test_recon_all_6_subject_was_edited_by_hand():
    command = original_command(RECON_ALL_6, "freesurfer")
    assert command.split()[0].endswith("/recon-all") and " -all " in command
    evidence = " | ".join(detect_edits(RECON_ALL_6, "freesurfer"))
    assert "tmp/control.dat" in evidence and "wm.mgz" in evidence and "-autorecon2-cp" in evidence
