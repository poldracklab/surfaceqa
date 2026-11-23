"""Cut surface meshes with slice planes and pack the resulting line segments."""

import numpy as np

from surfaceqa.planes import Plane, to_screen

QUANT = 64
SURFACE_ORDER = ("lh.pial", "rh.pial", "lh.white", "rh.white")


def _lone_corner(side: np.ndarray) -> np.ndarray:
    """Index (0-2) of the corner that is alone on its side of the plane."""
    lone_is_positive = side.sum(axis=1) == 1
    return np.argmax(side == lone_is_positive[:, None], axis=1)


def _edge_crossing(vertices, dist, a, b):
    """Where edge a-b crosses the plane; a and b are ordered so shared edges agree exactly."""
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    rows = np.arange(len(a))
    d_lo = np.where(a < b, dist[rows, 0], dist[rows, 1])
    d_hi = np.where(a < b, dist[rows, 1], dist[rows, 0])
    t = d_lo / (d_lo - d_hi)
    return vertices[lo] + t[:, None] * (vertices[hi] - vertices[lo])


def _cut_faces(vertices: np.ndarray, faces: np.ndarray, axis: int, index: np.ndarray):
    """Segments where each face crosses its own plane; returns (segments, kept mask)."""
    dist = vertices[faces][:, :, axis] - index[:, None]
    side = dist >= 0
    cut = side.any(axis=1) & ~side.all(axis=1)
    faces, dist, side = faces[cut], dist[cut], side[cut]
    rows = np.arange(len(faces))
    lone = _lone_corner(side)
    ends = []
    for step in (1, 2):
        other = (lone + step) % 3
        pair_dist = np.stack([dist[rows, lone], dist[rows, other]], axis=1)
        ends.append(_edge_crossing(vertices, pair_dist, faces[rows, lone], faces[rows, other]))
    segments = np.stack(ends, axis=1)
    real = np.any(segments[:, 0] != segments[:, 1], axis=1)
    kept = np.flatnonzero(cut)[real]
    return segments[real], kept


def slice_segments(vertices: np.ndarray, faces: np.ndarray, axis: int, index: float) -> np.ndarray:
    """Intersection of the mesh with the plane coordinate[axis] == index, as (n, 2, 3)."""
    segments, _ = _cut_faces(vertices, faces, axis, np.full(len(faces), float(index)))
    return segments


def _face_slice_pairs(vertices, faces, axis: int, n_slices: int):
    """Every (face, integer slice) pair where the slice plane can cut the face."""
    coord = vertices[faces][:, :, axis]
    first = np.maximum(np.floor(coord.min(axis=1)).astype(int) + 1, 0)
    last = np.minimum(np.floor(coord.max(axis=1)).astype(int), n_slices - 1)
    count = np.maximum(last - first + 1, 0)
    face_idx = np.repeat(np.arange(len(faces)), count)
    starts = np.cumsum(count) - count
    offset = np.arange(count.sum()) - np.repeat(starts, count)
    return face_idx, first[face_idx] + offset


def _screen_rows(segments: np.ndarray, plane: Plane, shape) -> np.ndarray:
    x, y = to_screen(segments[:, :, plane.h_axis], segments[:, :, plane.v_axis], plane, shape)
    return np.stack([x[:, 0], y[:, 0], x[:, 1], y[:, 1]], axis=1)


def plane_segments(vertices_grid: np.ndarray, faces: np.ndarray, plane: Plane,
                   shape: tuple[int, int, int]) -> list[np.ndarray]:
    """One (n, 4) array of x1, y1, x2, y2 screen coordinates per slice of the plane."""
    n_slices = shape[plane.axis]
    face_idx, slice_idx = _face_slice_pairs(vertices_grid, faces, plane.axis, n_slices)
    segments, kept = _cut_faces(vertices_grid, faces[face_idx], plane.axis, slice_idx.astype(float))
    rows = _screen_rows(segments, plane, shape)
    slice_idx = slice_idx[kept]
    order = np.argsort(slice_idx, kind="stable")
    bounds = np.searchsorted(slice_idx[order], np.arange(n_slices + 1))
    return [rows[order[bounds[i]:bounds[i + 1]]] for i in range(n_slices)]


def _quantize(rows: np.ndarray) -> np.ndarray:
    return np.clip(np.round((rows + 0.5) * QUANT), 0, 65535).astype("<u2")


def pack_plane(per_surface: dict[str, list[np.ndarray]]) -> tuple[bytes, dict]:
    """Concatenate quantized segments, surface by surface and slice by slice."""
    chunks, offsets, total = [], {}, 0
    for name in (s for s in SURFACE_ORDER if s in per_surface):
        counts = [len(rows) for rows in per_surface[name]]
        offsets[name] = [total + int(c) for c in np.concatenate([[0], np.cumsum(counts)])]
        total = offsets[name][-1]
        chunks += [_quantize(rows) for rows in per_surface[name]]
    blob = np.concatenate(chunks).tobytes() if chunks else b""
    return blob, {"quant": QUANT, "surfaces": offsets}


def unpack_slice(blob: bytes, index: dict, surface: str, i: int) -> np.ndarray:
    start, stop = index["surfaces"][surface][i:i + 2]
    raw = np.frombuffer(blob, dtype="<u2", count=(stop - start) * 4, offset=start * 8)
    return raw.reshape(-1, 4) / index["quant"] - 0.5
