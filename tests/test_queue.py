from surfaceqa.queue import blind_order, next_key, review_queue

KEYS = ["s__a", "s__b", "s__c", "s__d"]
NONE = {key: "none" for key in KEYS}


def test_queue_keeps_worst_first_order():
    assert review_queue(KEYS, {**NONE, "s__b": "draft"}, "ann", blind=False) == KEYS


def test_submitted_subjects_leave_the_queue():
    assert review_queue(KEYS, {**NONE, "s__a": "submitted"}, "ann", blind=False) == KEYS[1:]


def test_skipped_subjects_go_last_and_are_not_dropped():
    states = {**NONE, "s__a": "skipped", "s__c": "skipped"}
    assert review_queue(KEYS, states, "ann", blind=False) == ["s__b", "s__d", "s__a", "s__c"]


def test_blind_order_is_shuffled_stable_per_reviewer_and_differs_between_reviewers():
    keys = [f"s__{n:02d}" for n in range(20)]
    ann = blind_order(keys, "ann")
    assert sorted(ann) == keys and ann != keys
    assert blind_order(list(reversed(keys)), "ann") == ann
    assert blind_order(keys, "bob") != ann
    states = {key: "none" for key in keys}
    assert review_queue(keys, states, "ann", blind=True) == ann


def test_next_after_the_last_wraps_to_the_first():
    assert next_key(KEYS, "s__b") == "s__c"
    assert next_key(KEYS, "s__d") == "s__a"
    assert next_key(KEYS, None) == "s__a"
    assert next_key(KEYS, "s__not-queued") == "s__a"


def test_next_is_none_when_nothing_else_is_left():
    assert next_key([], None) is None
    assert next_key(["s__a"], "s__a") is None
