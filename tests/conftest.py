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


@pytest.fixture
def qa_planted(tmp_path) -> Path:
    """Built QA directory with indicator inputs: one FastSurfer subject with a planted error,
    one clean FastSurfer subject, one clean recon-all subject."""
    from surfaceqa.build import build_all
    from surfaceqa.discover import find_subjects
    from surfaceqa.site import write_site
    from tests.synth import write_qa_files

    shape = (64, 64, 64)
    planted = write_subject(tmp_path / "fastsurfer", shape=shape)
    write_qa_files(planted, plant={"ribbon_blob": ((0.0, 0.0, 16.0), 4.0)})
    write_qa_files(write_subject(tmp_path / "fastsurfer", name="sub-02", shape=shape))
    recon = write_subject(tmp_path / "freesurfer-8.2.0", pipeline="freesurfer", shape=shape)
    write_qa_files(recon, pipeline="freesurfer")
    qa_dir = tmp_path / "qa"
    build_all(find_subjects([tmp_path / "fastsurfer", tmp_path / "freesurfer-8.2.0"]), qa_dir)
    write_site(qa_dir)
    return qa_dir
