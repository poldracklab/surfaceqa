import json

from surfaceqa.finalize import finalize, is_stale, load_final
from surfaceqa.layout import current_run_dir
from surfaceqa.review_store import list_reviews, save_review, submit_review
from tests.reviewing import make_review

KEY = "fastsurfer__sub-01"


def _run(qa) -> str:
    return current_run_dir(qa, KEY).name


def test_finalize_writes_one_file_per_subject_with_a_run(qa):
    submit_review(qa, make_review("ann", KEY, _run(qa), sinus="minor"))
    records = finalize(qa)
    assert sorted(r["key"] for r in records) == [KEY, "freesurfer-8.2.0__sub-01"]
    assert sorted(p.name for p in (qa / "final").iterdir()) == [
        f"{KEY}.json", "freesurfer-8.2.0__sub-01.json"]
    final = load_final(qa, KEY)
    assert final["status"] == "single" and final["run"] == _run(qa)
    assert final["items"]["sinus"]["final"] == "minor"
    assert load_final(qa, "freesurfer-8.2.0__sub-01")["status"] == "unreviewed"
    assert load_final(qa, "fastsurfer__sub-02") is None  # missing files, no run


def test_finalize_uses_only_reviews_of_the_current_run(qa):
    submit_review(qa, make_review("ann", KEY, "000000000000", sinus="major"))
    finalize(qa)
    assert load_final(qa, KEY)["status"] == "unreviewed"


def test_final_is_stale_after_a_review_changes(qa):
    run = _run(qa)
    submit_review(qa, make_review("ann", KEY, run))
    finalize(qa)
    final = load_final(qa, KEY)
    assert not is_stale(final, list_reviews(qa, KEY, run), run)
    submit_review(qa, make_review("bob", KEY, run))
    assert is_stale(final, list_reviews(qa, KEY, run), run)
    assert is_stale(final, [], "ffffffffffff")


def test_a_draft_does_not_make_the_final_stale(qa):
    run = _run(qa)
    submit_review(qa, make_review("ann", KEY, run))
    finalize(qa)
    save_review(qa, make_review("bob", KEY, run, submitted=False))
    assert not is_stale(load_final(qa, KEY), list_reviews(qa, KEY, run), run)


def test_unreadable_final_file_is_none(qa):
    (qa / "final").mkdir()
    (qa / "final" / f"{KEY}.json").write_text("{")
    assert load_final(qa, KEY) is None
