import pytest

import dmd_optimizer as tool
from helpers import artwork, blank, flicker_frames, score_frames, write_dump


@pytest.fixture
def dump_path(tmp_path):
    frames = score_frames(12) + flicker_frames(10, variant=1) + [artwork(2)]
    return write_dump(tmp_path / "demo_rom.txt", frames)


def files_in(folder):
    return sorted(path.name for path in folder.iterdir())


def error_message(captured):
    """The one error line of a failed run; it must be the last line on standard error."""
    lines = captured.err.splitlines()
    assert [line.startswith("dmd_optimizer: error: ") for line in lines].count(True) == 1
    assert lines[-1].startswith("dmd_optimizer: error: ")
    return lines[-1][len("dmd_optimizer: error: "):]


def test_writes_three_files_and_a_summary(dump_path, tmp_path, capsys):
    out = tmp_path / "out"
    assert tool.main([str(dump_path), "--out-dir", str(out)]) == 0
    assert files_in(out) == ["demo_rom-report.html", "demo_rom.cROM", "demo_rom.cRP"]
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "dump files read: 1",
        "frames read: 23",
        "distinct frames: 23",
        "frames kept: 3",
        "frames kept unmerged: 1",
        "masks used: 1",
        "frames merged by shape mode alone: 9",
        f"wrote {out / 'demo_rom.cROM'}",
        f"wrote {out / 'demo_rom.cRP'}",
        f"wrote {out / 'demo_rom-report.html'}",
    ]
    assert "dmd_optimizer: reading dumps" in captured.err and "dmd_optimizer: writing files" in captured.err
    project = tool.read_project(out / "demo_rom.cROM", out / "demo_rom.cRP")
    assert project.header["nFrames"] == 3 and project.header["name"].rstrip(b"\x00") == b"demo_rom"
    assert project.crom["CompMaskID"].tolist() == [0, 255, 255]
    assert project.crom["ShapeCompMode"].tolist() == [0, 1, 0]


