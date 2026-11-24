"""What the start page needs to know about folders: what is in them and where a build may go."""

import os
from pathlib import Path

from surfaceqa.discover import find_subjects, is_subject, source_root
from surfaceqa.settings import sources as recorded_sources

MAX_FOLDERS = 500
MOUNTS = ("/Volumes", "/mnt", "/media")
BUILD_FILES = ("build.lock", "build_status.json", "build.log")


def is_qa_dir(path: Path) -> bool:
    return (Path(path) / "subjects").is_dir()


def _is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _subfolders(path: Path) -> list[Path]:
    """The visible sub-folders of a folder, by name; none if it cannot be read."""
    try:
        found = [p for p in path.iterdir() if not p.name.startswith(".") and _is_dir(p)]
    except OSError:
        return []
    return sorted(found, key=lambda p: p.name.lower())


def _holds_subject(path: Path) -> bool:
    try:
        return is_subject(path)
    except OSError:
        return False


def describe(path: Path) -> dict:
    """A folder as the browser shows it: whether it is a subject, or how many it holds."""
    path = Path(path)
    subject = _holds_subject(path)
    n_subjects = 0 if subject else sum(_holds_subject(p) for p in _subfolders(path))
    return {"path": str(path), "name": path.name or str(path), "subject": subject, "n_subjects": n_subjects}


def _listing(path: Path, folders: list[dict], error: str | None = None, truncated: bool = False) -> dict:
    parent = None if path.parent == path else str(path.parent)
    return {"path": str(path), "parent": parent, "folders": folders, "error": error, "truncated": truncated}


def list_folders(path: Path) -> dict:
    """The sub-folders of a folder. File names are never part of the answer."""
    path = Path(path).expanduser()
    if not _is_dir(path):
        return _listing(path, [], "This is not a folder.")
    if not os.access(path, os.R_OK | os.X_OK):
        return _listing(path, [], "This folder cannot be read.")
    found = _subfolders(path)
    shown = [describe(p) for p in found[:MAX_FOLDERS]]
    return _listing(path, shown, truncated=len(found) > MAX_FOLDERS)


def places() -> list[dict]:
    """Where the folder browser can start: the home folder and the mounted disks."""
    mounted = [p for mount in MOUNTS for p in _subfolders(Path(mount))]
    return [{"path": str(Path.home()), "name": "Home"}, *({"path": str(p), "name": p.name} for p in mounted)]


def _usable(folder: Path) -> bool:
    """Whether a build could write to this folder, which may not exist yet."""
    if folder.exists():
        return folder.is_dir() and os.access(folder, os.W_OK | os.X_OK)
    return folder.parent != folder and _usable(folder.parent)


def _same_sources(folder: Path, sources: list[Path]) -> bool:
    return {str(p) for p in recorded_sources(folder)} == {str(Path(s).resolve()) for s in sources}


def _free(folder: Path, sources: list[Path]) -> bool:
    return not folder.exists() or _empty(folder) or (is_qa_dir(folder) and _same_sources(folder, sources))


def _in_home(name: str, sources: list[Path]) -> Path:
    base = Path.home() / "surfaceqa"
    names = (name if n == 1 else f"{name}-{n}" for n in range(1, 10_000))
    return next(base / candidate for candidate in names if _free(base / candidate, sources))


def default_out(sources: list[Path]) -> Path:
    """Where the QA directory goes unless the researcher says otherwise."""
    root = source_root(sources[0])
    beside = root.parent / "surfaceqa"
    if _usable(beside) and (is_qa_dir(beside) or not beside.exists() or _empty(beside)):
        return beside
    return _in_home(root.name, sources)


def _empty(folder: Path) -> bool:
    """Nothing in it but hidden files and what a build that never got going left behind."""
    try:
        return folder.is_dir() and all(p.name.startswith(".") or p.name in BUILD_FILES
                                       for p in folder.iterdir())
    except OSError:
        return False


def adds_to_existing(out: Path) -> bool:
    return is_qa_dir(out)


def _inside(path: Path, folders: list[Path]) -> bool:
    return any(path == folder or folder in path.parents for folder in folders)


def _source_problem(sources: list[Path]) -> str | None:
    if not sources:
        return "Choose a folder to inspect."
    for source in sources:
        if not _is_dir(Path(source)):
            return f"Not a folder: {source}"
        if not find_subjects([source]):
            return f"No subject found in {source} (a subject is a folder containing mri/ and surf/)."
    try:
        find_subjects(sources)
    except ValueError as error:
        return str(error)
    return None


def _out_problem(sources: list[Path], out: Path) -> str | None:
    out = Path(out).expanduser().resolve()
    if _inside(out, [source_root(source) for source in sources]):
        return f"{out} is inside a folder being inspected; nothing is written into the input data."
    if out.exists() and not out.is_dir():
        return f"{out} is not a folder."
    if not _usable(out):
        return f"{out} cannot be written."
    if out.exists() and not _empty(out) and not is_qa_dir(out):
        return f"{out} is not empty and is not a QA directory."
    return None


def check_request(sources: list[Path], out: Path) -> str | None:
    """Why this build cannot be started, or None when it can. Nothing is created."""
    sources = [Path(source).expanduser() for source in sources]
    return _source_problem(sources) or _out_problem(sources, out)


def plan(sources: list, out: str) -> dict:
    """What a build of these folders would do: where it goes, how many subjects, and why not
    if it cannot be started. An empty `out` means the default place."""
    sources = [Path(source).expanduser() for source in sources if str(source).strip()]
    problem = _source_problem(sources)
    if problem:
        return {"out": "", "error": problem, "adds": False, "n_subjects": 0}
    target = Path(out.strip()).expanduser() if out.strip() else default_out(sources)
    return {"out": str(target), "error": _out_problem(sources, target),
            "adds": adds_to_existing(target), "n_subjects": len(find_subjects(sources))}
