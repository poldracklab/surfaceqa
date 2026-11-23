# surfaceqa Plan 1: Build Pipeline and Scrollable Viewer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `surfaceqa build` turns FastSurfer and recon-all subject folders into per-subject report pages with a three-view scrollable T1 viewer showing the pial and white surface contours, and `surfaceqa serve` shows them in a browser.

**Architecture:** A Python package reads each subject through a small pipeline adapter, reorients the T1 to an RAS+ "display grid", cuts the four surface meshes with every slice plane, and writes slice images plus packed contour segments into a per-run folder under the QA directory. Static pages (Jinja2) and a vanilla-JS canvas viewer read those files; a FastAPI app serves them. Nothing is written into the input folders.

**Tech Stack:** Python 3.13 (uv), nibabel, numpy, Pillow, Jinja2, FastAPI + uvicorn, pytest, httpx (test client); vanilla ES-module JavaScript tested with `node --test` (node 26 is installed).

**Spec:** `docs/superpowers/specs/2026-11-22-surfaceqa-design.md`

## Where this plan sits

The spec is five subsystems. Each gets its own plan, written when the one before it is done, because each depends on what the previous one learns from real data.

1. **This plan:** inputs, pipeline adapters, contours, slice images, viewer, index, server.
2. Indicators, regions, suspicion score, findings overlay, region panels, checklist layout.
3. Rating protocol, marks, several reviewers, blind mode, skip, finalize, export.
4. Fix guidance: FastSurfer recipes from the spec; recon-all 8.2 recipes researched from the FreeSurfer 8 documentation.
5. Side-by-side comparison of two reconstructions; cohort thickness outliers.

## Global Constraints

- `uv` for package management; every command is `uv run ...`.
- No code or imports in any `__init__.py` (files exist, empty).
- pytest, test functions and fixtures only, no test classes.
- Red, green, refactor. The failing test is committed before the implementation, as its own commit.
- A test is changed only when the requirement changed or the test was wrong, never to make it pass.
- Short functions; one responsibility per module.
- Building reports must not call FreeSurfer binaries.
- Never write inside an input (source) directory.
- Commit messages end with `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.
- Colors: pial yellow `#ffe100`, left white surface blue `#2b6cff`, right white surface red `#ff3b30`.
- T1 shown is `mri/orig.mgz`.

## Review Focus

Inputs the spec implies but that are easy to get wrong. Each has a test in the task named.

1. **Surface coordinates are tkr RAS, not scanner RAS.** A subject whose volume has a nonzero `c_ras` must still have contours on the anatomy (Task 3, `test_tkr_to_grid_ignores_cras`).
2. **Volumes that are not 320^3 LIA at 0.8 mm.** The recon-all example is 256^3 at 1 mm; a non-LIA or non-cubic volume must still reorient correctly (Task 3, `test_display_volume_reorients_any_orientation`).
3. **A subject missing a required file.** The build continues and that subject's page says what is missing (Task 6, `test_build_subject_missing_files`). `?h.pial` absent but `?h.pial.T1` present is not "missing" (Task 2, `test_pial_falls_back_to_pial_t1`).
4. **The same subject name in two source folders** (`fastsurfer/sub-07`, `freesurfer-8.2.0/sub-07`) must not overwrite each other (Task 1, `test_same_name_in_two_sources_has_distinct_keys`).
5. **Rebuilds.** Unchanged surfaces: nothing is re-rendered. Changed surfaces: a new run folder, the old one kept (Task 6, `test_rebuild_unchanged_is_noop`, `test_rebuild_after_surface_change_keeps_old_run`).

## File Structure

```
pyproject.toml
src/surfaceqa/__init__.py          empty
src/surfaceqa/discover.py          find subject folders in source folders
src/surfaceqa/pipelines.py         detect pipeline + version; map file roles; report missing
src/surfaceqa/geometry.py          display grid: reorient volume, tkr RAS -> grid affine
src/surfaceqa/contours.py          mesh/plane intersection; pack segments to binary
src/surfaceqa/slices.py            intensity window; write slice JPEGs
src/surfaceqa/planes.py            the three planes: axes, flips, edge letters (shared with JS via meta.json)
src/surfaceqa/fingerprint.py       hash of the four surface files
src/surfaceqa/build.py             per-subject build, run folders, meta.json, parallel build
src/surfaceqa/site.py              render index.html and subject pages
src/surfaceqa/server.py            FastAPI app factory
src/surfaceqa/cli.py               argparse entry point: build, serve
src/surfaceqa/web/templates/{base,index,subject,missing}.html
src/surfaceqa/web/static/{logic.js,viewer.js,app.css}
tests/__init__.py                  empty
tests/synth.py                     writes a small synthetic subject folder
tests/conftest.py                  fixtures
tests/test_*.py                    one per module
tests/js/logic.test.mjs            node tests for logic.js
```

QA directory layout written by `build`:

```
<qa_dir>/index.html
<qa_dir>/static/...                         copied from the package
<qa_dir>/subjects/<key>/index.html          the subject page (or the "missing files" page)
<qa_dir>/subjects/<key>/current.json        {"run": "<fingerprint>"}
<qa_dir>/subjects/<key>/runs/<fingerprint>/meta.json
<qa_dir>/subjects/<key>/runs/<fingerprint>/slices/<plane>/<NNN>.jpg
<qa_dir>/subjects/<key>/runs/<fingerprint>/contours_<plane>.bin
<qa_dir>/subjects/<key>/runs/<fingerprint>/contours_<plane>.json
```

`<key>` is `<source folder name>__<subject folder name>`, e.g. `fastsurfer__sub-07`. `<plane>` is `sagittal`, `coronal` or `axial`.

---

### Task 1: Project scaffold, synthetic subject, subject discovery

**Files:**
- Create: `pyproject.toml`, `src/surfaceqa/__init__.py`, `tests/__init__.py`, `tests/synth.py`, `tests/conftest.py`, `src/surfaceqa/discover.py`
- Test: `tests/test_synth.py`, `tests/test_discover.py`

