"""Write small synthetic FreeSurfer-style subject folders for tests."""

from pathlib import Path

import nibabel as nib
import numpy as np

DIRECTIONS = {
    "R": (1, 0, 0), "L": (-1, 0, 0),
    "A": (0, 1, 0), "P": (0, -1, 0),
    "S": (0, 0, 1), "I": (0, 0, -1),
}
SURFACES = {"lh.white": 8.0, "rh.white": 8.0, "lh.pial": 10.0, "rh.pial": 10.0}
FASTSURFER_STAMP = (
    "freesurfer-linux-rocky8_x86_64-8.2.0-20260314-d932c45\n2.6.1+a314cd4f (stable)\n"
)
FREESURFER_STAMP = "freesurfer-linux-ubuntu24_x86_64-8.2.0-20260314-d932c45\n"


def icosphere(radius: float, subdivisions: int = 3) -> tuple[np.ndarray, np.ndarray]:
    verts, faces = _icosahedron()
    for _ in range(subdivisions):
        verts, faces = _subdivide(verts, faces)
    verts = verts / np.linalg.norm(verts, axis=1, keepdims=True) * radius
    return verts, faces


def _icosahedron() -> tuple[np.ndarray, np.ndarray]:
    t = (1 + 5**0.5) / 2
    verts = np.array(
        [[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0],
         [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
         [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]], dtype=float)
    faces = np.array(
        [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11],
         [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
         [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
         [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1]])
    return verts, faces


def _subdivide(verts: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    verts = [tuple(v) for v in verts]
    cache: dict[tuple[int, int], int] = {}

    def midpoint(a: int, b: int) -> int:
        key = (min(a, b), max(a, b))
        if key not in cache:
            mid = (np.array(verts[a]) + np.array(verts[b])) / 2
            verts.append(tuple(mid / np.linalg.norm(mid)))
            cache[key] = len(verts) - 1
        return cache[key]

    new_faces = []
    for a, b, c in faces:
        ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
        new_faces += [[a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]]
    return np.array(verts), np.array(new_faces)


def _voxel_sizes(voxel) -> np.ndarray:
    return np.broadcast_to(np.asarray(voxel, dtype=float), (3,)).copy()


def _affine(shape, voxel, orientation: str, cras) -> np.ndarray:
    affine = np.eye(4)
    affine[:3, :3] = np.array([DIRECTIONS[c] for c in orientation], dtype=float).T * _voxel_sizes(voxel)
    affine[:3, 3] = np.asarray(cras) - affine[:3, :3] @ (np.asarray(shape) / 2)
    return affine


def _sphere_volume(shape, affine: np.ndarray, centre) -> np.ndarray:
    """A ball at `centre` in tkr RAS, the space FreeSurfer surfaces are written in.

    FreeSurfer defines tkr RAS from the voxel grid alone (as if the volume were
    coronal, LIA), so for other orientations it is not scanner RAS minus c_ras.
    """
    tkr = nib.MGHImage(np.zeros(shape, dtype=np.uint8), affine).header.get_vox2ras_tkr()
    idx = np.indices(shape).reshape(3, -1).T
    mm = idx @ tkr[:3, :3].T + tkr[:3, 3] - np.asarray(centre)
    inside = np.linalg.norm(mm, axis=1) <= 10.0
    return (inside * 110).astype(np.uint8).reshape(shape)


def _volume_info(shape, voxel, affine: np.ndarray, cras) -> dict:
    mdc = affine[:3, :3] / _voxel_sizes(voxel)
    return {
        "head": np.array([2, 0, 20], dtype=np.int32),
        "valid": "1  # volume info valid",
        "filename": "../mri/orig.mgz",
        "volume": np.array(shape),
        "voxelsize": _voxel_sizes(voxel),
        "xras": mdc[:, 0], "yras": mdc[:, 1], "zras": mdc[:, 2],
        "cras": np.asarray(cras, dtype=float),
    }


DEFAULT = object()  # write the pipeline's usual command line into the log
FASTSURFER_COMMAND = ("/fastsurfer/run_fastsurfer.sh --fs_license /fastsurfer/my_mri_data/license.txt "
                      "--t1 /fastsurfer/my_mri_data/anat_avg/sub-01_T1w_avg.nii.gz --sid sub-01 "
                      "--sd /outputs --3T --threads 8")
FREESURFER_COMMAND = ("/usr/local/freesurfer/8.2.0/bin/recon-all -subjid sub-01 -i a.nii.gz -i b.nii.gz "
                      "-T2 t2.mgz -T2pial -3T -all -parallel -openmp 8")
DEFAULT_COMMAND = {"fastsurfer": FASTSURFER_COMMAND, "freesurfer": FREESURFER_COMMAND}


def fastsurfer_log(command: str | None) -> str:
    call = f"Invocation: {command}\n" if command else ""
    return f"Start of the log\nVersion: 2.6.1+a314cd4f\n{call}Reading the image\n"


def recon_all_log(command: str | None) -> str:
    """One invocation as recon-all writes it: date, cd, setenv, the command, then the run."""
    call = f"{command}\n" if command else ""
    return ("Wed Sep 16 09:33:45 PDT 2026\n/data/freesurfer/sub-01\n"
            f"setenv SUBJECTS_DIR /data/freesurfer\n{call}subjid sub-01\n"
            "recon-all finished without error\n")


def _write_logs(subj: Path, pipeline: str, omit, command) -> None:
    command = DEFAULT_COMMAND.get(pipeline) if command is DEFAULT else command
    files = {"scripts/build-stamp.txt": FASTSURFER_STAMP}
    if pipeline == "fastsurfer":
        files["scripts/deep-seg.log"] = fastsurfer_log(command)
    else:
        files = {"scripts/build-stamp.txt": FREESURFER_STAMP,
                 "scripts/recon-all.log": recon_all_log(command)}
    for rel, text in files.items():
        if rel not in omit:
            (subj / rel).write_text(text)


def write_subject(root: Path, name: str = "sub-01", pipeline: str = "fastsurfer",
                  shape=(32, 40, 48), voxel=1.0, orientation: str = "LIA",
                  cras=(0.0, 0.0, 0.0), omit: tuple[str, ...] = (),
                  centre=(0.0, 0.0, 0.0), command=DEFAULT) -> Path:
    """`voxel` is one size or three (file axis order); `centre` is the ball's tkr RAS position."""
    subj = Path(root) / name
    for sub in ("mri", "surf", "scripts"):
        (subj / sub).mkdir(parents=True, exist_ok=True)
    affine = _affine(shape, voxel, orientation, cras)
    if "mri/orig.mgz" not in omit:
        nib.save(nib.MGHImage(_sphere_volume(shape, affine, centre), affine), subj / "mri" / "orig.mgz")
    info = _volume_info(shape, voxel, affine, cras)
    for surf, radius in SURFACES.items():
        if f"surf/{surf}" not in omit:
            verts, faces = icosphere(radius)
            verts = verts + np.asarray(centre)
            nib.freesurfer.write_geometry(subj / "surf" / surf, verts, faces, volume_info=info)
    _write_logs(subj, pipeline, omit, command)
    return subj


# ---- extra files read by the indicators ---------------------------------------------------

SEG_NAME = {"fastsurfer": "aparc.DKTatlas+aseg.deep.mgz", "freesurfer": "aseg.presurf.mgz"}


def _tkr_coords(img) -> np.ndarray:
    """tkr RAS position of every voxel, shape (*volume shape, 3)."""
    tkr = img.header.get_vox2ras_tkr()
    idx = np.indices(img.shape).reshape(3, -1).T
    return (idx @ tkr[:3, :3].T + tkr[:3, 3]).reshape(*img.shape, 3)


def _tissue(coords: np.ndarray, cortex_left: int, cortex_right: int) -> np.ndarray:
    r = np.linalg.norm(coords, axis=-1)
    left = coords[..., 0] < 0
    labels = np.zeros(r.shape, dtype=np.int32)
    labels[r < 8] = np.where(left, 2, 41)[r < 8]
    shell = (r >= 8) & (r < 10)
    labels[shell] = np.where(left, cortex_left, cortex_right)[shell]
    return labels


def _plant_ribbon_blob(ribbon: np.ndarray, coords: np.ndarray, centre, radius: float) -> None:
    blob = (np.linalg.norm(coords - np.asarray(centre), axis=-1) <= radius) & (ribbon == 0)
    ribbon[blob] = np.where(coords[..., 0] < 0, 3, 42)[blob]


def _plant_seg_blob(seg: np.ndarray, ribbon: np.ndarray, coords: np.ndarray, centre, radius: float) -> None:
    blob = (np.linalg.norm(coords - np.asarray(centre), axis=-1) <= radius) & (ribbon == 0)
    seg[blob] = np.where(coords[..., 0] < 0, 3, 42)[blob]


def _save_like(img, data: np.ndarray, path: Path) -> None:
    nib.save(nib.MGHImage(data, img.affine), path)


def _write_label(path: Path, vertices: np.ndarray, members=None) -> None:
    members = range(len(vertices)) if members is None else members
    lines = ["#!ascii label, from subject synth", str(len(members))]
    lines += ["{} {:.3f} {:.3f} {:.3f} 0.0".format(i, *vertices[i]) for i in members]
    path.write_text("\n".join(lines) + "\n")


def _near(verts: np.ndarray, planted, hemi: str) -> np.ndarray:
    """Which vertices a planted (hemi, centre, radius, ...) entry covers."""
    if not planted or planted[0] != hemi:
        return np.zeros(len(verts), dtype=bool)
    return np.linalg.norm(verts - np.asarray(planted[1]), axis=1) <= planted[2]


def _write_sphere_reg(subj: Path, hemi: str, verts: np.ndarray, faces: np.ndarray) -> None:
    """The ball's own shape, blown up to radius 100: every synthetic subject is registered."""
    centred = verts - verts.mean(axis=0)
    sphere = centred / np.linalg.norm(centred, axis=1, keepdims=True) * 100.0
    nib.freesurfer.write_geometry(subj / "surf" / f"{hemi}.sphere.reg", sphere, faces)


def _write_surface_measures(subj: Path, plant: dict, sphere_reg: bool) -> None:
    (subj / "label").mkdir(exist_ok=True)
    for hemi in ("lh", "rh"):
        verts, faces = nib.freesurfer.read_geometry(subj / "surf" / f"{hemi}.pial")
        thickness = np.full(len(verts), plant.get("thickness", 2.0), dtype=np.float32)
        patch = plant.get("thick_patch")
        thickness[_near(verts, patch, hemi)] = patch[3] if patch and len(patch) > 3 else 5.0
        nib.freesurfer.write_morph_data(subj / "surf" / f"{hemi}.thickness", thickness)
        in_cortex = np.flatnonzero(~_near(verts, plant.get("not_cortex"), hemi))
        _write_label(subj / "label" / f"{hemi}.cortex.label", verts, in_cortex)
        if sphere_reg:
            _write_sphere_reg(subj, hemi, verts, faces)


def write_qa_files(subj: Path, pipeline: str = "fastsurfer", plant: dict | None = None,
                   sphere_reg: bool = True) -> None:
    """Ribbon, segmentation, parcellation, norm, thickness and cortex labels for the synthetic ball.

    plant: {"ribbon_blob": (centre tkr mm, radius mm)} adds cortex to the ribbon that the
    segmentation does not have; {"thick_patch": (hemi, centre tkr mm, radius mm)} sets
    thickness 5.0 (or a fourth entry) on the pial vertices within the radius; {"thickness": mm}
    sets it everywhere else; {"not_cortex": (hemi, centre, radius)} leaves vertices out of the
    cortex label. `sphere_reg` writes the registration spheres.
    """
    plant = plant or {}
    mri = subj / "mri"
    img = nib.load(mri / "orig.mgz")
    coords = _tkr_coords(img)
    ribbon = _tissue(coords, 3, 42)
    parcels = _tissue(coords, 1028, 2028)
    if "ribbon_blob" in plant:
        _plant_ribbon_blob(ribbon, coords, *plant["ribbon_blob"])
    _save_like(img, ribbon.astype(np.uint8), mri / "ribbon.mgz")
    _save_like(img, np.isin(ribbon, (2, 3)).astype(np.uint8), mri / "lh.ribbon.mgz")
    _save_like(img, np.isin(ribbon, (41, 42)).astype(np.uint8), mri / "rh.ribbon.mgz")
    seg = parcels.copy() if pipeline == "fastsurfer" else _tissue(coords, 3, 42)
    if "seg_blob" in plant:  # cortex in the segmentation where the ribbon has none
        _plant_seg_blob(seg, ribbon, coords, *plant["seg_blob"])
    _save_like(img, seg, mri / SEG_NAME[pipeline])
    _save_like(img, parcels, mri / "aparc.DKTatlas+aseg.mgz")
    norm = np.select([np.isin(parcels, (2, 41)), parcels > 0], [110, 70], 0).astype(np.uint8)
    _save_like(img, norm, mri / "norm.mgz")
    _write_surface_measures(subj, plant, sphere_reg)
