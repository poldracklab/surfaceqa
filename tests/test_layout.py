import os

import pytest

from surfaceqa.layout import replace_text


def test_replace_text_writes_the_file_and_leaves_nothing_else(tmp_path):
    replace_text(tmp_path / "a.json", "one")
    replace_text(tmp_path / "a.json", "two")
    assert (tmp_path / "a.json").read_text() == "two"
    assert [p.name for p in tmp_path.iterdir()] == ["a.json"]


def test_a_failed_write_keeps_the_old_content(tmp_path, monkeypatch):
    replace_text(tmp_path / "a.json", "old")

    def broken(*args):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(OSError):
        replace_text(tmp_path / "a.json", "new")
    assert (tmp_path / "a.json").read_text() == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["a.json"]
