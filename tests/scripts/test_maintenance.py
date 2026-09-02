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

    def test_hook_script_has_python_interpreter_fallback(self):
        # On Windows, `python3` is often the Microsoft Store stub (non-zero exit,
        # no output); a hardcoded python3 silently disables the hook and degrades
        # the session guard to a global "default". Both locales must probe and
        # fall back to `python`, and never invoke a bare hardcoded interpreter.
        for lang in ("zh", "en"):
            script = hook_script(lang)
            self.assertIn(
                "if python3 -c 'import sys' >/dev/null 2>&1; then PY=python3; else PY=python; fi",
                script,
            )
            self.assertIn('"$PY" -c', script)
            self.assertNotIn("| python3 -c", script)
            self.assertNotIn("\npython3 -c", script)


if __name__ == "__main__":
    unittest.main()
