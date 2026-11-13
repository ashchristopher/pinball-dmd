import numpy as np
import pytest

import dmd_optimizer as tool
from helpers import H, W


def brute_labels(view, mask):
    keep = ~mask
    return [tuple(row[keep]) for row in view]


def same_partition(labels, keys):
    pairs = set(zip(labels.tolist(), keys))
    return len(pairs) == len(set(labels.tolist())) == len(set(keys))


def test_labels_group_frames_that_are_equal_outside_the_mask():
    rng = np.random.default_rng(5)
    base = rng.integers(0, 4, size=(6, H, W), dtype=np.uint8)
    frames = np.concatenate([base, base, base])  # 18 frames: every base frame three times
    frames[6:12, 8:16, 20:60] = rng.integers(0, 4, size=(6, 8, 40))  # differ inside the mask only
    frames[12:18, 2, 3] = (frames[12:18, 2, 3] + 1) % 4  # differ outside the mask
    view = frames.reshape(18, -1)
    mask = np.zeros((H, W), bool)
    mask[8:16, 20:60] = True
    mask = mask.reshape(-1)
    labeller = tool.Labeller(view, W, H)
    labels = labeller.labels(tool.mask_blocks(mask, W, H))
    assert same_partition(labels, brute_labels(view, mask))
    assert len(set(labels.tolist())) == 12
    plain = labeller.labels()
    assert same_partition(plain, brute_labels(view, np.zeros(W * H, bool)))
    assert same_partition(labeller.labels([]), brute_labels(view, np.zeros(W * H, bool)))


def test_several_rectangles():
    rng = np.random.default_rng(6)
    frames = np.repeat(rng.integers(0, 4, size=(1, H, W), dtype=np.uint8), 4, axis=0)
    frames[1, 0:4, 0:6] = 3 - frames[0, 0:4, 0:6]
    frames[2, 20:30, 100:128] = 3 - frames[0, 20:30, 100:128]
    frames[3, 10, 50] = 3 - frames[0, 10, 50]
    mask = np.zeros((H, W), bool)
    mask[0:4, 0:6] = True
    mask[20:30, 100:128] = True
    mask = mask.reshape(-1)
    blocks = tool.mask_blocks(mask, W, H)
    assert sorted(blocks) == [(0, 2, 0, 3), (10, 15, 50, 64)]
    labels = tool.Labeller(frames.reshape(4, -1), W, H).labels(blocks)
    assert labels[0] == labels[1] == labels[2] != labels[3]


def test_mask_cells():
    mask = np.zeros((H, W), bool)
    mask[2:4, 6:10] = True
    assert tool.mask_cells(mask.reshape(-1), W, H).tolist() == [1 * 64 + 3, 1 * 64 + 4]


def test_mask_blocks_rejects_a_mask_that_is_not_made_of_filled_rectangles():
    mask = np.zeros((H, W), bool)
    mask[0:8, 0:4] = True
    mask[0:4, 0:12] = True  # an L shape
    with pytest.raises(ValueError):
        tool.mask_blocks(mask.reshape(-1), W, H)
