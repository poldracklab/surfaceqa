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
FULL_COVERAGE = 0.9  # below this share of the cortex, the result says how much was compared
WHY_SKIPPED = "no usable sphere.reg, thickness and cortex label, or no cohort values"


def _too_few(cohort: Cohort | None) -> str:
    if cohort is not None and cohort.note:
        return cohort.note
    count = 0 if cohort is None else cohort.n
    return f"needs {thresholds.MIN_COHORT} subjects in this source folder; there are {count}"


def _sphere_usable(sphere: np.ndarray | None) -> bool:
    """Every vertex has a direction: no missing coordinates and none at the centre."""
    return (sphere is not None and bool(np.isfinite(sphere).all())
            and bool((np.linalg.norm(sphere, axis=1) > 0).all()))


def _comparable(surface: HemiSurface, hemi: str, cohort: Cohort) -> bool:
    return (_sphere_usable(surface.sphere) and surface.thickness is not None
            and surface.cortex is not None and hemi in cohort.median
            and (len(surface.cortex) == 0 or int(surface.cortex.max()) < len(surface.thickness))
            and len(surface.sphere) == len(surface.thickness) == len(surface.pial_grid))


def _compared(surface: HemiSurface, median: np.ndarray, spread: np.ndarray) -> tuple[np.ndarray, float]:
    """Cortex vertices much thicker than the cohort is at the nearest common point, and the
    share of cortex vertices at which the cohort has values to compare with."""
    at = nearest(target_points(), surface.sphere)
    excess = surface.thickness - median[at]
    usable = np.isfinite(excess) & (spread[at] > 0)
    deviations = np.divide(excess, spread[at], out=np.zeros(len(at)), where=usable)
    in_cortex = np.zeros(len(at), dtype=bool)
    in_cortex[surface.cortex] = True
    far = (usable & in_cortex & (deviations >= thresholds.COHORT_Z)
           & (excess >= thresholds.COHORT_MIN_MM))
    return far, float((usable & in_cortex).sum() / max(in_cortex.sum(), 1))


def _patches(hemi: str, surface: HemiSurface, selected: np.ndarray) -> list[Finding]:
    return [vertex_finding(NAME, KIND, hemi, surface.pial_grid[group])
            for group in connected_groups(selected, surface.faces)
            if len(group) >= thresholds.MIN_COHORT_VERTICES]


def _coverage_note(coverage: dict[str, float]) -> str:
    """Says where only part of the cortex could be compared, so "ran" is not read as "all of it"."""
    return "; ".join(f"{hemi}: cohort values at {share:.0%} of cortex vertices"
                     for hemi, share in coverage.items() if share < FULL_COVERAGE)


def cohort_thickness(data: SubjectData) -> IndicatorResult:
    cohort = data.cohort
    if cohort is None or cohort.median is None:
        return not_run(NAME, KIND, _too_few(cohort))
    if all(surface.sphere is None for surface in data.hemis.values()):
        return not_run(NAME, KIND, "no sphere.reg")
    results = {hemi: _compared(s, cohort.median[hemi], cohort.spread[hemi])
               for hemi, s in data.hemis.items() if _comparable(s, hemi, cohort)}
    usable = {hemi: data.hemis[hemi] for hemi, (_, share) in results.items() if share > 0}
    skipped = unchecked(data, usable, WHY_SKIPPED)
    if not usable:
        return not_run(NAME, KIND, skipped)
    findings = [f for hemi, s in usable.items() for f in _patches(hemi, s, results[hemi][0])]
    notes = [skipped, _coverage_note({hemi: results[hemi][1] for hemi in usable})]
    return capped(NAME, KIND, findings, "; ".join(note for note in notes if note))


COHORT_INDICATORS = (cohort_thickness,)