**Interfaces:**
- Produces:
  - `tests/synth.py`: `write_subject(root: Path, name: str = "sub-01", pipeline: str = "fastsurfer", shape=(32, 40, 48), voxel=1.0, orientation: str = "LIA", cras=(0.0, 0.0, 0.0), omit: tuple[str, ...] = ()) -> Path`. Writes `mri/orig.mgz` (uint8, a bright sphere of radius 10 mm centred on the volume centre, value 110 inside, 0 outside), `surf/{lh,rh}.{white,pial}` (icosphere meshes centred on the volume centre in tkr RAS, i.e. the origin: white radius 8 mm, pial radius 10 mm; `lh` shifted -0.0 and `rh` identical is fine), and the log files that identify the pipeline (below). `omit` lists relative paths not to write. Returns the subject folder.
    - `pipeline="fastsurfer"`: `scripts/deep-seg.log` containing the line `Version: 2.6.1+a314cd4f`, and `scripts/build-stamp.txt` containing `freesurfer-linux-rocky8_x86_64-8.2.0-20260314-d932c45\n2.6.1+a314cd4f (stable)\n`.
    - `pipeline="freesurfer"`: `scripts/recon-all.log` (any content) and `scripts/build-stamp.txt` containing `freesurfer-linux-ubuntu24_x86_64-8.2.0-20260314-d932c45\n`.
  - `tests/synth.py`: `icosphere(radius: float, subdivisions: int = 3) -> tuple[np.ndarray, np.ndarray]` (vertices `(n,3)` float, faces `(m,3)` int).
  - `conftest.py` fixtures: `synth_subject(tmp_path) -> Path` (a FastSurfer subject at `tmp_path/"fastsurfer"/"sub-01"`), `synth_sources(tmp_path) -> list[Path]` (two source folders `fastsurfer` and `freesurfer-8.2.0`, each containing `sub-01`, the second with `pipeline="freesurfer"`).
  - `discover.py`: `@dataclass(frozen=True) class SubjectRef: source: str; name: str; path: Path` with property `key -> str` returning `f"{source}__{name}"`; `find_subjects(sources: list[Path], patterns: list[str] | None = None) -> list[SubjectRef]`.

- [ ] **Step 1: Scaffold**

`uv init --package --name surfaceqa --python 3.13`, then `uv add nibabel numpy pillow jinja2 fastapi uvicorn` and `uv add --dev pytest httpx`. Set `[project.scripts] surfaceqa = "surfaceqa.cli:main"`. Empty `src/surfaceqa/__init__.py` (delete what `uv init` put there) and `tests/__init__.py`. Configure pytest `testpaths = ["tests"]`.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_synth.py
def test_synth_subject_has_readable_volume_and_surfaces(synth_subject):
    img = nib.load(synth_subject / "mri" / "orig.mgz")
    assert img.shape == (32, 40, 48)
    assert nib.aff2axcodes(img.affine) == ("L", "I", "A")
    verts, faces = nib.freesurfer.read_geometry(synth_subject / "surf" / "lh.pial")
    assert np.allclose(np.linalg.norm(verts, axis=1), 10.0, atol=1e-4)
    assert faces.shape[1] == 3

def test_synth_subject_can_omit_files(tmp_path):
    subj = write_subject(tmp_path / "src", omit=("surf/rh.pial",))
    assert not (subj / "surf" / "rh.pial").exists()

# tests/test_discover.py
def test_find_subjects_lists_folders_with_mri_and_surf(synth_sources):
    refs = find_subjects(synth_sources)
    assert [r.key for r in refs] == ["fastsurfer__sub-01", "freesurfer-8.2.0__sub-01"]

def test_same_name_in_two_sources_has_distinct_keys(synth_sources):
    refs = find_subjects(synth_sources)
    assert len({r.key for r in refs}) == 2

def test_find_subjects_accepts_a_single_subject_folder(synth_subject):
    refs = find_subjects([synth_subject])
    assert [(r.source, r.name) for r in refs] == [("fastsurfer", "sub-01")]

def test_find_subjects_skips_non_subject_folders(synth_sources):
    (synth_sources[0] / "QA").mkdir()
    (synth_sources[0] / "fsaverage").mkdir()
    assert all(r.name == "sub-01" for r in find_subjects(synth_sources))

def test_find_subjects_filters_by_shell_pattern(synth_sources):
    write_subject(synth_sources[0], name="sub-02")
    refs = find_subjects(synth_sources, patterns=["sub-02"])
    assert [r.name for r in refs] == ["sub-02"]
```

- [ ] **Step 3: Run to verify failure, then commit the tests**

Run: `uv run pytest -q` — expected: import errors for `tests.synth` / `surfaceqa.discover`.
Commit: `test: synthetic subject and subject discovery`.

- [ ] **Step 4: Implement `tests/synth.py`, `tests/conftest.py`, `src/surfaceqa/discover.py`**

- The synthetic volume's affine must be built for the requested `orientation` and `cras`, so that the tkr RAS origin is the volume centre (FreeSurfer's vox2ras-tkr convention). Write surfaces with `nib.freesurfer.write_geometry(..., volume_info=...)` carrying `cras`.
- A folder is a subject when it contains both `mri/` and `surf/`. A source that is itself a subject yields one ref whose `source` is its parent folder's name. Names containing `fsaverage` are skipped. Results are sorted by `key`. `patterns` are `fnmatch` patterns on `name`.

- [ ] **Step 5: Run to verify pass, then commit**

Run: `uv run pytest -q` — expected: 7 passed.
Commit: `feat: project scaffold, synthetic subject, subject discovery`.

---

### Task 2: Pipeline detection and file roles

**Files:**
- Create: `src/surfaceqa/pipelines.py`
- Test: `tests/test_pipelines.py`

**Interfaces:**
- Consumes: `SubjectRef`, `write_subject`.
- Produces:
  - `@dataclass(frozen=True) class PipelineInfo: name: str; version: str | None` where `name` is `"fastsurfer"`, `"freesurfer"` or `"unknown"`.
  - `detect_pipeline(subject_dir: Path) -> PipelineInfo`
  - `@dataclass(frozen=True) class SubjectFiles: t1: Path | None; surfaces: dict[str, Path]; missing: list[str]`. `surfaces` keys are exactly `"lh.pial"`, `"rh.pial"`, `"lh.white"`, `"rh.white"` for those present. `missing` holds relative paths such as `"surf/rh.pial"`, empty when complete.
  - `subject_files(subject_dir: Path) -> SubjectFiles`

- [ ] **Step 1: Write the failing tests**

```python
def test_detects_fastsurfer_with_version(synth_subject):
    assert detect_pipeline(synth_subject) == PipelineInfo("fastsurfer", "2.6.1")

def test_detects_freesurfer_with_version(tmp_path):
    subj = write_subject(tmp_path / "fs", pipeline="freesurfer")
    assert detect_pipeline(subj) == PipelineInfo("freesurfer", "8.2.0")

def test_freesurfer_6_build_stamp(tmp_path):
    subj = write_subject(tmp_path / "fs", pipeline="freesurfer")
    (subj / "scripts" / "build-stamp.txt").write_text(
        "freesurfer-Linux-centos6_x86_64-stable-pub-v6.0.0-2beb96c\n")
    assert detect_pipeline(subj).version == "6.0.0"

def test_no_logs_is_unknown(tmp_path):
    subj = write_subject(tmp_path / "x", omit=("scripts/deep-seg.log", "scripts/build-stamp.txt"))
    assert detect_pipeline(subj) == PipelineInfo("unknown", None)

