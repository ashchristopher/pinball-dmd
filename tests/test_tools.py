import importlib.util
from pathlib import Path

import numpy as np

import dmd_optimizer as tool
from helpers import artwork, score_frames, write_dump

TOOLS = Path(__file__).resolve().parent.parent / "tools"


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project_files(folder, frames, name="demo"):
    folder.mkdir()
    dump = tool.read_dumps([write_dump(folder / "x.txt", frames)])
    project = tool.new_project(dump, tool.analyze(dump), name)
    tool.write_project(project, folder / "p.cROM", folder / "p.cRP")
    return [str(folder / "p.cROM"), str(folder / "p.cRP")]


def test_sample_dump_keeps_the_first_records(tmp_path, capsys):
    sample = load("make_sample_dump")
    source = write_dump(tmp_path / "long.txt", score_frames(12), newline="\r\n")
    sample.main([str(source), str(tmp_path / "short.txt"), "5"])
    assert capsys.readouterr().out == f"wrote {tmp_path / 'short.txt'} with 5 records\n"
    short = tool.read_dumps([tmp_path / "short.txt"])
    whole = tool.read_dumps([source])
    assert len(short.record_frame) == 5 and short.warnings == []
    assert np.array_equal(short.frames, whole.frames[:5])
    assert source.read_bytes().startswith((tmp_path / "short.txt").read_bytes())


def test_sample_dump_of_a_short_file_is_a_copy(tmp_path):
    sample = load("make_sample_dump")
    source = write_dump(tmp_path / "long.txt", score_frames(3))
    sample.main([str(source), str(tmp_path / "short.txt")])
    assert (tmp_path / "short.txt").read_bytes() == source.read_bytes()


def test_identical_projects_compare_equal(tmp_path, capsys):
    compare = load("compare_projects")
    first = project_files(tmp_path / "a", score_frames(12))
    second = project_files(tmp_path / "b", score_frames(12))
    assert compare.main(first + second) == 0
    assert capsys.readouterr().out == "the projects are identical\n"


def test_differences_are_listed_by_field(tmp_path, capsys):
    compare = load("compare_projects")
    first = project_files(tmp_path / "a", score_frames(12) + [artwork(1)])
    second = project_files(tmp_path / "b", score_frames(12) + [artwork(2)], name="other")
    assert compare.main(first + second) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "header name: b'demo' != b'other'"
    assert any(line.startswith("cROM HashCode: 1 of 2 values differ, first at index 1 (") for line in lines)
    assert any(line.startswith("cRP oFrames: 1120 of 8192 values differ, first at index ") for line in lines)
    assert lines[-1] == f"{len(lines) - 1} differences"
