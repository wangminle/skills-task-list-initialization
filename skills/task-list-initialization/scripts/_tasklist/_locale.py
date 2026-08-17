"""Compatibility re-export. Canonical locale data lives in ``locales.py``."""

from __future__ import annotations

from .locales import (
    DATE_COLUMN_SEMANTICS,
    DUAL_DATE_COLS,
    LOCALES,
    MAINTENANCE_RULE_MARKER,
    MAINTENANCE_RULE_MARKER_EN,
    MIGRATEABLE_DATE_SEMANTICS,
    SINGLE_DATE_ALIASES,
    SINGLE_DATE_COL,
    STATUS_SUGGESTIONS,
    T,
    TASKLIST_HOOK_MARKER,
    UNMAPPABLE_DATE_SEMANTICS,
    Locale,
    Section,
    WIKI_ID_REF_RE,
)

__all__ = [
    "Section",
    "Locale",
    "LOCALES",
    "T",
    "STATUS_SUGGESTIONS",
    "DUAL_DATE_COLS",
    "SINGLE_DATE_COL",
    "SINGLE_DATE_ALIASES",
    "DATE_COLUMN_SEMANTICS",
    "MIGRATEABLE_DATE_SEMANTICS",
    "UNMAPPABLE_DATE_SEMANTICS",
    "MAINTENANCE_RULE_MARKER",
    "MAINTENANCE_RULE_MARKER_EN",
    "TASKLIST_HOOK_MARKER",
    "WIKI_ID_REF_RE",
]
