"""CLI regression tests (split from the former monolithic file)."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase, load_cli_module  # noqa: E402


class CliBugs2Test(CliTestCase):
    def test_bug061_archive_merge_rejects_column_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                f"{self._zh_dual_header()}\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-002 | 修复 | later-old | 2020-02-01 00:00 | 2020-02-01 00:00 | 已修复 | n |\n"
                "| BUG-003 | 修复 | keep | 2026-08-01 10:00 | - | 待修复 | n |\n",
                encoding="utf-8",
            )
            archive = Path(tmp) / "task-list-archive-202608.md"
            archive.write_text(
                "# 任务跟踪列表（归档）\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 完成日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | old | 2020-01-01 | 已修复 | n |\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "archive", "--file", str(target),
                "--older-than-days", "30", "--as-of", "2026-08-13",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            combined = result.stdout + result.stderr
            self.assertIn("归档合并失败", combined)
            arch_text = archive.read_text(encoding="utf-8")
            self.assertNotIn("发现时间", arch_text)
            self.assertIn("| BUG-001 |", arch_text)
            self.assertNotIn("| BUG-002 |", arch_text)

    def test_bug062_no_sync_summary_skips_english_inconsistent_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# Task Tracking List\n\n"
                "## Bugs\n\n"
                "| ID | Action | Description | Found | Done | Status | Notes |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | Fix | a | 2026-01-01 10:00 | - | Pending Fix | n |\n\n"
                "## Summary\n\n"
                "| Category | Total | Done | Pending | Rate |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| Bugs | 5 | 2 | 2 | 40% |\n"
                "| **Total** | 5 | 2 | 2 | 40% |\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "add", "--file", str(target), "--section", "Bugs",
                "--action", "Fix", "--description", "b", "--status", "Pending Fix",
                "--no-sync-summary",
            )
            self.assertIn("BUG-002", result.stdout)
            text = target.read_text(encoding="utf-8")
            self.assertIn("| BUG-002 |", text)
            self.assertIn("| Bugs | 5 | 2 | 2 | 40% |", text)

    def test_bug063_from_json_rejects_non_string_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            payload = Path(tmp) / "entries.json"
            payload.write_text(
                json.dumps({
                    "section": "代码 Bug",
                    "action": "修复",
                    "description": ["x", "y"],
                    "status": "待修复",
                }),
                encoding="utf-8",
            )
            result = self.run_cli(
                "add", "--file", str(target), "--from-json", str(payload), check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            combined = result.stdout + result.stderr
            self.assertIn("必须是字符串", combined)
            text = target.read_text(encoding="utf-8")
            self.assertNotIn("['x', 'y']", text)

    def test_bug064_add_does_not_rewrite_summary_over_glued_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            original = (
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                f"{self._zh_dual_header()}\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | real | 2026-01-01 10:00 | - | 待修复 | n |\n\n"
                "## 统计摘要\n\n"
                "| 分类 | 总数 | 已完成 | 待开发/待修复 | 完成率 |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| 代码 Bug | 1 | 0 | 1 | 0% |\n"
                f"{self._zh_adj_header()}\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| ADJ-001 | 调整 | glued | 2026-01-01 10:00 | - | 待办 | n |\n\n"
                "## 功能开发\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
            )
            target.write_text(original, encoding="utf-8")
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "should-roll-back",
                "--status", "待修复",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_text(encoding="utf-8"), original)
            self.assertIn("| ADJ-001 |", target.read_text(encoding="utf-8"))

    def test_bug065_add_rejects_completed_before_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "reversed",
                "--status", "已修复",
                "--found-time", "2026-06-02 10:00",
                "--completed-time", "2026-06-01 10:00",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("完成时间不能早于发现时间", result.stdout + result.stderr)
            self.assertNotIn("| BUG-001 |", target.read_text(encoding="utf-8"))

    def test_bug065_update_rejects_clearing_completed_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "done",
                "--status", "已修复",
                "--found-time", "2026-06-01 10:00",
                "--completed-time", "2026-06-02 10:00",
            )
            result = self.run_cli(
                "update", "--file", str(target), "--id", "BUG-001",
                "--completed-time", "-",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("不能将完成时间设为 -", result.stdout + result.stderr)
            text = target.read_text(encoding="utf-8")
            self.assertIn("2026-06-02 10:00", text)

    def test_bug066_check_flags_short_separator_unpadded_date_and_lowercase_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            sep = Path(tmp) / "sep.md"
            sep.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                f"{self._zh_dual_header()}\n"
                "| -- | -- | -- | -- | -- | -- | -- |\n"
                "| BUG-001 | 修复 | real | 2026-01-01 10:00 | - | 待修复 | n |\n",
                encoding="utf-8",
            )
            sep_result = self.run_cli("check", "--file", str(sep), check=False)
            self.assertNotEqual(sep_result.returncode, 0)
            self.assertIn("分隔行", sep_result.stdout + sep_result.stderr)

            unpadded = Path(tmp) / "date.md"
            unpadded.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                f"{self._zh_dual_header()}\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | real | 2026-1-1 10:00 | - | 待修复 | n |\n",
                encoding="utf-8",
            )
            date_result = self.run_cli("check", "--file", str(unpadded), check=False)
            self.assertNotEqual(date_result.returncode, 0)
            self.assertIn("2026-1-1", date_result.stdout + date_result.stderr)

            lower = Path(tmp) / "lower.md"
            lower.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| id | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | real | 2026-01-01 10:00 | - | 待修复 | n |\n",
                encoding="utf-8",
            )
            lower_result = self.run_cli("check", "--file", str(lower), check=False)
            self.assertNotEqual(lower_result.returncode, 0)
            self.assertIn("表头与标准不一致", lower_result.stdout + lower_result.stderr)

    def test_bug067_escape_backslash_and_date_only_time_reverse(self):
        mod = load_cli_module()
        logical = r"C:\|foo"
        encoded = mod.escape_cell(logical)
        self.assertEqual(encoded, r"C:\\\|foo")
        self.assertEqual(mod.split_cells("| " + encoded + " |"), [logical])
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                f"{self._zh_dual_header()}\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | real | 2026-01-02 | 2026-01-01 | 已修复 | n |\n",
                encoding="utf-8",
            )
            result = self.run_cli("standardize", "--file", str(target))
            self.assertIn("完成时间早于发现时间", result.stdout)

    def test_bug068_unbraced_project_dir_archive_locale_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target), "--lang", "en")
            (Path(tmp) / "CLAUDE.md").write_text(
                "## Session-end Task Sync\n\nRule.\n", encoding="utf-8"
            )
            claude_dir = Path(tmp) / ".claude"
            hooks = claude_dir / "hooks"
            hooks.mkdir(parents=True)
            script = hooks / "tasklist_sync_reminder.sh"
            script.write_text("#!/bin/bash\n", encoding="utf-8")
            (claude_dir / "settings.json").write_text(
                json.dumps({
                    "hooks": {
                        "Stop": [{
                            "matcher": "",
                            "hooks": [{
                                "type": "command",
                                "command": 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/tasklist_sync_reminder.sh"',
                            }],
                        }]
                    }
                }),
                encoding="utf-8",
            )
            result = self.run_cli("standardize", "--file", str(target), "--format", "json")
            maint = json.loads(result.stdout)["maintenance"]
            self.assertTrue(maint["hook_installed"])
            self.assertFalse(maint.get("claude_hook_broken"))

            en = Path(tmp) / "en.md"
            en.write_text(
                "# Task Tracking List\n\n"
                "## Bugs\n\n"
                "| ID | Action | Description | Found | Done | Status | Notes |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | Fix | old | 2020-01-01 10:00 | 2020-01-02 10:00 | Fixed | n |\n"
                "| BUG-002 | Fix | keep | 2026-08-01 10:00 | - | Pending Fix | see [[BUG-001]] |\n",
                encoding="utf-8",
            )
            arch = self.run_cli(
                "archive", "--file", str(en),
                "--older-than-days", "30", "--as-of", "2026-08-13",
                check=False,
            )
            combined = arch.stdout + arch.stderr
            self.assertNotEqual(arch.returncode, 0)
            self.assertNotIn("第 ", combined)
            self.assertIn("line ", combined.lower())

            os.chmod(target, 0o644)
            self.run_cli(
                "add", "--file", str(target), "--section", "Bugs",
                "--action", "Fix", "--description", "perm", "--status", "Pending Fix",
            )
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o644)
