"""Where a reviewer's mark is on the subject: tkr coordinate and nearest surface vertex."""

from pathlib import Path

import nibabel as nib
import numpy as np

from surfaceqa.geometry import to_tkr


def _nearest_vertex(surface_path: Path, tkr: np.ndarray) -> int | None:
    """Index of the surface vertex nearest the point; None when the file cannot be read."""
    try:
        vertices, _ = nib.freesurfer.read_geometry(surface_path)
    except (OSError, ValueError):
        return None
    return int(np.argmin(np.sum((vertices - tkr) ** 2, axis=1)))


def locate_mark(mark: dict, meta: dict) -> dict:
    """The mark with its tkr RAS coordinate and, when the source surface is readable, its vertex."""
    tkr = to_tkr(np.asarray(mark["grid"], dtype=float), np.asarray(meta["grid_to_tkr"]))
    vertex = None
    if mark["surface"] is not None:
        vertex = _nearest_vertex(Path(meta["path"]) / "surf" / mark["surface"], tkr)
    return {**mark, "tkr": [round(float(v), 2) for v in tkr], "vertex": vertex}


def locate_marks(review: dict, meta: dict) -> dict:
    return {**review, "marks": [locate_mark(mark, meta) for mark in review["marks"]]}
