import re
import struct
import zlib

import numpy as np

import dmd_optimizer as tool
from helpers import artwork, flicker_frames, score_frames, write_dump


def report(tmp_path, frames, times=None, **settings):
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", frames, times)])
    analysis = tool.analyze(dump, tool.Options(**settings))
    return dump, analysis, tool.report_html(dump, analysis, "demo")


def test_png_image_is_a_valid_palette_png():
    indexed = np.array([[0, 1, 2], [2, 1, 0]], np.uint8)
    data = tool.png_image(indexed, [(0, 0, 0), (255, 127, 0), (9, 8, 7)])
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    position, chunks = 8, {}
    while position < len(data):
        length, tag = struct.unpack(">I4s", data[position:position + 8])
        body = data[position + 8:position + 8 + length]
        assert struct.unpack(">I", data[position + 8 + length:position + 12 + length])[0] == zlib.crc32(tag + body)
        chunks[tag] = body
        position += 12 + length
    assert list(chunks) == [b"IHDR", b"PLTE", b"IDAT", b"IEND"]
    assert struct.unpack(">IIBBBBB", chunks[b"IHDR"]) == (3, 2, 8, 3, 0, 0, 0)
    assert chunks[b"PLTE"] == bytes([0, 0, 0, 255, 127, 0, 9, 8, 7])
    assert zlib.decompress(chunks[b"IDAT"]) == bytes([0, 0, 1, 2, 0, 2, 1, 0])  # filter byte 0 before each row


def test_summary_lists_the_run(tmp_path):
    frames = score_frames(12) + flicker_frames(10, variant=1) + [artwork(2)]
    dump, analysis, page = report(tmp_path, frames + frames[:3])
    assert tool.summarize(dump, analysis) == {
        "dump files read": 1,
        "frames read": 26,
        "distinct frames": 23,
        "frames kept": 3,
        "frames kept unmerged": 1,
        "masks used": 1,
        "frames merged by shape mode alone": 9,
    }
    for label, value in tool.summarize(dump, analysis).items():
        assert f"<tr><th>{label}</th><td>{value}</td></tr>" in page
    assert "<tr><th>--max-vary</th><td>25% (1024 pixels)</td></tr>" in page
    assert "<tr><th>--min-lit</th><td>32 pixels</td></tr>" in page
    assert "<tr><th>shape mode</th><td>on</td></tr>" in page
    assert "<title>DMD mask optimizer report for demo</title>" in page


def test_one_section_per_mask_and_one_for_shape_mode(tmp_path):
    frames = score_frames(12) + flicker_frames(10, variant=1) + score_frames(7, variant=2, x=88)
    dump, analysis, page = report(tmp_path, frames)
    assert len(analysis.masks) == 2
    assert re.findall(r'<details id="([^"]+)">', page) == ["mask-0", "mask-1", "shape-only"]
    assert "Mask 0 (auto-00 " in page and "1 groups, 12 frames merged into 1" in page
    assert "Shape mode with no mask: 1 groups, 10 frames merged into 1" in page
    assert re.findall(r'<div class="group" id="frame-(\d+)">', page) == ["0", "2", "1"]
    assert "Frame 0: 12 frames merged, shape mode off" in page
    assert "Frame 1: 10 frames merged, shape mode on" in page
    # a kept frame and up to three other members are pictured for every group, plus one picture per mask
    assert page.count("<img ") == 3 * 4 + 2
    assert "kept frame 0, first shown at 0x000003e8" in page
    assert "merged frame, first shown at 0x0000044c" in page


def test_the_report_is_self_contained(tmp_path):
    _, _, page = report(tmp_path, score_frames(12))
    assert page.startswith("<!doctype html>") and page.rstrip().endswith("</html>")
    assert "http://" not in page and "https://" not in page
    assert set(re.findall(r'src="([^":]+):', page)) == {"data"}


def test_review_first_list_is_ordered_by_varying_area(tmp_path):
    frames = score_frames(12) + flicker_frames(10, variant=1)
    dump, analysis, page = report(tmp_path, frames)
    assert "<h2>The 2 merged groups with the largest varying area</h2>" in page
    listed = re.findall(r'<li><a href="#frame-(\d+)">Frame \d+</a>: (\d+)% of the limit', page)
    assert [number for number, _ in listed] == ["1", "0"]  # the flicker varies over more pixels
    assert [int(share) for _, share in listed] == sorted((int(share) for _, share in listed), reverse=True)


def test_nothing_merged(tmp_path):
    _, _, page = report(tmp_path, [artwork(0), artwork(1), artwork(2)])
    assert "<h2>Merged groups</h2><p>No frames were merged.</p>" in page
    assert "<details" not in page and "<img " not in page


def test_no_shape_section_without_shape_groups(tmp_path):
    _, _, page = report(tmp_path, score_frames(12))
    assert re.findall(r'<details id="([^"]+)">', page) == ["mask-0"]


def test_no_warnings(tmp_path):
    assert "<h2>Warnings</h2>\n<p>No warnings.</p>" in report(tmp_path, score_frames(12))[2]


def test_warnings_list_short_frames_collisions_and_truncated_dumps(tmp_path):
    path = write_dump(tmp_path / "x.txt", score_frames(12) + [artwork(1), artwork(2)], times=list(range(0, 1400, 100)))
    text = path.read_bytes()
    path.write_bytes(text[:-100])  # the last record loses its last row
    dump = tool.read_dumps([path])
    dump.record_duration[12] = 3
    analysis = tool.analyze(dump)
    analysis.collisions.append((5, 12))
    page = tool.report_html(dump, analysis, "demo")
    assert "record 14 is incomplete or invalid; reading stopped there" in page
    assert "Kept frame 1 is shown for 3 ms. The editor marks frames under 15 ms inactive" in page
    assert ("The frame first shown at 0x000001f4 has the same CRC32 as kept frame 1 under that "
            "frame's mask and shape mode, but different pixels.") in page


def test_rom_name_is_escaped(tmp_path):
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", score_frames(3))])
    page = tool.report_html(dump, tool.analyze(dump), "a<b>&c")
    assert "report for a&lt;b&gt;&amp;c</h1>" in page and "<b>&c" not in page