def test_subject_files_complete(synth_subject):
    files = subject_files(synth_subject)
    assert files.missing == []
    assert files.t1 == synth_subject / "mri" / "orig.mgz"
    assert set(files.surfaces) == {"lh.pial", "rh.pial", "lh.white", "rh.white"}

def test_subject_files_reports_missing(tmp_path):
    subj = write_subject(tmp_path / "s", omit=("surf/rh.white", "mri/orig.mgz"))
    assert subject_files(subj).missing == ["mri/orig.mgz", "surf/rh.white"]

def test_pial_falls_back_to_pial_t1(tmp_path):
    subj = write_subject(tmp_path / "s")
    (subj / "surf" / "lh.pial").rename(subj / "surf" / "lh.pial.T1")
    files = subject_files(subj)
    assert files.missing == []
    assert files.surfaces["lh.pial"].name == "lh.pial.T1"
```

- [ ] **Step 2: Run to verify failure, commit tests** (`test: pipeline detection and file roles`)

- [ ] **Step 3: Implement**

- FastSurfer when `scripts/deep-seg.log` or `scripts/recon-surf.log` exists; version is the first `\d+\.\d+\.\d+` on the first line of `deep-seg.log` starting with `Version:`, else on line 2 of `build-stamp.txt`.
- Otherwise FreeSurfer when `scripts/recon-all.log` or `scripts/build-stamp.txt` exists; version is the first `\d+\.\d+\.\d+` in line 1 of `build-stamp.txt`.
- A surface "exists" only if the path resolves to a readable file (a dangling symlink counts as absent). `missing` is sorted.

- [ ] **Step 4: Run to verify pass, commit** (`feat: pipeline detection and file roles`)

---

### Task 3: Display grid geometry

**Files:**
- Create: `src/surfaceqa/geometry.py`, `src/surfaceqa/planes.py`
- Test: `tests/test_geometry.py`, `tests/test_planes.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class DisplayVolume: data: np.ndarray; tkr_to_grid: np.ndarray; voxel_sizes: tuple[float, float, float]`. `data` is the volume reoriented so axis 0 increases to the subject's Right, axis 1 to Anterior, axis 2 to Superior. `tkr_to_grid` is the 4x4 affine taking tkr RAS mm to (fractional) grid indices, where an integer index is a voxel centre. `voxel_sizes` are in grid-axis order.
  - `load_display_volume(path: Path) -> DisplayVolume`
  - `to_grid(vertices_tkr: np.ndarray, tkr_to_grid: np.ndarray) -> np.ndarray` (`(n,3)` -> `(n,3)`)
  - `planes.py`: `@dataclass(frozen=True) class Plane: name: str; axis: int; h_axis: int; v_axis: int; h_flip: bool; v_flip: bool; edges: dict[str, str]` and `PLANES: dict[str, Plane]`:

    | name | axis | h_axis | v_axis | h_flip | v_flip | edges (left, right, top, bottom) |
    |---|---|---|---|---|---|---|
    | sagittal | 0 | 1 | 2 | False | True | P, A, S, I |
    | coronal | 1 | 0 | 2 | True | True | R, L, S, I |
    | axial | 2 | 0 | 1 | True | True | R, L, A, P |

    (Radiological: the subject's right is on screen left. `*_flip` True means the screen coordinate is `size - 1 - index`. These follow Freeview's defaults; Task 8 checks them against `freeview`.)
  - `planes.py`: `slice_image(data: np.ndarray, plane: Plane, index: int) -> np.ndarray` returning the 2-D slice in screen orientation (row 0 at top, column 0 at left).
  - `planes.py`: `to_screen(h: np.ndarray, v: np.ndarray, plane: Plane, shape: tuple[int, int, int]) -> tuple[np.ndarray, np.ndarray]` mapping in-plane grid coordinates to screen pixel coordinates (pixel centres at integers).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_geometry.py
def test_display_volume_is_ras(synth_subject):
    vol = load_display_volume(synth_subject / "mri" / "orig.mgz")
    assert vol.data.shape == (32, 48, 40)   # LIA (32,40,48) -> R, A, S

def test_tkr_origin_maps_to_volume_centre(synth_subject):
    vol = load_display_volume(synth_subject / "mri" / "orig.mgz")
    centre = to_grid(np.zeros((1, 3)), vol.tkr_to_grid)[0]
    assert np.allclose(centre, [16, 24, 20])

def test_grid_axes_point_right_anterior_superior(synth_subject):
    vol = load_display_volume(synth_subject / "mri" / "orig.mgz")
    pts = to_grid(np.array([[5.0, 0, 0], [0, 5.0, 0], [0, 0, 5.0]]), vol.tkr_to_grid)
    origin = to_grid(np.zeros((1, 3)), vol.tkr_to_grid)[0]
    assert np.allclose(pts - origin, np.eye(3) * 5.0)

def test_tkr_to_grid_ignores_cras(tmp_path):
    subj = write_subject(tmp_path / "s", cras=(12.0, -7.0, 3.0))
    vol = load_display_volume(subj / "mri" / "orig.mgz")
    assert np.allclose(to_grid(np.zeros((1, 3)), vol.tkr_to_grid)[0], [16, 24, 20])

@pytest.mark.parametrize("orientation", ["LIA", "RAS", "LPS", "PIR"])
def test_display_volume_reorients_any_orientation(tmp_path, orientation):
    subj = write_subject(tmp_path / orientation, orientation=orientation, voxel=0.8)
    vol = load_display_volume(subj / "mri" / "orig.mgz")
    # the bright sphere (radius 10 mm) is centred on the tkr origin in every orientation
    centre = to_grid(np.zeros((1, 3)), vol.tkr_to_grid)[0]
    bright = np.argwhere(vol.data > 0)
    assert np.allclose(bright.mean(axis=0), centre, atol=0.6)
    assert vol.voxel_sizes == pytest.approx((0.8, 0.8, 0.8))

def test_surface_sits_on_sphere_edge_in_grid(synth_subject):
    vol = load_display_volume(synth_subject / "mri" / "orig.mgz")
    verts, _ = nib.freesurfer.read_geometry(synth_subject / "surf" / "lh.pial")
    grid = to_grid(verts, vol.tkr_to_grid)
    inside = vol.data[tuple(np.round(grid * 0.95 + np.array([16, 24, 20]) * 0.05).astype(int).T)]
    assert (inside > 0).mean() > 0.99

# tests/test_planes.py
def test_planes_table():
    c = PLANES["coronal"]
    assert (c.axis, c.h_axis, c.v_axis, c.h_flip, c.v_flip) == (1, 0, 2, True, True)
    assert PLANES["sagittal"].edges == {"left": "P", "right": "A", "top": "S", "bottom": "I"}
    assert PLANES["axial"].edges == {"left": "R", "right": "L", "top": "A", "bottom": "P"}

def test_slice_image_orientation():
    data = np.zeros((4, 5, 6), dtype=np.uint8)
    data[3, 2, 5] = 9          # far right, mid, most superior
    img = slice_image(data, PLANES["coronal"], 2)
    assert img.shape == (6, 4)  # rows = S axis, cols = R axis
    assert img[0, 0] == 9       # right is screen-left, superior is top

def test_to_screen_matches_slice_image():
    data = np.zeros((4, 5, 6), dtype=np.uint8)
    data[3, 2, 5] = 9
    x, y = to_screen(np.array([3.0]), np.array([5.0]), PLANES["coronal"], data.shape)
    assert (x[0], y[0]) == (0.0, 0.0)
```

