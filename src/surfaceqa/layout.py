"""Where things live inside a QA directory."""

import json
import os
import re
from pathlib import Path

RUN_NAME = re.compile(r"[0-9a-f]{12}")


def subject_dir(qa_dir: Path, key: str) -> Path:
    return Path(qa_dir) / "subjects" / key


def current_run_dir(qa_dir: Path, key: str) -> Path | None:
    """The folder of the subject's current run, or None if it has none."""
    folder = subject_dir(qa_dir, key)
    try:
        run = json.loads((folder / "current.json").read_text())["run"]
    except (OSError, KeyError, TypeError, ValueError):
        return None
    return folder / "runs" / run if is_run_name(run) else None


def is_run_name(value) -> bool:
    return isinstance(value, str) and RUN_NAME.fullmatch(value) is not None


def plain_name(value) -> bool:
    """A single file or folder name: text that cannot lead out of the folder it is used in."""
    return (isinstance(value, str) and value not in ("", ".", "..")
            and not any(char in value for char in "/\\\0"))


def subject_folders(qa_dir: Path) -> list[Path]:
    """The subject folders of a QA directory, by name. A link is not one: it may lead anywhere."""
    root = Path(qa_dir) / "subjects"
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.is_symlink())


def run_meta(run_dir: Path) -> dict | None:
    """meta.json of a run folder, or None when the folder or the names in it cannot be trusted.

    A QA directory may have been built by someone else, and what its files say ends up in
    paths. The run is the folder's name whatever the file says, a link is not read, and
    neither is a file whose source or subject name is not a plain name.
    """
    run_dir = Path(run_dir)
    if run_dir.is_symlink() or run_dir.parent.is_symlink() or not is_run_name(run_dir.name):
        return None
    meta = read_json(run_dir / "meta.json")
    if not isinstance(meta, dict) or not (plain_name(meta.get("source")) and plain_name(meta.get("name"))):
        return None
    return {**meta, "run": run_dir.name}


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def replace_file(path: Path, write, mode: str = "w") -> None:
    """Write a file whole: a reader, or a build that is stopped, never leaves half of it."""
    partial = path.with_name(f".{path.name}.{os.getpid()}.partial")
    try:
        with open(partial, mode, **({} if "b" in mode else {"newline": ""})) as handle:
            write(handle)
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)


def replace_text(path: Path, text: str) -> None:
    replace_file(path, lambda handle: handle.write(text))


def file_signature(root: Path, rels) -> dict[str, list[int]]:
    """Size and modification time of each of these files that exists, to detect changes."""
    signature = {}
    for rel in rels:
        path = Path(root) / rel
        if path.is_file():
            stat = path.stat()
            signature[rel] = [stat.st_size, stat.st_mtime_ns]
    return signature
