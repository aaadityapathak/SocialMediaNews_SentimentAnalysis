"""Load the shared repository test policy for component-local pytest runs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from test_support import (  # noqa: E402, F401
    pytest_addoption,
    pytest_configure,
    pytest_collection_modifyitems,
)
