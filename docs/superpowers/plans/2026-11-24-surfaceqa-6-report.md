# surfaceqa stage 6: error distribution report — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (the user chose native execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `surfaceqa report <qa_dir>` writes one page (and three tables) that shows how the different kinds of error are distributed over the subjects and brain regions of a QA directory.

**Architecture:** A pure module, `summary.py`, turns "what is known about each subject" (its combined reviews and its indicator findings) into counts. `report.py` gathers that per subject, calls the summary functions per source folder, renders one standalone HTML page from a template and writes the tables. Nothing new is stored per subject and the review server is not involved.

**Tech Stack:** Python 3.13, uv, Jinja2; pytest. No JavaScript, no new dependencies. Bars and grids are HTML and CSS written by the template.

**Spec:** `docs/superpowers/specs/2026-11-22-surfaceqa-design.md` (Goals 5, Anti-goals, "Several reviewers", "Indicators"). The report itself is a new request (2026-11-24: "a report showing the distribution of different types of errors across subjects"); this plan is its design.

## Global Constraints

- `uv` for packages, `uv run` for every command. No new dependencies.
- No code or imports in `__init__.py`.
- pytest, functions and fixtures, no test classes. Tests written first, seen to fail, committed before the implementation.
- Short functions; one responsibility per module.
- Nothing is written into a source folder.
- A person makes every judgment. Indicator results are never shown as, or mixed into, ratings.
- The report must not let a subject, a region or a cohort look fine because nothing was recorded: "not reviewed" and "indicator did not run" are always shown as such, never as zero errors.
- Commit messages end with `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.

## Decisions made in this plan (designer's calls, for the user to correct)

1. **Two kinds of "error" are reported, kept apart.** First what reviewers recorded (ratings per region, marked problems by kind, grades); then, in its own section headed as automated, what the indicators found. The second is there because it exists before anyone has reviewed, and to show how well the indicators agree with the reviewers.
2. **A command, and a button on the main page** (changed at the user's request, 2026-11-24: "I'd like to be able to recreate the report from the main web page"). `surfaceqa report` writes `<qa>/report/index.html`, which also opens from disk. The index page of the review server has a "Report" link to the page last made, with its date, and an "Update report" button that makes it again and opens it. **In a blind review (`serve --blind`) the server offers neither and answers 404**: the report shows every reviewer's ratings in aggregate, which a blind reviewer must not see; there the coordinator uses the command. Without `--blind` the overview already shows all ratings to anyone who gives no name, so the report reveals nothing new.
3. **Reviews are combined when the report is made**, with the same rule as `finalize` (within one step: the lower label; further apart: a disagreement; a `consensus` review stands alone). `finalize` need not have been run and nothing in `final/` is read or changed. Only submitted reviews count; the page says how many drafts were left out.
4. **One section per source folder**, since pipelines, versions and cohorts do not compare. Review progress is also given for the whole directory.
5. **What the page shows, per source folder:**
   - **Progress and grades:** subjects reviewed, in disagreement, unratable, not reviewed; a bar of the final grades.
   - **Ratings by region:** for each of the 11 checklist items, a stacked bar of how many subjects are none / minor / major (or ok / concern / exclude), in disagreement, and not reviewed.
   - **Marked problems:** a table of regions by problem kind (pial too far out, gray matter missed, white surface short, white surface past, crossing, topology): the number of subjects with at least one such mark, and the number of marks.
   - **Subjects by region:** a grid, one row per subject and one column per item, worst subjects first, each cell showing the final rating; the subject name links to its page, with grade, "edited" and the number of marks beside it.
   - **Indicators (automated):** for each indicator, how many subjects it ran on, how many have a finding, and the median and largest number of findings; a table of regions by finding kind (subjects with a finding).
   - **Indicators against reviewers:** per region, among reviewed subjects, how many had a finding and were rated none, minor or major, and how many had no finding and were rated none, minor or major. This is the table for judging the thresholds.
6. **Counting rules.** A subject counts once per cell. Marks are those of the reviewers whose reviews count (pooled, as in `finalize`). A subject whose indicators failed or did not run is "not computed", outside every indicator count. A subject in disagreement on an item is "disagreement" for that item, not dropped.
7. **Three tables** beside the page, tab-separated: `region_ratings.tsv` (source, item, level, subjects), `problem_kinds.tsv` (source, region, kind, subjects, marks), `indicator_agreement.tsv` (source, region, finding, rating, subjects).
8. **No reviewer names and no notes on the page**; it is the one page meant to be passed around. Subject names are shown.
9. **Appearance:** the site's dark style, copied into the page so it stands alone. Each level has a colour and its number; colour is never the only carrier. (Load the `dataviz` skill before writing the template.)

## Review Focus

1. A QA directory with no submitted review: every reviewer section says so; no bar, grid cell or count reads as "no errors".
2. Denominators: unreviewed subjects, unratable subjects, subjects in disagreement and subjects without indicator results appear in their own category and in no other.
3. A subject reviewed on an earlier run only (rebuilt since): it is "not reviewed" for the current run.
4. Subject or source names with HTML or tab characters: escaped on the page, harmless in the tables.
5. A `consensus` review beside the reviews it settles: counted once, and its marks only.
6. A blind server never serves or writes the report, under any spelling of the address.

---

### Task 1: Per-subject facts and progress

**Files:** Create `src/surfaceqa/summary.py`; Test `tests/test_summary.py`.

**Interfaces — Produces:**
- A *subject fact* is a dict: `{"key", "source", "name", "href", "edited": bool | None, "final": dict | None, "drafts": int, "findings": dict | None}`; `final` is `consensus.combine(...)` of the current run's reviews (None when the subject has no run); `findings` is the content of `findings.json` or None.
- `progress(facts) -> dict`: `{"subjects", "reviewed", "disagreement", "unratable", "unreviewed", "drafts"}` (the four states are exclusive and add up to `subjects`; `reviewed` = status single, agreed or settled and ratable).
- `grade_counts(facts) -> list[tuple[str, int]]`: every grade of the protocol in order with its count, then `("disagreement", n)` and `("not graded", n)`; reviewed subjects only.

- [ ] Tests first, on facts built by a helper from `tests/reviewing.make_review` and `combine`: states add up; a draft is counted in `drafts` and not as reviewed; an unratable subject is in `unratable` only; a grade disagreement is counted under "disagreement"; no reviews at all gives `reviewed == 0` and an all-zero grade list.
- [ ] Run, see them fail. Commit tests. Implement. Run all tests. Commit.

### Task 2: Regions, problem kinds and the subject grid

**Files:** Modify `src/surfaceqa/summary.py`; Test `tests/test_summary.py`.

**Interfaces — Produces:**
- `LEVELS`: for an item, its scale from the protocol followed by `"disagreement"`, `"unreviewed"`.
- `region_ratings(facts) -> list[dict]`: one per checklist item in protocol order: `{"item", "title", "counts": {level: n}}`; counts add up to the number of subjects that can be rated (unratable ones are left out and reported by `progress`).
- `problem_kinds(facts) -> list[dict]`: one per region (the 9 regions, not the two whole-brain passes): `{"region", "title", "cells": {kind: {"subjects": n, "marks": n}}}` for every mark kind of the protocol.
- `subject_grid(facts) -> list[dict]`: one per subject: `{"key", "name", "href", "edited", "grade", "status", "marks": n, "cells": {item: level}}`, ordered by number of major items (most first), then minor, then name; unreviewed subjects last.

- [ ] Tests first: three subjects (one all none; one sinus major with two `pial_out` marks and one `gray_missed` in orbitofrontal; one unreviewed) give the exact counts; an item two steps apart between two reviewers is "disagreement" for that item and still counted for its other items; a mark in a region rated minor is counted; a consensus review replaces the others and only its marks count; grid order; every region and kind is present with zeros.
- [ ] Run, see them fail. Commit tests. Implement. Run all tests. Commit.

### Task 3: Indicators, and indicators against reviewers

**Files:** Modify `src/surfaceqa/summary.py`; Test `tests/test_summary.py`.

**Interfaces — Produces:**
- `indicator_summary(facts) -> list[dict]`: one per indicator name seen: `{"name", "ran": n, "not_run": n, "with_findings": n, "median": float, "largest": int}` over the subjects where it ran; plus `not_computed(facts) -> int` (subjects with a run and no findings file).
- `finding_kinds(facts) -> list[dict]`: one per region: `{"region", "title", "cells": {kind: subjects}}` over scored finding kinds (places to look are left out).
- `agreement(facts) -> list[dict]`: one per region: `{"region", "title", "fired": {level: n}, "quiet": {level: n}}` over subjects that have both a final rating for the region and indicator results; `level` is none, minor or major.

- [ ] Tests first: findings records built by hand (`{"indicators": [...], "findings": [{"indicator", "kind", "region"}, ...]}`): counts per indicator, median and largest; an indicator that did not run on a subject is in `not_run` and not in `ran`; a subject without findings is in `not_computed` and nowhere else; `look_here` findings are not counted; agreement table for four subjects covering fired/quiet × none/major; a subject in disagreement or unreviewed for a region is not in that region's agreement row.
- [ ] Run, see them fail. Commit tests. Implement. Run all tests. Commit.

### Task 4: The page, the tables and the command

**Files:** Create `src/surfaceqa/report.py`, `src/surfaceqa/web/templates/report.html`; Modify `src/surfaceqa/cli.py`, `README.md`; Test `tests/test_report.py`, `tests/test_cli.py`.

**Interfaces — Consumes:** Tasks 1–3; `site.subject_records(qa_dir)` (default view), `review_store.list_reviews`, `consensus.combine`, `qa.load_findings`. **Produces:**
- `report.subject_facts(qa_dir) -> list[dict]` (`href` is `../subjects/<key>/index.html`, URL-quoted).
- `report.write_report(qa_dir) -> Path`: writes `<qa>/report/index.html` and the three tables; returns the page's path.
- `surfaceqa report <qa_dir>`: prints the path; exit 2 for a folder that is not a QA directory (as `export`).
- The page: a title with the date and the QA directory name; overall progress; then per source folder the six parts of Decision 5, each with a one-line statement of what is counted. The reviewer parts of a source without a submitted review are replaced by "No submitted reviews yet."; the indicator part is headed "Automated indicators — not judgments".

- [ ] Tests first, on the `qa_reviewed` fixture and on a directory with no reviews: the page exists and names both sources; counts on the page equal the summary functions' (checked through the tables); "No submitted reviews yet." appears and no "0 subjects with major" style line does; no reviewer name and no note text from the fixture (`ann`, `bob`, `ann-note-xyzzy`, `mark-note-plugh`) is on the page; a subject named `<b>x</b>` is escaped; the page has no `<script` and no `http` reference; the three tables have the pinned headers; `main(["report", qa])` returns 0 and prints the path; `main(["report", not_a_qa_dir])` returns 2; nothing under `ratings/`, `final/` or `subjects/` is modified.
- [ ] Run, see them fail. Commit tests. Implement (load the `dataviz` skill first). Run all tests. Commit.

### Task 5: The report on the review server

**Files:** Modify `src/surfaceqa/server.py`, `src/surfaceqa/site.py`, `src/surfaceqa/web/templates/index.html`; Test `tests/test_server.py`, `tests/test_site.py`.

**Interfaces — Consumes:** `report.write_report`, `report.REPORT_DIR = "report"`, `report.TABLES` (the three file names). **Produces:**
- `POST /report`: makes the report again and redirects (303) to `/report/index.html`.
- `GET /report/index.html` and `GET /report/<table>.tsv` for the three tables: the files last written; 404 when there are none or for any other name.
- All three answer 404 on a blind server.
- The index page of a non-blind server: `<form method="post" action="/report">` with the button "Update report" (or "Make report" when there is none), and beside it a link "Report" with "made <date and time>" when `report/index.html` exists. The pages `build` writes to disk and the blind index have neither.

- [ ] Tests first: the POST writes the page and redirects; the GET serves it and the tables; `/report/../ratings/...`, `/report/other.html` and `/report/` spelled with encoded dots are 404; before any report the GET is 404 and the index says "Make report"; after it the index shows the link and the date; on a blind server, with and without a name, POST and GET are 404, the index has no report form, and no report file is written; the subject links on the served page open the subject pages.
- [ ] Run, see them fail. Commit tests. Implement. Run all tests. Commit.

### Task 6: Real data, and review

- [ ] Run `surfaceqa report` on `~/surfaceqa-demo` (test reviews by several names) and on `~/surfaceqa-network` (46 subjects; one draft, so the reviewer parts must read "No submitted reviews yet." and the indicator parts must be filled). Open both pages in the browser and check them on screenshots; compare three counts by hand against the subject pages.
- [ ] In the browser: press "Update report" on the index of both servers and check that the page is made again and opens. README: the command and the button, what each part counts, and that a blind server does not offer the report.
- [ ] Run all tests. Commit. Final whole-branch review by an independent reviewer, with this plan's Review Focus.
