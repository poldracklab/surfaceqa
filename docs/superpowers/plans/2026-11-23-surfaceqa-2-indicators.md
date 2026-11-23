# surfaceqa Plan 2: Indicators, Regions, Ranking, Checklist

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `surfaceqa build` also computes automated indicators of the surface errors Kay looks for, assigns each finding to one of his regions, ranks subjects by a suspicion score within their pipeline, and the subject page becomes his checklist: every region listed, most suspicious locations first, each one click away in the viewer.

**Architecture:** A loader reads the extra files each pipeline provides into a `SubjectData` of arrays on the display grid. Each indicator is a pure function `SubjectData -> list[Finding]`, returning nothing (and saying why) when its inputs are absent. `regions.py` labels findings and supplies default look-here locations for regions with no findings. The build writes `findings.json` and a packed voxel list per run; the page and viewer read them. Nothing here decides pass or fail.

**Tech Stack:** as Plan 1, plus `scipy` (`ndimage` for clustering and distance transforms).

**Spec:** `docs/superpowers/specs/2026-11-22-surfaceqa-design.md` (sections Indicators, Regions, Subject report page, Index page, Pipelines).

## What real data showed (subject 07, three reconstructions)

Measured before writing this plan; these numbers set the defaults below.

| Measure | FastSurfer 2.6.1 | recon-all 8.2.0 | NSD FreeSurfer 6 |
|---|---|---|---|
| Ribbon over segmentation background, mm^3 (clusters; largest) | 10,125 (11,845; 217) | 3 (3; 1) | 11,122 (3,207; 6,069) |
| Ribbon over cerebellum labels, mm^3 (largest cluster) | 178 (25) | 516 (86) | 1,002 (134) |
| Segmentation cortex outside ribbon, mm^3 | 9,427 | 48,862 | 54,974 |
| Left and right ribbon overlap, voxels | 151 | 41 | 183 |
| Cortex vertices thicker than 4.5 mm (lh) | 391 | 488 | 341 |

Consequences:

- Raw disagreement is dominated by thousands of one-voxel boundary clusters. Every volume indicator therefore counts only voxels more than `MARGIN_MM` past the boundary and only clusters of at least `MIN_CLUSTER_MM3`.
- recon-all's `aseg.presurf.mgz` labels cortex generously (48,862 mm^3 "missed"), so "missed gray matter" runs only when the segmentation has cortical parcels (labels 1000 and up), i.e. FastSurfer's deep-learning segmentation.
- recon-all 8.2 writes `mri/vsinus.mgz` and `mri/mca-dura.mgz` (label volumes: 12,769 and 1,197 nonzero voxels in the example; the ribbon overlaps them by 2 and 14 voxels). They are used as extra non-brain masks when present.
- The NSD subject's 6,069 mm^3 cluster of ribbon over background is the first thing to look at once the overlay exists (Task 8).

## Global Constraints

- Everything in Plan 1's Global Constraints still applies (uv, no code in `__init__.py`, pytest functions and fixtures, tests committed before implementation, tests never weakened to pass, short functions, no FreeSurfer binaries, never write into a source directory, commit trailer).
- The default branch is `main`. Work on branch `plan-2-indicators`.
- Indicators never produce a pass. Wording on every page: a region with no findings says "No indicator fired here. Look anyway." and is never shown as OK.
- All thresholds are named constants in one module (`thresholds.py`) and are recorded in `findings.json`, so a report says what it was computed with.
- `BUILD_FORMAT` becomes `2`, so Plan 1 run folders are re-rendered.

## Review Focus

1. **An indicator whose input file is absent** (recon-all has no deep-learning segmentation; FreeSurfer 6 has no `vsinus.mgz`; a subject may lack `thickness`): it is reported as "not run" with the reason, the build succeeds, and the subject is not ranked as if it scored zero on that indicator without saying so (Task 1 `test_missing_optional_files_become_none`, Task 6 `test_skipped_indicators_are_reported`).
2. **Boundary noise**: a one-voxel shell of disagreement all around the brain must yield no findings (Task 3 `test_one_voxel_shell_is_not_a_finding`).
3. **A finding's location must be inside its cluster**, also for C-shaped clusters whose centroid is outside (Task 2 `test_location_is_inside_a_c_shaped_cluster`).
4. **Voxel sizes**: sizes are in mm^3 and margins in mm for 1 mm and 0.8 mm data alike, and for anisotropic voxels (Task 2 `test_sizes_and_margins_are_in_mm`).
5. **A subject with thousands of findings** must not produce an unusable page or a huge file: findings are capped per indicator, largest first, and the cap is reported (Task 6 `test_findings_are_capped_and_the_cap_is_reported`).

## File Structure

```
src/surfaceqa/thresholds.py        every tunable number, with a one-line reason each
src/surfaceqa/findings.py          Finding, cluster_findings(), margin helpers
src/surfaceqa/subjectdata.py       SubjectData and load_subject_data() (per-pipeline file roles)
src/surfaceqa/indicators_volume.py the six volume indicators
src/surfaceqa/indicators_surface.py thickness and topology indicators
src/surfaceqa/regions.py           REGIONS table, assign_region(), default_locations()
src/surfaceqa/scoring.py           suspicion score, rank within pipeline
src/surfaceqa/qa.py                run all indicators for a subject; write findings.json + voxels
src/surfaceqa/build.py             (modify) call qa after rendering; BUILD_FORMAT = 2
src/surfaceqa/site.py              (modify) ranking columns; checklist data for the template
src/surfaceqa/web/templates/subject.html, index.html, _checklist.html   (modify / create)
src/surfaceqa/web/static/logic.js, viewer.js, checklist.js, app.css      (modify / create)
tests/synth.py                     (modify) optional QA files with planted errors
tests/test_findings.py, test_subjectdata.py, test_indicators_volume.py,
tests/test_indicators_surface.py, test_regions.py, test_scoring.py, test_qa.py
```

New files per run folder:

```
findings.json          indicators run/skipped, thresholds, findings, score, default locations
findings_voxels.bin    uint16 little-endian R, A, S triples, finding by finding
```

---

### Task 1: Thresholds and subject data loader

**Files:**
- Create: `src/surfaceqa/thresholds.py`, `src/surfaceqa/subjectdata.py`
- Modify: `tests/synth.py`, `pyproject.toml` (`uv add scipy`)
- Test: `tests/test_subjectdata.py`

**Interfaces:**
- Produces `thresholds.py` (module constants; `as_dict() -> dict` returns them all for the report):

  | Name | Value | Reason |
  |---|---|---|
  | `MARGIN_MM` | 1.0 | boundary disagreement of one voxel is noise on both 0.8 and 1 mm data |
  | `MIN_CLUSTER_MM3` | 20.0 | below this the largest real clusters on subject 07 are indistinguishable from noise |
  | `BRIGHT_MAD` | 4.0 | ribbon voxels brighter than median + 4 scaled MADs of deep ribbon intensity |
  | `THICK_MM` | 4.5 | FreeSurfer caps thickness at 5; about 0.4% of cortex vertices exceed 4.5 on subject 07 |
  | `MIN_THICK_VERTICES` | 50 | a patch, not isolated vertices |
  | `MIN_DEFECT_VERTICES` | 100 | small topology defects are fixed automatically and are routine |
  | `MAX_FINDINGS_PER_INDICATOR` | 50 | page stays usable; cap is reported |
  | `NEAR_MM` | 4.0 | "next to" the cerebellum or hippocampus for region assignment |
  | `MEDIAL_MM` | 6.0 | "medial": within this distance of the other hemisphere |

