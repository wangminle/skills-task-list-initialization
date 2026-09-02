"""Meta-tests for evals.json and its fixtures (DEF-06 / REQ-10).

Every eval whose prompt assumes "task-list.md already exists" must ship a real fixture
file so the evaluation workspace has the assumed preconditions. These tests guard that
contract: referenced fixtures must exist, parse, and — where the prompt makes a specific
claim about the file's state (e.g. "legacy single-date schema") — the fixture actually
exhibits that state.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "skills" / "task-list-initialization"
EVALS_JSON = SKILL_DIR / "evals" / "evals.json"
CLI = SKILL_DIR / "scripts" / "task_list_cli.py"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=SKILL_DIR,
        text=True,
        capture_output=True,
        check=False,
    )


class EvalsMetaTest(unittest.TestCase):
    def test_evals_json_is_valid_and_has_expected_count(self):
        data = json.loads(EVALS_JSON.read_text(encoding="utf-8"))
        self.assertEqual(data["skill_name"], "task-list-initialization")
        self.assertEqual(len(data["evals"]), 8)
        ids = [e["id"] for e in data["evals"]]
        self.assertEqual(ids, [1, 2, 3, 4, 5, 6, 7, 8])

    def test_all_referenced_fixtures_exist(self):
        data = json.loads(EVALS_JSON.read_text(encoding="utf-8"))
        for ev in data["evals"]:
            for rel in ev.get("files", []):
                fixture = SKILL_DIR / rel
                self.assertTrue(
                    fixture.exists(),
                    f"eval {ev['id']} ({ev['name']}) references {rel} but it does not exist",
                )

    def test_no_eval_with_existing_file_assumption_has_empty_files(self):
        """An eval whose prompt assumes task-list.md already exists must provide a fixture.

        This is the core DEF-06 fix: previously evals 2/3/4/5 all had `files: []` while
        their prompts said "我们项目根的 task-list.md 已经存在了". Detect the assumption
        heuristically via prompt keywords and assert files is non-empty.
        """
        data = json.loads(EVALS_JSON.read_text(encoding="utf-8"))
        assumption_markers = [
            "已经存在",
            "已经有了",
            "已有 BUG-001",
            "已有「统计摘要」",
            "半年前的",
            "task-list.md 里已有",
        ]
        for ev in data["evals"]:
            prompt = ev.get("prompt", "")
            assumes_existing = any(marker in prompt for marker in assumption_markers)
            if assumes_existing:
                self.assertTrue(
                    ev.get("files"),
                    f"eval {ev['id']} ({ev['name']}) assumes an existing file but has empty files",
                )

    def test_eval3_fixture_reports_single_date_schema(self):
        """eval 3's prompt claims a legacy 6-column single-date schema — the fixture must match."""
        data = json.loads(EVALS_JSON.read_text(encoding="utf-8"))
        ev3 = next(e for e in data["evals"] if e["id"] == 3)
        fixture = SKILL_DIR / ev3["files"][0]
        result = _run_cli("standardize", "--file", str(fixture), "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(
            report.get("schema"),
            "single",
            "eval 3 fixture must be detected as single-date schema",
        )

    def test_eval4_fixture_has_bug001_in_progress(self):
        """eval 4's prompt says BUG-001 status is 进行中 — the fixture must match."""
        data = json.loads(EVALS_JSON.read_text(encoding="utf-8"))
        ev4 = next(e for e in data["evals"] if e["id"] == 4)
        fixture = SKILL_DIR / ev4["files"][0]
        text = fixture.read_text(encoding="utf-8")
        self.assertIn("BUG-001", text)
        # The BUG-001 row must carry 进行中 (not 已修复), matching the prompt premise.
        bug_line = next(line for line in text.splitlines() if "BUG-001" in line and "|" in line and "ID" not in line)
        self.assertIn("进行中", bug_line)

    def test_eval5_fixture_has_summary_section_with_zero_counts(self):
        """eval 5's prompt says the summary table exists but numbers are all 0."""
        data = json.loads(EVALS_JSON.read_text(encoding="utf-8"))
        ev5 = next(e for e in data["evals"] if e["id"] == 5)
        fixture = SKILL_DIR / ev5["files"][0]
        text = fixture.read_text(encoding="utf-8")
        self.assertIn("## 统计摘要", text)
        # The 总计 row must read all zeros (the stale state the prompt describes).
        total_line = next(line for line in text.splitlines() if "**总计**" in line)
        self.assertIn("| 0 | 0 | 0 | 0%", total_line.replace("**", ""))

    def test_eval7_fixture_check_fails_on_intra_table_blank(self):
        """eval 7's fixture must fail check for a blank between BUG rows, then pass after safe-fixes."""
        data = json.loads(EVALS_JSON.read_text(encoding="utf-8"))
        ev7 = next(e for e in data["evals"] if e["id"] == 7)
        fixture = SKILL_DIR / ev7["files"][0]
        before = _run_cli("check", "--file", str(fixture))
        self.assertNotEqual(before.returncode, 0, before.stdout + before.stderr)
        self.assertIn("空行切断", before.stdout + before.stderr)

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            target.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
            _run_cli("standardize", "--file", str(target), "--apply-safe-fixes", "--fix-only")
            after = _run_cli("check", "--file", str(target))
            self.assertEqual(after.returncode, 0, after.stdout + after.stderr)
            text = target.read_text(encoding="utf-8")
            bug_block = text.split("## 调整事项")[0]
            self.assertNotRegex(bug_block, r"\| BUG-001 .*\n\n\| BUG-002")

    def test_eval8_fixture_check_fails_on_html_and_backticks(self):
        """eval 8's fixture must fail check for raw <title> and unpaired backticks."""
        data = json.loads(EVALS_JSON.read_text(encoding="utf-8"))
        ev8 = next(e for e in data["evals"] if e["id"] == 8)
        fixture = SKILL_DIR / ev8["files"][0]
        result = _run_cli("check", "--file", str(fixture))
        combined = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, combined)
        self.assertIn("裸 HTML", combined)
        self.assertIn("<title>", combined)
        self.assertIn("反引号未闭合", combined)




