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


def _affine(shape, voxel: float, orientation: str, cras) -> np.ndarray:
    affine = np.eye(4)
    affine[:3, :3] = np.array([DIRECTIONS[c] for c in orientation], dtype=float).T * voxel
    affine[:3, 3] = np.asarray(cras) - affine[:3, :3] @ (np.asarray(shape) / 2)
    return affine


def _sphere_volume(shape, affine: np.ndarray, cras) -> np.ndarray:
    idx = np.indices(shape).reshape(3, -1).T
    mm = idx @ affine[:3, :3].T + affine[:3, 3] - np.asarray(cras)
    inside = np.linalg.norm(mm, axis=1) <= 10.0
    return (inside * 110).astype(np.uint8).reshape(shape)


def _volume_info(shape, voxel: float, affine: np.ndarray, cras) -> dict:
    mdc = affine[:3, :3] / voxel
    return {
        "head": np.array([2, 0, 20], dtype=np.int32),
        "valid": "1  # volume info valid",
        "filename": "../mri/orig.mgz",
        "volume": np.array(shape),
        "voxelsize": np.array([voxel] * 3),
        "xras": mdc[:, 0], "yras": mdc[:, 1], "zras": mdc[:, 2],
        "cras": np.asarray(cras, dtype=float),
    }


def _write_logs(subj: Path, pipeline: str, omit) -> None:
    files = {"scripts/build-stamp.txt": FASTSURFER_STAMP}
    if pipeline == "fastsurfer":
        files["scripts/deep-seg.log"] = "Start of the log\nVersion: 2.6.1+a314cd4f\n"
    else:
        files = {"scripts/build-stamp.txt": FREESURFER_STAMP,
                 "scripts/recon-all.log": "recon-all finished without error\n"}
    for rel, text in files.items():
        if rel not in omit:
            (subj / rel).write_text(text)


def write_subject(root: Path, name: str = "sub-01", pipeline: str = "fastsurfer",
                  shape=(32, 40, 48), voxel: float = 1.0, orientation: str = "LIA",
                  cras=(0.0, 0.0, 0.0), omit: tuple[str, ...] = ()) -> Path:
    subj = Path(root) / name
    for sub in ("mri", "surf", "scripts"):
        (subj / sub).mkdir(parents=True, exist_ok=True)
    affine = _affine(shape, voxel, orientation, cras)
    if "mri/orig.mgz" not in omit:
        nib.save(nib.MGHImage(_sphere_volume(shape, affine, cras), affine), subj / "mri" / "orig.mgz")
    info = _volume_info(shape, voxel, affine, cras)
    for surf, radius in SURFACES.items():
        if f"surf/{surf}" not in omit:
            verts, faces = icosphere(radius)
            nib.freesurfer.write_geometry(subj / "surf" / surf, verts, faces, volume_info=info)
    _write_logs(subj, pipeline, omit)
    return subj
