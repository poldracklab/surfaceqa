"""Counts for the report, from what is known about each subject."""

import pytest

from surfaceqa.consensus import combine
from surfaceqa.protocol import item_ids, load_protocol
from surfaceqa.summary import (agreement, finding_kinds, grade_counts, indicator_summary,
                               not_computed, problem_kinds, progress, region_ratings, subject_grid)
from tests.reviewing import MARK, make_review

REGIONS = [item for item in item_ids() if item not in ("birdseye", "t1")]


def mark(region="sinus", kind="pial_out"):
    return {**MARK, "region": region, "kind": kind}


def found(*findings, not_run=()):
    """Indicator results: findings as (indicator, kind, region); every named indicator ran."""
    names = sorted({f[0] for f in findings} | {"ribbon_outside_brain", "thick_patches"})
    listed = [{"name": name, "status": "ran", "reason": ""} for name in names if name not in not_run]
    listed += [{"name": name, "status": "not run", "reason": "no file"} for name in not_run]
    return {"indicators": listed,
            "findings": [{"indicator": i, "kind": k, "region": r} for i, k, r in findings]}


def fact(name, *reviews, findings=None, has_run=True, edited=False, source="fs"):
    return {"key": f"{source}__{name}", "source": source, "name": name,
            "href": f"../subjects/{source}__{name}/index.html", "edited": edited,
            "final": combine(list(reviews)) if has_run else None,
            "drafts": sum(1 for r in reviews if not r["submitted"]), "findings": findings}


@pytest.fixture
def cohort():
    """clean: all none. bad: sinus major (two pial marks), orbitofrontal minor (one missed-gray
    mark). split: two reviewers two steps apart on the cerebellum and on the grade.
    gone: cannot be rated. draft: a draft only. new: nothing."""
    bad = make_review("ann", grade="C", sinus="major", orbitofrontal="minor",
                      marks=[mark(), mark(), mark("orbitofrontal", "gray_missed")])
    return [
        fact("clean", make_review("ann", grade="A")),
        fact("bad", bad),
        fact("split", make_review("ann", grade="A", cerebellum="none", sinus="minor"),
             make_review("bob", grade="D", cerebellum="major", sinus="minor")),
        fact("gone", make_review("ann", grade=None, unratable="no surfaces in half the brain")),
        fact("draft", make_review("ann", submitted=False, sinus="major")),
        fact("new"),
    ]


# ---- progress and grades --------------------------------------------------------------------

def test_progress_states_are_exclusive_and_add_up(cohort):
    assert progress(cohort) == {"subjects": 6, "reviewed": 2, "disagreement": 1, "unratable": 1,
                                "unreviewed": 2, "drafts": 1}


def test_a_subject_without_a_run_is_unreviewed():
    assert progress([fact("x", has_run=False)])["unreviewed"] == 1


def test_grades_are_listed_in_order_with_disagreements_apart(cohort):
    counts = grade_counts(cohort)
    assert [grade for grade, _ in counts] == [*load_protocol()["grades"], "disagreement", "not graded"]
    assert {grade: n for grade, n in counts if n} == {"A": 1, "C": 1, "disagreement": 1}


def test_no_reviews_at_all():
    facts = [fact("a"), fact("b")]
    assert progress(facts)["reviewed"] == 0 and progress(facts)["unreviewed"] == 2
    assert all(n == 0 for _, n in grade_counts(facts))


# ---- ratings by region ------------------------------------------------------------------------

def test_region_ratings_count_every_ratable_subject_once_per_item(cohort):
    rows = {row["item"]: row for row in region_ratings(cohort)}
    assert list(rows) == item_ids()
    assert rows["sinus"]["title"] and rows["sinus"]["counts"] == {
        "none": 1, "minor": 1, "major": 1, "disagreement": 0, "unreviewed": 2}
    assert rows["cerebellum"]["counts"] == {
        "none": 2, "minor": 0, "major": 0, "disagreement": 1, "unreviewed": 2}
    assert rows["birdseye"]["counts"] == {
        "ok": 3, "concern": 0, "exclude": 0, "disagreement": 0, "unreviewed": 2}
    for row in rows.values():
        assert sum(row["counts"].values()) == 5  # the unratable subject is not rated at all


# ---- marked problems --------------------------------------------------------------------------

def test_problem_kinds_count_subjects_and_marks_per_region(cohort):
    rows = {row["region"]: row for row in problem_kinds(cohort)}
    assert list(rows) == REGIONS
    kinds = load_protocol()["mark_kinds"]
    assert all(list(row["cells"]) == kinds for row in rows.values())
    assert rows["sinus"]["cells"]["pial_out"] == {"subjects": 1, "marks": 2}
    assert rows["orbitofrontal"]["cells"]["gray_missed"] == {"subjects": 1, "marks": 1}  # rated minor
    assert rows["sinus"]["cells"]["gray_missed"] == {"subjects": 0, "marks": 0}
    total = sum(cell["marks"] for row in rows.values() for cell in row["cells"].values())
    assert total == 3  # the draft's marks do not count


def test_a_consensus_review_stands_alone_with_its_own_marks():
    ann = make_review("ann", sinus="major", marks=[mark(), mark()])
    bob = make_review("bob", sinus="none")
    settled = make_review("consensus", sinus="minor", marks=[mark("sinus", "gray_missed")])
    facts = [fact("s", ann, bob, settled)]
    cells = {row["region"]: row["cells"] for row in problem_kinds(facts)}["sinus"]
    assert cells["pial_out"]["marks"] == 0 and cells["gray_missed"] == {"subjects": 1, "marks": 1}
    assert {r["item"]: r["counts"] for r in region_ratings(facts)}["sinus"]["minor"] == 1
    assert progress(facts)["reviewed"] == 1


