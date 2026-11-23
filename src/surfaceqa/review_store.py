"""Review files: <qa>/ratings/<subject key>/<run>/<reviewer>.json."""

import json
import os
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from surfaceqa.reviews import stored_review

UNCHECKED = object()  # "do not compare with what is stored"
_LOCKS: defaultdict[Path, threading.Lock] = defaultdict(threading.Lock)
_LOCKS_GUARD = threading.Lock()


class Conflict(Exception):
    """The stored review is not the one the caller last saw: another window saved since."""


def _subject_folder(qa_dir: Path, key: str) -> Path:
    return Path(qa_dir) / "ratings" / key


def review_path(qa_dir: Path, key: str, run: str, reviewer: str) -> Path:
    return _subject_folder(qa_dir, key) / run / f"{reviewer}.json"


def _read(path: Path) -> dict | None:
    """The review in a file; None when it is absent, unreadable or not a valid review."""
    try:
        return stored_review(json.loads(path.read_text()))
    except (OSError, ValueError):
        return None


def load_review(qa_dir: Path, key: str, run: str, reviewer: str) -> dict | None:
    return _read(review_path(qa_dir, key, run, reviewer))


def _stamp(now: datetime | None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat()


def _write(path: Path, review: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(review, indent=1))
    os.replace(temporary, path)


def _lock_for(path: Path) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS[path]


def _store(qa_dir: Path, review: dict, now: datetime | None, submit: bool, expected) -> dict:
    """Read, decide and write one review file as a single step, so that saves which
    overlap cannot undo a submission or write over each other half way."""
    path = review_path(qa_dir, review["key"], review["run"], review["reviewer"])
    with _lock_for(path):
        stored = _read(path)
        if expected is not UNCHECKED and (stored["saved"] if stored else None) != expected:
            raise Conflict(path.name)
        stamp = _stamp(now)
        submitted = stored["submitted"] if stored else None
        review = {**review, "saved": stamp, "revised": submitted is not None,
                  "submitted": submitted or (stamp if submit else None)}
        _write(path, review)
    return review


def save_review(qa_dir: Path, review: dict, now: datetime | None = None,
                expected=UNCHECKED) -> dict:
    """Store a review; one that was already submitted stays submitted and is flagged revised.

    With `expected` (the `saved` time the caller last saw, None for "never saved"), the
    review is stored only if that is still what is on disk; otherwise Conflict.
    """
    return _store(qa_dir, review, now, False, expected)


def submit_review(qa_dir: Path, review: dict, now: datetime | None = None,
                  expected=UNCHECKED) -> dict:
    return _store(qa_dir, review, now, True, expected)


def _reviews_in(folder: Path) -> list[dict]:
    paths = sorted(folder.glob("*.json")) if folder.is_dir() else []
    return [review for review in map(_read, paths) if review is not None]


def list_reviews(qa_dir: Path, key: str, run: str) -> list[dict]:
    """Every valid review of this run, by reviewer name."""
    return _reviews_in(_subject_folder(qa_dir, key) / run)


def all_reviews(qa_dir: Path, key: str) -> list[dict]:
    """Every valid review of the subject, over all its runs, by run and reviewer."""
    folder = _subject_folder(qa_dir, key)
    runs = sorted(p for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []
    return [review for run in runs for review in _reviews_in(run)]


def earlier_reviews(qa_dir: Path, key: str, current_run: str, reviewer: str) -> list[dict]:
    """This reviewer's submitted reviews of the subject's other runs, newest first."""
    found = [review for review in all_reviews(qa_dir, key)
             if review["reviewer"] == reviewer and review["run"] != current_run]
    submitted = [review for review in found if review["submitted"]]
    return sorted(submitted, key=lambda review: review["submitted"], reverse=True)
