"""REQ-07: summary --policy auto|by-section|by-prefix and refusal on caliber conflict.

A record whose ID prefix doesn't match its physical section (e.g. DEV-003 sitting in
检查事项) makes the by-prefix and by-section calibers disagree. Under --policy auto a
write must be refused (non-zero exit, file byte-identical) and the report must list
BOTH calibers; an explicit --policy is required to rewrite the summary.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase  # noqa: E402


class CliSummaryPolicyTest(CliTestCase):
    def _conflicted_zh(self, *, dev_total="4", chk_total="1") -> str:
        """Dual-schema ledger with DEV-003/004 misplaced into 检查事项.

        by-section: 代码 Bug 1/1, 功能开发 2/2, 检查事项 3/3.
        by-prefix:  代码 Bug 1/1, 功能开发 4/4, 检查事项 1/1.
        The written summary defaults to the by-prefix caliber.
        """
        return (
            "# 任务跟踪列表\n\n"
            "## 统计摘要\n\n"
            "| 分类 | 总数 | 已完成 | 待开发/待修复 | 完成率 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 代码 Bug | 1 | 1 | 0 | 100% |\n"
            f"| 功能开发 | {dev_total} | {dev_total} | 0 | 100% |\n"
            f"| 检查事项 | {chk_total} | {chk_total} | 0 | 100% |\n"
            "| **总计** | 6 | 6 | 0 | 100% |\n"
            "\n## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | 示例 | 2026-01-05 10:00 | 2026-01-05 11:00 | 已修复 | - |\n"
            "\n## 功能开发\n\n"
            "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| DEV-001 | 开发 | 示例 | 2026-01-05 10:00 | 2026-01-05 11:00 | 已完成 | - |\n"
            "| DEV-002 | 开发 | 示例 | 2026-01-05 10:00 | 2026-01-05 11:00 | 已完成 | - |\n"
            "\n## 检查事项\n\n"
            "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| CHK-001 | 检查 | 示例 | 2026-01-05 10:00 | 2026-01-05 11:00 | 已完成 | - |\n"
            "| DEV-003 | 开发 | 错位一 | 2026-01-06 10:00 | 2026-01-06 11:00 | 已完成 | - |\n"
            "| DEV-004 | 开发 | 错位二 | 2026-01-06 10:00 | 2026-01-06 11:00 | 已完成 | - |\n"
        )

    def _conflicted_en(self) -> str:
        return (
            "# Task Tracking List\n\n"
            "## Summary\n\n"
            "| Category | Total | Done | Pending | Rate |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| Bugs | 1 | 1 | 0 | 100% |\n"
            "| Features | 4 | 4 | 0 | 100% |\n"
            "| Reviews | 1 | 1 | 0 | 100% |\n"
            "| **Total** | 6 | 6 | 0 | 100% |\n"
            "\n## Bugs\n\n"
            "| ID | Action | Description | Found | Done | Status | Notes |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | Fix | sample | 2026-01-05 10:00 | 2026-01-05 11:00 | Fixed | - |\n"
            "\n## Features\n\n"
            "| ID | Action | Item | Found | Done | Status | Notes |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| DEV-001 | Build | sample | 2026-01-05 10:00 | 2026-01-05 11:00 | Done | - |\n"
            "| DEV-002 | Build | sample | 2026-01-05 10:00 | 2026-01-05 11:00 | Done | - |\n"
            "\n## Reviews\n\n"
            "| ID | Action | Item | Found | Done | Status | Notes |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| CHK-001 | Review | sample | 2026-01-05 10:00 | 2026-01-05 11:00 | Done | - |\n"
            "| DEV-003 | Build | misplaced | 2026-01-06 10:00 | 2026-01-06 11:00 | Done | - |\n"
            "| DEV-004 | Build | misplaced | 2026-01-06 10:00 | 2026-01-06 11:00 | Done | - |\n"
        )

    def test_auto_refuses_write_on_conflict_and_keeps_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            original = self._conflicted_zh()
            target.write_text(original, encoding="utf-8")

            result = self.run_cli("summary", "--file", str(target), "--write", "--policy", "auto", check=False)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), original)
            self.assertIn("按前缀统计", result.stdout)
            self.assertIn("按分区统计", result.stdout)
            # Both calibers must be listed: prefix 4/1 vs section 2/3 (REQ-07 acceptance).
            self.assertIn("功能开发", result.stdout)
            self.assertIn("总数 4", result.stdout)
            self.assertIn("总数 2", result.stdout)
            self.assertIn("总数 1", result.stdout)
            self.assertIn("总数 3", result.stdout)
            self.assertIn("已拒绝写入", result.stdout)
            self.assertIn("与「按前缀」口径一致", result.stdout)
            self.assertIn("--policy by-prefix", result.stdout)
            self.assertIn("--policy by-section", result.stdout)

    def test_default_policy_is_auto(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            original = self._conflicted_zh()
            target.write_text(original, encoding="utf-8")

            result = self.run_cli("summary", "--file", str(target), "--write", check=False)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), original)
            self.assertIn("已拒绝写入", result.stdout)

    def test_auto_dry_run_refused_on_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            original = self._conflicted_zh()
            target.write_text(original, encoding="utf-8")

            result = self.run_cli(
                "summary", "--file", str(target), "--write", "--dry-run", check=False
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), original)
            self.assertIn("已拒绝写入", result.stdout)

    def test_auto_refuses_when_neither_caliber_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            original = self._conflicted_zh(dev_total="9")
            target.write_text(original, encoding="utf-8")

            result = self.run_cli("summary", "--file", str(target), "--write", check=False)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), original)
            self.assertIn("与两种口径均不一致", result.stdout)
            self.assertIn("按前缀统计", result.stdout)
            self.assertIn("按分区统计", result.stdout)

    def test_by_prefix_write_preserves_prefix_caliber(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._conflicted_zh(), encoding="utf-8")

            self.run_cli(
                "summary", "--file", str(target), "--write", "--policy", "by-prefix"
            )

            text = target.read_text(encoding="utf-8")
            self.assertIn("| 功能开发 | 4 | 4 | 0 | 100% |", text)
            self.assertIn("| 检查事项 | 1 | 1 | 0 | 100% |", text)
            self.assertNotIn("| 检查事项 | 3 |", text)

    def test_by_section_write_uses_physical_caliber(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._conflicted_zh(), encoding="utf-8")

            self.run_cli("summary", "--file", str(target), "--write", "--policy", "by-section")

            text = target.read_text(encoding="utf-8")
            self.assertIn("| 功能开发 | 2 | 2 | 0 | 100% |", text)
            self.assertIn("| 检查事项 | 3 | 3 | 0 | 100% |", text)
            self.assertNotIn("| 功能开发 | 4 |", text)

    def test_auto_write_succeeds_when_calibers_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target), "--with-summary")
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "已修复bug",
                "--status", "已修复",
            )

            self.run_cli(
                "summary", "--file", str(target), "--write", "--policy", "auto"
            )

            text = target.read_text(encoding="utf-8")
            self.assertIn("| 代码 Bug | 1 | 1 | 0 | 100% |", text)

    def test_readonly_auto_reports_conflict_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            original = self._conflicted_zh()
            target.write_text(original, encoding="utf-8")

            result = self.run_cli("summary", "--file", str(target), check=False)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), original)
            self.assertIn("口径冲突", result.stdout)
            self.assertIn("按前缀统计", result.stdout)
            self.assertIn("按分区统计", result.stdout)

    def test_readonly_by_prefix_shows_prefix_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._conflicted_zh(), encoding="utf-8")

            result = self.run_cli(
                "summary", "--file", str(target), "--policy", "by-prefix", check=False
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("按前缀统计", result.stdout)
            self.assertIn("- 功能开发: 4", result.stdout)
            self.assertIn("- 检查事项: 1", result.stdout)

    def test_add_does_not_silently_rewrite_conflicted_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._conflicted_zh(), encoding="utf-8")

            result = self.run_cli(
                "add", "--file", str(target), "--section", "功能开发",
                "--action", "开发", "--description", "新增开发事项", "--status", "已完成",
            )

            text = target.read_text(encoding="utf-8")
            self.assertIn("DEV-005", text)
            # The by-prefix summary must survive: add must not re-bucket it by section.
            self.assertIn("| 功能开发 | 4 | 4 | 0 | 100% |", text)
            self.assertNotIn("| 功能开发 | 3 |", text)
            self.assertIn("跳过统计摘要同步", result.stderr)

    def test_bug069_check_accepts_by_prefix_summary(self):
        # BUG-069: a summary written with --policy by-prefix is this tool's own output;
        # check must judge it against the by-prefix caliber, not flag it as drift.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._conflicted_zh(), encoding="utf-8")

            self.run_cli("summary", "--file", str(target), "--write", "--policy", "by-prefix")
            result = self.run_cli("check", "--file", str(target), check=False)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("检查通过", result.stdout)
            self.assertNotIn("摘要表过期", result.stdout)

    def test_bug069_check_flags_drift_when_neither_caliber_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._conflicted_zh(dev_total="9"), encoding="utf-8")

            result = self.run_cli("check", "--file", str(target), check=False)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("摘要表过期", result.stdout)

    def test_bug070_pending_wording_is_unified(self):
        # BUG-070: the pending column must read 待开发/待修复 everywhere, matching the
        # rendered summary header (conflict report and drift messages alike).
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            original = self._conflicted_zh(dev_total="9").replace(
                "| 代码 Bug | 1 | 1 | 0 | 100% |", "| 代码 Bug | 1 | 1 | 1 | 100% |"
            )
            target.write_text(original, encoding="utf-8")

            result = self.run_cli("summary", "--file", str(target), "--write", check=False)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("待开发/待修复", result.stdout)
            self.assertNotIn("待开发 {", result.stdout)

            check = self.run_cli("check", "--file", str(target), check=False)
            self.assertIn("待开发/待修复", check.stdout)

    def test_write_path_discloses_excluded_rows(self):
        # REQ-06 + REQ-07 interaction: when width-mismatched rows are excluded the two
        # calibers can agree (no conflict), so auto may rewrite — but the number change
        # (totals dropping the broken rows) must never be silent, and --dry-run stdout
        # must stay a clean copy of the file content (note goes to stderr).
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._conflicted_zh().replace(
                "| DEV-003 | 开发 | 错位一 | 2026-01-06 10:00 | 2026-01-06 11:00 | 已完成 | - |",
                "| DEV-003 | 开发 | 错位一 | 2026-01-06 10:00 | 2026-01-06 11:00 | 已完成 | 备注 | 多一列 |",
            ).replace(
                "| DEV-004 | 开发 | 错位二 | 2026-01-06 10:00 | 2026-01-06 11:00 | 已完成 | - |",
                "| DEV-004 | 开发 | 错位二 | 2026-01-06 10:00 | 2026-01-06 11:00 | 已完成 | 备注 | 多一列 |",
            ), encoding="utf-8")

            result = self.run_cli("summary", "--file", str(target), "--write", check=False)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("2 行因列数与表头不符未参与统计", result.stderr)
            text = target.read_text(encoding="utf-8")
            # Both misplaced DEV rows excluded: 开发 2 (DEV-001/002), 检查 1 (CHK-001).
            self.assertIn("| 功能开发 | 2 | 2 | 0 | 100% |", text)
            self.assertIn("| 检查事项 | 1 | 1 | 0 | 100% |", text)

            dry = self.run_cli(
                "summary", "--file", str(target), "--write", "--dry-run", check=False
            )
            self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
            self.assertNotIn("未参与统计", dry.stdout)
            self.assertIn("未参与统计", dry.stderr)

    def _conflicted_zh_by_section_summary(self) -> str:
        """Same misplaced records as _conflicted_zh, but the written summary is the
        by-section caliber: 代码 Bug 1, 功能开发 2, 检查事项 3 (physical placement)."""
        return self._conflicted_zh(dev_total="2", chk_total="3")

    def test_bug073_add_syncs_by_section_summary_despite_conflict(self):
        # BUG-073: the caliber judgment must run on the PRE-write text. On post-write
        # text the old summary numbers match neither caliber, so a by-section summary
        # was misjudged as ambiguous and the sync wrongly skipped (stale 总计).
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._conflicted_zh_by_section_summary(), encoding="utf-8")

            result = self.run_cli(
                "add", "--file", str(target), "--section", "功能开发",
                "--action", "开发", "--description", "新增开发事项", "--status", "已完成",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("跳过统计摘要同步", result.stderr)
            self.assertIn("已同步统计摘要", result.stdout)
            text = target.read_text(encoding="utf-8")
            self.assertIn("| 功能开发 | 3 | 3 | 0 | 100% |", text)
            self.assertIn("| **总计** | 7 | 7 | 0 | 100% |", text)
            check = self.run_cli("check", "--file", str(target), check=False)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_bug073_update_syncs_by_section_summary_despite_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._conflicted_zh_by_section_summary(), encoding="utf-8")

            result = self.run_cli(
                "update", "--file", str(target), "--id", "DEV-001", "--notes", "补充",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("跳过统计摘要同步", result.stderr)
            text = target.read_text(encoding="utf-8")
            self.assertIn("| 功能开发 | 2 | 2 | 0 | 100% |", text)

    def test_bug073_add_still_skips_by_prefix_summary_on_conflict(self):
        # The guard must still hold when the written caliber is by-prefix: add must not
        # re-bucket an ambiguous summary (existing by-prefix scenario stays skipped).
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._conflicted_zh(), encoding="utf-8")

            result = self.run_cli(
                "add", "--file", str(target), "--section", "功能开发",
                "--action", "开发", "--description", "新增开发事项", "--status", "已完成",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("跳过统计摘要同步", result.stderr)
            text = target.read_text(encoding="utf-8")
            self.assertIn("| 功能开发 | 4 | 4 | 0 | 100% |", text)

    def test_bug074_dry_run_alone_stays_readonly(self):
        # BUG-074: a bare --dry-run (without --write) must stay on the read-only stats
        # view — not print the whole rewritten file, not refuse with exit 1 on conflict.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            original = self._conflicted_zh()
            target.write_text(original, encoding="utf-8")

            result = self.run_cli("summary", "--file", str(target), "--dry-run", check=False)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), original)
            self.assertNotIn("已拒绝写入", result.stdout)
            # Read-only view prints counts, not the rewritten file content.
            self.assertNotIn("| BUG-001 | 修复 | 示例 |", result.stdout)
            self.assertIn("口径冲突", result.stdout)

    def test_en_locale_refusal_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            original = self._conflicted_en()
            target.write_text(original, encoding="utf-8")

            result = self.run_cli(
                "summary", "--file", str(target), "--write", "--policy", "auto", check=False
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), original)
            self.assertIn("Write refused", result.stdout)
            self.assertIn("By ID prefix", result.stdout)
            self.assertIn("By section", result.stdout)


if __name__ == "__main__":
    unittest.main()
