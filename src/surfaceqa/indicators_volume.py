"""Indicators computed on voxel volumes. Each returns located findings or says why it did not run."""

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from surfaceqa import thresholds
from surfaceqa.findings import Finding, cluster_findings, deeper_than, farther_than
from surfaceqa.subjectdata import SubjectData

CORTEX = (3, 42)
WHITE = (2, 41)
CEREBELLUM = (7, 8, 46, 47)
NOT_BRAIN = (0, 24)  # background, and the CSF label that SynthSeg puts around the brain
SEG_CORTEX = (3, 42)  # cortex as one class per hemisphere (aseg, SynthSeg)
MAD_TO_SD = 1.4826
MISSING = {
    "ribbon": "no ribbon.mgz",
    "seg": "no independent segmentation",
    "nonbrain": "no sinus or dura label files (vsinus.mgz, mca-dura.mgz) for this subject",
    "norm": "no norm.mgz",
    "hemi_ribbon": "no lh.ribbon.mgz and rh.ribbon.mgz",
}
NO_CORTEX = "segmentation has no cortex labels"


@dataclass
class IndicatorResult:
    name: str
    kind: str
    status: str = "ran"
    reason: str = ""
    findings: list[Finding] = field(default_factory=list)
    dropped: int = 0


def not_run(name: str, kind: str, reason: str) -> IndicatorResult:
    return IndicatorResult(name, kind, status="not run", reason=reason)


def _missing(data: SubjectData, *fields: str) -> str:
    """Why the indicator cannot run, or an empty string when every input is there."""
    return "; ".join(MISSING[f] for f in fields if getattr(data, f) is None)


def _result(name: str, kind: str, mask: np.ndarray, data: SubjectData) -> IndicatorResult:
    findings, dropped = cluster_findings(
        mask, name, kind, data.voxel_sizes,
        thresholds.MIN_CLUSTER_MM3, thresholds.MAX_FINDINGS_PER_INDICATOR)
    return IndicatorResult(name, kind, findings=findings, dropped=dropped)


def _cortex(data: SubjectData) -> np.ndarray:
    return np.isin(data.ribbon, CORTEX)


def _deep(mask: np.ndarray, data: SubjectData) -> np.ndarray:
    return deeper_than(mask, thresholds.MARGIN_MM, data.voxel_sizes)


def ribbon_outside_brain(data: SubjectData) -> IndicatorResult:
    name, kind = "ribbon_outside_brain", "pial_out"
    if reason := _missing(data, "ribbon", "seg"):
        return not_run(name, kind, reason)
    return _result(name, kind, _cortex(data) & _deep(np.isin(data.seg, NOT_BRAIN), data), data)


def ribbon_in_nonbrain_mask(data: SubjectData) -> IndicatorResult:
    name, kind = "ribbon_in_nonbrain_mask", "pial_out"
    if reason := _missing(data, "ribbon", "nonbrain"):
        return not_run(name, kind, reason)
    return _result(name, kind, _cortex(data) & data.nonbrain, data)


def ribbon_in_cerebellum(data: SubjectData) -> IndicatorResult:
    name, kind = "ribbon_in_cerebellum", "pial_out"
    if reason := _missing(data, "ribbon", "seg"):
        return not_run(name, kind, reason)
    return _result(name, kind, _cortex(data) & _deep(np.isin(data.seg, CEREBELLUM), data), data)


def missed_gray(data: SubjectData) -> IndicatorResult:
    name, kind = "missed_gray", "gray_missed"
    if reason := _missing(data, "ribbon", "seg"):
        return not_run(name, kind, reason)
    seg_cortex = (data.seg >= 1000) | np.isin(data.seg, SEG_CORTEX)
    if not seg_cortex.any():
        return not_run(name, kind, NO_CORTEX)
    missed = farther_than(seg_cortex & (data.ribbon == 0), data.ribbon > 0,
                          thresholds.MARGIN_MM, data.voxel_sizes)
    return _result(name, kind, missed, data)


def white_matter_in_ribbon(data: SubjectData) -> IndicatorResult:
    name, kind = "white_matter_in_ribbon", "white_short"
    if reason := _missing(data, "ribbon", "seg"):
        return not_run(name, kind, reason)
    return _result(name, kind, _cortex(data) & _deep(np.isin(data.seg, WHITE), data), data)


def _bright_threshold(values: np.ndarray) -> float:
    median = np.median(values)
    mad = np.median(np.abs(values - median))
    return float(median + thresholds.BRIGHT_MAD * MAD_TO_SD * mad)


def bright_ribbon(data: SubjectData) -> IndicatorResult:
    name, kind = "bright_ribbon", "pial_out"
    if reason := _missing(data, "ribbon", "norm"):
        return not_run(name, kind, reason)
    deep = farther_than(_cortex(data), np.isin(data.ribbon, WHITE),
                        thresholds.MARGIN_MM, data.voxel_sizes)
    if not deep.any():
        return IndicatorResult(name, kind)
    return _result(name, kind, deep & (data.norm > _bright_threshold(data.norm[deep])), data)


def hemisphere_crossing(data: SubjectData) -> IndicatorResult:
    name, kind = "hemisphere_crossing", "crossing"
    if reason := _missing(data, "hemi_ribbon"):
        return not_run(name, kind, reason)
    return _result(name, kind, data.hemi_ribbon["lh"] & data.hemi_ribbon["rh"], data)


VOLUME_INDICATORS: tuple[Callable[[SubjectData], IndicatorResult], ...] = (
    ribbon_outside_brain, ribbon_in_nonbrain_mask, ribbon_in_cerebellum, missed_gray,
    white_matter_in_ribbon, bright_ribbon, hemisphere_crossing)
