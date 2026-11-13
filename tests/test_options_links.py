import numpy as np

import dmd_optimizer as tool


def make_dump(record_frame, record_file, frames=4):
    records = len(record_frame)
    return tool.Dump(
        width=128, height=32, shades=4,
        frames=np.zeros((frames, 128 * 32), np.uint8),
        record_frame=np.array(record_frame, np.int64),
        record_time=np.arange(records, dtype=np.uint32),
        record_duration=np.full(records, 30, np.uint32),
        record_file=np.array(record_file, np.int64),
        files=["a.txt", "b.txt"], warnings=[],
    )


def test_limit_is_rounded_down():
    assert tool.Options().limit(4096) == 1024
    assert tool.Options(max_vary=10).limit(4096) == 409
    assert tool.Options(max_vary=12.5).limit(4096) == 512
    assert tool.Options(max_vary=0).limit(4096) == 0
    assert tool.Options(max_vary=100).limit(12288) == 12288


def test_lit_pixels_needed():
    assert tool.Options().lit_needed(4096) == 32
    assert tool.Options().lit_needed(192 * 64) == 96
    assert tool.Options(min_lit=7).lit_needed(4096) == 7
    assert tool.Options(min_lit=0).lit_needed(4096) == 0


def test_shape_view():
    frames = np.array([[0, 1, 2, 3], [15, 0, 0, 1]], np.uint8)
    view = tool.shape_view(frames)
    assert view.dtype == np.uint8 and view.tolist() == [[0, 1, 1, 1], [1, 0, 0, 1]]


def test_links_are_unordered_pairs_of_neighbours_within_a_file():
    #            file a: 0 1 0 2 2 | file b: 2 3
    dump = make_dump([0, 1, 0, 2, 2, 2, 3], [0, 0, 0, 0, 0, 1, 1])
    assert tool.timeline_links(dump).tolist() == [[0, 1], [0, 2], [2, 3]]


def test_frames_on_both_sides_of_a_file_boundary_are_not_linked():
    dump = make_dump([0, 1], [0, 1])
    links = tool.timeline_links(dump)
    assert links.shape == (0, 2)
