"""Summary table computation and rewrite."""
from __future__ import annotations

import re
from collections import defaultdict
from .locales import (
    Locale,
)
from .parser import _fenced_code_mask, collect_records, is_section_heading_line, parse_sections
from .schemas import cell_at_field, section_for_title

def has_summary_section(text: str, locale: Locale) -> bool:
    lines = text.splitlines()
    fence = _fenced_code_mask(lines)
    return any(
        (not fence[index])
        and bool(re.match(rf"^##\s+{re.escape(locale.summary_section)}\s*$", line))
        for index, line in enumerate(lines)
    )

def _summary_section_start(lines: list[str], locale: Locale) -> int | None:
    fence = _fenced_code_mask(lines)
    for index, line in enumerate(lines):
        if fence[index]:
            continue
        if re.match(rf"^##\s+{re.escape(locale.summary_section)}\s*$", line):
            return index
    return None

def parse_summary_fields(text: str, locale: Locale) -> dict[str, dict[str, object]]:
    """Read category -> {total, done, pending, rate} from the summary table (if present).

    The summary table has 5 columns: 分类, 总数, 已完成, 待开发/待修复, 完成率.
    total/done/pending are ints; rate is a float (percent, may be None when unparsable).
    """
    sections = parse_sections(text)
    info = sections.get(locale.summary_section)
    if not info:
        return {}
    result: dict[str, dict[str, object]] = {}
    for _, cells in info.get("rows", []):
        if len(cells) < 4:
            continue
        name = cells[0].replace("**", "").strip()
        entry: dict[str, object] = {}
        for i, key in enumerate(("total", "done", "pending")):
            raw = str(cells[i + 1]).replace(",", "").strip()
            try:
                entry[key] = int(raw)
            except ValueError:
                continue
        # 5th column: completion rate. Store as float percent (e.g. "99.6%" → 99.6).
        if len(cells) >= 5:
            rate_raw = str(cells[4]).replace(",", "").strip().rstrip("%")
            try:
                entry["rate"] = float(rate_raw)
            except ValueError:
                pass
        if entry:
            result[name] = entry
    return result

def compute_summary_rows(text: str, locale: Locale) -> list[tuple[str, int, int, int]]:
    sections = parse_sections(text)
    records = collect_records(text)
    headers_by_title = {
        title: list(info.get("headers") or []) for title, info in sections.items()
    }
    records_by_section: defaultdict[str, list[tuple[list[str], list[str]]]] = defaultdict(list)
    for title, _, cells in records:
        records_by_section[title].append((cells, headers_by_title.get(title, [])))

    rows: list[tuple[str, int, int, int]] = []
    for title in sections:
        if title == locale.summary_section:
            continue
        section = section_for_title(title, locale)
        if not section or not section.prefix:
            continue
        section_records = records_by_section.get(title, [])
        total = len(section_records)
        # BUG-027/BUG-037: read status BY HEADER NAME, not cells[-2]. A notes cell with an
        # unescaped pipe splits the row into extra cells, so cells[-2] lands on a notes
        # fragment and the completed/pending counts (and rate) are silently wrong.
        done = sum(
            1
            for cells, headers in section_records
            if cell_at_field(cells, headers, "status", locale, fallback=-2)
            in locale.completed_statuses
        )
        pending = sum(
            1
            for cells, headers in section_records
            if cell_at_field(cells, headers, "status", locale, fallback=-2)
            in locale.pending_statuses
        )
        rows.append((title, total, done, pending))
    return rows

def _compute_rate(done: int, total: int) -> float:
    """Numeric completion rate in percent, single source of truth for both render and drift.

    0 when no records; 100.0 when fully done; otherwise round(done/total*100, 1). When
    items remain pending, the rounding can still land on 100.0 (e.g. 999/1000 → 99.9,
    but 999/1001 → 99.8); a hard cap to 99.9 keeps "100%" exclusive to truly-complete
    sections so it never reads as "all done" while work is still open.
    """
    if not total:
        return 0.0
    if done >= total:
        return 100.0
    r = round(done / total * 100, 1)
    if r >= 100:
        return 99.9
    return r

def _format_rate(done: int, total: int) -> str:
    """Render the rate cell as it appears in the summary table."""
    r = _compute_rate(done, total)
    if r == int(r):
        return f"{int(r)}%"
    return f"{r}%"

def render_summary_with_counts(rows: list[tuple[str, int, int, int]], locale: Locale) -> str:
    cols = list(locale.summary_columns)
    lines = [
        f"## {locale.summary_section}",
        "",
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    total_all = done_all = pending_all = 0
    for title, total, done, pending in rows:
        lines.append(f"| {title} | {total} | {done} | {pending} | {_format_rate(done, total)} |")
        total_all += total
        done_all += done
        pending_all += pending
    lines.append(f"| **{locale.total_label}** | {total_all} | {done_all} | {pending_all} | {_format_rate(done_all, total_all)} |")
    return "\n".join(lines)

def update_summary_text(text: str, locale: Locale) -> str:
    table = render_summary_with_counts(compute_summary_rows(text, locale), locale)
    lines = text.splitlines()
    fence = _fenced_code_mask(lines)
    start = _summary_section_start(lines, locale)
    if start is None:
        return text.rstrip() + "\n\n" + table + "\n"

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if fence[index]:
            continue
        if is_section_heading_line(lines[index]):
            end = index
            break
    block = table.splitlines()
    tail = lines[end:]
    if tail:
        block = block + [""]
    new_lines = lines[:start] + block + tail
    return "\n".join(new_lines).rstrip() + "\n"

