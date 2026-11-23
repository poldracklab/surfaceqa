"""What a review is: its shape, what a browser may send, and what submitting requires."""

import math
import re

from surfaceqa.contours import SURFACE_ORDER
from surfaceqa.protocol import PASS_ITEMS, item_ids, load_protocol, scale_for
from surfaceqa.regions import REGIONS

RESERVED = "consensus"  # the joint review that settles a disagreement
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}")
MAX_NOTE = 2000
MAX_MARKS = 200
PASS_TITLES = {"birdseye": "Bird's-eye view", "t1": "T1 quality"}


class ReviewError(ValueError):
    """A review payload that cannot be accepted; the message names the field."""


def valid_reviewer(name: str) -> bool:
    return isinstance(name, str) and NAME.fullmatch(name) is not None


def item_title(item_id: str) -> str:
    titles = {**PASS_TITLES, **{region.id: region.title for region in REGIONS}}
    return titles[item_id]


def empty_review(key: str, run: str, reviewer: str) -> dict:
    return {"protocol": load_protocol()["version"], "key": key, "run": run, "reviewer": reviewer,
            "saved": None, "submitted": None, "revised": False, "skipped": False,
            "unratable": None,
            "items": {item: {"rating": None, "note": ""} for item in item_ids()},
            "marks": [], "grade": None, "notes": ""}


def _text(value, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > MAX_NOTE:
        raise ReviewError(f"{field}: the note must be text of at most {MAX_NOTE} characters")
    return value


def _choice(value, allowed, field: str):
    if value is not None and (not isinstance(value, str) or value not in allowed):
        raise ReviewError(f"{field}: {value!r} is not one of {', '.join(allowed)}")
    return value


def _item(item_id: str, sent, protocol: dict) -> dict:
    if not isinstance(sent, dict):
        raise ReviewError(f"items: {item_id} must be an object")
    rating = _choice(sent.get("rating"), scale_for(item_id, protocol), f"items: {item_id} rating")
    return {"rating": rating, "note": _text(sent.get("note"), f"items: {item_id}")}


def _items(sent, protocol: dict) -> dict:
    if not isinstance(sent, dict):
        raise ReviewError("items: must be an object")
    unknown = [item for item in sent if item not in item_ids()]
    if unknown:
        raise ReviewError(f"items: unknown item {unknown[0]!r}")
    return {item: _item(item, sent.get(item, {}), protocol) for item in item_ids()}


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _grid(value) -> list[float]:
    if not isinstance(value, list) or len(value) != 3 or not all(_number(v) for v in value):
        raise ReviewError("marks: grid must be three finite numbers")
    return [float(v) for v in value]


def _finding(value):
    if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
        raise ReviewError("marks: finding must be a finding number")
    return value


def _mark(sent, protocol: dict) -> dict:
    if not isinstance(sent, dict):
        raise ReviewError("marks: each mark must be an object")
    kinds = [kind["id"] for kind in protocol["mark_kinds"]]
    regions = [region.id for region in REGIONS]
    if sent.get("region") is None or sent.get("kind") is None:
        raise ReviewError("marks: a mark needs a region and a kind")
    return {"region": _choice(sent.get("region"), regions, "marks: region"),
            "kind": _choice(sent.get("kind"), kinds, "marks: kind"),
            "grid": _grid(sent.get("grid")),
            "surface": _choice(sent.get("surface"), SURFACE_ORDER, "marks: surface"),
            "finding": _finding(sent.get("finding")),
            "note": _text(sent.get("note"), "marks: note")}


def _marks(sent, protocol: dict) -> list[dict]:
    if not isinstance(sent, list) or len(sent) > MAX_MARKS:
        raise ReviewError(f"marks: must be a list of at most {MAX_MARKS} marks")
    return [_mark(mark, protocol) for mark in sent]


def clean_review(payload: dict, key: str, run: str, reviewer: str) -> dict:
    """The review a browser sent, holding only known fields; ReviewError names a bad one."""
    if not isinstance(payload, dict):
        raise ReviewError("the review must be an object")
    protocol = load_protocol()
    reason = _text(payload.get("unratable"), "unratable reason").strip()
    return {**empty_review(key, run, reviewer),
            "skipped": payload.get("skipped") is True,
            "unratable": reason or None,
            "items": _items(payload.get("items", {}), protocol),
            "marks": _marks(payload.get("marks", []), protocol),
            "grade": _choice(payload.get("grade"), protocol["grades"], "grade"),
            "notes": _text(payload.get("notes"), "notes")}


def _unmarked_major(review: dict) -> list[str]:
    marked = {mark["region"] for mark in review["marks"]}
    return [item for item, entry in review["items"].items()
            if item not in PASS_ITEMS and entry["rating"] == "major" and item not in marked]


def missing_for_submit(review: dict) -> list[str]:
    """What still has to be done before this review can be submitted; empty when nothing."""
    if (review.get("unratable") or "").strip():
        return []
    lines = [f"{item_title(item)}: not rated" for item, entry in review["items"].items()
             if entry["rating"] is None]
    if review["grade"] is None:
        lines.append("Overall grade: not chosen")
    lines += [f"{item_title(item)}: rated major, so mark at least one problem there"
              for item in _unmarked_major(review)]
    return lines