# REQ-09: benchmark evidence must come from real agent runs. These mechanical rules
# reject the failure modes found in the deleted V0.2 benchmark (CHK-012): placeholder
# model names / skill paths, all-zero tokens & tool_calls, and a declared
# runs_per_configuration that does not match the actual run records.
BENCHMARK_PLACEHOLDER_STRINGS = ("<model-name>", "<path-to-skill>", "<insert", "TODO:", "TBD")


def benchmark_guard_violations(data: dict, runs_root: Path | None = None) -> list[str]:
    """Mechanical REQ-09 rules for a benchmark summary JSON. Tolerant to shape.

    `runs_root` optionally cross-checks the declared count against on-disk run
    directories; synthetic-payload unit tests pass None so the live (possibly
    mid-run) workspace cannot contaminate them.
    """
    violations: list[str] = []
    text = json.dumps(data, ensure_ascii=False)
    for placeholder in BENCHMARK_PLACEHOLDER_STRINGS:
        if placeholder in text:
            violations.append(f"placeholder string present: {placeholder}")

    runs = data.get("runs")
    if runs is None:
        runs = [r for c in data.get("configurations", []) for r in c.get("runs", [])]
    for index, record in enumerate(runs):
        tokens = record.get("tokens")
        calls = record.get("tool_calls")
        if tokens in (0, None) and calls in (0, None):
            violations.append(f"run record {index}: tokens and tool_calls are both zero")

    declared = data.get("runs_per_configuration")
    if declared is not None:
        configurations = data.get("configurations")
        if configurations:
            for config in configurations:
                actual = len(config.get("runs", []))
                if actual != declared:
                    violations.append(
                        f"configuration {config.get('name', '?')}: declared "
                        f"{declared} runs but {actual} present"
                    )
        # Cross-check against the on-disk run workspace when it exists (it is
        # gitignored, so this fires only on a machine that actually ran the evals).
        if runs_root is not None and runs_root.is_dir():
            for config_dir in runs_root.iterdir():
                if config_dir.is_dir():
                    actual = len([p for p in config_dir.iterdir() if p.is_dir()])
                    if actual != declared:
                        violations.append(
                            f"workspace {config_dir.name}: declared {declared} runs "
                            f"but {actual} directories present"
                        )
    return violations


