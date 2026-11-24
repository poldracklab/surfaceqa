"""The display grid: a volume reoriented to Right, Anterior, Superior axes."""

from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np
from nibabel import orientations as ornt

RAS = ornt.axcodes2ornt(("R", "A", "S"))


@dataclass(frozen=True)
class DisplayVolume:
    data: np.ndarray
    tkr_to_grid: np.ndarray
    voxel_sizes: tuple[float, float, float]
    grid_to_scanner: np.ndarray  # display grid index -> scanner RAS, in mm


def load_display_volume(path: Path) -> DisplayVolume:
    img = nib.load(path)
    transform = ornt.ornt_transform(ornt.io_orientation(img.affine), RAS)
    data = ornt.apply_orientation(np.asarray(img.dataobj), transform)
    grid_to_file = ornt.inv_ornt_aff(transform, img.shape)
    grid_to_tkr = img.header.get_vox2ras_tkr() @ grid_to_file
    sizes = np.linalg.norm(grid_to_tkr[:3, :3], axis=0)
    return DisplayVolume(data, np.linalg.inv(grid_to_tkr), tuple(float(s) for s in sizes),
                         img.affine @ grid_to_file)


def to_grid(vertices_tkr: np.ndarray, tkr_to_grid: np.ndarray) -> np.ndarray:
    return vertices_tkr @ tkr_to_grid[:3, :3].T + tkr_to_grid[:3, 3]


def to_tkr(points_grid: np.ndarray, grid_to_tkr: np.ndarray) -> np.ndarray:
    return points_grid @ grid_to_tkr[:3, :3].T + grid_to_tkr[:3, 3]
