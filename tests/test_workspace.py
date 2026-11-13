import numpy as np

import dmd_optimizer as tool
from helpers import H, W, bright_frames, flicker_frames, score_frames, score_only_frames, write_dump


def workspace(tmp_path, frames, **options):
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", frames)])
    return tool.Workspace(dump, tool.Options(**options))


def rectangle(x0, y0, x1, y1):
    mask = np.zeros((H, W), bool)
    mask[y0:y1, x0:x1] = True
    return mask.reshape(-1)


def no_mask_shape():
    return tool.Candidate(region=-1, mask=None, cells=None, blocks=None, area=0, shape=True)


SCORE = rectangle(38, 20, 66, 30)  # covers the six score digits drawn by score_frames


def test_varying_batches_give_the_same_answer_for_any_batch_size(monkeypatch):
    rng = np.random.default_rng(4)
    frames = rng.integers(0, 4, size=(40, 30), dtype=np.uint8)
    frames[10:20] = frames[10]  # a run of identical frames
    order = rng.permutation(40)
    starts = np.array([0, 1, 4, 5, 17, 30, 39])  # runs of 1, 3, 1, 12, 13, 9 and 1 frames
    ends = list(starts[1:]) + [40]
    expected = np.array([(frames[order[a:b]] != frames[order[a]]).any(axis=0) for a, b in zip(starts, ends)])
    for size in (1, 2, 5, 13, 14, 1000):
        monkeypatch.setattr(tool, "BATCH_FRAMES", size)
        result = np.zeros_like(expected)
        seen = []
        for first, differ in tool.varying_batches(frames, order, starts):
            result[first:first + len(differ)] = differ
            seen.extend(range(first, first + len(differ)))
        assert seen == list(range(7)), size  # every run exactly once, in order
        assert np.array_equal(result, expected), size


def test_flicker_is_merged_by_the_shape_view_without_a_mask(tmp_path):
    work = workspace(tmp_path, flicker_frames(10))
    candidate = no_mask_shape()
    labels, good, gain = work.mergeable(candidate)
    assert gain == 9
    work.apply(candidate, labels, good)
    assert work.root.tolist() == [0] * 10
    assert work.group_mask.tolist() == [-1] * 10 and work.group_shape.all()
    assert work.pool == []


def test_brightness_changes_beyond_the_limit_are_not_merged(tmp_path):
    work = workspace(tmp_path, bright_frames())
    assert work.mergeable(no_mask_shape())[2] == 0
    assert workspace(tmp_path, bright_frames(), max_vary=50).mergeable(no_mask_shape())[2] == 2


def test_a_region_merges_frames_that_differ_inside_it(tmp_path):
    work = workspace(tmp_path, score_frames(8))
    candidate = work.candidate(0, SCORE, False)
    assert candidate.area == 280 and candidate.blocks == [(10, 15, 19, 33)]
    labels, good, gain = work.mergeable(candidate)
    assert gain == 7
    work.apply(candidate, labels, good)
    assert work.root.tolist() == [0] * 8
    assert work.group_mask.tolist() == [0] * 8 and not work.group_shape.any()
    assert len(work.pool) == 1 and work.pool_of_region == {0: 0}
    assert work.mergeable(candidate)[2] == 0  # nothing left to merge


def test_a_region_too_small_for_the_change_merges_nothing(tmp_path):
    work = workspace(tmp_path, score_frames(8))
    assert work.mergeable(work.candidate(0, rectangle(38, 20, 50, 30), False))[2] == 0


def test_frames_with_nothing_lit_outside_the_region_are_not_merged(tmp_path):
    frames = score_only_frames(7)
    region = rectangle(38, 10, 66, 20)
    strict = workspace(tmp_path, frames)
    assert strict.mergeable(strict.candidate(0, region, False))[2] == 0
    relaxed = workspace(tmp_path, frames, min_lit=0)
    assert relaxed.mergeable(relaxed.candidate(0, region, False))[2] == 6


def test_a_group_blocks_a_region_that_does_not_contain_its_mask(tmp_path):
    first, second = score_frames(2)
    third = first.copy()
    third[6:10, 100:110] = 3  # differs from the first frame only in another place
    work = workspace(tmp_path, [first, second, third])
    score = work.candidate(0, SCORE, False)
    labels, good, gain = work.mergeable(score)
    assert gain == 1
    work.apply(score, labels, good)  # frames 0 and 1 now form a group that uses the score region
    other = work.candidate(1, rectangle(98, 4, 112, 12), False)
    assert work.mergeable(other)[2] == 0  # frame 0 belongs to a group whose mask is not inside it
    both = work.candidate(2, SCORE | rectangle(98, 4, 112, 12), False)
    labels, good, gain = work.mergeable(both)
    assert gain == 1  # the group {0, 1} and frame 2
    work.apply(both, labels, good)
    assert work.root.tolist() == [0, 0, 0] and work.group_mask.tolist() == [1, 1, 1]


def test_a_value_view_region_cannot_absorb_a_shape_view_group(tmp_path):
    frames = flicker_frames(6)
    changed = frames[0].copy()
    changed[6:10, 100:110] = 3
    work = workspace(tmp_path, frames + [changed])
    candidate = no_mask_shape()
    labels, good, _ = work.mergeable(candidate)
    work.apply(candidate, labels, good)  # the six flicker frames form a shape-view group
    region = rectangle(98, 4, 112, 12)
    assert work.mergeable(work.candidate(0, region, False))[2] == 0
    assert work.mergeable(work.candidate(0, region, True))[2] == 1
