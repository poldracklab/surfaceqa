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
    assert thresholds.as_dict()["MARGIN_MM"] == 1.0 and len(thresholds.as_dict()) == 13


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


def test_registration_sphere_is_loaded_and_tracked(tmp_path):
    from surfaceqa.pipelines import detect_pipeline
    from surfaceqa.subjectdata import input_signature, load_subject_data
    from tests.synth import write_qa_files, write_subject

    subj = write_subject(tmp_path / "fastsurfer")
    write_qa_files(subj)
    pipeline = detect_pipeline(subj)
    data = load_subject_data(subj, pipeline)
    assert data.hemis["lh"].sphere.shape == data.hemis["lh"].pial_grid.shape
    assert data.cohort is None
    assert "surf/lh.sphere.reg" in input_signature(subj, pipeline)
    (subj / "surf" / "lh.sphere.reg").unlink()
    assert load_subject_data(subj, pipeline).hemis["lh"].sphere is None


# ---- alignment with the T1 ----------------------------------------------------------------------

AUXILIARY = {"aparc.DKTatlas+aseg.deep.mgz": "seg", "ribbon.mgz": "ribbon", "norm.mgz": "norm",
             "aparc.DKTatlas+aseg.mgz": "parc", "lh.ribbon.mgz": "hemi_ribbon"}


def _resave(path, change):
    """Save the volume again with its affine changed by `change(affine)`; the voxels stay."""
    img = nib.load(path)
    nib.save(nib.MGHImage(np.asarray(img.dataobj), change(img.affine.copy())), path)


def _shifted(mm: float):
    def change(affine):
        affine[0, 3] += mm
        return affine
    return change


def _stretched(affine):
    affine[:3, :3] *= 1.2  # the same array, larger voxels
    return affine


def _load(subject):
    return load_subject_data(subject, detect_pipeline(subject))


@pytest.mark.parametrize("name, field", AUXILIARY.items())
def test_a_volume_shifted_against_the_t1_is_not_used_and_is_named(synth_subject, name, field):
    write_qa_files(synth_subject)
    assert getattr(_load(synth_subject), field) is not None and _load(synth_subject).misaligned == []
    _resave(synth_subject / "mri" / name, _shifted(40.0))
    data = _load(synth_subject)
    assert getattr(data, field) is None and data.misaligned == [name]


def test_a_volume_with_other_voxel_sizes_is_not_used(synth_subject):
    write_qa_files(synth_subject)
    _resave(synth_subject / "mri" / "ribbon.mgz", _stretched)
    data = _load(synth_subject)
    assert data.ribbon is None and data.misaligned == ["ribbon.mgz"]


def test_a_volume_stored_in_another_orientation_of_the_same_space_is_used(synth_subject):
    write_qa_files(synth_subject)
    before = _load(synth_subject).ribbon
    path = synth_subject / "mri" / "ribbon.mgz"
    turned = nib.as_closest_canonical(nib.load(path))  # other axis order, same place in the scanner
    assert not np.allclose(turned.affine, nib.load(path).affine)
    nib.save(nib.MGHImage(np.asarray(turned.dataobj), turned.affine), path)
    data = _load(synth_subject)
    assert np.array_equal(data.ribbon, before) and data.misaligned == []


def test_a_difference_far_below_a_voxel_is_not_a_misalignment(synth_subject):
    write_qa_files(synth_subject)
    _resave(synth_subject / "mri" / "norm.mgz", _shifted(0.001))
    data = _load(synth_subject)
    assert data.norm is not None and data.misaligned == []


def test_a_misaligned_nonbrain_mask_is_named(tmp_path):
    subj = write_subject(tmp_path / "fs", pipeline="freesurfer")
    write_qa_files(subj, pipeline="freesurfer")
    ref = nib.load(subj / "mri" / "orig.mgz")
    nib.save(nib.MGHImage(np.ones((32, 40, 48), dtype=np.float32), ref.affine), subj / "mri" / "vsinus.mgz")
    _resave(subj / "mri" / "vsinus.mgz", _shifted(40.0))
    data = _load(subj)
    assert data.nonbrain is None and data.misaligned == ["vsinus.mgz"]


def test_the_subject_page_says_which_files_were_left_out_as_misaligned(synth_subject, tmp_path):
    from surfaceqa.build import build_all
    from surfaceqa.discover import find_subjects
    from surfaceqa.qa import load_findings
    from surfaceqa.site import write_site
    write_qa_files(synth_subject)
    _resave(synth_subject / "mri" / "norm.mgz", _shifted(40.0))
    qa = tmp_path / "qa"
    build_all(find_subjects([synth_subject]), qa)
    write_site(qa)
    note = load_findings(qa, "fastsurfer__sub-01")["input_note"]
    assert "norm.mgz" in note and "not aligned with the T1" in note
    assert "not aligned with the T1" in (qa / "subjects" / "fastsurfer__sub-01" / "index.html").read_text()
