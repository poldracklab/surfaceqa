"""Fixed points on the unit sphere at which every subject's surface measures are sampled.

A subject's `sphere.reg` puts its vertices in spherical coordinates shared by all subjects
(those of FreeSurfer's average subject), so no average subject is needed to compare them.
"""

from functools import cache

import numpy as np
from scipy.spatial import cKDTree

TARGET_ORDER = 6  # 40962 points, about 1.7 degrees apart


def _icosahedron() -> tuple[np.ndarray, np.ndarray]:
    t = (1 + 5**0.5) / 2
    vertices = np.array([[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t],
                         [0, -1, -t], [0, 1, -t], [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]],
                        dtype=float)
    faces = np.array([[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9],
                      [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8], [3, 9, 4], [3, 4, 2],
                      [3, 2, 6], [3, 6, 8], [3, 8, 9], [4, 9, 5], [2, 4, 11], [6, 2, 10],
                      [8, 6, 7], [9, 8, 1]])
    return vertices, faces


def _subdivide(vertices: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split every triangle in four, adding one vertex at the middle of each edge."""
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    unique, inverse = np.unique(edges, axis=0, return_inverse=True)
    middles = vertices[unique].mean(axis=1)
    ab, bc, ca = (inverse.reshape(3, -1) + len(vertices))
    a, b, c = faces.T
    split = np.concatenate([np.stack(f, axis=1) for f in
                            ((a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca))])
    return np.concatenate([vertices, middles]), split


def unit(points: np.ndarray) -> np.ndarray:
    return points / np.linalg.norm(points, axis=1, keepdims=True)


def icosphere(order: int) -> tuple[np.ndarray, np.ndarray]:
    """A unit sphere of 10 * 4**order + 2 evenly spread vertices, and its triangles."""
    vertices, faces = _icosahedron()
    for _ in range(order):
        vertices, faces = _subdivide(unit(vertices), faces)
    return unit(vertices), faces


@cache
def target_points() -> np.ndarray:
    points = icosphere(TARGET_ORDER)[0]
    points.setflags(write=False)
    return points


def nearest(points: np.ndarray, queries: np.ndarray) -> np.ndarray:
    """For each query direction, the index of the point in the closest direction."""
    return cKDTree(unit(np.asarray(points, dtype=float))).query(unit(np.asarray(queries, dtype=float)))[1]
