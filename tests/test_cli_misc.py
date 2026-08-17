"""CLI regression tests (split from the former monolithic file)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase, load_cli_module  # noqa: E402


class CliMiscTest(CliTestCase):
    def test_fix_only_does_not_apply_safe_fixes(self):
        # Regression: --fix-only is an output modifier and must NOT add missing sections.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )
            result = self.run_cli("standardize", "--file", str(target), "--fix-only")
            self.assertIn("修复完成", result.stdout)
            text = target.read_text(encoding="utf-8")
            self.assertNotIn("## 调整事项", text)
            self.assertNotIn("## 配置运维", text)

    def test_bad_action_lists_allowed_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            result = self.run_cli(
                "add", "--file", str(target), "--section", "配置运维",
                "--action", "部署", "--description", "x", "--status", "待办",
                check=False,
            )
            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("部署", combined)
            self.assertIn("运维", combined)
            self.assertIn("修复", combined)

    def test_section_prefix_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target), "--profile", "extended")
            for section, expect_prefix in (
                ("CHK", "CHK-001"),
                ("ADJ", "ADJ-001"),
                ("TST", "TST-001"),
                ("检查", "CHK-002"),
                ("调整", "ADJ-002"),
                ("测试", "TST-002"),
                ("PLN", "PLN-001"),
                ("RES", "RES-001"),
                ("规划", "PLN-002"),
                ("调研", "RES-002"),
            ):
                result = self.run_cli(
                    "add", "--file", str(target), "--section", section,
                    "--action", "检查" if expect_prefix.startswith(("CHK", "RES")) else (
                        "规划" if expect_prefix.startswith("PLN") else (
                            "调整" if expect_prefix.startswith("ADJ") else "检查"
                        )
                    ),
                    "--description", f"via {section}",
                    "--status", "待办",
                )
                self.assertIn(f"已追加：{expect_prefix}", result.stdout)

    def test_detect_locale_ignores_english_mentions_in_notes(self):
        # Notes mentioning "# Task Tracking List" / "## Docs" must not flip a zh file to en.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "x", "--status", "待修复",
                "--notes", "参考模板 # Task Tracking List 和 ## Docs",
            )
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "y", "--status", "待修复",
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("| BUG-002 |", target.read_text(encoding="utf-8"))
            check = self.run_cli("check", "--file", str(target))
            self.assertIn("检查通过", check.stdout)

    def test_insert_row_respects_tab_heading_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n\n"
                "##\t文档维护\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "z", "--status", "待修复",
                "--no-check",
            )
            text = target.read_text(encoding="utf-8")
            bug_pos = text.find("| BUG-001 |")
            doc_pos = text.find("##\t文档维护")
            self.assertGreater(bug_pos, 0)
            self.assertLess(bug_pos, doc_pos)

    def test_warn_time_reverse(self):
        """Completed time earlier than found time should produce a quality warning."""
        mod = load_cli_module()
        text = (
            "# 任务跟踪列表\n\n## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | reverse | 2026-08-10 10:00 | 2026-08-09 10:00 | 已修复 | ok |\n"
        )
        records = mod.collect_records(text)
        headers = mod.section_headers_by_title(text)
        warnings = mod.record_quality_warnings(records, mod.get_locale("zh"), headers)
        self.assertTrue(any("完成时间早于发现时间" in w for w in warnings))

    def test_warn_id_not_ascending(self):
        """IDs going backwards within a section should produce a warning."""
        mod = load_cli_module()
        text = (
            "# 任务跟踪列表\n\n## 调整事项\n\n"
            "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| ADJ-018 | 调整 | a | 2026-01-01 10:00 | - | 待办 | x |\n"
            "| ADJ-014 | 调整 | b | 2026-01-02 10:00 | - | 待办 | y |\n"
        )
        records = mod.collect_records(text)
        headers = mod.section_headers_by_title(text)
        warnings = mod.record_quality_warnings(records, mod.get_locale("zh"), headers)
        self.assertTrue(any("行序回退" in w and "ADJ-018" in w and "ADJ-014" in w for w in warnings))

    def test_warn_duplicate_records(self):
        """Two records with identical cells (except ID) should be flagged."""
        mod = load_cli_module()
        text = (
            "# 任务跟踪列表\n\n## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | dup | 2026-01-01 10:00 | 2026-01-02 10:00 | 已修复 | same |\n"
            "| BUG-002 | 修复 | dup | 2026-01-01 10:00 | 2026-01-02 10:00 | 已修复 | same |\n"
        )
        records = mod.collect_records(text)
        headers = mod.section_headers_by_title(text)
        warnings = mod.record_quality_warnings(records, mod.get_locale("zh"), headers)
        self.assertTrue(any("完全相同" in w for w in warnings))

    def test_optimize_threshold_single_record_no_suggestion(self):
        """A single optimize record should NOT trigger extended-profile suggestion."""
        mod = load_cli_module()
        text = (
            "# 任务跟踪列表\n\n## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 优化 | single | 2026-01-01 10:00 | - | 待办 | - |\n"
            "| BUG-002 | 修复 | other | 2026-01-02 10:00 | - | 待办 | - |\n"
            "| BUG-003 | 修复 | other | 2026-01-03 10:00 | - | 待办 | - |\n"
            "| BUG-004 | 修复 | other | 2026-01-04 10:00 | - | 待办 | - |\n"
        )
        sections = mod.parse_sections(text)
        records = mod.collect_records(text)
        recs = mod.classify_extension_recommendations(
            "minimal", "minimal", records, sections, mod.get_locale("zh")
        )
        opt_recs = [r for r in recs if "优化" in r and "分区" in r]
        self.assertEqual(len(opt_recs), 0)

    def test_apply_safe_fixes_removes_intra_table_blank_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._preview_safety_file(blank_between=True), encoding="utf-8")
            self.run_cli(
                "standardize", "--file", str(target),
                "--apply-safe-fixes", "--fix-only",
            )
            text = target.read_text(encoding="utf-8")
            bug_block = text.split("## 调整事项")[0]
            self.assertNotRegex(bug_block, r"\| BUG-001 .*\n\n\| BUG-002")
            self.assertIn("\n\n## 调整事项", text)
            after = self.run_cli("check", "--file", str(target))
            self.assertEqual(after.returncode, 0)

    def test_legacy_research_rec_mentions_moving_section(self):
        # DEV-018: rename-in-place left 调研 in the wrong template slot.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "## 开源项目调研\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| RES-001 | 检查 | x | 2026-01-01 00:00 | - | 待办 | n |\n",
                encoding="utf-8",
            )
            result = self.run_cli("standardize", "--file", str(target))
            self.assertIn("开源项目调研", result.stdout)
            self.assertIn("整段移到", result.stdout)
