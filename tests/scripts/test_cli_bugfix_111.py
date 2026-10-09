"""BUG-111: an existing empty summary must not bypass missing-category checks."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase  # noqa: E402


class EmptySummaryGateTest(CliTestCase):
    LABELS = {
        "zh": ("代码 Bug", "修复", "待修复", "统计摘要", "摘要表缺少分类「代码 Bug」的行"),
        "en": ("Bugs", "Fix", "Pending Fix", "Summary", 'Summary table is missing a row for category "Bugs"'),
    }

    def _create_ledger(self, target: Path, lang: str, *, with_summary: bool = True) -> None:
        section, action, status, _summary, _message = self.LABELS[lang]
        flags = ("--with-summary",) if with_summary else ()
        self.run_cli(
            "init", "--output", str(target), "--lang", lang,
            "--profile", "extended", *flags,
        )
        self.run_cli(
            "add", "--file", str(target), "--section", section,
            "--action", action, "--description", "pending bug",
            "--status", status, "--found-time", "2026-10-08 10:00",
        )
        self.run_cli("check", "--file", str(target))

    def _empty_summary(self, target: Path, lang: str) -> bytes:
        summary = self.LABELS[lang][3]
        text = target.read_text(encoding="utf-8")
        body, table = text.split(f"## {summary}\n", 1)
        # Keep the actual generated heading, header and delimiter, removing every
        # category and total row. The record table above is left intact.
        header, separator, _rows = table.lstrip("\n").split("\n", 2)
        target.write_text(
            f"{body}## {summary}\n\n{header}\n{separator}\n", encoding="utf-8"
        )
        return target.read_bytes()

    def _assert_rejects_empty_summary(self, lang: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self._create_ledger(target, lang)
            # Both explicit counting policies remain valid controls.
            for policy in ("by-section", "by-prefix"):
                self.run_cli("summary", "--file", str(target), "--write", "--policy", policy)
                self.run_cli("check", "--file", str(target))
            original = self._empty_summary(target, lang)
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(self.LABELS[lang][4], result.stdout)
            self.assertEqual(target.read_bytes(), original)
            self.assertIn(b"BUG-001", original)

    def test_check_rejects_empty_summary_zh(self):
        self._assert_rejects_empty_summary("zh")

    def test_check_rejects_empty_summary_en(self):
        self._assert_rejects_empty_summary("en")

    def test_ledger_without_optional_summary_still_passes(self):
        for lang in self.LABELS:
            with self.subTest(lang=lang), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / "task-list.md"
                self._create_ledger(target, lang, with_summary=False)
                self.assertNotIn(
                    f"## {self.LABELS[lang][3]}", target.read_text(encoding="utf-8")
                )

    def test_summary_write_repairs_empty_summary(self):
        for lang in self.LABELS:
            with self.subTest(lang=lang), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / "task-list.md"
                self._create_ledger(target, lang)
                self._empty_summary(target, lang)
                self.run_cli("summary", "--file", str(target), "--write")
                self.run_cli("check", "--file", str(target))
                text = target.read_text(encoding="utf-8")
                self.assertIn(f"| {self.LABELS[lang][0]} | 1 | 0 | 1 | 0% |", text)
                self.assertIn("BUG-001", text)
