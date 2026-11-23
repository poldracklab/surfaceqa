import re

import nibabel as nib

from surfaceqa.fingerprint import surface_fingerprint
from surfaceqa.pipelines import subject_files
from tests.synth import icosphere


def test_fingerprint_is_stable_and_12_hex(synth_subject):
    s = subject_files(synth_subject).surfaces
    fp = surface_fingerprint(s)
    assert fp == surface_fingerprint(s) and re.fullmatch(r"[0-9a-f]{12}", fp)


def test_fingerprint_changes_when_a_surface_changes(synth_subject):
    s = subject_files(synth_subject).surfaces
    before = surface_fingerprint(s)
    v, f = icosphere(9.0)
    nib.freesurfer.write_geometry(s["rh.white"], v, f)
    assert surface_fingerprint(s) != before
