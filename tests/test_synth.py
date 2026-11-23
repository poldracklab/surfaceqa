import nibabel as nib
import numpy as np

from tests.synth import write_subject


def test_synth_subject_has_readable_volume_and_surfaces(synth_subject):
    img = nib.load(synth_subject / "mri" / "orig.mgz")
    assert img.shape == (32, 40, 48)
    assert nib.aff2axcodes(img.affine) == ("L", "I", "A")
    verts, faces = nib.freesurfer.read_geometry(synth_subject / "surf" / "lh.pial")
    assert np.allclose(np.linalg.norm(verts, axis=1), 10.0, atol=1e-4)
    assert faces.shape[1] == 3


def test_synth_subject_can_omit_files(tmp_path):
    subj = write_subject(tmp_path / "src", omit=("surf/rh.pial",))
    assert not (subj / "surf" / "rh.pial").exists()
