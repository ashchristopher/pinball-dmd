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

_TIMESTAMP = re.compile(rb"^0x([0-9A-Fa-f]{8})[ \t]*\r?$", re.MULTILINE)
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
    marks = list(_TIMESTAMP.finditer(data))
    size = None
    frames = None
    times = []
    warning = None
    for number, mark in enumerate(marks, start=1):
        end = marks[number].start() if number < len(marks) else len(data)
        lines = [line.rstrip(b"\r") for line in data[mark.end():end].split(b"\n")]
        lines = [line for line in lines if line]
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
            frames = np.empty((len(marks), width * height), np.uint8)
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
        frames[len(times)] = pixels
        times.append(int(mark.group(1), 16))
        if len(lines) > height:
            warning = f"{name}: unexpected text after record {number}; reading stopped there"
            break
    if not times:
        raise OptimizerError(f"{name}: no complete frame found")
    if len(times) < len(frames):
        frames = frames[:len(times)].copy()  # give the unused part back
    return frames, np.array(times, np.uint32), size, warning


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
    index = {}  # pixels of a distinct frame -> its number
    record_frame = []
    times = []
    durations = []
    files = []
    warnings = []
    for number, path in enumerate(paths):
        try:
            data = Path(path).read_bytes()
        except OSError as error:
            raise OptimizerError(f"{path}: cannot read the file ({error.strerror})") from None
        frames, file_times, file_size, warning = parse_dump_text(data, path)
        del data  # the text of a dump is several times larger than its frames
        if size is None:
            size = file_size
        elif file_size != size:
            raise OptimizerError(
                f"{path}: frame size {file_size[0]}x{file_size[1]} differs from "
                f"{size[0]}x{size[1]} in {paths[0]}"
            )
        if warning:
            warnings.append(warning)
        for row in frames:
            record_frame.append(index.setdefault(row.tobytes(), len(index)))
        times.append(file_times)
        durations.append(frame_durations(file_times))
        files.append(np.full(len(file_times), number, np.int64))
    width, height = size
    distinct = np.frombuffer(b"".join(index), np.uint8).reshape(len(index), width * height)
    return Dump(
        width=width,
        height=height,
        shades=16 if int(distinct.max()) > 3 else 4,
        frames=distinct,
        record_frame=np.array(record_frame, np.int64),
        record_time=np.concatenate(times),
        record_duration=np.concatenate(durations),
        record_file=np.concatenate(files),
        files=paths,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Part 2: analysis
# ---------------------------------------------------------------------------

NO_MASK = 255  # mask number stored for a frame that uses no mask


def _compared_pixels(frames, mask, shape):
    """The pixels libserum compares: masked pixels removed, lit/unlit only in shape mode."""
    data = np.asarray(frames, np.uint8)
    if mask is not None:
        data = np.ascontiguousarray(data[..., np.asarray(mask) == 0])  # a copy, safe to change
        if shape:
            np.minimum(data, 1, out=data)
    elif shape:
        data = np.minimum(data, 1)
    return np.ascontiguousarray(data)


def frame_hash(pixels, mask=None, shape=False):
    """CRC32 of one frame as libserum computes it.

    pixels is uint8 [pixels]; mask marks ignored pixels with non-zero values, or
    is None; with shape=True every lit pixel counts as 1.
    """
    return zlib.crc32(_compared_pixels(pixels, mask, shape)) & 0xFFFFFFFF


def _row_hashes(rows):
    """CRC32 of every row of compared pixels, as uint32 [n]."""
    return np.fromiter((zlib.crc32(row) for row in rows), np.uint32, len(rows))


def frame_hashes(frames, mask=None, shape=False):
    """frame_hash of every row of frames [n, pixels], as uint32 [n]."""
    return _row_hashes(_compared_pixels(frames, mask, shape))


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


class Labeller:
    """Labels frames so that equal labels mean "equal outside a mask" in one view.

    Each 2x2 cell of each frame gets a 64-bit hash. The hash of a frame outside a
    mask is the sum of the hashes of its unmasked cells, read from a table of
    sums so that a rectangle costs four lookups per frame. Hash collisions are
    possible in theory, which is why step E re-checks every result pixel by pixel.

    The table takes 8 bytes per cell and frame, twice the size of the frames
    themselves. With one Labeller per view it is the largest block of memory the
    tool holds; the README states the totals.
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


BATCH_FRAMES = 4096  # frames copied at a time when the members of classes or groups are compared


def varying_batches(frames, order, starts):
    """Find where the frames of each run differ, copying a bounded number of frames at a time.

    order lists frame numbers and a run begins at every index in starts. Yields
    (first, differ) for consecutive batches of runs: differ is bool [runs, pixels]
    for the runs first, first + 1, ..., True where the frames of a run differ in value.
    """
    ends = np.append(starts[1:], len(order))
    first = 0
    while first < len(starts):
        last = max(first + 1, int(np.searchsorted(ends, starts[first] + BATCH_FRAMES, side="right")))
        rows = frames[order[starts[first]:ends[last - 1]]]
        local = starts[first:last] - starts[first]
        yield first, np.maximum.reduceat(rows, local, axis=0) != np.minimum.reduceat(rows, local, axis=0)
        first = last


class Workspace:
    """The frames and the current groups during steps B to D of the design."""

    def __init__(self, dump, options):
        self.frames = dump.frames
        self.width = dump.width
        self.height = dump.height
        count, pixels = self.frames.shape
        self.limit = options.limit(pixels)
        self.min_lit = options.lit_needed(pixels)
        lit = self.frames > 0
        rows, columns = self.height // CELL, self.width // CELL
        self.lit_cells = (
            lit.reshape(count, rows, CELL, columns, CELL)
            .sum(axis=(2, 4), dtype=np.uint8)
            .reshape(count, rows * columns)
        )
        self.lit_total = lit.sum(axis=1)
        self.labellers = {False: Labeller(self.frames, self.width, self.height)}
        if options.shape_mode:
            # lit, read as bytes, is the shape view; using it saves a copy as large as the frames
            self.labellers[True] = Labeller(lit.view(np.uint8), self.width, self.height)
        del lit
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
            for first, differ in varying_batches(self.frames, frames, starts):
                if candidate.mask is not None:
                    differ &= ~candidate.mask
                batch = classes[starts[first:first + len(differ)]]
                sound[batch] = differ.sum(axis=1) + candidate.area <= self.limit
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
    varying = np.zeros((len(kept), work.frames.shape[1]), bool)
    for first, differ in varying_batches(work.frames, order, starts):
        varying[first:first + len(differ)] = differ
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
        kept = np.array([groups[number].kept for number in numbers])
        kept_rows = _compared_pixels(frames[kept], mask, shape)
        by_hash = {}
        for position, value in enumerate(_row_hashes(kept_rows).tolist()):
            groups[numbers[position]].hash = value
            by_hash.setdefault(value, []).append(position)
        for start in range(0, len(frames), BATCH_FRAMES):  # a bounded number of frames at a time
            rows = _compared_pixels(frames[start:start + BATCH_FRAMES], mask, shape)
            for offset, value in enumerate(_row_hashes(rows).tolist()):
                for position in by_hash.get(value, ()):
                    frame, number = start + offset, numbers[position]
                    if not np.array_equal(rows[offset], kept_rows[position]):
                        collisions.append((frame, int(kept[position])))
                        continue
                    matches[frame] += 1
                    if own[frame] != number:
                        raise OptimizerError(
                            defect.format(
                                f"frame {frame} matches the kept frame {int(kept[position])} of another group"
                            )
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
        seen = set()
        for shape in (False, True) if options.shape_mode else (False,):
            view = shape_view(dump.frames) if shape else dump.frames
            for region in candidate_regions(view, links, work.limit, dump.width, dump.height):
                key = region.tobytes()
                if key not in seen:
                    seen.add(key)
                    regions.append(region)
        view = None  # the shape view is as large as the frames; do not keep it
    say(f"choosing masks from {len(regions)} candidate regions")
    choose_masks(work, regions, options)
    say("tightening settings")
    tighten(work, options)
    work.labellers.clear()  # the largest tables in memory; step E does not use them
    say("verifying")
    return finish(work, options)


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
