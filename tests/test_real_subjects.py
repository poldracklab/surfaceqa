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


@pytest.mark.parametrize("subject", [FASTSURFER, RECON_ALL_8, RECON_ALL_6])
def test_real_subjects_map_onto_the_common_sphere(subject, tmp_path):
    import numpy as np
    from surfaceqa.thickness_map import load_thickness_map, write_thickness_map

    assert write_thickness_map(subject, tmp_path) is True
    maps = load_thickness_map(tmp_path)
    assert set(maps) == {"lh", "rh"}
    for values in maps.values():
        cortex = values[np.isfinite(values)]
        assert 0.8 < len(cortex) / len(values) < 0.97  # the rest is the medial wall
        assert 2.0 < np.median(cortex) < 3.2  # a plausible cortical thickness in mm


def test_real_reconstructions_of_one_person_share_scanner_space():
    import numpy as np
    from surfaceqa.compare import subject_label
    from surfaceqa.geometry import load_display_volume

    assert {subject_label(p.name) for p in (FASTSURFER, RECON_ALL_8, RECON_ALL_6)} == {"7"}
    centres = []
    for subject in (FASTSURFER, RECON_ALL_8):
        volume = load_display_volume(subject / "mri" / "orig.mgz")
        middle = np.append((np.array(volume.data.shape) - 1) / 2, 1.0)
        centres.append((volume.grid_to_scanner @ middle)[:3])
    # the same T1, conformed to 0.8 mm by one pipeline and 1 mm by the other
    assert np.linalg.norm(centres[0] - centres[1]) < 1.0
