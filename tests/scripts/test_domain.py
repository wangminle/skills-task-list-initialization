"""C1: domain types cover four date semantics, not just single/dual column counts."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import ensure_scripts_on_path  # noqa: E402

ensure_scripts_on_path()

from _tasklist.domain import (  # noqa: E402
    DateSemantic,
    HeaderKind,
    Ledger,
    SectionSchema,
    TaskRecord,
    ValidationIssue,
)
from _tasklist.locales import LOCALES  # noqa: E402
from _tasklist.schemas import date_column_semantic, resolve_header  # noqa: E402


class DomainDateSemanticTest(unittest.TestCase):
    def test_four_date_semantics_exist(self):
        self.assertEqual(
            {member.value for member in DateSemantic},
            {"found", "completed", "started", "planned"},
        )

    def test_zh_and_en_labels_map_to_all_four_semantics(self):
        zh = LOCALES["zh"]
        en = LOCALES["en"]
        expected = {
            ("发现日期", "zh", DateSemantic.FOUND),
            ("完成日期", "zh", DateSemantic.COMPLETED),
            ("开始日期", "zh", DateSemantic.STARTED),
            ("规划日期", "zh", DateSemantic.PLANNED),
            ("Found Date", "en", DateSemantic.FOUND),
            ("Done Date", "en", DateSemantic.COMPLETED),
            ("Start Date", "en", DateSemantic.STARTED),
            ("Plan Date", "en", DateSemantic.PLANNED),
        }
        for label, lang, semantic in expected:
            locale = zh if lang == "zh" else en
            self.assertEqual(date_column_semantic(label, locale), semantic.value)

    def test_resolve_header_distinguishes_legacy_semantics_not_just_column_count(self):
        zh = LOCALES["zh"]
        bug = next(s for s in zh.base_sections if s.prefix == "BUG")
        found = ["ID", "动作", "问题描述", "发现日期", "状态", "备注"]
        done = ["ID", "动作", "问题描述", "完成日期", "状态", "备注"]
        started = ["ID", "动作", "问题描述", "开始日期", "状态", "备注"]
        planned = ["ID", "动作", "问题描述", "规划日期", "状态", "备注"]
        dual = ["ID", "动作", "问题描述", "发现时间", "完成时间", "状态", "备注"]

        self.assertEqual(resolve_header(found, bug, zh).kind, HeaderKind.LEGACY_SINGLE)
        self.assertEqual(resolve_header(found, bug, zh).semantic, DateSemantic.FOUND)
        self.assertEqual(resolve_header(done, bug, zh).semantic, DateSemantic.COMPLETED)
        self.assertEqual(resolve_header(started, bug, zh).kind, HeaderKind.LEGACY_SINGLE)
        self.assertEqual(resolve_header(started, bug, zh).semantic, DateSemantic.STARTED)
        self.assertEqual(resolve_header(planned, bug, zh).semantic, DateSemantic.PLANNED)
        self.assertEqual(resolve_header(dual, bug, zh).kind, HeaderKind.STANDARD_DUAL)
        self.assertIsNone(resolve_header(dual, bug, zh).semantic)

    def test_resolve_header_accepts_feature_description_description_alias(self):
        # REQ-05: the translation-workflow sample's 功能开发 section uses 功能描述 as the
        # description column with a 开始日期 date column. This is the same single-date shape
        # as 事项 — it must pass check/add (header recognition), while migration reports the
        # unmappable 开始日期 semantic (REQ-03) instead of a generic "unknown header" error.
        zh = LOCALES["zh"]
        dev = next(s for s in zh.base_sections if s.prefix == "DEV")
        header = ["ID", "动作", "功能描述", "开始日期", "状态", "备注"]
        resolved = resolve_header(header, dev, zh)
        self.assertEqual(resolved.kind, HeaderKind.LEGACY_SINGLE)
        self.assertEqual(resolved.semantic, DateSemantic.STARTED)

    def test_section_schema_field_index_is_name_based(self):
        schema = SectionSchema.from_columns(
            title="代码 Bug",
            prefix="BUG",
            columns=("ID", "动作", "问题描述", "发现时间", "完成时间", "状态", "备注"),
        )
        self.assertEqual(schema.field_index["status"], 5)
        self.assertEqual(schema.field_index["notes"], 6)
        self.assertNotIn(-2, schema.field_index.values())

    def test_task_record_and_validation_issue_are_constructible(self):
        record = TaskRecord(
            item_id="BUG-001",
            action="修复",
            description="示例",
            status="待修复",
            notes="-",
            section_title="代码 Bug",
            dates={DateSemantic.FOUND: "2026-08-14 01:00"},
            source_line=12,
        )
        issue = ValidationIssue(
            code="duplicate_id",
            message="重复 ID：BUG-001",
            severity="error",
            line=12,
        )
        ledger = Ledger(source_text="# x\n", records=(record,), issues=(issue,))
        self.assertEqual(ledger.records[0].item_id, "BUG-001")
        self.assertEqual(ledger.issues[0].code, "duplicate_id")


if __name__ == "__main__":
    unittest.main()
