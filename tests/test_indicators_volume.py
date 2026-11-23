import numpy as np
import pytest
from scipy import ndimage

from surfaceqa.indicators_volume import VOLUME_INDICATORS
from surfaceqa.subjectdata import SubjectData


def clean() -> SubjectData:
    """A 40^3, 1 mm ball: white matter r < 10, cortex 10 <= r < 14, centred at (20, 20, 20)."""
    idx = np.indices((40, 40, 40))
    r = np.sqrt(((idx - 20) ** 2).sum(axis=0))
    left = idx[0] < 20
    ribbon = np.zeros((40, 40, 40), dtype=np.int32)
    ribbon[r < 10] = np.where(left, 2, 41)[r < 10]
    shell = (r >= 10) & (r < 14)
    ribbon[shell] = np.where(left, 3, 42)[shell]
    seg = ribbon.copy()
    seg[ribbon == 3] = 1028
    seg[ribbon == 42] = 2028
    seg[17:23, 17:23, 0:5] = 8  # cerebellum, below the ball (which starts at z = 7)
    norm = np.select([np.isin(ribbon, (2, 41)), np.isin(ribbon, (3, 42))], [110.0, 70.0], 0.0)
    hemi = {"lh": np.isin(ribbon, (2, 3)), "rh": np.isin(ribbon, (41, 42))}
    return SubjectData(voxel_sizes=(1.0, 1.0, 1.0), ribbon=ribbon, hemi_ribbon=hemi, seg=seg,
                       seg_name="seg", nonbrain=None, nonbrain_names=[], parc=None, norm=norm, hemis={})


