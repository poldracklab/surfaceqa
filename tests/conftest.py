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


@pytest.fixture
def qa(synth_sources, tmp_path) -> Path:
    """A built QA directory: two complete subjects and one with a missing surface."""
    from surfaceqa.build import build_all
    from surfaceqa.discover import find_subjects
    from surfaceqa.site import write_site

    write_subject(synth_sources[0], name="sub-02", omit=("surf/lh.white",))
    qa_dir = tmp_path / "qa"
    build_all(find_subjects(synth_sources), qa_dir)
    write_site(qa_dir)
    return qa_dir
