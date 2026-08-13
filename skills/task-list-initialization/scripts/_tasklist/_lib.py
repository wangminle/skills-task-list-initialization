from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from ._locale import (
    DATE_COLUMN_SEMANTICS,
    DUAL_DATE_COLS,
    LOCALES,
    MAINTENANCE_RULE_MARKER,
    MAINTENANCE_RULE_MARKER_EN,
    MIGRATEABLE_DATE_SEMANTICS,
    SINGLE_DATE_ALIASES,
    SINGLE_DATE_COL,
    STATUS_SUGGESTIONS,
    TASKLIST_HOOK_MARKER,
    T,
    UNMAPPABLE_DATE_SEMANTICS,
    Locale,
    Section,
    WIKI_ID_REF_RE,
)
from .repository import atomic_write, commit_all

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


def suggest_status(raw: str, locale: Locale) -> list[str]:
    """Suggest nearest standard statuses for a non-standard value."""
    key = raw.strip().lower()
    mapped = STATUS_SUGGESTIONS.get(locale.name, {}).get(key) or STATUS_SUGGESTIONS.get(
        locale.name, {}
    ).get(raw.strip())
    if mapped:
        return [s for s in mapped if s in locale.statuses]
    # Fuzzy fallback against the official enum (excluding placeholder "-").
    candidates = sorted(s for s in locale.statuses if s != "-")
    close = difflib.get_close_matches(raw.strip(), candidates, n=2, cutoff=0.4)
    return close


def get_locale(lang: str) -> Locale:
    if lang not in LOCALES:
        raise SystemExit(T["zh"]["bad_lang"].format(lang))
    return LOCALES[lang]


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


def detect_locale(text: str) -> str:
    """Sniff a task-list's language from structural markers only (H1 + ## headings).

    Uses parse_sections / line-anchored H1 matches so a Notes or Description cell that
    mentions an English template name (e.g. "# Task Tracking List" or "## Docs") cannot
    flip a Chinese file to en. Defaults to zh.
    """
    en = LOCALES["en"]
    zh = LOCALES["zh"]
    sections = parse_sections(text)
    en_titles = {s.title for s in en.all_sections()} | {en.summary_section}
    zh_titles = {s.title for s in zh.all_sections()} | {zh.summary_section}
    en_hits = sum(1 for title in sections if title in en_titles)
    zh_hits = sum(1 for title in sections if title in zh_titles)
    if en_hits > zh_hits:
        return "en"
    if zh_hits > en_hits:
        return "zh"
    for line in text.splitlines():
        if re.match(rf"^{re.escape(en.title)}\s*$", line):
            return "en"
        if re.match(rf"^{re.escape(zh.title)}\s*$", line):
            return "zh"
    return "zh"


def to_single_date_columns(columns: tuple[str, ...], locale: Locale) -> tuple[str, ...]:
    """Collapse the dual-date columns into a single 完成日期 / Done Date column.

    Drops 发现时间/Found and renames 完成时间/Done → 完成日期/Done Date, so a 7-column
    table becomes 6 columns and a 9-column dev table becomes 8. Used only to validate a
    legitimately single-date file against a matching header — never to rewrite the file.
    """
    found, done = DUAL_DATE_COLS[locale.name]
    single = SINGLE_DATE_COL[locale.name]
    out: list[str] = []
    for col in columns:
        if col == found:
            continue
        out.append(single if col == done else col)
    return tuple(out)


def _single_date_slot_name(headers: list[str], canonical_single: list[str], locale: Locale) -> str | None:
    """Return the actual date-column label when headers match a single-date shape, else None."""
    single = SINGLE_DATE_COL[locale.name]
    aliases = set(SINGLE_DATE_ALIASES[locale.name])
    if len(headers) != len(canonical_single):
        return None
    date_name: str | None = None
    for actual, expected in zip(headers, canonical_single):
        if expected == single:
            if actual not in aliases:
                return None
            date_name = actual
        elif actual != expected:
            return None
    return date_name


def matches_single_date_header(
    headers: list[str], section: Section, locale: Locale
) -> str | None:
    """If headers are a compatible single-date shape for the section, return the date label.

    Accepts every label in SINGLE_DATE_ALIASES (完成日期/发现日期/开始日期/规划日期 and en
    equivalents). Used by check/add so the three paths share one recognition rule (BUG-026).
    """
    return _single_date_slot_name(
        headers, list(to_single_date_columns(section.columns, locale)), locale
    )


def date_column_semantic(date_header: str, locale: Locale) -> str | None:
    """Map a single-date column label to found/completed/started/planned, or None."""
    return DATE_COLUMN_SEMANTICS[locale.name].get(date_header)


