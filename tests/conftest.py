from pathlib import Path

import pytest

from tests.synth import write_subject


@pytest.fixture
def synth_subject(tmp_path) -> Path:
    return write_subject(tmp_path / "fastsurfer")


@pytest.fixture
def synth_sources(tmp_path) -> list[Path]:
    write_subject(tmp_path / "fastsurfer")
    write_subject(tmp_path / "freesurfer-8.2.0", pipeline="freesurfer")
    return [tmp_path / "fastsurfer", tmp_path / "freesurfer-8.2.0"]
