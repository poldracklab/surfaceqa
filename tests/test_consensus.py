from surfaceqa.consensus import combine
from tests.reviewing import MARK, make_review


def test_no_submitted_review_is_unreviewed():
    final = combine([])
    assert final["status"] == "unreviewed" and final["reviewers"] == []
    assert final["items"]["sinus"]["final"] is None and final["needs_fix"] == []


def test_drafts_do_not_count():
    final = combine([make_review("ann", submitted=False, sinus="major")])
    assert final["status"] == "unreviewed" and final["reviewers"] == []


def test_one_reviewer_keeps_their_ratings():
    final = combine([make_review("ann", sinus="major", t1="concern", grade="C", marks=[MARK])])
    assert final["status"] == "single" and final["reviewers"] == ["ann"]
    assert final["items"]["sinus"] == {"final": "major", "ratings": {"ann": "major"}, "disagree": False}
    assert final["items"]["t1"]["final"] == "concern"
    assert final["grade"] == {"final": "C", "grades": {"ann": "C"}, "disagree": False}
    assert final["needs_fix"] == ["sinus"] and final["inputs"] == {"ann": "2026-11-23T12:00:00+00:00"}


def test_one_step_apart_takes_the_lower():
    final = combine([make_review("ann", sinus="none", cerebellum="major", t1="ok"),
                     make_review("bob", sinus="minor", cerebellum="minor", t1="concern")])
    assert final["status"] == "agreed"
    assert final["items"]["sinus"]["final"] == "none"
    assert final["items"]["cerebellum"]["final"] == "minor"
    assert final["items"]["t1"]["final"] == "ok"
    assert final["disagreements"] == []


def test_two_steps_apart_is_a_disagreement():
    final = combine([make_review("ann", sinus="none"), make_review("bob", sinus="major")])
    assert final["items"]["sinus"] == {"final": None, "disagree": True,
                                       "ratings": {"ann": "none", "bob": "major"}}
    assert final["disagreements"] == ["sinus"] and final["status"] == "disagreement"
    assert final["items"]["cerebellum"]["final"] == "none"


def test_marks_are_pooled_with_their_reviewer():
    other = {**MARK, "kind": "gray_missed"}
    final = combine([make_review("ann", sinus="major", marks=[MARK]),
                     make_review("bob", sinus="major", marks=[other])])
    assert [(m["reviewer"], m["kind"]) for m in final["marks"]] == [("ann", "pial_out"),
                                                                    ("bob", "gray_missed")]


def test_needs_fix_lists_regions_final_major():
    both = combine([make_review("ann", sinus="major"), make_review("bob", sinus="major")])
    assert both["needs_fix"] == ["sinus"]
    split = combine([make_review("ann", sinus="minor"), make_review("bob", sinus="major")])
    assert split["needs_fix"] == []


def test_one_unratable_of_two_is_a_disagreement():
    final = combine([make_review("ann"), make_review("bob", unratable="motion")])
    assert final["status"] == "disagreement" and "unratable" in final["disagreements"]
    assert final["unratable"] is False


def test_all_unratable_is_final_unratable():
    final = combine([make_review("ann", unratable="motion"), make_review("bob", unratable="blur")])
    assert final["unratable"] is True and final["status"] == "agreed"
    assert final["disagreements"] == [] and final["needs_fix"] == []
    assert final["items"]["sinus"]["final"] is None and final["grade"]["final"] is None


def test_grades_within_a_letter_take_the_better():
    final = combine([make_review("ann", grade="B"), make_review("bob", grade="C+")])
    assert final["grade"] == {"final": "B", "grades": {"ann": "B", "bob": "C+"}, "disagree": False}
    edge = combine([make_review("ann", grade="A"), make_review("bob", grade="B")])
    assert edge["grade"]["final"] == "A" and edge["status"] == "agreed"


def test_grades_more_than_a_letter_apart_disagree():
    final = combine([make_review("ann", grade="A"), make_review("bob", grade="C")])
    assert final["grade"]["final"] is None and final["grade"]["disagree"] is True
    assert final["disagreements"] == ["grade"] and final["status"] == "disagreement"


def test_three_reviewers_use_the_spread():
    wide = combine([make_review("ann", sinus="none"), make_review("bob", sinus="minor"),
                    make_review("cat", sinus="major")])
    assert wide["items"]["sinus"]["disagree"] is True
    near = combine([make_review("ann", sinus="minor"), make_review("bob", sinus="minor"),
                    make_review("cat", sinus="major")])
    assert near["items"]["sinus"]["final"] == "minor" and near["status"] == "agreed"


def test_a_consensus_review_settles_the_subject():
    final = combine([make_review("ann", sinus="none"), make_review("bob", sinus="major"),
                     make_review("consensus", sinus="minor", grade="B-")])
    assert final["status"] == "settled" and final["reviewers"] == ["consensus"]
    assert final["items"]["sinus"]["final"] == "minor" and final["grade"]["final"] == "B-"
    assert final["disagreements"] == []


def test_a_draft_consensus_review_settles_nothing():
    final = combine([make_review("ann", sinus="none"), make_review("bob", sinus="major"),
                     make_review("consensus", submitted=False)])
    assert final["status"] == "disagreement" and final["reviewers"] == ["ann", "bob"]
