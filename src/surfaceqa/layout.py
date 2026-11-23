"""Where things live inside a QA directory."""

import json
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
