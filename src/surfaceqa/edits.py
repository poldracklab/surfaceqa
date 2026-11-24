"""Tell whether a subject was manually edited, from its logs and the contents of its files.

The existence of `brain.finalsurfs.manedit.mgz` is not evidence: both pipelines write it
themselves as a copy of `brain.finalsurfs.mgz`.
"""

from pathlib import Path

import nibabel as nib
import numpy as np

from surfaceqa.invocation import RERUN_FLAGS, all_commands

BFS = "mri/brain.finalsurfs.mgz"
BFS_EDIT = "mri/brain.finalsurfs.manedit.mgz"
FASTSURFER_SEG_EDIT = "mri/aparc.DKTatlas+aseg.deep.manedit.mgz"
RECON_ALL_EDIT_FILES = ("tmp/control.dat", "mri/aseg.manedit.mgz")
WM = "mri/wm.mgz"
NOT_CHECKED = "could not be read, so it was not checked for edits"
ERASED = 1  # recon-all 8 itself writes 255 into wm.mgz, so only erased voxels are evidence


def _voxels(path: Path) -> np.ndarray:
    return np.asarray(nib.load(path).dataobj)


def _exists(subject_dir: Path, rel: str) -> list[str]:
    return [f"{rel} exists"] if (subject_dir / rel).is_file() else []


def _count(subject_dir: Path, rel: str, count) -> int | str | None:
    """`count()` on a file that exists; a sentence when the file cannot be read."""
    if not (subject_dir / rel).is_file():
        return None
    try:
        return count()
    except Exception:
        return f"{rel} {NOT_CHECKED}"


def _voxel_evidence(found: int | str | None, sentence: str) -> list[str]:
    if isinstance(found, str):
        return [found]
    return [sentence.format(n=found, s="" if found == 1 else "s")] if found else []


def _changed_finalsurfs(subject_dir: Path) -> list[str]:
    def count() -> int:
        return int((_voxels(subject_dir / BFS) != _voxels(subject_dir / BFS_EDIT)).sum())

    found = _count(subject_dir, BFS_EDIT, count) if (subject_dir / BFS).is_file() else None
    return _voxel_evidence(found, f"{BFS_EDIT} differs from {BFS} in {{n}} voxel{{s}}")


def _erased_white_matter(subject_dir: Path) -> list[str]:
    found = _count(subject_dir, WM, lambda: int((_voxels(subject_dir / WM) == ERASED).sum()))
    return _voxel_evidence(found, f"{WM} has {{n}} voxel{{s}} erased by hand (value 1)")


def _edits_flag(subject_dir: Path) -> list[str]:
    evidence = []
    if any("--edits" in command.split() for command in all_commands(subject_dir, "fastsurfer")):
        evidence.append("scripts/deep-seg.log records a run with --edits")
    try:
        lines = (subject_dir / "scripts" / "recon-surf.log").read_text(errors="replace").splitlines()
    except OSError:
        lines = []
    if any("recon-surf.sh" in line and "--edits" in line.split() for line in lines):
        evidence.append("scripts/recon-surf.log records a run with --edits")
    return evidence


def _partial_reruns(subject_dir: Path) -> list[str]:
    later = all_commands(subject_dir, "freesurfer")[1:]
    # only the flags that rerun after an edit; a first run done in stages is not an edit
    flags = sorted({word for command in later for word in command.split()} & RERUN_FLAGS)
    return [f"scripts/recon-all.log records a later run with {' '.join(flags)}"] if flags else []


def _fastsurfer_evidence(subject_dir: Path) -> list[str]:
    return [*_edits_flag(subject_dir), *_exists(subject_dir, FASTSURFER_SEG_EDIT),
            *_changed_finalsurfs(subject_dir)]


def _recon_all_evidence(subject_dir: Path) -> list[str]:
    files = [line for rel in RECON_ALL_EDIT_FILES for line in _exists(subject_dir, rel)]
    return [*files, *_erased_white_matter(subject_dir), *_partial_reruns(subject_dir)]


def detect_edits(subject_dir: Path, pipeline: str) -> list[str]:
    """One sentence per sign that the subject was edited; empty when there is none."""
    subject_dir = Path(subject_dir)
    if pipeline == "fastsurfer":
        return _fastsurfer_evidence(subject_dir)
    return _recon_all_evidence(subject_dir) if pipeline == "freesurfer" else []


def edit_state(evidence: list[str]) -> bool | None:
    """Edited (True), not (False), or unknown (None) when a file could not be checked and
    nothing else shows an edit."""
    if any(not sentence.endswith(NOT_CHECKED) for sentence in evidence):
        return True
    return None if evidence else False
