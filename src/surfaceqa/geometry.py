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


def load_display_volume(path: Path) -> DisplayVolume:
    img = nib.load(path)
    transform = ornt.ornt_transform(ornt.io_orientation(img.affine), RAS)
    data = ornt.apply_orientation(np.asarray(img.dataobj), transform)
    grid_to_tkr = img.header.get_vox2ras_tkr() @ ornt.inv_ornt_aff(transform, img.shape)
    sizes = np.linalg.norm(grid_to_tkr[:3, :3], axis=0)
    return DisplayVolume(data, np.linalg.inv(grid_to_tkr), tuple(float(s) for s in sizes))


def to_grid(vertices_tkr: np.ndarray, tkr_to_grid: np.ndarray) -> np.ndarray:
    return vertices_tkr @ tkr_to_grid[:3, :3].T + tkr_to_grid[:3, 3]
