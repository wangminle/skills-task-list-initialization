"""Agent maintenance-rule text, Stop-hook install, and detection."""
from __future__ import annotations

import json
import re
from pathlib import Path
from .locales import (
    MAINTENANCE_RULE_MARKER,
    MAINTENANCE_RULE_MARKER_EN,
    T,
    TASKLIST_HOOK_MARKER,
    Locale,
)

def text_claims_stop_hook(text: str) -> bool:
    """True when agent docs claim a Stop-hook / settings.json guarantee layer exists.

    Only an UNCONDITIONAL claim counts as a mismatch risk — e.g. "a Stop hook guarantees the
    sync runs". The official maintenance-rule template is conditional: it says the hook
    guarantees the trigger *when configured*, AND explicitly provides the no-hook fallback
    ("未配置时由 agent 自觉执行" / "without a hook, the agent runs the sync on its own"). That
    conditional wording must NOT be flagged, because installing the rule without --with-hook is
    a documented, valid state. BUG-036: the old test matched "stop hook" + "保证/guarantee"
    keywords anywhere and could not tell the two apart, so the official rule (installed without
    a hook) falsely reported a claim mismatch.
    """
    # Strip markdown noise so `Stop` hook / `.claude/settings.json` still match.
    flat = re.sub(r"[`*_]", "", text)
    lower = flat.lower()
    mentions_hook = bool(re.search(r"stop\s*hook", lower)) or (
        "settings.json" in lower and "hook" in lower
    )
    if not mentions_hook:
        return False
    guarantees = ("保证" in flat) or bool(re.search(r"guarante|ensur", lower))
    if not guarantees:
        return False
    # Conditional/fallback wording present → the doc is NOT making an unconditional claim, so
    # a missing hook is expected and not a mismatch. Detect both the zh and en fallback phrases
    # used by the official template, plus generic "when/if configured" conditionals.
    has_fallback = (
        ("未配置时" in flat and "自觉" in flat)
        or ("without a hook" in lower)
        or ("when no hook" in lower)
        or ("no hook is" in lower)
    )
    if has_fallback:
        return False
    return True

def _hook_claim_kind(text: str) -> str | None:
    """Which tool an agent file claims a Stop-hook guarantee for: claude, codex, or any."""
    if not text_claims_stop_hook(text):
        return None
    flat = re.sub(r"[`*_]", "", text)
    lower = flat.lower()
    if ".codex" in lower or re.search(r"\bcodex\b", lower):
        return "codex"
    if ".claude" in lower:
        return "claude"
    return "any"

def _gitignore_ignores_claude_dir(project_root: Path) -> bool:
    """True when .gitignore ignores the whole .claude/ directory (hooks would not clone)."""
    gitignore = project_root / ".gitignore"
    if not gitignore.is_file():
        return False
    try:
        raw = gitignore.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in raw.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped or stripped.startswith("!"):
            continue
        normalized = stripped.lstrip("/")
        if normalized in {".claude", ".claude/", "**/.claude", "**/.claude/"}:
            return True
        if normalized.startswith(".claude/"):
            rest = normalized[len(".claude/") :]
            if rest in {"", "*", "**", "**/"} or rest.endswith("/") or "*" in rest:
                return True
    return False

MAINTENANCE_RULE_ZH = """## 会话结束任务同步（必须）

每次会话结束前，若本次涉及任务完成——包括但不限于 bug 修复、功能开发、代码审查、测试数据准备、文档更新、配置运维——必须：

1. 把新增条目与状态变更写入根目录 `task-list.md`，与实际进度同步；
2. 在本次最后一条回复中告知用户：记录/更新了哪些条目（ID + 简述）。
3. 写入后跑 `check`。`check` 是预览门禁：表内空行、单元格裸 HTML、未按 CommonMark 闭合的反引号必须失败；围栏代码里的示例表格不算真实表；手改 md 后也必须再跑。

若本次未涉及任何任务完成，无需操作也无需提示。若已配置 `.claude/settings.json` 的 `Stop` hook，则由该 hook 保证每会话触发一次；**未配置时由 agent 在会话结束前自觉执行**（不要在未安装 hook 时写「由 Stop hook 保证触发」）。
"""