- [ ] **Step 2: Run to verify failure, commit tests** (`test: display grid geometry and planes`)

- [ ] **Step 3: Implement**

- vox2ras-tkr comes from `img.header.get_vox2ras_tkr()`. The reorientation comes from `nib.orientations.io_orientation(img.affine)` / `ornt_transform` to RAS; apply it to the data with `apply_orientation` and compose `inv_ornt_aff` into the affine: `grid_to_tkr = vox2ras_tkr @ inv_ornt_aff(ornt, shape)`, `tkr_to_grid = inv(grid_to_tkr)`.
- Read the data with `np.asarray(img.dataobj)` (keeps uint8).

- [ ] **Step 4: Run to verify pass, commit** (`feat: display grid geometry and planes`)

---

### Task 4: Surface contours

**Files:**
- Create: `src/surfaceqa/contours.py`
- Test: `tests/test_contours.py`

**Interfaces:**
- Consumes: `Plane`, `PLANES`, `to_screen`, `icosphere`.
- Produces:
  - `slice_segments(vertices: np.ndarray, faces: np.ndarray, axis: int, index: float) -> np.ndarray`: the intersection of the mesh with the plane `coordinate[axis] == index`, as an `(n, 2, 3)` array of segment endpoints in the same coordinates as `vertices`. A triangle with a vertex exactly on the plane is handled by treating "on the plane" as the positive side.
  - `plane_segments(vertices_grid: np.ndarray, faces: np.ndarray, plane: Plane, shape: tuple[int, int, int]) -> list[np.ndarray]`: one `(n, 4)` float array per slice index along `plane.axis`, columns `x1, y1, x2, y2` in screen pixel coordinates.
  - `QUANT = 64` and `pack_plane(per_surface: dict[str, list[np.ndarray]]) -> tuple[bytes, dict]`: concatenates, surface by surface (in the order `lh.pial, rh.pial, lh.white, rh.white`) and slice by slice, the segments quantized as little-endian uint16 `round((coord + 0.5) * QUANT)`. The dict is `{"quant": 64, "surfaces": {name: [offset_0, ..., offset_n_slices]}}`, offsets counted in segments from the start of the file, so slice `i` of a surface is segments `offsets[i]:offsets[i+1]`.
  - `unpack_slice(blob: bytes, index: dict, surface: str, i: int) -> np.ndarray` (`(n,4)` float; the inverse, used by tests and later plans).

- [ ] **Step 1: Write the failing tests**

```python
def test_sphere_cut_through_centre_is_a_circle():
    verts, faces = icosphere(10.0, subdivisions=4)
    segs = slice_segments(verts, faces, axis=2, index=0.0)
    pts = segs.reshape(-1, 3)
    assert np.allclose(pts[:, 2], 0.0)
    assert np.allclose(np.linalg.norm(pts[:, :2], axis=1), 10.0, atol=0.05)
    length = np.linalg.norm(segs[:, 0] - segs[:, 1], axis=1).sum()
    assert length == pytest.approx(2 * np.pi * 10.0, rel=0.01)

def test_sphere_cut_off_centre_has_smaller_radius():
    verts, faces = icosphere(10.0, subdivisions=4)
    pts = slice_segments(verts, faces, axis=0, index=6.0).reshape(-1, 3)
    assert np.allclose(np.linalg.norm(pts[:, 1:], axis=1), 8.0, atol=0.05)

def test_plane_missing_the_mesh_gives_no_segments():
    verts, faces = icosphere(10.0)
    assert slice_segments(verts, faces, axis=1, index=11.0).shape == (0, 2, 3)

def test_contour_is_closed():
    # every endpoint is shared by exactly two segments
    verts, faces = icosphere(10.0, subdivisions=3)
    pts = np.round(slice_segments(verts, faces, 2, 0.3).reshape(-1, 3), 6)
    _, counts = np.unique(pts, axis=0, return_counts=True)
    assert (counts == 2).all()

def test_vertex_exactly_on_plane_does_not_break_closure():
    verts, faces = icosphere(10.0, subdivisions=2)   # has vertices at z == 0
    pts = np.round(slice_segments(verts, faces, 2, 0.0).reshape(-1, 3), 6)
    _, counts = np.unique(pts, axis=0, return_counts=True)
    assert (counts % 2 == 0).all() and len(pts) > 0

def test_plane_segments_are_in_screen_coordinates():
    verts, faces = icosphere(10.0, subdivisions=4)
    grid = verts + np.array([16, 24, 20])
    per_slice = plane_segments(grid, faces, PLANES["coronal"], (32, 48, 40))
    assert len(per_slice) == 48
    mid = per_slice[24]
    # coronal: x = 31 - R index, y = 39 - S index; circle centred at (15, 19)
    r = np.hypot(mid[:, 0] - 15.0, mid[:, 1] - 19.0)
    assert np.allclose(r, 10.0, atol=0.05)
    assert per_slice[0].shape == (0, 4)

def test_pack_round_trip():
    verts, faces = icosphere(10.0, subdivisions=3)
    grid = verts + np.array([16, 24, 20])
    per = {name: plane_segments(grid, faces, PLANES["axial"], (32, 48, 40))
           for name in ("lh.pial", "rh.pial", "lh.white", "rh.white")}
    blob, index = pack_plane(per)
    assert index["quant"] == 64
    assert len(index["surfaces"]["rh.white"]) == 41
    assert len(blob) == index["surfaces"]["rh.white"][-1] * 4 * 2
    back = unpack_slice(blob, index, "rh.pial", 20)
    assert np.allclose(back, per["rh.pial"][20], atol=1 / 64)
```

- [ ] **Step 2: Run to verify failure, commit tests** (`test: surface contours`)

- [ ] **Step 3: Implement**

The algorithm, vectorized over faces: `d = vertices[faces][:, :, axis] - index`; `side = d >= 0`; a face is cut when its three `side` values are not all equal; in a cut face exactly one vertex is alone on its side, and the two edges from that vertex each cross the plane at `t = d_a / (d_a - d_b)`. For `plane_segments`, pre-compute each face's min and max along the axis once and select candidate faces per slice from those, so the cost does not scale as faces times slices. Real surfaces are about 190k faces and 320 slices per plane; all three planes of one surface should take a few seconds.

