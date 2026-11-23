"""The three viewing planes of the display grid and their screen layout."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Plane:
    name: str
    axis: int
    h_axis: int
    v_axis: int
    h_flip: bool
    v_flip: bool
    edges: dict[str, str]


def _edges(left: str, right: str, top: str, bottom: str) -> dict[str, str]:
    return {"left": left, "right": right, "top": top, "bottom": bottom}


PLANES = {
    "sagittal": Plane("sagittal", 0, 1, 2, False, True, _edges("P", "A", "S", "I")),
    "coronal": Plane("coronal", 1, 0, 2, True, True, _edges("R", "L", "S", "I")),
    "axial": Plane("axial", 2, 0, 1, True, True, _edges("R", "L", "A", "P")),
}


def slice_image(data: np.ndarray, plane: Plane, index: int) -> np.ndarray:
    """The slice in screen orientation: row 0 at the top, column 0 at the left."""
    img = np.take(data, index, axis=plane.axis)  # remaining axes keep their order
    if plane.h_axis > plane.v_axis:
        img = img.T
    img = img.T  # rows = v axis, columns = h axis
    if plane.h_flip:
        img = img[:, ::-1]
    if plane.v_flip:
        img = img[::-1, :]
    return img


def _flip(coord: np.ndarray, size: int, flip: bool) -> np.ndarray:
    return (size - 1 - coord) if flip else coord


def to_screen(h: np.ndarray, v: np.ndarray, plane: Plane,
              shape: tuple[int, int, int]) -> tuple[np.ndarray, np.ndarray]:
    x = _flip(h, shape[plane.h_axis], plane.h_flip)
    y = _flip(v, shape[plane.v_axis], plane.v_flip)
    return x, y
