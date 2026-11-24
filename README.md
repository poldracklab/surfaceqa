# surfaceqa

A browser tool for reviewing FreeSurfer and FastSurfer cortical surfaces, following the
procedure Kendrick Kay demonstrates in his surface QA video: scroll the T1 with the pial and
white surfaces drawn on it, check the known trouble spots, rate what you see, grade the subject.

A person makes every judgment. The automated indicators only order the subjects and point at
places to look; a low score does not mean the surfaces are correct, and no indicator result is
ever recorded as a rating.

## Quick start

```
uvx surfaceqa
```

This downloads the tool, starts it on your own machine and opens the start page in your
browser. Choose a FreeSurfer or FastSurfer subjects folder (or one subject), press Build, and
review. The only requirement is [uv](https://docs.astral.sh/uv/); FreeSurfer does not need to
be installed.

- Nothing leaves your machine, and nothing is written into the folder you inspect. The rendered
  pages and your reviews go into a separate QA directory, by default `surfaceqa/` beside the
  subjects folder (or `~/surfaceqa/<folder name>` when that place cannot be written). The start
  page shows the place before you build and lets you change it.
- The start page lists the projects you opened before, and opens a QA directory someone else
  built.
- A build can be cancelled; building the same folder again continues where it stopped. "Check
  for new or changed subjects" on a project's index page builds its folders again.
- The address printed at start carries a token. Other users of the same machine cannot use
  your copy of the tool without it.

Until the package is on PyPI, or to run the latest code:

```
uvx --from git+https://github.com/poldracklab/surfaceqa surfaceqa
```

When the data are on a server, run the tool there and look at it from your own machine:

```
ssh -L 8765:localhost:8765 <server>
uvx surfaceqa --no-browser        # on the server; open the address it prints on your machine
```

`surfaceqa --port 9000` uses another port. The rest of this page describes the separate
commands, which are what a lab uses to run one shared review server for several reviewers.

## Install

For development, or to use the separate commands from a checkout:

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
uv run surfaceqa build /data/derivatives/fastsurfer --out /data/qa \
    --rerun-template 'docker run --gpus all -v /data:/data deepmi/fastsurfer:latest {command}'
```
Optional. Stores the line that launches the pipeline for these source folders, with `{command}`
where the pipeline's own command goes. Fix guidance then shows rerun commands that can be pasted
as they are. Leave `{command}` outside quotes: the command is inserted with its own quoting.

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

```
uv run surfaceqa report /data/qa
```
Writes `/data/qa/report/index.html`: how the errors are spread over subjects and regions (see
"The report" below). The same page can be made again from the index page of `surfaceqa serve`.

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
5. Choose the overall grade and submit. Everything is saved as you go (a save the server did
   not answer is tried again by itself); submitting is refused,
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
  subject, and whether it was edited, until that reviewer has submitted it. A comparison with
  another reconstruction never shows findings. Nothing is shown until a name is given.
- `finalize`: where reviewers are within one step on an item, the final label is the lower
  one and their marks are pooled; two or more steps apart is a disagreement. Grades within one
  letter give the better grade; further apart is a disagreement. To settle a disagreement, the
  reviewers submit one joint review under the name `consensus`, and run `finalize` again.
- Ratings belong to the run (the surfaces) they were made on. After a subject is edited, rerun
  and rebuilt, it is unreviewed again and the earlier review is shown as "Previous run".

The wording of the rating scales is in `src/surfaceqa/protocol.json`, which has a version
number that is stored with every review.

## Fix guidance

For every problem marked in a region rated "Major (needs fix)", the subject page shows, under
the review:

- what to edit, in the order to try it;
- a `freeview` command that opens the T1, the file to edit and the four surfaces at the mark;
- the command that reruns the subject, built from the command of its first run (read from its
  log when the report was built).

While reviewing, the guidance follows your own marks. After `finalize` it comes from the final
labels, for anyone who may see them. The tool never edits or reruns anything itself. After a
rerun, run `surfaceqa build` again: the subject gets a new run and needs a new review.

The recipes are in `src/surfaceqa/recipes.json`.

- FastSurfer recipes follow the FastSurfer 2.6 editing documentation.
- recon-all recipes are for FreeSurfer 8. The FreeSurfer editing tutorials predate version 8;
  the recipes follow them where the version 8 `recon-all` script behaves the same way. One
  departure: for a pial surface that is too far out they edit
  `mri/brain.finalsurfs.manedit.mgz`, not `mri/brainmask.mgz`, because version 8 can rebuild
  the brainmask on a full rerun.
- Subjects of another version get the same recipes with a warning.

A subject that shows signs of manual edits (edit files, edit flags or partial reruns in its
logs) is marked "edited" on the pages and in the `edited` column of the export tables. When a
file could not be read and nothing else shows an edit, the page says "unknown" and the column
is blank.

## Comparing two reconstructions

When the same person was reconstructed more than once (another pipeline or version in another
source folder, another session in the same folder, or an earlier run of a subject that was
edited and rerun), the viewer's toolbar has a "Compare with…" menu. The chosen reconstruction
is shown under the subject's three views, or beside it when one view is shown.

- The two are kept at the same scanner position. Zoom is separate.
- Untick "Linked" to move them separately. Reconstructions made from different scans do not
  line up.
- The comparison is for looking only. Ratings and marks are made in the subject's own viewer.
- Subjects are matched by name: `sub-07`, `subj07` and `sub-07_ses-nsdanat` are the same person.

## Thickness compared across subjects

Once a source folder has 30 subjects, `build` also compares each subject's cortical thickness,
place by place, with the other subjects of that folder (using each subject's `surf/?h.sphere.reg`;
no fsaverage folder is needed). A patch that is much thicker than in the other subjects is listed
as a finding, "thicker than the cohort": often a place where the pial surface took in sinus or
dura. Below 30 subjects the subject page says that this indicator did not run.

Adding or rebuilding a subject changes the comparison for the whole folder, so the next `build`
recomputes the indicators of that folder's subjects. Slices and contours are not redone. This
also happens for the rest of a folder when a build is limited with `--subjects`. A subject whose
folder was deleted from the source, or whose latest build failed, no longer counts.

## The report

`surfaceqa report`, or the "Update report" button on the index page, makes one page per QA
directory with a part for each source folder:

- **Progress and grades:** how many subjects are reviewed, in disagreement between reviewers,
  could not be rated, or are not reviewed; and the final grades.
- **Ratings by region:** for each checklist item, how many subjects got each final rating.
- **Marked problems:** regions by kind of problem, as subjects with such a mark (and marks).
- **Subjects by region:** one row per subject, the most severe first, linked to its page.
- **Automated indicators:** on how many subjects each indicator ran and what it found, and the
  findings by region. These are not judgments.
- **Indicators against reviewers:** per region, how reviewers rated it where an indicator had a
  finding and where none had; the table for judging the thresholds.

The reviews are combined when the report is made, with the rule of `finalize`; `finalize` need
not have been run. Only submitted reviews count. The page names no reviewer and shows no notes.
It is made from the reviews of that moment and does not update by itself. Three tables are
written beside it (`region_ratings.tsv`, `problem_kinds.tsv`, `indicator_agreement.tsv`).

A server started with `--blind` neither makes nor shows the report, because it gives every
reviewer's ratings in aggregate; there, use the command.

## What is in a QA directory

```
index.html, static/           the read-only pages
subjects/<source>__<name>/    one folder per subject, with one folder per run
ratings/                      the reviews
final/                        final labels, written by finalize
export/                       tables, written by export
report/                       the report page and its tables
cohort/                       thickness statistics per source folder
settings.json                 rerun templates given to build
```

## Development

```
uv run pytest
```

## Publishing (maintainer)

```
uv run pytest
uv build
uv publish
```

`uv build` writes the wheel and the source archive into `dist/`; `uv publish` uploads them to
PyPI with your own token. The version is in `pyproject.toml`.