- [ ] **Step 4: Run to verify pass, commit** (`feat: surface contours`)

---

### Task 5: Slice images

**Files:**
- Create: `src/surfaceqa/slices.py`
- Test: `tests/test_slices.py`

**Interfaces:**
- Consumes: `Plane`, `PLANES`, `slice_image`.
- Produces:
  - `intensity_window(data: np.ndarray) -> tuple[float, float]`: `(0.0, p)` where `p` is the 99.5th percentile of the voxels greater than 0; `(0.0, 1.0)` for an all-zero volume.
  - `to_uint8(img: np.ndarray, window: tuple[float, float]) -> np.ndarray`: linear map of the window to 0..255, clipped.
  - `write_plane_slices(data: np.ndarray, plane: Plane, window: tuple[float, float], out_dir: Path) -> int`: writes `out_dir/NNN.jpg` (zero-padded to 3 digits, grayscale JPEG, quality 85) for every index along `plane.axis`; returns the count.

- [ ] **Step 1: Write the failing tests**

```python
def test_window_ignores_background_and_outliers():
    data = np.zeros((20, 20, 20), dtype=np.uint8)
    data[5:15, 5:15, 5:15] = 100
    data[10, 10, 10] = 255
    assert intensity_window(data) == (0.0, 100.0)

def test_window_of_empty_volume():
    assert intensity_window(np.zeros((4, 4, 4))) == (0.0, 1.0)

def test_to_uint8_clips():
    out = to_uint8(np.array([[0.0, 50.0, 100.0, 300.0]]), (0.0, 100.0))
    assert out.tolist() == [[0, 128, 255, 255]] and out.dtype == np.uint8

def test_write_plane_slices(tmp_path):
    data = np.zeros((4, 5, 6), dtype=np.uint8)
    data[3, 2, 5] = 200
    n = write_plane_slices(data, PLANES["coronal"], (0.0, 200.0), tmp_path)
    assert n == 5 and sorted(p.name for p in tmp_path.iterdir())[0] == "000.jpg"
    img = np.asarray(Image.open(tmp_path / "002.jpg"))
    assert img.shape == (6, 4)
    assert img[0, 0] > 100 and img[5, 3] < 40   # bright voxel at top-left
```

- [ ] **Step 2: Run to verify failure, commit tests** (`test: slice images`)
- [ ] **Step 3: Implement** (Pillow `Image.fromarray(..., mode "L").save(path, quality=85)`).
- [ ] **Step 4: Run to verify pass, commit** (`feat: slice images`)

---

### Task 6: Per-subject build

**Files:**
- Create: `src/surfaceqa/fingerprint.py`, `src/surfaceqa/build.py`
- Test: `tests/test_fingerprint.py`, `tests/test_build.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `fingerprint.py`: `surface_fingerprint(surfaces: dict[str, Path]) -> str`: first 12 hex characters of the SHA-256 over, for each of `lh.pial, rh.pial, lh.white, rh.white` in that order, the name followed by the file's bytes.
  - `build.py`: `@dataclass class BuildResult: key: str; status: str; run: str | None; missing: list[str]`. `status` is one of `"built"`, `"unchanged"`, `"missing"`, `"failed"`.
  - `build.py`: `build_subject(ref: SubjectRef, qa_dir: Path) -> BuildResult`
  - `build.py`: `build_all(refs: list[SubjectRef], qa_dir: Path, jobs: int = 1) -> list[BuildResult]` (results in the order of `refs`; process pool when `jobs > 1`; one subject raising must not stop the others: it becomes `status="failed"` with the exception text written to `subjects/<key>/error.txt`).
  - `meta.json` in the run folder:

    ```json
    {"key": "fastsurfer__sub-01", "source": "fastsurfer", "name": "sub-01",
     "path": "/abs/path/to/subject", "pipeline": "fastsurfer", "version": "2.6.1",
     "run": "<fingerprint>", "built": "<ISO 8601 UTC>",
     "shape": [32, 48, 40], "voxel_sizes": [1.0, 1.0, 1.0], "window": [0.0, 110.0],
     "planes": {"coronal": {"axis": 1, "h_axis": 0, "v_axis": 2, "h_flip": true, "v_flip": true,
                            "n_slices": 48, "width": 32, "height": 40,
                            "edges": {"left": "R", "right": "L", "top": "S", "bottom": "I"}},
                "sagittal": {...}, "axial": {...}},
     "surfaces": {"lh.pial": {"color": "#ffe100"}, "rh.pial": {"color": "#ffe100"},
                  "lh.white": {"color": "#2b6cff"}, "rh.white": {"color": "#ff3b30"}}}
    ```
  - When files are missing: no run folder; `subjects/<key>/missing.json` = `{"key", "source", "name", "path", "pipeline", "version", "missing": [...]}`.
  - `build.py`: `load_meta(qa_dir: Path, key: str) -> dict | None` (the current run's `meta.json`, or `None`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_fingerprint.py
def test_fingerprint_is_stable_and_12_hex(synth_subject):
    s = subject_files(synth_subject).surfaces
    fp = surface_fingerprint(s)
    assert fp == surface_fingerprint(s) and re.fullmatch(r"[0-9a-f]{12}", fp)

def test_fingerprint_changes_when_a_surface_changes(synth_subject):
    s = subject_files(synth_subject).surfaces
    before = surface_fingerprint(s)
    v, f = icosphere(9.0)
    nib.freesurfer.write_geometry(s["rh.white"], v, f)
    assert surface_fingerprint(s) != before

# tests/test_build.py
@pytest.fixture
def built(synth_subject, tmp_path):
    ref = find_subjects([synth_subject])[0]
    qa = tmp_path / "qa"
    return ref, qa, build_subject(ref, qa)

def test_build_subject_writes_run(built):
    ref, qa, res = built
    run = qa / "subjects" / "fastsurfer__sub-01" / "runs" / res.run
    assert res.status == "built"
    assert json.loads((run.parent.parent / "current.json").read_text()) == {"run": res.run}
    meta = json.loads((run / "meta.json").read_text())
    assert meta["pipeline"] == "fastsurfer" and meta["version"] == "2.6.1"
    assert meta["shape"] == [32, 48, 40]
    assert meta["planes"]["coronal"]["n_slices"] == 48
    assert meta["planes"]["coronal"]["width"] == 32 and meta["planes"]["coronal"]["height"] == 40
    assert meta["surfaces"]["rh.white"]["color"] == "#ff3b30"
    assert len(list((run / "slices" / "sagittal").glob("*.jpg"))) == 32
    for plane in ("sagittal", "coronal", "axial"):
        assert (run / f"contours_{plane}.bin").stat().st_size > 0
        assert "surfaces" in json.loads((run / f"contours_{plane}.json").read_text())

def test_built_contours_lie_on_the_sphere(built):
    ref, qa, res = built
    run = qa / "subjects" / ref.key / "runs" / res.run
    index = json.loads((run / "contours_axial.json").read_text())
    segs = unpack_slice((run / "contours_axial.bin").read_bytes(), index, "lh.pial", 20)
    # axial screen: x = 31 - R, y = 47 - A; sphere centre (16, 24) -> (15, 23); radius 10
    r = np.hypot(segs[:, 0] - 15.0, segs[:, 1] - 23.0)
    assert len(segs) > 0 and np.allclose(r, 10.0, atol=0.1)

def test_build_never_writes_into_the_source(built, synth_subject):
    before = {p: p.stat().st_mtime_ns for p in synth_subject.rglob("*")}
    ref, qa, _ = built
    build_subject(ref, qa)
    assert {p: p.stat().st_mtime_ns for p in synth_subject.rglob("*")} == before

def test_rebuild_unchanged_is_noop(built):
    ref, qa, res = built
    meta_path = qa / "subjects" / ref.key / "runs" / res.run / "meta.json"
    stamp = meta_path.stat().st_mtime_ns
    again = build_subject(ref, qa)
    assert again.status == "unchanged" and again.run == res.run
    assert meta_path.stat().st_mtime_ns == stamp

def test_rebuild_after_surface_change_keeps_old_run(built, synth_subject):
    ref, qa, res = built
    v, f = icosphere(9.0)
    nib.freesurfer.write_geometry(synth_subject / "surf" / "lh.pial", v, f)
    new = build_subject(ref, qa)
    runs = qa / "subjects" / ref.key / "runs"
    assert new.status == "built" and new.run != res.run
    assert {p.name for p in runs.iterdir()} == {res.run, new.run}
    assert json.loads((runs.parent / "current.json").read_text()) == {"run": new.run}

def test_build_subject_missing_files(tmp_path):
    subj = write_subject(tmp_path / "src", omit=("surf/rh.pial",))
    ref = find_subjects([subj])[0]
    res = build_subject(ref, tmp_path / "qa")
    assert res.status == "missing" and res.missing == ["surf/rh.pial"] and res.run is None
    info = json.loads((tmp_path / "qa" / "subjects" / ref.key / "missing.json").read_text())
    assert info["missing"] == ["surf/rh.pial"]

def test_interrupted_build_is_redone(built):
    ref, qa, res = built
    (qa / "subjects" / ref.key / "runs" / res.run / "meta.json").unlink()
    assert build_subject(ref, qa).status == "built"

def test_build_all_survives_a_broken_subject(synth_sources, tmp_path):
    (synth_sources[1] / "sub-01" / "surf" / "lh.white").write_bytes(b"not a surface")
    results = build_all(find_subjects(synth_sources), tmp_path / "qa", jobs=2)
    assert [r.status for r in results] == ["built", "failed"]
    assert (tmp_path / "qa" / "subjects" / "freesurfer-8.2.0__sub-01" / "error.txt").exists()

def test_load_meta(built):
    ref, qa, res = built
    assert load_meta(qa, ref.key)["run"] == res.run
    assert load_meta(qa, "nope__nobody") is None
```

