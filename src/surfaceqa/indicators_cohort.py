"""Thickness compared with the other subjects of the source folder, place by place."""

import numpy as np

from surfaceqa import thresholds
from surfaceqa.cohort import Cohort
from surfaceqa.findings import Finding
from surfaceqa.indicators_surface import capped, connected_groups, unchecked, vertex_finding
from surfaceqa.indicators_volume import IndicatorResult, not_run
from surfaceqa.sphere import nearest, target_points
from surfaceqa.subjectdata import HemiSurface, SubjectData

NAME, KIND = "cohort_thickness", "thickness"


def _too_few(cohort: Cohort | None) -> str:
    count = 0 if cohort is None else cohort.n
    return f"needs {thresholds.MIN_COHORT} subjects in this source folder; there are {count}"


def _comparable(surface: HemiSurface, hemi: str, cohort: Cohort) -> bool:
    return (surface.sphere is not None and surface.thickness is not None
            and surface.cortex is not None and hemi in cohort.median
            and len(surface.sphere) == len(surface.thickness) == len(surface.pial_grid))


def _far_above(surface: HemiSurface, median: np.ndarray, spread: np.ndarray) -> np.ndarray:
    """Cortex vertices much thicker than the cohort is at the nearest common point."""
    at = nearest(target_points(), surface.sphere)
    excess = surface.thickness - median[at]
    usable = np.isfinite(excess) & (spread[at] > 0)
    deviations = np.divide(excess, spread[at], out=np.zeros(len(at)), where=usable)
    in_cortex = np.zeros(len(at), dtype=bool)
    in_cortex[surface.cortex[surface.cortex < len(at)]] = True
    return (usable & in_cortex & (deviations >= thresholds.COHORT_Z)
            & (excess >= thresholds.COHORT_MIN_MM))


def _hemi_findings(hemi: str, surface: HemiSurface, cohort: Cohort) -> list[Finding]:
    selected = _far_above(surface, cohort.median[hemi], cohort.spread[hemi])
    return [vertex_finding(NAME, KIND, hemi, surface.pial_grid[group])
            for group in connected_groups(selected, surface.faces)
            if len(group) >= thresholds.MIN_COHORT_VERTICES]


def cohort_thickness(data: SubjectData) -> IndicatorResult:
    cohort = data.cohort
    if cohort is None or cohort.median is None:
        return not_run(NAME, KIND, _too_few(cohort))
    if all(surface.sphere is None for surface in data.hemis.values()):
        return not_run(NAME, KIND, "no sphere.reg")
    usable = {hemi: s for hemi, s in data.hemis.items() if _comparable(s, hemi, cohort)}
    findings = [f for hemi, s in usable.items() for f in _hemi_findings(hemi, s, cohort)]
    why = "no matching sphere.reg, thickness and cortex label, or no cohort values"
    return capped(NAME, KIND, findings, unchecked(data, usable, why))


COHORT_INDICATORS = (cohort_thickness,)
