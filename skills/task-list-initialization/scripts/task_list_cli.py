#!/usr/bin/env python3
"""Create and maintain Markdown task-list files (Chinese or English)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Schema: sections are locale-specific (titles + column headers), but the ID
# prefix scheme (BUG-/ADJ-/…) is language-independent so a task-list keeps the
# same IDs regardless of locale.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Section:
    title: str
    prefix: str | None
    columns: tuple[str, ...]


@dataclass(frozen=True)
class Locale:
    name: str
    title: str
    intro: str
    notes: tuple[str, ...]
    base_sections: tuple[Section, ...]
    planning: Section
    opt: Section
    res: Section
    dev_extended: Section
    actions: frozenset[str]
    statuses: frozenset[str]
    completed_statuses: frozenset[str]
    pending_statuses: frozenset[str]
    section_aliases: dict[str, str]
    summary_columns: tuple[str, ...]
    summary_section: str
    total_label: str
    action_optimize: str

    def all_sections(self) -> tuple[Section, ...]:
        return (*self.base_sections, self.planning, self.opt, self.res, self.dev_extended)

    def features_section(self) -> Section:
        # The base DEV-prefixed section (功能开发 / Features) that the development profile
        # replaces with the 9-column dev_extended table.
        return next(section for section in self.base_sections if section.prefix == "DEV")


_ZH = Locale(
    name="zh",
    title="# 任务跟踪列表",
    intro=(
        "记录本项目所有任务：代码 bug、bug 转需求、新增需求、需求调整、功能开发、"
        "代码审查、测试数据、文档维护、配置运维等。"
    ),
    notes=(
        "> 说明：本文件是当前项目的任务清单。所有新增事项、状态变更和完成记录都应同步写入本文件。",
        "> 字段说明：动作字段只允许以下 8 个固定枚举：修复、开发、优化、调整、规划、检查、文档、运维。",
        "> 时间说明：发现时间和完成时间分开记录，格式为 YYYY-MM-DD HH:MM，使用机器本地时区的 24 小时制时间；未完成事项的完成时间填 -。",
        "> 归并规则：审计、复核、核查、审查、验证、评估统一记为“检查”；重构、清理统一记为“优化”；方案、梳理统一记为“规划”；记录类文档事项统一记为“文档”。",
    ),
    base_sections=(
        Section("代码 Bug", "BUG", ("ID", "动作", "问题描述", "发现时间", "完成时间", "状态", "备注")),
        Section("调整事项", "ADJ", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注")),
        Section("检查事项", "CHK", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注")),
        Section("测试数据", "TST", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注")),
        Section("文档维护", "DOC", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注")),
        Section("功能开发", "DEV", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注")),
        Section("配置运维", "OPS", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注")),
    ),
    planning=Section("规划事项", "PLN", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注")),
    opt=Section("优化事项", "OPT", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注")),
    res=Section("调研事项", "RES", ("ID", "动作", "事项", "发现时间", "完成时间", "状态", "备注")),
    dev_extended=Section(
        "开发事项", "DEV", ("ID", "动作", "事项", "优先级", "预计时间", "发现时间", "完成时间", "状态", "备注")
    ),
    actions=frozenset({"修复", "开发", "优化", "调整", "规划", "检查", "文档", "运维"}),
    statuses=frozenset({"待修复", "已修复", "待开发", "进行中", "已完成", "已关闭", "已解决", "-"}),
    completed_statuses=frozenset({"已修复", "已完成", "已关闭", "已解决"}),
    pending_statuses=frozenset({"待修复", "待开发", "进行中"}),
    section_aliases={
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
    },
    summary_columns=("分类", "总数", "已完成", "待开发/待修复", "完成率"),
    summary_section="统计摘要",
    total_label="总计",
    action_optimize="优化",
)


_EN = Locale(
    name="en",
    title="# Task Tracking List",
    intro=(
        "Records all project tasks: bugs, bug-to-requirement conversions, new requirements, "
        "requirement adjustments, feature development, code reviews, test data, documentation, "
        "operations, etc."
    ),
    notes=(
        "> Note: This file is the project's task list. All new items, status changes, and completion records should be synced into this file.",
        "> Fields: The Action field allows only these 8 fixed values: Fix, Develop, Optimize, Adjust, Plan, Review, Doc, Ops.",
        "> Time: Found and Done are recorded separately in YYYY-MM-DD HH:MM format, using the machine's local timezone in 24-hour time; for incomplete items, Done is -.",
        "> Merging: Audit/Recheck/Verify/Review/Validate/Assess are unified as \"Review\"; Refactor/Cleanup as \"Optimize\"; Proposal/Outline as \"Plan\"; record-style documentation items as \"Doc\".",
    ),
    base_sections=(
        Section("Bugs", "BUG", ("ID", "Action", "Description", "Found", "Done", "Status", "Notes")),
        Section("Adjustments", "ADJ", ("ID", "Action", "Item", "Found", "Done", "Status", "Notes")),
        Section("Reviews", "CHK", ("ID", "Action", "Item", "Found", "Done", "Status", "Notes")),
        Section("Test Data", "TST", ("ID", "Action", "Item", "Found", "Done", "Status", "Notes")),
        Section("Docs", "DOC", ("ID", "Action", "Item", "Found", "Done", "Status", "Notes")),
        Section("Features", "DEV", ("ID", "Action", "Item", "Found", "Done", "Status", "Notes")),
        Section("Ops", "OPS", ("ID", "Action", "Item", "Found", "Done", "Status", "Notes")),
    ),
    planning=Section("Plans", "PLN", ("ID", "Action", "Item", "Found", "Done", "Status", "Notes")),
    opt=Section("Optimizations", "OPT", ("ID", "Action", "Item", "Found", "Done", "Status", "Notes")),
    res=Section("Research", "RES", ("ID", "Action", "Item", "Found", "Done", "Status", "Notes")),
    dev_extended=Section(
        "Development", "DEV", ("ID", "Action", "Item", "Priority", "Estimate", "Found", "Done", "Status", "Notes")
    ),
    actions=frozenset({"Fix", "Develop", "Optimize", "Adjust", "Plan", "Review", "Doc", "Ops"}),
    statuses=frozenset({"Pending Fix", "Fixed", "Pending Dev", "In Progress", "Done", "Closed", "Resolved", "-"}),
    completed_statuses=frozenset({"Fixed", "Done", "Closed", "Resolved"}),
    pending_statuses=frozenset({"Pending Fix", "Pending Dev", "In Progress"}),
    section_aliases={
        "bug": "Bugs",
        "Bug": "Bugs",
        "BUG": "Bugs",
        "Bugs": "Bugs",
        "dev": "Features",
        "feature": "Features",
        "features": "Features",
        "Features": "Features",
        "Development": "Development",
        "development": "Development",
        "doc": "Docs",
        "docs": "Docs",
        "Docs": "Docs",
        "ops": "Ops",
        "Ops": "Ops",
        "adjustment": "Adjustments",
        "Adjustments": "Adjustments",
        "review": "Reviews",
        "Reviews": "Reviews",
        "test": "Test Data",
        "Test Data": "Test Data",
        "plan": "Plans",
        "Plans": "Plans",
        "optimization": "Optimizations",
        "Optimizations": "Optimizations",
        "research": "Research",
        "Research": "Research",
    },
    summary_columns=("Category", "Total", "Done", "Pending", "Rate"),
    summary_section="Summary",
    total_label="Total",
    action_optimize="Optimize",
)


LOCALES = {"zh": _ZH, "en": _EN}


# Date-model variants. The canonical schema is dual-date (发现时间 + 完成时间 / Found +
# Done). A project may legitimately keep the legacy single-date schema (完成日期 / Done
# Date — 6-col, or 8-col dev). check/standardize auto-detect which model a file uses and
# validate against it, so a single-date file in good shape is NOT flagged as
# 「表头与标准不一致」on every section. Migration to dual-date remains opt-in (--migrate-schema).
DUAL_DATE_COLS = {"zh": ("发现时间", "完成时间"), "en": ("Found", "Done")}
SINGLE_DATE_COL = {"zh": "完成日期", "en": "Done Date"}
SINGLE_DATE_ALIASES = {
    "zh": ("完成日期", "发现日期"),
    "en": ("Done Date", "Found Date"),
}


# User-facing strings (CLI prompts, diagnostic report). Locale-driven so an English
# task-list gets an English report.
T = {
    "zh": {
        "report_title": "# task-list 标准化诊断报告",
        "file": "文件",
        "generated_at": "生成时间",
        "current_profile": "当前 Profile",
        "recommended_profile": "推荐 Profile",
        "record_count": "记录总数",
        "sec_structure": "## 结构问题",
        "sec_classification": "## 分类清晰度",
        "sec_completeness": "## 记录完整性",
        "sec_recommendations": "## 扩展与优化建议",
        "sec_autofix": "## 可自动修复项",
        "sec_maintenance": "## 维护规则状态",
        "sec_applied": "## 本次已执行修复",
        "empty": "无",
        "agent_file": "agent 文件",
        "agent_file_none": "未发现 CLAUDE.md / AGENTS.md",
        "rule_label": "会话结束同步规则",
        "hook_label": "Stop hook 保证层",
        "hook_optional": "未检测到（可选）",
        "installed": "已安装",
        "not_detected": "未检测到",
        "rec_install_rule": "- 建议：standardize 完成后询问用户是否安装「会话结束任务同步」规则（opt-in），模板见 references/maintenance-rule.md。",
        "rec_install_hook": "- 建议：规则已安装但未装 Stop hook；如需每次会话末强制触发可补装（可选）。",
        "dup_section": "重复章节：{0} 出现 {1} 次",
        "header_mismatch": "表头与标准不一致：{0}",
        "col_mismatch": "表格列数异常：第 {0} 行，期望 {1} 列，实际 {2} 列",
        "bad_action_line": "动作不在枚举中：第 {0} 行 {1}",
        "bad_status_line": "状态不在建议枚举中：第 {0} 行 {1}",
        "dup_id": "重复 ID：{0} 出现在行 {1}",
        "prefix_mismatch": "第 {0} 行：{1} 位于「{2}」，但该分区期望前缀 {3}-",
        "warn_sparse_notes": "{0} 条记录备注为空或仅为 -，建议补充文件、测试、来源或后续风险。",
        "warn_completed_no_time": "{0} 条已完成/已修复记录缺少完成时间。",
        "warn_active_has_time": "{0} 条未完成记录已经填写完成时间，建议核对状态。",
        "rec_profile_higher": "当前内容更接近 {0}，高于指定 profile {1}，建议人工确认是否升级。",
        "rec_legacy_research": "发现「开源项目调研」分区，建议统一命名为「调研事项」并使用 RES- 前缀。",
        "rec_legacy_doc": "发现「文档事项」分区，建议统一命名为「文档维护」。",
        "rec_opt_without_section": "存在优化类记录但没有「优化事项」分区；若优化事项较多，建议使用 extended profile。",
        "rec_res_without_section": "存在 RES- 记录但没有「调研事项」分区，建议补充分区或迁移记录。",
        "rec_priority_without_dev": "发现优先级字段但未使用「开发事项」标准扩展分区，建议核对开发表结构。",
        "rec_single_date_schema": "- 信息：本项目使用单日期 schema（合法变体），check 已按此校验；如需升级为双日期模型（发现时间/完成时间），可用 --migrate-schema（需批准）。",
        "rec_dup_id_mapping": "- 建议：检测到重复 ID；如需清理，新增 ADJ- 记录说明改号映射（旧号→新号），避免历史引用断裂。",
        "auto_fix_candidate": "可补齐缺失分区：{0}",
        "add_section_fix": "补齐缺失分区：{0}",
        "migrate_header": "迁移「{0}」表头为 {1} 列新 schema",
        "migrate_skip": "⚠️ {0}（第 {1} 行）：实际 {3} 列、legacy 表头 {2} 列，已跳过未迁移——多为单元格内未转义的 |，需人工处理",
        "migrate_skips": "⚠️ {0} 行因列数与表头不符未迁移（多为单元格内未转义的 |，需人工处理）：",
        "check_ok": "检查通过：未发现重复 ID、重复章节、列数异常或枚举问题",
        "section_not_found": "未找到分区：{0}",
        "prefix_unknown": "无法推断分区 ID 前缀：{0}",
        "bad_action": "动作不在枚举中：{0}",
        "bad_status": "状态不在建议枚举中：{0}",
        "bad_time": "时间格式应为 YYYY-MM-DD HH:MM：{0}",
        "bad_lang": "不支持的语言：{0}（可选：zh、en）",
        "target_exists": "目标文件已存在，使用 --force 覆盖：{0}",
        "generated_file": "已生成：{0}",
        "added": "已追加：{0} -> {1}",
        "report_written": "已生成报告：{0}",
        "fixes_applied": "修复完成：{0} 项",
        "summary_updated": "已更新统计摘要：{0}",
        "by_section": "按分区统计：",
        "by_status": "按状态统计：",
        "total_count": "总计：{0}",
    },
    "en": {
        "report_title": "# task-list Standardization Report",
        "file": "File",
        "generated_at": "Generated",
        "current_profile": "Current Profile",
        "recommended_profile": "Recommended Profile",
        "record_count": "Records",
        "sec_structure": "## Structure",
        "sec_classification": "## Classification",
        "sec_completeness": "## Completeness",
        "sec_recommendations": "## Recommendations",
        "sec_autofix": "## Auto-fixable",
        "sec_maintenance": "## Maintenance Rule",
        "sec_applied": "## Applied Fixes",
        "empty": "None",
        "agent_file": "Agent file",
        "agent_file_none": "No CLAUDE.md / AGENTS.md found",
        "rule_label": "Session-end sync rule",
        "hook_label": "Stop hook guarantee",
        "hook_optional": "not detected (optional)",
        "installed": "installed",
        "not_detected": "not detected",
        "rec_install_rule": "- Suggestion: after standardize, ask the user whether to install the session-end sync rule (opt-in); see references/maintenance-rule.md.",
        "rec_install_hook": "- Suggestion: rule installed but no Stop hook; add one to force a reminder every session end (optional).",
        "dup_section": "Duplicate section: {0} appears {1} times",
        "header_mismatch": "Header does not match the standard: {0}",
        "col_mismatch": "Column count mismatch: line {0}, expected {1}, found {2}",
        "bad_action_line": "Action not in enum: line {0} {1}",
        "bad_status_line": "Status not in suggested enum: line {0} {1}",
        "dup_id": "Duplicate ID: {0} at lines {1}",
        "prefix_mismatch": "Line {0}: {1} is under \"{2}\" but this section expects prefix {3}-",
        "warn_sparse_notes": "{0} records have empty or '-' notes; add files, tests, sources, or follow-up risks.",
        "warn_completed_no_time": "{0} completed/fixed records are missing a Done time.",
        "warn_active_has_time": "{0} incomplete records already have a Done time; check the status.",
        "rec_profile_higher": "Content looks closer to {0}, above the chosen profile {1}; confirm whether to upgrade.",
        "rec_legacy_research": "",
        "rec_legacy_doc": "",
        "rec_opt_without_section": "Optimize records exist but no \"Optimizations\" section; if there are many, use the extended profile.",
        "rec_res_without_section": "RES- records exist but no \"Research\" section; add the section or migrate the records.",
        "rec_priority_without_dev": "Priority field found but the \"Development\" extended section is not in use; check the dev table structure.",
        "rec_single_date_schema": "- Info: this project uses the single-date schema (a legitimate variant); check validates against it. To upgrade to the dual-date model (Found/Done), use --migrate-schema (requires approval).",
        "rec_dup_id_mapping": "- Suggestion: duplicate IDs detected; if cleaned up, add ADJ- records mapping old→new IDs to preserve audit traceability.",
        "auto_fix_candidate": "Can add missing section: {0}",
        "add_section_fix": "Added missing section: {0}",
        "migrate_header": "Migrate \"{0}\" header to {1}-column schema",
        "migrate_skip": "⚠️ {0} (line {1}): {3} cells vs {2}-col legacy header; skipped — likely an unescaped | in a cell; fix manually",
        "migrate_skips": "⚠️ {0} row(s) skipped due to column mismatch (likely an unescaped | in a cell; fix manually):",
        "check_ok": "Check passed: no duplicate IDs, duplicate sections, column mismatches, or enum issues",
        "section_not_found": "Section not found: {0}",
        "prefix_unknown": "Cannot infer ID prefix for section: {0}",
        "bad_action": "Action not in enum: {0}",
        "bad_status": "Status not in suggested enum: {0}",
        "bad_time": "Time format should be YYYY-MM-DD HH:MM: {0}",
        "bad_lang": "Unsupported language: {0} (options: zh, en)",
        "target_exists": "Target exists; use --force to overwrite: {0}",
        "generated_file": "Generated: {0}",
        "added": "Added: {0} -> {1}",
        "report_written": "Report generated: {0}",
        "fixes_applied": "Fixes applied: {0}",
        "summary_updated": "Summary updated: {0}",
        "by_section": "By section:",
        "by_status": "By status:",
        "total_count": "Total: {0}",
    },
}


# Maintenance-rule detection markers. Must stay in sync with references/maintenance-rule.md:
# the canonical rule block always carries this heading; the Stop hook command always names
# the tasklist reminder script. standardize uses these to report whether the maintenance
# rule / hook are already installed in the target project (read-only detection). The marker
# is language-agnostic: the zh rule uses 「会话结束任务同步」 and the en rule uses the same
# Chinese phrase is NOT reused — instead both locales mark the block with the same stable
# token below so detection works regardless of the installed language.
MAINTENANCE_RULE_MARKER = "会话结束任务同步"
MAINTENANCE_RULE_MARKER_EN = "Session-end Task Sync"
TASKLIST_HOOK_MARKER = "tasklist"


def get_locale(lang: str) -> Locale:
    if lang not in LOCALES:
        raise SystemExit(T["zh"]["bad_lang"].format(lang))
    return LOCALES[lang]


def detect_locale(text: str) -> str:
    """Sniff a task-list's language from its structural markers (title / section headings).

    Controlled template elements are language-specific, so this is robust even when a record's
    Notes cell happens to contain the other language. Defaults to zh.
    """
    en = LOCALES["en"]
    if en.title in text:
        return "en"
    for section in en.all_sections():
        if f"## {section.title}" in text:
            return "en"
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
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    cells: list[str] = []
    current: list[str] = []
    chars = stripped[1:-1]
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
    raise SystemExit(T[locale.name]["section_not_found"].format(title))


def prefix_for_section(title: str, locale: Locale) -> str:
    normalized = locale.section_aliases.get(title, title)
    known = expected_sections(locale).get(normalized)
    if known and known.prefix:
        return known.prefix
    if normalized == locale.dev_extended.title:
        return "DEV"
    raise SystemExit(T[locale.name]["prefix_unknown"].format(title))


def next_id(prefix: str, text: str) -> str:
    ids = re.findall(rf"\b{re.escape(prefix)}-(\d{{3,}})\b", text)
    number = max((int(item) for item in ids), default=0) + 1
    return f"{prefix}-{number:03d}"


def local_minute_now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


def normalize_time(value: str | None, default: str, locale: Locale | None = None) -> str:
    lang = (locale or LOCALES["zh"]).name
    if not value:
        return default
    value = value.strip()
    if value == "-":
        return value
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return f"{value} 00:00"
    if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", value):
        raise SystemExit(T[lang]["bad_time"].format(value))
    return value


def default_completed_time(status: str, now: str, locale: Locale) -> str:
    if status in locale.completed_statuses:
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


def legacy_completed_time(value: str, status: str, locale: Locale) -> str:
    if status in locale.completed_statuses:
        return legacy_time(value)
    return "-"


def single_date_cell(
    args: argparse.Namespace, status: str, now: str, locale: Locale
) -> str:
    """Build the lone date column for a single-date schema row."""
    raw = args.date or args.completed_time or ""
    if status in locale.completed_statuses:
        return legacy_time(normalize_time(raw or now, now, locale))
    return "-"


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
        if lines[index].startswith("## "):
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
    output.write_text(text, encoding="utf-8")
    print(T[locale.name]["generated_file"].format(output))
    return 0


def command_add(args: argparse.Namespace) -> int:
    path = Path(args.file)
    text = path.read_text(encoding="utf-8")
    locale = get_locale(detect_locale(text))
    lang = locale.name
    sections = parse_sections(text)
    section_title = find_section_by_title(args.section, sections, locale)
    headers = list(sections[section_title].get("headers") or [])
    if not headers:
        raise SystemExit(T[lang]["section_not_found"].format(section_title))
    section = section_for_title(section_title, locale)
    if not section:
        raise SystemExit(T[lang]["section_not_found"].format(section_title))
    prefix = prefix_for_section(section_title, locale)
    item_id = args.id or next_id(prefix, text)
    now = local_minute_now()
    found_time = normalize_time(args.found_time or args.date, now, locale)
    # --date is a legacy single-date fallback. It always seeds 发现时间/Found; for 完成时间/Done it
    # only backfills when the status is a completed state (mirroring legacy_completed_time), so
    # 未完成 records keep Done = "-" instead of a self-contradictory date.
    completed_value = args.completed_time
    if not completed_value and args.status in locale.completed_statuses:
        completed_value = args.date
    completed_time = normalize_time(
        completed_value, default_completed_time(args.status, now, locale), locale
    )
    description = args.description
    notes = args.notes or "-"

    if args.action not in locale.actions:
        raise SystemExit(T[lang]["bad_action"].format(args.action))
    if args.status not in locale.statuses:
        raise SystemExit(T[lang]["bad_status"].format(args.status))

    dev_dual = list(locale.dev_extended.columns)
    dev_single = list(to_single_date_columns(locale.dev_extended.columns, locale))
    section_dual = list(section.columns)
    section_single = list(to_single_date_columns(section.columns, locale))

    if headers == dev_dual:
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
    elif headers == dev_single:
        row = [
            item_id,
            args.action,
            description,
            args.priority or "P2",
            args.estimate or "-",
            single_date_cell(args, args.status, now, locale),
            args.status,
            notes,
        ]
    elif headers == section_dual:
        row = [item_id, args.action, description, found_time, completed_time, args.status, notes]
    elif headers == section_single:
        row = [
            item_id,
            args.action,
            description,
            single_date_cell(args, args.status, now, locale),
            args.status,
            notes,
        ]
    else:
        # Non-standard header: fall back to column count so mixed/legacy files still work.
        if len(headers) == len(dev_dual):
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
        elif len(headers) == len(dev_single):
            row = [
                item_id,
                args.action,
                description,
                args.priority or "P2",
                args.estimate or "-",
                single_date_cell(args, args.status, now, locale),
                args.status,
                notes,
            ]
        elif len(headers) == len(section_single):
            row = [
                item_id,
                args.action,
                description,
                single_date_cell(args, args.status, now, locale),
                args.status,
                notes,
            ]
        else:
            row = [item_id, args.action, description, found_time, completed_time, args.status, notes]

    new_text = insert_row(text, section_title, row, lang)
    if args.dry_run:
        print(new_text, end="")
        return 0
    path.write_text(new_text, encoding="utf-8")
    print(T[lang]["added"].format(item_id, section_title))
    return 0


def collect_records(text: str) -> list[tuple[str, int, list[str]]]:
    records = []
    for title, info in parse_sections(text).items():
        for line_no, cells in info.get("rows", []):
            if cells and re.match(r"^[A-Z]+-\d{3,}$", cells[0]):
                records.append((title, line_no + 1, cells))
    return records


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
    return [section for section in profile_sections(profile, locale) if section.title not in existing]


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
    records: list[tuple[str, int, list[str]]], locale: Locale
) -> list[str]:
    warnings: list[str] = []
    sparse_notes = 0
    completed_without_time = 0
    active_without_completed_dash = 0
    for _, _, cells in records:
        if len(cells) < 6:
            continue
        status = cells[-2]
        notes = cells[-1]
        completed_time = cells[-3]
        if notes in {"", "-"}:
            sparse_notes += 1
        if status in locale.completed_statuses and completed_time == "-":
            completed_without_time += 1
        if status in locale.pending_statuses and completed_time != "-":
            active_without_completed_dash += 1
    m = T[locale.name]
    if sparse_notes:
        warnings.append(m["warn_sparse_notes"].format(sparse_notes))
    if completed_without_time:
        warnings.append(m["warn_completed_no_time"].format(completed_without_time))
    if active_without_completed_dash:
        warnings.append(m["warn_active_has_time"].format(active_without_completed_dash))
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
    if any(cells[1] == locale.action_optimize for _, _, cells in records) and locale.opt.title not in headings:
        recommendations.append(m["rec_opt_without_section"])
    if any(cells[0].startswith("RES-") for _, _, cells in records) and locale.res.title not in headings:
        recommendations.append(m["rec_res_without_section"])
    if (
        any(locale.dev_extended.columns[3] in list(info.get("headers") or []) for info in sections.values())
        and locale.dev_extended.title not in headings
    ):
        recommendations.append(m["rec_priority_without_dev"])
    return recommendations


def analyze_standardization(
    text: str, requested_profile: str, file_label: str, project_root: Path, locale: Locale,
    schema_override: str = "auto",
) -> dict[str, object]:
    sections = parse_sections(text)
    records = collect_records(text)
    inferred = infer_profile(text, sections, locale)
    chosen = target_profile(requested_profile, inferred)
    schema = schema_override if schema_override != "auto" else detect_schema(text, locale)
    structural_issues = check_text(text, locale, schema)
    prefix_issues = prefix_mismatches(records, locale)
    missing = missing_sections_for_profile(sections, chosen, locale)
    quality = record_quality_warnings(records, locale)
    recommendations = classify_extension_recommendations(inferred, chosen, records, sections, locale)
    if schema == "single":
        recommendations.append(T[locale.name]["rec_single_date_schema"])
    id_counts = Counter(
        cells[0] for _, _, cells in records if cells and re.match(r"^[A-Z]+-\d{3,}$", cells[0])
    )
    if any(count > 1 for count in id_counts.values()):
        recommendations.append(T[locale.name]["rec_dup_id_mapping"])
    auto_fixes = [T[locale.name]["auto_fix_candidate"].format(section.title) for section in missing]
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
    lines = [
        f"- {m['agent_file']}{sep}{agent_file or m['agent_file_none']}",
        f"- {m['rule_label']}{sep}{m['installed'] if rule else m['not_detected']}",
        f"- {m['hook_label']}{sep}{m['installed'] if hook else m['hook_optional']}",
    ]
    if not rule:
        lines.append(m["rec_install_rule"])
    elif not hook:
        lines.append(m["rec_install_hook"])
    return lines


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
            text = (project_root / name).read_text(encoding="utf-8")
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


def migrate_legacy_schema(text: str, locale: Locale) -> tuple[str, list[str], list[str]]:
    lines = text.splitlines()
    migrated: list[str] = []
    fixes: list[str] = []
    warnings: list[str] = []
    current_title: str | None = None
    active_legacy_columns: tuple[str, ...] | None = None
    active_new_columns: tuple[str, ...] | None = None
    priority_col = locale.dev_extended.columns[3]

    for idx, line in enumerate(lines, 1):
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

        section = section_for_title(current_title or "", locale)
        if cells and cells[0] == "ID" and section:
            expected = list(section.columns)
            if cells != expected:
                active_legacy_columns = tuple(cells)
                active_new_columns = tuple(expected)
                fixes.append(T[locale.name]["migrate_header"].format(current_title, len(expected)))
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
                table_line([cells[0], cells[1], cells[2], legacy_time(date_value), legacy_completed_time(date_value, status, locale), status, cells[5]])
            )
            continue

        if len(active_legacy_columns) == 8 and len(cells) == 8 and priority_col in active_legacy_columns:
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
                        legacy_completed_time(date_value, status, locale),
                        status,
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
        warnings.append(T[locale.name]["migrate_skip"].format(cells[0], idx, len(active_legacy_columns), len(cells)))
        migrated.append(line)

    return "\n".join(migrated).rstrip() + "\n", fixes, warnings


def add_missing_sections(text: str, profile: str, locale: Locale) -> tuple[str, list[str]]:
    sections = parse_sections(text)
    missing = missing_sections_for_profile(sections, profile, locale)
    if not missing:
        return text, []
    additions = "\n".join(render_table(section).rstrip() for section in missing)
    fixed = text.rstrip() + "\n\n" + additions + "\n"
    return fixed, [T[locale.name]["add_section_fix"].format(section.title) for section in missing]


def check_text(text: str, locale: Locale, schema: str = "dual") -> list[str]:
    issues: list[str] = []
    m = T[locale.name]
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
    for title, info in sections.items():
        headers = list(info.get("headers") or [])
        expected = expected_map.get(title)
        if expected and headers and headers != list(expected.columns):
            if not (title == locale.dev_extended.title and headers == list(locale.dev_extended.columns)):
                issues.append(m["header_mismatch"].format(title))
        for line_no, cells in info.get("rows", []):
            if not headers:
                continue
            if len(cells) != len(headers):
                issues.append(m["col_mismatch"].format(line_no + 1, len(headers), len(cells)))
                continue
            if cells and re.match(r"^[A-Z]+-\d{3,}$", cells[0]):
                id_locations[cells[0]].append(line_no + 1)
                if len(cells) > 1 and cells[1] not in locale.actions:
                    issues.append(m["bad_action_line"].format(line_no + 1, cells[1]))
                if len(cells) > 4:
                    status_index = -2
                    if cells[status_index] not in locale.statuses:
                        issues.append(m["bad_status_line"].format(line_no + 1, cells[status_index]))

    for item_id, locations in id_locations.items():
        if len(locations) > 1:
            issues.append(m["dup_id"].format(item_id, ", ".join(map(str, locations))))
    return issues


def command_check(args: argparse.Namespace) -> int:
    path = Path(args.file)
    text = path.read_text(encoding="utf-8")
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
    records_by_section: defaultdict[str, list[list[str]]] = defaultdict(list)
    for title, _, cells in records:
        records_by_section[title].append(cells)

    rows: list[tuple[str, int, int, int]] = []
    for title in sections:
        if title == locale.summary_section:
            continue
        section = section_for_title(title, locale)
        if not section or not section.prefix:
            continue
        section_records = records_by_section.get(title, [])
        total = len(section_records)
        done = sum(1 for cells in section_records if len(cells) >= 2 and cells[-2] in locale.completed_statuses)
        pending = sum(1 for cells in section_records if len(cells) >= 2 and cells[-2] in locale.pending_statuses)
        rows.append((title, total, done, pending))
    return rows


def render_summary_with_counts(rows: list[tuple[str, int, int, int]], locale: Locale) -> str:
    def rate(done: int, total: int) -> str:
        return f"{round(done / total * 100)}%" if total else "0%"

    cols = list(locale.summary_columns)
    lines = [
        f"## {locale.summary_section}",
        "",
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    total_all = done_all = pending_all = 0
    for title, total, done, pending in rows:
        lines.append(f"| {title} | {total} | {done} | {pending} | {rate(done, total)} |")
        total_all += total
        done_all += done
        pending_all += pending
    lines.append(f"| **{locale.total_label}** | {total_all} | {done_all} | {pending_all} | {rate(done_all, total_all)} |")
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
    locale = get_locale(detect_locale(text))

    if args.write:
        new_text = update_summary_text(text, locale)
        if args.dry_run:
            print(new_text, end="")
            return 0
        path.write_text(new_text, encoding="utf-8")
        print(T[locale.name]["summary_updated"].format(path))
        return 0

    records = collect_records(text)
    by_section = Counter(title for title, _, _ in records)
    by_status = Counter(cells[-2] for _, _, cells in records if len(cells) >= 2)
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
    original_text = path.read_text(encoding="utf-8")
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
            path.write_text(working_text, encoding="utf-8")
    status_stream = sys.stderr if printed_preview else sys.stdout

    report = analyze_standardization(working_text, args.profile, str(path), project_root, locale, schema_override=args.schema)
    if args.format == "json":
        rendered = json.dumps({**report, "applied_fixes": applied_fixes, "migrate_warnings": migrate_warnings}, ensure_ascii=False, indent=2) + "\n"
    else:
        rendered = render_markdown_report(report, applied_fixes, locale)

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(rendered, encoding="utf-8")
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

    add = sub.add_parser("add", help="向指定分区追加一条记录")
    add.add_argument("--file", default="task-list.md", help="目标 task-list.md")
    add.add_argument("--section", required=True, help="分区标题，如 代码 Bug / Bugs")
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
