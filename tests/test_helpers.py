"""The test helpers decide whether results are right, so they are tested too."""
import copy
import types
import zlib

import numpy as np
import pytest

import dmd_optimizer as tool
from helpers import artwork, check_rules, flicker_frames, hand_labels, score_frames, write_dump


@pytest.fixture
def result(tmp_path):
    frames = score_frames(12) + flicker_frames(10, variant=1) + [artwork(2)]
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", frames)])
    return dump, tool.analyze(dump)


def test_a_correct_result_passes(result):
    check_rules(*result, tool.Options())


def test_a_group_split_in_two_is_rejected(result):
    dump, analysis = result
    whole = analysis.groups[0]
    halves = []
    for members in (whole.members[:6], whole.members[6:]):
        half = copy.copy(whole)
        half.kept, half.members = int(members[0]), members
        half.varying = (dump.frames[members] != dump.frames[members[0]]).any(axis=0)
        half.hash = tool.frame_hash(dump.frames[members[0]], analysis.masks[whole.mask])
        halves.append(half)
    analysis.groups[0:1] = halves
    with pytest.raises(AssertionError, match="R1"):
        check_rules(dump, analysis, tool.Options())


def test_a_view_looser_than_needed_is_rejected(result):
    dump, analysis = result
    group = analysis.groups[0]
    group.shape = True
    kept = dump.frames[group.kept][~analysis.masks[group.mask]]
    group.hash = zlib.crc32(np.minimum(kept, 1).tobytes())
    with pytest.raises(AssertionError, match="R5"):
        check_rules(dump, analysis, tool.Options())


def test_limits_are_enforced(result):
    dump, analysis = result
    with pytest.raises(AssertionError, match="R2 or R3"):
        check_rules(dump, analysis, tool.Options(max_vary=2))  # the score mask covers more than 2%
    with pytest.raises(AssertionError, match="R2 or R3"):
        check_rules(dump, analysis, tool.Options(min_lit=4000))
    with pytest.raises(AssertionError, match="R4"):
        check_rules(dump, analysis, tool.Options(max_masks=0))
    with pytest.raises(AssertionError, match="shape view used although it is disabled"):
        check_rules(dump, analysis, tool.Options(shape_mode=False))


def test_wrong_order_and_missing_frames_are_rejected(result):
    dump, analysis = result
    backwards = copy.copy(analysis)
    backwards.groups = analysis.groups[::-1]
    with pytest.raises(AssertionError, match="R6"):
        check_rules(dump, backwards, tool.Options())
    short = copy.copy(analysis)
    short.groups = analysis.groups[:-1]
    with pytest.raises(AssertionError, match="a frame is in no group or in several"):
        check_rules(dump, short, tool.Options())


def test_a_wrong_hash_is_rejected(result):
    dump, analysis = result
    analysis.groups[2].hash ^= 1
    with pytest.raises(AssertionError, match="hash"):
        check_rules(dump, analysis, tool.Options())


def test_hand_labels_pick_the_lowest_project_frame_that_matches_exactly():
    mask = np.array([0, 0, 0, 0, 1, 1, 1, 1], np.uint8)
    originals = np.array([
        [1, 2, 3, 0, 9, 9, 9, 9],  # frame 0: mask 0, value view
        [3, 3, 0, 0, 1, 1, 0, 0],  # frame 1: no mask, value view
        [3, 3, 0, 0, 1, 1, 0, 0],  # frame 2: a duplicate of frame 1
        [2, 0, 2, 0, 2, 0, 2, 0],  # frame 3: no mask, shape view
    ], np.uint8)
    project = types.SimpleNamespace(
        crom={"CompMaskID": np.array([0, 255, 255, 255], np.uint8),
              "ShapeCompMode": np.array([0, 0, 0, 1], np.uint8),
              "CompMasks": mask},
        crp={"oFrames": originals.reshape(-1)},
    )
    frames = np.array([
        [1, 2, 3, 0, 0, 1, 2, 3],  # equal to frame 0 outside the mask
        [3, 3, 0, 0, 1, 1, 0, 0],  # equal to frames 1 and 2: the lower number wins
        [1, 0, 3, 0, 1, 0, 3, 0],  # the lit shape of frame 3
        [1, 2, 3, 1, 9, 9, 9, 9],  # differs from frame 0 outside the mask
        [0, 0, 0, 0, 0, 0, 0, 0],  # matches nothing
    ], np.uint8)
    assert hand_labels(frames, project).tolist() == [0, 1, 3, -1, -1]
