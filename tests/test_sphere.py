import numpy as np

from surfaceqa.sphere import icosphere, nearest, target_points


def test_target_points_are_40962_unit_vectors():
    points = target_points()
    assert points.shape == (40962, 3)
    assert np.allclose(np.linalg.norm(points, axis=1), 1.0)
    assert target_points() is points  # computed once


def test_icosphere_vertex_and_face_counts():
    for order, n in [(0, 12), (1, 42), (3, 642)]:
        vertices, faces = icosphere(order)
        assert len(vertices) == n and len(faces) == 20 * 4**order
        assert np.allclose(np.linalg.norm(vertices, axis=1), 1.0)
        assert len(np.unique(vertices.round(6), axis=0)) == n


def test_nearest_ignores_the_radius_of_either_set():
    points, _ = icosphere(2)
    order = np.random.default_rng(0).permutation(len(points))
    found = nearest(points * 100.0, points[order] * 3.0 + 1e-4)
    assert (found == order).all()
