#!/usr/bin/env python3
"""Compatibility wrapper for `python3 scripts/migrate.py`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fxxk_u_claude.migrate import main  # noqa: E402


if __name__ == "__main__":
    main()