- [ ] **Step 2: Run to verify failure, commit tests** (`test: per-subject build`)

- [ ] **Step 3: Implement**

`meta.json` is written last and is what marks a run as complete: a run folder without it is rebuilt from scratch. `current.json` is written after `meta.json`. Keep `build_subject` as a short sequence of calls to small functions (`_write_slices`, `_write_contours`, `_write_meta`, ...).

- [ ] **Step 4: Run to verify pass, commit** (`feat: per-subject build`)

---

### Task 7: Viewer logic (JavaScript, no DOM)

**Files:**
- Create: `src/surfaceqa/web/static/logic.js`, `tests/js/logic.test.mjs`
- Test: `tests/test_js.py` (runs the node tests from pytest so one command covers everything)

**Interfaces:**
- Consumes: `meta.json` and the contour files as specified in Tasks 4 and 6.
- Produces (ES module exports of `logic.js`):
  - `sliceSegments(buffer: ArrayBuffer, index: object, surface: string, i: number) -> Float32Array` (length `4n`: `x1,y1,x2,y2,...` in screen pixels; the inverse of `pack_plane`).
  - `gridToScreen(grid: [number, number, number], planeMeta: object) -> {x, y, slice}` and `screenToGrid(x, y, slice, planeMeta, shape) -> [r, a, s]`, using `axis`, `h_axis`, `v_axis`, `h_flip`, `v_flip`, `width`, `height` from `meta.planes[plane]`.
  - `clampSlice(i: number, n: number) -> number` (integer in `0..n-1`).
  - `crosshairs(cursor: [number, number, number], planeMeta: object) -> {x, y}` (where the other two planes cut this view).
  - `initialCursor(shape) -> [r, a, s]` (the centre voxel, floored).
  - `fit(viewW, viewH, imgW, imgH) -> {scale, dx, dy}` (largest scale that fits, centred).
  - `zoomAt(view: {scale, dx, dy}, factor: number, px: number, py: number) -> {scale, dx, dy}` (the image point under `(px, py)` stays under it; scale clamped to `0.5..32`).

- [ ] **Step 1: Write the failing tests**

`tests/js/logic.test.mjs`, using `node:test` and `node:assert/strict`, with these cases and values:

```js
const coronal = {axis: 1, h_axis: 0, v_axis: 2, h_flip: true, v_flip: true, width: 32, height: 40, n_slices: 48};
const sagittal = {axis: 0, h_axis: 1, v_axis: 2, h_flip: false, v_flip: true, width: 48, height: 40, n_slices: 32};
const shape = [32, 48, 40];

test("sliceSegments decodes quantized uint16", () => {
  const u = new Uint16Array([32, 32, 96, 160,  672, 32, 32, 32]);   // (c+0.5)*64
  const index = {quant: 64, surfaces: {"lh.pial": [0, 1, 2], "rh.pial": [2, 2, 2]}};
  assert.deepEqual([...sliceSegments(u.buffer, index, "lh.pial", 0)], [0, 0, 1, 2]);
  assert.deepEqual([...sliceSegments(u.buffer, index, "lh.pial", 1)], [10, 0, 0, 0]);
  assert.equal(sliceSegments(u.buffer, index, "rh.pial", 1).length, 0);
});
test("gridToScreen applies flips", () => {
  assert.deepEqual(gridToScreen([3, 24, 39], coronal), {x: 28, y: 0, slice: 24});
  assert.deepEqual(gridToScreen([3, 24, 39], sagittal), {x: 24, y: 0, slice: 3});
});
test("screenToGrid inverts gridToScreen", () => {
  assert.deepEqual(screenToGrid(28, 0, 24, coronal, shape), [3, 24, 39]);
  assert.deepEqual(screenToGrid(24, 0, 3, sagittal, shape), [3, 24, 39]);
});
test("clampSlice", () => {
  assert.equal(clampSlice(-3, 48), 0); assert.equal(clampSlice(99, 48), 47); assert.equal(clampSlice(7.6, 48), 8);
});
test("crosshairs show the other two planes", () => {
  assert.deepEqual(crosshairs([3, 24, 39], coronal), {x: 28, y: 0});
});
test("initialCursor is the centre", () => { assert.deepEqual(initialCursor(shape), [16, 24, 20]); });
test("fit centres the image", () => {
  assert.deepEqual(fit(640, 400, 32, 40), {scale: 10, dx: 160, dy: 0});
});
test("zoomAt keeps the pointed pixel fixed", () => {
  const v = zoomAt({scale: 10, dx: 160, dy: 0}, 2, 200, 100);
  assert.equal(v.scale, 20);
  assert.equal((200 - v.dx) / v.scale, (200 - 160) / 10);
  assert.equal(zoomAt({scale: 20, dx: 0, dy: 0}, 4, 0, 0).scale, 32);
});
```

