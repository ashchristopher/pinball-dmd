# DMD Mask Optimizer Implementation Plan

> For agentic workers: REQUIRED: load the `subagent-driven-development`
> Superpowers skill with `superpowers_skill` (if subagents are available),
> or load `executing-plans` with the same tool to implement this plan.

Goal: Build `dmd_optimizer.py`, a single-file tool that reads VPinMAME DMD dumps and writes a new ColorizingDMD project (`.cROM` + `.cRP`) plus an HTML review report, with frames that show the same screen already merged by comparison masks and shape mode.

Architecture: One Python file with five parts in file order: dump reader, analysis, project files, review report, command line. The analysis finds candidate mask regions from consecutive dump frames, scores each one on the whole dump the way libserum identifies frames, picks at most 64 greedily, then verifies pixel by pixel that every dump frame matches exactly one kept frame. Project files are read and written from one pair of layout tables.

Tech Stack: Python 3.10 or later, numpy 2.0 or later (the only dependency of the tool), pytest for tests, `uv` to run both. libserum 2.8.x (C++, built locally) is used by one opt-in test.

---

## Read this first

**The design is the authority.** It is at `docs/superpowers/specs/2026-11-12-dmd-mask-optimizer-design.md`. Tasks refer to its sections as "design section N". Read sections 2 (background), 7 (analysis) and 8 (file layouts) before starting.

**Every code block in this plan has been run.** The tool, the tests and the helper scripts were built and executed in a scratch copy before this plan was written (Python 3.13, numpy 2.5, macOS). The "Expected" lines are what those runs printed. On the real Twister dump the finished tool keeps 4,116 of 10,301 frames with 43 masks in about one minute, and libserum 2.8.2 identifies every dump frame as the tool predicts.

**If a result differs from the "Expected" line, stop and report it.** Do not change a threshold, a test, a helper or the code to make a step pass. A difference means either a copying mistake or an environment difference, and both need a human decision.

**Type the code as given.** Names are used by later tasks. Do not rename, reorder, "improve" or add features. The implementer makes no design decisions in this plan.

### Words used in this plan

| Word | Meaning |
|---|---|
| Record | One timestamped frame in a dump file |
| Distinct frame | A frame with a pixel pattern not seen earlier in the dump; numbered by first appearance |
| Value view | The pixel values of a frame |
| Shape view | 1 where a pixel is lit, 0 where it is not (Serum's "shape mode") |
| Mask | A set of pixels ignored when frames are compared (Serum's "comparison mask") |
| Setting | A mask (or no mask) together with a view |
| Class | All distinct frames that are equal to a given frame outside a mask, in a view |
| Group | Distinct frames merged into one kept frame; the kept frame is the earliest member |
| Region | A candidate mask found by the analysis |
| Pool | The regions chosen so far; at most 64 |

## Files

| Path | Responsibility |
|---|---|
| `dmd_optimizer.py` | The deliverable. Five parts, in this order: dump reader, analysis, project files, review report, command line |
| `pytest.ini` | Test configuration. Tests that need downloads are opt-in |
| `.gitignore` | Keeps downloads, build caches and output folders out of git |
| `README.md` | How to run the tool and the tests |
| `tests/helpers.py` | Made-up frames, a dump text writer, an independent check of the design's rules, and the benchmark measure |
| `tests/conftest.py` | Session fixtures for the Twister files |
| `tests/test_*.py` | One test file per task |
| `tools/make_sample_dump.py` | Copies the first records of a dump (for the fresh-import check) |
| `tools/compare_projects.py` | Compares two projects field by field |
| `tools/fetch_fixtures.py` | Downloads the Twister files into `fixtures/` and checks their SHA-256 |
| `tools/build_libserum.sh` | Builds libserum 2.8.x into `.cache/libserum` |

`dmd_optimizer.py` grows by appending. Each task from 2 to 17 adds one block of code at the end of the file. Task 17 ends the file with the `if __name__ == "__main__":` block, and nothing is appended after that.

## Conventions

- Run every command from the repository root.
- The test command is `uv run --with pytest --with numpy pytest -q`. It runs the fast tests (under two seconds). Tests that need the Twister files or libserum run only when selected with `-m twister` or `-m libserum`.
- If `uv` is not available, install `numpy>=2.0` and `pytest` into a virtual environment and use `python -m pytest -q` instead.
- "Append to `dmd_optimizer.py`" means: add the code at the end of the file, separated from the existing code by two blank lines. Never edit earlier code.
- `uv run dmd_optimizer.py ...` runs the tool itself. The file's header tells `uv` to install numpy.
- One commit per task, with the message given. Commit locally only. Do not push.

## Testing strategy

1. **Unit tests** for every function, in one test file per task (Tasks 2 to 17). Each task follows the cycle: write the test, see it fail, add the code, see it pass, commit.
2. **Scenario tests** of the whole analysis on made-up dumps with a known answer (Task 13): a counting score, a flickering title, a looping animation, two different screens, brightness changes beyond the limit, and a screen that is blank outside the varying area.
3. **An independent rule check.** `tests/helpers.py` contains `check_rules`, an implementation of rules R1 to R6 of the design by exact comparison that shares no code with the tool. Tasks 12 and 13 run it on every result, Task 13 tests that it rejects wrong results, and Task 19 runs it on the Twister result.
4. **Error handling** is tested where each error is raised: unreadable and unsupported dumps (Tasks 2, 3), damaged project files (Task 14), unusable ROM names (Task 15), option ranges, overwrite refusal, write failures and clean-up after a failed run (Task 17), and the tool's own verification failing (Task 12).
5. **Real data, opt-in** (Task 19): the Twister dump and a hand-made Twister project. Reading and rewriting the hand-made project must reproduce it byte for byte, the benchmark has fixed thresholds, rules R1 to R6 are checked on the result, and a second analysis must give the same result (rule R7).
6. **An independent oracle, opt-in** (Task 21): the real libserum must identify every dump frame as the tool predicts.
7. **Two checks only the user can run** in ColorizingDMD on Windows (Tasks 20 and 22 prepare them).

## Task order and dependencies

Run the tasks in order.

- Tasks 1 to 17 each append to `dmd_optimizer.py`, so they cannot run in parallel. Each needs every task before it.
- Tasks 18 to 22 add new files only. Their dependencies are stated at the top of each task.
- Tasks 19 and 21 need network access. Task 21 also needs git, cmake and a C++ compiler.
- Tasks 20 and 22 end with a hand-off to the user, followed by a comparison that can only happen after the user answers. Do the hand-off, note that the comparison is outstanding, and move on.

---

### Task 1: Project scaffolding and test helpers

Files:
- Create: `pytest.ini`
- Create: `.gitignore`
- Create: `tests/helpers.py`
- Create: `tests/test_smoke.py`
- Create: `dmd_optimizer.py`

The repository holds only `docs/` so far. This task adds the test configuration, the shared test helpers and the first lines of the tool.

`tests/helpers.py` is complete from the start and is used by almost every later task. Three things in it matter:

- `artwork(variant)` draws a fixed screen. Two variants differ over 1,120 pixels, more than a quarter of a 128x32 display, so the tool must treat them as different screens.
- `score_frames`, `flicker_frames`, `animation_frames`, `two_screens`, `bright_frames` and `score_only_frames` build the scenarios of design section 12.1.
- `check_rules` checks rules R1 to R6 of design section 7.2 by exact comparison. It is deliberately independent of the tool. Never change it to make a test pass. Task 13 adds tests that prove it rejects wrong results.
- `hand_labels` is the measure used by the Twister benchmark in Task 19 (design section 12.2).

- [ ] **Step 1: Create the test configuration**

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
pythonpath = . tests
addopts = -m "not twister and not libserum"
markers =
    twister: needs the Twister files (run tools/fetch_fixtures.py first); select with -m twister
    libserum: needs libserum built by tools/build_libserum.sh; select with -m libserum
```

Create `.gitignore`:

```text
__pycache__/
.pytest_cache/
.cache/
.worktrees/
fixtures/
handoff/
*-optimized/
```

- [ ] **Step 2: Create the shared test helpers**

Create `tests/helpers.py`:

```python
"""Shared test helpers: made-up frames, dump text, and an independent check of the design's rules."""
import zlib

import numpy as np

W, H = 128, 32

FONT = {
    "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"],
    "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"],
}


def blank(width=W, height=H):
    return np.zeros((height, width), np.uint8)


def draw_digits(frame, text, x, y, value=3):
    """Draw digits in a 3x5 font, 4 pixels apart, with the top-left corner at (x, y)."""
    for position, char in enumerate(text):
        for row, bits in enumerate(FONT[char]):
            for column, bit in enumerate(bits):
                if bit == "1":
                    frame[y + row, x + 4 * position + column] = value
    return frame


def artwork(variant=0):
    """A fixed screen: a border plus a filled block whose position depends on the variant.

    Two variants differ over 1,120 pixels, which is more than a quarter of the display.
    """
    frame = blank()
    frame[0, :] = frame[-1, :] = 2
    frame[:, 0] = frame[:, -1] = 2
    frame[3:17, 4 + 40 * variant:44 + 40 * variant] = 1
    return frame


def score_frames(count=12, variant=0, x=40, y=22):
    """One screen with a six-digit score that changes in every frame."""
    return [draw_digits(artwork(variant), f"{1000 * (k * k + 7) + 13 * k:06d}", x, y) for k in range(count)]


def flicker_frames(count=10, seed=1, variant=0):
    """One screen with a title whose lit pixels change brightness at random."""
    rng = np.random.default_rng(seed)
    frames = []
    for _ in range(count):
        frame = artwork(variant)
        frame[20:28, 60:100] = rng.integers(1, 4, size=(8, 40))
        frames.append(frame)
    return frames


def animation_frames(count=8, variant=0):
    """One screen with a small block moving inside a corner."""
    frames = []
    for k in range(count):
        frame = artwork(variant)
        frame[20:24, 100 + 2 * k:104 + 2 * k] = 3
        frames.append(frame)
    return frames


def two_screens():
    """Two screens that differ over more than a quarter of the display."""
    other = blank()
    other[8:32, 0:64] = 3
    return [artwork(), other]


def bright_frames():
    """The same lit shape at three brightness levels, over more than a quarter of the display."""
    frames = []
    for level in (1, 2, 3):
        frame = blank()
        frame[4:28, 8:88] = level
        frames.append(frame)
    return frames


def score_only_frames(count=7):
    """A score on a blank screen: nothing lit remains outside the varying area."""
    return [draw_digits(blank(), str(k + 1) * 6, 40, 12) for k in range(count)]


def dump_text(frames, times=None, newline="\n"):
    """The text of a dump holding the given frames (uint8 [height, width] each)."""
    lines = []
    for number, frame in enumerate(frames):
        time = times[number] if times is not None else 1000 + 100 * number
        lines.append(f"0x{time:08x}")
        lines.extend("".join("0123456789abcdef"[value] for value in row) for row in np.asarray(frame))
        lines.append("")
    return (newline.join(lines) + newline).encode("ascii")


def write_dump(path, frames, times=None, newline="\n"):
    path.write_bytes(dump_text(frames, times, newline))
    return path