- Produces `subjectdata.py`:

  ```python
  @dataclass
  class HemiSurface:
      pial_grid: np.ndarray            # (n, 3) vertices in grid coordinates
      faces: np.ndarray                # (m, 3)
      thickness: np.ndarray | None     # (n,)
      cortex: np.ndarray | None        # vertex indices of the cortex label
      defect_labels: np.ndarray | None # per vertex of the pre-fix surface
      nofix_grid: np.ndarray | None    # pre-fix surface vertices, grid coordinates

  @dataclass
  class SubjectData:
      voxel_sizes: tuple[float, float, float]
      ribbon: np.ndarray | None            # mri/ribbon.mgz on the grid: 2, 41 white; 3, 42 cortex
      hemi_ribbon: dict[str, np.ndarray] | None   # {"lh": bool, "rh": bool} from mri/?h.ribbon.mgz
      seg: np.ndarray | None               # the independent segmentation, integer labels
      seg_name: str | None                 # the file it came from, for the report
      nonbrain: np.ndarray | None          # bool: union of extra non-brain masks, or None
      nonbrain_names: list[str]
      parc: np.ndarray | None              # mri/aparc.DKTatlas+aseg.mgz, for regions
      norm: np.ndarray | None              # mri/norm.mgz
      hemis: dict[str, HemiSurface]

  def load_subject_data(subject_dir: Path, pipeline: PipelineInfo) -> SubjectData
  ```

  File roles:

  | Role | FastSurfer | recon-all / unknown |
  |---|---|---|
  | `seg` | `mri/aparc.DKTatlas+aseg.deep.mgz` | `mri/aseg.presurf.mgz` |
  | `nonbrain` | none | `mri/vsinus.mgz`, `mri/mca-dura.mgz` (those that exist; nonzero = non-brain) |
  | `defect_labels` / `nofix_grid` | `surf/?h.defect_labels`, `surf/?h.orig.nofix` | same |
  | everything else | same paths for all pipelines | |

  Every optional file that is absent or unreadable becomes `None` (or an empty list); loading never raises for a missing optional file. Volumes go through `load_display_volume`; a volume whose grid shape differs from `orig.mgz`'s becomes `None`.

- Produces `tests/synth.py`: `write_qa_files(subj: Path, pipeline: str = "fastsurfer", plant: dict | None = None) -> None`. Writes, consistent with the synthetic ball (white radius 8, pial radius 10, tkr origin): `mri/ribbon.mgz` (white matter inside r<8 as 2 for x<0 / 41 for x>=0 in tkr; cortex 8<=r<10 as 3 / 42), `mri/lh.ribbon.mgz`, `mri/rh.ribbon.mgz`, the pipeline's `seg` file (white 2/41, cortex as parcel 1028/2028 for FastSurfer or 3/42 for recon-all, 0 outside), `mri/aparc.DKTatlas+aseg.mgz` (same as the FastSurfer seg), `mri/norm.mgz` (110 white, 70 cortex, 0 outside), `surf/?h.thickness` (all 2.0), `label/?h.cortex.label` (all vertices). `plant` is reserved for later tasks' integration tests: keys `"ribbon_blob"` (centre in tkr mm, radius mm: extra cortex in ribbon and hemi ribbon but not in seg) and `"thick_patch"` (hemi, centre tkr mm, radius mm: thickness 5.0 on pial vertices within the radius).

- [ ] **Step 1: Write the failing tests**

```python
def test_loads_fastsurfer_roles(synth_subject):
    write_qa_files(synth_subject)
    data = load_subject_data(synth_subject, detect_pipeline(synth_subject))
    assert data.seg_name == "aparc.DKTatlas+aseg.deep.mgz"
    assert data.ribbon.shape == (32, 48, 40) and set(np.unique(data.ribbon)) == {0, 2, 3, 41, 42}
    assert data.hemi_ribbon["lh"].dtype == bool and data.hemi_ribbon["lh"].any()
    assert data.nonbrain is None and data.nonbrain_names == []
    assert data.hemis["lh"].thickness.shape == (len(data.hemis["lh"].pial_grid),)
    assert data.voxel_sizes == pytest.approx((1.0, 1.0, 1.0))

def test_loads_recon_all_roles_and_nonbrain_masks(tmp_path):
    subj = write_subject(tmp_path / "fs", pipeline="freesurfer")
    write_qa_files(subj, pipeline="freesurfer")
    mask = np.zeros((32, 40, 48), dtype=np.float32); mask[2, 3, 4] = 6111
    ref = nib.load(subj / "mri" / "orig.mgz")
    nib.save(nib.MGHImage(mask, ref.affine), subj / "mri" / "vsinus.mgz")
    data = load_subject_data(subj, detect_pipeline(subj))
    assert data.seg_name == "aseg.presurf.mgz"
    assert data.nonbrain_names == ["vsinus.mgz"] and data.nonbrain.sum() == 1

def test_missing_optional_files_become_none(synth_subject):
    data = load_subject_data(synth_subject, detect_pipeline(synth_subject))   # no QA files written
    assert data.ribbon is None and data.seg is None and data.parc is None and data.norm is None
    assert data.hemi_ribbon is None
    assert data.hemis["lh"].thickness is None and data.hemis["lh"].cortex is None
    assert len(data.hemis["lh"].pial_grid) > 0

def test_volume_with_another_shape_is_ignored(synth_subject):
    write_qa_files(synth_subject)
    nib.save(nib.MGHImage(np.zeros((8, 8, 8), dtype=np.uint8), np.eye(4)), synth_subject / "mri" / "norm.mgz")
    assert load_subject_data(synth_subject, detect_pipeline(synth_subject)).norm is None

def test_thresholds_as_dict_lists_every_constant():
    assert thresholds.as_dict()["MARGIN_MM"] == 1.0 and len(thresholds.as_dict()) == 9
```

- [ ] **Step 2: Run to verify failure; commit tests** (`test: thresholds and subject data loader`)
- [ ] **Step 3: Implement** (one small private loader per role; a single `_optional(fn, *args)` wrapper turns `OSError`/`ValueError` into `None`).
- [ ] **Step 4: Run to verify pass; commit** (`feat: thresholds and subject data loader`)

---

### Task 2: Findings and clustering

**Files:**
- Create: `src/surfaceqa/findings.py`
- Test: `tests/test_findings.py`

**Interfaces:**
- Produces:

  ```python
  KINDS = ("pial_out", "gray_missed", "white_short", "crossing", "thickness", "topology")

  @dataclass
  class Finding:
      indicator: str
      kind: str                       # one of KINDS
      grid: tuple[int, int, int]      # a voxel inside the finding, R, A, S
      size_mm3: float | None          # None for vertex-based findings
      n: int                          # voxels or vertices
      hemi: str | None = None
      region: str = ""
      voxels: np.ndarray | None = None   # (k, 3) uint16; not serialized in findings.json

  def deeper_than(mask: np.ndarray, margin_mm: float, voxel_sizes) -> np.ndarray
      # voxels of `mask` farther than margin_mm from the nearest voxel outside it
  def farther_than(mask: np.ndarray, from_mask: np.ndarray, margin_mm: float, voxel_sizes) -> np.ndarray
      # voxels of `mask` farther than margin_mm from the nearest voxel of `from_mask`
  def cluster_findings(mask: np.ndarray, indicator: str, kind: str, voxel_sizes,
                       min_mm3: float, limit: int) -> tuple[list[Finding], int]
      # 26-connected clusters of at least min_mm3, largest first, at most `limit`;
      # second value = number of clusters dropped by the limit
  ```

  A cluster's `grid` is its voxel deepest inside the cluster (largest distance to the cluster's outside; ties broken by lowest index), so it always lies in the cluster.

