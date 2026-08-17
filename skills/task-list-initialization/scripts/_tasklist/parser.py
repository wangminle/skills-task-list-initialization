"""Markdown table parsing: fences, cells, sections, records."""
from __future__ import annotations

import re
from .locales import T, Locale, WIKI_ID_REF_RE

def split_cells(line: str) -> list[str]:
    stripped = line.strip()
    # Leading | is required. Trailing | is optional (GFM/CommonMark); requiring it caused
    # silent row drops: split_cells returned [] → parse_sections skipped the line → check
    # never saw column mismatches and standardize under-counted records.
    if not stripped.startswith("|"):
        return []
    cells: list[str] = []
    current: list[str] = []
    # Body after the opening |. Strip a trailing delimiter | only when it is unescaped
    # (even number of preceding backslashes); a final \| is cell content, not a delimiter.
    body = stripped[1:]
    if body.endswith("|"):
        n = 0
        i = len(body) - 2
        while i >= 0 and body[i] == "\\":
            n += 1
            i -= 1
        if n % 2 == 0:
            body = body[:-1]
    chars = body
    index = 0
    length = len(chars)
    # Decode escaped pipes (\| → |) so the parser returns the LOGICAL cell value, not the
    # markdown syntax. escape_cell re-escapes on write, which makes split_cells/escape_cell
    # proper inverses and the migrate round-trip idempotent — otherwise a \| in 备注 gets
    # re-escaped to \\| on every pass (split_cells kept the backslash; escape_cell added
    # another). A backslash not followed by "|" is a literal backslash and is preserved.
    while index < length:
        char = chars[index]
        if char == "\\" and index + 1 < length:
            nxt = chars[index + 1]
            if nxt in ("\\", "|"):
                current.append(nxt)
                index += 2
                continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    cells.append("".join(current).strip())
    return cells

def _fenced_code_mask(lines: list[str]) -> list[bool]:
    """True for lines inside (or delimiting) a CommonMark fenced code block."""
    mask: list[bool] = []
    inside = False
    fence_char = ""
    fence_len = 0
    for line in lines:
        if inside:
            mask.append(True)
            closer = re.match(r"^( {0,3})(" + re.escape(fence_char) + r"{3,})\s*$", line)
            if closer and len(closer.group(2)) >= fence_len:
                inside = False
            continue
        match = _FENCE_OPEN_RE.match(line)
        if match:
            marker = match.group(2)
            info = match.group(3)
            if not (marker[0] == "`" and "`" in info):
                inside = True
                fence_char = marker[0]
                fence_len = len(marker)
                mask.append(True)
                continue
        mask.append(False)
    return mask

def _heading_title(line: str) -> str | None:
    """Return the ## heading title, or None if the line is not a heading."""
    match = re.match(r"^##\s+(.+?)\s*$", line)
    return match.group(1) if match else None

def _is_table_line(line: str) -> bool:
    return line.strip().startswith("|")

def _table_row_id(line: str) -> str:
    if not _is_table_line(line):
        return ""
    cells = split_cells(line)
    if cells and re.match(r"^[A-Z]+-\d{3,}$", cells[0]):
        return cells[0]
    return ""

def _backslash_escapes(text: str, index: int) -> bool:
    """True when an odd number of backslashes immediately precede text[index]."""
    slashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slashes += 1
        cursor -= 1
    return slashes % 2 == 1

def _next_unescaped_backtick_run(text: str, start: int) -> tuple[int, int] | None:
    """Return [run_start, run_end) of the next unescaped backtick run, or None."""
    index = start
    length = len(text)
    while index < length:
        if text[index] != "`":
            index += 1
            continue
        if _backslash_escapes(text, index):
            index += 1
            continue
        end = index + 1
        while end < length and text[end] == "`" and not _backslash_escapes(text, end):
            end += 1
        return index, end
    return None

def _code_span_ranges(text: str) -> tuple[list[tuple[int, int]], bool]:
    """Return complete inline-code spans [start, end) and whether any opener never closed.

    Follows CommonMark backtick-string pairing: an opener of length n closes on the next
    run of exactly n unescaped backticks with at least one character of content in between.
    A backslash-escaped backtick is literal punctuation, not a delimiter.
    """
    ranges: list[tuple[int, int]] = []
    unclosed = False
    index = 0
    length = len(text)
    while index < length:
        run = _next_unescaped_backtick_run(text, index)
        if run is None:
            break
        start, end_run = run
        run_len = end_run - start
        cursor = end_run
        closer_end = None
        while cursor < length:
            nxt = _next_unescaped_backtick_run(text, cursor)
            if nxt is None:
                break
            close_start, close_end = nxt
            if close_end - close_start == run_len and close_start > end_run:
                closer_end = close_end
                break
            cursor = close_end
        if closer_end is not None:
            ranges.append((start, closer_end))
            index = closer_end
        else:
            unclosed = True
            index = end_run
    return ranges, unclosed

def _text_outside_backticks(value: str) -> str:
    ranges, _ = _code_span_ranges(value)
    if not ranges:
        return value
    parts: list[str] = []
    cursor = 0
    for start, end in ranges:
        parts.append(value[cursor:start])
        cursor = end
    parts.append(value[cursor:])
    return "".join(parts)

def _has_unclosed_backticks(value: str) -> bool:
    _, unclosed = _code_span_ranges(value)
    return unclosed

def _looks_like_separator_attempt(cells: list[str]) -> bool:
    """True when every cell is made of dashes/colons/spaces (a separator-shaped row)."""
    if not cells:
        return False
    return all(
        cell and set(cell) <= {"-", ":", " "} and ("-" in cell or ":" in cell) for cell in cells
    )

