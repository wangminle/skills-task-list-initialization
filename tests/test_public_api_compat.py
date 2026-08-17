"""Import compatibility for the pre-split public API surface.

After C5, ``task_list_cli`` and ``_tasklist`` must keep an explicit compat
list (not star-import stdlib leaks). External callers such as
``from task_list_cli import detect_locale`` must keep working.
"""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

from helpers import ensure_scripts_on_path, load_cli_module  # noqa: E402

ensure_scripts_on_path()

# Baseline names called out by the refactor plan / external agents.
# Full formal list lives in ``_tasklist.public_api.PUBLIC_API``.
REQUIRED_COMPAT_NAMES = (
    "main",
    "detect_locale",
    "get_locale",
    "detect_schema",
    "split_cells",
    "collect_records",
    "parse_sections",
    "section_headers_by_title",
    "escape_cell",
    "render_summary_with_counts",
    "record_quality_warnings",
    "classify_extension_recommendations",
    "summary_drift_issues",
    "detect_maintenance_rule",
    "atomic_write",
    "commit_all",
    "LOCALES",
    "Section",
    "Locale",
)


class TestPublicApiCompat(unittest.TestCase):
    def test_public_api_module_lists_required_names(self):
        from _tasklist.public_api import PUBLIC_API

        missing = [n for n in REQUIRED_COMPAT_NAMES if n not in PUBLIC_API]
        self.assertEqual(missing, [], f"PUBLIC_API missing required names: {missing}")

    def test_task_list_cli_exports_required_names(self):
        mod = load_cli_module()
        missing = [n for n in REQUIRED_COMPAT_NAMES if not hasattr(mod, n)]
        self.assertEqual(missing, [], f"task_list_cli missing: {missing}")
        self.assertEqual(list(mod.__all__), list(mod.PUBLIC_API))

    def test_tasklist_package_exports_required_names(self):
        import _tasklist

        missing = [n for n in REQUIRED_COMPAT_NAMES if not hasattr(_tasklist, n)]
        self.assertEqual(missing, [], f"_tasklist missing: {missing}")
        self.assertEqual(list(_tasklist.__all__), list(_tasklist.PUBLIC_API))

    def test_from_task_list_cli_import_detect_locale(self):
        """Regression: ``from task_list_cli import detect_locale`` must succeed."""
        scripts = Path(__file__).resolve().parents[1] / (
            "skills/task-list-initialization/scripts"
        )
        sys.path.insert(0, str(scripts))
        # Fresh import path: load as top-level module name task_list_cli
        if "task_list_cli" in sys.modules:
            del sys.modules["task_list_cli"]
        mod = importlib.import_module("task_list_cli")
        detect_locale = mod.detect_locale
        self.assertEqual(detect_locale("# 任务跟踪列表\n"), "zh")
        self.assertEqual(detect_locale("# Task Tracking List\n"), "en")

    def test_every_public_api_name_is_bound(self):
        from _tasklist.public_api import PUBLIC_API
        import _tasklist.public_api as api

        mod = load_cli_module()
        for name in PUBLIC_API:
            self.assertTrue(hasattr(api, name), f"public_api unbound: {name}")
            self.assertTrue(hasattr(mod, name), f"task_list_cli unbound: {name}")
            self.assertIs(getattr(mod, name), getattr(api, name))


if __name__ == "__main__":
    unittest.main()
