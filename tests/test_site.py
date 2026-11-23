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


def test_places_to_look_are_explained_and_missed_gray_is_worded_as_a_possibility(tmp_path):
    subj = write_subject(tmp_path / "fastsurfer", shape=(64, 64, 64))
    write_qa_files(subj, plant={"seg_blob": ((0.0, 16.0, 0.0), 4.0)})  # network-made segmentation
    qa = tmp_path / "qa"
    build_all(find_subjects([subj]), qa)
    write_site(qa)
    page = html_lib.unescape((qa / "subjects" / "fastsurfer__sub-01" / "index.html").read_text())
    assert 'class="spot hint"' in page and "gray matter missed" not in page
    assert "usually sinus or dura" in page


# ---- review state on the pages -------------------------------------------------------------

import nibabel as nib

from surfaceqa.finalize import finalize
from surfaceqa.layout import current_run_dir
from surfaceqa.protocol import load_protocol
from surfaceqa.queue import blind_order
from surfaceqa.review_store import review_path, submit_review
from surfaceqa.site import View, render_index, render_subject, subject_records
from tests.reviewing import make_review

FIRST, SECOND, RECON = "fastsurfer__sub-01", "fastsurfer__sub-02", "freesurfer-8.2.0__sub-01"


def _view(reviewer=None, blind=False) -> View:
    return View(reviewer=reviewer, blind=blind, serving=True)


def _record(qa, key, view) -> dict:
    return next(r for r in subject_records(qa, view) if r["key"] == key)


def _page(qa, key, reviewer=None, blind=False) -> str:
    view = _view(reviewer, blind)
    return html_lib.unescape(render_subject(_record(qa, key, view), view))


def _index(qa, reviewer=None, blind=False) -> str:
    view = _view(reviewer, blind)
    return html_lib.unescape(render_index(subject_records(qa, view), view))


def _row(html: str, key: str) -> str:
    return next(row for row in html.split("<tr>") if f"subjects/{key}/" in row)


def test_static_index_lists_who_reviewed_each_subject(qa_reviewed):
    write_site(qa_reviewed)
    html = (qa_reviewed / "index.html").read_text()
    assert "ann, bob" in _row(html, FIRST)
    assert "ann" not in _row(html, SECOND)  # a draft is not a review
    assert "No subject has been reviewed yet" not in html


def test_static_subject_page_has_no_rating_controls_and_says_how_to_review(qa_reviewed):
    write_site(qa_reviewed)
    html = (qa_reviewed / "subjects" / FIRST / "index.html").read_text()
    assert 'type="radio"' not in html and "review.js" not in html and "review-data" not in html
    assert "surfaceqa serve" in html and "Reviewed by ann, bob" in html
    assert "Not yet reviewed" in (qa_reviewed / "subjects" / RECON / "index.html").read_text()


def test_named_reviewer_gets_rating_controls_for_all_eleven_items(qa_reviewed):
    html = _page(qa_reviewed, RECON, "cat")
    assert len(re.findall(r'<article class="item" data-item="', html)) == 11
    assert html.count('type="radio"') == 33
    assert html.count(">unrated<") == 11
    assert html.count('class="mark-here"') == 9
    assert 'id="grade"' in html and 'id="submit"' in html and 'id="skip"' in html
    assert 'id="remaining"' in html and "/next?after=" in html


def test_rating_labels_and_anchors_come_from_the_protocol(qa_reviewed):
    html = _page(qa_reviewed, RECON, "cat")
    protocol = load_protocol()
    for level in protocol["region_scale"] + protocol["pass_scale"]:
        assert level["label"] in html and level["anchor"] in html
    assert protocol["tie_rule"] in html
    assert all(f">{grade}</option>" in html for grade in protocol["grades"])


def test_saved_ratings_are_embedded_for_the_page(qa_reviewed):
    html = render_subject(_record(qa_reviewed, FIRST, _view("ann")), _view("ann"))
    data = json.loads(re.search(r'<script type="application/json" id="review-data">(.*?)</script>',
                                html, re.S).group(1))
    assert data["review"]["items"]["sinus"]["rating"] == "major"
    assert data["review"]["reviewer"] == "ann" and data["key"] == FIRST
    assert data["run"] == current_run_dir(qa_reviewed, FIRST).name
    assert data["missing"] == [] and data["protocol"]["version"] == 1


