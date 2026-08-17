"""Domain types for the task-list ledger.

These types make date semantics, header kinds, and validation issues explicit so
callers stop treating "6 vs 7 columns" as the whole schema model (REQ-11 / C1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DateSemantic(str, Enum):
    FOUND = "found"
    COMPLETED = "completed"
    STARTED = "started"
    PLANNED = "planned"


class HeaderKind(str, Enum):
    STANDARD_DUAL = "standard_dual"
    LEGACY_SINGLE = "legacy_single"
    LEGACY_EXTENDED = "legacy_extended"
    UNKNOWN = "unknown"


class SummaryPolicy(str, Enum):
    AUTO = "auto"
    BY_PREFIX = "by-prefix"
    BY_SECTION = "by-section"


class MigrationVerdict(str, Enum):
    LOSSLESS = "lossless"
    NEEDS_DECISION = "needs_decision"
    NOT_LEGACY = "not_legacy"


@dataclass(frozen=True)
class ResolvedHeader:
    kind: HeaderKind
    semantic: DateSemantic | None = None


# Single source of truth for the description-slot label aliases (REQ-05 / CHK-038 观察②):
# a legacy 功能开发 table writes the slot as 功能描述. schemas.py consumes this for both
# single-date shape matching (_single_date_slot_name) and header field indexing.
DESCRIPTION_FIELD_ALIASES = frozenset(
    {"问题描述", "事项", "功能描述", "Description", "Item", "Feature Description"}
)

_FIELD_ALIASES: dict[str, frozenset[str]] = {
    "action": frozenset({"动作", "Action"}),
    "description": DESCRIPTION_FIELD_ALIASES,
    "found_time": frozenset({"发现时间", "Found", "发现日期", "Found Date"}),
    "completed_time": frozenset({"完成时间", "Done", "完成日期", "Done Date"}),
    "single_date": frozenset(
        {"发现日期", "完成日期", "开始日期", "规划日期", "Found Date", "Done Date", "Start Date", "Plan Date"}
    ),
    "status": frozenset({"状态", "Status"}),
    "notes": frozenset({"备注", "Notes"}),
    "priority": frozenset({"优先级", "Priority"}),
    "estimate": frozenset({"预计时间", "Estimate"}),
}


def field_index_for(columns: tuple[str, ...] | list[str]) -> dict[str, int]:
    """Map logical field names to column indices. Never use cells[-2]-style access."""
    result: dict[str, int] = {}
    for field_name, names in _FIELD_ALIASES.items():
        for idx, header in enumerate(columns):
            if header in names:
                result[field_name] = idx
                break
    return result


@dataclass(frozen=True)
class SectionSchema:
    title: str
    prefix: str | None
    columns: tuple[str, ...]
    date_semantics: tuple[DateSemantic, ...]
    field_index: dict[str, int]

    @classmethod
    def from_columns(
        cls,
        title: str,
        prefix: str | None,
        columns: tuple[str, ...] | list[str],
        date_semantics: tuple[DateSemantic, ...] | None = None,
    ) -> SectionSchema:
        cols = tuple(columns)
        semantics = date_semantics
        if semantics is None:
            inferred: list[DateSemantic] = []
            for col in cols:
                if col in {"发现时间", "发现日期", "Found", "Found Date"}:
                    inferred.append(DateSemantic.FOUND)
                elif col in {"完成时间", "完成日期", "Done", "Done Date"}:
                    inferred.append(DateSemantic.COMPLETED)
                elif col in {"开始日期", "Start Date"}:
                    inferred.append(DateSemantic.STARTED)
                elif col in {"规划日期", "Plan Date"}:
                    inferred.append(DateSemantic.PLANNED)
            semantics = tuple(inferred)
        return cls(
            title=title,
            prefix=prefix,
            columns=cols,
            date_semantics=semantics,
            field_index=field_index_for(cols),
        )


@dataclass
class TaskRecord:
    item_id: str
    action: str
    description: str
    status: str
    notes: str
    section_title: str
    dates: dict[DateSemantic, str | None] = field(default_factory=dict)
    source_line: int | None = None
    cells: tuple[str, ...] = ()
    headers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: str = "error"
    line: int | None = None
    safe_fix: bool = False


@dataclass
class Ledger:
    source_text: str
    records: tuple[TaskRecord, ...] = ()
    issues: tuple[ValidationIssue, ...] = ()
    locale_name: str = "zh"
    dirty: bool = False
