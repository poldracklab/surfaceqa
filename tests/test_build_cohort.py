"""The cohort pass of the build: every subject compared with the others of its source folder."""

import pytest

from surfaceqa.build import build_all, build_subject
from surfaceqa.cohort import load_cohort
from surfaceqa.discover import find_subjects
from surfaceqa.layout import current_run_dir
from surfaceqa.qa import load_findings
from surfaceqa.thickness_map import load_thickness_map
from tests.synth import write_qa_files, write_subject

PATCH = ("lh", (0.0, 0.0, 10.0), 7.0)  # about 80 of the 642 vertices
PLANTED = "sub-03"


@pytest.fixture(autouse=True)
def small_cohorts(monkeypatch):
    monkeypatch.setattr("surfaceqa.thresholds.MIN_COHORT", 5)


def _add_subject(source, i: int, planted: bool = False):
    subj = write_subject(source, name=f"sub-{i:02d}")
    plant = {"thickness": 2.0 + 0.05 * i, **({"thick_patch": PATCH} if planted else {})}
    write_qa_files(subj, plant=plant)
    return subj


@pytest.fixture
def source(tmp_path):
    """Six subjects whose thickness differs a little; sub-03 has a planted thick patch."""
    folder = tmp_path / "fs"
    for i in range(6):
        _add_subject(folder, i, planted=(f"sub-{i:02d}" == PLANTED))
    return folder


def _cohort_indicator(qa, key) -> dict:
    return next(i for i in load_findings(qa, key)["indicators"] if i["name"] == "cohort_thickness")


def _cohort_findings(qa, key) -> list[dict]:
    return [f for f in load_findings(qa, key)["findings"] if f["indicator"] == "cohort_thickness"]


def _build(source, qa, jobs=1):
    return {r.key: r.status for r in build_all(find_subjects([source]), qa, jobs=jobs)}


@pytest.mark.parametrize("jobs", [1, 2])
def test_only_the_subject_with_the_planted_patch_stands_out(source, tmp_path, jobs):
    qa = tmp_path / "qa"
    statuses = _build(source, qa, jobs)
    assert set(statuses.values()) == {"built"} and len(statuses) == 6
    for key in statuses:
        assert _cohort_indicator(qa, key)["status"] == "ran"
        assert len(_cohort_findings(qa, key)) == (1 if key.endswith(PLANTED) else 0)
    (finding,) = _cohort_findings(qa, f"fs__{PLANTED}")
    assert finding["hemi"] == "lh" and finding["region"]
    assert load_cohort(qa, "fs").n == 6


def test_too_few_subjects_are_not_compared_and_the_page_data_says_so(source, tmp_path):
    qa = tmp_path / "qa"
    refs = find_subjects([source])[:4]
    build_all(refs, qa)
    for ref in refs:
        listed = _cohort_indicator(qa, ref.key)
        assert listed["status"] == "not run" and "there are 4" in listed["reason"]


def test_second_build_changes_nothing(source, tmp_path):
    qa = tmp_path / "qa"
    _build(source, qa)
    path = current_run_dir(qa, "fs__sub-00") / "findings.json"
    stamp = path.stat().st_mtime_ns
    assert set(_build(source, qa).values()) == {"unchanged"}
    assert path.stat().st_mtime_ns == stamp


def test_a_new_subject_recompares_the_whole_folder(source, tmp_path):
    qa = tmp_path / "qa"
    _build(source, qa)
    _add_subject(source, 6)
    statuses = _build(source, qa)
    assert statuses.pop("fs__sub-06") == "built"
    assert set(statuses.values()) == {"updated"} and len(statuses) == 6
    assert len(_cohort_findings(qa, f"fs__{PLANTED}")) == 1


def test_a_subject_that_loses_its_registration_loses_its_cohort_findings(source, tmp_path):
    qa = tmp_path / "qa"
    _build(source, qa)
    for hemi in ("lh", "rh"):
        (source / PLANTED / "surf" / f"{hemi}.sphere.reg").unlink()
    statuses = _build(source, qa)
    assert set(statuses.values()) == {"updated"}
    assert _cohort_findings(qa, f"fs__{PLANTED}") == []
    assert _cohort_indicator(qa, f"fs__{PLANTED}")["status"] == "not run"
    assert load_cohort(qa, "fs").n == 5 and _cohort_indicator(qa, "fs__sub-00")["status"] == "ran"


def test_a_folder_that_falls_below_the_minimum_drops_its_findings(source, tmp_path):
    qa = tmp_path / "qa"
    _build(source, qa)
    for name in ("sub-00", "sub-01"):
        for hemi in ("lh", "rh"):
            (source / name / "surf" / f"{hemi}.sphere.reg").unlink()
    _build(source, qa)
    assert _cohort_findings(qa, f"fs__{PLANTED}") == []
    assert "there are 4" in _cohort_indicator(qa, f"fs__{PLANTED}")["reason"]


def test_a_failed_cohort_pass_keeps_the_viewers_and_the_other_indicators(source, tmp_path, monkeypatch):
    monkeypatch.setattr("surfaceqa.build.update_cohorts", lambda qa_dir: 1 / 0)
    qa = tmp_path / "qa"
    statuses = _build(source, qa)
    assert set(statuses.values()) == {"built"}
    assert _cohort_indicator(qa, "fs__sub-00")["status"] == "not run"
    ran = [i for i in load_findings(qa, "fs__sub-00")["indicators"] if i["status"] == "ran"]
    assert len(ran) >= 5
    assert "ZeroDivisionError" in (qa / "cohort" / "error.txt").read_text()


def test_build_subject_alone_writes_the_map_and_uses_the_stored_cohort(source, tmp_path):
    qa = tmp_path / "qa"
    ref = next(r for r in find_subjects([source]) if r.name == PLANTED)
    assert build_subject(ref, qa).status == "built"
    assert set(load_thickness_map(current_run_dir(qa, ref.key))) == {"lh", "rh"}
    assert "there are 0" in _cohort_indicator(qa, ref.key)["reason"]
    _build(source, qa)
    assert build_subject(ref, qa).status == "unchanged"
    assert len(_cohort_findings(qa, ref.key)) == 1


def test_the_cohort_pass_never_writes_into_the_source(source, tmp_path):
    before = {p: p.stat().st_mtime_ns for p in source.rglob("*")}
    _build(source, tmp_path / "qa", jobs=2)
    assert {p: p.stat().st_mtime_ns for p in source.rglob("*")} == before
