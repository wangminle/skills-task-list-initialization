#!/usr/bin/env python3
"""Create and maintain Markdown task-list files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ACTIONS = {"修复", "开发", "优化", "调整", "规划", "检查", "文档", "运维"}
STATUSES = {"待修复", "已修复", "待开发", "进行中", "已完成", "已关闭", "已解决", "-"}
COMPLETED_STATUSES = {"已修复", "已完成", "已关闭", "已解决"}
PENDING_STATUSES = {"待修复", "待开发", "进行中"}

# Maintenance-rule detection markers. Must stay in sync with references/maintenance-rule.md:
# the canonical rule block always carries this heading; the Stop hook command always names
# the tasklist reminder script. standardize uses these to report whether the maintenance
# rule / hook are already installed in the target project (read-only detection).
MAINTENANCE_RULE_MARKER = "会话结束任务同步"
TASKLIST_HOOK_MARKER = "tasklist"


@dataclass(frozen=True)
class Section:
    title: str
    prefix: str | None
    columns: tuple[str, ...]


BASE_SECTIONS = [
    Section("代码 Bug", "BUG", ("ID", "动作", "问题描述", "发现时间", "完成时间", "状态", "备注")),
    Section("调整事项", "ADJ", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注")),
    Section("检查事项", "CHK", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注")),
    Section("测试数据", "TST", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注")),
    Section("文档维护", "DOC", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注")),
    Section("功能开发", "DEV", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注")),
    Section("配置运维", "OPS", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注")),
]

PLANNING_SECTION = Section("规划事项", "PLN", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注"))
OPT_SECTION = Section("优化事项", "OPT", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注"))
RES_SECTION = Section("调研事项", "RES", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注"))
DEV_EXTENDED_SECTION = Section(
    "开发事项", "DEV", ("ID", "动作", "事项", "优先级", "预计时间", "发现时间", "完成时间", "状态", "备注")
)


HEADER = """# 任务跟踪列表

记录本项目所有任务：代码 bug、bug 转需求、新增需求、需求调整、功能开发、代码审查、测试数据、文档维护、配置运维等。

