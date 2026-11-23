import html as html_lib
import json
import re
import shutil

from surfaceqa.build import build_all
from surfaceqa.discover import find_subjects
from surfaceqa.site import write_site
from tests.synth import write_qa_files, write_subject


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
    assert "<b>x" not in (qa / "subjects" / "src__sub-<b>x" / "index.html").read_text()


def test_index_orders_by_score_within_pipeline(qa_planted):
    html = (qa_planted / "index.html").read_text()
    rows = re.findall(r'href="subjects/([^/]+)/index.html"', html)
    assert rows == ["fastsurfer__sub-01", "fastsurfer__sub-02", "freesurfer-8.2.0__sub-01"]
    assert "1 of 2" in html and "2 of 2" in html and "1 of 1" in html
    assert "pial too far out" in html and "it does not mean a subject is good or bad" in html


def test_subject_page_has_checklist_in_order(qa_planted):
    html = html_lib.unescape((qa_planted / "subjects" / "fastsurfer__sub-01" / "index.html").read_text())
    titles = ["Bird's-eye view", "T1 quality", "Sagittal and transverse sinus",
              "Cortex / cerebellum interface", "Frontal midline", "Inferior frontal and orbitofrontal",
              "Inferior temporal, near the ear canal", "Medial temporal, hippocampus",
              "Outer edge of the brain", "White surface", "Hemispheres crossing"]
    positions = [html.index(f">{title}<") for title in titles]
    assert positions == sorted(positions)
    assert "Suspicion score" in html and "a low score does not mean the surfaces are correct" in html
    assert html.count("data-finding=") >= 1 and "pial too far out" in html


def test_regions_without_findings_say_look_anyway_and_never_ok(qa_planted):
    html = (qa_planted / "subjects" / "fastsurfer__sub-02" / "index.html").read_text()
    assert html.count("No indicator fired here. Look anyway") == 9
    assert not re.search(r"\bOK\b|no problems|looks fine|passed", html, re.I)


def test_not_run_indicators_are_listed_with_reasons(qa_planted):
    html = (qa_planted / "subjects" / "freesurfer-8.2.0__sub-01" / "index.html").read_text()
    assert "Not run for this subject:" in html and "ribbon_in_nonbrain_mask" in html and "sinus or dura" in html


def test_subject_without_indicator_inputs_says_what_was_not_run(qa):
    html = (qa / "subjects" / "fastsurfer__sub-01" / "index.html").read_text()
    assert "Not run for this subject:" in html and "no ribbon.mgz" in html


def test_subject_whose_indicators_failed_says_so(qa_planted):
    folder = qa_planted / "subjects" / "fastsurfer__sub-02"
    run = json.loads((folder / "current.json").read_text())["run"]
    (folder / "runs" / run / "findings.json").unlink()
    (folder / "runs" / run / "qa_error.txt").write_text("boom")
    write_site(qa_planted)
    html = (folder / "index.html").read_text()
    assert "The automated indicators failed for this subject" in html
    assert html.count("data-region=") == 9 and html.count("No indicator fired here. Look anyway") == 0
    assert html.count("Look through this region") == 9
    assert "not computed" in (qa_planted / "index.html").read_text()


def test_index_says_how_many_indicators_did_not_run(qa_planted):
    html = (qa_planted / "index.html").read_text()
    assert html.count("2 of 9 not run") == 3


def test_subject_with_no_indicator_run_is_not_ranked_as_zero(qa):
    html = (qa / "index.html").read_text()
    assert html.count("not computed") == 3 and " of 2<" not in html
    page = (qa / "subjects" / "fastsurfer__sub-01" / "index.html").read_text()
    assert "No indicator could run for this subject" in page and "Suspicion score" not in page


def test_subjects_are_ranked_within_their_source_folder(tmp_path):
    for site in ("siteA-fs6", "siteB-fs8"):
        write_qa_files(write_subject(tmp_path / site, pipeline="freesurfer", shape=(64, 64, 64)),
                       pipeline="freesurfer")
    qa = tmp_path / "qa"
    build_all(find_subjects([tmp_path / "siteA-fs6", tmp_path / "siteB-fs8"]), qa)
    write_site(qa)
    html = (qa / "index.html").read_text()
    assert html.count("1 of 1") == 2 and "of 2" not in html
    assert "rank 1 of 1 in siteA-fs6" in (qa / "subjects" / "siteA-fs6__sub-01" / "index.html").read_text()


def test_checklist_sits_beside_the_viewer(qa_planted):
    html = (qa_planted / "subjects" / "fastsurfer__sub-01" / "index.html").read_text()
    assert re.search(r'<div class="workspace">\s*<section class="viewer" id="viewer".*?</section>\s*'
                     r'<aside id="checklist" class="sidebar">.*?</aside>\s*</div>', html, re.S)
    aside = html[html.index('<aside id="checklist"'):html.index("</aside>")]
    assert aside.count("data-region=") == 9 and "data-finding=" in aside
    assert 'data-scroll="contours"' in aside and 'data-scroll="t1"' in aside


def test_whole_brain_pass_is_a_single_large_scrollable_view(qa_planted):
    """The bird's-eye and T1 passes scroll one large view (coronal first), not a grid of thumbnails."""
    html = (qa_planted / "subjects" / "fastsurfer__sub-01" / "index.html").read_text()
    viewer = html[html.index('<section class="viewer"'):html.index("</section>", html.index('<section class="viewer"'))]
    layouts = re.findall(r'data-layout="(\w+)"', viewer)
    assert layouts == ["three", "coronal", "sagittal", "axial"]
    assert "montage" not in html
    aside = html[html.index('<aside id="checklist"'):html.index("</aside>")]
    assert ">Scroll through all slices<" in aside and ">Scroll through all slices, T1 only<" in aside
    assert "n / p: next / previous location" in viewer


def test_places_to_look_are_listed_separately_and_not_counted(tmp_path):
    subj = write_subject(tmp_path / "fs6", pipeline="freesurfer", shape=(64, 64, 64))
    write_qa_files(subj, pipeline="freesurfer", plant={"seg_blob": ((0.0, 16.0, 0.0), 4.0)})
    qa = tmp_path / "qa"
    build_all(find_subjects([subj]), qa)
    write_site(qa)
    page = html_lib.unescape((qa / "subjects" / "fs6__sub-01" / "index.html").read_text())
    assert "Places to look (not counted in the score):" in page
    assert re.search(r'class="spot hint"[^>]*>cortex label outside the pial surface · \d+ mm³<', page)
    assert "Suspicion score 0.0" in page
    row = (qa / "index.html").read_text()
    assert re.search(r'<td class="num">0</td><td></td>', row)  # no findings, nothing "largest"
