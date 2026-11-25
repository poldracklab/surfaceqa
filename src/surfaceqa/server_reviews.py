"""What the server does with a review that a browser sends."""

import re
from pathlib import Path

from surfaceqa.marks import locate_marks
from surfaceqa.queue import next_key, review_queue
from surfaceqa.review_store import Conflict, load_review, save_review, submit_review
from surfaceqa.reviews import ReviewError, clean_review, empty_review, missing_for_submit

REBUILT = ("This subject was rebuilt and its surfaces changed, so this review no longer "
           "applies. Reload the page to review the new surfaces.")


OTHER_WINDOW = ("This review was changed in another window after this page was opened. "
                "Reload the page to continue from the saved review.")
WRITER_ID = re.compile(r"[0-9A-Za-z-]{1,64}")  # the name a page gives itself when it opens
STAY_COMPLETE = "This review is submitted, so it has to stay complete. Not saved:"


class Refused(Exception):
    """A request the server will not carry out: an HTTP status and what to tell the reviewer.

    `saved` is the time of the draft that was stored anyway, when one was.
    """

    def __init__(self, status: int, detail, saved: str | None = None):
        super().__init__(str(detail))
        self.status, self.detail, self.saved = status, detail, saved

    def body(self) -> dict:
        return {"detail": self.detail, **({"saved": self.saved} if self.saved else {})}


def current_review(qa_dir: Path, record: dict, reviewer: str) -> dict:
    stored = load_review(qa_dir, record["key"], record["run"], reviewer)
    review = stored or empty_review(record["key"], record["run"], reviewer)
    return {"review": review, "missing": missing_for_submit(review)}


def _checked(record: dict, reviewer: str, payload) -> dict:
    """The review in the payload, if it is for this reviewer, this run, and valid."""
    if not isinstance(payload, dict):
        raise Refused(422, "the review must be an object")
    if payload.get("reviewer") != reviewer:
        opened_as = payload.get("reviewer") or "someone else"
        raise Refused(409, f"This page was opened as {opened_as}, but the reviewer name is now "
                           f"{reviewer}. Reload the page.")
    if payload.get("run") != record["run"]:
        raise Refused(409, REBUILT)
    try:
        return clean_review(payload, record["key"], record["run"], reviewer)
    except ReviewError as error:
        raise Refused(422, str(error)) from error


def _writer(payload: dict) -> dict | None:
    """Which page sent this and which of its saves it is; None from a page that does not say."""
    name, seq = payload.get("writer"), payload.get("seq")
    if name is None and seq is None:
        return None
    named = isinstance(name, str) and WRITER_ID.fullmatch(name) is not None
    if not named or type(seq) is not int or seq < 0:
        raise Refused(422, "writer and seq: the page must name itself and number its saves")
    return {"id": name, "seq": seq}


def store_review(qa_dir: Path, record: dict, reviewer: str, payload, submit: bool) -> dict:
    """Save what the browser sent and, when asked and complete, submit it: one write.

    The payload names the reviewer the page was opened as and the `saved` time it last
    saw; a page that is out of date in either respect is refused, not written.
    """
    review = _checked(record, reviewer, payload)
    writer = _writer(payload)
    stored = load_review(qa_dir, record["key"], record["run"], reviewer)
    missing = missing_for_submit(review)
    if missing and stored and stored["submitted"]:
        raise Refused(422, [STAY_COMPLETE, *missing])
    review = locate_marks(review, record, stored)
    store = submit_review if submit and not missing else save_review
    try:
        review = store(qa_dir, review, expected=payload.get("saved"), writer=writer)
    except Conflict:
        raise Refused(409, OTHER_WINDOW) from None
    if submit and missing:
        raise Refused(422, missing, saved=review["saved"])
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
