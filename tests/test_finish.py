import numpy as np
import pytest

import dmd_optimizer as tool
from helpers import H, W, artwork, check_rules, draw_digits, flicker_frames, score_frames, write_dump


def finished(tmp_path, frames, **settings):
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", frames)])
    options = tool.Options(**settings)
    work = tool.Workspace(dump, options)
    regions = tool.candidate_regions(dump.frames, tool.timeline_links(dump), work.limit, W, H)
    tool.choose_masks(work, regions, options)
    tool.tighten(work, options)
    return dump, options, work, tool.finish(work, options)


def test_groups_masks_and_hashes(tmp_path):
    frames = score_frames(7, variant=0, x=8) + flicker_frames(6, variant=2) + score_frames(12, variant=1, x=48)
    dump, options, work, analysis = finished(tmp_path, frames)
    check_rules(dump, analysis, options)
    assert (analysis.limit, analysis.min_lit) == (1024, 32)
    assert [group.kept for group in analysis.groups] == [0, 7, 13]
    assert [len(group.members) for group in analysis.groups] == [7, 6, 12]
    # masks are numbered by frames saved: the twelve-frame family comes first
    assert [group.mask for group in analysis.groups] == [1, tool.NO_MASK, 0]
    assert [group.shape for group in analysis.groups] == [False, True, False]
    assert analysis.mask_saved == [11, 6]
    assert analysis.masks.shape == (2, W * H) and analysis.masks.dtype == bool
    assert analysis.collisions == []
    for group in analysis.groups:
        mask = None if group.mask == tool.NO_MASK else analysis.masks[group.mask]
        assert group.hash == tool.frame_hash(dump.frames[group.kept], mask, group.shape)


def test_masks_that_save_equally_are_numbered_by_area(tmp_path):
    wide = score_frames(7, variant=0, x=8)  # six digits change
    narrow = [draw_digits(artwork(1), f"{11 * (k + 1):02d}", 60, 22) for k in range(7)]  # two digits change
    dump, options, _, analysis = finished(tmp_path, wide + narrow)
    check_rules(dump, analysis, options)
    assert analysis.mask_saved == [6, 6]
    assert int(analysis.masks[0].sum()) < int(analysis.masks[1].sum())
    assert [group.mask for group in analysis.groups] == [1, 0]  # the narrow region is mask 0


def test_masks_that_save_equally_with_equal_areas_keep_the_order_they_were_chosen_in(tmp_path):
    frames = score_frames(7, variant=0, x=8) + score_frames(7, variant=1, x=48)
    dump, options, _, analysis = finished(tmp_path, frames)
    check_rules(dump, analysis, options)
    assert analysis.mask_saved == [6, 6]
    assert int(analysis.masks[0].sum()) == int(analysis.masks[1].sum())
    assert [group.mask for group in analysis.groups] == [0, 1]


def test_regions_that_end_up_unused_are_dropped(tmp_path):
    dump, options, work, _ = finished(tmp_path, score_frames(12))
    unused = np.zeros((H, W), bool)
    unused[2:10, 100:120] = True
    work.pool.append(work.candidate(99, unused.reshape(-1), False))
    analysis = tool.finish(work, options)
    assert len(analysis.masks) == 1
    check_rules(dump, analysis, options)


def test_no_masks_gives_an_empty_mask_array(tmp_path):
    _, _, _, analysis = finished(tmp_path, score_frames(3))
    assert analysis.masks.shape == (0, W * H) and analysis.mask_saved == []
    assert [group.mask for group in analysis.groups] == [tool.NO_MASK] * 3


def test_verification_rejects_a_frame_that_matches_two_kept_frames(tmp_path):
    dump, _, _, analysis = finished(tmp_path, score_frames(12))
    whole = analysis.groups[0]
    halves = [
        tool.Group(kept=0, members=whole.members[:6], mask=whole.mask, shape=False, varying=whole.varying),
        tool.Group(kept=6, members=whole.members[6:], mask=whole.mask, shape=False, varying=whole.varying),
    ]
    with pytest.raises(tool.OptimizerError, match="internal check failed"):
        tool.verify_groups(dump.frames, halves, analysis.masks)


def test_verification_rejects_a_frame_that_matches_no_kept_frame(tmp_path):
    dump, _, _, analysis = finished(tmp_path, score_frames(12))
    whole = analysis.groups[0]
    wrong = [tool.Group(kept=0, members=whole.members, mask=tool.NO_MASK, shape=False, varying=whole.varying)]
    with pytest.raises(tool.OptimizerError, match="frame 1 matches 0 kept frames"):
        tool.verify_groups(dump.frames, wrong, analysis.masks)


def test_crc_collisions_are_reported_not_fatal(tmp_path, monkeypatch):
    dump, _, _, analysis = finished(tmp_path, score_frames(3))
    monkeypatch.setattr(tool.zlib, "crc32", lambda data: 7)  # every frame gets the same hash
    collisions = tool.verify_groups(dump.frames, analysis.groups, analysis.masks)
    assert sorted(collisions) == [(0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1)]
    assert [group.hash for group in analysis.groups] == [7, 7, 7]
