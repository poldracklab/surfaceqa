"""Write the final labels of every subject: <qa>/final/<subject key>.json."""

import json
from pathlib import Path

from surfaceqa.consensus import combine
from surfaceqa.layout import current_run_dir, read_json
from surfaceqa.review_store import list_reviews


def _keys_with_a_run(qa_dir: Path) -> list[tuple[str, str]]:
    root = Path(qa_dir) / "subjects"
    folders = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    runs = [(folder.name, current_run_dir(qa_dir, folder.name)) for folder in folders]
    return [(key, run_dir.name) for key, run_dir in runs if run_dir is not None]


def finalize(qa_dir: Path) -> list[dict]:
    """Combine the reviews of each subject's current run and store the result."""
    folder = Path(qa_dir) / "final"
    folder.mkdir(exist_ok=True)
    records = []
    for key, run in _keys_with_a_run(qa_dir):
        record = {"key": key, "run": run, **combine(list_reviews(qa_dir, key, run))}
        (folder / f"{key}.json").write_text(json.dumps(record, indent=1))
        records.append(record)
    return records


def load_final(qa_dir: Path, key: str) -> dict | None:
    final = read_json(Path(qa_dir) / "final" / f"{key}.json")
    return final if isinstance(final, dict) and "status" in final else None


def is_stale(final: dict, reviews: list[dict], run: str) -> bool:
    """True when the surfaces or the submitted reviews changed after finalize ran."""
    return final["run"] != run or final["inputs"] != combine(reviews)["inputs"]
