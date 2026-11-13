import dmd_optimizer as tool
from helpers import H, W, artwork, dump_text


def test_the_tool_imports():
    assert issubclass(tool.OptimizerError, Exception)


def test_helper_writes_dump_text():
    lines = dump_text([artwork(), artwork(1)], times=[1000, 1100]).split(b"\n")
    assert lines[0] == b"0x000003e8" and lines[H + 2] == b"0x0000044c"
    assert all(len(line) == W for line in lines[1:H + 1])
    assert lines[1] == b"2" * W  # the top border of the artwork
    assert lines[H + 1] == b""
