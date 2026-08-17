"""A1/A2: self-contained legacy fixtures + REQ-04 path-consistency tests.

The four fixtures in ``tests/fixtures/legacy/`` are minimal, publishable equivalents of
the four historical samples (design/discussion is gitignored, so CI must not reference it).
They preserve the structural differences that once broke the tool (DEF-01..DEF-08):

  * pdf-markdown: 发现日期 Bug section + 完成日期 others  (clean file, must pass check)
  * prd-workflow: duplicate 文档维护 section              (real structural issue, reported)
  * translation:  功能开发 with 功能描述 + 开始日期; 规划事项 with 规划日期
                  (unmappable semantics: check passes, migrate refuses)
  * patent:       8-col 开发事项 (优先级/预计时间), 前缀错位 DEV-* in 检查事项,
                  unescaped-pipe row, by-prefix summary table

REQ-04: check/add/migrate must classify every section header identically (one resolver).
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "legacy"
CLI = ROOT / "skills" / "task-list-initialization" / "scripts" / "task_list_cli.py"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import ensure_scripts_on_path  # noqa: E402

ensure_scripts_on_path()

from _tasklist.domain import HeaderKind  # noqa: E402
from _tasklist.locales import LOCALES  # noqa: E402
from _tasklist.parser import parse_sections  # noqa: E402
from _tasklist.schemas import (  # noqa: E402
    resolve_header,
    section_for_title,
)


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


def _fixture_headers(name: str) -> dict[str, list[str]]:
    """Return {section_title: header_cells} for a fixture's table sections."""
    text = (FIXTURES / f"{name}-task-list.md").read_text(encoding="utf-8")
    result: dict[str, list[str]] = {}
    for title, info in parse_sections(text).items():
        headers = info.get("headers") or []
        if headers:
            result[title] = list(headers)
    return result


class LegacyFixtureCheckTest(unittest.TestCase):
    def fixture(self, name: str) -> Path:
        path = FIXTURES / f"{name}-task-list.md"
        self.assertTrue(path.exists(), f"missing fixture {path}")
        return path

    def test_pdf_markdown_fixture_passes_check(self):
        """A clean legacy single-date file (发现日期 Bug + 完成日期 others) must pass."""
        result = _run_cli("check", "--file", str(self.fixture("pdf-markdown")))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("检查通过", result.stdout)

    def test_prd_workflow_fixture_reports_duplicate_section(self):
        """REQ-05: real structural issues are reported, not masked by header rejection."""
        result = _run_cli("check", "--file", str(self.fixture("prd-workflow")))
        combined = result.stdout + result.stderr
        self.assertIn("重复章节", combined)
        self.assertIn("文档维护", combined)
        self.assertNotIn("表头与标准不一致", combined)

    def test_translation_fixture_passes_check_with_unmappable_semantics(self):
        """REQ-05/REQ-03: 功能描述 + 开始日期 and 规划日期 headers pass check (not
        header errors), even though migration must refuse them as semantically unmappable."""
        result = _run_cli("check", "--file", str(self.fixture("translation")))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("表头与标准不一致", result.stdout + result.stderr)

    def test_translation_fixture_migrate_refuses_unmappable_headers(self):
        result = _run_cli(
            "standardize", "--file", str(self.fixture("translation")),
            "--migrate-schema", "--dry-run",
        )
        self.assertNotEqual(result.returncode, 0)
        err = result.stdout + result.stderr
        self.assertIn("无法无损迁移", err)
        self.assertIn("开始日期", err)

    def test_patent_fixture_reports_col_mismatch_and_prefix_warning(self):
        """REQ-06/REQ-08: unescaped-pipe row is a real issue; DEV-* in 检查事项 is a
        prefix-misplacement warning (not an error, records are not moved)."""
        result = _run_cli("check", "--file", str(self.fixture("patent")))
        combined = result.stdout + result.stderr
        self.assertIn("列数异常", combined)
        self.assertIn("DEV-005", combined)
        self.assertIn("前缀错位", combined)
        self.assertNotIn("表头与标准不一致", combined)