- [ ] **Step 1: Write the failing tests**

```python
VOX = (1.0, 1.0, 1.0)

def test_clusters_are_sorted_largest_first_with_sizes_in_mm3():
    mask = np.zeros((20, 20, 20), bool); mask[2:5, 2:5, 2:5] = True; mask[10:14, 10:14, 10:14] = True
    found, dropped = cluster_findings(mask, "x", "pial_out", (0.8, 0.8, 0.8), min_mm3=1.0, limit=10)
    assert [f.n for f in found] == [64, 27] and dropped == 0
    assert found[0].size_mm3 == pytest.approx(64 * 0.512)
    assert found[0].indicator == "x" and found[0].kind == "pial_out"

def test_small_clusters_are_dropped():
    mask = np.zeros((10, 10, 10), bool); mask[1, 1, 1] = True; mask[5:8, 5:8, 5:8] = True
    found, _ = cluster_findings(mask, "x", "pial_out", VOX, min_mm3=20.0, limit=10)
    assert [f.n for f in found] == [27]

def test_location_is_inside_a_c_shaped_cluster():
    mask = np.zeros((12, 12, 3), bool)
    mask[2:10, 2:10, 1] = True; mask[4:8, 4:10, 1] = False      # a C: centroid is in the gap
    (f,), _ = cluster_findings(mask, "x", "pial_out", VOX, min_mm3=1.0, limit=10)
    assert mask[f.grid]

def test_voxels_are_kept_for_the_overlay():
    mask = np.zeros((6, 6, 6), bool); mask[1:3, 1:3, 1:3] = True
    (f,), _ = cluster_findings(mask, "x", "pial_out", VOX, min_mm3=1.0, limit=10)
    assert f.voxels.shape == (8, 3) and f.voxels.dtype == np.uint16
    assert mask[tuple(f.voxels.T)].all()

def test_limit_keeps_the_largest_and_counts_the_rest():
    mask = np.zeros((40, 5, 5), bool)
    for i, size in enumerate((1, 2, 3, 4)):
        mask[i * 8:i * 8 + size, 0, 0] = True
    found, dropped = cluster_findings(mask, "x", "pial_out", VOX, min_mm3=1.0, limit=2)
    assert [f.n for f in found] == [4, 3] and dropped == 2

def test_diagonal_voxels_are_one_cluster():
    mask = np.zeros((4, 4, 4), bool); mask[0, 0, 0] = mask[1, 1, 1] = True
    assert len(cluster_findings(mask, "x", "pial_out", VOX, 1.0, 10)[0]) == 1

def test_sizes_and_margins_are_in_mm():
    mask = np.zeros((30, 30, 30), bool); mask[5:25, 5:25, 5:25] = True
    assert deeper_than(mask, 1.0, (1.0, 1.0, 1.0)).sum() == 18 ** 3     # one voxel shell removed
    assert deeper_than(mask, 1.0, (0.5, 0.5, 0.5)).sum() == 16 ** 3     # two voxel shells removed
    aniso = deeper_than(mask, 1.0, (1.0, 1.0, 0.5))
    assert aniso.sum() == 18 * 18 * 16

def test_farther_than():
    mask = np.ones((10, 1, 1), bool); src = np.zeros((10, 1, 1), bool); src[0] = True
    assert farther_than(mask, src, 2.0, VOX)[:, 0, 0].tolist() == [False] * 3 + [True] * 7

def test_empty_mask_gives_no_findings():
    assert cluster_findings(np.zeros((4, 4, 4), bool), "x", "pial_out", VOX, 1.0, 10) == ([], 0)
```

- [ ] **Step 2: Run to verify failure; commit tests** (`test: findings and clustering`)
- [ ] **Step 3: Implement** with `scipy.ndimage.label` (structure `np.ones((3,3,3))`), `find_objects` to work on each cluster's bounding box, and `distance_transform_edt(..., sampling=voxel_sizes)`.
- [ ] **Step 4: Run to verify pass; commit** (`feat: findings and clustering`)

---

### Task 3: Volume indicators

**Files:**
- Create: `src/surfaceqa/indicators_volume.py`
- Test: `tests/test_indicators_volume.py`

**Interfaces:**
- Consumes: `SubjectData`, `cluster_findings`, `deeper_than`, `farther_than`, `thresholds`.
- Produces: each indicator is `fn(data: SubjectData) -> IndicatorResult`, with

  ```python
  @dataclass
  class IndicatorResult:
      name: str
      kind: str
      status: str                 # "ran" or "not run"
      reason: str = ""            # why not, in plain words, e.g. "no ribbon.mgz"
      findings: list[Finding] = field(default_factory=list)
      dropped: int = 0            # clusters beyond MAX_FINDINGS_PER_INDICATOR
  VOLUME_INDICATORS: tuple[Callable[[SubjectData], IndicatorResult], ...]
  ```

  Definitions. `cortex = ribbon in (3, 42)`; `white = ribbon in (2, 41)`; `CEREBELLUM = (7, 8, 46, 47)`; `SEG_WHITE = (2, 41)`; `seg_cortex = seg >= 1000`. All use `MIN_CLUSTER_MM3` and `MAX_FINDINGS_PER_INDICATOR`.

  | name | kind | mask | needs |
  |---|---|---|---|
  | `ribbon_outside_brain` | pial_out | `cortex & deeper_than(seg == 0, MARGIN_MM)` | ribbon, seg |
  | `ribbon_in_nonbrain_mask` | pial_out | `cortex & nonbrain` (no margin: these are explicit sinus/dura labels) | ribbon, nonbrain |
  | `ribbon_in_cerebellum` | pial_out | `cortex & deeper_than(isin(seg, CEREBELLUM), MARGIN_MM)` | ribbon, seg |
  | `missed_gray` | gray_missed | `farther_than(seg_cortex & (ribbon == 0), ribbon > 0, MARGIN_MM)` | ribbon, seg with parcels |
  | `white_matter_in_ribbon` | white_short | `cortex & deeper_than(isin(seg, SEG_WHITE), MARGIN_MM)` | ribbon, seg |
  | `bright_ribbon` | pial_out | `deep & (norm > median(norm[deep]) + BRIGHT_MAD * 1.4826 * MAD(norm[deep]))`, where `deep = farther_than(cortex, white, MARGIN_MM)` | ribbon, norm |
  | `hemisphere_crossing` | crossing | `hemi_ribbon["lh"] & hemi_ribbon["rh"]` (no margin) | hemi_ribbon |

  `missed_gray` with a segmentation that has no label >= 1000 is `not run` with reason `"segmentation has no cortical parcels (recon-all's aseg labels cortex too generously to compare)"`.

- [ ] **Step 1: Write the failing tests**