`tests/test_js.py`:

```python
def test_node_logic_tests():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    out = subprocess.run([node, "--test", "tests/js/"], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
```

- [ ] **Step 2: Run to verify failure, commit tests** (`test: viewer logic`)

Run: `uv run pytest tests/test_js.py -q` — expected: FAIL (module `logic.js` not found).

- [ ] **Step 3: Implement `logic.js`** (pure functions, no DOM, no imports).
- [ ] **Step 4: Run to verify pass, commit** (`feat: viewer logic`)

---

### Task 8: Pages, viewer, server, CLI

**Files:**
- Create: `src/surfaceqa/site.py`, `src/surfaceqa/server.py`, `src/surfaceqa/cli.py`, `src/surfaceqa/web/templates/{base,index,subject,missing}.html`, `src/surfaceqa/web/static/{viewer.js,app.css}`
- Modify: `pyproject.toml` (include `web/` as package data)
- Test: `tests/test_site.py`, `tests/test_server.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `build_all`, `BuildResult`, `load_meta`, `find_subjects`, `logic.js`.
- Produces:
  - `site.py`: `write_site(qa_dir: Path) -> None`. Copies the package's `web/static/` to `<qa_dir>/static/`, writes `<qa_dir>/index.html` and one `<qa_dir>/subjects/<key>/index.html` per subject folder found under `<qa_dir>/subjects/` (the viewer page when a current run exists, the missing-files page when `missing.json` exists, an error page when only `error.txt` exists). It reads only the QA directory, so it can be rerun without the sources.
  - `server.py`: `create_app(qa_dir: Path) -> fastapi.FastAPI`, serving `qa_dir` as static files with `index.html` as the directory index. Later plans add API routes to this app.
  - `cli.py`: `main(argv: list[str] | None = None) -> int`.
    - `surfaceqa build SOURCE [SOURCE ...] --out QA_DIR [--subjects PATTERN ...] [--jobs N]`. `--out` defaults to `surfaceqa/` beside the first source (its sibling). Prints one line per subject (`key  status`) and a summary; returns 0 when no subject failed, 1 otherwise. A subject with missing files is not a failure of the command.
    - `surfaceqa serve QA_DIR [--host 127.0.0.1] [--port 8765]`. Prints the URL and runs uvicorn.
    - Refuses with exit code 2 and a message when `--out` is inside any source folder.

**Page content (exact):**
- Index: a table, one row per subject, columns `Subject` (link to the subject page; text is the subject name), `Source`, `Pipeline` (e.g. `fastsurfer 2.6.1`; `unknown` when not detected), `Status` (`ready`, `missing files`, or `build failed`), sorted by key. Title `surfaceqa`.
- Subject page header: subject name, source, pipeline and version, the subject's path, and the line `Not yet reviewed` (ratings arrive in Plan 3; the page must not suggest a subject is fine).
- Missing-files page: the header plus `This subject could not be rendered. Missing files:` and the list.
- Viewer, in the subject page: three canvases side by side (coronal, sagittal, axial, in that order), each with its edge letters and a readout `plane  slice i / n`. A toolbar with: `Surfaces` checkbox, per-surface checkboxes (`pial`, `white`), and `Reset view`. Key help line under the viewer: `scroll or arrow keys: change slice · click: move the other two views · ctrl/cmd + scroll: zoom · drag: pan · double-click a view: enlarge / restore · hold s: hide surfaces`.

**Viewer behaviour (`viewer.js`, DOM code only; all arithmetic goes through `logic.js`):**
- State: `cursor = [r, a, s]` grid indices, one `{scale, dx, dy}` per view, surface visibility flags, `enlarged` view or none.
- Each view shows the slice of its plane at `cursor[axis]`: the JPEG `runs/<run>/slices/<plane>/<NNN>.jpg` drawn with image smoothing off, then that slice's segments for each visible surface in `meta.surfaces[name].color`, line width 1.5 CSS pixels regardless of zoom, then crosshair lines (thin, 40% opacity).
- Contours for a plane are fetched once (`contours_<plane>.bin` + `.json`) and kept. Neighbouring slice images (±3) are preloaded.
- Wheel over a view steps that view's slice by one per wheel notch; up/down arrows step the view under the pointer (the coronal view when the pointer is over none); page up/down step by 10.
- Click sets the cursor from `screenToGrid`, moving the other two views.
- `s` held hides all surfaces; releasing restores the checkbox state.
- Canvases are sized for the device pixel ratio so lines stay sharp.
- The page works when opened through `surfaceqa serve`; it need not work from `file://`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_site.py
@pytest.fixture
def qa(synth_sources, tmp_path):
    bad = write_subject(synth_sources[0], name="sub-02", omit=("surf/lh.white",))
    qa = tmp_path / "qa"
    build_all(find_subjects(synth_sources), qa)
    write_site(qa)
    return qa

def test_index_lists_every_subject(qa):
    html = (qa / "index.html").read_text()
    for key in ("fastsurfer__sub-01", "fastsurfer__sub-02", "freesurfer-8.2.0__sub-01"):
        assert f'href="subjects/{key}/index.html"' in html
    assert "fastsurfer 2.6.1" in html and "freesurfer 8.2.0" in html
    assert html.count(">ready<") == 2 and html.count(">missing files<") == 1

def test_subject_page_has_viewer_and_is_not_marked_reviewed(qa):
    html = (qa / "subjects" / "fastsurfer__sub-01" / "index.html").read_text()
    run = json.loads((qa / "subjects" / "fastsurfer__sub-01" / "current.json").read_text())["run"]
    assert html.count("<canvas") == 3
    assert f"runs/{run}/meta.json" in html
    assert "Not yet reviewed" in html
    assert "hold s: hide surfaces" in html

