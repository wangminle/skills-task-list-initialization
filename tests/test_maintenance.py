"""C4: maintenance rule text is generated from one source."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import ROOT, ensure_scripts_on_path  # noqa: E402

ensure_scripts_on_path()

from _tasklist.locales import MAINTENANCE_RULE_MARKER, MAINTENANCE_RULE_MARKER_EN  # noqa: E402
from _tasklist.maintenance import (  # noqa: E402
    HOOK_SCRIPT_NAME,
    TASKLIST_HOOK_COMMAND,
    hook_script,
    rule_text,
)

REFERENCE = (
    ROOT
    / "skills"
    / "task-list-initialization"
    / "references"
    / "maintenance-rule.md"
)


class MaintenanceSourceTest(unittest.TestCase):
    def test_reference_embeds_generated_rule_and_hook_verbatim(self):
        ref = REFERENCE.read_text(encoding="utf-8")
        self.assertIn(rule_text("zh").strip(), ref)
        self.assertIn(rule_text("en").strip(), ref)
        self.assertIn(hook_script("zh").strip(), ref)
        self.assertIn(
            'Before this session ends, follow the Session-end Task Sync rule in CLAUDE.md',
            ref,
        )
        self.assertIn("${CLAUDE_PROJECT_DIR}/.claude/hooks/tasklist_sync_reminder.sh", ref)
        self.assertIn(HOOK_SCRIPT_NAME, ref)
        self.assertIn(MAINTENANCE_RULE_MARKER, ref)
        self.assertIn(MAINTENANCE_RULE_MARKER_EN, ref)

    def test_markers_and_script_name_are_stable(self):
        self.assertEqual(MAINTENANCE_RULE_MARKER, "会话结束任务同步")
        self.assertEqual(MAINTENANCE_RULE_MARKER_EN, "Session-end Task Sync")
        self.assertEqual(HOOK_SCRIPT_NAME, "tasklist_sync_reminder.sh")
        self.assertIn(HOOK_SCRIPT_NAME, TASKLIST_HOOK_COMMAND)
        self.assertIn("${CLAUDE_PROJECT_DIR}", TASKLIST_HOOK_COMMAND)


if __name__ == "__main__":
    unittest.main()
