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
