"""Domain/table fragments → Markdown lines."""
from __future__ import annotations

import re
from .locales import (
    T,
    Locale,
    Section,
)
from .parser import _code_span_ranges, _fenced_code_mask, _heading_title, _is_separator_row, _is_table_line, _table_row_id, is_section_heading_line, parse_sections, split_cells
from .schemas import _is_valid_time, matches_single_date_header, missing_sections_for_profile, profile_sections, time_column_indices
from .summary import _summary_section_start

DANGEROUS_HTML_TAGS = (
    "title",
    "details",
    "script",
    "style",
    "textarea",
    "svg",
    "html",
    "head",
    "body",
    "table",
    "iframe",
    "xmp",
    "noembed",
    "noframes",
    "plaintext",
)

DANGEROUS_HTML_TAG_RE = re.compile(
    r"</?(?:" + "|".join(DANGEROUS_HTML_TAGS) + r")(?:\s[^>]*)?/?>",
    re.IGNORECASE,
)

_CELL_LINEBREAKS = dict.fromkeys(
    map(ord, "\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029"), " "
)

def _wrap_inline_code(text: str) -> str:
    fence_len = 1
    while "`" * fence_len in text:
        fence_len += 1
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    fence = "`" * fence_len
    return f"{fence}{pad}{text}{pad}{fence}"

def _protect_dangerous_html(value: str) -> str:
    """Wrap raw flow-breaking HTML tags in inline code; leave already-fenced tags alone."""
    ranges, _ = _code_span_ranges(value)
    covered: set[int] = set()
    for start, end in ranges:
        covered.update(range(start, end))
    pieces: list[str] = []
    index = 0
    length = len(value)
    while index < length:
        if index in covered:
            end = index
            while end < length and end in covered:
                end += 1
            pieces.append(value[index:end])
            index = end
            continue
        end = index
        while end < length and end not in covered:
            end += 1
        chunk = value[index:end]
        pieces.append(
            DANGEROUS_HTML_TAG_RE.sub(lambda match: _wrap_inline_code(match.group(0)), chunk)
        )
        index = end
    return "".join(pieces)

def escape_cell(value: str) -> str:
    value = value.translate(_CELL_LINEBREAKS).strip()
    value = _protect_dangerous_html(value)
    # Escape backslashes before pipes so a logical `\|` round-trips as `\\\|` in GFM
    # (otherwise `\\` consumes the escape and the following `|` splits the column).
    value = value.replace("\\", "\\\\").replace("|", "\\|")
    return value or "-"

def render_table(section: Section) -> str:
    head = "| " + " | ".join(section.columns) + " |"
    sep = "| " + " | ".join(["---"] * len(section.columns)) + " |"
    return f"## {section.title}\n\n{head}\n{sep}\n"

def render_section_blocks(sections: list[Section]) -> str:
    """Render section tables as one block, separated by a blank line.

    Single source of truth for the gap between consecutive section tables
    (used by both build_template and add_missing_sections). A lone "\\n" join
    glues the next ``## heading`` onto the previous ``| --- |`` separator row,
    which GFM then swallows as a table row (issue #1: add_missing_sections).
    """
    return "\n\n".join(render_table(section).rstrip() for section in sections)

def render_summary(sections: list[Section], locale: Locale) -> str:
    cols = list(locale.summary_columns)
    rows = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for section in sections:
        rows.append(f"| {section.title} | 0 | 0 | 0 | 0% |")
    rows.append(f"| **{locale.total_label}** | 0 | 0 | 0 | 0% |")
    return f"## {locale.summary_section}\n\n" + "\n".join(rows) + "\n"

def build_template(profile: str, with_summary: bool, locale: Locale) -> str:
    sections = profile_sections(profile, locale)
    header = "\n".join([locale.title, "", locale.intro, "", *locale.notes])
    blocks = [header.rstrip(), render_section_blocks(sections)]
    if with_summary:
        blocks.append(render_summary(sections, locale).rstrip())
    return "\n\n".join(block for block in blocks if block) + "\n"

def table_line(cells: list[str]) -> str:
    return "| " + " | ".join(escape_cell(cell) for cell in cells) + " |"

