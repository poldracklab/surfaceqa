# surfaceqa stage 3: recording the review — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (the user chose native execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reviewers rate every checklist item, mark problems on the image, grade the subject and submit; several reviewers work independently (optionally blind); `finalize` combines them and `export` writes the tables.

**Architecture:** Review state lives in JSON files under `<qa>/ratings/`, one per subject, run and reviewer. Pure modules validate reviews, combine them and order the queue. `surfaceqa serve` renders the index and subject pages at request time for the named reviewer (so it can hide what that reviewer must not see) and exposes a small JSON API; the static pages written by `build` stay as a read-only overview. A new browser module records ratings and marks through the existing viewer.

**Tech Stack:** Python 3.13, uv, FastAPI, Jinja2, nibabel, numpy; vanilla JS ES modules tested with `node --test` through `tests/test_js.py`; pytest.

**Spec:** `docs/superpowers/specs/2026-11-22-surfaceqa-design.md` (sections "Subject report page", "Several reviewers", "Ratings", "Index page", "Commands").

## Global Constraints

- `uv` for packages, `uv run` for every command. No new dependencies.
- No code or imports in `__init__.py`.
- pytest, functions and fixtures, no test classes. Tests written first, seen to fail, committed before the implementation.
- Short functions; one responsibility per module.
- Nothing is ever written into a source (derivatives) folder. Reviews go under `<qa>/ratings/`, final labels under `<qa>/final/`, tables under `<qa>/export/`.
- An unrated item is shown as unrated, never as OK. No indicator result ever fills in a rating.
- A reviewer never sees another reviewer's ratings or marks for a subject before submitting their own.
- Ratings are tied to the run (surface fingerprint) they were made on.
- Commit messages end with `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.

## Decisions made in this plan (designer's calls, for the user to correct)

1. **Marks snap to the drawn contour in the browser.** The server then adds the tkr coordinate and, when the source surface file is readable, the nearest vertex index. If the source volume is not mounted the vertex is left empty and the mark is still saved.
2. **A region rated major needs at least one mark before submitting**, because stage 4 writes fix guidance per mark.
3. **Editing after submitting is allowed.** The first submission time is kept and the review is flagged `revised`.
4. **More than two reviewers:** the spec's two-reviewer rule is applied to the spread between the lowest and highest rating.
5. **Overall grade in `finalize`:** grades within one letter (three steps on the 13-step scale) give the better grade, in the same direction as the spec's rule for ratings; further apart is a disagreement.
6. **Settling a disagreement:** the reviewers submit one joint review under the reserved name `consensus`. When it exists for a run, `finalize` uses it alone.
7. **No name given:** in normal mode the pages are a read-only overview showing everything. In `--blind` mode nothing but the name form is shown until a name is given.
8. **`export` contains submitted reviews only**; drafts are not exported.

## Review Focus

Inputs the spec implies and a user will meet; each has a test in the task named.

1. The subject is rebuilt with new surfaces while a review page is open: the save is refused with a clear message, not written onto the wrong run (Task 8).
2. A reviewer name containing `/`, `..`, spaces or nothing: refused, no file written outside `ratings/` (Tasks 2, 8).
3. A review file that is truncated or not JSON: the index and subject page still render and the file is ignored (Tasks 3, 7).
4. Source volume not mounted while reviewing: a mark saves with an empty vertex (Task 4).
5. Blind mode: the findings files are not served by direct URL to a reviewer who has not submitted (Task 8).

## File structure

| File | Responsibility |
|---|---|
| `src/surfaceqa/protocol.json` | Versioned wording: scales with anchors, grades, mark kinds |
| `src/surfaceqa/protocol.py` | Load the protocol; list item ids |
| `src/surfaceqa/reviews.py` | Shape of a review; validate a payload; what is missing before submit |
| `src/surfaceqa/review_store.py` | Read and write review files |
| `src/surfaceqa/marks.py` | Add tkr coordinate and vertex index to a mark |
| `src/surfaceqa/consensus.py` | Combine reviews into final labels (pure) |
| `src/surfaceqa/finalize.py` | Write `<qa>/final/<key>.json`; report disagreements |
| `src/surfaceqa/queue.py` | A reviewer's order of subjects; next subject |
| `src/surfaceqa/export.py` | Write the four TSV tables |
| `src/surfaceqa/site.py` (modify) | Review fields on records; render functions shared by `build` and `serve` |
| `src/surfaceqa/server.py` (modify) | Reviewer cookie, pages per reviewer, review API, blind gate |
| `src/surfaceqa/cli.py` (modify) | `serve --blind`, `finalize`, `export` |
| `src/surfaceqa/build.py` (modify) | `grid_to_tkr` in `meta.json`; `BUILD_FORMAT = 3` |
| `src/surfaceqa/web/templates/_review.html`, `_reviewer.html`, `_final.html` (new); `index.html`, `subject.html`, `_checklist.html`, `_header.html`, `_summary.html`, `base.html` (modify) | Rating controls, name form, final labels |
| `src/surfaceqa/web/static/logic.js` (modify) | Pure helpers: snapping, marks on a slice, items remaining, key to rating |
| `src/surfaceqa/web/static/review.js` (new) | Rating, marking, autosave, submit, keyboard, help |
| `src/surfaceqa/web/static/viewer.js` (modify) | `setMarks`, `pick` |

Files on disk:

```
<qa>/ratings/<key>/<run>/<reviewer>.json
<qa>/final/<key>.json
<qa>/export/{ratings,marks,final,indicators}.tsv
```

---

### Task 1: Protocol file

**Files:** Create `src/surfaceqa/protocol.json`, `src/surfaceqa/protocol.py`; Test `tests/test_protocol.py`

**Interfaces:**
- Produces: `load_protocol() -> dict`; `item_ids() -> list[str]` (`["birdseye", "t1", *region ids in REGIONS order]`); `PASS_ITEMS = ("birdseye", "t1")`; `scale_for(item_id, protocol) -> list[str]` (ids of the levels, least severe first).

`protocol.json` (exact copy):

```json
{
  "version": 1,
  "region_scale": [
    {"id": "none", "key": "1", "label": "None", "anchor": "No error seen in this region."},
    {"id": "minor", "key": "2", "label": "Minor", "anchor": "Visible but confined; would not change an analysis much. Leave it."},
    {"id": "major", "key": "3", "label": "Major (needs fix)", "anchor": "A careful analyst would edit or exclude."}
  ],
  "pass_scale": [
    {"id": "ok", "key": "1", "label": "OK", "anchor": "Nothing that affects the surfaces."},
    {"id": "concern", "key": "2", "label": "Concern", "anchor": "A problem worth a note; the subject is still usable."},
    {"id": "exclude", "key": "3", "label": "Consider excluding", "anchor": "The image or reconstruction is not usable as it is."}
  ],
  "tie_rule": "When torn between two levels, choose the lower and write a note.",
  "grades": ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"],
  "mark_kinds": [
    {"id": "pial_out", "label": "pial too far out"},
    {"id": "gray_missed", "label": "gray matter missed"},
    {"id": "white_short", "label": "white surface short of white matter"},
    {"id": "white_past", "label": "white surface past white matter"},
    {"id": "crossing", "label": "hemispheres crossing"},
    {"id": "topology", "label": "topology defect"}
  ]
}
```

- [ ] **Step 1: Tests** — `test_protocol_has_a_version_and_three_levels_per_scale`; `test_item_ids_are_the_two_passes_then_the_nine_regions_in_order` (`item_ids()[:2] == ["birdseye", "t1"]`, `item_ids()[2:] == [r.id for r in REGIONS]`, length 11); `test_scale_for_a_pass_and_for_a_region` (`scale_for("t1", p) == ["ok", "concern", "exclude"]`, `scale_for("sinus", p) == ["none", "minor", "major"]`); `test_protocol_file_is_packaged` (loads through `importlib.resources`).
- [ ] **Step 2:** `uv run pytest tests/test_protocol.py -q` → FAIL (no module). Commit tests.
- [ ] **Step 3:** Implement. Check `pyproject.toml` packages the `.json` (the templates already ship; follow the same mechanism).
- [ ] **Step 4:** PASS. Commit.

### Task 2: Review records and validation

**Files:** Create `src/surfaceqa/reviews.py`; Test `tests/test_reviews.py`

**Interfaces:**
- Consumes: `load_protocol`, `item_ids`, `scale_for`.
- Produces:
  - `RESERVED = "consensus"`; `valid_reviewer(name: str) -> bool` — true only for `^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$`.
  - `class ReviewError(ValueError)`.
  - `empty_review(key, run, reviewer) -> dict`.
  - `clean_review(payload: dict, key, run, reviewer) -> dict` — returns a review holding only known fields; raises `ReviewError` naming the bad field.
  - `missing_for_submit(review: dict) -> list[str]` — human-readable lines; empty when the review can be submitted.

A review:

```python
{"protocol": 1, "key": ..., "run": ..., "reviewer": ...,
 "saved": None, "submitted": None, "revised": False, "skipped": False,
 "unratable": None,                      # or the reason, a non-empty string
 "items": {item_id: {"rating": None, "note": ""} for every item id},
 "marks": [],   # {"region", "kind", "grid": [x, y, z], "surface": str | None, "finding": int | None, "note": str}
 "grade": None, "notes": ""}
