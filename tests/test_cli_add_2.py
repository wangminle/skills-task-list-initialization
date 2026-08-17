"""CLI regression tests (split from the former monolithic file)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase  # noqa: E402


class CliAdd2Test(CliTestCase):
    def test_add_dry_run_prints_only_new_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "dry",
                "--status", "待修复", "--dry-run",
            )
            self.assertIn("| BUG-001 |", result.stdout)
            self.assertNotIn("# 任务跟踪列表", result.stdout)
            self.assertNotIn("## 调整事项", result.stdout)
            # file untouched (template notes mention [[BUG-001]] wiki syntax — match a table row)
            self.assertNotIn("| BUG-001 |", target.read_text(encoding="utf-8"))

    def test_add_rejects_invalid_and_cross_prefix_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            bad = self.run_cli(
                "add", "--file", str(target), "--section", "文档维护",
                "--id", "FOO", "--action", "文档", "--description", "x", "--status", "待办",
                check=False,
            )
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("FOO", bad.stdout + bad.stderr)
            cross = self.run_cli(
                "add", "--file", str(target), "--section", "文档维护",
                "--id", "BUG-999", "--action", "文档", "--description", "y", "--status", "待办",
                check=False,
            )
            self.assertNotEqual(cross.returncode, 0)
            self.assertIn("BUG-999", cross.stdout + cross.stderr)
            self.assertNotIn("| FOO |", target.read_text(encoding="utf-8"))
            self.assertNotIn("| BUG-999 |", target.read_text(encoding="utf-8"))

    def test_add_wraps_raw_title_tag_in_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "html in notes",
                "--status", "待修复", "--notes", "broken <title> tag",
            )
            self.assertEqual(result.returncode, 0)
            text = target.read_text(encoding="utf-8")
            self.assertIn("`<title>`", text)
            self.assertNotRegex(text, r"(?<!`) <title> (?!`)")
            check = self.run_cli("check", "--file", str(target))
            self.assertEqual(check.returncode, 0)