def is_supported_legacy_header(cells: list[str], section: Section, locale: Locale) -> bool:
    """True iff `cells` is a losslessly-migrateable 6/8-col single-date legacy header.

    Only found/completed semantics migrate (REQ-02/REQ-03). started/planned match the
    single-date *shape* for check/add but are unmappable — use matches_single_date_header
    + date_column_semantic for those. Reordered dual-date headers return False.
    """
    date_name = matches_single_date_header(cells, section, locale)
    if date_name is None:
        return False
    return date_column_semantic(date_name, locale) in MIGRATEABLE_DATE_SEMANTICS


def is_unmappable_legacy_header(cells: list[str], section: Section, locale: Locale) -> str | None:
    """Return the date column name when the header is known but not losslessly migrateable."""
    date_name = matches_single_date_header(cells, section, locale)
    if date_name is None:
        return None
    if date_column_semantic(date_name, locale) in UNMAPPABLE_DATE_SEMANTICS:
        return date_name
    return None


def detect_schema(text: str, locale: Locale) -> str:
    """Detect whether a file uses the dual-date or single-date schema.

    Dual takes precedence: if any section carries both 发现时间 + 完成时间 (or Found +
    Done) headers, the file is dual. Otherwise a section with a single-date header
    (完成日期 / Done Date / 发现日期) marks it single. A file with neither (e.g. a fresh
    template) defaults to dual, the canonical model.
    """
    dual = DUAL_DATE_COLS[locale.name]
    single_aliases = SINGLE_DATE_ALIASES[locale.name]
    has_dual = has_single = False
    for info in parse_sections(text).values():
        headers = set(info.get("headers") or [])
        if dual[0] in headers and dual[1] in headers:
            has_dual = True
        elif any(alias in headers for alias in single_aliases):
            has_single = True
    if has_dual:
        return "dual"
    if has_single:
        return "single"
    return "dual"


def section_aliased_from(locale: Locale) -> dict[str, list[str]]:
    """Reverse lookup of a locale's section_aliases: canonical title → legacy variants."""
    result: dict[str, list[str]] = {}
    for legacy, standard in locale.section_aliases.items():
        if legacy != standard:
            result.setdefault(standard, []).append(legacy)
    return result


def profile_sections(profile: str, locale: Locale) -> list[Section]:
    sections = list(locale.base_sections)
    if profile in {"planning", "extended", "development"}:
        sections.append(locale.planning)
    if profile in {"extended", "development"}:
        sections.append(locale.opt)
        sections.append(locale.res)
    if profile == "development":
        # Replace the base DEV section (功能开发 / Features) in place with the 9-column
        # 开发事项 / Development table, preserving its position.
        features = locale.features_section()
        sections[sections.index(features)] = locale.dev_extended
    return sections


def render_table(section: Section) -> str:
    head = "| " + " | ".join(section.columns) + " |"
    sep = "| " + " | ".join(["---"] * len(section.columns)) + " |"
    return f"## {section.title}\n\n{head}\n{sep}\n"


def render_summary(sections: list[Section], locale: Locale) -> str:
    cols = list(locale.summary_columns)
    rows = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for section in sections:
        rows.append(f"| {section.title} | 0 | 0 | 0 | 0% |")
    rows.append(f"| **{locale.total_label}** | 0 | 0 | 0 | 0% |")
    return f"## {locale.summary_section}\n\n" + "\n".join(rows) + "\n"


def section_for_title(title: str, locale: Locale) -> Section | None:
    normalized = locale.section_aliases.get(title, title)
    if normalized == locale.dev_extended.title:
        return locale.dev_extended
    return expected_sections(locale).get(normalized)


def build_template(profile: str, with_summary: bool, locale: Locale) -> str:
    sections = profile_sections(profile, locale)
    header = "\n".join([locale.title, "", locale.intro, "", *locale.notes])
    parts = [header.rstrip(), ""]
    parts.extend(render_table(section).rstrip() + "\n" for section in sections)
    if with_summary:
        parts.append(render_summary(sections, locale).rstrip())
    return "\n".join(parts).rstrip() + "\n"


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
        if char == "\\" and index + 1 < length and chars[index + 1] == "|":
            current.append("|")
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


# Tags that change document flow in GFM/HTML previewers. Unknown tags (e.g. <id>)
# and comparison operators (a < b) are left alone — do not globally escape every `<`.
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
_FENCE_OPEN_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")


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
    value = value.replace("\n", " ").strip()
    value = _protect_dangerous_html(value)
    value = value.replace("|", "\\|")
    return value or "-"


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
        if _is_separator_row(cells):
            continue
        if _has_unclosed_backticks(line):
            issues.append(m["unpaired_backtick"].format(index + 1))
        html_match = DANGEROUS_HTML_TAG_RE.search(_text_outside_backticks(line))
        if html_match:
            tag_match = re.match(r"</?([A-Za-z]+)", html_match.group(0))
            tag = (tag_match.group(1) if tag_match else html_match.group(0)).lower()
            issues.append(m["raw_html"].format(index + 1, tag))
    return issues


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


