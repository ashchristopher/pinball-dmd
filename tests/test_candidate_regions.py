import numpy as np

import dmd_optimizer as tool
from helpers import H, W, artwork, flicker_frames, score_frames, two_screens

LIMIT = 1024


def regions_of(frames, limit=LIMIT):
    view = np.stack(frames).reshape(len(frames), -1)
    links = np.array([[k, k + 1] for k in range(len(frames) - 1)], np.int64).reshape(-1, 2)
    return view, tool.candidate_regions(view, links, limit, W, H)


def test_a_changing_score_gives_regions_that_grow_to_cover_it():
    view, regions = regions_of(score_frames(12))
    assert regions, "no region found"
    changed = (view != view[0]).any(axis=0)
    assert (regions[-1] | ~changed).all(), "the last region does not cover every changed pixel"
    assert all(int(region.sum()) <= LIMIT for region in regions)
    assert all(region.dtype == bool and region.shape == (W * H,) for region in regions)
    assert len({region.tobytes() for region in regions}) == len(regions), "duplicate regions"


def test_regions_are_padded():
    _, regions = regions_of(score_frames(12))
    for region in regions:
        assert np.array_equal(tool.pad_region(region, W, H) & region, region)
        cells = region.reshape(H // 2, 2, W // 2, 2)
        assert (cells.all(axis=(1, 3)) == cells.any(axis=(1, 3))).all()


def test_frames_that_differ_too_much_give_no_region():
    assert regions_of(two_screens())[1] == []


def test_identical_views_give_no_region():
    shapes = [tool.shape_view(frame) for frame in flicker_frames(6)]
    assert regions_of(shapes)[1] == []


def test_no_links_give_no_region():
    view = np.stack(score_frames(3)).reshape(3, -1)
    assert tool.candidate_regions(view, np.zeros((0, 2), np.int64), LIMIT, W, H) == []


def test_a_set_is_not_joined_when_the_union_would_exceed_the_limit():
    frames = score_frames(6)
    wide = artwork()
    wide[18:30, 4:100] = 3  # differs from the score screen over 1,100 pixels or more
    view, regions = regions_of(frames + [wide])
    changed_by_wide = view[-1] != view[0]
    assert changed_by_wide.sum() > LIMIT
    assert all((region & changed_by_wide).sum() < changed_by_wide.sum() for region in regions)


def test_smallest_difference_is_processed_first():
    base = artwork()
    small = base.copy()
    small[24, 60] = 3
    large = base.copy()
    large[20:26, 20:40] = 3
    view = np.stack([base, large, small]).reshape(3, -1)
    links = np.array([[0, 1], [0, 2]], np.int64)
    regions = tool.candidate_regions(view, links, LIMIT, W, H)
    # the link 0-2 differs in one pixel and is processed before the link 0-1
    assert int(regions[0].sum()) == 16
    assert regions[1][24 * W + 60] and regions[1][22 * W + 30]