> 说明：本文件是当前项目的任务清单。所有新增事项、状态变更和完成记录都应同步写入本文件。
> 字段说明：动作字段只允许以下 8 个固定枚举：修复、开发、优化、调整、规划、检查、文档、运维。
> 时间说明：发现时间和完成时间分开记录，格式为 YYYY-MM-DD HH:MM，使用机器本地时区的 24 小时制时间；未完成事项的完成时间填 -。
> 归并规则：审计、复核、核查、审查、验证、评估统一记为“检查”；重构、清理统一记为“优化”；方案、梳理统一记为“规划”；记录类文档事项统一记为“文档”。
"""


SECTION_ALIASES = {
    "代码Bug": "代码 Bug",
    "bug": "代码 Bug",
    "BUG": "代码 Bug",
    "开发": "功能开发",
    "功能": "功能开发",
    "功能开发": "功能开发",
    "开发事项": "开发事项",
    "文档": "文档维护",
    "文档事项": "文档维护",
    "文档维护": "文档维护",
    "运维": "配置运维",
    "配置": "配置运维",
    "配置运维": "配置运维",
    "开源项目调研": "调研事项",
}

# Reverse lookup of SECTION_ALIASES: canonical title → variant/legacy headings that alias
# to it. Used by find_section_by_title so a file written with a legacy heading (e.g.
# 开源项目调研 / 文档事项) still matches a request for the canonical name (调研事项 / 文档维护).
SECTION_ALIASED_FROM: dict[str, list[str]] = {}
for _legacy, _standard in SECTION_ALIASES.items():
    if _legacy != _standard:
        SECTION_ALIASED_FROM.setdefault(_standard, []).append(_legacy)


def profile_sections(profile: str) -> list[Section]:
    sections = list(BASE_SECTIONS)
    if profile in {"planning", "extended", "development"}:
        sections.append(PLANNING_SECTION)
    if profile in {"extended", "development"}:
        sections.append(OPT_SECTION)
        sections.append(RES_SECTION)
    if profile == "development":
        sections = [s for s in sections if s.title != "功能开发"]
        sections.insert(5, DEV_EXTENDED_SECTION)
    return sections


def render_table(section: Section) -> str:
    head = "| " + " | ".join(section.columns) + " |"
    sep = "| " + " | ".join(["---"] * len(section.columns)) + " |"
    return f"## {section.title}\n\n{head}\n{sep}\n"


def render_summary(sections: list[Section]) -> str:
    rows = [
        "| 分类 | 总数 | 已完成 | 待开发/待修复 | 完成率 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for section in sections:
        rows.append(f"| {section.title} | 0 | 0 | 0 | 0% |")
    rows.append("| **总计** | 0 | 0 | 0 | 0% |")
    return "## 统计摘要\n\n" + "\n".join(rows) + "\n"


def section_for_title(title: str) -> Section | None:
    normalized = SECTION_ALIASES.get(title, title)
    if normalized == "开发事项":
        return DEV_EXTENDED_SECTION
    return expected_sections().get(normalized)


def build_template(profile: str, with_summary: bool) -> str:
    sections = profile_sections(profile)
    parts = [HEADER.rstrip(), ""]
    parts.extend(render_table(section).rstrip() + "\n" for section in sections)
    if with_summary:
        parts.append(render_summary(sections).rstrip())
    return "\n".join(parts).rstrip() + "\n"


def split_cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in stripped[1:-1]:
        if char == "\\" and not escaped:
            escaped = True
            current.append(char)
            continue
        if char == "|" and not escaped:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        escaped = False
    cells.append("".join(current).strip())
    return cells


def escape_cell(value: str) -> str:
    value = value.replace("\n", " ").strip()
    value = value.replace("|", "\\|")
    return value or "-"


def parse_sections(text: str) -> dict[str, dict[str, object]]:
    sections: dict[str, dict[str, object]] = {}
    current: str | None = None
    for index, line in enumerate(text.splitlines()):
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
            elif cells and not all(set(cell) <= {"-", ":", " "} for cell in cells):
                sections[current]["rows"].append((index, cells))
    return sections


def expected_sections() -> dict[str, Section]:
    sections = {section.title: section for section in profile_sections("extended")}
    sections[DEV_EXTENDED_SECTION.title] = DEV_EXTENDED_SECTION
    return sections


def find_section_by_title(title: str, sections: dict[str, dict[str, object]]) -> str:
    normalized = SECTION_ALIASES.get(title, title)
    # Collect candidate headings that should all resolve to the same section:
    #  1. the normalized title;
    #  2. the dev profile counterpart (功能开发 ↔ 开发事项);
    #  3. legacy/variant headings that alias to this target (reverse lookup), so a file
    #     written with 开源项目调研 matches a request for 调研事项 (and 文档事项 → 文档维护).
    candidates = [normalized]
    if normalized == "功能开发":
        candidates.append("开发事项")
    elif normalized == "开发事项":
        candidates.append("功能开发")
    for variant in SECTION_ALIASED_FROM.get(normalized, []):
        if variant not in candidates:
            candidates.append(variant)
    for candidate in candidates:
        if candidate in sections:
            return candidate
    if title in sections:
        return title
    raise SystemExit(f"未找到分区：{title}")


def prefix_for_section(title: str, headers: list[str]) -> str:
    normalized = SECTION_ALIASES.get(title, title)
    known = expected_sections().get(normalized)
    if known and known.prefix:
        return known.prefix
    if normalized == "开发事项":
        return "DEV"
    raise SystemExit(f"无法推断分区 ID 前缀：{title}")


def next_id(prefix: str, text: str) -> str:
    ids = re.findall(rf"\b{re.escape(prefix)}-(\d{{3,}})\b", text)
    number = max((int(item) for item in ids), default=0) + 1
    return f"{prefix}-{number:03d}"


def local_minute_now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


def normalize_time(value: str | None, default: str) -> str:
    if not value:
        return default
    value = value.strip()
    if value == "-":
        return value
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return f"{value} 00:00"
    if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", value):
        raise SystemExit(f"时间格式应为 YYYY-MM-DD HH:MM：{value}")
    return value


def default_completed_time(status: str, now: str) -> str:
    if status in COMPLETED_STATUSES:
        return now
    return "-"


def legacy_time(value: str) -> str:
    value = value.strip()
    if value == "-":
        return value
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return f"{value} 00:00"
    if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", value):
        return value
    return value


def legacy_completed_time(value: str, status: str) -> str:
    if status in COMPLETED_STATUSES:
        return legacy_time(value)
    return "-"


def table_line(cells: list[str]) -> str:
    return "| " + " | ".join(escape_cell(cell) for cell in cells) + " |"


def insert_row(text: str, section_title: str, row: list[str]) -> str:
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
        raise SystemExit(f"未找到分区：{section_title}")

    insert_at = len(lines)
    for index in range(heading_index + 1, len(lines)):
        if lines[index].startswith("## "):
            insert_at = index
            break
    while insert_at > heading_index and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    line = "| " + " | ".join(escape_cell(cell) for cell in row) + " |"
    lines.insert(insert_at, line)
    return "\n".join(lines).rstrip() + "\n"


def command_init(args: argparse.Namespace) -> int:
    output = Path(args.output)
    text = build_template(args.profile, args.with_summary)
    if args.dry_run:
        print(text, end="")
        return 0
    if output.exists() and not args.force:
        print(f"目标文件已存在，使用 --force 覆盖：{output}", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(f"已生成：{output}")
    return 0


def command_add(args: argparse.Namespace) -> int:
    path = Path(args.file)
    text = path.read_text(encoding="utf-8")
    sections = parse_sections(text)
    section_title = find_section_by_title(args.section, sections)
    headers = list(sections[section_title].get("headers") or [])
    if not headers:
        raise SystemExit(f"分区缺少表头：{section_title}")
    prefix = prefix_for_section(section_title, headers)
    item_id = args.id or next_id(prefix, text)
    now = local_minute_now()
    found_time = normalize_time(args.found_time or args.date, now)
    # --date is a legacy single-date fallback. It always seeds 发现时间; for 完成时间 it only
    # backfills when the status is a completed state (mirroring legacy_completed_time), so
    # 未完成 records keep 完成时间 = "-" instead of a self-contradictory date.
    completed_value = args.completed_time
    if not completed_value and args.status in COMPLETED_STATUSES:
        completed_value = args.date
    completed_time = normalize_time(completed_value, default_completed_time(args.status, now))
    description = args.description
    notes = args.notes or "-"

    if args.action not in ACTIONS:
        raise SystemExit(f"动作不在枚举中：{args.action}")
    if args.status not in STATUSES:
        raise SystemExit(f"状态不在建议枚举中：{args.status}")

    if headers == list(DEV_EXTENDED_SECTION.columns):
        row = [
            item_id,
            args.action,
            description,
            args.priority or "P2",
            args.estimate or "-",
            found_time,
            completed_time,
            args.status,
            notes,
        ]
    else:
        row = [item_id, args.action, description, found_time, completed_time, args.status, notes]

    new_text = insert_row(text, section_title, row)
    if args.dry_run:
        print(new_text, end="")
        return 0
    path.write_text(new_text, encoding="utf-8")
    print(f"已追加：{item_id} -> {section_title}")
    return 0


def collect_records(text: str) -> list[tuple[str, int, list[str]]]:
    records = []
    for title, info in parse_sections(text).items():
        for line_no, cells in info.get("rows", []):
            if cells and re.match(r"^[A-Z]+-\d{3,}$", cells[0]):
                records.append((title, line_no + 1, cells))
    return records


def infer_profile(text: str, sections: dict[str, dict[str, object]]) -> str:
    headings = set(sections)
    if "开发事项" in headings:
        return "development"
    for info in sections.values():
        headers = list(info.get("headers") or [])
        if "优先级" in headers or "预计时间" in headers:
            return "development"
    if {"优化事项", "调研事项", "开源项目调研"} & headings:
        return "extended"
    if "规划事项" in headings:
        return "planning"
    return "minimal"


def profile_rank(profile: str) -> int:
    return {"minimal": 0, "planning": 1, "extended": 2, "development": 3}[profile]


def target_profile(requested: str, inferred: str) -> str:
    if requested == "auto":
        return inferred
    return requested


def missing_sections_for_profile(sections: dict[str, dict[str, object]], profile: str) -> list[Section]:
    existing = {SECTION_ALIASES.get(title, title) for title in sections}
    return [section for section in profile_sections(profile) if section.title not in existing]


def prefix_mismatches(records: list[tuple[str, int, list[str]]]) -> list[str]:
    issues: list[str] = []
    for title, line_no, cells in records:
        section = section_for_title(title)
        if not section or not section.prefix:
            continue
        item_id = cells[0]
        if not item_id.startswith(f"{section.prefix}-"):
            issues.append(f"第 {line_no} 行：{item_id} 位于「{title}」，但该分区期望前缀 {section.prefix}-")
    return issues


def record_quality_warnings(records: list[tuple[str, int, list[str]]]) -> list[str]:
    warnings: list[str] = []
    sparse_notes = 0
    completed_without_time = 0
    active_without_completed_dash = 0
    for _, _, cells in records:
        if len(cells) < 7:
            continue
        status = cells[-2]
        notes = cells[-1]
        completed_time = cells[-3]
        if notes in {"", "-"}:
            sparse_notes += 1
        if status in COMPLETED_STATUSES and completed_time == "-":
            completed_without_time += 1
        if status in {"待修复", "待开发", "进行中"} and completed_time != "-":
            active_without_completed_dash += 1
    if sparse_notes:
        warnings.append(f"{sparse_notes} 条记录备注为空或仅为 -，建议补充文件、测试、来源或后续风险。")
    if completed_without_time:
        warnings.append(f"{completed_without_time} 条已完成/已修复记录缺少完成时间。")
    if active_without_completed_dash:
        warnings.append(f"{active_without_completed_dash} 条未完成记录已经填写完成时间，建议核对状态。")
    return warnings


def classify_extension_recommendations(
    inferred: str, chosen: str, records: list[tuple[str, int, list[str]]], sections: dict[str, dict[str, object]]
) -> list[str]:
    recommendations: list[str] = []
    headings = set(sections)
    if profile_rank(inferred) > profile_rank(chosen):
        recommendations.append(f"当前内容更接近 {inferred}，高于指定 profile {chosen}，建议人工确认是否升级。")
    if "开源项目调研" in headings:
        recommendations.append("发现「开源项目调研」分区，建议统一命名为「调研事项」并使用 RES- 前缀。")
    if "文档事项" in headings:
        recommendations.append("发现「文档事项」分区，建议统一命名为「文档维护」。")
    if any(cells[1] == "优化" for _, _, cells in records) and "优化事项" not in headings:
        recommendations.append("存在优化类记录但没有「优化事项」分区；若优化事项较多，建议使用 extended profile。")
    if any(cells[0].startswith("RES-") for _, _, cells in records) and "调研事项" not in headings:
        recommendations.append("存在 RES- 记录但没有「调研事项」分区，建议补充分区或迁移记录。")
    if any("优先级" in list(info.get("headers") or []) for info in sections.values()) and "开发事项" not in headings:
        recommendations.append("发现优先级字段但未使用「开发事项」标准扩展分区，建议核对开发表结构。")
    return recommendations


def detect_maintenance_rule(project_root: Path) -> dict[str, object]:
    """Detect whether the session-end task-list sync rule and Stop hook are installed.

    Read-only: scans the project root (parent of the target task-list.md) for the canonical
    rule heading in CLAUDE.md / AGENTS.md and a tasklist Stop hook in .claude/settings.json.
    standardize surfaces this so the agent can offer to install the maintenance rule when it
    is missing — it never writes these files itself (installation follows maintenance-rule.md).
    """
    # Scan BOTH agent files rather than stopping at the first one that exists. The rule may
    # legitimately live in AGENTS.md even when CLAUDE.md is also present (e.g. installed before
    # CLAUDE.md existed); checking only the first existing file would misreport it as missing
    # and prompt a duplicate install. Prefer CLAUDE.md both when picking the file that holds
    # the marker and when choosing the install target if neither has it yet.
    candidates = ("CLAUDE.md", "AGENTS.md")
    existing = [name for name in candidates if (project_root / name).exists()]
    containing: list[str] = []
    for name in existing:
        try:
            if MAINTENANCE_RULE_MARKER in (project_root / name).read_text(encoding="utf-8"):
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

    hook_installed = False
    settings_path = project_root / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            for entry in data.get("hooks", {}).get("Stop", []):
                for hook in entry.get("hooks", []):
                    if TASKLIST_HOOK_MARKER in str(hook.get("command", "")):
                        hook_installed = True
                        break
                if hook_installed:
                    break
        except (json.JSONDecodeError, OSError, AttributeError):
            hook_installed = False

    return {
        "agent_file": agent_file,
        "rule_installed": rule_installed,
        "hook_installed": hook_installed,
    }


def analyze_standardization(text: str, requested_profile: str, file_label: str, project_root: Path) -> dict[str, object]:
    sections = parse_sections(text)
    records = collect_records(text)
    inferred = infer_profile(text, sections)
    chosen = target_profile(requested_profile, inferred)
    structural_issues = check_text(text)
    prefix_issues = prefix_mismatches(records)
    missing = missing_sections_for_profile(sections, chosen)
    quality = record_quality_warnings(records)
    recommendations = classify_extension_recommendations(inferred, chosen, records, sections)
    auto_fixes = [f"可补齐缺失分区：{section.title}" for section in missing]
    headings = list(sections)
    maintenance = detect_maintenance_rule(project_root)
    return {
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


def render_markdown_report(report: dict[str, object], applied_fixes: list[str] | None = None) -> str:
    applied_fixes = applied_fixes or []

    def bullet(items: object, empty: str = "无") -> str:
        values = list(items or [])
        if not values:
            return f"- {empty}"
        return "\n".join(f"- {item}" for item in values)

    return "\n".join(
        [
            "# task-list 标准化诊断报告",
            "",
            f"- 文件：{report['file']}",
            f"- 生成时间：{report['generated_at']}",
            f"- 当前 Profile：{report['current_profile']}",
            f"- 推荐 Profile：{report['recommended_profile']}",
            f"- 记录总数：{report['record_count']}",
            "",
            "## 结构问题",
            "",
            bullet(report["structural_issues"]),
            "",
            "## 分类清晰度",
            "",
            bullet(report["classification_issues"]),
            "",
            "## 记录完整性",
            "",
            bullet(report["quality_warnings"]),
            "",
            "## 扩展与优化建议",
            "",
            bullet(report["recommendations"]),
            "",
            "## 可自动修复项",
            "",
            bullet(report["auto_fix_candidates"]),
            "",
            "## 维护规则状态",
            "",
            "\n".join(render_maintenance_lines(report.get("maintenance") or {})),
            "",
            "## 本次已执行修复",
            "",
            bullet(applied_fixes),
            "",
        ]
    )


def render_maintenance_lines(status: dict[str, object]) -> list[str]:
    """Render the maintenance-rule detection result as report bullets.

    Detection is read-only and advisory: standardize never installs the rule itself.
    The bullets tell the agent (and user) what is present and what to consider installing,
    pointing at references/maintenance-rule.md for the install template.
    """
    agent_file = status.get("agent_file")
    rule = bool(status.get("rule_installed"))
    hook = bool(status.get("hook_installed"))
    lines = [
        f"- agent 文件：{agent_file or '未发现 CLAUDE.md / AGENTS.md'}",
        f"- 会话结束同步规则：{'已安装' if rule else '未检测到'}",
        f"- Stop hook 保证层：{'已安装' if hook else '未检测到（可选）'}",
    ]
    if not rule:
        lines.append(
            "- 建议：standardize 完成后询问用户是否安装「会话结束任务同步」规则（opt-in），"
            "模板见 references/maintenance-rule.md。"
        )
    elif not hook:
        lines.append("- 建议：规则已安装但未装 Stop hook；如需每次会话末强制触发可补装（可选）。")
    return lines


def migrate_legacy_schema(text: str) -> tuple[str, list[str]]:
    lines = text.splitlines()
    migrated: list[str] = []
    fixes: list[str] = []
    current_title: str | None = None
    active_legacy_columns: tuple[str, ...] | None = None
    active_new_columns: tuple[str, ...] | None = None

    for line in lines:
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            current_title = heading.group(1)
            active_legacy_columns = None
            active_new_columns = None
            migrated.append(line)
            continue

        cells = split_cells(line)
        if not cells:
            migrated.append(line)
            continue

        is_separator = all(set(cell) <= {"-", ":", " "} for cell in cells)
        if is_separator and active_new_columns:
            migrated.append("| " + " | ".join(["---"] * len(active_new_columns)) + " |")
            continue

        section = section_for_title(current_title or "")
        if cells and cells[0] == "ID" and section:
            expected = list(section.columns)
            if cells != expected:
                active_legacy_columns = tuple(cells)
                active_new_columns = tuple(expected)
                fixes.append(f"迁移「{current_title}」表头为 {len(expected)} 列新 schema")
                migrated.append(table_line(expected))
            else:
                active_legacy_columns = None
                active_new_columns = None
                migrated.append(line)
            continue

        if not active_legacy_columns or not active_new_columns:
            migrated.append(line)
            continue

        if not re.match(r"^[A-Z]+-\d{3,}$", cells[0]):
            migrated.append(line)
            continue

        if len(active_legacy_columns) == 6 and len(cells) == 6:
            date_value = cells[3]
            status = cells[4]
            migrated.append(
                table_line([cells[0], cells[1], cells[2], legacy_time(date_value), legacy_completed_time(date_value, status), status, cells[5]])
            )
            continue

        if len(active_legacy_columns) == 8 and len(cells) == 8 and "优先级" in active_legacy_columns:
            date_value = cells[5]
            status = cells[6]
            migrated.append(
                table_line(
                    [
                        cells[0],
                        cells[1],
                        cells[2],
                        cells[3],
                        cells[4],
                        legacy_time(date_value),
                        legacy_completed_time(date_value, status),
                        status,
                        cells[7],
                    ]
                )
            )
            continue

        migrated.append(line)

    return "\n".join(migrated).rstrip() + "\n", fixes


def add_missing_sections(text: str, profile: str) -> tuple[str, list[str]]:
    sections = parse_sections(text)
    missing = missing_sections_for_profile(sections, profile)
    if not missing:
        return text, []
    additions = "\n".join(render_table(section).rstrip() for section in missing)
    fixed = text.rstrip() + "\n\n" + additions + "\n"
    return fixed, [f"补齐缺失分区：{section.title}" for section in missing]


def check_text(text: str) -> list[str]:
    issues: list[str] = []
    sections = parse_sections(text)
    seen_titles = Counter(re.findall(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE))
    for title, count in seen_titles.items():
        if count > 1:
            issues.append(f"重复章节：{title} 出现 {count} 次")

    id_locations: defaultdict[str, list[int]] = defaultdict(list)
    for title, info in sections.items():
        headers = list(info.get("headers") or [])
        expected = expected_sections().get(title)
        if expected and headers and headers != list(expected.columns):
            if not (title == "开发事项" and headers == list(DEV_EXTENDED_SECTION.columns)):
                issues.append(f"表头与标准不一致：{title}")
        for line_no, cells in info.get("rows", []):
            if not headers:
                continue
            if len(cells) != len(headers):
                issues.append(f"表格列数异常：第 {line_no + 1} 行，期望 {len(headers)} 列，实际 {len(cells)} 列")
                continue
            if cells and re.match(r"^[A-Z]+-\d{3,}$", cells[0]):
                id_locations[cells[0]].append(line_no + 1)
                if len(cells) > 1 and cells[1] not in ACTIONS:
                    issues.append(f"动作不在枚举中：第 {line_no + 1} 行 {cells[1]}")
                if len(cells) > 4:
                    status_index = -2
                    if cells[status_index] not in STATUSES:
                        issues.append(f"状态不在建议枚举中：第 {line_no + 1} 行 {cells[status_index]}")

    for item_id, locations in id_locations.items():
        if len(locations) > 1:
            issues.append(f"重复 ID：{item_id} 出现在行 {', '.join(map(str, locations))}")
    return issues


def command_check(args: argparse.Namespace) -> int:
    text = Path(args.file).read_text(encoding="utf-8")
    issues = check_text(text)
    if issues:
        for issue in issues:
            print(issue)
        return 1
    print("检查通过：未发现重复 ID、重复章节、列数异常或枚举问题")
    return 0


def compute_summary_rows(text: str) -> list[tuple[str, int, int, int]]:
    sections = parse_sections(text)
    records = collect_records(text)
    records_by_section: defaultdict[str, list[list[str]]] = defaultdict(list)
    for title, _, cells in records:
        records_by_section[title].append(cells)

    rows: list[tuple[str, int, int, int]] = []
    for title in sections:
        if title == "统计摘要":
            continue
        section = section_for_title(title)
        if not section or not section.prefix:
            continue
        section_records = records_by_section.get(title, [])
        total = len(section_records)
        done = sum(1 for cells in section_records if len(cells) >= 2 and cells[-2] in COMPLETED_STATUSES)
        pending = sum(1 for cells in section_records if len(cells) >= 2 and cells[-2] in PENDING_STATUSES)
        rows.append((title, total, done, pending))
    return rows


def render_summary_with_counts(rows: list[tuple[str, int, int, int]]) -> str:
    def rate(done: int, total: int) -> str:
        return f"{round(done / total * 100)}%" if total else "0%"

    lines = [
        "## 统计摘要",
        "",
        "| 分类 | 总数 | 已完成 | 待开发/待修复 | 完成率 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    total_all = done_all = pending_all = 0
    for title, total, done, pending in rows:
        lines.append(f"| {title} | {total} | {done} | {pending} | {rate(done, total)} |")
        total_all += total
        done_all += done
        pending_all += pending
    lines.append(f"| **总计** | {total_all} | {done_all} | {pending_all} | {rate(done_all, total_all)} |")
    return "\n".join(lines)


def update_summary_text(text: str) -> str:
    table = render_summary_with_counts(compute_summary_rows(text))
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(r"^##\s+统计摘要\s*$", line):
            start = index
            break
    if start is None:
        return text.rstrip() + "\n\n" + table + "\n"

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
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
    text = path.read_text(encoding="utf-8")

    if args.write:
        new_text = update_summary_text(text)
        if args.dry_run:
            print(new_text, end="")
            return 0
        path.write_text(new_text, encoding="utf-8")
        print(f"已更新统计摘要：{path}")
        return 0

    records = collect_records(text)
    by_section = Counter(title for title, _, _ in records)
    by_status = Counter(cells[-2] for _, _, cells in records if len(cells) >= 2)
    print("按分区统计：")
    for title, count in by_section.items():
        print(f"- {title}: {count}")
    print("按状态统计：")
    for status, count in by_status.items():
        print(f"- {status}: {count}")
    print(f"总计：{len(records)}")
    return 0


def command_standardize(args: argparse.Namespace) -> int:
    path = Path(args.file)
    project_root = path.resolve().parent
    original_text = path.read_text(encoding="utf-8")
    working_text = original_text
    applied_fixes: list[str] = []
    # --fix-only is an output modifier (summary instead of full report); it does not itself
    # trigger fixes. Repairs run only with --apply-safe-fixes or --migrate-schema.
    should_fix = args.apply_safe_fixes or args.migrate_schema

    if args.migrate_schema:
        working_text, fixes = migrate_legacy_schema(working_text)
        applied_fixes.extend(fixes)

    initial_report = analyze_standardization(working_text, args.profile, str(path), project_root)
    chosen_profile = str(initial_report["recommended_profile"])

    if args.apply_safe_fixes:
        working_text, fixes = add_missing_sections(working_text, chosen_profile)
        applied_fixes.extend(fixes)

    # When previewing with --dry-run, stdout is reserved for the file content so it can be
    # redirected safely; route all status/report messages to stderr in that case.
    printed_preview = False
    if should_fix and working_text != original_text:
        if args.dry_run:
            print(working_text, end="")
            printed_preview = True
        else:
            path.write_text(working_text, encoding="utf-8")
    status_stream = sys.stderr if printed_preview else sys.stdout

    report = analyze_standardization(working_text, args.profile, str(path), project_root)
    if args.format == "json":
        rendered = json.dumps({**report, "applied_fixes": applied_fixes}, ensure_ascii=False, indent=2) + "\n"
    else:
        rendered = render_markdown_report(report, applied_fixes)

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(rendered, encoding="utf-8")
        print(f"已生成报告：{report_path}", file=status_stream)

    if args.fix_only:
        print(f"修复完成：{len(applied_fixes)} 项", file=status_stream)
        for fix in applied_fixes:
            print(f"- {fix}", file=status_stream)
        return 0

    if not args.report and not printed_preview:
        print(rendered, end="" if rendered.endswith("\n") else "\n")
    elif should_fix:
        print(f"修复完成：{len(applied_fixes)} 项", file=status_stream)

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="初始化、追加和检查 Markdown task-list.md")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="生成 task-list.md 模板")
    init.add_argument("--output", default="task-list.md", help="输出文件路径")
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

    add = sub.add_parser("add", help="向指定分区追加一条记录")
    add.add_argument("--file", default="task-list.md", help="目标 task-list.md")
    add.add_argument("--section", required=True, help="分区标题，如 代码 Bug")
    add.add_argument("--action", required=True, help="动作枚举")
    add.add_argument("--description", required=True, help="问题描述或事项")
    add.add_argument("--status", required=True, help="状态")
    add.add_argument("--notes", default="-", help="备注")
    add.add_argument("--found-time", help="发现时间，格式 YYYY-MM-DD HH:MM，默认当前本地时间")
    add.add_argument("--completed-time", help="完成时间，格式 YYYY-MM-DD HH:MM；未完成可填 -")
    add.add_argument("--date", help="兼容旧参数（旧单日期 schema）；回退填充发现时间，且仅在状态为完成态时回填完成时间，否则为 -")
    add.add_argument("--id", help="显式指定 ID，默认自动分配")
    add.add_argument("--priority", help="开发事项优先级，默认 P2")
    add.add_argument("--estimate", help="开发事项预计时间")
    add.add_argument("--dry-run", action="store_true", help="只打印结果，不写文件")
    add.set_defaults(func=command_add)

    check = sub.add_parser("check", help="检查结构和枚举问题")
    check.add_argument("--file", default="task-list.md", help="目标 task-list.md")
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
    standardize.add_argument("--apply-safe-fixes", action="store_true", help="执行低风险修复，如补齐缺失空分区")
    standardize.add_argument("--migrate-schema", action="store_true", help="迁移旧日期列 schema 到发现时间/完成时间 schema")
    standardize.add_argument("--fix-only", action="store_true", help="只输出修复摘要而不展开完整报告；需配合 --apply-safe-fixes 或 --migrate-schema 使用")
    standardize.add_argument("--dry-run", action="store_true", help="打印修复后的文件内容，不写回")
    standardize.set_defaults(func=command_standardize)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
