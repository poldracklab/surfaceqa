"""Counts for the report: how ratings, marked problems and indicator findings are spread
over the subjects and regions.

Every function takes subject facts, one dict per subject:
`{"key", "source", "name", "href", "edited", "final", "drafts", "findings"}`, where `final`
is the subject's reviews combined (`consensus.combine`; None without a run) and `findings`
is what the indicators wrote (None when they did not).

Nothing here turns "not recorded" into "no error": subjects that were not reviewed, could
not be rated, are in disagreement or have no indicator results keep their own category.
"""

from collections import Counter
from statistics import median

from surfaceqa.checklist import HINT_KIND, scored_findings
from surfaceqa.findings import KINDS
from surfaceqa.protocol import PASS_ITEMS, item_ids, load_protocol, scale_for
from surfaceqa.reviews import item_title

DISAGREEMENT, UNREVIEWED, UNRATABLE = "disagreement", "unreviewed", "unratable"
NOT_GRADED = "not graded"
FINDING_KINDS = tuple(kind for kind in KINDS if kind != HINT_KIND)
REGION_LEVELS = ("none", "minor", "major")


def _regions() -> list[str]:
    return [item for item in item_ids() if item not in PASS_ITEMS]


def state(fact: dict) -> str:
    """reviewed, disagreement, unratable or unreviewed: exactly one for every subject."""
    final = fact["final"]
    if final is None or final["status"] == UNREVIEWED:
        return UNREVIEWED
    if final["unratable"]:
        return UNRATABLE
    return DISAGREEMENT if final["status"] == DISAGREEMENT else "reviewed"


def _torn(fact: dict) -> bool:
    """The reviewers disagree on whether the subject can be rated at all. Until they settle
    it, nothing one of them recorded is final: no rating, no grade, no marks."""
    return fact["final"] is not None and UNRATABLE in fact["final"]["disagreements"]


def _rated(facts: list[dict]) -> list[dict]:
    """Subjects with ratings: reviewed, or in disagreement on some items."""
    return [fact for fact in facts if state(fact) in ("reviewed", DISAGREEMENT)]


def progress(facts: list[dict]) -> dict:
    states = Counter(state(fact) for fact in facts)
    return {"subjects": len(facts), "reviewed": states["reviewed"],
            "disagreement": states[DISAGREEMENT], "unratable": states[UNRATABLE],
            "unreviewed": states[UNREVIEWED], "drafts": sum(fact["drafts"] for fact in facts)}


def _grade(fact: dict) -> str:
    grade = fact["final"]["grade"]
    disputed = grade["disagree"] or _torn(fact)
    return DISAGREEMENT if disputed else (grade["final"] or NOT_GRADED)


def grade_counts(facts: list[dict]) -> list[tuple[str, int]]:
    """Every grade in order with the number of rated subjects that got it."""
    counts = Counter(_grade(fact) for fact in _rated(facts))
    return [(grade, counts[grade]) for grade in (*load_protocol()["grades"], DISAGREEMENT, NOT_GRADED)]


def _level(fact: dict, item: str) -> str:
    """The subject's final rating of an item, or why it has none."""
    current = state(fact)
    if current in (UNREVIEWED, UNRATABLE):
        return current
    if _torn(fact):
        return DISAGREEMENT
    entry = fact["final"]["items"][item]
    return entry["final"] or (DISAGREEMENT if entry["disagree"] else UNREVIEWED)


def region_ratings(facts: list[dict]) -> list[dict]:
    """Per checklist item, how many subjects have each rating; unratable subjects are left out."""
    protocol = load_protocol()
    ratable = [fact for fact in facts if state(fact) != UNRATABLE]
    rows = []
    for item in item_ids():
        counts = Counter(_level(fact, item) for fact in ratable)
        levels = (*scale_for(item, protocol), DISAGREEMENT, UNREVIEWED)
        rows.append({"item": item, "title": item_title(item),
                     "counts": {level: counts[level] for level in levels}})
    return rows


def _marks(fact: dict) -> list[dict]:
    counted = state(fact) in ("reviewed", DISAGREEMENT) and not _torn(fact)
    return fact["final"]["marks"] if counted else []


def _problem_cell(facts: list[dict], region: str, kind: str) -> dict:
    per_subject = [sum(1 for mark in _marks(fact) if mark["region"] == region and mark["kind"] == kind)
                   for fact in facts]
    return {"subjects": sum(1 for n in per_subject if n), "marks": sum(per_subject)}


