import numpy as np

import dmd_optimizer as tool
from helpers import H, W


def pad(points):
    pixels = np.zeros((H, W), bool)
    for x, y in points:
        pixels[y, x] = True
    return tool.pad_region(pixels.reshape(-1), W, H).reshape(H, W)


def rectangle(x0, y0, x1, y1):
    expected = np.zeros((H, W), bool)
    expected[y0:y1, x0:x1] = True
    return expected


def test_nothing_selected_gives_an_empty_region():
    assert not pad([]).any()


def test_one_pixel_becomes_a_rectangle_on_the_grid():
    # (10, 10) grows to a plus shape over x 9..11 and y 9..11, which touches cells 4..5 both ways
    assert np.array_equal(pad([(10, 10)]), rectangle(8, 8, 12, 12))


def test_corner_pixel_stays_inside_the_display():
    assert np.array_equal(pad([(0, 0)]), rectangle(0, 0, 2, 2))
    assert np.array_equal(pad([(W - 1, H - 1)]), rectangle(W - 2, H - 2, W, H))


def test_close_pixels_share_one_rectangle():
    # cells 5 and 7 are selected, one empty cell column between them: no cut
    assert np.array_equal(pad([(10, 10), (14, 10)]), rectangle(8, 8, 16, 12))


def test_distant_pixels_get_separate_rectangles():
    # cells 4..5 and 8..9 are selected, two empty cell columns between them: cut
    expected = rectangle(8, 8, 12, 12) | rectangle(16, 8, 20, 12)
    assert np.array_equal(pad([(10, 10), (18, 10)]), expected)


def test_rows_are_cut_like_columns():
    expected = rectangle(8, 8, 12, 12) | rectangle(8, 16, 12, 20)
    assert np.array_equal(pad([(10, 10), (10, 18)]), expected)


def test_an_l_shape_fills_its_bounding_rectangle():
    points = [(x, 10) for x in range(10, 30)] + [(10, y) for y in range(10, 24)]
    # grown, the lines reach x 9..30 and y 9..24, which is cells 4..15 across and 4..12 down
    assert np.array_equal(pad(points), rectangle(8, 8, 32, 26))


def test_columns_are_cut_before_rows():
    # one block on the left, two blocks stacked on the right: three rectangles
    expected = rectangle(8, 8, 12, 12) | rectangle(40, 2, 44, 6) | rectangle(40, 24, 44, 28)
    assert np.array_equal(pad([(10, 10), (42, 4), (42, 26)]), expected)


def test_result_is_aligned_to_the_two_pixel_grid():
    rng = np.random.default_rng(3)
    points = [(int(rng.integers(W)), int(rng.integers(H))) for _ in range(12)]
    cells = pad(points).reshape(H // 2, 2, W // 2, 2)
    assert (cells.all(axis=(1, 3)) == cells.any(axis=(1, 3))).all()