def test_a_new_reviewer_gets_an_empty_review_embedded(qa_reviewed):
    html = render_subject(_record(qa_reviewed, FIRST, _view("cat")), _view("cat"))
    data = json.loads(re.search(r'id="review-data">(.*?)</script>', html, re.S).group(1))
    assert data["review"]["items"]["sinus"]["rating"] is None and len(data["missing"]) == 12


def test_a_reviewer_who_has_not_submitted_does_not_get_others_ratings(qa_reviewed):
    finalize(qa_reviewed)
    for html in (_page(qa_reviewed, FIRST, "cat"), _index(qa_reviewed, "cat")):
        # the grade itself cannot be searched for: every grade is an option of the grade menu
        assert "bob-note-quux" not in html and '<td class="grade">C+</td>' not in html
        assert "ann-note-xyzzy" not in html and "mark-note-plugh" not in html
        assert "ann, bob" in html and "Other reviewers" not in html
    record = _record(qa_reviewed, FIRST, _view("cat"))
    assert record["others"] == [] and record["final"] is None and record["comparison"] is None


def test_a_reviewer_who_has_submitted_sees_the_others(qa_reviewed):
    html = _page(qa_reviewed, FIRST, "ann")
    assert "Other reviewers" in html and "bob-note-quux" in html and "<td>C+ " in html
    assert "ann-note-xyzzy" in html and "mark-note-plugh" in html


def test_without_a_name_everything_is_shown_read_only(qa_reviewed):
    html = _page(qa_reviewed, FIRST)
    assert "ann-note-xyzzy" in html and "bob-note-quux" in html and 'type="radio"' not in html
    assert 'action="/reviewer"' in html


def test_blind_page_hides_score_findings_and_hints_until_submitted(qa_reviewed):
    hidden = _page(qa_reviewed, FIRST, "cat", blind=True)
    assert "data-finding=" not in hidden and "Suspicion score" not in hidden
    assert "pial too far out ·" not in hidden and 'data-findings="off"' in hidden
    assert 'id="show-findings"' not in hidden
    assert "hidden until you submit your review (blind mode)" in hidden
    assert hidden.count('type="radio"') == 33
    shown = _page(qa_reviewed, FIRST, "ann", blind=True)
    assert "data-finding=" in shown and "Suspicion score" in shown
    assert 'data-findings="off"' not in shown


def test_blind_index_hides_scores_of_unsubmitted_subjects_and_is_shuffled_per_reviewer(qa_reviewed):
    cat = _index(qa_reviewed, "cat", blind=True)
    assert cat.count("hidden until you submit") == 3 and "pial too far out" not in cat
    assert re.findall(r'href="subjects/([^/]+)/index.html"', cat) == blind_order(
        [FIRST, SECOND, RECON], "cat")
    ann = _index(qa_reviewed, "ann", blind=True)
    assert ann.count("hidden until you submit") == 2 and "pial too far out" in _row(ann, FIRST)


def test_blind_without_a_name_shows_only_the_name_form(qa_reviewed):
    for html in (_index(qa_reviewed, blind=True), _page(qa_reviewed, FIRST, blind=True)):
        assert 'action="/reviewer"' in html and "Give your name" in html
        # the header may carry the address that was asked for, to return to after naming
        main = html.split("<main>")[1]
        assert "sub-0" not in main and "<canvas" not in main and "ann" not in main
        assert "<table" not in main and "review-data" not in html


def test_final_labels_are_shown_after_finalize(qa_reviewed):
    finalize(qa_reviewed)
    write_site(qa_reviewed)
    row = _row((qa_reviewed / "index.html").read_text(), FIRST)
    assert '<td class="grade">C+</td>' in row and '<td class="num fix">0</td>' in row
    page = html_lib.unescape((qa_reviewed / "subjects" / FIRST / "index.html").read_text())
    assert "Final" in page and "Reviewed by ann, bob" in page


