"""Reviews for tests: complete, submitted, with chosen ratings."""

from surfaceqa.protocol import PASS_ITEMS, item_ids
from surfaceqa.reviews import empty_review

MARK = {"region": "sinus", "kind": "pial_out", "grid": [16.0, 20.0, 30.0], "surface": "lh.pial",
        "finding": None, "note": "", "tkr": [0.0, 0.0, 6.0], "vertex": 5}


def make_review(reviewer: str, key: str = "fastsurfer__sub-01", run: str = "run1",
                grade: str | None = "B", submitted: bool = True, unratable: str | None = None,
                marks=(), **ratings) -> dict:
    """Every item at its lowest level unless named, e.g. make_review("ann", sinus="major")."""
    review = empty_review(key, run, reviewer)
    for item in item_ids():
        lowest = "ok" if item in PASS_ITEMS else "none"
        review["items"][item] = {"rating": ratings.get(item, lowest), "note": ""}
    stamp = f"2026-11-23T12:00:00+00:00"
    return {**review, "grade": grade, "marks": list(marks), "unratable": unratable,
            "saved": stamp, "submitted": stamp if submitted else None}
