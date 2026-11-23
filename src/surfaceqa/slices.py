"""Turn the display volume into grayscale slice images."""

from pathlib import Path

import numpy as np
from PIL import Image

from surfaceqa.planes import Plane, slice_image

JPEG_QUALITY = 85


def intensity_window(data: np.ndarray) -> tuple[float, float]:
    """Black at 0, white at the 99.5th percentile of the non-background voxels."""
    foreground = data[data > 0]
    if foreground.size == 0:
        return (0.0, 1.0)
    return (0.0, float(np.percentile(foreground, 99.5)))


def to_uint8(img: np.ndarray, window: tuple[float, float]) -> np.ndarray:
    low, high = window
    scaled = (img.astype(float) - low) / (high - low) * 255.0
    return np.clip(np.floor(scaled + 0.5), 0, 255).astype(np.uint8)


def write_plane_slices(data: np.ndarray, plane: Plane, window: tuple[float, float],
                       out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    n_slices = data.shape[plane.axis]
    for index in range(n_slices):
        pixels = to_uint8(slice_image(data, plane, index), window)
        Image.fromarray(np.ascontiguousarray(pixels)).save(
            out_dir / f"{index:03d}.jpg", quality=JPEG_QUALITY)
    return n_slices
