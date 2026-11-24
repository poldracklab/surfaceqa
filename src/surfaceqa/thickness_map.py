"""A subject's cortical thickness sampled at the common sphere points, kept in its run folder."""

import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np

from surfaceqa.sphere import nearest, target_points

MAP_FILE = "thickness_map.npz"
MAP_VERSION = 1  # raise when the sampling changes, so maps are made again
HEMIS = ("lh", "rh")
INPUTS = ("surf/{hemi}.sphere.reg", "surf/{hemi}.thickness", "label/{hemi}.cortex.label")


def _signature(subject_dir: Path) -> str:
    """Size and modification time of every input that exists, to detect changes."""
    found = {}
    for hemi in HEMIS:
        for rel in (pattern.format(hemi=hemi) for pattern in INPUTS):
            path = subject_dir / rel
            if path.is_file():
                stat = path.stat()
                found[rel] = [stat.st_size, stat.st_mtime_ns]
    return json.dumps({"version": MAP_VERSION, "inputs": found}, sort_keys=True)


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


def _stored_signature(path: Path) -> str | None:
    try:
        with np.load(path) as stored:
            return str(stored["signature"])
    except Exception:
        return None


def _save(path: Path, maps: dict[str, np.ndarray], signature: str) -> None:
    partial = path.with_suffix(".partial")
    with open(partial, "wb") as handle:
        np.savez_compressed(handle, signature=np.array(signature), **maps)
    os.replace(partial, path)


def write_thickness_map(subject_dir: Path, run_dir: Path) -> bool:
    """Make the map unless it is up to date; True when the file was written or removed."""
    path = Path(run_dir) / MAP_FILE
    signature = _signature(Path(subject_dir))
    if _stored_signature(path) == signature:
        return False
    maps = _maps(Path(subject_dir))
    if maps:
        _save(path, maps, signature)
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
