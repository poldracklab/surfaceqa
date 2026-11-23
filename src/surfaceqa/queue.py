"""The order in which one reviewer is given the subjects."""

import random


def blind_order(keys: list[str], reviewer: str) -> list[str]:
    """A shuffle that is the same every time for one reviewer and differs between reviewers."""
    shuffled = sorted(keys)
    random.Random(reviewer).shuffle(shuffled)
    return shuffled


def review_queue(ordered_keys: list[str], states: dict[str, str], reviewer: str,
                 blind: bool) -> list[str]:
    """Subjects still to review: skipped ones last, submitted ones left out.

    `states` gives each subject's state for this reviewer: none, draft, skipped or submitted.
    """
    keys = blind_order(ordered_keys, reviewer) if blind else ordered_keys
    open_keys = [key for key in keys if states.get(key, "none") in ("none", "draft")]
    return open_keys + [key for key in keys if states.get(key) == "skipped"]


def next_key(queue: list[str], after: str | None) -> str | None:
    """The queued subject that follows `after`, wrapping round; None when no other is left."""
    others = [key for key in queue if key != after]
    if not others:
        return None
    if after not in queue:
        return others[0]
    return queue[(queue.index(after) + 1) % len(queue)]
