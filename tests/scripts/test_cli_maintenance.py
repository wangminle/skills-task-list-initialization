"""CLI regression tests (split from the former monolithic file)."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import CliTestCase, load_cli_module  # noqa: E402


def _find_bash() -> str:
    """Locate a real bash executable.

    On Windows, ``C:\\Windows\\System32\\bash.exe`` is the WSL launcher stub —
    when WSL is not installed it exits non-zero and prints an install banner,
    which masks what the hook actually does. Skip the system directories and
    use the first real bash on PATH (e.g. Git Bash); POSIX keeps plain "bash".
    """
    if os.name != "nt":
        return "bash"
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        low = entry.lower()
        if "system32" in low or "syswow64" in low:
            continue
        candidate = Path(entry) / "bash.exe"
        if candidate.is_file():
            return str(candidate)
    return "bash"


@contextlib.contextmanager
def _bash_visible_on_path():
    """Temporarily prepend a PATH dir containing a dummy `bash` (BUG-093).

    The installer probes ``shutil.which("bash")`` but never executes it during
    install, so a no-op shim keeps the install-path tests green on machines
    without a real bash (plain Windows). Hook EXECUTION tests still resolve a
    real bash via ``_find_bash()`` and must stay outside this context.
    """
    with tempfile.TemporaryDirectory() as shim_tmp:
        shim_dir = Path(shim_tmp)
        if os.name == "nt":
            (shim_dir / "bash.bat").write_bytes(b"@echo off\r\n")
        else:
            shim = shim_dir / "bash"
            shim.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            shim.chmod(0o755)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{shim_dir}{os.pathsep}{old_path}"
        try:
            yield
        finally:
            os.environ["PATH"] = old_path


@contextlib.contextmanager
def _bash_missing_from_path():
    """Temporarily strip PATH so ``shutil.which("bash")`` finds nothing.

    The CLI subprocess is launched via an absolute interpreter path and is
    stdlib-only, so an empty PATH exercises a genuine "no bash anywhere"
    install attempt on every platform.
    """
    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = ""
    try:
        yield
    finally:
        os.environ["PATH"] = old_path


class CliMaintenanceTest(CliTestCase):
    def test_maintenance_flags_claimed_hook_without_actual(self):
        # Docs claim Stop hook / settings.json guarantee, but neither exists → inconsistency.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            (Path(tmp) / "CLAUDE.md").write_text(
                "## 会话结束任务同步（必须）\n\n"
                "该时机由 `.claude/settings.json` 的 Stop hook 保证触发（每会话一次）。\n",
                encoding="utf-8",
            )
            result = self.run_cli("standardize", "--file", str(target), "--format", "json")
            payload = json.loads(result.stdout)
            maint = payload["maintenance"]
            self.assertTrue(maint["rule_installed"])
            self.assertFalse(maint["hook_installed"])
            self.assertTrue(maint["hook_claimed"])
            self.assertTrue(maint["claim_mismatch"])
            md = self.run_cli("standardize", "--file", str(target))
            self.assertIn("声明与实际不一致", md.stdout)
            self.assertIn("Stop hook", md.stdout)

    def test_maintenance_no_mismatch_when_hook_matches_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            (Path(tmp) / "CLAUDE.md").write_text(
                "## 会话结束任务同步（必须）\n\n"
                "该时机由 `.claude/settings.json` 的 Stop hook 保证触发（每会话一次）。\n",
                encoding="utf-8",
            )
            (Path(tmp) / ".claude").mkdir()
            (Path(tmp) / ".claude" / "settings.json").write_text(
                json.dumps({
                    "hooks": {
                        "Stop": [
                            {"matcher": "", "hooks": [
                                {"type": "command", "command": "bash .claude/hooks/tasklist_sync_reminder.sh"}
                            ]}
                        ]
                    }
                }),
                encoding="utf-8",
            )
            result = self.run_cli("standardize", "--file", str(target), "--format", "json")
            maint = json.loads(result.stdout)["maintenance"]
            self.assertTrue(maint["hook_claimed"])
            self.assertTrue(maint["hook_installed"])
            self.assertFalse(maint["claim_mismatch"])

    def test_install_maintenance_rule_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            result = self.run_cli("install-maintenance", "--file", str(target))
            self.assertIn("CLAUDE.md", result.stdout)
            claude = (Path(tmp) / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("会话结束任务同步", claude)
            # second run is idempotent
            again = self.run_cli("install-maintenance", "--file", str(target))
            self.assertIn("已安装", again.stdout)
            self.assertEqual(claude.count("会话结束任务同步"), 1)

    def test_install_maintenance_refuses_invalid_settings_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            settings = Path(tmp) / ".claude" / "settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text("{not-json KEEPME", encoding="utf-8")
            with _bash_visible_on_path():
                result = self.run_cli(
                    "install-maintenance", "--file", str(target), "--with-hook", check=False,
                )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("JSON", result.stdout + result.stderr)
            self.assertEqual("{not-json KEEPME", settings.read_text(encoding="utf-8"))

    def test_install_maintenance_cross_file_idempotent(self):
        # Rule already in AGENTS.md must not be duplicated into CLAUDE.md.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            (Path(tmp) / "AGENTS.md").write_text(
                "## 会话结束任务同步\n\nalready here\n", encoding="utf-8"
            )
            (Path(tmp) / "CLAUDE.md").write_text("# project\n", encoding="utf-8")
            result = self.run_cli("install-maintenance", "--file", str(target))
            self.assertIn("AGENTS.md", result.stdout)
            self.assertNotIn("会话结束任务同步", (Path(tmp) / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_install_maintenance_hook_script_names_actual_agent_file(self):
        # The Stop-hook reminder must reference the file the rule actually lives in.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            (Path(tmp) / "AGENTS.md").write_text("# project\n", encoding="utf-8")
            with _bash_visible_on_path():
                self.run_cli("install-maintenance", "--file", str(target), "--with-hook")
            script = (Path(tmp) / ".claude" / "hooks" / "tasklist_sync_reminder.sh").read_text(
                encoding="utf-8"
            )
            self.assertIn("AGENTS.md", script)
            self.assertNotIn("CLAUDE.md 的", script)

    def test_install_maintenance_rejects_hooks_null_and_stop_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            settings = Path(tmp) / ".claude" / "settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text('{"hooks": {"Stop": {}}}\n', encoding="utf-8")
            with _bash_visible_on_path():
                result = self.run_cli(
                    "install-maintenance", "--file", str(target), "--with-hook", check=False,
                )
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stdout + result.stderr)
            self.assertFalse(
                (Path(tmp) / ".claude" / "hooks" / "tasklist_sync_reminder.sh").exists()
            )
            # hooks:null is normalized and install proceeds
            settings.write_text('{"hooks": null}\n', encoding="utf-8")
            with _bash_visible_on_path():
                ok = self.run_cli(
                    "install-maintenance", "--file", str(target), "--with-hook",
                )
            self.assertEqual(ok.returncode, 0)
            loaded = json.loads(settings.read_text(encoding="utf-8"))
            self.assertIsInstance(loaded["hooks"]["Stop"], list)

    def test_install_maintenance_hook_uses_claude_project_dir(self):
        # New installs must use CLAUDE_PROJECT_DIR so Stop hooks work when cwd ≠ repo root.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            with _bash_visible_on_path():
                self.run_cli("install-maintenance", "--file", str(target), "--with-hook")
            settings = json.loads(
                (Path(tmp) / ".claude" / "settings.json").read_text(encoding="utf-8")
            )
            cmd = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
            self.assertIn("CLAUDE_PROJECT_DIR", cmd)
            self.assertIn("tasklist_sync_reminder.sh", cmd)
            # Simulate hook cwd = subdirectory: relative path would fail; PROJECT_DIR form resolves.
            runtime = Path(tmp) / "runtime"
            runtime.mkdir()
            rel = subprocess.run(
                [_find_bash(), "-c", "bash .claude/hooks/tasklist_sync_reminder.sh"],
                cwd=runtime,
                input="{}",
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(rel.returncode, 0)
            abs_cmd = cmd.replace("${CLAUDE_PROJECT_DIR}", tmp)
            # Use a fresh random session_id per run. The hook gates on a per-session guard
            # file at /tmp/claude-tasklist-sync-<session_id>; a fixed value leaves that file
            # behind in the system-wide /tmp and makes every subsequent run silently exit 0
            # with no output, so the assertion below would flake.
            ok = subprocess.run(
                [_find_bash(), "-c", abs_cmd],
                cwd=runtime,
                input=json.dumps({"session_id": f"hook-cwd-test-{uuid.uuid4()}"}),
                text=True,
                capture_output=True,
            )
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn("decision", ok.stdout)

    def test_install_maintenance_upgrades_legacy_relative_hook(self):
        # Re-running --with-hook must rewrite legacy relative commands (not pure skip).
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            settings_path = Path(tmp) / ".claude" / "settings.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                json.dumps({
                    "hooks": {
                        "Stop": [
                            {
                                "matcher": "",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "bash .claude/hooks/tasklist_sync_reminder.sh",
                                    }
                                ],
                            }
                        ]
                    }
                }),
                encoding="utf-8",
            )
            with _bash_visible_on_path():
                result = self.run_cli(
                    "install-maintenance", "--file", str(target), "--with-hook",
                )
            self.assertEqual(result.returncode, 0)
            self.assertIn("已升级", result.stdout)
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            cmd = loaded["hooks"]["Stop"][0]["hooks"][0]["command"]
            self.assertIn("CLAUDE_PROJECT_DIR", cmd)
            self.assertNotEqual(cmd, "bash .claude/hooks/tasklist_sync_reminder.sh")
            # Second run is idempotent skip (already CLAUDE_PROJECT_DIR).
            with _bash_visible_on_path():
                again = self.run_cli(
                    "install-maintenance", "--file", str(target), "--with-hook",
                )
            self.assertIn("已安装（跳过）", again.stdout)
            self.assertNotIn("已升级", again.stdout)

    def test_install_maintenance_repairs_crlf_hook_script(self):
        # BUG-105: a hook script written on (or synced through) Windows carries CRLF
        # line endings — bash cannot parse "fi\r" and the Stop hook dies with
        # "syntax error: unexpected end of file". The old idempotency check compared
        # via read_text(), which normalizes CRLF to \n, so the corrupted script
        # compared EQUAL to the template: re-running the installer printed "skip"
        # and never repaired it. The comparison is now byte-exact and atomic_write
        # emits LF verbatim, so --with-hook is self-healing.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            with _bash_visible_on_path():
                self.run_cli("install-maintenance", "--file", str(target), "--with-hook")
            script_path = Path(tmp) / ".claude" / "hooks" / "tasklist_sync_reminder.sh"
            healthy = script_path.read_bytes()
            self.assertNotIn(b"\r", healthy)
            # Corrupt the copy the way a Windows-side write/sync would: CRLF endings.
            script_path.write_bytes(healthy.replace(b"\n", b"\r\n"))
            with _bash_visible_on_path():
                result = self.run_cli(
                    "install-maintenance", "--file", str(target), "--with-hook",
                    check=False,
                )
            self.assertEqual(result.returncode, 0)
            self.assertIn("已重写", result.stdout)
            self.assertEqual(script_path.read_bytes(), healthy)

    def test_install_maintenance_with_hook_refuses_without_bash(self):
        # BUG-093: on bash-less machines (plain Windows) the old installer wrote a
        # `bash ...` hook "successfully" that then failed on every Stop event. The
        # installer must refuse up front and leave the project byte-identical.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            agent = Path(tmp) / "CLAUDE.md"
            agent.write_text("# project\n", encoding="utf-8")
            with _bash_missing_from_path():
                result = self.run_cli(
                    "install-maintenance", "--file", str(target), "--with-hook",
                    check=False,
                )
                dry = self.run_cli(
                    "install-maintenance", "--file", str(target), "--with-hook",
                    "--dry-run", check=False,
                )
            self.assertEqual(result.returncode, 1)
            self.assertEqual(dry.returncode, 1)
            combined = result.stdout + result.stderr + dry.stdout + dry.stderr
            self.assertIn("bash", combined)
            self.assertIn("--with-hook", combined)
            # Nothing was written: agent file unchanged, no hook artifacts at all.
            self.assertEqual(agent.read_text(encoding="utf-8"), "# project\n")
            self.assertFalse((Path(tmp) / ".claude").exists())

    def test_install_maintenance_hook_installs_when_bash_on_path(self):
        # Positive counterpart: with bash visible on PATH the hook installs
        # normally — independent of whether the host itself provides bash.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            with _bash_visible_on_path():
                result = self.run_cli(
                    "install-maintenance", "--file", str(target), "--with-hook",
                )
            self.assertEqual(result.returncode, 0)
            settings = json.loads(
                (Path(tmp) / ".claude" / "settings.json").read_text(encoding="utf-8")
            )
            cmd = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
            self.assertIn("tasklist_sync_reminder.sh", cmd)
            self.assertIn("CLAUDE_PROJECT_DIR", cmd)

    def test_detect_codex_hook_broken_path(self):
        """Codex hook with non-existent script path should be flagged as broken."""
        mod = load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            codex_dir = Path(tmp) / ".codex"
            codex_dir.mkdir()
            (codex_dir / "hooks.json").write_text(json.dumps({
                "hooks": {
                    "Stop": [{
                        "hooks": [{
                            "type": "command",
                            "command": "bash '/nonexistent/path/tasklist_sync_reminder.sh'"
                        }]
                    }]
                }
            }), encoding="utf-8")
            status = mod.detect_maintenance_rule(Path(tmp))
            self.assertTrue(status.get("codex_hook_installed"))
            self.assertIsNotNone(status.get("codex_hook_broken"))

    def test_detect_codex_hook_valid_path(self):
        """Codex hook with existing script path should not be flagged as broken."""
        mod = load_cli_module()
        with tempfile.TemporaryDirectory() as tmp:
            codex_dir = Path(tmp) / ".codex"
            codex_dir.mkdir()
            hooks_dir = codex_dir / "hooks"
            hooks_dir.mkdir()
            script = hooks_dir / "tasklist_sync_reminder.sh"
            script.write_text("#!/bin/bash\n", encoding="utf-8")
            (codex_dir / "hooks.json").write_text(json.dumps({
                "hooks": {
                    "Stop": [{
                        "hooks": [{
                            "type": "command",
                            "command": f"bash '{script}'"
                        }]
                    }]
                }
            }), encoding="utf-8")
            status = mod.detect_maintenance_rule(Path(tmp))
            self.assertTrue(status.get("codex_hook_installed"))
            self.assertIsNone(status.get("codex_hook_broken"))

    def test_maintenance_codex_claim_not_satisfied_by_claude_hook(self):
        # BUG-048: AGENTS.md Codex guarantee must not be waived because Claude hook exists.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            (Path(tmp) / "CLAUDE.md").write_text(
                "## 会话结束任务同步（必须）\n\n"
                "若已配置 `.claude/settings.json` 的 Stop hook，则由该 hook 保证；"
                "**未配置时由 agent 自觉执行**。\n",
                encoding="utf-8",
            )
            (Path(tmp) / "AGENTS.md").write_text(
                "## 会话结束任务同步（必须）\n\n"
                "该时机由 `.Codex/settings.json` 的 Stop hook 保证触发（每会话一次）。\n",
                encoding="utf-8",
            )
            claude_dir = Path(tmp) / ".claude"
            claude_dir.mkdir()
            (claude_dir / "settings.json").write_text(
                json.dumps({
                    "hooks": {
                        "Stop": [{
                            "matcher": "",
                            "hooks": [{
                                "type": "command",
                                "command": 'bash "${CLAUDE_PROJECT_DIR}/.claude/hooks/tasklist_sync_reminder.sh"',
                            }],
                        }]
                    }
                }),
                encoding="utf-8",
            )
            (claude_dir / "hooks").mkdir()
            (claude_dir / "hooks" / "tasklist_sync_reminder.sh").write_text("#!/bin/bash\n", encoding="utf-8")
            result = self.run_cli("standardize", "--file", str(target), "--format", "json")
            maint = json.loads(result.stdout)["maintenance"]
            self.assertTrue(maint["hook_installed"])
            self.assertFalse(maint["codex_hook_installed"])
            self.assertTrue(maint["claim_mismatch"])

    def test_maintenance_flags_rule_duplicated_in_both_agent_files(self):
        # BUG-049: canonical install writes one file; both containing the marker is a warning.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            rule = "## 会话结束任务同步（必须）\n\n规则正文略。\n"
            (Path(tmp) / "CLAUDE.md").write_text(rule, encoding="utf-8")
            (Path(tmp) / "AGENTS.md").write_text(rule, encoding="utf-8")
            result = self.run_cli("standardize", "--file", str(target))
            self.assertIn("规则双写", result.stdout)

    def test_maintenance_flags_absolute_hook_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            (Path(tmp) / "CLAUDE.md").write_text(
                "## 会话结束任务同步\n\n规则。\n", encoding="utf-8"
            )
            claude_dir = Path(tmp) / ".claude"
            hooks = claude_dir / "hooks"
            hooks.mkdir(parents=True)
            script = hooks / "tasklist_sync_reminder.sh"
            script.write_text("#!/bin/bash\n", encoding="utf-8")
            (claude_dir / "settings.json").write_text(
                json.dumps({
                    "hooks": {
                        "Stop": [{
                            "matcher": "",
                            "hooks": [{
                                "type": "command",
                                "command": f"bash {script}",
                            }],
                        }]
                    }
                }),
                encoding="utf-8",
            )
            result = self.run_cli("standardize", "--file", str(target), "--format", "json")
            maint = json.loads(result.stdout)["maintenance"]
            self.assertTrue(maint["hook_installed"])
            self.assertTrue(maint["hook_nonportable"])
            md = self.run_cli("standardize", "--file", str(target))
            self.assertIn("CLAUDE_PROJECT_DIR", md.stdout)

    def test_maintenance_flags_claude_dir_gitignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            (Path(tmp) / "CLAUDE.md").write_text(
                "## 会话结束任务同步\n\n规则。\n", encoding="utf-8"
            )
            claude_dir = Path(tmp) / ".claude"
            hooks = claude_dir / "hooks"
            hooks.mkdir(parents=True)
            (hooks / "tasklist_sync_reminder.sh").write_text("#!/bin/bash\n", encoding="utf-8")
            (claude_dir / "settings.json").write_text(
                json.dumps({
                    "hooks": {
                        "Stop": [{
                            "matcher": "",
                            "hooks": [{
                                "type": "command",
                                "command": 'bash "${CLAUDE_PROJECT_DIR}/.claude/hooks/tasklist_sync_reminder.sh"',
                            }],
                        }]
                    }
                }),
                encoding="utf-8",
            )
            (Path(tmp) / ".gitignore").write_text(".claude/\n", encoding="utf-8")
            result = self.run_cli("standardize", "--file", str(target), "--format", "json")
            maint = json.loads(result.stdout)["maintenance"]
            self.assertTrue(maint["claude_gitignored"])
            md = self.run_cli("standardize", "--file", str(target))
            self.assertIn(".gitignore", md.stdout)

    def test_maintenance_does_not_flag_settings_local_gitignore(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "task-list.md"
            self.run_cli("init", "--output", str(target))
            (Path(tmp) / "CLAUDE.md").write_text(
                "## 会话结束任务同步\n\n规则。\n", encoding="utf-8"
            )
            (Path(tmp) / ".gitignore").write_text(
                ".claude/settings.local.json\n", encoding="utf-8"
            )
            result = self.run_cli("standardize", "--file", str(target), "--format", "json")
            maint = json.loads(result.stdout)["maintenance"]
            self.assertFalse(maint["claude_gitignored"])
