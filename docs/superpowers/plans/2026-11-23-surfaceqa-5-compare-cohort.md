# surfaceqa stage 5: comparison and cohort thickness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (the user chose native execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (A) A subject's thickness is compared, place by place, with the other subjects of its source folder, and patches that are much thicker than the cohort become findings. (B) A subject page can show a second reconstruction of the same person (another pipeline, or the previous run of an edited subject) next to the viewer, kept at the same scanner coordinates.

**Architecture:** (A) `build` writes, per run, the subject's thickness sampled at a fixed set of points on the registration sphere. A cohort pass then computes the median and spread per point for each source folder, and the cohort indicator runs with the other indicators, so its findings live in the same `findings.json`. (B) Every run gets a small standalone viewer page. The subject page loads the chosen one in a frame beside its own viewer, and the two exchange cursor positions as scanner coordinates.

**Tech Stack:** Python 3.13, uv, nibabel, numpy, scipy, FastAPI, Jinja2; vanilla JS; pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-22-surfaceqa-design.md`, sections "Indicators" (cohort thickness outliers) and "Comparing two reconstructions of one subject".

## Global Constraints

- `uv` for packages, `uv run` for every command. No new dependencies.
- No code or imports in `__init__.py`.
- pytest, functions and fixtures, no test classes. Tests written first, seen to fail, committed before the implementation.
- Short functions; one responsibility per module.
- Nothing is ever written into a source folder. Building needs no FreeSurfer binaries and no fsaverage folder.
- Indicators only rank and point. The cohort indicator never produces a rating, and where it is off the page says so.
- Blind review: nothing an indicator produced reaches a reviewer before they submit that subject. This holds for the new viewer pages and for earlier runs.
- Commit messages end with `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.

## Facts found while planning

- **The sinus and dura segmentations are already used.** Stage 2 built `ribbon_in_nonbrain_mask`, which reads `mri/vsinus.mgz` and `mri/mca-dura.mgz`. The item I proposed for this stage is done; nothing is planned for it.
- **There is no real cohort to test on.** The mounted data has at most three reconstructions per source folder, all of subject 07. The cohort indicator can be verified on synthetic data only; its thresholds are uncalibrated until the 50 subjects exist.
- **No fsaverage is needed.** Each subject's `surf/?h.sphere.reg` already places its vertices in the common (fsaverage-aligned) spherical coordinates. Sampling every subject at the same fixed points on that sphere gives comparable maps.
- `viewer.js` holds one viewer per page in module state. Two viewers on one page would need a rewrite; a frame needs none.

## Decisions made in this plan (designer's calls, for the user to correct)

