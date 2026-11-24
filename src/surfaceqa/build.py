"""Render one subject's slices and contours into its run folder in the QA directory."""

import json
import shutil
import traceback
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

import nibabel as nib
import numpy as np

from surfaceqa.cohort import Cohort, failed_cohort, load_cohort, update_cohorts
from surfaceqa.contours import SURFACE_ORDER, pack_plane, plane_segments
from surfaceqa.discover import SubjectRef
from surfaceqa.fingerprint import surface_fingerprint
from surfaceqa.geometry import DisplayVolume, load_display_volume, to_grid
from surfaceqa.layout import current_run_dir, read_json, replace_text, subject_dir
from surfaceqa.pipelines import PipelineInfo, SubjectFiles, detect_pipeline, subject_files
from surfaceqa.planes import PLANES, Plane
from surfaceqa.provenance import write_provenance
from surfaceqa import qa
from surfaceqa.qa import write_findings
from surfaceqa.slices import intensity_window, write_plane_slices
from surfaceqa.subjectdata import input_signature, load_subject_data
from surfaceqa.thickness_map import write_thickness_map

BUILD_FORMAT = 4  # raise when the contents of a run folder change, so old runs are re-rendered
COLORS = {"lh.pial": "#ffe100", "rh.pial": "#ffe100", "lh.white": "#2b6cff", "rh.white": "#ff3b30"}


@dataclass
class BuildResult:
    key: str
    status: str  # built, updated (indicators, map or provenance redone), unchanged, missing, failed
    run: str | None = None
    missing: list[str] = field(default_factory=list)


def _write_json(path: Path, payload: dict) -> None:
    replace_text(path, json.dumps(payload, indent=1))


def _identity(ref: SubjectRef, pipeline: PipelineInfo) -> dict:
    return {"key": ref.key, "source": ref.source, "name": ref.name, "path": str(ref.path),
            "pipeline": pipeline.name, "version": pipeline.version}


def _clear_stale(folder: Path) -> None:
    for name in ("missing.json", "error.txt"):
        (folder / name).unlink(missing_ok=True)


def _report_missing(ref: SubjectRef, pipeline: PipelineInfo, files: SubjectFiles,
                    folder: Path) -> BuildResult:
    _clear_stale(folder)
    _write_json(folder / "missing.json", {**_identity(ref, pipeline), "missing": files.missing})
    return BuildResult(ref.key, "missing", missing=files.missing)


def _load_surfaces_grid(files: SubjectFiles, volume: DisplayVolume) -> dict:
    surfaces = {}
    for name in SURFACE_ORDER:
        vertices, faces = nib.freesurfer.read_geometry(files.surfaces[name])
        surfaces[name] = (to_grid(vertices, volume.tkr_to_grid), faces)
    return surfaces


def _write_contours(surfaces: dict, volume: DisplayVolume, run_dir: Path) -> None:
    shape = volume.data.shape
    for plane in PLANES.values():
        per_surface = {name: plane_segments(verts, faces, plane, shape)
                       for name, (verts, faces) in surfaces.items()}
        blob, index = pack_plane(per_surface)
        (run_dir / f"contours_{plane.name}.bin").write_bytes(blob)
        _write_json(run_dir / f"contours_{plane.name}.json", index)


def _write_slices(volume: DisplayVolume, window, run_dir: Path) -> None:
    for plane in PLANES.values():
        write_plane_slices(volume.data, plane, window, run_dir / "slices" / plane.name)


def _plane_meta(plane: Plane, shape) -> dict:
    return {"axis": plane.axis, "h_axis": plane.h_axis, "v_axis": plane.v_axis,
            "h_flip": plane.h_flip, "v_flip": plane.v_flip, "n_slices": shape[plane.axis],
            "width": shape[plane.h_axis], "height": shape[plane.v_axis], "edges": plane.edges}