def _is_separator_row(cells: list[str]) -> bool:
    """True iff cells form a GFM table separator (each column at least three dashes).

    `| -- |` is separator-shaped but not GFM-valid: CommonMark requires three or more
    dashes per column, so a short separator breaks preview. BUG-039 still applies —
    all-blank rows (`| | | |`) are not separators because they contain no dash/colon.
    """
    if not _looks_like_separator_attempt(cells):
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)

def parse_sections(text: str) -> dict[str, dict[str, object]]:
    sections: dict[str, dict[str, object]] = {}
    current: str | None = None
    lines = text.splitlines()
    fence = _fenced_code_mask(lines)
    for index, line in enumerate(lines):
        if fence[index]:
            continue
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            current = heading.group(1)
            sections.setdefault(current, {"start": index, "headers": [], "rows": []})
            continue
        if current and line.strip().startswith("|"):
            cells = split_cells(line)
            if not cells:
                continue
            if cells and cells[0].upper() == "ID":
                sections[current]["headers"] = cells
            elif _is_separator_row(cells):
                # A real separator row (| --- | :--- |) — skip it. BUG-039: an all-empty row
                # (| | | |, every cell "") used to match this branch because set("") <= any set,
                # so it was silently dropped as a separator and never reached check/summary.
                # _is_separator_row requires at least one cell to contain a dash or colon, which
                # distinguishes a genuine separator from an all-blank data row.
                continue
            else:
                sections[current]["rows"].append((index, cells))
    return sections

def collect_records(text: str) -> list[tuple[str, int, list[str]]]:
    records = []
    for title, info in parse_sections(text).items():
        for line_no, cells in info.get("rows", []):
            if cells and re.match(r"^[A-Z]+-\d{3,}$", cells[0]):
                records.append((title, line_no + 1, cells))
    return records

def _collect_wiki_refs(text: str) -> list[tuple[int, str]]:
    """Yield (1-based line_no, ref_id) for every [[ID]] wiki ref in data rows."""
    refs: list[tuple[int, str]] = []
    for info in parse_sections(text).values():
        for line_no, cells in info.get("rows", []):
            for cell in cells:
                for match in WIKI_ID_REF_RE.finditer(cell):
                    refs.append((line_no + 1, match.group(1)))
    return refs

def section_headers_by_title(text: str) -> dict[str, list[str]]:
    """Map each section title → its header cells (empty list when absent).

    Lets list/summary locate the 状态/Status and 备注/Notes columns BY NAME instead of
    guessing with cells[-2] / cells[-1], which mis-indexes rows with unescaped pipes in notes
    (BUG-027/BUG-037): an over-wide row's cells[-2] lands on a notes fragment, not the status.
    """
    return {
        title: list(info.get("headers") or [])
        for title, info in parse_sections(text).items()
    }

def is_section_heading_line(line: str) -> bool:
    """True for a markdown ## heading, including tab after the hashes (`##\\tTitle`)."""
    return bool(re.match(r"^##\s+", line))

def _looks_like_id(value: str) -> bool:
    """Heuristic: does this cell LOOK like an ID (letters-digits) without being valid?

    Matches the PREFIX-NUMBER shape (e.g. bug-001, BUG-12, Bug-1) so a malformed ID in the
    first column surfaces in check instead of being silently skipped. Deliberately narrower
    than a generic \"contains a dash\": it requires leading letters then a dash then digits,
    which ordinary 描述/备注 text almost never satisfies.
    """
    return bool(_ID_LIKE.match(value.strip()))

_ID_LIKE = re.compile(r"^[A-Za-z]+-\d+$")

_FENCE_OPEN_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")

def find_record_line(
    text: str, item_id: str, locale: Locale
) -> tuple[str, int, list[str], list[str]]:
    """Locate a record by ID. Returns (section_title, 0-based line index, cells, headers)."""
    sections = parse_sections(text)
    for title, info in sections.items():
        headers = list(info.get("headers") or [])
        for line_no, cells in info.get("rows", []):
            if cells and cells[0] == item_id:
                return title, line_no, list(cells), headers
    raise SystemExit(T[locale.name]["id_not_found"].format(item_id))


def parse_ledger(text: str, locale: Locale | None = None):
    """Parse Markdown into a Ledger of TaskRecords (C2).

    Records are indexed by header field names. The original text is kept so
    ``render_ledger`` can round-trip bytes for an unmodified ledger.
    """
    from .domain import DateSemantic, Ledger, TaskRecord
    from .schemas import cell_at_field, detect_locale, get_locale

    if locale is None:
        locale = get_locale(detect_locale(text))
    records: list[TaskRecord] = []
    for title, info in parse_sections(text).items():
        headers = list(info.get("headers") or [])
        for line_no, cells in info.get("rows") or []:
            if not cells or not re.match(r"^[A-Z]+-\d{3,}$", cells[0]):
                continue
            found = cell_at_field(cells, headers, "found_time", locale)
            done = cell_at_field(cells, headers, "completed_time", locale)
            dates: dict[DateSemantic, str | None] = {}
            if found and found != "-":
                dates[DateSemantic.FOUND] = found
            if done and done != "-":
                dates[DateSemantic.COMPLETED] = done
            records.append(
                TaskRecord(
                    item_id=cells[0],
                    action=cell_at_field(cells, headers, "action", locale),
                    description=cell_at_field(cells, headers, "description", locale),
                    status=cell_at_field(cells, headers, "status", locale),
                    notes=cell_at_field(cells, headers, "notes", locale) or "-",
                    section_title=title,
                    dates=dates,
                    source_line=line_no + 1,
                    cells=tuple(cells),
                    headers=tuple(headers),
                )
            )
    return Ledger(source_text=text, records=tuple(records), locale_name=locale.name)

