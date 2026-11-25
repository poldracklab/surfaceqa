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


# ---- the same page saving again ---------------------------------------------------------------

def _draft(notes: str) -> dict:
    return {**empty_review(KEY, RUN, "ann"), "notes": notes}


def _page(seq: int, page: str = "page-a") -> dict:
    return {"id": page, "seq": seq}


def test_a_later_save_of_the_same_page_is_stored_whatever_stamp_it_saw(tmp_path):
    """The page left while a save was on its way: both carry the stamp from before."""
    save_review(tmp_path, _draft("first"), expected=None, writer=_page(1))
    save_review(tmp_path, _draft("second"), expected=None, writer=_page(2))
    assert load_review(tmp_path, KEY, RUN, "ann")["notes"] == "second"


def test_an_earlier_save_of_the_same_page_that_arrives_late_changes_nothing(tmp_path):
    newer = save_review(tmp_path, _draft("second"), expected=None, writer=_page(2))
    answer = save_review(tmp_path, _draft("first"), expected=None, writer=_page(1))
    assert answer == newer == load_review(tmp_path, KEY, RUN, "ann")


def test_a_save_repeated_because_its_answer_was_lost_is_not_a_conflict(tmp_path):
    save_review(tmp_path, _draft("same"), expected=None, writer=_page(1))
    again = save_review(tmp_path, _draft("same"), expected=None, writer=_page(2))
    assert again["notes"] == "same" and again["writer"] == _page(2)


def test_another_page_with_an_old_stamp_is_still_a_conflict(tmp_path):
    import pytest
    from surfaceqa.review_store import Conflict
    save_review(tmp_path, _draft("first"), expected=None, writer=_page(1))
    with pytest.raises(Conflict):
        save_review(tmp_path, _draft("other"), expected=None, writer=_page(5, "page-b"))
    with pytest.raises(Conflict):
        save_review(tmp_path, _draft("other"), expected=None)
    assert load_review(tmp_path, KEY, RUN, "ann")["notes"] == "first"


def test_a_page_that_another_page_saved_over_is_a_conflict_again(tmp_path):
    import pytest
    from surfaceqa.review_store import Conflict
    first = save_review(tmp_path, _draft("first"), expected=None, writer=_page(1))
    save_review(tmp_path, _draft("other"), expected=first["saved"], writer=_page(1, "page-b"))
    with pytest.raises(Conflict):
        save_review(tmp_path, _draft("mine"), expected=first["saved"], writer=_page(2))


def test_a_stored_writer_that_is_malformed_is_no_writer(tmp_path):
    import json
    save_review(tmp_path, _draft("first"), expected=None, writer=_page(1))
    path = review_path(tmp_path, KEY, RUN, "ann")
    path.write_text(json.dumps({**json.loads(path.read_text()), "writer": {"id": 3, "seq": "x"}}))
    assert load_review(tmp_path, KEY, RUN, "ann")["writer"] is None


# ---- two servers on one QA directory -------------------------------------------------------------

def _slow_save(qa_dir: str, notes: str, start, results) -> None:
    """One server process: reads what is stored, takes its time, then writes."""
    import time
    from surfaceqa import review_store
    read = review_store._read

    def slow_read(path):
        found = read(path)
        time.sleep(0.5)  # long enough for the other process to read the same thing
        return found

    review_store._read = slow_read
    start.wait()
    try:
        review_store.save_review(qa_dir, _draft(notes), expected=None)
        results.put(("accepted", notes))
    except review_store.Conflict:
        results.put(("conflict", notes))


def test_two_processes_cannot_both_save_over_the_same_stored_review(tmp_path):
    import multiprocessing
    context = multiprocessing.get_context("spawn")
    start, results = context.Barrier(2), context.Queue()
    workers = [context.Process(target=_slow_save, args=(str(tmp_path), notes, start, results))
               for notes in ("A", "B")]
    for worker in workers:
        worker.start()
    outcomes = dict(results.get(timeout=30) for _ in workers)
    for worker in workers:
        worker.join(timeout=30)
    assert sorted(outcomes) == ["accepted", "conflict"]
    assert load_review(tmp_path, KEY, RUN, "ann")["notes"] == outcomes["accepted"]
    assert [p.name for p in review_path(tmp_path, KEY, RUN, "ann").parent.iterdir()] == ["ann.json"]
