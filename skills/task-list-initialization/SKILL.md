---
name: task-list-initialization
description: Use when a user wants to create, standardize, migrate, validate, or maintain a project-level task-list.md for software projects, agent projects, skills, workflows, planning docs, or AI collaboration rules.
---

# Task List Initialization

## Overview

Use this skill to create or standardize a project-level `task-list.md`. The file is a stable task ledger for humans and AI agents: it records bugs, feature work, reviews, tests, docs, plans, and operations in one predictable Markdown format.

The default model is intentionally small: a fixed header, task-type sections, and Markdown tables. Add optional fields only when the project clearly needs them.

## Workflow

1. Inspect the project for `task-list.md`, `AGENTS.md`, `CLAUDE.md`, planning docs, changelogs, and existing issue notes.
2. If no task list exists, create one from the standard template **in the user's language** (see Language below).
3. If a task list exists, preserve records and normalize only with user approval.
4. Use the standard categories and 7-column table unless project evidence calls for extensions.
5. When the user wants future agents to keep the list updated, install maintenance rules (opt-in): write the canonical session-end sync rule into the project's agent file — `CLAUDE.md` if it exists, else `AGENTS.md`, else create `CLAUDE.md` — and optionally add the `Stop` hook for a reliable "every session" guarantee. Match the rule text and hook message to the task-list's language. Use the template and file-selection logic in `references/maintenance-rule.md`.
6. Validate duplicate IDs, broken table rows, unsupported actions/statuses, and summary drift before finishing.
7. For a task list that has been used for a while, use `standardize` first. It defaults to diagnostics and reporting only; run repair only when the user explicitly asks for it or passes repair flags.

## Default Schema

Use the template in `references/task-list-template.md` unless the project has an existing stronger convention.

Core sections:

| Section | Prefix | Default table |
| --- | --- | --- |
| `代码 Bug` | `BUG-` | `ID / 动作 / 问题描述 / 发现时间 / 完成时间 / 状态 / 备注` |
| `调整事项` | `ADJ-` | `ID / 动作 / 事项 / 发现时间 / 完成时间 / 状态 / 备注` |
| `检查事项` | `CHK-` | `ID / 动作 / 事项 / 发现时间 / 完成时间 / 状态 / 备注` |
| `测试数据` | `TST-` | `ID / 动作 / 事项 / 发现时间 / 完成时间 / 状态 / 备注` |
| `文档维护` | `DOC-` | `ID / 动作 / 事项 / 发现时间 / 完成时间 / 状态 / 备注` |
| `功能开发` | `DEV-` | `ID / 动作 / 事项 / 发现时间 / 完成时间 / 状态 / 备注` |
| `配置运维` | `OPS-` | `ID / 动作 / 事项 / 发现时间 / 完成时间 / 状态 / 备注` |

Optional sections:

- `规划事项` / `PLN-`: roadmaps, WBS, staged plans.
- `优化事项` / `OPT-`: refactors, cleanup, performance or UX optimization.
- `调研事项` / `RES-`: external repository research, technology research, prior-art search.
- `统计摘要`: only when the project needs progress accounting.

## Field Rules

- `动作` must be one of: `修复`, `开发`, `优化`, `调整`, `规划`, `检查`, `文档`, `运维`.
- Map near-synonyms before writing: 审计/复核/核查/审查/验证/评估 -> `检查`; 重构/清理 -> `优化`; 方案/梳理 -> `规划`; 记录类文档 -> `文档`.
- Use `BUG-001` style IDs: prefix + three-digit number. IDs are unique, increasing, and never reused.
- Record both `发现时间` and `完成时间`. Use machine-local timezone timestamps in `YYYY-MM-DD HH:MM` 24-hour format. Use `-` for `完成时间` when the task is not complete.
- Bug completion normally uses `已修复`; non-bug completion normally uses `已完成`.
- Use `待修复`, `待开发`, `进行中`, `已关闭` only when the project needs active-state tracking.
- `已解决` is allowed for troubleshooting items that are diagnosed and closed; prefer `已完成` otherwise. It counts as a completed status.
- Escape literal pipes inside table cells as `\|`.
- Put implementation notes, changed files, review source, and validation results in `备注`.

## Project Variants

Choose the smallest variant that fits:

- `minimal`: common 7-section 7-column template.
- `planning`: minimal + `规划事项`.
- `extended`: minimal + `规划事项`, `优化事项`, `调研事项`.
- `development`: extended + a 9-column `开发事项` table with `优先级` and `预计时间`.

Use `development` only when priority and effort estimates are actually useful. The four reference projects showed that forcing the extended development table onto every project adds maintenance cost.

## Language

The task-list comes in two languages: Chinese (Simplified, `zh`) and English (`en`). Pick the language by the one the user is interacting in:

- **Chinese** interaction → Chinese task-list (`init --lang zh`, the default).
- **Any other language** → tell the user you will produce an English task-list, then create it (`init --lang en`).
- **Cannot determine** the language → default to Chinese (`zh`).

The English task-list is a faithful translation of the Chinese one: same sections, same ID prefixes (`BUG-`/`ADJ-`/…), same 7-column model — only the labels differ (section titles, column headers, action/status enums, header notes). Existing files are handled by auto-detection: `add`/`check`/`summary`/`standardize` sniff the file's language from its structural markers (title and section headings) and validate against the matching locale, so they take no `--lang` flag.

