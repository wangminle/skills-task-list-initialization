"""CLI regression tests (split from the former monolithic file)."""

from __future__ import annotations

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
