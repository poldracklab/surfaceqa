"""Run every indicator on a subject and write the findings into its run folder."""

import json
from pathlib import Path

import numpy as np

from surfaceqa import thresholds
from surfaceqa.findings import Finding
from surfaceqa.indicators_cohort import COHORT_INDICATORS
from surfaceqa.indicators_surface import SURFACE_INDICATORS
from surfaceqa.indicators_volume import VOLUME_INDICATORS, IndicatorResult
from surfaceqa.layout import current_run_dir, read_json
from surfaceqa.regions import assign_region, build_context, default_locations
from surfaceqa import scoring
from surfaceqa.scoring import finding_points, suspicion_score
from surfaceqa.subjectdata import SubjectData

QA_VERSION = 10  # raise whenever indicators, regions or scoring change, so findings are recomputed
FINDINGS_FILE = "findings.json"
ERROR_FILE = "qa_error.txt"
NON_BRAIN_REGIONS = {"sinus", "cerebellum", "outer_edge", "frontal_midline"}
VOXELS_FILE = "findings_voxels.bin"
INDICATORS = (*VOLUME_INDICATORS, *SURFACE_INDICATORS, *COHORT_INDICATORS)


def run_indicators(data: SubjectData) -> tuple[list[IndicatorResult], str]:
    """Every indicator's result with findings assigned to regions, and a note on region assignment."""
    results = [indicator(data) for indicator in INDICATORS]
    context = build_context(data)
    for result in results:
        for finding in result.findings:
            finding.region = assign_region(finding, context)
        relabel_by_region(result.findings)
    return results, context.reason


def relabel_by_region(findings: list[Finding]) -> None:
    """A segmentation's cortex beyond the pial surface means different things in different places.

    Next to the sinus, the cerebellum or the outer edge of the brain it is usually sinus or
    dura that the surface was right to leave out, so it becomes an unscored place to look.
    Under the frontal and temporal lobes it stays a possible miss of gray matter.
    """
    for finding in findings:
        if finding.kind == "gray_missed" and finding.region in NON_BRAIN_REGIONS:
            finding.kind = "look_here"


def _indicator_record(result: IndicatorResult) -> dict:
    return {"name": result.name, "kind": result.kind, "status": result.status,
            "reason": result.reason, "n_findings": len(result.findings), "dropped": result.dropped}


def _finding_record(number: int, finding: Finding, voxel_start: int) -> dict:
    size = None if finding.size_mm3 is None else round(float(finding.size_mm3), 1)
    return {"id": number, "indicator": finding.indicator, "kind": finding.kind,
            "region": finding.region, "hemi": finding.hemi,
            "grid": [int(v) for v in finding.grid], "size_mm3": size, "n": int(finding.n),
            "points": round(finding_points(finding), 2),
            "voxel_start": voxel_start, "voxel_count": len(finding.voxels)}


def _records_and_voxels(findings: list[Finding]) -> tuple[list[dict], bytes]:
    ordered = sorted(findings, key=lambda f: -round(finding_points(f), 2))
    records, chunks, start = [], [], 0
    for number, finding in enumerate(ordered):
        records.append(_finding_record(number, finding, start))
        chunks.append(finding.voxels.astype("<u2"))
        start += len(finding.voxels)
    blob = np.concatenate(chunks).tobytes() if chunks else b""
    return records, blob


def write_findings(data: SubjectData, run_dir: Path, inputs: dict | None = None) -> dict:
    """`inputs` is the signature of the files the data was read from (see is_up_to_date)."""
    results, region_note = run_indicators(data)
    findings = [f for result in results for f in result.findings]
    records, blob = _records_and_voxels(findings)
    out = {"qa_version": QA_VERSION, "inputs": inputs or {},
           "score": suspicion_score(findings), "thresholds": thresholds.as_dict(),
           "scoring": scoring.as_dict(), "region_note": region_note, "indicators": [_indicator_record(r) for r in results],
           "findings": records, "defaults": default_locations(data)}
    (Path(run_dir) / VOXELS_FILE).write_bytes(blob)
    (Path(run_dir) / FINDINGS_FILE).write_text(json.dumps(out, indent=1))
    return out


def is_up_to_date(run_dir: Path, inputs: dict) -> bool:
    """Findings exist, were made by this version of the indicators, from these input files."""
    found = read_json(Path(run_dir) / FINDINGS_FILE)
    return (found is not None and found.get("qa_version") == QA_VERSION
            and found.get("inputs") == inputs)


def load_findings(qa_dir: Path, key: str) -> dict | None:
    run_dir = current_run_dir(qa_dir, key)
    return None if run_dir is None else read_json(run_dir / FINDINGS_FILE)
