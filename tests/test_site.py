import json
import shutil

from surfaceqa.build import build_all
from surfaceqa.discover import find_subjects
from surfaceqa.site import write_site
from tests.synth import write_subject


def test_index_lists_every_subject(qa):
    html = (qa / "index.html").read_text()
    for key in ("fastsurfer__sub-01", "fastsurfer__sub-02", "freesurfer-8.2.0__sub-01"):
        assert f'href="subjects/{key}/index.html"' in html
    assert "fastsurfer 2.6.1" in html and "freesurfer 8.2.0" in html
    assert html.count(">ready<") == 2 and html.count(">missing files<") == 1


def test_subject_page_has_viewer_and_is_not_marked_reviewed(qa):
    html = (qa / "subjects" / "fastsurfer__sub-01" / "index.html").read_text()
    run = json.loads((qa / "subjects" / "fastsurfer__sub-01" / "current.json").read_text())["run"]
    assert html.count("<canvas") == 3
    assert f"runs/{run}/meta.json" in html
    assert "Not yet reviewed" in html
    assert "hold s: hide surfaces" in html


def test_missing_page_names_the_files(qa):
    html = (qa / "subjects" / "fastsurfer__sub-02" / "index.html").read_text()
    assert "surf/lh.white" in html and "<canvas" not in html


def test_static_files_are_copied(qa):
    assert {"logic.js", "viewer.js", "app.css"} <= {p.name for p in (qa / "static").iterdir()}


def test_write_site_needs_only_the_qa_dir(qa, synth_sources):
    shutil.rmtree(synth_sources[0])
    shutil.rmtree(synth_sources[1])
    write_site(qa)
    assert (qa / "index.html").exists()


def test_subject_names_are_html_escaped(tmp_path):
    subj = write_subject(tmp_path / "src", name="sub-<b>x")
    qa = tmp_path / "qa"
    build_all(find_subjects([subj]), qa)
    write_site(qa)
    assert "<b>x" not in (qa / "index.html").read_text()


def test_subject_page_has_a_slice_slider_per_view(qa):
    html = (qa / "subjects" / "fastsurfer__sub-01" / "index.html").read_text()
    assert html.count('type="range"') == 3


def test_subject_whose_latest_build_is_missing_files_is_not_shown_as_ready(qa, synth_sources):
    (synth_sources[0] / "sub-01" / "surf" / "rh.white").unlink()
    build_all(find_subjects(synth_sources), qa)
    write_site(qa)
    index = (qa / "index.html").read_text()
    assert index.count(">ready<") == 1 and index.count(">missing files<") == 2
    page = (qa / "subjects" / "fastsurfer__sub-01" / "index.html").read_text()
    assert "surf/rh.white" in page
    assert "shows the previous build" in page and page.count("<canvas") == 3


def test_subject_whose_latest_build_failed_is_not_shown_as_ready(qa, synth_sources):
    (synth_sources[0] / "sub-01" / "surf" / "rh.white").write_bytes(b"junk")
    build_all(find_subjects(synth_sources), qa)
    write_site(qa)
    index = (qa / "index.html").read_text()
    assert index.count(">ready<") == 1 and index.count(">build failed<") == 1
    page = (qa / "subjects" / "fastsurfer__sub-01" / "index.html").read_text()
    assert "shows the previous build" in page and "error.txt" in page


def test_subject_names_are_escaped_on_the_subject_page(tmp_path):
    subj = write_subject(tmp_path / "src", name="sub-<b>x")
    qa = tmp_path / "qa"
    build_all(find_subjects([subj]), qa)
    write_site(qa)
    assert "<b>x" not in (qa / "subjects" / "fastsurfer__sub-<b>x" / "index.html").read_text()
