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
