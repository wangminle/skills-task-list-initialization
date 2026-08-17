"""CLI regression tests (split from the former monolithic file)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase  # noqa: E402


class CliListTest(CliTestCase):
    def test_sections_lists_headings(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target), "--profile", "extended")
            result = self.run_cli("sections", "--file", str(target))
            for title in ("代码 Bug", "调整事项", "调研事项", "配置运维"):
                self.assertIn(title, result.stdout)

    def test_sections_json_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            result = self.run_cli("sections", "--file", str(target), "--format", "json")
            payload = json.loads(result.stdout)
            titles = [s["title"] for s in payload["sections"]]
            self.assertIn("代码 Bug", titles)
            self.assertTrue(any(s.get("prefix") == "BUG" for s in payload["sections"]))

    def test_list_filters_by_status_and_keyword(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "sqlite 锁",
                "--status", "待修复", "--notes", "db",
            )
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "其他",
                "--status", "已修复",
                "--found-time", "2026-08-04 10:00",
                "--completed-time", "2026-08-04 11:00",
            )
            result = self.run_cli(
                "list", "--file", str(target), "--status", "待修复", "--keyword", "sqlite",
            )
            self.assertIn("BUG-001", result.stdout)
            self.assertNotIn("BUG-002", result.stdout)
            by_id = self.run_cli("list", "--file", str(target), "--id", "BUG-002", "--format", "json")
            payload = json.loads(by_id.stdout)
            self.assertEqual(len(payload["records"]), 1)
            self.assertEqual(payload["records"][0]["id"], "BUG-002")
