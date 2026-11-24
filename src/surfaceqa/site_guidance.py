"""Which marked problems a viewer gets fix guidance for, and the guidance itself."""

from pathlib import Path

from surfaceqa.guidance import build_guidance
from surfaceqa.provenance import load_provenance
from surfaceqa.review_store import load_review
from surfaceqa.settings import rerun_template

NO_GUIDANCE = {"guidance": None, "guidance_from": None, "edited": None, "evidence": []}
UNSETTLED = ("unreviewed", "disagreement")


def _usable_final(fields: dict) -> dict | None:
    """Final labels the viewer may see, that are up to date and agreed."""
    final = fields["final"]
    if final is None or fields["final_stale"] or final["status"] in UNSETTLED:
        return None
    return final


def _major_marks(marks: list[dict], major: list[str]) -> list[dict]:
    return [mark for mark in marks if mark["region"] in major]


def _own_marks(qa_dir: Path, record: dict, reviewer: str | None) -> list[dict] | None:
    review = load_review(qa_dir, record["key"], record["run"], reviewer) if reviewer else None
    if review is None:
        return None
    major = [item for item, entry in review["items"].items() if entry.get("rating") == "major"]
    return _major_marks(review["marks"], major)


def _marks(qa_dir: Path, record: dict, view, fields: dict) -> tuple[list[dict], str | None]:
    """The marks to give guidance for and whose they are: the final labels' or the viewer's."""
    final = _usable_final(fields)
    if final is not None:
        return _major_marks(final["marks"], final["needs_fix"]), "final"
    own = _own_marks(qa_dir, record, view.reviewer)
    return (own, "own") if own is not None else ([], None)


def _shown_provenance(provenance: dict | None, fields: dict) -> dict | None:
    """The record of how the subject was made, without its edit state for a blind reviewer
    who has not submitted: knowing a subject was edited could colour the review."""
    if provenance is None or not fields["hide_indicators"]:
        return provenance
    return {**provenance, "edited": None, "evidence": []}


def guidance_fields(qa_dir: Path, record: dict, view, fields: dict) -> dict:
    """Fix guidance for one subject as `view.reviewer` may see it.

    `fields` are the subject's review fields, which already hold back the final labels
    from a reviewer who has not submitted.
    """
    if not record["has_run"]:
        return dict(NO_GUIDANCE)
    provenance = _shown_provenance(load_provenance(qa_dir, record["key"]), fields)
    marks, source = _marks(qa_dir, record, view, fields)
    guidance = build_guidance(record, provenance, marks, rerun_template(qa_dir, record["source"]))
    return {"guidance": guidance, "guidance_from": source,
            "edited": provenance["edited"] if provenance else None,
            "evidence": provenance["evidence"] if provenance else []}
