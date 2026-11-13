"""Independent check of the tool's output with the real libserum (section 12.3 of the design)."""
import ctypes

import pytest

import dmd_optimizer as tool
from conftest import ROOT
from helpers import blank, draw_digits, write_dump

pytestmark = pytest.mark.libserum

NO_FRAME = 0xFFFFFFFF
SAME_FRAME = 0xFFFFFFFE


class SerumFrame(ctypes.Structure):
    """Serum_Frame_Struc of libserum 2.8.x (src/serum.h)."""

    _fields_ = [
        ("frame", ctypes.c_void_p), ("palette", ctypes.c_void_p), ("rotations", ctypes.c_void_p),
        ("frame32", ctypes.c_void_p), ("width32", ctypes.c_uint32), ("rotations32", ctypes.c_void_p),
        ("rotationsinframe32", ctypes.c_void_p), ("modifiedelements32", ctypes.c_void_p),
        ("frame64", ctypes.c_void_p), ("width64", ctypes.c_uint32), ("rotations64", ctypes.c_void_p),
        ("rotationsinframe64", ctypes.c_void_p), ("modifiedelements64", ctypes.c_void_p),
        ("SerumVersion", ctypes.c_uint32), ("flags", ctypes.c_uint8), ("nocolors", ctypes.c_uint32),
        ("ntriggers", ctypes.c_uint32), ("triggerID", ctypes.c_uint32), ("frameID", ctypes.c_uint32),
        ("rotationtimer", ctypes.c_uint32),
    ]


@pytest.fixture(scope="module")
def library():
    build = ROOT / ".cache" / "libserum" / "build"
    found = sorted(build.glob("libserum*.dylib")) + sorted(build.glob("libserum*.so"))
    if not found:
        pytest.skip("libserum is not built; run tools/build_libserum.sh")
    loaded = ctypes.CDLL(str(found[0]))
    loaded.Serum_Load.restype = ctypes.POINTER(SerumFrame)
    loaded.Serum_Load.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint8]
    loaded.Serum_Colorize.restype = ctypes.c_uint32
    loaded.Serum_Colorize.argtypes = [ctypes.c_char_p]
    loaded.Serum_SetGenerateCRomC.argtypes = [ctypes.c_bool]
    loaded.Serum_Dispose.restype = None
    return loaded


def problems_found(library, dump, analysis, folder, rom_name):
    """Write the project, let libserum identify every dump record, and list what it got wrong."""
    target = folder / rom_name
    target.mkdir(parents=True)
    project = tool.new_project(dump, analysis, rom_name)
    tool.write_project(project, target / f"{rom_name}.cROM", target / f"{rom_name}.cRP")
    active = project.crom["ActiveFrames"]
    predicted = {}
    for number, group in enumerate(analysis.groups):
        for member in group.members.tolist():
            predicted[member] = number
    library.Serum_SetGenerateCRomC(False)
    flag = 1 if dump.height == 32 else 2  # ask for frames 32 or 64 pixels high
    loaded = library.Serum_Load(str(folder).encode(), rom_name.encode(), flag)
    assert loaded, "libserum could not load the project"
    try:
        assert loaded.contents.nocolors == dump.shades
        assert (loaded.contents.width32 if dump.height == 32 else loaded.contents.width64) == dump.width
        last = None
        problems = []
        for record, frame in enumerate(dump.record_frame.tolist()):
            result = library.Serum_Colorize(dump.frames[frame].tobytes())
            expected = predicted[frame]
            if result == SAME_FRAME:
                if expected != last:
                    problems.append((record, "same frame", last, expected))
            elif result == NO_FRAME:
                if active[expected]:
                    problems.append((record, "no frame", None, expected))
            else:
                last = loaded.contents.frameID
                if last != expected:
                    problems.append((record, "other frame", last, expected))
        return problems
    finally:
        library.Serum_Dispose()


def test_libserum_identifies_a_192x64_project_with_sixteen_shades(library, tmp_path):
    def screen(step):
        frame = blank(192, 64)
        frame[2:30, 4:120] = 5
        frame[40:60, 150:190] = 9
        return draw_digits(frame, f"{1000 * (step * step + 7) + 13 * step:06d}", 20, 44, value=15)

    other = blank(192, 64)
    other[10:50, 30:160] = 12
    frames = [screen(step) for step in range(10)]
    dump = tool.read_dumps([write_dump(tmp_path / "big.txt", frames + [other] + frames[:3])])
    analysis = tool.analyze(dump)
    assert [(len(group.members), group.mask) for group in analysis.groups] == [(10, 0), (1, tool.NO_MASK)]
    assert problems_found(library, dump, analysis, tmp_path / "altcolor", "big") == []


@pytest.mark.twister
def test_libserum_identifies_every_twister_frame_as_predicted(library, twister_dump, twister_analysis, tmp_path):
    assert problems_found(library, twister_dump, twister_analysis, tmp_path / "altcolor", "twst_405") == []
