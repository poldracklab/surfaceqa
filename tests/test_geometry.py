import nibabel as nib
import numpy as np
import pytest

from surfaceqa.geometry import load_display_volume, to_grid
from tests.synth import write_subject

ORIGIN = [15, 24, 19]  # tkr origin of the (32, 40, 48) LIA synthetic volume, in R, A, S grid indices


def test_display_volume_is_ras(synth_subject):
    vol = load_display_volume(synth_subject / "mri" / "orig.mgz")
    assert vol.data.shape == (32, 48, 40)  # LIA (32, 40, 48) -> R, A, S


def test_tkr_origin_maps_to_volume_centre(synth_subject):
    vol = load_display_volume(synth_subject / "mri" / "orig.mgz")
    centre = to_grid(np.zeros((1, 3)), vol.tkr_to_grid)[0]
    assert np.allclose(centre, ORIGIN)


def test_grid_axes_point_right_anterior_superior(synth_subject):
    vol = load_display_volume(synth_subject / "mri" / "orig.mgz")
    pts = to_grid(np.array([[5.0, 0, 0], [0, 5.0, 0], [0, 0, 5.0]]), vol.tkr_to_grid)
    origin = to_grid(np.zeros((1, 3)), vol.tkr_to_grid)[0]
    assert np.allclose(pts - origin, np.eye(3) * 5.0)


def test_tkr_to_grid_ignores_cras(tmp_path):
    subj = write_subject(tmp_path / "s", cras=(12.0, -7.0, 3.0))
    vol = load_display_volume(subj / "mri" / "orig.mgz")
    assert np.allclose(to_grid(np.zeros((1, 3)), vol.tkr_to_grid)[0], ORIGIN)


@pytest.mark.parametrize("orientation", ["LIA", "RAS", "LPS", "PIR"])
def test_display_volume_reorients_any_orientation(tmp_path, orientation):
    subj = write_subject(tmp_path / orientation, orientation=orientation, voxel=0.8)
    vol = load_display_volume(subj / "mri" / "orig.mgz")
    # the bright sphere (radius 10 mm) is centred on the tkr origin in every orientation
    centre = to_grid(np.zeros((1, 3)), vol.tkr_to_grid)[0]
    bright = np.argwhere(vol.data > 0)
    assert np.allclose(bright.mean(axis=0), centre, atol=0.6)
    assert vol.voxel_sizes == pytest.approx((0.8, 0.8, 0.8))


def test_surface_sits_on_sphere_edge_in_grid(synth_subject):
    vol = load_display_volume(synth_subject / "mri" / "orig.mgz")
    verts, _ = nib.freesurfer.read_geometry(synth_subject / "surf" / "lh.pial")
    # rounding to a voxel centre moves a point by up to 0.87 mm, so stay 1 mm clear of the edge
    inside = vol.data[tuple(np.round(to_grid(verts * 0.9, vol.tkr_to_grid)).astype(int).T)]
    outside = vol.data[tuple(np.round(to_grid(verts * 1.1, vol.tkr_to_grid)).astype(int).T)]
    assert (inside > 0).all()
    assert (outside == 0).all()


def test_grid_to_scanner_agrees_with_the_image_affine(tmp_path):
    subj = write_subject(tmp_path / "s", orientation="PIR", voxel=(1.0, 0.7, 1.3),
                         cras=(3.0, -2.0, 5.0))
    path = subj / "mri" / "orig.mgz"
    img = nib.load(path)
    # every voxel gets its own value, so one can be found again in the reordered display data
    numbered = np.arange(np.prod(img.shape), dtype=np.float32).reshape(img.shape)
    nib.save(nib.MGHImage(numbered, img.affine), path)
    vol = load_display_volume(path)
    file_index = np.array([5, 9, 13])
    value = np.asarray(nib.load(path).dataobj)[tuple(file_index)]
    grid_index = np.argwhere(vol.data == value)[0]
    expected = img.affine @ np.append(file_index, 1.0)
    assert np.allclose(vol.grid_to_scanner @ np.append(grid_index, 1.0), expected, atol=1e-4)


def test_scanner_and_surface_coordinates_differ_by_cras(tmp_path):
    # true for the conformed (LIA) volumes FreeSurfer makes; tkr is defined from the grid alone
    subj = write_subject(tmp_path / "s", cras=(3.0, -2.0, 5.0))
    vol = load_display_volume(subj / "mri" / "orig.mgz")
    grid_to_tkr = np.linalg.inv(vol.tkr_to_grid)
    assert np.allclose(vol.grid_to_scanner[:3, :3], grid_to_tkr[:3, :3])
    assert np.allclose(vol.grid_to_scanner[:3, 3] - grid_to_tkr[:3, 3], [3.0, -2.0, 5.0], atol=1e-4)
