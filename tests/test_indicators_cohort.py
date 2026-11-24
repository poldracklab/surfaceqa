import warnings

import numpy as np
import pytest

from surfaceqa.checklist import finding_text
from surfaceqa.cohort import Cohort
from surfaceqa.indicators_cohort import cohort_thickness
from surfaceqa.subjectdata import HemiSurface, SubjectData
from tests.synth import icosphere

N = 40962


def hemi(thickness=2.5):
    verts, faces = icosphere(10.0, 4)  # 2562 vertices
    return HemiSurface(pial_grid=verts + 20.0, faces=faces, thickness=np.full(len(verts), thickness),
                       cortex=np.arange(len(verts)), defect_labels=None, nofix_grid=None,
                       sphere=verts * 10.0)


def cohort(n=30, median=2.5, spread=0.1, hemis=("lh", "rh")):
    return Cohort("fs", n, "sig", {h: np.full(N, median, dtype=np.float32) for h in hemis},
                  {h: np.full(N, spread, dtype=np.float32) for h in hemis})


def data_with(cohort_, **hemis):
    return SubjectData(voxel_sizes=(1.0, 1.0, 1.0), ribbon=None, hemi_ribbon=None, seg=None,
                       seg_name=None, nonbrain=None, nonbrain_names=[], parc=None, norm=None,
                       hemis=hemis, cohort=cohort_)


def top(h, above=8.0):
    return h.pial_grid[:, 2] > 20 + above


@pytest.fixture(autouse=True)
def no_warnings():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        yield


def test_subject_like_the_cohort_has_no_findings():
    result = cohort_thickness(data_with(cohort(), lh=hemi(), rh=hemi()))
    assert result.status == "ran" and result.findings == [] and result.reason == ""
    assert result.name == "cohort_thickness" and result.kind == "thickness"


def test_patch_much_thicker_than_the_cohort_is_found_at_its_place():
    left, right = hemi(), hemi()
    right.thickness[top(right)] = 5.0
    (f,) = cohort_thickness(data_with(cohort(), lh=left, rh=right)).findings
    assert f.kind == "thickness" and f.hemi == "rh" and f.indicator == "cohort_thickness"
    assert f.n == int(top(right).sum()) and f.size_mm3 is None
    assert f.grid[2] >= 28 and abs(f.grid[0] - 20) <= 2 and abs(f.grid[1] - 20) <= 2


def test_thickness_normal_for_the_cohort_is_not_a_finding_even_when_high():
    h = hemi()
    h.thickness[top(h)] = 5.0
    thick_everywhere = cohort(median=4.8, spread=0.3)
    assert cohort_thickness(data_with(thick_everywhere, lh=h)).findings == []


def test_patch_smaller_than_the_minimum_is_not_reported():
    h = hemi()
    nearest_top = np.argsort(-h.pial_grid[:, 2])[:20]
    h.thickness[nearest_top] = 5.0
    assert cohort_thickness(data_with(cohort(), lh=h)).findings == []


def test_many_deviations_but_under_a_millimetre_is_not_reported():
    h = hemi()
    h.thickness[top(h)] = 3.2  # 7 robust SDs, 0.7 mm
    assert cohort_thickness(data_with(cohort(), lh=h)).findings == []


def test_over_a_millimetre_but_few_deviations_is_not_reported():
    h = hemi()
    h.thickness[top(h)] = 4.0  # 1.5 mm, 3 robust SDs
    assert cohort_thickness(data_with(cohort(spread=0.5), lh=h)).findings == []


def test_patch_outside_the_cortex_label_is_not_reported():
    h = hemi()
    h.thickness[top(h)] = 5.0
    h.cortex = np.flatnonzero(~top(h))
    assert cohort_thickness(data_with(cohort(), lh=h)).findings == []


@pytest.mark.parametrize("spread", [np.nan, 0.0])
def test_points_without_a_usable_spread_are_not_compared(spread):
    h = hemi()
    h.thickness[top(h)] = 5.0
    c = cohort()
    c.spread["lh"][:] = spread
    result = cohort_thickness(data_with(c, lh=h))
    assert result.status == "ran" and result.findings == []


