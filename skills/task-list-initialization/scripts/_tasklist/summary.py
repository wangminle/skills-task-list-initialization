"""Summary table computation and rewrite."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from .locales import (
    Locale,
    Section,
)
from .parser import _fenced_code_mask, collect_records, is_section_heading_line, parse_sections
from .schemas import cell_at_field, section_for_title


class SummaryPolicy(str, Enum):
    """Caliber used to bucket records into summary rows (REQ-07).

    BY_SECTION counts records by their physical section; BY_PREFIX attributes each
    record to the section owning its ID prefix, so misplaced rows follow their ID.
    AUTO refuses to rewrite a summary while the two calibers disagree.
    """

    AUTO = "auto"
    BY_SECTION = "by-section"
    BY_PREFIX = "by-prefix"


@dataclass(frozen=True)
class SummaryPolicyDecision:
    """Resolved caliber plus the evidence needed to render a conflict report."""

    rows: list[tuple[str, int, int, int]]
    conflict: bool
    section_rows: list[tuple[str, int, int, int]]
    prefix_rows: list[tuple[str, int, int, int]]
    matches_existing: SummaryPolicy | None

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

_ID_PREFIX_RE = re.compile(r"^([A-Z]+)-\d+")


def _summary_section_titles(
    sections: dict, locale: Locale
) -> list[tuple[str, dict, Section | None]]:
    """Row-set titles in file order.

    Recognized sections that own an ID prefix, plus custom (non-registry) sections
    that carry a real table (BUG-076): the read-only summary already counts those
    records, so dropping them here made the written table and its 总计 undercount.
    """
    rows: list[tuple[str, dict, Section | None]] = []
    for title in sections:
        if title == locale.summary_section:
            continue
        section = section_for_title(title, locale)
        if not section:
            if sections[title].get("headers"):
                rows.append((title, sections[title], None))
            continue
        if not section.prefix:
            continue
        rows.append((title, sections[title], section))
    return rows


def _count_rows(
    text: str,
    locale: Locale,
    target_for_record,
) -> list[tuple[str, int, int, int]]:
    """Aggregate (total, done, pending) per row title using a per-record target chooser."""
    sections = parse_sections(text)
    records = collect_records(text)
    headers_by_title = {
        title: list(info.get("headers") or []) for title, info in sections.items()
    }
    row_titles = [title for title, _, _ in _summary_section_titles(sections, locale)]
    counts: dict[str, list[int]] = {title: [0, 0, 0] for title in row_titles}

    for title, _, cells in records:
        headers = headers_by_title.get(title, [])
        # REQ-06: width-mismatched rows (usually an unescaped | splitting a cell) are
        # structural anomalies already flagged by check as col_mismatch; they must not
        # feed statistics - header-indexed reads land on cell fragments, so a date or
        # effort string would surface as a status and totals would count broken rows.
        if headers and len(cells) != len(headers):
            continue
        target = target_for_record(title, cells, sections, locale)
        if target not in counts:
            continue
        # BUG-027/BUG-037: read status BY HEADER NAME, not cells[-2]. A notes cell with an
        # unescaped pipe splits the row into extra cells, so cells[-2] lands on a notes
        # fragment and the completed/pending counts (and rate) are silently wrong.
        status = cell_at_field(
            cells, headers_by_title.get(title, []), "status", locale, fallback=-2
        )
        entry = counts[target]
        entry[0] += 1
        if status in locale.completed_statuses:
            entry[1] += 1
        if status in locale.pending_statuses:
            entry[2] += 1

    return [(title, c[0], c[1], c[2]) for title, c in counts.items()]


def compute_summary_rows(text: str, locale: Locale) -> list[tuple[str, int, int, int]]:
    """By-section caliber: each record counts toward its physical section."""
    return _count_rows(text, locale, lambda title, _cells, _sections, _locale: title)


def compute_summary_rows_by_prefix(
    text: str, locale: Locale
) -> list[tuple[str, int, int, int]]:
    """By-prefix caliber: each record counts toward the section owning its ID prefix.

    Records whose ID has no parsable prefix (or whose prefix maps to no row section)
    fall back to their physical section, so both calibers share the same row set and
    only the attribution of misplaced records differs.
    """
    prefix_to_title: dict[str, str] = {}
    for row_title, _, section in _summary_section_titles(parse_sections(text), locale):
        if section is None or not section.prefix:
            continue  # custom sections own no prefix; their records stay physical
        prefix_to_title.setdefault(section.prefix, row_title)

    def target_for_record(title, cells, _sections, _loc):
        match = _ID_PREFIX_RE.match(cells[0].strip()) if cells else None
        if match:
            mapped = prefix_to_title.get(match.group(1))
            if mapped is not None:
                return mapped
        return title

    return _count_rows(text, locale, target_for_record)


def _written_rows(text: str, locale: Locale) -> dict[str, tuple[int, int, int]]:
    """The summary table currently written in the file, keyed by category title."""
    written = parse_summary_fields(text, locale)
    out: dict[str, tuple[int, int, int]] = {}
    for name, fields in written.items():
        if name == locale.total_label:
            continue
        total, done, pending = fields.get("total"), fields.get("done"), fields.get("pending")
        if isinstance(total, int) and isinstance(done, int) and isinstance(pending, int):
            out[name] = (total, done, pending)
    return out


def _rows_match_written(
    rows: list[tuple[str, int, int, int]], written: dict[str, tuple[int, int, int]]
) -> bool:
    if not written:
        return False
    computed = {title: (t, d, p) for title, t, d, p in rows}
    return computed == written


def resolve_summary_policy(
    text: str, locale: Locale, policy: SummaryPolicy
) -> SummaryPolicyDecision:
    """Compute both calibers once and resolve the effective rows for `policy`.

    AUTO: uses the shared result when both calibers agree; on conflict the caller must
    refuse to write (the decision carries both row sets and which one, if either, the
    file's current summary matches, for the conflict report).
    """
    section_rows = compute_summary_rows(text, locale)
    prefix_rows = compute_summary_rows_by_prefix(text, locale)
    conflict = section_rows != prefix_rows
    written = _written_rows(text, locale)
    matches_existing: SummaryPolicy | None = None
    if conflict:
        if _rows_match_written(prefix_rows, written):
            matches_existing = SummaryPolicy.BY_PREFIX
        elif _rows_match_written(section_rows, written):
            matches_existing = SummaryPolicy.BY_SECTION

    if policy is SummaryPolicy.BY_PREFIX:
        rows = prefix_rows
    else:
        rows = section_rows
    return SummaryPolicyDecision(
        rows=rows,
        conflict=conflict,
        section_rows=section_rows,
        prefix_rows=prefix_rows,
        matches_existing=matches_existing,
    )


def written_summary_caliber(text: str, locale: Locale) -> SummaryPolicy | None:
    """Which caliber the file's written summary matches, or None when neither does.

    BUG-069: a summary written via `--policy by-prefix` is legitimate output of this
    tool, so consumers (drift validation) must judge it against the caliber it
    actually matches instead of always assuming by-section.
    """
    written = _written_rows(text, locale)
    if not written:
        return None
    if _rows_match_written(compute_summary_rows_by_prefix(text, locale), written):
        return SummaryPolicy.BY_PREFIX
    if _rows_match_written(compute_summary_rows(text, locale), written):
        return SummaryPolicy.BY_SECTION
    return None


def summary_sync_would_change_caliber(text: str, locale: Locale) -> bool:
    """True when an automatic by-section rewrite would override an established caliber.

    Guards add/update/archive auto-sync (§5.2: the caliber must be unambiguous before a
    summary write; when in doubt, only report). A written summary that already matches
    the by-section numbers makes the rewrite a no-op, so it is not blocked.
    """
    section_rows = compute_summary_rows(text, locale)
    prefix_rows = compute_summary_rows_by_prefix(text, locale)
    if section_rows == prefix_rows:
        return False
    written = _written_rows(text, locale)
    if _rows_match_written(section_rows, written):
        return False
    return True

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

def update_summary_text(
    text: str,
    locale: Locale,
    rows: list[tuple[str, int, int, int]] | None = None,
) -> str:
    """Rewrite the summary section from `rows` (by-section caliber unless given)."""
    if rows is None:
        rows = compute_summary_rows(text, locale)
    table = render_summary_with_counts(rows, locale)
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

