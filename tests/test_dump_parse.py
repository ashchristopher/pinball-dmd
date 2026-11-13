import numpy as np
import pytest

import dmd_optimizer as tool
from helpers import H, W, artwork, blank, dump_text, score_frames


def test_parses_frames_times_and_size():
    frames = score_frames(3)
    parsed, times, size, warning = tool.parse_dump_text(dump_text(frames, times=[16, 255, 70000]), "a.txt")
    assert size == (W, H)
    assert warning is None
    assert parsed.dtype == np.uint8 and parsed.shape == (3, W * H)
    assert np.array_equal(parsed, np.stack(frames).reshape(3, -1))
    assert times.dtype == np.uint32 and times.tolist() == [16, 255, 70000]


def test_crlf_gives_the_same_result():
    frames = score_frames(2)
    unix = tool.parse_dump_text(dump_text(frames), "a.txt")
    windows = tool.parse_dump_text(dump_text(frames, newline="\r\n"), "a.txt")
    assert np.array_equal(unix[0], windows[0]) and np.array_equal(unix[1], windows[1])


def test_reads_192x64():
    frame = blank(192, 64)
    frame[10, 20] = 3
    parsed, _, size, _ = tool.parse_dump_text(dump_text([frame]), "a.txt")
    assert size == (192, 64) and parsed[0].reshape(64, 192)[10, 20] == 3


def test_hex_digits_in_both_cases():
    frame = blank()
    frame[0, :16] = np.arange(16)
    text = dump_text([frame])
    parsed_lower = tool.parse_dump_text(text, "a.txt")[0]
    parsed_upper = tool.parse_dump_text(text.replace(b"abcdef", b"ABCDEF"), "a.txt")[0]
    assert parsed_lower[0][:16].tolist() == list(range(16))
    assert np.array_equal(parsed_lower, parsed_upper)


def test_truncated_last_record_is_skipped_with_a_warning():
    text = dump_text(score_frames(3))
    cut = text[: len(text) - 5 * (W + 1)]  # drop the last rows of the third record
    parsed, times, _, warning = tool.parse_dump_text(cut, "a.txt")
    assert len(parsed) == 2 and len(times) == 2
    assert warning == "a.txt: record 3 is incomplete or invalid; reading stopped there"


def test_short_row_stops_reading():
    lines = dump_text(score_frames(3)).split(b"\n")
    lines[H + 2 + 5] = lines[H + 2 + 5][:-1]  # one pixel missing in a row of the second record
    parsed, _, _, warning = tool.parse_dump_text(b"\n".join(lines), "a.txt")
    assert len(parsed) == 1 and "record 2" in warning


def test_letter_beyond_f_stops_reading():
    lines = dump_text(score_frames(2)).split(b"\n")
    lines[H + 2 + 3] = b"g" + lines[H + 2 + 3][1:]
    parsed, _, _, warning = tool.parse_dump_text(b"\n".join(lines), "a.txt")
    assert len(parsed) == 1 and "record 2" in warning


def test_text_after_a_complete_record_stops_reading_and_keeps_the_record():
    first, second, third = (dump_text([frame]) for frame in score_frames(3))
    damaged = second.replace(b"0x000003e8", b"0x3e8")  # a timestamp with too few digits
    parsed, times, _, warning = tool.parse_dump_text(first + damaged + third, "a.txt")
    assert len(parsed) == 1 and times.tolist() == [1000]
    assert warning == "a.txt: unexpected text after record 1; reading stopped there"


@pytest.mark.parametrize("extra", [b"0123" * 32, b"z" * 128])
def test_a_row_too_many_after_the_first_record_keeps_the_record(extra):
    # the extra line is as wide as a pixel row, so only the supported height tells where the record ends
    first, second = (dump_text([frame]) for frame in score_frames(2))
    parsed, times, size, warning = tool.parse_dump_text(first + extra + b"\n\n" + second, "a.txt")
    assert size == (W, H) and len(parsed) == 1 and times.tolist() == [1000]
    assert warning == "a.txt: unexpected text after record 1; reading stopped there"


def test_blank_lines_inside_a_record_are_ignored():
    lines = dump_text(score_frames(3)).split(b"\n")
    lines.insert(H + 2 + 7, b"")  # a blank line between two rows of the second record
    parsed, _, _, warning = tool.parse_dump_text(b"\n".join(lines), "a.txt")
    assert len(parsed) == 3 and warning is None


def test_unsupported_size_is_an_error():
    with pytest.raises(tool.OptimizerError, match="64x16 is not supported"):
        tool.parse_dump_text(dump_text([blank(64, 16)]), "a.txt")


def test_no_frame_is_an_error():
    with pytest.raises(tool.OptimizerError, match="a.txt: no complete frame found"):
        tool.parse_dump_text(b"not a dump\n", "a.txt")
    with pytest.raises(tool.OptimizerError, match="a.txt: no complete frame found"):
        tool.parse_dump_text(b"0x000003e8\n", "a.txt")


def test_a_file_cut_inside_its_first_record_is_an_error():
    # only three rows of the first record remain, so the size cannot be recognised
    with pytest.raises(tool.OptimizerError, match="frame size 128x3 is not supported"):
        tool.parse_dump_text(dump_text([artwork()])[: 10 + 3 * (W + 1)], "a.txt")