class BenchmarkGuardTest(unittest.TestCase):
    BENCHMARK_JSON = SKILL_DIR / "evals" / "benchmark.json"

    def test_guard_catches_placeholder_strings(self):
        bad = {
            "runs_per_configuration": 3,
            "configurations": [
                {"name": "with_skill", "runs": [{"model": "<model-name>", "tokens": 100, "tool_calls": 4}] * 3}
            ],
        }
        self.assertTrue(benchmark_guard_violations(bad, runs_root=None))

    def test_guard_catches_all_zero_metrics(self):
        bad = {
            "runs_per_configuration": 3,
            "configurations": [
                {"name": "with_skill", "runs": [{"model": "glm-5.2", "tokens": 0, "tool_calls": 0}] * 3}
            ],
        }
        violations = benchmark_guard_violations(bad, runs_root=None)
        self.assertTrue(any("both zero" in v for v in violations))

    def test_guard_catches_declared_vs_actual_run_count(self):
        bad = {
            "runs_per_configuration": 3,
            "configurations": [
                {"name": "with_skill", "runs": [{"model": "glm-5.2", "tokens": 10, "tool_calls": 1}]}
            ],
        }
        violations = benchmark_guard_violations(bad, runs_root=None)
        self.assertTrue(any("declared" in v for v in violations))

    def test_guard_catches_empty_runs_list(self):
        # BUG-077: an empty runs list is a violation, not "no records to check" —
        # otherwise a placeholder benchmark declaring 3 runs per config slips through
        # both the count check and the all-zero-metrics loop.
        bad = {
            "runs_per_configuration": 3,
            "configurations": [{"name": "with_skill", "runs": []}],
        }
        violations = benchmark_guard_violations(bad, runs_root=None)
        self.assertTrue(any("declared" in v for v in violations))

    def test_guard_accepts_a_clean_benchmark(self):
        good = {
            "runs_per_configuration": 3,
            "configurations": [
                {
                    "name": name,
                    "runs": [
                        {"model": "glm-5.2", "tokens": 100 + i, "tool_calls": 4 + i}
                        for i in range(3)
                    ],
                }
                for name in ("with_skill", "baseline")
            ],
        }
        self.assertEqual(benchmark_guard_violations(good, runs_root=None), [])

    def test_real_benchmark_file_if_present_passes_guard(self):
        """If evals/benchmark.json exists it must satisfy the REQ-09 mechanical rules.

        Until real agent runs are conducted the file stays absent (D1) — vacuous pass.
        The moment someone commits one, these rules bind.
        """
        if not self.BENCHMARK_JSON.exists():
            self.skipTest("benchmark.json not produced yet (real agent runs pending)")
        data = json.loads(self.BENCHMARK_JSON.read_text(encoding="utf-8"))
        self.assertEqual(benchmark_guard_violations(data), [])


class TriggerEvalsMetaTest(unittest.TestCase):
    TRIGGER_EVALS_JSON = SKILL_DIR / "evals" / "trigger-evals.json"
    KINDS = {"should_trigger", "implicit_trigger", "should_not_trigger", "behavior"}

    def test_trigger_evals_schema_and_coverage(self):
        data = json.loads(self.TRIGGER_EVALS_JSON.read_text(encoding="utf-8"))
        self.assertEqual(data["skill_name"], "task-list-initialization")
        evals = data["evals"]
        ids = [e["id"] for e in evals]
        self.assertEqual(len(ids), len(set(ids)), "trigger eval ids must be unique")
        kinds = {e["kind"] for e in evals}
        self.assertEqual(kinds, self.KINDS, "all four matrix categories must be covered")
        for ev in evals:
            self.assertIn(ev["kind"], self.KINDS)
            self.assertTrue(ev.get("prompt"))
            self.assertTrue(ev.get("expect"))
            for rel in ev.get("files", []):
                self.assertTrue(
                    (SKILL_DIR / rel).exists(),
                    f"trigger eval {ev['id']} references missing fixture {rel}",
                )

    def test_trigger_evals_have_no_placeholder_strings(self):
        text = self.TRIGGER_EVALS_JSON.read_text(encoding="utf-8")
        for placeholder in BENCHMARK_PLACEHOLDER_STRINGS:
            self.assertNotIn(placeholder, text)


class EvalsPlaceholderTest(unittest.TestCase):
    def test_evals_json_has_no_placeholder_strings(self):
        """REQ-10 / D1: committed eval metadata must not carry template leftovers."""
        text = EVALS_JSON.read_text(encoding="utf-8")
        for placeholder in BENCHMARK_PLACEHOLDER_STRINGS:
            self.assertNotIn(placeholder, text)


if __name__ == "__main__":
    unittest.main()