@pytest.mark.parametrize("cohort_,count", [(None, 0), (Cohort("fs", 4, "sig", None, None), 4)])
def test_off_until_there_are_enough_subjects(cohort_, count):
    result = cohort_thickness(data_with(cohort_, lh=hemi()))
    assert result.status == "not run" and result.findings == []
    assert result.reason == f"needs 30 subjects in this source folder; there are {count}"


def test_not_run_without_a_registration_sphere():
    h = hemi()
    h.sphere = None
    result = cohort_thickness(data_with(cohort(), lh=h))
    assert result.status == "not run" and "sphere.reg" in result.reason


def test_a_hemisphere_that_cannot_be_compared_is_named():
    bad_count, good = hemi(), hemi()
    bad_count.sphere = bad_count.sphere[:-1]
    good.thickness[top(good)] = 5.0
    result = cohort_thickness(data_with(cohort(), lh=bad_count, rh=good))
    assert len(result.findings) == 1 and result.reason.startswith("lh not checked")
    result = cohort_thickness(data_with(cohort(hemis=("lh",)), lh=hemi(), rh=good))
    assert result.findings == [] and result.reason.startswith("rh not checked")


def test_the_checklist_names_the_comparison():
    record = {"indicator": "cohort_thickness", "kind": "thickness", "size_mm3": None, "n": 60}
    assert finding_text(record) == "thicker than the cohort · 60 vertices"
    assert finding_text({**record, "indicator": "thick_patches"}) == "thick patch · 60 vertices"


# ---- the comparison is made place by place, hemisphere by hemisphere ------------------------

def _thick_at_the_top(median=2.5):
    """Cohort statistics that are 5 mm thick around the top of the left hemisphere only."""
    from surfaceqa.sphere import target_points

    c = cohort(median=median)
    c.median["lh"][target_points()[:, 2] > 0.7] = 5.0
    return c


def test_thickness_usual_at_that_place_is_not_a_finding_but_is_one_elsewhere():
    usual, elsewhere = hemi(), hemi()
    usual.thickness[top(usual)] = 5.0
    elsewhere.thickness[elsewhere.pial_grid[:, 2] < 20 - 8.0] = 5.0
    assert cohort_thickness(data_with(_thick_at_the_top(), lh=usual)).findings == []
    (f,) = cohort_thickness(data_with(_thick_at_the_top(), lh=elsewhere)).findings
    assert f.grid[2] <= 12


def test_each_hemisphere_is_compared_with_its_own_statistics():
    left, right = hemi(), hemi()
    left.thickness[top(left)] = 5.0
    right.thickness[top(right)] = 5.0
    (f,) = cohort_thickness(data_with(_thick_at_the_top(), lh=left, rh=right)).findings
    assert f.hemi == "rh"


@pytest.mark.parametrize("spoil", [np.nan, np.inf, 0.0])
def test_a_registration_sphere_with_a_bad_vertex_leaves_that_hemisphere_out(spoil):
    bad, good = hemi(), hemi()
    bad.sphere = bad.sphere.copy()
    bad.sphere[5] = spoil
    good.thickness[top(good)] = 5.0
    result = cohort_thickness(data_with(cohort(), lh=bad, rh=good))
    assert result.status == "ran" and len(result.findings) == 1
    assert result.reason.startswith("lh not checked")


def test_a_hemisphere_with_no_cohort_values_is_reported_as_not_checked():
    c = cohort()
    c.median["lh"][:] = np.nan
    c.spread["lh"][:] = np.nan
    h = hemi()
    h.thickness[top(h)] = 5.0
    result = cohort_thickness(data_with(c, lh=h, rh=hemi()))
    assert result.findings == [] and result.reason.startswith("lh not checked")
    alone = cohort_thickness(data_with(c, lh=h))
    assert alone.status == "not run" and "no cohort values" in alone.reason


def test_partial_cohort_coverage_is_stated():
    from surfaceqa.sphere import target_points

    c = cohort()
    c.median["lh"][target_points()[:, 2] < 0] = np.nan  # the lower half has too few subjects
    result = cohort_thickness(data_with(c, lh=hemi(), rh=hemi()))
    assert result.status == "ran"
    assert "lh: cohort values at 5" in result.reason and "% of cortex vertices" in result.reason
    assert "rh" not in result.reason
