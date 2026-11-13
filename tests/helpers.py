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
