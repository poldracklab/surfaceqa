from importlib import resources

from surfaceqa.protocol import PASS_ITEMS, item_ids, load_protocol, scale_for
from surfaceqa.regions import REGIONS


def test_protocol_has_a_version_and_three_levels_per_scale():
    protocol = load_protocol()
    assert protocol["version"] == 1
    assert [level["id"] for level in protocol["region_scale"]] == ["none", "minor", "major"]
    assert [level["id"] for level in protocol["pass_scale"]] == ["ok", "concern", "exclude"]
    assert all(level["anchor"] and level["key"] for level in protocol["region_scale"])
    assert len(protocol["grades"]) == 13 and protocol["grades"][0] == "A+"
    assert len(protocol["mark_kinds"]) == 6


def test_item_ids_are_the_two_passes_then_the_nine_regions_in_order():
    assert PASS_ITEMS == ("birdseye", "t1")
    assert item_ids()[:2] == ["birdseye", "t1"]
    assert item_ids()[2:] == [region.id for region in REGIONS]
    assert len(item_ids()) == 11


def test_scale_for_a_pass_and_for_a_region():
    protocol = load_protocol()
    assert scale_for("t1", protocol) == ["ok", "concern", "exclude"]
    assert scale_for("sinus", protocol) == ["none", "minor", "major"]


def test_protocol_file_is_packaged():
    assert (resources.files("surfaceqa") / "protocol.json").is_file()
