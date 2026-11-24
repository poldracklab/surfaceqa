"""How far a build has got, kept in the QA directory for whoever is watching."""

import json
from pathlib import Path

from surfaceqa.layout import read_json, replace_text, subject_dir

STATUS_FILE = "build_status.json"


def write(qa_dir: Path, **fields) -> None:
    Path(qa_dir).mkdir(parents=True, exist_ok=True)
    replace_text(Path(qa_dir) / STATUS_FILE, json.dumps(fields))


def read(qa_dir: Path) -> dict | None:
    stored = read_json(Path(qa_dir) / STATUS_FILE)
    return stored if isinstance(stored, dict) else None


def _last_line(path: Path) -> str:
    try:
        lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    except OSError:
        lines = []
    return lines[-1] if lines else "the build failed"


def _problem(qa_dir: Path, result) -> dict:
    if result.status == "missing":
        reason = f"missing: {', '.join(result.missing)}"
    else:
        reason = _last_line(subject_dir(qa_dir, result.key) / "error.txt")
    return {"key": result.key, "status": result.status, "reason": reason}


def problems(qa_dir: Path, results: list) -> list[dict]:
    """The subjects that could not be built, each with one line saying why."""
    return [_problem(qa_dir, r) for r in results if r.status in ("failed", "missing")]


def cohort_failed(qa_dir: Path) -> bool:
    return (Path(qa_dir) / "cohort" / "error.txt").is_file()
