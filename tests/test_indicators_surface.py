import numpy as np

from surfaceqa.indicators_surface import thick_patches, topology_defects
from surfaceqa.subjectdata import HemiSurface, SubjectData
from tests.synth import icosphere


def hemi(radius=10.0, sub=4):
    verts, faces = icosphere(radius, sub)
    return HemiSurface(pial_grid=verts + 20.0, faces=faces, thickness=np.full(len(verts), 2.0),
                       cortex=np.arange(len(verts)), defect_labels=None, nofix_grid=None)


def data_with(lh):
    return SubjectData(voxel_sizes=(1.0, 1.0, 1.0), ribbon=None, hemi_ribbon=None, seg=None,
                       seg_name=None, nonbrain=None, nonbrain_names=[], parc=None, norm=None,
                       hemis={"lh": lh})


def test_uniform_thickness_has_no_patches():
    assert thick_patches(data_with(hemi())).findings == []


def test_thick_patch_is_found_at_its_place():
    h = hemi()
    top = h.pial_grid[:, 2] > 20 + 8.0  # a cap at the top of the sphere
    h.thickness[top] = 5.0
    (f,) = thick_patches(data_with(h)).findings
    assert f.kind == "thickness" and f.hemi == "lh" and f.n == int(top.sum()) and f.size_mm3 is None
    assert f.grid[2] >= 28 and abs(f.grid[0] - 20) <= 2 and abs(f.grid[1] - 20) <= 2


def test_two_separate_patches_are_two_findings():
    h = hemi()
    h.thickness[h.pial_grid[:, 2] > 28.0] = 5.0
    h.thickness[h.pial_grid[:, 2] < 12.0] = 5.0
    assert len(thick_patches(data_with(h)).findings) == 2


def test_scattered_thick_vertices_are_not_a_patch():
    h = hemi()
    h.thickness[::40] = 5.0
    assert thick_patches(data_with(h)).findings == []


def test_thick_vertices_outside_the_cortex_label_are_ignored():
    h = hemi()
    top = h.pial_grid[:, 2] > 28.0
    h.thickness[top] = 5.0
    h.cortex = np.flatnonzero(~top)
    assert thick_patches(data_with(h)).findings == []


def test_thickness_not_run_without_thickness():
    h = hemi()
    h.thickness = None
    r = thick_patches(data_with(h))
    assert r.status == "not run" and r.reason


def test_large_topology_defect_is_found_small_one_is_not():
    h = hemi()
    h.nofix_grid = h.pial_grid.copy()
    labels = np.zeros(len(h.pial_grid), int)
    labels[:10] = 2
    big = np.flatnonzero(h.pial_grid[:, 2] > 28.0)
    labels[big] = 1
    h.defect_labels = labels
    (f,) = topology_defects(data_with(h)).findings
    assert f.kind == "topology" and f.n == len(big) and f.grid[2] >= 28


def test_topology_not_run_without_prefix_surface():
    h = hemi()
    h.defect_labels = np.zeros(len(h.pial_grid), int)
    assert topology_defects(data_with(h)).status == "not run"


def test_a_hemisphere_without_thickness_is_named():
    lh, rh = hemi(), hemi()
    rh.thickness = None
    data = data_with(lh)
    data.hemis["rh"] = rh
    result = thick_patches(data)
    assert result.status == "ran" and "rh" in result.reason and "not checked" in result.reason


def test_a_cortex_label_that_does_not_fit_the_surface_does_not_crash():
    h = hemi()
    h.cortex = np.array([0, 1, 10 ** 7])
    assert thick_patches(data_with(h)).status == "ran"
