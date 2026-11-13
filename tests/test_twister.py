"""Tests on the real Twister dump and the hand-made Twister project (section 12.2 of the design)."""
import collections

import numpy as np
import pytest

import dmd_optimizer as tool
from conftest import TWISTER_CROM, TWISTER_CRP
from helpers import check_rules, hand_labels

pytestmark = pytest.mark.twister

PIXELS = 128 * 32


def test_dump_facts(twister_dump):
    dump = twister_dump
    assert (dump.width, dump.height, dump.shades) == (128, 32, 4)
    assert len(dump.record_frame) == 14443
    assert len(dump.frames) == 10301
    assert dump.warnings == []
    assert len(np.unique(tool.shape_view(dump.frames), axis=0)) == 6906


def test_reference_project_round_trip(twister_reference, tmp_path):
    project = twister_reference
    counts = {name: project.header[name] for name in ("nFrames", "nCompMasks", "nSprites", "nBackgrounds")}
    assert counts == {"nFrames": 5093, "nCompMasks": 64, "nSprites": 31, "nBackgrounds": 2}
    tool.write_project(project, tmp_path / "copy.cROM", tmp_path / "copy.cRP")
    for original, copy in ((TWISTER_CROM, tmp_path / "copy.cROM"), (TWISTER_CRP, tmp_path / "copy.cRP")):
        assert original.stat().st_size == copy.stat().st_size
        with open(original, "rb") as first, open(copy, "rb") as second:
            while True:
                block = first.read(1 << 24)
                assert block == second.read(1 << 24), f"{copy.name} differs from the reference"
                if not block:
                    break


def test_reference_hashes_are_reproduced(twister_reference):
    crom = twister_reference.crom
    frames = twister_reference.crp["oFrames"].reshape(-1, PIXELS)
    masks = crom["CompMasks"].reshape(-1, PIXELS)
    for number in range(len(frames)):
        mask = None if crom["CompMaskID"][number] == tool.NO_MASK else masks[crom["CompMaskID"][number]]
        expected = int(crom["HashCode"][number])
        assert tool.frame_hash(frames[number], mask, bool(crom["ShapeCompMode"][number])) == expected, number


def test_benchmark_with_default_options(twister_dump, twister_reference, twister_analysis):
    dump, analysis = twister_dump, twister_analysis
    labels = hand_labels(dump.frames, twister_reference)
    assert int((labels >= 0).sum()) == 10275  # the hand-made project identifies all but 26 frames

    merged = different = 0
    for group in analysis.groups:
        if len(group.members) > 1:
            counts = collections.Counter(labels[group.members].tolist())
            merged += len(group.members)
            different += len(group.members) - counts.most_common(1)[0][1]
    share = 100.0 * different / merged
    print(f"\nkept {len(analysis.groups)} of {len(dump.frames)} frames, {len(analysis.masks)} masks, "
          f"grouped differently by hand: {different} of {merged} ({share:.1f}%), "
          f"CRC32 collisions: {len(analysis.collisions)}")

    assert len(analysis.groups) <= 4500
    assert len(analysis.masks) <= 64
    assert share <= 3.5


def test_rules_hold_on_the_twister_dump(twister_dump, twister_analysis):
    check_rules(twister_dump, twister_analysis, tool.Options())  # rules R1 to R6, by exact comparison


def test_a_second_analysis_gives_the_same_result(twister_dump, twister_analysis):
    # Rule R7. The project files and the report are computed from the dump and the analysis
    # alone, so equal analyses give byte-identical files (tests/test_cli.py checks that step).
    first, second = twister_analysis, tool.analyze(twister_dump)
    assert np.array_equal(first.masks, second.masks)
    assert first.mask_saved == second.mask_saved and first.collisions == second.collisions
    assert len(first.groups) == len(second.groups)
    for a, b in zip(first.groups, second.groups):
        assert (a.kept, a.mask, a.shape, a.hash) == (b.kept, b.mask, b.shape, b.hash)
        assert np.array_equal(a.members, b.members) and np.array_equal(a.varying, b.varying)