MAINTENANCE_RULE_EN = """## Session-end Task Sync (Required)

Before each session ends, if this session involved completing work — including but not limited to bug fixes, feature development, code review, test-data preparation, documentation updates, or operations — you must:

1. Sync new entries and status changes into the root `task-list.md`, keeping it in step with actual progress;
2. Tell the user in your final reply which entries you recorded/updated (ID + short note).
3. Run `check` after writing. `check` is the preview gate: intra-table blank lines, raw HTML in cells, and unclosed CommonMark code spans must fail; fenced table examples are not real tables; re-run `check` after any hand edit.

If this session completed no work, do nothing and say nothing. If a `Stop` hook is configured in `.claude/settings.json`, that hook guarantees one trigger per session; **without a hook, the agent must run this sync on its own before ending** (do not claim a Stop-hook guarantee when none is installed).
"""

HOOK_SCRIPT_ZH = """#!/usr/bin/env bash
# 若 python3 不可用（如 Windows 微软商店桩，exit 非零且无输出），回退到 python。
if python3 -c 'import sys' >/dev/null 2>&1; then PY=python3; else PY=python; fi
input="$(cat)"
session_id="$(printf '%s' "$input" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("session_id") or "default")' 2>/dev/null || echo default)"
guard="/tmp/claude-tasklist-sync-${session_id}"
[ -f "$guard" ] && exit 0
touch "$guard"
"$PY" -c 'import json; print(json.dumps({"decision":"block","reason":"会话结束前请按 CLAUDE.md 的「会话结束任务同步」规则：若本次涉及任务完成，把新增条目与状态变更写入根目录 task-list.md 并在回复中告知用户；否则简短说明无需同步。本提醒每会话仅触发一次。"}, ensure_ascii=False))'
"""

HOOK_SCRIPT_EN = """#!/usr/bin/env bash
# Fall back to python when python3 is unusable (e.g. the Windows Store stub: non-zero exit, no output).
if python3 -c 'import sys' >/dev/null 2>&1; then PY=python3; else PY=python; fi
input="$(cat)"
session_id="$(printf '%s' "$input" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("session_id") or "default")' 2>/dev/null || echo default)"
guard="/tmp/claude-tasklist-sync-${session_id}"
[ -f "$guard" ] && exit 0
touch "$guard"
"$PY" -c 'import json; print(json.dumps({"decision":"block","reason":"Before this session ends, follow the Session-end Task Sync rule in CLAUDE.md: if this session completed work, sync new entries and status changes into the root task-list.md and tell the user in your reply; otherwise briefly state there is nothing to sync. This reminder fires once per session."}))'
"""

TASKLIST_HOOK_COMMAND = (
    'bash "${CLAUDE_PROJECT_DIR}/.claude/hooks/tasklist_sync_reminder.sh"'
)

def _load_settings_for_hooks(settings_path: Path, m: dict[str, str]) -> dict:
    """Parse settings.json and ensure hooks.Stop is a writable list; abort on bad shape."""
    settings: dict = {"hooks": {"Stop": []}}
    if settings_path.exists():
        try:
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(m["settings_bad_json"].format(settings_path, exc)) from exc
        if not isinstance(loaded, dict):
            raise SystemExit(m["settings_bad_shape"].format(settings_path, "root must be a JSON object"))
        settings = loaded
    hooks = settings.get("hooks", {"Stop": []})
    if hooks is None:
        hooks = {"Stop": []}
        settings["hooks"] = hooks
    elif not isinstance(hooks, dict):
        raise SystemExit(
            m["settings_bad_shape"].format(settings_path, '"hooks" must be a JSON object or null')
        )
    stop_list = hooks.get("Stop", [])
    if stop_list is None:
        stop_list = []
        hooks["Stop"] = stop_list
    elif not isinstance(stop_list, list):
        raise SystemExit(
            m["settings_bad_shape"].format(settings_path, '"hooks.Stop" must be a JSON array or null')
        )
    return settings

