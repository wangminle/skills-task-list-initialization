"""Structural and business-rule checks."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from .locales import (
    T,
    Locale,
    Section,
    WIKI_ID_REF_RE,
)
from .maintenance import detect_maintenance_rule, render_maintenance_lines
from .parser import _fenced_code_mask, _has_unclosed_backticks, _heading_title, _is_separator_row, _is_table_line, _looks_like_id, _looks_like_separator_attempt, _text_outside_backticks, collect_records, parse_sections, section_headers_by_title, split_cells
from .renderer import DANGEROUS_HTML_TAG_RE, _intra_table_blank_gaps, find_intra_table_blank_candidates, find_pipe_escape_candidates
from .schemas import _is_valid_time, _parse_task_time, _single_date_slot_name, cell_at_field, detect_schema, expected_sections, header_field_index, infer_profile, local_minute_now, missing_sections_for_profile, profile_rank, section_for_title, suggest_status, target_profile, time_column_indices, to_single_date_columns
from .summary import (
    SummaryPolicy,
    _ID_PREFIX_RE,
    _compute_rate,
    _format_rate,
    compute_summary_rows,
    compute_summary_rows_by_prefix,
    has_summary_section,
    parse_summary_fields,
    written_summary_caliber,
)

def preview_safety_issues(text: str, locale: Locale) -> list[str]:
    """Flag GFM-preview breakers that parse_sections silently skips or cannot see."""
    m = T[locale.name]
    issues: list[str] = []
    lines = text.splitlines()
    for first_blank, item_id, _gap in _intra_table_blank_gaps(lines):
        if item_id:
            issues.append(m["table_blank_break"].format(first_blank, item_id))
        else:
            issues.append(m["table_blank_break_noid"].format(first_blank))
    fence = _fenced_code_mask(lines)
    for index, line in enumerate(lines):
        if fence[index] or not _is_table_line(line):
            continue
        cells = split_cells(line)
        if _looks_like_separator_attempt(cells) and not _is_separator_row(cells):
            issues.append(m["bad_separator"].format(index + 1))
            continue
        if _is_separator_row(cells):
            continue
        if _has_unclosed_backticks(line):
            issues.append(m["unpaired_backtick"].format(index + 1))
        # Match per cell, not per line (CHK-102 ②): GFM renders cells independently,
        # so an unclosed "<tag" fragment in one cell joined with a ">" in a later cell
        # forms a pseudo-tag that exists nowhere in the rendered preview. Per-cell
        # matching also mirrors escape_cell, which wraps complete tags per cell "back
        # to back" with this check - what the write path can fix, check flags.
        for cell in cells:
            html_match = DANGEROUS_HTML_TAG_RE.search(_text_outside_backticks(cell))
            if html_match:
                tag_match = re.match(r"</?([A-Za-z]+)", html_match.group(0))
                tag = (tag_match.group(1) if tag_match else html_match.group(0)).lower()
                issues.append(m["raw_html"].format(index + 1, tag))
                break
    return issues

def check_text(text: str, locale: Locale, schema: str = "dual") -> list[str]:
    issues: list[str] = []
    m = T[locale.name]
    # Scan raw lines first: parse_sections skips blanks and cannot see preview breakers.
    issues.extend(preview_safety_issues(text, locale))
    sections = parse_sections(text)
    expected_map = expected_sections(locale)
    if schema == "single":
        # Validate against the single-date header shape so a legitimately single-date file
        # passes instead of being flagged on every section.
        expected_map = {
            title: Section(section.title, section.prefix, to_single_date_columns(section.columns, locale))
            for title, section in expected_map.items()
        }
    seen_titles: Counter[str] = Counter()
    lines = text.splitlines()
    fence = _fenced_code_mask(lines)
    for index, line in enumerate(lines):
        if fence[index]:
            continue
        title = _heading_title(line)
        if title:
            seen_titles[title] += 1
    for title, count in seen_titles.items():
        if count > 1:
            issues.append(m["dup_section"].format(title, count))

    id_locations: defaultdict[str, list[int]] = defaultdict(list)
    known_ids: set[str] = set()
    wiki_refs: list[tuple[int, str]] = []  # (line_no, ref_id)

    for title, info in sections.items():
        headers = list(info.get("headers") or [])
        expected = expected_map.get(title)
        if expected and headers:
            expected_cols = list(expected.columns)
            if schema == "single":
                # Accept any SINGLE_DATE_ALIASES label in the date slot (BUG-026 / REQ-04/05).
                compatible = (
                    headers == expected_cols
                    or _single_date_slot_name(headers, expected_cols, locale) is not None
                )
                if not compatible:
                    issues.append(m["header_mismatch"].format(title))
            elif schema == "mixed":
                dual_ok = headers == expected_cols
                single_expected = list(to_single_date_columns(tuple(expected.columns), locale))
                single_ok = _single_date_slot_name(headers, single_expected, locale) is not None
                if not dual_ok and not single_ok:
                    issues.append(m["header_mismatch"].format(title))
            elif headers != expected_cols:
                issues.append(m["header_mismatch"].format(title))
        for line_no, cells in info.get("rows", []):
            if not headers:
                continue
            if len(cells) != len(headers):
                issues.append(m["col_mismatch"].format(line_no + 1, len(headers), len(cells)))
                # Still harvest [[ID]] refs from overwide rows so dangling-ref checks work.
                for cell in cells:
                    for match in WIKI_ID_REF_RE.finditer(cell):
                        wiki_refs.append((line_no + 1, match.group(1)))
                continue
            if cells and re.match(r"^[A-Z]+-\d{3,}$", cells[0]):
                id_locations[cells[0]].append(line_no + 1)
                known_ids.add(cells[0])
                if len(cells) > 1 and cells[1] not in locale.actions:
                    issues.append(m["bad_action_line"].format(line_no + 1, cells[1]))
                if len(cells) > 4:
                    status_index = -2
                    status = cells[status_index]
                    if status not in locale.statuses:
                        suggestions = suggest_status(status, locale)
                        if suggestions:
                            issues.append(
                                m["bad_status_suggest"].format(
                                    line_no + 1, status, " / ".join(suggestions)
                                )
                            )
                        else:
                            issues.append(m["bad_status_line"].format(line_no + 1, status))
                if len(cells) >= 6:
                    # Validate time cells by locating them FROM THIS SECTION'S HEADER by name
                    # (发现时间/完成时间, or 完成日期/Done Date). A mixed file can carry both
                    # dual and single sections; indexing by a file-wide fixed offset (cells[-3])
                    # would mis-index a 6-col row as 7-col and flag the 事项 value as an invalid
                    # time. When the header is non-standard (no recognized date column names),
                    # fall back to the legacy fixed-offset logic so behavior is unchanged.
                    named_indices = time_column_indices(headers, locale)
                    if named_indices:
                        time_indices = named_indices
                    elif schema == "dual":
                        # BUG-033: the old branch used [-3, -4] (negative indices), but the
                        # guard `0 <= tidx < len(cells)` is always False for negatives, so the
                        # fallback was dead code and invalid times in non-standard-header
                        # sections were silently missed. Convert to non-negative offsets.
                        time_indices = [len(cells) - 4, len(cells) - 3]
                    else:
                        time_indices = [len(cells) - 3]
                    for tidx in time_indices:
                        if 0 <= tidx < len(cells) and not _is_valid_time(cells[tidx]):
                            issues.append(m["bad_time_line"].format(line_no + 1, cells[tidx]))
                    # Hard constraint (dual-date only): incomplete status must not keep a
                    # completion timestamp. On single-date schemas the sole date column is
                    # also mapped as completed_time, and pending rows routinely carry a date
                    # there — applying this rule would falsely fail legitimate 6-col files.
                    field_idx = header_field_index(headers, locale)
                    if (
                        "found_time" in field_idx
                        and "status" in field_idx
                        and "completed_time" in field_idx
                    ):
                        status_val = cells[field_idx["status"]]
                        done_val = cells[field_idx["completed_time"]]
                        if status_val in locale.pending_statuses and done_val != "-":
                            issues.append(
                                m["active_has_time_line"].format(
                                    line_no + 1, cells[0], status_val
                                )
                            )
                for cell in cells:
                    for match in WIKI_ID_REF_RE.finditer(cell):
                        wiki_refs.append((line_no + 1, match.group(1)))
            elif cells and _looks_like_id(cells[0]):
                # A first cell shaped like an ID (letters-digits, e.g. bug-001 / BUG-12) but
                # NOT matching the strict ^[A-Z]+-\d{3,}$ form used to fall through silently:
                # it was neither counted as a record nor flagged, so check reported "passed"
                # and summary reported "总计：0". Flag it explicitly so malformed IDs surface
                # instead of hiding as un-validated rows.
                issues.append(m["bad_id_line"].format(line_no + 1, cells[0]))
            elif cells and not cells[0].strip() and any(c.strip() for c in cells[1:]):
                # BUG-039: a data row whose ID cell is empty but which carries content in later
                # columns slipped through every branch above (empty "" is not a valid ID and
                # not _looks_like_id), so check passed and summary under-counted. A non-empty
                # row with a blank ID column is almost certainly a malformed/missing-ID record
                # and must be surfaced.
                issues.append(m["bad_id_line"].format(line_no + 1, cells[0]))

    for item_id, locations in id_locations.items():
        if len(locations) > 1:
            issues.append(m["dup_id"].format(item_id, ", ".join(map(str, locations))))

    for line_no, ref_id in wiki_refs:
        if ref_id not in known_ids:
            issues.append(m["dangling_ref"].format(line_no, ref_id))
    issues.extend(summary_drift_issues(text, locale))
    return issues

def validate_action_status(action: str, status: str | None, locale: Locale) -> None:
    lang = locale.name
    if action not in locale.actions:
        raise SystemExit(T[lang]["bad_action"].format(action))
    # status may be None when the section header has no 状态/Status column (BUG-030): in that
    # case there is no status to cross-validate, so skip the status half of the check.
    if status is None:
        return
    if status not in locale.statuses:
        suggestions = suggest_status(status, locale)
        if suggestions:
            raise SystemExit(
                T[lang]["bad_status_with_suggest"].format(status, " / ".join(suggestions))
            )
        raise SystemExit(T[lang]["bad_status"].format(status))

def summary_drift_issues(text: str, locale: Locale) -> list[str]:
    """Compare summary-table total/done/pending/rate with actual record counts.

    Also checks internal consistency: done + pending must equal total for each row, and
    the written completion rate must match a recomputation within rounding tolerance.
    """
    if not has_summary_section(text, locale):
        return []
    written = parse_summary_fields(text, locale)
    if not written:
        return []
    # BUG-069: judge drift against the caliber the written table actually matches —
    # a summary produced by `summary --write --policy by-prefix` is legitimate, so
    # comparing it against by-section numbers would flag the tool's own output.
    actual_rows = compute_summary_rows(text, locale)
    if written_summary_caliber(text, locale) is SummaryPolicy.BY_PREFIX:
        actual_rows = compute_summary_rows_by_prefix(text, locale)
    actual_map = {title: (total, done, pending) for title, total, done, pending in actual_rows}
    actual_total = sum(t for t, _, _ in actual_map.values())
    actual_done = sum(d for _, d, _ in actual_map.values())
    actual_pending = sum(p for _, _, p in actual_map.values())
    m = T[locale.name]
    # Tolerance for completion-rate comparison. The rate column is rendered at 1-decimal
    # precision, so a recomputed raw value (e.g. 99.63) rounds to 99.6; allow ±0.15 to
    # absorb that without false positives, while still catching hard errors like a
    # stale "100%" that should be 99.6.
    RATE_TOLERANCE = 0.15
    issues: list[str] = []
    for title, (total, done, pending) in actual_map.items():
        if title not in written:
            continue
        w = written[title]
        if w.get("total") != total:
            issues.append(m["summary_stale"].format(title, w.get("total"), total))
        if w.get("done") != done:
            issues.append(m["summary_stale_done"].format(title, w.get("done"), done))
        if w.get("pending") != pending:
            issues.append(m["summary_stale_pending"].format(title, w.get("pending"), pending))
        # Internal consistency: done + pending should equal total
        wt, wd, wp = w.get("total"), w.get("done"), w.get("pending")
        if isinstance(wt, int) and isinstance(wd, int) and isinstance(wp, int):
            if wd + wp != wt:
                issues.append(m["summary_inconsistent"].format(title, wd, wp, wt))
            # Completion-rate drift: the written rate must match a fresh recomputation.
            wr = w.get("rate")
            if isinstance(wr, float) and isinstance(wt, int) and isinstance(wd, int):
                expected = _compute_rate(wd, wt)
                if abs(wr - expected) > RATE_TOLERANCE:
                    issues.append(
                        m["summary_stale_rate"].format(title, wr, _format_rate(wd, wt))
                    )
    # Total row
    if locale.total_label in written:
        w = written[locale.total_label]
        if w.get("total") != actual_total:
            issues.append(m["summary_stale_total"].format(w.get("total"), actual_total))
        if w.get("done") != actual_done:
            issues.append(m["summary_stale_done"].format(locale.total_label, w.get("done"), actual_done))
        if w.get("pending") != actual_pending:
            issues.append(m["summary_stale_pending"].format(locale.total_label, w.get("pending"), actual_pending))
        wt, wd, wp = w.get("total"), w.get("done"), w.get("pending")
        if isinstance(wt, int) and isinstance(wd, int) and isinstance(wp, int):
            if wd + wp != wt:
                issues.append(m["summary_inconsistent"].format(locale.total_label, wd, wp, wt))
            wr = w.get("rate")
            if isinstance(wr, float):
                expected = _compute_rate(wd, wt)
                if abs(wr - expected) > RATE_TOLERANCE:
                    issues.append(
                        m["summary_stale_rate"].format(locale.total_label, wr, _format_rate(wd, wt))
                    )
    return issues

def prefix_mismatches(
    records: list[tuple[str, int, list[str]]], locale: Locale
) -> list[str]:
    # A prefix no registry section owns is not misplacement: the by-prefix summary
    # caliber counts such records under their physical section, so warning here would
    # contradict it (check says misplaced, summary says in place). Only warn when the
    # record's prefix is a known one owned by a different section (BUG-075).
    known_prefixes = {s.prefix for s in locale.all_sections() if s.prefix}
    issues: list[str] = []
    for title, line_no, cells in records:
        section = section_for_title(title, locale)
        if not section or not section.prefix:
            continue
        item_id = cells[0]
        match = _ID_PREFIX_RE.match(item_id.strip()) if item_id.strip() else None
        record_prefix = match.group(1) if match else None
        if record_prefix is None or record_prefix not in known_prefixes:
            continue
        if item_id.startswith(f"{section.prefix}-"):
            continue
        issues.append(
            T[locale.name]["prefix_mismatch"].format(line_no, item_id, title, section.prefix)
        )
    return issues

def record_quality_warnings(
    records: list[tuple[str, int, list[str]]], locale: Locale,
    headers_by_title: dict[str, list[str]] | None = None,
) -> list[str]:
    warnings: list[str] = []
    sparse_notes = 0
    completed_without_time = 0
    active_without_completed_dash = 0
    time_reverse_count = 0
    headers_by_title = headers_by_title or {}

    # Track IDs per section for sequence-regression detection
    section_ids: dict[str, list[str]] = {}
    # Track full cell tuples for exact-duplicate detection (exclude line number)
    seen_rows: dict[tuple[str, ...], str] = {}
    duplicate_count = 0

    for title, _, cells in records:
        if len(cells) < 6:
            continue
        headers = headers_by_title.get(title, [])
        # BUG-027/BUG-037: locate status/notes/completed-time BY HEADER NAME so an unescaped
        # pipe in notes (which splits the row into extra cells) no longer mis-indexes these.
        status = cell_at_field(cells, headers, "status", locale, fallback=-2)
        notes = cell_at_field(cells, headers, "notes", locale, fallback=-1)
        completed_time = cell_at_field(cells, headers, "completed_time", locale, fallback=-3)
        found_time = cell_at_field(cells, headers, "found_time", locale, fallback=-4)
        if notes in {"", "-"}:
            sparse_notes += 1
        if status in locale.completed_statuses and completed_time == "-":
            completed_without_time += 1
        if status in locale.pending_statuses and completed_time != "-":
            active_without_completed_dash += 1
        # Detect completed time earlier than found time (datetime or date-only, BUG-067)
        if (
            completed_time and completed_time != "-"
            and found_time and found_time != "-"
        ):
            ft = _parse_task_time(found_time)
            ct = _parse_task_time(completed_time)
            if ft is not None and ct is not None and ct < ft:
                time_reverse_count += 1
        # Collect IDs per section for sequence check
        if cells and re.match(r"^[A-Z]+-\d{3,}$", cells[0]):
            section_ids.setdefault(title, []).append(cells[0])
        # Exact duplicate detection: same cells EXCLUDING the ID column
        # (different IDs with identical description/time/notes/备注 are duplicates)
        row_key = tuple(cells[1:]) if len(cells) > 1 else tuple(cells)
        if row_key in seen_rows:
            duplicate_count += 1
        else:
            seen_rows[row_key] = title

    m = T[locale.name]
    if sparse_notes:
        warnings.append(m["warn_sparse_notes"].format(sparse_notes))
    if completed_without_time:
        warnings.append(m["warn_completed_no_time"].format(completed_without_time))
    if active_without_completed_dash:
        warnings.append(m["warn_active_has_time"].format(active_without_completed_dash))
    if time_reverse_count:
        warnings.append(m["warn_time_reverse"].format(time_reverse_count))
    # ID sequence regression: flag when IDs within a section go backwards
    for title, ids in section_ids.items():
        for i in range(1, len(ids)):
            prev_num = int(ids[i - 1].split("-")[1])
            curr_num = int(ids[i].split("-")[1])
            if curr_num < prev_num:
                warnings.append(m["warn_id_not_ascending"].format(title, ids[i - 1], ids[i]))
                break  # one warning per section is enough
    if duplicate_count:
        warnings.append(m["warn_duplicate_records"].format(duplicate_count))
    return warnings


def time_reversal_issues(
    records: list[tuple[str, int, list[str]]], locale: Locale,
    headers_by_title: dict[str, list[str]] | None = None,
) -> list[str]:
    """Per-row time-order violations (completed earlier than found).

    The write path refuses NEW inversions (time_reverse_write gate), but that gate
    cannot see pre-existing rows, so legacy inversions used to pass a green check
    (CHK-103 finding 4). check surfaces them here as warnings - line-level, unlike
    the aggregate warn_time_reverse kept for standardize's report. Warning-class on
    purpose (REQ-08 philosophy): exit code unchanged, post-write auto-check never
    rolls back on these alone.
    """
    headers_by_title = headers_by_title or {}
    issues: list[str] = []
    m = T[locale.name]
    for title, line_no, cells in records:
        if len(cells) < 6:
            continue
        headers = headers_by_title.get(title, [])
        completed_time = cell_at_field(cells, headers, "completed_time", locale, fallback=-3)
        found_time = cell_at_field(cells, headers, "found_time", locale, fallback=-4)
        if not (completed_time and completed_time != "-" and found_time and found_time != "-"):
            continue
        ft = _parse_task_time(found_time)
        ct = _parse_task_time(completed_time)
        if ft is not None and ct is not None and ct < ft:
            issues.append(
                m["time_reverse_existing"].format(line_no, cells[0], found_time, completed_time)
            )
    return issues


def completed_missing_time_issues(
    records: list[tuple[str, int, list[str]]], locale: Locale,
    headers_by_title: dict[str, list[str]] | None = None,
) -> list[str]:
    """Per-row completed-status records whose Done time is still '-'.

    Same read-path blind-spot family as time_reversal_issues (CHK-103 finding 5):
    the aggregate warn_completed_no_time existed but was only consumed by
    standardize's report, so a legacy completed-without-time row passed a green
    check. Warning-class (REQ-08): exit code unchanged, post-write auto-check
    never rolls back on these alone. Sparse-notes, ID-order and exact-duplicate
    warnings deliberately stay standardize-only (style/low-risk classes).
    """
    headers_by_title = headers_by_title or {}
    issues: list[str] = []
    m = T[locale.name]
    for title, line_no, cells in records:
        if len(cells) < 6:
            continue
        headers = headers_by_title.get(title, [])
        status = cell_at_field(cells, headers, "status", locale, fallback=-2)
        completed_time = cell_at_field(cells, headers, "completed_time", locale, fallback=-3)
        if status in locale.completed_statuses and completed_time == "-":
            issues.append(
                m["completed_no_time_existing"].format(line_no, cells[0], status)
            )
    return issues


def classify_extension_recommendations(
    inferred: str,
    chosen: str,
    records: list[tuple[str, int, list[str]]],
    sections: dict[str, dict[str, object]],
    locale: Locale,
) -> list[str]:
    recommendations: list[str] = []
    headings = set(sections)
    m = T[locale.name]
    if profile_rank(inferred) > profile_rank(chosen):
        recommendations.append(m["rec_profile_higher"].format(inferred, chosen))
    if locale.name == "zh":
        if "开源项目调研" in headings:
            recommendations.append(m["rec_legacy_research"])
        if "文档事项" in headings:
            recommendations.append(m["rec_legacy_doc"])
    recommendations.extend(section_order_recommendations(list(sections), locale))
    # Optimize-section suggestion: require >= 5 optimize records AND > 5% of total
    # to avoid false positives on projects with a single optimization entry.
    optimize_count = sum(
        1 for _, _, cells in records
        if len(cells) > 1 and cells[1] == locale.action_optimize
    )
    total_count = len(records)
    if (
        optimize_count >= 5
        and total_count > 0
        and optimize_count / total_count > 0.05
    ) and locale.opt.title not in headings:
        recommendations.append(m["rec_opt_without_section"])
    if any(
        cells and cells[0].startswith("RES-") for _, _, cells in records
    ) and locale.res.title not in headings:
        recommendations.append(m["rec_res_without_section"])
    if (
        any(locale.dev_extended.columns[3] in list(info.get("headers") or []) for info in sections.values())
        and locale.dev_extended.title not in headings
    ):
        recommendations.append(m["rec_priority_without_dev"])
    return recommendations

def section_order_recommendations(headings: list[str], locale: Locale) -> list[str]:
    """Warn when known sections appear in an order that differs from the template."""
    template = [
        section.title
        for section in (*locale.base_sections, locale.planning, locale.opt, locale.res)
    ]
    rank = {title: index for index, title in enumerate(template)}
    seen: list[str] = []
    for heading in headings:
        title = locale.section_aliases.get(heading, heading)
        if title in rank:
            seen.append(title)
    previous = -1
    for title in seen:
        current = rank[title]
        if current < previous:
            return [T[locale.name]["rec_section_order"].format(" → ".join(seen))]
        previous = current
    return []

def analyze_standardization(
    text: str, requested_profile: str, file_label: str, project_root: Path, locale: Locale,
    schema_override: str = "auto",
) -> dict[str, object]:
    sections = parse_sections(text)
    records = collect_records(text)
    headers_by_title = section_headers_by_title(text)
    inferred = infer_profile(text, sections, locale)
    chosen = target_profile(requested_profile, inferred)
    schema = schema_override if schema_override != "auto" else detect_schema(text, locale)
    structural_issues = check_text(text, locale, schema)
    prefix_issues = prefix_mismatches(records, locale)
    missing = missing_sections_for_profile(sections, chosen, locale)
    quality = record_quality_warnings(records, locale, headers_by_title)
    recommendations = classify_extension_recommendations(inferred, chosen, records, sections, locale)
    if schema == "single":
        recommendations.append(T[locale.name]["rec_single_date_schema"])
    id_counts = Counter(
        cells[0] for _, _, cells in records if cells and re.match(r"^[A-Z]+-\d{3,}$", cells[0])
    )
    if any(count > 1 for count in id_counts.values()):
        recommendations.append(T[locale.name]["rec_dup_id_mapping"])
    auto_fixes = [T[locale.name]["auto_fix_candidate"].format(section.title) for section in missing]
    auto_fixes.extend(find_pipe_escape_candidates(text, locale))
    auto_fixes.extend(find_intra_table_blank_candidates(text, locale))
    headings = list(sections)
    maintenance = detect_maintenance_rule(project_root)
    return {
        "lang": locale.name,
        "schema": schema,
        "file": file_label,
        "generated_at": local_minute_now(),
        "record_count": len(records),
        "current_profile": inferred,
        "recommended_profile": chosen,
        "sections": headings,
        "missing_sections": [section.title for section in missing],
        "structural_issues": structural_issues,
        "classification_issues": prefix_issues,
        "quality_warnings": quality,
        "recommendations": recommendations,
        "auto_fix_candidates": auto_fixes,
        "maintenance": maintenance,
    }

def render_markdown_report(
    report: dict[str, object], applied_fixes: list[str] | None, locale: Locale
) -> str:
    applied_fixes = applied_fixes or []
    lang = locale.name
    m = T[lang]

    def bullet(items: object, empty_key: str = "empty") -> str:
        values = list(items or [])
        if not values:
            return f"- {m[empty_key]}"
        return "\n".join(f"- {item}" for item in values)

    return "\n".join(
        [
            m["report_title"],
            "",
            f"- {m['file']}：{report['file']}" if lang == "zh" else f"- {m['file']}: {report['file']}",
            f"- {m['generated_at']}：{report['generated_at']}" if lang == "zh" else f"- {m['generated_at']}: {report['generated_at']}",
            f"- {m['current_profile']}：{report['current_profile']}" if lang == "zh" else f"- {m['current_profile']}: {report['current_profile']}",
            f"- {m['recommended_profile']}：{report['recommended_profile']}" if lang == "zh" else f"- {m['recommended_profile']}: {report['recommended_profile']}",
            f"- {m['record_count']}：{report['record_count']}" if lang == "zh" else f"- {m['record_count']}: {report['record_count']}",
            "",
            m["sec_structure"],
            "",
            bullet(report["structural_issues"]),
            "",
            m["sec_classification"],
            "",
            bullet(report["classification_issues"]),
            "",
            m["sec_completeness"],
            "",
            bullet(report["quality_warnings"]),
            "",
            m["sec_recommendations"],
            "",
            bullet(report["recommendations"]),
            "",
            m["sec_autofix"],
            "",
            bullet(report["auto_fix_candidates"]),
            "",
            m["sec_maintenance"],
            "",
            "\n".join(render_maintenance_lines(report.get("maintenance") or {}, locale)),
            "",
            m["sec_applied"],
            "",
            bullet(applied_fixes),
            "",
        ]
    )

def _has_structural_issues(text: str, locale: Locale) -> bool:
    """True when check would fail for reasons other than a stale summary table."""
    schema = detect_schema(text, locale)
    issues = check_text(text, locale, schema)
    drift = set(summary_drift_issues(text, locale))
    return any(issue not in drift for issue in issues)


_ISSUE_FRAGMENTS = (
    ("含裸 HTML", "raw_html"),
    ("raw HTML tag", "raw_html"),
    ("反引号未闭合", "unclosed_backtick"),
    ("unclosed", "unclosed_backtick"),
    ("被空行切断", "intra_table_blank"),
    ("blank line", "intra_table_blank"),
    ("表格分隔行", "bad_separator"),
    ("separator is not GFM", "bad_separator"),
    ("重复章节", "duplicate_section"),
    ("Duplicate section", "duplicate_section"),
    ("表头与标准不一致", "header_mismatch"),
    ("Header does not match", "header_mismatch"),
    ("表格列数异常", "column_count"),
    ("Column count mismatch", "column_count"),
    ("动作不在枚举中", "bad_action"),
    ("Action not in enum", "bad_action"),
    ("状态不在建议枚举中", "bad_status"),
    ("Status not in suggested enum", "bad_status"),
    ("时间不合法", "bad_time"),
    ("Invalid time", "bad_time"),
    ("完成时间不是", "pending_has_completed_time"),
    ("悬空引用", "dangling_ref"),
    ("Dangling reference", "dangling_ref"),
    ("重复 ID", "duplicate_id"),
    ("Duplicate ID", "duplicate_id"),
    ("ID 格式非法", "bad_id"),
    ("invalid ID", "bad_id"),
    ("摘要表", "summary_drift"),
    ("Summary stale", "summary_drift"),
    ("Summary inconsistent", "summary_drift"),
    ("Summary rate", "summary_drift"),
    ("期望前缀", "prefix_mismatch"),
    ("expected prefix", "prefix_mismatch"),
)


def _code_for_message(message: str, locale: Locale) -> str:
    for fragment, code in _ISSUE_FRAGMENTS:
        if fragment in message:
            return code
    return "other"


def validate_ledger(ledger, schema: str = "auto") -> list:
    """Return structured ValidationIssue values for a parsed ledger (C3)."""
    from .domain import ValidationIssue
    from .parser import collect_records
    from .schemas import detect_schema, get_locale

    locale = get_locale(ledger.locale_name)
    text = ledger.source_text
    resolved = schema if schema != "auto" else detect_schema(text, locale)
    issues: list[ValidationIssue] = []
    for message in check_text(text, locale, resolved):
        code = _code_for_message(message, locale)
        line = None
        match = re.search(r"(?:第 |[Ll]ine )(\d+)", message)
        if match:
            line = int(match.group(1))
        issues.append(
            ValidationIssue(code=code, message=message, severity="error", line=line)
        )
    for message in prefix_mismatches(collect_records(text), locale):
        issues.append(
            ValidationIssue(code="prefix_mismatch", message=message, severity="warning")
        )
    # REQ-12: a 状态=- row is now a hard bad_status error from check_text; the old
    # placeholder_status warning would double-report the same row (CHK-037 观察①).
    return issues

