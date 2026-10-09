"""Fleet inspection: scan a root directory for every task-list.md and audit each one.

The single-file commands (check / standardize) leave fleet health to "someone remembers
to run it" — batch audits were hand-rolled shell loops. `fleet` makes the sweep a first
class command: point it at a node directory, it finds every task-list.md below it,
runs the same check + standardize diagnostics per file, optionally applies the safe
fix pipeline (under the per-file write lock), and aggregates a pass/fail summary with
a non-zero exit code when anything fails — so the audit can be scheduled or scripted.
"""
from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path

from .locales import T, Locale
from .renderer import add_missing_sections, collapse_intra_table_blank_lines, escape_cell, escape_unescaped_pipes
from .repository import LockTimeout, atomic_write, file_lock
from .schemas import detect_locale, get_locale, local_minute_now
from .validator import (
    analyze_standardization,
    completed_missing_time_issues,
    prefix_mismatches,
    time_reversal_issues,
)
from .parser import collect_records, section_headers_by_title

# Directory names never descended into during a fleet scan: VCS metadata, dependency
# trees, and Syncthing version backups (a .stversions copy is a backup snapshot, not a
# live ledger). Project-specific exclusions (eval outputs, runtime mirrors, frozen
# archives) go through --exclude globs.
DEFAULT_EXCLUDES = (".git", ".hg", ".svn", "node_modules", ".stversions")

_LEDGER_NAME = "task-list.md"

_MAINT_LABELS = {
    "zh": {
        "rule_missing": "缺规则",
        "hook_missing": "缺hook",
        "rule_duplicated": "规则双装",
        "hook_nonportable": "hook不可移植",
        "claude_gitignored": ".claude被忽略",
        "claim_mismatch": "声明不符",
        "hook_broken": "hook失效",
    },
    "en": {
        "rule_missing": "rule-missing",
        "hook_missing": "hook-missing",
        "rule_duplicated": "rule-duplicated",
        "hook_nonportable": "hook-nonportable",
        "claude_gitignored": ".claude-gitignored",
        "claim_mismatch": "claim-mismatch",
        "hook_broken": "hook-broken",
    },
}


def _matches_exclude(root: Path, path: Path, patterns: list[str]) -> bool:
    """fnmatch against the root-relative POSIX path, its parents, and the bare name.

    fnmatch's `*` crosses path separators. A leading-anchored pattern like
    `evals/workspace/runs` (also tried as `evals/workspace/runs/*`) excludes
    only that exact root-relative subtree; use `*/evals/workspace/runs` to
    exclude it wherever it nests, or a bare name like `examples` to match any
    directory so named.
    """
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.as_posix()
    for pattern in patterns:
        p = pattern.strip().rstrip("/")
        if not p:
            continue
        if fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(rel, p + "/*"):
            return True
        if fnmatch.fnmatch(path.name, p):
            return True
    return False


def find_task_lists(
    root: Path, excludes: list[str] | None = None, *, scan_errors: list[str] | None = None
) -> list[Path]:
    """Every task-list.md under *root*, with default and user exclusions applied.

    ``scan_errors``, when given, collects one message per directory os.walk could not
    read (BUG-098): the default ``onerror=None`` swallows PermissionError and friends,
    so a mis-permissioned cron/CI root silently reported "no files found" with exit 0
    as if the sweep had covered everything.
    """

    def _on_scan_error(err: OSError) -> None:
        if scan_errors is not None:
            where = getattr(err, "filename", None) or str(root)
            why = getattr(err, "strerror", None) or str(err)
            scan_errors.append(f"{where}: {why}")

    patterns = list(excludes or [])
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=_on_scan_error):
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in DEFAULT_EXCLUDES
            and not _matches_exclude(root, Path(dirpath) / d, patterns)
        )
        if _LEDGER_NAME in filenames:
            candidate = Path(dirpath) / _LEDGER_NAME
            if not _matches_exclude(root, candidate, patterns):
                found.append(candidate)
    return sorted(found)


def maintenance_flags(status: dict) -> list[str]:
    """Condense a detect_maintenance_rule status dict into stable flag names."""
    flags: list[str] = []
    if not status.get("rule_installed"):
        flags.append("rule_missing")
    if not (status.get("hook_installed") or status.get("codex_hook_installed")):
        flags.append("hook_missing")
    if status.get("rule_duplicated"):
        flags.append("rule_duplicated")
    if status.get("hook_nonportable"):
        flags.append("hook_nonportable")
    if status.get("claude_gitignored"):
        flags.append("claude_gitignored")
    if status.get("claim_mismatch"):
        flags.append("claim_mismatch")
    if status.get("claude_hook_broken") or status.get("codex_hook_broken"):
        flags.append("hook_broken")
    return flags


