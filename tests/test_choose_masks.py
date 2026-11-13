import dmd_optimizer as tool
from helpers import H, W, flicker_frames, score_frames, write_dump


def choose(tmp_path, frames, **settings):
    """Run steps A to C on a dump of the given frames; returns the workspace."""
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", frames)])
    options = tool.Options(**settings)
    work = tool.Workspace(dump, options)
    regions = tool.candidate_regions(dump.frames, tool.timeline_links(dump), work.limit, W, H)
    tool.choose_masks(work, regions, options)
    return work


def groups(work):
    return len(set(work.root.tolist()))


def three_screens(variants=7):
    """Three different screens, each with its own score in its own place."""
    frames = []
    for screen in range(3):
        frames += score_frames(variants, variant=screen, x=8 + 40 * screen)
    return frames


def test_a_score_screen_becomes_one_group_with_one_region(tmp_path):
    work = choose(tmp_path, score_frames(12))
    assert groups(work) == 1 and len(work.pool) == 1
    changed = (work.frames != work.frames[0]).any(axis=0)
    assert (work.pool[0].mask | ~changed).all()
    assert work.group_mask.tolist() == [0] * 12


def test_flicker_needs_no_region(tmp_path):
    work = choose(tmp_path, flicker_frames(10))
    assert groups(work) == 1 and work.pool == [] and work.group_shape.all()


def test_shape_mode_can_be_switched_off(tmp_path):
    work = choose(tmp_path, flicker_frames(10), shape_mode=False)
    assert not work.group_shape.any()
    assert True not in work.labellers


def test_a_family_below_min_gain_is_left_alone(tmp_path):
    assert groups(choose(tmp_path, score_frames(4))) == 4  # merging would save 3 frames, fewer than 5
    assert groups(choose(tmp_path, score_frames(4), min_gain=3)) == 1


def test_no_region_is_used_when_max_masks_is_zero(tmp_path):
    work = choose(tmp_path, score_frames(12) + flicker_frames(10), max_masks=0)
    assert work.pool == []
    assert groups(work) == 12 + 1


def test_three_screens_use_three_regions(tmp_path):
    work = choose(tmp_path, three_screens())
    assert groups(work) == 3 and len(work.pool) == 3


def test_the_pool_never_exceeds_max_masks(tmp_path):
    work = choose(tmp_path, three_screens(), max_masks=2)
    assert len(work.pool) == 2
    assert groups(work) == 2 + 7  # two screens merged, the third left as seven frames
    assert sorted(set(work.group_mask.tolist())) == [-1, 0, 1]


def test_the_larger_family_is_chosen_first(tmp_path):
    frames = score_frames(7, variant=0, x=8) + score_frames(12, variant=1, x=48)
    work = choose(tmp_path, frames, max_masks=1)
    assert len(work.pool) == 1
    assert groups(work) == 7 + 1  # the twelve-frame family got the only region
