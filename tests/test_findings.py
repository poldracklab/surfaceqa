import numpy as np
import pytest

from surfaceqa.findings import cluster_findings, deeper_than, farther_than

VOX = (1.0, 1.0, 1.0)


def test_clusters_are_sorted_largest_first_with_sizes_in_mm3():
    mask = np.zeros((20, 20, 20), bool)
    mask[2:5, 2:5, 2:5] = True
    mask[10:14, 10:14, 10:14] = True
    found, dropped = cluster_findings(mask, "x", "pial_out", (0.8, 0.8, 0.8), min_mm3=1.0, limit=10)
    assert [f.n for f in found] == [64, 27] and dropped == 0
    assert found[0].size_mm3 == pytest.approx(64 * 0.512)
    assert found[0].indicator == "x" and found[0].kind == "pial_out"


def test_small_clusters_are_dropped():
    mask = np.zeros((10, 10, 10), bool)
    mask[1, 1, 1] = True
    mask[5:8, 5:8, 5:8] = True
    found, _ = cluster_findings(mask, "x", "pial_out", VOX, min_mm3=20.0, limit=10)
    assert [f.n for f in found] == [27]


def test_location_is_inside_a_c_shaped_cluster():
    mask = np.zeros((12, 12, 3), bool)
    mask[2:10, 2:10, 1] = True
    mask[4:8, 4:10, 1] = False  # a C: the centroid is in the gap
    (f,), _ = cluster_findings(mask, "x", "pial_out", VOX, min_mm3=1.0, limit=10)
    assert mask[f.grid]


def test_voxels_are_kept_for_the_overlay():
    mask = np.zeros((6, 6, 6), bool)
    mask[1:3, 1:3, 1:3] = True
    (f,), _ = cluster_findings(mask, "x", "pial_out", VOX, min_mm3=1.0, limit=10)
    assert f.voxels.shape == (8, 3) and f.voxels.dtype == np.uint16
    assert mask[tuple(f.voxels.T)].all()


def test_limit_keeps_the_largest_and_counts_the_rest():
    mask = np.zeros((40, 5, 5), bool)
    for i, size in enumerate((1, 2, 3, 4)):
        mask[i * 8:i * 8 + size, 0, 0] = True
    found, dropped = cluster_findings(mask, "x", "pial_out", VOX, min_mm3=1.0, limit=2)
    assert [f.n for f in found] == [4, 3] and dropped == 2


def test_diagonal_voxels_are_one_cluster():
    mask = np.zeros((4, 4, 4), bool)
    mask[0, 0, 0] = mask[1, 1, 1] = True
    assert len(cluster_findings(mask, "x", "pial_out", VOX, 1.0, 10)[0]) == 1


def test_sizes_and_margins_are_in_mm():
    mask = np.zeros((30, 30, 30), bool)
    mask[5:25, 5:25, 5:25] = True
    assert deeper_than(mask, 1.0, (1.0, 1.0, 1.0)).sum() == 18 ** 3  # one voxel shell removed
    assert deeper_than(mask, 1.0, (0.5, 0.5, 0.5)).sum() == 16 ** 3  # two voxel shells removed
    assert deeper_than(mask, 1.0, (1.0, 1.0, 0.5)).sum() == 18 * 18 * 16


def test_farther_than():
    mask = np.ones((10, 1, 1), bool)
    src = np.zeros((10, 1, 1), bool)
    src[0] = True
    assert farther_than(mask, src, 2.0, VOX)[:, 0, 0].tolist() == [False] * 3 + [True] * 7


def test_empty_mask_gives_no_findings():
    assert cluster_findings(np.zeros((4, 4, 4), bool), "x", "pial_out", VOX, 1.0, 10) == ([], 0)
