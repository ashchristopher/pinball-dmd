import numpy as np

import dmd_optimizer as tool


def test_crc32_is_the_standard_one():
    # 0xCBF43926 is the published CRC-32 check value for the ASCII text "123456789"
    pixels = np.frombuffer(b"123456789", np.uint8)
    assert tool.frame_hash(pixels) == 0xCBF43926


def test_masked_pixels_are_skipped():
    pixels = np.array([0, 1, 2, 3, 3, 2, 1, 0], np.uint8)
    mask = np.array([0, 0, 1, 1, 0, 0, 1, 0], np.uint8)
    assert tool.frame_hash(pixels, mask) == tool.frame_hash(np.array([0, 1, 3, 2, 0], np.uint8))


def test_shape_mode_counts_every_lit_pixel_as_one():
    pixels = np.array([0, 1, 2, 3, 15], np.uint8)
    assert tool.frame_hash(pixels, shape=True) == tool.frame_hash(np.array([0, 1, 1, 1, 1], np.uint8))
    assert tool.frame_hash(pixels, shape=True) != tool.frame_hash(pixels)


def test_everything_masked_hashes_to_zero():
    assert tool.frame_hash(np.array([1, 2, 3], np.uint8), np.ones(3, np.uint8)) == 0


def test_frame_hashes_matches_frame_hash_row_by_row():
    frames = np.random.default_rng(0).integers(0, 4, size=(5, 64), dtype=np.uint8)
    mask = np.zeros(64, bool)
    mask[10:30] = True
    for shape in (False, True):
        hashes = tool.frame_hashes(frames, mask, shape)
        assert hashes.dtype == np.uint32
        assert hashes.tolist() == [tool.frame_hash(row, mask, shape) for row in frames]
    assert tool.frame_hashes(frames).tolist() == [tool.frame_hash(row) for row in frames]
