# Task List Initialization · 任务清单初始化

**[English](#english)** | **[中文](#中文)**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-48%20passing-brightgreen.svg)](tests/)

---

## English

> A Claude Code Skill that creates, standardizes, validates, and maintains a project-level `task-list.md` — a stable task ledger shared by humans and AI agents.

### Overview

Every project accumulates bugs, features, reviews, tests, docs, and ops work. This skill gives all of that work **one predictable Markdown format**: a fixed header, task-type sections, and 7-column tables. The model is intentionally small — optional fields are added only when a project clearly needs them.

### Features

- **One standard, four profiles** — `minimal`, `planning`, `extended`, `development`.
- **Bilingual** — Chinese (Simplified, default) and English task-lists; `init --lang` picks the language, other commands auto-detect it from the file.
- **CLI tooling** — generate, append, validate, summarize, and standardize via `task_list_cli.py`.
- **Report-first standardization** — diagnoses before it edits; repairs only with explicit flags.
- **Safe `add` / strict `check`** — `check` flags malformed IDs (e.g. `bug-001`, `BUG-12`) and invalid timestamps instead of silently skipping them; `add` refuses to write into a section whose header does not match a recognized schema (e.g. a reordered `ID / Status / Action / …`) rather than guessing the column layout and corrupting data. An explicit `--id` that already exists is also refused, instead of silently creating a duplicate.
- **Schema variants** — `check`/`standardize` auto-detect dual-date vs the legitimate legacy single-date schema (`--schema auto|dual|single`), so a single-date file in good shape passes instead of being flagged on every section. `add` matches the section's schema too, appending 6-col rows to single-date files.
- **Schema migration** — upgrades legacy single-date columns to the Found / Done model.
- **Maintenance-rule check** — `standardize` detects whether the project already has the session-end sync rule and Stop hook, and flags them in the report so the agent can offer to install them.
- **Tested** — 48 unit tests covering init, add, check, summary, standardize, aliases, reverse aliases, heading-whitespace tolerance, `--fix-only` semantics, maintenance-rule detection, schema-variant detection, timestamp validation, invalid-ID detection, non-standard-header rejection, case-insensitive section resolution, and the English locale.

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

`Pending Fix` · `Fixed` · `Pending Dev` · `In Progress` · `Done` · `Resolved` · `Closed`

Bug completion uses `Fixed`; non-bug completion uses `Done`. The four terminal states (`Fixed` / `Done` / `Resolved` / `Closed`) all count as completed.

### CLI

`task_list_cli.py` is a single-file, **stdlib-only** Python 3.8+ tool. On Windows, replace `python3` with `python`.

| Command | Purpose |
| --- | --- |
| `init` | Generate a template |
| `add` | Append a record to a section |
| `check` | Validate ID format, structure, enums & timestamps |
| `summary` | Count records; `--write` rewrites the summary table |
| `standardize` | Diagnose and optionally repair |

```bash
# Generate a task list (Chinese by default)
python3 skills/task-list-initialization/scripts/task_list_cli.py init --output task-list.md

# English template, extended profile + summary
python3 skills/task-list-initialization/scripts/task_list_cli.py init \
  --lang en --profile extended --with-summary --output task-list.md

# Append a record (section/action/status labels follow the file's language)
python3 skills/task-list-initialization/scripts/task_list_cli.py add \
  --file task-list.md --section "Bugs" --action Fix \
  --description "Login fails" --status "Pending Fix" --notes "Reproduced locally"

# Validate
python3 skills/task-list-initialization/scripts/task_list_cli.py check --file task-list.md

# Validate a single-date (legacy) file against its own schema
python3 skills/task-list-initialization/scripts/task_list_cli.py check --file task-list.md --schema single

# Recompute & write the summary table
python3 skills/task-list-initialization/scripts/task_list_cli.py summary --file task-list.md --write

# Diagnose an existing list (report only, no edits)
python3 skills/task-list-initialization/scripts/task_list_cli.py standardize \
  --file task-list.md --report docs/task-list-standardize-report.md
```

`init --lang {zh,en}` selects the language (`zh` = Simplified Chinese, default; `en` = English). `add`/`check`/`summary`/`standardize` auto-detect the language from the target file, so no `--lang` is needed for them. `check`/`standardize` accept `--schema {auto,dual,single}` (default `auto`) to validate a file that intentionally keeps the legacy single-date schema. `add` also matches the target section's schema and emits the corresponding column count. `check` flags malformed IDs (`bug-001`) and invalid timestamps; `add` refuses a section whose header does not match a recognized schema (e.g. reordered columns) rather than guessing — run `standardize --migrate-schema` or fix the header first. Run `--help` on any subcommand for the full option list.

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
| `--migrate-schema` | Migrate legacy single-date columns to Found / Done |
| `--fix-only` | Output modifier — print only a repair summary; pair with `--apply-safe-fixes` or `--migrate-schema` |

It will not rename sections, move records, or rewrite duplicate IDs without your approval — those are semantic changes and appear as report recommendations.

Every report also includes a **maintenance-rule status** section that detects whether the project has the session-end sync rule (`CLAUDE.md` / `AGENTS.md`) and the optional `Stop` hook installed. The CLI detects only; the agent asks before installing anything.

A project may legitimately keep the **single-date schema** (`Done Date` / 6-col). `check`/`standardize` auto-detect the schema and validate against it (override with `--schema single|dual`), and the report notes that `--migrate-schema` can upgrade it to dual-date. When duplicate IDs are detected, the report recommends adding `ADJ-` records to document the old→new ID mapping rather than silently renumbering. When `--migrate-schema` hits a data row whose cell count doesn't match the header (almost always an unescaped literal `|` in a cell), it leaves the row untouched and surfaces a `migrate_warnings` list in `--fix-only` and `--format json` output instead of silently undercounting.

### Testing

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

48 tests, all passing.

### Project Structure

```
skills-task-list-initialization/
├── skills/task-list-initialization/
│   ├── SKILL.md                              # Skill definition
│   ├── references/
│   │   ├── task-list-standard.md             # Standard distilled from 4 projects
│   │   ├── task-list-template.md             # Canonical templates
│   │   └── maintenance-rule.md               # Session-end sync rule + Stop hook template
│   └── scripts/
│       └── task_list_cli.py                  # Python CLI
├── tests/
│   └── test_task_list_cli.py                 # Unit tests
├── task-list.md                              # This project's own ledger
├── LICENSE                                   # MIT
└── README.md
```

### License

[MIT](LICENSE) © 2026 fenix-wangminle.

---

## 中文

> 一个 Claude Code 技能，用于创建、标准化、校验与维护项目级 `task-list.md`——一份供人类与 AI 协作共用的稳定任务台账。

### 概览

每个项目都会积累 bug、功能、审查、测试、文档和运维事项。本技能把这些事项收敛到**一种可预测的 Markdown 格式**：固定文件头、按类型分区的章节、7 列表格。模型刻意保持精简——仅当项目确实需要时才启用可选字段。

### 特性

- **一套标准、四种模板**——`minimal`、`planning`、`extended`、`development`。
- **中英双语**——中文（简体，默认）与英文 task-list；`init --lang` 选择语言，其余命令按文件自动检测。
- **命令行工具**——通过 `task_list_cli.py` 完成生成、追加、校验、统计与标准化。
- **先诊断后修复**——默认只生成报告，必须显式开启参数才会改写文件。
- **安全 add / 严格 check**——`check` 检出非法 ID（如 `bug-001`、`BUG-12`）和非法时间戳，不再静默跳过；`add` 遇到表头不符合标准 schema 的分区（如错位的 `ID / 状态 / 动作 / …`）会拒绝写入，避免按列数猜测而把数据填进错误列。显式 `--id` 指定已存在的 ID 时也会拒绝写入，而非静默制造重复。
- **schema 变体**——`check`/`standardize` 自动识别双日期与合法的单日期 schema（`--schema auto|dual|single`），单日期的好文件能通过校验，而非每个分区都报「表头不一致」。`add` 也会按分区 schema 追加对应列数的行。
- **结构迁移**——把旧的单日期列迁移到「发现时间 / 完成时间」。
- **维护规则检测**——`standardize` 检查项目是否已安装会话结束同步规则与 Stop hook，并在报告中标注，由 agent 询问用户后按需安装。
- **经过测试**——48 个单元测试，覆盖 init、add、check、summary、standardize、分区别名、反向别名、标题空白容错、`--fix-only` 语义、维护规则检测、schema 变体检测、时间戳校验、非法 ID 检测、非标准表头拒绝、分区别名大小写不敏感与英文 locale。

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

`待修复` · `已修复` · `待开发` · `进行中` · `已完成` · `已解决` · `已关闭`

Bug 完成态用 `已修复`，非 Bug 完成态用 `已完成`。四个终态（`已修复` / `已完成` / `已解决` / `已关闭`）均按完成态统计。

### 命令行工具

`task_list_cli.py` 是单文件、**仅依赖标准库**的 Python 3.8+ 工具。Windows 上请把 `python3` 替换为 `python`。

| 命令 | 用途 |
| --- | --- |
| `init` | 生成模板 |
| `add` | 向分区追加一条记录 |
| `check` | 校验 ID 格式、结构、枚举与时间戳 |
| `summary` | 统计记录；`--write` 回写统计摘要 |
| `standardize` | 诊断并可选修复 |

```bash
# 生成任务清单（默认中文简体）
python3 skills/task-list-initialization/scripts/task_list_cli.py init --output task-list.md

# 英文模板，extended 并附统计摘要
python3 skills/task-list-initialization/scripts/task_list_cli.py init \
  --lang en --profile extended --with-summary --output task-list.md

# 追加一条记录（语言按文件自动检测）
python3 skills/task-list-initialization/scripts/task_list_cli.py add \
  --file task-list.md --section "代码 Bug" --action 修复 \
  --description "登录失败" --status 待修复 --notes "本地可复现"

# 校验
python3 skills/task-list-initialization/scripts/task_list_cli.py check --file task-list.md

# 按单日期（旧）schema 校验
python3 skills/task-list-initialization/scripts/task_list_cli.py check --file task-list.md --schema single

# 重算并回写统计摘要
python3 skills/task-list-initialization/scripts/task_list_cli.py summary --file task-list.md --write

# 诊断已有清单（只出报告，不改文件）
python3 skills/task-list-initialization/scripts/task_list_cli.py standardize \
  --file task-list.md --report docs/task-list-standardize-report.md
```

`init --lang {zh,en}` 选择语言（`zh` 中文简体，默认；`en` 英文）。`add`/`check`/`summary`/`standardize` 按目标文件自动检测语言，无需传 `--lang`。`check`/`standardize` 支持 `--schema {auto,dual,single}`（默认 `auto`），对刻意保留旧单日期 schema 的文件按此校验。`add` 会按目标分区 schema 自动输出对应列数。`check` 检出非法 ID（`bug-001`）与非法时间戳；`add` 遇到表头不符合标准 schema 的分区（如列顺序错位）会拒绝写入而非猜测——请先运行 `standardize --migrate-schema` 或手工修正表头。运行各子命令的 `--help` 查看完整参数。

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
| `--migrate-schema` | 迁移旧单日期列为「发现时间 / 完成时间」 |
| `--fix-only` | 输出修饰：仅打印修复摘要；需配合 `--apply-safe-fixes` 或 `--migrate-schema` |

未经你同意，它不会重命名章节、移动记录或重写重复 ID——这些属于语义变更，只会作为报告建议出现。

每份报告还包含**维护规则状态**分区，检测项目是否已安装会话结束同步规则（`CLAUDE.md` / `AGENTS.md`）与可选 `Stop` hook。CLI 只负责检测，是否安装由 agent 询问用户后再决定。

项目可以合法保留**单日期 schema**（`完成日期` / 6 列）。`check`/`standardize` 自动识别并按此校验（可用 `--schema single|dual` 覆盖），报告中提示可用 `--migrate-schema` 升级为双日期。检测到重复 ID 时，报告会建议新增 `ADJ-` 记录说明旧号→新号映射，而非静默重编号。`--migrate-schema` 遇到列数与表头不符的数据行（几乎总是单元格里未转义的 `|`）时，会保留原行并在 `--fix-only` / `--format json` 输出中以 `migrate_warnings` 列出，不再静默漏报。

### 测试

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

48 个测试，全部通过。

### 项目结构

```
skills-task-list-initialization/
├── skills/task-list-initialization/
│   ├── SKILL.md                              # 技能定义
│   ├── references/
│   │   ├── task-list-standard.md             # 四项目归纳标准
│   │   ├── task-list-template.md             # 标准模板
│   │   └── maintenance-rule.md               # 会话末同步规则 + Stop hook 模板
│   └── scripts/
│       └── task_list_cli.py                  # 命令行工具
├── tests/
│   └── test_task_list_cli.py                 # 单元测试
├── task-list.md                              # 本项目自身任务台账
├── LICENSE                                   # MIT
└── README.md
```

### 许可证

[MIT](LICENSE) © 2026 fenix-wangminle。
