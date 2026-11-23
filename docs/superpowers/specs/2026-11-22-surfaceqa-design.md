# surfaceqa: design

Date: 2026-11-22
Status: draft for approval

## Intent

Check the quality of up to about 50 cortical surface reconstructions,
made with FastSurfer or with FreeSurfer `recon-all` (8.2), the way Kendrick Kay does in "Looking at the quality of
FreeSurfer surface reconstructions"
(https://www.youtube.com/watch?v=CVPmWWE_NJs), in far less time than his
roughly 20 minutes of scrolling per subject, with the judgments recorded,
and with concrete fix instructions for every subject judged to have a
problem. Several people will review.

Example input: `/Volumes/extdata1/NSD/BIDS/derivatives/fastsurfer/sub-07`
(FastSurfer 2.6.1, FreeSurfer 8.2.0 underneath, 0.8 mm isotropic NSD T1,
320^3 conformed volumes, about 96k vertices per hemisphere).

The same subject also exists as
`derivatives/freesurfer-8.2.0/sub-07` (recon-all 8.2.0, 1 mm, 256^3,
with a T2) and `derivatives/freesurfer-NSD/subj07` (FreeSurfer 6.0,
0.8 mm, manually edited by the NSD team). These three are the test
material, and the manually edited one is the nearest thing available to
a reference.

## What Kay does (the procedure being supported)

He scrolls coronal slices of the T1 with pial (yellow) and white
(dark red / dark blue) contours overlaid, in passes:

1. Bird's-eye: two plausible hemispheres, no missing lobes, no surface
   jumping across a gap.
2. T1 only, ignoring surfaces: blur, intensity flatness, reslicing /
   banding, defacing artifacts.
3. Pial surface through known trouble spots:
   - sagittal and transverse sinus (worst in the most posterior slices):
     pial extends into sinus
   - cortex / cerebellum interface: pial extends into cerebellum
   - frontal midline, where the two pial surfaces nearly touch
   - inferior frontal membrane: pial includes bright non-brain tissue
   - dura around the outer edge of the brain
   - orbitofrontal cortex and the dropout region near the ear canal:
     gray matter missed
   - hippocampus / brainstem: ambiguous, "par for the course"
4. White surface: gyral crowns underestimated, deep sulci followed,
   left and right hemispheres crossing.
5. An overall letter grade, explicitly dependent on tolerance and on
   which regions matter for the study.

He also compares two processing versions of one subject and says he
would want axial and sagittal views as well as coronal.

## Goals

1. A per-subject browser report that walks a reviewer through Kay's
   passes, with a rating recorded for each pass/region and an overall
   grade.
2. A scrollable slice viewer in the report: the T1 with the pial and
   white (gray/white boundary) surfaces overlaid. (Requested explicitly.
   "Pial and gray surfaces" is read here as pial plus white surface;
   that reading is the designer's.)
3. Automated indicators of the specific errors Kay looks for, used to
   rank subjects and to put the most suspicious locations first.
4. For each region the reviewer marks as needing a fix, a fix recipe
   specific to FastSurfer 2.6.1.
5. An index across subjects: suspicion ranking, review status, grades,
   and a table export of all ratings.

## Non-goals

- Automatic pass/fail without a human. Indicators only rank and point.
- Editing volumes or rerunning FastSurfer for the user.
- General T1 image-quality metrics (MRIQC covers that); the T1 pass is
  a human look.
- A vision-model grader.
- QA of subcortical segmentation, corpus callosum, hypothalamus,
  cerebellum sub-segmentation, or eTIV.
- EPI / functional QC, remote datasets, and a prevalence census, which
  surfcensus (below) covers.

## Anti-goals

- A report that lets a subject look "fine" because no indicator fired.
  Every subject gets the full checklist; an unreviewed region is shown
  as unreviewed, never as OK.
- Writing anything into the FastSurfer derivatives directory.
- Fix advice that contradicts the FastSurfer documentation (for example
  telling people to edit `brainmask.mgz` or add control points, which
  FastSurfer lists as undefined behavior).

## Constraints

- Python, managed with `uv`; all commands via `uv run`.
- pytest, test-first (red, green, refactor), tests committed before
  implementation; test functions and fixtures, not test classes.
- No code or imports in `__init__.py`.
- Short functions, modular code.
- Building reports must not require FreeSurfer binaries (pure Python
  reading of `.mgz` and surface files). `freeview` is needed only by the
  person doing a fix.
- Input lives on an external volume and is read-only as far as this tool
  is concerned.

## Prior art: surfcensus

https://github.com/tknapen/surfcensus (BSD-3-Clause, first published
2026-11-23) is a browser rating app for FreeSurfer surfaces plus EPI
movies. It covers a box around the occipital pole only (sagittal sinus
and falx, tentorium and transverse sinus, white surface), scores
subjects by cortical-thickness outliers in fsaverage space, and records
ratings and click marks. It has no fix guidance, no whole-brain
checklist, and has not been tried on FastSurfer output; several raters
at once is listed as planned. By its own README, nobody has yet rated a
brain with it.

Adapted from it in this design (each marked "from surfcensus" below):
three linked views with crosshairs, hold-a-key to hide contours,
keyboard rating, a none / minor / major scale with written anchors in a
versioned protocol file, marks snapped to the surface, blind and
worst-first ordering, the skip rule, an "unratable" flag, the
two-rater consensus rule, cohort thickness outliers in fsaverage space,
and checking contour placement against Freeview's conventions.

Building on surfcensus directly was considered and not chosen
(designer's call): its scope is the occipital pole and a census of
public data, and the whole-brain checklist, the FastSurfer-specific
indicators, and the fix guidance are most of the work here. Its code is
BSD-licensed, so individual pieces can be reused with attribution if
the builder finds that cheaper.

## Approaches considered

A. **Structured review report.** Render slices with contours, zoom on
   Kay's trouble spots, human rates each, fix recipes follow from the
   ratings. Human sees everything; costs minutes per subject.

B. **Automated flagging only.** Numeric indicators report problems with
   no human. Near-zero human time, but the indicators are unvalidated
   and a missed error is silent.

C. **Vision-model grader.** Send slice images to a model. Unvalidated
   and hard to trust for errors on the order of 1 mm.

**Chosen (by the user): A with B's indicators built in.** Indicators
rank and sort; a person makes every call. The ratings collected over
the 50 subjects are then the evidence for how well the indicators work.
C is left out.

## Design

### Commands

- `surfaceqa build <fastsurfer_dir> --out <qa_dir> [--subjects ...]`
  For each subject: read inputs, compute indicators, render viewer
  assets and region panels, write the subject report and refresh the
  index. Safe to rerun; subjects run in parallel.
- `surfaceqa serve <qa_dir> [--host ...] [--blind]`
  Web server for reviewing. Serves the reports and saves ratings.
  Listens on the local machine by default; `--host` makes it reachable
  by other reviewers on the lab network. There are no accounts or
  passwords: a reviewer gives a name (designer's call; this assumes a
  trusted network).
- `surfaceqa finalize <qa_dir>`
  Combines the raters' ratings into final labels and lists
  disagreements (see Several reviewers).
- `surfaceqa export <qa_dir>`
  Writes one table (TSV) of all ratings, grades, and indicator values.

Default `<qa_dir>` is a sibling `surfaceqa/` folder next to the
FastSurfer derivatives folder (designer's call).

### Pipelines

`<fastsurfer_dir>` may be a FastSurfer or a recon-all subjects folder,
and `build` may be given several. Each subject's pipeline and version
are detected from its logs and build stamp and shown in the report.
Folder names like `sub-07`, `subj07` and `sub-07_ses-nsdanat` are all
accepted as subjects.

Everything pipeline-specific sits behind one small adapter per
pipeline: which files play which role, how the original command is
recovered, and which fix recipes apply. A subject from an unrecognized
pipeline or version still gets the viewer, checklist and whatever
indicators its files allow; its fix guidance carries a clear warning
that the recipes were written for another version.

Suspicion scores are ranked within a pipeline, not across pipelines.

### Inputs read per subject

(Listed for FastSurfer. For recon-all the "deep-learning segmentation"
role is filled by `mri/aseg.presurf.mgz` / `mri/aparc+aseg.mgz`, with
the same caveat about independence. recon-all 8.2 also writes
`mri/vsinus.mgz` and `mri/mca-dura.mgz`; if, on inspection, these are
sinus and dura segmentations, the builder should use them for the
ribbon-over-non-cortex indicator. Not yet checked.)

- `mri/orig.mgz`: the T1 shown to the reviewer (unstripped, so sinus and
  dura are visible). Designer's call.
- `surf/{lh,rh}.pial`, `surf/{lh,rh}.white`
- `mri/ribbon.mgz`, `mri/aparc.DKTatlas+aseg.deep.mgz`, `mri/aseg.mgz`,
  `mri/norm.mgz`
- `surf/{lh,rh}.thickness`, `label/{lh,rh}.cortex.label`
- `surf/{lh,rh}.defects.pointset`, `mri/{lh,rh}.surface.defects.mgz`,
  `scripts/recon-surf.log` (topology defects, original command line)
- `stats/` is not relied on (empty in the example).

A subject with missing required files gets a report page saying what is
missing rather than failing the whole build.

### Scrollable viewer

- Three linked views side by side (coronal, sagittal, axial), each
  with crosshair lines showing where the other two cut (from
  surfcensus; Kay says he wants all three). Any one can be enlarged to
  fill the viewer; coronal is the primary view, as in the video.
- Scroll by mouse wheel, slider, and arrow keys; zoom and pan. Clicking
  in one view moves the other two to that point.
- Holding `s` hides the contours (from surfcensus).
- T1 slices are pre-rendered images, one per slice per plane, with a
  fixed robust intensity window.
- Surface contours are the exact intersection of each surface mesh with
  each slice plane, stored as line segments and drawn over the image in
  the browser, so they can be switched on and off (Kay's T1 pass ignores
  the surfaces) and stay sharp when zoomed.
- Colors follow the video: pial yellow, white surface blue (left) and
  red (right).
- Optional overlay of indicator findings (colored voxels).
- Clicking a finding or a region panel jumps the viewer to that plane
  and slice.

### Indicators

Each produces localized findings (a cluster with a location, size, and
type) plus a per-subject number. All thresholds are provisional and are
for ranking only.

| Indicator | Computed from | Error it targets |
|---|---|---|
| Ribbon over non-cortex | ribbon voxels the deep-learning segmentation labels background or cerebellum | pial into sinus, dura, membrane, cerebellum |
| Missed gray matter | deep-learning cortex voxels outside the ribbon | orbitofrontal / temporal gray missed |
| Ribbon intensity anomaly | T1 intensity inside ribbon far from the subject's gray-matter distribution | bright membrane / dura included |
| White matter outside white surface | deep-learning white-matter voxels outside the white surface | gyral crowns underestimated |
| Hemisphere crossing | voxels in both left and right ribbon | hemispheres crossing |
| Thickness outliers | clusters of very thick / very thin vertices within the cortex label | either surface misplaced |
| Topology defects | defect count and size from the defect files and log | white-surface topology problems |
| Cohort thickness outliers (from surfcensus) | each subject's thickness map in fsaverage space compared, location by location, with the other subjects of the same pipeline; needs `sphere.reg`, an fsaverage, and about 30 subjects | local thickening where pial absorbed sinus, tentorium or dura |

The cohort indicator is switched on only when there are enough
subjects of one pipeline; until then the report says it is off.

Known limits, to be stated in the report:

- FastSurfer builds its surfaces starting from the same deep-learning
  segmentation, so agreement between the two is not independent
  evidence of correctness. Disagreement is still informative, mainly for
  the pial surface, which is placed from image intensity.
- The sinus is medium gray (Kay's words), so the intensity indicator
  will often miss it; the sinus panels are always shown regardless.

### Regions

Each finding is assigned to one of Kay's regions using the DKT labels
and simple geometry (distance to the midline, to the cerebellum labels,
to the hippocampus/amygdala labels, position along the
anterior-posterior axis):

1. sagittal / transverse sinus (posterior medial and tentorial)
2. cortex / cerebellum interface
3. frontal midline
4. inferior frontal / orbitofrontal
5. inferior temporal / ear-canal dropout
6. medial temporal (hippocampus, brainstem side)
7. outer edge (dura), everything else lateral
8. white surface (gyral crowns, deep sulci)
9. hemisphere crossing

### Subject report page, top to bottom

1. Header: subject, FastSurfer version, suspicion score, indicator
   summary, review status.
2. The scrollable viewer.
3. The checklist, in Kay's order. Each item has a short description of
   what to look for (from the video), zoomed panels, and a rating:
   - Bird's-eye: a montage of evenly spaced coronal slices.
   - T1 quality: the same montage without contours.
   - One item per region above: panels at the top findings for that
     region; if there are none, panels at default anatomical slices for
     that region, so the reviewer still looks.
   - Rating scale for region items (from surfcensus, wording adapted):
     none / minor / major, plus a free-text note. Minor: visible but
     confined, would not change an analysis much, leave it. Major: a
     careful analyst would edit or exclude; this is "needs fix" in the
     rest of this document. When torn between two levels, choose the
     lower and write a note. A subject can also be flagged unratable
     with a reason. The wording and anchors live in a protocol file
     with a version, and every rating stores the protocol version.
   - Rating is keyboard-driven (number keys for levels, keys to move
     between items and subjects), with a `?` help screen (from
     surfcensus).
   - Rating choices for bird's-eye and T1 quality: OK / concern /
     consider excluding, plus a note. No edit recipe exists for these.
   - Marking problems (designer's call): a region rated "needs fix"
     carries a list of marked problems. Each has a location and a kind
     of error (pial too far out, gray matter missed, white surface
     short of white matter, white surface past white matter,
     hemispheres crossing, topology defect). The reviewer creates one
     either by accepting an indicator finding or by clicking on the
     misplaced contour in the viewer (the mark snaps to the nearest
     surface vertex, from surfcensus, so it names the vertices that are
     wrong), so problems found by scrolling where no indicator
     fired can be recorded. Recipes are generated per marked problem.
4. Overall grade (A to F with plus/minus, as Kay grades) and notes.
5. Fix guidance, generated from the ratings (below).

Unrated items are visibly unrated. The page shows how many items remain.

### Several reviewers

- Any number of reviewers can rate the same subjects or different
  ones; both splitting the set and double-rating are supported.
- A reviewer never sees another reviewer's ratings or marks for a
  subject before submitting their own.
- Subjects are presented worst-scoring first by default. `--blind`
  shuffles the order and hides the indicator scores and findings until
  the rating is submitted, for unbiased agreement measurement (from
  surfcensus).
- Skip defers a subject to the end of that reviewer's queue; it is
  never dropped or counted as a rating (from surfcensus).
- `finalize` (rule from surfcensus): where two reviewers are within one
  step on an item, the final label is the lower value and the marks are
  pooled; where they are two steps apart or one said unratable, the
  subject is listed as a disagreement to be settled together. A subject
  rated by one reviewer keeps that reviewer's ratings. Fix guidance is
  shown per reviewer during review and from the final labels after
  `finalize`.
- The index shows, per subject, who has rated it, the final label
  where there is one, and whether it is in disagreement.
- The export is long format: one row per subject, reviewer and item,
  plus a table of marks and a table of final labels.

### Ratings

- Saved by the local server as one JSON file per subject per rater under
  `<qa_dir>/ratings/`, with rater name and timestamp. Rater name is
  asked once and remembered in the browser. (Designer's call.)
- Ratings are tied to the run they were made on (designer's call).
  Each build fingerprints the subject's surface files. If the
  fingerprint is unchanged, a rebuild keeps the ratings. If it changed
  (the subject was edited and rerun), the subject returns to
  "unreviewed" and the earlier ratings are shown as "previous run".
- Each run's report assets are kept in their own folder under the
  subject, so the previous run's contours remain available. FastSurfer
  reruns in place, so this copy is the only record of the pre-edit
  surfaces.
- Whether a subject has been edited is determined from `--edits` in the
  logs and from comparing file contents, not from the existence of
  `manedit` files: in the unedited example
  `mri/brain.finalsurfs.manedit.mgz` already exists and is identical to
  `brain.finalsurfs.mgz` (so no copy step is needed for that file).

### Index page

Table of subjects sorted by suspicion score (highest first): indicator
values, review status, grade, number of regions marked "needs fix", link
to the report.

### Fix guidance

**recon-all subjects.** recon-all's editing workflow differs from
FastSurfer's (it supports brain-mask edits and control points, which
FastSurfer forbids). The recon-all 8.2 recipes are to be written by the
builder from the FreeSurfer 8 documentation, in the same form as the
FastSurfer table below; they have not been researched yet and nothing
in this document should be read as recon-all advice.

**FastSurfer subjects.** Written against the FastSurfer 2.6.1 editing documentation
(https://deep-mi.org/FastSurfer/stable/overview/EDITING.html). For each
region rated "needs fix", the report shows a recipe:

| Problem | Recipe (in the order FastSurfer recommends) |
|---|---|
| Pial too far out (sinus, dura, membrane, cerebellum) | 1. Copy `mri/aparc.DKTatlas+aseg.deep.mgz` to `mri/aparc.DKTatlas+aseg.deep.manedit.mgz` and correct the gray-matter labels there (the docs name "gray matter over segmentation into the dura"). 2. If that is not enough, edit `mri/brain.finalsurfs.manedit.mgz`: paint 1 where it should not be gray matter. |
| Gray matter missed by pial | Same two files; in `brain.finalsurfs.manedit.mgz` paint 255 to include. |
| White surface misses or overshoots white matter | 1. Segmentation edit as above. 2. If not enough, edit `mri/wm.mgz` and/or `mri/filled.mgz`: 255 to include in white matter, 1 to exclude. |
| Topology defect | White-matter edit as above at the defect location. |
| Hemispheres crossing | No dedicated edit is documented. The recipe says so, and points to the segmentation edit at that location as the thing to try. |

Each recipe also gives:

- a `freeview` command composed by this tool that opens the T1, the
  volume to edit, and the four surfaces at the finding's coordinates
  (the FastSurfer docs give no freeview command for these edits);
- the copy command that creates the `manedit` file;
- the rerun command: the subject's original FastSurfer call with
  `--edits` added, plus `--surf_only` when the segmentation was not
  edited, and the same `--t1` as the first run (the docs say a different
  image is an error). The original call is on the `Invocation:` line of
  `scripts/deep-seg.log`; in the example it is
  `/fastsurfer/run_fastsurfer.sh --fs_license /fastsurfer/my_mri_data/license.txt --t1 /fastsurfer/my_mri_data/anat_avg/sub-07_T1w_avg.nii.gz --sid sub-07 --sd /outputs --3T --threads 8`.
  That is the command as seen inside the container: the paths are
  container paths and the container launch line (mounts, GPU flags) is
  not in the logs. The recipe shows the in-container command and says
  that it must be run with the same container setup as the first run.
  If the line is missing, a template is shown instead. `build` accepts
  an optional rerun template (the user's container launch line with a
  placeholder for the FastSurfer arguments); when given, recipes show a
  complete copy-paste command (designer's call);
- the do-not-edit list from the docs: `mri/mask.mgz`,
  `mri/brainmask.mgz`, `tmp/control.dat`, seed files,
  `mri/aseg.presurf.mgz` (undefined behavior in FastSurfer);
- the docs' warning that edits can introduce systematic effects, with a
  reminder to keep track of which subjects were edited (the export
  table records it);
- Kay's note where relevant that the region is often not worth fixing
  (ear-canal dropout, hippocampal region).

After a rerun, running `surfaceqa build` again produces a fresh report
for that subject.

### Comparing two reconstructions of one subject (designer's call)

Kay compares two versions of the same subject, and the example subject
exists in three. The viewer can show a second reconstruction of the
same subject, chosen from the others that were built (another pipeline,
or the previous run of an edited subject): two viewers side by side,
kept at the same scanner coordinates. Side by side, not overlaid,
because the reconstructions can differ in resolution and in the T1 they
were run on. This is the last piece to be built, and the rest does not
depend on it.

## Testing

- Unit tests on small synthetic data: tiny volumes and simple meshes
  with planted errors (ribbon leaking into a "cerebellum" label, two
  hemispheres overlapping, a known mesh/plane intersection, a planted
  thick patch). Each indicator test must fail unless the planted error
  is found at the right place.
- Coordinate handling (surface coordinates to voxel indices to slice
  images) tested against a mesh with a known position, and contour
  placement compared with `freeview` screenshots of `sub-07` on this
  machine (surfcensus documents the conventions it verified against
  Freeview's source; those are a useful reference).
- The consensus rule tested on constructed pairs of ratings.
- The three real reconstructions of subject 07 as integration tests,
  one per pipeline adapter, skipped when the volume is not mounted.
- Fix recipes tested against the table above.

## Left to the builder

- Libraries (expected: nibabel, numpy, scipy, Pillow, Jinja2; a minimal
  web server), image format and size of slice images, how contour
  segments are stored, package layout.
- Exact indicator thresholds, cluster-size cutoffs, and the formula for
  the suspicion score, calibrated on `sub-07` and revisited as ratings
  accumulate.
- The exact geometric rules that assign findings to regions, and the
  default slices per region.
- Visual design of the pages.