def test_missing_page_names_the_files(qa):
    html = (qa / "subjects" / "fastsurfer__sub-02" / "index.html").read_text()
    assert "surf/lh.white" in html and "<canvas" not in html

def test_static_files_are_copied(qa):
    assert {"logic.js", "viewer.js", "app.css"} <= {p.name for p in (qa / "static").iterdir()}

def test_write_site_needs_only_the_qa_dir(qa, synth_sources):
    shutil.rmtree(synth_sources[0]); shutil.rmtree(synth_sources[1])
    write_site(qa)
    assert (qa / "index.html").exists()

def test_subject_names_are_html_escaped(tmp_path):
    subj = write_subject(tmp_path / "src", name="sub-<b>x")
    qa = tmp_path / "qa"
    build_all(find_subjects([subj]), qa); write_site(qa)
    assert "<b>x" not in (qa / "index.html").read_text()

# tests/test_server.py
def test_server_serves_index_and_assets(qa):
    client = TestClient(create_app(qa))
    assert client.get("/").status_code == 200
    assert "surfaceqa" in client.get("/").text
    assert client.get("/static/logic.js").status_code == 200
    run = json.loads((qa / "subjects" / "fastsurfer__sub-01" / "current.json").read_text())["run"]
    base = f"/subjects/fastsurfer__sub-01/runs/{run}"
    assert client.get(f"{base}/meta.json").json()["key"] == "fastsurfer__sub-01"
    assert client.get(f"{base}/slices/coronal/010.jpg").headers["content-type"] == "image/jpeg"
    assert client.get(f"{base}/contours_coronal.bin").status_code == 200

def test_server_does_not_serve_outside_qa_dir(qa):
    assert TestClient(create_app(qa)).get("/../../etc/passwd").status_code in (400, 404)

# tests/test_cli.py
def test_cli_build_writes_site(synth_sources, tmp_path, capsys):
    qa = tmp_path / "qa"
    assert main(["build", *map(str, synth_sources), "--out", str(qa)]) == 0
    assert (qa / "index.html").exists()
    assert "fastsurfer__sub-01  built" in capsys.readouterr().out

def test_cli_build_default_out_is_sibling(synth_sources):
    assert main(["build", str(synth_sources[0])]) == 0
    assert (synth_sources[0].parent / "surfaceqa" / "index.html").exists()

def test_cli_build_subject_filter(synth_sources, tmp_path):
    write_subject(synth_sources[0], name="sub-02")
    qa = tmp_path / "qa"
    main(["build", str(synth_sources[0]), "--out", str(qa), "--subjects", "sub-02"])
    assert [p.name for p in (qa / "subjects").iterdir()] == ["fastsurfer__sub-02"]

def test_cli_refuses_out_inside_source(synth_sources, capsys):
    assert main(["build", str(synth_sources[0]), "--out", str(synth_sources[0] / "qa")]) == 2
    assert not (synth_sources[0] / "qa").exists()

def test_cli_build_returns_1_when_a_subject_fails(synth_sources, tmp_path):
    (synth_sources[1] / "sub-01" / "surf" / "lh.white").write_bytes(b"junk")
    assert main(["build", *map(str, synth_sources), "--out", str(tmp_path / "qa")]) == 1

def test_cli_build_no_subjects_found(tmp_path, capsys):
    (tmp_path / "empty").mkdir()
    assert main(["build", str(tmp_path / "empty"), "--out", str(tmp_path / "qa")]) == 2
    assert "no subjects found" in capsys.readouterr().err.lower()
```

(`qa` fixture moves to `conftest.py` so `test_server.py` can use it.)

- [ ] **Step 2: Run to verify failure, commit tests** (`test: pages, server, CLI`)

- [ ] **Step 3: Implement `site.py`, templates, `server.py`, `cli.py`, `viewer.js`, `app.css`**

Jinja2 with autoescape on. `app.css`: dark page background (the T1 is dark), system font, the three views share the width equally and stack vertically below 900 px.

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q` — expected: all pass.

- [ ] **Step 5: Build the three real reconstructions**

Run:
```bash
uv run surfaceqa build \
  /Volumes/extdata1/NSD/BIDS/derivatives/fastsurfer \
  /Volumes/extdata1/NSD/BIDS/derivatives/freesurfer-8.2.0 \
  /Volumes/extdata1/NSD/BIDS/derivatives/freesurfer-NSD \
  --out ~/surfaceqa-demo --jobs 3
```
Expected: `fastsurfer__sub-07  built`, `freesurfer-NSD__subj07  built`, the `freesurfer-8.2.0` subjects built or reported with their missing files, no `failed`. Note the wall time per subject and the size of each run folder in the commit message. If a subject takes more than about 3 minutes, profile `plane_segments` before going on.

- [ ] **Step 6: Check contour placement against freeview**

For `fastsurfer/sub-07`, take a coronal screenshot with the installed freeview at the slice the viewer calls coronal 160:

```bash
S=/Volumes/extdata1/NSD/BIDS/derivatives/fastsurfer/sub-07
freeview -v $S/mri/orig.mgz \
  -f $S/surf/lh.pial:edgecolor=yellow $S/surf/rh.pial:edgecolor=yellow \
     $S/surf/lh.white:edgecolor=blue $S/surf/rh.white:edgecolor=red \
  -viewport coronal -layout 1 -slice 160 160 160 -ss /tmp/fv_coronal.png -quit
```

`-slice` takes voxel indices of `orig.mgz` (LIA), so work out which grid index along A that is from `tkr_to_grid` rather than assuming 160, and open that slice in the viewer (`uv run surfaceqa serve ~/surfaceqa-demo`). Compare the two images side by side: left/right must match (radiological), the contours must cross the same sulci at the same places, pial outside white. Repeat for one sagittal and one axial slice, and once for `freesurfer-8.2.0/sub-07` (1 mm, 256^3). Any mismatch in orientation or a visible offset is a bug in Task 3 or 4: fix it there, with a new failing test first. Record what was compared and the result in the commit message.

- [ ] **Step 7: Exercise the viewer in a browser**

With the server running, check each line of the viewer behaviour list above by hand (or with a browser automation tool): scrolling each view, clicking to move the other two, zoom and pan, enlarge and restore, holding `s`, the surface checkboxes, the readouts, and the missing-files page if one exists. Fix what does not work; anything that was logic gets a test in `tests/js/logic.test.mjs` first.

- [ ] **Step 8: Commit** (`feat: pages, viewer, server, CLI`)

---

## Done when

- `uv run pytest -q` passes.
- The three real reconstructions of subject 07 open in the browser with contours that match freeview.
- Nothing was written under `/Volumes/extdata1/NSD/BIDS/derivatives/`.
