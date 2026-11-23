import csv

from surfaceqa.build import build_all
from surfaceqa.discover import find_subjects
from surfaceqa.export import export_tables
from surfaceqa.finalize import finalize
from surfaceqa.layout import current_run_dir
from surfaceqa.review_store import submit_review
from tests.reviewing import make_review

FIRST, SECOND, RECON = "fastsurfer__sub-01", "fastsurfer__sub-02", "freesurfer-8.2.0__sub-01"


def _table(qa, name) -> list[dict]:
    with open(qa / "export" / f"{name}.tsv", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_export_writes_four_tables(qa_reviewed):
    paths = export_tables(qa_reviewed)
    assert sorted(p.name for p in paths) == ["final.tsv", "indicators.tsv", "marks.tsv", "ratings.tsv"]
    assert all(p.parent == qa_reviewed / "export" for p in paths)


def test_export_to_another_folder(qa_reviewed, tmp_path):
    paths = export_tables(qa_reviewed, tmp_path / "tables")
    assert all(p.parent == tmp_path / "tables" and p.is_file() for p in paths)


def test_ratings_table_has_one_row_per_submitted_review_and_item(qa_reviewed):
    export_tables(qa_reviewed)
    rows = _table(qa_reviewed, "ratings")
    assert list(rows[0]) == ["key", "source", "subject", "pipeline", "version", "run", "current_run",
                             "reviewer", "protocol", "submitted", "revised", "item", "rating", "note"]
    assert len(rows) == 24 and {r["reviewer"] for r in rows} == {"ann", "bob"}
    assert {r["key"] for r in rows} == {FIRST}  # ann's draft of sub-02 is not exported
    ann_sinus = next(r for r in rows if r["reviewer"] == "ann" and r["item"] == "sinus")
    assert ann_sinus["rating"] == "major" and ann_sinus["note"] == "ann-note-xyzzy"
    assert ann_sinus["source"] == "fastsurfer" and ann_sinus["subject"] == "sub-01"
    assert ann_sinus["pipeline"] == "fastsurfer" and ann_sinus["current_run"] == "yes"
    assert ann_sinus["protocol"] == "1" and ann_sinus["revised"] == "no"


def test_grade_is_exported_as_the_overall_item(qa_reviewed):
    export_tables(qa_reviewed)
    overall = {r["reviewer"]: r for r in _table(qa_reviewed, "ratings") if r["item"] == "overall"}
    assert overall["ann"]["rating"] == "C" and overall["bob"]["rating"] == "C+"
    assert overall["bob"]["note"] == "bob-note-quux"


def test_unratable_review_has_an_unratable_row(qa_reviewed):
    run = current_run_dir(qa_reviewed, RECON).name
    review = make_review("cat", RECON, run, grade=None, unratable="severe motion")
    submit_review(qa_reviewed, review)
    export_tables(qa_reviewed)
    rows = [r for r in _table(qa_reviewed, "ratings") if r["reviewer"] == "cat"]
    assert len(rows) == 13
    assert [r["note"] for r in rows if r["item"] == "unratable"] == ["severe motion"]


def test_notes_with_tabs_and_newlines_stay_on_one_row(qa_reviewed):
    run = current_run_dir(qa_reviewed, RECON).name
    review = make_review("cat", RECON, run)
    review["notes"] = "line one\nline\ttwo\r\nthree"
    submit_review(qa_reviewed, review)
    export_tables(qa_reviewed)
    text = (qa_reviewed / "export" / "ratings.tsv").read_text()
    assert len(text.splitlines()) == 1 + 36
    assert "line one line two  three" in text


def test_marks_table_has_one_row_per_mark_with_coordinates(qa_reviewed):
    export_tables(qa_reviewed)
    rows = _table(qa_reviewed, "marks")
    assert list(rows[0]) == ["key", "run", "current_run", "reviewer", "region", "kind", "surface",
                             "vertex", "grid_x", "grid_y", "grid_z", "tkr_x", "tkr_y", "tkr_z",
                             "finding", "note"]
    assert len(rows) == 1
    mark = rows[0]
    assert (mark["reviewer"], mark["region"], mark["kind"]) == ("ann", "sinus", "pial_out")
    assert (mark["surface"], mark["vertex"], mark["finding"]) == ("lh.pial", "5", "")
    assert [mark["grid_x"], mark["grid_y"], mark["grid_z"]] == ["16.0", "20.0", "30.0"]
    assert mark["tkr_z"] == "6.0" and mark["note"] == "mark-note-plugh"


def test_final_table_is_written_after_finalize_and_marks_stale_finals(qa_reviewed):
    export_tables(qa_reviewed)
    assert _table(qa_reviewed, "final") == []
    finalize(qa_reviewed)
    export_tables(qa_reviewed)
    rows = _table(qa_reviewed, "final")
    assert list(rows[0]) == ["key", "run", "status", "reviewers", "item", "final", "disagree"]
    first = {r["item"]: r for r in rows if r["key"] == FIRST}
    assert len(first) == 13 and first["sinus"]["final"] == "minor" and first["overall"]["final"] == "C+"
    assert first["sinus"]["status"] == "agreed" and first["sinus"]["reviewers"] == "ann,bob"
    assert first["unratable"]["final"] == "no" and first["sinus"]["disagree"] == "no"
    assert {r["status"] for r in rows if r["key"] == RECON} == {"unreviewed"}
    run = current_run_dir(qa_reviewed, FIRST).name
    submit_review(qa_reviewed, make_review("cat", FIRST, run, sinus="none"))
    export_tables(qa_reviewed)
    assert {r["status"] for r in _table(qa_reviewed, "final") if r["key"] == FIRST} == {"stale"}


def test_indicator_table_has_a_row_per_indicator_and_the_score(qa_reviewed):
    export_tables(qa_reviewed)
    rows = _table(qa_reviewed, "indicators")
    assert list(rows[0]) == ["key", "source", "subject", "pipeline", "version", "run", "score",
                             "indicator", "status", "n_findings", "reason"]
    first = [r for r in rows if r["key"] == FIRST]
    assert len(first) == 9 and float(first[0]["score"]) > 0
    outside = next(r for r in first if r["indicator"] == "ribbon_outside_brain")
    assert outside["status"] == "ran" and int(outside["n_findings"]) >= 1


def test_subject_without_indicator_results_has_one_not_computed_row(qa):
    export_tables(qa)
    rows = [r for r in _table(qa, "indicators") if r["key"] == "fastsurfer__sub-02"]
    assert len(rows) == 1 and rows[0]["status"] == "not computed" and rows[0]["indicator"] == ""


def test_export_without_any_review_writes_headers_only(qa_planted):
    export_tables(qa_planted)
    for name in ("ratings", "marks", "final"):
        assert len((qa_planted / "export" / f"{name}.tsv").read_text().splitlines()) == 1


def test_ratings_of_an_earlier_run_are_exported_as_not_current(qa_reviewed):
    import nibabel as nib

    surface = qa_reviewed.parent / "fastsurfer" / "sub-01" / "surf" / "lh.pial"
    verts, faces, info = nib.freesurfer.read_geometry(surface, read_metadata=True)
    nib.freesurfer.write_geometry(surface, verts * 0.9, faces, volume_info=info)
    build_all(find_subjects([qa_reviewed.parent / "fastsurfer"]), qa_reviewed)
    export_tables(qa_reviewed)
    assert {r["current_run"] for r in _table(qa_reviewed, "ratings")} == {"no"}
    assert {r["current_run"] for r in _table(qa_reviewed, "marks")} == {"no"}
