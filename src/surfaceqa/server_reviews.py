"""What the server does with a review that a browser sends."""

from pathlib import Path

from surfaceqa.marks import locate_marks
from surfaceqa.queue import next_key, review_queue
from surfaceqa.review_store import load_review, save_review, submit_review
from surfaceqa.reviews import ReviewError, clean_review, empty_review, missing_for_submit

REBUILT = ("This subject was rebuilt and its surfaces changed, so this review no longer "
           "applies. Reload the page to review the new surfaces.")


class Refused(Exception):
    """A request the server will not carry out: an HTTP status and what to tell the reviewer."""

    def __init__(self, status: int, detail):
        super().__init__(str(detail))
        self.status, self.detail = status, detail


def current_review(qa_dir: Path, record: dict, reviewer: str) -> dict:
    stored = load_review(qa_dir, record["key"], record["run"], reviewer)
    review = stored or empty_review(record["key"], record["run"], reviewer)
    return {"review": review, "missing": missing_for_submit(review)}


def store_review(qa_dir: Path, record: dict, reviewer: str, payload, submit: bool) -> dict:
    """Save what the browser sent as a draft and, when asked and complete, submit it."""
    if not isinstance(payload, dict):
        raise Refused(422, "the review must be an object")
    if payload.get("run") != record["run"]:
        raise Refused(409, REBUILT)
    try:
        review = clean_review(payload, record["key"], record["run"], reviewer)
    except ReviewError as error:
        raise Refused(422, str(error)) from error
    review = save_review(qa_dir, locate_marks(review, record))
    missing = missing_for_submit(review)
    if submit and missing:
        raise Refused(422, missing)
    if submit:
        review = submit_review(qa_dir, review)
    return {"review": review, "missing": missing}


def has_submitted(qa_dir: Path, record: dict, reviewer: str | None) -> bool:
    if reviewer is None or not record["has_run"]:
        return False
    review = load_review(qa_dir, record["key"], record["run"], reviewer)
    return review is not None and bool(review["submitted"])


def next_subject(records: list[dict], reviewer: str, blind: bool, after: str | None) -> str | None:
    """The key of the next subject in this reviewer's queue, or None when none is left."""
    reviewable = [record for record in records if record["has_run"]]
    states = {record["key"]: record["mine"] for record in reviewable}
    queue = review_queue([record["key"] for record in reviewable], states, reviewer, blind)
    return next_key(queue, after)
