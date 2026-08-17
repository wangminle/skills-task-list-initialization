---
name: task-list-initialization
description: Use when creating, standardizing, migrating, validating, or maintaining a project-level task-list.md (bug/feature/review/test/doc/ops ledger). Trigger on 建立任务台账 / 整理 task-list / 初始化任务清单 / changelog 迁台账 / 会话结束同步任务 / set up a bug ledger / track bugs and features in one Markdown file — even if the user never says "task-list". Also for check/repair/archive and installing CLAUDE.md/AGENTS.md session-end sync rules. Do not use for ad-hoc TODOs, GitHub Issues I/O, or general PM tools.
---

# Task List Initialization

> Skill version **V0.3.7**. Canonical string: repo root `VERSION`.

## Overview

Use this skill to create or standardize a project-level `task-list.md`. The file is a stable task ledger for humans and AI agents: it records bugs, feature work, reviews, tests, docs, plans, and operations in one predictable Markdown format.

The default model is intentionally small: a fixed header, task-type sections, and Markdown tables. Add optional fields only when the project clearly needs them.

## Workflow

1. Inspect the project for `task-list.md`, `AGENTS.md`, `CLAUDE.md`, planning docs, changelogs, and existing issue notes.
2. If no task list exists, create one from the standard template **in the user's language** (see Language below).
3. If a task list exists, preserve records and normalize only with user approval.
4. Use the standard categories and 7-column table unless project evidence calls for extensions.
5. When the user wants future agents to keep the list updated, install maintenance rules (opt-in). Prefer `install-maintenance` (and `--with-hook` when they want the Stop-hook guarantee). The command follows the same file-selection logic and rule text as `references/maintenance-rule.md` (`CLAUDE.md` if it exists, else `AGENTS.md`, else create `CLAUDE.md`), matched to the task-list's language. Ask before installing. Stop hook commands use `${CLAUDE_PROJECT_DIR}` so they keep working when the session cwd is not the repo root; re-running `--with-hook` upgrades legacy relative paths.
6. Validate malformed/invalid ID formats, duplicate IDs, broken table rows, unsupported actions/statuses, invalid timestamps, summary drift, **and preview-breaking markup** (intra-table blank lines, raw HTML tags in cells, unclosed CommonMark code spans) before finishing. `check` passing is a preview gate, not only a schema gate.
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
- Record both `发现时间` and `完成时间`. Use machine-local timezone timestamps in `YYYY-MM-DD HH:MM` 24-hour format. Use `-` for `完成时间` when the task is not complete. Completed time must not precede found time: `add`/`update` refuse new inversions; `check` warns on legacy ones (exit code unchanged). Correct existing inversions with git evidence via `update --notes-append` — see `references/cli-reference.md`.
- Bug completion normally uses `已修复`; non-bug completion normally uses `已完成`.
- Use `待修复` for open bugs; use `待办` as the generic open status for docs/ops/reviews/adjustments/optimizations/plans (or `待开发` for feature work). Also supported: `进行中`, `已关闭`, `已解决`.
- `已解决` is allowed for troubleshooting items that are diagnosed and closed; prefer `已完成` otherwise. It counts as a completed status.
- `-` is the missing-value placeholder for time (and optional) columns only — it is **not a status**: `add`/`update` reject `--status -` with the allowed list, and `check` flags existing `状态=-` rows by line number.
- Escape literal pipes inside table cells as `\|`. `standardize --apply-safe-fixes` can auto-escape unescaped `|` in overwide rows when status/time columns still align after merge.
- **Preview safety (required):**
  1. Data rows in the same table must be contiguous — **no blank lines between `|` rows**. Blanks are only allowed between the table and the next `##` heading. CommonMark/GFM ends a table at a blank line; later `| ... |` lines become a new (broken) table. `standardize --apply-safe-fixes` collapses those intra-table blanks but **must not rewrite fenced code blocks** (Markdown table *examples* keep their blank lines).
  2. Cells must not contain **raw HTML tags** that change document flow (`<title>`, `<details>`, `<script>`, `<style>`, `<textarea>`, `<svg>`, `<html>`, `<head>`, `<body>`, `<table>`, `<iframe>`, `<xmp>`, `<noembed>`, `<noframes>`, `<plaintext>`). Wrap them in backticks (`` `<title>` ``) or write HTML entities. Do **not** globally replace every `<` — placeholders like `<id>` and comparisons like `a < b` are fine.
  3. **Backticks on each data row must form closed CommonMark code spans**: an opener run of *n* backticks closes on the next unescaped run of exactly *n* (content in between may contain shorter runs). Double-backtick spans may contain a single backtick and may wrap HTML such as `<title>`; character-count parity is not enough — two backticks with no matching closer must fail. A backslash-escaped backtick is literal. For regex character classes, do not leave an opener unclosed; write the word「反引号」or wrap the whole token in a longer fence.
  4. If you hand-edit the Markdown (skipping the CLI), run `check` again. `check` is the preview gate: it must fail on intra-table blanks, raw flow-breaking HTML, and unclosed backtick spans — a green `check` must not mean “preview is fine” unless those rules passed.
  5. After syncing the ledger, if preview still looks wrong, look at intra-table blanks and raw HTML first (and re-run `check`; it should already name the line).
