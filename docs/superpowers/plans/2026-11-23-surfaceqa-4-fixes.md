# surfaceqa stage 4: fix guidance — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (the user chose native execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For every problem a reviewer marks in a region rated "Major (needs fix)", the subject page shows what to edit, the `freeview` command that opens the right files at that spot, and the command that reruns the subject; for FastSurfer and for recon-all 8.

**Architecture:** The recipe wording lives in one versioned data file, `recipes.json`, with one block per pipeline. `build` records, per run, the subject's original command line and whether it looks edited (`provenance.json`), so guidance works when the source volume is not mounted. A pure module turns (run meta, provenance, marks) into a guidance record; the server renders it as an HTML fragment that the review page reloads after each save.

**Tech Stack:** Python 3.13, uv, FastAPI, Jinja2, nibabel, numpy; vanilla JS; pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-22-surfaceqa-design.md`, section "Fix guidance" (and "Pipelines", "Ratings" for the edited flag).

## Global Constraints

- `uv` for packages, `uv run` for every command. No new dependencies.
- No code or imports in `__init__.py`.
- pytest, functions and fixtures, no test classes. Tests written first, seen to fail, committed before the implementation.
- Short functions; one responsibility per module.
- Nothing is ever written into a source (derivatives) folder. The tool never runs an edit or a rerun itself; it only shows commands.
- FastSurfer guidance never tells anyone to edit `mri/mask.mgz`, `mri/brainmask.mgz`, `tmp/control.dat`, seed files or `mri/aseg.presurf.mgz`.
- Guidance is made only from marks in regions rated major by a person. No indicator finding produces guidance on its own.
- Visibility rules of stage 3 hold: guidance from the final labels is shown only to someone allowed to see the final labels.
- Commit messages end with `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.

## Where the recon-all recipes come from

The spec left these to be researched. Findings (wiki tutorials are from the 7.x era and name no version; the 8.x behaviour was read from the `recon-all` script, 8.1.0 installed locally and 8.2.0 on GitHub):

