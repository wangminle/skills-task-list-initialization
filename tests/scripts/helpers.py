"""Shared test helpers for the task-list CLI and layered package."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "skills" / "task-list-initialization" / "scripts" / "task_list_cli.py"
SCRIPTS = CLI.parent


def ensure_scripts_on_path() -> None:
    """Make ``import _tasklist`` work from unittest files."""
    path = str(SCRIPTS)
    if path not in sys.path:
        sys.path.insert(0, path)


def load_cli_module():
    """Import task_list_cli.py as a module (for unit-testing public helpers)."""
    spec = importlib.util.spec_from_file_location("task_list_cli", CLI)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["task_list_cli"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def run_cli(*args: str, cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=str(cwd or ROOT),
        text=True,
        capture_output=True,
        check=check,
    )


class CliTestCase(unittest.TestCase):
    def run_cli(self, *args, check=True):
        result = subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if check and result.returncode != 0:
            self.fail(
                f"CLI failed with {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
        return result

    def _zh_dual_header(self):
        return "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |"

    def _zh_adj_header(self):
        return "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |"

    def _preview_safety_file(self, *, blank_between=False, notes1="n", notes2="n"):
        gap = "\n" if blank_between else ""
        return (
            "# 任务跟踪列表\n\n"
            "## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            f"| BUG-001 | 修复 | first | 2026-01-01 10:00 | - | 待修复 | {notes1} |\n"
            f"{gap}"
            f"| BUG-002 | 修复 | second | 2026-01-01 11:00 | - | 待修复 | {notes2} |\n"
            "\n## 调整事项\n\n"
            "| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
        )

    def _file_with_fenced_table_example(self):
        return (
            "# 任务跟踪列表\n\n"
            "## 代码 Bug\n\n"
            "| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | real | 2026-01-01 10:00 | - | 待修复 | n |\n"
            "\n"
            "示例：\n\n"
            "```markdown\n"
            "| ID | 动作 |\n"
            "| --- | --- |\n"
            "\n"
            "| BUG-999 | 修复 |\n"
            "```\n"
        )

    def _file_fenced_heading_before_real_table(self, *, with_summary=False, extra_fence_summary=False):
        summary = ""
        if with_summary:
            summary = (
                "\n## 统计摘要\n\n"
                "| 分类 | 总数 | 已完成 | 待开发/待修复 | 完成率 |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| 代码 Bug | 1 | 0 | 1 | 0% |\n"
                "| **总计** | 1 | 0 | 1 | 0% |\n"
            )
        fence_summary = ""
        if extra_fence_summary:
            fence_summary = (
                "```markdown\n"
                "## 统计摘要\n\n"
                "| 分类 | 总数 | 已完成 | 待开发/待修复 | 完成率 |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| 代码 Bug | 99 | 99 | 0 | 100% |\n"
                "```\n\n"
            )
        return (
            "# 任务跟踪列表\n\n"
            "## 代码 Bug\n\n"
            "示例：\n\n"
            "```markdown\n"
            "## 代码 Bug\n\n"
            f"{self._zh_dual_header()}\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| BUG-999 | 修复 | example | 2026-01-01 00:00 | - | 待修复 | - |\n"
            "```\n\n"
            f"{fence_summary}"
            f"{self._zh_dual_header()}\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| BUG-001 | 修复 | real | 2026-01-01 10:00 | - | 待修复 | n |\n"
            f"{summary}"
        )
