import json
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
            self.assertIn("| BUG-001 | 修复 | 旧bug | 2026-06-17 00:00 | 2026-06-17 00:00 | 已修复 | ok |", text)
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


if __name__ == "__main__":
    unittest.main()
