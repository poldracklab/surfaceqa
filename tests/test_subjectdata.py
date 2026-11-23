import nibabel as nib
import numpy as np
import pytest

from surfaceqa import thresholds
from surfaceqa.pipelines import detect_pipeline
from surfaceqa.subjectdata import load_subject_data
from tests.synth import write_qa_files, write_subject


def test_loads_fastsurfer_roles(synth_subject):
    write_qa_files(synth_subject)
    data = load_subject_data(synth_subject, detect_pipeline(synth_subject))
    assert data.seg_name == "aparc.DKTatlas+aseg.deep.mgz"
    assert data.ribbon.shape == (32, 48, 40) and set(np.unique(data.ribbon)) == {0, 2, 3, 41, 42}
    assert data.hemi_ribbon["lh"].dtype == bool and data.hemi_ribbon["lh"].any()
    assert data.nonbrain is None and data.nonbrain_names == []
    assert data.hemis["lh"].thickness.shape == (len(data.hemis["lh"].pial_grid),)
    assert data.voxel_sizes == pytest.approx((1.0, 1.0, 1.0))


def test_loads_recon_all_roles_and_nonbrain_masks(tmp_path):
    subj = write_subject(tmp_path / "fs", pipeline="freesurfer")
    write_qa_files(subj, pipeline="freesurfer")
    mask = np.zeros((32, 40, 48), dtype=np.float32)
    mask[2, 3, 4] = 6111
    ref = nib.load(subj / "mri" / "orig.mgz")
    nib.save(nib.MGHImage(mask, ref.affine), subj / "mri" / "vsinus.mgz")
    data = load_subject_data(subj, detect_pipeline(subj))
    assert data.seg_name == "aseg.presurf.mgz"
    assert data.nonbrain_names == ["vsinus.mgz"] and data.nonbrain.sum() == 1


def test_missing_optional_files_become_none(synth_subject):
    data = load_subject_data(synth_subject, detect_pipeline(synth_subject))  # no QA files written
    assert data.ribbon is None and data.seg is None and data.parc is None and data.norm is None
    assert data.hemi_ribbon is None
    assert data.hemis["lh"].thickness is None and data.hemis["lh"].cortex is None
    assert len(data.hemis["lh"].pial_grid) > 0


def test_volume_with_another_shape_is_ignored(synth_subject):
    write_qa_files(synth_subject)
    nib.save(nib.MGHImage(np.zeros((8, 8, 8), dtype=np.uint8), np.eye(4)),
             synth_subject / "mri" / "norm.mgz")
    assert load_subject_data(synth_subject, detect_pipeline(synth_subject)).norm is None


def test_thresholds_as_dict_lists_every_constant():
    assert thresholds.as_dict()["MARGIN_MM"] == 1.0 and len(thresholds.as_dict()) == 9


@pytest.mark.parametrize("keep", [0, 0.5])
def test_truncated_optional_file_becomes_none(synth_subject, keep):
    write_qa_files(synth_subject)
    path = synth_subject / "mri" / "ribbon.mgz"
    raw = path.read_bytes()
    path.write_bytes(raw[:int(len(raw) * keep)])  # e.g. recon-all still writing
    data = load_subject_data(synth_subject, detect_pipeline(synth_subject))
    assert data.ribbon is None and data.norm is not None


def test_segmentation_method_is_recorded(synth_subject, tmp_path):
    write_qa_files(synth_subject)
    assert load_subject_data(synth_subject, detect_pipeline(synth_subject)).seg_method == "network"
    old = write_subject(tmp_path / "fs6", pipeline="freesurfer")
    write_qa_files(old, pipeline="freesurfer")
    assert load_subject_data(old, detect_pipeline(old)).seg_method == "atlas"
    # recon-all 8 keeps the SynthSeg output its segmentation was copied from
    (old / "mri" / "synthseg.rca.mgz").write_bytes((old / "mri" / "aseg.presurf.mgz").read_bytes())
    assert load_subject_data(old, detect_pipeline(old)).seg_method == "network"
