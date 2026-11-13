import numpy as np
import pytest

import dmd_optimizer as tool
from helpers import artwork, blank, flicker_frames, score_frames, write_dump


def build(tmp_path, frames, times=None, name="demo"):
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", frames, times)])
    analysis = tool.analyze(dump)
    return dump, analysis, tool.new_project(dump, analysis, name)


def test_default_colours_are_the_editor_ramp():
    assert tool.default_colours(4).tolist() == [0x0000, 0x5140, 0xA280, 0xFBE0]
    ramp = tool.default_colours(16)
    assert ramp.dtype == np.uint16 and ramp[0] == 0 and ramp[15] == 0xFBE0
    assert ramp[7] == (14 << 11) | (14 << 5)  # floor(31 * 7 / 15) = 14


def test_header_and_identification_fields(tmp_path):
    frames = score_frames(12) + flicker_frames(10, variant=1) + [artwork(2)]
    dump, analysis, project = build(tmp_path, frames)
    assert project.header == {
        "name": b"demo", "header_length": 80, "fWidth": 128, "fHeight": 32, "fWidthX": 256,
        "fHeightX": 64, "nFrames": 3, "noColors": 4, "nCompMasks": 1, "nSprites": 0,
        "nBackgrounds": 0, "is256x64": 0,
    }
    crom = project.crom
    assert crom["CompMaskID"].tolist() == [0, 255, 255]
    assert crom["ShapeCompMode"].tolist() == [0, 1, 0]
    assert crom["HashCode"].tolist() == [group.hash for group in analysis.groups]
    assert crom["HashCode"].dtype == np.uint32
    assert crom["HashCode"][0] == tool.frame_hash(dump.frames[0], analysis.masks[0])
    assert crom["HashCode"][2] == tool.frame_hash(dump.frames[22])
    assert np.array_equal(crom["CompMasks"], analysis.masks[0].astype(np.uint8))
    assert set(crom["CompMasks"].tolist()) == {0, 1}


def test_everything_else_is_as_after_a_fresh_import(tmp_path):
    dump, analysis, project = build(tmp_path, score_frames(12) + [artwork(2)])
    crom, crp = project.crom, project.crp
    kept = dump.frames[[0, 12]]
    ramp = np.array([0x0000, 0x5140, 0xA280, 0xFBE0], np.uint16)
    assert np.array_equal(crom["cFrames"], ramp[kept].reshape(-1)) and crom["cFrames"].dtype == np.uint16
    assert np.array_equal(crom["FrameSpriteBB"], np.tile([0, 0, 127, 31], 2 * 32))
    expected = {"DynaMasks": 255, "DynaMasksX": 255, "FrameSprites": 255, "TriggerID": 0xFFFFFFFF,
                "BackgroundID": 0xFFFF, "BackgroundMask": 1, "BackgroundMaskX": 1}
    given = {"HashCode", "ShapeCompMode", "CompMaskID", "CompMasks", "cFrames", "ActiveFrames", "FrameSpriteBB"}
    for name, _, _ in tool._crom_layout(project.header):
        if name not in given:
            assert np.ndim(crom[name]) == 0 and crom[name] == expected.get(name, 0), name
    assert np.array_equal(crp["oFrames"], kept.reshape(-1))
    assert crp["name"].tobytes() == b"demo".ljust(64, b"\x00")
    assert crp["Palette"][:5].tolist() == [0x0000, 0x5140, 0xA280, 0xFBE0, 0] and len(crp["Palette"]) == 16384
    assert crp["acEditColorsS"].tolist() == [0x0000, 0x5140, 0xA280, 0xFBE0] + [0] * 12
    for name, _, _ in tool._crp_layout(project.header):
        if name not in {"name", "oFrames", "Mask_Names", "FrameDuration", "Palette", "acEditColorsS"}:
            assert np.ndim(crp[name]) == 0 and crp[name] == 0, name


