"""Detect which pipeline made a subject folder and locate the files we read."""

import re
from dataclasses import dataclass
from pathlib import Path

VERSION = re.compile(r"\d+\.\d+\.\d+")
SURFACE_CANDIDATES = {
    "lh.pial": ("lh.pial", "lh.pial.T1"),
    "rh.pial": ("rh.pial", "rh.pial.T1"),
    "lh.white": ("lh.white",),
    "rh.white": ("rh.white",),
}
T1 = "mri/orig.mgz"
HEMIS = ("lh", "rh")


@dataclass(frozen=True)
class PipelineInfo:
    name: str
    version: str | None


@dataclass(frozen=True)
class SubjectFiles:
    t1: Path | None
    surfaces: dict[str, Path]
    missing: list[str]


def _lines(path: Path) -> list[str]:
    try:
        return path.read_text(errors="replace").splitlines()
    except OSError:
        return []


def _version_in(text: str | None) -> str | None:
    found = VERSION.search(text or "")
    return found.group(0) if found else None


def _fastsurfer_version(scripts: Path) -> str | None:
    for line in _lines(scripts / "deep-seg.log"):
        if line.startswith("Version:"):
            return _version_in(line)
    stamp = _lines(scripts / "build-stamp.txt")
    return _version_in(stamp[1]) if len(stamp) > 1 else None


def _freesurfer_version(scripts: Path) -> str | None:
    stamp = _lines(scripts / "build-stamp.txt")
    return _version_in(stamp[0]) if stamp else None


def detect_pipeline(subject_dir: Path) -> PipelineInfo:
    scripts = Path(subject_dir) / "scripts"
    if (scripts / "deep-seg.log").is_file() or (scripts / "recon-surf.log").is_file():
        return PipelineInfo("fastsurfer", _fastsurfer_version(scripts))
    if (scripts / "recon-all.log").is_file() or (scripts / "build-stamp.txt").is_file():
        return PipelineInfo("freesurfer", _freesurfer_version(scripts))
    return PipelineInfo("unknown", None)


def _first_file(folder: Path, names: tuple[str, ...]) -> Path | None:
    return next((folder / n for n in names if (folder / n).is_file()), None)


def subject_files(subject_dir: Path) -> SubjectFiles:
    subject_dir = Path(subject_dir)
    t1 = subject_dir / T1
    missing = [] if t1.is_file() else [T1]
    surfaces = {}
    for role, names in SURFACE_CANDIDATES.items():
        found = _first_file(subject_dir / "surf", names)
        if found is None:
            missing.append(f"surf/{role}")
        else:
            surfaces[role] = found
    return SubjectFiles(t1 if t1.is_file() else None, surfaces, sorted(missing))
