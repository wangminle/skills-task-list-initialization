# Task List Initialization · 任务清单初始化

**Version:** `V0.3.2`

**[English](#english)** | **[中文](#中文)**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-V0.3.2-blue.svg)](VERSION)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-141%20passing-brightgreen.svg)](tests/)

---

## English

> A Claude Code Skill that creates, standardizes, validates, and maintains a project-level `task-list.md` — a stable task ledger shared by humans and AI agents.

### Overview

Every project accumulates bugs, features, reviews, tests, docs, and ops work. This skill gives all of that work **one predictable Markdown format**: a fixed header, task-type sections, and 7-column tables. The model is intentionally small — optional fields are added only when a project clearly needs them.

### Features

- **One standard, four profiles** — `minimal`, `planning`, `extended`, `development`.
- **Bilingual** — Chinese (Simplified, default) and English task-lists; `init --lang` picks the language, other commands auto-detect it from the file.
- **CLI tooling** — generate, append, update, validate, summarize, and standardize via `task_list_cli.py`.
- **Report-first standardization** — diagnoses before it edits; repairs only with explicit flags.
- **Safe `add` / `update` / strict `check`** — `add`/`update` auto-check after write (rollback on failure); `--notes-file` / `--from-json` avoid shell escaping; `update --id` patches status/notes/times in place. `check` flags malformed IDs and invalid timestamps; `add` refuses non-standard headers rather than guessing column layout.
- **Schema variants** — `check`/`standardize` auto-detect dual-date vs the supported single-date schema (`--schema auto|dual|single`). Compatible single-date labels include **`Done Date` / `完成日期`**, **`Found Date` / `发现日期`**, and also historical `Start Date` / `开始日期` / `Plan Date` / `规划日期` for read/append. `add` matches a section's recognized schema and appends the matching column count.
- **Schema migration** — `--migrate-schema` upgrades losslessly-migrateable 6/8-col single-date headers (`Found Date` / `发现日期` → Found only; `Done Date` / `完成日期` → Done only) while **preserving day precision** (no fabricated `00:00`) and **never copying across semantics**. `Start Date` / `Plan Date` headers are recognized but refused with an explicit unmappable message (file unchanged).
- **Maintenance-rule check** — `standardize` detects the session-end sync rule and Stop hook, and flags **claim vs actual** mismatches (docs assert a Stop-hook guarantee but none is installed).
- **Generic Todo status** — `待办` / `Todo` for non-bug open work; non-standard statuses get suggested mappings.
- **Safe pipe escape** — `--apply-safe-fixes` can merge/escape unescaped `|` in overwide rows.
- **Wiki cross-refs** — `[[BUG-001]]` syntax with dangling-reference detection in `check`.
- **Archive** — `archive --older-than-days N` moves old completed rows to `task-list-archive-YYYYMM.md`.
- **Tested** — 130 unit tests covering init, add, update, list, sections, from-json, notes-file, auto-check rollback, check, summary, standardize, archive, install-maintenance (including CLAUDE_PROJECT_DIR Stop-hook path + legacy relative-path upgrade), aliases, reverse aliases, heading-whitespace tolerance, `--fix-only` semantics, maintenance-rule detection (including claim mismatch and cross-file idempotence), schema-variant detection, timestamp validation, invalid-ID detection, non-standard-header rejection, archive ID non-reuse, pipe escape, wiki refs, status suggestions, case-insensitive section resolution, English locale, summary drift four-field comparison, rate precision cap, time-reverse detection, ID-order regression detection, duplicate-record detection, and Codex hook path validation.

### The Task List Standard

#### Table Schema

The default table is 7 columns, shared across all sections:

```
| ID | Action | Item / Description | Found | Done | Status | Notes |
```

| Field | Rule |
| --- | --- |
| `ID` | `PREFIX-001`, e.g. `BUG-001`; increasing, never reused |
| `Action` | One of 8 fixed actions |
| `Found` | `YYYY-MM-DD HH:MM`, local timezone, 24h |
| `Done` | Same format; `-` when incomplete |
| `Notes` | Highest-density field — root cause, files, tests, review source |

> Labels are localized — Chinese by default (`init --lang zh`) or English (`init --lang en`). ID prefixes (`BUG-`/`ADJ-`/…) and the 7-column model are identical across languages; only the labels differ. The Bugs section uses `Description`; other sections use `Item`. See the bilingual table in `references/task-list-standard.md`.

#### Sections

| Section | Prefix | Purpose |
| --- | --- | --- |
| Bugs | `BUG` | Defects, regressions, security risks |
| Adjustments | `ADJ` | Scope, positioning, config adjustments |
| Reviews | `CHK` | Audit, review, verification, assessment |
| Test Data | `TST` | Test samples, fixtures, datasets |
| Docs | `DOC` | Docs added, revised, archived |
| Features | `DEV` | New features, modules, engineering |
| Ops | `OPS` | Env, deploy, deps, git |

Optional: `Plans PLN`, `Optimizations OPT`, `Research RES`, `Summary`.

#### Actions

The `Action` field must be one of 8 values; near-synonyms are merged:

`Fix` · `Develop` · `Optimize` (absorbs refactor/cleanup) · `Adjust` · `Plan` (absorbs proposal/outline) · `Review` (absorbs audit/recheck/verify/assess) · `Doc` · `Ops`

#### Statuses

`Pending Fix` · `Fixed` · `Todo` · `Pending Dev` · `In Progress` · `Done` · `Resolved` · `Closed`

Bug completion uses `Fixed`; non-bug completion uses `Done`. Prefer `Todo` for generic open non-bug work (docs/ops/reviews/…). The four terminal states (`Fixed` / `Done` / `Resolved` / `Closed`) all count as completed.

### CLI

`task_list_cli.py` is a **stdlib-only** Python 3.8+ CLI (implementation lives under `scripts/_tasklist/`). On Windows, replace `python3` with `python`.

| Command | Purpose |
| --- | --- |
| `init` | Generate a template |
| `add` | Append one or more records (`--from-json`, `--notes-file`; auto-checks after write) |
| `update` | Patch an existing record by `--id` (status, notes-append, times, …) |
| `list` | Filter records by `--id` / `--status` / `--section` / `--keyword` |
| `sections` | List section headings (`--format json`) |
| `check` | Validate ID format, structure, enums & timestamps |
| `summary` | Count records by section; `--write` rewrites the summary table (section-based counts — see note below) |
| `standardize` | Diagnose and optionally repair |
| `archive` | Move old completed rows to an archive file |
| `install-maintenance` | Install session-end sync rule (opt-in; `--with-hook` for Stop hook) |

```bash
SKILL_CLI=skills/task-list-initialization/scripts/task_list_cli.py
# After install under ~/.claude/skills/: SKILL_CLI=$SKILL_DIR/scripts/task_list_cli.py

# Generate a task list (Chinese by default)
python3 "$SKILL_CLI" init --output task-list.md

# English template, extended profile + summary
python3 "$SKILL_CLI" init \
  --lang en --profile extended --with-summary --output task-list.md

# Append a record (section/action/status labels follow the file's language)
python3 "$SKILL_CLI" add \
  --file task-list.md --section "Bugs" --action Fix \
  --description "Login fails" --status "Pending Fix" --notes "Reproduced locally"

# Batch add / long notes without shell escaping
python3 "$SKILL_CLI" add --file task-list.md --from-json entries.json
python3 "$SKILL_CLI" add --file task-list.md --section "Bugs" --action Fix \
  --description "x" --status "Pending Fix" --notes-file notes.txt

# Update status / append notes
python3 "$SKILL_CLI" update --file task-list.md --id BUG-001 \
  --status Fixed --completed-time "2026-08-04 16:00" --notes-append "Verified"

# List / install maintenance / validate
python3 "$SKILL_CLI" list --file task-list.md --status "Pending Fix"
python3 "$SKILL_CLI" sections --file task-list.md --format json
python3 "$SKILL_CLI" install-maintenance --file task-list.md
python3 "$SKILL_CLI" check --file task-list.md

# Validate a single-date (legacy) file against its own schema
python3 "$SKILL_CLI" check --file task-list.md --schema single

# Recompute & write the summary table (counts by physical section)
python3 "$SKILL_CLI" summary --file task-list.md --write

# Diagnose an existing list (report only, no edits)
python3 "$SKILL_CLI" standardize \
  --file task-list.md --report task-list-standardize-report.md
```

`init --lang {zh,en}` selects the language (`zh` = Simplified Chinese, default; `en` = English). `add`/`update`/`check`/`summary`/`standardize` auto-detect the language from the target file, so no `--lang` is needed for them. `add`/`update` auto-run `check` after writing (rollback on failure; `--no-check` to skip). `check`/`standardize` accept `--schema {auto,dual,single}` (default `auto`) to validate a file that intentionally keeps a compatible single-date schema (`Done Date` / `完成日期`, `Found Date` / `发现日期`, etc.). `add` also matches the target section's recognized schema and emits the corresponding column count. `check` flags malformed IDs (`bug-001`) and invalid timestamps; `add` refuses a section whose header does not match a recognized schema (e.g. reordered columns) rather than guessing — fix the header manually. Use `--migrate-schema` for losslessly-migrateable 6/8-col single-date headers (`Found Date` / `Done Date`). `summary --write` aggregates by **physical section**, not ID prefix; if a historical file counted by prefix and has misplaced rows, review before rewriting. Run `--help` on any subcommand for the full option list.

### Profiles

Pick the smallest variant that fits. `development` is intended only when priority and effort estimates are genuinely useful — forcing it on every project adds maintenance cost.

| Profile | Sections |
| --- | --- |
| `minimal` | 7 base sections |
| `planning` | minimal + `Plans` |
| `extended` | planning + `Optimizations` + `Research` |
| `development` | extended, with 9-column `Development` (`Priority` + `Estimate`) |

### Standardizing Existing Lists

`standardize` is **report-first**: by default it only diagnoses and never edits the file. Repairs require explicit flags:

| Flag | Behavior |
| --- | --- |
| `--apply-safe-fixes` | Low-risk fixes, e.g. add missing empty sections |
| `--migrate-schema` | Migrate a supported 6/8-col single-date header to Found / Done (review first; see caveat below) |
| `--fix-only` | Output modifier — print only a repair summary; pair with `--apply-safe-fixes` or `--migrate-schema` |

It will not rename sections, move records, or rewrite duplicate IDs without your approval — those are semantic changes and appear as report recommendations.

Every report also includes a **maintenance-rule status** section that detects whether the project has the session-end sync rule (`CLAUDE.md` / `AGENTS.md`) and the optional `Stop` hook installed. Prefer `install-maintenance` (opt-in; add `--with-hook` for the Stop-hook guarantee) when the user wants it installed — do not install without consent.

A project may legitimately keep a **compatible single-date schema** (`Done Date` / `完成日期`, `Found Date` / `发现日期`, or historical `Start Date` / `Plan Date`; 6-col, or 8-col development). `check`/`standardize` auto-detect and validate that shape (override with `--schema single|dual`). `--migrate-schema` upgrades losslessly-migrateable headers only: `Found Date` → Found (day precision kept, Done = `-`); `Done Date` → Done (Found = `-`); `Start Date` / `Plan Date` are refused with an explicit unmappable message and the file is left unchanged. When duplicate IDs are detected, the report recommends adding `ADJ-` records to document the old→new ID mapping rather than silently renumbering. When `--migrate-schema` hits a data row whose cell count doesn't match the header (almost always an unescaped literal `|` in a cell), it leaves the row untouched and surfaces a `migrate_warnings` list in `--fix-only` and `--format json` output instead of silently undercounting.

### Testing

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

130 tests, all passing.

### Project Structure

```
skills-task-list-initialization/
├── VERSION                                   # V0.3.2
├── skills/task-list-initialization/
│   ├── SKILL.md                              # Skill definition
│   ├── evals/
│   │   └── evals.json                        # Skill-creator eval cases
│   ├── references/
│   │   ├── task-list-standard.md             # Recommended field/schema standard
│   │   ├── task-list-template.md             # Canonical templates
│   │   └── maintenance-rule.md               # Session-end sync rule + Stop hook template
│   └── scripts/
│       ├── task_list_cli.py                  # CLI entry (re-exports)
│       └── _tasklist/                        # Implementation package (_lib.py, _locale.py)
├── tests/
│   └── test_task_list_cli.py                 # Unit tests (130)
├── LICENSE                                   # MIT
└── README.md
```

### License

[MIT](LICENSE) © 2026 fenix-wangminle.

### Changelog

#### V0.3.2

- Summary drift check expanded to four-field comparison (total / done / pending / internal consistency)
- Completion rate precision fixed: 1 decimal place, capped at 99.9% when tasks remain (no false 100%)
- Codex `.codex/hooks.json` Stop-hook detection with script-path existence validation
- Quality warnings: time-reverse (done < found), ID-order regression within sections, exact duplicate records (excluding ID column)
- Profile recommendation threshold tightened: optimize records must be ≥5 AND >5% of total
- Version strings simplified (no build/date suffix); **130** unit tests

#### V0.3.1

- Stop hook installs with `${CLAUDE_PROJECT_DIR}` (relative `.claude/hooks/...` broke when hook cwd ≠ repo root)
- `install-maintenance --with-hook` upgrades legacy relative-path hooks idempotently (`maint_hook_upgraded`)
- Docs: `maintenance-rule.md` / `SKILL.md` warn against relative hook paths; **100** unit tests

#### V0.3.0

- CLI package split (`scripts/_tasklist/`); commands: `update`, `list`, `sections`, `install-maintenance`, `archive`, …
- Safer writes: post-write `check` + rollback; summary sync; explicit ID format/prefix checks; no ID reuse after archive
- Safer migrate/install: refuse unknown/reordered headers; refuse bad/malformed `settings.json` shapes; locale detection ignores notes substrings
- Docs note: single-date `check`/`add` accept Found/Done/Start/Plan date labels; migrate preserves day precision and refuses unmappable Start/Plan; summary counts by section
- Docs/evals aligned (`evals/evals.json`, `$SKILL_DIR` paths); **98** unit tests

---

## 中文

> 一个 Claude Code 技能，用于创建、标准化、校验与维护项目级 `task-list.md`——一份供人类与 AI 协作共用的稳定任务台账。

### 概览

每个项目都会积累 bug、功能、审查、测试、文档和运维事项。本技能把这些事项收敛到**一种可预测的 Markdown 格式**：固定文件头、按类型分区的章节、7 列表格。模型刻意保持精简——仅当项目确实需要时才启用可选字段。

### 特性

- **一套标准、四种模板**——`minimal`、`planning`、`extended`、`development`。
- **中英双语**——中文（简体，默认）与英文 task-list；`init --lang` 选择语言，其余命令按文件自动检测。
- **命令行工具**——通过 `task_list_cli.py` 完成生成、追加、更新、校验、统计与标准化。
- **先诊断后修复**——默认只生成报告，必须显式开启参数才会改写文件。
- **安全 add / update / 严格 check**——`add`/`update` 写后自动校验（失败回滚）；`--notes-file` / `--from-json` 避开 shell 转义；`update --id` 就地改状态/备注/时间。`check` 检出非法 ID 与非法时间戳；`add` 拒绝非标准表头而非猜测列布局。
- **schema 变体**——`check`/`standardize` 自动识别双日期与受支持的单日期 schema（`--schema auto|dual|single`）。兼容的单日期标签包括 **`完成日期` / `Done Date`**、**`发现日期` / `Found Date`**，以及历史的 `开始日期` / `规划日期`（可读可追加）。`add` 按分区已识别的 schema 追加对应列数。
- **结构迁移**——`--migrate-schema` 将可无损迁移的 6/8 列单日期表头升级为双日期：`发现日期` → 仅写入发现时间；`完成日期` → 仅写入完成时间；**保持日精度**（不补造 `00:00`），**禁止跨语义复制**。`开始日期` / `规划日期` 可识别但拒绝迁移并给出明确「无法映射」说明（文件不变）。
- **维护规则检测**——`standardize` 检查会话结束同步规则与 Stop hook，并做**声明 vs 实际**一致性校验（文档声称由 hook 保证触发但实际未装 → 标红）。
- **通用待办状态**——`待办` / `Todo` 覆盖非 Bug 类未完成；非标准状态附带建议映射。
- **自动转义 `|`**——`--apply-safe-fixes` 可合并并转义导致列数错乱的未转义 `|`。
- **条目互引**——`[[BUG-001]]` 语法，`check` 检测悬空引用。
- **归档**——`archive --older-than-days N` 将旧的已完成记录移到 `task-list-archive-YYYYMM.md`。
- **经过测试**——130 个单元测试，覆盖 init、add、update、list、sections、from-json、notes-file、写后校验回滚、check、summary、standardize、archive、install-maintenance（含 `CLAUDE_PROJECT_DIR` Stop hook 路径与旧相对路径升级）、分区别名与反向别名、标题空白容错、`--fix-only` 语义、维护规则声明一致性与跨文件幂等、schema 变体检测、时间戳校验、非法 ID 检出、非标准表头拒绝、归档后 ID 不复用、管道符转义、互引检测、状态建议映射、分区大小写不敏感解析与英文 locale、摘要漂移四字段比较、完成率精度上限、时间倒置检测、ID 行序回退检测、重复记录检测与 Codex hook 路径校验。

### 任务清单标准

#### 表格结构

默认表格为 7 列，所有分区通用：

```
| ID | 动作 | 事项 / 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |
```

| 字段 | 规则 |
| --- | --- |
| `ID` | `前缀-001`，如 `BUG-001`；递增、不复用 |
| `动作` | 8 个固定动作之一 |
| `发现时间` | `YYYY-MM-DD HH:MM`，本地时区 24 小时制 |
| `完成时间` | 同格式；未完成填 `-` |
| `备注` | 信息密度最高——根因、文件、测试、来源 |

#### 分区

| 分区 | 前缀 | 用途 |
| --- | --- | --- |
| 代码 Bug | `BUG` | 缺陷、回归、安全风险 |
| 调整事项 | `ADJ` | 需求口径、定位、配置调整 |
| 检查事项 | `CHK` | 审计、复核、验证、评估 |
| 测试数据 | `TST` | 测试样本、夹具、数据集 |
| 文档维护 | `DOC` | 文档新增、修订、归档 |
| 功能开发 | `DEV` | 新功能、模块、工程能力 |
| 配置运维 | `OPS` | 环境、部署、依赖、Git |

可选分区：`规划事项 PLN`、`优化事项 OPT`、`调研事项 RES`、`统计摘要`。

#### 动作枚举

`动作` 必须为 8 个值之一，近义词需归并：

`修复` · `开发` · `优化`（合并 重构/清理）· `调整` · `规划`（合并 方案/梳理）· `检查`（合并 审计/复核/核查/审查/验证/评估）· `文档` · `运维`

#### 状态

`待修复` · `已修复` · `待办` · `待开发` · `进行中` · `已完成` · `已解决` · `已关闭`

Bug 完成态用 `已修复`，非 Bug 完成态用 `已完成`。通用未完成优先用 `待办`（文档/运维/检查/调整等）。四个终态（`已修复` / `已完成` / `已解决` / `已关闭`）均按完成态统计。

### 命令行工具

`task_list_cli.py` 是 **仅依赖标准库** 的 Python 3.8+ CLI（实现位于 `scripts/_tasklist/`）。Windows 上请把 `python3` 替换为 `python`。

| 命令 | 用途 |
| --- | --- |
| `init` | 生成模板 |
| `add` | 追加一条或多条（`--from-json` / `--notes-file`；写后自动校验） |
| `update` | 按 `--id` 更新已有记录（状态、备注追加、时间等） |
| `list` | 按 `--id` / `--status` / `--section` / `--keyword` 筛选记录 |
| `sections` | 列出分区（`--format json`） |
| `check` | 校验 ID 格式、结构、枚举与时间戳 |
| `summary` | 按物理分区统计；`--write` 回写统计摘要（见下方口径说明） |
| `standardize` | 诊断并可选修复 |
| `archive` | 将旧已完成记录移到归档文件 |
| `install-maintenance` | 安装会话结束同步规则（可选；`--with-hook` 装 Stop hook） |

```bash
SKILL_CLI=skills/task-list-initialization/scripts/task_list_cli.py
# 安装到 ~/.claude/skills/ 后：SKILL_CLI=$SKILL_DIR/scripts/task_list_cli.py

# 生成任务清单（默认中文简体）
python3 "$SKILL_CLI" init --output task-list.md

# 英文模板，extended 并附统计摘要
python3 "$SKILL_CLI" init \
  --lang en --profile extended --with-summary --output task-list.md

# 追加一条记录（语言按文件自动检测）
python3 "$SKILL_CLI" add \
  --file task-list.md --section "代码 Bug" --action 修复 \
  --description "登录失败" --status 待修复 --notes "本地可复现"

# 批量追加 / 长备注（避开 shell 转义）
python3 "$SKILL_CLI" add --file task-list.md --from-json entries.json
python3 "$SKILL_CLI" add --file task-list.md --section "代码 Bug" --action 修复 \
  --description "x" --status 待修复 --notes-file notes.txt

# 更新状态 / 追加备注
python3 "$SKILL_CLI" update --file task-list.md --id BUG-001 \
  --status 已修复 --completed-time "2026-08-04 16:00" --notes-append "已验证"

# 筛选 / 安装维护规则 / 校验
python3 "$SKILL_CLI" list --file task-list.md --status 待修复
python3 "$SKILL_CLI" sections --file task-list.md --format json
python3 "$SKILL_CLI" install-maintenance --file task-list.md
python3 "$SKILL_CLI" check --file task-list.md

# 按单日期（旧）schema 校验
python3 "$SKILL_CLI" check --file task-list.md --schema single

# 重算并回写统计摘要（按物理分区计数）
python3 "$SKILL_CLI" summary --file task-list.md --write

# 诊断已有清单（只出报告，不改文件）
python3 "$SKILL_CLI" standardize \
  --file task-list.md --report task-list-standardize-report.md
```

`init --lang {zh,en}` 选择语言（`zh` 中文简体，默认；`en` 英文）。`add`/`update`/`check`/`summary`/`standardize` 按目标文件自动检测语言，无需传 `--lang`。`add`/`update` 写后默认自动 `check`（失败回滚；`--no-check` 可跳过）。`check`/`standardize` 支持 `--schema {auto,dual,single}`（默认 `auto`），对刻意保留兼容单日期 schema（`完成日期` / `发现日期` 等）的文件按此校验。`add` 会按目标分区已识别的 schema 自动输出对应列数。`check` 检出非法 ID（`bug-001`）与非法时间戳；`add` 遇到表头不符合已识别 schema 的分区（如列顺序错位）会拒绝写入而非猜测——请手工修正表头。对可无损迁移的 6/8 列单日期表头（`发现日期` / `完成日期`）使用 `--migrate-schema`。`summary --write` 按**物理章节**汇总，不是按 ID 前缀；若历史文件原先按前缀统计且存在错放记录，回写前请先核对。运行各子命令的 `--help` 查看完整参数。

### 模板类型

选择刚好够用的最小模板。`development` 仅在优先级与工时估算真正有用时启用——强加到每个项目会增加维护成本。

| 模板 | 分区 |
| --- | --- |
| `minimal` | 7 个基础分区 |
| `planning` | minimal + `规划事项` |
| `extended` | planning + `优化事项` + `调研事项` |
| `development` | extended，使用 9 列 `开发事项`（`优先级` + `预计时间`） |

### 已有清单标准化

`standardize` 采用**先诊断**策略：默认只诊断，绝不改写文件。修复必须显式开启参数：

| 参数 | 行为 |
| --- | --- |
| `--apply-safe-fixes` | 低风险修复，如补齐缺失空分区 |
| `--migrate-schema` | 将受支持的 6/8 列单日期表头迁移为「发现时间 / 完成时间」（先审阅；见下方注意） |
| `--fix-only` | 输出修饰：仅打印修复摘要；需配合 `--apply-safe-fixes` 或 `--migrate-schema` |

未经你同意，它不会重命名章节、移动记录或重写重复 ID——这些属于语义变更，只会作为报告建议出现。

每份报告还包含**维护规则状态**分区，检测项目是否已安装会话结束同步规则（`CLAUDE.md` / `AGENTS.md`）与可选 `Stop` hook。用户同意后优先用 `install-maintenance` 安装（可选 `--with-hook`）；未经同意不要安装。

项目可以合法保留**兼容的单日期 schema**（`完成日期` / `发现日期`，以及历史的 `开始日期` / `规划日期`；6 列，或 8 列开发扩展）。`check`/`standardize` 自动识别并按此校验（可用 `--schema single|dual` 覆盖）。`--migrate-schema` 仅升级可无损迁移的表头：`发现日期` → 仅发现时间（保持日精度，完成时间=`-`）；`完成日期` → 仅完成时间（发现时间=`-`）；`开始日期` / `规划日期` 拒绝并给出「无法映射」说明，文件不变。检测到重复 ID 时，报告会建议新增 `ADJ-` 记录说明旧号→新号映射，而非静默重编号。`--migrate-schema` 遇到列数与表头不符的数据行（几乎总是单元格里未转义的 `|`）时，会保留原行并在 `--fix-only` / `--format json` 输出中以 `migrate_warnings` 列出，不再静默漏报。

### 测试

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

121 个测试，全部通过。

### 项目结构

```
skills-task-list-initialization/
├── VERSION                                   # V0.3.2
├── skills/task-list-initialization/
│   ├── SKILL.md                              # 技能定义
│   ├── evals/
│   │   └── evals.json                        # Skill-creator 评测用例
│   ├── references/
│   │   ├── task-list-standard.md             # 推荐字段 / schema 标准
│   │   ├── task-list-template.md             # 标准模板
│   │   └── maintenance-rule.md               # 会话末同步规则 + Stop hook 模板
│   └── scripts/
│       ├── task_list_cli.py                  # CLI 入口（再导出）
│       └── _tasklist/                        # 实现包（_lib.py、_locale.py）
├── tests/
│   └── test_task_list_cli.py                 # 单元测试（130）
├── LICENSE                                   # MIT
└── README.md
```

### 许可证

[MIT](LICENSE) © 2026 fenix-wangminle。

### 更新日志

#### V0.3.2

- 摘要漂移校验扩展为四字段比较（总数 / 已完成 / 待处理 / 内部一致性）
- 完成率精度修复：1 位小数，有未完成时上限 99.9%（不再假报 100%）
- Codex `.codex/hooks.json` Stop hook 检测，含脚本路径存在性校验
- 质量告警：时间倒置（完成 < 发现）、分区内 ID 行序回退、精确重复记录（排除 ID 列）
- 扩展配置文件建议阈值收紧：优化记录需 ≥5 条且 >总数 5%
- 版本号简化（去除 build/日期后缀）；**130** 个单元测试

#### V0.3.1

- Stop hook 安装改为 `${CLAUDE_PROJECT_DIR}`（相对路径在 hook cwd ≠ 仓库根时会假报脚本缺失）
- `install-maintenance --with-hook` 幂等升级旧相对路径 hook（`maint_hook_upgraded`）
- 文档同步：`maintenance-rule.md` / `SKILL.md` 明确禁止相对路径；**100** 个单元测试

#### V0.3.0

- CLI 拆分为 `scripts/_tasklist/`；新增/完善 `update`、`list`、`sections`、`install-maintenance`、`archive` 等
- 写路径更安全：写后 `check` 回滚、摘要同步、显式 ID 格式/前缀校验、归档后不复用 ID
- migrate/install 更安全：拒未知/重排表头、拒畸形 settings、语言检测忽略备注子串
- 文档标明：单日期 `check`/`add` 接受发现/完成/开始/规划日期标签；migrate 保持日精度并拒绝无法映射的开始/规划日期；summary 按物理分区计数
- 文档与 evals 对齐；**98** 个单元测试
