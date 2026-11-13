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