def test_marks_of_two_reviewers_are_pooled_and_the_subject_counts_once():
    facts = [fact("s", make_review("ann", sinus="major", marks=[mark()]),
                  make_review("bob", sinus="major", marks=[mark(), mark()]))]
    assert {row["region"]: row["cells"] for row in problem_kinds(facts)}["sinus"]["pial_out"] == {
        "subjects": 1, "marks": 3}


# ---- the grid of subjects ---------------------------------------------------------------------

def test_subject_grid_lists_the_worst_first_and_the_unreviewed_last(cohort):
    grid = subject_grid(cohort)
    assert [row["name"] for row in grid] == ["bad", "split", "clean", "gone", "draft", "new"]
    bad = grid[0]
    assert bad["grade"] == "C" and bad["marks"] == 3 and bad["status"] == "reviewed"
    assert bad["cells"]["sinus"] == "major" and bad["cells"]["orbitofrontal"] == "minor"
    assert bad["href"] == "../subjects/fs__bad/index.html" and bad["edited"] is False
    split = grid[1]
    assert split["status"] == "disagreement" and split["grade"] == "disagreement"
    assert split["cells"]["cerebellum"] == "disagreement" and split["cells"]["sinus"] == "minor"
    assert set(grid[3]["cells"].values()) == {"unratable"} and grid[3]["status"] == "unratable"
    assert set(grid[5]["cells"].values()) == {"unreviewed"} and grid[5]["grade"] is None
    assert list(bad["cells"]) == item_ids()


def test_the_top_of_a_whole_brain_scale_counts_as_severe_in_the_order():
    facts = [fact("a", make_review("ann", sinus="minor")), fact("b", make_review("ann", t1="exclude"))]
    assert [row["name"] for row in subject_grid(facts)] == ["b", "a"]


# ---- indicators -------------------------------------------------------------------------------

@pytest.fixture
def scanned():
    return [
        fact("one", make_review("ann", sinus="major", marks=[mark()]),
             findings=found(("ribbon_outside_brain", "pial_out", "sinus"),
                            ("ribbon_outside_brain", "pial_out", "sinus"),
                            ("ribbon_outside_brain", "pial_out", "outer_edge"),
                            ("missed_gray", "look_here", "sinus"))),
        fact("two", make_review("ann"),
             findings=found(("thick_patches", "thickness", "sinus"))),
        fact("three", make_review("ann", sinus="major", marks=[mark()]),
             findings=found(not_run=("thick_patches",))),
        fact("four", make_review("ann"), findings=found()),
        fact("five", findings=found(("ribbon_outside_brain", "pial_out", "sinus"))),
        fact("failed", make_review("ann", sinus="major", marks=[mark()]), findings=None),
        fact("norun", has_run=False),
    ]


def test_indicator_summary_counts_where_each_ran_and_what_it_found(scanned):
    rows = {row["name"]: row for row in indicator_summary(scanned)}
    assert rows["ribbon_outside_brain"] == {
        "name": "ribbon_outside_brain", "ran": 5, "not_run": 0, "with_findings": 2,
        "median": 0.0, "largest": 3}
    assert rows["thick_patches"]["ran"] == 4 and rows["thick_patches"]["not_run"] == 1
    assert rows["thick_patches"]["with_findings"] == 1
    assert rows["missed_gray"]["with_findings"] == 0  # a place to look is not a finding
    assert not_computed(scanned) == 1  # "failed"; a subject without a run is not expected to have any


def test_finding_kinds_count_subjects_per_region_and_leave_out_places_to_look(scanned):
    rows = {row["region"]: row for row in finding_kinds(scanned)}
    assert list(rows) == REGIONS
    assert rows["sinus"]["cells"]["pial_out"] == 2 and rows["sinus"]["cells"]["thickness"] == 1
    assert rows["outer_edge"]["cells"]["pial_out"] == 1
    assert "look_here" not in rows["sinus"]["cells"]
    assert sum(rows["cerebellum"]["cells"].values()) == 0


def test_agreement_compares_findings_with_ratings_region_by_region(scanned):
    rows = {row["region"]: row for row in agreement(scanned)}
    assert rows["sinus"]["fired"] == {"none": 1, "minor": 0, "major": 1}  # two, one
    assert rows["sinus"]["quiet"] == {"none": 1, "minor": 0, "major": 1}  # four, three
    assert rows["outer_edge"]["fired"] == {"none": 1, "minor": 0, "major": 0}
    assert rows["outer_edge"]["quiet"] == {"none": 3, "minor": 0, "major": 0}
    # unreviewed (five) and without indicator results (failed) are in no cell
    assert sum(rows["sinus"]["fired"].values()) + sum(rows["sinus"]["quiet"].values()) == 4


def test_a_region_in_disagreement_is_not_in_its_agreement_row():
    split = fact("s", make_review("ann", cerebellum="none"), make_review("bob", cerebellum="major"),
                 findings=found(("ribbon_in_cerebellum", "pial_out", "cerebellum")))
    rows = {row["region"]: row for row in agreement([split])}
    assert sum(rows["cerebellum"]["fired"].values()) == 0
    assert sum(rows["sinus"]["quiet"].values()) == 1


def test_nothing_known_gives_empty_tables_not_errors():
    assert indicator_summary([]) == [] and not_computed([]) == 0
    assert all(sum(row["cells"].values()) == 0 for row in finding_kinds([]))
    assert subject_grid([]) == [] and progress([])["subjects"] == 0
