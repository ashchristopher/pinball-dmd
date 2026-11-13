import numpy as np
import pytest

import dmd_optimizer as tool


def sample_project(frames=3, masks=2, sprites=2, backgrounds=1, shades=4, imported=0):
    """A project with random content in every field, including sprites and backgrounds."""
    rng = np.random.default_rng(11)
    header = {
        "name": b"sample\x00left-over bytes after the terminator",
        "header_length": 80, "fWidth": 128, "fHeight": 32, "fWidthX": 256, "fHeightX": 64,
        "nFrames": frames, "noColors": shades, "nCompMasks": masks, "nSprites": sprites,
        "nBackgrounds": backgrounds, "is256x64": 0,
    }

    def fill(layout, fields):
        for name, dtype, count in layout:
            if callable(count):
                count = count(fields)
            high = min(int(np.iinfo(np.dtype(dtype)).max), 60000)
            fields[name] = rng.integers(0, high, size=count).astype(dtype)
        return fields

    crom = fill(tool._crom_layout(header), {})
    crp = {"isImported": np.array([imported], "<u4")}
    for name, dtype, count in tool._crp_layout(header):
        if name != "isImported":
            crp.update(fill([(name, dtype, count)], dict(crp)))
    ordered = {name: crp[name] for name, _, _ in tool._crp_layout(header)}
    return tool.Project(header=header, crom=crom, crp=ordered)


def expected_crom_size(frames, masks, sprites, backgrounds, shades, pixels=4096, extra=16384):
    per_frame = (4 + 1 + 1 + 1 + 2 * pixels + 2 * extra + pixels + extra + 2 * 2 * 32 * shades + 32 + 1
                 + 2 * 2 * 256 + 4 + 2 * 128 + 2 + pixels + extra + 32 + 64 + 32 + 64)
    per_sprite = 1 + 16384 * (1 + 2 + 1 + 2) + 4 * 4 + 2 * 4 + 2 * 16 + 2 * 2 * 9 * shades + 2 * 16384 + 1
    per_background = 1 + 2 * pixels + 2 * extra
    return 106 + frames * per_frame + masks * pixels + sprites * per_sprite + backgrounds * per_background


CRP_FIXED_SIZE = (64 + 64 * 4 + 1024 * 2 + 1 + 1 + 4096 + 4 + 1 + 4 + 4 + 2048 + 4 + 512 * 4 + 16384 + 8160
                  + 255 * 4 + 1020 * 2 + 510 * 4 + 16384 * 2 + 32 + 4 + 16384 + 4096 * 4 + 16384 + 4 + 4 + 4 + 512)


def test_file_sizes_follow_the_layout(tmp_path):
    project = sample_project()
    tool.write_project(project, tmp_path / "s.cROM", tmp_path / "s.cRP")
    assert (tmp_path / "s.cROM").stat().st_size == expected_crom_size(3, 2, 2, 1, 4)
    assert (tmp_path / "s.cRP").stat().st_size == CRP_FIXED_SIZE + 3 * 4096 + 3 * 4


def test_a_128x32_four_shade_frame_takes_83950_bytes():
    assert expected_crom_size(1, 0, 0, 0, 4) - expected_crom_size(0, 0, 0, 0, 4) == 83950
    assert expected_crom_size(0, 0, 0, 0, 4) == 106


def test_the_header_is_written_field_by_field(tmp_path):
    tool.write_project(sample_project(), tmp_path / "s.cROM", tmp_path / "s.cRP")
    raw = (tmp_path / "s.cROM").read_bytes()[:106]
    assert raw[:6] == b"sample" and len(raw) == 106
    assert np.frombuffer(raw[64:100], "<u4").tolist() == [80, 128, 32, 256, 64, 3, 4, 2, 2]
    assert np.frombuffer(raw[100:102], "<u2").tolist() == [1]
    assert np.frombuffer(raw[102:106], "<u4").tolist() == [0]


def test_reading_back_gives_the_same_project(tmp_path):
    project = sample_project(imported=2)
    tool.write_project(project, tmp_path / "s.cROM", tmp_path / "s.cRP")
    back = tool.read_project(tmp_path / "s.cROM", tmp_path / "s.cRP")
    assert back.header == {**project.header, "name": project.header["name"].ljust(64, b"\x00")}
    for original, copy in ((project.crom, back.crom), (project.crp, back.crp)):
        assert list(original) == list(copy)
        for name in original:
            assert original[name].dtype == copy[name].dtype, name
            assert np.array_equal(original[name], copy[name]), name
    assert len(back.crp["importedPal"]) == 2 * 64 * 3
    tool.write_project(back, tmp_path / "t.cROM", tmp_path / "t.cRP")
    assert (tmp_path / "t.cROM").read_bytes() == (tmp_path / "s.cROM").read_bytes()
    assert (tmp_path / "t.cRP").read_bytes() == (tmp_path / "s.cRP").read_bytes()


def test_an_int_fills_a_whole_field(tmp_path):
    project = sample_project(frames=2, masks=0, sprites=0, backgrounds=0)
    project.crom["DynaMasks"] = 255
    project.crom["TriggerID"] = 0xFFFFFFFF
    project.crom["cFramesX"] = 0
    tool.write_project(project, tmp_path / "s.cROM", tmp_path / "s.cRP")
    back = tool.read_project(tmp_path / "s.cROM", tmp_path / "s.cRP")
    assert back.crom["DynaMasks"].tolist() == [255] * (2 * 4096)
    assert back.crom["TriggerID"].tolist() == [0xFFFFFFFF] * 2
    assert not back.crom["cFramesX"].any() and len(back.crom["cFramesX"]) == 2 * 16384


def test_a_field_of_the_wrong_length_is_refused(tmp_path):
    project = sample_project()
    project.crom["HashCode"] = project.crom["HashCode"][:-1]
    with pytest.raises(ValueError, match="field HashCode has 2 values, expected 3"):
        tool.write_project(project, tmp_path / "s.cROM", tmp_path / "s.cRP")


def test_unsupported_formats_are_refused(tmp_path):
    for change in ({"header_length": 56}, {"is256x64": 1}):
        project = sample_project()
        project.header.update(change)
        tool.write_project(project, tmp_path / "s.cROM", tmp_path / "s.cRP")
        with pytest.raises(tool.OptimizerError, match="unsupported project format"):
            tool.read_project(tmp_path / "s.cROM", tmp_path / "s.cRP")


def test_damaged_files_are_refused(tmp_path):
    tool.write_project(sample_project(), tmp_path / "s.cROM", tmp_path / "s.cRP")
    whole = (tmp_path / "s.cROM").read_bytes()
    (tmp_path / "short.cROM").write_bytes(whole[:-1])
    with pytest.raises(tool.OptimizerError, match="the file ends inside the field SpriteShapeMode"):
        tool.read_project(tmp_path / "short.cROM", tmp_path / "s.cRP")
    (tmp_path / "long.cROM").write_bytes(whole + b"\x00")
    with pytest.raises(tool.OptimizerError, match="unexpected data after the last field"):
        tool.read_project(tmp_path / "long.cROM", tmp_path / "s.cRP")
    (tmp_path / "tiny.cROM").write_bytes(whole[:50])
    with pytest.raises(tool.OptimizerError, match="too short to be a .cROM"):
        tool.read_project(tmp_path / "tiny.cROM", tmp_path / "s.cRP")
