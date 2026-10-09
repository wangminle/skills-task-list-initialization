"""Fleet scan, write-lock, custom-section constraint, and time-precision regressions."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CLI, CliTestCase, ROOT, ensure_scripts_on_path  # noqa: E402

ensure_scripts_on_path()
from _tasklist.fleet import run_fleet  # noqa: E402
from _tasklist.repository import LockTimeout, _lock_fd_once, _unlock_fd, file_lock  # noqa: E402

ZH_HEADER = "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |"
ZH_SEP = "| --- | --- | --- | --- | --- | --- | --- |"
ZH_BUG_SECTION = f"## 代码 Bug\n\n{ZH_HEADER}\n{ZH_SEP}\n"

EN_HEADER = "| ID | Action | Description | Found | Done | Status | Notes |"
EN_SEP = "| --- | --- | --- | --- | --- | --- | --- |"
EN_BUG_SECTION = f"## Bugs\n\n{EN_HEADER}\n{EN_SEP}\n"


def _minimal_file(rows: str = "") -> str:
    return f"# 任务跟踪列表\n\n{ZH_BUG_SECTION}{rows}"


def _en_minimal_file(rows: str = "") -> str:
    return f"# Task Tracking List\n\n{EN_BUG_SECTION}{rows}"


class FleetScanTest(CliTestCase):
    def test_fleet_scans_tree_and_aggregates_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proj-a").mkdir()
            (root / "proj-b").mkdir()
            (root / "proj-a" / "task-list.md").write_text(_minimal_file(), encoding="utf-8")
            (root / "proj-b" / "task-list.md").write_text(
                _minimal_file("| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | n |\n"
                              "\n| BUG-002 | 修复 | y | 2026-01-01 11:00 | - | 待修复 | n |\n"),
                encoding="utf-8",
            )
            result = self.run_cli("fleet", "--root", str(root), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("[通过] proj-a/task-list.md", result.stdout)
            self.assertIn("[失败] proj-b/task-list.md", result.stdout)
            self.assertIn("通过 1、失败 1", result.stdout)

    def test_fleet_exclude_glob_and_default_excludes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep").mkdir()
            (root / "keep" / "task-list.md").write_text(_minimal_file(), encoding="utf-8")
            (root / "skipme" / "examples").mkdir(parents=True)
            (root / "skipme" / "examples" / "task-list.md").write_text(_minimal_file(), encoding="utf-8")
            (root / ".stversions").mkdir()
            (root / ".stversions" / "task-list.md").write_text(_minimal_file(), encoding="utf-8")
            result = self.run_cli("fleet", "--root", str(root), "--exclude", "*/examples")
            self.assertIn("共 1 个", result.stdout)
            entry_lines = [ln for ln in result.stdout.splitlines() if ln.startswith("[")]
            self.assertEqual(len(entry_lines), 1)
            self.assertIn("keep/task-list.md", entry_lines[0])

    def test_fleet_apply_safe_fixes_repairs_and_rechecks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proj").mkdir()
            target = root / "proj" / "task-list.md"
            target.write_text(
                _minimal_file("| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | n |\n"
                              "\n| BUG-002 | 修复 | y | 2026-01-01 11:00 | - | 待修复 | n |\n"),
                encoding="utf-8",
            )
            result = self.run_cli("fleet", "--root", str(root), "--apply-safe-fixes", check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[修复] proj/task-list.md", result.stdout)
            self.assertIn("复检通过", result.stdout)
            self.assertIn("检查通过", self.run_cli("check", "--file", str(target)).stdout)

    def test_fleet_json_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proj").mkdir()
            (root / "proj" / "task-list.md").write_text(_minimal_file(), encoding="utf-8")
            report = root / "out" / "fleet.md"
            result = self.run_cli(
                "fleet", "--root", str(root), "--format", "json", "--report", str(report)
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["total"], 1)
            self.assertEqual(payload["passed"], 1)
            self.assertEqual(payload["files"][0]["rel"], "proj/task-list.md")
            self.assertIn("maintenance", payload["files"][0])
            self.assertIn("proj/task-list.md", report.read_text(encoding="utf-8"))

    def test_fleet_missing_root_and_empty_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = self.run_cli("fleet", "--root", str(Path(tmp) / "nope"), check=False)
            self.assertEqual(missing.returncode, 2)
            empty = self.run_cli("fleet", "--root", tmp, check=False)
            self.assertEqual(empty.returncode, 0)
            self.assertIn("未找到", empty.stdout)


class CustomSectionConstraintTest(CliTestCase):
    def test_id_row_in_headerless_custom_table_fails_check(self):
        # The "第五轮审查" incident shape: a custom log section whose table carries
        # record IDs in the first column of a non-record (headerless) table — counted
        # by the by-prefix summary yet invisible to per-row validation.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                _minimal_file("| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | n |\n")
                + "\n## 2026-09-29 工作日志\n\n"
                "| 编号 | 优先级 | 修复结果 |\n| --- | --- | --- |\n"
                "| BUG-122 | P2 | 伪状态列 |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("BUG-122", result.stdout)
            self.assertIn("不是受支持的记录表", result.stdout)

    def test_custom_section_without_id_rows_still_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                _minimal_file("| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | n |\n")
                + "\n## 2026-09-29 工作日志\n\n"
                "| 命令或操作 | 结果 |\n| --- | --- |\n| pytest | 通过 |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target))
            self.assertIn("检查通过", result.stdout)

    def test_fenced_example_id_rows_are_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                _minimal_file("| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | n |\n")
                + "\n## 说明\n\n```markdown\n| 编号 | 结果 |\n| --- | --- |\n| BUG-122 | 示例 |\n```\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target))
            self.assertIn("检查通过", result.stdout)


class TimePrecisionTest(CliTestCase):
    def test_mixed_precision_same_day_is_not_an_inversion(self):
        # Date-only Done on the same day as a timed Found is precision loss from
        # single→dual migration, not an inversion: no warning, no git archaeology.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                _minimal_file(
                    "| BUG-001 | 修复 | x | 2026-09-02 18:21 | 2026-09-02 | 已修复 | n |\n"
                ),
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target))
            self.assertNotIn("倒挂", result.stdout)

    def test_earlier_calendar_day_still_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                _minimal_file(
                    "| BUG-001 | 修复 | x | 2026-09-02 | 2026-09-01 | 已修复 | n |\n"
                ),
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target))
            self.assertIn("倒挂", result.stdout)

    def test_write_path_accepts_same_day_date_only_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(_minimal_file(), encoding="utf-8")
            ok = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug", "--action", "修复",
                "--description", "x", "--status", "已修复",
                "--found-time", "2026-09-30 15:00", "--completed-time", "2026-09-30",
            )
            self.assertIn("已追加", ok.stdout)
            # BUG-094: the explicit date-only Done lands at DAY precision — no 00:00
            # padding that would manufacture a same-day inversion downstream.
            text = target.read_text(encoding="utf-8")
            self.assertIn("| BUG-001 | 修复 | x | 2026-09-30 15:00 | 2026-09-30 | 已修复 |", text)
            check = self.run_cli("check", "--file", str(target))
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            self.assertNotIn("倒挂", check.stdout)
            # The padded-00:00 inversion used to make even a notes-only update fail the
            # post-write gate (rollback treated the pre-existing warning as NEW).
            followup = self.run_cli(
                "update", "--file", str(target), "--id", "BUG-001", "--notes-append", "后续备注"
            )
            self.assertIn("已更新", followup.stdout)
            bad = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug", "--action", "修复",
                "--description", "y", "--status", "已修复",
                "--found-time", "2026-09-30 15:00", "--completed-time", "2026-09-29",
                check=False,
            )
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("不能早于", bad.stdout + bad.stderr)

    def test_update_path_same_day_date_only_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                _minimal_file(
                    "| BUG-001 | 修复 | x | 2026-09-30 15:00 | 2026-09-30 15:30 | 已修复 | n |\n"
                ),
                encoding="utf-8",
            )
            ok = self.run_cli("update", "--file", str(target), "--id", "BUG-001",
                              "--completed-time", "2026-09-30")
            self.assertIn("已更新", ok.stdout)
            # BUG-094: update also keeps the explicit date-only value at day precision.
            text = target.read_text(encoding="utf-8")
            self.assertIn("| BUG-001 | 修复 | x | 2026-09-30 15:00 | 2026-09-30 | 已修复 |", text)
            check = self.run_cli("check", "--file", str(target))
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            self.assertNotIn("倒挂", check.stdout)
            bad = self.run_cli("update", "--file", str(target), "--id", "BUG-001",
                               "--completed-time", "2026-09-29", check=False)
            self.assertNotEqual(bad.returncode, 0)


class WriteLockTest(CliTestCase):
    def test_file_lock_blocks_second_holder_and_times_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(_minimal_file(), encoding="utf-8")
            with file_lock(target):
                with self.assertRaises(LockTimeout):
                    with file_lock(target, timeout=0.5):
                        pass

    def test_file_lock_released_after_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(_minimal_file(), encoding="utf-8")
            with file_lock(target):
                pass
            with file_lock(target, timeout=1.0):
                pass

    def test_lock_contention_on_one_file_does_not_abort_fleet_sweep(self):
        # BUG-095: a LockTimeout while fixing ONE ledger used to abort the whole
        # --apply-safe-fixes sweep with a traceback, discarding every result already
        # gathered. The file must be recorded as an error entry and the sweep continue.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "locked").mkdir()
            (root / "open").mkdir()
            locked_target = root / "locked" / "task-list.md"
            # Intra-table blank line gives this file an auto-fix candidate so the
            # sweep actually tries to take its lock.
            locked_target.write_text(
                _minimal_file("| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | n |\n"
                              "\n| BUG-002 | 修复 | y | 2026-01-01 11:00 | - | 待修复 | n |\n"),
                encoding="utf-8",
            )
            (root / "open" / "task-list.md").write_text(_minimal_file(), encoding="utf-8")
            held = threading.Event()
            release = threading.Event()

            def hold():
                with file_lock(locked_target):
                    held.set()
                    release.wait(10)

            holder = threading.Thread(target=hold)
            holder.start()
            self.assertTrue(held.wait(5))
            try:
                results = run_fleet(root, apply_fixes=True, lock_timeout=0.5)
            finally:
                release.set()
                holder.join(5)
            by_rel = {entry["rel"]: entry for entry in results}
            self.assertEqual(len(results), 2)
            self.assertEqual(by_rel["locked/task-list.md"]["status"], "error")
            self.assertIn("锁等待超时", by_rel["locked/task-list.md"]["error"])
            self.assertEqual(by_rel["open/task-list.md"]["status"], "pass")

    def test_missing_target_add_creates_no_directory_and_no_lock(self):
        # BUG-099: acquiring the lock used to mkdir the parent and leave a stray
        # task-list.md.lock BEFORE the command reported file_not_found.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = base / "nope" / "task-list.md"
            result = self.run_cli(
                "add", "--file", str(target), "--section", "代码 Bug", "--action", "修复",
                "--description", "x", "--status", "待修复", check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("文件不存在", result.stderr)
            self.assertFalse(
                (base / "nope").exists(), "lock acquisition must not create the parent directory"
            )

    @unittest.skipIf(sys.platform == "win32", "POSIX permission bits")
    def test_unwritable_lock_directory_reports_localized_error(self):
        # BUG-099: creating the lock sidecar in a read-only directory used to leak a
        # raw PermissionError traceback.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "task-list.md"
            target.write_text(_minimal_file(), encoding="utf-8")
            root.chmod(0o555)
            try:
                result = self.run_cli(
                    "add", "--file", str(target), "--section", "代码 Bug", "--action", "修复",
                    "--description", "x", "--status", "待修复", check=False,
                )
                self.assertEqual(result.returncode, 1)
                self.assertIn("无法为", result.stderr)
                self.assertIn("创建写锁", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
            finally:
                root.chmod(0o755)

    def test_concurrent_adds_serialize_and_never_duplicate_ids(self):
        # The duplicate-ID incident shape: N parallel sessions each add one record.
        # With the write lock they serialize; every record lands with a distinct ID.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(_minimal_file(), encoding="utf-8")
            procs = [
                subprocess.Popen(
                    [sys.executable, str(CLI), "add", "--file", str(target),
                     "--section", "代码 Bug", "--action", "修复",
                     "--description", f"并发 {i}", "--status", "待修复"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                for i in range(6)
            ]
            for proc in procs:
                self.assertEqual(proc.wait(), 0)
            ids = [
                line.split("|")[1].strip()
                for line in target.read_text(encoding="utf-8").splitlines()
                if line.startswith("| BUG-")
            ]
            self.assertEqual(len(ids), 6)
            self.assertEqual(len(set(ids)), 6)
            check = self.run_cli("check", "--file", str(target))
            self.assertIn("检查通过", check.stdout)


class MsvcrtLockBranchTest(unittest.TestCase):
    """TST-026②: the Windows (msvcrt) halves of the lock primitives, mocked on POSIX.

    ``_lock_fd_once`` / ``_unlock_fd`` branch on ``os.name == "nt"`` and are
    unreachable on a POSIX run otherwise. The fake mirrors msvcrt.locking's
    byte-range semantics keyed by inode: a second handle onto the SAME file
    conflicts, two different files do not.
    """

    @staticmethod
    def _fake_msvcrt():
        fake = types.ModuleType("msvcrt")
        fake.LK_NBLCK, fake.LK_UNLCK = 1, 2
        state = {"locked": set(), "calls": []}

        def locking(fd, mode, nbytes):
            ino = os.fstat(fd).st_ino
            state["calls"].append((ino, mode, nbytes))
            if mode == fake.LK_NBLCK:
                if ino in state["locked"]:
                    raise OSError(13, "locking byte range already locked")
                state["locked"].add(ino)
            else:
                state["locked"].discard(ino)

        fake.locking = locking
        fake.state = state
        return fake

    def test_lock_fd_once_nt_branch_success_and_conflict(self):
        fake = self._fake_msvcrt()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.md"
            target.write_text("x", encoding="utf-8")
            fd = os.open(str(target), os.O_RDWR | os.O_CREAT, 0o644)
            try:
                with mock.patch.dict(sys.modules, {"msvcrt": fake}):
                    with mock.patch("os.name", "nt"):
                        self.assertTrue(_lock_fd_once(fd))
                        # Same file already locked: msvcrt raises OSError -> False,
                        # which file_lock turns into retry-then-LockTimeout.
                        self.assertFalse(_lock_fd_once(fd))
                        _unlock_fd(fd)
                        self.assertEqual(fake.state["locked"], set())
                        self.assertEqual(fake.state["calls"][-1][1], fake.LK_UNLCK)
                        # Relock after unlock succeeds: the release really freed it.
                        self.assertTrue(_lock_fd_once(fd))
            finally:
                os.close(fd)

    def test_file_lock_nt_branch_acquires_and_times_out(self):
        fake = self._fake_msvcrt()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text("x", encoding="utf-8")
            with mock.patch.dict(sys.modules, {"msvcrt": fake}):
                with mock.patch("os.name", "nt"):
                    with file_lock(target):
                        self.assertEqual(len(fake.state["locked"]), 1)
                        with self.assertRaises(LockTimeout):
                            with file_lock(target, timeout=0.3):
                                pass
                    # Leaving the outer context ran the LK_UNLCK release path.
                    self.assertEqual(fake.state["locked"], set())
            self.assertTrue(any(m == fake.LK_UNLCK for _, m, _ in fake.state["calls"]))


class PseudoHeaderSmugglingTest(CliTestCase):
    """BUG-097: a pseudo header (first cell says ID) is not a supported record table."""

    def test_pseudo_header_custom_table_dev_row_fails_check(self):
        # `| ID | 问题 | 结论 |` gave the custom table non-empty headers, so the old
        # "if not headers" gate never fired: the DEV-777 row entered known_ids and the
        # by-prefix summary counted it as 功能开发 while skipping per-row validation.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                _minimal_file("| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | n |\n")
                + "\n## 临时记录\n\n"
                "| ID | 问题 | 结论 |\n| --- | --- | --- |\n"
                "| DEV-777 | 修复 | 示例 |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("DEV-777", result.stdout)
            self.assertIn("不是受支持的记录表", result.stdout)

    def test_supported_custom_record_section_still_validates_normally(self):
        # The BUG-076 compat surface: a custom section whose header matches a
        # registered record shape stays a legitimate record table (full per-row
        # validation, check passes on a well-formed row).
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                _minimal_file("| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | n |\n")
                + "\n## 读书笔记\n\n"
                "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
                "| --- | --- | --- | --- | --- | --- | --- |\n"
                "| READ-001 | 检查 | 自定义分区记录 | 2026-08-03 10:00 | - | 待办 | - |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target))
            self.assertIn("检查通过", result.stdout)


class SmuggledIdentityTest(CliTestCase):
    """BUG-100: smuggled rows still register identities/references globally."""

    def test_smuggled_rows_register_dup_ref_and_malformed_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(
                _minimal_file(
                    "| BUG-001 | 修复 | x | 2026-01-01 10:00 | - | 待修复 | 关联 [[DEV-777]] |\n"
                )
                + "\n## 工作日志\n\n"
                "| 编号 | 优先级 | 修复结果 |\n| --- | --- | --- |\n"
                "| BUG-001 | P2 | 重复登记 |\n"
                "| DEV-777 | P2 | 走私行 |\n"
                "| BUG-01 | P2 | 两位数字 |\n",
                encoding="utf-8",
            )
            result = self.run_cli("check", "--file", str(target), check=False)
            self.assertEqual(result.returncode, 1)
            # Duplicate across standard + smuggled table is reported.
            self.assertIn("重复 ID：BUG-001", result.stdout)
            # A [[ref]] to an ID that only exists in the smuggled table is NOT dangling.
            self.assertNotIn("悬空", result.stdout)
            # Two-digit ID shapes surface instead of falling through silently.
            self.assertIn("BUG-01", result.stdout)
            self.assertIn("ID 格式非法", result.stdout)


class FleetOutputContractTest(CliTestCase):
    """BUG-098/BUG-101: fleet machine output and report robustness."""

    def test_empty_tree_json_output_is_parseable(self):
        # Zero files used to print localized prose on stdout, breaking json.load in
        # automation; the JSON contract must hold for the empty sweep too.
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_cli("fleet", "--root", tmp, "--format", "json", check=False)
            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["total"], 0)
            self.assertEqual(payload["files"], [])
            self.assertEqual(payload["scan_errors"], [])

    def test_report_includes_user_excludes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep").mkdir()
            (root / "keep" / "task-list.md").write_text(_minimal_file(), encoding="utf-8")
            (root / "scratch").mkdir()
            (root / "scratch" / "task-list.md").write_text(_minimal_file(), encoding="utf-8")
            report = root / "fleet.md"
            self.run_cli(
                "fleet", "--root", str(root), "--exclude", "scratch", "--report", str(report)
            )
            text = report.read_text(encoding="utf-8")
            self.assertIn("scratch", text)
            self.assertNotIn("scratch/task-list.md", text)

    def test_unwritable_report_path_is_a_localized_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proj").mkdir()
            (root / "proj" / "task-list.md").write_text(_minimal_file(), encoding="utf-8")
            blocker = root / "blocker"
            blocker.write_text("i am a file", encoding="utf-8")
            result = self.run_cli(
                "fleet", "--root", str(root), "--report", str(blocker / "sub" / "fleet.md"),
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("无法写入报告", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    @unittest.skipIf(sys.platform == "win32", "POSIX permission bits")
    def test_unreadable_directory_fails_the_sweep_loudly(self):
        # os.walk's default onerror=None swallowed PermissionError, so a mis-permissioned
        # root reported "no files found" with exit 0 as if the sweep had covered everything.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep").mkdir()
            (root / "keep" / "task-list.md").write_text(_minimal_file(), encoding="utf-8")
            locked_dir = root / "vault"
            locked_dir.mkdir()
            (locked_dir / "task-list.md").write_text(_minimal_file(), encoding="utf-8")
            locked_dir.chmod(0o000)
            try:
                result = self.run_cli("fleet", "--root", str(root), check=False)
                self.assertEqual(result.returncode, 1)
                self.assertIn("读取失败", result.stdout)
                self.assertIn("巡检可能不完整", result.stdout)
                json_result = self.run_cli(
                    "fleet", "--root", str(root), "--format", "json", check=False
                )
                payload = json.loads(json_result.stdout)
                self.assertEqual(payload["total"], 1)
                self.assertEqual(len(payload["scan_errors"]), 1)
                self.assertIn("vault", payload["scan_errors"][0])
            finally:
                locked_dir.chmod(0o755)

    def test_report_escapes_pipe_in_relative_path(self):
        # BUG-101: a directory named a|b split the report's first column.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            piped = root / "a|b"
            piped.mkdir()
            (piped / "task-list.md").write_text(_minimal_file(), encoding="utf-8")
            report = root / "fleet.md"
            self.run_cli("fleet", "--root", str(root), "--report", str(report))
            text = report.read_text(encoding="utf-8")
            data_row = next(
                line for line in text.splitlines()
                if line.startswith("| ") and "task-list.md" in line
            )
            self.assertIn("a\\|b/task-list.md", data_row)
            # 8 columns + leading/trailing pipes; escaped pipes must not split a cell.
            import re as _re

            self.assertEqual(len(_re.split(r"(?<!\\)\|", data_row)), 10)


class FleetEnglishLocaleTest(CliTestCase):
    """TST-026⑥: the fleet suite asserted only Chinese output; the en matrix now covered."""

    def test_english_ledgers_render_english_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pass").mkdir()
            (root / "fail").mkdir()
            (root / "pass" / "task-list.md").write_text(_en_minimal_file(), encoding="utf-8")
            (root / "fail" / "task-list.md").write_text(
                _en_minimal_file(
                    "| BUG-001 | Fix | x | 2026-01-01 10:00 | - | Pending Fix | n |\n"
                    "\n| BUG-002 | Fix | y | 2026-01-01 11:00 | - | Pending Fix | n |\n"
                ),
                encoding="utf-8",
            )
            result = self.run_cli("fleet", "--root", str(root), "--lang", "en", check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("[PASS] pass/task-list.md", result.stdout)
            self.assertIn("[FAIL] fail/task-list.md", result.stdout)
            # The failing file's own diagnostics come out in the FILE's language (en).
            self.assertIn("blank line", result.stdout)
            self.assertNotIn("通过", result.stdout)
            self.assertIn("1 passed, 1 failed", result.stdout)

    def test_english_report_and_json_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proj").mkdir()
            (root / "proj" / "task-list.md").write_text(_en_minimal_file(), encoding="utf-8")
            report = root / "fleet.md"
            result = self.run_cli(
                "fleet", "--root", str(root), "--lang", "en",
                "--format", "json", "--report", str(report),
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["total"], 1)
            self.assertEqual(payload["passed"], 1)
            self.assertEqual(payload["files"][0]["lang"], "en")
            text = report.read_text(encoding="utf-8")
            self.assertIn("# task-list Fleet Scan Report", text)
            self.assertIn("| File | Result | Records | Profile | Schema |", text)
            self.assertIn("pass", text)

    def test_en_output_language_over_zh_ledger(self):
        # --lang steers only the sweep's own framing; the zh ledger is detected,
        # reported, and counted in its own locale (lang: zh), framed by English labels.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "zhproj").mkdir()
            (root / "zhproj" / "task-list.md").write_text(_minimal_file(), encoding="utf-8")
            text = self.run_cli("fleet", "--root", str(root), "--lang", "en")
            self.assertIn("[PASS] zhproj/task-list.md", text.stdout)
            payload = json.loads(
                self.run_cli("fleet", "--root", str(root), "--lang", "en", "--format", "json").stdout
            )
            self.assertEqual(payload["files"][0]["lang"], "zh")
            self.assertEqual(payload["passed"], 1)


class Python38CompatTest(CliTestCase):
    def test_no_python39_only_runtime_apis_in_scripts(self):
        # BUG-096 (BUG-092 family): the package promises Python 3.8+, so no
        # 3.9+-only stdlib attribute accesses may appear under scripts/. AST-level,
        # so docstrings/comments mentioning an API do not false-positive.
        import ast

        scripts_dir = ROOT / "skills" / "task-list-initialization" / "scripts"
        banned = {"is_relative_to", "removeprefix", "removesuffix", "with_stem"}
        sources = sorted(scripts_dir.rglob("*.py"))
        self.assertTrue(sources)
        for py in sources:
            tree = ast.parse(py.read_text(encoding="utf-8"))
            used = {
                node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
            }
            hit = banned & used
            self.assertFalse(
                hit,
                f"{sorted(hit)} are Python 3.9+ APIs (package promises 3.8+); found in {py}",
            )


class FleetBoundaryTest(CliTestCase):
    """BUG-102/103/104: per-file decode isolation, empty-tree reports, path escaping."""

    def test_bad_maintenance_encoding_does_not_abort_the_sweep(self):
        # BUG-102: a UTF-16 CLAUDE.md beside a valid ledger used to raise
        # UnicodeDecodeError outside the per-file boundary, emptying stdout and
        # discarding every other project's result.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "good").mkdir()
            (root / "bad").mkdir()
            (root / "good" / "task-list.md").write_text(_minimal_file(), encoding="utf-8")
            (root / "bad" / "task-list.md").write_text(_minimal_file(), encoding="utf-8")
            (root / "bad" / "CLAUDE.md").write_bytes(b"\xff\xfe")
            result = self.run_cli(
                "fleet", "--root", str(root), "--format", "json", check=False
            )
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("Traceback", result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["total"], 2)
            by_rel = {entry["rel"]: entry for entry in payload["files"]}
            self.assertEqual(by_rel["good/task-list.md"]["status"], "pass")
            self.assertEqual(by_rel["bad/task-list.md"]["status"], "error")
            self.assertTrue(by_rel["bad/task-list.md"].get("error"))

    def test_empty_text_mode_writes_and_overwrites_the_report(self):
        # BUG-103: default text output returned before --report, so an empty tree
        # exited 0 without creating the report and left a previous report stale.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "out.md"
            report.write_text("STALE REPORT\n", encoding="utf-8")
            result = self.run_cli(
                "fleet", "--root", str(root), "--report", str(report), check=False
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("未找到任何 task-list.md", result.stdout)
            text = report.read_text(encoding="utf-8")
            self.assertNotIn("STALE REPORT", text)
            self.assertIn("# task-list 批量巡检报告", text)
            self.assertIn("| 文件 | 结果 | 记录 |", text)
            self.assertIn("已生成报告", result.stderr)

            json_report = root / "out.json.md"
            json_result = self.run_cli(
                "fleet", "--root", str(root), "--format", "json",
                "--report", str(json_report), check=False,
            )
            self.assertEqual(json_result.returncode, 0)
            self.assertEqual(json.loads(json_result.stdout)["total"], 0)
            self.assertIn("# task-list 批量巡检报告", json_report.read_text(encoding="utf-8"))

            blocker = root / "blocker"
            blocker.write_text("not a directory", encoding="utf-8")
            blocked = self.run_cli(
                "fleet", "--root", str(root),
                "--report", str(blocker / "sub" / "fleet.md"),
                check=False,
            )
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("无法写入报告", blocked.stderr)
            self.assertNotIn("Traceback", blocked.stderr)

    def test_report_escapes_backslash_then_pipe_in_relative_path(self):
        # BUG-104: escaping only "|" leaves an even run of backslashes in front of
        # the pipe, so split_cells still sees a column break. escape_cell escapes
        # backslashes first.
        from _tasklist.parser import split_cells

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            weird = root / "a\\|b"
            weird.mkdir()
            (weird / "task-list.md").write_text(_minimal_file(), encoding="utf-8")
            report = root / "fleet.md"
            self.run_cli("fleet", "--root", str(root), "--report", str(report))
            text = report.read_text(encoding="utf-8")
            data_row = next(
                line for line in text.splitlines()
                if "task-list.md" in line and line.startswith("| ")
            )
            header = next(line for line in text.splitlines() if line.startswith("| 文件 |"))
            cells = split_cells(data_row)
            self.assertEqual(len(cells), len(split_cells(header)))
            self.assertEqual(len(cells), 8)
            self.assertEqual(cells[0], "a\\|b/task-list.md")


if __name__ == "__main__":
    import unittest

    unittest.main()