A helper in the test module builds a clean `SubjectData` on a 40^3, 1 mm grid: a ball of white matter (r < 10, left half 2, right half 41) and cortex (10 <= r < 14, 3 / 42) centred at (20, 20, 20); `seg` equal to the ribbon but with cortex as 1028 / 2028; `hemi_ribbon` split at x = 20; `norm` 110 / 70 / 0; cerebellum label 8 as a 6 x 6 x 5 block at `[17:23, 17:23, 0:5]` in `seg` only (below the ball, which starts at z = 7). `clean()` returns it; each test plants one error.

```python
def names_run(data):
    return {r.name: r for r in (ind(data) for ind in VOLUME_INDICATORS)}

def test_clean_subject_has_no_findings():
    assert all(r.findings == [] for r in names_run(clean()).values())

def test_one_voxel_shell_is_not_a_finding():
    data = clean()
    shell = ndimage.binary_dilation(data.ribbon > 0) & (data.ribbon == 0)   # pial one voxel too far out, everywhere
    data.ribbon[shell] = 3
    r = names_run(data)
    assert r["ribbon_outside_brain"].findings == [] and r["missed_gray"].findings == []

def test_ribbon_blob_outside_the_brain_is_found_where_it_is():
    data = clean(); data.ribbon[30:36, 17:23, 17:23] = 3          # 6 mm blob beyond the 14 mm ball edge at x=34
    (f,) = names_run(data)["ribbon_outside_brain"].findings
    assert f.kind == "pial_out" and 31 <= f.grid[0] <= 35 and 17 <= f.grid[1] <= 22

def test_ribbon_in_explicit_nonbrain_mask_needs_no_margin():
    data = clean(); data.nonbrain = np.zeros_like(data.ribbon, bool)
    data.nonbrain[20:24, 20:24, 31:34] = True                      # 48 voxels inside the cortex shell
    (f,) = names_run(data)["ribbon_in_nonbrain_mask"].findings
    assert f.n == int((np.isin(data.ribbon, (3, 42)) & data.nonbrain).sum())

def test_ribbon_in_cerebellum():
    data = clean(); data.ribbon[17:23, 17:23, 0:5] = 3
    (f,) = names_run(data)["ribbon_in_cerebellum"].findings
    assert f.n == 4 ** 3                                           # the block minus its 1 mm rim (the volume edge at z = 0 is not a rim)

def test_missed_gray():
    data = clean(); data.seg[30:36, 17:23, 17:23] = 1028           # parcel where the ribbon has nothing
    (f,) = names_run(data)["missed_gray"].findings
    assert f.kind == "gray_missed" and data.ribbon[f.grid] == 0

def test_missed_gray_is_not_run_without_parcels():
    data = clean(); data.seg[data.seg == 1028] = 3; data.seg[data.seg == 2028] = 42
    r = names_run(data)["missed_gray"]
    assert r.status == "not run" and "parcels" in r.reason

def test_white_matter_in_ribbon():
    data = clean(); data.ribbon[14:20, 17:23, 17:23] = 3           # ribbon calls deep white matter cortex
    (f,) = names_run(data)["white_matter_in_ribbon"].findings
    assert f.kind == "white_short"

def test_bright_ribbon():
    data = clean(); data.norm[20:24, 20:24, 31:34] = 200           # bright tissue in the outer cortex shell
    (f,) = names_run(data)["bright_ribbon"].findings
    assert 20 <= f.grid[0] <= 23 and 31 <= f.grid[2] <= 33

def test_hemisphere_crossing():
    data = clean(); data.hemi_ribbon["lh"][20:23, 18:22, 18:22] = True   # lh reaches into rh
    (f,) = names_run(data)["hemisphere_crossing"].findings
    assert f.kind == "crossing" and f.n == 3 * 4 * 4

@pytest.mark.parametrize("field,names", [
    ("ribbon", {"ribbon_outside_brain", "ribbon_in_nonbrain_mask", "ribbon_in_cerebellum",
                "missed_gray", "white_matter_in_ribbon", "bright_ribbon"}),
    ("seg", {"ribbon_outside_brain", "ribbon_in_cerebellum", "missed_gray", "white_matter_in_ribbon"}),
    ("norm", {"bright_ribbon"}), ("hemi_ribbon", {"hemisphere_crossing"}),
    ("nonbrain", {"ribbon_in_nonbrain_mask"}),
])
def test_indicators_without_their_input_do_not_run(field, names):
    data = clean(); setattr(data, field, None)
    r = names_run(data)
    assert {n for n, res in r.items() if res.status == "not run"} >= names
    assert all(res.reason for res in r.values() if res.status == "not run")
```

- [ ] **Step 2: Run to verify failure; commit tests** (`test: volume indicators`)
- [ ] **Step 3: Implement.** One function per indicator, each a guard (`_need(data, "ribbon", "seg")` returning the not-run result) plus its mask plus a shared `_result(name, kind, mask, data)`.
- [ ] **Step 4: Run to verify pass; commit** (`feat: volume indicators`)

---

### Task 4: Surface indicators

**Files:**
- Create: `src/surfaceqa/indicators_surface.py`
- Test: `tests/test_indicators_surface.py`

**Interfaces:**
- Produces: `thick_patches(data) -> IndicatorResult` (name `thick_patches`, kind `thickness`) and `topology_defects(data) -> IndicatorResult` (name `topology_defects`, kind `topology`); `SURFACE_INDICATORS = (thick_patches, topology_defects)`.
  - `thick_patches`: per hemisphere, vertices in the cortex label with thickness >= `THICK_MM`, grouped into connected patches along mesh edges; patches of at least `MIN_THICK_VERTICES`; `n` = vertices, `size_mm3 = None`, `hemi` set, `grid` = the rounded grid position of the patch vertex nearest the patch's mean position, `voxels` = unique rounded grid positions of the patch's vertices (clipped to the volume). Largest first across both hemispheres, capped. Not run when both hemispheres lack thickness; a hemisphere without a cortex label uses all vertices.
  - `topology_defects`: per hemisphere, each nonzero label in `defect_labels` with at least `MIN_DEFECT_VERTICES` vertices is a finding located like a thick patch, using `nofix_grid`. Not run when no hemisphere has both `defect_labels` and `nofix_grid` of equal length.

- [ ] **Step 1: Write the failing tests**

