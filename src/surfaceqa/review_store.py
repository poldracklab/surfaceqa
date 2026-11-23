"""Review files: <qa>/ratings/<subject key>/<run>/<reviewer>.json."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = {"key", "run", "reviewer", "saved", "submitted", "items", "marks", "grade"}


def _subject_folder(qa_dir: Path, key: str) -> Path:
    return Path(qa_dir) / "ratings" / key


def review_path(qa_dir: Path, key: str, run: str, reviewer: str) -> Path:
    return _subject_folder(qa_dir, key) / run / f"{reviewer}.json"


def _read(path: Path) -> dict | None:
    try:
        review = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return review if _usable(review) else None


def _usable(review) -> bool:
    """A file with the shape of a review; anything else is ignored, never trusted."""
    if not isinstance(review, dict) or not REQUIRED <= set(review):
        return False
    return isinstance(review["items"], dict) and isinstance(review["marks"], list)


def load_review(qa_dir: Path, key: str, run: str, reviewer: str) -> dict | None:
    """The stored review, or None when there is none or the file cannot be read."""
    return _read(review_path(qa_dir, key, run, reviewer))


def _stamp(now: datetime | None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def _write(path: Path, review: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(review, indent=1))
    os.replace(temporary, path)


def _store(qa_dir: Path, review: dict, now: datetime | None, submit: bool) -> dict:
    stored = load_review(qa_dir, review["key"], review["run"], review["reviewer"])
    stamp = _stamp(now)
    submitted = stored["submitted"] if stored else None
    review = {**review, "saved": stamp, "revised": submitted is not None,
              "submitted": submitted or (stamp if submit else None)}
    _write(review_path(qa_dir, review["key"], review["run"], review["reviewer"]), review)
    return review


def save_review(qa_dir: Path, review: dict, now: datetime | None = None) -> dict:
    """Store a review; one that was already submitted stays submitted and is flagged revised."""
    return _store(qa_dir, review, now, submit=False)


def submit_review(qa_dir: Path, review: dict, now: datetime | None = None) -> dict:
    return _store(qa_dir, review, now, submit=True)


def _reviews_in(folder: Path) -> list[dict]:
    paths = sorted(folder.glob("*.json")) if folder.is_dir() else []
    return [review for review in map(_read, paths) if review is not None]


def list_reviews(qa_dir: Path, key: str, run: str) -> list[dict]:
    """Every readable review of this run, by reviewer name."""
    return _reviews_in(_subject_folder(qa_dir, key) / run)


def earlier_reviews(qa_dir: Path, key: str, current_run: str, reviewer: str) -> list[dict]:
    """This reviewer's submitted reviews of the subject's other runs, newest first."""
    folder = _subject_folder(qa_dir, key)
    runs = [p for p in folder.iterdir() if p.is_dir() and p.name != current_run] if folder.is_dir() else []
    found = [_read(run / f"{reviewer}.json") for run in runs]
    submitted = [review for review in found if review and review["submitted"]]
    return sorted(submitted, key=lambda review: review["submitted"], reverse=True)
