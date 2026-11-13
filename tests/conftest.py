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
