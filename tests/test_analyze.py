import numpy as np

import dmd_optimizer as tool
from helpers import (
    H, W, animation_frames, bright_frames, check_rules, flicker_frames, score_frames,
    score_only_frames, two_screens, write_dump,
)


def analyzed(tmp_path, frames, **settings):
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", frames)])
    options = tool.Options(**settings)
    analysis = tool.analyze(dump, options)
    check_rules(dump, analysis, options)
    return dump, analysis


def settings_of(analysis):
    return [(len(group.members), group.mask, group.shape) for group in analysis.groups]


def test_counting_score(tmp_path):
    dump, analysis = analyzed(tmp_path, score_frames(12))
    assert settings_of(analysis) == [(12, 0, False)]
    changed = (dump.frames != dump.frames[0]).any(axis=0)
    assert (analysis.masks[0] | ~changed).all() and analysis.masks[0].sum() <= 400


def test_flickering_title(tmp_path):
    _, analysis = analyzed(tmp_path, flicker_frames(10))
    assert settings_of(analysis) == [(10, tool.NO_MASK, True)]
    assert len(analysis.masks) == 0


def test_animation_in_a_corner(tmp_path):
    dump, analysis = analyzed(tmp_path, animation_frames(8))
    assert settings_of(analysis) == [(8, 0, False)]
    corner = np.zeros((H, W), bool)
    corner[18:26, 98:122] = True
    assert not (analysis.masks[0] & ~corner.reshape(-1)).any()


def test_two_different_screens_are_both_kept(tmp_path):
    _, analysis = analyzed(tmp_path, two_screens())
    assert settings_of(analysis) == [(1, tool.NO_MASK, False)] * 2


def test_brightness_changes_beyond_the_limit_keep_frames_apart(tmp_path):
    _, analysis = analyzed(tmp_path, bright_frames())
    assert settings_of(analysis) == [(1, tool.NO_MASK, False)] * 3


def test_a_screen_blank_outside_the_varying_area_is_not_merged(tmp_path):
    _, analysis = analyzed(tmp_path, score_only_frames(7))
    assert len(analysis.groups) == 7 and len(analysis.masks) == 0


def test_all_scenarios_in_one_dump(tmp_path):
    frames = (
        score_frames(12) + two_screens()[1:] + flicker_frames(10, variant=1)
        + animation_frames(8, variant=2) + bright_frames() + score_only_frames(7)
    )
    dump, analysis = analyzed(tmp_path, frames)
    sizes = sorted(len(group.members) for group in analysis.groups)
    assert sizes == [1] * 11 + [8, 10, 12]  # 1 other screen, 3 brightness levels, 7 bare scores
    assert len(analysis.masks) == 2  # the score and the animation; the flicker needs none


def test_pool_size_limit(tmp_path):
    frames = []
    for screen in range(3):
        frames += score_frames(7, variant=screen, x=8 + 40 * screen)
    _, analysis = analyzed(tmp_path, frames, max_masks=2)
    assert len(analysis.masks) == 2
    assert sorted(len(group.members) for group in analysis.groups) == [1] * 7 + [7, 7]


def test_without_shape_mode(tmp_path):
    frames = flicker_frames(10) + score_frames(12, variant=1)
    _, analysis = analyzed(tmp_path, frames, shape_mode=False)
    # without the shape view the flicker is merged by a mask over the title instead
    assert settings_of(analysis) == [(10, 1, False), (12, 0, False)]


def test_nothing_is_merged_when_nothing_may_vary(tmp_path):
    _, analysis = analyzed(tmp_path, score_frames(12) + flicker_frames(10), max_vary=0)
    assert len(analysis.groups) == 22 and len(analysis.masks) == 0


def test_only_shape_merging_without_masks(tmp_path):
    _, analysis = analyzed(tmp_path, score_frames(12) + flicker_frames(10), max_masks=0)
    assert len(analysis.groups) == 13 and len(analysis.masks) == 0


def test_score_and_flicker_on_the_same_screen(tmp_path):
    rng = np.random.default_rng(2)
    frames = []
    for frame in score_frames(12):
        frame = frame.copy()
        frame[4:12, 90:120] = rng.integers(1, 4, size=(8, 30))
        frames.append(frame)
    _, analysis = analyzed(tmp_path, frames)
    assert settings_of(analysis) == [(12, 0, True)]


def test_frames_of_several_files(tmp_path):
    first = write_dump(tmp_path / "one.txt", score_frames(12)[:6])
    second = write_dump(tmp_path / "two.txt", score_frames(12)[6:])
    dump = tool.read_dumps([first, second])
    analysis = tool.analyze(dump)
    check_rules(dump, analysis, tool.Options())
    assert settings_of(analysis) == [(12, 0, False)]


def test_progress_messages_and_default_options(tmp_path):
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", score_frames(12))])
    messages = []
    analysis = tool.analyze(dump, progress=messages.append)
    assert analysis.options == tool.Options()
    assert messages[0] == "preparing frames" and messages[-1] == "verifying"
    assert any(message.startswith("choosing masks from ") for message in messages)


def test_the_result_does_not_depend_on_the_run(tmp_path):
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", score_frames(12) + flicker_frames(10))])
    first, second = tool.analyze(dump), tool.analyze(dump)
    assert np.array_equal(first.masks, second.masks)
    assert settings_of(first) == settings_of(second)
    assert [group.hash for group in first.groups] == [group.hash for group in second.groups]
