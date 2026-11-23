import pytest

from surfaceqa.discover import find_subjects
from tests.synth import write_subject


def test_find_subjects_lists_folders_with_mri_and_surf(synth_sources):
    refs = find_subjects(synth_sources)
    assert [r.key for r in refs] == ["fastsurfer__sub-01", "freesurfer-8.2.0__sub-01"]


def test_same_name_in_two_sources_has_distinct_keys(synth_sources):
    refs = find_subjects(synth_sources)
    assert len({r.key for r in refs}) == 2


def test_find_subjects_accepts_a_single_subject_folder(synth_subject):
    refs = find_subjects([synth_subject])
    assert [(r.source, r.name) for r in refs] == [("fastsurfer", "sub-01")]


def test_find_subjects_skips_non_subject_folders(synth_sources):
    (synth_sources[0] / "QA").mkdir()
    (synth_sources[0] / "fsaverage").mkdir()
    assert all(r.name == "sub-01" for r in find_subjects(synth_sources))


def test_find_subjects_filters_by_shell_pattern(synth_sources):
    write_subject(synth_sources[0], name="sub-02")
    refs = find_subjects(synth_sources, patterns=["sub-02"])
    assert [r.name for r in refs] == ["sub-02"]


def test_a_subject_named_twice_is_listed_once(synth_sources):
    refs = find_subjects([synth_sources[0], synth_sources[0] / "sub-01"])
    assert [r.key for r in refs] == ["fastsurfer__sub-01"]


def test_two_different_folders_with_the_same_key_are_refused(tmp_path):
    a = write_subject(tmp_path / "siteA" / "freesurfer").parent
    b = write_subject(tmp_path / "siteB" / "freesurfer").parent
    with pytest.raises(ValueError, match="freesurfer__sub-01"):
        find_subjects([a, b])
