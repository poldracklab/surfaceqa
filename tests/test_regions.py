import dataclasses

import numpy as np
import pytest

from surfaceqa.findings import Finding
from surfaceqa.regions import REGIONS, assign_region, build_context, default_locations
from surfaceqa.subjectdata import SubjectData

# (label, x range, y range, z range) for the left hemisphere; ranges are inclusive
LEFT_BOXES = [
    (1005, (10, 29), (10, 20), (30, 45)),  # cuneus
    (1028, (10, 29), (60, 70), (30, 45)),  # superior frontal
    (1012, (10, 29), (60, 70), (15, 22)),  # lateral orbitofrontal
    (1009, (10, 29), (35, 45), (15, 22)),  # inferior temporal
    (1016, (24, 29), (35, 45), (24, 28)),  # parahippocampal
    (1029, (10, 29), (25, 34), (46, 50)),  # superior parietal
    (8, (12, 28), (8, 22), (8, 20)),       # cerebellum
    (17, (25, 28), (36, 44), (29, 31)),    # hippocampus
]
RIGHT_LABEL = {8: 47, 17: 53}


def _fill(parc, label, xr, yr, zr):
    parc[xr[0]:xr[1] + 1, yr[0]:yr[1] + 1, zr[0]:zr[1] + 1] = label


def toy() -> SubjectData:
    """A 60 x 80 x 60, 1 mm toy brain: left cerebrum x 10..29, right x 31..50."""
    parc = np.zeros((60, 80, 60), dtype=np.int32)
    ribbon = np.zeros_like(parc)
    ribbon[10:30] = 3
    ribbon[31:51] = 42
    for label, xr, yr, zr in LEFT_BOXES:
        _fill(parc, label, xr, yr, zr)
        mirrored = (60 - xr[1], 60 - xr[0])
        _fill(parc, RIGHT_LABEL.get(label, label + 1000), mirrored, yr, zr)
    return SubjectData(voxel_sizes=(1.0, 1.0, 1.0), ribbon=ribbon, hemi_ribbon=None, seg=None,
                       seg_name=None, nonbrain=None, nonbrain_names=[], parc=parc, norm=None, hemis={})


def f(kind, grid):
    return Finding("x", kind, grid, 30.0, 30)


@pytest.mark.parametrize("kind,grid,region", [
    ("crossing", (30, 40, 40), "crossing"),
    ("white_short", (15, 65, 40), "white_surface"),
    ("topology", (15, 15, 40), "white_surface"),
    ("pial_out", (28, 15, 40), "sinus"),  # medial cuneus
    ("pial_out", (12, 15, 40), "outer_edge"),  # lateral cuneus: not near the midline
    ("pial_out", (20, 15, 23), "cerebellum"),  # just above the cerebellum
    ("pial_out", (28, 65, 40), "frontal_midline"),
    ("pial_out", (15, 65, 18), "orbitofrontal"),
    ("gray_missed", (15, 40, 18), "inferior_temporal"),
    ("pial_out", (26, 40, 26), "medial_temporal"),
    ("thickness", (15, 30, 49), "outer_edge"),
    ("pial_out", (32, 15, 40), "sinus"),  # right hemisphere, medial
])
def test_assign_region(kind, grid, region):
    assert assign_region(f(kind, grid), build_context(toy())) == region


def test_without_parcellation_everything_is_outer_edge_and_says_why():
    data = toy()
    data.parc = None
    ctx = build_context(data)
    assert assign_region(f("pial_out", (28, 15, 40)), ctx) == "outer_edge" and "aparc" in ctx.reason
    assert assign_region(f("crossing", (30, 40, 40)), ctx) == "crossing"


def test_regions_are_in_checklist_order():
    assert [r.id for r in REGIONS] == [
        "sinus", "cerebellum", "frontal_midline", "orbitofrontal", "inferior_temporal",
        "medial_temporal", "outer_edge", "white_surface", "crossing"]


def test_default_locations_are_inside_their_parcel():
    data = toy()
    locs = default_locations(data)
    assert {d["label"] for d in locs["sinus"]} == {"lh cuneus", "rh cuneus"}
    for d in locs["sinus"]:
        assert data.parc[tuple(d["grid"])] in (1005, 2005)
    assert locs["cerebellum"] == []  # the toy has no lingual or fusiform parcels
    assert default_locations(dataclasses.replace(data, parc=None)) == {}


def test_a_finding_outside_the_parcellation_box_is_still_assigned():
    assert assign_region(f("pial_out", (0, 0, 0)), build_context(toy())) in {r.id for r in REGIONS}