class LegacyHeaderConsistencyTest(unittest.TestCase):
    """REQ-04: check/add/migrate classify every section header identically.

    Each fixture section must resolve to a recognized header kind through the shared
    resolver (D3). These tests pin the classification for the four real-world shapes so
    a future split of the recognition logic cannot silently diverge.
    """

    def _resolve(self, name: str) -> dict[str, HeaderKind]:
        zh = LOCALES["zh"]
        kinds: dict[str, HeaderKind] = {}
        for title, headers in _fixture_headers(name).items():
            section = section_for_title(title, zh)
            if section is None:
                continue
            if len(headers) == 1 and headers[0].startswith("|") is False:
                continue
            cells = headers if isinstance(headers[0], str) else headers
            resolved = resolve_header(cells, section, zh)
            kinds[title] = resolved.kind
        return kinds

    def test_all_fixture_sections_resolve_to_recognized_kinds(self):
        for name in ("pdf-markdown", "prd-workflow", "translation", "patent"):
            kinds = self._resolve(name)
            self.assertTrue(kinds, f"{name}: no resolvable sections")
            for title, kind in kinds.items():
                self.assertIn(
                    kind,
                    {HeaderKind.STANDARD_DUAL, HeaderKind.LEGACY_SINGLE, HeaderKind.LEGACY_EXTENDED},
                    f"{name}: section {title} resolved to unknown kind {kind!r}",
                )

    def test_patent_extended_section_is_legacy_extended(self):
        """The 8-col 开发事项 (优先级/预计时间) header must be legacy_extended."""
        kinds = self._resolve("patent")
        self.assertEqual(kinds.get("开发事项"), HeaderKind.LEGACY_EXTENDED)

    def test_translation_feature_section_is_legacy_single(self):
        """功能描述 + 开始日期 is the same single-date shape as 事项 + 完成日期."""
        kinds = self._resolve("translation")
        self.assertEqual(kinds.get("功能开发"), HeaderKind.LEGACY_SINGLE)

    def test_translation_plan_section_is_legacy_single(self):
        """规划事项 with 规划日期 must resolve as a single-date shape."""
        kinds = self._resolve("translation")
        self.assertEqual(kinds.get("规划事项"), HeaderKind.LEGACY_SINGLE)

    def test_bug_sections_are_legacy_single_in_all_fixtures(self):
        """Every 代码 Bug section (发现日期) is a legacy single-date shape (DEF-02 fix)."""
        for name in ("pdf-markdown", "prd-workflow", "translation", "patent"):
            kinds = self._resolve(name)
            self.assertEqual(
                kinds.get("代码 Bug"),
                HeaderKind.LEGACY_SINGLE,
                f"{name}: 代码 Bug not classified as legacy_single",
            )


if __name__ == "__main__":
    unittest.main()

class DescriptionSlotAliasNarrowingTest(unittest.TestCase):
    """BUG-081: description-slot aliases are locale- and section-scoped.

    功能描述/Feature Description is legacy compat for the DEV section only; header
    labels must match the auto-detected locale (SKILL.md). Cross-language labels and
    cross-section labels (事项 in 代码 Bug) stay non-standard for check AND add.
    """

    def _check(self, *lines: str) -> subprocess.CompletedProcess:
        with __import__("tempfile").TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(CLI), "check", "--file", str(target)],
                text=True, capture_output=True, check=False,
            )

    def test_zh_bug_section_with_item_label_is_rejected(self):
        result = self._check(
            "# 测试", "", "## 代码 Bug", "",
            "| ID | 动作 | 事项 | 发现日期 | 状态 | 备注 |",
            "| --- | --- | --- | --- | --- | --- |",
            "| BUG-001 | 修复 | x | 2026-01-05 | 待修复 | - |",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("表头与标准不一致：代码 Bug", result.stdout + result.stderr)

    def test_en_features_with_zh_label_is_rejected(self):
        result = self._check(
            "# Test", "", "## Features", "",
            "| ID | Action | 功能描述 | Done Date | Status | Notes |",
            "| --- | --- | --- | --- | --- | --- |",
            "| DEV-001 | Develop | x | 2026-01-05 | Todo | - |",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Header does not match the standard: Features", result.stdout + result.stderr)

    def test_zh_bug_section_with_en_label_is_rejected(self):
        result = self._check(
            "# 测试", "", "## 代码 Bug", "",
            "| ID | 动作 | Description | 发现日期 | 状态 | 备注 |",
            "| --- | --- | --- | --- | --- | --- |",
            "| BUG-001 | 修复 | x | 2026-01-05 | 待修复 | - |",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("表头与标准不一致：代码 Bug", result.stdout + result.stderr)

    def test_dev_section_legacy_variant_still_accepted(self):
        zh = self._check(
            "# 测试", "", "## 功能开发", "",
            "| ID | 动作 | 功能描述 | 开始日期 | 状态 | 备注 |",
            "| --- | --- | --- | --- | --- | --- |",
            "| DEV-001 | 开发 | x | 2026-01-05 | 待开发 | - |",
        )
        self.assertEqual(zh.returncode, 0, zh.stdout + zh.stderr)
        en = self._check(
            "# Test", "", "## Features", "",
            "| ID | Action | Feature Description | Done Date | Status | Notes |",
            "| --- | --- | --- | --- | --- | --- |",
            "| DEV-001 | Develop | x | 2026-01-05 | Todo | - |",
        )
        self.assertEqual(en.returncode, 0, en.stdout + en.stderr)

    def test_add_refuses_cross_section_description_label(self):
        with __import__("tempfile").TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 测试\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 事项 | 发现日期 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | x | 2026-01-05 | 待修复 | - |\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(CLI), "add", "--file", str(target),
                 "--section", "代码 Bug", "--action", "修复",
                 "--description", "y", "--status", "待修复"],
                text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("拒绝写入", result.stdout + result.stderr)
