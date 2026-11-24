"""Compose the freeview command that opens a subject at a marked problem."""

import math
import shlex

T1 = "mri/orig.mgz"
SURFACE_COLORS = {"lh.white": "blue", "lh.pial": "yellow", "rh.white": "red", "rh.pial": "yellow"}
OVERLAY = ":colormap=heat:opacity=0.4"
NO_FOLDER = "<subject folder>"


def _path(subject_path: str, rel: str) -> str:
    return shlex.quote(f"{subject_path or NO_FOLDER}/{rel}")


def _volumes(subject_path: str, edit: str | None, overlay: bool) -> list[str]:
    volumes = [_path(subject_path, T1)]
    if edit:
        volumes.append(_path(subject_path, edit) + (OVERLAY if overlay else ""))
    return volumes


def _surfaces(subject_path: str) -> list[str]:
    return [f"{_path(subject_path, f'surf/{name}')}:edgecolor={color}"
            for name, color in SURFACE_COLORS.items()]


def usable_point(tkr) -> bool:
    """Three finite numbers."""
    return (isinstance(tkr, (list, tuple)) and len(tkr) == 3
            and all(isinstance(v, (int, float)) and math.isfinite(v) for v in tkr))


def _cursor(tkr) -> list[str]:
    if not usable_point(tkr):
        return []
    return ["-ras", *(f"{value:.2f}" for value in tkr), "tkreg", "-cc"]


def freeview_command(subject_path: str, edit: str | None, tkr, overlay: bool = False) -> str:
    """The T1, the volume to edit and the four surfaces, with the cursor at `tkr` (surface RAS)."""
    words = ["freeview", "-v", *_volumes(subject_path, edit, overlay), "-f",
             *_surfaces(subject_path), *_cursor(tkr), "-viewport", "coronal"]
    return " ".join(words)