```python
def hemi(radius=10.0, sub=4):
    verts, faces = icosphere(radius, sub)
    return HemiSurface(pial_grid=verts + 20.0, faces=faces, thickness=np.full(len(verts), 2.0),
                       cortex=np.arange(len(verts)), defect_labels=None, nofix_grid=None)

def data_with(lh):
    return SubjectData(voxel_sizes=(1.0, 1.0, 1.0), ribbon=None, hemi_ribbon=None, seg=None, seg_name=None,
                       nonbrain=None, nonbrain_names=[], parc=None, norm=None, hemis={"lh": lh})

def test_uniform_thickness_has_no_patches():
    assert thick_patches(data_with(hemi())).findings == []

def test_thick_patch_is_found_at_its_place():
    h = hemi(); top = h.pial_grid[:, 2] > 20 + 8.0                 # a cap at the top of the sphere
    h.thickness[top] = 5.0
    (f,) = thick_patches(data_with(h)).findings
    assert f.kind == "thickness" and f.hemi == "lh" and f.n == int(top.sum()) and f.size_mm3 is None
    assert f.grid[2] >= 28 and abs(f.grid[0] - 20) <= 2 and abs(f.grid[1] - 20) <= 2

def test_two_separate_patches_are_two_findings():
    h = hemi(); h.thickness[h.pial_grid[:, 2] > 28.0] = 5.0; h.thickness[h.pial_grid[:, 2] < 12.0] = 5.0
    assert len(thick_patches(data_with(h)).findings) == 2

def test_scattered_thick_vertices_are_not_a_patch():
    h = hemi(); h.thickness[::40] = 5.0
    assert thick_patches(data_with(h)).findings == []

def test_thick_vertices_outside_the_cortex_label_are_ignored():
    h = hemi(); top = h.pial_grid[:, 2] > 28.0; h.thickness[top] = 5.0
    h.cortex = np.flatnonzero(~top)
    assert thick_patches(data_with(h)).findings == []

def test_thickness_not_run_without_thickness():
    h = hemi(); h.thickness = None
    r = thick_patches(data_with(h))
    assert r.status == "not run" and r.reason

def test_large_topology_defect_is_found_small_one_is_not():
    h = hemi(); h.nofix_grid = h.pial_grid.copy(); labels = np.zeros(len(h.pial_grid), int)
    big = np.flatnonzero(h.pial_grid[:, 2] > 28.0); labels[big] = 1; labels[:10] = 2
    h.defect_labels = labels
    (f,) = topology_defects(data_with(h)).findings
    assert f.kind == "topology" and f.n == len(big) and f.grid[2] >= 28

def test_topology_not_run_without_prefix_surface():
    h = hemi(); h.defect_labels = np.zeros(len(h.pial_grid), int)
    assert topology_defects(data_with(h)).status == "not run"
```

- [ ] **Step 2: Run to verify failure; commit tests** (`test: surface indicators`)
- [ ] **Step 3: Implement.** Connected patches with `scipy.sparse.csgraph.connected_components` on the edge graph restricted to the selected vertices.
- [ ] **Step 4: Run to verify pass; commit** (`feat: surface indicators`)

---

### Task 5: Regions

**Files:**
- Create: `src/surfaceqa/regions.py`
- Test: `tests/test_regions.py`

