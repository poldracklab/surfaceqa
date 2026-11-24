"""The report page and its tables, made from a QA directory."""

import csv

import pytest

from surfaceqa.build import build_all
from surfaceqa.discover import find_subjects
from surfaceqa.report import REPORT_DIR, TABLES, subject_facts, write_report
from surfaceqa.summary import progress, region_ratings
from tests.synth import write_qa_files, write_subject

FIRST, SECOND, RECON = "fastsurfer__sub-01", "fastsurfer__sub-02", "freesurfer-8.2.0__sub-01"


def _table(qa, name) -> list[dict]:
    with open(qa / REPORT_DIR / name, newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _snapshot(qa) -> dict:
    return {str(p.relative_to(qa)): p.stat().st_mtime_ns for folder in ("ratings", "final", "subjects")
            for p in (qa / folder).rglob("*") if p.is_file()}


def test_facts_hold_the_combined_reviews_and_the_findings(qa_reviewed):
    facts = {fact["key"]: fact for fact in subject_facts(qa_reviewed)}
    assert set(facts) == {FIRST, SECOND, RECON}
    first = facts[FIRST]
    assert first["final"]["reviewers"] == ["ann", "bob"] and first["drafts"] == 0
    assert first["final"]["items"]["sinus"]["final"] == "minor"  # major and minor: the lower
    assert first["findings"]["score"] > 0 and first["source"] == "fastsurfer"
    assert first["href"] == f"../subjects/{FIRST}/index.html"
    assert facts[SECOND]["drafts"] == 1 and facts[SECOND]["final"]["status"] == "unreviewed"


def test_report_page_and_tables_are_written(qa_reviewed):
    before = _snapshot(qa_reviewed)
    page = write_report(qa_reviewed)
    assert page == qa_reviewed / REPORT_DIR / "index.html" and page.is_file()
    assert sorted(p.name for p in page.parent.iterdir()) == sorted(["index.html", *TABLES])
    assert _snapshot(qa_reviewed) == before  # reviews, final labels and subject pages untouched
    html = page.read_text()
    assert "fastsurfer" in html and "freesurfer-8.2.0" in html
    assert "<script" not in html and "http" not in html  # stands alone, opens from disk
    assert f'href="../subjects/{FIRST}/index.html"' in html


def test_region_table_matches_the_summary(qa_reviewed):
    write_report(qa_reviewed)
    rows = _table(qa_reviewed, "region_ratings.tsv")
    assert list(rows[0]) == ["source", "item", "level", "subjects"]
    facts = [f for f in subject_facts(qa_reviewed) if f["source"] == "fastsurfer"]
    expected = {(row["item"], level): n for row in region_ratings(facts)
                for level, n in row["counts"].items()}
    found = {(r["item"], r["level"]): int(r["subjects"]) for r in rows if r["source"] == "fastsurfer"}
    assert found == expected and found[("sinus", "minor")] == 1 and found[("sinus", "unreviewed")] == 1


def test_problem_and_agreement_tables(qa_reviewed):
    write_report(qa_reviewed)
    kinds = _table(qa_reviewed, "problem_kinds.tsv")
    assert list(kinds[0]) == ["source", "region", "kind", "subjects", "marks"]
    cell = next(r for r in kinds if (r["source"], r["region"], r["kind"]) == ("fastsurfer", "sinus", "pial_out"))
    assert (cell["subjects"], cell["marks"]) == ("1", "1")
    agree = _table(qa_reviewed, "indicator_agreement.tsv")
    assert list(agree[0]) == ["source", "region", "finding", "rating", "subjects"]
    assert {r["finding"] for r in agree} == {"yes", "no"}
    assert sum(int(r["subjects"]) for r in agree if (r["source"], r["region"]) == ("fastsurfer", "sinus")) == 1


def test_no_reviewer_names_or_notes_on_the_page(qa_reviewed):
    html = write_report(qa_reviewed).read_text()
    for private in ("ann", "bob", "ann-note-xyzzy", "bob-note-quux", "mark-note-plugh"):
        assert private not in html, private


def test_source_without_reviews_says_so_and_shows_the_indicators(qa_reviewed):
    html = write_report(qa_reviewed).read_text()
    recon = html[html.index('id="source-freesurfer-8.2.0"'):]
    assert "No submitted reviews yet." in recon
    assert "Automated indicators" in recon and "not judgments" in recon
    assert "ribbon_outside_brain" in recon
    fast = html[html.index('id="source-fastsurfer"'):html.index('id="source-freesurfer-8.2.0"')]
    assert "No submitted reviews yet." not in fast and "Ratings by region" in fast
    assert "1 draft" in fast and "not counted" in fast


def test_a_directory_without_any_review_never_reads_as_no_errors(qa_planted):
    html = write_report(qa_planted).read_text()
    assert html.count("No submitted reviews yet.") == 2
    for misleading in ("Ratings by region", "Marked problems", "Subjects by region", "0 major", "no errors"):
        assert misleading not in html, misleading
    assert progress(subject_facts(qa_planted))["reviewed"] == 0
    assert "0 of 3 subjects reviewed" in html
    assert all(int(r["subjects"]) == 0 for r in _table(qa_planted, "region_ratings.tsv")
               if r["level"] != "unreviewed")


def test_names_are_escaped_on_the_page_and_harmless_in_the_tables(tmp_path):
    subj = write_subject(tmp_path / "fs", name="a<b>&x", pipeline="freesurfer", shape=(64, 64, 64))
    write_qa_files(subj, pipeline="freesurfer")
    qa = tmp_path / "qa"
    build_all(find_subjects([tmp_path / "fs"]), qa)
    html = write_report(qa).read_text()
    assert "a&lt;b&gt;&amp;x" in html and "a<b>&x" not in html
    assert all(len(row) == 4 for row in csv.reader(open(qa / REPORT_DIR / "region_ratings.tsv"), delimiter="\t"))


def test_a_subject_without_a_run_or_without_indicator_results_is_counted_as_such(qa):
    # `qa`: two built subjects without indicator input files, one that could not be built
    html = write_report(qa).read_text()
    assert "1 subject could not be built" in html
    facts = {f["key"]: f for f in subject_facts(qa)}
    assert facts[SECOND]["final"] is None and facts[SECOND]["findings"] is None


def test_report_is_made_again_from_the_current_reviews(qa_reviewed):
    from surfaceqa.layout import current_run_dir
    from surfaceqa.review_store import submit_review
    from tests.reviewing import make_review

    write_report(qa_reviewed)
    run = current_run_dir(qa_reviewed, RECON).name
    submit_review(qa_reviewed, make_review("cat", RECON, run, cerebellum="minor"))
    write_report(qa_reviewed)
    rows = _table(qa_reviewed, "region_ratings.tsv")
    cell = next(r for r in rows if (r["source"], r["item"], r["level"]) == ("freesurfer-8.2.0", "cerebellum", "minor"))
    assert cell["subjects"] == "1"
