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