def _is_separator_row(cells: list[str]) -> bool:
    """True iff cells form a markdown table separator (e.g. | --- | :--- |).

    Every cell must contain only separator characters (-, :, space), AND at least one cell
    must contain a dash or colon. This rejects all-blank rows (| | | |) which the old
    `all(set(cell) <= {-, :, ' '})` test mistook for separators because the empty string is a
    subset of every set — see BUG-039. A row with only spaces is a data row, not a separator.
    """
    if not cells:
        return False
    if not all(set(cell) <= {"-", ":", " "} for cell in cells):
        return False
    return any("-" in cell or ":" in cell for cell in cells)


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
            if cells and cells[0] == "ID":
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


def expected_sections(locale: Locale) -> dict[str, Section]:
    sections = {section.title: section for section in profile_sections("extended", locale)}
    sections[locale.dev_extended.title] = locale.dev_extended
    return sections


def find_section_by_title(title: str, sections: dict[str, dict[str, object]], locale: Locale) -> str:
    normalized = locale.section_aliases.get(title, title)
    # Collect candidate headings that should all resolve to the same section:
    #  1. the normalized title;
    #  2. the dev profile counterpart (功能开发 ↔ 开发事项 / Features ↔ Development);
    #  3. legacy/variant headings that alias to this target (reverse lookup), so a file
    #     written with 开源项目调研 matches a request for 调研事项 (and 文档事项 → 文档维护).
    candidates = [normalized]
    features = locale.features_section()
    if normalized == features.title:
        candidates.append(locale.dev_extended.title)
    elif normalized == locale.dev_extended.title:
        candidates.append(features.title)
    for variant in section_aliased_from(locale).get(normalized, []):
        if variant not in candidates:
            candidates.append(variant)
    for candidate in candidates:
        if candidate in sections:
            return candidate
    if title in sections:
        return title
    # Case-insensitive fallback: accept any capitalization of a heading actually in the file
    # (e.g. "bugs" / "BUGS" -> "Bugs"). The alias table only covers some lowercase plurals,
    # so without this the CLI reports "section not found" on natural-case English input.
    lowered = title.strip().lower()
    for heading in sections:
        if heading.lower() == lowered:
            return heading
    available = "、".join(sections) if locale.name == "zh" else ", ".join(sections)
    raise SystemExit(T[locale.name]["section_not_found_with_list"].format(title, available))


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
        return Path(file_arg).read_text(encoding="utf-8").rstrip("\n")
    if inline is not None:
        return inline
    return default


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
    """Write new_text; unless --no-check, validate and roll back on failure.

    Returns 0 on success. On check failure, restores original_text and returns 1.
    Does not print success banners — callers print 已追加/已更新 after this returns 0.
    Prints check_ok only when validation ran and passed.
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
        issues = [i for i in issues if "摘要" not in i and "Summary stale" not in i]
    if issues:
        atomic_write(path, original_text)
        print(T[locale.name]["check_failed_rollback"], file=sys.stderr)
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1
    print(T[locale.name]["check_ok"])
    return 0


def has_summary_section(text: str, locale: Locale) -> bool:
    return any(
        re.match(rf"^##\s+{re.escape(locale.summary_section)}\s*$", line)
        for line in text.splitlines()
    )


def maybe_sync_summary(text: str, locale: Locale, enabled: bool) -> tuple[str, bool]:
    """Recompute 统计摘要 when the section already exists. Never creates it."""
    if not enabled or not has_summary_section(text, locale):
        return text, False
    return update_summary_text(text, locale), True


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
    actual_rows = compute_summary_rows(text, locale)
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


def header_field_index(headers: list[str], locale: Locale) -> dict[str, int]:
    """Map logical field names to column indices for the given header row."""
    dual_found, dual_done = DUAL_DATE_COLS[locale.name]
    semantics = DATE_COLUMN_SEMANTICS[locale.name]
    found_aliases = {name for name, sem in semantics.items() if sem == "found"}
    completed_aliases = {name for name, sem in semantics.items() if sem == "completed"}
    # started/planned stay as single-date "date" columns for time validation only — they are
    # not dual-model found/completed fields (BUG-026).
    other_single = {
        name for name, sem in semantics.items() if sem in UNMAPPABLE_DATE_SEMANTICS
    }
    aliases = {
        "action": {"动作", "Action"},
        "description": {"问题描述", "事项", "Description", "Item"},
        "found_time": {dual_found, *found_aliases},
        "completed_time": {dual_done, *completed_aliases},
        "single_date": {*found_aliases, *completed_aliases, *other_single},
        "status": {"状态", "Status"},
        "notes": {"备注", "Notes"},
        "priority": {"优先级", "Priority"},
        "estimate": {"预计时间", "Estimate"},
    }
    result: dict[str, int] = {}
    for field, names in aliases.items():
        for idx, header in enumerate(headers):
            if header in names:
                result[field] = idx
                break
    return result


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


def prefix_for_section(title: str, locale: Locale) -> str:
    normalized = locale.section_aliases.get(title, title)
    known = expected_sections(locale).get(normalized)
    if known and known.prefix:
        return known.prefix
    if normalized == locale.dev_extended.title:
        return "DEV"
    raise SystemExit(T[locale.name]["prefix_unknown"].format(title))


def is_section_heading_line(line: str) -> bool:
    """True for a markdown ## heading, including tab after the hashes (`##\\tTitle`)."""
    return bool(re.match(r"^##\s+", line))


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


