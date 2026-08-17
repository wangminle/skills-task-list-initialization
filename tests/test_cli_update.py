"""CLI regression tests (split from the former monolithic file)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase  # noqa: E402


class CliUpdateTest(CliTestCase):
    def test_update_status_and_completed_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "登录无响应",
                "--found-time", "2026-08-04 10:00", "--completed-time", "-",
                "--status", "进行中", "--notes", "排查中", "--no-check",
            )
            result = self.run_cli(
                "update", "--file", str(target), "--id", "BUG-001",
                "--status", "已修复",
                "--completed-time", "2026-08-04 16:00",
            )
            self.assertIn("已更新：BUG-001", result.stdout)
            text = target.read_text(encoding="utf-8")
            self.assertIn(
                "| BUG-001 | 修复 | 登录无响应 | 2026-08-04 10:00 | 2026-08-04 16:00 | 已修复 | 排查中 |",
                text,
            )

    def test_update_notes_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "x",
                "--status", "进行中", "--notes", "初诊", "--no-check",
            )
            self.run_cli(
                "update", "--file", str(target), "--id", "BUG-001",
                "--notes-append", "测试通过",
            )
            text = target.read_text(encoding="utf-8")
            self.assertIn("初诊；测试通过", text)

    def test_update_rejects_unknown_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            result = self.run_cli(
                "update", "--file", str(target), "--id", "BUG-999",
                "--status", "已修复", check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("BUG-999", result.stdout + result.stderr)

    def test_update_status_demotion_clears_completed_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.run_cli(
                "add", "--file", str(target), "--section", "文档维护",
                "--action", "文档", "--description", "d", "--status", "已完成",
                "--found-time", "2026-08-01 10:00", "--completed-time", "2026-08-01 11:00",
            )
            result = self.run_cli(
                "update", "--file", str(target), "--id", "DOC-001", "--status", "待办",
            )
            self.assertEqual(result.returncode, 0)
            text = target.read_text(encoding="utf-8")
            self.assertIn("| DOC-001 | 文档 | d | 2026-08-01 10:00 | - | 待办 |", text)
            self.assertNotIn("| 2026-08-01 11:00 | 待办 |", text)

    def test_update_priority_rejects_when_column_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.run_cli(
                "add", "--file", str(target), "--section", "文档维护",
                "--action", "文档", "--description", "p", "--status", "待办",
            )
            before = target.read_text(encoding="utf-8")
            result = self.run_cli(
                "update", "--file", str(target), "--id", "DOC-001", "--priority", "P0",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--priority", result.stdout + result.stderr)
            self.assertEqual(before, target.read_text(encoding="utf-8"))

    def test_update_found_time_rejects_single_date_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 文档维护\n\n"
                "| ID | 动作 | 事项 | 完成日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| DOC-001 | 文档 | x | 2026-08-01 | 待办 | n |\n",
                encoding="utf-8",
            )
            before = target.read_text(encoding="utf-8")
            result = self.run_cli(
                "update", "--file", str(target), "--id", "DOC-001",
                "--found-time", "2026-08-02 10:00", check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--found-time", result.stdout + result.stderr)
            self.assertEqual(before, target.read_text(encoding="utf-8"))