def insert_row(text: str, section_title: str, row: list[str], lang: str = "zh") -> str:
    lines = text.splitlines()
    fence = _fenced_code_mask(lines)
    heading_index = None
    # Match headings with the same tolerance as parse_sections (^##\s+(.+?)\s*$) so that
    # irregular heading whitespace (e.g. "##   代码 Bug") still resolves; skip fenced
    # examples so a ```markdown sample cannot steal the insert point (BUG-053).
    for index, line in enumerate(lines):
        if fence[index]:
            continue
        if _heading_title(line) == section_title:
            heading_index = index
            break
    if heading_index is None:
        raise SystemExit(T[lang]["section_not_found"].format(section_title))

    section_end = len(lines)
    for index in range(heading_index + 1, len(lines)):
        if fence[index]:
            continue
        if is_section_heading_line(lines[index]):
            section_end = index
            break
    last_table = None
    for index in range(heading_index + 1, section_end):
        if fence[index]:
            continue
        if _is_table_line(lines[index]):
            last_table = index
    if last_table is not None:
        insert_at = last_table + 1
    else:
        insert_at = section_end
        while insert_at > heading_index and lines[insert_at - 1].strip() == "":
            insert_at -= 1
    line = "| " + " | ".join(escape_cell(cell) for cell in row) + " |"
    lines.insert(insert_at, line)
    return "\n".join(lines).rstrip() + "\n"

def replace_row_line(text: str, line_index: int, cells: list[str]) -> str:
    lines = text.splitlines()
    lines[line_index] = table_line(cells)
    return "\n".join(lines).rstrip() + "\n"

def append_notes(existing: str, addition: str) -> str:
    existing = (existing or "").strip()
    addition = addition.strip()
    if not addition:
        return existing or "-"
    if existing in {"", "-"}:
        return addition
    return f"{existing}；{addition}"

def build_row_for_headers(
    headers: list[str],
    section: Section,
    *,
    item_id: str,
    action: str,
    description: str,
    status: str,
    notes: str,
    found_time: str,
    completed_time: str,
    priority: str | None,
    estimate: str | None,
    single_date: str,
    locale: Locale,
    section_title: str,
) -> list[str]:
    """Build a data row aligned to the section header schema (dual/single/dev)."""
    lang = locale.name
    if headers == list(locale.dev_extended.columns):
        return [
            item_id,
            action,
            description,
            priority or "P2",
            estimate or "-",
            found_time,
            completed_time,
            status,
            notes,
        ]
    if headers == list(section.columns):
        return [item_id, action, description, found_time, completed_time, status, notes]
    # Compatible single-date shape for this section (完成日期/发现日期/开始日期/规划日期).
    if matches_single_date_header(headers, section, locale) is not None:
        return [item_id, action, description, single_date, status, notes]
    # 8-col development single-date (section may already be locale.dev_extended).
    if matches_single_date_header(headers, locale.dev_extended, locale) is not None:
        return [
            item_id,
            action,
            description,
            priority or "P2",
            estimate or "-",
            single_date,
            status,
            notes,
        ]
    raise SystemExit(T[lang]["nonstandard_header"].format(section_title, len(headers)))

def collapse_intra_table_blank_lines(text: str, locale: Locale) -> tuple[str, list[str]]:
    """Drop blank lines that sit between two table rows. Section-gap blanks are kept."""
    lines = text.splitlines()
    gaps = _intra_table_blank_gaps(lines)
    if not gaps:
        return text, []
    drop: set[int] = set()
    fixes: list[str] = []
    m = T[locale.name]
    for first_blank, item_id, gap in gaps:
        drop.update(gap)
        if item_id:
            fixes.append(m["blank_collapse_fix"].format(first_blank, item_id))
        else:
            fixes.append(m["blank_collapse_fix_noid"].format(first_blank))
    new_lines = [line for index, line in enumerate(lines) if index not in drop]
    return "\n".join(new_lines).rstrip() + "\n", fixes

def find_intra_table_blank_candidates(text: str, locale: Locale) -> list[str]:
    candidates: list[str] = []
    m = T[locale.name]
    for first_blank, item_id, _gap in _intra_table_blank_gaps(text.splitlines()):
        if item_id:
            candidates.append(m["auto_fix_blank"].format(first_blank, item_id))
        else:
            candidates.append(m["auto_fix_blank_noid"].format(first_blank))
    return candidates

def _intra_table_blank_gaps(lines: list[str]) -> list[tuple[int, str, range]]:
    """Find blank runs that sit between two `|` table rows in the same section.

    Returns (1-based first blank line, nearest record ID, 0-based index range to drop).
    Blanks between the last table row and the next `##` heading are not included.
    Fenced code blocks are ignored so Markdown table *examples* are not treated as ledger tables.
    """
    fence = _fenced_code_mask(lines)
    gaps: list[tuple[int, str, range]] = []
    last_table_idx: int | None = None
    for index, line in enumerate(lines):
        if fence[index]:
            last_table_idx = None
            continue
        if is_section_heading_line(line):
            last_table_idx = None
            continue
        if _is_table_line(line):
            if last_table_idx is not None and index > last_table_idx + 1:
                gap = range(last_table_idx + 1, index)
                if gap and all(not lines[j].strip() for j in gap):
                    item_id = _table_row_id(lines[last_table_idx]) or _table_row_id(line)
                    gaps.append((last_table_idx + 2, item_id, gap))
            last_table_idx = index
        elif line.strip():
            last_table_idx = None
    return gaps

