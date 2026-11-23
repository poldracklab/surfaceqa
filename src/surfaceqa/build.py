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

from surfaceqa.contours import SURFACE_ORDER, pack_plane, plane_segments
from surfaceqa.discover import SubjectRef
from surfaceqa.fingerprint import surface_fingerprint
from surfaceqa.geometry import DisplayVolume, load_display_volume, to_grid
from surfaceqa.layout import current_run_dir, read_json, subject_dir
from surfaceqa.pipelines import PipelineInfo, SubjectFiles, detect_pipeline, subject_files
from surfaceqa.planes import PLANES, Plane
from surfaceqa import qa
from surfaceqa.qa import write_findings
from surfaceqa.slices import intensity_window, write_plane_slices
from surfaceqa.subjectdata import input_signature, load_subject_data

BUILD_FORMAT = 2  # raise when the contents of a run folder change, so old runs are re-rendered
COLORS = {"lh.pial": "#ffe100", "rh.pial": "#ffe100", "lh.white": "#2b6cff", "rh.white": "#ff3b30"}


@dataclass
class BuildResult:
    key: str
    status: str  # built, updated (indicators recomputed), unchanged, missing, failed
    run: str | None = None
    missing: list[str] = field(default_factory=list)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=1))


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
        "planes": {name: _plane_meta(plane, shape) for name, plane in PLANES.items()},
        "surfaces": {name: {"color": COLORS[name]} for name in SURFACE_ORDER},
    }


def _update_qa(ref: SubjectRef, pipeline: PipelineInfo, run_dir: Path) -> bool:
    """Compute the indicators unless they are up to date; True when they were (re)computed.

    A failure is recorded in the run folder and must not lose the viewer. It is retried
    on the next build, as are findings made from other input files or by older code.
    """
    inputs = input_signature(ref.path, pipeline)
    if qa.is_up_to_date(run_dir, inputs):
        return False
    error_file = run_dir / qa.ERROR_FILE
    try:
        write_findings(load_subject_data(ref.path, pipeline), run_dir, inputs)
        error_file.unlink(missing_ok=True)
    except Exception:
        (run_dir / qa.FINDINGS_FILE).unlink(missing_ok=True)  # never leave stale findings
        error_file.write_text(traceback.format_exc())
    return True


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


def build_subject(ref: SubjectRef, qa_dir: Path) -> BuildResult:
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
    recomputed = _update_qa(ref, pipeline, run_dir)
    status = "built" if not rendered else ("updated" if recomputed else "unchanged")
    _clear_stale(folder)
    _write_json(folder / "current.json", {"run": run})
    return BuildResult(ref.key, status, run=run)


def _safe_build(qa_dir: Path, ref: SubjectRef) -> BuildResult:
    try:
        return build_subject(ref, qa_dir)
    except Exception:
        folder = subject_dir(qa_dir, ref.key)
        folder.mkdir(parents=True, exist_ok=True)
        _clear_stale(folder)
        (folder / "error.txt").write_text(traceback.format_exc())
        return BuildResult(ref.key, "failed")


def build_all(refs: list[SubjectRef], qa_dir: Path, jobs: int = 1) -> list[BuildResult]:
    """Build every subject; results come back in the order of refs."""
    build = partial(_safe_build, Path(qa_dir))
    if jobs <= 1:
        return [build(ref) for ref in refs]
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(build, refs))


def load_meta(qa_dir: Path, key: str) -> dict | None:
    run_dir = current_run_dir(qa_dir, key)
    return None if run_dir is None else read_json(run_dir / "meta.json")