def local_minute_now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


def _try_strptime(value: str, fmt: str) -> bool:
    try:
        datetime.strptime(value, fmt)
        return True
    except ValueError:
        return False


def _is_valid_time(value: str) -> bool:
    """True if value is "-", empty, or a real date/datetime in the task-list formats.

    Accepts both the dual-schema `YYYY-MM-DD HH:MM` and the single-schema date-only
    `YYYY-MM-DD`, but rejects shape-valid yet nonexistent dates such as 2026-99-99 99:99.
    """
    value = value.strip()
    if value in ("-", ""):
        return True
    return any(_try_strptime(value, fmt) for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"))


_ID_LIKE = re.compile(r"^[A-Za-z]+-\d+$")


def _looks_like_id(value: str) -> bool:
    """Heuristic: does this cell LOOK like an ID (letters-digits) without being valid?

    Matches the PREFIX-NUMBER shape (e.g. bug-001, BUG-12, Bug-1) so a malformed ID in the
    first column surfaces in check instead of being silently skipped. Deliberately narrower
    than a generic \"contains a dash\": it requires leading letters then a dash then digits,
    which ordinary 描述/备注 text almost never satisfies.
    """
    return bool(_ID_LIKE.match(value.strip()))


def time_column_indices(headers: list[str], locale: Locale) -> list[int]:
    """Indices of the date/time columns in a section header, found BY NAME.

    A section may use either the dual schema (发现时间 + 完成时间 / Found + Done, both 7-col
    and 9-col dev) or the single schema (完成日期 / Done Date, 6-col / 8-col dev). A mixed
    file can carry both shapes in different sections, so time columns must be located from
    each section's own header names — never from a file-wide fixed offset like cells[-3].
    Doing otherwise mis-indexes a 6-col row as if it were 7-col and flags the 事项 value
    ("b") as an invalid time. Returns the column indices actually present (found-time first
    when present, then completed-time).
    """
    dual = DUAL_DATE_COLS[locale.name]
    single_aliases = SINGLE_DATE_ALIASES[locale.name]
    indices: list[int] = []
    for position, name in enumerate(headers):
        if name == dual[0]:
            indices.append(position)
        elif name in (dual[1], *single_aliases):
            # 完成时间 (dual) and 完成日期/发现日期 (single) all serve as the
            # completed-time slot; keep completed-time after found-time in order.
            indices.append(position)
    # Re-sort to guarantee found-time (if present) precedes completed-time, matching the
    # header's left-to-right order rather than insertion order above.
    return sorted(indices)


def normalize_time(value: str | None, default: str, locale: Locale | None = None) -> str:
    lang = (locale or LOCALES["zh"]).name
    if not value:
        return default
    value = value.strip()
    if value == "-":
        return value
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        value = f"{value} 00:00"
    if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", value):
        raise SystemExit(T[lang]["bad_time"].format(value))
    # Reject shape-valid but semantically invalid dates (e.g. 2026-99-99 99:99): the regex
    # only checks the digit pattern, so without this a nonexistent month/day/hour would be
    # written verbatim and later pass check.
    if not _try_strptime(value, "%Y-%m-%d %H:%M"):
        raise SystemExit(T[lang]["bad_time"].format(value))
    return value


def default_completed_time(status: str, now: str, locale: Locale) -> str:
    if status in locale.completed_statuses:
        return now
    return "-"


def preserve_date_precision(value: str) -> str:
    """Pass through a legacy date cell without inventing minute precision (BUG-026 / REQ-01).

    Day-only values stay `YYYY-MM-DD`; already-timed values stay as-is. Missing stays `-`.
    New writes via normalize_time may still pad 00:00 — that path is for freshly authored
    records, not historical migration.
    """
    value = (value or "").strip()
    if not value:
        return "-"
    return value


def legacy_time(value: str) -> str:
    """Deprecated shim: prefer preserve_date_precision for migration.

    Kept for single_date_cell / callers that already pass through normalize_time (which
    pads 00:00 for new records). Does NOT pad day-only values anymore (BUG-026).
    """
    return preserve_date_precision(value)


def map_legacy_date_to_dual(date_value: str, semantic: str) -> tuple[str, str]:
    """Map one legacy single-date cell onto (found_time, completed_time) by semantic.

    Never copies across semantics and never invents 00:00 (BUG-026 / REQ-01 / REQ-02).
    """
    preserved = preserve_date_precision(date_value)
    if semantic == "found":
        return preserved, "-"
    if semantic == "completed":
        return "-", preserved
    raise ValueError(f"unmigrateable date semantic: {semantic}")


def legacy_completed_time(value: str, status: str, locale: Locale) -> str:
    """Deprecated: cross-semantic copy removed (BUG-026). Prefer map_legacy_date_to_dual."""
    if status in locale.completed_statuses:
        return preserve_date_precision(value)
    return "-"


def single_date_cell(
    args: argparse.Namespace, status: str, now: str, locale: Locale, *, semantic: str = "completed"
) -> str:
    """Build the lone date column for a single-date schema row.

    completed semantic: only completed statuses get a date (pending stays `-`).
    found / started / planned semantic: the column is the record's sole date, so pending
    rows still receive `--date` / now (BUG-026 / REQ-05).
    """
    raw = args.date or args.completed_time or ""
    if semantic == "completed":
        if status in locale.completed_statuses:
            return normalize_time(raw or now, now, locale)
        return "-"
    return normalize_time(raw or now, now, locale)


def table_line(cells: list[str]) -> str:
    return "| " + " | ".join(escape_cell(cell) for cell in cells) + " |"


def insert_row(text: str, section_title: str, row: list[str], lang: str = "zh") -> str:
    lines = text.splitlines()
    heading_index = None
    # Match headings with the same tolerance as parse_sections (^##\s+(.+?)\s*$) so that
    # irregular heading whitespace (e.g. "##   代码 Bug") still resolves; an exact-string
    # compare here would reject headings that detection elsewhere accepts.
    for index, line in enumerate(lines):
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading and heading.group(1) == section_title:
            heading_index = index
            break
    if heading_index is None:
        raise SystemExit(T[lang]["section_not_found"].format(section_title))

    insert_at = len(lines)
    for index in range(heading_index + 1, len(lines)):
        if is_section_heading_line(lines[index]):
            insert_at = index
            break
    while insert_at > heading_index and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    line = "| " + " | ".join(escape_cell(cell) for cell in row) + " |"
    lines.insert(insert_at, line)
    return "\n".join(lines).rstrip() + "\n"


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
            if key not in item or item[key] in (None, ""):
                raise SystemExit(T[lang]["from_json_entry_missing"].format(index, key))
        entries.append(
            {
                "section": str(item["section"]),
                "action": str(item["action"]),
                "description": str(item["description"]),
                "status": str(item["status"]),
                "notes": str(item.get("notes") or "-"),
                "found_time": item.get("found_time") or item.get("found-time"),
                "completed_time": item.get("completed_time") or item.get("completed-time"),
                "date": item.get("date"),
                "id": item.get("id"),
                "priority": item.get("priority"),
                "estimate": item.get("estimate"),
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
    notes = str(entry.get("notes") or "-")
    ns = argparse.Namespace(
        date=date_val,
        completed_time=completed_value,
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

    text, synced = maybe_sync_summary(text, locale, not args.no_sync_summary)

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
        skip_summary_drift=args.no_sync_summary,
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
        cells[indices["completed_time"]] = normalize_time(
            args.completed_time, args.completed_time, locale
        )
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

    new_text = replace_row_line(original, line_index, cells)
    new_text, synced = maybe_sync_summary(new_text, locale, not args.no_sync_summary)
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
        skip_summary_drift=args.no_sync_summary,
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


MAINTENANCE_RULE_ZH = """## 会话结束任务同步（必须）

每次会话结束前，若本次涉及任务完成——包括但不限于 bug 修复、功能开发、代码审查、测试数据准备、文档更新、配置运维——必须：

1. 把新增条目与状态变更写入根目录 `task-list.md`，与实际进度同步；
2. 在本次最后一条回复中告知用户：记录/更新了哪些条目（ID + 简述）。
3. 写入后跑 `check`。`check` 是预览门禁：表内空行、单元格裸 HTML、不成对反引号必须失败；手改 md 后也必须再跑。

若本次未涉及任何任务完成，无需操作也无需提示。若已配置 `.claude/settings.json` 的 `Stop` hook，则由该 hook 保证每会话触发一次；**未配置时由 agent 在会话结束前自觉执行**（不要在未安装 hook 时写「由 Stop hook 保证触发」）。
"""

MAINTENANCE_RULE_EN = """## Session-end Task Sync (Required)

Before each session ends, if this session involved completing work — including but not limited to bug fixes, feature development, code review, test-data preparation, documentation updates, or operations — you must:

1. Sync new entries and status changes into the root `task-list.md`, keeping it in step with actual progress;
2. Tell the user in your final reply which entries you recorded/updated (ID + short note).
3. Run `check` after writing. `check` is the preview gate: intra-table blank lines, raw HTML in cells, and unpaired backticks must fail; re-run `check` after any hand edit.

If this session completed no work, do nothing and say nothing. If a `Stop` hook is configured in `.claude/settings.json`, that hook guarantees one trigger per session; **without a hook, the agent must run this sync on its own before ending** (do not claim a Stop-hook guarantee when none is installed).
"""

HOOK_SCRIPT_ZH = """#!/usr/bin/env bash
input="$(cat)"
session_id="$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_id") or "default")' 2>/dev/null || echo default)"
guard="/tmp/claude-tasklist-sync-${session_id}"
[ -f "$guard" ] && exit 0
touch "$guard"
python3 -c 'import json; print(json.dumps({"decision":"block","reason":"会话结束前请按 CLAUDE.md 的「会话结束任务同步」规则：若本次涉及任务完成，把新增条目与状态变更写入根目录 task-list.md 并在回复中告知用户；否则简短说明无需同步。本提醒每会话仅触发一次。"}, ensure_ascii=False))'
"""

HOOK_SCRIPT_EN = """#!/usr/bin/env bash
input="$(cat)"
session_id="$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_id") or "default")' 2>/dev/null || echo default)"
guard="/tmp/claude-tasklist-sync-${session_id}"
[ -f "$guard" ] && exit 0
touch "$guard"
python3 -c 'import json; print(json.dumps({"decision":"block","reason":"Before this session ends, follow the Session-end Task Sync rule in CLAUDE.md: if this session completed work, sync new entries and status changes into the root task-list.md and tell the user in your reply; otherwise briefly state there is nothing to sync. This reminder fires once per session."}))'
"""

# Claude Code expands ${CLAUDE_PROJECT_DIR} and also exports it; relative `.claude/hooks/...`
# breaks when the hook cwd is a subdirectory (e.g. runtime/) or an internal helper path.
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
            if "CLAUDE_PROJECT_DIR" not in cmd:
                hook["command"] = TASKLIST_HOOK_COMMAND
                changed = True
    return changed


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


def cell_at_field(
    cells: list[str], headers: list[str], field: str, locale: Locale, *, fallback: int | None = None
) -> str:
    """Read a cell value by its logical field name, located from the section header.

    Falls back to a positional index (e.g. -2 for status) only when the header has no
    recognized column name AND a fallback is given. Without a recognized header AND no
    fallback, returns "" so callers do not crash on short rows.
    """
    if headers:
        idx = header_field_index(headers, locale).get(field)
        if idx is not None and 0 <= idx < len(cells):
            return cells[idx]
    if fallback is not None:
        pos = fallback if fallback >= 0 else len(cells) + fallback
        if 0 <= pos < len(cells):
            return cells[pos]
    return ""


def infer_profile(text: str, sections: dict[str, dict[str, object]], locale: Locale) -> str:
    headings = set(sections)
    if locale.dev_extended.title in headings:
        return "development"
    for info in sections.values():
        headers = list(info.get("headers") or [])
        if locale.dev_extended.columns[3] in headers or locale.dev_extended.columns[4] in headers:
            return "development"
    extended_markers = {locale.opt.title, locale.res.title}
    if locale.name == "zh":
        extended_markers.add("开源项目调研")
    if extended_markers & headings:
        return "extended"
    if locale.planning.title in headings:
        return "planning"
    return "minimal"


def profile_rank(profile: str) -> int:
    return {"minimal": 0, "planning": 1, "extended": 2, "development": 3}[profile]


def target_profile(requested: str, inferred: str) -> str:
    if requested == "auto":
        return inferred
    return requested


def missing_sections_for_profile(
    sections: dict[str, dict[str, object]], profile: str, locale: Locale
) -> list[Section]:
    existing = {locale.section_aliases.get(title, title) for title in sections}
    missing = [
        section for section in profile_sections(profile, locale) if section.title not in existing
    ]
    if profile == "development":
        features = locale.features_section()
        # Replacing 功能开发/Features with the 9-column 开发事项/Development table is a
        # semantic migration (record remap + extra columns), not a safe auto-add. If the
        # file still has the base DEV section, do not also append dev_extended.
        if features.title in existing and locale.dev_extended.title not in existing:
            missing = [section for section in missing if section.title != locale.dev_extended.title]
    return missing


def prefix_mismatches(
    records: list[tuple[str, int, list[str]]], locale: Locale
) -> list[str]:
    issues: list[str] = []
    for title, line_no, cells in records:
        section = section_for_title(title, locale)
        if not section or not section.prefix:
            continue
        item_id = cells[0]
        if not item_id.startswith(f"{section.prefix}-"):
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
        # Detect completed time earlier than found time
        if (
            completed_time and completed_time != "-"
            and found_time and found_time != "-"
        ):
            try:
                ft = datetime.strptime(found_time, "%Y-%m-%d %H:%M")
                ct = datetime.strptime(completed_time, "%Y-%m-%d %H:%M")
                if ct < ft:
                    time_reverse_count += 1
            except ValueError:
                pass
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


def migrate_legacy_schema(text: str, locale: Locale) -> tuple[str, list[str], list[str]]:
    """Upgrade losslessly-migrateable single-date headers to dual-date (BUG-026).

    Pre-scans every section header first (MigrationPlan lite): if any section uses an
    unmappable date semantic (开始日期/规划日期) or an unknown header, refuse with a
    clear message and leave the file untouched. Only found/completed single-date
    headers are rewritten; day precision is preserved (no fabricated 00:00) and dates
    are never copied across semantics.
    """
    # --- Pass 1: plan ---
    for title, info in parse_sections(text).items():
        headers = list(info.get("headers") or [])
        if not headers or headers[0] != "ID":
            continue
        section = section_for_title(title, locale)
        if not section:
            continue
        if headers == list(section.columns):
            continue
        if is_supported_legacy_header(headers, section, locale):
            continue
        unmappable = is_unmappable_legacy_header(headers, section, locale)
        if unmappable:
            raise SystemExit(
                T[locale.name]["migrate_unmappable"].format(title, unmappable)
            )
        # Also check against dev_extended shape when the section is the features slot
        # that might carry an 8-col header under a non-dev title — rare; fall through.
        raise SystemExit(
            T[locale.name]["migrate_unknown_header"].format(title, len(headers))
        )

    lines = text.splitlines()
    migrated: list[str] = []
    fixes: list[str] = []
    warnings: list[str] = []
    current_title: str | None = None
    active_legacy_columns: tuple[str, ...] | None = None
    active_new_columns: tuple[str, ...] | None = None
    active_semantic: str | None = None
    priority_col = locale.dev_extended.columns[3]

    for idx, line in enumerate(lines, 1):
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            current_title = heading.group(1)
            active_legacy_columns = None
            active_new_columns = None
            active_semantic = None
            migrated.append(line)
            continue

        cells = split_cells(line)
        if not cells:
            migrated.append(line)
            continue

        is_separator = _is_separator_row(cells)
        if is_separator and active_new_columns:
            migrated.append("| " + " | ".join(["---"] * len(active_new_columns)) + " |")
            continue

        section = section_for_title(current_title or "", locale)
        if cells and cells[0] == "ID" and section:
            expected = list(section.columns)
            if cells == expected:
                active_legacy_columns = None
                active_new_columns = None
                active_semantic = None
                migrated.append(line)
            elif is_supported_legacy_header(cells, section, locale):
                date_name = matches_single_date_header(cells, section, locale)
                active_semantic = date_column_semantic(date_name or "", locale)
                active_legacy_columns = tuple(cells)
                active_new_columns = tuple(expected)
                fixes.append(T[locale.name]["migrate_header"].format(current_title, len(expected)))
                migrated.append(table_line(expected))
            else:
                # Pass 1 should have caught this; keep as a hard fail for safety.
                raise SystemExit(
                    T[locale.name]["migrate_unknown_header"].format(current_title, len(cells))
                )
            continue

        if not active_legacy_columns or not active_new_columns or not active_semantic:
            migrated.append(line)
            continue

        if not re.match(r"^[A-Z]+-\d{3,}$", cells[0]):
            migrated.append(line)
            continue

        if len(active_legacy_columns) == 6 and len(cells) == 6:
            found, completed = map_legacy_date_to_dual(cells[3], active_semantic)
            migrated.append(
                table_line(
                    [cells[0], cells[1], cells[2], found, completed, cells[4], cells[5]]
                )
            )
            continue

        if len(active_legacy_columns) == 8 and len(cells) == 8 and priority_col in active_legacy_columns:
            found, completed = map_legacy_date_to_dual(cells[5], active_semantic)
            migrated.append(
                table_line(
                    [
                        cells[0],
                        cells[1],
                        cells[2],
                        cells[3],
                        cells[4],
                        found,
                        completed,
                        cells[6],
                        cells[7],
                    ]
                )
            )
            continue

        # Active migration context + a data row whose cell count doesn't match the legacy
        # header — almost always an unescaped literal pipe splitting one cell in two. We
        # can't safely remap cells we can't align to columns, so leave the row untouched
        # and WARN. Without this the header migrates, the row silently stays behind, and
        # "修复完成" reads as complete while check still flags the row as a column mismatch.
        warnings.append(
            T[locale.name]["migrate_skip"].format(
                cells[0], idx, len(active_legacy_columns), len(cells)
            )
        )
        migrated.append(line)

    return "\n".join(migrated).rstrip() + "\n", fixes, warnings


def _summary_section_start(lines: list[str], locale: Locale) -> int | None:
    for index, line in enumerate(lines):
        if re.match(rf"^##\s+{re.escape(locale.summary_section)}\s*$", line):
            return index
    return None


def add_missing_sections(text: str, profile: str, locale: Locale) -> tuple[str, list[str]]:
    sections = parse_sections(text)
    missing = missing_sections_for_profile(sections, profile, locale)
    if not missing:
        return text, []
    additions = "\n".join(render_table(section).rstrip() for section in missing)
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


def escape_unescaped_pipes(text: str, locale: Locale) -> tuple[str, list[str]]:
    """Rewrite data rows whose cell count exceeds the header by escaping literal pipes.

    Safe/deterministic when the merge heuristic aligns status + time columns. Rows that
    cannot be confidently repaired are left untouched.
    """
    lines = text.splitlines()
    fixes: list[str] = []
    headers: list[str] = []

    for index, line in enumerate(lines):
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            headers = []
            continue
        cells = split_cells(line)
        if not cells:
            continue
        if cells[0] == "ID":
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
    seen_titles = Counter(re.findall(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE))
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
            elif headers != expected_cols:
                # Dual mode: also accept a compatible single-date shape when the file was
                # forced to dual incorrectly — but normally detect_schema already chose
                # single. Keep strict dual equality here.
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


def command_check(args: argparse.Namespace) -> int:
    path = Path(args.file)
    text = read_task_list(path)
    locale = get_locale(detect_locale(text))
    schema = args.schema if args.schema != "auto" else detect_schema(text, locale)
    issues = check_text(text, locale, schema)
    if issues:
        for issue in issues:
            print(issue)
        return 1
    print(T[locale.name]["check_ok"])
    return 0


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
    start = None
    for index, line in enumerate(lines):
        if re.match(rf"^##\s+{re.escape(locale.summary_section)}\s*$", line):
            start = index
            break
    if start is None:
        return text.rstrip() + "\n\n" + table + "\n"

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if is_section_heading_line(lines[index]):
            end = index
            break
    block = table.splitlines()
    tail = lines[end:]
    if tail:
        block = block + [""]
    new_lines = lines[:start] + block + tail
    return "\n".join(new_lines).rstrip() + "\n"


def command_summary(args: argparse.Namespace) -> int:
    path = Path(args.file)
    text = read_task_list(path)
    locale = get_locale(detect_locale(text))

    if args.write:
        new_text = update_summary_text(text, locale)
        if args.dry_run:
            print(new_text, end="")
            return 0
        atomic_write(path, new_text)
        print(T[locale.name]["summary_updated"].format(path))
        return 0

    records = collect_records(text)
    headers_by_title = section_headers_by_title(text)
    by_section = Counter(title for title, _, _ in records)
    # BUG-037: read status BY HEADER NAME. cells[-2] lands on a notes fragment when a notes
    # cell holds an unescaped pipe, so the status distribution printed garbage status names.
    by_status = Counter(
        cell_at_field(cells, headers_by_title.get(title, []), "status", locale, fallback=-2)
        for title, _, cells in records
        if len(cells) >= 2
    )
    m = T[locale.name]
    print(m["by_section"])
    for title, count in by_section.items():
        print(f"- {title}: {count}")
    print(m["by_status"])
    for status, count in by_status.items():
        print(f"- {status}: {count}")
    print(m["total_count"].format(len(records)))
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


def merge_archive_body(existing: str, archive_body: str) -> str:
    """Merge a new archive body into an existing archive file.

    Sections already present in the archive get the new rows appended to their existing
    table; sections not yet present are appended as whole blocks. Appending full section
    blocks unconditionally would create duplicate `## Title` sections on a second
    same-month run, which the archive file itself would then fail check on.
    """
    text = existing.rstrip() + "\n"
    body_lines = archive_body.splitlines()
    for title, info in parse_sections(archive_body).items():
        rows = info.get("rows") or []
        if not rows:
            continue
        if re.search(rf"^##\s+{re.escape(title)}\s*$", text, flags=re.MULTILINE):
            for _, cells in rows:
                text = insert_row(text, title, cells)
            continue
        start = int(info["start"])
        end = len(body_lines)
        for index in range(start + 1, len(body_lines)):
            if is_section_heading_line(body_lines[index]):
                end = index
                break
        block = "\n".join(body_lines[start:end]).rstrip()
        text = text.rstrip() + "\n\n" + block + "\n"
    return text.rstrip() + "\n"


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
            dangling.append(f"第 {line_no} 行 [[{ref_id}]]")
    if dangling:
        raise SystemExit(
            T[locale.name]["archive_dangling_refs"].format("、".join(dangling[:10]))
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
        existing = archive_path.read_text(encoding="utf-8")
        final_archive = merge_archive_body(existing, archive_body)
    else:
        final_archive = archive_body

    # Keep an existing 统计摘要 in step with the records left in the main file.
    main_text, synced = maybe_sync_summary(main_text, locale, True)

    commit_all([(archive_path, final_archive), (path, main_text)])
    print(T[locale.name]["archive_moved"].format(moved, archive_path))
    if synced:
        print(T[locale.name]["summary_synced"])
    return 0


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


