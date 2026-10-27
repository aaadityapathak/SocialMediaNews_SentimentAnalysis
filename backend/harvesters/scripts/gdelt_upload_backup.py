"""Portable command-line entry point for importing a GDELT CSV backup."""

import sys
from pathlib import Path

_src = Path(__file__).parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from gdelt_retrieve.importer import main

if __name__ == "__main__":
    main()
