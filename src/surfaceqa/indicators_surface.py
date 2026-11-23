"""Indicators computed on the surface meshes: thick patches and topology defects."""

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from surfaceqa import thresholds
from surfaceqa.findings import Finding
from surfaceqa.indicators_volume import IndicatorResult, not_run
from surfaceqa.subjectdata import HemiSurface, SubjectData


def _vertex_finding(name: str, kind: str, hemi: str, positions: np.ndarray) -> Finding:
    """A finding for a group of vertices, located at the vertex nearest the group's middle."""
    middle = positions.mean(axis=0)
    nearest = positions[np.argmin(np.linalg.norm(positions - middle, axis=1))]
    voxels = np.unique(np.clip(np.rint(positions), 0, 65535).astype(np.uint16), axis=0)
    grid = tuple(int(v) for v in np.clip(np.rint(nearest), 0, None))
    return Finding(name, kind, grid, None, len(positions), hemi=hemi, voxels=voxels)


def _capped(name: str, kind: str, findings: list[Finding]) -> IndicatorResult:
    findings = sorted(findings, key=lambda f: -f.n)
    limit = thresholds.MAX_FINDINGS_PER_INDICATOR
    return IndicatorResult(name, kind, findings=findings[:limit], dropped=max(len(findings) - limit, 0))


def _connected_groups(selected: np.ndarray, faces: np.ndarray) -> list[np.ndarray]:
    """Groups of selected vertices joined by mesh edges."""
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    edges = edges[selected[edges].all(axis=1)]
    n = len(selected)
    graph = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(n, n))
    _, labels = connected_components(graph, directed=False)
    labels = np.where(selected, labels, -1)
    return [np.flatnonzero(labels == label) for label in np.unique(labels[selected])]


def _thick_vertices(surface: HemiSurface) -> np.ndarray:
    thick = surface.thickness >= thresholds.THICK_MM
    if surface.cortex is None:
        return thick
    in_cortex = np.zeros(len(thick), dtype=bool)
    in_cortex[surface.cortex] = True
    return thick & in_cortex


def _hemi_thick_patches(name: str, hemi: str, surface: HemiSurface) -> list[Finding]:
    groups = _connected_groups(_thick_vertices(surface), surface.faces)
    return [_vertex_finding(name, "thickness", hemi, surface.pial_grid[group])
            for group in groups if len(group) >= thresholds.MIN_THICK_VERTICES]


def thick_patches(data: SubjectData) -> IndicatorResult:
    name, kind = "thick_patches", "thickness"
    usable = {hemi: s for hemi, s in data.hemis.items()
              if s.thickness is not None and len(s.thickness) == len(s.pial_grid)}
    if not usable:
        return not_run(name, kind, "no thickness files")
    findings = [f for hemi, s in usable.items() for f in _hemi_thick_patches(name, hemi, s)]
    return _capped(name, kind, findings)


def _has_defect_data(surface: HemiSurface) -> bool:
    return (surface.defect_labels is not None and surface.nofix_grid is not None
            and len(surface.defect_labels) == len(surface.nofix_grid))


def _hemi_defects(name: str, hemi: str, surface: HemiSurface) -> list[Finding]:
    labels = np.rint(surface.defect_labels).astype(int)
    ids, counts = np.unique(labels[labels > 0], return_counts=True)
    return [_vertex_finding(name, "topology", hemi, surface.nofix_grid[labels == i])
            for i, count in zip(ids, counts) if count >= thresholds.MIN_DEFECT_VERTICES]


def topology_defects(data: SubjectData) -> IndicatorResult:
    name, kind = "topology_defects", "topology"
    usable = {hemi: s for hemi, s in data.hemis.items() if _has_defect_data(s)}
    if not usable:
        return not_run(name, kind, "no defect labels with a matching pre-fix surface (orig.nofix)")
    findings = [f for hemi, s in usable.items() for f in _hemi_defects(name, hemi, s)]
    return _capped(name, kind, findings)


SURFACE_INDICATORS = (thick_patches, topology_defects)
