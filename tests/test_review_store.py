from datetime import datetime, timedelta, timezone

from surfaceqa.review_store import (earlier_reviews, list_reviews, load_review, review_path,
                                    save_review, submit_review)
from surfaceqa.reviews import empty_review

KEY, RUN = "fastsurfer__sub-01", "abc123abc123"
T0 = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


def test_saved_review_is_read_back_with_a_timestamp(tmp_path):
    saved = save_review(tmp_path, {**empty_review(KEY, RUN, "ann"), "grade": "B"}, now=T0)
    assert saved["saved"] == "2026-11-23T12:00:00+00:00"
    assert review_path(tmp_path, KEY, RUN, "ann") == tmp_path / "ratings" / KEY / RUN / "ann.json"
    assert load_review(tmp_path, KEY, RUN, "ann") == saved
    assert saved["grade"] == "B" and saved["submitted"] is None


def test_submitting_records_the_time(tmp_path):
    done = submit_review(tmp_path, empty_review(KEY, RUN, "ann"), now=T0)
    assert done["submitted"] == done["saved"] == "2026-11-23T12:00:00+00:00"
    assert done["revised"] is False


def test_saving_after_submitting_keeps_the_submission_time_and_flags_revised(tmp_path):
    submit_review(tmp_path, empty_review(KEY, RUN, "ann"), now=T0)
    later = save_review(tmp_path, {**empty_review(KEY, RUN, "ann"), "grade": "C"},
                        now=T0 + timedelta(hours=1))
    assert later["submitted"] == "2026-11-23T12:00:00+00:00"
    assert later["saved"] == "2026-11-23T13:00:00+00:00"
    assert later["revised"] is True and later["grade"] == "C"


def test_reviews_of_two_reviewers_are_separate_files(tmp_path):
    save_review(tmp_path, {**empty_review(KEY, RUN, "ann"), "grade": "A"})
    save_review(tmp_path, {**empty_review(KEY, RUN, "bob"), "grade": "F"})
    assert [(r["reviewer"], r["grade"]) for r in list_reviews(tmp_path, KEY, RUN)] == [
        ("ann", "A"), ("bob", "F")]


def test_list_reviews_ignores_unreadable_files(tmp_path):
    save_review(tmp_path, empty_review(KEY, RUN, "ann"))
    review_path(tmp_path, KEY, RUN, "bob").write_text('{"trunc')
    review_path(tmp_path, KEY, RUN, "cat").write_text('[1, 2]')
    assert [r["reviewer"] for r in list_reviews(tmp_path, KEY, RUN)] == ["ann"]


def test_load_review_of_a_truncated_or_absent_file_is_none(tmp_path):
    assert load_review(tmp_path, KEY, RUN, "ann") is None
    path = review_path(tmp_path, KEY, RUN, "ann")
    path.parent.mkdir(parents=True)
    path.write_text('{"trunc')
    assert load_review(tmp_path, KEY, RUN, "ann") is None


def test_reviews_of_another_run_are_not_listed_for_this_run(tmp_path):
    save_review(tmp_path, empty_review(KEY, "000000000000", "ann"))
    assert list_reviews(tmp_path, KEY, RUN) == []


def test_earlier_reviews_returns_only_submitted_reviews_of_other_runs(tmp_path):
    submit_review(tmp_path, empty_review(KEY, "old1", "ann"), now=T0)
    submit_review(tmp_path, empty_review(KEY, "old2", "ann"), now=T0 + timedelta(days=1))
    save_review(tmp_path, empty_review(KEY, "old3", "ann"))
    submit_review(tmp_path, empty_review(KEY, "old1", "bob"))
    submit_review(tmp_path, empty_review(KEY, RUN, "ann"))
    assert [r["run"] for r in earlier_reviews(tmp_path, KEY, RUN, "ann")] == ["old2", "old1"]
    assert earlier_reviews(tmp_path, "nobody__sub-99", RUN, "ann") == []


def test_no_temporary_file_is_left_behind(tmp_path):
    save_review(tmp_path, empty_review(KEY, RUN, "ann"))
    save_review(tmp_path, empty_review(KEY, RUN, "ann"))
    assert [p.name for p in (tmp_path / "ratings" / KEY / RUN).iterdir()] == ["ann.json"]
