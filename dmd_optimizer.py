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