def problem_kinds(facts: list[dict]) -> list[dict]:
    """Per region and kind of problem: subjects with such a mark, and marks."""
    kinds = [kind["id"] for kind in load_protocol()["mark_kinds"]]
    return [{"region": region, "title": item_title(region),
             "cells": {kind: _problem_cell(facts, region, kind) for kind in kinds}}
            for region in _regions()]


def _severity(row: dict) -> tuple:
    """Sort key: rated subjects by how much is wrong, then unratable, then unreviewed."""
    protocol = load_protocol()
    steps = [scale_for(item, protocol).index(level) for item, level in row["cells"].items()
             if level in scale_for(item, protocol)]
    rank = {UNRATABLE: 1, UNREVIEWED: 2}.get(row["status"], 0)
    return (rank, -steps.count(2), -steps.count(1), row["name"])


def _grid_row(fact: dict) -> dict:
    current = state(fact)
    rated = current in ("reviewed", DISAGREEMENT)
    return {"key": fact["key"], "name": fact["name"], "href": fact["href"], "edited": fact["edited"],
            "status": current, "grade": _grade(fact) if rated else None, "marks": len(_marks(fact)),
            "cells": {item: _level(fact, item) for item in item_ids()}}


def subject_grid(facts: list[dict]) -> list[dict]:
    """One row per subject with its rating of every item, the worst subjects first."""
    return sorted((_grid_row(fact) for fact in facts), key=_severity)


# ---- indicators -------------------------------------------------------------------------------

def _scored(fact: dict) -> list[dict]:
    """The subject's findings that count as possible errors, not the places to look."""
    return scored_findings(fact["findings"])


def _listed(facts: list[dict]) -> list[dict]:
    """Subjects with an indicator record, whether or not any indicator could run."""
    return [fact for fact in facts if fact["findings"] is not None]


def _computed(facts: list[dict]) -> list[dict]:
    """Subjects on which at least one indicator ran. Only these can be said to have, or not
    to have, a finding: where nothing ran, "no finding" would mean "not looked at"."""
    return [fact for fact in _listed(facts)
            if any(entry["status"] == "ran" for entry in fact["findings"]["indicators"])]


def not_computed(facts: list[dict]) -> int:
    """Subjects that were built but on which no indicator ran (they failed, or lacked their files)."""
    computed = {fact["key"] for fact in _computed(facts)}
    return sum(1 for fact in facts if fact["final"] is not None and fact["key"] not in computed)


def _indicator_row(name: str, facts: list[dict]) -> dict:
    listed = [(fact, entry) for fact in facts for entry in fact["findings"]["indicators"]
              if entry["name"] == name]
    counts = [sum(1 for f in _scored(fact) if f["indicator"] == name)
              for fact, entry in listed if entry["status"] == "ran"]
    return {"name": name, "ran": len(counts), "not_run": len(listed) - len(counts),
            "with_findings": sum(1 for n in counts if n),
            "median": float(median(counts)) if counts else 0.0, "largest": max(counts, default=0)}


def indicator_summary(facts: list[dict]) -> list[dict]:
    """Per indicator: on how many subjects it ran, and how many findings it gave."""
    listed = _listed(facts)
    names = dict.fromkeys(entry["name"] for fact in listed for entry in fact["findings"]["indicators"])
    return [_indicator_row(name, listed) for name in names]


def finding_kinds(facts: list[dict]) -> list[dict]:
    """Per region and kind of finding: subjects with at least one."""
    computed = _computed(facts)
    seen = [{(f["region"], f["kind"]) for f in _scored(fact)} for fact in computed]
    return [{"region": region, "title": item_title(region),
             "cells": {kind: sum(1 for pairs in seen if (region, kind) in pairs)
                       for kind in FINDING_KINDS}}
            for region in _regions()]


def _agreement_row(region: str, facts: list[dict]) -> dict:
    fired, quiet = Counter(), Counter()
    for fact in facts:
        level = _level(fact, region)
        if level in REGION_LEVELS:
            has_finding = any(f["region"] == region for f in _scored(fact))
            (fired if has_finding else quiet)[level] += 1
    return {"region": region, "title": item_title(region),
            "fired": {level: fired[level] for level in REGION_LEVELS},
            "quiet": {level: quiet[level] for level in REGION_LEVELS}}


def agreement(facts: list[dict]) -> list[dict]:
    """Per region, among subjects with both a final rating and indicator results: how the
    rating falls where an indicator had a finding there, and where none had."""
    computed = _computed(facts)
    return [_agreement_row(region, computed) for region in _regions()]
