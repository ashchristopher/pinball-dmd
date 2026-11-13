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