- Cross-link entries with `[[BUG-001]]` / `[[DOC-036]]` wiki syntax; `check` reports dangling references.
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

The English task-list is a faithful translation of the Chinese one: same sections, same ID prefixes (`BUG-`/`ADJ-`/…), same 7-column model — only the labels differ (section titles, column headers, action/status enums, header notes). Header labels must stay within the detected locale: the only cross-label compat is the legacy DEV section writing its description slot as `功能描述` / `Feature Description` — everything cross-language or cross-section (e.g. `事项` under 代码 Bug) is non-standard and rejected. Existing files are handled by auto-detection: `add`/`check`/`summary`/`standardize` sniff the file's language from its structural markers (title and section headings) and validate against the matching locale, so they take no `--lang` flag.

When installing the maintenance rule (workflow step 5, or the standardize maintenance check), match the rule text and Stop-hook message to the task-list's language — see `references/maintenance-rule.md`.

## Standardizing Existing Lists

Use `standardize` when an existing `task-list.md` needs review, cleanup planning, or cautious normalization. This mode is intentionally analytical first: it checks structure, record completeness, classification clarity, and whether the file should remain minimal or use `planning`, `extended`, or `development`.

Default behavior is report-only and must not edit the task list:

```bash
python3 "$SKILL_DIR/scripts/task_list_cli.py" standardize --file task-list.md --report docs/task-list-standardize-report.md
```

Repair requires explicit flags:

- `--apply-safe-fixes`: apply low-risk fixes such as adding missing empty standard sections, collapsing blank lines between table data rows (**not** inside fenced code blocks), and escaping unescaped `|` inside data cells when the row can be realigned (usually notes/description).
- `--migrate-schema`: migrate legacy single-date schemas to `发现时间 / 完成时间`. Data rows whose cell count doesn't match the header (usually an unescaped `|` in a cell) are left untouched and reported as `migrate_warnings` (in `--fix-only` and `--format json` output) instead of being silently skipped; prefer `--apply-safe-fixes` first when the issue is only unescaped pipes.
- `--fix-only`: output modifier — print only a repair summary (no full report); it does not trigger fixes itself, so pair it with `--apply-safe-fixes` or `--migrate-schema`.

Do not automatically rename sections, move records between categories, or rewrite duplicate IDs without user approval. Those are semantic changes and should appear as report recommendations. If the file still has「开源项目调研」, recommend renaming it to「调研事项」**and moving the whole section after「优化事项」** (renaming in place leaves it in the wrong template slot). `standardize` also warns when known sections appear out of template order (Features → Ops → Plans → Optimizations → Research) without relocating rows.

