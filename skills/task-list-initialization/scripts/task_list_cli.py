#!/usr/bin/env python3
"""Create and maintain Markdown task-list files (Chinese or English).

Implementation is split under `_tasklist/` for maintainability:
- `_locale.py` — Locale/Section data, i18n strings, status suggestions
- `_lib.py` — parsing, validation, commands, argparse
This module re-exports the public API so existing imports and tests keep working.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _tasklist._locale import *  # noqa: F403,E402
from _tasklist._lib import *  # noqa: F403,E402
from _tasklist._lib import main  # noqa: E402  (explicit re-export so ruff resolves main)


if __name__ == "__main__":
    raise SystemExit(main())
