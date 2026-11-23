"""A located indicator result, and the helpers that turn voxel masks into findings."""

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

KINDS = ("pial_out", "gray_missed", "white_short", "crossing", "thickness", "topology")
FULL_CONNECTIVITY = np.ones((3, 3, 3), dtype=bool)
EPS = 1e-6  # distances are sums of voxel sizes; compare them with a little slack


@dataclass
class Finding:
    indicator: str
    kind: str
    grid: tuple[int, int, int]
    size_mm3: float | None
    n: int
    hemi: str | None = None
    region: str = ""
    voxels: np.ndarray | None = None


def deeper_than(mask: np.ndarray, margin_mm: float, voxel_sizes) -> np.ndarray:
    """Voxels of mask farther than margin_mm from the nearest voxel outside it."""
    return ndimage.distance_transform_edt(mask, sampling=voxel_sizes) > margin_mm + EPS


def farther_than(mask: np.ndarray, from_mask: np.ndarray, margin_mm: float, voxel_sizes) -> np.ndarray:
    """Voxels of mask farther than margin_mm from the nearest voxel of from_mask."""
    if not from_mask.any():
        return mask.copy()
    distance = ndimage.distance_transform_edt(~from_mask, sampling=voxel_sizes)
    return mask & (distance > margin_mm + EPS)


def _deepest_voxel(cluster: np.ndarray, voxel_sizes) -> tuple[int, int, int]:
    """The voxel of the cluster farthest from its outside, so it is always inside."""
    padded = np.pad(cluster, 1)
    depth = ndimage.distance_transform_edt(padded, sampling=voxel_sizes)
    return tuple(int(i) - 1 for i in np.unravel_index(np.argmax(depth), depth.shape))


def _finding(labels, label: int, box, indicator: str, kind: str, voxel_sizes) -> Finding:
    cluster = labels[box] == label
    start = np.array([s.start for s in box])
    voxels = (np.argwhere(cluster) + start).astype(np.uint16)
    grid = tuple(int(v) for v in start + _deepest_voxel(cluster, voxel_sizes))
    volume = float(len(voxels) * np.prod(voxel_sizes))
    return Finding(indicator, kind, grid, volume, len(voxels), voxels=voxels)


def cluster_findings(mask: np.ndarray, indicator: str, kind: str, voxel_sizes,
                     min_mm3: float, limit: int) -> tuple[list[Finding], int]:
    """26-connected clusters of at least min_mm3, largest first, at most `limit` of them."""
    labels, count = ndimage.label(mask, structure=FULL_CONNECTIVITY)
    if count == 0:
        return [], 0
    sizes = np.bincount(labels.ravel())[1:]
    big = np.flatnonzero(sizes * np.prod(voxel_sizes) >= min_mm3 - EPS)
    order = big[np.argsort(-sizes[big], kind="stable")]
    boxes = ndimage.find_objects(labels)
    found = [_finding(labels, int(i) + 1, boxes[i], indicator, kind, voxel_sizes) for i in order[:limit]]
    return found, max(len(order) - limit, 0)
