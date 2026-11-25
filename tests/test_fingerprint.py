import re

import nibabel as nib
import numpy as np

from surfaceqa.fingerprint import run_fingerprint
from surfaceqa.pipelines import subject_files
from tests.synth import icosphere


def test_fingerprint_is_stable_and_12_hex(synth_subject):
    files = subject_files(synth_subject)
    fp = run_fingerprint(files)
    assert fp == run_fingerprint(files) and re.fullmatch(r"[0-9a-f]{12}", fp)


def test_fingerprint_changes_when_a_surface_changes(synth_subject):
    files = subject_files(synth_subject)
    before = run_fingerprint(files)
    v, f = icosphere(9.0)
    nib.freesurfer.write_geometry(files.surfaces["rh.white"], v, f)
    assert run_fingerprint(files) != before


def test_fingerprint_changes_when_the_t1_changes(synth_subject):
    files = subject_files(synth_subject)
    before = run_fingerprint(files)
    img = nib.load(files.t1)
    nib.save(nib.MGHImage(np.zeros(img.shape, np.uint8), img.affine, img.header), files.t1)
    assert run_fingerprint(files) != before