def _rel_posix(path: Path, root: Path) -> str:
    """Root-relative POSIX path, or the full path when *path* is outside *root*.

    Uses ``relative_to`` + ``except ValueError`` instead of ``Path.is_relative_to``
    (BUG-096): the latter is Python 3.9+ while this package promises 3.8+.
    """
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _error_entry(path: Path, root: Path, message: str) -> dict:
    """A status=error result row for one file the sweep could not process."""
    return {
        "path": str(path),
        "rel": _rel_posix(path, root),
        "fixes": [],
        "status": "error",
        "error": message,
        "issues": [],
        "warnings": [],
    }


def inspect_file(path: Path, root: Path) -> dict:
    """Run the full read-only diagnostic battery on one ledger."""
    rel = _rel_posix(path, root)
    entry: dict[str, object] = {"path": str(path), "rel": rel, "fixes": []}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        entry.update({"status": "error", "error": str(exc), "issues": [], "warnings": []})
        return entry
    locale = get_locale(detect_locale(text))
    report = analyze_standardization(text, "auto", str(path), path.resolve().parent, locale)
    records = collect_records(text)
    headers_by_title = section_headers_by_title(text)
    warnings = (
        prefix_mismatches(records, locale)
        + time_reversal_issues(records, locale, headers_by_title)
        + completed_missing_time_issues(records, locale, headers_by_title)
    )
    issues = list(report["structural_issues"])
    entry.update(
        {
            "status": "fail" if issues else "pass",
            "lang": locale.name,
            "schema": report["schema"],
            "profile": report["current_profile"],
            "records": report["record_count"],
            "issues": issues,
            "warnings": warnings,
            "auto_fix_candidates": report["auto_fix_candidates"],
            "maintenance": maintenance_flags(report.get("maintenance") or {}),
        }
    )
    return entry


def _apply_safe_fixes(path: Path, profile: str, locale: Locale) -> list[str]:
    """The standardize safe-fix pipeline (blank collapse, pipe escape, missing sections).

    Caller must hold file_lock(path). Returns the applied fix descriptions.
    """
    text = path.read_text(encoding="utf-8")
    working, blank_fixes = collapse_intra_table_blank_lines(text, locale)
    working, pipe_fixes = escape_unescaped_pipes(working, locale)
    working, section_fixes = add_missing_sections(working, profile, locale)
    applied = blank_fixes + pipe_fixes + section_fixes
    if working != text:
        atomic_write(path, working)
    return applied


def run_fleet(
    root: Path,
    excludes: list[str] | None = None,
    apply_fixes: bool = False,
    *,
    locale_name: str = "zh",
    scan_errors: list[str] | None = None,
    lock_timeout: float = 10.0,
) -> list[dict]:
    """Inspect every ledger under *root*; optionally safe-fix then re-inspect each.

    Per-file failures are isolated. A lock timeout or an I/O error while fixing one
    ledger (BUG-095), and a decode error while diagnosing one ledger (BUG-102), must
    not abort the whole sweep. The file is recorded as a status=error entry and the
    loop continues; the CLI turns any non-pass entry into a non-zero exit code.
    Programming errors are not caught here.
    """
    m = T[locale_name]
    results: list[dict] = []
    for path in find_task_lists(root, excludes, scan_errors=scan_errors):
        try:
            entry = inspect_file(path, root)
            if apply_fixes and entry.get("auto_fix_candidates") and entry.get("status") != "error":
                locale = get_locale(str(entry.get("lang") or "zh"))
                try:
                    with file_lock(path, timeout=lock_timeout):
                        applied = _apply_safe_fixes(
                            path, str(entry.get("profile") or "minimal"), locale
                        )
                except LockTimeout as exc:
                    entry = _error_entry(
                        path, root, m["fleet_lock_error"].format(path, int(exc.waited))
                    )
                except OSError as exc:
                    entry = _error_entry(path, root, m["fleet_io_error"].format(exc))
                else:
                    if applied:
                        entry = inspect_file(path, root)
                        entry["fixes"] = applied
        except (OSError, UnicodeError) as exc:
            # inspect_file only guards the ledger read. Maintenance detection reads
            # CLAUDE.md / AGENTS.md / settings.json / hooks.json and lets
            # UnicodeDecodeError escape (it is a ValueError, not an OSError). That
            # used to kill the sweep and drop every other result (BUG-102). The
            # same boundary covers the post-fix re-inspect.
            entry = _error_entry(path, root, m["fleet_io_error"].format(exc))
        results.append(entry)
    return results