```

Rules for `clean_review`: an item's rating is `None` or a level of that item's scale; a mark's `region` is a region id, `kind` a mark-kind id, `grid` three finite numbers, `surface` `None` or one of `SURFACE_ORDER`; `grade` is `None` or in the protocol's grades; notes and reason at most 2000 characters; at most 200 marks; unknown item ids are an error; missing items are filled as unrated. `saved`, `submitted`, `revised`, `tkr` and `vertex` in a payload are ignored (the server owns them).

Rules for `missing_for_submit`: with an `unratable` reason nothing else is required. Otherwise: one line per unrated item, one if there is no grade, one per region rated `major` with no mark in that region.

- [ ] **Step 1: Tests**
  - `test_valid_reviewer_accepts_plain_names_and_refuses_paths` — accepts `"russ"`, `"r-2_b"`, `"consensus"`; refuses `""`, `"a/b"`, `".."`, `"a b"`, `"é"`, 41 characters, `"-a"`.
  - `test_empty_review_lists_every_item_as_unrated`
  - `test_clean_review_keeps_valid_ratings_marks_and_grade`
  - `test_clean_review_refuses_a_region_level_on_a_pass_item` (`{"t1": {"rating": "major"}}` → `ReviewError` matching `t1`)
  - `test_clean_review_refuses_unknown_items_kinds_grades_and_surfaces` (parametrized)
  - `test_clean_review_refuses_non_finite_grid`
  - `test_clean_review_ignores_server_owned_fields` (payload `submitted` does not appear in the result)
  - `test_clean_review_fills_missing_items_as_unrated`
  - `test_long_note_is_refused` (2001 characters)
  - `test_missing_for_submit_lists_unrated_items_and_grade` (empty review → 11 item lines + grade line)
  - `test_major_region_without_a_mark_blocks_submit`; `test_major_region_with_a_mark_can_be_submitted`
  - `test_unratable_with_a_reason_can_be_submitted_with_nothing_rated`; `test_blank_unratable_reason_does_not_count` (`"  "` → still missing)
- [ ] **Step 2:** FAIL. Commit tests.
- [ ] **Step 3:** Implement with one small checker per field.
- [ ] **Step 4:** PASS. Commit.

### Task 3: Review store

**Files:** Create `src/surfaceqa/review_store.py`; Test `tests/test_review_store.py`

**Interfaces:**
- Produces:
  - `review_path(qa_dir, key, run, reviewer) -> Path` → `<qa>/ratings/<key>/<run>/<reviewer>.json`
  - `load_review(qa_dir, key, run, reviewer) -> dict | None` (`None` when absent or unreadable)
  - `save_review(qa_dir, review: dict, now: datetime | None = None) -> dict` — sets `saved`; if the stored copy was submitted, keeps its `submitted` and sets `revised = True`; writes to a temporary file in the same folder and renames.
  - `submit_review(qa_dir, review, now=None) -> dict` — as save, and sets `submitted` if not already set.
  - `list_reviews(qa_dir, key, run) -> list[dict]` — every readable review of that run, sorted by reviewer.
  - `earlier_reviews(qa_dir, key, current_run, reviewer) -> list[dict]` — that reviewer's submitted reviews of other runs, newest first.

- [ ] **Step 1: Tests** (`tmp_path` as the QA directory)
  - `test_saved_review_is_read_back_with_a_timestamp`
  - `test_saving_after_submitting_keeps_the_submission_time_and_flags_revised`
  - `test_reviews_of_two_reviewers_are_separate_files`
  - `test_list_reviews_ignores_unreadable_files` (write `{"trunc` beside a good one → one review)
  - `test_load_review_of_a_truncated_file_is_none`
  - `test_reviews_of_another_run_are_not_listed_for_this_run`
  - `test_earlier_reviews_returns_only_submitted_reviews_of_other_runs`
  - `test_no_temporary_file_is_left_behind`
- [ ] **Step 2:** FAIL. Commit tests. **Step 3:** Implement. **Step 4:** PASS. Commit.

### Task 4: Locating a mark (tkr coordinate and vertex)

**Files:** Modify `src/surfaceqa/build.py` (`_run_meta`, `BUILD_FORMAT = 3`), `src/surfaceqa/geometry.py`; Create `src/surfaceqa/marks.py`; Tests `tests/test_marks.py`, `tests/test_build.py`

**Interfaces:**
- Produces:
  - `meta.json` gains `"grid_to_tkr"`: 4×4 nested list, the inverse of `DisplayVolume.tkr_to_grid`.
  - `geometry.to_tkr(points_grid: np.ndarray, grid_to_tkr: np.ndarray) -> np.ndarray`
  - `marks.locate_mark(mark: dict, meta: dict) -> dict` — returns the mark with `"tkr": [x, y, z]` (rounded to 2 decimals) and `"vertex": int | None`. The vertex is the index of the nearest vertex of `mark["surface"]` read from `<meta["path"]>/surf/<surface>`; `None` when the mark has no surface or the file cannot be read.
  - `marks.locate_marks(review: dict, meta: dict) -> dict`

- [ ] **Step 1: Tests**
  - `test_meta_records_grid_to_tkr_that_inverts_the_display_transform` (build the synthetic subject; a surface vertex mapped with `to_grid` and back with the stored matrix returns within 1e-4)
  - `test_build_format_change_rerenders_an_existing_run` (existing mechanism; assert a format-2 `meta.json` is replaced)
  - `test_mark_on_a_vertex_gets_that_vertex_and_its_tkr_coordinate` (take vertex 17 of `lh.pial`, put the mark at its grid position → `vertex == 17`, `tkr` equals the vertex within 0.01)
  - `test_mark_without_a_surface_has_no_vertex_but_has_tkr`
  - `test_mark_is_located_without_the_source_folder` (delete the synthetic subject folder after the build → `vertex is None`, `tkr` present, no exception)
- [ ] **Step 2:** FAIL. Commit tests. **Step 3:** Implement. **Step 4:** PASS, full suite green. Commit.

### Task 5: Combining reviews

**Files:** Create `src/surfaceqa/consensus.py`, `src/surfaceqa/finalize.py`; Tests `tests/test_consensus.py`, `tests/test_finalize.py`

**Interfaces:**
- Produces:
  - `consensus.combine(reviews: list[dict]) -> dict` — pure. Only submitted reviews count. If one is by `consensus`, it alone is used and `status` is `"settled"`.

    ```python
    {"status": "unreviewed" | "single" | "agreed" | "disagreement" | "settled",
     "reviewers": [...], "inputs": {reviewer: saved},
     "unratable": bool,
     "items": {item_id: {"final": level | None, "ratings": {reviewer: level}, "disagree": bool}},
     "grade": {"final": grade | None, "grades": {reviewer: grade}, "disagree": bool},
     "marks": [mark + {"reviewer": ...}],          # pooled, in reviewer order
     "needs_fix": [region ids whose final is "major"],
     "disagreements": [item ids, "grade", "unratable"]}
    ```
  - Rule per item: positions on that item's scale; highest minus lowest ≤ 1 → `final` is the lowest; ≥ 2 → `final` `None`, `disagree` true. Grade: positions in the protocol's grades; spread ≤ 3 → the better grade; > 3 → disagree. Unratable: all reviewers → `unratable` true, no disagreement; some but not all → `"unratable"` in `disagreements`. `status` is `disagreement` when `disagreements` is non-empty.
  - `finalize.finalize(qa_dir) -> list[dict]` — for every subject with a current run, combines that run's reviews, adds `key` and `run`, writes `<qa>/final/<key>.json`, returns the records.
  - `finalize.load_final(qa_dir, key) -> dict | None`
  - `finalize.is_stale(final: dict, reviews: list[dict], run: str) -> bool` — true when the run differs or `inputs` no longer equals the submitted reviews' `saved` times.

- [ ] **Step 1: Tests** (a `review(reviewer, **ratings)` helper in the test file builds complete submitted reviews)
  - `test_no_submitted_review_is_unreviewed`; `test_drafts_do_not_count`
  - `test_one_reviewer_keeps_their_ratings` (status `single`)
  - `test_one_step_apart_takes_the_lower` (`none` + `minor` → `none`; `minor` + `major` → `minor`)
  - `test_two_steps_apart_is_a_disagreement` (`none` + `major` → final `None`, item in `disagreements`, status `disagreement`)
  - `test_marks_are_pooled_with_their_reviewer`
  - `test_needs_fix_lists_regions_final_major` (both `major` → listed; `minor` + `major` → not listed)
  - `test_one_unratable_of_two_is_a_disagreement`; `test_all_unratable_is_final_unratable`
  - `test_grades_within_a_letter_take_the_better` (`B` + `C+` → `B`); `test_grades_more_than_a_letter_apart_disagree` (`A` + `C` → disagree)
  - `test_three_reviewers_use_the_spread` (`none`, `minor`, `major` → disagree; `minor`, `minor`, `major` → `minor`)
  - `test_a_consensus_review_settles_the_subject` (two disagreeing + `consensus` → status `settled`, finals from the consensus review, `reviewers == ["consensus"]`)
  - `test_finalize_writes_one_file_per_subject_with_a_run`; `test_finalize_uses_only_reviews_of_the_current_run`
  - `test_final_is_stale_after_a_review_changes`
- [ ] **Step 2:** FAIL. Commit tests. **Step 3:** Implement. **Step 4:** PASS. Commit.

### Task 6: A reviewer's queue

**Files:** Create `src/surfaceqa/queue.py`; Test `tests/test_queue.py`

**Interfaces:**
- Produces:
  - `review_queue(ordered_keys: list[str], states: dict[str, str], reviewer: str, blind: bool) -> list[str]` — `states[key]` is `"none" | "draft" | "skipped" | "submitted"`. Submitted subjects are left out; skipped ones go to the end; the rest keep `ordered_keys` order, or, when blind, the order of `random.Random(reviewer).shuffle` applied to the sorted keys.
  - `next_key(queue: list[str], after: str | None) -> str | None` — the first queued subject after `after` in the queue, wrapping round; `None` when the queue is empty or holds only `after`.
  - `blind_order(keys, reviewer) -> list[str]` (also used by the index).

- [ ] **Step 1: Tests** — `test_queue_keeps_worst_first_order`; `test_submitted_subjects_leave_the_queue`; `test_skipped_subjects_go_last_and_are_not_dropped`; `test_blind_order_is_shuffled_stable_per_reviewer_and_differs_between_reviewers` (20 keys); `test_next_after_the_last_wraps_to_the_first`; `test_next_is_none_when_nothing_else_is_left`.
- [ ] **Step 2:** FAIL. Commit tests. **Step 3:** Implement. **Step 4:** PASS. Commit.

### Task 7: Pages that show review state

**Files:** Modify `src/surfaceqa/site.py`, templates `index.html`, `subject.html`, `_checklist.html`, `_header.html`, `_summary.html`, `base.html`; Create `_review.html`, `_reviewer.html`, `_final.html`; Modify `app.css`; Test `tests/test_site.py`, `tests/conftest.py`

**Interfaces:**
- Consumes: `list_reviews`, `load_review`, `earlier_reviews`, `load_final`, `is_stale`, `combine`, `review_queue`, `blind_order`, `load_protocol`.
- Produces:
  - `site.View` — frozen dataclass `(reviewer: str | None = None, blind: bool = False, serving: bool = False)`.
  - `site.subject_records(qa_dir, view: View = View()) -> list[dict]` — today's records plus, per record:
    `reviewers` (names with a submitted review of the current run), `mine` (`"none" | "draft" | "skipped" | "submitted"`), `my_review` (dict or `None`), `final` (from `load_final`, `None` if absent), `final_stale`, `earlier` (own earlier-run reviews), `others` (other reviewers' submitted reviews), `show_others`, `hide_indicators`.
    - `show_others` = no reviewer and not blind, or `mine == "submitted"`.
    - `hide_indicators` = blind and `mine != "submitted"`.
    - When `show_others` is false, `others` is `[]` and `final` is `None` in the record (so no template can leak them). When `hide_indicators` is true, `score`, `rank`, `largest`, `n_findings` are `None` and `sections` is `checklist_sections(None)` with a flag `blind: True`.
    - Order: existing order; when blind, `blind_order` of the keys.
  - `site.render_index(records, view) -> str`, `site.render_subject(record, view) -> str` (`root` computed as today).
  - `write_site(qa_dir)` unchanged in signature; uses `View()`.
  - Fixture `qa_reviewed` in `conftest.py`: `qa_planted` plus submitted reviews by `ann` and `bob` for `fastsurfer__sub-01` (ann: `sinus` major with one mark, grade `C`; bob: `sinus` minor, grade `C+`), and a draft by `ann` for `fastsurfer__sub-02`.

Page content:
- **Index.** New columns: "Reviewed by", "Final grade", "Needs fix" (count), and, with a reviewer, "Your review". A subject in disagreement shows `disagreement` in the grade column; a stale final shows "run `surfaceqa finalize` again". The sentence "No subject has been reviewed yet" is removed. With `serving` and a reviewer, a "Next subject" link to `/next`.
- **Subject header.** "Review" shows: not reviewed / the reviewers' names / "in disagreement".
- **Checklist.** With `serving` and a reviewer, each of the 11 items carries `data-item="<id>"`, three radio buttons from its scale (labels and anchors from the protocol), a note field, and the text `unrated` until rated. Region items carry a "Mark a problem" button and an empty `<ul class="marks">`; finding buttons get an adjacent "Accept as mark" button (`data-accept="<finding id>"`). Below the checklist (`_review.html`): tie rule, grade select, notes, unratable checkbox with reason, "items remaining" counter, Save status, Submit, Skip, Next subject. Without `serving` or without a reviewer, the controls are replaced by one note: "Ratings are recorded when this page is opened through `surfaceqa serve` and you have given your name."
- **Blind and not submitted.** No score, rank, findings, hints or indicator notes; the summary says "Indicator results are hidden until you submit your review (blind mode)." The viewer section gets `data-findings="off"`; the Findings checkbox is not rendered.
- **Final and others (`_final.html`).** When `show_others`: a table of items × reviewers with the final column, pooled marks, final grade.
- **Earlier runs.** "Previous run" block listing the reviewer's own earlier ratings, read-only, with the sentence "The surfaces have changed since this review; the subject needs to be reviewed again."
- `base.html` header shows the reviewer's name with a "change" control, or the name form (`_reviewer.html`, posts to `/reviewer`), only when `serving`.
- The page embeds the protocol and the review as JSON in `<script type="application/json" id="review-data">` (`{"protocol", "review", "key", "run", "missing"}`), only when `serving` with a reviewer.

- [ ] **Step 1: Tests** (static unless a `View` is given)
  - `test_static_index_lists_who_reviewed_each_subject` (`ann` and `bob` in the sub-01 row)
  - `test_static_subject_page_has_no_rating_controls_and_says_how_to_review`
  - `test_named_reviewer_gets_rating_controls_for_all_eleven_items` (11 `data-item`, each with three radios; the word `unrated` appears 11 times for a reviewer with no review)
  - `test_rating_labels_and_anchors_come_from_the_protocol`
  - `test_saved_ratings_are_embedded_for_the_page` (parse `#review-data`; ann's `sinus` is `major`)
  - `test_a_reviewer_who_has_not_submitted_does_not_get_others_ratings` (view as `cat` on sub-01: neither `"C+"` nor ann's note text is anywhere in the HTML; "Reviewed by" names are present)
  - `test_a_reviewer_who_has_submitted_sees_the_others` (view as `ann`: bob's `minor` shown)
  - `test_blind_page_hides_score_findings_and_hints_until_submitted` (view `cat`, blind: no `data-finding`, no "Suspicion score"; view `ann`, blind: present)
  - `test_blind_index_hides_scores_of_unsubmitted_subjects_and_is_shuffled_per_reviewer`
  - `test_blind_without_a_name_shows_only_the_name_form` (index and subject)
  - `test_final_labels_are_shown_after_finalize` (run `finalize`; the static index row of sub-01 has final grade `C+`, the better of `C` and `C+` by decision 5, and needs-fix count `0`, because `major` + `minor` → `minor`)
  - `test_stale_final_is_flagged` (save a new review after finalize)
  - `test_disagreement_is_shown_on_the_index`
  - `test_ratings_of_an_earlier_run_are_shown_as_previous_run_and_subject_is_unreviewed` (rewrite a surface, rebuild; view as `ann`: `mine == "none"`, page has "Previous run")
  - `test_unreadable_review_file_does_not_break_the_pages`
  - Existing test `test_subject_page_has_viewer_and_is_not_marked_reviewed` keeps passing.
- [ ] **Step 2:** FAIL. Commit tests.
- [ ] **Step 3:** Implement: `_review_fields` and friends in `site.py` (split a `site_reviews.py` helper module out if `site.py` passes ~200 lines), then templates and CSS.
- [ ] **Step 4:** PASS, full suite green. Commit.

### Task 8: Server — reviewer, pages, API, blind gate

**Files:** Modify `src/surfaceqa/server.py`, `src/surfaceqa/cli.py`; Tests `tests/test_server.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `create_app(qa_dir, blind: bool = False) -> FastAPI`; CLI `surfaceqa serve QA_DIR [--host] [--port] [--blind]`.

| Route | Behaviour |
|---|---|
| `POST /reviewer` (form `name`, `next`) | Valid name → cookie `surfaceqa_reviewer` (one year, `SameSite=Lax`), 303 to `next` if it is a local path starting with `/`, else `/`. Invalid → 400 with the rule in words. |
| `POST /reviewer/clear` | Deletes the cookie, 303 to `/`. |
| `GET /`, `/index.html` | `render_index` for the cookie's reviewer. |
| `GET /subjects/{key}/`, `/subjects/{key}/index.html` | `render_subject`; 404 for an unknown key. |
| `GET /api/review/{key}` | The reviewer's review of the current run, or `empty_review`; 401 without a valid cookie; 404 unknown key or no run. |
| `PUT /api/review/{key}` | Body is a review payload with `run`. 409 `{"detail": "This subject was rebuilt… reload the page"}` when `run` is not the current run. `clean_review` → `locate_marks` → `save_review`. 422 with the `ReviewError` text. Any save clears `skipped` unless the payload sets it. Returns `{"review", "missing"}`. |
| `POST /api/review/{key}/submit` | Same body. Saves; if `missing_for_submit` is non-empty → 422 `{"detail": [...lines]}` and the review stays a draft; else `submit_review`. |
| `GET /next?after={key}` | 303 to the next subject in the reviewer's queue, or to `/` when none is left. |
| `GET .../runs/{run}/findings.json`, `findings_voxels.bin` | In blind mode: 404 unless the cookie's reviewer has submitted that subject's current run. Otherwise served as before. |
| everything else | Static files, as now. |

Request bodies larger than 1 MB are refused (413).

- [ ] **Step 1: Tests** (`TestClient`; fixtures `qa_planted`, `qa_reviewed`)
  - `test_setting_a_name_sets_a_cookie_and_redirects_back`
  - `test_bad_names_are_refused_and_nothing_is_written` (parametrized `"a/b"`, `".."`, `""`; `ratings/` unchanged)
  - `test_redirect_target_outside_the_site_is_ignored` (`next=https://example.org` and `next=//example.org` → `/`)
  - `test_review_api_needs_a_name` (401)
  - `test_a_saved_draft_is_returned_on_the_next_get`
  - `test_saving_writes_the_file_under_ratings_for_the_current_run`
  - `test_invalid_rating_is_refused_with_the_field_named` (422, `t1`)
  - `test_save_against_an_old_run_is_refused` (409, nothing written)
  - `test_submit_with_unrated_items_is_refused_and_lists_them` (422; file exists as draft; `submitted` is `None`)
  - `test_complete_review_can_be_submitted` (`submitted` set)
  - `test_marks_get_a_tkr_coordinate_when_saved`
  - `test_skip_moves_the_subject_to_the_end_of_the_queue` (`/next` after skipping sub-01 goes elsewhere; when only skipped ones remain, `/next` returns sub-01)
  - `test_next_goes_to_the_most_suspicious_unsubmitted_subject`
  - `test_subject_page_is_rendered_for_the_named_reviewer` (controls present with cookie, absent without)
  - `test_unknown_subject_is_404` (page and API)
  - `test_blind_findings_files_are_not_served_before_submitting` (404 for `cat`, 200 for `ann` on sub-01; 200 for anyone when not blind)
  - `test_oversized_body_is_refused`
  - existing static and traversal tests keep passing
  - CLI: `test_serve_accepts_blind` (parser only; patch `uvicorn.run` and assert `create_app` received `blind=True`)
- [ ] **Step 2:** FAIL. Commit tests.
- [ ] **Step 3:** Implement; keep route handlers to a few lines each, logic in a `server_reviews.py` helper if `server.py` grows past ~150 lines.
- [ ] **Step 4:** PASS, full suite. Commit.

### Task 9: Browser logic (pure functions)

**Files:** Modify `src/surfaceqa/web/static/logic.js`; Test `tests/js/logic.test.mjs`

**Interfaces — produces:**
- `nearestOnContours(segmentsBySurface, x, y, maxDist)` → `{x, y, surface, dist} | null`. `segmentsBySurface` is `{name: Float32Array | number[]}` of `x1,y1,x2,y2` runs in plane pixel coordinates (what `sliceSegments` returns); the nearest point may lie inside a segment, not only at an end.
- `marksOnSlice(marks, plane, slice, reach)` → marks whose `grid[plane.axis]` is within `reach` slices.
- `itemsRemaining(review, itemIds)` → number of unrated items, plus 1 when there is no grade; 0 when `review.unratable` is a non-blank string.
- `levelForKey(key, scale)` → the level id whose `key` matches, or `null`.
- `stepItem(current, delta, n)` → like `stepIndex` but stops at the ends.

- [ ] **Step 1: Tests** — nearest point is the foot of the perpendicular on a segment; picks the nearer of two surfaces; `null` beyond `maxDist`; `null` with no segments; `marksOnSlice` reach; `itemsRemaining` for an empty review is 12, with all rated and a grade is 0, unratable is 0, blank reason is not; `levelForKey("2", regionScale) === "minor"`, `"9"` → `null`; `stepItem` does not wrap.
- [ ] **Step 2:** `uv run pytest tests/test_js.py -q` → FAIL. Commit tests. **Step 3:** Implement. **Step 4:** PASS. Commit.

### Task 10: Rating and marking in the browser

**Files:** Create `src/surfaceqa/web/static/review.js`; Modify `viewer.js`, `checklist.js`, `subject.html`, `app.css`; Test `tests/test_site.py` (script tag, help markup), browser check

**Interfaces:**
- Consumes: `#review-data`, the API of Task 8, `logic.js` helpers of Task 9.
- Produces in `viewer.js` (added to `window.surfaceqaViewer`):
  - `setMarks(marks)` — draws each mark as a magenta ring on slices within 1 of its position, in all three views.
  - `pick()` → `Promise<{grid, surface} | null>` — the next click on any view resolves with the clicked point snapped to the nearest drawn contour within `SNAP_MM = 3` in that view (grid position from `screenToGrid` at the snapped point), or unsnapped with `surface: null`; `Escape` resolves `null`. While picking, the cursor is a crosshair and the click does not move the views.
  - When the viewer section has `data-findings="off"`, findings are not requested.

Behaviour of `review.js`:
- Fills the controls from the embedded review; every change updates the "unrated" text and the items-remaining counter, and saves (debounced 500 ms, `PUT`). The status line reads `Saved 14:03`, or `Not saved: <server message>`; a 409 shows the reload message and disables the controls.
- "Mark a problem" in a region item → `viewer.pick()` → a mark in that region with kind chosen from a select (default: the first kind), a note field, "go to" and "remove". "Accept as mark" on a finding creates a mark at the finding's position with `finding` set and the kind mapped `pial_out→pial_out`, `gray_missed→gray_missed`, `white_short→white_short`, `crossing→crossing`, `topology→topology`, anything else → `pial_out` (editable).
- Submit posts; on 422 the returned lines are listed above the button and the first unrated item scrolls into view; on success the page reloads (so, in blind mode, the indicators appear).
- Skip saves `skipped: true` and goes to `/next?after=<key>`.
- Keys (ignored while typing): `1` `2` `3` rate the current item; `j` / `k` next / previous item (highlighted, scrolled into view); `m` mark a problem in the current region item; `g` focus the grade; `?` open or close the help panel listing all keys including the viewer's; `Shift+N` next subject. `n` / `p` remain next / previous location.

- [ ] **Step 1: Tests** — `test_review_script_is_loaded_only_when_reviewing`; `test_help_panel_lists_the_rating_keys`; `test_keys_line_mentions_rating_keys`.
- [ ] **Step 2:** FAIL. Commit tests.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Tests PASS. Browser check on `~/surfaceqa-demo` (rebuild first; `BUILD_FORMAT` changed): give a name; rate by keyboard; place a mark on the pial contour and confirm in the saved JSON that `surface` is set, `vertex` is an integer and `tkr` is within 1 mm of the same point read in the viewer; accept a finding; reload and see everything restored; submit with items missing (refused, listed); complete and submit; second reviewer does not see the first one's ratings; `--blind` hides findings until submit. Record what was checked in the ledger. Commit.

### Task 11: Export

**Files:** Create `src/surfaceqa/export.py`; Modify `cli.py` (`export`, `finalize` commands); Tests `tests/test_export.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `export_tables(qa_dir, out_dir: Path | None = None) -> list[Path]` (default `<qa>/export/`); CLI `surfaceqa export QA_DIR [--out DIR]` and `surfaceqa finalize QA_DIR`.
- `finalize` writes the final files, rewrites the static site, and prints one line per subject in disagreement (`<key>: sinus (ann major, bob none); grade (ann A, bob C)`), then counts by status. Exit code 0.
- Tables, tab-separated with a header, tabs and newlines in notes replaced by spaces:
  - `ratings.tsv`: `key, source, subject, pipeline, version, run, current_run, reviewer, protocol, submitted, revised, item, rating, note`. One row per submitted review and item; the grade is item `overall` (rating = grade, note = notes); an unratable review has one extra row, item `unratable`, note = reason. Reviews of earlier runs are included with `current_run` `no`.
  - `marks.tsv`: `key, run, current_run, reviewer, region, kind, surface, vertex, grid_x, grid_y, grid_z, tkr_x, tkr_y, tkr_z, finding, note`.
  - `final.tsv`: `key, run, status, reviewers, item, final, disagree` — one row per item plus `overall` and `unratable`; from the final files; a stale final is written with status `stale`.
  - `indicators.tsv`: `key, source, subject, pipeline, version, run, score, indicator, status, n_findings, reason` — one row per subject and indicator; subjects without indicator results have one row with `indicator` empty and `status` `not computed`.

- [ ] **Step 1: Tests** (fixture `qa_reviewed`)
  - `test_ratings_table_has_one_row_per_submitted_review_and_item` (ann and bob × 12 rows; ann's draft of sub-02 absent)
  - `test_grade_is_exported_as_the_overall_item`
  - `test_notes_with_tabs_and_newlines_stay_on_one_row`
  - `test_marks_table_has_one_row_per_mark_with_coordinates`
  - `test_final_table_is_written_after_finalize_and_marks_stale_finals`
  - `test_indicator_table_has_a_row_per_indicator_and_the_score`
  - `test_export_without_any_review_writes_headers_only`
  - `test_ratings_of_an_earlier_run_are_exported_as_not_current`
  - CLI: `test_export_command_writes_four_tables`; `test_finalize_command_lists_disagreements`; `test_finalize_and_export_refuse_a_folder_that_is_not_a_qa_directory` (exit 2)
- [ ] **Step 2:** FAIL. Commit tests. **Step 3:** Implement. **Step 4:** PASS, full suite. Commit.

### Task 12: Use it on the three reconstructions, and document

**Files:** Modify `README.md`; ledger only otherwise

- [ ] **Step 1:** Rebuild `~/surfaceqa-demo` from the three subject-07 folders; confirm nothing under `/Volumes/extdata1/NSD/BIDS/derivatives` changed (compare a listing with modification times before and after).
- [ ] **Step 2:** Review one subject fully as two reviewers through the browser with a deliberate two-step disagreement; run `finalize` (disagreement listed), settle it as `consensus`, run `finalize` again (settled), run `export` and read the four tables.
- [ ] **Step 3:** Write `README.md`: what the tool is, the five commands with one example each, how a review session goes, the keys, where ratings are stored, what blind mode does, and that scores only order the work. No claims beyond what was checked.
- [ ] **Step 4:** Full suite green. Commit.