def _upgrade_tasklist_hook_commands(stop_list: list) -> bool:
    """Rewrite legacy relative-path tasklist hooks to CLAUDE_PROJECT_DIR form."""
    changed = False
    for item in stop_list:
        if not isinstance(item, dict):
            continue
        for hook in item.get("hooks", []) or []:
            if not isinstance(hook, dict):
                continue
            cmd = str(hook.get("command", ""))
            if TASKLIST_HOOK_MARKER not in cmd:
                continue
            if "${CLAUDE_PROJECT_DIR}" not in cmd:
                hook["command"] = TASKLIST_HOOK_COMMAND
                changed = True
    return changed

def _extract_hook_script_path(command: str) -> str | None:
    """Extract the script path from a hook command like bash 'path' or bash "path"."""
    # Match quoted paths containing tasklist_sync_reminder.sh
    match = re.search(r"""['"]([^'"]*tasklist[^'"]*)['"]""", command)
    if match:
        return match.group(1)
    # Unquoted: take everything after bash
    match = re.match(r"\s*bash\s+(.+)", command.strip())
    if match:
        return match.group(1).strip()
    return None

def _detect_hook_in_json(data: dict, project_root: Path) -> tuple[bool, str | None, bool]:
    """Check for a tasklist Stop hook in a parsed JSON hooks config.

    Returns (found, broken_path, nonportable). broken_path is set when the command
    references a script path that does not exist. nonportable is True when the command
    does not use ${CLAUDE_PROJECT_DIR}.
    """
    found = False
    broken_path = None
    nonportable = False
    for entry in data.get("hooks", {}).get("Stop", []):
        if not isinstance(entry, dict):
            continue
        for hook in entry.get("hooks", []) or []:
            if not isinstance(hook, dict):
                continue
            cmd = str(hook.get("command", ""))
            if TASKLIST_HOOK_MARKER not in cmd:
                continue
            found = True
            if "CLAUDE_PROJECT_DIR" not in cmd:
                nonportable = True
            script_path = _extract_hook_script_path(cmd)
            if script_path:
                resolved = script_path.replace("${CLAUDE_PROJECT_DIR}", str(project_root))
                resolved = resolved.replace("$CLAUDE_PROJECT_DIR", str(project_root))
                if not Path(resolved).exists():
                    broken_path = script_path
            break
        if found:
            break
    return found, broken_path, nonportable

