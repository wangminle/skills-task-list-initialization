"""C2: parser/renderer round-trip and header-indexed records."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import ensure_scripts_on_path, run_cli  # noqa: E402

ensure_scripts_on_path()

from _tasklist.locales import LOCALES  # noqa: E402
from _tasklist.parser import parse_ledger, parse_sections, split_cells  # noqa: E402
from _tasklist.renderer import render_ledger  # noqa: E402


class ParserRendererTest(unittest.TestCase):
    def test_split_cells_decodes_escaped_pipe(self):
        self.assertEqual(split_cells("| a \\| b |"), ["a | b"])

    def test_split_cells_accepts_missing_trailing_pipe(self):
        self.assertEqual(split_cells("| a | b"), ["a", "b"])

    def test_tab_heading_is_a_real_section(self):
        text = "# t\n\n##\t代码 Bug\n\n| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n| --- | --- | --- | --- | --- | --- |\n"
        sections = parse_sections(text)
        self.assertIn("代码 Bug", sections)

    def test_fenced_heading_is_not_a_section(self):
        text = (
            "# t\n\n```markdown\n## 代码 Bug\n```\n\n"
            "## 调整事项\n\n| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
        )
        sections = parse_sections(text)
        self.assertNotIn("代码 Bug", sections)
        self.assertIn("调整事项", sections)

    def test_overwide_row_is_kept_as_record_cells(self):
        text = (
            "# t\n\n## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | a | 2026-08-14 01:00 | - | 待修复 | note | extra |\n"
        )
        ledger = parse_ledger(text, LOCALES["zh"])
        self.assertEqual(len(ledger.records), 1)
        self.assertEqual(ledger.records[0].item_id, "BUG-001")
        self.assertGreater(len(ledger.records[0].cells), 7)

    def test_mixed_schema_parses_both_sections(self):
        text = (
            "# t\n\n## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | a | 2026-08-14 01:00 | - | 待修复 | - |\n\n"
            "## 调整事项\n\n"
            "| ID | 动作 | 事项 | 完成日期 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| ADJ-001 | 调整 | b | 2026-08-14 | 待办 | - |\n"
        )
        ledger = parse_ledger(text, LOCALES["zh"])
        ids = {r.item_id for r in ledger.records}
        self.assertEqual(ids, {"BUG-001", "ADJ-001"})

    def test_init_template_round_trip_bytes_and_records(self):
        with __import__("tempfile").TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            result = run_cli("init", "--output", str(target))
            self.assertEqual(result.returncode, 0)
            original = target.read_text(encoding="utf-8")
            locale = LOCALES["zh"]
            ledger = parse_ledger(original, locale)
            rendered = render_ledger(ledger)
            self.assertEqual(rendered, original)
            again = parse_ledger(rendered, locale)
            self.assertEqual(
                [(r.item_id, r.section_title, r.cells) for r in again.records],
                [(r.item_id, r.section_title, r.cells) for r in ledger.records],
            )


if __name__ == "__main__":
    unittest.main()
