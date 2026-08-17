"""CLI regression tests (split from the former monolithic file)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase, load_cli_module  # noqa: E402


class CliArchiveTest(CliTestCase):
    def test_bug073_archive_syncs_by_section_summary_despite_conflict(self):
        # BUG-073 archive path: the caliber judgment must use the PRE-archive text.
        # With a by-section summary and a misplaced DEV record (calibers conflict),
        # archiving completed rows must still sync the summary — the old code judged
        # on the post-archive text where the stale summary matched neither caliber
        # and wrongly skipped the sync.
        content = (
            "# 任务跟踪列表\n\n"
            "## 统计摘要\n\n"
            "| 分类 | 总数 | 已完成 | 待开发/待修复 | 完成率 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 功能开发 | 2 | 2 | 0 | 100% |\n"
            "| 检查事项 | 3 | 2 | 1 | 66.7% |\n"
            "| **总计** | 5 | 4 | 1 | 80% |\n"
            "\n## 功能开发\n\n"
            "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| DEV-001 | 开发 | 甲 | 2026-01-05 10:00 | 2026-01-05 11:00 | 已完成 | - |\n"
            "| DEV-002 | 开发 | 乙 | 2026-01-05 10:00 | 2026-01-05 11:00 | 已完成 | - |\n"
            "\n## 检查事项\n\n"
            "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| CHK-001 | 检查 | 丙 | 2026-01-05 10:00 | 2026-01-05 11:00 | 已完成 | - |\n"
            "| CHK-002 | 检查 | 丁（未完成） | 2026-08-10 10:00 | - | 待办 | - |\n"
            "| DEV-003 | 开发 | 错位 | 2026-01-06 10:00 | 2026-01-06 11:00 | 已完成 | - |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            archive = Path(tmp) / "out-archive.md"
            target.write_text(content, encoding="utf-8")

            result = self.run_cli(
                "archive", "--file", str(target), "--older-than-days", "0",
                "--output", str(archive),
            )

            self.assertIn("已归档 4 条", result.stdout)
            self.assertNotIn("跳过统计摘要同步", result.stderr)
            self.assertIn("已同步统计摘要", result.stdout)
            text = target.read_text(encoding="utf-8")
            # Only CHK-002 remains: 功能开发 0, 检查事项 1, 总计 1.
            self.assertIn("| 功能开发 | 0 | 0 | 0 | 0% |", text)
            self.assertIn("| 检查事项 | 1 | 0 | 1 | 0% |", text)
            self.assertIn("| **总计** | 1 | 0 | 1 | 0% |", text)
            for path in (target, archive):
                check = self.run_cli("check", "--file", str(path))
                self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_archive_moves_old_completed_records(self):
        content = (
            "# 任务跟踪列表\n\n"
            "## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | old done | 2026-01-01 10:00 | 2026-01-02 10:00 | 已修复 | n |\n"
            "| BUG-002 | 修复 | recent done | 2026-07-01 10:00 | 2026-07-02 10:00 | 已修复 | n |\n"
            "| BUG-003 | 修复 | still open | 2026-01-01 10:00 | - | 待修复 | n |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(content, encoding="utf-8")
            archive = Path(tmp) / "task-list-archive-202601.md"
            result = self.run_cli(
                "archive", "--file", str(target),
                "--older-than-days", "30",
                "--as-of", "2026-07-11",
                "--output", str(archive),
            )
            self.assertEqual(result.returncode, 0)
            main = target.read_text(encoding="utf-8")
            archived = archive.read_text(encoding="utf-8")
            self.assertNotIn("BUG-001", main)
            self.assertIn("BUG-002", main)
            self.assertIn("BUG-003", main)
            self.assertIn("BUG-001", archived)
            self.assertNotIn("BUG-002", archived)
            self.assertNotIn("BUG-003", archived)

    def test_archive_refuses_output_same_as_file(self):
        # Archiving into the main file would overwrite then wipe records while reporting success.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 文档维护\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| DOC-001 | 文档 | old | 2026-01-01 10:00 | 2026-01-02 10:00 | 已完成 | n |\n",
                encoding="utf-8",
            )
            before = target.read_text(encoding="utf-8")
            result = self.run_cli(
                "archive", "--file", str(target), "--older-than-days", "30",
                "--as-of", "2026-08-04", "--output", str(target), check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("相同", result.stdout + result.stderr)
            self.assertEqual(before, target.read_text(encoding="utf-8"))

    def test_archive_merges_into_existing_archive_section(self):
        # A second same-month archive run must merge rows into the existing section
        # instead of appending a duplicate ## 文档维护 block.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            archive = Path(tmp) / "archive.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 文档维护\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| DOC-001 | 文档 | first | 2026-01-01 10:00 | 2026-01-02 10:00 | 已完成 | n |\n",
                encoding="utf-8",
            )
            self.run_cli(
                "archive", "--file", str(target), "--older-than-days", "30",
                "--as-of", "2026-08-04", "--output", str(archive),
            )
            self.run_cli(
                "add", "--file", str(target), "--section", "文档维护",
                "--action", "文档", "--description", "second", "--status", "已完成",
                "--found-time", "2026-01-03 10:00", "--completed-time", "2026-01-04 10:00",
            )
            self.run_cli(
                "archive", "--file", str(target), "--older-than-days", "30",
                "--as-of", "2026-08-04", "--output", str(archive),
            )
            text = archive.read_text(encoding="utf-8")
            self.assertEqual(text.count("## 文档维护"), 1)
            self.assertIn("first", text)
            self.assertIn("second", text)

    def test_next_id_does_not_reuse_archived_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | a | 2026-01-01 10:00 | - | 待修复 | n |\n"
                "| BUG-002 | 修复 | b | 2026-01-01 10:00 | 2026-01-02 10:00 | 已修复 | n |\n",
                encoding="utf-8",
            )
            self.run_cli(
                "archive", "--file", str(target), "--older-than-days", "30",
                "--as-of", "2026-08-04",
            )
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "new", "--status", "待修复",
            )
            text = target.read_text(encoding="utf-8")
            self.assertIn("| BUG-003 | 修复 | new |", text)
            self.assertNotIn("| BUG-002 | 修复 | new |", text)

    def test_archive_survives_id_only_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID |\n"
                "| --- |\n"
                "| BUG-001 |\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "archive", "--file", str(target), "--older-than-days", "1",
                "--as-of", "2026-08-04", check=False,
            )
            combined = result.stdout + result.stderr
            self.assertNotIn("Traceback", combined)
            self.assertNotIn("IndexError", combined)

    def test_archive_atomic_restores_on_failure(self):
        """If the archive commit fails partway, the main file must keep all records.

        Reproduces the original half-move risk: archive commits the archive file then the
        main file as one transaction. If the main-file write fails, both roll back —
        records are never left dropped from the main file without a complete archive.
        We drive commit_all in-process (matching how command_archive commits) so the
        injected os.replace fault actually takes effect.
        """
        mod = load_cli_module()

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            archive = Path(tmp) / "task-list-archive-202601.md"
            original_main = (
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | old done | 2026-01-01 10:00 | 2026-01-02 10:00 | 已修复 | n |\n"
                "| BUG-002 | 修复 | still open | 2026-01-01 10:00 | - | 待修复 | n |\n"
            )
            target.write_text(original_main, encoding="utf-8")

            archive_body = "# 任务跟踪列表（归档）\n\n## 代码 Bug\n\n| BUG-001 | ... |\n"
            main_after = original_main.replace("| BUG-001 | 修复 | old done | 2026-01-01 10:00 | 2026-01-02 10:00 | 已修复 | n |\n", "")

            # Fail os.replace only when the destination is the main file, so the archive
            # commit succeeds but the main-file commit fails — then the rollback
            # restores the archive to absent and the main file retains BUG-001.
            real_replace = os.replace

            def flaky_replace(src, dst):
                if Path(dst) == target:
                    raise OSError("simulated main-file write failure")
                return real_replace(src, dst)

            with mock.patch("os.replace", side_effect=flaky_replace):
                with self.assertRaises(OSError):
                    mod.commit_all([(archive, archive_body), (target, main_after)])

            main = target.read_text(encoding="utf-8")
            # BUG-001 must still be in the main file (roll back restored it).
            self.assertIn("BUG-001", main)
            # Archive file must not exist (it was committed then rolled back to absent).
            self.assertFalse(archive.exists())