**Schema variants.** A project may legitimately keep the legacy **single-date schema** (`ID/动作/事项/完成日期/状态/备注`, 6-col; or 8-col dev) and not migrate to the canonical dual-date model. `check`/`standardize` auto-detect which schema a file uses and validate against it (`--schema auto|dual|single`, default `auto`), so a single-date file in good shape passes instead of being flagged on every section. When the schema is single-date, the report notes that `--migrate-schema` can upgrade it (opt-in, requires approval). Do not force a migration just because the schema differs from the default. `add` detects the target section's schema too and appends a row with the matching column count (single-date 6-col, dual-date 7-col, or dev 8/9-col), so it works on a single-date file without hand-writing the row.

**Duplicate IDs.** When the report finds duplicate IDs, prefer adding `ADJ-` records that document the old→new ID mapping over silently renumbering — this keeps historical references traceable. The actual cleanup (renumber, merge, or leave as-is) still requires explicit user approval.

### Maintenance-rule check

Every `standardize` report includes a **维护规则状态** section (read-only detection). It reports whether the project already has:

- the canonical **会话结束任务同步** rule in `CLAUDE.md` / `AGENTS.md` (warn if **both** files contain it — install in one file only, prefer `CLAUDE.md`), and
- the optional **Stop hook** in `.claude/settings.json`, and
- **claim vs actual** consistency **per tool**: a Claude hook does not satisfy an AGENTS.md Codex guarantee (and vice versa). If docs claim a Stop-hook / `settings.json` guarantee but no matching hook exists, the report flags `声明与实际不一致` (install the hook or soften the claim).
- hook **portability**: commands that do not use `${CLAUDE_PROJECT_DIR}` (relative or absolute paths) are flagged.
- `.gitignore` ignoring the whole `.claude/` directory (hooks would not clone). Ignoring only `.claude/settings.local.json` is fine.

When the rule is missing, ask the user whether they want future agents to keep the list updated. If they agree, prefer `install-maintenance` (add `--with-hook` only when they also want the Stop-hook guarantee). That CLI path is idempotent and matches `references/maintenance-rule.md`. Manual install from the reference is still fine when the project needs custom wording. Do not install anything without explicit user consent (opt-in).

### Archiving long-lived lists

For large ledgers, archive completed records on demand (never automatic): `archive --file task-list.md --older-than-days 90` moves old completed rows into `task-list-archive-YYYYMM.md`; archived IDs are never reused (subsequent `add` scans sibling archive files). See `references/cli-reference.md` for `--as-of` / `--output`.

## CLI

Use `$SKILL_DIR/scripts/task_list_cli.py` for repeatable operations: `init`, `add`, `update`, `list`, `sections`, `install-maintenance`, `check`, `summary`, `standardize`, `archive`. Before running commands, **read `references/cli-reference.md`** — it carries the command list, flag semantics, schema/locale auto-detection, write-path rollback behavior (new issues roll back, pre-existing ones are disclosed, not deadlocking), `summary --policy` counting calibers, and archiving details.

Safety behaviors to rely on even without the reference: writes roll back only what they broke; a summary rewrite never silently re-buckets a conflicted ledger; `--status -` is rejected; `check` is the preview gate and never auto-moves records. Prefer CLI generation for new files, then review the wording manually.

## References

- `references/task-list-standard.md`: four-project summary, common rules, differences, risks, and maintenance guidance. Single source of the migration matrix.
- `references/cli-reference.md`: full CLI command list, flag semantics, write-path rollback, summary calibers, archiving, and the git-evidence recipe for correcting legacy time inversions (`git log -S` pickaxe + `git show` keyword probes + `update --notes-append`).
- `references/task-list-template.md`: canonical Markdown templates for each profile.
- `references/maintenance-rule.md`: canonical maintenance-rule text (Chinese and English), file-selection logic, language-matching guidance, and optional `Stop`-hook guarantee layer for installing into a project's `CLAUDE.md`/`AGENTS.md`.
- `evals/evals.json`: skill-creator evaluation cases.
- Repo root `VERSION`: current skill version string (`V0.3.7`).
