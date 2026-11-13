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