def _run_meta(ref, pipeline, run: str, volume: DisplayVolume, window) -> dict:
    shape = [int(n) for n in volume.data.shape]
    return {
        **_identity(ref, pipeline), "run": run, "format": BUILD_FORMAT,
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "shape": shape, "voxel_sizes": list(volume.voxel_sizes), "window": list(window),
        "grid_to_tkr": np.linalg.inv(volume.tkr_to_grid).tolist(),
        "grid_to_scanner": volume.grid_to_scanner.tolist(),
        "planes": {name: _plane_meta(plane, shape) for name, plane in PLANES.items()},
        "surfaces": {name: {"color": COLORS[name]} for name in SURFACE_ORDER},
    }


def _qa_inputs(ref: SubjectRef, pipeline: PipelineInfo, cohort: Cohort | None) -> dict:
    """What the findings are made from: the subject's files and the cohort it is compared with."""
    return {**input_signature(ref.path, pipeline), "cohort": [cohort.signature if cohort else ""]}


def _update_qa(ref: SubjectRef, pipeline: PipelineInfo, run_dir: Path,
               cohort: Cohort | None = None) -> bool:
    """Compute the indicators unless they are up to date; True when they were (re)computed.

    A failure is recorded in the run folder and must not lose the viewer. It is retried
    on the next build, as are findings made from other input files, from another cohort
    or by older code.
    """
    inputs = _qa_inputs(ref, pipeline, cohort)
    if qa.is_up_to_date(run_dir, inputs):
        return False
    error_file = run_dir / qa.ERROR_FILE
    try:
        write_findings(load_subject_data(ref.path, pipeline, cohort), run_dir, inputs)
        error_file.unlink(missing_ok=True)
    except Exception:
        (run_dir / qa.FINDINGS_FILE).unlink(missing_ok=True)  # never leave stale findings
        error_file.write_text(traceback.format_exc())
    return True


def _update_map(ref: SubjectRef, run_dir: Path) -> bool:
    """Sample the thickness for the cohort comparison; a failure must not lose the viewer."""
    try:
        return write_thickness_map(ref.path, run_dir)
    except Exception:
        return False


def _update_provenance(ref: SubjectRef, pipeline: PipelineInfo, run_dir: Path) -> bool:
    """Record the original command and edit state; a failure must not lose the viewer."""
    try:
        return write_provenance(ref, pipeline, run_dir)
    except Exception:
        return False


def _render_run(ref, pipeline, files: SubjectFiles, run: str, run_dir: Path) -> None:
    shutil.rmtree(run_dir, ignore_errors=True)  # an interrupted build starts over
    run_dir.mkdir(parents=True)
    volume = load_display_volume(files.t1)
    window = intensity_window(volume.data)
    _write_slices(volume, window, run_dir)
    _write_contours(_load_surfaces_grid(files, volume), volume, run_dir)
    _write_json(run_dir / "meta.json", _run_meta(ref, pipeline, run, volume, window))  # last


def _is_current(run_dir: Path) -> bool:
    """A finished run folder written by this version of the build."""
    try:
        return json.loads((run_dir / "meta.json").read_text()).get("format") == BUILD_FORMAT
    except (OSError, ValueError):
        return False


def _prepare_subject(ref: SubjectRef, qa_dir: Path) -> BuildResult:
    """Everything that depends on the subject alone: the viewer, the thickness map, the provenance."""
    folder = subject_dir(qa_dir, ref.key)
    folder.mkdir(parents=True, exist_ok=True)
    pipeline, files = detect_pipeline(ref.path), subject_files(ref.path)
    if files.missing:
        return _report_missing(ref, pipeline, files, folder)
    run = surface_fingerprint(files.surfaces)
    run_dir = folder / "runs" / run
    rendered = _is_current(run_dir)
    if not rendered:
        _render_run(ref, pipeline, files, run, run_dir)
    redone = _update_map(ref, run_dir)
    redone = _update_provenance(ref, pipeline, run_dir) or redone
    _clear_stale(folder)
    _write_json(folder / "current.json", {"run": run})
    return BuildResult(ref.key, "updated" if rendered and redone else
                       ("unchanged" if rendered else "built"), run=run)


def _run_indicators(ref: SubjectRef, qa_dir: Path, result: BuildResult,
                    cohort: Cohort | None) -> BuildResult:
    """The indicators of a prepared subject, compared with `cohort` when there is one."""
    if result.run is None:
        return result
    run_dir = subject_dir(qa_dir, ref.key) / "runs" / result.run
    recomputed = _update_qa(ref, detect_pipeline(ref.path), run_dir, cohort)
    if recomputed and result.status == "unchanged":
        return BuildResult(ref.key, "updated", run=result.run)
    return result


