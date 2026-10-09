"""BUG-106~110 regressions: report overwrite, concurrent archive, separator gate, pipe titles, width-row IDs."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase, SCRIPTS, ensure_scripts_on_path  # noqa: E402

ensure_scripts_on_path()

ZH_HEADER = "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |"
ZH_SEP = "| --- | --- | --- | --- | --- | --- | --- |"
ZH_BUG_SECTION = f"## 代码 Bug\n\n{ZH_HEADER}\n{ZH_SEP}\n"
ZH_ADJ_HEADER = "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |"


def _minimal_file(rows: str = "") -> str:
    return f"# 任务跟踪列表\n\n{ZH_BUG_SECTION}{rows}"


class FleetReportOverwriteGuardTest(CliTestCase):
    """BUG-106: --report must never overwrite an input ledger, aliases included."""

    def test_fleet_report_refuses_input_ledger_and_keeps_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proj").mkdir()
            target = root / "proj" / "task-list.md"
            original = _minimal_file()
            target.write_text(original, encoding="utf-8")
            result = self.run_cli(
                "fleet", "--root", str(root), "--report", str(target), check=False
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("是同一文件", result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_fleet_report_refuses_input_ledger_via_dotted_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proj").mkdir()
            target = root / "proj" / "task-list.md"
            original = _minimal_file()
            target.write_text(original, encoding="utf-8")
            alias = str(root / "proj" / ".." / "proj" / "task-list.md")
            result = self.run_cli(
                "fleet", "--root", str(root), "--report", alias, check=False
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("是同一文件", result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_fleet_apply_safe_fixes_with_report_on_input_refuses_before_repairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proj").mkdir()
            target = root / "proj" / "task-list.md"
            # The intra-table blank line is exactly what --apply-safe-fixes would
            # remove; refusing the clash must also keep the REPAIR from running.
            original = _minimal_file(
                "| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | n |\n"
                "\n"
                "| BUG-002 | 修复 | y | 2026-01-01 11:00 | - | 待修复 | n |\n"
            )
            target.write_text(original, encoding="utf-8")
            result = self.run_cli(
                "fleet",
                "--root",
                str(root),
                "--apply-safe-fixes",
                "--report",
                str(target),
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("是同一文件", result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_fleet_report_to_distinct_path_still_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proj").mkdir()
            target = root / "proj" / "task-list.md"
            original = _minimal_file()
            target.write_text(original, encoding="utf-8")
            report = Path(tmp) / "fleet-report.md"
            result = self.run_cli("fleet", "--root", str(root), "--report", str(report))
            self.assertEqual(result.returncode, 0)
            self.assertTrue(report.exists())
            self.assertIn("task-list.md", report.read_text(encoding="utf-8"))
            self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_standardize_report_on_input_refuses_before_repairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            original = _minimal_file(
                "| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | n |\n"
                "\n"
                "| BUG-002 | 修复 | y | 2026-01-01 11:00 | - | 待修复 | n |\n"
            )
            target.write_text(original, encoding="utf-8")
            result = self.run_cli(
                "standardize",
                "--file",
                str(target),
                "--apply-safe-fixes",
                "--report",
                str(target),
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("是同一文件", result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), original)


# Child-process source for the BUG-107 concurrency test. Each process runs a full
# `archive` CLI invocation but stalls INSIDE its critical section (at commit_all)
# until the peer arrives or 2s pass. Under the fix only one child can be in that
# section at a time - the other is blocked on the archive's own lock - so the loser
# times out, commits, releases, and the winner re-reads the archive fresh before
# merging. Without the archive lock, both children read the shared archive BEFORE
# either writes, so the later commit silently drops the other's records (BUG-107).
ARCHIVE_RUNNER_SOURCE = '''\
import sys
import time
from pathlib import Path

scripts, mine, peer = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
cli_args = sys.argv[4:]

sys.path.insert(0, scripts)
from _tasklist import cli as cli_impl

real_commit_all = cli_impl.commit_all


def commit_all_with_barrier(updates):
    mine.write_text("ready", encoding="utf-8")
    deadline = time.monotonic() + 2.0
    while not peer.exists():
        if time.monotonic() > deadline:
            break
        time.sleep(0.01)
    return real_commit_all(updates)


cli_impl.commit_all = commit_all_with_barrier
sys.exit(cli_impl.main(["archive", *cli_args]))
'''


class ConcurrentArchiveSharedTargetTest(CliTestCase):
    """BUG-107: two mains archiving into one shared archive must not lose records."""

    def test_two_mains_archiving_concurrently_keep_all_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "a").mkdir()
            (tmp_path / "b").mkdir()
            main_a = tmp_path / "a" / "task-list.md"
            main_b = tmp_path / "b" / "task-list.md"
            main_a.write_text(
                _minimal_file(
                    "| BUG-101 | 修复 | done-a | 2026-01-01 10:00 | 2026-01-02 10:00 | 已修复 | n |\n"
                    "| BUG-102 | 修复 | keep-a | 2026-01-01 11:00 | - | 待修复 | n |\n"
                ),
                encoding="utf-8",
            )
            main_b.write_text(
                _minimal_file(
                    "| BUG-201 | 修复 | done-b | 2026-01-01 10:00 | 2026-01-02 10:00 | 已修复 | n |\n"
                    "| BUG-202 | 修复 | keep-b | 2026-01-01 11:00 | - | 待修复 | n |\n"
                ),
                encoding="utf-8",
            )
            archive = tmp_path / "shared-archive.md"
            runner = tmp_path / "concurrent_archive_runner.py"
            runner.write_text(ARCHIVE_RUNNER_SOURCE, encoding="utf-8")

            def spawn(mine: Path, peer: Path, main: Path) -> subprocess.Popen:
                return subprocess.Popen(
                    [
                        sys.executable,
                        str(runner),
                        str(SCRIPTS),
                        str(mine),
                        str(peer),
                        "--file",
                        str(main),
                        "--older-than-days",
                        "30",
                        "--as-of",
                        "2026-10-08",
                        "--output",
                        str(archive),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

            proc_a = spawn(tmp_path / "marker-a", tmp_path / "marker-b", main_a)
            proc_b = spawn(tmp_path / "marker-b", tmp_path / "marker-a", main_b)
            out_a, err_a = proc_a.communicate(timeout=120)
            out_b, err_b = proc_b.communicate(timeout=120)
            self.assertEqual(proc_a.returncode, 0, f"A stdout:\n{out_a}\nA stderr:\n{err_a}")
            self.assertEqual(proc_b.returncode, 0, f"B stdout:\n{out_b}\nB stderr:\n{err_b}")

            archive_text = archive.read_text(encoding="utf-8")
            self.assertIn("BUG-101", archive_text)
            self.assertIn("BUG-201", archive_text)
            # each main dropped only its own archived record
            self.assertNotIn("BUG-101", main_a.read_text(encoding="utf-8"))
            self.assertIn("BUG-102", main_a.read_text(encoding="utf-8"))
            self.assertNotIn("BUG-201", main_b.read_text(encoding="utf-8"))
            self.assertIn("BUG-202", main_b.read_text(encoding="utf-8"))


class SeparatorGateTest(CliTestCase):
    """BUG-108: a record-table header without a same-width delimiter row breaks preview."""

    def test_check_flags_missing_separator(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                f"{ZH_HEADER}\n"
                "| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | n |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("第 5 行记录表头下缺少紧邻的分隔行（表头 7 列）", result.stdout)

    def test_check_flags_separator_width_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                f"{ZH_HEADER}\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | n |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("第 6 行分隔行 6 列与表头 7 列不一致", result.stdout)

    def test_check_flags_blank_line_between_header_and_separator(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                f"{ZH_HEADER}\n"
                "\n"
                f"{ZH_SEP}\n"
                "| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | n |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("缺少紧邻的分隔行", result.stdout)

    def test_fenced_example_header_without_separator_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                f"{ZH_HEADER}\n{ZH_SEP}\n"
                "| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | n |\n"
                "\n示例：\n\n"
                "```markdown\n"
                "| ID | 动作 |\n"
                "| BUG-999 | 修复 |\n"
                "```\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target))
            self.assertEqual(result.returncode, 0)

    def test_add_refuses_section_with_broken_separator(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            original = (
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                f"{ZH_HEADER}\n"
                "| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | n |\n"
                "\n## 调整事项\n\n"
                f"{ZH_ADJ_HEADER}\n{ZH_SEP}\n"
            )
            target.write_text(original, encoding="utf-8")
            result = self.run_cli(
                "add",
                "--file",
                str(target),
                "--section",
                "代码 Bug",
                "--action",
                "修复",
                "--description",
                "new bug",
                "--status",
                "待修复",
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("add 已拒绝写入", result.stderr)
            self.assertIn("代码 Bug", result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_add_still_writes_healthy_section_in_same_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                "# 任务跟踪列表\n\n"
                "## 代码 Bug\n\n"
                f"{ZH_HEADER}\n"
                "| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | n |\n"
                "\n## 调整事项\n\n"
                f"{ZH_ADJ_HEADER}\n{ZH_SEP}\n",
                encoding="utf-8",
            )
            result = self.run_cli(
                "add",
                "--file",
                str(target),
                "--section",
                "调整事项",
                "--action",
                "调整",
                "--description",
                "tweak",
                "--status",
                "待办",
                check=False,
            )
            # The pre-existing separator defect is disclosed, not blocking (no-deadlock
            # baseline policy); the healthy section stays writable.
            self.assertEqual(result.returncode, 0, result.stderr)
            text = target.read_text(encoding="utf-8")
            self.assertIn("| ADJ-001 | 调整 | tweak |", text)
            self.assertIn("存量问题", result.stderr)


class PipeTitleSummaryTest(CliTestCase):
    """BUG-109: `|` in a custom section title must be escaped in the summary table."""

    @staticmethod
    def _pipe_file() -> str:
        return (
            "# 任务跟踪列表\n\n"
            "## 研究 | 调试\n\n"
            f"{ZH_HEADER}\n{ZH_SEP}\n"
            "| DEV-001 | 开发 | x | 2026-01-01 10:00 | - | 待开发 | n |\n"
        )

    def test_summary_write_escapes_pipe_in_category_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(self._pipe_file(), encoding="utf-8")
            result = self.run_cli("summary", "--file", str(target), "--write")
            self.assertEqual(result.returncode, 0)
            text = target.read_text(encoding="utf-8")
            self.assertIn("| 研究 \\| 调试 | 1 | 0 | 1 | 0% |", text)
            # the written table is a valid 5-column GFM table
            result = self.run_cli("check", "--file", str(target))
            self.assertEqual(result.returncode, 0, result.stdout)
            # rewriting from the escaped form is idempotent
            before = target.read_text(encoding="utf-8")
            result = self.run_cli("summary", "--file", str(target), "--write")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(target.read_text(encoding="utf-8"), before)

    def test_check_flags_legacy_unescaped_pipe_summary_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                self._pipe_file()
                + "\n## 统计摘要\n\n"
                "| 分类 | 总数 | 已完成 | 待开发/待修复 | 完成率 |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| 研究 | 调试 | 1 | 0 | 1 | 0% |\n"
                "| **总计** | 1 | 0 | 1 | 0% |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("摘要表第 13 行有 6 列，与摘要表 5 列不一致", result.stdout)

    def test_check_flags_missing_summary_category_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                self._pipe_file()
                + "\n## 统计摘要\n\n"
                "| 分类 | 总数 | 已完成 | 待开发/待修复 | 完成率 |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| **总计** | 1 | 0 | 1 | 0% |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("摘要表缺少分类「研究 | 调试」的行", result.stdout)


class WidthRowIdTest(CliTestCase):
    """BUG-110: width-anomalous rows must still register their ID."""

    def test_overwide_row_participates_in_duplicate_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                _minimal_file(
                    "| DEV-777 | 开发 | wide | 2026-01-01 10:00 | - | 待开发 | note | extra |\n"
                    "| DEV-777 | 开发 | dup | 2026-01-01 11:00 | - | 待开发 | n |\n"
                ),
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("重复 ID：DEV-777", result.stdout)
            # the width anomaly itself is still reported
            self.assertIn("列数异常", result.stdout)

    def test_overwide_row_id_resolves_wiki_refs_no_false_dangling(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                _minimal_file(
                    "| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | see [[DEV-777]] |\n"
                    "| DEV-777 | 开发 | wide | 2026-01-01 10:00 | - | 待开发 | note | extra |\n"
                ),
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("列数异常", result.stdout)
            self.assertNotIn("悬空引用", result.stdout)
            self.assertNotIn("DEV-777 指向不存在", result.stdout)


if __name__ == "__main__":
    unittest.main()
