"""Header profiles, date semantics, locale detection, time helpers."""
from __future__ import annotations

import argparse
import difflib
import re
from datetime import datetime
from .domain import DESCRIPTION_FIELD_ALIASES, DateSemantic, HeaderKind, ResolvedHeader
from .locales import (
    DATE_COLUMN_SEMANTICS,
    DUAL_DATE_COLS,
    LOCALES,
    MIGRATEABLE_DATE_SEMANTICS,
    SINGLE_DATE_ALIASES,
    SINGLE_DATE_COL,
    STATUS_SUGGESTIONS,
    T,
    UNMAPPABLE_DATE_SEMANTICS,
    Locale,
    Section,
)
from .parser import parse_sections

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

# Validation-side description-slot aliases, keyed by locale and by the canonical slot
# label of the section being validated. The only legacy variant is 功能开发 writing
# the slot as 功能描述 (translation sample, REQ-05). Header labels must match the
# auto-detected locale (SKILL.md locale convention): cross-language labels
# (功能描述 in an English table, Item in a Chinese one) and cross-section labels
# (事项 in 代码 Bug, which canonically uses 问题描述) stay non-standard.
_DESCRIPTION_SLOT_ALIASES: dict[str, dict[str, frozenset[str]]] = {
    "zh": {
        "问题描述": frozenset({"问题描述"}),
        "事项": frozenset({"事项", "功能描述"}),
    },
    "en": {
        "Description": frozenset({"Description"}),
        "Item": frozenset({"Item", "Feature Description"}),
    },
}


def _single_date_slot_name(headers: list[str], canonical_single: list[str], locale: Locale) -> str | None:
    """Return the actual date-column label when headers match a single-date shape, else None.

    Non-date columns must match the canonical name, except the description slot which
    accepts only the aliases registered for THIS locale and THIS canonical slot in
    _DESCRIPTION_SLOT_ALIASES — 功能描述/Feature Description is dev-section-only
    legacy compat, and everything cross-language or cross-section stays rejected.
    """
    single = SINGLE_DATE_COL[locale.name]
    aliases = set(SINGLE_DATE_ALIASES[locale.name])
    desc_slots = _DESCRIPTION_SLOT_ALIASES[locale.name]
    if len(headers) != len(canonical_single):
        return None
    date_name: str | None = None
    for actual, expected in zip(headers, canonical_single):
        if expected == single:
            if actual not in aliases:
                return None
            date_name = actual
        elif expected in desc_slots:
            if actual not in desc_slots[expected]:
                return None
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


def _is_extended_single_date_shape(headers: list[str], locale: Locale) -> bool:
    """True if headers carry the extended single-date markers (优先级/预计时间 or en)."""
    return locale.dev_extended.columns[3] in headers and locale.dev_extended.columns[4] in headers


def resolve_header(cells: list[str], section: Section, locale: Locale) -> ResolvedHeader:
    """Classify a header row (D3): dual / legacy-single / legacy-extended / unknown."""
    actual = list(cells)
    if actual == list(section.columns):
        return ResolvedHeader(HeaderKind.STANDARD_DUAL)
    if actual == list(locale.dev_extended.columns):
        return ResolvedHeader(HeaderKind.STANDARD_DUAL)
    date_name = matches_single_date_header(actual, section, locale)
    kind = HeaderKind.LEGACY_SINGLE
    # An 8-column single-date header carrying 优先级/预计时间 (Priority/Estimate) is the
    # LEGACY_EXTENDED variant no matter which section title hosts it (功能开发 or 开发事项) —
    # the distinction is the shape, not the section (REQ-04 / plan A2).
    if date_name is not None and _is_extended_single_date_shape(actual, locale):
        kind = HeaderKind.LEGACY_EXTENDED
    if date_name is None and section.prefix == "DEV":
        date_name = matches_single_date_header(actual, locale.dev_extended, locale)
        kind = HeaderKind.LEGACY_EXTENDED
    if date_name is None:
        return ResolvedHeader(HeaderKind.UNKNOWN)
    raw = date_column_semantic(date_name, locale)
    semantic = DateSemantic(raw) if raw else None
    return ResolvedHeader(kind, semantic)

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


def is_supported_record_header(headers: list[str], locale: Locale) -> bool:
    """True when *headers* matches ANY registered section's record shape (dual or single).

    A custom (non-registry) section carrying this full shape is a legitimate record
    table (BUG-076 compat: summary counts it, so per-row validation must run too).
    Anything else — no header at all, or a pseudo header like ``| ID | 问题 | 结论 |``
    whose first cell merely says ID — is NOT a record table; its ID-shaped rows
    smuggle records past per-row validation (BUG-097).
    """
    for section in locale.all_sections():
        if resolve_header(headers, section, locale).kind is not HeaderKind.UNKNOWN:
            return True
    return False