def detect_maintenance_rule(project_root: Path) -> dict[str, object]:
    """Detect whether the session-end task-list sync rule and Stop hooks are installed.

    Read-only: scans the project root for the canonical rule heading in CLAUDE.md /
    AGENTS.md, a tasklist Stop hook in .claude/settings.json (Claude Code), and
    .codex/hooks.json (Codex). Also validates that hook commands point to scripts
    that actually exist. Flags claim-vs-actual mismatches: docs that assert a
    Stop-hook guarantee while no matching hook exists.
    """
    # Scan BOTH agent files rather than stopping at the first one that exists.
    candidates = ("CLAUDE.md", "AGENTS.md")
    existing = [name for name in candidates if (project_root / name).exists()]
    containing: list[str] = []
    agent_texts: list[str] = []
    for name in existing:
        try:
            text = (project_root / name).read_text(encoding="utf-8")
            agent_texts.append(text)
            if MAINTENANCE_RULE_MARKER in text or MAINTENANCE_RULE_MARKER_EN in text:
                containing.append(name)
        except OSError:
            continue

    if containing:
        agent_file = "CLAUDE.md" if "CLAUDE.md" in containing else containing[0]
        rule_installed = True
    elif existing:
        agent_file = "CLAUDE.md" if "CLAUDE.md" in existing else existing[0]
        rule_installed = False
    else:
        agent_file = None
        rule_installed = False

    # Claude Code hook: .claude/settings.json
    hook_installed = False
    claude_hook_broken: str | None = None
    hook_nonportable = False
    settings_path = project_root / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            hook_installed, claude_hook_broken, hook_nonportable = _detect_hook_in_json(
                data, project_root
            )
        except (json.JSONDecodeError, OSError, AttributeError):
            hook_installed = False

    # Codex hook: .codex/hooks.json
    codex_hook_installed = False
    codex_hook_broken: str | None = None
    codex_path = project_root / ".codex" / "hooks.json"
    if codex_path.exists():
        try:
            data = json.loads(codex_path.read_text(encoding="utf-8"))
            codex_hook_installed, codex_hook_broken, _ = _detect_hook_in_json(
                data, project_root
            )
        except (json.JSONDecodeError, OSError, AttributeError):
            codex_hook_installed = False

    hook_claimed = False
    claim_mismatch = False
    for text in agent_texts:
        kind = _hook_claim_kind(text)
        if kind is None:
            continue
        hook_claimed = True
        if kind == "claude" and not hook_installed:
            claim_mismatch = True
        elif kind == "codex" and not codex_hook_installed:
            claim_mismatch = True
        elif kind == "any" and not (hook_installed or codex_hook_installed):
            claim_mismatch = True

    return {
        "agent_file": agent_file,
        "rule_installed": rule_installed,
        "rule_duplicated": len(containing) > 1,
        "hook_installed": hook_installed,
        "hook_nonportable": hook_nonportable,
        "claude_gitignored": _gitignore_ignores_claude_dir(project_root),
        "claude_hook_broken": claude_hook_broken,
        "codex_hook_installed": codex_hook_installed,
        "codex_hook_broken": codex_hook_broken,
        "hook_claimed": hook_claimed,
        "claim_mismatch": claim_mismatch,
    }

def render_maintenance_lines(status: dict[str, object], locale: Locale) -> list[str]:
    """Render the maintenance-rule detection result as report bullets.

    Detection is read-only and advisory: standardize never installs the rule itself.
    """
    m = T[locale.name]
    sep = "：" if locale.name == "zh" else ": "
    agent_file = status.get("agent_file")
    rule = bool(status.get("rule_installed"))
    hook = bool(status.get("hook_installed"))
    claude_broken = status.get("claude_hook_broken")
    codex_hook = bool(status.get("codex_hook_installed"))
    codex_broken = status.get("codex_hook_broken")
    claim_mismatch = bool(status.get("claim_mismatch"))
    lines = [
        f"- {m['agent_file']}{sep}{agent_file or m['agent_file_none']}",
        f"- {m['rule_label']}{sep}{m['installed'] if rule else m['not_detected']}",
        f"- {m['hook_label']}{sep}{m['installed'] if hook else m['hook_optional']}",
        f"- {m['codex_hook_label']}{sep}{m['installed'] if codex_hook else m['hook_optional']}",
    ]
    if claude_broken:
        lines.append(f"- ⚠️ Claude hook: {m['codex_hook_broken'].format(claude_broken)}")
    if codex_broken:
        lines.append(f"- ⚠️ {m['codex_hook_label']}: {m['codex_hook_broken'].format(codex_broken)}")
    if claim_mismatch:
        lines.append(m["rec_claim_mismatch"])
    if status.get("rule_duplicated"):
        lines.append(m["rec_rule_duplicated"])
    if status.get("hook_nonportable"):
        lines.append(m["rec_hook_nonportable"])
    if status.get("claude_gitignored"):
        lines.append(m["rec_claude_gitignored"])
    if not rule:
        lines.append(m["rec_install_rule"])
    elif not hook and not codex_hook:
        lines.append(m["rec_install_hook"])
    return lines


HOOK_SCRIPT_NAME = "tasklist_sync_reminder.sh"


def rule_text(lang: str) -> str:
    """Canonical session-end sync rule body (zh/en)."""
    return MAINTENANCE_RULE_ZH if lang == "zh" else MAINTENANCE_RULE_EN


def hook_script(lang: str) -> str:
    """Canonical Stop-hook reminder script (zh/en)."""
    return HOOK_SCRIPT_ZH if lang == "zh" else HOOK_SCRIPT_EN

