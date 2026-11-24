"""Where things live inside a QA directory."""

import json
import os
from pathlib import Path


def subject_dir(qa_dir: Path, key: str) -> Path:
    return Path(qa_dir) / "subjects" / key


def current_run_dir(qa_dir: Path, key: str) -> Path | None:
    """The folder of the subject's current run, or None if it has none."""
    folder = subject_dir(qa_dir, key)
    try:
        run = json.loads((folder / "current.json").read_text())["run"]
    except (OSError, KeyError, ValueError):
        return None
    return folder / "runs" / run


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
