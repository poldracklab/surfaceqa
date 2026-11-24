import pytest

from surfaceqa.settings import rerun_template, save_rerun_template

TEMPLATE = "docker run --gpus all -v /data:/data img {command}"


def test_template_round_trip(tmp_path):
    save_rerun_template(tmp_path, ["fastsurfer"], TEMPLATE)
    assert rerun_template(tmp_path, "fastsurfer") == TEMPLATE
    assert rerun_template(tmp_path, "freesurfer-8.2.0") is None


def test_templates_of_different_builds_are_both_kept(tmp_path):
    save_rerun_template(tmp_path, ["fastsurfer"], TEMPLATE)
    save_rerun_template(tmp_path, ["freesurfer-8.2.0", "other"], "ssh box {command}")
    assert rerun_template(tmp_path, "fastsurfer") == TEMPLATE
    assert rerun_template(tmp_path, "other") == "ssh box {command}"


def test_no_settings_file(tmp_path):
    assert rerun_template(tmp_path, "fastsurfer") is None


@pytest.mark.parametrize("content", ["not json", "[1]", '{"rerun_templates": [1]}',
                                     '{"rerun_templates": {"fastsurfer": 3}}'])
def test_malformed_settings_are_ignored_and_replaced(tmp_path, content):
    (tmp_path / "settings.json").write_text(content)
    assert rerun_template(tmp_path, "fastsurfer") is None
    save_rerun_template(tmp_path, ["fastsurfer"], TEMPLATE)
    assert rerun_template(tmp_path, "fastsurfer") == TEMPLATE


def test_a_stored_template_without_the_placeholder_is_ignored(tmp_path):
    import json
    from surfaceqa.settings import rerun_template

    (tmp_path / "settings.json").write_text(json.dumps(
        {"rerun_templates": {"a": "docker run image", "b": "docker run image {command}"}}))
    assert rerun_template(tmp_path, "a") is None
    assert rerun_template(tmp_path, "b") == "docker run image {command}"


def test_sources_and_templates_do_not_erase_each_other(tmp_path):
    from surfaceqa.settings import save_sources, sources

    save_sources(tmp_path, [tmp_path / "a"])
    save_rerun_template(tmp_path, ["a"], TEMPLATE)
    assert sources(tmp_path) == [(tmp_path / "a").resolve()]
    save_sources(tmp_path, [tmp_path / "b"])
    assert rerun_template(tmp_path, "a") == TEMPLATE
    assert sources(tmp_path) == [(tmp_path / "a").resolve(), (tmp_path / "b").resolve()]


def test_a_source_is_recorded_once(tmp_path):
    from surfaceqa.settings import save_sources, sources

    save_sources(tmp_path, [tmp_path / "a", tmp_path / "b"])
    save_sources(tmp_path, [tmp_path / "b", tmp_path / "c", tmp_path / "c"])
    assert [p.name for p in sources(tmp_path)] == ["a", "b", "c"]


@pytest.mark.parametrize("content", [None, "not json", "[1]", '{"sources": 3}', '{"sources": [1, "/x"]}'])
def test_sources_of_missing_or_malformed_settings(tmp_path, content):
    from pathlib import Path

    from surfaceqa.settings import sources

    if content is not None:
        (tmp_path / "settings.json").write_text(content)
    assert sources(tmp_path) == ([Path("/x")] if content and "/x" in content else [])
