import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "task-list-initialization" / "scripts" / "task_list_cli.py"


def load_cli_module():
    """Import task_list_cli.py as a module (for unit-testing pure helpers)."""
    spec = importlib.util.spec_from_file_location("task_list_cli", CLI)
    mod = importlib.util.module_from_spec(spec)
    # dataclasses needs the module registered before exec_module.
    sys.modules["task_list_cli"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


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

    def test_add_next_id_ignores_id_reference_in_notes(self):
        # Regression: next_id used a full-text regex, so an ID *referenced* inside a 备注
        # cell (e.g. "关联 BUG-099") was counted as an existing record and inflated the
        # next number to BUG-100 even when only BUG-001 existed. It must only count IDs
        # that actually appear as the first column of a data row.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "首条",
                "--found-time", "2026-06-17 09:00", "--completed-time", "-",
                "--status", "待修复", "--notes", "关联 BUG-099 上下文",
            )
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "第二条",
                "--status", "待修复",
            )
            # BUG-002, NOT BUG-100: the BUG-099 text in the first row's 备注 is a reference,
            # not a real record ID.
            self.assertIn("已追加：BUG-002", result.stdout)
            self.assertNotIn("BUG-100", result.stdout)

    def test_add_next_id_ignores_cross_prefix_reference_in_description(self):
        # A reference to a DIFFERENT prefix inside a cell must not affect this prefix's
        # numbering at all (cross-prefix isolation was already correct; this locks it in).
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "阻塞于 DEV-500",
                "--status", "待修复",
            )
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "下一条",
                "--status", "待修复",
            )
            self.assertIn("已追加：BUG-002", result.stdout)

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
            # BUG-026: 发现日期 → found keeps day precision; completed is "-"; no 00:00.
            self.assertIn("| BUG-001 | 修复 | 旧字段 bug | 2026-06-17 | - | 已修复 | 已验证 |", text)

    def test_add_date_does_not_seed_completed_time_for_incomplete(self):
        # Regression: --date is a legacy 发现时间 fallback and must NOT seed 完成时间
        # for 未完成 statuses, otherwise the record is self-contradictory.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "未完成bug",
                "--date", "2026-06-17", "--status", "待修复",
            )

            text = target.read_text(encoding="utf-8")
            self.assertIn(
                "| BUG-001 | 修复 | 未完成bug | 2026-06-17 00:00 | - | 待修复 | - |",
                text,
            )
            self.assertNotIn(
                "| BUG-001 | 修复 | 未完成bug | 2026-06-17 00:00 | 2026-06-17 00:00 |",
                text,
            )

    def test_standardize_dry_run_stdout_is_only_file_content(self):
        # Regression: --dry-run must keep stdout to the previewed file content only;
        # the diagnostic report must not be appended to the same stdout.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )
            before = target.read_text(encoding="utf-8")

            result = self.run_cli(
                "standardize", "--file", str(target), "--apply-safe-fixes", "--dry-run"
            )

            # stdout is the previewed file: it has the newly added sections...
            self.assertIn("## 调整事项", result.stdout)
            self.assertIn("## 配置运维", result.stdout)
            # ...and must NOT contain the diagnostic report
            self.assertNotIn("# task-list 标准化诊断报告", result.stdout)
            self.assertNotIn("推荐 Profile", result.stdout)
            # the repair summary went to stderr, not stdout
            self.assertIn("修复完成", result.stderr)
            # original file untouched in dry-run
            self.assertEqual(before, target.read_text(encoding="utf-8"))

    def test_add_to_legacy_aliased_section_name(self):
        # Regression: prefix_for_section must resolve SECTION_ALIASES, otherwise legacy
        # section names like 开源项目调研 (→ 调研事项 / RES-) cannot accept new records.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 开源项目调研\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "add", "--file", str(target), "--section", "开源项目调研",
                "--action", "检查", "--description", "调研项A", "--status", "已完成",
            )
            self.assertIn("已追加：RES-001", result.stdout)
            text = target.read_text(encoding="utf-8")
            self.assertIn("| RES-001 | 检查 | 调研项A |", text)

    def test_add_dev_alias_works_in_development_profile(self):
        # Regression: on a development-profile file (which has 开发事项, not 功能开发),
        # the 开发/功能 aliases must still resolve to the dev section.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target), "--profile", "development")
            for alias in ("开发", "功能", "开发事项"):
                self.run_cli(
                    "add", "--file", str(target), "--section", alias,
                    "--action", "开发", "--description", f"功能-{alias}",
                    "--status", "待开发", "--priority", "P1", "--estimate", "2d",
                )
            text = target.read_text(encoding="utf-8")
            # All three aliases land in 开发事项 with sequential DEV- IDs and 9 columns
            self.assertIn("| DEV-001 | 开发 | 功能-开发 | P1 | 2d |", text)
            self.assertIn("| DEV-002 | 开发 | 功能-功能 | P1 | 2d |", text)
            self.assertIn("| DEV-003 | 开发 | 功能-开发事项 | P1 | 2d |", text)

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

    def test_add_date_backfills_completed_time_for_completed_status(self):
        # Regression: for completed statuses, --date backfills 完成时间 (consistent with
        # the legacy single-date schema and legacy_completed_time); incomplete stays '-'.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "已完成bug",
                "--date", "2026-06-17", "--status", "已修复",
            )
            text = target.read_text(encoding="utf-8")
            self.assertIn(
                "| BUG-001 | 修复 | 已完成bug | 2026-06-17 00:00 | 2026-06-17 00:00 | 已修复 | - |",
                text,
            )

    def test_add_canonical_name_matches_legacy_research_heading(self):
        # Symmetry: a file written with the legacy 开源项目调研 heading should accept a
        # request for the canonical 调研事项 (reverse alias), mirroring 功能开发/开发事项.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 开源项目调研\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "add", "--file", str(target), "--section", "调研事项",
                "--action", "检查", "--description", "调研项B", "--status", "已完成",
            )
            self.assertIn("已追加：RES-001", result.stdout)
            self.assertIn("| RES-001 | 检查 | 调研项B |", target.read_text(encoding="utf-8"))

    def test_add_to_heading_with_irregular_whitespace(self):
        # Regression: insert_row must match headings with the same tolerance as
        # parse_sections (^##\s+...). A heading like "##   代码 Bug" (multiple spaces)
        # is detected by check/summary but used to fail add with "未找到分区".
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "##   代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "空格标题bug", "--status", "待修复",
            )
            self.assertIn("已追加：BUG-001", result.stdout)
            self.assertIn("| BUG-001 | 修复 | 空格标题bug |", target.read_text(encoding="utf-8"))

    def test_add_canonical_name_matches_legacy_doc_heading(self):
        # The reverse-alias mechanism is general: 文档事项 in the file → 文档维护 request.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 文档事项\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "add", "--file", str(target), "--section", "文档维护",
                "--action", "文档", "--description", "文档A", "--status", "已完成",
            )
            self.assertIn("已追加：DOC-001", result.stdout)
            self.assertIn("| DOC-001 | 文档 | 文档A |", target.read_text(encoding="utf-8"))

    def test_standardize_flags_missing_maintenance_rule(self):
        # standardize must surface 维护规则状态 so the agent can offer to install the rule.
        # Fresh project: no CLAUDE.md / AGENTS.md / settings.json → both 未检测到.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            result = self.run_cli("standardize", "--file", str(target))
            self.assertIn("## 维护规则状态", result.stdout)
            self.assertIn("agent 文件：未发现 CLAUDE.md / AGENTS.md", result.stdout)
            self.assertIn("会话结束同步规则：未检测到", result.stdout)
            self.assertIn("Stop hook 保证层：未检测到", result.stdout)
            self.assertIn("询问用户是否安装", result.stdout)

    def test_standardize_detects_installed_rule_and_hook(self):
        # CLAUDE.md with the canonical heading + settings.json Stop hook → both 已安装.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            (Path(tmp) / "CLAUDE.md").write_text(
                "## 会话结束任务同步（必须）\n\n规则正文略。\n", encoding="utf-8"
            )
            (Path(tmp) / ".claude").mkdir()
            (Path(tmp) / ".claude" / "settings.json").write_text(
                json.dumps({
                    "hooks": {
                        "Stop": [
                            {"matcher": "", "hooks": [
                                {"type": "command", "command": "bash .claude/hooks/tasklist_sync_reminder.sh"}
                            ]}
                        ]
                    }
                }),
                encoding="utf-8",
            )
            result = self.run_cli("standardize", "--file", str(target))
            self.assertIn("agent 文件：CLAUDE.md", result.stdout)
            self.assertIn("会话结束同步规则：已安装", result.stdout)
            self.assertIn("Stop hook 保证层：已安装", result.stdout)
            self.assertNotIn("询问用户是否安装", result.stdout)

    def test_standardize_rule_present_hook_missing_suggests_hook(self):
        # Rule installed but no Stop hook → recommend the optional hook, not a full reinstall.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            (Path(tmp) / "AGENTS.md").write_text(
                "## 会话结束任务同步\n\n规则正文略。\n", encoding="utf-8"
            )
            result = self.run_cli("standardize", "--file", str(target))
            self.assertIn("agent 文件：AGENTS.md", result.stdout)
            self.assertIn("会话结束同步规则：已安装", result.stdout)
            self.assertIn("Stop hook 保证层：未检测到", result.stdout)
            self.assertIn("规则已安装但未装 Stop hook", result.stdout)

    def test_standardize_maintenance_section_in_json_report(self):
        # JSON format must carry the maintenance status for programmatic consumers.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            result = self.run_cli("standardize", "--file", str(target), "--format", "json")
            payload = json.loads(result.stdout)
            self.assertIn("maintenance", payload)
            self.assertEqual(payload["maintenance"]["agent_file"], None)
            self.assertFalse(payload["maintenance"]["rule_installed"])
            self.assertFalse(payload["maintenance"]["hook_installed"])

    def test_standardize_detects_rule_in_agents_when_claude_also_exists(self):
        # Regression: when both CLAUDE.md and AGENTS.md exist but the rule is only in
        # AGENTS.md, detection must NOT stop at CLAUDE.md and falsely report 未检测到
        # (which would prompt a duplicate install).
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            (Path(tmp) / "CLAUDE.md").write_text("# 项目说明\n\n无同步规则。\n", encoding="utf-8")
            (Path(tmp) / "AGENTS.md").write_text(
                "## 会话结束任务同步\n\n规则正文略。\n", encoding="utf-8"
            )
            result = self.run_cli("standardize", "--file", str(target))
            self.assertIn("agent 文件：AGENTS.md", result.stdout)
            self.assertIn("会话结束同步规则：已安装", result.stdout)
            self.assertNotIn("会话结束同步规则：未检测到", result.stdout)
            self.assertNotIn("询问用户是否安装", result.stdout)

    def test_standardize_prefers_claude_when_both_agent_files_have_rule(self):
        # When both files carry the marker, report CLAUDE.md (the install-side preference)
        # as the containing file, still flagged as installed.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            rule = "## 会话结束任务同步（必须）\n\n规则正文略。\n"
            (Path(tmp) / "CLAUDE.md").write_text(rule, encoding="utf-8")
            (Path(tmp) / "AGENTS.md").write_text(rule, encoding="utf-8")
            result = self.run_cli("standardize", "--file", str(target))
            self.assertIn("agent 文件：CLAUDE.md", result.stdout)
            self.assertIn("会话结束同步规则：已安装", result.stdout)

    def test_standardize_no_rule_anywhere_points_at_claude_as_target(self):
        # Both agent files exist, neither has the rule → 未检测到, and the install target
        # shown is CLAUDE.md (preferred), not AGENTS.md.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            (Path(tmp) / "CLAUDE.md").write_text("# 项目说明\n", encoding="utf-8")
            (Path(tmp) / "AGENTS.md").write_text("# Agents 说明\n", encoding="utf-8")
            result = self.run_cli("standardize", "--file", str(target))
            self.assertIn("agent 文件：CLAUDE.md", result.stdout)
            self.assertIn("会话结束同步规则：未检测到", result.stdout)
            self.assertIn("询问用户是否安装", result.stdout)

    def test_init_english_template(self):
        # --lang en produces an English template: English title, section headings, columns.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--lang", "en", "--output", str(target))
            text = target.read_text(encoding="utf-8")
            self.assertIn("# Task Tracking List", text)
            self.assertIn("## Bugs", text)
            self.assertIn("## Ops", text)
            self.assertIn("| ID | Action | Description | Found | Done | Status | Notes |", text)
            self.assertIn("> Fields: The Action field allows only these 8 fixed values", text)
            # Chinese must NOT leak into the English template.
            self.assertNotIn("任务跟踪列表", text)
            self.assertNotIn("代码 Bug", text)

    def test_init_default_lang_is_chinese(self):
        # No --lang → Chinese (Simplified) template, preserving prior behavior.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            text = target.read_text(encoding="utf-8")
            self.assertIn("# 任务跟踪列表", text)
            self.assertIn("## 代码 Bug", text)

    def test_add_to_english_section_auto_detects_locale(self):
        # add auto-detects English from the file and accepts English section/action/status.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--lang", "en", "--output", str(target))
            result = self.run_cli(
                "add", "--file", str(target), "--section", "Bugs",
                "--action", "Fix", "--description", "login fails",
                "--status", "Pending Fix", "--notes", "repro locally",
            )
            self.assertIn("Added: BUG-001 -> Bugs", result.stdout)
            text = target.read_text(encoding="utf-8")
            self.assertIn("| BUG-001 | Fix | login fails |", text)
            self.assertIn("| BUG-001 | Fix | login fails |", text.split("## Adjustments")[0])

    def test_check_validates_english_enums(self):
        # check on an English file rejects a non-enum English action.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--lang", "en", "--output", str(target))
            with target.open("a", encoding="utf-8") as handle:
                handle.write("\n| BUG-001 | Repair | bad action | 2026-06-17 09:00 | - | Pending Fix | - |\n")
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Action not in enum", result.stdout)

    def test_standardize_english_report(self):
        # standardize on an English file yields an English diagnostic report.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--lang", "en", "--output", str(target))
            result = self.run_cli("standardize", "--file", str(target))
            self.assertIn("# task-list Standardization Report", result.stdout)
            self.assertIn("## Maintenance Rule", result.stdout)
            self.assertIn("Session-end sync rule", result.stdout)
            # Chinese report strings must not leak.
            self.assertNotIn("## 维护规则状态", result.stdout)

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

    def test_check_accepts_single_date_schema(self):
        # A legitimately single-date (6-col 完成日期) file in good shape must PASS check
        # — auto-detected as single, validated against the single-date header. Previously
        # every section was flagged 表头与标准不一致, making check pure noise on such files.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 完成日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | 单日期 bug | 2026-06-17 | 已修复 | ok |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target))
            self.assertIn("检查通过", result.stdout)

    def test_add_to_single_date_schema(self):
        # add must emit 6-col rows when the file uses the single-date schema, not dual-date 7-col.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 完成日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "单日期新 bug", "--status", "待修复",
            )
            text = target.read_text(encoding="utf-8")
            self.assertIn(
                "| BUG-001 | 修复 | 单日期新 bug | - | 待修复 | - |",
                text,
            )
            result = self.run_cli("check", "--file", str(target))
            self.assertIn("检查通过", result.stdout)
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "单日期已修复",
                "--date", "2026-06-17", "--status", "已修复",
            )
            text = target.read_text(encoding="utf-8")
            self.assertIn(
                "| BUG-002 | 修复 | 单日期已修复 | 2026-06-17 00:00 | 已修复 | - |",
                text,
            )

    def test_check_schema_flag_forces_single(self):
        # --schema single forces single-date validation even without auto-detection logic.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 功能开发\n\n"
                "| ID | 动作 | 事项 | 完成日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| DEV-001 | 开发 | 单日期功能 | 2026-06-17 | 已完成 | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), "--schema", "single")
            self.assertIn("检查通过", result.stdout)

    def test_standardize_single_date_recommendation(self):
        # standardize on a single-date file surfaces the schema info line (so the agent can
        # offer migration) AND validates against single-date (no blanket header-mismatch).
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 完成日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | 单日期 | 2026-06-17 | 已修复 | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli("standardize", "--file", str(target))
            self.assertIn("使用单日期 schema（合法变体）", result.stdout)
            self.assertIn("--migrate-schema", result.stdout)
            self.assertNotIn("表头与标准不一致", result.stdout)

    def test_standardize_dup_id_mapping_recommendation(self):
        # When duplicate IDs are detected, standardize must nudge toward adding ADJ- mapping
        # records instead of silently renumbering (per the standard's 改号映射 rule).
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            with target.open("a", encoding="utf-8") as handle:
                handle.write("\n| BUG-001 | 修复 | A | 2026-06-17 09:00 | 2026-06-17 10:00 | 已修复 | - |\n")
                handle.write("| BUG-001 | 修复 | B | 2026-06-17 09:30 | 2026-06-17 10:30 | 已修复 | - |\n")
            result = self.run_cli("standardize", "--file", str(target))
            self.assertIn("重复 ID", result.stdout)
            self.assertIn("新增 ADJ- 记录说明改号映射", result.stdout)

    def test_standardize_json_includes_schema_field(self):
        # JSON consumers get the detected schema so they can branch on it.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 完成日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | 单日期 | 2026-06-17 | 已修复 | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli("standardize", "--file", str(target), "--format", "json")
            payload = json.loads(result.stdout)
            self.assertEqual(payload["schema"], "single")

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

    def test_add_section_is_case_insensitive(self):
        # Regression: the EN alias table only carried lowercase plurals for SOME sections
        # (features/docs) but not others (bugs/reviews/...), so `add --section bugs` failed
        # with "section not found". Section resolution is now case-insensitive against the
        # headings actually present in the file.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--lang", "en", "--output", str(target))
            self.run_cli(
                "add", "--file", str(target), "--section", "bugs",
                "--action", "Fix", "--description", "lowercase", "--status", "Pending Fix",
            )
            self.run_cli(
                "add", "--file", str(target), "--section", "BUGS",
                "--action", "Fix", "--description", "uppercase", "--status", "Pending Fix",
            )
            text = target.read_text(encoding="utf-8")
            self.assertIn("| BUG-001 | Fix | lowercase |", text)
            self.assertIn("| BUG-002 | Fix | uppercase |", text)

    def test_add_rejects_invalid_date(self):
        # Regression: normalize_time only shape-matched the timestamp, so a shape-valid but
        # nonexistent date (2026-99-99 99:99) was written verbatim. It now parses for real.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "bad date",
                "--found-time", "2026-99-99 99:99", "--status", "待修复", check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("2026-99-99 99:99", result.stderr + result.stdout)
            # No partial write — the bad record must not be in the file.
            self.assertNotIn("bad date", target.read_text(encoding="utf-8"))

    def test_check_flags_invalid_date(self):
        # Regression: check validated structure/enums but not time values, so a record with
        # 2026-99-99 99:99 passed silently. A legit single-date (date-only) file must still pass.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | bad | 2026-99-99 99:99 | - | 待修复 | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("2026-99-99 99:99", result.stdout + result.stderr)

            single = Path(tmp) / "single.md"
            single.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 完成日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | ok | 2026-06-17 | 已修复 | done |\n",
                encoding="utf-8",
            )
            ok = self.run_cli("check", "--file", str(single))
            self.assertIn("检查通过", ok.stdout)

    def test_check_mixed_schema_does_not_misindex_time(self):
        # Regression: detect_schema is file-level (any dual section → whole file "dual"), but
        # check_text indexed time cells by a file-wide fixed offset (cells[-3]/[-4]). In a
        # MIXED file — one dual section (7-col) + one single section (6-col) — the 6-col row
        # was mis-indexed as 7-col, so the 事项 value ("b") was flagged as 时间不合法. Time
        # columns must be located from each section's OWN header by name.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | a | 2026-06-17 09:00 | - | 待修复 | - |\n\n"
                "## 调整事项\n\n"
                "| ID | 动作 | 事项 | 完成日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| ADJ-001 | 调整 | b | 2026-06-17 | 已完成 | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            combined = result.stdout + result.stderr
            # The single section's header still legitimately mismatches under dual detection —
            # that report is correct and stays. But the 事项 value must NOT be mis-flagged.
            self.assertIn("表头与标准不一致：调整事项", combined)
            self.assertNotIn("时间不合法", combined)

            # A genuinely invalid time in EITHER schema of a mixed file must still be caught
            # (the fix must not silence real errors to hide the mis-index).
            bad = Path(tmp) / "bad.md"
            bad.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | a | 2026-99-99 99:99 | - | 待修复 | - |\n\n"
                "## 调整事项\n\n"
                "| ID | 动作 | 事项 | 完成日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| ADJ-001 | 调整 | b | 2026-13-45 | 已完成 | - |\n",
                encoding="utf-8",
            )
            bad_result = self.run_cli("check", "--file", str(bad), check=False)
            bad_combined = bad_result.stdout + bad_result.stderr
            self.assertIn("2026-99-99 99:99", bad_combined)
            self.assertIn("2026-13-45", bad_combined)

    def test_check_flags_invalid_id_format(self):
        # Regression: a malformed ID (bug-001, BUG-12, Bug-1) in the first column used to be
        # silently skipped — it matched neither ^[A-Z]+-\d{3,}$ (so no field checks ran) nor
        # any error path, so check reported "passed" while summary reported 总计：0. Such IDs
        # must now surface as bad_id_line so the file is not treated as clean.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| bug-001 | 修复 | 非法ID | 2026-06-23 10:00 | - | 待修复 | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ID 格式非法", result.stdout + result.stderr)

            # A legal ID must still pass; and a 备注/描述 cell that merely LOOKS like an ID
            # (e.g. "见 bug-001") must NOT be flagged — _looks_like_id only inspects cells[0].
            ok = Path(tmp) / "ok.md"
            ok.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | 正常 | 2026-06-23 10:00 | - | 待修复 | 见 bug-001 旧引用 |\n",
                encoding="utf-8",
            )
            ok_result = self.run_cli("check", "--file", str(ok))
            self.assertIn("检查通过", ok_result.stdout)

    def test_add_refuses_nonstandard_reordered_header(self):
        # Regression: on a reordered but column-count-matching header (| ID | 状态 | 动作 | ... |),
        # add used to fall back to column COUNT and write values in the default order, so the
        # 动作 value "修复" landed under the 状态 column — silent data corruption. add must now
        # REFUSE and leave the file untouched, directing the user to standardize first.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 状态 | 动作 | 问题描述 | 发现时间 | 完成时间 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )
            before = target.read_text(encoding="utf-8")
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "顺序错位", "--status", "待修复",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            # File untouched: no row written, header still ends with the separator.
            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertNotIn("顺序错位", target.read_text(encoding="utf-8"))
            self.assertIn("表头与标准 schema 不符", result.stdout + result.stderr)

            # A legitimate single-date header (6-col, correct order) must still accept add.
            single = Path(tmp) / "single.md"
            single.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 完成日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )
            self.run_cli(
                "add", "--file", str(single), "--section", "代码 Bug",
                "--action", "修复", "--description", "单日期正常", "--status", "待修复",
            )
            self.assertIn("| BUG-001 | 修复 | 单日期正常 |", single.read_text(encoding="utf-8"))

    def test_add_refuses_duplicate_explicit_id(self):
        # Regression: `add --id BUG-001` when BUG-001 already exists silently appended a
        # second row (rc=0, no warning); only check caught it afterward. add now refuses at
        # write time, enforcing the "IDs unique, never reused" invariant on the write path.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "first", "--status", "已修复",
            )
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--id", "BUG-001", "--action", "修复", "--description", "DUPE",
                "--status", "已修复", check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("BUG-001", result.stderr + result.stdout)
            # No partial write — the duplicate must not be in the file.
            text = target.read_text(encoding="utf-8")
            self.assertNotIn("DUPE", text)
            self.assertEqual(text.count("| BUG-001 |"), 1)

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

    def test_standardize_dev_profile_does_not_duplicate_dev_section(self):
        # Regression BUG-021: development profile safe-fixes must not append 开发事项
        # while 功能开发 still exists (in-place dev migration is not a safe auto-add).
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target), "--profile", "minimal")

            self.run_cli(
                "standardize", "--file", str(target), "--profile", "development", "--apply-safe-fixes"
            )

            text = target.read_text(encoding="utf-8")
            self.assertIn("## 功能开发", text)
            self.assertNotIn("## 开发事项", text)
            headings = re.findall(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE)
            dev_headings = [heading for heading in headings if heading in ("功能开发", "开发事项")]
            self.assertEqual(len(dev_headings), 1)

    def test_split_cells_accepts_missing_trailing_pipe(self):
        # Regression: GFM/CommonMark treat the trailing | as optional. Requiring it caused
        # split_cells to return [] → parse_sections silently skipped the row → check never
        # saw col mismatches and standardize under-counted records (real-world: 239 vs 253).
        cli = load_cli_module()
        self.assertEqual(cli.split_cells("| a | b | c"), ["a", "b", "c"])
        self.assertEqual(cli.split_cells("| a | b | c |"), ["a", "b", "c"])
        self.assertEqual(
            cli.split_cells("| BUG-001 | 修复 | desc | 2026-01-01 10:00 | - | 待修复 | note"),
            ["BUG-001", "修复", "desc", "2026-01-01 10:00", "-", "待修复", "note"],
        )
        # Escaped pipes still decode; missing trailing | must not drop the row.
        self.assertEqual(cli.split_cells(r"| a | b \| c"), ["a", "b | c"])
        self.assertEqual(cli.split_cells(r"| a | b \| c |"), ["a", "b | c"])
        # Non-table lines still return [].
        self.assertEqual(cli.split_cells("not a table"), [])

    def test_check_and_count_include_rows_without_trailing_pipe(self):
        # A well-formed 7-col row missing only the trailing | must be counted and must NOT
        # be reported as a column mismatch. An 8-col row (unescaped |) missing the trailing
        # | must still surface in check — previously both were silently dropped.
        content = (
            "# 任务跟踪列表\n\n"
            "## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | ok | 2026-01-01 10:00 | - | 待修复 | n |\n"
            "| BUG-002 | 修复 | missing trail | 2026-01-01 10:00 | - | 待修复 | n\n"
            "| BUG-003 | 修复 | extra | pipe | 2026-01-01 10:00 | - | 待修复 | n\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(content, encoding="utf-8")

            cli = load_cli_module()
            text = target.read_text(encoding="utf-8")
            records = cli.collect_records(text)
            self.assertEqual([cells[0] for _, _, cells in records], ["BUG-001", "BUG-002", "BUG-003"])
            self.assertEqual([len(cells) for _, _, cells in records], [7, 7, 8])

            result = self.run_cli("check", "--file", str(target), check=False)
            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            # BUG-003's unescaped | is visible; BUG-002 (missing trail only) is not a mismatch.
            self.assertIn("期望 7 列，实际 8 列", combined)
            self.assertIn("未转义", combined)
            self.assertNotIn("期望 7 列，实际 7 列", combined)

            std = self.run_cli("standardize", "--file", str(target), "--format", "json")
            payload = json.loads(std.stdout)
            self.assertEqual(payload["record_count"], 3)

    # ------------------------------------------------------------------
    # Improvement suite: claim-vs-actual, 待办, pipe escape, [[ID]],
    # archive, status suggestions
    # ------------------------------------------------------------------

    def test_maintenance_flags_claimed_hook_without_actual(self):
        # Docs claim Stop hook / settings.json guarantee, but neither exists → inconsistency.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            (Path(tmp) / "CLAUDE.md").write_text(
                "## 会话结束任务同步（必须）\n\n"
                "该时机由 `.claude/settings.json` 的 Stop hook 保证触发（每会话一次）。\n",
                encoding="utf-8",
            )
            result = self.run_cli("standardize", "--file", str(target), "--format", "json")
            payload = json.loads(result.stdout)
            maint = payload["maintenance"]
            self.assertTrue(maint["rule_installed"])
            self.assertFalse(maint["hook_installed"])
            self.assertTrue(maint["hook_claimed"])
            self.assertTrue(maint["claim_mismatch"])
            md = self.run_cli("standardize", "--file", str(target))
            self.assertIn("声明与实际不一致", md.stdout)
            self.assertIn("Stop hook", md.stdout)

    def test_maintenance_no_mismatch_when_hook_matches_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            (Path(tmp) / "CLAUDE.md").write_text(
                "## 会话结束任务同步（必须）\n\n"
                "该时机由 `.claude/settings.json` 的 Stop hook 保证触发（每会话一次）。\n",
                encoding="utf-8",
            )
            (Path(tmp) / ".claude").mkdir()
            (Path(tmp) / ".claude" / "settings.json").write_text(
                json.dumps({
                    "hooks": {
                        "Stop": [
                            {"matcher": "", "hooks": [
                                {"type": "command", "command": "bash .claude/hooks/tasklist_sync_reminder.sh"}
                            ]}
                        ]
                    }
                }),
                encoding="utf-8",
            )
            result = self.run_cli("standardize", "--file", str(target), "--format", "json")
            maint = json.loads(result.stdout)["maintenance"]
            self.assertTrue(maint["hook_claimed"])
            self.assertTrue(maint["hook_installed"])
            self.assertFalse(maint["claim_mismatch"])

    def test_add_and_check_accept_generic_todo_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target), "--profile", "extended")
            self.run_cli(
                "add", "--file", str(target), "--section", "文档维护",
                "--action", "文档", "--description", "更新 README",
                "--status", "待办", "--notes", "通用待办",
            )
            check = self.run_cli("check", "--file", str(target))
            self.assertEqual(check.returncode, 0)
            self.assertIn("待办", target.read_text(encoding="utf-8"))

    def test_add_accepts_english_todo_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--lang", "en", "--output", str(target))
            self.run_cli(
                "add", "--file", str(target), "--section", "Docs",
                "--action", "Doc", "--description", "Update README",
                "--status", "Todo",
            )
            self.assertEqual(self.run_cli("check", "--file", str(target)).returncode, 0)

    def test_apply_safe_fixes_escapes_unescaped_pipes_in_notes(self):
        # Unescaped | in 备注 splits the row; --apply-safe-fixes must merge+escape.
        content = (
            "# 任务跟踪列表\n\n"
            "## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | ok | 2026-01-01 10:00 | - | 待修复 | a | b |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(content, encoding="utf-8")
            before = self.run_cli("check", "--file", str(target), check=False)
            self.assertNotEqual(before.returncode, 0)
            self.assertIn("列数异常", before.stdout + before.stderr)

            self.run_cli(
                "standardize", "--file", str(target),
                "--apply-safe-fixes", "--fix-only",
            )
            text = target.read_text(encoding="utf-8")
            self.assertIn(r"a \| b", text)
            after = self.run_cli("check", "--file", str(target))
            self.assertEqual(after.returncode, 0)

    def test_check_reports_dangling_wiki_id_refs(self):
        content = (
            "# 任务跟踪列表\n\n"
            "## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | linked | 2026-01-01 10:00 | - | 待修复 | see [[DOC-036]] and [[BUG-001]] |\n"
            "## 文档维护\n\n"
            "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(content, encoding="utf-8")
            result = self.run_cli("check", "--file", str(target), check=False)
            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("悬空引用", combined)
            self.assertIn("DOC-036", combined)
            self.assertNotIn("[[BUG-001]]", combined)  # self-ref exists

    def test_check_passes_valid_wiki_id_refs(self):
        content = (
            "# 任务跟踪列表\n\n"
            "## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | a | 2026-01-01 10:00 | 2026-01-02 10:00 | 已修复 | [[DEV-001]] |\n"
            "## 功能开发\n\n"
            "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| DEV-001 | 开发 | b | 2026-01-01 10:00 | - | 待办 | from [[BUG-001]] |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(content, encoding="utf-8")
            self.assertEqual(self.run_cli("check", "--file", str(target)).returncode, 0)

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

    def test_check_suggests_mapping_for_nonstandard_status(self):
        content = (
            "# 任务跟踪列表\n\n"
            "## 文档维护\n\n"
            "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| DOC-001 | 文档 | x | 2026-01-01 10:00 | - | 待处理 | n |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(content, encoding="utf-8")
            result = self.run_cli("check", "--file", str(target), check=False)
            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("待处理", combined)
            self.assertIn("建议", combined)
            self.assertTrue("待办" in combined or "待开发" in combined)

    # ------------------------------------------------------------------
    # CLI ergonomics: update, auto-check, file/stdin/JSON, sections
    # ------------------------------------------------------------------

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

    def test_add_auto_checks_and_rolls_back_on_failure(self):
        # Pre-existing invalid time makes post-write check fail; add must not leave the new row.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | ok | 2026-01-01 10:00 | - | 待修复 | - |\n"
                "| BUG-002 | 修复 | broken | 2026-99-99 99:99 | - | 待修复 | - |\n",
                encoding="utf-8",
            )
            before = target.read_text(encoding="utf-8")
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "新条目", "--status", "待修复",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(before, target.read_text(encoding="utf-8"))
            self.assertNotIn("新条目", target.read_text(encoding="utf-8"))

    def test_add_no_check_skips_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "skip check",
                "--status", "待修复", "--no-check",
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("已追加：BUG-001", result.stdout)
            # Default path would also print check_ok; --no-check must not.
            self.assertNotIn("检查通过", result.stdout)

    def test_add_notes_file_avoids_shell_escaping(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            notes_file = Path(tmp) / "notes.txt"
            notes_file.write_text('含"引号"；分号; 与 | 竖线', encoding="utf-8")
            self.run_cli("init", "--output", str(target))
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "转义场景",
                "--status", "待修复", "--notes-file", str(notes_file),
            )
            text = target.read_text(encoding="utf-8")
            self.assertIn(r'含"引号"；分号; 与 \| 竖线', text)

    def test_add_from_json_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            entries = Path(tmp) / "entries.json"
            entries.write_text(
                json.dumps(
                    [
                        {
                            "section": "代码 Bug",
                            "action": "修复",
                            "description": "批量 bug",
                            "status": "待修复",
                            "notes": "n1",
                            "found_time": "2026-08-04 10:00",
                            "completed_time": "-",
                        },
                        {
                            "section": "调整事项",
                            "action": "调整",
                            "description": "批量调整",
                            "status": "已完成",
                            "notes": "n2",
                            "found_time": "2026-08-04 11:00",
                            "completed_time": "2026-08-04 12:00",
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.run_cli("init", "--output", str(target))
            result = self.run_cli(
                "add", "--file", str(target), "--from-json", str(entries),
            )
            self.assertIn("BUG-001", result.stdout)
            self.assertIn("ADJ-001", result.stdout)
            text = target.read_text(encoding="utf-8")
            self.assertIn("| BUG-001 | 修复 | 批量 bug |", text)
            self.assertIn("| ADJ-001 | 调整 | 批量调整 |", text)

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

    def test_add_unknown_section_lists_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            result = self.run_cli(
                "add", "--file", str(target), "--section", "不存在的分区",
                "--action", "修复", "--description", "x", "--status", "待修复",
                check=False,
            )
            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("未找到分区", combined)
            self.assertIn("代码 Bug", combined)
            self.assertIn("配置运维", combined)

    # ------------------------------------------------------------------
    # Round-2 ergonomics: summary sync, aliases, errors, list, dry-run
    # ------------------------------------------------------------------

    def test_add_syncs_summary_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target), "--with-summary")
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "a",
                "--status", "已修复", "--found-time", "2026-08-04 10:00",
                "--completed-time", "2026-08-04 11:00",
            )
            text = target.read_text(encoding="utf-8")
            self.assertIn("| 代码 Bug | 1 | 1 | 0 | 100% |", text)
            self.assertIn("| **总计** | 1 | 1 | 0 | 100% |", text)

    def test_add_no_sync_summary_leaves_zeros(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target), "--with-summary")
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "a",
                "--status", "待修复", "--no-sync-summary",
            )
            text = target.read_text(encoding="utf-8")
            self.assertIn("| 代码 Bug | 0 | 0 | 0 | 0% |", text)

    def test_check_reports_stale_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target), "--with-summary")
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "a",
                "--status", "待修复", "--no-sync-summary",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("摘要", combined)
            self.assertIn("代码 Bug", combined)

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

    def test_install_maintenance_rule_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            result = self.run_cli("install-maintenance", "--file", str(target))
            self.assertIn("CLAUDE.md", result.stdout)
            claude = (Path(tmp) / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("会话结束任务同步", claude)
            # second run is idempotent
            again = self.run_cli("install-maintenance", "--file", str(target))
            self.assertIn("已安装", again.stdout)
            self.assertEqual(claude.count("会话结束任务同步"), 1)

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

    def test_install_maintenance_refuses_invalid_settings_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            settings = Path(tmp) / ".claude" / "settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text("{not-json KEEPME", encoding="utf-8")
            result = self.run_cli(
                "install-maintenance", "--file", str(target), "--with-hook", check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("JSON", result.stdout + result.stderr)
            self.assertEqual("{not-json KEEPME", settings.read_text(encoding="utf-8"))

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

    def test_install_maintenance_cross_file_idempotent(self):
        # Rule already in AGENTS.md must not be duplicated into CLAUDE.md.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            (Path(tmp) / "AGENTS.md").write_text(
                "## 会话结束任务同步\n\nalready here\n", encoding="utf-8"
            )
            (Path(tmp) / "CLAUDE.md").write_text("# project\n", encoding="utf-8")
            result = self.run_cli("install-maintenance", "--file", str(target))
            self.assertIn("AGENTS.md", result.stdout)
            self.assertNotIn("会话结束任务同步", (Path(tmp) / "CLAUDE.md").read_text(encoding="utf-8"))

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

    def test_install_maintenance_hook_script_names_actual_agent_file(self):
        # The Stop-hook reminder must reference the file the rule actually lives in.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            (Path(tmp) / "AGENTS.md").write_text("# project\n", encoding="utf-8")
            self.run_cli("install-maintenance", "--file", str(target), "--with-hook")
            script = (Path(tmp) / ".claude" / "hooks" / "tasklist_sync_reminder.sh").read_text(
                encoding="utf-8"
            )
            self.assertIn("AGENTS.md", script)
            self.assertNotIn("CLAUDE.md 的", script)

    def test_check_flags_incomplete_status_with_completed_time(self):
        # check must catch the 状态/完成时间 contradiction instead of letting it pass.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 文档维护\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| DOC-001 | 文档 | x | 2026-01-01 10:00 | 2026-01-02 10:00 | 待办 | n |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("待办", result.stdout)

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

    def test_standardize_survives_malformed_short_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 |\n",
                encoding="utf-8",
            )
            result = self.run_cli("standardize", "--file", str(target), check=False)
            combined = result.stdout + result.stderr
            self.assertNotIn("Traceback", combined)
            self.assertNotIn("IndexError", combined)

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

    def test_install_maintenance_rejects_hooks_null_and_stop_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            settings = Path(tmp) / ".claude" / "settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text('{"hooks": {"Stop": {}}}\n', encoding="utf-8")
            result = self.run_cli(
                "install-maintenance", "--file", str(target), "--with-hook", check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stdout + result.stderr)
            self.assertFalse(
                (Path(tmp) / ".claude" / "hooks" / "tasklist_sync_reminder.sh").exists()
            )
            # hooks:null is normalized and install proceeds
            settings.write_text('{"hooks": null}\n', encoding="utf-8")
            ok = self.run_cli(
                "install-maintenance", "--file", str(target), "--with-hook",
            )
            self.assertEqual(ok.returncode, 0)
            loaded = json.loads(settings.read_text(encoding="utf-8"))
            self.assertIsInstance(loaded["hooks"]["Stop"], list)

    def test_install_maintenance_hook_uses_claude_project_dir(self):
        # New installs must use CLAUDE_PROJECT_DIR so Stop hooks work when cwd ≠ repo root.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.run_cli("install-maintenance", "--file", str(target), "--with-hook")
            settings = json.loads(
                (Path(tmp) / ".claude" / "settings.json").read_text(encoding="utf-8")
            )
            cmd = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
            self.assertIn("CLAUDE_PROJECT_DIR", cmd)
            self.assertIn("tasklist_sync_reminder.sh", cmd)
            # Simulate hook cwd = subdirectory: relative path would fail; PROJECT_DIR form resolves.
            runtime = Path(tmp) / "runtime"
            runtime.mkdir()
            rel = subprocess.run(
                ["bash", "-c", "bash .claude/hooks/tasklist_sync_reminder.sh"],
                cwd=runtime,
                input="{}",
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(rel.returncode, 0)
            abs_cmd = cmd.replace("${CLAUDE_PROJECT_DIR}", tmp)
            # Use a fresh random session_id per run. The hook gates on a per-session guard
            # file at /tmp/claude-tasklist-sync-<session_id>; a fixed value leaves that file
            # behind in the system-wide /tmp and makes every subsequent run silently exit 0
            # with no output, so the assertion below would flake.
            ok = subprocess.run(
                ["bash", "-c", abs_cmd],
                cwd=runtime,
                input=json.dumps({"session_id": f"hook-cwd-test-{uuid.uuid4()}"}),
                text=True,
                capture_output=True,
            )
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn("decision", ok.stdout)

    def test_install_maintenance_upgrades_legacy_relative_hook(self):
        # Re-running --with-hook must rewrite legacy relative commands (not pure skip).
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            settings_path = Path(tmp) / ".claude" / "settings.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                json.dumps({
                    "hooks": {
                        "Stop": [
                            {
                                "matcher": "",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "bash .claude/hooks/tasklist_sync_reminder.sh",
                                    }
                                ],
                            }
                        ]
                    }
                }),
                encoding="utf-8",
            )
            result = self.run_cli(
                "install-maintenance", "--file", str(target), "--with-hook",
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("已升级", result.stdout)
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            cmd = loaded["hooks"]["Stop"][0]["hooks"][0]["command"]
            self.assertIn("CLAUDE_PROJECT_DIR", cmd)
            self.assertNotEqual(cmd, "bash .claude/hooks/tasklist_sync_reminder.sh")
            # Second run is idempotent skip (already CLAUDE_PROJECT_DIR).
            again = self.run_cli(
                "install-maintenance", "--file", str(target), "--with-hook",
            )
            self.assertIn("已安装（跳过）", again.stdout)
            self.assertNotIn("已升级", again.stdout)

    def test_check_schema_single_flags_dual_dev_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 开发事项\n\n"
                "| ID | 动作 | 事项 | 优先级 | 预计时间 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
                "| DEV-001 | 开发 | x | P1 | 1d | 2026-08-01 10:00 | - | 待开发 | n |\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "check", "--file", str(target), "--schema", "single", check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("开发事项", result.stdout + result.stderr)

    # --- BUG-030 ~ BUG-039 regression tests (CHK-015 follow-up) ---

    def test_bug030_update_action_no_keyerror_without_status_column(self):
        # update --action on a header with no 状态 column must not crash with KeyError.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 备注 |\n| --- | --- | --- |\n| BUG-001 | 修复 | note |\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "update", "--file", str(target), "--id", "BUG-001",
                "--action", "开发", "--no-check", check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertNotIn("KeyError", result.stderr)
            self.assertIn("开发", target.read_text(encoding="utf-8"))

    def test_bug031_single_date_status_demotion_preserves_date(self):
        # On a single-date schema, update --status to a pending value must NOT clear 完成日期.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 完成日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | x | 2026-08-01 | 已修复 | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "update", "--file", str(target), "--id", "BUG-001", "--status", "进行中",
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            text = target.read_text(encoding="utf-8")
            bug_row = [l for l in text.splitlines() if l.startswith("| BUG-001")][0]
            self.assertIn("2026-08-01", bug_row)

    def test_bug032_update_notes_rejects_when_column_missing(self):
        # update --notes on a header with no 备注 column must reject, not silently report updated.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 |\n| --- | --- | --- |\n| BUG-001 | 修复 | old |\n",
                encoding="utf-8",
            )
            before = target.read_text(encoding="utf-8")
            result = self.run_cli(
                "update", "--file", str(target), "--id", "BUG-001",
                "--notes", "newnote", "--no-check", check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--notes", result.stdout + result.stderr)
            self.assertEqual(before, target.read_text(encoding="utf-8"))

    def test_bug032b_update_description_rejects_when_column_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 状态 | 备注 |\n| --- | --- | --- | --- |\n| BUG-001 | 修复 | 待修复 | - |\n",
                encoding="utf-8",
            )
            before = target.read_text(encoding="utf-8")
            result = self.run_cli(
                "update", "--file", str(target), "--id", "BUG-001",
                "--description", "newdesc", "--no-check", check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--description", result.stdout + result.stderr)
            self.assertEqual(before, target.read_text(encoding="utf-8"))

    def test_bug033_check_reports_invalid_time_in_custom_section(self):
        # A custom section with a non-standard date column name must still validate the time.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 自定义\n\n"
                "| ID | 动作 | 事项 | 日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | x | not-a-date | 已修复 | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("时间不合法", result.stdout)

    def test_bug034_archive_refuses_dangling_references(self):
        # archive must refuse when remaining records reference an archived ID.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | a | 2026-01-01 00:00 | 2026-01-02 00:00 | 已修复 | - |\n"
                "| BUG-002 | 检查 | b | 2026-08-01 00:00 | - | 进行中 | 依赖 [[BUG-001]] |\n",
                encoding="utf-8",
            )
            before = target.read_text(encoding="utf-8")
            result = self.run_cli(
                "archive", "--file", str(target), "--older-than-days", "30",
                "--as-of", "2026-08-07", check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("悬空引用", result.stderr)
            # File untouched (refused before writing).
            self.assertEqual(before, target.read_text(encoding="utf-8"))

    def test_bug035_archive_rejects_oversized_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | a | 2026-01-01 00:00 | 2026-01-02 00:00 | 已修复 | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "archive", "--file", str(target), "--older-than-days", "1000000000",
                "--as-of", "2026-08-07", check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("OverflowError", result.stderr)

    def test_bug035b_archive_rejects_negative_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | a | 2026-01-01 00:00 | 2026-01-02 00:00 | 已修复 | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "archive", "--file", str(target), "--older-than-days", "-1",
                "--as-of", "2026-08-07", check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("已归档", result.stdout)

    def test_bug036_official_rule_no_false_claim_mismatch(self):
        # The official maintenance-rule text (with the no-hook fallback clause) must NOT
        # trigger a claim_mismatch when installed without a hook.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.run_cli("install-maintenance", "--file", str(target))
            result = self.run_cli("standardize", "--file", str(target), "--format", "json")
            payload = json.loads(result.stdout)
            maint = payload["maintenance"]
            self.assertTrue(maint["rule_installed"])
            self.assertFalse(maint["claim_mismatch"])

    def test_bug037_list_status_finds_row_with_unescaped_pipe(self):
        # list --status must find a record whose notes contain an unescaped pipe.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 检查 | x | 2026-08-01 00:00 | - | 待办 | note with | pipe |\n",
                encoding="utf-8",
            )
            result = self.run_cli("list", "--file", str(target), "--status", "待办")
            self.assertIn("BUG-001", result.stdout)

    def test_bug037b_summary_status_by_header_index(self):
        # summary must read the status by header name, not cells[-2].
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 检查 | x | 2026-08-01 00:00 | - | 待办 | note with | pipe |\n",
                encoding="utf-8",
            )
            result = self.run_cli("summary", "--file", str(target))
            self.assertIn("待办", result.stdout)
            self.assertNotIn("note with", result.stdout)

    def test_bug038_missing_file_gives_clean_error(self):
        # All commands must report a localized file-not-found instead of a traceback.
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.md"
            for cmd in ("check", "summary", "list", "sections", "standardize"):
                result = self.run_cli(cmd, "--file", str(missing), check=False)
                self.assertNotIn("Traceback", result.stderr)
                self.assertIn("不存在", result.stderr)

    def test_bug038b_non_utf8_file_gives_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_bytes(b"\xff\xfe# not utf8\n")
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertNotIn("Traceback", result.stderr)
            self.assertNotIn("UnicodeDecodeError", result.stderr)

    def test_bug038c_directory_path_gives_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_cli("check", "--file", str(tmp), check=False)
            self.assertNotIn("Traceback", result.stderr)
            self.assertNotIn("IsADirectoryError", result.stderr)

    def test_bug038d_add_update_archive_missing_file_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.md"
            r_add = self.run_cli(
                "add", "--file", str(missing), "--section", "代码 Bug",
                "--action", "修复", "--description", "x", "--status", "待修复", check=False,
            )
            self.assertNotIn("Traceback", r_add.stderr)
            r_update = self.run_cli(
                "update", "--file", str(missing), "--id", "BUG-001", "--status", "待办",
                check=False,
            )
            self.assertNotIn("Traceback", r_update.stderr)
            r_archive = self.run_cli(
                "archive", "--file", str(missing), "--older-than-days", "30", check=False,
            )
            self.assertNotIn("Traceback", r_archive.stderr)

    def test_bug039_check_flags_empty_id_row(self):
        # A data row with an empty ID cell but content in later columns must be flagged.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | a | 2026-01-01 00:00 | - | 待修复 | - |\n"
                "|  | 修复 | empty id | 2026-01-01 00:00 | - | 待修复 | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ID 格式非法", result.stdout)

    def test_bug039b_check_flags_all_empty_cell_row(self):
        # An all-empty-cell row must not be silently swallowed as a separator.
        mod = load_cli_module()
        text = (
            "## 代码 Bug\n\n"
            "| ID | 动作 | 备注 |\n| --- | --- | --- |\n"
            "| BUG-001 | 修复 | n |\n"
            "|  |  |  |\n"
        )
        sections = mod.parse_sections(text)
        rows = sections["代码 Bug"]["rows"]
        # The all-empty row must be present as a row (not dropped as a separator).
        self.assertEqual(len(rows), 2)

    # --- BUG-026: migrate fidelity + header recognition (REQ-01~05) ---

    def test_bug026_migrate_found_date_no_fabricate_completed_or_midnight(self):
        # 发现日期 → found keeps day precision; completed stays "-"; no 00:00 padding.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | 已修 | 2026-01-05 | 已修复 | - |\n"
                "| BUG-002 | 修复 | 未修 | 2026-01-06 | 待修复 | - |\n",
                encoding="utf-8",
            )
            self.run_cli(
                "standardize", "--file", str(target), "--migrate-schema", "--fix-only"
            )
            text = target.read_text(encoding="utf-8")
            self.assertIn(
                "| BUG-001 | 修复 | 已修 | 2026-01-05 | - | 已修复 | - |", text
            )
            self.assertIn(
                "| BUG-002 | 修复 | 未修 | 2026-01-06 | - | 待修复 | - |", text
            )
            self.assertNotIn("00:00", text)
            check = self.run_cli("check", "--file", str(target))
            self.assertIn("检查通过", check.stdout)

    def test_bug026_migrate_done_date_keeps_day_precision_no_found_copy(self):
        # 完成日期 → completed keeps day precision; found stays "-".
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 文档维护\n\n"
                "| ID | 动作 | 事项 | 完成日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| DOC-001 | 文档 | x | 2026-03-01 | 已完成 | - |\n",
                encoding="utf-8",
            )
            self.run_cli(
                "standardize", "--file", str(target), "--migrate-schema", "--fix-only"
            )
            text = target.read_text(encoding="utf-8")
            self.assertIn(
                "| DOC-001 | 文档 | x | - | 2026-03-01 | 已完成 | - |", text
            )
            self.assertNotIn("00:00", text)

    def test_bug026_check_and_add_accept_found_date_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | a | 2026-01-05 | 待修复 | - |\n",
                encoding="utf-8",
            )
            check = self.run_cli("check", "--file", str(target))
            self.assertIn("检查通过", check.stdout)
            add = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "b", "--status", "待修复",
                "--date", "2026-02-01",
            )
            self.assertIn("已追加：BUG-002", add.stdout)
            row = [
                l for l in target.read_text(encoding="utf-8").splitlines()
                if l.startswith("| BUG-002")
            ][0]
            # 发现日期 semantic: pending rows still carry the found date.
            self.assertIn("2026-02-01", row)
            self.assertIn("待修复", row)

    def test_bug026_migrate_refuses_start_date_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            before = (
                "# 任务跟踪列表\n\n## 功能开发\n\n"
                "| ID | 动作 | 事项 | 开始日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| DEV-001 | 开发 | x | 2026-01-05 | 进行中 | - |\n"
            )
            target.write_text(before, encoding="utf-8")
            result = self.run_cli(
                "standardize", "--file", str(target), "--migrate-schema", "--fix-only",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            err = result.stdout + result.stderr
            self.assertIn("开始日期", err)
            self.assertIn("无法映射", err)
            self.assertEqual(before, target.read_text(encoding="utf-8"))

    # --- BUG-040: summary drift must check done/pending, not just total ---

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

    # --- BUG-041: completion rate must not show 100% with pending items ---

    def test_rate_precision_with_pending(self):
        """1070/1074 should render as 99.6%, not 100%."""
        mod = load_cli_module()
        rows = [("test", 1074, 1070, 4)]
        rendered = mod.render_summary_with_counts(rows, mod.get_locale("zh"))
        rate_line = [l for l in rendered.splitlines() if "test" in l][0]
        self.assertIn("99.6%", rate_line)
        self.assertNotIn("100%", rate_line)

    def test_rate_capped_at_99_9_when_rounding_up(self):
        """9999/10000 must show 99.9%, never 100%."""
        mod = load_cli_module()
        rows = [("test", 10000, 9999, 1)]
        rendered = mod.render_summary_with_counts(rows, mod.get_locale("zh"))
        rate_line = [l for l in rendered.splitlines() if "test" in l][0]
        self.assertIn("99.9%", rate_line)
        self.assertNotIn("100%", rate_line)

    # --- BUG-042: time reverse detection ---

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

    # --- BUG-043: ID sequence regression warning ---

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

    # --- BUG-044: exact duplicate record detection ---

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

    # --- BUG-045: Codex hook detection ---

    def test_detect_codex_hook_broken_path(self):
        """Codex hook with non-existent script path should be flagged as broken."""
        mod = load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            codex_dir = Path(tmp) / ".codex"
            codex_dir.mkdir()
            (codex_dir / "hooks.json").write_text(json.dumps({
                "hooks": {
                    "Stop": [{
                        "hooks": [{
                            "type": "command",
                            "command": "bash '/nonexistent/path/tasklist_sync_reminder.sh'"
                        }]
                    }]
                }
            }), encoding="utf-8")
            status = mod.detect_maintenance_rule(Path(tmp))
            self.assertTrue(status.get("codex_hook_installed"))
            self.assertIsNotNone(status.get("codex_hook_broken"))

    def test_detect_codex_hook_valid_path(self):
        """Codex hook with existing script path should not be flagged as broken."""
        mod = load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            codex_dir = Path(tmp) / ".codex"
            codex_dir.mkdir()
            hooks_dir = codex_dir / "hooks"
            hooks_dir.mkdir()
            script = hooks_dir / "tasklist_sync_reminder.sh"
            script.write_text("#!/bin/bash\n", encoding="utf-8")
            (codex_dir / "hooks.json").write_text(json.dumps({
                "hooks": {
                    "Stop": [{
                        "hooks": [{
                            "type": "command",
                            "command": f"bash '{script}'"
                        }]
                    }]
                }
            }), encoding="utf-8")
            status = mod.detect_maintenance_rule(Path(tmp))
            self.assertTrue(status.get("codex_hook_installed"))
            self.assertIsNone(status.get("codex_hook_broken"))

    # --- BUG-046: profile threshold for optimize suggestion ---

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

    # --- Completion-rate field validation (summary drift catches wrong rate) ---

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

    # --- Atomic writes (REQ-13): writes must be crash-safe and multi-file recoverable ---

    def test_atomic_write_preserves_target_on_replace_failure(self):
        """If os.replace fails mid-write, the target file must be byte-for-byte unchanged.

        The old code path (path.write_text) truncated the file on failure. atomic_write
        uses a temp + os.replace, so a failed rename leaves the original untouched.
        """
        mod = load_cli_module()
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            original = "# 任务跟踪列表\n\n原始内容\n"
            target.write_text(original, encoding="utf-8")
            original_bytes = target.read_bytes()

            with mock.patch("os.replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    mod.atomic_write(target, "# completely different content\n")

            self.assertEqual(target.read_bytes(), original_bytes)

    def test_commit_all_restores_on_partial_failure(self):
        """commit_all must roll back already-committed files when a later one fails.

        Two files: the first writes fine, the second's os.replace fails. After the
        exception, the first file must be restored to its pre-transaction content.
        """
        mod = load_cli_module()
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            f1 = Path(tmp) / "a.md"
            f2 = Path(tmp) / "b.md"
            f1.write_text("original-a\n", encoding="utf-8")
            f2.write_text("original-b\n", encoding="utf-8")

            # Fail os.replace only when the destination is f2, so the rollback's own
            # os.replace (which targets f1 to restore it) still succeeds.
            real_replace = os.replace

            def flaky_replace(src, dst):
                if Path(dst) == f2:
                    raise OSError("simulated failure on second file")
                return real_replace(src, dst)

            with mock.patch("os.replace", side_effect=flaky_replace):
                with self.assertRaises(OSError):
                    mod.commit_all([
                        (f1, "new-a\n"),
                        (f2, "new-b\n"),
                    ])

            # f1 must have been restored to its original content, not left as "new-a".
            self.assertEqual(f1.read_text(encoding="utf-8"), "original-a\n")

    def test_archive_atomic_restores_on_failure(self):
        """If the archive commit fails partway, the main file must keep all records.

        Reproduces the original half-move risk: archive commits the archive file then the
        main file as one transaction. If the main-file write fails, both roll back —
        records are never left dropped from the main file without a complete archive.
        We drive commit_all in-process (matching how command_archive commits) so the
        injected os.replace fault actually takes effect.
        """
        mod = load_cli_module()
        from unittest import mock

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


if __name__ == "__main__":
    unittest.main()
