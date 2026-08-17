"""Lossless legacy-schema migration."""
from __future__ import annotations

import re
from .locales import (
    T,
    Locale,
)
from .parser import _fenced_code_mask, _is_separator_row, parse_sections, split_cells
from .renderer import table_line
from .schemas import date_column_semantic, is_supported_legacy_header, is_unmappable_legacy_header, map_legacy_date_to_dual, matches_single_date_header, section_for_title

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
    fence = _fenced_code_mask(lines)
    migrated: list[str] = []
    fixes: list[str] = []
    warnings: list[str] = []
    current_title: str | None = None
    active_legacy_columns: tuple[str, ...] | None = None
    active_new_columns: tuple[str, ...] | None = None
    active_semantic: str | None = None
    priority_col = locale.dev_extended.columns[3]

    for idx, line in enumerate(lines, 1):
        if fence[idx - 1]:
            migrated.append(line)
            continue
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

