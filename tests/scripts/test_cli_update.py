"""CLI regression tests (split from the former monolithic file)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase  # noqa: E402


class CliUpdateTest(CliTestCase):
    _multi_error_file = (
        "# 任务跟踪列表\n\n"
        "## 代码 Bug\n\n"
        "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| BUG-001 | 修复 | first | 2026-01-01 10:00 | - | 待修复 | n |\n"
        "| BUG-002 | 修复 | second | 2026-01-01 11:00 | - | 待修复 | 含 <title> 裸标签 |\n"
    )

    def test_update_keeps_write_when_errors_are_preexisting(self):
        # CHK-102 (1): with pre-existing check errors in OTHER rows, updating a clean
        # row must not roll back - the write keeps and residuals are disclosed.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._multi_error_file, encoding="utf-8")
            result = self.run_cli(
                "update", "--file", str(target), "--id", "BUG-001",
                "--status", "已修复", "--completed-time", "2026-01-01 12:00",
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("已更新：BUG-001", result.stdout)
            self.assertIn("存量问题", result.stderr)
            text = target.read_text(encoding="utf-8")
            self.assertIn("| BUG-001 | 修复 | first | 2026-01-01 10:00 | 2026-01-01 12:00 | 已修复 | n |", text)
            self.assertIn("含 <title> 裸标签", text)

    def test_update_rolls_back_when_introducing_new_issue(self):
        # CHK-102 (1): a write that introduces a NEW issue (dangling ref, which the
        # write path does not sanitize) must still roll back despite pre-existing ones.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._multi_error_file, encoding="utf-8")
            before = target.read_text(encoding="utf-8")
            result = self.run_cli(
                "update", "--file", str(target), "--id", "BUG-001",
                "--notes", "见 [[FOO-999]]",
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("已回滚", result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), before)

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

    def test_bug084_same_prefix_ref_swap_is_new_issue(self):
        # BUG-084: digit-collapsed fingerprints merged same-prefix IDs
        # ([[BUG-002]] ≡ [[BUG-003]]), so swapping one dangling ref for a fresh
        # one was mislabeled "pre-existing" and kept. IDs must stay distinct.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | a | 2026-01-05 10:00 | - | 待修复 | 见 [[BUG-002]] |\n",
                encoding="utf-8",
            )
            before = target.read_text(encoding="utf-8")
            result = self.run_cli(
                "update", "--file", str(target), "--id", "BUG-001",
                "--notes", "见 [[BUG-003]]", check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("已回滚", result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), before)
