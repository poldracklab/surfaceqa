"""Load the files the indicators read, as arrays on the display grid."""

from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np

from surfaceqa.cohort import Cohort
from surfaceqa.geometry import load_display_volume, to_grid
from surfaceqa.pipelines import PipelineInfo, subject_files

HEMIS = ("lh", "rh")
SEG_FILE = {"fastsurfer": "aparc.DKTatlas+aseg.deep.mgz"}
DEFAULT_SEG_FILE = "aseg.presurf.mgz"
NONBRAIN_FILES = {"fastsurfer": ()}
DEFAULT_NONBRAIN_FILES = ("vsinus.mgz", "mca-dura.mgz")
PARC_FILE = "aparc.DKTatlas+aseg.mgz"
SYNTHSEG_FILE = "synthseg.rca.mgz"


@dataclass
class HemiSurface:
    pial_grid: np.ndarray
    faces: np.ndarray
    thickness: np.ndarray | None
    cortex: np.ndarray | None
    defect_labels: np.ndarray | None
    nofix_grid: np.ndarray | None
    sphere: np.ndarray | None = None  # sphere.reg: the vertices in coordinates shared by all subjects


@dataclass
class SubjectData:
    voxel_sizes: tuple[float, float, float]
    ribbon: np.ndarray | None
    hemi_ribbon: dict[str, np.ndarray] | None
    seg: np.ndarray | None
    seg_name: str | None
    nonbrain: np.ndarray | None
    nonbrain_names: list[str]
    parc: np.ndarray | None
    norm: np.ndarray | None
    hemis: dict[str, HemiSurface]
    seg_method: str = "network"  # "network" (FastSurfer, SynthSeg) or "atlas" (older recon-all)
    cohort: Cohort | None = None  # thickness across the subjects of the same source folder


def _optional(reader, *args):
    """The reader's result, or None when the file is absent or unreadable."""
    try:
        return reader(*args)
    except Exception:  # truncated, empty or half-written files raise many different errors
        return None


def _volume(path: Path, shape) -> np.ndarray | None:
    volume = _optional(load_display_volume, path)
    if volume is None or volume.data.shape != tuple(shape):
        return None
    return volume.data


def _labels(path: Path, shape) -> np.ndarray | None:
    data = _volume(path, shape)
    return None if data is None else np.rint(data).astype(np.int32)


def _hemi_ribbon(mri: Path, shape) -> dict[str, np.ndarray] | None:
    masks = {hemi: _volume(mri / f"{hemi}.ribbon.mgz", shape) for hemi in HEMIS}
    if any(mask is None for mask in masks.values()):
        return None
    return {hemi: mask > 0 for hemi, mask in masks.items()}


def _nonbrain(mri: Path, names, shape) -> tuple[np.ndarray | None, list[str]]:
    found = {name: _volume(mri / name, shape) for name in names}
    found = {name: data for name, data in found.items() if data is not None}
    if not found:
        return None, []
    return np.any([data > 0 for data in found.values()], axis=0), list(found)


def _grid_surface(path: Path, tkr_to_grid) -> tuple[np.ndarray, np.ndarray]:
    vertices, faces = nib.freesurfer.read_geometry(path)
    return to_grid(vertices, tkr_to_grid), faces


def _sphere(path: Path) -> np.ndarray:
    return nib.freesurfer.read_geometry(path)[0]


def _hemi_surface(subject_dir: Path, hemi: str, pial_path: Path, tkr_to_grid) -> HemiSurface:
    surf = subject_dir / "surf"
    pial_grid, faces = _grid_surface(pial_path, tkr_to_grid)
    nofix = _optional(_grid_surface, surf / f"{hemi}.orig.nofix", tkr_to_grid)
    return HemiSurface(
        pial_grid=pial_grid, faces=faces,
        thickness=_optional(nib.freesurfer.read_morph_data, surf / f"{hemi}.thickness"),
        cortex=_optional(nib.freesurfer.read_label, subject_dir / "label" / f"{hemi}.cortex.label"),
        defect_labels=_optional(nib.freesurfer.read_morph_data, surf / f"{hemi}.defect_labels"),
        nofix_grid=None if nofix is None else nofix[0],
        sphere=_optional(_sphere, surf / f"{hemi}.sphere.reg"),
    )


def _seg_method(mri: Path, pipeline: PipelineInfo) -> str:
    """How the segmentation was made. recon-all 8 copies its aseg from SynthSeg and keeps
    that file; older versions label voxels from an atlas, which takes sinus and dura for cortex."""
    if pipeline.name == "fastsurfer" or (mri / SYNTHSEG_FILE).is_file():
        return "network"
    return "atlas"


def _input_files(pipeline: PipelineInfo) -> list[str]:
    """Every optional file the indicators read, relative to the subject folder."""
    mri = ["ribbon.mgz", "lh.ribbon.mgz", "rh.ribbon.mgz", "norm.mgz", PARC_FILE, SYNTHSEG_FILE,
           SEG_FILE.get(pipeline.name, DEFAULT_SEG_FILE),
           *NONBRAIN_FILES.get(pipeline.name, DEFAULT_NONBRAIN_FILES)]
    surf = [f"{hemi}.{name}" for hemi in HEMIS 
            for name in ("thickness", "defect_labels", "orig.nofix", "sphere.reg")]
    return [f"mri/{f}" for f in mri] + [f"surf/{f}" for f in surf] + [
        f"label/{hemi}.cortex.label" for hemi in HEMIS]


def input_signature(subject_dir: Path, pipeline: PipelineInfo) -> dict[str, list[int]]:
    """Size and modification time of each indicator input that exists, to detect changes."""
    signature = {}
    for rel in _input_files(pipeline):
        path = Path(subject_dir) / rel
        if path.is_file():
            stat = path.stat()
            signature[rel] = [stat.st_size, stat.st_mtime_ns]
    return signature


def load_subject_data(subject_dir: Path, pipeline: PipelineInfo,
                      cohort: Cohort | None = None) -> SubjectData:
    subject_dir = Path(subject_dir)
    mri = subject_dir / "mri"
    files = subject_files(subject_dir)
    grid = load_display_volume(files.t1)
    shape = grid.data.shape
    seg_name = SEG_FILE.get(pipeline.name, DEFAULT_SEG_FILE)
    seg = _labels(mri / seg_name, shape)
    nonbrain, names = _nonbrain(mri, NONBRAIN_FILES.get(pipeline.name, DEFAULT_NONBRAIN_FILES), shape)
    hemis = {hemi: _hemi_surface(subject_dir, hemi, files.surfaces[f"{hemi}.pial"], grid.tkr_to_grid)
             for hemi in HEMIS if f"{hemi}.pial" in files.surfaces}
    return SubjectData(
        voxel_sizes=grid.voxel_sizes, ribbon=_labels(mri / "ribbon.mgz", shape),
        hemi_ribbon=_hemi_ribbon(mri, shape), seg=seg, seg_name=seg_name if seg is not None else None,
        nonbrain=nonbrain, nonbrain_names=names, parc=_labels(mri / PARC_FILE, shape),
        norm=_volume(mri / "norm.mgz", shape), hemis=hemis, seg_method=_seg_method(mri, pipeline),
        cohort=cohort)
