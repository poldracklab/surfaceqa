import pytest

from surfaceqa.protocol import item_ids
from surfaceqa.reviews import (ReviewError, clean_review, empty_review, missing_for_submit,
                               valid_reviewer)

KEY, RUN, WHO = "fastsurfer__sub-01", "abc123abc123", "ann"
MARK = {"region": "sinus", "kind": "pial_out", "grid": [10.5, 20.0, 30.25],
        "surface": "lh.pial", "finding": 3, "note": "into the sinus"}


def payload(**fields) -> dict:
    return {**empty_review(KEY, RUN, WHO), **fields}


def complete(**fields) -> dict:
    """A review with every item at its lowest level and a grade."""
    items = {i: {"rating": "ok" if i in ("birdseye", "t1") else "none", "note": ""}
             for i in item_ids()}
    return payload(items=items, grade="B", **fields)


@pytest.mark.parametrize("name", ["russ", "r-2_b", "consensus", "A" * 40])
def test_valid_reviewer_accepts_plain_names(name):
    assert valid_reviewer(name)


@pytest.mark.parametrize("name", ["", "a/b", "..", "a b", "é", "A" * 41, "-a", "a.b", "a\n"])
def test_valid_reviewer_refuses_paths_and_odd_names(name):
    assert not valid_reviewer(name)


def test_empty_review_lists_every_item_as_unrated():
    review = empty_review(KEY, RUN, WHO)
    assert list(review["items"]) == item_ids()
    assert all(item == {"rating": None, "note": ""} for item in review["items"].values())
    assert (review["key"], review["run"], review["reviewer"]) == (KEY, RUN, WHO)
    assert review["protocol"] == 1 and review["submitted"] is None and review["marks"] == []


def test_clean_review_keeps_valid_ratings_marks_and_grade():
    items = {"sinus": {"rating": "major", "note": "bad"}, "t1": {"rating": "concern", "note": ""}}
    review = clean_review(payload(items=items, marks=[MARK], grade="C+", notes="hm"), KEY, RUN, WHO)
    assert review["items"]["sinus"] == {"rating": "major", "note": "bad"}
    assert review["items"]["t1"]["rating"] == "concern"
    assert review["marks"] == [MARK]
    assert review["grade"] == "C+" and review["notes"] == "hm"


def test_clean_review_refuses_a_region_level_on_a_pass_item():
    with pytest.raises(ReviewError, match="t1"):
        clean_review(payload(items={"t1": {"rating": "major", "note": ""}}), KEY, RUN, WHO)


@pytest.mark.parametrize("fields, word", [
    ({"items": {"nose": {"rating": "none", "note": ""}}}, "nose"),
    ({"marks": [{**MARK, "kind": "wobbly"}]}, "kind"),
    ({"marks": [{**MARK, "region": "nose"}]}, "region"),
    ({"marks": [{**MARK, "surface": "lh.inflated"}]}, "surface"),
    ({"grade": "E"}, "grade"),
    ({"marks": "none"}, "marks"),
    ({"items": []}, "items"),
])
def test_clean_review_refuses_unknown_items_kinds_grades_and_surfaces(fields, word):
    with pytest.raises(ReviewError, match=word):
        clean_review(payload(**fields), KEY, RUN, WHO)


@pytest.mark.parametrize("grid", [[1, 2], [1, 2, float("nan")], [1, 2, float("inf")], "abc",
                                  [1, 2, "3"], [1, 2, True]])
def test_clean_review_refuses_non_finite_grid(grid):
    with pytest.raises(ReviewError, match="grid"):
        clean_review(payload(marks=[{**MARK, "grid": grid}]), KEY, RUN, WHO)


def test_clean_review_ignores_server_owned_fields():
    sent = payload(submitted="2020-01-01", saved="2020-01-01", revised=True,
                   marks=[{**MARK, "vertex": 5, "tkr": [1, 2, 3]}], reviewer="bob", key="x")
    review = clean_review(sent, KEY, RUN, WHO)
    assert review["submitted"] is None and review["saved"] is None and review["revised"] is False
    assert "vertex" not in review["marks"][0] and "tkr" not in review["marks"][0]
    assert review["reviewer"] == WHO and review["key"] == KEY


def test_clean_review_fills_missing_items_as_unrated():
    review = clean_review({"items": {"sinus": {"rating": "minor"}}}, KEY, RUN, WHO)
    assert list(review["items"]) == item_ids()
    assert review["items"]["sinus"] == {"rating": "minor", "note": ""}
    assert review["items"]["cerebellum"]["rating"] is None


def test_long_note_is_refused():
    with pytest.raises(ReviewError, match="note"):
        clean_review(payload(notes="x" * 2001), KEY, RUN, WHO)
    with pytest.raises(ReviewError, match="sinus"):
        clean_review(payload(items={"sinus": {"rating": None, "note": "x" * 2001}}), KEY, RUN, WHO)


def test_too_many_marks_are_refused():
    with pytest.raises(ReviewError, match="marks"):
        clean_review(payload(marks=[MARK] * 201), KEY, RUN, WHO)


def test_skipped_and_unratable_are_kept():
    review = clean_review(payload(skipped=True, unratable="  motion  "), KEY, RUN, WHO)
    assert review["skipped"] is True and review["unratable"] == "motion"
    assert clean_review(payload(unratable="   "), KEY, RUN, WHO)["unratable"] is None


def test_missing_for_submit_lists_unrated_items_and_grade():
    missing = missing_for_submit(empty_review(KEY, RUN, WHO))
    assert len(missing) == 12
    assert any("grade" in line for line in missing)
    assert any("Sagittal and transverse sinus" in line for line in missing)


def test_complete_review_can_be_submitted():
    assert missing_for_submit(complete()) == []


def test_major_region_without_a_mark_blocks_submit():
    review = complete()
    review["items"]["sinus"]["rating"] = "major"
    missing = missing_for_submit(review)
    assert len(missing) == 1 and "mark" in missing[0] and "sinus" in missing[0].lower()


def test_major_region_with_a_mark_can_be_submitted():
    review = complete(marks=[MARK])
    review["items"]["sinus"]["rating"] = "major"
    assert missing_for_submit(review) == []


def test_unratable_with_a_reason_can_be_submitted_with_nothing_rated():
    assert missing_for_submit(payload(unratable="severe motion")) == []


def test_blank_unratable_reason_does_not_count():
    assert len(missing_for_submit(payload(unratable="  "))) == 12
