"""Argparse surface and command handlers."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from .locales import (
    MAINTENANCE_RULE_MARKER,
    MAINTENANCE_RULE_MARKER_EN,
    T,
    TASKLIST_HOOK_MARKER,
    Locale,
)
from .repository import atomic_write, commit_all
from .maintenance import HOOK_SCRIPT_EN, HOOK_SCRIPT_ZH, MAINTENANCE_RULE_EN, MAINTENANCE_RULE_ZH, TASKLIST_HOOK_COMMAND, _load_settings_for_hooks, _upgrade_tasklist_hook_commands, detect_maintenance_rule
from .migration import migrate_legacy_schema
from .parser import _collect_wiki_refs, _fenced_code_mask, collect_records, find_record_line, is_section_heading_line, parse_sections, section_headers_by_title
from .renderer import add_missing_sections, append_notes, build_row_for_headers, build_template, collapse_intra_table_blank_lines, escape_unescaped_pipes, insert_row, replace_row_line, table_line
from .schemas import _reject_reversed_times, cell_at_field, date_column_semantic, default_completed_time, detect_locale, detect_schema, find_section_by_title, get_locale, header_field_index, local_minute_now, matches_single_date_header, normalize_time, prefix_for_section, section_for_title, single_date_cell
from .summary import (
    SummaryPolicy,
    has_summary_section,
    resolve_summary_policy,
    summary_sync_would_change_caliber,
    update_summary_text,
)
from .validator import _has_structural_issues, analyze_standardization, check_text, completed_missing_time_issues, prefix_mismatches, render_markdown_report, summary_drift_issues, time_reversal_issues, validate_action_status

def read_task_list(path: Path, *, lang: str = "zh") -> str:
    """Read a task-list file with localized, single-line errors (BUG-028/BUG-038).

    Wraps read_text so FileNotFoundError / IsADirectoryError / UnicodeDecodeError / Permission
    errors surface as a clean SystemExit message instead of a raw Python traceback, which
    pollutes the agent's context and is not localizable. Every command entry point should
    read the target file through this helper.
    """
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(T[lang]["file_not_found"].format(path))
    except (IsADirectoryError, PermissionError, UnicodeDecodeError, OSError) as exc:
        raise SystemExit(T[lang]["file_not_readable"].format(path, exc)) from exc

_ID_TOKEN_RE = re.compile(r"\[\[[A-Z]+-\d+\]\]|[A-Z]+-\d+")


def _normalized_issue_set(issues: list[str]) -> set[str]:
    """Comparable issue fingerprints: positional digits collapse, IDs stay distinct.

    Inserting or deleting a row shifts line numbers in check messages, so raw strings
    cannot be diffed before/after a write. Line numbers and counts collapse to N, but
    ID tokens ([[BUG-002]], DEV-059) are guarded: BUG-002 ≠ BUG-003, so a write that
    swaps one dangling ref for a fresh one is NEW, while the same ref merely moving
    lines is not (BUG-084). Residual imprecision — a same-row invalid value changing
    to another invalid value — is unreachable: add/update validate values up front.
    """

    def _guard_id(m: re.Match) -> str:
        # Map each digit to a letter inside ID tokens so they survive the digit
        # collapse (BUG-002 -> BUG-AAB), keeping same-prefix IDs distinct.
        return "".join("ABCDEFGHIJ"[int(ch)] if ch.isdigit() else ch for ch in m.group(0))

    def _normalize(issue: str) -> str:
        guarded = _ID_TOKEN_RE.sub(_guard_id, issue)
        return re.sub(r"\d+", "N", guarded)

    return {_normalize(issue) for issue in issues}


def write_with_optional_check(
    path: Path,
    original_text: str,
    new_text: str,
    locale: Locale,
    *,
    dry_run: bool,
    no_check: bool,
    skip_summary_drift: bool = False,
) -> int:
    """Write new_text; unless --no-check, validate; roll back only on NEW issues.

    Post-write issues the original file already had (normalized comparison,
    digits collapsed) keep the write and are disclosed on stderr via
    write_kept_residual; only issues introduced by this write restore
    original_text and return 1.
    Does not print success banners — callers print 已追加/已更新 after this returns 0.
    Prints check_ok only when validation ran and passed clean.
    """
    if dry_run:
        print(new_text, end="")
        return 0
    atomic_write(path, new_text)
    if no_check:
        return 0
    schema = detect_schema(new_text, locale)
    issues = check_text(new_text, locale, schema)
    if skip_summary_drift:
        drift = set(summary_drift_issues(new_text, locale))
        issues = [i for i in issues if i not in drift]
    if issues:
        # Baseline-aware rollback (CHK-102 ①): rolling back on *any* post-write issue
        # deadlocks multi-error files - fixing row A is blocked by pre-existing errors
        # in row B and vice versa. Roll back only when this write introduces issues the
        # original did not have; pre-existing ones are disclosed on stderr instead
        # (check remains the gate that fails loudly on purpose).
        baseline = check_text(original_text, locale, schema)
        if skip_summary_drift:
            baseline_drift = set(summary_drift_issues(original_text, locale))
            baseline = [i for i in baseline if i not in baseline_drift]
        if _normalized_issue_set(issues) - _normalized_issue_set(baseline):
            atomic_write(path, original_text)
            print(T[locale.name]["check_failed_rollback"], file=sys.stderr)
            for issue in issues:
                print(issue, file=sys.stderr)
            return 1
        print(T[locale.name]["write_kept_residual"].format(len(issues)), file=sys.stderr)
        return 0
    print(T[locale.name]["check_ok"])
    return 0

def resolve_text_option(
    inline: str | None,
    file_arg: str | None,
    *,
    inline_flag: str,
    file_flag: str,
    default: str | None,
    lang: str,
) -> str | None:
    """Resolve --notes/--description from inline value, --*-file path, or stdin (-)."""
    if file_arg is not None:
        if inline is not None and inline != default:
            raise SystemExit(T[lang]["notes_conflict"].format(inline_flag, file_flag))
        if file_arg == "-":
            return sys.stdin.read().rstrip("\n")
        # BUG-085: same localized error contract as read_task_list (missing /
        # unreadable / non-UTF-8 --*-file inputs must not leak a Python traceback).
        return read_task_list(Path(file_arg), lang=lang).rstrip("\n")
    if inline is not None:
        return inline
    return default

def _entry_from_args(
    args: argparse.Namespace,
    *,
    section: str,
    action: str,
    description: str,
    status: str,
    notes: str,
    found_time: str | None,
    completed_time: str | None,
    date: str | None,
    item_id: str | None,
    priority: str | None,
    estimate: str | None,
) -> dict[str, object]:
    return {
        "section": section,
        "action": action,
        "description": description,
        "status": status,
        "notes": notes,
        "found_time": found_time,
        "completed_time": completed_time,
        "date": date,
        "id": item_id,
        "priority": priority,
        "estimate": estimate,
    }

def _json_str(
    item: dict,
    key: str,
    index: int,
    lang: str,
    *,
    required: bool = False,
    default: str | None = None,
) -> str | None:
    if key not in item or item[key] is None:
        if required:
            raise SystemExit(T[lang]["from_json_entry_missing"].format(index, key))
        return default
    val = item[key]
    if not isinstance(val, str):
        raise SystemExit(T[lang]["from_json_bad_type"].format(index, key, type(val).__name__))
    if required and val == "":
        raise SystemExit(T[lang]["from_json_entry_missing"].format(index, key))
    return val

def _load_from_json(path_arg: str, locale: Locale) -> list[dict[str, object]]:
    lang = locale.name
    try:
        raw = sys.stdin.read() if path_arg == "-" else Path(path_arg).read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(T[lang]["from_json_bad"].format(exc)) from exc
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        raise SystemExit(T[lang]["from_json_bad"].format("expected a non-empty object or array"))
    entries: list[dict[str, object]] = []
    required = ("section", "action", "description", "status")
    for index, item in enumerate(data, 1):
        if not isinstance(item, dict):
            raise SystemExit(T[lang]["from_json_bad"].format(f"entry {index} is not an object"))
        for key in required:
            _json_str(item, key, index, lang, required=True)
        found_time = item.get("found_time", item.get("found-time"))
        completed_time = item.get("completed_time", item.get("completed-time"))
        if found_time is not None and not isinstance(found_time, str):
            raise SystemExit(
                T[lang]["from_json_bad_type"].format(index, "found_time", type(found_time).__name__)
            )
        if completed_time is not None and not isinstance(completed_time, str):
            raise SystemExit(
                T[lang]["from_json_bad_type"].format(
                    index, "completed_time", type(completed_time).__name__
                )
            )
        entries.append(
            {
                "section": _json_str(item, "section", index, lang, required=True),
                "action": _json_str(item, "action", index, lang, required=True),
                "description": _json_str(item, "description", index, lang, required=True),
                "status": _json_str(item, "status", index, lang, required=True),
                "notes": _json_str(item, "notes", index, lang, default="-") or "-",
                "found_time": found_time or None,
                "completed_time": completed_time or None,
                "date": _json_str(item, "date", index, lang),
                "id": _json_str(item, "id", index, lang),
                "priority": _json_str(item, "priority", index, lang),
                "estimate": _json_str(item, "estimate", index, lang),
            }
        )
    return entries

def _append_one_entry(
    text: str,
    entry: dict[str, object],
    locale: Locale,
    *,
    extra_id_texts: list[str] | None = None,
) -> tuple[str, str, str, list[str]]:
    """Append one entry. Returns (new_text, item_id, section_title, row_cells)."""
    lang = locale.name
    extras = list(extra_id_texts or [])
    sections = parse_sections(text)
    section_title = find_section_by_title(str(entry["section"]), sections, locale)
    headers = list(sections[section_title].get("headers") or [])
    if not headers:
        raise SystemExit(T[lang]["section_not_found"].format(section_title))
    section = section_for_title(section_title, locale)
    if not section:
        raise SystemExit(T[lang]["section_not_found"].format(section_title))
    prefix = prefix_for_section(section_title, locale)
    item_id = str(entry["id"]) if entry.get("id") else next_id(prefix, text, *extras)
    if entry.get("id"):
        # An explicit --id must satisfy the documented ID format (大写前缀-三位数字) and
        # carry the target section's prefix; otherwise the row would be written but never
        # counted by collect_records, or misfiled under the wrong section.
        if not re.match(r"^[A-Z]+-\d{3,}$", item_id):
            raise SystemExit(T[lang]["bad_id_on_add"].format(item_id))
        if not item_id.startswith(f"{prefix}-"):
            raise SystemExit(
                T[lang]["prefix_mismatch_on_add"].format(item_id, section_title, prefix)
            )
        existing_ids = {cells[0] for _, _, cells in collect_records(text) if cells}
        for blob in extras:
            existing_ids.update(cells[0] for _, _, cells in collect_records(blob) if cells)
        if item_id in existing_ids:
            raise SystemExit(T[lang]["dup_id_on_add"].format(item_id))
    now = local_minute_now()
    action = str(entry["action"])
    status = str(entry["status"])
    validate_action_status(action, status, locale)
    date_val = str(entry["date"]) if entry.get("date") else None
    found_raw = str(entry["found_time"]) if entry.get("found_time") else date_val
    found_time = normalize_time(found_raw, now, locale)
    completed_value = str(entry["completed_time"]) if entry.get("completed_time") else None
    if not completed_value and status in locale.completed_statuses:
        completed_value = date_val
    completed_time = normalize_time(
        completed_value, default_completed_time(status, now, locale), locale
    )
    _reject_reversed_times(found_time, completed_time, locale)
    notes = str(entry.get("notes") or "-")
    ns = argparse.Namespace(
        date=date_val,
        completed_time=completed_value,
        found_time=found_raw,
    )
    date_header = matches_single_date_header(headers, section, locale)
    if date_header is None and section.title != locale.dev_extended.title:
        date_header = matches_single_date_header(headers, locale.dev_extended, locale)
    semantic = date_column_semantic(date_header, locale) if date_header else "completed"
    if semantic is None:
        semantic = "completed"
    row = build_row_for_headers(
        headers,
        section,
        item_id=item_id,
        action=action,
        description=str(entry["description"]),
        status=status,
        notes=notes,
        found_time=found_time,
        completed_time=completed_time,
        priority=str(entry["priority"]) if entry.get("priority") else None,
        estimate=str(entry["estimate"]) if entry.get("estimate") else None,
        single_date=single_date_cell(ns, status, now, locale, semantic=semantic),
        locale=locale,
        section_title=section_title,
    )
    return insert_row(text, section_title, row, lang), item_id, section_title, row

def command_init(args: argparse.Namespace) -> int:
    locale = get_locale(args.lang)
    output = Path(args.output)
    text = build_template(args.profile, args.with_summary, locale)
    if args.dry_run:
        print(text, end="")
        return 0
    if output.exists() and not args.force:
        print(T[locale.name]["target_exists"].format(output), file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(output, text)
    print(T[locale.name]["generated_file"].format(output))
    return 0

def command_add(args: argparse.Namespace) -> int:
    path = Path(args.file)
    original = read_task_list(path)
    locale = get_locale(detect_locale(original))
    lang = locale.name

    if args.from_json:
        entries = _load_from_json(args.from_json, locale)
    else:
        description = resolve_text_option(
            args.description,
            getattr(args, "description_file", None),
            inline_flag="--description",
            file_flag="--description-file",
            default=None,
            lang=lang,
        )
        notes = resolve_text_option(
            args.notes,
            getattr(args, "notes_file", None),
            inline_flag="--notes",
            file_flag="--notes-file",
            default="-",
            lang=lang,
        )
        if not args.section or not args.action or description is None or not args.status:
            raise SystemExit(T[lang]["add_fields_required"])
        entries = [
            _entry_from_args(
                args,
                section=args.section,
                action=args.action,
                description=description,
                status=args.status,
                notes=notes or "-",
                found_time=args.found_time,
                completed_time=args.completed_time,
                date=args.date,
                item_id=args.id,
                priority=args.priority,
                estimate=args.estimate,
            )
        ]

    text = original
    added: list[tuple[str, str, list[str]]] = []
    archive_texts = sibling_archive_texts(path)
    for entry in entries:
        text, item_id, section_title, row = _append_one_entry(
            text, entry, locale, extra_id_texts=archive_texts
        )
        added.append((item_id, section_title, row))

    # BUG-064: do not auto-rewrite the summary on an already-broken file — that path
    # can delete adjacent section headers and then pass check on the damaged result.
    sync_summary = (not args.no_sync_summary) and (not _has_structural_issues(original, locale))
    text, synced, stale_summary = maybe_sync_summary(text, locale, sync_summary, baseline=original)

    if args.dry_run:
        for _, _, row in added:
            print(table_line(row))
        return 0

    rc = write_with_optional_check(
        path,
        original,
        text,
        locale,
        dry_run=False,
        no_check=args.no_check,
        skip_summary_drift=args.no_sync_summary or stale_summary,
    )
    if rc != 0:
        return rc
    for item_id, section_title, _ in added:
        print(T[lang]["added"].format(item_id, section_title))
    if synced:
        print(T[lang]["summary_synced"])
    return 0

def command_update(args: argparse.Namespace) -> int:
    path = Path(args.file)
    original = read_task_list(path)
    locale = get_locale(detect_locale(original))
    lang = locale.name

    if args.notes is not None and args.notes_file is not None:
        raise SystemExit(T[lang]["notes_conflict"].format("--notes", "--notes-file"))
    if args.notes_append is not None and args.notes_append_file is not None:
        raise SystemExit(T[lang]["notes_conflict"].format("--notes-append", "--notes-append-file"))

    notes_override = resolve_text_option(
        args.notes,
        args.notes_file,
        inline_flag="--notes",
        file_flag="--notes-file",
        default=None,
        lang=lang,
    )
    notes_append = resolve_text_option(
        args.notes_append,
        args.notes_append_file,
        inline_flag="--notes-append",
        file_flag="--notes-append-file",
        default=None,
        lang=lang,
    )
    description = resolve_text_option(
        args.description,
        args.description_file,
        inline_flag="--description",
        file_flag="--description-file",
        default=None,
        lang=lang,
    )

    field_set = any(
        v is not None
        for v in (
            args.action,
            description,
            args.status,
            notes_override,
            notes_append,
            args.found_time,
            args.completed_time,
            args.priority,
            args.estimate,
        )
    )
    if not field_set:
        raise SystemExit(T[lang]["update_no_fields"])

    title, line_index, cells, headers = find_record_line(original, args.id, locale)
    if len(cells) != len(headers):
        raise SystemExit(
            T[lang]["col_mismatch"].format(line_index + 1, len(headers), len(cells))
        )
    indices = header_field_index(headers, locale)

    if args.action is not None:
        if "action" not in indices:
            raise SystemExit(T[lang]["field_not_applicable"].format("--action", title))
        # BUG-030: --action's status-for-cross-check lookup crashed with KeyError when the
        # header has no 状态/Status column. Only read the existing status when the column
        # exists; when there is no status column AND no --status was passed, validate the
        # action in isolation (no status to cross-check against).
        if args.status is not None:
            status_for_check: str | None = args.status
        elif "status" in indices:
            status_for_check = cells[indices["status"]]
        else:
            status_for_check = None
        validate_action_status(args.action, status_for_check, locale)
        cells[indices["action"]] = args.action
    if description is not None:
        # BUG-032: silently skipping when the column is absent, while reporting "已更新", is a
        # data-integrity lie. The other field branches reject with field_not_applicable; notes
        # and description must do the same for consistency.
        if "description" not in indices:
            raise SystemExit(T[lang]["field_not_applicable"].format("--description", title))
        cells[indices["description"]] = description
    if args.status is not None:
        if "status" not in indices:
            raise SystemExit(T[lang]["nonstandard_header"].format(title, len(headers)))
        action_val = (
            args.action
            if args.action is not None
            else (cells[indices["action"]] if "action" in indices else "")
        )
        validate_action_status(action_val, args.status, locale)
        cells[indices["status"]] = args.status
    if args.found_time is not None:
        if "found_time" not in indices:
            raise SystemExit(T[lang]["field_not_applicable"].format("--found-time", title))
        cells[indices["found_time"]] = normalize_time(args.found_time, args.found_time, locale)
    if args.completed_time is not None:
        if "completed_time" not in indices:
            raise SystemExit(T[lang]["field_not_applicable"].format("--completed-time", title))
        new_completed = normalize_time(
            args.completed_time, args.completed_time, locale
        )
        if args.status is not None:
            status_now = args.status
        elif "status" in indices:
            status_now = cells[indices["status"]]
        else:
            status_now = ""
        if new_completed == "-" and status_now in locale.completed_statuses:
            raise SystemExit(T[lang]["completed_time_required"])
        cells[indices["completed_time"]] = new_completed
    if args.priority is not None:
        if "priority" not in indices:
            raise SystemExit(T[lang]["field_not_applicable"].format("--priority", title))
        cells[indices["priority"]] = args.priority
    if args.estimate is not None:
        if "estimate" not in indices:
            raise SystemExit(T[lang]["field_not_applicable"].format("--estimate", title))
        cells[indices["estimate"]] = args.estimate

    if notes_override is not None:
        # BUG-032: --notes must reject with field_not_applicable when the column is absent,
        # not silently skip while reporting "已更新" — the other field branches already do.
        if "notes" not in indices:
            raise SystemExit(T[lang]["field_not_applicable"].format("--notes", title))
        cells[indices["notes"]] = notes_override
    if notes_append is not None:
        if "notes" not in indices:
            raise SystemExit(T[lang]["field_not_applicable"].format("--notes-append", title))
        cells[indices["notes"]] = append_notes(cells[indices["notes"]], notes_append)

    # If status flipped to completed and completed_time not explicitly set, default to now
    # when the Done cell is still "-".
    if (
        args.status is not None
        and args.status in locale.completed_statuses
        and args.completed_time is None
        and "completed_time" in indices
        and cells[indices["completed_time"]] == "-"
    ):
        cells[indices["completed_time"]] = local_minute_now()

    # Mirror image: if status flipped back to incomplete (待办/进行中/…) and the caller did
    # not explicitly set a completed time, reset the Done cell to "-" — per the documented
    # time/status constraint an unfinished record must not keep a completion time.
    # BUG-031: this reset is DUAL-schema only. On a single-date schema the lone 完成日期 /
    # Done Date column is also mapped as completed_time, but pending rows legitimately carry a
    # date there (it is the record's only date, not a completion timestamp). check explicitly
    # exempts single-date from the same constraint, so update must match. found_time is present
    # only in the dual schema (发现时间 / Found), so its absence marks single-date.
    if (
        args.status is not None
        and args.status in locale.pending_statuses
        and args.completed_time is None
        and "found_time" in indices
        and "completed_time" in indices
        and cells[indices["completed_time"]] != "-"
    ):
        cells[indices["completed_time"]] = "-"

    if "found_time" in indices and "completed_time" in indices:
        _reject_reversed_times(
            cells[indices["found_time"]], cells[indices["completed_time"]], locale
        )

    new_text = replace_row_line(original, line_index, cells)
    sync_summary = (not args.no_sync_summary) and (not _has_structural_issues(original, locale))
    new_text, synced, stale_summary = maybe_sync_summary(new_text, locale, sync_summary, baseline=original)
    if args.dry_run:
        print(table_line(cells))
        return 0
    rc = write_with_optional_check(
        path,
        original,
        new_text,
        locale,
        dry_run=False,
        no_check=args.no_check,
        skip_summary_drift=args.no_sync_summary or stale_summary,
    )
    if rc != 0:
        return rc
    print(T[lang]["updated"].format(args.id))
    if synced:
        print(T[lang]["summary_synced"])
    return 0

def command_sections(args: argparse.Namespace) -> int:
    path = Path(args.file)
    text = read_task_list(path)
    locale = get_locale(detect_locale(text))
    sections = parse_sections(text)
    rows = []
    for title, info in sections.items():
        if title == locale.summary_section:
            prefix = None
        else:
            try:
                prefix = prefix_for_section(title, locale)
            except SystemExit:
                prefix = None
        headers = list(info.get("headers") or [])
        rows.append(
            {
                "title": title,
                "prefix": prefix,
                "columns": len(headers),
                "headers": headers,
                "rows": len(info.get("rows") or []),
            }
        )
    if args.format == "json":
        print(json.dumps({"lang": locale.name, "sections": rows}, ensure_ascii=False, indent=2))
        return 0
    for row in rows:
        prefix = row["prefix"] or "-"
        print(f"{row['title']}\t{prefix}\t{row['columns']}cols\t{row['rows']}rows")
    return 0

def command_list(args: argparse.Namespace) -> int:
    path = Path(args.file)
    text = read_task_list(path)
    locale = get_locale(detect_locale(text))
    records = collect_records(text)
    headers_by_title = section_headers_by_title(text)
    section_filter = None
    if args.section:
        sections = parse_sections(text)
        section_filter = find_section_by_title(args.section, sections, locale)

    results = []
    for title, line_no, cells in records:
        if args.id and cells[0] != args.id:
            continue
        if section_filter and title != section_filter:
            continue
        headers = headers_by_title.get(title, [])
        # BUG-037: read status/notes BY HEADER NAME, not cells[-2]/cells[-1]. A row whose notes
        # cell contains an unescaped pipe splits into extra cells, so cells[-2] lands on a notes
        # fragment and the status filter silently misses the record.
        status = cell_at_field(cells, headers, "status", locale, fallback=-2)
        if args.status and status != args.status:
            continue
        if args.keyword:
            hay = " ".join(cells).lower()
            if args.keyword.lower() not in hay:
                continue
        action = cell_at_field(cells, headers, "action", locale, fallback=1)
        description = cell_at_field(cells, headers, "description", locale, fallback=2)
        notes = cell_at_field(cells, headers, "notes", locale, fallback=-1)
        results.append(
            {
                "id": cells[0],
                "section": title,
                "action": action,
                "description": description,
                "status": status,
                "notes": notes,
                "line": line_no,
                "cells": cells,
            }
        )

    if args.format == "json":
        print(json.dumps({"count": len(results), "records": results}, ensure_ascii=False, indent=2))
        return 0
    for row in results:
        print(table_line(row["cells"]))
    return 0

def command_install_maintenance(args: argparse.Namespace) -> int:
    path = Path(args.file)
    project_root = path.resolve().parent
    text = read_task_list(path) if path.exists() else ""
    locale = get_locale(detect_locale(text) if text else "zh")
    lang = locale.name
    m = T[lang]

    # Pick agent file: CLAUDE.md > AGENTS.md > create CLAUDE.md
    claude = project_root / "CLAUDE.md"
    agents = project_root / "AGENTS.md"
    if claude.exists():
        target = claude
    elif agents.exists():
        target = agents
    else:
        target = claude

    # Cross-file idempotence: the rule counts as installed when ANY agent file already
    # carries it — checking only the picked target would append a duplicate copy to
    # CLAUDE.md when the rule already lives in AGENTS.md (and vice versa).
    agent_texts = {
        p: p.read_text(encoding="utf-8") for p in (claude, agents) if p.exists()
    }
    holder = next(
        (
            p
            for p, content in agent_texts.items()
            if MAINTENANCE_RULE_MARKER in content or MAINTENANCE_RULE_MARKER_EN in content
        ),
        None,
    )
    # Collect every (path, text) the command intends to write, then commit them as one
    # atomic transaction (REQ-13). If any write fails, already-written files roll back
    # to their pre-install bytes — no half-installed rule/hook/settings state.
    plans: list[tuple[Path, str]] = []
    hook_script_needs_chmod = False
    if holder is not None:
        print(m["maint_rule_present"].format(holder.name))
        rule_file_name = holder.name
    else:
        existing = agent_texts.get(target, "")
        block = MAINTENANCE_RULE_ZH if lang == "zh" else MAINTENANCE_RULE_EN
        new_content = (existing.rstrip() + "\n\n" + block).lstrip() + "\n"
        if not args.dry_run:
            plans.append((target, new_content))
        print(m["maint_installed_rule"].format(target.name))
        rule_file_name = target.name

    if not args.with_hook:
        if not args.dry_run and plans:
            commit_all(plans)
        print(m["maint_hook_skipped"])
        return 0

    settings_path = project_root / ".claude" / "settings.json"
    hook_script = project_root / ".claude" / "hooks" / "tasklist_sync_reminder.sh"
    status = detect_maintenance_rule(project_root)
    if status.get("hook_installed"):
        # Idempotent path: still upgrade legacy relative commands / rewrite missing script.
        if args.dry_run:
            print(m["maint_hook_present"])
            return 0
        settings = _load_settings_for_hooks(settings_path, m)
        stop_list = settings["hooks"]["Stop"]
        upgraded = _upgrade_tasklist_hook_commands(stop_list)
        script = HOOK_SCRIPT_ZH if lang == "zh" else HOOK_SCRIPT_EN
        desired = script.replace("CLAUDE.md", rule_file_name)
        if (not hook_script.exists()) or hook_script.read_text(encoding="utf-8") != desired:
            plans.append((hook_script, desired))
            hook_script_needs_chmod = True
        if upgraded:
            plans.append((settings_path, json.dumps(settings, ensure_ascii=False, indent=2) + "\n"))
        if plans:
            commit_all(plans)
            if hook_script_needs_chmod:
                hook_script.chmod(hook_script.stat().st_mode | 0o111)
        if upgraded:
            print(m["maint_hook_upgraded"])
        else:
            print(m["maint_hook_present"])
        return 0

    if args.dry_run:
        print(m["maint_installed_hook"].format(str(hook_script.relative_to(project_root))))
        return 0

    # Parse and shape-check settings.json BEFORE building the write plans, so a malformed
    # but parseable file (hooks:null / Stop as dict) aborts cleanly with no half-install.
    settings = _load_settings_for_hooks(settings_path, m)
    stop_list = settings["hooks"]["Stop"]

    # The reminder text must name the agent file that actually holds the rule.
    script = HOOK_SCRIPT_ZH if lang == "zh" else HOOK_SCRIPT_EN
    plans.append((hook_script, script.replace("CLAUDE.md", rule_file_name)))
    hook_script_needs_chmod = True

    entry = {
        "matcher": "",
        "hooks": [
            {
                "type": "command",
                "command": TASKLIST_HOOK_COMMAND,
            }
        ],
    }
    # Avoid duplicate tasklist hooks
    already = False
    for item in stop_list:
        if not isinstance(item, dict):
            continue
        for hook in item.get("hooks", []) or []:
            if isinstance(hook, dict) and TASKLIST_HOOK_MARKER in str(hook.get("command", "")):
                already = True
                break
        if already:
            break
    if not already:
        stop_list.append(entry)
    else:
        _upgrade_tasklist_hook_commands(stop_list)
    plans.append((settings_path, json.dumps(settings, ensure_ascii=False, indent=2) + "\n"))

    commit_all(plans)
    if hook_script_needs_chmod:
        hook_script.chmod(hook_script.stat().st_mode | 0o111)
    print(m["maint_installed_hook"].format(".claude/hooks/tasklist_sync_reminder.sh"))
    return 0

def command_check(args: argparse.Namespace) -> int:
    path = Path(args.file)
    text = read_task_list(path)
    locale = get_locale(detect_locale(text))
    schema = args.schema if args.schema != "auto" else detect_schema(text, locale)
    issues = check_text(text, locale, schema)
    # REQ-08: prefix/section misplacement is a warning, not an error. standardize already
    # reports these records; check must surface the same warning list without moving
    # records (reclassification is a semantic change reserved for the user) and without
    # failing the gate - post-write auto-check must not roll back on warnings alone.
    warnings = prefix_mismatches(collect_records(text), locale)
    for issue in issues:
        print(issue)
    if warnings:
        print(T[locale.name]["check_prefix_warnings"])
        for warning in warnings:
            print(warning)
    # CHK-103 finding 4: surface pre-existing time inversions (completed < found)
    # as warnings. The write path already refuses new ones; without this a legacy
    # inversion passes a green check. Warning-class per REQ-08: exit code unchanged.
    reversals = time_reversal_issues(collect_records(text), locale, section_headers_by_title(text))
    if reversals:
        print(T[locale.name]["check_time_reverse_warnings"])
        for reversal in reversals:
            print(reversal)
    # CHK-103 finding 5 (ruled: surface this one class): completed-status rows whose
    # Done time is still '-' used to pass a green check because the aggregate warning
    # was standardize-only. Warning-class, exit code unchanged. Sparse-notes, ID-order
    # and exact-duplicate warnings stay standardize-only (style/low-risk).
    missing_done = completed_missing_time_issues(collect_records(text), locale, section_headers_by_title(text))
    if missing_done:
        print(T[locale.name]["check_completed_no_time_warnings"])
        for issue in missing_done:
            print(issue)
    if issues:
        return 1
    print(T[locale.name]["check_ok"])
    return 0

def _print_summary_rows_block(
    label: str, rows: list[tuple[str, int, int, int]], locale_name: str
) -> None:
    print(label)
    for title, total, done, pending in rows:
        print(T[locale_name]["summary_row_counts"].format(title, total, done, pending))


def _print_summary_policy_conflict(decision, locale_name: str) -> None:
    """Render the dual-caliber report shown when auto must refuse (REQ-07)."""
    m = T[locale_name]
    print(m["summary_policy_conflict"])
    _print_summary_rows_block(m["by_prefix"], decision.prefix_rows, locale_name)
    _print_summary_rows_block(m["by_section"], decision.section_rows, locale_name)
    if decision.matches_existing is SummaryPolicy.BY_PREFIX:
        print(m["summary_policy_match_prefix"])
    elif decision.matches_existing is SummaryPolicy.BY_SECTION:
        print(m["summary_policy_match_section"])
    else:
        print(m["summary_policy_no_match"])
    print(m["summary_policy_refused"])
    print(m["summary_policy_hint"])


def command_summary(args: argparse.Namespace) -> int:
    path = Path(args.file)
    text = read_task_list(path)
    locale = get_locale(detect_locale(text))
    policy = SummaryPolicy(args.policy)
    decision = resolve_summary_policy(text, locale, policy)
    # REQ-06: rows whose cell count disagrees with the section header (check reports them
    # as col_mismatch, usually an unescaped | splitting a cell) must not feed statistics:
    # header-indexed reads land on cell fragments, so dates/effort strings would surface
    # as statuses, and totals would count broken rows.
    headers_by_title = section_headers_by_title(text)
    skipped_rows = sum(
        1
        for title, _, cells in collect_records(text)
        if headers_by_title.get(title) and len(cells) != len(headers_by_title[title])
    )

    if args.write:
        # REQ-07: auto never rewrites a summary while the calibers disagree — the file's
        # counting semantics are ambiguous, so the user must pick a caliber explicitly.
        # BUG-074: gate on --write only; a bare --dry-run must stay on the read-only
        # stats view instead of printing the whole rewritten file (or refusing with
        # exit 1 on conflict) as if a write had been requested.
        if decision.conflict and policy is SummaryPolicy.AUTO:
            _print_summary_policy_conflict(decision, locale.name)
            return 1
        new_text = update_summary_text(text, locale, decision.rows)
        # The recount drops width-mismatched rows; say so on stderr so the number change
        # (e.g. 总计 260 → 254) is never silent. stderr keeps --dry-run stdout a clean
        # copy of the file content for redirect (BUG-009 convention).
        if skipped_rows:
            print(
                T[locale.name]["summary_skipped_col_mismatch"].format(skipped_rows),
                file=sys.stderr,
            )
        if args.dry_run:
            print(new_text, end="")
            return 0
        atomic_write(path, new_text)
        print(T[locale.name]["summary_updated"].format(path))
        return 0

    records = collect_records(text)
    # REQ-06: rows whose cell count disagrees with the section header (check reports them
    # as col_mismatch, usually an unescaped | splitting a cell) must not feed statistics:
    # header-indexed reads land on cell fragments, so dates/effort strings would surface
    # as statuses, and totals would count broken rows.
    stat_records = [
        (title, line_no, cells)
        for title, line_no, cells in records
        if not headers_by_title.get(title) or len(cells) == len(headers_by_title[title])
    ]
    skipped_rows = len(records) - len(stat_records)
    by_section = Counter(title for title, _, _ in stat_records)
    # BUG-037: read status BY HEADER NAME. cells[-2] lands on a notes fragment when a notes
    # cell holds an unescaped pipe, so the status distribution printed garbage status names.
    by_status = Counter(
        cell_at_field(cells, headers_by_title.get(title, []), "status", locale, fallback=-2)
        for title, _, cells in stat_records
        if len(cells) >= 2
    )
    m = T[locale.name]

    if decision.conflict and policy is SummaryPolicy.AUTO:
        # Read-only auto view of an ambiguous file: show both calibers instead of
        # silently picking one, plus the hint for an explicit --policy rewrite.
        _print_summary_rows_block(m["by_prefix"], decision.prefix_rows, locale.name)
        _print_summary_rows_block(m["by_section"], decision.section_rows, locale.name)
        print(m["summary_policy_conflict"])
        if decision.matches_existing is SummaryPolicy.BY_PREFIX:
            print(m["summary_policy_match_prefix"])
        elif decision.matches_existing is SummaryPolicy.BY_SECTION:
            print(m["summary_policy_match_section"])
        else:
            print(m["summary_policy_no_match"])
        print(m["summary_policy_hint"])
    elif policy is SummaryPolicy.BY_PREFIX:
        counts = {title: total for title, total, _, _ in decision.rows}
        print(m["by_prefix"])
        for title, count in counts.items():
            print(f"- {title}: {count}")
    else:
        print(m["by_section"])
        for title, count in by_section.items():
            print(f"- {title}: {count}")
    print(m["by_status"])
    for status, count in by_status.items():
        print(f"- {status}: {count}")
    print(m["total_count"].format(len(stat_records)))
    if skipped_rows:
        print(m["summary_skipped_col_mismatch"].format(skipped_rows))
    return 0

def command_standardize(args: argparse.Namespace) -> int:
    path = Path(args.file)
    project_root = path.resolve().parent
    original_text = read_task_list(path)
    locale = get_locale(detect_locale(original_text))
    working_text = original_text
    applied_fixes: list[str] = []
    migrate_warnings: list[str] = []
    # --fix-only is an output modifier (summary instead of full report); it does not itself
    # trigger fixes. Repairs run only with --apply-safe-fixes or --migrate-schema.
    should_fix = args.apply_safe_fixes or args.migrate_schema

    if args.migrate_schema:
        working_text, fixes, migrate_warnings = migrate_legacy_schema(working_text, locale)
        applied_fixes.extend(fixes)

    initial_report = analyze_standardization(working_text, args.profile, str(path), project_root, locale, schema_override=args.schema)
    chosen_profile = str(initial_report["recommended_profile"])

    if args.apply_safe_fixes:
        working_text, blank_fixes = collapse_intra_table_blank_lines(working_text, locale)
        applied_fixes.extend(blank_fixes)
        working_text, pipe_fixes = escape_unescaped_pipes(working_text, locale)
        applied_fixes.extend(pipe_fixes)
        working_text, fixes = add_missing_sections(working_text, chosen_profile, locale)
        applied_fixes.extend(fixes)

    # When previewing with --dry-run, stdout is reserved for the file content so it can be
    # redirected safely; route all status/report messages to stderr in that case.
    printed_preview = False
    if should_fix and working_text != original_text:
        if args.dry_run:
            print(working_text, end="")
            printed_preview = True
        else:
            atomic_write(path, working_text)
    status_stream = sys.stderr if printed_preview else sys.stdout

    report = analyze_standardization(working_text, args.profile, str(path), project_root, locale, schema_override=args.schema)
    if args.format == "json":
        rendered = json.dumps({**report, "applied_fixes": applied_fixes, "migrate_warnings": migrate_warnings}, ensure_ascii=False, indent=2) + "\n"
    else:
        rendered = render_markdown_report(report, applied_fixes, locale)

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(report_path, rendered)
        print(T[locale.name]["report_written"].format(report_path), file=status_stream)

    if args.fix_only:
        print(T[locale.name]["fixes_applied"].format(len(applied_fixes)), file=status_stream)
        for fix in applied_fixes:
            print(f"- {fix}", file=status_stream)
        if migrate_warnings:
            print(T[locale.name]["migrate_skips"].format(len(migrate_warnings)), file=status_stream)
            for warning in migrate_warnings:
                print(warning, file=status_stream)
        # CHK-038 观察① (BUG-072 precedent): --fix-only prints only the fix summary, so
        # residuals that still fail check (e.g. legacy 状态=- rows kept verbatim by
        # migrate) would read as "all done". Disclose the remainder on stderr; the exit
        # code stays 0 — check owns the gate, this is a disclosure, not a failure.
        if should_fix and not args.dry_run:
            resolved_schema = (
                args.schema if args.schema != "auto" else detect_schema(working_text, locale)
            )
            remaining = check_text(working_text, locale, resolved_schema)
            if remaining:
                print(
                    T[locale.name]["fixes_residual"].format(len(remaining)),
                    file=sys.stderr,
                )
        return 0

    if not args.report and not printed_preview:
        print(rendered, end="" if rendered.endswith("\n") else "\n")
    elif should_fix:
        print(T[locale.name]["fixes_applied"].format(len(applied_fixes)), file=status_stream)
        if migrate_warnings:
            print(T[locale.name]["migrate_skips"].format(len(migrate_warnings)), file=status_stream)
            for warning in migrate_warnings:
                print(warning, file=status_stream)

    return 0

def command_archive(args: argparse.Namespace) -> int:
    path = Path(args.file)
    text = read_task_list(path)
    locale = get_locale(detect_locale(text))
    # BUG-035: --older-than-days had no range check. Values >999999999 crashed with an
    # OverflowError stack trace; negative values silently archived ALL completed records
    # because the cutoff landed in the future. Clamp to a sane positive range.
    if args.older_than_days < 0:
        raise SystemExit(T[locale.name]["archive_days_negative"].format(args.older_than_days))
    if args.older_than_days > 365 * 100:
        raise SystemExit(
            T[locale.name]["archive_days_too_large"].format(args.older_than_days, 365 * 100)
        )
    if args.as_of:
        try:
            as_of = datetime.strptime(args.as_of, "%Y-%m-%d")
        except ValueError:
            raise SystemExit(T[locale.name]["archive_as_of_bad"].format(args.as_of))
    else:
        as_of = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    main_text, archive_body, moved = archive_old_completed(
        text, locale, args.older_than_days, as_of
    )
    if moved == 0:
        print(T[locale.name]["archive_none"])
        return 0

    if args.output:
        archive_path = Path(args.output)
    else:
        archive_path = path.with_name(f"task-list-archive-{as_of.strftime('%Y%m')}.md")

    # Archiving into the main file itself would first write the archive body over the
    # main file and then overwrite it with main_text (records dropped from both), while
    # reporting success. Refuse before writing anything.
    if archive_path.resolve() == path.resolve():
        raise SystemExit(T[locale.name]["archive_output_same"].format(archive_path))

    # BUG-034: archiving records out of the main file can leave dangling [[ID]] references
    # behind (a still-open record's notes cite an ID that just got archived). check would flag
    # them only AFTER the write, so the user would not discover the breakage unless they ran
    # check separately. Detect before writing and refuse so the references can be resolved.
    remaining_ids = {cells[0] for _, _, cells in collect_records(main_text) if cells}
    dangling: list[str] = []
    for line_no, ref_id in _collect_wiki_refs(main_text):
        if ref_id not in remaining_ids:
            dangling.append(T[locale.name]["archive_dangling_item"].format(line_no, ref_id))
    if dangling:
        sep = "、" if locale.name == "zh" else "; "
        raise SystemExit(
            T[locale.name]["archive_dangling_refs"].format(sep.join(dangling[:10]))
        )

    if args.dry_run:
        print(main_text, end="")
        print("---ARCHIVE---", file=sys.stderr)
        print(archive_body, end="", file=sys.stderr)
        return 0

    # Build the full archive content up front: append-merge into an existing same-month
    # archive, or use the new body verbatim. Both the archive file and the main file are
    # then committed as one transaction (REQ-13): if either write fails, both roll back
    # to their pre-archive bytes — records are never left half-moved (dropped from the
    # main file but missing from the archive).
    if archive_path.exists():
        existing = read_task_list(archive_path, lang=locale.name)
        moved_ids = re.findall(r"^\|\s*([A-Z]+-\d+)\s*\|", archive_body, re.M)
        existing_ids = set(re.findall(r"^\|\s*([A-Z]+-\d+)\s*\|", existing, re.M))
        conflicts = sorted({i for i in moved_ids if i in existing_ids} | {
            i for i, n in Counter(moved_ids).items() if n > 1
        })
        if conflicts:
            raise SystemExit(
                T[locale.name]["archive_dupe"].format(
                    ", ".join(conflicts), archive_path.name
                )
            )
        final_archive = merge_archive_body(existing, archive_body, locale)
    else:
        final_archive = archive_body

    # Keep an existing 统计摘要 in step with the records left in the main file.
    main_text, synced, _stale_summary = maybe_sync_summary(main_text, locale, True, baseline=text)

    commit_all([(archive_path, final_archive), (path, main_text)])
    print(T[locale.name]["archive_moved"].format(moved, archive_path))
    if synced:
        print(T[locale.name]["summary_synced"])
    return 0

def maybe_sync_summary(
    text: str, locale: Locale, enabled: bool, baseline: str | None = None
) -> tuple[str, bool, bool]:
    """Recompute 统计摘要 when the section already exists. Never creates it.

    Returns (text, synced, stale_summary). When the by-prefix and by-section calibers
    disagree and the written summary does not already match the by-section numbers,
    the sync is skipped (REQ-07/§5.2: never re-bucket an ambiguous summary silently)
    and stale_summary=True tells the caller to filter summary-drift issues from the
    post-write check so the append itself is not rolled back.

    BUG-073: the caliber judgment must run on `baseline` (the text BEFORE this write).
    On the post-write text the old summary numbers match neither caliber, so a file
    whose summary is legitimately by-section would be misjudged as ambiguous and the
    sync wrongly skipped. When baseline is omitted the post-write text is used.
    """
    caliber_text = text if baseline is None else baseline
    if not enabled or not has_summary_section(caliber_text, locale):
        return text, False, False
    if summary_sync_would_change_caliber(caliber_text, locale):
        print(T[locale.name]["summary_sync_skipped_conflict"], file=sys.stderr)
        return text, False, True
    return update_summary_text(text, locale), True, False

def sibling_archive_texts(main_path: Path) -> list[str]:
    """Load sibling Markdown files whose names look like archives (ID high-water source).

    next_id / explicit --id must not reuse numbers that already live only in an archive
    file; otherwise [[BUG-002]] refs silently retarget after a later add.
    """
    parent = main_path.resolve().parent
    main_res = main_path.resolve()
    texts: list[str] = []
    for path in sorted(parent.glob("*.md")):
        if path.resolve() == main_res:
            continue
        if "archive" not in path.name.lower():
            continue
        try:
            texts.append(path.read_text(encoding="utf-8"))
        except OSError:
            continue
    return texts

def next_id(prefix: str, text: str, *extra_texts: str) -> str:
    # Only count IDs that actually appear as the FIRST column of a data row. A naive
    # full-text regex would also match an ID *referenced* inside a 备注 / 问题描述 cell
    # (e.g. "关联 BUG-099", "依赖 DEV-012") and inflate the next number, producing
    # BUG-100 instead of BUG-002 even when only BUG-001 exists as a real record.
    # collect_records already parses rows and matches the ID column with ^[A-Z]+-\d{3,}$,
    # so reusing it keeps the row/column scope correct while preserving the >=3-digit rule.
    # Extra texts (sibling archive files) are included so archived max IDs are never reused.
    id_pattern = re.compile(rf"^{re.escape(prefix)}-(\d{{3,}})$")
    numbers = []
    for blob in (text, *extra_texts):
        for _, _, cells in collect_records(blob):
            if cells:
                match = id_pattern.match(cells[0])
                if match:
                    numbers.append(int(match.group(1)))
    number = max(numbers, default=0) + 1
    return f"{prefix}-{number:03d}"

def archive_old_completed(
    text: str,
    locale: Locale,
    older_than_days: int,
    as_of: datetime,
) -> tuple[str, str, int]:
    """Move completed records older than N days out of the main list into an archive body.

    Returns (new_main_text, archive_body, moved_count). Archive body is a partial markdown
    document (title + only sections that received rows). Empty sections are omitted.
    """
    lines = text.splitlines()
    sections = parse_sections(text)
    # line index → keep?
    drop_lines: set[int] = set()
    archived_by_section: dict[str, list[list[str]]] = defaultdict(list)
    headers_by_section: dict[str, list[str]] = {}

    cutoff = as_of - timedelta(days=older_than_days)

    for title, info in sections.items():
        headers = list(info.get("headers") or [])
        if not headers:
            continue
        headers_by_section[title] = headers
        for line_no, cells in info.get("rows", []):
            if len(cells) != len(headers):
                continue
            if not cells or not re.match(r"^[A-Z]+-\d{3,}$", cells[0]):
                continue
            field_idx = header_field_index(headers, locale)
            if "status" not in field_idx:
                # Malformed short headers (e.g. "| ID |" alone) must not crash archive;
                # check already reports them — skip until the table is repairable.
                continue
            status = cells[field_idx["status"]]
            if status not in locale.completed_statuses:
                continue
            # Prefer named 完成时间/Done / 完成日期; fall back to cells[-3] when present.
            done_idx = field_idx.get("completed_time")
            if done_idx is None:
                done_idx = len(cells) - 3
            if not (0 <= done_idx < len(cells)):
                continue
            done_at = _parse_completed_date(cells[done_idx])
            if done_at is None:
                continue
            if done_at > cutoff:
                continue
            drop_lines.add(line_no)
            archived_by_section[title].append(cells)

    if not drop_lines:
        return text, "", 0

    new_main_lines = [line for idx, line in enumerate(lines) if idx not in drop_lines]
    # Collapse blank runs left between remaining table rows (section-gap blanks stay).
    main_text = "\n".join(new_main_lines).rstrip() + "\n"
    main_text, _blank_fixes = collapse_intra_table_blank_lines(main_text, locale)

    archive_parts = [
        locale.title.replace("任务跟踪列表", "任务跟踪列表（归档）").replace(
            "Task Tracking List", "Task Tracking List (Archive)"
        ),
        "",
        (
            f"> 从主表归档：完成时间早于或等于 {cutoff.strftime('%Y-%m-%d')} "
            f"（--older-than-days {older_than_days}，as-of {as_of.strftime('%Y-%m-%d')}）。"
            if locale.name == "zh"
            else f"> Archived from main list: Done on or before {cutoff.strftime('%Y-%m-%d')} "
            f"(--older-than-days {older_than_days}, as-of {as_of.strftime('%Y-%m-%d')})."
        ),
        "",
    ]
    moved = 0
    for title, rows in archived_by_section.items():
        headers = headers_by_section.get(title) or []
        archive_parts.append(f"## {title}")
        archive_parts.append("")
        archive_parts.append("| " + " | ".join(headers) + " |")
        archive_parts.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            archive_parts.append(table_line(row))
            moved += 1
        archive_parts.append("")

    return main_text, "\n".join(archive_parts).rstrip() + "\n", moved

def merge_archive_body(
    existing: str, archive_body: str, locale: Locale | None = None
) -> str:
    """Merge a new archive body into an existing archive file.

    Sections already present in the archive get the new rows appended to their existing
    table; sections not yet present are appended as whole blocks. Appending full section
    blocks unconditionally would create duplicate `## Title` sections on a second
    same-month run, which the archive file itself would then fail check on.
    """
    locale = locale or get_locale(detect_locale(existing or archive_body))
    text = existing.rstrip() + "\n"
    existing_sections = parse_sections(existing)
    body_lines = archive_body.splitlines()
    body_fence = _fenced_code_mask(body_lines)
    for title, info in parse_sections(archive_body).items():
        rows = info.get("rows") or []
        if not rows:
            continue
        if title in existing_sections:
            existing_headers = list(existing_sections[title].get("headers") or [])
            new_headers = list(info.get("headers") or [])
            if existing_headers and new_headers and list(existing_headers) != list(new_headers):
                raise SystemExit(
                    T[locale.name]["archive_schema_mismatch"].format(
                        title, len(existing_headers), len(new_headers)
                    )
                )
            for _, cells in rows:
                if existing_headers and len(cells) != len(existing_headers):
                    raise SystemExit(
                        T[locale.name]["archive_schema_mismatch"].format(
                            title, len(existing_headers), len(cells)
                        )
                    )
                text = insert_row(text, title, cells, locale.name)
            continue
        start = int(info["start"])
        end = len(body_lines)
        for index in range(start + 1, len(body_lines)):
            if body_fence[index]:
                continue
            if is_section_heading_line(body_lines[index]):
                end = index
                break
        block = "\n".join(body_lines[start:end]).rstrip()
        text = text.rstrip() + "\n\n" + block + "\n"
    return text.rstrip() + "\n"

def _parse_completed_date(value: str) -> datetime | None:
    """Parse 完成时间 / Done for archive age checks. Returns date-only datetime or None."""
    if not value or value == "-":
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="初始化、追加和检查 Markdown task-list.md")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="生成 task-list.md 模板")
    init.add_argument("--output", default="task-list.md", help="输出文件路径")
    init.add_argument(
        "--lang",
        choices=["zh", "en"],
        default="zh",
        help="模板语言：zh 中文简体（默认）、en 英文",
    )
    init.add_argument(
        "--profile",
        choices=["minimal", "planning", "extended", "development"],
        default="minimal",
        help="模板类型",
    )
    init.add_argument("--with-summary", action="store_true", help="追加统计摘要")
    init.add_argument("--force", action="store_true", help="覆盖已存在文件")
    init.add_argument("--dry-run", action="store_true", help="只打印结果，不写文件")
    init.set_defaults(func=command_init)

    add = sub.add_parser("add", help="向指定分区追加一条或多条记录")
    add.add_argument("--file", default="task-list.md", help="目标 task-list.md")
    add.add_argument("--section", help="分区标题，如 代码 Bug / Bugs（--from-json 时可省略）")
    add.add_argument("--action", help="动作枚举（--from-json 时可省略）")
    add.add_argument("--description", help="问题描述或事项（--from-json / --description-file 时可省略）")
    add.add_argument("--description-file", help="从文件或 stdin（-）读取描述，避免 shell 转义")
    add.add_argument("--status", help="状态（--from-json 时可省略）")
    add.add_argument("--notes", default=None, help="备注")
    add.add_argument("--notes-file", help="从文件或 stdin（-）读取备注，避免 shell 转义")
    add.add_argument("--found-time", help="发现时间，格式 YYYY-MM-DD HH:MM，默认当前本地时间")
    add.add_argument("--completed-time", help="完成时间，格式 YYYY-MM-DD HH:MM；未完成可填 -")
    add.add_argument("--date", help="兼容旧参数（旧单日期 schema）；回退填充发现时间，且仅在状态为完成态时回填完成时间，否则为 -")
    add.add_argument("--id", help="显式指定 ID，默认自动分配")
    add.add_argument("--priority", help="开发事项优先级，默认 P2")
    add.add_argument("--estimate", help="开发事项预计时间")
    add.add_argument(
        "--from-json",
        help="从 JSON 文件或 stdin（-）批量追加；每项需含 section/action/description/status",
    )
    add.add_argument("--no-check", action="store_true", help="跳过写后结构校验（默认写后自动 check，失败则回滚）")
    add.add_argument(
        "--no-sync-summary",
        action="store_true",
        help="跳过统计摘要自动重算（默认：文件已有统计摘要章节时自动 sync）",
    )
    add.add_argument("--dry-run", action="store_true", help="只打印将追加的行，不写文件")
    add.set_defaults(func=command_add)

    update = sub.add_parser("update", help="按 ID 更新已有记录字段")
    update.add_argument("--file", default="task-list.md", help="目标 task-list.md")
    update.add_argument("--id", required=True, help="要更新的记录 ID，如 BUG-001")
    update.add_argument("--action", help="新动作")
    update.add_argument("--description", help="新问题描述/事项")
    update.add_argument("--description-file", help="从文件或 stdin（-）读取描述")
    update.add_argument("--status", help="新状态")
    update.add_argument("--notes", help="覆盖备注")
    update.add_argument("--notes-file", help="从文件或 stdin（-）读取备注并覆盖")
    update.add_argument("--notes-append", help="追加到现有备注（以中文分号分隔）")
    update.add_argument("--notes-append-file", help="从文件或 stdin（-）读取并追加到备注")
    update.add_argument("--found-time", help="新发现时间 YYYY-MM-DD HH:MM")
    update.add_argument("--completed-time", help="新完成时间 YYYY-MM-DD HH:MM 或 -")
    update.add_argument("--priority", help="开发事项优先级")
    update.add_argument("--estimate", help="开发事项预计时间")
    update.add_argument("--no-check", action="store_true", help="跳过写后结构校验（默认写后自动 check，失败则回滚）")
    update.add_argument(
        "--no-sync-summary",
        action="store_true",
        help="跳过统计摘要自动重算（默认：文件已有统计摘要章节时自动 sync）",
    )
    update.add_argument("--dry-run", action="store_true", help="只打印更新后的行，不写文件")
    update.set_defaults(func=command_update)

    sections = sub.add_parser("sections", help="列出文件中的分区（机器可读）")
    sections.add_argument("--file", default="task-list.md", help="目标 task-list.md")
    sections.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    sections.set_defaults(func=command_sections)

    list_cmd = sub.add_parser("list", help="按 ID/状态/分区/关键词筛选记录")
    list_cmd.add_argument("--file", default="task-list.md", help="目标 task-list.md")
    list_cmd.add_argument("--id", help="精确匹配 ID")
    list_cmd.add_argument("--status", help="按状态筛选")
    list_cmd.add_argument("--section", help="按分区筛选")
    list_cmd.add_argument("--keyword", help="在整行单元格中子串搜索（大小写不敏感）")
    list_cmd.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    list_cmd.set_defaults(func=command_list)

    install_maint = sub.add_parser(
        "install-maintenance",
        help="安装会话结束同步规则到 CLAUDE.md/AGENTS.md（opt-in；可选 Stop hook）",
    )
    install_maint.add_argument("--file", default="task-list.md", help="用于定位项目根与检测语言")
    install_maint.add_argument(
        "--with-hook",
        action="store_true",
        help="同时安装 .claude/settings.json Stop hook + reminder 脚本",
    )
    install_maint.add_argument("--dry-run", action="store_true", help="只打印将执行的操作，不写文件")
    install_maint.set_defaults(func=command_install_maintenance)

    check = sub.add_parser("check", help="检查结构和枚举问题")
    check.add_argument("--file", default="task-list.md", help="目标 task-list.md")
    check.add_argument(
        "--schema",
        choices=["auto", "dual", "single"],
        default="auto",
        help="日期 schema：auto 自动检测（默认）、dual 双日期、single 单日期（合法变体，按此校验）",
    )
    check.set_defaults(func=command_check)

    summary = sub.add_parser("summary", help="输出记录数量统计")
    summary.add_argument("--file", default="task-list.md", help="目标 task-list.md")
    summary.add_argument("--write", action="store_true", help="按当前记录重算并回写统计摘要表")
    summary.add_argument("--dry-run", action="store_true", help="配合 --write 时只打印结果，不写文件")
    summary.add_argument(
        "--policy",
        choices=["auto", "by-section", "by-prefix"],
        default="auto",
        help="统计口径：auto 两种口径一致才写入（冲突时拒绝并报告双口径）、by-section 按物理分区、by-prefix 按 ID 前缀",
    )
    summary.set_defaults(func=command_summary)

    standardize = sub.add_parser("standardize", help="诊断并可选规范化已有 task-list.md")
    standardize.add_argument("--file", default="task-list.md", help="目标 task-list.md")
    standardize.add_argument(
        "--profile",
        choices=["auto", "minimal", "planning", "extended", "development"],
        default="auto",
        help="目标模板类型；auto 会按现有内容推荐",
    )
    standardize.add_argument("--report", help="写入诊断报告路径；不传则输出到 stdout")
    standardize.add_argument("--format", choices=["markdown", "json"], default="markdown", help="报告格式")
    standardize.add_argument(
        "--schema",
        choices=["auto", "dual", "single"],
        default="auto",
        help="日期 schema：auto 自动检测（默认）、dual 双日期、single 单日期（合法变体，按此校验）",
    )
    standardize.add_argument("--apply-safe-fixes", action="store_true", help="执行低风险修复：补齐缺失空分区、删除表内空行、转义单元格内未转义的 |")
    standardize.add_argument("--migrate-schema", action="store_true", help="迁移旧日期列 schema 到发现时间/完成时间 schema")
    standardize.add_argument("--fix-only", action="store_true", help="只输出修复摘要而不展开完整报告；需配合 --apply-safe-fixes 或 --migrate-schema 使用")
    standardize.add_argument("--dry-run", action="store_true", help="打印修复后的文件内容，不写回")
    standardize.set_defaults(func=command_standardize)

    archive = sub.add_parser("archive", help="将已完成且超过 N 天的记录移到归档文件")
    archive.add_argument("--file", default="task-list.md", help="目标 task-list.md")
    archive.add_argument(
        "--older-than-days",
        type=int,
        required=True,
        help="归档完成时间早于（含） as-of 往前 N 天的已完成记录",
    )
    archive.add_argument(
        "--as-of",
        help="基准日期 YYYY-MM-DD，默认今天（便于测试与复现）",
    )
    archive.add_argument(
        "--output",
        help="归档文件路径，默认 task-list-archive-YYYYMM.md（与主表同目录）",
    )
    archive.add_argument("--dry-run", action="store_true", help="只打印主表内容到 stdout，归档内容到 stderr，不写文件")
    archive.set_defaults(func=command_archive)
    return parser

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)