def shifted_ball(voxel: float, shift_mm: float) -> SubjectData:
    """Segmentation cortex ends at r = 14 mm; the ribbon's pial edge is shift_mm farther out (or in)."""
    n = int(round(48 / voxel))
    idx = np.indices((n, n, n))
    r = np.sqrt(((idx - n // 2) ** 2).sum(axis=0)) * voxel
    ribbon = np.select([r < 10, r < 14 + shift_mm], [2, 3], 0).astype(np.int32)
    seg = np.select([r < 10, r < 14], [2, 1028], 0).astype(np.int32)
    return SubjectData(voxel_sizes=(voxel,) * 3, ribbon=ribbon, hemi_ribbon=None, seg=seg,
                       seg_name="seg", nonbrain=None, nonbrain_names=[], parc=None, norm=None, hemis={})


def names_run(data):
    return {r.name: r for r in (ind(data) for ind in VOLUME_INDICATORS)}


def test_clean_subject_has_no_findings():
    assert all(r.findings == [] for r in names_run(clean()).values())


def test_one_voxel_shell_is_not_a_finding():
    data = clean()
    shell = ndimage.binary_dilation(data.ribbon > 0) & (data.ribbon == 0)  # pial one voxel too far out
    data.ribbon[shell] = 3
    r = names_run(data)
    assert r["ribbon_outside_brain"].findings == [] and r["missed_gray"].findings == []


def test_ribbon_blob_outside_the_brain_is_found_where_it_is():
    data = clean()
    data.ribbon[30:36, 17:23, 17:23] = 3  # a blob reaching past the ball's edge at x = 34
    (f,) = names_run(data)["ribbon_outside_brain"].findings
    assert f.kind == "pial_out" and 31 <= f.grid[0] <= 35 and 17 <= f.grid[1] <= 22


def test_ribbon_in_explicit_nonbrain_mask_needs_no_margin():
    data = clean()
    data.nonbrain = np.zeros_like(data.ribbon, bool)
    data.nonbrain[20:24, 20:24, 31:34] = True  # 48 voxels inside the cortex shell
    (f,) = names_run(data)["ribbon_in_nonbrain_mask"].findings
    assert f.n == int((np.isin(data.ribbon, (3, 42)) & data.nonbrain).sum())


def test_ribbon_in_cerebellum():
    data = clean()
    data.ribbon[17:23, 17:23, 0:5] = 3
    (f,) = names_run(data)["ribbon_in_cerebellum"].findings
    assert f.n == 4 ** 3  # the block minus its 1 mm rim (the volume edge at z = 0 is not a rim)


def test_missed_gray():
    data = clean()
    data.seg[30:36, 17:23, 17:23] = 1028  # a parcel where the ribbon has nothing
    (f,) = names_run(data)["missed_gray"].findings
    assert f.kind == "gray_missed" and data.ribbon[f.grid] == 0


def generic_cortex(data: SubjectData) -> SubjectData:
    """Cortex labelled as one class per hemisphere (3 / 42), as SynthSeg and aseg do."""
    data.seg[data.seg == 1028] = 3
    data.seg[data.seg == 2028] = 42
    return data


def test_missed_gray_runs_on_a_segmentation_with_one_cortex_class():
    data = generic_cortex(clean())
    assert names_run(data)["missed_gray"].findings == []
    data.seg[30:36, 17:23, 17:23] = 3  # cortex where the ribbon has nothing
    (f,) = names_run(data)["missed_gray"].findings
    assert f.kind == "gray_missed" and data.ribbon[f.grid] == 0


def test_missed_gray_is_not_run_when_the_segmentation_has_no_cortex_labels():
    data = clean()
    data.seg[data.seg >= 1000] = 0
    r = names_run(data)["missed_gray"]
    assert r.status == "not run" and "no cortex labels" in r.reason


def test_ribbon_over_csf_counts_as_outside_the_brain():
    # SynthSeg labels the fluid around the brain as CSF (24), not as background
    data = clean()
    data.seg[data.seg == 0] = 24
    assert names_run(data)["ribbon_outside_brain"].findings == []
    data.ribbon[30:36, 17:23, 17:23] = 3
    (f,) = names_run(data)["ribbon_outside_brain"].findings
    assert f.kind == "pial_out" and 31 <= f.grid[0] <= 35


def test_white_matter_in_ribbon():
    data = clean()
    data.ribbon[14:20, 17:23, 17:23] = 3  # the ribbon calls deep white matter cortex
    (f,) = names_run(data)["white_matter_in_ribbon"].findings
    assert f.kind == "white_short"


def test_bright_ribbon():
    data = clean()
    data.norm[20:24, 20:24, 31:34] = 200  # bright tissue in the outer cortex shell
    (f,) = names_run(data)["bright_ribbon"].findings
    assert 20 <= f.grid[0] <= 23 and 31 <= f.grid[2] <= 33


def test_hemisphere_crossing():
    data = clean()
    data.hemi_ribbon["lh"][20:23, 18:22, 18:22] = True  # lh reaches into rh
    (f,) = names_run(data)["hemisphere_crossing"].findings
    assert f.kind == "crossing" and f.n == 3 * 4 * 4


@pytest.mark.parametrize("field,names", [
    ("ribbon", {"ribbon_outside_brain", "ribbon_in_nonbrain_mask", "ribbon_in_cerebellum",
                "missed_gray", "white_matter_in_ribbon", "bright_ribbon"}),
    ("seg", {"ribbon_outside_brain", "ribbon_in_cerebellum", "missed_gray", "white_matter_in_ribbon"}),
    ("norm", {"bright_ribbon"}),
    ("hemi_ribbon", {"hemisphere_crossing"}),
    ("nonbrain", {"ribbon_in_nonbrain_mask"}),
])
def test_indicators_without_their_input_do_not_run(field, names):
    data = clean()
    setattr(data, field, None)
    r = names_run(data)
    assert {n for n, res in r.items() if res.status == "not run"} >= names
    assert all(res.reason for res in r.values() if res.status == "not run")


def test_one_voxel_shell_in_every_direction_is_not_a_finding():
    data = clean()
    shell = ndimage.binary_dilation(data.ribbon > 0, structure=np.ones((3, 3, 3))) & (data.ribbon == 0)
    data.ribbon[shell] = 3
    r = names_run(data)
    assert r["ribbon_outside_brain"].findings == [] and r["missed_gray"].findings == []


@pytest.mark.parametrize("voxel,shift", [(1.0, 1.0), (0.8, 0.8), (1.0, -1.0), (0.8, -0.8)])
def test_pial_edge_off_by_one_voxel_is_not_a_finding(voxel, shift):
    r = names_run(shifted_ball(voxel, shift))
    assert r["ribbon_outside_brain"].findings == [] and r["missed_gray"].findings == []


@pytest.mark.parametrize("voxel,shift", [(1.0, 3.0), (0.8, 3.0), (0.8, 2.0)])
def test_pial_edge_off_by_millimetres_is_a_finding(voxel, shift):
    # 2 mm at 0.8 mm voxels is the size of the sinus errors the tool exists to find
    assert names_run(shifted_ball(voxel, shift))["ribbon_outside_brain"].findings
    assert names_run(shifted_ball(voxel, -shift))["missed_gray"].findings
