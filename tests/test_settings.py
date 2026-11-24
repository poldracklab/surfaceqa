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