When installing the maintenance rule (workflow step 5, or the standardize maintenance check), match the rule text and Stop-hook message to the task-list's language — see `references/maintenance-rule.md`.

## Standardizing Existing Lists

Use `standardize` when an existing `task-list.md` needs review, cleanup planning, or cautious normalization. This mode is intentionally analytical first: it checks structure, record completeness, classification clarity, and whether the file should remain minimal or use `planning`, `extended`, or `development`.

Default behavior is report-only and must not edit the task list:

```bash
python3 skills/task-list-initialization/scripts/task_list_cli.py standardize --file task-list.md --report docs/task-list-standardize-report.md
```

Repair requires explicit flags:

- `--apply-safe-fixes`: apply low-risk fixes such as adding missing empty standard sections.
- `--migrate-schema`: migrate legacy single-date schemas to `发现时间 / 完成时间`. Data rows whose cell count doesn't match the header (usually an unescaped `|` in a cell) are left untouched and reported as `migrate_warnings` (in `--fix-only` and `--format json` output) instead of being silently skipped.
- `--fix-only`: output modifier — print only a repair summary (no full report); it does not trigger fixes itself, so pair it with `--apply-safe-fixes` or `--migrate-schema`.

Do not automatically rename sections, move records between categories, or rewrite duplicate IDs without user approval. Those are semantic changes and should appear as report recommendations.

**Schema variants.** A project may legitimately keep the legacy **single-date schema** (`ID/动作/事项/完成日期/状态/备注`, 6-col; or 8-col dev) and not migrate to the canonical dual-date model. `check`/`standardize` auto-detect which schema a file uses and validate against it (`--schema auto|dual|single`, default `auto`), so a single-date file in good shape passes instead of being flagged on every section. When the schema is single-date, the report notes that `--migrate-schema` can upgrade it (opt-in, requires approval). Do not force a migration just because the schema differs from the default. `add` detects the target section's schema too and appends a row with the matching column count (single-date 6-col, dual-date 7-col, or dev 8/9-col), so it works on a single-date file without hand-writing the row.

**Duplicate IDs.** When the report finds duplicate IDs, prefer adding `ADJ-` records that document the old→new ID mapping over silently renumbering — this keeps historical references traceable. The actual cleanup (renumber, merge, or leave as-is) still requires explicit user approval.

### Maintenance-rule check

Every `standardize` report includes a **维护规则状态** section (read-only detection). It reports whether the project already has:

- the canonical **会话结束任务同步** rule in `CLAUDE.md` / `AGENTS.md`, and
- the optional **Stop hook** in `.claude/settings.json`.

When the rule is missing, ask the user whether they want future agents to keep the list updated. If they agree, install it exactly as in workflow step 5 — same template, same file-selection logic (`CLAUDE.md` > `AGENTS.md` > create `CLAUDE.md`), idempotent — using `references/maintenance-rule.md`. The CLI detects only; it never installs. When the rule is present but the Stop hook is not, offer the hook as an optional guarantee layer. Do not install anything without explicit user consent (opt-in).

## CLI

Use `scripts/task_list_cli.py` for repeatable operations. On Windows, replace `python3` with `python`.

```bash
python3 skills/task-list-initialization/scripts/task_list_cli.py init --output task-list.md
python3 skills/task-list-initialization/scripts/task_list_cli.py init --lang en --profile extended --with-summary --output task-list.md
python3 skills/task-list-initialization/scripts/task_list_cli.py add --file task-list.md --section "代码 Bug" --action 修复 --description "登录失败" --status 待修复 --notes "复现于本地"
python3 skills/task-list-initialization/scripts/task_list_cli.py check --file task-list.md
python3 skills/task-list-initialization/scripts/task_list_cli.py summary --file task-list.md
python3 skills/task-list-initialization/scripts/task_list_cli.py summary --file task-list.md --write
python3 skills/task-list-initialization/scripts/task_list_cli.py standardize --file task-list.md --report docs/task-list-standardize-report.md
python3 skills/task-list-initialization/scripts/task_list_cli.py standardize --file task-list.md --migrate-schema --apply-safe-fixes
```

`init --lang {zh,en}` selects the template language (`zh` = Simplified Chinese, default; `en` = English). The other subcommands auto-detect the language from the target file. `check`/`standardize` accept `--schema {auto,dual,single}` (default `auto`) to validate a file that keeps the legacy single-date schema. `add` auto-matches the target section's schema and emits the corresponding column count, so no flag is needed.

Run `--help` for all options. Prefer CLI generation for new files, then review the result manually for project-specific wording.

`summary --write` recomputes the `统计摘要` table from current records (total / completed / pending / completion rate) and writes it back, appending the section if it does not exist yet. Use `--dry-run` to preview without writing.

## References

- `references/task-list-standard.md`: four-project summary, common rules, differences, risks, and maintenance guidance.
- `references/task-list-template.md`: canonical Markdown templates for each profile.
- `references/maintenance-rule.md`: canonical maintenance-rule text (Chinese and English), file-selection logic, language-matching guidance, and optional `Stop`-hook guarantee layer for installing into a project's `CLAUDE.md`/`AGENTS.md`.