1. **The cohort is the source folder**, as for the suspicion rank (the spec says "same pipeline"; a source folder is one pipeline, version and resolution).
2. **On at 30 subjects** with a thickness map in the source folder (the spec's "about 30"). Below that the indicator is listed as not run, with "needs 30 subjects in this source folder; there are N".
3. **Thick only.** A finding is a connected patch of at least 50 cortex vertices that are each at least 4 robust standard deviations (median and scaled MAD across the cohort) and at least 1.0 mm thicker than the cohort median there. Thin patches are not reported, as in the existing thickness indicator.
4. **The subject is part of its own cohort** (no leave-one-out). With a median over 30 or more subjects the difference is negligible.
5. **Findings are of kind `thickness`** (weight 0.5 in the score), with the text "thicker than the cohort".
6. **A change in the cohort recomputes the indicators of every subject in that source folder** on the next `build` (adding one subject changes everyone's comparison). Slices and contours are not re-rendered.
7. **Comparison candidates** are (a) subjects in other source folders with the same subject label, where the label is the name without a `_ses-…` suffix, without `sub-`/`subj`/`sub` and without leading zeros (`sub-07`, `subj07`, `sub-07_ses-nsdanat` all give `7`), and same-label subjects in the same folder; (b) earlier runs of the same subject.
8. **Layout.** With three views shown, the comparison's three views sit in a row directly under the subject's, so each plane is above its counterpart. With one view shown, the two are left and right. The subject's own viewer stays the one that is reviewed and marked; the comparison is view-only.
9. **Linking** is by scanner coordinates, with a "Linked" checkbox to scroll the two independently. Reconstructions made from different scans (the NSD FreeSurfer 6 one) will not line up; a line under the comparison says so. Zoom is not linked.
10. **An earlier run built before this stage has no scanner matrix.** It is linked by surface (tkr) coordinates, which is right when the edited rerun used the same T1.
11. **Build format 4**: every current run is re-rendered once on the next `build`, to record the scanner matrix. Reviews are unaffected (the run id does not change).

## Review Focus

1. A blind reviewer opens `runs/<run>/viewer.html` or the findings of an earlier run directly: nothing an indicator produced before they submit; nothing at all before a name is given.
2. A subject whose `sphere.reg`, thickness or cortex label is missing, unreadable or of another vertex count: that hemisphere is left out with a reason; the build and the cohort survive.
3. Cohort points where fewer than 30 subjects have cortex (medial wall edge): no comparison there, no division by a zero spread.
4. A cohort that shrinks below 30, or a subject rebuilt with new surfaces: old cohort findings do not linger.
5. The viewer route with a run name or key that is not one (`..`, another subject's run): 404. A message from a window that is not the comparison frame: ignored.

---

### Task 1: Scanner coordinates in the run

**Files:** Modify `src/surfaceqa/geometry.py`, `src/surfaceqa/build.py`; Test `tests/test_geometry.py`, `tests/test_build.py`.

**Interfaces — Produces:** `DisplayVolume.grid_to_scanner: np.ndarray` (4×4, display grid index → scanner RAS mm); `meta["grid_to_scanner"]` (nested list); `BUILD_FORMAT = 4`.

- [ ] Tests first: for a synthetic volume written with `orientation="PIR"`, `voxel=(1.0, 0.7, 1.3)`, `cras=(3, -2, 5)`, `grid_to_scanner` applied to a grid index equals the image affine applied to the corresponding file voxel; `grid_to_scanner[:3, 3] - grid_to_tkr[:3, 3] == cras`; `meta["grid_to_scanner"]` is 4×4; a format-3 run is rebuilt (the existing format test, with the constant; `test_build_writes_findings` asserts `format == 4`, a requirement change).
- [ ] Run, see them fail. Commit tests.
- [ ] Implement (`img.affine @ inv_ornt_aff(transform, img.shape)`). Run all tests. Commit.

### Task 2: Thickness on the common sphere

**Files:** Create `src/surfaceqa/sphere.py`, `src/surfaceqa/thickness_map.py`; Test `tests/test_sphere.py`, `tests/test_thickness_map.py`; Modify `tests/synth.py` (`write_qa_files` gains `sphere_reg=True` writing `surf/?h.sphere.reg` as the pial vertices scaled to radius 100, and `thickness=` per-hemisphere override).

**Interfaces — Produces:**
- `sphere.TARGET_ORDER = 6`; `sphere.target_points() -> np.ndarray` (40962×3 unit vectors, cached); `sphere.icosphere(order) -> (vertices, faces)`; `sphere.nearest(points, queries) -> np.ndarray` (index into `points` for each query, both normalised to unit length).
- `thickness_map.MAP_FILE = "thickness_map.npz"`; `write_thickness_map(subject_dir: Path, run_dir: Path) -> bool` (True when written or removed; skips when its stored input signature and `MAP_VERSION` match); `load_thickness_map(run_dir) -> dict[str, np.ndarray] | None` (hemi → float32 of length 40962, NaN outside the cortex label; a hemisphere that cannot be mapped is absent; None when no hemisphere can).

- [ ] Tests first: `target_points()` has 40962 unit rows; `nearest` returns the right index for rotated copies; a subject whose thickness is 2.5 everywhere with a planted 5.0 cap gives a map that is 5.0 at target points inside the cap and 2.5 outside; vertices outside the cortex label give NaN; a `sphere.reg` with another vertex count than the thickness file, a missing file and a truncated file each leave that hemisphere out; nothing is written when inputs are unchanged; the source folder is untouched.
- [ ] Run, see them fail. Commit tests.
- [ ] Implement. Run all tests. Commit.

### Task 3: Cohort statistics

**Files:** Create `src/surfaceqa/cohort.py`; Modify `src/surfaceqa/thresholds.py` (`MIN_COHORT = 30`, `COHORT_Z = 4.0`, `COHORT_MIN_MM = 1.0`, `MIN_COHORT_VERTICES = 50`); Test `tests/test_cohort.py`.

**Interfaces — Consumes:** `load_thickness_map`, `layout.current_run_dir`. **Produces:**
- `@dataclass Cohort: source: str; n: int; signature: str; median: dict[str, np.ndarray] | None; spread: dict[str, np.ndarray] | None` (`median is None` when off).
- `update_cohorts(qa_dir) -> set[str]`: for every source folder in the QA directory, gathers the maps of the current runs, writes `<qa>/cohort/<source>.json` (`{version, n, signature, members: {key: run}}`) and, when `n >= MIN_COHORT`, `<qa>/cohort/<source>.npz`; removes the `.npz` when off; returns the sources whose signature changed.
- `load_cohort(qa_dir, source) -> Cohort | None` (None when never computed).
- `spread = 1.4826 × MAD`; a point with fewer than `MIN_COHORT` non-NaN subjects has NaN median and spread.

- [ ] Tests first (with `MIN_COHORT` monkeypatched to 5 and maps written directly): median and spread equal numpy's on a constructed stack; a point where only 4 subjects have values is NaN; 4 subjects → off, `n == 4`, no `.npz`; adding a subject changes the signature and the returned set; an unchanged cohort returns an empty set and rewrites nothing; a cohort that drops below the minimum removes the `.npz`; two source folders are independent; a subject without a map is not counted.
- [ ] Run, see them fail. Commit tests.
- [ ] Implement. Run all tests. Commit.

### Task 4: The cohort indicator

**Files:** Create `src/surfaceqa/indicators_cohort.py`; Modify `src/surfaceqa/subjectdata.py` (`HemiSurface.sphere: np.ndarray | None`; `SubjectData.cohort: Cohort | None = None`; `load_subject_data(subject_dir, pipeline, cohort=None)`; `sphere.reg` in `_input_files`), `src/surfaceqa/qa.py` (indicator added; `QA_VERSION = 8`), `src/surfaceqa/checklist.py` (text by indicator: `cohort_thickness` → "thicker than the cohort"); Test `tests/test_indicators_cohort.py`, `tests/test_qa.py`, `tests/test_subjectdata.py`.

**Interfaces — Produces:** `cohort_thickness(data: SubjectData) -> IndicatorResult`, name `"cohort_thickness"`, kind `"thickness"`. Not run with: `"needs 30 subjects in this source folder; there are N"` (cohort None counts as 0), or `"no sphere.reg"`. A hemisphere without usable files is named in `reason`, as in `thick_patches`.

- [ ] Tests first: a subject with a planted 5 mm patch of ≥ 50 vertices against a flat 2.5 ± 0.1 cohort gives one finding whose `grid` is inside the patch, on the right hemisphere; a patch of 20 vertices gives none; a patch 0.5 mm thicker (many SDs, under 1 mm) gives none; a patch outside the cortex label gives none; points with NaN or zero spread give none and no warning; cohort off → not run with the count in the reason; no `sphere.reg` → not run; the finding gets a region and the text "thicker than the cohort · N vertices"; `findings.json` lists the indicator for every subject.
- [ ] Run, see them fail. Commit tests.
- [ ] Implement, reusing `_connected_groups`, `_vertex_finding`, `_capped`. Run all tests. Commit.

### Task 5: Build in three passes

**Files:** Modify `src/surfaceqa/build.py`, `README.md`; Test `tests/test_build.py`, `tests/test_cli.py`.

**Interfaces — Consumes:** Tasks 2–4. **Produces:** `build_subject(ref, qa_dir)` unchanged in signature: renders, writes the thickness map and provenance, and runs the indicators with the cohort stored on disk (none → off). `build_all` does: (1) per subject, in parallel: render, map, provenance; (2) `update_cohorts`; (3) per subject, in parallel: indicators. The findings' `inputs` signature gains `"cohort": [signature]`, so a changed cohort recomputes them. A subject's status is `updated` when pass 3 recomputed its findings.

- [ ] Tests first (`MIN_COHORT` patched to 5): six synthetic subjects in one folder, one with a planted thick patch → after `build_all` only that subject has a `cohort_thickness` finding and all six list the indicator as ran; four subjects → all "not run" with "there are 4"; a second `build_all` is all `unchanged` and rewrites no findings; adding a seventh subject gives `updated` for the six and `built` for the new one; removing the planted subject's map inputs and rebuilding leaves no cohort finding; with `jobs=2` the results are the same; a failure in the cohort pass leaves every viewer and the other indicators (cohort listed as not run); the source folders are untouched.
- [ ] Run, see them fail. Commit tests.
- [ ] Implement. README: the cohort indicator, when it is on, and that a new subject recomputes its folder. Run all tests. Commit.

### Task 6: A viewer page per run, and the candidates

**Files:** Create `src/surfaceqa/compare.py`, `src/surfaceqa/web/templates/_viewer.html` (the viewer section moved out of `subject.html`), `src/surfaceqa/web/templates/viewer.html`; Modify `src/surfaceqa/site.py`, `src/surfaceqa/server.py`, `subject.html`; Test `tests/test_compare.py`, `tests/test_site.py`, `tests/test_server.py`.

**Interfaces — Produces:**
- `compare.subject_label(name: str) -> str`.
- `compare.candidates(qa_dir, record, records) -> list[dict]`: `{"group": "other" | "previous", "label": str, "href": str}`; others first (label `"<source> · <name>"`), then earlier runs newest first (label `"earlier run, built <date>"`); `href` relative to the subject page: `../<key>/runs/<run>/viewer.html`, key URL-quoted. The record gains `compare: list[dict]`.
- `site.render_viewer(record, run, view) -> str`: a page with a one-line title (name, pipeline, built date), the viewer section for that run and nothing else; `data-findings="off"` when `record["hide_indicators"]`. `write_site` writes `viewer.html` into every run folder that has a `meta.json`.
- `GET /subjects/{key}/runs/{run}/viewer.html`: 404 for an unknown key, a run name not matching `RUN_NAME`, a run without `meta.json`, and for a blind server without a reviewer name.
- `subject.html`: when `subject.compare` is not empty, the toolbar has `<select id="compare-with">` (first option "Compare with…", `<optgroup>`s "Same subject, other reconstruction" and "Earlier runs") and `<label><input type="checkbox" id="compare-linked" checked> Linked</label>`; the viewer section ends with `<div id="compare" hidden><iframe title="Comparison"></iframe><p class="note">…</p></div>`.

- [ ] Tests first: labels for `sub-07`, `subj07`, `sub-07_ses-nsdanat`, `sub-007`, `sub-17` (`7`,`7`,`7`,`7`,`17`); candidates for two sources with the same subject, for a subject with two runs (surface changed and rebuilt), none for a lone subject (no select on the page); a subject with missing files is not a candidate; the route's status codes above; in blind mode the page of an unsubmitted subject has `data-findings="off"` and `findings.json` of an **earlier** run is 404 until the reviewer has submitted; the static `viewer.html` exists for each run; the subject page is otherwise unchanged (existing site tests pass untouched).
- [ ] Run, see them fail. Commit tests.
- [ ] Implement. Run all tests. Commit.

### Task 7: Linking the two viewers

**Files:** Modify `src/surfaceqa/web/static/logic.js`, `viewer.js`, `app.css`, `viewer.html`, `subject.html`; Create `src/surfaceqa/web/static/link.js`; Test `tests/js/logic.test.mjs`, `tests/test_site.py`.

**Interfaces — Produces:**
- `logic.js`: `applyAffine(m, p)`, `invertAffine(m)`, `positionMessage(cursor, meta, layout)` → `{type: "surfaceqa:position", scanner: [x,y,z] | null, tkr: [x,y,z], layout}`, `cursorFromMessage(message, meta)` → grid index (rounded), using `scanner` when the message and the meta both have it, else `tkr`; null for a message of another type or with non-numeric coordinates.
- `viewer.js`: every cursor change goes through one `setCursor(grid, {quiet})`; unless quiet it dispatches `surfaceqa:cursor` on the viewer element; `setLayout` dispatches `surfaceqa:layout`; `window.surfaceqaViewer` gains `cursor()`, `layout()` and `goTo(grid, {quiet: true})` (no scroll into view, no event).
- `link.js`: `link(peer: () => Window | null, enabled: () => boolean)`: posts `positionMessage` to the peer on `surfaceqa:cursor` / `surfaceqa:layout`; on a `message` event whose `source` is the peer, applies `cursorFromMessage` quietly and the layout. On the subject page the peer is the frame, shown and loaded when a comparison is chosen, hidden and emptied on "Compare with…"; on `viewer.html` the peer is `window.parent` (nothing happens when the page is opened on its own). The newly loaded frame is sent the current position once it reports ready.
- CSS: `#compare` under the panels; `.viewer.single #compare` beside them.

- [ ] Tests first (node): `invertAffine` of a rotated, scaled, shifted matrix times the matrix is the identity; a position sent from grid A with one meta and read with another meta (different voxel size and origin, same scanner space) lands on the voxel at the same scanner point; without a scanner matrix on either side the tkr route is used; malformed messages give null. Python: both pages load `link.js`; `viewer.html` has no review, checklist or guidance markup.
- [ ] Run, see them fail. Commit tests.
- [ ] Implement. Run all tests. Commit.

### Task 8: Verification on the real subjects, and the README

**Files:** Modify `README.md` ("Comparing two reconstructions", "Not built yet" removed), `tests/test_real_subjects.py`.

- [ ] Real-data test (skipped when the volume is not mounted): the FastSurfer and the recon-all 8.2 `sub-07` are candidates for each other; each has a thickness map with both hemispheres; the cohort indicator is not run with "there are 1" / "there are 3".
- [ ] Rebuild `~/surfaceqa-demo` (source listing compared before and after). In the browser: FastSurfer `sub-07` compared with recon-all 8.2 `sub-07` — scroll, click and change layout on either side, and check on screenshots that the same sulcus is under both crosshairs; untick "Linked"; compare with the NSD FreeSurfer 6 subject and confirm the note covers the misalignment; a blind reviewer's comparison shows no findings.
- [ ] Cohort mechanics on real data, outside the test suite: build the three recon-all 8.2 reconstructions with the minimum lowered to 3 into a scratch QA directory, to see that real `sphere.reg` files map and that the pass completes. This checks the plumbing, not the thresholds.
- [ ] Run all tests. Commit. Final whole-branch review by an independent reviewer, with this plan's Review Focus.
