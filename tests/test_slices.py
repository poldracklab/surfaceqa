import numpy as np
from PIL import Image

from surfaceqa.planes import PLANES
from surfaceqa.slices import intensity_window, to_uint8, write_plane_slices


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
    assert img[0, 0] > 100 and img[5, 3] < 40  # bright voxel at top-left
