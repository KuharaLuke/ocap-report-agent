import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path so "from models import ..." works
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from aar_pipeline.loader import MissionLoader

DATA_FILE = PROJECT_ROOT / "2026_03_08__21_33_RandomPatrolGenerator.json.gz"
TEST_OUTPUT = PROJECT_ROOT / "test_output"


@pytest.fixture(scope="session")
def mission():
    """Load the real OCAP2 mission file once, shared across all tests."""
    return MissionLoader.load(DATA_FILE)


@pytest.fixture(scope="session")
def output_dir():
    """Ensure test_output/ exists and return its path."""
    TEST_OUTPUT.mkdir(exist_ok=True)
    return TEST_OUTPUT