**Interfaces:**
- Produces:
  - `REGIONS: tuple[Region, ...]`, in checklist order, with `@dataclass(frozen=True) class Region: id: str; title: str; look_for: str; default_labels: tuple[int, ...]`. `default_labels` are left-hemisphere DKT numbers; the right hemisphere is the same plus 1000. Exact copy:

    | id | title | look_for | default_labels |
    |---|---|---|---|
    | `sinus` | Sagittal and transverse sinus | The pial surface extending into the sinus along the midline and under the occipital lobe. The sinus is medium gray and easy to mistake for cortex. Worst in the most posterior slices. | 1005, 1021 |
    | `cerebellum` | Cortex / cerebellum interface | The pial surface running into the cerebellum on the inferior side of the occipital and temporal lobes. | 1013, 1007 |
    | `frontal_midline` | Frontal midline | The two pial surfaces nearly touch here. Check that neither extends too far or crosses the midline. | 1026, 1028 |
    | `orbitofrontal` | Inferior frontal and orbitofrontal | The pial surface including the bright membrane under the frontal lobe, and orbitofrontal gray matter being missed. | 1012, 1014 |
    | `inferior_temporal` | Inferior temporal, near the ear canal | Gray matter missed by the pial surface in the signal-dropout region. Common, and often not worth fixing. | 1009 |
    | `medial_temporal` | Medial temporal, hippocampus | Surfaces are often irregular around the hippocampus. Judge leniently; it is hard to say what is correct here. | 1016, 1006 |
    | `outer_edge` | Outer edge of the brain | Dura or other tissue just outside the brain included in the pial surface. | 1029, 1024 |
    | `white_surface` | White surface | The white surface cutting off the tips of gyri, or missing deep sulci. | 1024, 1035 |
    | `crossing` | Hemispheres crossing | The left and right surfaces overlapping at the midline. | 1023 |

  - `assign_region(finding: Finding, ctx: RegionContext) -> str`, with `build_context(data: SubjectData) -> RegionContext` computed once per subject (distance maps to cerebellum labels 7, 8, 46, 47 and to hippocampus/amygdala labels 17, 18, 53, 54 in `parc`; for each hemisphere the distance to the other hemisphere's cerebrum, `ribbon in (41, 42)` for a left location and `(2, 3)` for a right one; and the nearest cortical parcel label at every voxel). Rules, first match wins:

    1. kind `crossing` -> `crossing`; kind `white_short` or `topology` -> `white_surface`.
    2. nearest parcel (hemisphere removed: `label % 1000`) in {6, 16}, or within `NEAR_MM` of hippocampus/amygdala -> `medial_temporal`.
    3. within `NEAR_MM` of the cerebellum -> `cerebellum`.
    4. nearest parcel in {5, 21, 25, 13, 10, 29, 11} and within `MEDIAL_MM` of the other hemisphere -> `sinus`.
    5. nearest parcel in {28, 26, 2, 14, 17} and within `MEDIAL_MM` of the other hemisphere -> `frontal_midline`.
    6. nearest parcel in {12, 14, 19} -> `orbitofrontal`.
    7. nearest parcel in {9, 7, 15} -> `inferior_temporal`.
    8. otherwise -> `outer_edge`.

    Which hemisphere a location belongs to is the hemisphere of its nearest parcel. With `parc` absent every finding of rule 2-8 kinds is `outer_edge` and `ctx.reason` says `"no aparc.DKTatlas+aseg.mgz; findings could not be assigned to regions"`.
  - `default_locations(data: SubjectData) -> dict[str, list[dict]]`: for each region and each of its default labels in each hemisphere that exists in `parc`, `{"grid": [r, a, s], "label": "<hemi> <parcel name>"}`, where the voxel is the parcel voxel nearest the parcel's centroid. `{}` when `parc` is absent. Parcel names for the labels used come from a small dict in the module (`5: "cuneus"`, `21: "pericalcarine"`, `13: "lingual"`, `7: "fusiform"`, `26: "rostral anterior cingulate"`, `28: "superior frontal"`, `12: "lateral orbitofrontal"`, `14: "medial orbitofrontal"`, `9: "inferior temporal"`, `16: "parahippocampal"`, `6: "entorhinal"`, `29: "superior parietal"`, `24: "precentral"`, `35: "insula"`, `23: "posterior cingulate"`).

- [ ] **Step 1: Write the failing tests**

A test helper builds a 60 x 80 x 60, 1 mm `SubjectData` with a toy brain: left cerebrum `x in [10, 29]`, right `x in [31, 50]` (ribbon 3 / 42 throughout for simplicity), and in `parc` these boxes (left; right mirrored with +1000): cuneus 1005 at `y in [10, 20], z in [30, 45]`; superior frontal 1028 at `y in [60, 70], z in [30, 45]`; lateral orbitofrontal 1012 at `y in [60, 70], z in [15, 22]`; inferior temporal 1009 at `y in [35, 45], z in [15, 22]`; parahippocampal 1016 at `y in [35, 45], z in [24, 28]` for `x in [24, 29]`; superior parietal 1029 at `y in [25, 34], z in [46, 50]`; cerebellum 8 at `x in [12, 28], y in [8, 22], z in [8, 20]`; hippocampus 17 at `x in [25, 28], y in [36, 44], z in [29, 31]`.

```python
def f(kind, grid):
    return Finding("x", kind, grid, 30.0, 30)

@pytest.mark.parametrize("kind,grid,region", [
    ("crossing", (30, 40, 40), "crossing"),
    ("white_short", (15, 65, 40), "white_surface"),
    ("topology", (15, 15, 40), "white_surface"),
    ("pial_out", (28, 15, 40), "sinus"),              # medial cuneus
    ("pial_out", (12, 15, 40), "outer_edge"),         # lateral cuneus: not near the midline
    ("pial_out", (20, 15, 23), "cerebellum"),         # just above the cerebellum
    ("pial_out", (28, 65, 40), "frontal_midline"),
    ("pial_out", (15, 65, 18), "orbitofrontal"),
    ("gray_missed", (15, 40, 18), "inferior_temporal"),
    ("pial_out", (26, 40, 26), "medial_temporal"),
    ("thickness", (15, 30, 49), "outer_edge"),
    ("pial_out", (32, 15, 40), "sinus"),              # right hemisphere, medial
])
def test_assign_region(kind, grid, region):
    assert assign_region(f(kind, grid), build_context(toy())) == region

def test_without_parcellation_everything_is_outer_edge_and_says_why():
    data = toy(); data.parc = None
    ctx = build_context(data)
    assert assign_region(f("pial_out", (28, 15, 40)), ctx) == "outer_edge" and "aparc" in ctx.reason
    assert assign_region(f("crossing", (30, 40, 40)), ctx) == "crossing"

def test_regions_are_in_checklist_order():
    assert [r.id for r in REGIONS] == ["sinus", "cerebellum", "frontal_midline", "orbitofrontal",
        "inferior_temporal", "medial_temporal", "outer_edge", "white_surface", "crossing"]

def test_default_locations_are_inside_their_parcel():
    data = toy(); locs = default_locations(data)
    assert {d["label"] for d in locs["sinus"]} == {"lh cuneus", "rh cuneus"}
    for d in locs["sinus"]:
        assert data.parc[tuple(d["grid"])] in (1005, 2005)
    assert locs["cerebellum"] == []            # the toy has no lingual or fusiform parcels
    assert default_locations(dataclasses.replace(data, parc=None)) == {}
```

- [ ] **Step 2: Run to verify failure; commit tests** (`test: regions`)
- [ ] **Step 3: Implement.** Distance maps with `distance_transform_edt(sampling=voxel_sizes)`; nearest parcel with `return_indices=True` on the complement of the cortical-parcel mask.
- [ ] **Step 4: Run to verify pass; commit** (`feat: regions`)

---

### Task 6: Score, QA run, build integration

**Files:**
- Create: `src/surfaceqa/scoring.py`, `src/surfaceqa/qa.py`
- Modify: `src/surfaceqa/build.py` (`BUILD_FORMAT = 2`; call `qa.write_findings` before `meta.json`), `tests/synth.py` (the `plant` options of Task 1)
- Test: `tests/test_scoring.py`, `tests/test_qa.py`, `tests/test_build.py` (add)

**Interfaces:**
- Produces `scoring.py`:
  - `finding_points(f: Finding) -> float`: `min(size, 10.0) * WEIGHT[f.kind]`, where `size = f.size_mm3 / 100` for volume findings and `f.n / 100` for vertex findings, and `WEIGHT = {"pial_out": 1.0, "gray_missed": 1.0, "white_short": 1.0, "crossing": 2.0, "thickness": 0.5, "topology": 0.5}` (thickness and topology weigh less because the same error usually also shows as a volume finding).
  - `suspicion_score(findings: list[Finding]) -> float`: the sum, rounded to 1 decimal.
  - `rank_within_pipeline(scores: dict[str, tuple[str, float]]) -> dict[str, dict]`: input `key -> (pipeline name, score)`; output `key -> {"rank": 1-based, highest score first, ties share the lower number, "of": subjects in that pipeline}`.
- Produces `qa.py`:
  - `run_indicators(data: SubjectData) -> list[IndicatorResult]` (volume then surface, findings given their `region`).
  - `write_findings(data: SubjectData, run_dir: Path) -> dict` writing `findings.json`:

    ```json
    {"score": 12.3,
     "thresholds": {"MARGIN_MM": 1.0, "...": "..."},
     "region_note": "",
     "indicators": [{"name": "ribbon_outside_brain", "kind": "pial_out", "status": "ran",
                     "reason": "", "n_findings": 2, "dropped": 0}],
     "findings": [{"id": 0, "indicator": "...", "kind": "pial_out", "region": "sinus", "hemi": null,
                   "grid": [28, 15, 40], "size_mm3": 217.0, "n": 424, "points": 2.2,
                   "voxel_start": 0, "voxel_count": 424}],
     "defaults": {"sinus": [{"grid": [28, 15, 40], "label": "lh cuneus"}]}}
    ```

    Findings are ordered by `points` descending and `id` is the position in that order. `findings_voxels.bin` holds each finding's voxels as uint16 little-endian R, A, S triples; `voxel_start` and `voxel_count` are in voxels.
  - `load_findings(qa_dir: Path, key: str) -> dict | None` (the current run's `findings.json`).
- `build.py`: a failure inside the QA step must not lose the viewer. It is caught, the run is completed without `findings.json`, and `subjects/<key>/qa_error.txt` holds the traceback (removed by the next successful QA run).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scoring.py
def test_points():
    assert finding_points(Finding("x", "pial_out", (0, 0, 0), 250.0, 500)) == 2.5
    assert finding_points(Finding("x", "pial_out", (0, 0, 0), 5000.0, 9000)) == 10.0     # capped
    assert finding_points(Finding("x", "crossing", (0, 0, 0), 100.0, 100)) == 2.0
    assert finding_points(Finding("x", "thickness", (0, 0, 0), None, 300)) == 1.5

def test_score_is_the_rounded_sum():
    fs = [Finding("x", "pial_out", (0, 0, 0), 123.0, 1), Finding("x", "pial_out", (0, 0, 0), 20.0, 1)]
    assert suspicion_score(fs) == 1.4 and suspicion_score([]) == 0.0

def test_rank_within_pipeline():
    ranks = rank_within_pipeline({"a": ("fastsurfer", 5.0), "b": ("fastsurfer", 9.0),
                                  "c": ("freesurfer", 1.0), "d": ("fastsurfer", 5.0)})
    assert ranks["b"] == {"rank": 1, "of": 3} and ranks["a"]["rank"] == 2 and ranks["d"]["rank"] == 2
    assert ranks["c"] == {"rank": 1, "of": 1}

# tests/test_qa.py
@pytest.fixture
def planted(tmp_path):
    subj = write_subject(tmp_path / "fastsurfer", shape=(64, 64, 64))
    write_qa_files(subj, plant={"ribbon_blob": ((0.0, 0.0, 16.0), 4.0),
                                "thick_patch": ("lh", (0.0, 10.0, 0.0), 5.0)})
    return subj

def test_clean_synthetic_subject_scores_zero(tmp_path):
    subj = write_subject(tmp_path / "fastsurfer", shape=(64, 64, 64)); write_qa_files(subj)
    out = write_findings(load_subject_data(subj, detect_pipeline(subj)), tmp_path)
    assert out["score"] == 0.0 and out["findings"] == []
    assert {i["status"] for i in out["indicators"]} <= {"ran", "not run"}

def test_planted_errors_are_found_and_written(planted, tmp_path):
    out = write_findings(load_subject_data(planted, detect_pipeline(planted)), tmp_path)
    kinds = {f["indicator"] for f in out["findings"]}
    assert {"ribbon_outside_brain", "thick_patches"} <= kinds
    assert out["score"] > 0 and [f["id"] for f in out["findings"]] == list(range(len(out["findings"])))
    assert out["findings"] == sorted(out["findings"], key=lambda f: -f["points"])
    assert json.loads((tmp_path / "findings.json").read_text()) == out
    blob = np.frombuffer((tmp_path / "findings_voxels.bin").read_bytes(), "<u2").reshape(-1, 3)
    assert len(blob) == sum(f["voxel_count"] for f in out["findings"])
    f0 = next(f for f in out["findings"] if f["indicator"] == "ribbon_outside_brain")
    vox = blob[f0["voxel_start"]:f0["voxel_start"] + f0["voxel_count"]]
    assert tuple(f0["grid"]) in {tuple(v) for v in vox.tolist()}

def test_skipped_indicators_are_reported(tmp_path):
    subj = write_subject(tmp_path / "fs", pipeline="freesurfer", shape=(64, 64, 64))
    write_qa_files(subj, pipeline="freesurfer")
    out = write_findings(load_subject_data(subj, detect_pipeline(subj)), tmp_path)
    skipped = {i["name"]: i["reason"] for i in out["indicators"] if i["status"] == "not run"}
    assert "missed_gray" in skipped and "ribbon_in_nonbrain_mask" in skipped and all(skipped.values())

def test_findings_are_capped_and_the_cap_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(thresholds, "MAX_FINDINGS_PER_INDICATOR", 1)
    subj = write_subject(tmp_path / "fastsurfer", shape=(64, 64, 64))
    write_qa_files(subj, plant={"ribbon_blob": ((0.0, 0.0, 16.0), 4.0)})
    data = load_subject_data(subj, detect_pipeline(subj)); data.ribbon[2:8, 2:8, 2:8] = 3   # a second blob
    out = write_findings(data, tmp_path)
    ind = next(i for i in out["indicators"] if i["name"] == "ribbon_outside_brain")
    assert ind["n_findings"] == 1 and ind["dropped"] == 1

# tests/test_build.py (add)
def test_build_writes_findings(tmp_path):
    subj = write_subject(tmp_path / "fastsurfer", shape=(64, 64, 64))
    write_qa_files(subj, plant={"ribbon_blob": ((0.0, 0.0, 16.0), 4.0)})
    ref = find_subjects([subj])[0]; qa = tmp_path / "qa"
    res = build_subject(ref, qa)
    assert load_findings(qa, ref.key)["score"] > 0
    assert json.loads((qa / "subjects" / ref.key / "runs" / res.run / "meta.json").read_text())["format"] == 2

def test_qa_failure_keeps_the_viewer(tmp_path, monkeypatch):
    subj = write_subject(tmp_path / "fastsurfer"); write_qa_files(subj)
    monkeypatch.setattr("surfaceqa.build.write_findings", lambda *a, **k: 1 / 0)
    ref = find_subjects([subj])[0]; qa = tmp_path / "qa"
    res = build_subject(ref, qa)
    assert res.status == "built" and load_meta(qa, ref.key) is not None
    assert load_findings(qa, ref.key) is None
    assert "ZeroDivisionError" in (qa / "subjects" / ref.key / "qa_error.txt").read_text()
```

- [ ] **Step 2: Run to verify failure; commit tests** (`test: score, QA run, build integration`)
- [ ] **Step 3: Implement.** The existing Plan 1 build tests use subjects without QA files; they must keep passing with every indicator reported as not run.
- [ ] **Step 4: Run the whole suite; commit** (`feat: score, QA run, build integration`)

---

### Task 7: Checklist page, findings overlay, ranked index

**Files:**
- Create: `src/surfaceqa/web/templates/_checklist.html`, `src/surfaceqa/web/static/checklist.js`
- Modify: `src/surfaceqa/site.py`, `web/templates/subject.html`, `web/templates/index.html`, `web/static/logic.js`, `web/static/viewer.js`, `web/static/app.css`, `tests/js/logic.test.mjs`
- Test: `tests/test_site.py` (add), `tests/js/logic.test.mjs` (add)

**Interfaces:**
- Consumes: `load_findings`, `REGIONS`, `rank_within_pipeline`.
- Produces `logic.js` additions:
  - `findingVoxelsOnSlice(voxels: Uint16Array, finding: {voxel_start, voxel_count}, plane, slice) -> Array<[x, y]>`: screen coordinates of that finding's voxels lying on the slice.
  - `montageSlices(n: number, count: number) -> number[]`: `count` slice indices evenly spaced strictly inside `0..n-1` (for `n = 320, count = 20`: first 15, last 304, step about 15.2, rounded).
  - `zoomTo(viewW, viewH, plane, pixel: {h, v}, x, y, fieldMm) -> {scale, dx, dy}`: a view centred on screen point `(x, y)` showing `fieldMm` millimetres across the smaller canvas dimension.
- `viewer.js` exposes `window.surfaceqaViewer = {goTo(grid, {zoomMm}), setHighlight(findingId | null)}`; `checklist.js` uses only that.

**Page content (exact):**

Subject page, below the header and above the viewer, an indicator summary:
- `Suspicion score <score> · rank <rank> of <of> <pipeline> subjects`, followed by the sentence `The score only orders subjects and locations for review. It is not a judgment of quality, and a low score does not mean the surfaces are correct.`
- A line `Not run for this subject:` listing each indicator that did not run with its reason, when there are any; `region_note` when non-empty; `The automated indicators failed for this subject (see qa_error.txt); the checklist below has no findings to show.` when there is no `findings.json`.
- A toolbar checkbox `Findings` (default on) that shows or hides the overlay.

Below the viewer, the checklist, in this order:
1. `Bird's-eye view`: `Scroll through the whole brain first: two plausible hemispheres, no missing lobes, no surface jumping across a gap.` A montage of 20 coronal slices with contours.
2. `T1 quality`: `Look at the image, not the surfaces: blur, uneven intensity, banding from reslicing, defacing artifacts.` The same montage without contours.
3. One section per region in `REGIONS` order: its title, its `look_for` text, then either the region's findings as buttons, most points first (`<what> · <size>` where `<what>` is `pial too far out`, `gray matter missed`, `white surface short`, `hemispheres overlap`, `thick patch`, `topology defect`, and `<size>` is `217 mm³` or `391 vertices`), or `No indicator fired here. Look anyway:` followed by the region's default locations as buttons labelled with their `label`. A region with neither says `No indicator fired here. Look anyway by scrolling through this region.`
- Clicking a button moves all three views to the location, zooms each to a 60 mm field, highlights the finding's voxels, and scrolls the viewer into view. Clicking a montage tile moves the coronal view to that slice at the default zoom.

Viewer overlay: voxels of all findings on the current slice as translucent squares (`rgba(0, 229, 255, 0.35)`), the highlighted finding at `0.7` opacity; hidden while `s` is held or when `Findings` is unticked.

Index page: columns `Subject`, `Source`, `Pipeline`, `Status`, `Score`, `Rank`, `Findings` (count), `Largest` (the top finding as `<what> · <size> · <region title>`). Rows are grouped by pipeline (pipeline names sorted) and, within a pipeline, ordered by score descending; subjects without a score come last in their group and show `not computed`. The note above the table reads: `Subjects are ordered by suspicion score within each pipeline. No subject has been reviewed yet. The score only orders the work; it does not mean a subject is good or bad.`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_site.py (add); `qa_planted` fixture in conftest: fastsurfer sub-01 with QA files and
# plant={"ribbon_blob": ((0, 0, 16), 4)}, fastsurfer sub-02 clean with QA files, freesurfer-8.2.0 sub-01
# clean with QA files (all shape (64, 64, 64)), built and written.
def test_index_orders_by_score_within_pipeline(qa_planted):
    html = (qa_planted / "index.html").read_text()
    rows = re.findall(r'href="subjects/([^/]+)/index.html"', html)
    assert rows == ["fastsurfer__sub-01", "fastsurfer__sub-02", "freesurfer-8.2.0__sub-01"]
    assert "1 of 2" in html and "2 of 2" in html and "1 of 1" in html
    assert "pial too far out" in html and "it does not mean a subject is good or bad" in html

def test_subject_page_has_checklist_in_order(qa_planted):
    html = (qa_planted / "subjects" / "fastsurfer__sub-01" / "index.html").read_text()
    titles = ["Bird's-eye view", "T1 quality", "Sagittal and transverse sinus", "Cortex / cerebellum interface",
              "Frontal midline", "Inferior frontal and orbitofrontal", "Inferior temporal, near the ear canal",
              "Medial temporal, hippocampus", "Outer edge of the brain", "White surface", "Hemispheres crossing"]
    positions = [html.index(html_escape(t)) for t in titles]
    assert positions == sorted(positions)
    assert "Suspicion score" in html and "a low score does not mean the surfaces are correct" in html
    assert html.count("data-finding=") >= 1 and "pial too far out" in html

def test_regions_without_findings_say_look_anyway_and_never_ok(qa_planted):
    html = (qa_planted / "subjects" / "fastsurfer__sub-02" / "index.html").read_text()
    assert html.count("No indicator fired here. Look anyway") == 9
    assert not re.search(r"\bOK\b|no problems|looks fine|passed", html, re.I)

def test_not_run_indicators_are_listed_with_reasons(qa_planted):
    html = (qa_planted / "subjects" / "freesurfer-8.2.0__sub-01" / "index.html").read_text()
    assert "Not run for this subject:" in html and "missed_gray" in html and "parcels" in html

def test_subject_without_findings_file_says_so(qa):        # Plan 1 fixture: no QA files, indicators not run
    html = (qa / "subjects" / "fastsurfer__sub-01" / "index.html").read_text()
    assert "Not run for this subject:" in html
```

```js
// tests/js/logic.test.mjs (add)
test("findingVoxelsOnSlice picks the voxels on the slice, in screen coordinates", () => {
  const voxels = new Uint16Array([3, 24, 39,  4, 24, 39,  3, 25, 39,  9, 9, 9]);
  assert.deepEqual(findingVoxelsOnSlice(voxels, {voxel_start: 0, voxel_count: 3}, coronal, 24), [[28, 0], [27, 0]]);
  assert.deepEqual(findingVoxelsOnSlice(voxels, {voxel_start: 3, voxel_count: 1}, coronal, 24), []);
});
test("montageSlices are evenly spaced inside the volume", () => {
  const s = montageSlices(320, 20);
  assert.equal(s.length, 20); assert.equal(s[0], 15); assert.equal(s[19], 304);
  assert.ok(s.every((v, i) => i === 0 || v > s[i - 1]));
  assert.deepEqual(montageSlices(5, 20), [0, 1, 2, 3, 4]);
});
test("zoomTo centres the point and sets the field of view", () => {
  const v = zoomTo(600, 400, coronal, {h: 0.8, v: 0.8}, 10, 20, 50);
  assert.equal(v.scale, 8);                                  // 400 px / 50 mm
  assert.equal(v.dx + (10 + 0.5) * 0.8 * v.scale, 300);
  assert.equal(v.dy + (20 + 0.5) * 0.8 * v.scale, 200);
});
```

- [ ] **Step 2: Run to verify failure; commit tests** (`test: checklist page, overlay, ranked index`)
- [ ] **Step 3: Implement.** The montage is drawn in the browser from the existing slice images and contour files (small canvases), so the build writes nothing new for it. `site.py` passes the template a list of sections, each `{id, title, look_for, findings, defaults}`.
- [ ] **Step 4: Run the whole suite; commit** (`feat: checklist page, overlay, ranked index`)

---

### Task 8: Real data, calibration, record

**Files:**
- Modify: `src/surfaceqa/thresholds.py` (only if the evidence below calls for it)
- Create: `docs/indicators-on-subject-07.md`

- [ ] **Step 1: Build the three reconstructions**

Run: `uv run surfaceqa build <the three derivative folders> --out ~/surfaceqa-demo --jobs 3`
Expected: all built, none failed, no `qa_error.txt`. Record the added time per subject; if QA adds more than about 60 s per subject, profile (the distance transforms are the likely cost; computing them once per subject in `build_context` and inside bounding boxes is the fix).

- [ ] **Step 2: Look at every finding**

For each of `fastsurfer__sub-07`, `freesurfer-8.2.0__sub-07`, `freesurfer-NSD__subj07`: open the subject page, click through every finding button, and for each note region assigned, what the image shows (real error of the kind named / real error of another kind / boundary noise / anatomy the indicator misreads, e.g. a vessel or the choroid plexus), with a screenshot of the worst three per subject. Start with the NSD subject's large ribbon-over-background cluster.

- [ ] **Step 3: Compare with what Kay says**

His video grades one NSD-like subject A-/B+ and names pial into the sagittal sinus, the inferior frontal membrane, and orbitofrontal misses. For each: did an indicator fire there in any of the three reconstructions? Indicators that are mostly noise, and error types he names that nothing catches, are the two lists that matter.

- [ ] **Step 4: Adjust thresholds only with a reason**

Any change to `thresholds.py` gets a failing test first where it changes behaviour the tests pin (they pin `MARGIN_MM` and the minimums through `as_dict()`), and a line in the document saying what was seen that motivated it. An indicator that is mostly noise on all three subjects is not deleted: its weight in `scoring.WEIGHT` is lowered and the document says so.

- [ ] **Step 5: Write `docs/indicators-on-subject-07.md` and commit**

Contents: the table of findings per subject and indicator (count, total size, how many were real), the two lists from Step 3, each threshold change with its reason, the time and size cost, and a plain statement that three reconstructions of one subject is not validation. Commit: `docs: indicators on subject 07; calibration`.

---

## Done when

- `uv run pytest -q` passes.
- The three real reconstructions show ranked findings, a checklist in Kay's order, and working jump-to buttons and overlay.
- `docs/indicators-on-subject-07.md` says, indicator by indicator, what fired and whether it was real.
- Nothing was written under `/Volumes/extdata1/NSD/BIDS/derivatives/`.

## Deliberately not in this plan

- Ratings, marks, reviewers (Plan 3). The checklist has no rating controls yet.
- Fix recipes (Plan 4). Finding kinds here are the keys Plan 4's recipes will use.
- Cohort thickness outliers in fsaverage space and side-by-side comparison (Plan 5).
- Static zoomed panel images. The design called for "zoomed panels" per region; this plan uses buttons that move and zoom the live viewer instead, which shows the same place in all three planes and can be scrolled. If static panels turn out to be wanted (for printing or a quick skim), they are a small addition later.
