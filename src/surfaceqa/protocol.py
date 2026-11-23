"""The rating protocol: the wording of the scales, kept in a versioned file."""

import json
from functools import cache
from importlib import resources

from surfaceqa.regions import REGIONS

PASS_ITEMS = ("birdseye", "t1")


@cache
def load_protocol() -> dict:
    return json.loads((resources.files("surfaceqa") / "protocol.json").read_text())


def item_ids() -> list[str]:
    """Every item a reviewer rates: the two whole-brain passes, then the regions."""
    return [*PASS_ITEMS, *(region.id for region in REGIONS)]


def scale_for(item_id: str, protocol: dict) -> list[str]:
    """The levels of an item's scale, least severe first."""
    name = "pass_scale" if item_id in PASS_ITEMS else "region_scale"
    return [level["id"] for level in protocol[name]]
