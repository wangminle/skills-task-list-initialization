"""CLI regression tests (split from the former monolithic file)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase, load_cli_module  # noqa: E402


class CliBugs1Test(CliTestCase):
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
            bug_row = [line for line in text.splitlines() if line.startswith("| BUG-001")][0]
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
        # summary must read the status by header name, not cells[-2] (BUG-037). Since
        # REQ-06 the unescaped-pipe row is a width anomaly and must be EXCLUDED from
        # statistics outright instead of being counted with fragment-based field reads;
        # the header-name read still shows on the well-formed row.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 检查 | x | 2026-08-01 00:00 | - | 待办 | ok |\n"
                "| BUG-002 | 检查 | y | 2026-08-02 00:00 | - | 待办 | note with | pipe |\n",
                encoding="utf-8",
            )
            result = self.run_cli("summary", "--file", str(target))
            self.assertIn("待办", result.stdout)
            self.assertNotIn("note with", result.stdout)
            # REQ-06: the broken row is excluded, not miscounted.
            self.assertIn("总计：1", result.stdout)
            self.assertIn("1 行因列数与表头不符未参与统计", result.stdout)

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
                line for line in target.read_text(encoding="utf-8").splitlines()
                if line.startswith("| BUG-002")
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

    def test_bug053_add_does_not_insert_inside_fenced_example(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._file_fenced_heading_before_real_table(), encoding="utf-8")
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "new", "--status", "待修复",
                "--found-time", "2026-08-13 12:00", "--id", "BUG-002",
            )
            text = target.read_text(encoding="utf-8")
            fence_body = text.split("```markdown", 1)[1].split("```", 1)[0]
            self.assertNotIn("BUG-002", fence_body)
            real_table = text.split("```", 2)[-1]
            self.assertIn("| BUG-002 |", real_table)
            listed = self.run_cli("list", "--file", str(target), "--id", "BUG-002")
            self.assertIn("BUG-002", listed.stdout)

    def test_bug054_summary_write_ignores_fenced_pseudo_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                self._file_fenced_heading_before_real_table(
                    with_summary=True, extra_fence_summary=True
                ),
                encoding="utf-8",
            )
            original_real = "| BUG-001 | 修复 | real |"
            self.run_cli("summary", "--file", str(target), "--write")
            text = target.read_text(encoding="utf-8")
            self.assertIn(original_real, text)
            self.assertEqual(text.count("```"), 4)
            self.assertIn("| BUG-001 |", text)
            check = self.run_cli("check", "--file", str(target))
            self.assertIn("检查通过", check.stdout)

    def test_bug055_apply_safe_fixes_does_not_let_fenced_header_hijack_real_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                f"{self._zh_dual_header()}\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | real | 2026-01-01 10:00 | - | 待修复 | n |\n\n"
                "```markdown\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| BUG-888 | 修复 | sample | 2026-01-01 00:00 | 待修复 | has | extra |\n"
                "```\n\n"
                "| BUG-002 | 修复 | after-fence | 2026-01-02 10:00 | - | 待修复 | n |\n",
                encoding="utf-8",
            )
            before = self.run_cli("check", "--file", str(target))
            self.assertIn("检查通过", before.stdout)
            self.run_cli(
                "standardize", "--file", str(target),
                "--apply-safe-fixes", "--fix-only",
            )
            text = target.read_text(encoding="utf-8")
            self.assertIn(
                "| BUG-002 | 修复 | after-fence | 2026-01-02 10:00 | - | 待修复 | n |",
                text,
            )
            after = self.run_cli("check", "--file", str(target))
            self.assertIn("检查通过", after.stdout)

    def test_bug056_migrate_skips_fenced_example_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "```markdown\n"
                "| ID | 动作 | 问题描述 | 完成日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| BUG-888 | 修复 | sample | 2026-01-01 | 已修复 | - |\n"
                "```\n\n"
                "| ID | 动作 | 问题描述 | 完成日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | real | 2026-01-01 | 已修复 | n |\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "standardize", "--file", str(target),
                "--migrate-schema", "--fix-only",
            )
            text = target.read_text(encoding="utf-8")
            fence_body = text.split("```markdown", 1)[1].split("```", 1)[0]
            self.assertIn("完成日期", fence_body)
            self.assertIn("| BUG-888 |", fence_body)
            self.assertIn("| 发现时间 | 完成时间 |", text.split("```", 2)[-1])
            self.assertNotIn("BUG-888", result.stdout)

    def test_bug057_check_ignores_fenced_duplicate_headings(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._file_fenced_heading_before_real_table(), encoding="utf-8")
            result = self.run_cli("check", "--file", str(target))
            self.assertIn("检查通过", result.stdout)
            self.assertNotIn("重复章节：", result.stdout + result.stderr)

    def test_bug058_add_to_mixed_schema_file_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                f"{self._zh_dual_header()}\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | a | 2026-06-17 09:00 | - | 待修复 | - |\n\n"
                "## 调整事项\n\n"
                "| ID | 动作 | 事项 | 完成日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| ADJ-001 | 调整 | b | 2026-06-17 | 已完成 | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "mixed-ok", "--status", "待修复",
                "--found-time", "2026-08-13 12:00",
            )
            self.assertIn("BUG-002", result.stdout)
            text = target.read_text(encoding="utf-8")
            self.assertIn("| BUG-002 |", text)
            self.assertIn("| ADJ-001 |", text)

    def test_bug059_escape_cell_strips_carriage_return(self):
        mod = load_cli_module()
        self.assertNotIn("\r", mod.escape_cell("keep\rgoing"))
        self.assertEqual(mod.escape_cell("keep\rgoing"), "keep going")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "cr", "--status", "待修复",
                "--notes", "alpha\rbeta",
            )
            text = target.read_text(encoding="utf-8")
            self.assertIn("alpha beta", text)
            self.assertNotIn("\r", text.split("| BUG-001 |")[1].split("\n", 1)[0])

    def test_bug060_found_date_schema_honors_found_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | old | 2026-01-01 | 待修复 | n |\n",
                encoding="utf-8",
            )
            self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "dated", "--status", "待修复",
                "--found-time", "2026-06-01 12:00",
            )
            text = target.read_text(encoding="utf-8")
            self.assertIn("| BUG-002 | 修复 | dated | 2026-06-01 12:00 | 待修复 |", text)
            self.assertNotIn("| BUG-002 | 修复 | dated | 2026-08-", text)
