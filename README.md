# surfaceqa

A browser tool for reviewing FreeSurfer and FastSurfer cortical surfaces, following the
procedure Kendrick Kay demonstrates in his surface QA video: scroll the T1 with the pial and
white surfaces drawn on it, check the known trouble spots, rate what you see, grade the subject.

A person makes every judgment. The automated indicators only order the subjects and point at
places to look; a low score does not mean the surfaces are correct, and no indicator result is
ever recorded as a rating.

## Install

```
uv sync
```

Building the reports reads `.mgz` and surface files directly; FreeSurfer does not need to be
installed.

## Commands

```
uv run surfaceqa build /data/derivatives/fastsurfer --out /data/qa --jobs 4
```
Renders a report for every subject in one or more FastSurfer or `recon-all` subjects folders
(or single subject folders) into a QA directory. Nothing is written into the source folders.
Safe to rerun: unchanged subjects are skipped, and a subject whose surfaces changed gets a new
run while the old one is kept.

```
uv run surfaceqa serve /data/qa
uv run surfaceqa serve /data/qa --host 0.0.0.0 --blind
```
Opens the reports for reviewing at http://127.0.0.1:8765/. `--host` makes the server reachable
from other machines; there are no accounts or passwords, so use it only on a network you trust.

```
uv run surfaceqa finalize /data/qa
```
Combines the reviewers' submitted ratings into final labels and lists the subjects they
disagree on.

```
uv run surfaceqa export /data/qa
```
Writes four tab-separated tables to `/data/qa/export/`: `ratings.tsv` (one row per subject,
reviewer and item), `marks.tsv`, `final.tsv` and `indicators.tsv`. Only submitted reviews are
exported.

## A review session

1. Open the index and type your name in the header (letters, digits, `-` and `_`). The browser
   remembers it. Without a name the pages are a read-only overview.
2. Click "Next subject to review", or pick a subject. Subjects are listed most suspicious
   first within each source folder.
3. Work down the checklist beside the viewer: the two whole-brain passes, then the nine
   regions. Each has buttons that take the viewer to the indicator findings there, or to
   default places to look when no indicator fired.
4. Rate every item. A region rated "Major (needs fix)" needs at least one marked problem:
   press "Mark a problem" and click the misplaced contour (the mark snaps to the surface), or
   press "+ mark" next to a finding.
5. Choose the overall grade and submit. Everything is saved as you go; submitting is refused,
   with a list, while anything is missing. A subject that cannot be rated at all is submitted
   with a reason instead.
6. "Skip for now" puts the subject at the end of your queue.

A review can still be changed after it is submitted; it is then flagged as revised.

### Keys

| Key | Action |
|---|---|
| scroll, arrow keys | change slice |
| click | move the other two views to that point |
| ctrl/cmd + scroll, drag | zoom, pan |
| double-click a view | enlarge / restore |
| hold `s` | hide the surfaces |
| `n` / `p` | next / previous location in the checklist |
| `j` / `k` | next / previous checklist item |
| `1` `2` `3` | rate the current item |
| `m` | mark a problem in the current region (`Esc` cancels) |
| `g` | go to the grade |
| `Shift+N` | next subject |
| `?` | show the keys |

## Several reviewers

- Each reviewer's review is its own file: `<qa>/ratings/<subject>/<run>/<name>.json`.
- A reviewer sees other reviewers' ratings, marks and the final labels for a subject only
  after submitting their own review of it. The names of those who have reviewed it are shown.
- `--blind` shuffles the order of subjects per reviewer and hides the scores and findings of a
  subject until that reviewer has submitted it. Nothing is shown until a name is given.
- `finalize`: where reviewers are within one step on an item, the final label is the lower
  one and their marks are pooled; two or more steps apart is a disagreement. Grades within one
  letter give the better grade; further apart is a disagreement. To settle a disagreement, the
  reviewers submit one joint review under the name `consensus`, and run `finalize` again.
- Ratings belong to the run (the surfaces) they were made on. After a subject is edited, rerun
  and rebuilt, it is unreviewed again and the earlier review is shown as "Previous run".

The wording of the rating scales is in `src/surfaceqa/protocol.json`, which has a version
number that is stored with every review.

## What is in a QA directory

```
index.html, static/           the read-only pages
subjects/<source>__<name>/    one folder per subject, with one folder per run
ratings/                      the reviews
final/                        final labels, written by finalize
export/                       tables, written by export
```

## Not built yet

Fix guidance for subjects that need editing, side-by-side comparison of two reconstructions,
and thickness outliers across the cohort.

## Development

```
uv run pytest
```
