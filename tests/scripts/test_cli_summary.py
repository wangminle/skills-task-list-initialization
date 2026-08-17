"""CLI regression tests (split from the former monolithic file)."""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase, load_cli_module  # noqa: E402


class CliSummaryTest(CliTestCase):
    def test_summary_write_recomputes_statistics_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target), "--with-summary")
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "已修复bug",
                "--found-time", "2026-06-18 09:00", "--completed-time", "2026-06-18 10:00",
                "--status", "已修复",
            )
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "待修bug",
                "--found-time", "2026-06-18 11:00", "--completed-time", "-",
                "--status", "待修复",
            )

            result = self.run_cli("summary", "--file", str(target), "--write")
            self.assertIn("已更新统计摘要", result.stdout)

            text = target.read_text(encoding="utf-8")
            self.assertIn("| 代码 Bug | 2 | 1 | 1 | 50% |", text)
            self.assertIn("| **总计** | 2 | 1 | 1 | 50% |", text)

    def test_summary_excludes_width_mismatched_rows_from_stats(self):
        # REQ-06: rows whose cell count disagrees with the header (unescaped | in a
        # cell) must not feed statistics - previously the notes fragment surfaced in
        # the status distribution and totals counted the broken row.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | 正常行 | 2026-08-17 09:00 | - | 待修复 | - |\n"
                "| BUG-002 | 修复 | 异常行 | 2026-08-17 09:30 | - | 待修复 | note with | 1.5h |\n",
                encoding="utf-8",
            )
            result = self.run_cli("summary", "--file", str(target))
            self.assertIn("代码 Bug: 1", result.stdout)
            self.assertIn("待修复: 1", result.stdout)
            self.assertIn("总计：1", result.stdout)
            self.assertIn("1 行因列数与表头不符未参与统计", result.stdout)
            self.assertNotIn("1.5h", result.stdout)

    def test_summary_write_excludes_width_mismatched_rows(self):
        # REQ-06 on the write path: recomputed summary counts only well-formed rows;
        # the broken row stays in the file untouched (escaping it is a separate fix).
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 检查事项\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| CHK-001 | 检查 | 正常 | 2026-08-17 09:00 | 2026-08-17 10:00 | 已完成 | - |\n"
                "| CHK-002 | 检查 | 异常 | 2026-08-17 09:30 | 2026-08-17 11:00 | 已完成 | note | 1.5h |\n",
                encoding="utf-8",
            )
            result = self.run_cli("summary", "--file", str(target), "--write")
            self.assertIn("已更新统计摘要", result.stdout)
            text = target.read_text(encoding="utf-8")
            self.assertIn("| 检查事项 | 1 | 1 | 0 | 100% |", text)
            self.assertIn("| **总计** | 1 | 1 | 0 | 100% |", text)
            self.assertIn("note | 1.5h", text)

    def test_summary_write_appends_section_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.assertNotIn("## 统计摘要", target.read_text(encoding="utf-8"))

            self.run_cli("summary", "--file", str(target), "--write")

            text = target.read_text(encoding="utf-8")
            self.assertIn("## 统计摘要", text)
            self.assertIn("| **总计** | 0 | 0 | 0 | 0% |", text)

    def test_migrate_schema_fix_only_does_not_add_sections(self):
        # Regression: --migrate-schema --fix-only migrates the schema but must NOT add
        # missing sections (that requires --apply-safe-fixes).
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | 旧bug | 2026-06-17 | 已修复 | ok |\n",
                encoding="utf-8",
            )
            self.run_cli("standardize", "--file", str(target), "--migrate-schema", "--fix-only")
            text = target.read_text(encoding="utf-8")
            # schema migrated to 7 columns...
            self.assertIn("| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |", text)
            # BUG-026: no cross-semantic copy / no fabricated 00:00
            self.assertIn("| BUG-001 | 修复 | 旧bug | 2026-06-17 | - | 已修复 | ok |", text)
            # ...but no missing sections added
            self.assertNotIn("## 调整事项", text)

    def test_summary_write_english(self):
        # summary --write recomputes the English summary table (Summary / Total labels).
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--lang", "en", "--with-summary", "--output", str(target))
            self.run_cli(
                "add", "--file", str(target), "--section", "Bugs",
                "--action", "Fix", "--description", "fixed bug",
                "--found-time", "2026-06-18 09:00", "--completed-time", "2026-06-18 10:00",
                "--status", "Fixed",
            )
            self.run_cli("summary", "--file", str(target), "--write")
            text = target.read_text(encoding="utf-8")
            self.assertIn("## Summary", text)
            self.assertIn("| Category | Total | Done | Pending | Rate |", text)
            self.assertIn("| **Total** | 1 | 1 | 0 | 100% |", text)

    def test_migrate_schema_idempotent_with_escaped_pipes(self):
        # Regression: split_cells must DECODE \| → | so escape_cell re-escapes it on write,
        # making the migrate round-trip idempotent. Previously a 备注 containing \|\| got
        # double-escaped to \\|\\| on migrate (real-world hit on CHK-006/DOC-005), turning a
        # 7-col row into 9 cols. A second migrate must also be stable.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 完成日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                r"| BUG-001 | 修复 | 转义示例 | 2026-06-17 | 已修复 | ok \|\| done |" "\n",
                encoding="utf-8",
            )
            self.run_cli("standardize", "--file", str(target), "--migrate-schema", "--fix-only")
            text = target.read_text(encoding="utf-8")
            # Single-escaped pipe preserved (rendered as ||), NOT double-escaped.
            self.assertIn(r"已修复 | ok \|\| done |", text)
            self.assertNotIn(r"ok \\|\\|", text)
            # Idempotent: a second migrate must not add another backslash layer.
            self.run_cli("standardize", "--file", str(target), "--migrate-schema", "--fix-only")
            text2 = target.read_text(encoding="utf-8")
            self.assertIn(r"已修复 | ok \|\| done |", text2)
            self.assertNotIn(r"ok \\|\\|", text2)

    def test_migrate_warns_on_skipped_malformed_row(self):
        # Regression: a data row whose cell count doesn't match the legacy header — almost
        # always an unescaped literal pipe splitting one cell in two — must be reported as a
        # SKIPPED warning, not silently left behind while the header migrates. Real-world hit:
        # the prd-draft migration reported "修复完成：12 项" while two 8-col rows (BUG-057/071,
        # unescaped JS `||`) were silently left un-migrated; only a follow-up `check` caught it.
        content = (
            "# 任务跟踪列表\n\n"
            "## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 完成日期 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | 正常行 | 2026-06-17 | 已修复 | ok |\n"
            "| BUG-002 | 修复 | 含原始管道 cfg.x || 4096 的行 | 2026-06-17 | 已修复 | 见 admin.js |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(content, encoding="utf-8")
            result = self.run_cli(
                "standardize", "--file", str(target), "--migrate-schema", "--fix-only"
            )
            combined = result.stdout + result.stderr
            self.assertIn("修复完成", combined)
            # The malformed row is flagged with its ID, source line, and both column counts —
            # not silently omitted while the header counts as migrated.
            self.assertIn("BUG-002（第 8 行）", combined)
            self.assertIn("实际 8 列", combined)
            self.assertIn("legacy 表头 6 列", combined)

            # JSON consumers see migrate_warnings too (fresh un-migrated copy).
            target2 = Path(tmp) / "task-list2.md"
            target2.write_text(content, encoding="utf-8")
            result_json = self.run_cli(
                "standardize", "--file", str(target2), "--migrate-schema", "--format", "json"
            )
            payload = json.loads(result_json.stdout)
            self.assertTrue(payload.get("migrate_warnings"))

    def test_standardize_apply_safe_fixes_inserts_before_summary(self):
        # Regression BUG-020: new sections must be inserted before 统计摘要, not after it.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target), "--with-summary", "--profile", "minimal")

            self.run_cli(
                "standardize", "--file", str(target), "--profile", "extended", "--apply-safe-fixes"
            )

            text = target.read_text(encoding="utf-8")
            summary_pos = text.find("## 统计摘要")
            self.assertGreater(summary_pos, 0)
            for section in ("## 规划事项", "## 优化事项", "## 调研事项"):
                self.assertIn(section, text)
                self.assertLess(text.find(section), summary_pos, f"{section} must precede summary")
            headings = re.findall(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE)
            self.assertEqual(headings[-1], "统计摘要")

    def test_migrate_schema_refuses_reordered_dual_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            content = (
                "# 任务跟踪列表\n\n"
                "## 文档维护\n\n"
                "| ID | 状态 | 动作 | 事项 | 发现时间 | 完成时间 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| DOC-001 | 待办 | 文档 | 说明 | 2026-08-01 10:00 | - | n |\n"
            )
            target.write_text(content, encoding="utf-8")
            result = self.run_cli(
                "standardize", "--file", str(target), "--migrate-schema", "--fix-only",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("无法迁移", result.stdout + result.stderr)
            self.assertEqual(content, target.read_text(encoding="utf-8"))

    def test_archive_syncs_existing_summary(self):
        # Archiving rows out of a file with 统计摘要 must leave the summary in step,
        # otherwise the next check reports 摘要表过期.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target), "--with-summary")
            self.run_cli(
                "add", "--file", str(target), "--section", "文档维护",
                "--action", "文档", "--description", "old", "--status", "已完成",
                "--found-time", "2026-01-01 10:00", "--completed-time", "2026-01-02 10:00",
            )
            self.run_cli(
                "add", "--file", str(target), "--section", "文档维护",
                "--action", "文档", "--description", "new", "--status", "待办",
            )
            result = self.run_cli(
                "archive", "--file", str(target), "--older-than-days", "30",
                "--as-of", "2026-08-04",
            )
            self.assertIn("已归档 1 条", result.stdout)
            check = self.run_cli("check", "--file", str(target))
            self.assertIn("检查通过", check.stdout)

    def test_bug076_custom_section_with_table_gets_summary_row(self):
        # BUG-076: a custom (non-registry) section carrying a real table must appear
        # in the written summary (the read-only view already counts its records), and
        # a pure-prose section without a table must NOT get a row.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | 甲 | 2026-08-01 10:00 | 2026-08-01 11:00 | 已修复 | - |\n"
                "\n## 读书笔记\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| READ-001 | 检查 | 自定义分区记录 | 2026-08-03 10:00 | - | 待办 | - |\n"
                "\n## 附注\n\n"
                "纯文字段落，没有表格。\n",
                encoding="utf-8",
            )
            self.run_cli("summary", "--file", str(target), "--write")

            text = target.read_text(encoding="utf-8")
            self.assertIn("| 代码 Bug | 1 | 1 | 0 | 100% |", text)
            self.assertIn("| 读书笔记 | 1 | 0 | 1 | 0% |", text)
            self.assertIn("| **总计** | 2 | 1 | 1 | 50% |", text)
            self.assertNotIn("| 附注 |", text)
            check = self.run_cli("check", "--file", str(target))
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_summary_drift_catches_done_mismatch(self):
        """Changing only the done/pending counts (total stays same) must be caught."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.run_cli("add", "--file", str(target), "--section", "代码 Bug",
                         "--action", "修复", "--description", "test",
                         "--status", "已修复", "--found-time", "2026-01-01 10:00",
                         "--completed-time", "2026-01-02 10:00", "--no-check")
            self.run_cli("summary", "--file", str(target), "--write")
            # Tamper: change done=1 -> done=0, pending=0 -> pending=1 (total stays 1)
            text = target.read_text(encoding="utf-8")
            text = text.replace("| 代码 Bug | 1 | 1 | 0 |", "| 代码 Bug | 1 | 0 | 1 |")
            text = text.replace("| **总计** | **1** | **1** | **0** |",
                                "| **总计** | **1** | **0** | **1** |")
            target.write_text(text, encoding="utf-8")
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertNotEqual(result.returncode, 0)
            out = result.stdout + result.stderr
            self.assertIn("已完成", out)

    def test_rate_precision_with_pending(self):
        """1070/1074 should render as 99.6%, not 100%."""
        mod = load_cli_module()
        rows = [("test", 1074, 1070, 4)]
        rendered = mod.render_summary_with_counts(rows, mod.get_locale("zh"))
        rate_line = [line for line in rendered.splitlines() if "test" in line][0]
        self.assertIn("99.6%", rate_line)
        self.assertNotIn("100%", rate_line)

    def test_rate_capped_at_99_9_when_rounding_up(self):
        """9999/10000 must show 99.9%, never 100%."""
        mod = load_cli_module()
        rows = [("test", 10000, 9999, 1)]
        rendered = mod.render_summary_with_counts(rows, mod.get_locale("zh"))
        rate_line = [line for line in rendered.splitlines() if "test" in line][0]
        self.assertIn("99.9%", rate_line)
        self.assertNotIn("100%", rate_line)

    def test_summary_drift_catches_wrong_rate(self):
        """A summary rate cell that contradicts the record counts must be flagged.

        Reproduces the audit finding: an existing file with a hand-written 100% rate
        that should be 99.6% (e.g. 1070/1074 done) was silently accepted because the
        rate column was never compared — only total/done/pending were. Now the rate
        field participates in the drift check.
        """
        mod = load_cli_module()
        locale = mod.get_locale("zh")
        # 1074 total, 1070 done, 4 pending. Correct rate = 99.6%.
        # Build 1070 done records is impractical; instead test the comparator
        # directly with a summary table whose rate is wrong relative to its own
        # done/total (which is exactly the stored-file failure mode).
        text = (
            "# 任务跟踪列表\n\n"
            "> 说明：test\n\n"
            "## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | - |\n"
            "| BUG-002 | 修复 | y | 2026-01-02 10:00 | 2026-01-03 10:00 | 已修复 | - |\n"
            "\n## 统计摘要\n\n"
            "| 分类 | 总数 | 已完成 | 待开发/待修复 | 完成率 |\n"
            "| --- | --- | --- | --- | --- |\n"
            # actual: total=2 done=1 pending=1 → correct rate 50%, written 100% (wrong)
            "| 代码 Bug | 2 | 1 | 1 | 100% |\n"
            "| **总计** | **2** | **1** | **1** | **100%** |\n"
        )
        issues = mod.summary_drift_issues(text, locale)
        rate_issues = [i for i in issues if "完成率" in i or "rate" in i.lower()]
        self.assertGreater(len(rate_issues), 0, f"expected rate drift, got {issues}")

    def test_summary_drift_tolerates_rounding(self):
        """A rate that matches within rounding tolerance must NOT be flagged.

        1/3 → 33.333...% rounds to 33.3% at 1-decimal render precision. A stored 33.3%
        is correct within tolerance, so it must not produce a false positive.
        """
        mod = load_cli_module()
        locale = mod.get_locale("zh")
        text = (
            "# 任务跟踪列表\n\n"
            "> 说明：test\n\n"
            "## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | x | 2026-01-01 10:00 | 2026-01-02 10:00 | 已修复 | - |\n"
            "| BUG-002 | 修复 | y | 2026-01-02 10:00 | - | 待修复 | - |\n"
            "| BUG-003 | 修复 | z | 2026-01-03 10:00 | - | 待修复 | - |\n"
            "\n## 统计摘要\n\n"
            "| 分类 | 总数 | 已完成 | 待开发/待修复 | 完成率 |\n"
            "| --- | --- | --- | --- | --- |\n"
            # actual: 1/3 = 33.333% → renders as 33.3%. Written 33.3% is within tolerance.
            "| 代码 Bug | 3 | 1 | 2 | 33.3% |\n"
            "| **总计** | **3** | **1** | **2** | **33.3%** |\n"
        )
        issues = mod.summary_drift_issues(text, locale)
        rate_issues = [i for i in issues if "完成率" in i or "rate" in i.lower()]
        self.assertEqual(rate_issues, [], f"should tolerate rounding, got {rate_issues}")

    def test_req15_rate_one_decimal_matches_history(self):
        """REQ-15: 21/22 renders as 95.5% (one decimal, no pure-format diff vs history)
        and 114/114-style full completion renders as 100% (trailing zeros stripped)."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            rows = "\n".join(
                f"| BUG-{i:03d} | 修复 | 示例 | 2026-01-01 09:00 | "
                f"{'2026-01-05 10:00' if i <= 21 else '-'} | "
                f"{'已修复' if i <= 21 else '待修复'} | - |"
                for i in range(1, 23)
            )
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                f"{rows}\n",
                encoding="utf-8",
            )
            self.run_cli("summary", "--file", str(target), "--write")
            text = target.read_text(encoding="utf-8")
            self.assertIn("| 代码 Bug | 22 | 21 | 1 | 95.5% |", text)

            # All 22 done → 100%, not 100.0%.
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                f"{rows.replace('2026-01-01 09:00 | - | 待修复', '2026-01-01 09:00 | 2026-01-06 10:00 | 已修复')}\n",
                encoding="utf-8",
            )
            self.run_cli("summary", "--file", str(target), "--write")
            self.assertIn("| 代码 Bug | 22 | 22 | 0 | 100% |", target.read_text(encoding="utf-8"))

    def test_bug076_custom_section_included_in_written_summary(self):
        """BUG-076: an unregistered custom section carrying a real table must appear in
        the summary --write table and the totals, matching the read-only view (the old
        code silently dropped it, undercounting 总计)."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | a | 2026-01-01 09:00 | - | 待修复 | - |\n"
                "\n## 临时跟踪\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| FOO-001 | 修复 | custom section | 2026-01-01 09:00 | - | 待修复 | - |\n",
                encoding="utf-8",
            )
            self.run_cli("summary", "--file", str(target), "--write")
            text = target.read_text(encoding="utf-8")
            self.assertIn("| 代码 Bug | 1 | 0 | 1 | 0% |", text)
            self.assertIn("| 临时跟踪 | 1 | 0 | 1 | 0% |", text)
            self.assertIn("| **总计** | 2 | 0 | 2 | 0% |", text)
