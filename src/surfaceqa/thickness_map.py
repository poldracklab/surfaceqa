"""A subject's cortical thickness sampled at the common sphere points, kept in its run folder."""

import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np

from surfaceqa.layout import file_signature
from surfaceqa.pipelines import HEMIS
from surfaceqa.sphere import nearest, target_points

MAP_FILE = "thickness_map.npz"
MAP_VERSION = 1  # raise when the sampling changes, so maps are made again
INPUTS = ("surf/{hemi}.sphere.reg", "surf/{hemi}.thickness", "label/{hemi}.cortex.label")


def _signature(subject_dir: Path) -> str:
    """What the map is made from, to detect changes."""
    rels = [pattern.format(hemi=hemi) for hemi in HEMIS for pattern in INPUTS]
    return json.dumps({"version": MAP_VERSION, "inputs": file_signature(subject_dir, rels)},
                      sort_keys=True)


def _hemi_map(subject_dir: Path, hemi: str) -> np.ndarray:
    """Thickness of the subject vertex nearest each common point; NaN outside the cortex label."""
    sphere, _ = nib.freesurfer.read_geometry(subject_dir / "surf" / f"{hemi}.sphere.reg")
    thickness = nib.freesurfer.read_morph_data(subject_dir / "surf" / f"{hemi}.thickness")
    cortex = nib.freesurfer.read_label(subject_dir / "label" / f"{hemi}.cortex.label")
    if len(thickness) != len(sphere):
        raise ValueError("thickness and sphere.reg have different numbers of vertices")
    values = np.full(len(sphere), np.nan, dtype=np.float32)
    values[cortex] = thickness[cortex]
    return values[nearest(sphere, target_points())]


def _maps(subject_dir: Path) -> dict[str, np.ndarray]:
    maps = {}
    for hemi in HEMIS:
        try:
            maps[hemi] = _hemi_map(subject_dir, hemi)
        except Exception:  # missing, truncated or mismatched files: this hemisphere is left out
            continue
    return maps


def map_signature(run_dir: Path) -> str | None:
    """What the run's map was made from, or None when it has no readable map."""
    try:
        with np.load(Path(run_dir) / MAP_FILE) as stored:
            return str(stored["signature"])
    except Exception:
        return None


def save_thickness_map(run_dir: Path, maps: dict[str, np.ndarray], signature: str) -> None:
    path = Path(run_dir) / MAP_FILE
    partial = path.with_suffix(".partial")
    with open(partial, "wb") as handle:
        np.savez_compressed(handle, signature=np.array(signature), **maps)
    os.replace(partial, path)


def write_thickness_map(subject_dir: Path, run_dir: Path) -> bool:
    """Make the map unless it is up to date; True when the file was written or removed."""
    path = Path(run_dir) / MAP_FILE
    signature = _signature(Path(subject_dir))
    if map_signature(run_dir) == signature:
        return False
    maps = _maps(Path(subject_dir))
    if maps:
        save_thickness_map(run_dir, maps, signature)
        return True
    existed = path.exists()
    path.unlink(missing_ok=True)
    return existed


def load_thickness_map(run_dir: Path) -> dict[str, np.ndarray] | None:
    """hemisphere -> thickness at the common points, or None when the run has no usable map."""
    try:
        with np.load(Path(run_dir) / MAP_FILE) as stored:
            maps = {hemi: stored[hemi] for hemi in HEMIS if hemi in stored.files}
    except Exception:
        return None
    return maps or None
