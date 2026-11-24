"""Combine the reviewers' submitted reviews of one run into final labels.

Rule (from surfcensus, as adopted in the design): where the reviewers are within one step
on an item the final label is the lower one; two or more steps apart, or disagreement on
whether the subject can be rated at all, is settled by the reviewers together. They record
that as one review under the name "consensus", which then stands alone.
"""

from surfaceqa.protocol import PASS_ITEMS, item_ids, load_protocol, scale_for
from surfaceqa.reviews import RESERVED

ITEM_REACH = 1  # steps on a rating scale that still count as agreement
GRADE_REACH = 3  # steps on the grade scale: one letter


def _counted(reviews: list[dict]) -> list[dict]:
    submitted = sorted((r for r in reviews if r.get("submitted")), key=lambda r: r["reviewer"])
    settled = [r for r in submitted if r["reviewer"] == RESERVED]
    return settled or submitted


def _lowest_within(values: dict[str, str], scale: list[str], reach: int) -> dict:
    """Final value and whether the reviewers disagree, given each reviewer's value."""
    positions = [scale.index(value) for value in values.values()]
    if not positions:
        return {"final": None, "disagree": False}
    if max(positions) - min(positions) > reach:
        return {"final": None, "disagree": True}
    return {"final": scale[min(positions)], "disagree": False}


def _item(item: str, raters: list[dict], protocol: dict) -> dict:
    ratings = {r["reviewer"]: r["items"][item]["rating"] for r in raters
               if r["items"][item]["rating"] is not None}
    return {**_lowest_within(ratings, scale_for(item, protocol), ITEM_REACH), "ratings": ratings}


def _grade(raters: list[dict], protocol: dict) -> dict:
    grades = {r["reviewer"]: r["grade"] for r in raters if r["grade"] is not None}
    result = _lowest_within(grades, protocol["grades"], GRADE_REACH)
    return {"final": result["final"], "grades": grades, "disagree": result["disagree"]}


def _status(counted: list[dict], disagreements: list[str]) -> str:
    if not counted:
        return "unreviewed"
    if counted[0]["reviewer"] == RESERVED:
        return "settled"
    if disagreements:
        return "disagreement"
    return "single" if len(counted) == 1 else "agreed"


def _needs_fix(items: dict) -> list[str]:
    return [item for item, entry in items.items()
            if item not in PASS_ITEMS and entry["final"] == "major"]


def combine(reviews: list[dict]) -> dict:
    protocol = load_protocol()
    counted = _counted(reviews)
    raters = [r for r in counted if not r.get("unratable")]
    split = 0 < len(raters) < len(counted)  # some say it cannot be rated, some rated it
    items = {item: _item(item, raters, protocol) for item in item_ids()}
    grade = _grade(raters, protocol)
    disagreements = [item for item, entry in items.items() if entry["disagree"]]
    disagreements += ["grade"] * grade["disagree"] + ["unratable"] * split
    return {"status": _status(counted, disagreements),
            "reviewers": [r["reviewer"] for r in counted],
            "inputs": {r["reviewer"]: r["saved"] for r in counted},
            "unratable": bool(counted) and not raters,
            "items": items, "grade": grade,
            "marks": [{**mark, "reviewer": r["reviewer"]} for r in raters for mark in r["marks"]],
            "needs_fix": _needs_fix(items), "disagreements": disagreements}
