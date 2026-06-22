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


if __name__ == "__main__":
    unittest.main()
