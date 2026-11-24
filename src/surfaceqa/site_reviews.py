"""What the pages show about reviews, and what one reviewer is allowed to see."""

from pathlib import Path

from surfaceqa.finalize import is_stale, load_final
from surfaceqa.protocol import item_ids, load_protocol
from surfaceqa.regions import REGIONS
from surfaceqa.review_store import earlier_reviews, list_reviews, load_review
from surfaceqa.reviews import RESERVED, empty_review, item_title, missing_for_submit

STATE_LABEL = {"none": "not started", "draft": "draft", "skipped": "skipped",
               "submitted": "submitted"}
NO_REVIEW = {"reviewers": [], "mine": "none", "mine_label": "", "final": None,
             "final_stale": False, "final_cell": "", "needs_fix_n": None, "earlier": [],
             "others": [], "show_others": False, "hide_indicators": False, "comparison": None,
             "review_data": None, "review_label": "Not yet reviewed"}


def _labels() -> dict[str, str]:
    protocol = load_protocol()
    levels = protocol["region_scale"] + protocol["pass_scale"]
    return {level["id"]: level["label"] for level in levels}


def _state(review: dict | None) -> str:
    if review is None:
        return "none"
    if review["submitted"]:
        return "submitted"
    return "skipped" if review.get("skipped") else "draft"


def _cell(review: dict, item: str) -> dict:
    entry = review["items"].get(item, {})
    return {"label": _labels().get(entry.get("rating"), ""), "note": entry.get("note", "")}


def _mark_rows(reviews: list[dict]) -> list[dict]:
    titles = {region.id: region.title for region in REGIONS}
    kinds = {kind["id"]: kind["label"] for kind in load_protocol()["mark_kinds"]}
    return [{"reviewer": review["reviewer"], "region": titles.get(mark["region"], mark["region"]),
             "kind": kinds.get(mark["kind"], mark["kind"]), "note": mark.get("note", "")}
            for review in reviews for mark in review["marks"]]


def _review_rows(review: dict) -> list[dict]:
    return [{"title": item_title(item), **_cell(review, item)} for item in item_ids()]


def _comparison(submitted: list[dict], final: dict | None) -> dict | None:
    """Every reviewer's ratings side by side, with the final label when there is one."""
    if not submitted:
        return None
    labels = _labels()
    rows = [{"title": item_title(item), "cells": [_cell(review, item) for review in submitted],
             "final": labels.get(final["items"][item]["final"], "") if final else ""}
            for item in item_ids()]
    grades = {"title": "Overall grade", "final": (final["grade"]["final"] or "") if final else "",
              "cells": [{"label": review["grade"] or "", "note": review.get("notes", "")}
                        for review in submitted]}
    unratable = [f"{review['reviewer']}: cannot be rated ({review['unratable']})"
                 for review in submitted if review.get("unratable")]
    return {"reviewers": [review["reviewer"] for review in submitted], "rows": rows + [grades],
            "marks": _mark_rows(submitted), "has_final": final is not None,
            "unratable": unratable}


def _final_cell(final: dict | None, stale: bool) -> str:
    if final is None or final["status"] == "unreviewed":
        return ""
    if stale:
        return "run surfaceqa finalize again"
    if final["status"] == "disagreement":
        return "disagreement"
    return "unratable" if final["unratable"] else (final["grade"]["final"] or "")


def _review_label(reviewers: list[str], final: dict | None) -> str:
    if not reviewers:
        return "Not yet reviewed"
    disputed = final is not None and final["status"] == "disagreement"
    return f"Reviewed by {', '.join(reviewers)}" + (" · in disagreement" if disputed else "")


def _earlier(qa_dir: Path, key: str, run: str, reviewer: str | None) -> list[dict]:
    reviews = earlier_reviews(qa_dir, key, run, reviewer) if reviewer else []
    return [{"run": review["run"], "submitted": review["submitted"], "grade": review["grade"],
             "rows": _review_rows(review)} for review in reviews]


def _review_data(key: str, run: str, reviewer: str, review: dict | None) -> dict:
    review = review or empty_review(key, run, reviewer)
    return {"protocol": load_protocol(), "review": review, "key": key, "run": run,
            "missing": missing_for_submit(review)}


def review_fields(qa_dir: Path, record: dict, view) -> dict:
    """The review state of one subject as `view.reviewer` may see it.

    A named reviewer gets other reviewers' ratings and the final labels only after
    submitting their own review of the subject. Without a name the pages are an overview
    that shows everything, except in blind mode.
    """
    if not record["has_run"]:
        return dict(NO_REVIEW)
    key, run, reviewer = record["key"], record["run"], view.reviewer
    submitted = [review for review in list_reviews(qa_dir, key, run) if review["submitted"]]
    mine = load_review(qa_dir, key, run, reviewer) if reviewer else None
    state = _state(mine)
    # the joint "consensus" review is written with the reviews it settles in view
    show = state == "submitted" or reviewer == RESERVED or (reviewer is None and not view.blind)
    final = load_final(qa_dir, key) if show else None
    stale = final is not None and is_stale(final, submitted, run)
    current = final if final is not None and not stale and final["status"] != "unreviewed" else None
    reviewers = [review["reviewer"] for review in submitted]
    return {
        "reviewers": reviewers, "mine": state, "mine_label": STATE_LABEL[state],
        "final": final, "final_stale": stale, "final_cell": _final_cell(final, stale),
        "needs_fix_n": len(current["needs_fix"]) if current else None,
        "earlier": _earlier(qa_dir, key, run, reviewer),
        "others": [r for r in submitted if r["reviewer"] != reviewer] if show else [],
        "show_others": show, "hide_indicators": view.blind and state != "submitted",
        "comparison": _comparison(submitted, current) if show else None,
        "review_data": _review_data(key, run, reviewer, mine) if view.serving and reviewer else None,
        "review_label": _review_label(reviewers, current),
    }
