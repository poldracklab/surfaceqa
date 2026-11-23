import numpy as np

from surfaceqa.planes import PLANES, slice_image, to_screen


def test_planes_table():
    c = PLANES["coronal"]
    assert (c.axis, c.h_axis, c.v_axis, c.h_flip, c.v_flip) == (1, 0, 2, True, True)
    assert PLANES["sagittal"].edges == {"left": "P", "right": "A", "top": "S", "bottom": "I"}
    assert PLANES["axial"].edges == {"left": "R", "right": "L", "top": "A", "bottom": "P"}


def test_slice_image_orientation():
    data = np.zeros((4, 5, 6), dtype=np.uint8)
    data[3, 2, 5] = 9  # far right, mid, most superior
    img = slice_image(data, PLANES["coronal"], 2)
    assert img.shape == (6, 4)  # rows = S axis, cols = R axis
    assert img[0, 0] == 9  # right is screen-left, superior is top


def test_to_screen_matches_slice_image():
    data = np.zeros((4, 5, 6), dtype=np.uint8)
    data[3, 2, 5] = 9
    x, y = to_screen(np.array([3.0]), np.array([5.0]), PLANES["coronal"], data.shape)
    assert (x[0], y[0]) == (0.0, 0.0)
