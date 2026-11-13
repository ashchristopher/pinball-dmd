import numpy as np
import pytest

import dmd_optimizer as tool
from helpers import artwork, blank, score_frames, write_dump


def test_duration_rule():
    times = np.array([1000, 1100, 1090, 6000, 6010, 10010, 14011], np.uint32)
    # next - this; 30 when the next is earlier, the gap exceeds 4000 ms, or there is no next
    assert tool.frame_durations(times).tolist() == [100, 30, 30, 10, 4000, 30, 30]
    assert tool.frame_durations(np.array([5], np.uint32)).tolist() == [30]


def test_distinct_frames_keep_first_appearance_order(tmp_path):
    a, b, c = score_frames(3)
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", [a, b, a, c, b])])
    assert (dump.width, dump.height, dump.shades) == (128, 32, 4)
    assert np.array_equal(dump.frames, np.stack([a, b, c]).reshape(3, -1))
    assert dump.record_frame.tolist() == [0, 1, 0, 2, 1]
    assert dump.record_time.tolist() == [1000, 1100, 1200, 1300, 1400]
    assert dump.record_duration.tolist() == [100, 100, 100, 100, 30]
    assert dump.record_file.tolist() == [0, 0, 0, 0, 0]
    assert dump.warnings == []


def test_sixteen_shades_are_detected(tmp_path):
    frame = artwork()
    frame[5, 5] = 9
    assert tool.read_dumps([write_dump(tmp_path / "x.txt", [frame])]).shades == 16


def test_several_files_are_joined_in_the_order_given(tmp_path):
    a, b, c = score_frames(3)
    first = write_dump(tmp_path / "one.txt", [a, b], times=[10, 50])
    second = write_dump(tmp_path / "two.txt", [c, a], times=[7, 9])
    dump = tool.read_dumps([first, second])
    assert dump.files == [str(first), str(second)]
    assert dump.record_frame.tolist() == [0, 1, 2, 0]
    assert dump.record_file.tolist() == [0, 0, 1, 1]
    assert dump.record_duration.tolist() == [40, 30, 2, 30]  # the last record of each file gets 30 ms


def test_warning_of_a_truncated_file_is_kept(tmp_path):
    path = write_dump(tmp_path / "x.txt", score_frames(3))
    path.write_bytes(path.read_bytes()[:-200])
    dump = tool.read_dumps([path])
    assert len(dump.record_frame) == 2
    assert dump.warnings == [f"{path}: record 3 is incomplete or invalid; reading stopped there"]


def test_mixed_sizes_are_an_error(tmp_path):
    small = write_dump(tmp_path / "small.txt", [artwork()])
    large = write_dump(tmp_path / "large.txt", [blank(192, 64)])
    with pytest.raises(tool.OptimizerError, match="frame size 192x64 differs from 128x32"):
        tool.read_dumps([small, large])


def test_unreadable_file_is_an_error(tmp_path):
    with pytest.raises(tool.OptimizerError, match="missing.txt: cannot read the file"):
        tool.read_dumps([tmp_path / "missing.txt"])