def render_text(
    results: list[dict],
    root: Path,
    excludes: list[str],
    locale: Locale,
    scan_errors: list[str] | None = None,
) -> str:
    m = T[locale.name]
    excluded = ", ".join([*DEFAULT_EXCLUDES, *excludes])
    lines = [m["fleet_header"].format(root, excluded)]
    if scan_errors:
        # Incomplete-sweep disclosure (BUG-098): stdout stays machine-parsable; the
        # warning block is part of the report text so a scheduled run cannot mistake
        # "directories skipped" for "everything passed".
        lines.append(m["fleet_scan_errors"].format(len(scan_errors)))
        for message in scan_errors:
            lines.append(m["fleet_issue_item"].format(message))
    passed = failed = fix_count = 0
    for entry in results:
        rel = str(entry.get("rel") or entry["path"])
        fixes = list(entry.get("fixes") or [])
        fix_count += len(fixes)
        issues = list(entry.get("issues") or [])
        warnings = list(entry.get("warnings") or [])
        maint = list(entry.get("maintenance") or [])
        suffix = ""
        if maint:
            labels = _MAINT_LABELS[locale.name]
            suffix = "；" + "、".join(labels.get(f, f) for f in maint) if locale.name == "zh" else "; maint: " + ",".join(maint)
        if entry.get("status") == "error":
            failed += 1
            lines.append(m["fleet_fail"].format(rel, "?"))
            lines.append(m["fleet_issue_item"].format(entry.get("error", "")))
            continue
        if issues:
            failed += 1
            if fixes:
                lines.append(m["fleet_fixed_fail"].format(rel, len(fixes), len(issues)))
            else:
                lines.append(m["fleet_fail"].format(rel, len(issues)))
            for issue in issues[:10]:
                lines.append(m["fleet_issue_item"].format(issue))
            if len(issues) > 10:
                lines.append(m["fleet_issue_item"].format(f"... +{len(issues) - 10}"))
            continue
        passed += 1
        base = [rel, entry.get("records", 0), entry.get("profile", "-"), entry.get("schema", "-")]
        if fixes:
            lines.append(m["fleet_fixed_ok"].format(rel, len(fixes)) + suffix)
        elif warnings:
            lines.append(m["fleet_pass_warn"].format(*base, len(warnings)) + suffix)
        else:
            lines.append(m["fleet_pass"].format(*base) + suffix)
    lines.append(m["fleet_total"].format(len(results), passed, failed, fix_count))
    return "\n".join(lines) + "\n"


def render_report(
    results: list[dict],
    root: Path,
    locale: Locale,
    excludes: list[str] | None = None,
    scan_errors: list[str] | None = None,
) -> str:
    m = T[locale.name]
    lines = [
        m["fleet_report_title"],
        "",
        # Same exclusion list as render_text (BUG-098): the report previously joined
        # only DEFAULT_EXCLUDES, hiding the user's own --exclude patterns from the
        # written record of what the sweep actually covered.
        m["fleet_header"].format(root, ", ".join([*DEFAULT_EXCLUDES, *(excludes or [])])),
        "",
        m["fleet_report_header"],
        m["fleet_report_sep"],
    ]
    for entry in results:
        rel = str(entry.get("rel") or entry["path"])
        issues = list(entry.get("issues") or [])
        result = m["fleet_result_fail"] if issues or entry.get("status") == "error" else m["fleet_result_pass"]
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} |".format(
                # Same escaping as ledger cells (BUG-101/104). Replacing only "|"
                # leaves an even run of backslashes in front of a pipe, which
                # split_cells still treats as a column break.
                escape_cell(rel),
                result,
                entry.get("records", "-"),
                entry.get("profile", "-"),
                entry.get("schema", "-"),
                len(issues),
                len(list(entry.get("warnings") or [])),
                len(list(entry.get("fixes") or [])),
            )
        )
    if scan_errors:
        lines.append("")
        lines.append(m["fleet_scan_errors"].format(len(scan_errors)))
        for message in scan_errors:
            lines.append(m["fleet_issue_item"].format(message))
    return "\n".join(lines) + "\n"


def results_to_json(
    results: list[dict],
    root: Path,
    excludes: list[str],
    scan_errors: list[str] | None = None,
) -> str:
    payload = {
        "root": str(root),
        "generated_at": local_minute_now(),
        "default_excludes": list(DEFAULT_EXCLUDES),
        "excludes": list(excludes),
        # Incomplete-sweep disclosure (BUG-098): automation must be able to tell
        # "scanned everything, all pass" from "could not even list the directories".
        "scan_errors": list(scan_errors or []),
        "total": len(results),
        "passed": sum(1 for e in results if e.get("status") == "pass"),
        "failed": sum(1 for e in results if e.get("status") != "pass"),
        "fixes_applied": sum(len(list(e.get("fixes") or [])) for e in results),
        "files": results,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
