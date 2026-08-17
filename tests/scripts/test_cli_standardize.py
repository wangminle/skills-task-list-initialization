"""CLI regression tests (split from the former monolithic file)."""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase  # noqa: E402


class CliStandardizeTest(CliTestCase):
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

    def test_standardize_warns_when_research_section_out_of_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 功能开发\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "## 调研事项\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| RES-001 | 检查 | x | 2026-01-01 00:00 | - | 待办 | n |\n"
                "## 配置运维\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )
            result = self.run_cli("standardize", "--file", str(target))
            self.assertIn("章节顺序", result.stdout)
