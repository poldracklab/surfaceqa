from pathlib import Path

import pytest

from tests.synth import write_subject


@pytest.fixture(autouse=True)
def surfaceqa_home(tmp_path_factory, monkeypatch) -> Path:
    """No test reads or writes the real list of recent projects."""
    home = tmp_path_factory.mktemp("surfaceqa_home")
    monkeypatch.setenv("SURFACEQA_HOME", str(home))
    return home


@pytest.fixture
def synth_subject(tmp_path) -> Path:
    return write_subject(tmp_path / "fastsurfer")


@pytest.fixture
def synth_sources(tmp_path) -> list[Path]:
    write_subject(tmp_path / "fastsurfer")
    write_subject(tmp_path / "freesurfer-8.2.0", pipeline="freesurfer")
    return [tmp_path / "fastsurfer", tmp_path / "freesurfer-8.2.0"]


@pytest.fixture
def many(tmp_path) -> Path:
    """A source with enough subjects that a build can be stopped in the middle."""
    for i in range(12):
        write_subject(tmp_path / "study", name=f"sub-{i:02d}")
    return tmp_path / "study"


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


@pytest.fixture
def qa_reviewed(qa_planted) -> Path:
    """qa_planted with reviews: ann (sinus major, one mark, grade C) and bob (sinus minor,
    grade C+) submitted fastsurfer__sub-01; ann has a draft of fastsurfer__sub-02."""
    from surfaceqa.layout import current_run_dir
    from surfaceqa.review_store import save_review, submit_review
    from tests.reviewing import MARK, make_review

    first, second = "fastsurfer__sub-01", "fastsurfer__sub-02"
    run = current_run_dir(qa_planted, first).name
    ann = make_review("ann", first, run, grade="C", sinus="major",
                      marks=[{**MARK, "note": "mark-note-plugh"}])
    ann["items"]["sinus"]["note"] = "ann-note-xyzzy"
    submit_review(qa_planted, ann)
    bob = make_review("bob", first, run, grade="C+", sinus="minor")
    bob["notes"] = "bob-note-quux"
    submit_review(qa_planted, bob)
    draft = make_review("ann", second, current_run_dir(qa_planted, second).name, submitted=False)
    save_review(qa_planted, draft)
    return qa_planted
