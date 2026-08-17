"""CLI regression tests (split from the former monolithic file)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase  # noqa: E402


class CliAdd1Test(CliTestCase):
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

    def _preexisting_error_file(self, tmp):
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
        return target

    def test_add_keeps_write_when_errors_are_preexisting(self):
        # Post-write check fails only on BUG-002's pre-existing time; the add itself
        # is clean, so the write is kept (baseline-aware rollback) and residual disclosed.
        with tempfile.TemporaryDirectory() as tmp:
            target = self._preexisting_error_file(tmp)
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "新条目", "--status", "待修复",
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("已追加：BUG-003", result.stdout)
            self.assertIn("存量问题", result.stderr)
            self.assertIn("新条目", target.read_text(encoding="utf-8"))
            self.assertIn("2026-99-99 99:99", target.read_text(encoding="utf-8"))

    def test_add_auto_checks_and_rolls_back_on_new_issue(self):
        # The add itself introduces a dangling ID reference; rollback fires.
        with tempfile.TemporaryDirectory() as tmp:
            target = self._preexisting_error_file(tmp)
            before = target.read_text(encoding="utf-8")
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "新条目", "--status", "待修复",
                "--notes", "见 [[FOO-999]]", check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("回滚", result.stderr)
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

    def test_add_wraps_raw_title_tag_in_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "html in notes",
                "--status", "待修复", "--notes", "broken <title> tag",
            )
            self.assertEqual(result.returncode, 0)
            text = target.read_text(encoding="utf-8")
            self.assertIn("`<title>`", text)
            self.assertNotRegex(text, r"(?<!`) <title> (?!`)")
            check = self.run_cli("check", "--file", str(target))
            self.assertEqual(check.returncode, 0)

    def test_bug084_line_shift_keeps_write_for_preexisting_error(self):
        # BUG-082/084: appending above a pre-existing error shifts its line number;
        # the fingerprint must still match the baseline (positional digits collapse)
        # so the legitimate add is kept and the residual disclosed.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | a | 2026-01-05 10:00 | - | 待修复 | - |\n"
                "\n## 检查事项\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| CHK-001 | 检查 | x | 2026-99-99 99:99 | - | 待办 | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "新条目", "--status", "待修复",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("已追加：BUG-002", result.stdout)
            self.assertIn("存量问题", result.stderr)
            self.assertIn("新条目", target.read_text(encoding="utf-8"))