- 8.x `recon-all` runs with `-fix-vsinus -fix-mca-dura -synthstrip -synthseg -synthmorph` by default (`etc/global-expert-options.v8.txt`).
- `mri/vsinus.mgz` and `mri/mca-dura.mgz` are segmentations of the venous sinuses and the dura near the middle cerebral artery. They are used only to set those voxels to 1 in `mri/brain.finalsurfs.mgz`, which keeps the pial surface out of them.
- `mri/brain.finalsurfs.manedit.mgz` is created by recon-all itself (a copy of `brain.finalsurfs.mgz`). On a rerun, its voxels of value 255 and 1 are transferred into `brain.finalsurfs.mgz`.
- `mri/brainmask.mgz` is rebuilt from `T1.mgz` and `synthstrip.mgz` whenever those are newer; the "will not be overwritten" protection exists only for the old skull strip. So brainmask edits (the 7.x tutorial's advice for pial errors) can be lost on a full rerun in 8.x.
- `mri/wm.mgz` edits (255 fill, 1 erase) and `tmp/control.dat` are kept and used as in 7.x.
- Rerun flags that still exist: `-autorecon-pial`, `-autorecon2-wm`, `-autorecon2-cp`, `-autorecon3`. `-make all` is refused by the script. `-T2pial` is not remembered between runs; it has to be given again.
- The original command is the line after `setenv SUBJECTS_DIR` at the top of `scripts/recon-all.log`.

## Decisions made in this plan (designer's calls, for the user to correct)

1. **recon-all, pial too far out: edit `brain.finalsurfs.manedit.mgz`, not `brainmask.mgz`.** This departs from the 7.x tutorial (which says brainmask except near the cerebellum) because of the overwrite risk above, and because it is how 8.x itself removes sinus and dura. The recipe names the brainmask route as the older documented alternative, with the caveat.
2. **recon-all recipe table** (in the order to try):

   | Problem | Recipe | Rerun |
   |---|---|---|
   | Pial too far out | Erase (value 1) the non-brain voxels in `mri/brain.finalsurfs.manedit.mgz`. | `-autorecon-pial` |
   | Gray matter missed | 1. If the white surface is also short there, fix the white surface first (next row). 2. If `brain.finalsurfs.mgz` is 1 there (the sinus or dura mask removed real cortex), paint 255 in `brain.finalsurfs.manedit.mgz`. | as the step used |
   | White surface short of white matter | 1. Fill (255) the missing white matter in `mri/wm.mgz`. 2. If the white matter there is darker than 110 in `brainmask.mgz`, add control points (`tmp/control.dat`) in definite white matter instead. | `-autorecon2-wm -autorecon3`; `-autorecon2-cp -autorecon3` |
   | White surface past white matter | Erase (1) the non-white-matter voxels in `mri/wm.mgz`. | `-autorecon2-wm -autorecon3` |
   | Topology defect | Look at `surf/?h.orig.nofix` at the defect; fill holes (255) or erase bridges (1) in `mri/wm.mgz`. | `-autorecon2-wm -autorecon3` |
   | Hemispheres crossing | No dedicated edit is documented. If the white surfaces cross, edit `wm.mgz` there; if only the pial surfaces touch, erase the voxels between them in `brain.finalsurfs.manedit.mgz`. | as the step used |

   Every recon-all recipe carries the wiki's cautions: edit a copy of the subject, edit as little as possible, do not erase cerebellum from the brainmask, do not edit the aseg.
3. **Rerun command for recon-all** is built from the original: `recon-all -s <name>` + the stage flags + the original's other options, with the inputs (`-i`, `-T2 <file>`, `-FLAIR <file>`) and `-all` removed, `-expert <file>` replaced by `-xopts-use`, and `-T2pial` / `-FLAIRpial` kept. The page says it must be run with the same `SUBJECTS_DIR` and FreeSurfer version.
4. **Versions.** The FastSurfer recipes are marked as written for 2.6, the recon-all ones for 8. Any other version (the `freesurfer-NSD` folder is 6.0.0) or an unknown pipeline gets a warning at the top of the guidance; an unknown pipeline is shown no recipe steps, only the marked problems.
5. **`freeview` command** uses the subject folder path recorded at build time and the mark's surface coordinate: `-ras X Y Z tkreg -cc`. Surfaces are colored as in the report (pial yellow, left white blue, right white red). The volume to edit is loaded on top of `orig.mgz`.
6. **Which marks drive the guidance.** A reviewer sees guidance from their own review while reviewing. Once final labels exist, are up to date, are not in disagreement, and the viewer may see them, guidance comes from the final labels' pooled marks. Without a name (outside blind mode) only final guidance is shown.
7. **Edited flag** (spec: from the logs and file contents, not from the existence of manedit files). A subject counts as edited when any of these holds; the evidence is listed on the page and `edited` is added to every export table:
   - FastSurfer: `--edits` on an `Invocation:` line of `deep-seg.log` or `recon-surf.log`; `mri/aparc.DKTatlas+aseg.deep.manedit.mgz` exists; `brain.finalsurfs.manedit.mgz` differs from `brain.finalsurfs.mgz`.
   - recon-all: `tmp/control.dat` exists; `mri/aseg.manedit.mgz` exists; `mri/wm.mgz` has voxels of value 255 or 1 (the script's own test); a later invocation in `recon-all.log` used an `-autorecon…` flag.
   A recon-all pial edit that has already been rerun cannot be told from the sinus mask by file contents; the log test covers it.
8. **Rerun template.** `surfaceqa build --rerun-template '<launch line with {command}>'` stores the template for the source folders of that build in `<qa>/settings.json`. Guidance then shows the complete line. Without it, FastSurfer guidance shows the in-container command and says it needs the same container setup as the first run.
9. **Not in this stage:** using `vsinus.mgz` / `mca-dura.mgz` in the sinus indicator for recon-all subjects. It fits better with the indicator work of stage 5.

## Review Focus

1. A subject whose log has no command line (or no log): guidance shows a template with placeholders, never an empty or half command.
2. A path or subject name with spaces or shell characters: every shown command is quoted so that pasting it is safe.
3. A mark without a usable coordinate, or of a kind the pipeline has no recipe for: the problem is still listed, without a broken `freeview` line.
4. A FastSurfer original command that already contains `--edits` or `--surf_only`: neither is added twice, and the "segmentation edited" variant has no `--surf_only`.
5. A reviewer who has not submitted asks for the guidance address directly: they get guidance from their own marks only, never the final labels or others' marks (also in blind mode).

---

### Task 1: Recipe data

**Files:** Create `src/surfaceqa/recipes.json`, `src/surfaceqa/recipes.py`; Test `tests/test_recipes.py`.

**Interfaces — Produces:**
- `load_recipes() -> dict` (cached): `{"version": 1, "pipelines": {"fastsurfer": P, "freesurfer": P}, "region_notes": {region_id: text}}` with `P = {"written_for": "2.6" | "8", "docs": url, "recipes": {kind_id: {"steps": [STEP]}}, "never_edit": [str], "cautions": [str], "rerun_note": str}` and `STEP = {"text": str, "edit": relative file | null, "copy_from": relative file | null, "paint": str, "rerun": rerun id, "overlay": bool}`.
- Rerun ids: FastSurfer `"seg"`, `"surf"`; recon-all `"pial"`, `"wm"`, `"cp"`.
- `recipe_for(pipeline: str, kind: str) -> dict | None`
- `version_warning(pipeline: str, version: str | None) -> str | None`: `None` when the version starts with the block's `written_for` major(.minor); otherwise a sentence naming both versions; for an unknown pipeline a sentence saying no recipes exist.

- [ ] **Step 1: tests** — `test_every_mark_kind_has_a_recipe_for_both_pipelines` (kinds from `protocol.json`); `test_fastsurfer_recipes_follow_the_spec_table`: `pial_out` and `gray_missed` steps edit, in order, `mri/aparc.DKTatlas+aseg.deep.manedit.mgz` (copy from `mri/aparc.DKTatlas+aseg.deep.mgz`, rerun `seg`) then `mri/brain.finalsurfs.manedit.mgz` (rerun `surf`; paint text contains `1` for `pial_out`, `255` for `gray_missed`); `white_short`, `white_past`, `topology` end with a step naming `mri/wm.mgz` and `mri/filled.mgz` (rerun `surf`); `crossing` text contains "No dedicated edit is documented". `test_fastsurfer_never_edit_list` equals the five files in Global Constraints and no FastSurfer step edits one of them. `test_freesurfer_recipes_follow_the_plan_table`: edit files and rerun ids as in decision 2; no step edits `mri/brainmask.mgz`. `test_region_notes` exist for `inferior_temporal` and `medial_temporal` and no other region. `test_version_warning`: `("fastsurfer","2.6.1")` and `("freesurfer","8.2.0")` → `None`; `("freesurfer","6.0.0")` mentions `6.0.0` and `8`; `("fastsurfer", None)` and `("unknown", None)` → a warning.
- [ ] **Step 2:** run `uv run pytest tests/test_recipes.py -q` — FAIL (module missing). Commit tests.
- [ ] **Step 3:** write `recipes.json` (wording from the spec table for FastSurfer, decision 2 for recon-all; cautions: FastSurfer's "edits can introduce systematic effects; keep track of edited subjects", the wiki's four cautions for recon-all; region notes: Kay's "often not worth fixing" for ear-canal dropout and the hippocampal region) and `recipes.py`.
- [ ] **Step 4:** run — PASS. Commit.

### Task 2: Original command and rerun commands

**Files:** Create `src/surfaceqa/invocation.py`; Modify `tests/synth.py` (`write_subject(..., command: str | None = DEFAULT)` writes an `Invocation:` line into `deep-seg.log`, or the four-line header into `recon-all.log`; `command=None` writes neither); Test `tests/test_invocation.py`.

**Interfaces — Produces:**
- `original_command(subject_dir: Path, pipeline: str) -> str | None` — FastSurfer: text after `Invocation: ` on the first such line of `scripts/deep-seg.log`. recon-all: the first line of `scripts/recon-all.log` whose first word ends in `recon-all`.
- `rerun_commands(pipeline: str, command: str | None, name: str, template: str | None = None) -> dict[str, str]` keyed by rerun id. `template` wraps each command by replacing `{command}`.
- `PLACEHOLDER` commands used when `command` is `None`: `run_fastsurfer.sh <the options of the first run> --edits [--surf_only]` and `recon-all -s <name> <stage flags>`.

- [ ] **Step 1: tests** — with the spec's example line: `seg` = original + ` --edits`; `surf` = original + ` --edits --surf_only`; `--t1` value unchanged. Original already containing `--edits --surf_only`: `seg` has `--edits` once and no `--surf_only`; `surf` has each once. recon-all example `/usr/local/freesurfer/8.2.0/bin/recon-all -subjid sub-07 -i a.nii.gz -i b.nii.gz -T2 t2.mgz -T2pial -3T -all -parallel -openmp 8` → `pial` = `recon-all -s sub-07 -autorecon-pial -T2pial -3T -parallel -openmp 8`; `wm` uses `-autorecon2-wm -autorecon3`; `cp` uses `-autorecon2-cp -autorecon3`; `-expert opts.txt` becomes `-xopts-use`. A name with a space is shell-quoted. No command → the placeholders, containing `<`. Template `docker run --gpus all img {command}` wraps every command. `original_command` reads both synthetic logs, returns `None` for a missing log, and for a log with two invocations returns the first.
- [ ] **Step 2:** run — FAIL. Commit tests.
- [ ] **Step 3:** implement with `shlex.split` / `shlex.join`.
- [ ] **Step 4:** run — PASS. Commit.

### Task 3: Edited flag and provenance file

**Files:** Create `src/surfaceqa/edits.py`, `src/surfaceqa/provenance.py`; Modify `src/surfaceqa/build.py`; Test `tests/test_edits.py`, `tests/test_provenance.py`, `tests/test_build.py`.

**Interfaces — Produces:**
- `detect_edits(subject_dir: Path, pipeline: str) -> list[str]` — the evidence sentences of decision 7; empty when unedited.
- `provenance.PROVENANCE_VERSION = 1`, `PROVENANCE_FILE = "provenance.json"`
- `write_provenance(ref: SubjectRef, pipeline: PipelineInfo, run_dir: Path) -> bool` — writes `{"version", "command": str | None, "edited": bool, "evidence": [str], "signature": {...}}`; returns `False` and writes nothing when the stored file has the current version and signature (size and mtime of the log files and edit carriers).
- `load_provenance(qa_dir: Path, key: str) -> dict | None` — `None` for a missing or wrong-shaped file.
- `build_subject` calls `write_provenance` after the indicators; a rewrite of an already rendered run gives status `"updated"`; a failure here is caught and leaves the viewer (same rule as indicator failures).

- [ ] **Step 1: tests** — unedited synthetic subjects of both pipelines, including one where `brain.finalsurfs.manedit.mgz` is an identical copy → `[]`. One test per evidence line of decision 7, each asserting the sentence names the file or flag. `write_provenance` round trip; unchanged second call returns `False`; adding `tmp/control.dat` makes the next build `"updated"` with `edited` true; a `provenance.json` holding a JSON list loads as `None`; build with `detect_edits` raising still returns `"built"` and `load_meta` works; build never changes the source (existing test covers it — keep it green).
- [ ] **Step 2:** run — FAIL. Commit tests.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** `uv run pytest -q` — PASS. Commit.

### Task 4: Rerun template setting

**Files:** Create `src/surfaceqa/settings.py`; Modify `src/surfaceqa/cli.py`; Test `tests/test_settings.py`, `tests/test_cli.py`.

**Interfaces — Produces:**
- `save_rerun_template(qa_dir: Path, sources: list[str], template: str) -> None` (merges into `<qa>/settings.json`), `rerun_template(qa_dir: Path, source: str) -> str | None` (missing or malformed file → `None`).
- `surfaceqa build ... --rerun-template TEMPLATE`; a template without `{command}` is a usage error (exit 2, message names `{command}`), checked before anything is built.

- [ ] **Step 1: tests** — round trip; two builds with different sources keep both templates; malformed `settings.json` → `None`; CLI stores the template under each source name; CLI rejects a template without the placeholder and builds nothing.
- [ ] **Step 2:** run — FAIL. Commit tests.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run — PASS. Commit.

### Task 5: Guidance record

**Files:** Create `src/surfaceqa/freeview.py`, `src/surfaceqa/guidance.py`; Test `tests/test_freeview.py`, `tests/test_guidance.py`.

**Interfaces — Consumes:** `recipe_for`, `version_warning`, `load_recipes`, `rerun_commands`, mark dicts (`region`, `kind`, `tkr`, `note`, optional `reviewer`), run meta (`path`, `name`, `pipeline`, `version`), provenance dict or `None`.

**Produces:**
- `freeview_command(subject_path: str, edit: str | None, tkr: list[float] | None, overlay: bool = False) -> str` — `freeview -v <S>/mri/orig.mgz [<S>/<edit>[:colormap=heat:opacity=0.4]] -f <S>/surf/lh.white:edgecolor=blue <S>/surf/lh.pial:edgecolor=yellow <S>/surf/rh.white:edgecolor=red <S>/surf/rh.pial:edgecolor=yellow [-ras X Y Z tkreg -cc] -viewport coronal`, coordinates to two decimals, every path shell-quoted.
- `build_guidance(meta: dict, provenance: dict | None, marks: list[dict], template: str | None) -> dict | None` — `None` when `marks` is empty; otherwise `{"warning": str | None, "problems": [{"region", "region_title", "kind", "kind_label", "note", "reviewer", "region_note": str | None, "steps": [{"text", "paint", "edit", "copy": str | None, "freeview": str, "rerun": {"label", "command"}}]}], "never_edit": [str], "cautions": [str], "rerun_note": str, "edited": bool, "evidence": [str], "docs": url | None}`. `copy` is `cp <from> <to>` with full quoted paths, only for steps that have `copy_from`. Problems are ordered by region (checklist order).

- [ ] **Step 1: tests** — freeview: exact string for a plain case; a subject path with a space is quoted; no `tkr` → no `-ras`; `overlay` adds the colormap suffix. guidance: FastSurfer `pial_out` mark → two steps, first with the copy command and the `seg` rerun (no `--surf_only`), second with the `surf` rerun; the `freeview` line carries the mark's coordinate and the step's file; recon-all `white_short` → `wm` then `cp` reruns, original `-T2pial` carried; mark in `medial_temporal` has a region note, in `sinus` none; FreeSurfer 6.0.0 → warning set, steps still present; unknown pipeline → warning set, `steps == []`, problem still listed; mark kind without a recipe → listed with `steps == []`; provenance `None` → placeholder commands; template applied; no marks → `None`; FastSurfer result's `never_edit` is the five files.
- [ ] **Step 2:** run — FAIL. Commit tests.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run — PASS. Commit.

### Task 6: Which marks, and the page

**Files:** Create `src/surfaceqa/site_guidance.py`, `src/surfaceqa/web/templates/_guidance.html`; Modify `src/surfaceqa/site_reviews.py` (expose what is needed), `src/surfaceqa/site.py` (`render_guidance(record) -> str`; record gains `guidance`, `guidance_from`, `edited`, `evidence`), `subject.html` (`<section id="guidance">` after the review), `_header.html` ("edited" badge), `index.html` (edited marker beside the pipeline), `export.py` (`edited` column in every table), `app.css`; Test `tests/test_site.py`, `tests/test_export.py`.

**Interfaces — Produces:**
- `guidance_fields(qa_dir, record, view, review_fields: dict) -> dict` implementing decision 6: marks of regions rated major, from the final labels (`guidance_from = "final"`) or from the viewer's own review (`"own"`), else `guidance = None`. Marks in a region not rated major are ignored.
- The fragment lists, per problem: region, kind, note, the steps as a numbered list, and each command in a `<pre class="command">` with a "Copy" button; then the do-not-edit list, the cautions, the edited evidence, the version warning at the top, and a last line "After the rerun, run `surfaceqa build` again; the subject then needs a new review."

- [ ] **Step 1: tests** — named reviewer with a draft holding a major region and a mark: page contains the recipe file name and `freeview`; the same reviewer with the mark's region rated minor: no guidance section content; second reviewer who has not submitted sees none of the first reviewer's guidance; after `finalize` and own submission the fragment says it comes from the final labels and pools both reviewers' marks; final in disagreement → own marks; stale final → own marks; unnamed overview shows final guidance, and nothing in blind mode; a note containing `<script>` is escaped; edited subject shows the badge and evidence; export tables have an `edited` column (`yes`/`no`).
- [ ] **Step 2:** run — FAIL. Commit tests.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** `uv run pytest -q` — PASS. Commit.

### Task 7: Server route and live refresh

**Files:** Modify `src/surfaceqa/server.py` (`GET /subjects/{key}/guidance` → the fragment for the current viewer; 404 for an unknown key; in blind mode without a name 404), `src/surfaceqa/web/static/review.js` (after each successful save or submit, fetch the fragment and replace `#guidance`; "Copy" buttons use `navigator.clipboard`, falling back to selecting the text), `README.md` (fix guidance section; `--rerun-template`; remove fix guidance from "Not built yet"); Test `tests/test_server.py`.

- [ ] **Step 1: tests** — after `PUT` of a review with a major region and mark, `GET …/guidance` returns the recipe; reviewer B's request returns no recipe; after both submit and finalize, B's request shows the final guidance; unknown key → 404; blind without a name → 404; the address with a trailing slash or other case → 404.
- [ ] **Step 2:** run — FAIL. Commit tests.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** `uv run pytest -q` — PASS. Commit.

### Task 8: Real data check

- [ ] Rebuild `~/surfaceqa-demo` from the three source folders (source listing hash identical before and after); confirm statuses are `updated`, not `built`.
- [ ] In a browser: mark a pial problem on `fastsurfer__sub-07` and on `freesurfer-8.2.0__sub-07`; confirm the guidance appears after the save without a reload, the rerun lines match the logs (`--3T --threads 8`; `-T2pial -3T -parallel -openmp 8`), and `freesurfer-NSD` shows the version warning.
- [ ] Run the shown `freeview` command for one mark with the local FreeSurfer 8.1 and confirm from a screenshot that the cursor is on the marked contour.
- [ ] Integration tests for the three real subjects (skipped when the volume is not mounted): `original_command` is found and `detect_edits` is empty.
