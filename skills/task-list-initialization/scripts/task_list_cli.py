#!/usr/bin/env python3
"""Create and maintain Markdown task-list files (Chinese or English).

Implementation lives under ``_tasklist/``. This entry script only fixes
``sys.path`` and re-exports the formal public API compatibility surface.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _tasklist import public_api as _public_api  # noqa: E402
from _tasklist.public_api import PUBLIC_API  # noqa: E402

globals().update({name: getattr(_public_api, name) for name in PUBLIC_API})

__all__ = list(PUBLIC_API)


if __name__ == "__main__":
    raise SystemExit(_public_api.main())
