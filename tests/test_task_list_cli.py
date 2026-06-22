import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "task-list-initialization" / "scripts" / "task_list_cli.py"


class TaskListCliTest(unittest.TestCase):
    def run_cli(self, *args, check=True):
        result = subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if check and result.returncode != 0:
            self.fail(
                f"CLI failed with {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
        return result

    def test_init_generates_default_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))

            text = target.read_text(encoding="utf-8")
            self.assertIn("# 任务跟踪列表", text)
            self.assertIn("## 代码 Bug", text)
            self.assertIn("| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |", text)
            self.assertIn("| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |", text)
            self.assertIn("## 配置运维", text)

    def test_add_uses_next_id_and_target_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.run_cli(
                "add",
                "--file",
                str(target),
                "--section",
                "代码 Bug",
                "--action",
                "修复",
                "--description",
                "示例 bug",
                "--found-time",
                "2026-06-18 09:30",
                "--completed-time",
                "-",
                "--status",
                "待修复",
                "--notes",
                "等待处理",
            )

            text = target.read_text(encoding="utf-8")
            self.assertIn(
                "| BUG-001 | 修复 | 示例 bug | 2026-06-18 09:30 | - | 待修复 | 等待处理 |",
                text,
            )
            self.assertIn("| BUG-001 | 修复 | 示例 bug |", text.split("## 调整事项")[0])

    def test_check_reports_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            with target.open("a", encoding="utf-8") as handle:
                handle.write("\n| BUG-001 | 修复 | A | 2026-06-17 09:00 | 2026-06-17 10:00 | 已修复 | - |\n")
                handle.write("| BUG-001 | 修复 | B | 2026-06-17 09:30 | 2026-06-17 10:30 | 已修复 | - |\n")

            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("重复 ID", result.stdout)

    def test_standardize_reports_without_mutating_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            report = Path(tmp) / "standardize-report.md"
            self.run_cli("init", "--output", str(target))
            before = target.read_text(encoding="utf-8")

            result = self.run_cli("standardize", "--file", str(target), "--report", str(report))

            self.assertIn("已生成报告", result.stdout)
            self.assertEqual(before, target.read_text(encoding="utf-8"))
            report_text = report.read_text(encoding="utf-8")
            self.assertIn("# task-list 标准化诊断报告", report_text)
            self.assertIn("推荐 Profile", report_text)
            self.assertIn("推荐 Profile：minimal", report_text)

    def test_standardize_apply_safe_fixes_adds_missing_core_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )

            self.run_cli("standardize", "--file", str(target), "--apply-safe-fixes")

            text = target.read_text(encoding="utf-8")
            self.assertIn("## 调整事项", text)
            self.assertIn("## 配置运维", text)

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

    def test_summary_write_appends_section_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.assertNotIn("## 统计摘要", target.read_text(encoding="utf-8"))

            self.run_cli("summary", "--file", str(target), "--write")

            text = target.read_text(encoding="utf-8")
            self.assertIn("## 统计摘要", text)
            self.assertIn("| **总计** | 0 | 0 | 0 | 0% |", text)

    def test_standardize_fix_only_migrates_legacy_six_column_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | 旧字段 bug | 2026-06-17 | 已修复 | 已验证 |\n",
                encoding="utf-8",
            )

            result = self.run_cli("standardize", "--file", str(target), "--migrate-schema", "--fix-only")

            self.assertIn("修复完成", result.stdout)
            self.assertNotIn("# task-list 标准化诊断报告", result.stdout)
            text = target.read_text(encoding="utf-8")
            self.assertIn("| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |", text)
            self.assertIn("| BUG-001 | 修复 | 旧字段 bug | 2026-06-17 00:00 | 2026-06-17 00:00 | 已修复 | 已验证 |", text)


if __name__ == "__main__":
    unittest.main()