def build_subject(ref: SubjectRef, qa_dir: Path) -> BuildResult:
    """Build one subject, compared with the cohort statistics already stored (if any)."""
    result = _prepare_subject(ref, qa_dir)
    return _run_indicators(ref, qa_dir, result, load_cohort(qa_dir, ref.source))


def _failed(qa_dir: Path, ref: SubjectRef) -> BuildResult:
    folder = subject_dir(qa_dir, ref.key)
    folder.mkdir(parents=True, exist_ok=True)
    _clear_stale(folder)
    (folder / "error.txt").write_text(traceback.format_exc())
    return BuildResult(ref.key, "failed")


def _safe_prepare(qa_dir: Path, ref: SubjectRef) -> BuildResult:
    try:
        return _prepare_subject(ref, qa_dir)
    except Exception:
        return _failed(qa_dir, ref)


def _safe_indicators(qa_dir: Path, compared: bool, job: tuple[SubjectRef, BuildResult]) -> BuildResult:
    ref, result = job
    try:
        cohort = load_cohort(qa_dir, ref.source) if compared else failed_cohort(ref.source)
        return _run_indicators(ref, qa_dir, result, cohort)
    except Exception:
        return _failed(qa_dir, ref)


def _safe_cohorts(qa_dir: Path) -> set[str] | None:
    """Bring the cohort statistics up to date. Returns the source folders whose statistics
    changed, or None (and leaves a note) when that failed."""
    error_file = qa_dir / "cohort" / "error.txt"
    try:
        changed = update_cohorts(qa_dir)
        error_file.unlink(missing_ok=True)
        return changed
    except Exception:
        error_file.parent.mkdir(parents=True, exist_ok=True)
        error_file.write_text(traceback.format_exc())
        return None


def _also_affected(qa_dir: Path, changed: set[str], built: list[SubjectRef]) -> list[tuple[SubjectRef, BuildResult]]:
    """Subjects that were not asked for but whose cohort changed, so their comparison is stale.

    A build of some subjects (`--subjects`) changes what every subject of the folder is
    compared with. Only subjects whose source folder is still there can be recomputed.
    """
    asked, jobs = {ref.key for ref in built}, []
    root = qa_dir / "subjects"
    for folder in sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
        meta = load_meta(qa_dir, folder.name)
        if (meta and folder.name not in asked and meta.get("source") in changed
                and Path(meta.get("path") or "\0").is_dir()):
            ref = SubjectRef(meta["source"], meta["name"], Path(meta["path"]))
            jobs.append((ref, BuildResult(ref.key, "unchanged", run=meta["run"])))
    return jobs


def _each(function, items: list, pool: ProcessPoolExecutor | None) -> list:
    return [function(item) for item in items] if pool is None else list(pool.map(function, items))


def _build_passes(refs: list[SubjectRef], qa_dir: Path, pool: ProcessPoolExecutor | None) -> list[BuildResult]:
    """Each subject on its own, then the cohort statistics, then the indicators that use them."""
    prepared = _each(partial(_safe_prepare, qa_dir), refs, pool)
    changed = _safe_cohorts(qa_dir)
    jobs = list(zip(refs, prepared)) + _also_affected(qa_dir, changed or set(), refs)
    return _each(partial(_safe_indicators, qa_dir, changed is not None), jobs, pool)


def build_all(refs: list[SubjectRef], qa_dir: Path, jobs: int = 1) -> list[BuildResult]:
    """Build every subject; results come back in the order of refs, followed by any other
    subjects whose cohort comparison had to be redone."""
    qa_dir = Path(qa_dir)
    if jobs <= 1:
        return _build_passes(refs, qa_dir, None)
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        return _build_passes(refs, qa_dir, pool)


def load_meta(qa_dir: Path, key: str) -> dict | None:
    run_dir = current_run_dir(qa_dir, key)
    return None if run_dir is None else read_json(run_dir / "meta.json")
