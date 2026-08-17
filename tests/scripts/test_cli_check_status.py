"""REQ-12 (dash is not a status) and BUG-075 check-side regression tests.

Split from test_cli_check.py to keep every test file under the 600-line REQ-11 cap.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase  # noqa: E402


class CliCheckStatusDashTest(CliTestCase):

    def test_req12_dash_is_not_a_status_add(self):
        # REQ-12: "-" is the missing-value placeholder, not a business status; add must
        # reject it and list the allowed enum.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._preview_safety_file(), encoding="utf-8")
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug",
                "--action", "修复", "--description", "x", "--status", "-",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            combined = result.stdout + result.stderr
            self.assertIn("状态不在建议枚举中", combined)
            self.assertIn("待修复", combined)
            # The file must be untouched by the rejected add.
            self.assertNotIn("| BUG-003 |", target.read_text(encoding="utf-8"))

    def test_req12_dash_is_not_a_status_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._preview_safety_file(), encoding="utf-8")
            result = self.run_cli(
                "update", "--file", str(target), "--id", "BUG-001", "--status", "-",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("状态不在建议枚举中", result.stdout + result.stderr)

    def test_req12_check_flags_dash_status_row_with_line(self):
        # An existing row whose 状态 cell is "-" must be reported as an invalid status
        # with its line number, and check must fail.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | a | 2026-01-01 00:00 | - | - | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertEqual(result.returncode, 1)
            combined = result.stdout + result.stderr
            # Pin the exact message (line + offending status), not just any hyphen.
            self.assertIn("状态不在建议枚举中：第 7 行 -", combined)

    def test_bug075_unknown_prefix_no_misplacement_warning(self):
        # BUG-075: a record whose ID prefix no registered section claims (FOO-) is not
        # "misplaced" — by-prefix caliber falls it back to its physical section, so the
        # warning must stay silent for it while still firing for known prefixes.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | a | 2026-01-01 09:00 | - | 待修复 | - |\n"
                "| FOO-001 | 修复 | unknown prefix | 2026-01-01 09:00 | - | 待修复 | - |\n"
                "\n## 检查事项\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| DEV-001 | 开发 | known prefix misplaced | 2026-01-01 09:00 | - | 待开发 | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            combined = result.stdout + result.stderr
            self.assertIn("DEV-001", combined)
            self.assertIn("期望前缀 CHK-", combined)
            self.assertNotIn("FOO-001", combined)
