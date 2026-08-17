"""C3: structured ValidationIssue codes from validate_ledger."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import ensure_scripts_on_path  # noqa: E402

ensure_scripts_on_path()

from _tasklist.locales import LOCALES  # noqa: E402
from _tasklist.parser import parse_ledger  # noqa: E402
from _tasklist.validator import validate_ledger  # noqa: E402


class ValidatorTest(unittest.TestCase):
    def test_duplicate_id_has_stable_code(self):
        text = (
            "# t\n\n## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | a | 2026-08-14 01:00 | - | 待修复 | - |\n"
            "| BUG-001 | 修复 | b | 2026-08-14 01:01 | - | 待修复 | - |\n"
        )
        issues = validate_ledger(parse_ledger(text, LOCALES["zh"]))
        self.assertIn("duplicate_id", {i.code for i in issues})

    def test_duplicate_section_has_stable_code(self):
        text = (
            "# t\n\n## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- |\n\n"
            "## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
        )
        issues = validate_ledger(parse_ledger(text, LOCALES["zh"]))
        self.assertIn("duplicate_section", {i.code for i in issues})

    def test_bad_status_and_time_codes(self):
        text = (
            "# t\n\n## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | a | 2026-99-99 99:99 | - | 未知状态 | - |\n"
        )
        codes = {i.code for i in validate_ledger(parse_ledger(text, LOCALES["zh"]))}
        self.assertIn("bad_status", codes)
        self.assertIn("bad_time", codes)

    def test_prefix_mismatch_is_warning(self):
        text = (
            "# t\n\n## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| DEV-001 | 开发 | a | 2026-08-14 01:00 | - | 待办 | - |\n"
        )
        issues = validate_ledger(parse_ledger(text, LOCALES["zh"]))
        prefix = [i for i in issues if i.code == "prefix_mismatch"]
        self.assertTrue(prefix)
        self.assertEqual(prefix[0].severity, "warning")

    def test_placeholder_dash_status_is_warning_not_check_error(self):
        text = (
            "# t\n\n## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | a | 2026-08-14 01:00 | - | - | - |\n"
        )
        ledger = parse_ledger(text, LOCALES["zh"])
        issues = validate_ledger(ledger)
        placeholders = [i for i in issues if i.code == "placeholder_status"]
        self.assertTrue(placeholders)
        error_codes = {i.code for i in issues if i.severity == "error"}
        self.assertNotIn("placeholder_status", error_codes)


if __name__ == "__main__":
    unittest.main()
