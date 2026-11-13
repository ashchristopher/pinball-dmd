import numpy as np

import dmd_optimizer as tool
from helpers import H, W, flicker_frames, score_frames, write_dump


def rectangle(x0, y0, x1, y1):
    mask = np.zeros((H, W), bool)
    mask[y0:y1, x0:x1] = True
    return mask.reshape(-1)


SMALL = rectangle(38, 20, 66, 30)  # the score drawn by score_frames
LARGE = rectangle(30, 18, 100, 32)  # contains SMALL


def workspace(tmp_path, frames, **settings):
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", frames)])
    options = tool.Options(**settings)
    return tool.Workspace(dump, options), options


def merge(work, candidate):
    labels, good, _ = work.mergeable(candidate)
    work.apply(candidate, labels, good)


def test_a_group_moves_to_the_smallest_region_that_still_merges_it(tmp_path):
    # screen 0 changes only inside SMALL; screen 1 also changes elsewhere inside LARGE
    wide = []
    for frame in score_frames(6, variant=1):
        frame = frame.copy()
        frame[24:28, 80:90] = frame[22:26, 40:50]
        wide.append(frame)
    work, options = workspace(tmp_path, score_frames(6) + wide)
    merge(work, work.candidate(0, LARGE, True))  # both screens merge under the large region
    merge(work, work.candidate(1, SMALL, False))  # nothing to merge: every frame is in a LARGE group
    assert work.group_mask.tolist() == [0] * 12 and len(work.pool) == 1
    work.pool.append(work.candidate(1, SMALL, False))  # make the small region available to step D
    tool.tighten(work, options)
    assert work.group_mask.tolist() == [1] * 6 + [0] * 6
    assert not work.group_shape.any()  # the value view is enough for both groups


def test_of_two_regions_with_the_same_area_the_earlier_one_in_the_pool_wins(tmp_path):
    left = rectangle(36, 20, 64, 30)  # both cover the score, and both have 280 pixels
    right = SMALL
    assert int(left.sum()) == int(right.sum()) == 280
    for first, second in ((left, right), (right, left)):
        work, options = workspace(tmp_path, score_frames(6))
        merge(work, work.candidate(0, LARGE, False))
        work.pool.append(work.candidate(1, first, False))
        work.pool.append(work.candidate(2, second, False))
        tool.tighten(work, options)
        assert work.group_mask.tolist() == [1] * 6


def test_a_flicker_group_keeps_no_mask_and_the_shape_view(tmp_path):
    work, options = workspace(tmp_path, flicker_frames(8))
    merge(work, tool.Candidate(region=-1, mask=None, cells=None, blocks=None, area=0, shape=True))
    tool.tighten(work, options)
    assert work.group_mask.tolist() == [-1] * 8 and work.group_shape.all()


def test_a_masked_shape_group_loses_the_mask_when_the_shapes_are_equal(tmp_path):
    work, options = workspace(tmp_path, flicker_frames(8))
    merge(work, work.candidate(0, rectangle(56, 18, 104, 30), True))
    assert work.group_mask.tolist() == [0] * 8
    tool.tighten(work, options)
    assert work.group_mask.tolist() == [-1] * 8 and work.group_shape.all()


def test_single_frames_are_untouched(tmp_path):
    work, options = workspace(tmp_path, score_frames(3))
    tool.tighten(work, options)
    assert work.group_mask.tolist() == [-1] * 3 and not work.group_shape.any()


def test_without_shape_mode_only_value_settings_are_tried(tmp_path):
    work, options = workspace(tmp_path, score_frames(6), shape_mode=False)
    merge(work, work.candidate(0, LARGE, False))
    work.pool.append(work.candidate(1, SMALL, False))
    tool.tighten(work, options)
    assert work.group_mask.tolist() == [1] * 6 and not work.group_shape.any()
