"""CLI regression tests (split from the former monolithic file)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase  # noqa: E402


class CliInitTest(CliTestCase):
    def test_init_generates_default_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))

            text = target.read_text(encoding="utf-8")
            self.assertIn("# 任务跟踪列表", text)
            self.assertIn("## 代码 Bug", text)
            self.assertIn("| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |", text)
            self.assertIn("| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |", text)
            self.assertIn("## 配置运维", text)

    def test_init_english_template(self):
        # --lang en produces an English template: English title, section headings, columns.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--lang", "en", "--output", str(target))
            text = target.read_text(encoding="utf-8")
            self.assertIn("# Task Tracking List", text)
            self.assertIn("## Bugs", text)
            self.assertIn("## Ops", text)
            self.assertIn("| ID | Action | Description | Found | Done | Status | Notes |", text)
            self.assertIn("> Fields: The Action field allows only these 8 fixed values", text)
            # Chinese must NOT leak into the English template.
            self.assertNotIn("任务跟踪列表", text)
            self.assertNotIn("代码 Bug", text)

    def test_init_default_lang_is_chinese(self):
        # No --lang → Chinese (Simplified) template, preserving prior behavior.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            text = target.read_text(encoding="utf-8")
            self.assertIn("# 任务跟踪列表", text)
            self.assertIn("## 代码 Bug", text)
