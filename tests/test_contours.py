import numpy as np
import pytest

from surfaceqa.contours import pack_plane, plane_segments, slice_segments, unpack_slice
from surfaceqa.planes import PLANES
from tests.synth import icosphere


def test_sphere_cut_through_centre_is_a_circle():
    verts, faces = icosphere(10.0, subdivisions=4)
    segs = slice_segments(verts, faces, axis=2, index=0.0)
    pts = segs.reshape(-1, 3)
    assert np.allclose(pts[:, 2], 0.0)
    assert np.allclose(np.linalg.norm(pts[:, :2], axis=1), 10.0, atol=0.05)
    length = np.linalg.norm(segs[:, 0] - segs[:, 1], axis=1).sum()
    assert length == pytest.approx(2 * np.pi * 10.0, rel=0.01)


def test_sphere_cut_off_centre_has_smaller_radius():
    verts, faces = icosphere(10.0, subdivisions=4)
    pts = slice_segments(verts, faces, axis=0, index=6.0).reshape(-1, 3)
    assert np.allclose(np.linalg.norm(pts[:, 1:], axis=1), 8.0, atol=0.05)


def test_plane_missing_the_mesh_gives_no_segments():
    verts, faces = icosphere(10.0)
    assert slice_segments(verts, faces, axis=1, index=11.0).shape == (0, 2, 3)


def test_contour_is_closed():
    # every endpoint is shared by exactly two segments
    verts, faces = icosphere(10.0, subdivisions=3)
    pts = np.round(slice_segments(verts, faces, 2, 0.3).reshape(-1, 3), 6)
    _, counts = np.unique(pts, axis=0, return_counts=True)
    assert (counts == 2).all()


def test_vertex_exactly_on_plane_does_not_break_closure():
    verts, faces = icosphere(10.0, subdivisions=2)  # has vertices at z == 0
    pts = np.round(slice_segments(verts, faces, 2, 0.0).reshape(-1, 3), 6)
    _, counts = np.unique(pts, axis=0, return_counts=True)
    assert (counts % 2 == 0).all() and len(pts) > 0


def test_plane_segments_are_in_screen_coordinates():
    verts, faces = icosphere(10.0, subdivisions=4)
    grid = verts + np.array([16, 24, 20])
    per_slice = plane_segments(grid, faces, PLANES["coronal"], (32, 48, 40))
    assert len(per_slice) == 48
    mid = per_slice[24]
    # coronal: x = 31 - R index, y = 39 - S index; circle centred at (15, 19)
    r = np.hypot(mid[:, 0] - 15.0, mid[:, 1] - 19.0)
    assert np.allclose(r, 10.0, atol=0.05)
    assert per_slice[0].shape == (0, 4)


def test_pack_round_trip():
    verts, faces = icosphere(10.0, subdivisions=3)
    grid = verts + np.array([16, 24, 20])
    per = {name: plane_segments(grid, faces, PLANES["axial"], (32, 48, 40))
           for name in ("lh.pial", "rh.pial", "lh.white", "rh.white")}
    blob, index = pack_plane(per)
    assert index["quant"] == 64
    assert len(index["surfaces"]["rh.white"]) == 41
    assert len(blob) == index["surfaces"]["rh.white"][-1] * 4 * 2
    back = unpack_slice(blob, index, "rh.pial", 20)
    assert np.allclose(back, per["rh.pial"][20], atol=1 / 64)
