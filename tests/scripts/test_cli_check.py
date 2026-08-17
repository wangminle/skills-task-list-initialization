"""CLI regression tests (split from the former monolithic file)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase, load_cli_module  # noqa: E402


class CliCheckTest(CliTestCase):
    def test_check_warns_prefix_misplacement_without_failing(self):
        # REQ-08: a DEV-prefixed record physically under 检查事项 (expects CHK-) is
        # reported as a named warning with line/section/expected prefix; the gate
        # still passes and the record is not moved.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 检查事项\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| DEV-074 | 检查 | 错位记录 | 2026-08-17 09:00 | - | 待办 | - |\n",
                encoding="utf-8",
            )
            before = target.read_text(encoding="utf-8")
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertEqual(result.returncode, 0)
            self.assertIn("前缀错位警告", result.stdout)
            self.assertIn("DEV-074", result.stdout)
            self.assertIn("检查事项", result.stdout)
            self.assertIn("CHK-", result.stdout)
            self.assertIn("检查通过", result.stdout)
            self.assertEqual(target.read_text(encoding="utf-8"), before)

    def test_check_prefix_warnings_print_alongside_errors(self):
        # REQ-08: warnings print even when hard errors exist; the exit code stays
        # driven by errors (1 here), warnings alone never fail the gate.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 检查事项\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| DEV-074 | 检查 | 错位记录 | 2026-08-17 09:00 | - | 待办 | - |\n"
                "| DEV-074 | 检查 | 重复记录 | 2026-08-17 09:10 | - | 待办 | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("重复 ID", result.stdout)
            self.assertIn("前缀错位警告", result.stdout)
            self.assertIn("DEV-074", result.stdout)

    def test_check_prefix_warning_english_locale(self):
        # REQ-08: the warning header is localized for en files.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# Task Tracker\n\n## Reviews\n\n"
                "| ID | Action | Item | Found | Done | Status | Notes |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| DEV-074 | Review | misfiled record | 2026-08-17 09:00 | - | Pending Fix | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertEqual(result.returncode, 0)
            self.assertIn("Prefix misplacement warnings", result.stdout)
            self.assertIn("DEV-074", result.stdout)
            self.assertIn("CHK-", result.stdout)

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
            result = self.run_cli("check", "--file", str(target))
            # BUG-058: mixed dual+single files are valid in auto mode; each section is
            # checked against its own header. Forced --schema dual still flags the 6-col
            # section. The 事项 value must never be mis-flagged as an invalid time.
            self.assertIn("检查通过", result.stdout)
            forced = self.run_cli("check", "--file", str(target), "--schema", "dual", check=False)
            self.assertIn("表头与标准不一致：调整事项", forced.stdout + forced.stderr)
            self.assertNotIn("时间不合法", forced.stdout + forced.stderr)

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

    def test_check_flags_blank_line_inside_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._preview_safety_file(blank_between=True), encoding="utf-8")
            result = self.run_cli("check", "--file", str(target), check=False)
            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("空行切断", combined)
            self.assertIn("BUG-001", combined)

    def test_check_allows_blank_between_table_and_next_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._preview_safety_file(blank_between=False), encoding="utf-8")
            result = self.run_cli("check", "--file", str(target))
            self.assertEqual(result.returncode, 0)

    def test_check_flags_raw_html_title_in_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                self._preview_safety_file(notes2="<title>"),
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("裸 HTML", combined)
            self.assertIn("<title>", combined)

    def test_check_passes_html_inside_backticks(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                self._preview_safety_file(notes2="`<title>`"),
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target))
            self.assertEqual(result.returncode, 0)

    def test_check_does_not_flag_placeholder_or_less_than(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                self._preview_safety_file(notes1="see <id>", notes2="a < b"),
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target))
            self.assertEqual(result.returncode, 0)

    def test_check_flags_unpaired_backticks(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                self._preview_safety_file(notes2=r"regex $`"),
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("反引号未闭合", combined)

    def test_escape_cell_wraps_dangerous_html_but_not_placeholders(self):
        mod = load_cli_module()
        self.assertEqual(mod.escape_cell("see <title> here"), "see `<title>` here")
        self.assertEqual(mod.escape_cell("already `<title>` ok"), "already `<title>` ok")
        self.assertEqual(mod.escape_cell("see <id> and a < b"), "see <id> and a < b")
        self.assertEqual(mod.escape_cell("<iframe>"), "`<iframe>`")

    def test_check_english_preview_safety_messages(self):
        content = (
            "# Task Tracking List\n\n"
            "## Bugs\n\n"
            "| ID | Action | Description | Found | Done | Status | Notes |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | Fix | first | 2026-01-01 10:00 | - | Pending Fix | n |\n"
            "\n"
            "| BUG-002 | Fix | second | 2026-01-01 11:00 | - | Pending Fix | <title> |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(content, encoding="utf-8")
            result = self.run_cli("check", "--file", str(target), check=False)
            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("blank line", combined.lower())
            self.assertIn("raw HTML", combined)
            self.assertIn("<title>", combined)

    def test_check_ignores_blank_inside_fenced_code_table_example(self):
        # BUG-050: a fenced Markdown table example is not a real ledger table.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._file_with_fenced_table_example(), encoding="utf-8")
            result = self.run_cli("check", "--file", str(target))
            self.assertEqual(result.returncode, 0)

    def test_apply_safe_fixes_preserves_blanks_inside_fenced_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            original = self._file_with_fenced_table_example()
            target.write_text(original, encoding="utf-8")
            self.run_cli(
                "standardize", "--file", str(target),
                "--apply-safe-fixes", "--fix-only",
            )
            text = target.read_text(encoding="utf-8")
            self.assertIn("```markdown\n| ID | 动作 |\n| --- | --- |\n\n| BUG-999 | 修复 |\n```", text)
            self.assertNotIn("BUG-999", text.split("```markdown")[0])

    def test_check_allows_double_backtick_span_containing_backtick(self):
        # BUG-051: CommonMark ``a ` b`` is a closed span, not unpaired.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                self._preview_safety_file(notes2="see ``a ` b`` here"),
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target))
            self.assertEqual(result.returncode, 0)

    def test_check_allows_html_inside_double_backticks(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                self._preview_safety_file(notes2="``<title>``"),
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target))
            self.assertEqual(result.returncode, 0)

    def test_escape_cell_preserves_double_backtick_html_span(self):
        mod = load_cli_module()
        self.assertEqual(mod.escape_cell("``<title>``"), "``<title>``")
        self.assertEqual(mod.escape_cell("see ``a ` b`` here"), "see ``a ` b`` here")

    def test_check_allows_backslash_escaped_backtick(self):
        # CommonMark: \ ` is a literal backtick, not an opener.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                self._preview_safety_file(notes2=r"path:\`file.md"),
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target))
            self.assertEqual(result.returncode, 0)

    def test_check_flags_even_count_unclosed_backticks(self):
        # Two backticks with no matching closer must fail the preview gate.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                self._preview_safety_file(notes2="坏代码 ``never closed"),
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("反引号未闭合", combined)

    def test_check_flags_raw_iframe(self):
        # BUG-052: flow-breaking tags beyond title/details/script/...
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                self._preview_safety_file(notes2="<iframe>"),
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("裸 HTML", combined)
            self.assertIn("iframe", combined.lower())