def detect_schema(text: str, locale: Locale) -> str:
    """Detect whether a file uses the dual-date or single-date schema.

    Dual takes precedence when the file is uniform. A file that mixes dual-date and
    single-date sections (legitimate per-section schemas) is reported as ``mixed`` so
    check/add can validate each section against its own header instead of failing the
    whole file (BUG-058).
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
    if has_dual and has_single:
        return "mixed"
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

def expected_sections(locale: Locale) -> dict[str, Section]:
    sections = {section.title: section for section in profile_sections("extended", locale)}
    sections[locale.dev_extended.title] = locale.dev_extended
    return sections

def section_for_title(title: str, locale: Locale) -> Section | None:
    normalized = locale.section_aliases.get(title, title)
    if normalized == locale.dev_extended.title:
        return locale.dev_extended
    return expected_sections(locale).get(normalized)

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

def prefix_for_section(title: str, locale: Locale) -> str:
    normalized = locale.section_aliases.get(title, title)
    known = expected_sections(locale).get(normalized)
    if known and known.prefix:
        return known.prefix
    if normalized == locale.dev_extended.title:
        return "DEV"
    raise SystemExit(T[locale.name]["prefix_unknown"].format(title))

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

def get_locale(lang: str) -> Locale:
    if lang not in LOCALES:
        raise SystemExit(T["zh"]["bad_lang"].format(lang))
    return LOCALES[lang]

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
        "description": DESCRIPTION_FIELD_ALIASES,
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

def normalize_time_keep_day(value: str | None, default: str, locale: Locale | None = None) -> str:
    """normalize_time, but an explicit date-only value keeps day precision on write (BUG-094).

    Validation is identical (shape + real-calendar check, both via normalize_time); only
    the landed value differs: a value the user wrote as ``YYYY-MM-DD`` lands verbatim
    instead of being padded to ``00:00``, so the precision-aware gate, the written cell
    and the reader-side comparison all see the same granularity. Padding was what turned
    a legal same-day date-only Done into a permanent "00:00 < found" inversion that also
    blocked later note-only updates (the write-path rollback treated it as a NEW issue).
    """
    if value and re.match(r"^\d{4}-\d{2}-\d{2}$", value.strip()):
        normalize_time(value, default, locale)
        return value.strip()
    return normalize_time(value, default, locale)

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
    rows still receive `--found-time` / `--date` / now (BUG-026 / REQ-05 / BUG-060).
    """
    found_raw = getattr(args, "found_time", None) or ""
    raw = ""
    if semantic == "completed":
        raw = args.date or args.completed_time or ""
        if status in locale.completed_statuses:
            return normalize_time_keep_day(raw or now, now, locale)
        return "-"
    raw = found_raw or args.date or args.completed_time or ""
    return normalize_time_keep_day(raw or now, now, locale)

def local_minute_now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")

def _try_strptime(value: str, fmt: str) -> bool:
    try:
        datetime.strptime(value, fmt)
        return True
    except ValueError:
        return False

def _parse_task_time(value: str) -> datetime | None:
    """Parse a task-list timestamp; accept zero-padded date or datetime. None if empty/-."""
    value = value.strip()
    if value in ("-", ""):
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", value):
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M")
        except ValueError:
            return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None
    return None

def _parse_task_time_precise(value: str) -> tuple[datetime, bool] | None:
    """Parse like _parse_task_time, also reporting whether the value has minute precision.

    Returns (parsed, has_time): has_time is False for date-only `YYYY-MM-DD` values,
    whose implied 00:00 is a precision artifact, not a real midnight timestamp.
    """
    value = value.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", value):
        parsed = _parse_task_time(value)
        return (parsed, True) if parsed is not None else None
    parsed = _parse_task_time(value)
    return (parsed, False) if parsed is not None else None

def times_reversed(found: str, completed: str) -> bool:
    """True only when completed < found is proven at the available precision.

    A date-only value carries day precision, so comparing its implied 00:00 against a
    minute-precision counterpart manufactures inversions out of thin air (the legacy
    single→dual migration pain: every date-only Done on the same day as a timed Found
    warned forever and needed git archaeology to clear). Mixed-precision pairs compare
    at day granularity: only a strictly earlier calendar day is a real inversion.
    """
    pf = _parse_task_time_precise(found)
    pc = _parse_task_time_precise(completed)
    if pf is None or pc is None:
        return False
    (ft, found_has_time), (ct, completed_has_time) = pf, pc
    if found_has_time and completed_has_time:
        return ct < ft
    return ct.date() < ft.date()

def _reject_reversed_times(found: str, completed: str, locale: Locale) -> None:
    if times_reversed(found, completed):
        raise SystemExit(T[locale.name]["time_reverse_write"].format(found, completed))

def _is_valid_time(value: str) -> bool:
    """True if value is "-", empty, or a zero-padded date/datetime in the task-list formats.

    Accepts both the dual-schema `YYYY-MM-DD HH:MM` and the single-schema date-only
    `YYYY-MM-DD`, but rejects unpadded values such as 2026-1-1 (BUG-066) and nonexistent
    dates such as 2026-99-99 99:99.
    """
    value = value.strip()
    if value in ("-", ""):
        return True
    return _parse_task_time(value) is not None

