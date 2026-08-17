"""CLI regression tests (split from the former monolithic file)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase, load_cli_module  # noqa: E402


class CliParserTest(CliTestCase):
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