def test_mask_names(tmp_path):
    _, analysis, project = build(tmp_path, score_frames(12))
    names = project.crp["Mask_Names"].reshape(64, 32)
    percent = int(analysis.masks[0].sum() * 100 / 4096 + 0.5)
    assert names[0].tobytes().rstrip(b"\x00") == f"auto-00 {percent}% 11 frames".encode()
    assert not names[1:].any()
    assert tool.mask_name(63, np.ones(4096, bool), 123456789012345) == "auto-63 100% 123456789012345 f"
    assert len(tool.mask_name(63, np.ones(4096, bool), 123456789012345)) == 30


def test_duration_is_the_longest_of_the_group_and_short_frames_are_inactive(tmp_path):
    frames = score_frames(6) + [artwork(1), artwork(2)] + score_frames(1)
    times = [0, 10, 20, 500, 510, 520, 530, 540, 2540]
    # durations: 10 10 480 10 10 10 | 10 | 2000 | 30 (last record)
    dump, analysis, project = build(tmp_path, frames, times, name="demo")
    assert [len(group.members) for group in analysis.groups] == [6, 1, 1]
    assert project.crp["FrameDuration"].tolist() == [480, 10, 2000]
    assert project.crp["FrameDuration"].dtype == np.uint32
    assert project.crom["ActiveFrames"].tolist() == [1, 0, 1]


def test_written_files_have_the_sizes_of_the_design(tmp_path):
    _, analysis, project = build(tmp_path, score_frames(12) + [artwork(2)])
    tool.write_project(project, tmp_path / "demo.cROM", tmp_path / "demo.cRP")
    assert (tmp_path / "demo.cROM").stat().st_size == 106 + 2 * 83950 + 1 * 4096
    assert (tmp_path / "demo.cRP").stat().st_size == 21004003 - 5093 * 4100 + 2 * 4100
    back = tool.read_project(tmp_path / "demo.cROM", tmp_path / "demo.cRP")
    assert back.crom["CompMaskID"].tolist() == [0, 255]
    assert back.crom["BackgroundMaskX"].tolist() == [1] * (2 * 256 * 64)
    assert len(back.crom["SpriteShapeMode"]) == 0 and len(back.crp["importedPal"]) == 0


def test_192x64_with_sixteen_shades(tmp_path):
    frame = blank(192, 64)
    frame[10:20, 10:60] = 12
    _, _, project = build(tmp_path, [frame])
    header = project.header
    assert (header["fWidth"], header["fHeight"], header["fWidthX"], header["fHeightX"]) == (192, 64, 96, 32)
    assert header["noColors"] == 16
    assert project.crom["cFrames"].max() == tool.default_colours(16)[12]
    assert project.crom["FrameSpriteBB"][:4].tolist() == [0, 0, 191, 63]
    tool.write_project(project, tmp_path / "demo.cROM", tmp_path / "demo.cRP")
    pixels, extra = 192 * 64, 96 * 32
    per_frame = 4 + 3 + 2 * pixels + 2 * extra + pixels + extra + 4 * 32 * 16 + 32 + 1 + 1024 + 4 + 256 + 2 + pixels + extra + 192
    assert (tmp_path / "demo.cROM").stat().st_size == 106 + per_frame


@pytest.mark.parametrize("name", [
    "", "a" * 64, "caf\u00e9", "a/b", "a\\b", "..", ".", "x:y", "what?", "a b", "rom.", ".rom",
    "nul", "COM1", "lpt9.old", "a\x00b", "a\nb", "a\rb", "tab\there",
])
def test_unusable_rom_names_are_refused(tmp_path, name):
    with pytest.raises(tool.OptimizerError, match="is not usable"):
        tool.check_rom_name(name)
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", [artwork()])])
    with pytest.raises(tool.OptimizerError, match="is not usable"):
        tool.new_project(dump, tool.analyze(dump), name)


def test_usable_rom_names_are_accepted():
    for name in ("twst_405", "a" * 63, "afm_113b", "My-ROM_1.2", "x", "com10", "null"):
        tool.check_rom_name(name)