def test_default_output_folder_is_named_after_the_rom(dump_path, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert tool.main([str(dump_path)]) == 0
    assert files_in(tmp_path / "demo_rom-optimized") == ["demo_rom-report.html", "demo_rom.cROM", "demo_rom.cRP"]


def test_rom_name_option(dump_path, tmp_path):
    out = tmp_path / "out"
    assert tool.main([str(dump_path), "--out-dir", str(out), "--rom-name", "twst_405"]) == 0
    assert files_in(out) == ["twst_405-report.html", "twst_405.cROM", "twst_405.cRP"]
    assert tool.read_project(out / "twst_405.cROM", out / "twst_405.cRP").header["name"][:9] == b"twst_405\x00"


def test_existing_files_are_not_overwritten_without_force(dump_path, tmp_path, capsys):
    out = tmp_path / "out"
    out.mkdir()
    (out / "demo_rom.cRP").write_bytes(b"hand-made")
    assert tool.main([str(dump_path), "--out-dir", str(out)]) == 1
    assert files_in(out) == ["demo_rom.cRP"] and (out / "demo_rom.cRP").read_bytes() == b"hand-made"
    error = capsys.readouterr().err
    assert error == f"dmd_optimizer: error: {out / 'demo_rom.cRP'} already exists; pass --force to overwrite it\n"
    assert tool.main([str(dump_path), "--out-dir", str(out), "--force"]) == 0
    assert files_in(out) == ["demo_rom-report.html", "demo_rom.cROM", "demo_rom.cRP"]
    assert (out / "demo_rom.cRP").read_bytes() != b"hand-made"


def test_options_change_the_result(dump_path, tmp_path):
    plain = tmp_path / "plain"
    assert tool.main([str(dump_path), "--out-dir", str(plain), "--max-masks", "0", "--no-shape-mode"]) == 0
    project = tool.read_project(plain / "demo_rom.cROM", plain / "demo_rom.cRP")
    assert project.header["nFrames"] == 23 and project.header["nCompMasks"] == 0
    assert set(project.crom["CompMaskID"].tolist()) == {255} and not project.crom["ShapeCompMode"].any()
    strict = tmp_path / "strict"
    assert tool.main([str(dump_path), "--out-dir", str(strict), "--min-gain", "12", "--max-vary", "30",
                      "--min-lit", "10"]) == 0
    assert tool.read_project(strict / "demo_rom.cROM", strict / "demo_rom.cRP").header["nFrames"] == 14


@pytest.mark.parametrize("arguments, message", [
    (["--max-vary", "101"], "--max-vary must be between 0 and 100"),
    (["--max-vary", "-1"], "--max-vary must be between 0 and 100"),
    (["--max-masks", "65"], "--max-masks must be between 0 and 64"),
    (["--max-masks", "-1"], "--max-masks must be between 0 and 64"),
    (["--min-gain", "0"], "--min-gain must be at least 1"),
    (["--min-lit", "-5"], "--min-lit must not be negative"),
    (["--rom-name", "a/b"], "ROM name 'a/b' is not usable"),
])
def test_values_out_of_range_are_errors(dump_path, tmp_path, capsys, arguments, message):
    out = tmp_path / "out"
    assert tool.main([str(dump_path), "--out-dir", str(out)] + arguments) == 1
    captured = capsys.readouterr()
    assert message in error_message(captured) and captured.err.count("\n") == 1
    assert captured.out == "" and not out.exists()


def test_dump_errors_are_reported(tmp_path, capsys):
    out = tmp_path / "out"
    assert tool.main([str(tmp_path / "missing.txt"), "--out-dir", str(out)]) == 1
    assert "missing.txt: cannot read the file" in error_message(capsys.readouterr())
    odd = write_dump(tmp_path / "odd.txt", [blank(64, 16)])
    assert tool.main([str(odd), "--out-dir", str(out)]) == 1
    assert "frame size 64x16 is not supported" in error_message(capsys.readouterr())
    mixed = write_dump(tmp_path / "large.txt", [blank(192, 64)])
    small = write_dump(tmp_path / "small.txt", [artwork()])
    assert tool.main([str(small), str(mixed), "--out-dir", str(out)]) == 1
    captured = capsys.readouterr()
    assert "differs from 128x32" in error_message(captured)
    assert captured.out == "" and not out.exists()


def test_a_truncated_dump_gives_a_warning_and_still_works(tmp_path, capsys):
    path = write_dump(tmp_path / "cut.txt", score_frames(12))
    path.write_bytes(path.read_bytes()[:-50])
    assert tool.main([str(path), "--out-dir", str(tmp_path / "out")]) == 0
    assert "dmd_optimizer: warning: " in capsys.readouterr().err
    assert tool.read_project(tmp_path / "out" / "cut.cROM", tmp_path / "out" / "cut.cRP").header["nFrames"] == 1


def test_a_failed_run_leaves_nothing_behind(dump_path, tmp_path, capsys, monkeypatch):
    def broken(*arguments):
        raise tool.OptimizerError("internal check failed: test")

    monkeypatch.setattr(tool, "report_html", broken)
    out = tmp_path / "out"
    assert tool.main([str(dump_path), "--out-dir", str(out)]) == 1
    assert error_message(capsys.readouterr()) == "internal check failed: test"
    assert not out.exists()
    out.mkdir()
    (out / "notes.txt").write_text("keep me")
    assert tool.main([str(dump_path), "--out-dir", str(out)]) == 1
    assert files_in(out) == ["notes.txt"]


def test_running_out_of_memory_is_reported_in_one_line(dump_path, tmp_path, capsys, monkeypatch):
    def exhausted(*arguments):
        raise MemoryError()

    monkeypatch.setattr(tool, "analyze", exhausted)
    out = tmp_path / "out"
    assert tool.main([str(dump_path), "--out-dir", str(out)]) == 1
    captured = capsys.readouterr()
    assert error_message(captured).startswith("not enough memory. Allow about 60 KB per distinct 128x32 frame")
    assert captured.out == "" and not out.exists()


def test_write_problems_are_reported(dump_path, tmp_path, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the output folder should be")
    assert tool.main([str(dump_path), "--out-dir", str(blocker)]) == 1
    assert error_message(capsys.readouterr()).startswith("cannot write the output files: ")
    assert blocker.read_text() == "a file where the output folder should be"


def failing_replace(monkeypatch, *fail_at):
    """Make the given calls (1 = first) of os.replace inside the tool raise."""
    real = tool.os.replace
    calls = []

    def replace(source, target):
        calls.append((source, target))
        if len(calls) in fail_at:
            raise OSError("simulated failure")
        return real(source, target)

    monkeypatch.setattr(tool.os, "replace", replace)


OUTPUTS = ("demo_rom.cROM", "demo_rom.cRP", "demo_rom-report.html")


def existing_outputs(folder):
    folder.mkdir()
    old = {name: f"old {name}".encode() for name in OUTPUTS}
    for name, content in old.items():
        (folder / name).write_bytes(content)
    return old


@pytest.mark.parametrize("fail_at", [1, 2, 3])
def test_a_failed_move_into_a_new_folder_leaves_nothing(dump_path, tmp_path, capsys, monkeypatch, fail_at):
    failing_replace(monkeypatch, fail_at)
    out = tmp_path / "out"
    assert tool.main([str(dump_path), "--out-dir", str(out)]) == 1
    assert error_message(capsys.readouterr()) == "cannot write the output files: simulated failure"
    assert not out.exists()


@pytest.mark.parametrize("fail_at", [1, 2, 3, 4, 5, 6])
def test_a_failed_move_restores_the_existing_files(dump_path, tmp_path, capsys, monkeypatch, fail_at):
    out = tmp_path / "out"
    old = existing_outputs(out)
    failing_replace(monkeypatch, fail_at)  # with --force every file takes two moves: set aside, then install
    assert tool.main([str(dump_path), "--out-dir", str(out), "--force"]) == 1
    assert error_message(capsys.readouterr()) == "cannot write the output files: simulated failure"
    assert files_in(out) == sorted(old)
    for name, content in old.items():
        assert (out / name).read_bytes() == content, name


def test_when_putting_back_fails_too_the_previous_version_is_kept_and_named(dump_path, tmp_path, capsys, monkeypatch):
    out = tmp_path / "out"
    old = existing_outputs(out)
    # move 4 installs the second file and fails; move 5 would put its previous version back and fails too
    failing_replace(monkeypatch, 4, 5)
    assert tool.main([str(dump_path), "--out-dir", str(out), "--force"]) == 1
    message = error_message(capsys.readouterr())
    (staging,) = [path for path in out.iterdir() if path.is_dir()]
    kept = staging / "demo_rom.cRP.previous"
    assert message == ("cannot write the output files: simulated failure. Putting the previous state back "
                       f"failed as well; check these files by hand: {kept}")
    assert kept.read_bytes() == old["demo_rom.cRP"]
    assert not (out / "demo_rom.cRP").exists()
    assert (out / "demo_rom.cROM").read_bytes() == old["demo_rom.cROM"]  # put back
    assert (out / "demo_rom-report.html").read_bytes() == old["demo_rom-report.html"]  # never touched


def test_a_new_file_that_cannot_be_removed_again_is_named(dump_path, tmp_path, capsys, monkeypatch):
    failing_replace(monkeypatch, 2)  # the first file is installed, the second is claimed but its move fails

    def remove(path):
        raise OSError("simulated failure")

    monkeypatch.setattr(tool.os, "remove", remove)
    out = tmp_path / "out"
    assert tool.main([str(dump_path), "--out-dir", str(out)]) == 1
    message = error_message(capsys.readouterr())
    assert message.endswith(f"check these files by hand: {out / 'demo_rom.cRP'}, {out / 'demo_rom.cROM'}")
    assert (out / "demo_rom.cROM").exists() and (out / "demo_rom.cRP").read_bytes() == b""


def test_a_temporary_folder_that_cannot_be_removed_is_only_a_warning(dump_path, tmp_path, capsys, monkeypatch):
    def rmtree(path):
        raise OSError("simulated failure")

    monkeypatch.setattr(tool.shutil, "rmtree", rmtree)
    out = tmp_path / "out"
    old = existing_outputs(out)
    assert tool.main([str(dump_path), "--out-dir", str(out), "--force"]) == 0
    captured = capsys.readouterr()
    assert "dmd_optimizer: warning: could not remove the temporary folder" in captured.err
    assert "error" not in captured.err
    assert all((out / name).read_bytes() != old[name] for name in OUTPUTS)  # the new files are in place


def test_force_replaces_all_three_files_and_leaves_no_extra_files(dump_path, tmp_path):
    out = tmp_path / "out"
    old = existing_outputs(out)
    (out / "demo_rom.cROM.old").write_bytes(b"a file of the user")
    assert tool.main([str(dump_path), "--out-dir", str(out), "--force"]) == 0
    assert files_in(out) == ["demo_rom-report.html", "demo_rom.cROM", "demo_rom.cROM.old", "demo_rom.cRP"]
    assert all((out / name).read_bytes() != old[name] for name in OUTPUTS)
    assert (out / "demo_rom.cROM.old").read_bytes() == b"a file of the user"


@pytest.mark.parametrize("force", [[], ["--force"]])
def test_a_folder_with_the_name_of_an_output_file_is_never_replaced(dump_path, tmp_path, capsys, force):
    out = tmp_path / "out"
    (out / "demo_rom.cRP").mkdir(parents=True)
    (out / "demo_rom.cRP" / "child.txt").write_text("keep me")
    (out / "demo_rom-report.html").write_bytes(b"old report")
    assert tool.main([str(dump_path), "--out-dir", str(out)] + force) == 1
    captured = capsys.readouterr()
    assert error_message(captured) == f"{out / 'demo_rom.cRP'} is a folder; the tool replaces files only"
    assert captured.err.count("\n") == 1  # refused before any work
    assert files_in(out) == ["demo_rom-report.html", "demo_rom.cRP"]
    assert (out / "demo_rom.cRP" / "child.txt").read_text() == "keep me"
    assert (out / "demo_rom-report.html").read_bytes() == b"old report"


def test_a_folder_that_appears_during_a_forced_run_is_put_back(dump_path, tmp_path, capsys, monkeypatch):
    out = tmp_path / "out"
    old = existing_outputs(out)
    real = tool.report_html

    def report_and_folder(*arguments):
        (out / "demo_rom.cRP").unlink()
        (out / "demo_rom.cRP").mkdir()
        (out / "demo_rom.cRP" / "child.txt").write_text("keep me")
        return real(*arguments)

    monkeypatch.setattr(tool, "report_html", report_and_folder)
    assert tool.main([str(dump_path), "--out-dir", str(out), "--force"]) == 1
    message = error_message(capsys.readouterr())
    assert message == f"cannot write the output files: {out / 'demo_rom.cRP'} is a folder, not a file"
    assert files_in(out) == sorted(old)
    assert (out / "demo_rom.cRP" / "child.txt").read_text() == "keep me"
    assert (out / "demo_rom.cROM").read_bytes() == old["demo_rom.cROM"]  # put back
    assert (out / "demo_rom-report.html").read_bytes() == old["demo_rom-report.html"]


def test_a_link_that_points_nowhere_counts_as_an_existing_file(dump_path, tmp_path, capsys, monkeypatch):
    out = tmp_path / "out"
    old = existing_outputs(out)
    link = out / "demo_rom.cRP"
    link.unlink()
    try:
        link.symlink_to("missing-target")
    except (OSError, NotImplementedError):
        pytest.skip("this system cannot create symbolic links")
    assert tool.main([str(dump_path), "--out-dir", str(out)]) == 1  # refused without --force
    assert error_message(capsys.readouterr()).endswith("already exists; pass --force to overwrite it")
    failing_replace(monkeypatch, 6)  # the last of the six moves of a forced run fails
    assert tool.main([str(dump_path), "--out-dir", str(out), "--force"]) == 1
    assert error_message(capsys.readouterr()) == "cannot write the output files: simulated failure"
    assert files_in(out) == sorted(old)
    assert link.is_symlink() and str(link.readlink()) == "missing-target"  # the link is back
    assert (out / "demo_rom.cROM").read_bytes() == old["demo_rom.cROM"]
    assert (out / "demo_rom-report.html").read_bytes() == old["demo_rom-report.html"]


def test_a_file_that_appears_while_the_files_are_moved_is_not_overwritten(dump_path, tmp_path, capsys, monkeypatch):
    out = tmp_path / "out"
    real = tool.os.replace

    def replace_and_intruder(source, target):
        if not (out / "demo_rom.cRP").exists():
            (out / "demo_rom.cRP").write_bytes(b"appeared meanwhile")  # just before the first file is installed
        return real(source, target)

    monkeypatch.setattr(tool.os, "replace", replace_and_intruder)
    assert tool.main([str(dump_path), "--out-dir", str(out)]) == 1
    assert error_message(capsys.readouterr()) == f"{out / 'demo_rom.cRP'} already exists; pass --force to overwrite it"
    assert files_in(out) == ["demo_rom.cRP"] and (out / "demo_rom.cRP").read_bytes() == b"appeared meanwhile"


@pytest.mark.parametrize("function", ["listdir", "rmdir"])
def test_a_failing_removal_of_the_empty_folder_keeps_the_error_message(dump_path, tmp_path, capsys, monkeypatch, function):
    out = tmp_path / "out"
    real = getattr(tool.os, function)

    def failing(path, *arguments, **keywords):
        if path == out:
            raise PermissionError("simulated failure")
        return real(path, *arguments, **keywords)

    def broken(*arguments):
        raise tool.OptimizerError("internal check failed: test")

    monkeypatch.setattr(tool.os, function, failing)
    monkeypatch.setattr(tool, "report_html", broken)
    assert tool.main([str(dump_path), "--out-dir", str(out)]) == 1
    captured = capsys.readouterr()
    assert error_message(captured) == "internal check failed: test"
    assert f"dmd_optimizer: warning: could not remove the empty folder {out}: simulated failure" in captured.err
    assert files_in(out) == []


def test_a_file_that_appears_during_the_run_is_not_overwritten(dump_path, tmp_path, capsys, monkeypatch):
    out = tmp_path / "out"
    real = tool.report_html

    def report_and_intruder(*arguments):
        (out / "demo_rom.cRP").write_bytes(b"appeared meanwhile")
        return real(*arguments)

    monkeypatch.setattr(tool, "report_html", report_and_intruder)
    assert tool.main([str(dump_path), "--out-dir", str(out)]) == 1
    assert error_message(capsys.readouterr()).endswith("demo_rom.cRP already exists; pass --force to overwrite it")
    assert files_in(out) == ["demo_rom.cRP"] and (out / "demo_rom.cRP").read_bytes() == b"appeared meanwhile"


def test_two_runs_give_identical_files(dump_path, tmp_path):
    for name in ("one", "two"):
        assert tool.main([str(dump_path), "--out-dir", str(tmp_path / name)]) == 0
    for name in files_in(tmp_path / "one"):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes(), name


def test_help_lists_every_option(capsys):
    with pytest.raises(SystemExit) as stop:
        tool.main(["--help"])
    assert stop.value.code == 0
    text = capsys.readouterr().out
    for option in ("--out-dir", "--rom-name", "--max-vary", "--max-masks", "--min-gain", "--min-lit",
                   "--no-shape-mode", "--force"):
        assert option in text
