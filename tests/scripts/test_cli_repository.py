"""CLI regression tests (split from the former monolithic file)."""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase, load_cli_module  # noqa: E402


class CliRepositoryTest(CliTestCase):
    def test_atomic_write_preserves_target_on_replace_failure(self):
        """If os.replace fails mid-write, the target file must be byte-for-byte unchanged.

        The old code path (path.write_text) truncated the file on failure. atomic_write
        uses a temp + os.replace, so a failed rename leaves the original untouched.
        """
        mod = load_cli_module()

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            original = "# 任务跟踪列表\n\n原始内容\n"
            target.write_text(original, encoding="utf-8")
            original_bytes = target.read_bytes()

            with mock.patch("os.replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    mod.atomic_write(target, "# completely different content\n")

            self.assertEqual(target.read_bytes(), original_bytes)

    def test_commit_all_restores_on_partial_failure(self):
        """commit_all must roll back already-committed files when a later one fails.

        Two files: the first writes fine, the second's os.replace fails. After the
        exception, the first file must be restored to its pre-transaction content.
        """
        mod = load_cli_module()

        with tempfile.TemporaryDirectory() as tmp:
            f1 = Path(tmp) / "a.md"
            f2 = Path(tmp) / "b.md"
            f1.write_text("original-a\n", encoding="utf-8")
            f2.write_text("original-b\n", encoding="utf-8")

            # Fail os.replace only when the destination is f2, so the rollback's own
            # os.replace (which targets f1 to restore it) still succeeds.
            real_replace = os.replace

            def flaky_replace(src, dst):
                if Path(dst) == f2:
                    raise OSError("simulated failure on second file")
                return real_replace(src, dst)

            with mock.patch("os.replace", side_effect=flaky_replace):
                with self.assertRaises(OSError):
                    mod.commit_all([
                        (f1, "new-a\n"),
                        (f2, "new-b\n"),
                    ])

            # f1 must have been restored to its original content, not left as "new-a".
            self.assertEqual(f1.read_text(encoding="utf-8"), "original-a\n")

    def test_req13_install_maintenance_second_file_failure(self):
        """REQ-13 CLI path: fail the hook-script write (2nd planned file); the agent
        file (1st) must be rolled back to its pre-install state — no residual rule."""
        import argparse

        mod = load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            ledger = project / "task-list.md"
            ledger.write_text(
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )
            # command_install_maintenance resolves the project root, so planned paths
            # carry the resolved prefix (/private/var on macOS) — resolve here too.
            hook_script = (
                project / ".claude" / "hooks" / "tasklist_sync_reminder.sh"
            ).resolve()
            real_replace = os.replace

            def flaky_replace(src, dst):
                if Path(dst) == hook_script:
                    raise OSError("simulated failure on second planned file")
                return real_replace(src, dst)

            args = argparse.Namespace(
                file=str(ledger), with_hook=True, dry_run=False
            )
            with mock.patch("os.replace", side_effect=flaky_replace):
                # Capture the command's own prints so module-level tests stay silent
                # (CHK-037 观察③: stray "已安装…" lines polluted the suite output).
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(OSError):
                        mod.command_install_maintenance(args)

            # First file (CLAUDE.md, newly created by the first commit) must have no
            # residual maintenance-rule content after the rollback.
            claude = project / "CLAUDE.md"
            if claude.exists():
                content = claude.read_text(encoding="utf-8")
                self.assertNotIn("会话结束任务同步", content)
                self.assertNotIn("Session-end Task Sync", content)
            self.assertFalse(hook_script.exists())
            self.assertFalse((project / ".claude" / "settings.json").exists())

    def test_req13_archive_write_failure_keeps_main_intact(self):
        """REQ-13 CLI path: fail the archive-file write; the main ledger must be
        byte-for-byte unchanged (never truncated or left half-archived)."""
        import argparse

        mod = load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            ledger = project / "task-list.md"
            original = (
                "# 任务跟踪列表\n\n## 代码 Bug\n\n"
                "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | done long ago | 2026-01-01 09:00 | 2026-01-05 10:00 | 已修复 | - |\n"
            )
            ledger.write_text(original, encoding="utf-8")
            original_bytes = ledger.read_bytes()
            archive_path = project / "task-list-archive-202601.md"
            real_replace = os.replace

            def flaky_replace(src, dst):
                if Path(dst) == archive_path:
                    raise OSError("simulated failure on archive file")
                return real_replace(src, dst)

            args = argparse.Namespace(
                file=str(ledger),
                older_than_days=30,
                as_of="2026-08-17",
                output=str(archive_path),
                dry_run=False,
            )
            with mock.patch("os.replace", side_effect=flaky_replace):
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(OSError):
                        mod.command_archive(args)

            self.assertEqual(ledger.read_bytes(), original_bytes)
            self.assertFalse(archive_path.exists())