def test_stale_final_is_flagged(qa_reviewed):
    finalize(qa_reviewed)
    run = current_run_dir(qa_reviewed, FIRST).name
    submit_review(qa_reviewed, make_review("cat", FIRST, run, grade="A"))
    row = _row(_index(qa_reviewed), FIRST)
    assert "run surfaceqa finalize again" in row and '<td class="grade">C+</td>' not in row


def test_disagreement_is_shown_on_the_index_and_the_subject_page(qa_reviewed):
    run = current_run_dir(qa_reviewed, RECON).name
    submit_review(qa_reviewed, make_review("ann", RECON, run, cerebellum="none"))
    submit_review(qa_reviewed, make_review("bob", RECON, run, cerebellum="major",
                                           marks=[{**make_mark("cerebellum")}]))
    finalize(qa_reviewed)
    assert "disagreement" in _row(_index(qa_reviewed), RECON)
    assert "in disagreement" in _page(qa_reviewed, RECON)


def make_mark(region: str) -> dict:
    from tests.reviewing import MARK
    return {**MARK, "region": region}


def test_ratings_of_an_earlier_run_are_shown_as_previous_run_and_subject_is_unreviewed(qa_reviewed):
    surface = qa_reviewed.parent / "fastsurfer" / "sub-01" / "surf" / "lh.pial"
    verts, faces, info = nib.freesurfer.read_geometry(surface, read_metadata=True)
    nib.freesurfer.write_geometry(surface, verts * 0.9, faces, volume_info=info)
    build_all(find_subjects([qa_reviewed.parent / "fastsurfer"]), qa_reviewed)
    record = _record(qa_reviewed, FIRST, _view("ann"))
    assert record["mine"] == "none" and record["reviewers"] == []
    html = _page(qa_reviewed, FIRST, "ann")
    assert "Previous run" in html and "The surfaces have changed since this review" in html
    assert "ann-note-xyzzy" in html and html.count(">unrated<") == 11
    assert "Previous run" not in _page(qa_reviewed, FIRST, "cat")


def test_unreadable_review_file_does_not_break_the_pages(qa_reviewed):
    run = current_run_dir(qa_reviewed, FIRST).name
    review_path(qa_reviewed, FIRST, run, "dan").write_text('{"items": {"trunc')
    review_path(qa_reviewed, FIRST, run, "eve").write_text('{"items": 3, "submitted": "x"}')
    assert "ann, bob" in _row(_index(qa_reviewed), FIRST)
    assert "Reviewed by ann, bob" in _page(qa_reviewed, FIRST)
    assert 'type="radio"' in _page(qa_reviewed, FIRST, "dan")


def test_index_shows_the_reviewers_own_progress_and_a_next_link(qa_reviewed):
    html = _index(qa_reviewed, "ann")
    assert "submitted" in _row(html, FIRST) and "draft" in _row(html, SECOND)
    assert "not started" in _row(html, RECON) and 'href="/next"' in html
    assert 'href="/next"' not in _index(qa_reviewed)


def test_review_script_is_loaded_only_when_reviewing(qa_reviewed):
    assert "static/review.js" in _page(qa_reviewed, FIRST, "cat")
    assert "static/review.js" not in _page(qa_reviewed, FIRST)


def test_help_panel_lists_the_rating_keys(qa_reviewed):
    html = _page(qa_reviewed, FIRST, "cat")
    help_panel = re.search(r'<div id="help".*?</div>', html, re.S).group(0)
    for words in ("1 2 3", "j / k", "Shift+N", "hold s", "n / p", "?"):
        assert words in help_panel
    assert " hidden" in help_panel.split(">")[0]


def test_keys_line_mentions_rating_keys(qa_reviewed):
    html = _page(qa_reviewed, FIRST, "cat")
    assert "1 2 3: rate" in html and "?: all keys" in html
    assert "1 2 3: rate" not in _page(qa_reviewed, FIRST)
