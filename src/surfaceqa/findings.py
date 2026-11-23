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


def _margin_box(margin_mm: float, voxel_sizes) -> tuple[int, ...]:
    """Size of the box, in voxels per axis, that reaches margin_mm in every direction.

    The margin is counted in whole voxels along each axis (the nearest whole number, at
    least one) and applies to diagonal neighbours too, so a boundary that is off by one
    voxel in any direction is inside it. Rounding up instead would make the margin 1.6 mm
    at 0.8 mm voxels, wider than the thinnest errors worth finding.
    """
    steps = [max(1, int(np.floor(margin_mm / size + 0.5))) for size in voxel_sizes]
    return tuple(2 * s + 1 for s in steps)


def deeper_than(mask: np.ndarray, margin_mm: float, voxel_sizes) -> np.ndarray:
    """Voxels of mask with no voxel outside the mask within the margin.

    The edge of the volume does not count as outside.
    """
    box = _margin_box(margin_mm, voxel_sizes)
    return ndimage.minimum_filter(mask.astype(np.uint8), size=box, mode="nearest").astype(bool)


def farther_than(mask: np.ndarray, from_mask: np.ndarray, margin_mm: float, voxel_sizes) -> np.ndarray:
    """Voxels of mask with no voxel of from_mask within the margin."""
    box = _margin_box(margin_mm, voxel_sizes)
    near = ndimage.maximum_filter(from_mask.astype(np.uint8), size=box, mode="constant", cval=0)
    return mask & ~near.astype(bool)


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