def check_rules(dump, analysis, options):
    """Check rules R1 to R6 of the design by exact comparison, independently of the tool's own checks.

    R5 is checked up to ties: of two masks with the same area, the checker cannot
    tell which came first in the pool, so it only requires that no setting with a
    smaller mask, no mask at all, or a tighter view reproduces a group.
    """
    frames = dump.frames
    count, pixels = frames.shape
    limit = int(options.max_vary * pixels // 100)
    min_lit = pixels // 128 if options.min_lit is None else options.min_lit
    views = {False: frames, True: (frames > 0).astype(np.uint8)}
    masks = analysis.masks
    none = np.zeros(pixels, bool)
    partitions = {}

    def mask_of(number):
        return none if number == 255 else masks[number]

    def classes(number, shape):
        """A label per frame; equal labels mean equal pixels outside the mask in the view."""
        if (number, shape) not in partitions:
            rows = np.ascontiguousarray(views[shape][:, ~mask_of(number)])
            seen = {}
            labels = [seen.setdefault(row.tobytes(), len(seen)) for row in rows]
            partitions[number, shape] = np.array(labels)
        return partitions[number, shape]

    def reproduces(members, kept, number, shape):
        labels = classes(number, shape)
        same = labels == labels[kept]
        return int(same.sum()) == len(members) and bool(same[members].all())

    def passes(kept, varying, number):
        mask = mask_of(number)
        if mask.sum() + (varying & ~mask).sum() > limit:
            return False
        return number == 255 or (frames[kept] > 0)[~mask].sum() >= min_lit

    assert len(masks) <= min(options.max_masks, 64), "R4: too many masks"
    areas = [int(mask.sum()) for mask in masks]
    seen = np.zeros(count, int)
    used = set()
    saved = [0] * len(masks)
    for group in analysis.groups:
        members = np.asarray(group.members)
        assert group.kept == members[0] == members.min(), "kept frame is not the earliest member"
        assert (np.diff(members) > 0).all(), "members are not in ascending order"
        seen[members] += 1
        varying = (frames[members] != frames[group.kept]).any(axis=0)
        assert np.array_equal(varying, group.varying), "varying map is wrong"
        assert reproduces(members, group.kept, group.mask, group.shape), "R1"
        assert passes(group.kept, varying, group.mask), "R2 or R3"
        data = frames[group.kept][~mask_of(group.mask)]
        if group.shape:
            data = np.minimum(data, 1)
        assert group.hash == zlib.crc32(data.tobytes()), "hash"
        if len(members) == 1:
            assert (group.mask, group.shape) == (255, False), "an unmerged frame has a setting"
            continue
        if group.mask != 255:
            used.add(group.mask)
            saved[group.mask] += len(members) - 1
        if not options.shape_mode:
            assert not group.shape, "shape view used although it is disabled"
        # R5: no setting that comes earlier in step D's order reproduces the group
        earlier = []
        if group.shape:
            earlier.append((group.mask, False))
        if group.mask != 255:
            earlier.append((255, True))
            for number in range(len(masks)):
                if areas[number] < areas[group.mask]:
                    earlier.extend([(number, False), (number, True)])
        for number, shape in earlier:
            if shape and not options.shape_mode:
                continue
            tighter = reproduces(members, group.kept, number, shape) and passes(group.kept, varying, number)
            assert not tighter, "R5: a tighter setting exists"
    assert (seen == 1).all(), "a frame is in no group or in several"
    assert used == set(range(len(masks))), "a mask is unused or missing"
    assert saved == list(analysis.mask_saved), "frames saved per mask"
    assert saved == sorted(saved, reverse=True), "masks are not numbered by frames saved"
    kept = [group.kept for group in analysis.groups]
    assert kept == sorted(kept), "R6: kept frames are not in order of first appearance"


def hand_labels(frames, project):
    """For every frame: the lowest-numbered frame of a project that identifies it, or -1.

    A project frame identifies a frame when both are equal at every pixel outside
    the project frame's mask, in its view (design section 12.2). Pixels are
    compared exactly; no hash is involved.
    """
    crom = project.crom
    pixels = frames.shape[1]
    originals = project.crp["oFrames"].reshape(-1, pixels)
    masks = crom["CompMasks"].reshape(-1, pixels)
    labels = np.full(len(frames), -1, np.int64)
    settings = sorted(set(zip(crom["CompMaskID"].tolist(), crom["ShapeCompMode"].tolist())))
    for mask_number, shape in settings:
        keep = np.ones(pixels, bool) if mask_number == 255 else masks[mask_number] == 0

        def compared(rows):
            rows = rows[:, keep]
            return np.ascontiguousarray(np.minimum(rows, 1) if shape else rows)

        users = np.flatnonzero((crom["CompMaskID"] == mask_number) & (crom["ShapeCompMode"] == shape))
        lowest = {}
        for number, row in zip(users.tolist(), compared(originals[users])):
            lowest.setdefault(row.tobytes(), number)
        for frame, row in enumerate(compared(frames)):
            found = lowest.get(row.tobytes(), -1)
            if found >= 0 and (labels[frame] < 0 or found < labels[frame]):
                labels[frame] = found
    return labels
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_smoke.py`:

```python
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
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `1 error` with `ModuleNotFoundError: No module named 'dmd_optimizer'`.

- [ ] **Step 5: Create the tool with its header**

Create `dmd_optimizer.py`:

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=2.0"]
# ///
"""DMD mask optimizer.

Reads VPinMAME DMD dumps and writes a new ColorizingDMD project (Serum format)
in which frames that show the same screen are already merged by comparison
masks and shape mode.

Design: docs/superpowers/specs/2026-11-12-dmd-mask-optimizer-design.md
"""
from __future__ import annotations

import argparse
import base64
import heapq
import html
import os
import re
import shutil
import struct
import sys
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np


class OptimizerError(Exception):
    """A problem the user can act on. main() prints it and exits with status 1."""
```

Every import is used by a later task. Leave them all in.

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `2 passed`.

- [ ] **Step 7: Commit**

```bash
git add pytest.ini .gitignore tests/helpers.py tests/test_smoke.py dmd_optimizer.py
git commit -m "chore: scaffold the tool, test configuration and test helpers"
```

---

### Task 2: Dump reader: the text of one dump file

Depends on: Task 1 and all tasks before it.

Files:
- Modify: `dmd_optimizer.py` (append)
- Test: `tests/test_dump_parse.py`

Design section 6. A dump is text: a timestamp line `0x` plus 8 hex digits (milliseconds), then one line of hex digits per pixel row, then a blank line. `parse_dump_text` turns the bytes of one file into an array of frames and an array of timestamps.

Reading stops, with a warning, at the first record that is incomplete or holds a character other than a hex digit. If other text follows the rows of a complete record, that record is kept and reading stops after it. Blank lines are ignored everywhere, as the editor ignores them. The width of the first row fixes the frame size: 128 means 128x32 and 192 means 192x64. Any other width, or a first record with too few rows, is an unsupported size.

The tests cover:

- both supported sizes
- CRLF and LF line endings
- hex digits in lower and upper case
- a truncated last record, a short row and a letter beyond `f` (reading stops with a warning naming the record)
- text after a complete record (the record is kept, reading stops), including a line exactly as wide as a pixel row after the first record
- blank lines between the rows of a record (ignored)
- an unsupported size, a file with no frame, and a file cut inside its first record (errors)

- [ ] **Step 1: Write the failing test**

Create `tests/test_dump_parse.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q tests/test_dump_parse.py`
Expected: `14 failed`, with `AttributeError: module 'dmd_optimizer' has no attribute 'parse_dump_text'`.

- [ ] **Step 3: Write the implementation**

Append to `dmd_optimizer.py`:

```python
# ---------------------------------------------------------------------------
# Part 1: dump reader
# ---------------------------------------------------------------------------

SUPPORTED_SIZES = ((128, 32), (192, 64))

_TIMESTAMP = re.compile(rb"^0x([0-9A-Fa-f]{8})[ \t]*$", re.MULTILINE)
_PIXEL_VALUE = np.full(256, 255, np.uint8)
for _value, _char in enumerate(b"0123456789abcdef"):
    _PIXEL_VALUE[_char] = _value
for _value, _char in enumerate(b"ABCDEF", start=10):
    _PIXEL_VALUE[_char] = _value


def parse_dump_text(data, name):
    """Parse the text of one dump file.

    Returns (frames, times, (width, height), warning):
    frames is uint8 [records, width * height], times is uint32 [records] in
    milliseconds, and warning is None or a message saying where reading stopped.
    Blank lines are ignored everywhere, as ColorizingDMD ignores them.
    """
    data = data.replace(b"\r", b"")
    marks = list(_TIMESTAMP.finditer(data))
    size = None
    frames = []
    times = []
    warning = None
    for number, mark in enumerate(marks, start=1):
        end = marks[number].start() if number < len(marks) else len(data)
        lines = [line for line in data[mark.end():end].split(b"\n") if line]
        if size is None:
            if not lines:
                break
            width = len(lines[0])
            rows = 0
            while rows < len(lines) and len(lines[rows]) == width:
                rows += 1
            height = dict(SUPPORTED_SIZES).get(width)
            if height is None or rows < height:
                raise OptimizerError(
                    f"{name}: frame size {width}x{rows} is not supported "
                    "(supported sizes are 128x32 and 192x64)"
                )
            size = (width, height)
        width, height = size
        rows = lines[:height]
        pixels = None
        if len(rows) == height and all(len(row) == width for row in rows):
            pixels = _PIXEL_VALUE[np.frombuffer(b"".join(rows), np.uint8)]
            if (pixels == 255).any():
                pixels = None
        if pixels is None:
            warning = f"{name}: record {number} is incomplete or invalid; reading stopped there"
            break
        frames.append(pixels)
        times.append(int(mark.group(1), 16))
        if len(lines) > height:
            warning = f"{name}: unexpected text after record {number}; reading stopped there"
            break
    if not frames:
        raise OptimizerError(f"{name}: no complete frame found")
    return np.stack(frames), np.array(times, np.uint32), size, warning
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with numpy pytest -q tests/test_dump_parse.py`
Expected: `14 passed`.

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `16 passed`.

- [ ] **Step 5: Commit**

```bash
git add dmd_optimizer.py tests/test_dump_parse.py
git commit -m "feat: parse the text of a dump file"
```

---

### Task 3: Dump reader: durations, distinct frames and several files

Depends on: Task 2 and all tasks before it.

Files:
- Modify: `dmd_optimizer.py` (append)
- Test: `tests/test_dump_read.py`

Design section 6. `read_dumps` reads one or more files into a `Dump`: the distinct frames in order of first appearance, and for every record its distinct frame number, timestamp, duration and file.

The duration rule is ColorizingDMD's: the time to the next record, or 30 ms when there is no next record in the file, when the next timestamp is earlier, or when the gap is over 4000 ms.

The tests cover:

- the duration rule, including a gap of exactly 4000 ms and a single record
- distinct frames numbered by first appearance
- 4 versus 16 shades
- several files joined in the order given, each ending with a 30 ms record
- the warning of a truncated file is kept
- dumps of different sizes and an unreadable file (errors)

- [ ] **Step 1: Write the failing test**

Create `tests/test_dump_read.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q tests/test_dump_read.py`
Expected: `7 failed`, with `AttributeError: module 'dmd_optimizer' has no attribute 'read_dumps'`.

- [ ] **Step 3: Write the implementation**

Append to `dmd_optimizer.py`:

```python
DEFAULT_FRAME_DURATION = 30  # ms, ColorizingDMD's value when a duration is unknown
MAX_FRAME_DURATION = 4000  # ms, longer gaps are treated as unknown


def frame_durations(times):
    """Duration of each record by ColorizingDMD's rule: the time to the next record."""
    durations = np.full(len(times), DEFAULT_FRAME_DURATION, np.uint32)
    if len(times) > 1:
        gap = times[1:].astype(np.int64) - times[:-1].astype(np.int64)
        known = (gap >= 0) & (gap <= MAX_FRAME_DURATION)
        durations[:-1][known] = gap[known]
    return durations


@dataclass
class Dump:
    """One or more dump files of the same ROM, with exact duplicate frames removed."""

    width: int
    height: int
    shades: int  # 4 or 16
    frames: np.ndarray  # uint8 [distinct frames, width * height], in order of first appearance
    record_frame: np.ndarray  # int64 [records]: distinct frame number shown by each record
    record_time: np.ndarray  # uint32 [records]: timestamp in milliseconds
    record_duration: np.ndarray  # uint32 [records]: milliseconds on screen
    record_file: np.ndarray  # int64 [records]: index into files
    files: list
    warnings: list


def read_dumps(paths):
    """Read dump files, in the order given, into one Dump."""
    paths = [str(path) for path in paths]
    size = None
    parts = []
    warnings = []
    for path in paths:
        try:
            data = Path(path).read_bytes()
        except OSError as error:
            raise OptimizerError(f"{path}: cannot read the file ({error.strerror})") from None
        frames, times, file_size, warning = parse_dump_text(data, path)
        if size is None:
            size = file_size
        elif file_size != size:
            raise OptimizerError(
                f"{path}: frame size {file_size[0]}x{file_size[1]} differs from "
                f"{size[0]}x{size[1]} in {paths[0]}"
            )
        if warning:
            warnings.append(warning)
        parts.append((frames, times))
    index = {}
    record_frame = []
    for frames, _ in parts:
        for row in frames:
            record_frame.append(index.setdefault(row.tobytes(), len(index)))
    width, height = size
    distinct = np.frombuffer(b"".join(index), np.uint8).reshape(len(index), width * height)
    return Dump(
        width=width,
        height=height,
        shades=16 if int(distinct.max()) > 3 else 4,
        frames=distinct,
        record_frame=np.array(record_frame, np.int64),
        record_time=np.concatenate([times for _, times in parts]),
        record_duration=np.concatenate([frame_durations(times) for _, times in parts]),
        record_file=np.concatenate(
            [np.full(len(times), number, np.int64) for number, (_, times) in enumerate(parts)]
        ),
        files=paths,
        warnings=warnings,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with numpy pytest -q tests/test_dump_read.py`
Expected: `7 passed`.

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `23 passed`.

- [ ] **Step 5: Commit**

```bash
git add dmd_optimizer.py tests/test_dump_read.py
git commit -m "feat: read dump files into distinct frames with durations"
```

---

### Task 4: Frame hashing as libserum does it

Depends on: Task 3 and all tasks before it.

Files:
- Modify: `dmd_optimizer.py` (append)
- Test: `tests/test_hashing.py`

Design section 2.1. libserum identifies a frame by a CRC32 over its pixel bytes, skipping masked pixels; in shape mode every lit pixel counts as 1. The CRC is the one `zlib.crc32` computes. These functions must reproduce libserum exactly, because the hashes are written into the project file.

This block starts part 2 of the file (analysis).

The tests cover:

- the published CRC-32 check value `0xCBF43926` for "123456789"
- masked pixels are skipped
- shape mode folds every lit value to 1
- a frame with every pixel masked hashes to 0
- the batch function agrees with the single-frame function

- [ ] **Step 1: Write the failing test**

Create `tests/test_hashing.py`:

```python
import numpy as np

import dmd_optimizer as tool


def test_crc32_is_the_standard_one():
    # 0xCBF43926 is the published CRC-32 check value for the ASCII text "123456789"
    pixels = np.frombuffer(b"123456789", np.uint8)
    assert tool.frame_hash(pixels) == 0xCBF43926


def test_masked_pixels_are_skipped():
    pixels = np.array([0, 1, 2, 3, 3, 2, 1, 0], np.uint8)
    mask = np.array([0, 0, 1, 1, 0, 0, 1, 0], np.uint8)
    assert tool.frame_hash(pixels, mask) == tool.frame_hash(np.array([0, 1, 3, 2, 0], np.uint8))


def test_shape_mode_counts_every_lit_pixel_as_one():
    pixels = np.array([0, 1, 2, 3, 15], np.uint8)
    assert tool.frame_hash(pixels, shape=True) == tool.frame_hash(np.array([0, 1, 1, 1, 1], np.uint8))
    assert tool.frame_hash(pixels, shape=True) != tool.frame_hash(pixels)


def test_everything_masked_hashes_to_zero():
    assert tool.frame_hash(np.array([1, 2, 3], np.uint8), np.ones(3, np.uint8)) == 0


def test_frame_hashes_matches_frame_hash_row_by_row():
    frames = np.random.default_rng(0).integers(0, 4, size=(5, 64), dtype=np.uint8)
    mask = np.zeros(64, bool)
    mask[10:30] = True
    for shape in (False, True):
        hashes = tool.frame_hashes(frames, mask, shape)
        assert hashes.dtype == np.uint32
        assert hashes.tolist() == [tool.frame_hash(row, mask, shape) for row in frames]
    assert tool.frame_hashes(frames).tolist() == [tool.frame_hash(row) for row in frames]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q tests/test_hashing.py`
Expected: `5 failed`, with `AttributeError: module 'dmd_optimizer' has no attribute 'frame_hashes'`.

- [ ] **Step 3: Write the implementation**

Append to `dmd_optimizer.py`:

```python
# ---------------------------------------------------------------------------
# Part 2: analysis
# ---------------------------------------------------------------------------

NO_MASK = 255  # mask number stored for a frame that uses no mask


def _compared_pixels(frames, mask, shape):
    """The pixels libserum compares: masked pixels removed, lit/unlit only in shape mode."""
    data = np.asarray(frames, np.uint8)
    if mask is not None:
        data = data[..., np.asarray(mask) == 0]
    if shape:
        data = np.minimum(data, 1)
    return np.ascontiguousarray(data)


def frame_hash(pixels, mask=None, shape=False):
    """CRC32 of one frame as libserum computes it.

    pixels is uint8 [pixels]; mask marks ignored pixels with non-zero values, or
    is None; with shape=True every lit pixel counts as 1.
    """
    return zlib.crc32(_compared_pixels(pixels, mask, shape)) & 0xFFFFFFFF


def frame_hashes(frames, mask=None, shape=False):
    """frame_hash of every row of frames [n, pixels], as uint32 [n]."""
    rows = _compared_pixels(frames, mask, shape)
    return np.fromiter((zlib.crc32(row) for row in rows), np.uint32, len(rows))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with numpy pytest -q tests/test_hashing.py`
Expected: `5 passed`.

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `28 passed`.

- [ ] **Step 5: Commit**

```bash
git add dmd_optimizer.py tests/test_hashing.py
git commit -m "feat: hash frames the way libserum does"
```

---

### Task 5: Padding a set of pixels into a region

Depends on: Task 4 and all tasks before it.

Files:
- Modify: `dmd_optimizer.py` (append)
- Test: `tests/test_padding.py`

Design section 7.3, "Padding a set of pixels into a region". `pad_region` grows a set of pixels by one pixel, snaps it to 2x2 cells, cuts the selected cells into blocks wherever two or more consecutive cell columns (then rows) are empty, and fills the bounding rectangle of each block.

Padding is what makes a mask cover digits the dump never showed, and what keeps the number of different masks small.

The tests cover:

- an empty set
- a single pixel and pixels in the display corners
- two pixels one empty cell apart (one rectangle) and two empty cells apart (two rectangles), for columns and for rows
- an L shape fills its bounding rectangle
- columns are cut before rows
- every result is aligned to the 2-pixel grid

- [ ] **Step 1: Write the failing test**

Create `tests/test_padding.py`:

```python
import numpy as np

import dmd_optimizer as tool
from helpers import H, W


def pad(points):
    pixels = np.zeros((H, W), bool)
    for x, y in points:
        pixels[y, x] = True
    return tool.pad_region(pixels.reshape(-1), W, H).reshape(H, W)


def rectangle(x0, y0, x1, y1):
    expected = np.zeros((H, W), bool)
    expected[y0:y1, x0:x1] = True
    return expected


def test_nothing_selected_gives_an_empty_region():
    assert not pad([]).any()


def test_one_pixel_becomes_a_rectangle_on_the_grid():
    # (10, 10) grows to a plus shape over x 9..11 and y 9..11, which touches cells 4..5 both ways
    assert np.array_equal(pad([(10, 10)]), rectangle(8, 8, 12, 12))


def test_corner_pixel_stays_inside_the_display():
    assert np.array_equal(pad([(0, 0)]), rectangle(0, 0, 2, 2))
    assert np.array_equal(pad([(W - 1, H - 1)]), rectangle(W - 2, H - 2, W, H))


def test_close_pixels_share_one_rectangle():
    # cells 5 and 7 are selected, one empty cell column between them: no cut
    assert np.array_equal(pad([(10, 10), (14, 10)]), rectangle(8, 8, 16, 12))


def test_distant_pixels_get_separate_rectangles():
    # cells 4..5 and 8..9 are selected, two empty cell columns between them: cut
    expected = rectangle(8, 8, 12, 12) | rectangle(16, 8, 20, 12)
    assert np.array_equal(pad([(10, 10), (18, 10)]), expected)


def test_rows_are_cut_like_columns():
    expected = rectangle(8, 8, 12, 12) | rectangle(8, 16, 12, 20)
    assert np.array_equal(pad([(10, 10), (10, 18)]), expected)


def test_an_l_shape_fills_its_bounding_rectangle():
    points = [(x, 10) for x in range(10, 30)] + [(10, y) for y in range(10, 24)]
    # grown, the lines reach x 9..30 and y 9..24, which is cells 4..15 across and 4..12 down
    assert np.array_equal(pad(points), rectangle(8, 8, 32, 26))


def test_columns_are_cut_before_rows():
    # one block on the left, two blocks stacked on the right: three rectangles
    expected = rectangle(8, 8, 12, 12) | rectangle(40, 2, 44, 6) | rectangle(40, 24, 44, 28)
    assert np.array_equal(pad([(10, 10), (42, 4), (42, 26)]), expected)


def test_result_is_aligned_to_the_two_pixel_grid():
    rng = np.random.default_rng(3)
    points = [(int(rng.integers(W)), int(rng.integers(H))) for _ in range(12)]
    cells = pad(points).reshape(H // 2, 2, W // 2, 2)
    assert (cells.all(axis=(1, 3)) == cells.any(axis=(1, 3))).all()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q tests/test_padding.py`
Expected: `9 failed`, with `AttributeError: module 'dmd_optimizer' has no attribute 'pad_region'`.

- [ ] **Step 3: Write the implementation**

Append to `dmd_optimizer.py`:

```python
CELL = 2  # masks are aligned to cells of CELL x CELL pixels


def _segments(occupied):
    """Runs of an occupancy vector, cut where two or more consecutive entries are empty."""
    index = np.flatnonzero(occupied)
    breaks = np.flatnonzero(np.diff(index) > 2)
    starts = np.concatenate(([index[0]], index[breaks + 1]))
    ends = np.concatenate((index[breaks], [index[-1]])) + 1
    return list(zip(starts.tolist(), ends.tolist()))


def _blocks(cells, top, bottom, left, right, found):
    """Append to found the bounding boxes (top, bottom, left, right) of the blocks of cells."""
    part = cells[top:bottom, left:right]
    rows = np.flatnonzero(part.any(axis=1))
    if rows.size == 0:
        return
    columns = np.flatnonzero(part.any(axis=0))
    top, bottom = top + int(rows[0]), top + int(rows[-1]) + 1
    left, right = left + int(columns[0]), left + int(columns[-1]) + 1
    part = cells[top:bottom, left:right]
    pieces = _segments(part.any(axis=0))
    if len(pieces) > 1:
        for start, end in pieces:
            _blocks(cells, top, bottom, left + start, left + end, found)
        return
    pieces = _segments(part.any(axis=1))
    if len(pieces) > 1:
        for start, end in pieces:
            _blocks(cells, top + start, top + end, left, right, found)
        return
    found.append((top, bottom, left, right))


def pad_region(pixels, width, height):
    """pad(V) of the design: a set of pixels padded into rectangles on the 2-pixel grid.

    pixels is bool [width * height]; the result has the same shape.
    """
    selected = np.asarray(pixels, bool).reshape(height, width)
    grown = selected.copy()
    grown[1:] |= selected[:-1]
    grown[:-1] |= selected[1:]
    grown[:, 1:] |= selected[:, :-1]
    grown[:, :-1] |= selected[:, 1:]
    cells = grown.reshape(height // CELL, CELL, width // CELL, CELL).any(axis=(1, 3))
    found = []
    _blocks(cells, 0, cells.shape[0], 0, cells.shape[1], found)
    padded = np.zeros_like(cells)
    for top, bottom, left, right in found:
        padded[top:bottom, left:right] = True
    return np.repeat(np.repeat(padded, CELL, axis=0), CELL, axis=1).reshape(-1)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with numpy pytest -q tests/test_padding.py`
Expected: `9 passed`.

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `37 passed`.

- [ ] **Step 5: Commit**

```bash
git add dmd_optimizer.py tests/test_padding.py
git commit -m "feat: pad pixel sets into rectangles on the 2-pixel grid"
```

---

### Task 6: Options, the shape view and timeline links

Depends on: Task 5 and all tasks before it.

Files:
- Modify: `dmd_optimizer.py` (append)
- Test: `tests/test_options_links.py`

Design sections 5 and 7.1, and step A.1 of section 7.3. `Options` holds the settings of a run and converts the percentage limit into pixels (rounded down). `timeline_links` lists the pairs of distinct frames that follow each other directly in a dump file; step A looks for mask regions only between such pairs.

The tests cover:

- the limit is rounded down (25% of 4,096 is 1,024; 10% is 409)
- the default and an explicit `min_lit`, including 0
- the shape view of values up to 15
- links are unordered, sorted and without duplicates
- frames on either side of a file boundary are not linked

- [ ] **Step 1: Write the failing test**

Create `tests/test_options_links.py`:

```python
import numpy as np

import dmd_optimizer as tool


def make_dump(record_frame, record_file, frames=4):
    records = len(record_frame)
    return tool.Dump(
        width=128, height=32, shades=4,
        frames=np.zeros((frames, 128 * 32), np.uint8),
        record_frame=np.array(record_frame, np.int64),
        record_time=np.arange(records, dtype=np.uint32),
        record_duration=np.full(records, 30, np.uint32),
        record_file=np.array(record_file, np.int64),
        files=["a.txt", "b.txt"], warnings=[],
    )


def test_limit_is_rounded_down():
    assert tool.Options().limit(4096) == 1024
    assert tool.Options(max_vary=10).limit(4096) == 409
    assert tool.Options(max_vary=12.5).limit(4096) == 512
    assert tool.Options(max_vary=0).limit(4096) == 0
    assert tool.Options(max_vary=100).limit(12288) == 12288


def test_lit_pixels_needed():
    assert tool.Options().lit_needed(4096) == 32
    assert tool.Options().lit_needed(192 * 64) == 96
    assert tool.Options(min_lit=7).lit_needed(4096) == 7
    assert tool.Options(min_lit=0).lit_needed(4096) == 0


def test_shape_view():
    frames = np.array([[0, 1, 2, 3], [15, 0, 0, 1]], np.uint8)
    view = tool.shape_view(frames)
    assert view.dtype == np.uint8 and view.tolist() == [[0, 1, 1, 1], [1, 0, 0, 1]]


def test_links_are_unordered_pairs_of_neighbours_within_a_file():
    #            file a: 0 1 0 2 2 | file b: 2 3
    dump = make_dump([0, 1, 0, 2, 2, 2, 3], [0, 0, 0, 0, 0, 1, 1])
    assert tool.timeline_links(dump).tolist() == [[0, 1], [0, 2], [2, 3]]


def test_frames_on_both_sides_of_a_file_boundary_are_not_linked():
    dump = make_dump([0, 1], [0, 1])
    links = tool.timeline_links(dump)
    assert links.shape == (0, 2)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q tests/test_options_links.py`
Expected: `5 failed`, with `AttributeError: module 'dmd_optimizer' has no attribute 'Options'`.

- [ ] **Step 3: Write the implementation**

Append to `dmd_optimizer.py`:

```python
@dataclass
class Options:
    """The settings of a run (section 5 of the design)."""

    max_vary: float = 25.0  # percent of the display that may vary inside a merged group
    max_masks: int = 64  # mask slots the tool may use
    min_gain: int = 5  # frames a candidate must save to be applied
    min_lit: int | None = None  # lit pixels that must remain outside a mask; None = pixels // 128
    shape_mode: bool = True  # allow the shape view

    def limit(self, pixels):
        """The limit of the design in pixels: floor(max_vary / 100 * pixels)."""
        return int(self.max_vary * pixels // 100)

    def lit_needed(self, pixels):
        return pixels // 128 if self.min_lit is None else self.min_lit


def shape_view(frames):
    """The shape view of frames: 1 where a pixel is lit, otherwise 0."""
    return (np.asarray(frames) > 0).astype(np.uint8)


def timeline_links(dump):
    """Unordered pairs of distinct frames that appear one directly after the other in a dump file.

    Returns int64 [links, 2] with the lower frame number first, sorted, without duplicates.
    """
    first = dump.record_frame[:-1]
    second = dump.record_frame[1:]
    keep = (dump.record_file[:-1] == dump.record_file[1:]) & (first != second)
    if not keep.any():
        return np.zeros((0, 2), np.int64)
    pairs = np.stack([np.minimum(first, second)[keep], np.maximum(first, second)[keep]], axis=1)
    return np.unique(pairs, axis=0)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with numpy pytest -q tests/test_options_links.py`
Expected: `5 passed`.

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `42 passed`.

- [ ] **Step 5: Commit**

```bash
git add dmd_optimizer.py tests/test_options_links.py
git commit -m "feat: add options, the shape view and timeline links"
```

---

### Task 7: Candidate regions (step A)

Depends on: Task 6 and all tasks before it.

Files:
- Modify: `dmd_optimizer.py` (append)
- Test: `tests/test_candidate_regions.py`

Design section 7.3, step A. Links are processed from the smallest difference to the largest with a union-find structure. Each set remembers the pixels at which its members differ. When two sets are joined, the padded union of those pixels is recorded as a candidate region. Sets whose union would exceed the limit stay apart.

The earliest frame of a set is always its lowest frame number, because the higher root is attached to the lower one.

The tests cover:

- a changing score yields regions that grow until they cover every changed pixel
- every region is padded and within the limit, with no duplicates
- frames that differ over more than the limit give no region
- identical views give no region
- no links give no region
- a set is not joined when the union would exceed the limit, nor when only the padded union would
- the smallest difference is processed first

- [ ] **Step 1: Write the failing test**

Create `tests/test_candidate_regions.py`:

```python
import numpy as np

import dmd_optimizer as tool
from helpers import H, W, artwork, flicker_frames, score_frames, two_screens

LIMIT = 1024


def regions_of(frames, limit=LIMIT):
    view = np.stack(frames).reshape(len(frames), -1)
    links = np.array([[k, k + 1] for k in range(len(frames) - 1)], np.int64).reshape(-1, 2)
    return view, tool.candidate_regions(view, links, limit, W, H)


def test_a_changing_score_gives_regions_that_grow_to_cover_it():
    view, regions = regions_of(score_frames(12))
    assert regions, "no region found"
    changed = (view != view[0]).any(axis=0)
    assert (regions[-1] | ~changed).all(), "the last region does not cover every changed pixel"
    assert all(int(region.sum()) <= LIMIT for region in regions)
    assert all(region.dtype == bool and region.shape == (W * H,) for region in regions)
    assert len({region.tobytes() for region in regions}) == len(regions), "duplicate regions"


def test_regions_are_padded():
    _, regions = regions_of(score_frames(12))
    for region in regions:
        assert np.array_equal(tool.pad_region(region, W, H) & region, region)
        cells = region.reshape(H // 2, 2, W // 2, 2)
        assert (cells.all(axis=(1, 3)) == cells.any(axis=(1, 3))).all()


def test_frames_that_differ_too_much_give_no_region():
    assert regions_of(two_screens())[1] == []


def test_identical_views_give_no_region():
    shapes = [tool.shape_view(frame) for frame in flicker_frames(6)]
    assert regions_of(shapes)[1] == []


def test_no_links_give_no_region():
    view = np.stack(score_frames(3)).reshape(3, -1)
    assert tool.candidate_regions(view, np.zeros((0, 2), np.int64), LIMIT, W, H) == []


def test_a_set_is_not_joined_when_the_union_would_exceed_the_limit():
    frames = score_frames(6)
    wide = artwork()
    wide[18:30, 4:100] = 3  # differs from the score screen over 1,100 pixels or more
    view, regions = regions_of(frames + [wide])
    changed_by_wide = view[-1] != view[0]
    assert changed_by_wide.sum() > LIMIT
    assert all((region & changed_by_wide).sum() < changed_by_wide.sum() for region in regions)


def test_a_set_is_not_joined_when_only_the_padded_union_exceeds_the_limit():
    base = artwork()
    sparse = base.copy()
    sparse[4:29:4, 10:119:4] = 3  # 196 scattered pixels that form one block of 112 x 28 pixels when padded
    view, regions = regions_of([base, sparse])
    changed = view[0] != view[1]
    assert 0 < int(changed.sum()) <= LIMIT
    assert int(tool.pad_region(changed, W, H).sum()) == 112 * 28 > LIMIT
    assert regions == []


def test_smallest_difference_is_processed_first():
    base = artwork()
    small = base.copy()
    small[24, 60] = 3
    large = base.copy()
    large[20:26, 20:40] = 3
    view = np.stack([base, large, small]).reshape(3, -1)
    links = np.array([[0, 1], [0, 2]], np.int64)
    regions = tool.candidate_regions(view, links, LIMIT, W, H)
    # the link 0-2 differs in one pixel and is processed before the link 0-1
    assert int(regions[0].sum()) == 16
    assert regions[1][24 * W + 60] and regions[1][22 * W + 30]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q tests/test_candidate_regions.py`
Expected: `8 failed`, with `AttributeError: module 'dmd_optimizer' has no attribute 'candidate_regions'`.

- [ ] **Step 3: Write the implementation**

Append to `dmd_optimizer.py`:

```python
def candidate_regions(view, links, limit, width, height):
    """Step A of the design for one view.

    view is uint8 [frames, pixels], links comes from timeline_links, limit is in
    pixels. Returns the candidate regions (bool [pixels] each) in discovery order.
    """
    if len(links) == 0:
        return []
    difference = np.empty(len(links), np.int64)
    for start in range(0, len(links), 2048):
        part = links[start:start + 2048]
        difference[start:start + 2048] = (view[part[:, 0]] != view[part[:, 1]]).sum(axis=1)
    order = np.lexsort((links[:, 1], links[:, 0], difference))
    parent = list(range(len(view)))
    varying = {}  # earliest frame of a set -> bool [pixels]; a missing entry means "no pixel"

    def earliest(frame):
        while parent[frame] != frame:
            parent[frame] = parent[parent[frame]]
            frame = parent[frame]
        return frame

    regions = []
    seen = set()
    for link in order:
        if difference[link] > limit:
            break
        a = earliest(int(links[link, 0]))
        b = earliest(int(links[link, 1]))
        if a == b:
            continue
        joined = view[a] != view[b]
        if a in varying:
            joined |= varying[a]
        if b in varying:
            joined |= varying[b]
        count = int(joined.sum())
        if count > limit:
            continue
        if count:
            region = pad_region(joined, width, height)
            if int(region.sum()) > limit:
                continue
            key = region.tobytes()
            if key not in seen:
                seen.add(key)
                regions.append(region)
        low, high = min(a, b), max(a, b)
        parent[high] = low
        varying.pop(high, None)
        if count:
            varying[low] = joined
    return regions
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with numpy pytest -q tests/test_candidate_regions.py`
Expected: `8 passed`.

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `50 passed`.

- [ ] **Step 5: Commit**

```bash
git add dmd_optimizer.py tests/test_candidate_regions.py
git commit -m "feat: find candidate mask regions from timeline links"
```

---

### Task 8: Labelling frames that are equal outside a mask

Depends on: Task 7 and all tasks before it.

Files:
- Modify: `dmd_optimizer.py` (append)
- Test: `tests/test_labeller.py`

Scoring a candidate means grouping all frames that are equal outside its mask. Doing that by comparing pixels would take minutes per run, so `Labeller` hashes instead. Every 2x2 cell of every frame gets a 64-bit hash, and a table of sums gives the hash of any rectangle of cells in four lookups. The hash of a frame outside a mask is its total minus the hashes of the masked rectangles. Arithmetic wraps around at 64 bits on purpose.

Equal hashes are treated as equal frames here. Step E (Task 12) re-checks every result pixel by pixel, so a hash collision cannot produce a wrong project.

`mask_blocks` returns the rectangles of a padded mask. It raises `ValueError` for a mask that is not a union of filled rectangles, which cannot come out of `pad_region`.

The tests cover:

- labels agree with a brute-force comparison, with a mask, with no mask and with an empty block list
- a mask made of several rectangles
- the cell indices of a mask
- a mask that is not made of filled rectangles is rejected

- [ ] **Step 1: Write the failing test**

Create `tests/test_labeller.py`:

```python
import numpy as np
import pytest

import dmd_optimizer as tool
from helpers import H, W


def brute_labels(view, mask):
    keep = ~mask
    return [tuple(row[keep]) for row in view]


def same_partition(labels, keys):
    pairs = set(zip(labels.tolist(), keys))
    return len(pairs) == len(set(labels.tolist())) == len(set(keys))


def test_labels_group_frames_that_are_equal_outside_the_mask():
    rng = np.random.default_rng(5)
    base = rng.integers(0, 4, size=(6, H, W), dtype=np.uint8)
    frames = np.concatenate([base, base, base])  # 18 frames: every base frame three times
    frames[6:12, 8:16, 20:60] = rng.integers(0, 4, size=(6, 8, 40))  # differ inside the mask only
    frames[12:18, 2, 3] = (frames[12:18, 2, 3] + 1) % 4  # differ outside the mask
    view = frames.reshape(18, -1)
    mask = np.zeros((H, W), bool)
    mask[8:16, 20:60] = True
    mask = mask.reshape(-1)
    labeller = tool.Labeller(view, W, H)
    labels = labeller.labels(tool.mask_blocks(mask, W, H))
    assert same_partition(labels, brute_labels(view, mask))
    assert len(set(labels.tolist())) == 12
    plain = labeller.labels()
    assert same_partition(plain, brute_labels(view, np.zeros(W * H, bool)))
    assert same_partition(labeller.labels([]), brute_labels(view, np.zeros(W * H, bool)))


def test_several_rectangles():
    rng = np.random.default_rng(6)
    frames = np.repeat(rng.integers(0, 4, size=(1, H, W), dtype=np.uint8), 4, axis=0)
    frames[1, 0:4, 0:6] = 3 - frames[0, 0:4, 0:6]
    frames[2, 20:30, 100:128] = 3 - frames[0, 20:30, 100:128]
    frames[3, 10, 50] = 3 - frames[0, 10, 50]
    mask = np.zeros((H, W), bool)
    mask[0:4, 0:6] = True
    mask[20:30, 100:128] = True
    mask = mask.reshape(-1)
    blocks = tool.mask_blocks(mask, W, H)
    assert sorted(blocks) == [(0, 2, 0, 3), (10, 15, 50, 64)]
    labels = tool.Labeller(frames.reshape(4, -1), W, H).labels(blocks)
    assert labels[0] == labels[1] == labels[2] != labels[3]


def test_mask_cells():
    mask = np.zeros((H, W), bool)
    mask[2:4, 6:10] = True
    assert tool.mask_cells(mask.reshape(-1), W, H).tolist() == [1 * 64 + 3, 1 * 64 + 4]


def test_mask_blocks_rejects_a_mask_that_is_not_made_of_filled_rectangles():
    mask = np.zeros((H, W), bool)
    mask[0:8, 0:4] = True
    mask[0:4, 0:12] = True  # an L shape
    with pytest.raises(ValueError):
        tool.mask_blocks(mask.reshape(-1), W, H)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q tests/test_labeller.py`
Expected: `4 failed`, with `AttributeError: module 'dmd_optimizer' has no attribute 'mask_blocks'`.

- [ ] **Step 3: Write the implementation**

Append to `dmd_optimizer.py`:

```python
class Labeller:
    """Labels frames so that equal labels mean "equal outside a mask" in one view.

    Each 2x2 cell of each frame gets a 64-bit hash. The hash of a frame outside a
    mask is the sum of the hashes of its unmasked cells, read from a table of
    sums so that a rectangle costs four lookups per frame. Hash collisions are
    possible in theory, which is why step E re-checks every result pixel by pixel.
    """

    def __init__(self, view, width, height):
        rows, columns = height // CELL, width // CELL
        weights = np.random.default_rng(20261112).integers(
            1, 2**63, size=(rows, CELL, columns, CELL), dtype=np.uint64
        )
        # sums[f, y, x] is the sum of the cell hashes of frame f above row y and left of column x
        self.sums = np.zeros((len(view), rows + 1, columns + 1), np.uint64)
        for start in range(0, len(view), 1024):
            block = view[start:start + 1024].reshape(-1, rows, CELL, columns, CELL)
            cells = (block.astype(np.uint64) * weights).sum(axis=(2, 4))
            self.sums[start:start + 1024, 1:, 1:] = cells.cumsum(axis=1).cumsum(axis=2)
        self.total = self.sums[:, rows, columns].copy()

    def labels(self, blocks=None):
        """A label per frame. blocks lists the masked rectangles in cells, or is None."""
        hashes = self.total
        if blocks:
            hashes = hashes.copy()
            sums = self.sums
            for top, bottom, left, right in blocks:
                hashes -= sums[:, bottom, right] - sums[:, top, right] - sums[:, bottom, left] + sums[:, top, left]
        return np.unique(hashes, return_inverse=True)[1]


def mask_cells(mask, width, height):
    """Indices of the 2x2 cells covered by a mask (bool [pixels]) on the 2-pixel grid."""
    cells = np.asarray(mask, bool).reshape(height // CELL, CELL, width // CELL, CELL)[:, 0, :, 0]
    return np.flatnonzero(cells)


def mask_blocks(mask, width, height):
    """The rectangles (top, bottom, left, right), in cells, that make up a padded mask."""
    cells = np.asarray(mask, bool).reshape(height // CELL, CELL, width // CELL, CELL)[:, 0, :, 0]
    found = []
    _blocks(cells, 0, cells.shape[0], 0, cells.shape[1], found)
    covered = sum((bottom - top) * (right - left) for top, bottom, left, right in found)
    if covered != int(cells.sum()):
        raise ValueError("mask is not a union of filled rectangles on the 2-pixel grid")
    return found
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with numpy pytest -q tests/test_labeller.py`
Expected: `4 passed`.

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `54 passed`.

- [ ] **Step 5: Commit**

```bash
git add dmd_optimizer.py tests/test_labeller.py
git commit -m "feat: label frames that are equal outside a mask"
```

---

### Task 9: The workspace: judging and applying a candidate (step B)

Depends on: Task 8 and all tasks before it.

Files:
- Modify: `dmd_optimizer.py` (append)
- Test: `tests/test_workspace.py`

Design section 7.3, step B. `Workspace` holds the frames and the current groups as three arrays with one entry per distinct frame: `root` (the kept frame of the frame's group), `group_mask` (the pool index of the group's mask, -1 for none) and `group_shape` (whether the group uses the shape view).

`mergeable(candidate)` returns which classes under the candidate may be merged and how many frames that saves. A class is mergeable when it holds two or more current groups, every such group has a mask inside the candidate's mask and a view that is not looser, and the merged class would pass rules R2 (varying area) and R3 (lit pixels outside the mask).

R2 and R3 depend only on which frames are in a class, and classes never change. Their result is therefore computed once per candidate and kept in `candidate.sound`. Because of that cache, a `Candidate` belongs to the workspace that first judged it. Create candidates per workspace and never share one between two workspaces; the tests follow this rule.

The tests cover:

- brightness flicker is merged by the shape view with no mask
- brightness changes beyond the limit are not merged, and are merged when the limit is raised
- a region merges frames that differ inside it and is added to the pool once
- a region too small for the change merges nothing
- frames with nothing lit outside the region are not merged (R3), unless `min_lit` is 0
- a group blocks a region that does not contain its mask, and a region that contains it absorbs the group
- a value-view candidate cannot absorb a shape-view group

- [ ] **Step 1: Write the failing test**

Create `tests/test_workspace.py`:

```python
import numpy as np

import dmd_optimizer as tool
from helpers import H, W, bright_frames, flicker_frames, score_frames, score_only_frames, write_dump


def workspace(tmp_path, frames, **options):
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", frames)])
    return tool.Workspace(dump, tool.Options(**options))


def rectangle(x0, y0, x1, y1):
    mask = np.zeros((H, W), bool)
    mask[y0:y1, x0:x1] = True
    return mask.reshape(-1)


def no_mask_shape():
    return tool.Candidate(region=-1, mask=None, cells=None, blocks=None, area=0, shape=True)


SCORE = rectangle(38, 20, 66, 30)  # covers the six score digits drawn by score_frames


def test_flicker_is_merged_by_the_shape_view_without_a_mask(tmp_path):
    work = workspace(tmp_path, flicker_frames(10))
    candidate = no_mask_shape()
    labels, good, gain = work.mergeable(candidate)
    assert gain == 9
    work.apply(candidate, labels, good)
    assert work.root.tolist() == [0] * 10
    assert work.group_mask.tolist() == [-1] * 10 and work.group_shape.all()
    assert work.pool == []


def test_brightness_changes_beyond_the_limit_are_not_merged(tmp_path):
    work = workspace(tmp_path, bright_frames())
    assert work.mergeable(no_mask_shape())[2] == 0
    assert workspace(tmp_path, bright_frames(), max_vary=50).mergeable(no_mask_shape())[2] == 2


def test_a_region_merges_frames_that_differ_inside_it(tmp_path):
    work = workspace(tmp_path, score_frames(8))
    candidate = work.candidate(0, SCORE, False)
    assert candidate.area == 280 and candidate.blocks == [(10, 15, 19, 33)]
    labels, good, gain = work.mergeable(candidate)
    assert gain == 7
    work.apply(candidate, labels, good)
    assert work.root.tolist() == [0] * 8
    assert work.group_mask.tolist() == [0] * 8 and not work.group_shape.any()
    assert len(work.pool) == 1 and work.pool_of_region == {0: 0}
    assert work.mergeable(candidate)[2] == 0  # nothing left to merge


def test_a_region_too_small_for_the_change_merges_nothing(tmp_path):
    work = workspace(tmp_path, score_frames(8))
    assert work.mergeable(work.candidate(0, rectangle(38, 20, 50, 30), False))[2] == 0


def test_frames_with_nothing_lit_outside_the_region_are_not_merged(tmp_path):
    frames = score_only_frames(7)
    region = rectangle(38, 10, 66, 20)
    strict = workspace(tmp_path, frames)
    assert strict.mergeable(strict.candidate(0, region, False))[2] == 0
    relaxed = workspace(tmp_path, frames, min_lit=0)
    assert relaxed.mergeable(relaxed.candidate(0, region, False))[2] == 6


def test_a_group_blocks_a_region_that_does_not_contain_its_mask(tmp_path):
    first, second = score_frames(2)
    third = first.copy()
    third[6:10, 100:110] = 3  # differs from the first frame only in another place
    work = workspace(tmp_path, [first, second, third])
    score = work.candidate(0, SCORE, False)
    labels, good, gain = work.mergeable(score)
    assert gain == 1
    work.apply(score, labels, good)  # frames 0 and 1 now form a group that uses the score region
    other = work.candidate(1, rectangle(98, 4, 112, 12), False)
    assert work.mergeable(other)[2] == 0  # frame 0 belongs to a group whose mask is not inside it
    both = work.candidate(2, SCORE | rectangle(98, 4, 112, 12), False)
    labels, good, gain = work.mergeable(both)
    assert gain == 1  # the group {0, 1} and frame 2
    work.apply(both, labels, good)
    assert work.root.tolist() == [0, 0, 0] and work.group_mask.tolist() == [1, 1, 1]


def test_a_value_view_region_cannot_absorb_a_shape_view_group(tmp_path):
    frames = flicker_frames(6)
    changed = frames[0].copy()
    changed[6:10, 100:110] = 3
    work = workspace(tmp_path, frames + [changed])
    candidate = no_mask_shape()
    labels, good, _ = work.mergeable(candidate)
    work.apply(candidate, labels, good)  # the six flicker frames form a shape-view group
    region = rectangle(98, 4, 112, 12)
    assert work.mergeable(work.candidate(0, region, False))[2] == 0
    assert work.mergeable(work.candidate(0, region, True))[2] == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q tests/test_workspace.py`
Expected: `7 failed`, with `AttributeError: module 'dmd_optimizer' has no attribute 'Workspace'`.

- [ ] **Step 3: Write the implementation**

Append to `dmd_optimizer.py`:

```python
@dataclass
class Candidate:
    """A setting that could merge groups: a mask, or no mask, together with a view."""

    region: int  # index into the candidate regions, -1 for "no mask"
    mask: np.ndarray | None  # bool [pixels], None for "no mask"
    cells: np.ndarray | None  # indices of the masked cells, None for "no mask"
    blocks: list | None  # the masked rectangles in cells, None for "no mask"
    area: int  # number of masked pixels
    shape: bool  # True for the shape view, False for the value view
    sound: np.ndarray | None = None  # classes that pass rules R2 and R3, filled on first use


class Workspace:
    """The frames and the current groups during steps B to D of the design."""

    def __init__(self, dump, options):
        self.frames = dump.frames
        self.width = dump.width
        self.height = dump.height
        count, pixels = self.frames.shape
        self.limit = options.limit(pixels)
        self.min_lit = options.lit_needed(pixels)
        self.labellers = {False: Labeller(self.frames, self.width, self.height)}
        if options.shape_mode:
            self.labellers[True] = Labeller(shape_view(self.frames), self.width, self.height)
        lit = self.frames > 0
        rows, columns = self.height // CELL, self.width // CELL
        self.lit_cells = (
            lit.reshape(count, rows, CELL, columns, CELL)
            .sum(axis=(2, 4), dtype=np.uint8)
            .reshape(count, rows * columns)
        )
        self.lit_total = lit.sum(axis=1)
        self.root = np.arange(count)  # kept frame of the group each frame belongs to
        self.group_mask = np.full(count, -1)  # pool index of that group's mask, -1 for no mask
        self.group_shape = np.zeros(count, bool)  # True when that group uses the shape view
        self.pool = []  # chosen regions as Candidate objects (their view is not used)
        self.pool_of_region = {}  # candidate region index -> pool index

    def candidate(self, region, mask, shape):
        return Candidate(
            region=region,
            mask=mask,
            cells=mask_cells(mask, self.width, self.height),
            blocks=mask_blocks(mask, self.width, self.height),
            area=int(mask.sum()),
            shape=shape,
        )

    def lit_outside(self, frames, cells):
        """Lit pixels of the given frames outside the masked cells."""
        return self.lit_total[frames] - self.lit_cells[frames][:, cells].sum(axis=1)

    def mergeable(self, candidate):
        """Step B: judge a candidate against the current groups.

        Returns (labels, good, gain): labels is the class of every frame under the
        candidate, good says for every class whether it is mergeable, and gain is
        the number of frames that merging the good classes would save.
        """
        labels = self.labellers[candidate.shape].labels(candidate.blocks)
        count = len(labels)
        classes = int(labels.max()) + 1
        pairs = np.unique(labels * count + self.root)
        groups = np.bincount(pairs // count, minlength=classes)
        good = groups > 1
        if candidate.sound is None:
            # Groups only ever merge, so the classes holding two or more groups now
            # include every class that can hold two or more groups later.
            candidate.sound = np.flatnonzero(self._sound(labels, good, candidate))
        sound = np.zeros(classes, bool)
        sound[candidate.sound] = True
        good &= sound
        allowed = np.ones(count, bool)
        for number, chosen in enumerate(self.pool):
            if candidate.mask is None or (chosen.mask & ~candidate.mask).any():
                allowed &= self.group_mask != number
        if not candidate.shape:
            allowed &= ~self.group_shape
        good &= np.bincount(labels, weights=~allowed, minlength=classes) == 0
        return labels, good, int((groups[good] - 1).sum())

    def _sound(self, labels, wanted, candidate):
        """Rules R2 and R3 for the classes flagged in wanted.

        The answer depends only on which frames are in a class, so it never changes.
        """
        sound = wanted.copy()
        frames = np.flatnonzero(sound[labels])
        if candidate.mask is not None and len(frames):
            dark = self.lit_outside(frames, candidate.cells) < self.min_lit
            sound[labels[frames[dark]]] = False
            frames = frames[sound[labels[frames]]]
        if candidate.shape and len(frames):
            # In the value view the members of a class differ only inside the mask.
            frames = frames[np.argsort(labels[frames], kind="stable")]
            classes = labels[frames]
            starts = np.flatnonzero(np.concatenate(([True], classes[1:] != classes[:-1])))
            rows = self.frames[frames]
            differ = np.maximum.reduceat(rows, starts, axis=0) != np.minimum.reduceat(rows, starts, axis=0)
            if candidate.mask is not None:
                differ &= ~candidate.mask
            sound[classes[starts]] = differ.sum(axis=1) + candidate.area <= self.limit
        return sound

    def apply(self, candidate, labels, good):
        """Merge the groups of every good class into one group with the candidate's setting."""
        chosen = good[labels]
        if not chosen.any():
            return
        number = -1
        if candidate.mask is not None:
            number = self.pool_of_region.get(candidate.region)
            if number is None:
                number = len(self.pool)
                self.pool.append(candidate)
                self.pool_of_region[candidate.region] = number
        earliest = np.full(len(good), len(labels))
        np.minimum.at(earliest, labels[chosen], self.root[chosen])
        self.root[chosen] = earliest[labels[chosen]]
        self.group_mask[chosen] = number
        self.group_shape[chosen] = candidate.shape
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with numpy pytest -q tests/test_workspace.py`
Expected: `7 passed`.

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `61 passed`.

- [ ] **Step 5: Commit**

```bash
git add dmd_optimizer.py tests/test_workspace.py
git commit -m "feat: judge and apply candidate settings against the current groups"
```

---

### Task 10: Choosing masks (step C)

Depends on: Task 9 and all tasks before it.

Files:
- Modify: `dmd_optimizer.py` (append)
- Test: `tests/test_choose_masks.py`

Design section 7.3, step C. First the candidate "no mask, shape view" is applied. Then every region is scored in each enabled view as `gain * (1 - 0.5 * area / limit)` and the candidates wait in a priority queue. The best candidate is taken out, judged afresh against the current groups, and applied only if its fresh score still beats the best score left in the queue; otherwise it goes back with the fresh score.

Gains can only fall as groups merge, so a stale score is always an upper bound and the queue yields the true best candidate each round.

The tests cover:

- a score screen becomes one group with one region
- flicker needs no region
- shape mode switched off
- a family below `min_gain` is left alone, and merged when `min_gain` is lowered
- no region is used when `max_masks` is 0
- three screens use three regions
- the pool never exceeds `max_masks` and the turned-away screen stays unmerged (rule R4)
- the larger family is chosen first

- [ ] **Step 1: Write the failing test**

Create `tests/test_choose_masks.py`:

```python
import dmd_optimizer as tool
from helpers import H, W, flicker_frames, score_frames, write_dump


def choose(tmp_path, frames, **settings):
    """Run steps A to C on a dump of the given frames; returns the workspace."""
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", frames)])
    options = tool.Options(**settings)
    work = tool.Workspace(dump, options)
    regions = tool.candidate_regions(dump.frames, tool.timeline_links(dump), work.limit, W, H)
    tool.choose_masks(work, regions, options)
    return work


def groups(work):
    return len(set(work.root.tolist()))


def three_screens(variants=7):
    """Three different screens, each with its own score in its own place."""
    frames = []
    for screen in range(3):
        frames += score_frames(variants, variant=screen, x=8 + 40 * screen)
    return frames


def test_a_score_screen_becomes_one_group_with_one_region(tmp_path):
    work = choose(tmp_path, score_frames(12))
    assert groups(work) == 1 and len(work.pool) == 1
    changed = (work.frames != work.frames[0]).any(axis=0)
    assert (work.pool[0].mask | ~changed).all()
    assert work.group_mask.tolist() == [0] * 12


def test_flicker_needs_no_region(tmp_path):
    work = choose(tmp_path, flicker_frames(10))
    assert groups(work) == 1 and work.pool == [] and work.group_shape.all()


def test_shape_mode_can_be_switched_off(tmp_path):
    work = choose(tmp_path, flicker_frames(10), shape_mode=False)
    assert not work.group_shape.any()
    assert True not in work.labellers


def test_a_family_below_min_gain_is_left_alone(tmp_path):
    assert groups(choose(tmp_path, score_frames(4))) == 4  # merging would save 3 frames, fewer than 5
    assert groups(choose(tmp_path, score_frames(4), min_gain=3)) == 1


def test_no_region_is_used_when_max_masks_is_zero(tmp_path):
    work = choose(tmp_path, score_frames(12) + flicker_frames(10), max_masks=0)
    assert work.pool == []
    assert groups(work) == 12 + 1


def test_three_screens_use_three_regions(tmp_path):
    work = choose(tmp_path, three_screens())
    assert groups(work) == 3 and len(work.pool) == 3


def test_the_pool_never_exceeds_max_masks(tmp_path):
    work = choose(tmp_path, three_screens(), max_masks=2)
    assert len(work.pool) == 2
    assert groups(work) == 2 + 7  # two screens merged, the third left as seven frames
    assert sorted(set(work.group_mask.tolist())) == [-1, 0, 1]


def test_the_larger_family_is_chosen_first(tmp_path):
    frames = score_frames(7, variant=0, x=8) + score_frames(12, variant=1, x=48)
    work = choose(tmp_path, frames, max_masks=1)
    assert len(work.pool) == 1
    assert groups(work) == 7 + 1  # the twelve-frame family got the only region
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q tests/test_choose_masks.py`
Expected: `8 failed`, with `AttributeError: module 'dmd_optimizer' has no attribute 'choose_masks'`.

- [ ] **Step 3: Write the implementation**

Append to `dmd_optimizer.py`:

```python
def choose_masks(work, regions, options):
    """Step C of the design: merge groups, using at most options.max_masks regions."""
    if options.shape_mode:
        plain = Candidate(region=-1, mask=None, cells=None, blocks=None, area=0, shape=True)
        labels, good, _ = work.mergeable(plain)
        work.apply(plain, labels, good)
    if options.max_masks <= 0 or not regions:
        return
    views = (False, True) if options.shape_mode else (False,)
    candidates = [
        work.candidate(number, region, shape)
        for number, region in enumerate(regions)
        for shape in views
    ]

    def rank(position, gain):
        candidate = candidates[position]
        score = gain * (1.0 - 0.5 * candidate.area / work.limit)
        return (-score, candidate.area, candidate.region, candidate.shape, position)

    queue = []
    for position, candidate in enumerate(candidates):
        gain = work.mergeable(candidate)[2]
        if gain >= options.min_gain:
            heapq.heappush(queue, rank(position, gain))
    while queue:
        position = heapq.heappop(queue)[-1]
        candidate = candidates[position]
        if candidate.region not in work.pool_of_region and len(work.pool) >= options.max_masks:
            continue
        labels, good, gain = work.mergeable(candidate)
        if gain < options.min_gain:
            continue
        fresh = rank(position, gain)
        if queue and queue[0] < fresh:
            heapq.heappush(queue, fresh)
            continue
        work.apply(candidate, labels, good)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with numpy pytest -q tests/test_choose_masks.py`
Expected: `8 passed`.

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `69 passed`.

- [ ] **Step 5: Commit**

```bash
git add dmd_optimizer.py tests/test_choose_masks.py
git commit -m "feat: choose masks greedily by frames saved"
```

---

### Task 11: Tightest setting per group (step D)

Depends on: Task 10 and all tasks before it.

Files:
- Modify: `dmd_optimizer.py` (append)
- Test: `tests/test_tighten.py`

Design section 7.3, step D, and rule R5. Step C may leave a group with a larger mask or a looser view than it needs. `tighten` tries the settings in the design's order (no mask with the shape view, then each pool mask by increasing area with the value view and then the shape view) and gives each merged group the first one under which the class of its kept frame is exactly the group and rules R2 and R3 hold.

"No mask with the value view" is not tried: distinct frames are never equal in the value view, so it can never reproduce a group of two or more.

The tests cover:

- a group moves to the smallest region that still merges it, and its view becomes the value view when that is enough
- of two regions with the same area, the earlier one in the pool wins
- a flicker group keeps no mask and the shape view
- a masked shape-view group loses its mask when the shapes are equal
- single frames are untouched
- without shape mode only value-view settings are tried

- [ ] **Step 1: Write the failing test**

Create `tests/test_tighten.py`:

```python
import numpy as np

import dmd_optimizer as tool
from helpers import H, W, flicker_frames, score_frames, write_dump


def rectangle(x0, y0, x1, y1):
    mask = np.zeros((H, W), bool)
    mask[y0:y1, x0:x1] = True
    return mask.reshape(-1)


SMALL = rectangle(38, 20, 66, 30)  # the score drawn by score_frames
LARGE = rectangle(30, 18, 100, 32)  # contains SMALL


def workspace(tmp_path, frames, **settings):
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", frames)])
    options = tool.Options(**settings)
    return tool.Workspace(dump, options), options


def merge(work, candidate):
    labels, good, _ = work.mergeable(candidate)
    work.apply(candidate, labels, good)


def test_a_group_moves_to_the_smallest_region_that_still_merges_it(tmp_path):
    # screen 0 changes only inside SMALL; screen 1 also changes elsewhere inside LARGE
    wide = []
    for frame in score_frames(6, variant=1):
        frame = frame.copy()
        frame[24:28, 80:90] = frame[22:26, 40:50]
        wide.append(frame)
    work, options = workspace(tmp_path, score_frames(6) + wide)
    merge(work, work.candidate(0, LARGE, True))  # both screens merge under the large region
    merge(work, work.candidate(1, SMALL, False))  # nothing to merge: every frame is in a LARGE group
    assert work.group_mask.tolist() == [0] * 12 and len(work.pool) == 1
    work.pool.append(work.candidate(1, SMALL, False))  # make the small region available to step D
    tool.tighten(work, options)
    assert work.group_mask.tolist() == [1] * 6 + [0] * 6
    assert not work.group_shape.any()  # the value view is enough for both groups


def test_of_two_regions_with_the_same_area_the_earlier_one_in_the_pool_wins(tmp_path):
    left = rectangle(36, 20, 64, 30)  # both cover the score, and both have 280 pixels
    right = SMALL
    assert int(left.sum()) == int(right.sum()) == 280
    for first, second in ((left, right), (right, left)):
        work, options = workspace(tmp_path, score_frames(6))
        merge(work, work.candidate(0, LARGE, False))
        work.pool.append(work.candidate(1, first, False))
        work.pool.append(work.candidate(2, second, False))
        tool.tighten(work, options)
        assert work.group_mask.tolist() == [1] * 6


def test_a_flicker_group_keeps_no_mask_and_the_shape_view(tmp_path):
    work, options = workspace(tmp_path, flicker_frames(8))
    merge(work, tool.Candidate(region=-1, mask=None, cells=None, blocks=None, area=0, shape=True))
    tool.tighten(work, options)
    assert work.group_mask.tolist() == [-1] * 8 and work.group_shape.all()


def test_a_masked_shape_group_loses_the_mask_when_the_shapes_are_equal(tmp_path):
    work, options = workspace(tmp_path, flicker_frames(8))
    merge(work, work.candidate(0, rectangle(56, 18, 104, 30), True))
    assert work.group_mask.tolist() == [0] * 8
    tool.tighten(work, options)
    assert work.group_mask.tolist() == [-1] * 8 and work.group_shape.all()


def test_single_frames_are_untouched(tmp_path):
    work, options = workspace(tmp_path, score_frames(3))
    tool.tighten(work, options)
    assert work.group_mask.tolist() == [-1] * 3 and not work.group_shape.any()


def test_without_shape_mode_only_value_settings_are_tried(tmp_path):
    work, options = workspace(tmp_path, score_frames(6), shape_mode=False)
    merge(work, work.candidate(0, LARGE, False))
    work.pool.append(work.candidate(1, SMALL, False))
    tool.tighten(work, options)
    assert work.group_mask.tolist() == [1] * 6 and not work.group_shape.any()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q tests/test_tighten.py`
Expected: `6 failed`, with `AttributeError: module 'dmd_optimizer' has no attribute 'tighten'`.

- [ ] **Step 3: Write the implementation**

Append to `dmd_optimizer.py`:

```python
def _group_table(work):
    """The current groups as arrays.

    Returns (kept, group, sizes, order, starts, varying): kept frame of every
    group, group number of every frame, group sizes, the frames sorted by group,
    the start of every group in that order, and per group the pixels at which
    its members differ in value.
    """
    kept, group, sizes = np.unique(work.root, return_inverse=True, return_counts=True)
    order = np.argsort(group, kind="stable")
    starts = np.concatenate(([0], np.cumsum(sizes)[:-1]))
    rows = work.frames[order]
    varying = np.maximum.reduceat(rows, starts, axis=0) != np.minimum.reduceat(rows, starts, axis=0)
    return kept, group, sizes, order, starts, varying


def tighten(work, options):
    """Step D of the design: give every merged group the first setting that reproduces it."""
    kept, group, sizes, order, starts, varying = _group_table(work)
    pending = sizes > 1
    settings = [(-1, True)] if options.shape_mode else []
    by_area = sorted(range(len(work.pool)), key=lambda number: (work.pool[number].area, number))
    for number in by_area:
        settings.append((number, False))
        if options.shape_mode:
            settings.append((number, True))
    for number, shape in settings:
        if not pending.any():
            break
        chosen = work.pool[number] if number >= 0 else None
        labels = work.labellers[shape].labels(chosen.blocks if chosen else None)
        class_sizes = np.bincount(labels)
        kept_label = labels[kept]
        together = np.logical_and.reduceat(labels[order] == kept_label[group[order]], starts)
        fits = np.flatnonzero(pending & together & (class_sizes[kept_label] == sizes))
        if not len(fits):
            continue
        if chosen is None:
            passes = varying[fits].sum(axis=1) <= work.limit
        else:
            passes = chosen.area + (varying[fits] & ~chosen.mask).sum(axis=1) <= work.limit
            passes &= work.lit_outside(kept[fits], chosen.cells) >= work.min_lit
        settled = fits[passes]
        frames = np.isin(group, settled)
        work.group_mask[frames] = number
        work.group_shape[frames] = shape
        pending[settled] = False
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with numpy pytest -q tests/test_tighten.py`
Expected: `6 passed`.

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `75 passed`.

- [ ] **Step 5: Commit**

```bash
git add dmd_optimizer.py tests/test_tighten.py
git commit -m "feat: give every merged group its tightest setting"
```

---

### Task 12: Numbering, hashes and verification (step E)

Depends on: Task 11 and all tasks before it.

Files:
- Modify: `dmd_optimizer.py` (append)
- Test: `tests/test_finish.py`

Design section 7.3, step E. `finish` drops regions no group uses, numbers the masks by frames saved, builds the `Group` and `Analysis` objects and calls `verify_groups`.

`verify_groups` is the safety net of the whole tool. It identifies every distinct frame the way libserum does (by CRC32 under every mask and shape flag in use) and then compares pixels. Every frame must match exactly one kept frame, the one of its own group; otherwise it raises `OptimizerError` and no files are written. A hash match with different pixels is a CRC32 collision, which is returned as a warning.

The tests cover:

- groups, mask numbers, shape flags, frames saved and hashes of a mixed dump, checked with `check_rules`
- masks that save equally are numbered by area, and with equal areas in the order they were chosen
- regions that end up unused are dropped
- no masks gives an empty mask array
- verification rejects a frame that matches two kept frames and a frame that matches none
- CRC32 collisions are reported and are not fatal

- [ ] **Step 1: Write the failing test**

Create `tests/test_finish.py`:

```python
import numpy as np
import pytest

import dmd_optimizer as tool
from helpers import H, W, artwork, check_rules, draw_digits, flicker_frames, score_frames, write_dump


def finished(tmp_path, frames, **settings):
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", frames)])
    options = tool.Options(**settings)
    work = tool.Workspace(dump, options)
    regions = tool.candidate_regions(dump.frames, tool.timeline_links(dump), work.limit, W, H)
    tool.choose_masks(work, regions, options)
    tool.tighten(work, options)
    return dump, options, work, tool.finish(work, options)


def test_groups_masks_and_hashes(tmp_path):
    frames = score_frames(7, variant=0, x=8) + flicker_frames(6, variant=2) + score_frames(12, variant=1, x=48)
    dump, options, work, analysis = finished(tmp_path, frames)
    check_rules(dump, analysis, options)
    assert (analysis.limit, analysis.min_lit) == (1024, 32)
    assert [group.kept for group in analysis.groups] == [0, 7, 13]
    assert [len(group.members) for group in analysis.groups] == [7, 6, 12]
    # masks are numbered by frames saved: the twelve-frame family comes first
    assert [group.mask for group in analysis.groups] == [1, tool.NO_MASK, 0]
    assert [group.shape for group in analysis.groups] == [False, True, False]
    assert analysis.mask_saved == [11, 6]
    assert analysis.masks.shape == (2, W * H) and analysis.masks.dtype == bool
    assert analysis.collisions == []
    for group in analysis.groups:
        mask = None if group.mask == tool.NO_MASK else analysis.masks[group.mask]
        assert group.hash == tool.frame_hash(dump.frames[group.kept], mask, group.shape)


def test_masks_that_save_equally_are_numbered_by_area(tmp_path):
    wide = score_frames(7, variant=0, x=8)  # six digits change
    narrow = [draw_digits(artwork(1), f"{11 * (k + 1):02d}", 60, 22) for k in range(7)]  # two digits change
    dump, options, _, analysis = finished(tmp_path, wide + narrow)
    check_rules(dump, analysis, options)
    assert analysis.mask_saved == [6, 6]
    assert int(analysis.masks[0].sum()) < int(analysis.masks[1].sum())
    assert [group.mask for group in analysis.groups] == [1, 0]  # the narrow region is mask 0


def test_masks_that_save_equally_with_equal_areas_keep_the_order_they_were_chosen_in(tmp_path):
    frames = score_frames(7, variant=0, x=8) + score_frames(7, variant=1, x=48)
    dump, options, _, analysis = finished(tmp_path, frames)
    check_rules(dump, analysis, options)
    assert analysis.mask_saved == [6, 6]
    assert int(analysis.masks[0].sum()) == int(analysis.masks[1].sum())
    assert [group.mask for group in analysis.groups] == [0, 1]


def test_regions_that_end_up_unused_are_dropped(tmp_path):
    dump, options, work, _ = finished(tmp_path, score_frames(12))
    unused = np.zeros((H, W), bool)
    unused[2:10, 100:120] = True
    work.pool.append(work.candidate(99, unused.reshape(-1), False))
    analysis = tool.finish(work, options)
    assert len(analysis.masks) == 1
    check_rules(dump, analysis, options)


def test_no_masks_gives_an_empty_mask_array(tmp_path):
    _, _, _, analysis = finished(tmp_path, score_frames(3))
    assert analysis.masks.shape == (0, W * H) and analysis.mask_saved == []
    assert [group.mask for group in analysis.groups] == [tool.NO_MASK] * 3


def test_verification_rejects_a_frame_that_matches_two_kept_frames(tmp_path):
    dump, _, _, analysis = finished(tmp_path, score_frames(12))
    whole = analysis.groups[0]
    halves = [
        tool.Group(kept=0, members=whole.members[:6], mask=whole.mask, shape=False, varying=whole.varying),
        tool.Group(kept=6, members=whole.members[6:], mask=whole.mask, shape=False, varying=whole.varying),
    ]
    with pytest.raises(tool.OptimizerError, match="internal check failed"):
        tool.verify_groups(dump.frames, halves, analysis.masks)


def test_verification_rejects_a_frame_that_matches_no_kept_frame(tmp_path):
    dump, _, _, analysis = finished(tmp_path, score_frames(12))
    whole = analysis.groups[0]
    wrong = [tool.Group(kept=0, members=whole.members, mask=tool.NO_MASK, shape=False, varying=whole.varying)]
    with pytest.raises(tool.OptimizerError, match="frame 1 matches 0 kept frames"):
        tool.verify_groups(dump.frames, wrong, analysis.masks)


def test_crc_collisions_are_reported_not_fatal(tmp_path, monkeypatch):
    dump, _, _, analysis = finished(tmp_path, score_frames(3))
    monkeypatch.setattr(tool.zlib, "crc32", lambda data: 7)  # every frame gets the same hash
    collisions = tool.verify_groups(dump.frames, analysis.groups, analysis.masks)
    assert sorted(collisions) == [(0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1)]
    assert [group.hash for group in analysis.groups] == [7, 7, 7]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q tests/test_finish.py`
Expected: `8 failed`, with `AttributeError: module 'dmd_optimizer' has no attribute 'finish'`.

- [ ] **Step 3: Write the implementation**

Append to `dmd_optimizer.py`:

```python
@dataclass
class Group:
    """Frames merged into one kept frame."""

    kept: int  # distinct frame number of the kept frame, the earliest member
    members: np.ndarray  # distinct frame numbers in ascending order; members[0] == kept
    mask: int  # mask number, or NO_MASK
    shape: bool  # True when the group uses the shape view
    varying: np.ndarray  # bool [pixels]: where the members differ in value
    hash: int = 0  # CRC32 of the kept frame under the group's setting


@dataclass
class Analysis:
    """The result of analysing a dump."""

    options: Options
    limit: int  # pixels that may vary inside a merged group
    min_lit: int  # lit pixels required outside a mask
    masks: np.ndarray  # bool [masks, pixels] in mask-number order
    mask_saved: list  # frames saved by each mask
    groups: list  # Group objects in kept-frame order
    collisions: list  # (distinct frame, kept frame) pairs with equal CRC32 but different pixels


def verify_groups(frames, groups, masks):
    """Check rule R1 the way libserum identifies frames, and set every group's hash.

    Returns the CRC32 collisions found. Raises OptimizerError when a frame does
    not match exactly one kept frame, or matches the kept frame of another group.
    """
    defect = "internal check failed: {}. This is a defect in dmd_optimizer; no files were written."
    own = np.empty(len(frames), np.int64)
    by_setting = {}
    for number, group in enumerate(groups):
        own[group.members] = number
        by_setting.setdefault((group.mask, group.shape), []).append(number)
    matches = np.zeros(len(frames), np.int64)
    collisions = []
    for (mask_number, shape), numbers in sorted(by_setting.items()):
        mask = None if mask_number == NO_MASK else masks[mask_number]
        rows = _compared_pixels(frames, mask, shape)
        hashes = frame_hashes(frames, mask, shape).tolist()
        by_hash = {}
        for number in numbers:
            groups[number].hash = hashes[groups[number].kept]
            by_hash.setdefault(groups[number].hash, []).append(number)
        for frame, value in enumerate(hashes):
            for number in by_hash.get(value, ()):
                kept = groups[number].kept
                if not np.array_equal(rows[frame], rows[kept]):
                    collisions.append((frame, kept))
                    continue
                matches[frame] += 1
                if own[frame] != number:
                    raise OptimizerError(
                        defect.format(f"frame {frame} matches the kept frame {kept} of another group")
                    )
    wrong = np.flatnonzero(matches != 1)
    if len(wrong):
        raise OptimizerError(
            defect.format(f"frame {int(wrong[0])} matches {int(matches[wrong[0]])} kept frames")
        )
    return collisions


def finish(work, options):
    """Step E of the design: number the masks, compute the hashes and verify the result."""
    kept, group, sizes, order, starts, varying = _group_table(work)
    group_masks = work.group_mask[kept]
    used = sorted(set(group_masks[group_masks >= 0].tolist()))
    saved = {number: int((sizes[group_masks == number] - 1).sum()) for number in used}
    ranking = sorted(used, key=lambda number: (-saved[number], work.pool[number].area, number))
    renumbered = {old: new for new, old in enumerate(ranking)}
    if ranking:
        masks = np.stack([work.pool[old].mask for old in ranking])
    else:
        masks = np.zeros((0, work.frames.shape[1]), bool)
    members = np.split(order, starts[1:])
    groups = [
        Group(
            kept=int(kept[number]),
            members=members[number],
            mask=renumbered[int(group_masks[number])] if group_masks[number] >= 0 else NO_MASK,
            shape=bool(work.group_shape[kept[number]]),
            varying=varying[number],
        )
        for number in range(len(kept))
    ]
    collisions = verify_groups(work.frames, groups, masks)
    return Analysis(
        options=options,
        limit=work.limit,
        min_lit=work.min_lit,
        masks=masks,
        mask_saved=[saved[old] for old in ranking],
        groups=groups,
        collisions=collisions,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with numpy pytest -q tests/test_finish.py`
Expected: `8 passed`.

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `83 passed`.

- [ ] **Step 5: Commit**

```bash
git add dmd_optimizer.py tests/test_finish.py
git commit -m "feat: number masks, compute hashes and verify the result"
```

---

### Task 13: `analyze()`: the whole analysis

Depends on: Task 12 and all tasks before it.

Files:
- Modify: `dmd_optimizer.py` (append)
- Test: `tests/test_analyze.py`
- Test: `tests/test_helpers.py`

Design section 7. `analyze` runs steps A to E in order. Candidate regions are collected from the value view first and then from the shape view, without duplicates. The tests in `tests/test_analyze.py` are the scenarios of design section 12.1, and each result is checked with `check_rules`.

`tests/test_helpers.py` tests the test helpers themselves. `check_rules` decides whether a result is right, so it must reject wrong results: a group split in two, a looser view than needed, a result over the limits, a wrong order, a missing frame and a wrong hash. `hand_labels` is the measure used by the Twister benchmark in Task 19.

The tests cover:

- the six scenarios of the design, each alone and all in one dump
- the pool size limit (rule R4)
- shape mode off
- a limit of 0 (nothing merged)
- `max_masks` 0 (shape merging only)
- a score and flicker on the same screen (mask plus shape view)
- frames spread over several files
- progress messages and default options
- two runs give the same result (rule R7)
- `check_rules` accepts a correct result and rejects six kinds of wrong result
- `hand_labels` picks the lowest-numbered project frame that matches exactly

- [ ] **Step 1: Write the failing test**

Create `tests/test_analyze.py`:

```python
import numpy as np

import dmd_optimizer as tool
from helpers import (
    H, W, animation_frames, bright_frames, check_rules, flicker_frames, score_frames,
    score_only_frames, two_screens, write_dump,
)


def analyzed(tmp_path, frames, **settings):
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", frames)])
    options = tool.Options(**settings)
    analysis = tool.analyze(dump, options)
    check_rules(dump, analysis, options)
    return dump, analysis


def settings_of(analysis):
    return [(len(group.members), group.mask, group.shape) for group in analysis.groups]


def test_counting_score(tmp_path):
    dump, analysis = analyzed(tmp_path, score_frames(12))
    assert settings_of(analysis) == [(12, 0, False)]
    changed = (dump.frames != dump.frames[0]).any(axis=0)
    assert (analysis.masks[0] | ~changed).all() and analysis.masks[0].sum() <= 400


def test_flickering_title(tmp_path):
    _, analysis = analyzed(tmp_path, flicker_frames(10))
    assert settings_of(analysis) == [(10, tool.NO_MASK, True)]
    assert len(analysis.masks) == 0


def test_animation_in_a_corner(tmp_path):
    dump, analysis = analyzed(tmp_path, animation_frames(8))
    assert settings_of(analysis) == [(8, 0, False)]
    corner = np.zeros((H, W), bool)
    corner[18:26, 98:122] = True
    assert not (analysis.masks[0] & ~corner.reshape(-1)).any()


def test_two_different_screens_are_both_kept(tmp_path):
    _, analysis = analyzed(tmp_path, two_screens())
    assert settings_of(analysis) == [(1, tool.NO_MASK, False)] * 2


def test_brightness_changes_beyond_the_limit_keep_frames_apart(tmp_path):
    _, analysis = analyzed(tmp_path, bright_frames())
    assert settings_of(analysis) == [(1, tool.NO_MASK, False)] * 3


def test_a_screen_blank_outside_the_varying_area_is_not_merged(tmp_path):
    _, analysis = analyzed(tmp_path, score_only_frames(7))
    assert len(analysis.groups) == 7 and len(analysis.masks) == 0


def test_all_scenarios_in_one_dump(tmp_path):
    frames = (
        score_frames(12) + two_screens()[1:] + flicker_frames(10, variant=1)
        + animation_frames(8, variant=2) + bright_frames() + score_only_frames(7)
    )
    dump, analysis = analyzed(tmp_path, frames)
    sizes = sorted(len(group.members) for group in analysis.groups)
    assert sizes == [1] * 11 + [8, 10, 12]  # 1 other screen, 3 brightness levels, 7 bare scores
    assert len(analysis.masks) == 2  # the score and the animation; the flicker needs none


def test_pool_size_limit(tmp_path):
    frames = []
    for screen in range(3):
        frames += score_frames(7, variant=screen, x=8 + 40 * screen)
    _, analysis = analyzed(tmp_path, frames, max_masks=2)
    assert len(analysis.masks) == 2
    assert sorted(len(group.members) for group in analysis.groups) == [1] * 7 + [7, 7]


def test_without_shape_mode(tmp_path):
    frames = flicker_frames(10) + score_frames(12, variant=1)
    _, analysis = analyzed(tmp_path, frames, shape_mode=False)
    # without the shape view the flicker is merged by a mask over the title instead
    assert settings_of(analysis) == [(10, 1, False), (12, 0, False)]


def test_nothing_is_merged_when_nothing_may_vary(tmp_path):
    _, analysis = analyzed(tmp_path, score_frames(12) + flicker_frames(10), max_vary=0)
    assert len(analysis.groups) == 22 and len(analysis.masks) == 0


def test_only_shape_merging_without_masks(tmp_path):
    _, analysis = analyzed(tmp_path, score_frames(12) + flicker_frames(10), max_masks=0)
    assert len(analysis.groups) == 13 and len(analysis.masks) == 0


def test_score_and_flicker_on_the_same_screen(tmp_path):
    rng = np.random.default_rng(2)
    frames = []
    for frame in score_frames(12):
        frame = frame.copy()
        frame[4:12, 90:120] = rng.integers(1, 4, size=(8, 30))
        frames.append(frame)
    _, analysis = analyzed(tmp_path, frames)
    assert settings_of(analysis) == [(12, 0, True)]


def test_frames_of_several_files(tmp_path):
    first = write_dump(tmp_path / "one.txt", score_frames(12)[:6])
    second = write_dump(tmp_path / "two.txt", score_frames(12)[6:])
    dump = tool.read_dumps([first, second])
    analysis = tool.analyze(dump)
    check_rules(dump, analysis, tool.Options())
    assert settings_of(analysis) == [(12, 0, False)]


def test_progress_messages_and_default_options(tmp_path):
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", score_frames(12))])
    messages = []
    analysis = tool.analyze(dump, progress=messages.append)
    assert analysis.options == tool.Options()
    assert messages[0] == "preparing frames" and messages[-1] == "verifying"
    assert any(message.startswith("choosing masks from ") for message in messages)


def test_the_result_does_not_depend_on_the_run(tmp_path):
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", score_frames(12) + flicker_frames(10))])
    first, second = tool.analyze(dump), tool.analyze(dump)
    assert np.array_equal(first.masks, second.masks)
    assert settings_of(first) == settings_of(second)
    assert [group.hash for group in first.groups] == [group.hash for group in second.groups]
```

Create `tests/test_helpers.py`:

```python
"""The test helpers decide whether results are right, so they are tested too."""
import copy
import types
import zlib

import numpy as np
import pytest

import dmd_optimizer as tool
from helpers import artwork, check_rules, flicker_frames, hand_labels, score_frames, write_dump


@pytest.fixture
def result(tmp_path):
    frames = score_frames(12) + flicker_frames(10, variant=1) + [artwork(2)]
    dump = tool.read_dumps([write_dump(tmp_path / "x.txt", frames)])
    return dump, tool.analyze(dump)


def test_a_correct_result_passes(result):
    check_rules(*result, tool.Options())


def test_a_group_split_in_two_is_rejected(result):
    dump, analysis = result
    whole = analysis.groups[0]
    halves = []
    for members in (whole.members[:6], whole.members[6:]):
        half = copy.copy(whole)
        half.kept, half.members = int(members[0]), members
        half.varying = (dump.frames[members] != dump.frames[members[0]]).any(axis=0)
        half.hash = tool.frame_hash(dump.frames[members[0]], analysis.masks[whole.mask])
        halves.append(half)
    analysis.groups[0:1] = halves
    with pytest.raises(AssertionError, match="R1"):
        check_rules(dump, analysis, tool.Options())


def test_a_view_looser_than_needed_is_rejected(result):
    dump, analysis = result
    group = analysis.groups[0]
    group.shape = True
    kept = dump.frames[group.kept][~analysis.masks[group.mask]]
    group.hash = zlib.crc32(np.minimum(kept, 1).tobytes())
    with pytest.raises(AssertionError, match="R5"):
        check_rules(dump, analysis, tool.Options())


def test_limits_are_enforced(result):
    dump, analysis = result
    with pytest.raises(AssertionError, match="R2 or R3"):
        check_rules(dump, analysis, tool.Options(max_vary=2))  # the score mask covers more than 2%
    with pytest.raises(AssertionError, match="R2 or R3"):
        check_rules(dump, analysis, tool.Options(min_lit=4000))
    with pytest.raises(AssertionError, match="R4"):
        check_rules(dump, analysis, tool.Options(max_masks=0))
    with pytest.raises(AssertionError, match="shape view used although it is disabled"):
        check_rules(dump, analysis, tool.Options(shape_mode=False))


def test_wrong_order_and_missing_frames_are_rejected(result):
    dump, analysis = result
    backwards = copy.copy(analysis)
    backwards.groups = analysis.groups[::-1]
    with pytest.raises(AssertionError, match="R6"):
        check_rules(dump, backwards, tool.Options())
    short = copy.copy(analysis)
    short.groups = analysis.groups[:-1]
    with pytest.raises(AssertionError, match="a frame is in no group or in several"):
        check_rules(dump, short, tool.Options())


def test_a_wrong_hash_is_rejected(result):
    dump, analysis = result
    analysis.groups[2].hash ^= 1
    with pytest.raises(AssertionError, match="hash"):
        check_rules(dump, analysis, tool.Options())


def test_hand_labels_pick_the_lowest_project_frame_that_matches_exactly():
    mask = np.array([0, 0, 0, 0, 1, 1, 1, 1], np.uint8)
    originals = np.array([
        [1, 2, 3, 0, 9, 9, 9, 9],  # frame 0: mask 0, value view
        [3, 3, 0, 0, 1, 1, 0, 0],  # frame 1: no mask, value view
        [3, 3, 0, 0, 1, 1, 0, 0],  # frame 2: a duplicate of frame 1
        [2, 0, 2, 0, 2, 0, 2, 0],  # frame 3: no mask, shape view
    ], np.uint8)
    project = types.SimpleNamespace(
        crom={"CompMaskID": np.array([0, 255, 255, 255], np.uint8),
              "ShapeCompMode": np.array([0, 0, 0, 1], np.uint8),
              "CompMasks": mask},
        crp={"oFrames": originals.reshape(-1)},
    )
    frames = np.array([
        [1, 2, 3, 0, 0, 1, 2, 3],  # equal to frame 0 outside the mask
        [3, 3, 0, 0, 1, 1, 0, 0],  # equal to frames 1 and 2: the lower number wins
        [1, 0, 3, 0, 1, 0, 3, 0],  # the lit shape of frame 3
        [1, 2, 3, 1, 9, 9, 9, 9],  # differs from frame 0 outside the mask
        [0, 0, 0, 0, 0, 0, 0, 0],  # matches nothing
    ], np.uint8)
    assert hand_labels(frames, project).tolist() == [0, 1, 3, -1, -1]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q tests/test_analyze.py tests/test_helpers.py`
Expected: `15 failed, 1 passed, 6 errors`, with `AttributeError: module 'dmd_optimizer' has no attribute 'analyze'`. The one test that passes already exercises `hand_labels`, which needs only the test helpers. The errors come from a fixture that calls `analyze`.

- [ ] **Step 3: Write the implementation**

Append to `dmd_optimizer.py`:

```python
def analyze(dump, options=None, progress=None):
    """Find the groups, their settings and the masks for a dump (section 7 of the design).

    progress, when given, is called with a short message at the start of each stage.
    """
    options = options or Options()
    say = progress or (lambda message: None)
    say("preparing frames")
    work = Workspace(dump, options)
    regions = []
    if options.max_masks > 0 and work.limit > 0:
        say("finding candidate regions")
        links = timeline_links(dump)
        views = [dump.frames]
        if options.shape_mode:
            views.append(shape_view(dump.frames))
        seen = set()
        for view in views:
            for region in candidate_regions(view, links, work.limit, dump.width, dump.height):
                key = region.tobytes()
                if key not in seen:
                    seen.add(key)
                    regions.append(region)
    say(f"choosing masks from {len(regions)} candidate regions")
    choose_masks(work, regions, options)
    say("tightening settings")
    tighten(work, options)
    say("verifying")
    return finish(work, options)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with numpy pytest -q tests/test_analyze.py tests/test_helpers.py`
Expected: `22 passed`.

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `105 passed`.

- [ ] **Step 5: Commit**

```bash
git add dmd_optimizer.py tests/test_analyze.py tests/test_helpers.py
git commit -m "feat: analyse a dump end to end"
```

---

### Task 14: Project files: layout, reading and writing

Depends on: Task 13 and all tasks before it.

Files:
- Modify: `dmd_optimizer.py` (append)
- Test: `tests/test_project_files.py`

Design sections 8.1 to 8.3. `_crom_layout` and `_crp_layout` list every field of the two files in file order with its type and count. The reader and the writer both walk these lists, so the layout is stated once. Values are little-endian with no padding.

Character fields are read as raw bytes (`u1`), never as strings, so that bytes after a terminating zero survive a round trip. A field value may be an int instead of an array, meaning "every element has this value"; the writer streams such fields in chunks so a large new project does not need hundreds of megabytes of memory.

This block starts part 3 of the file (project files).

The tests cover:

- file sizes follow the layout, including sprites and backgrounds
- a 128x32 four-shade frame takes 83,950 bytes and the header 106
- the header bytes
- a project read back is identical and rewrites to identical bytes, including `importedPal`
- an int fills a whole field
- a field of the wrong length is refused
- unsupported header lengths and `is256x64` projects are refused
- short, long and tiny files are refused

- [ ] **Step 1: Write the failing test**

Create `tests/test_project_files.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q tests/test_project_files.py`
Expected: `7 failed, 1 passed`, with `AttributeError: module 'dmd_optimizer' has no attribute '_crom_layout'`. The one test that passes already only checks arithmetic inside the test file.

- [ ] **Step 3: Write the implementation**

Append to `dmd_optimizer.py`:

```python
# ---------------------------------------------------------------------------
# Part 3: project files
# ---------------------------------------------------------------------------

HEADER_LENGTH = 80  # format marker of ColorizingDMD v3.17.3, not a byte count
SPRITE_PIXELS = 256 * 64
_CROM_HEADER = struct.Struct("<64s9IHI")
_HEADER_FIELDS = (
    "name", "header_length", "fWidth", "fHeight", "fWidthX", "fHeightX",
    "nFrames", "noColors", "nCompMasks", "nSprites", "nBackgrounds", "is256x64",
)


def _crom_layout(header):
    """The fields that follow the .cROM header, in file order: (name, dtype, count)."""
    frames = header["nFrames"]
    masks = header["nCompMasks"]
    sprites = header["nSprites"]
    backgrounds = header["nBackgrounds"]
    pixels = header["fWidth"] * header["fHeight"]
    extra = header["fWidthX"] * header["fHeightX"]
    shades = header["noColors"]
    return [
        ("HashCode", "<u4", frames),
        ("ShapeCompMode", "u1", frames),
        ("CompMaskID", "u1", frames),
        ("CompMasks", "u1", masks * pixels),
        ("isExtraFrame", "u1", frames),
        ("cFrames", "<u2", frames * pixels),
        ("cFramesX", "<u2", frames * extra),
        ("DynaMasks", "u1", frames * pixels),
        ("DynaMasksX", "u1", frames * extra),
        ("Dyna4Cols", "<u2", frames * 32 * shades),
        ("Dyna4ColsX", "<u2", frames * 32 * shades),
        ("isExtraSprite", "u1", sprites),
        ("FrameSprites", "u1", frames * 32),
        ("SpriteOriginal", "u1", sprites * SPRITE_PIXELS),
        ("SpriteColored", "<u2", sprites * SPRITE_PIXELS),
        ("SpriteMaskX", "u1", sprites * SPRITE_PIXELS),
        ("SpriteColoredX", "<u2", sprites * SPRITE_PIXELS),
        ("ActiveFrames", "u1", frames),
        ("ColorRotations", "<u2", frames * 4 * 64),
        ("ColorRotationsX", "<u2", frames * 4 * 64),
        ("SpriteDetDwords", "<u4", sprites * 4),
        ("SpriteDetDwordPos", "<u2", sprites * 4),
        ("SpriteDetAreas", "<u2", sprites * 4 * 4),
        ("TriggerID", "<u4", frames),
        ("FrameSpriteBB", "<u2", frames * 32 * 4),
        ("isExtraBackground", "u1", backgrounds),
        ("BackgroundFrames", "<u2", backgrounds * pixels),
        ("BackgroundFramesX", "<u2", backgrounds * extra),
        ("BackgroundID", "<u2", frames),
        ("BackgroundMask", "u1", frames * pixels),
        ("BackgroundMaskX", "u1", frames * extra),
        ("DynaShadowsDirO", "u1", frames * 32),
        ("DynaShadowsColO", "<u2", frames * 32),
        ("DynaShadowsDirX", "u1", frames * 32),
        ("DynaShadowsColX", "<u2", frames * 32),
        ("DynaSprite4Cols", "<u2", sprites * 9 * shades),
        ("DynaSprite4ColsX", "<u2", sprites * 9 * shades),
        ("DynaSpriteMasks", "u1", sprites * SPRITE_PIXELS),
        ("DynaSpriteMasksX", "u1", sprites * SPRITE_PIXELS),
        ("SpriteShapeMode", "u1", sprites),
    ]


def _first(value):
    return int(value) if np.ndim(value) == 0 else int(value[0])


def _crp_layout(header):
    """The fields of the .cRP file, in file order: (name, dtype, count)."""
    frames = header["nFrames"]
    pixels = header["fWidth"] * header["fHeight"]
    return [
        ("name", "u1", 64),
        ("oFrames", "u1", frames * pixels),
        ("activeColSet", "<u4", 64),
        ("ColSets", "<u2", 64 * 16),
        ("acColSet", "u1", 1),
        ("preColSet", "u1", 1),
        ("nameColSet", "u1", 64 * 64),
        ("DrawColMode", "<u4", 1),
        ("Draw_Mode", "u1", 1),
        ("Mask_Sel_Mode", "<i4", 1),
        ("Fill_Mode", "<u4", 1),
        ("Mask_Names", "u1", 64 * 32),
        ("nSections", "<u4", 1),
        ("Section_Firsts", "<u4", 512),
        ("Section_Names", "u1", 512 * 32),
        ("Sprite_Names", "u1", 255 * 32),
        ("Sprite_Col_From_Frame", "<u4", 255),
        ("FrameDuration", "<u4", frames),
        ("SpriteRect", "<u2", 255 * 4),
        ("SpriteRectMirror", "<u4", 255 * 2),
        ("Palette", "<u2", 256 * 64),
        ("acEditColorsS", "<u2", 16),
        ("nImagePosSaves", "<u4", 1),
        ("ImagePosSaveName", "u1", 256 * 64),
        ("ImagePosSave", "<i4", 256 * 16),
        ("PalNames", "u1", 256 * 64),
        ("isImported", "<u4", 1),
        ("importedPal", "u1", lambda fields: _first(fields["isImported"]) * 64 * 3),
        ("TimeElapsed", "<u4", 1),
        ("isPupPack", "<u4", 1),
        ("PupPack", "<u2", 256),
    ]


@dataclass
class Project:
    """A ColorizingDMD project in memory.

    header holds the values of the .cROM header. crom and crp map field names to
    numpy arrays; an int in place of an array means "every element has this value".
    """

    header: dict
    crom: dict
    crp: dict


def _read_fields(stream, layout, path):
    fields = {}
    for name, dtype, count in layout:
        if callable(count):
            count = count(fields)
        data = np.fromfile(stream, dtype, count)
        if len(data) != count:
            raise OptimizerError(f"{path}: the file ends inside the field {name}")
        fields[name] = data
    if stream.read(1):
        raise OptimizerError(f"{path}: unexpected data after the last field")
    return fields


def read_project(crom_path, crp_path):
    """Read a .cROM and its .cRP as written by ColorizingDMD v3.17.3."""
    with open(crom_path, "rb") as stream:
        raw = stream.read(_CROM_HEADER.size)
        if len(raw) < _CROM_HEADER.size:
            raise OptimizerError(f"{crom_path}: the file is too short to be a .cROM")
        header = dict(zip(_HEADER_FIELDS, _CROM_HEADER.unpack(raw)))
        if header["header_length"] != HEADER_LENGTH or header["is256x64"]:
            raise OptimizerError(
                f"{crom_path}: unsupported project format (header length "
                f"{header['header_length']}, is256x64 {header['is256x64']})"
            )
        crom = _read_fields(stream, _crom_layout(header), crom_path)
    with open(crp_path, "rb") as stream:
        crp = _read_fields(stream, _crp_layout(header), crp_path)
    return Project(header=header, crom=crom, crp=crp)


def _write_fields(stream, layout, fields):
    for name, dtype, count in layout:
        if callable(count):
            count = count(fields)
        value = fields[name]
        if np.ndim(value) == 0:
            chunk = np.full(min(count, 1 << 20), value, dtype)
            for start in range(0, count, len(chunk) or 1):
                chunk[:count - start].tofile(stream)
            continue
        data = np.ascontiguousarray(value, dtype)
        if data.size != count:
            raise ValueError(f"field {name} has {data.size} values, expected {count}")
        data.tofile(stream)


def write_project(project, crom_path, crp_path):
    """Write a project as a .cROM and a .cRP in the layout of ColorizingDMD v3.17.3."""
    header = project.header
    with open(crom_path, "wb") as stream:
        stream.write(_CROM_HEADER.pack(*(header[name] for name in _HEADER_FIELDS)))
        _write_fields(stream, _crom_layout(header), project.crom)
    with open(crp_path, "wb") as stream:
        _write_fields(stream, _crp_layout(header), project.crp)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with numpy pytest -q tests/test_project_files.py`
Expected: `8 passed`.

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `113 passed`.

- [ ] **Step 5: Commit**

```bash
git add dmd_optimizer.py tests/test_project_files.py
git commit -m "feat: read and write ColorizingDMD project files"
```

---

### Task 15: Building a new project from an analysis

Depends on: Task 14 and all tasks before it.

Files:
- Modify: `dmd_optimizer.py` (append)
- Test: `tests/test_new_project.py`

Design sections 8.2 (last column), 8.3 and 8.4. `new_project` fills the identification fields from the analysis and gives every other field the value ColorizingDMD gives it on a fresh import: colourised frames in the default orange ramp, no dynamic masks, no sprites, no backgrounds.

The duration of a kept frame is the longest duration of any record that shows a member of its group. A kept frame shorter than 15 ms is marked inactive, as the editor does.

`check_rom_name` enforces the ROM name rule of design section 5: 1 to 63 letters, digits, `_`, `-` or `.`, not starting or ending with `.`, and not a Windows device name. The name is stored in a single-byte field and is also used as a file name on Windows.

The tests cover:

- the default colours for 4 and 16 shades
- the header and the identification fields
- every other field as after a fresh import
- mask names and their 30-byte limit
- the longest duration of the group, and inactive short frames
- the sizes of the written files
- 192x64 with 16 shades
- unusable and usable ROM names

- [ ] **Step 1: Write the failing test**

Create `tests/test_new_project.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q tests/test_new_project.py`
Expected: `27 failed`, with `AttributeError: module 'dmd_optimizer' has no attribute 'check_rom_name'`.

- [ ] **Step 3: Write the implementation**

Append to `dmd_optimizer.py`:

```python
SKIP_FRAME_DURATION = 15  # ms; the editor marks shorter frames inactive until they are coloured


_ROM_NAME = re.compile(r"[A-Za-z0-9_-]([A-Za-z0-9_.-]{0,61}[A-Za-z0-9_-])?")
_WINDOWS_DEVICES = {"CON", "PRN", "AUX", "NUL"} | {f"{port}{n}" for port in ("COM", "LPT") for n in range(1, 10)}


def check_rom_name(name):
    """Raise OptimizerError unless name can be stored in a project and used as a file name on any system."""
    if not _ROM_NAME.fullmatch(name) or name.split(".")[0].upper() in _WINDOWS_DEVICES:
        raise OptimizerError(
            f"ROM name {name!r} is not usable: use 1 to 63 letters, digits, '_', '-' or '.', "
            "not starting or ending with '.', and not a Windows device name such as NUL; "
            "--rom-name sets another name"
        )


def default_colours(shades):
    """The RGB565 orange ramp ColorizingDMD gives a freshly imported frame."""
    level = (31 * np.arange(shades)) // (shades - 1)
    return ((level << 11) | (level << 5)).astype(np.uint16)


def mask_name(number, mask, saved):
    """The name stored for a mask, at most 30 bytes."""
    percent = int(mask.sum() * 100 / mask.size + 0.5)
    return f"auto-{number:02d} {percent}% {saved} frames"[:30]


def kept_durations(dump, analysis):
    """Duration of every kept frame: the longest duration of any record showing its group."""
    longest = np.zeros(len(dump.frames), np.uint32)
    np.maximum.at(longest, dump.record_frame, dump.record_duration)
    return np.array([longest[group.members].max() for group in analysis.groups], np.uint32)


def new_project(dump, analysis, rom_name):
    """Build the project for an analysis, with every other value as after a fresh import."""
    check_rom_name(rom_name)
    width, height = dump.width, dump.height
    groups = analysis.groups
    kept = np.array([group.kept for group in groups], np.int64)
    colours = default_colours(dump.shades)
    durations = kept_durations(dump, analysis)
    header = {
        "name": rom_name.encode("ascii"),
        "header_length": HEADER_LENGTH,
        "fWidth": width,
        "fHeight": height,
        "fWidthX": width * 2 if height == 32 else width // 2,
        "fHeightX": 64 if height == 32 else 32,
        "nFrames": len(groups),
        "noColors": dump.shades,
        "nCompMasks": len(analysis.masks),
        "nSprites": 0,
        "nBackgrounds": 0,
        "is256x64": 0,
    }
    crom = {name: 0 for name, _, _ in _crom_layout(header)}
    crom.update(
        HashCode=np.array([group.hash for group in groups], np.uint32),
        ShapeCompMode=np.array([group.shape for group in groups], np.uint8),
        CompMaskID=np.array([group.mask for group in groups], np.uint8),
        CompMasks=analysis.masks.astype(np.uint8).reshape(-1),
        cFrames=colours[dump.frames[kept]].reshape(-1),
        DynaMasks=255,
        DynaMasksX=255,
        FrameSprites=255,
        ActiveFrames=(durations >= SKIP_FRAME_DURATION).astype(np.uint8),
        TriggerID=0xFFFFFFFF,
        FrameSpriteBB=np.tile(np.array([0, 0, width - 1, height - 1], np.uint16), len(groups) * 32),
        BackgroundID=0xFFFF,
        BackgroundMask=1,
        BackgroundMaskX=1,
    )
    names = np.zeros((64, 32), np.uint8)
    for number, mask in enumerate(analysis.masks):
        text = mask_name(number, mask, analysis.mask_saved[number]).encode("ascii")
        names[number, :len(text)] = np.frombuffer(text, np.uint8)
    palette = np.zeros(256 * 64, np.uint16)
    palette[:dump.shades] = colours
    edit_colours = np.zeros(16, np.uint16)
    edit_colours[:dump.shades] = colours
    stored_name = np.zeros(64, np.uint8)
    stored_name[:len(header["name"])] = np.frombuffer(header["name"], np.uint8)
    crp = {name: 0 for name, _, _ in _crp_layout(header)}
    crp.update(
        name=stored_name,
        oFrames=dump.frames[kept].reshape(-1),
        Mask_Names=names.reshape(-1),
        FrameDuration=durations,
        Palette=palette,
        acEditColorsS=edit_colours,
    )
    return Project(header=header, crom=crom, crp=crp)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with numpy pytest -q tests/test_new_project.py`
Expected: `27 passed`.

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `140 passed`.

- [ ] **Step 5: Commit**

```bash
git add dmd_optimizer.py tests/test_new_project.py
git commit -m "feat: build a new project from an analysis"
```

---

### Task 16: Review report

Depends on: Task 15 and all tasks before it.

Files:
- Modify: `dmd_optimizer.py` (append)
- Test: `tests/test_report.py`

Design section 9. `report_html` returns one self-contained HTML document. Pictures are 8-bit palette PNGs written by `png_image` with `zlib` and embedded as data URLs. On a kept frame, pixels at which the members differ are drawn in a cyan ramp and the inner edge of the mask in blue.

`summarize` returns the summary numbers; the command line prints the same numbers.

This block starts part 4 of the file (review report).

The tests cover:

- the PNG encoder, chunk by chunk
- the summary numbers and the options table
- one section per mask and one for shape mode with no mask, largest group first
- the report is self-contained
- the review-first list is ordered by varying area
- a dump with nothing merged
- no shape section without shape-only groups
- no warnings
- warnings for short frames, CRC32 collisions and truncated dumps
- the ROM name is HTML-escaped

- [ ] **Step 1: Write the failing test**

Create `tests/test_report.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q tests/test_report.py`
Expected: `10 failed`, with `AttributeError: module 'dmd_optimizer' has no attribute 'png_image'`.

- [ ] **Step 3: Write the implementation**

Append to `dmd_optimizer.py`:

```python
# ---------------------------------------------------------------------------
# Part 4: review report
# ---------------------------------------------------------------------------

REVIEW_FIRST = 20  # groups listed in the review-first section
MEMBERS_SHOWN = 3  # other members pictured beside a kept frame

_STYLE = """
body { font-family: sans-serif; margin: 1.5em; background: #f4f4f4; color: #111; }
table { border-collapse: collapse; margin-bottom: 1em; }
td, th { border: 1px solid #bbb; padding: 0.2em 0.6em; text-align: left; }
img { image-rendering: pixelated; background: #000; display: block; }
details { background: #fff; border: 1px solid #bbb; margin: 0.6em 0; padding: 0.4em 0.8em; }
summary { font-weight: bold; cursor: pointer; }
.group { border-top: 1px solid #ddd; margin-top: 0.8em; padding-top: 0.4em; }
.row { display: flex; flex-wrap: wrap; gap: 0.8em; }
figure { margin: 0; }
figcaption { font-size: 0.8em; color: #444; }
"""


def png_image(indexed, palette):
    """An 8-bit palette PNG. indexed is uint8 [height, width]; palette is a list of (r, g, b)."""

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    height, width = indexed.shape
    rows = np.concatenate([np.zeros((height, 1), np.uint8), indexed.astype(np.uint8)], axis=1)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0))
        + chunk(b"PLTE", bytes(value for colour in palette for value in colour))
        + chunk(b"IDAT", zlib.compress(rows.tobytes(), 9))
        + chunk(b"IEND", b"")
    )


def _palette(shades):
    """Palette of the report pictures: frame shades, the same shades marked as varying, mask outline."""
    top = shades - 1
    plain = [(255 * value // top, 127 * value // top, 0) for value in range(shades)]
    marked = [(60 * value // top, 110 + 145 * value // top, 150 + 105 * value // top) for value in range(shades)]
    return plain + marked + [(90, 120, 255)]


def _outline(mask):
    """The pixels on the inner edge of a mask given as bool [height, width]."""
    inside = mask.copy()
    inside[1:] &= mask[:-1]
    inside[:-1] &= mask[1:]
    inside[:, 1:] &= mask[:, :-1]
    inside[:, :-1] &= mask[:, 1:]
    inside[0] = inside[-1] = False
    inside[:, 0] = inside[:, -1] = False
    return mask & ~inside


def summarize(dump, analysis):
    """The summary numbers of a run, in the order they are shown."""
    groups = analysis.groups
    return {
        "dump files read": len(dump.files),
        "frames read": len(dump.record_frame),
        "distinct frames": len(dump.frames),
        "frames kept": len(groups),
        "frames kept unmerged": sum(1 for group in groups if len(group.members) == 1),
        "masks used": len(analysis.masks),
        "frames merged by shape mode alone": sum(
            len(group.members) - 1 for group in groups if group.mask == NO_MASK
        ),
    }


def report_html(dump, analysis, rom_name):
    """The review report as one self-contained HTML document."""
    width, height, shades = dump.width, dump.height, dump.shades
    pixels = width * height
    palette = _palette(shades)
    groups = analysis.groups
    durations = kept_durations(dump, analysis)
    frames_seen, first_record = np.unique(dump.record_frame, return_index=True)
    first_time = np.zeros(len(dump.frames), np.uint32)
    first_time[frames_seen] = dump.record_time[first_record]
    position = {group.kept: number for number, group in enumerate(groups)}

    def picture(indexed):
        data = base64.b64encode(png_image(indexed.reshape(height, width), palette)).decode("ascii")
        return f'<img src="data:image/png;base64,{data}" width="{width * 3}" height="{height * 3}" alt="">'

    def mask_of(group):
        return analysis.masks[group.mask] if group.mask != NO_MASK else np.zeros(pixels, bool)

    def varying_area(group):
        mask = mask_of(group)
        return int(mask.sum() + (group.varying & ~mask).sum())

    def group_block(number):
        group = groups[number]
        mask = mask_of(group)
        kept = dump.frames[group.kept] + shades * group.varying
        edge = _outline(mask.reshape(height, width)).reshape(-1) & ~group.varying
        kept[edge] = 2 * shades
        area = varying_area(group)
        share = 100 * area // analysis.limit if analysis.limit else 0
        figures = [
            f"<figure>{picture(kept)}<figcaption>kept frame {number}, first shown at "
            f"0x{first_time[group.kept]:08x}</figcaption></figure>"
        ]
        for member in group.members[1:1 + MEMBERS_SHOWN]:
            figures.append(
                f"<figure>{picture(dump.frames[member])}<figcaption>merged frame, first shown at "
                f"0x{first_time[member]:08x}</figcaption></figure>"
            )
        return (
            f'<div class="group" id="frame-{number}"><p>Frame {number}: {len(group.members)} frames '
            f'merged, shape mode {"on" if group.shape else "off"}, varying area {area} pixels '
            f"({share}% of the limit).</p><div class=\"row\">{''.join(figures)}</div></div>"
        )

    def section(anchor, title, numbers, extra=""):
        numbers = sorted(numbers, key=lambda number: (-len(groups[number].members), number))
        blocks = "".join(group_block(number) for number in numbers)
        return f'<details id="{anchor}"><summary>{title}</summary>{extra}{blocks}</details>'

    merged = [number for number, group in enumerate(groups) if len(group.members) > 1]
    out = [
        "<!doctype html><html><head><meta charset=\"utf-8\">",
        f"<title>DMD mask optimizer report for {html.escape(rom_name)}</title>",
        f"<style>{_STYLE}</style></head><body>",
        f"<h1>DMD mask optimizer report for {html.escape(rom_name)}</h1>",
        "<h2>Summary</h2><table>",
    ]
    for label, value in summarize(dump, analysis).items():
        out.append(f"<tr><th>{label}</th><td>{value}</td></tr>")
    options = analysis.options
    for label, value in (
        ("--max-vary", f"{options.max_vary:g}% ({analysis.limit} pixels)"),
        ("--max-masks", options.max_masks),
        ("--min-gain", options.min_gain),
        ("--min-lit", f"{analysis.min_lit} pixels"),
        ("shape mode", "on" if options.shape_mode else "off"),
    ):
        out.append(f"<tr><th>{label}</th><td>{value}</td></tr>")
    out.append("</table><p>Dump files: " + html.escape(", ".join(dump.files)) + "</p>")

    out.append("<h2>Warnings</h2>")
    warnings = [html.escape(warning) for warning in dump.warnings]
    for frame, kept in analysis.collisions:
        warnings.append(
            f"The frame first shown at 0x{first_time[frame]:08x} has the same CRC32 as kept frame "
            f"{position[kept]} under that frame's mask and shape mode, but different pixels. "
            "libserum cannot tell the two apart."
        )
    for number in np.flatnonzero(durations < SKIP_FRAME_DURATION):
        warnings.append(
            f"Kept frame {number} is shown for {durations[number]} ms. The editor marks frames "
            f"under {SKIP_FRAME_DURATION} ms inactive until they are coloured."
        )
    if warnings:
        out.append("<ul>" + "".join(f"<li>{warning}</li>" for warning in warnings) + "</ul>")
    else:
        out.append("<p>No warnings.</p>")

    if not merged:
        out.append("<h2>Merged groups</h2><p>No frames were merged.</p>")
    else:
        largest = sorted(merged, key=lambda number: (-varying_area(groups[number]), number))[:REVIEW_FIRST]
        out.append(f"<h2>The {len(largest)} merged groups with the largest varying area</h2><ol>")
        for number in largest:
            share = 100 * varying_area(groups[number]) // analysis.limit if analysis.limit else 0
            out.append(
                f'<li><a href="#frame-{number}">Frame {number}</a>: {share}% of the limit, '
                f"{len(groups[number].members)} frames merged</li>"
            )
        out.append("</ol><h2>Merged groups by mask</h2>")
        for mask_number, mask in enumerate(analysis.masks):
            numbers = [number for number in merged if groups[number].mask == mask_number]
            frames = sum(len(groups[number].members) for number in numbers)
            name = mask_name(mask_number, mask, analysis.mask_saved[mask_number])
            title = (
                f"Mask {mask_number} ({html.escape(name)}): covers {int(mask.sum())} pixels, "
                f"{len(numbers)} groups, {frames} frames merged into {len(numbers)}"
            )
            shown = np.where(mask, 2 * shades, 0).astype(np.uint8)
            out.append(section(f"mask-{mask_number}", title, numbers, picture(shown)))
        numbers = [number for number in merged if groups[number].mask == NO_MASK]
        if numbers:
            frames = sum(len(groups[number].members) for number in numbers)
            title = f"Shape mode with no mask: {len(numbers)} groups, {frames} frames merged into {len(numbers)}"
            out.append(section("shape-only", title, numbers))
    out.append("</body></html>")
    return "\n".join(out)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with numpy pytest -q tests/test_report.py`
Expected: `10 passed`.

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `150 passed`.

- [ ] **Step 5: Commit**

```bash
git add dmd_optimizer.py tests/test_report.py
git commit -m "feat: write the HTML review report"
```

---

### Task 17: Command line

Depends on: Task 16 and all tasks before it.

Files:
- Modify: `dmd_optimizer.py` (append)
- Test: `tests/test_cli.py`

Design sections 5 and 11. `main` parses the arguments, calls `run` and turns an `OptimizerError` into one line on standard error and exit status 1.

`run` refuses to overwrite existing output files unless `--force` is given, and it checks that before any work is done.

The three files are written into a temporary folder with a unique name inside the output folder. `install_files` then moves them onto their final names:

- Without `--force` it first claims each name by creating the file exclusively (`open(target, "xb")`), which fails if the file exists. A file that appeared while the tool was working is therefore never overwritten.
- With `--force` it first moves an existing file into the temporary folder.
- It never replaces a folder. `run` refuses a folder that has the name of an output file before any work is done, and `install_files` puts back a folder that appears later.
- A symbolic link under an output name counts as an existing file even when it points nowhere, which is why the code uses `os.path.lexists` and not `Path.exists`.
- If a step fails, it puts everything back, so an existing project is either replaced completely or left exactly as it was.
- If putting back fails as well, it raises `InstallError` naming the files to check by hand, and the temporary folder is kept because it holds the previous versions.

In every other case the temporary folder is removed at the end, and so is the output folder if this run created it and it is empty. A failure of either removal is a warning, never a second error.

Progress lines and warnings go to standard error while the tool works. A failed run prints exactly one line starting with `dmd_optimizer: error: `, as the last line on standard error, and nothing on standard output.

This block is part 5 and ends the file. Nothing is appended to `dmd_optimizer.py` after this task.

The tests cover:

- three files and the summary on a normal run
- the default output folder
- `--rom-name`
- existing files are kept without `--force` and replaced with it
- options that change the result, including `--max-masks 0 --no-shape-mode`
- every out-of-range option value and an unusable ROM name
- unreadable, unsupported and mixed-size dumps
- a truncated dump gives a warning and still works
- a failed run leaves nothing behind, and leaves an existing folder as it was
- a path that cannot be written
- a move that fails at any of its steps leaves a new folder empty and restores existing files exactly
- a failure while putting files back keeps the previous version and names it in the error message
- a temporary folder that cannot be removed is only a warning
- a file that appears during the run, or while the files are being moved, is not overwritten
- a failing removal of the empty output folder is a warning and keeps the error message last
- a folder with the name of an output file is never replaced, with or without `--force`, including one that appears during the run
- a symbolic link that points nowhere counts as an existing file and is put back after a failed forced run
- `--force` replaces all three files, leaves no extra files and does not touch other files of the user
- every failed run prints exactly one error line, last on standard error
- two runs give byte-identical files (rule R7)
- `--help` lists every option

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q tests/test_cli.py`
Expected: `39 failed`, with `AttributeError: module 'dmd_optimizer' has no attribute 'main'`.

- [ ] **Step 3: Write the implementation**

Append to `dmd_optimizer.py`:

```python
# ---------------------------------------------------------------------------
# Part 5: command line
# ---------------------------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(
        prog="dmd_optimizer.py",
        description="Write a ColorizingDMD project in which frames of a VPinMAME dump that show "
        "the same screen are already merged by comparison masks and shape mode.",
    )
    parser.add_argument("dumps", nargs="+", metavar="DUMP", help="VPinMAME dump file (.txt); all of the same ROM")
    parser.add_argument("--out-dir", metavar="DIR", help="output folder (default: <rom>-optimized)")
    parser.add_argument("--rom-name", metavar="NAME", help="ROM name (default: first dump's file name)")
    parser.add_argument("--max-vary", type=float, default=25.0, metavar="PCT",
                        help="percent of the display that may vary inside a merged group (default: 25)")
    parser.add_argument("--max-masks", type=int, default=64, metavar="N",
                        help="mask slots the tool may use, 0 to 64 (default: 64)")
    parser.add_argument("--min-gain", type=int, default=5, metavar="N",
                        help="frames a mask must save to be used (default: 5)")
    parser.add_argument("--min-lit", type=int, default=None, metavar="PIXELS",
                        help="lit pixels that must remain outside a mask (default: display pixels / 128)")
    parser.add_argument("--no-shape-mode", action="store_true", help="compare exact pixel values only")
    parser.add_argument("--force", action="store_true", help="overwrite existing output files")
    return parser


class InstallError(OptimizerError):
    """Moving the output files into place failed and not everything could be put back."""


def install_files(staged, targets, staging, force):
    """Move the staged files onto the targets.

    With force, a target that exists is first moved into the staging folder.
    Without force, each target name is claimed by creating the file exclusively,
    which fails if the file exists, so nothing can be overwritten by accident.
    A folder is never replaced. If any step fails, every target is put back as
    it was and OptimizerError is raised. If putting back fails too, InstallError
    names the files to check by hand.
    """
    moved = []  # (target, its previous version inside the staging folder or None)
    try:
        for source, target in zip(staged, targets):
            previous = None
            if not force:
                open(target, "xb").close()
            elif os.path.lexists(target):  # lexists also sees a link that points nowhere
                previous = staging / (target.name + ".previous")
                os.replace(target, previous)
            moved.append((target, previous))
            if previous is not None and previous.is_dir() and not previous.is_symlink():
                raise OSError(f"{target} is a folder, not a file")
            os.replace(source, target)
    except OSError as error:
        stranded = []
        for target, previous in reversed(moved):
            try:
                if previous is not None:
                    os.replace(previous, target)
                elif os.path.lexists(target):
                    os.remove(target)
            except OSError:
                stranded.append(str(target if previous is None else previous))
        if isinstance(error, FileExistsError):
            reason = f"{error.filename} already exists; pass --force to overwrite it"
        else:
            reason = f"cannot write the output files: {error}"
        if stranded:
            raise InstallError(
                f"{reason}. Putting the previous state back failed as well; "
                f"check these files by hand: {', '.join(stranded)}"
            ) from None
        raise OptimizerError(reason) from None


def run(args):
    """Run the tool for parsed arguments. Returns the exit status; raises OptimizerError."""
    if not 0 <= args.max_vary <= 100:
        raise OptimizerError("--max-vary must be between 0 and 100")
    if not 0 <= args.max_masks <= 64:
        raise OptimizerError("--max-masks must be between 0 and 64")
    if args.min_gain < 1:
        raise OptimizerError("--min-gain must be at least 1")
    if args.min_lit is not None and args.min_lit < 0:
        raise OptimizerError("--min-lit must not be negative")
    rom_name = args.rom_name or Path(args.dumps[0]).stem
    check_rom_name(rom_name)
    out_dir = Path(args.out_dir) if args.out_dir else Path(f"{rom_name}-optimized")
    targets = [out_dir / f"{rom_name}.cROM", out_dir / f"{rom_name}.cRP", out_dir / f"{rom_name}-report.html"]

    for target in targets:
        if target.is_dir() and not target.is_symlink():
            raise OptimizerError(f"{target} is a folder; the tool replaces files only")
        if os.path.lexists(target) and not args.force:
            raise OptimizerError(f"{target} already exists; pass --force to overwrite it")

    def say(message):
        print(f"dmd_optimizer: {message}", file=sys.stderr)

    say("reading dumps")
    dump = read_dumps(args.dumps)
    for warning in dump.warnings:
        say(f"warning: {warning}")
    options = Options(
        max_vary=args.max_vary,
        max_masks=args.max_masks,
        min_gain=args.min_gain,
        min_lit=args.min_lit,
        shape_mode=not args.no_shape_mode,
    )
    analysis = analyze(dump, options, say)
    project = new_project(dump, analysis, rom_name)
    created = not out_dir.exists()
    staging = None
    keep_staging = False
    done = False
    try:
        say("writing files")
        out_dir.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".dmd_optimizer-", dir=out_dir))
        staged = [staging / target.name for target in targets]
        write_project(project, staged[0], staged[1])
        staged[2].write_text(report_html(dump, analysis, rom_name), encoding="utf-8")
        install_files(staged, targets, staging, args.force)
        done = True
    except InstallError:
        keep_staging = True  # it holds previous versions that could not be put back
        raise
    except OSError as error:
        raise OptimizerError(f"cannot write the output files: {error}") from None
    finally:
        if staging is not None and not keep_staging:
            try:
                shutil.rmtree(staging)
            except OSError as error:
                say(f"warning: could not remove the temporary folder {staging}: {error}")
        if created and not done:
            try:
                if not os.listdir(out_dir):
                    os.rmdir(out_dir)
            except FileNotFoundError:
                pass  # the folder was never created
            except OSError as error:
                say(f"warning: could not remove the empty folder {out_dir}: {error}")
    for label, value in summarize(dump, analysis).items():
        print(f"{label}: {value}")
    for target in targets:
        print(f"wrote {target}")
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except OptimizerError as error:
        print(f"dmd_optimizer: error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with numpy pytest -q tests/test_cli.py`
Expected: `39 passed`.

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `189 passed`.

- [ ] **Step 5: Commit**

```bash
git add dmd_optimizer.py tests/test_cli.py
git commit -m "feat: add the command line"
```

---

### Task 18: Helper tools for the manual checks

Depends on: Tasks 15 and 17.

Files:
- Create: `tools/make_sample_dump.py`
- Create: `tools/compare_projects.py`
- Test: `tests/test_tools.py`

Design section 12.4 has two checks the user runs in ColorizingDMD. They need two small scripts: one that cuts a short sample out of a dump, and one that compares two projects field by field. `compare_projects.py` imports the tool, so it needs numpy.

The tests cover:

- the sample keeps exactly the first records and is a prefix of the source, with CRLF line endings
- a source shorter than the requested number of records is copied whole
- identical projects compare equal with exit status 0
- different projects list the differing header values and fields with exit status 1

- [ ] **Step 1: Write the failing test**

Create `tests/test_tools.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest --with numpy pytest -q tests/test_tools.py`
Expected: `4 failed`, with `FileNotFoundError` for `tools/make_sample_dump.py` and `tools/compare_projects.py`.

- [ ] **Step 3: Write the two tools**

Create `tools/make_sample_dump.py`:

```python
#!/usr/bin/env python3
"""Copy the first records of a dump into a new dump file.

Usage:  python3 tools/make_sample_dump.py SOURCE.txt TARGET.txt [RECORDS]

The editor names a project after the dump it imports, so TARGET's file name
becomes the ROM name of the project the editor creates from it.
"""
import sys


def first_records(data, records):
    """The leading part of dump text that holds the given number of records."""
    position = 0
    seen = 0
    for line in data.splitlines(keepends=True):
        if line.startswith(b"0x"):
            if seen == records:
                break
            seen += 1
        position += len(line)
    return data[:position]


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) not in (2, 3):
        sys.exit(__doc__)
    records = int(arguments[2]) if len(arguments) == 3 else 500
    with open(arguments[0], "rb") as stream:
        data = first_records(stream.read(), records)
    with open(arguments[1], "wb") as stream:
        stream.write(data)
    print(f"wrote {arguments[1]} with {data.count(b'0x')} records")


if __name__ == "__main__":
    main()
```

Create `tools/compare_projects.py`:

```python
#!/usr/bin/env python3
"""Compare two ColorizingDMD projects field by field.

Usage:  python3 tools/compare_projects.py A.cROM A.cRP B.cROM B.cRP

Prints one line per header value and per field that differs, then a summary.
Exit status 0 when the projects are identical, 1 otherwise.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dmd_optimizer as tool  # noqa: E402


def differences(first, second):
    """Lines describing how two projects differ; empty when they are identical."""
    lines = []
    for name in first.header:
        a, b = first.header[name], second.header[name]
        if a != b:
            if name == "name" and a.split(b"\x00")[0] != b.split(b"\x00")[0]:
                a, b = a.split(b"\x00")[0], b.split(b"\x00")[0]  # show the names without padding
            lines.append(f"header {name}: {a!r} != {b!r}")
    for label, a_fields, b_fields in (("cROM", first.crom, second.crom), ("cRP", first.crp, second.crp)):
        for name in a_fields:
            a, b = np.asarray(a_fields[name]), np.asarray(b_fields[name])
            if a.shape != b.shape:
                lines.append(f"{label} {name}: {a.size} values != {b.size} values")
            elif not np.array_equal(a, b):
                where = np.flatnonzero(a != b)
                lines.append(
                    f"{label} {name}: {len(where)} of {a.size} values differ, first at index "
                    f"{int(where[0])} ({int(a[where[0]])} != {int(b[where[0]])})"
                )
    return lines


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 4:
        sys.exit(__doc__)
    first = tool.read_project(arguments[0], arguments[1])
    second = tool.read_project(arguments[2], arguments[3])
    lines = differences(first, second)
    for line in lines:
        print(line)
    print(f"{len(lines)} differences" if lines else "the projects are identical")
    return 1 if lines else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest --with numpy pytest -q tests/test_tools.py`
Expected: `4 passed`.

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `193 passed`.

- [ ] **Step 5: Commit**

```bash
git add tools/make_sample_dump.py tools/compare_projects.py tests/test_tools.py
git commit -m "feat: add tools to cut a sample dump and compare two projects"
```

---

### Task 19: Twister files and tests on real data

Depends on: Task 17.

Files:
- Create: `tools/fetch_fixtures.py`
- Create: `tests/conftest.py`
- Test: `tests/test_twister.py`

Design section 12.2. The user supplied a real dump (`twst_405.txt`, 14,443 records) and a hand-made project for the same ROM (`twst_405.crom`, `twst_405.cRP`). The files are large and are not committed; a script downloads them into `fixtures/` and checks their SHA-256.

These tests check finished code against real files, so there is no failing step. They need network access for the download, about 1.5 GB of free memory and about 1 GB of disk space. The run takes two to three minutes, because the dump is analysed twice.

The tests cover:

- the dump facts: 14,443 records, 10,301 distinct frames, 6,906 distinct shapes, 128x32, 4 shades, no warnings
- reading the hand-made project and writing it back reproduces both files byte for byte
- the hash of all 5,093 frames of the hand-made project is reproduced
- the benchmark with default options: at most 4,500 kept frames, at most 64 masks, and at most 3.5% of merged frames grouped differently by hand
- rules R1 to R6 on the Twister result, checked by `check_rules`
- a second analysis gives the same result (rule R7)

"Grouped differently by hand" is defined in design section 12.2. `hand_labels` in `tests/helpers.py` implements it by exact comparison.

- [ ] **Step 1: Write the download script**

Create `tools/fetch_fixtures.py`:

```python
#!/usr/bin/env python3
"""Download the Twister test files into fixtures/ and check their SHA-256.

Run from the repository root:  python3 tools/fetch_fixtures.py
"""
import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
ARCHIVES = {
    "twst_405.zip": (
        "https://github.com/RenewedFire/Twister-Test/raw/main/twst_405.zip",
        "0a946f9c6ffdd5a28676ae181e6520b0195dec141f6eccd4e4ebda7ca1b20b67",
    ),
    "twst_405_11_12_2026.zip": (
        "https://github.com/RenewedFire/Twister-Test/raw/main/twst_405_11_12_2026.zip",
        "d4274254c12e6cf9e882abdc3db62804c74bfcb067e374e01397050830d7dfe6",
    ),
}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    FIXTURES.mkdir(exist_ok=True)
    for name, (url, expected) in ARCHIVES.items():
        archive = FIXTURES / name
        if not archive.exists() or sha256(archive) != expected:
            print(f"downloading {url}")
            urllib.request.urlretrieve(url, archive)
        if sha256(archive) != expected:
            sys.exit(f"{archive}: the SHA-256 does not match; the published file has changed")
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(FIXTURES)
            print(f"{name}: unpacked {', '.join(bundle.namelist())}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Download the files**

Run: `python3 tools/fetch_fixtures.py`
Expected:

```text
downloading https://github.com/RenewedFire/Twister-Test/raw/main/twst_405.zip
twst_405.zip: unpacked twst_405.txt
downloading https://github.com/RenewedFire/Twister-Test/raw/main/twst_405_11_12_2026.zip
twst_405_11_12_2026.zip: unpacked twst_405.cRP, twst_405.crom
```

If the download fails or the script reports that a SHA-256 does not match, stop and report it. The benchmark numbers below are valid only for these exact files.

- [ ] **Step 3: Write the shared fixtures**

Create `tests/conftest.py`:

```python
"""Fixtures shared by the tests that need the Twister files."""
import time
from pathlib import Path

import pytest

import dmd_optimizer as tool

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
TWISTER_DUMP = FIXTURES / "twst_405.txt"
TWISTER_CROM = FIXTURES / "twst_405.crom"
TWISTER_CRP = FIXTURES / "twst_405.cRP"


def twister_files_present():
    return TWISTER_DUMP.exists() and TWISTER_CROM.exists() and TWISTER_CRP.exists()


@pytest.fixture(scope="session")
def twister_dump():
    if not twister_files_present():
        pytest.skip("the Twister files are missing; run tools/fetch_fixtures.py")
    return tool.read_dumps([TWISTER_DUMP])


@pytest.fixture(scope="session")
def twister_reference():
    if not twister_files_present():
        pytest.skip("the Twister files are missing; run tools/fetch_fixtures.py")
    return tool.read_project(TWISTER_CROM, TWISTER_CRP)


@pytest.fixture(scope="session")
def twister_analysis(twister_dump):
    """The analysis of the Twister dump with default options; takes about a minute."""
    start = time.time()
    analysis = tool.analyze(twister_dump)
    print(f"\nTwister analysis: {time.time() - start:.0f} s")
    return analysis
```

- [ ] **Step 4: Write the tests**

Create `tests/test_twister.py`:

```python
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
```

- [ ] **Step 5: Run the Twister tests**

Run: `uv run --with pytest --with numpy pytest -q -s -m twister`
Expected: `6 passed`, and among the output these two lines (the number of seconds will differ):

```text
Twister analysis: 51 s
kept 4116 of 10301 frames, 43 masks, grouped differently by hand: 196 of 7682 (2.6%), CRC32 collisions: 0
```

The numbers 4116, 43 and 196 of 7682 are exact for this dump. If they differ, or a threshold fails, stop and report it. Do not change the thresholds.

- [ ] **Step 6: Run the fast tests**

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `193 passed`, with 6 deselected.

- [ ] **Step 7: Commit**

```bash
git add tools/fetch_fixtures.py tests/conftest.py tests/test_twister.py
git commit -m "test: check the tool against the Twister dump and reference project"
```

---

### Task 20: Prepare the fresh-import check for the user

Depends on: Tasks 18 and 19.

Files:
- Create (not committed): `handoff/twst_500.txt`, `handoff/twst_500-plain/`

Design section 12.4, check 1. The values of a new project (design section 8) come from reading the editor's source code. The only direct check is to let the editor import a small dump, save it untouched, and compare the result with the tool's output for the same dump with merging switched off.

This task prepares the files and hands them to the user. It does not wait for the answer. `handoff/` is ignored by git, so there is nothing to commit.

- [ ] **Step 1: Cut the sample dump**

Run:

```bash
mkdir -p handoff
python3 tools/make_sample_dump.py fixtures/twst_405.txt handoff/twst_500.txt 500
```

Expected: `wrote handoff/twst_500.txt with 500 records`

- [ ] **Step 2: Run the tool on the sample with merging switched off**

Run: `uv run dmd_optimizer.py handoff/twst_500.txt --max-masks 0 --no-shape-mode --out-dir handoff/twst_500-plain`
Expected on standard output:

```text
dump files read: 1
frames read: 500
distinct frames: 301
frames kept: 301
frames kept unmerged: 301
masks used: 0
frames merged by shape mode alone: 0
wrote handoff/twst_500-plain/twst_500.cROM
wrote handoff/twst_500-plain/twst_500.cRP
wrote handoff/twst_500-plain/twst_500-report.html
```

`handoff/twst_500-plain/twst_500.cROM` is 25,269,056 bytes (106 + 301 x 83,950).

- [ ] **Step 3: Hand the sample to the user**

Give the user the file `handoff/twst_500.txt` and this request, word for word:

> Please import `twst_500.txt` in ColorizingDMD as a new project, with every import filter unticked, then save it without changing anything. Send back the `twst_500.cROM` and `twst_500.cRP` the editor wrote.

Continue with Task 21 without waiting.

- [ ] **Step 4: When the two files come back, compare them**

Put the returned files into `handoff/editor/` and run:

```bash
uv run --with numpy python tools/compare_projects.py \
  handoff/twst_500-plain/twst_500.cROM handoff/twst_500-plain/twst_500.cRP \
  handoff/editor/twst_500.cROM handoff/editor/twst_500.cRP
```

Differences in these fields are expected and need no action:

| Field | Why it may differ |
|---|---|
| `cRP FrameDuration`, `cROM ActiveFrames` | The tool stores the longest duration of a frame; the editor stores the duration of its first occurrence (design section 8.4) |
| `cRP TimeElapsed` | The editor's work timer |
| `cRP Draw_Mode`, `Mask_Sel_Mode`, `Fill_Mode`, `DrawColMode`, `acColSet`, `preColSet`, `activeColSet`, `ColSets`, `nameColSet` | Editor interface state |

Any other line, and any `header` line, means design section 8 does not match the editor. Report the full output to the user. Do not change the tool on your own.

---

### Task 21: Independent check with libserum

Depends on: Tasks 17 and 19.

Files:
- Create: `tools/build_libserum.sh`
- Test: `tests/test_libserum.py`

Design section 12.3. libserum is the library pinball software uses to read Serum files. Branch `2.8.x` is the last one that loads `.cROM` files directly. The test writes a project with the tool, loads it with the real library, feeds it every dump record in order and requires the library to report the kept frame the tool predicted.

The library answers each frame with a frame number, with `0xFFFFFFFE` ("same frame as before") or with `0xFFFFFFFF` ("no frame"). "Same frame" is accepted when the prediction equals the last frame the library reported. "No frame" is accepted only for kept frames marked inactive (shorter than 15 ms).

Building needs git, cmake, a C++ compiler and network access. The build takes under a minute. These tests check finished code against a real library, so there is no failing step.

The tests cover:

- a made-up 192x64 project with 16 shades (needs only the library)
- the Twister project (needs the library and the Twister files)

- [ ] **Step 1: Write the build script**

Create `tools/build_libserum.sh`:

```bash
#!/usr/bin/env bash
# Build libserum 2.8.x into .cache/libserum for tests/test_libserum.py.
# 2.8.x is the last libserum line that loads .cROM files directly.
# Needs git, cmake and a C++ compiler. Run from anywhere:  tools/build_libserum.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/.cache/libserum"
COMMIT=198dc47a64b523ab933f51bedce59c8f1daf93eb

if [ ! -d "$DEST/.git" ]; then
  mkdir -p "$ROOT/.cache"
  git clone --branch 2.8.x https://github.com/PPUC/libserum.git "$DEST"
fi
cd "$DEST"
git fetch --quiet origin 2.8.x
git checkout --quiet "$COMMIT"
./platforms/external-common.sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 4
ls build/libserum*
```

Make it executable:

```bash
chmod +x tools/build_libserum.sh
```

- [ ] **Step 2: Build libserum**

Run: `tools/build_libserum.sh`
Expected: the output ends with a list of library files, on macOS:

```text
build/libserum64.2.8.2.dylib
build/libserum64.dylib
```

On Linux the names end in `.so`. If the build fails, stop and report the last 30 lines of its output.

- [ ] **Step 3: Write the test**

Create `tests/test_libserum.py`:

```python
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
```

- [ ] **Step 4: Run the libserum tests**

Run: `uv run --with pytest --with numpy pytest -q -s -m libserum`
Expected: `2 passed`. The run takes about one minute because it analyses the Twister dump.

If the library reports a problem, the assertion shows a list of `(record, kind, reported frame, predicted frame)` tuples. Stop and report it.

- [ ] **Step 5: Run the fast tests**

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `193 passed`, with 8 deselected.

- [ ] **Step 6: Commit**

```bash
git add tools/build_libserum.sh tests/test_libserum.py
git commit -m "test: verify the tool's output with the real libserum"
```

---

### Task 22: README, full run and the final acceptance check

Depends on: all earlier tasks.

Files:
- Create: `README.md`
- Create (not committed): `handoff/twst_405-optimized/`

- [ ] **Step 1: Write the README**

Create `README.md`:

````markdown
# DMD mask optimizer

`dmd_optimizer.py` reads VPinMAME DMD dumps and writes a new ColorizingDMD project
(Serum format) in which frames that show the same screen are already merged.
Comparison masks cover the areas that vary, such as scores and small animations.
Shape mode covers frames that differ only in brightness. The tool colours nothing.

The design is in `docs/superpowers/specs/2026-11-12-dmd-mask-optimizer-design.md`.

## Running the tool

The tool needs Python 3.10 or later and numpy 2.0 or later. With `uv`, numpy is
installed automatically:

```
uv run dmd_optimizer.py twst_405.txt
```

Without `uv`, install numpy and run `python3 dmd_optimizer.py twst_405.txt`.

Several dumps of the same ROM can be given at once. The output goes to
`<rom>-optimized/`:

| File | Content |
|---|---|
| `<rom>.cROM` | Open this with "Open project" in ColorizingDMD |
| `<rom>.cRP` | Loaded by the editor together with the `.cROM` |
| `<rom>-report.html` | Shows every merged group; open it in a browser |

## Options

| Option | Default | Meaning |
|---|---|---|
| `--out-dir DIR` | `<rom>-optimized` | Output folder |
| `--rom-name NAME` | first dump's file name | ROM name stored in the project |
| `--max-vary PCT` | 25 | Percent of the display that may vary inside a merged group |
| `--max-masks N` | 64 | Mask slots the tool may use |
| `--min-gain N` | 5 | Frames a mask must save to be used |
| `--min-lit PIXELS` | display pixels / 128 | Lit pixels that must remain outside a mask |
| `--no-shape-mode` | off | Compare exact pixel values only |
| `--force` | off | Overwrite existing output files |

A higher `--max-vary` merges more frames and raises the chance of merging screens
that should stay apart. The report lists the groups closest to the limit first.

## Running the tests

```
uv run --with pytest --with numpy pytest -q
```

Two groups of tests are opt-in because they need downloads:

```
python3 tools/fetch_fixtures.py                              # Twister dump and reference project
uv run --with pytest --with numpy pytest -q -s -m twister

tools/build_libserum.sh                                      # needs git, cmake and a C++ compiler
uv run --with pytest --with numpy pytest -q -s -m libserum
```

## Comparing two projects

```
uv run --with numpy python tools/compare_projects.py A.cROM A.cRP B.cROM B.cRP
```

This prints every header value and field that differs between two projects.
````

- [ ] **Step 2: Run every test**

Run: `uv run --with pytest --with numpy pytest -q`
Expected: `193 passed`, with 8 deselected.

Run: `uv run --with pytest --with numpy pytest -q -s -m "twister or libserum"`
Expected: `8 passed`, with 193 deselected. This takes two to three minutes.

- [ ] **Step 3: Run the tool on the Twister dump**

Run: `uv run dmd_optimizer.py fixtures/twst_405.txt --out-dir handoff/twst_405-optimized`
Expected on standard output, after about one minute:

```text
dump files read: 1
frames read: 14443
distinct frames: 10301
frames kept: 4116
frames kept unmerged: 2619
masks used: 43
frames merged by shape mode alone: 592
wrote handoff/twst_405-optimized/twst_405.cROM
wrote handoff/twst_405-optimized/twst_405.cRP
wrote handoff/twst_405-optimized/twst_405-report.html
```

`twst_405.cROM` is 345,714,434 bytes (106 + 4,116 x 83,950 + 43 x 4,096). Open `twst_405-report.html` in a browser and confirm that it shows the summary table, two warnings about kept frames shown for 0 ms, a list of 20 groups to review first, and 43 collapsible mask sections followed by a "Shape mode with no mask" section.

Run the same command again without `--force`.
Expected: exit status 1 and `dmd_optimizer: error: handoff/twst_405-optimized/twst_405.cROM already exists; pass --force to overwrite it`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add the README"
```

- [ ] **Step 5: Hand the Twister project to the user**

Give the user the folder `handoff/twst_405-optimized/` and this request, word for word:

> Please open `twst_405.cROM` from this folder with "Open project" in ColorizingDMD. Confirm that it loads, that it has 4,116 frames, and that the mask list shows 43 masks named `auto-00` to `auto-42`. Then save the project without changing anything and send back the `twst_405.cROM` and `twst_405.cRP` the editor wrote. The report `twst_405-report.html` shows what was merged.

- [ ] **Step 6: When the two files come back, compare them**

Put the returned files into `handoff/editor-twister/` and run:

```bash
uv run --with numpy python tools/compare_projects.py \
  handoff/twst_405-optimized/twst_405.cROM handoff/twst_405-optimized/twst_405.cRP \
  handoff/editor-twister/twst_405.cROM handoff/editor-twister/twst_405.cRP
```

The editor recomputes every hash when it saves. The check passes when none of these fields appears in the output: `cROM HashCode`, `cROM ShapeCompMode`, `cROM CompMaskID`, `cROM CompMasks`, `cRP oFrames`, and no `header` line.

Differences in `cRP TimeElapsed` and in the editor interface state fields listed in Task 20 are expected. Report the full output to the user either way. If an identification field differs, do not change the tool on your own.

---

## After the last task

The work is complete when:

- `uv run --with pytest --with numpy pytest -q` prints `193 passed`;
- `uv run --with pytest --with numpy pytest -q -s -m "twister or libserum"` prints `8 passed`;
- the two hand-offs of Tasks 20 and 22 have been given to the user.

The two ColorizingDMD checks finish whenever the user returns the files. Their outcome is reported to the user; it does not block the commits above.