def escape_unescaped_pipes(text: str, locale: Locale) -> tuple[str, list[str]]:
    """Rewrite data rows whose cell count exceeds the header by escaping literal pipes.

    Safe/deterministic when the merge heuristic aligns status + time columns. Rows that
    cannot be confidently repaired are left untouched.
    """
    lines = text.splitlines()
    fence = _fenced_code_mask(lines)
    fixes: list[str] = []
    headers: list[str] = []

    for index, line in enumerate(lines):
        if fence[index]:
            continue
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            headers = []
            continue
        cells = split_cells(line)
        if not cells:
            continue
        if cells[0].upper() == "ID":
            headers = cells
            continue
        if _is_separator_row(cells):
            continue
        if not headers or len(cells) <= len(headers):
            continue
        if not re.match(r"^[A-Z]+-\d{3,}$", cells[0]):
            continue
        repaired = try_repair_overwide_row(cells, len(headers), headers, locale)
        if repaired is None:
            continue
        lines[index] = table_line(repaired)
        fixes.append(
            T[locale.name]["pipe_escape_fix"].format(index + 1, repaired[0])
        )
    if not fixes:
        return text, []
    return "\n".join(lines).rstrip() + "\n", fixes

def find_pipe_escape_candidates(text: str, locale: Locale) -> list[str]:
    """Report rows that --apply-safe-fixes could escape (without mutating)."""
    candidates: list[str] = []
    sections = parse_sections(text)
    for title, info in sections.items():
        headers = list(info.get("headers") or [])
        if not headers:
            continue
        for line_no, cells in info.get("rows", []):
            if len(cells) <= len(headers):
                continue
            if not cells or not re.match(r"^[A-Z]+-\d{3,}$", cells[0]):
                continue
            repaired = try_repair_overwide_row(cells, len(headers), headers, locale)
            if repaired is not None:
                candidates.append(
                    T[locale.name]["auto_fix_pipe"].format(line_no + 1, cells[0])
                )
    return candidates

def try_repair_overwide_row(
    cells: list[str], expected: int, headers: list[str], locale: Locale
) -> list[str] | None:
    """Merge excess cells (from unescaped |) into one column when the result looks valid.

    Prefer merging into the last column (备注/Notes) — the most common place for literal
    pipes. Fall back to earlier merge points (description/item) when notes-merge fails
    the status/time heuristic.
    """
    if len(cells) <= expected or expected < 2:
        return None
    excess = len(cells) - expected
    # Prefer notes (last col), then walk left toward description.
    for merge_at in range(expected - 1, 0, -1):
        merged = cells[:merge_at] + [" | ".join(cells[merge_at : merge_at + excess + 1])] + cells[
            merge_at + excess + 1 :
        ]
        if len(merged) == expected and _row_looks_aligned(merged, headers, locale):
            return merged
    return None

def _row_looks_aligned(cells: list[str], headers: list[str], locale: Locale) -> bool:
    """Heuristic: repaired row is plausible if status is known and time cells parse."""
    if len(cells) != len(headers):
        return False
    status = cells[-2] if len(cells) >= 2 else ""
    if status not in locale.statuses:
        return False
    named = time_column_indices(headers, locale)
    for tidx in named or []:
        if 0 <= tidx < len(cells) and not _is_valid_time(cells[tidx]):
            return False
    return True

def add_missing_sections(text: str, profile: str, locale: Locale) -> tuple[str, list[str]]:
    sections = parse_sections(text)
    missing = missing_sections_for_profile(sections, profile, locale)
    if not missing:
        return text, []
    additions = render_section_blocks(missing)
    fixes = [T[locale.name]["add_section_fix"].format(section.title) for section in missing]
    lines = text.splitlines()
    summary_start = _summary_section_start(lines, locale)
    if summary_start is None:
        return text.rstrip() + "\n\n" + additions + "\n", fixes

    prefix = lines[:summary_start]
    while prefix and prefix[-1] == "":
        prefix.pop()
    suffix = lines[summary_start:]
    new_lines = prefix + [""] + additions.splitlines() + [""] + suffix
    return "\n".join(new_lines).rstrip() + "\n", fixes


def render_ledger(ledger) -> str:
    """Render a Ledger back to Markdown.

    Unmodified ledgers round-trip the original bytes. Callers that mutate rows
    still go through insert_row / replace_row_line.
    """
    return ledger.source_text

