# Task List Initialization · 任务清单初始化

**Version:** `V0.3.9`

**[English](#english)** | **[中文](#中文)**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-V0.3.9-blue.svg)](VERSION)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](README.md)
[![Tests](https://img.shields.io/badge/tests-350%20passing-brightgreen.svg)](tests/)

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
- **Safe `add` / `update` / strict `check`** — `add`/`update` auto-check after write (rollback on failure); `--notes-file` / `--from-json` avoid shell escaping; `update --id` patches status/notes/times in place. `check` flags malformed IDs, invalid timestamps, **and preview-breaking markup** (intra-table blank lines outside fenced code, raw flow-breaking HTML including `<iframe>`, unclosed CommonMark code spans). `add` refuses non-standard headers rather than guessing column layout; `escape_cell` wraps blacklisted raw HTML tags as inline code on write without rewriting already-closed double-backtick spans.
- **Schema variants** — `check`/`standardize` auto-detect dual-date vs the supported single-date schema (`--schema auto|dual|single`). Compatible single-date labels include **`Done Date` / `完成日期`**, **`Found Date` / `发现日期`**, and also historical `Start Date` / `开始日期` / `Plan Date` / `规划日期` for read/append. `add` matches a section's recognized schema and appends the matching column count.
- **Schema migration** — `--migrate-schema` upgrades losslessly-migrateable 6/8-col single-date headers (`Found Date` / `发现日期` → Found only; `Done Date` / `完成日期` → Done only) while **preserving day precision** (no fabricated `00:00`) and **never copying across semantics**. `Start Date` / `Plan Date` headers are recognized but refused with an explicit unmappable message (file unchanged).
- **Maintenance-rule check** — `standardize` detects the session-end sync rule and Stop hook, and flags **per-tool claim vs actual** mismatches (a Claude hook does not satisfy a Codex claim), rule duplication, hooks that omit `${CLAUDE_PROJECT_DIR}`, and `.gitignore` ignoring the whole `.claude/` directory.
- **Generic Todo status** — `待办` / `Todo` for non-bug open work; non-standard statuses get suggested mappings. `-` is the missing-value placeholder for time/optional columns only — not a status: `add`/`update` reject `--status -`, and `check` flags `状态=-` rows by line number (REQ-12).
- **Safe pipe escape + intra-table blanks** — `--apply-safe-fixes` can merge/escape unescaped `|` in overwide rows and delete blank lines between table data rows (**not** inside fenced code blocks).
- **Wiki cross-refs** — `[[BUG-001]]` syntax with dangling-reference detection in `check`.
- **Archive** — `archive --older-than-days N` moves old completed rows to `task-list-archive-YYYYMM.md`.
- **Tested** — 350 unit tests covering layered domain/parser/validator/maintenance modules plus init, add, update, list, sections, from-json, notes-file, auto-check rollback (baseline-aware: pre-existing issues don't block writes), check, summary, standardize, archive, install-maintenance (including CLAUDE_PROJECT_DIR Stop-hook path + legacy relative-path upgrade), aliases, reverse aliases, heading-whitespace tolerance, `--fix-only` semantics, maintenance-rule detection (including per-tool claim mismatch, rule duplication, non-portable hook paths, `.claude/` gitignore, idempotent re-runs), schema-variant detection, timestamp validation, invalid-ID detection, non-standard-header rejection, archive ID non-reuse, pipe escape, wiki refs, status suggestions, case-insensitive section resolution, English locale, summary drift four-field comparison, summary caliber policy (auto refuses to write on prefix/section conflicts), check prefix-misplacement warnings, width-anomalous-row exclusion from statistics, dash-as-status rejection, install-maintenance/archive fault-injection rollback, eval-meta placeholder guards, rate precision cap, time-reverse detection, ID-order regression detection, duplicate-record detection, Codex hook path validation, section-order recommendations, and **preview-safety** (intra-table blanks, fenced-code exclusion, per-cell-matched raw HTML including iframe, CommonMark backtick pairing, delimiter-row adjacency/width), by-prefix omission of empty custom sections, report-path identity refusal (fleet/standardize `--report` vs an input ledger), concurrent shared-archive locking, pipe-escaped summary category titles, overwide-row ID registration, empty-summary completeness gate (a summary reduced to its header and delimiter fails `check` naming the missing category). Heading scans on write/migrate/check skip fenced examples; mixed dual+single files pass `--schema auto`.

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
| `summary` | Count records by section; `--write` rewrites the summary table under the default `auto` policy — refuses to write when prefix/section calibers conflict (see note below) |
| `standardize` | Diagnose and optionally repair |
| `archive` | Move old completed rows to an archive file |
| `install-maintenance` | Install session-end sync rule (opt-in; `--with-hook` for Stop hook — requires bash on PATH) |
| `fleet` | Batch-inspect every `task-list.md` under a root directory (`--exclude` globs, `--apply-safe-fixes`, `--format json`, `--report`; exit 1 if any file fails or the scan is incomplete; exit 2 if the root is missing or the report cannot be written) |

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

# Recompute & write the summary table (default auto policy; refuses on caliber conflict)
python3 "$SKILL_CLI" summary --file task-list.md --write

# Diagnose an existing list (report only, no edits)
python3 "$SKILL_CLI" standardize \
  --file task-list.md --report task-list-standardize-report.md
```

`init --lang {zh,en}` selects the language (`zh` = Simplified Chinese, default; `en` = English). `add`/`update`/`check`/`summary`/`standardize` auto-detect the language from the target file, so no `--lang` is needed for them. `add`/`update` auto-run `check` after writing (rollback on failure; `--no-check` to skip). `check`/`standardize` accept `--schema {auto,dual,single}` (default `auto`) to validate a file that intentionally keeps a compatible single-date schema (`Done Date` / `完成日期`, `Found Date` / `发现日期`, etc.). `add` also matches the target section's recognized schema and emits the corresponding column count. `check` flags malformed IDs (`bug-001`) and invalid timestamps; `add` refuses a section whose header does not match a recognized schema (e.g. reordered columns) rather than guessing — fix the header manually. Use `--migrate-schema` for losslessly-migrateable 6/8-col single-date headers (`Found Date` / `Done Date`). `summary --write` honors `--policy auto|by-section|by-prefix` (default `auto`): when the by-section and by-prefix calibers disagree (misplaced rows), `auto` **refuses to write** (non-zero exit, file unchanged) and prints both counts — pass `--policy by-prefix` to keep prefix-caliber summaries or `--policy by-section` to switch to physical sections. `check` also prints prefix-misplacement warnings (warning-level: exit code unchanged, records never auto-moved), and statistics exclude width-anomalous rows (usually an unescaped `|`); the read-only `summary` view reports the excluded-row count. Run `--help` on any subcommand for the full option list.

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
| `--apply-safe-fixes` | Low-risk fixes, e.g. add missing empty sections, collapse intra-table blanks |
| `--migrate-schema` | Migrate a supported 6/8-col single-date header to Found / Done (review first; see caveat below) |
| `--fix-only` | Output modifier — print only a repair summary; pair with `--apply-safe-fixes` or `--migrate-schema` |

It will not rename sections, move records, or rewrite duplicate IDs without your approval — those are semantic changes and appear as report recommendations.

Every report also includes a **maintenance-rule status** section that detects whether the project has the session-end sync rule (`CLAUDE.md` / `AGENTS.md`) and the optional `Stop` hook installed. Prefer `install-maintenance` (opt-in; add `--with-hook` for the Stop-hook guarantee) when the user wants it installed — do not install without consent. `--with-hook` requires a real `bash` on `PATH` (plain Windows ships none — install Git Bash or WSL first); the installer refuses without one rather than writing a hook that can never run.

A project may legitimately keep a **compatible single-date schema** (`Done Date` / `完成日期`, `Found Date` / `发现日期`, or historical `Start Date` / `Plan Date`; 6-col, or 8-col development). `check`/`standardize` auto-detect and validate that shape (override with `--schema single|dual`). `--migrate-schema` upgrades losslessly-migrateable headers only: `Found Date` → Found (day precision kept, Done = `-`); `Done Date` → Done (Found = `-`); `Start Date` / `Plan Date` are refused with an explicit unmappable message and the file is left unchanged. When duplicate IDs are detected, the report recommends adding `ADJ-` records to document the old→new ID mapping rather than silently renumbering. When `--migrate-schema` hits a data row whose cell count doesn't match the header (almost always an unescaped literal `|` in a cell), it leaves the row untouched and surfaces a `migrate_warnings` list in `--fix-only` and `--format json` output instead of silently undercounting.

### Testing

```bash
python3 -m unittest discover -s tests/scripts -p 'test_*.py'
```

350 tests, all passing.

### Project Structure

```
skills-task-list-initialization/
├── VERSION                                   # V0.3.9
├── skills/task-list-initialization/
│   ├── SKILL.md                              # Skill definition
│   ├── evals/
│   │   ├── evals.json                        # Task-execution eval cases (fixtures wired)
│   │   ├── trigger-evals.json                # Trigger/behavior eval matrix (14 cases)
│   │   ├── run-evals.py                      # Headless real-agent eval runner
│   │   ├── aggregate-benchmark.py            # Run-telemetry aggregation (benchmark.json)
│   │   └── fixtures/                         # Eval precondition fixtures
│   ├── references/
│   │   ├── task-list-standard.md             # Recommended field/schema standard
│   │   ├── cli-reference.md                  # Full CLI commands, flags, rollback/caliber semantics
│   │   ├── task-list-template.md             # Canonical templates
│   │   └── maintenance-rule.md               # Session-end sync rule + Stop hook template
│   └── scripts/
│       ├── task_list_cli.py                  # CLI entry (re-exports public_api)
│       └── _tasklist/                        # Implementation package (cli/parser/validator/locales/public_api/…)
├── tests/
│   └── scripts/                               # Test suite (all test_*.py + shared helpers)
│       ├── helpers.py                         # Shared CLI test helpers
│       └── test_*.py                          # Unit tests (350)
├── LICENSE                                   # MIT
└── README.md
```

### License

[MIT](LICENSE) © 2026 fenix-wangminle.

### Changelog

#### V0.3.9

- BUG-111: an existing summary containing only its header and delimiter no longer bypasses missing-category checks; removing all summary data rows from a ledger now fails `check`. Ledgers without the optional summary still pass. Four new CLI regressions cover Chinese/English complete templates, valid counting policies, the absent-summary control, and `summary --write` recovery — **350** unit tests.
- DEV-030: new `fleet` batch-inspection subcommand — point it at a root directory and it recursively finds every `task-list.md`, runs the full per-file diagnosis (`check` + `standardize` diagnostics + maintenance-rule status, each in the file's own language), and prints a per-file table plus aggregate report; `--exclude` globs skip backup/eval/runtime trees (`.git`/`node_modules`/`.stversions` excluded by default), `--apply-safe-fixes` repairs in place under the write lock and re-checks, `--format json` / `--report` feed automation; exit codes (0 pass or empty tree / 1 a file fails, one file's diagnosis errors, or the scan is incomplete / 2 missing root or the report cannot be written) suit cron and CI health gates — the institutionalized replacement for hand-rolled multi-project check loops
- DEV-031: cross-process write lock — every write command (`add`/`update`/`archive`/`summary --write`/`standardize` repair/`init`/`fleet --apply-safe-fixes`) holds an exclusive advisory lock on a `task-list.md.lock` sidecar (POSIX `flock`, Windows `msvcrt`; 10s timeout with localized `lock_timeout`, auto-released on process death, dry-run and read-only commands never lock), closing the read-modify-write race that let two concurrent sessions mint duplicate IDs
- DEV-033: custom-section table constraint — a table outside the standard sections whose first column holds strict task IDs (`^[A-Z]+-\d{3,}$`) but has no recognized record header is now a `check` **error**; agents can no longer improvise record tables with pseudo-status columns (the field incident: a review-log section using P2/P3 as 状态)
- DEV-032: precision-aware time-inversion comparison — both sides timestamped → minute-level compare; either side date-only (legacy single→dual-date migration residue) → calendar-day compare only, so same-day pairs no longer warn forever and every remaining inversion is a real one (BUG-094 additionally keeps explicit date-only writes at day precision on disk, so the tool itself never manufactures one)
- BUG-094: explicit date-only `--found-time` / `--completed-time` / `--date` values now land verbatim (`YYYY-MM-DD`, no `00:00` padding) — the padded cell used to create a permanent same-day "inversion" that check flagged forever and that even blocked later notes-only updates via the write-path rollback
- BUG-095/BUG-096: `fleet --apply-safe-fixes` isolates per-file failures (lock timeout or I/O error → status=error entry, sweep continues, exit code stays non-zero) instead of aborting the whole sweep with a traceback; the Python 3.9+ `Path.is_relative_to` call is gone, restoring the 3.8+ compatibility promise (AST-level regression guard included)
- BUG-097/BUG-100: the custom-section gate validates a *supported record schema* (any registered dual/single-date header shape) rather than "has some header" — a pseudo header like `| ID | 问题 | 结论 |` can no longer smuggle ID rows past per-row validation into the by-prefix summary; smuggled rows still register their identities and `[[refs]]` globally, so cross-table duplicate IDs are reported, refs to smuggled-only IDs are not dangling, and two-digit ID shapes are flagged
- BUG-098/BUG-099/BUG-101: fleet output & lock hardening — empty-tree `--format json` stays parseable JSON; the `--report` file lists user `--exclude` patterns and escapes `|` in paths; unreadable directories fail the sweep loudly (`scan_errors`, exit 1) instead of a fake all-pass; an unwritable `--report` path exits 2 with a localized message; locking a missing target no longer creates its parent directory or a stray sidecar; lock-creation failures report a localized message naming the ledger; the lock-timeout message names the ledger path, not the internal `.lock` sidecar; `task-list.md.lock` is gitignored here (consumers should ignore `*.md.lock` too)
- Tests: 12 new regressions covering the BUG-094…101 batch (day-precision landing + post-write check + follow-up update, per-file lock isolation, missing-target side effects, read-only-directory lock error, pseudo-header smuggling, smuggled identity/ref semantics, empty-tree JSON, report excludes / unwritable path / pipe escaping, unreadable-dir disclosure, 3.9+-API AST guard, mocked Windows msvcrt lock branch, English-locale fleet matrix) — **324** unit tests
- BUG-102/BUG-103/BUG-104: one project's undecodable maintenance file (`CLAUDE.md` and the same class of sibling files) is recorded as `status=error` and the sweep continues, so JSON still contains the other projects; an empty tree in the default text mode still writes and overwrites `--report`; report paths go through `escape_cell`, so a name that contains both a backslash and a pipe no longer splits a column — **327** unit tests
- BUG-105: `atomic_write` emits `\n` verbatim instead of translating to the platform line separator — a Windows-side install had written CRLF into the bash hook script (`fi\r` is not `fi`; the Stop hook died at parse time), and the installer's idempotency check compared through `read_text()`, whose universal-newline read masked the corruption as "equal to template". Writes are now byte-faithful LF (matching the BUG-090 rollback twin) and the check compares raw bytes, so re-running `install-maintenance --with-hook` repairs a corrupted script and says so — **329** unit tests
- BUG-106: `fleet --report` and `standardize --report` refuse (exit 2, nothing written, ledger bytes untouched) when the report path resolves to the same file as an input ledger — relative/`..`/symlink aliases are collapsed via `resolve()` before comparing; for `fleet` the check runs before the sweep, so a report clash also suppresses `--apply-safe-fixes` repairs instead of repairing a file the report is about to overwrite
- BUG-107: `archive` holds a second lock, on the archive file itself, from its first read through commit (lock order always main → archive; only nested-lock command) — two different main ledgers archiving concurrently into one shared archive used to both read the archive before either wrote, so the later commit silently dropped the other side's records; duplicate-ID detection now runs inside the critical section on fresh data, and mutual cross-archiving degrades to a clean `lock_timeout`, never data loss — pinned by a barrier-synchronized two-process regression verified to fail on the unfixed code
- BUG-108: `check` fails on a record-table header whose GFM delimiter row is missing or whose column count differs from the header (CommonMark requires the delimiter IMMEDIATELY after the header with the same width; otherwise the whole table renders as plain text in preview) — line numbers reported for both cases, fenced example tables never count, and `add` refuses to append into the broken section (naming the line) while other sections in the same file stay writable with the defect disclosed as residual
- BUG-109: summary tables escape `|` in category titles (`研究 \| 调试`), so a legal custom heading like `## 研究 | 调试` no longer produces a 6-cell row in a 5-column table with shifted numbers; `check` now flags legacy width-broken summary rows and categories missing from the written table (shape first, numbers second; conservative when the caliber is ambiguous/stale)
- BUG-110: width-anomalous rows still register their strict ID — a duplicate ID hidden in an overwide row is now reported, and a `[[ref]]` to an ID that only exists in an overwide row is no longer falsely dangling — while such rows stay excluded from completion-rate statistics
- Tests: 17 new regressions in `tests/scripts/test_cli_bugfix_106_110.py` (report-overwrite refusal + dotted alias + repair-abort + distinct-path control, standardize report clash, two-process concurrent archive with a `commit_all` rendezvous barrier, separator missing/width/blank-line/fenced-exempt/add-refusal/add-healthy-section, pipe-title write + idempotency + legacy width + missing category, overwide-row duplicate + no-false-dangling) — **346** unit tests

#### V0.3.8

- BUG-089: Stop-hook template probes `python3 -c 'import sys'` and falls back to `python` — on Windows the Microsoft Store `python3` stub (non-zero exit, no output) silently disabled the hook and degraded the per-session guard to a single global `default`; `install-maintenance --with-hook` redeploys the fixed script and upgrades legacy relative commands to `${CLAUDE_PROJECT_DIR}` (idempotent)
- BUG-090: rollback is byte-faithful — `_restore` writes the snapshot via a binary atomic writer instead of decoding back through text mode, which on Windows re-translated `\n` and corrupted CRLF files (`\r\n` → `\r\r\n`) on every `commit_all` rollback
- BUG-092: `tests/scripts/test_evals_meta.py` lacked `from __future__ import annotations`, so its `Path | None` hint raised `TypeError` at import on Python 3.9 and took the whole suite down despite the advertised 3.8+ support — the suite now runs green on 3.9 / 3.13 / 3.14 (a repo-wide audit found no other missing deferred-annotation module, runtime-evaluated alias, or 3.9+-only API)
- BUG-093: `install-maintenance --with-hook` probes `shutil.which("bash")` up front and refuses (exit 1, nothing written, `--dry-run` included) on machines without bash, instead of installing a Stop hook that fails on every trigger (plain Windows ships no bash); install-path tests pin both sides via a PATH shim so they stay green on bash-less hosts, and README / cli-reference / SKILL.md now state the bash requirement
- Tests: hook-execution tests resolve a real bash on Windows (skipping the WSL launcher stub in System32); BUG-068 permission assertion is Windows-aware (read-only bit instead of mode bits); new regressions pin the interpreter fallback in both locales, the cross-platform byte-exact CRLF rollback, and the bash-probe refusal/install pair — **290** unit tests

#### V0.3.7

- BUG-082: baseline-aware write rollback - `add`/`update` diff post-write issues against the pre-write baseline: newly introduced problems roll back, pre-existing ones keep the write and are disclosed on stderr (no more deadlocks on legacy debt)
- BUG-083: preview-safety raw-HTML matching is per-cell (a `<title>` mentioned legitimately no longer matches a `<details>` elsewhere in the row)
- BUG-084: rollback fingerprints no longer collapse ID digits, so `[[BUG-002]]` and `[[BUG-003]]` are distinct
- BUG-085: `check` prints line-level warnings for existing time inversions (completed < found) - warning-class, exit code unchanged, since the write path already refuses new ones
- BUG-086: `check` warns on completed-status rows whose 完成时间 is still `-`
- REQ-09: real-agent eval harness (`evals/run-evals.py`, `evals/aggregate-benchmark.py`) with tool-deferral isolation (workspace-level `ENABLE_TOOL_SEARCH` override for headless runs); first `evals/benchmark.json` produced - 6 configurations x 3 runs, 100% task success - guarded by `test_evals_meta.py`
- Docs: full CLI reference moved to `references/cli-reference.md`, including the git-evidence recipe for correcting legacy time inversions
- `ruff check` clean on scripts and tests; **286** unit tests

#### V0.3.6

- REQ-12: `-` is the missing-value placeholder for time/optional columns only — **not a status**; `add`/`update` reject `--status -` with the allowed enum, `check` flags existing `状态=-` rows by line number
- REQ-09/10 eval trustworthiness: `evals/trigger-evals.json` (14 trigger/behavior cases per the plan matrix) with two new fixtures; mechanical benchmark guard in `test_evals_meta.py` (placeholder strings / all-zero tokens & tool_calls / declared-vs-actual run count fail the test once `evals/benchmark.json` exists); eval workspaces gitignored
- REQ-13/14/15 acceptance hardening: CLI-level fault injection for `install-maintenance` (hook-script write failure rolls the agent file back) and `archive` (archive-write failure leaves the main ledger untouched); the 5 read commands pin exit code 1 on missing files; 21/22 renders as `95.5%` and full completion as `100%`
- BUG-075/076 regression tests added (unknown ID prefixes are not "misplaced"; unregistered custom sections count in the written summary)
- `ruff check` clean on scripts and tests; **270** unit tests

#### V0.3.5

- `summary --policy auto|by-section|by-prefix` (default `auto`): with misplaced rows (ID prefix vs physical section) the two calibers disagree and `auto` **refuses to write** (non-zero exit, file unchanged), printing both counts plus which caliber the existing summary matches; `add` / `update` skip the summary auto-sync with a warning instead of silently re-bucketing
- `check` prints prefix-misplacement warnings (line, ID, section, expected prefix); warnings do not fail the gate and records are never auto-moved
- Statistics exclude width-anomalous rows (cell count vs header count, usually an unescaped `|`): cell fragments no longer surface as status names and totals no longer count broken rows; the read-only `summary` view reports the excluded-row count
- `ruff check` clean on scripts and tests; **232** unit tests

#### V0.3.4

- Split the former `_lib.py` monolith into layered modules: `domain` / `parser` / `renderer` / `schemas` / `summary` / `validator` / `migration` / `maintenance` / `cli`; `_lib.py` removed
- CLI entry uses explicit exports via `_tasklist/public_api.py` (formal compat list, including `detect_locale`; no stdlib star-import leaks); `_locale.py` is a compatibility re-export of `locales.py`
- Heading scans (`add` / `summary --write` / `--migrate-schema` / `--apply-safe-fixes` / duplicate-section check) skip fenced code, so Markdown table examples cannot steal insert points or rewrite real rows
- Mixed dual+single files pass `--schema auto`; `add` no longer rolls back a valid mixed ledger
- `--from-json` rejects non-string fields; `escape_cell` strips CR/line-breaks and escapes backslashes; GFM-invalid separators and unpadded dates fail `check`
- Archive merge refuses cross-schema column mismatch; unbraced `$CLAUDE_PROJECT_DIR` is recognized; `atomic_write` preserves file mode
- Maintenance-rule text is a single source of truth with `references/maintenance-rule.md`; CLI tests split into `test_cli_*.py` plus module tests
- `ruff check` clean on scripts and tests; **209** unit tests

#### V0.3.3

- `check` is a Markdown preview gate: intra-table blanks (fenced code excluded), raw flow-breaking HTML (`<title>`, `<iframe>`, `<xmp>`, …), and unclosed CommonMark code spans fail with line numbers
- `--apply-safe-fixes` collapses blank lines between table data rows (section-gap blanks and fenced examples kept)
- `escape_cell` wraps blacklisted raw HTML as inline code without rewriting closed double-backtick spans; placeholders like `<id>` and `a < b` are left alone
- `standardize` flags per-tool hook-claim mismatch, rule duplication, non-portable hook paths, `.claude/` gitignore, and section-order drift; legacy「开源项目调研」recommendations include moving the whole section
- Field rules in `SKILL.md` / `task-list-standard.md`; evals 7–8 cover preview-break fixtures; **168** unit tests

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
- **安全 add / update / 严格 check**——`add`/`update` 写后自动校验（新引入的问题回滚；存量问题保留写入并在 stderr 提示）；`--notes-file` / `--from-json` 避开 shell 转义；`update --id` 就地改状态/备注/时间。`check` 检出非法 ID、非法时间戳，以及**预览损坏写法**（表内空行且跳过围栏代码、按单元格匹配的裸 HTML、未按 CommonMark 闭合的反引号）。`add` 拒绝非标准表头而非猜测列布局；写入时把黑名单裸 HTML 标签包进行内代码，且不改写已闭合的双反引号 span。
- **schema 变体**——`check`/`standardize` 自动识别双日期与受支持的单日期 schema（`--schema auto|dual|single`）。兼容的单日期标签包括 **`完成日期` / `Done Date`**、**`发现日期` / `Found Date`**，以及历史的 `开始日期` / `规划日期`（可读可追加）。`add` 按分区已识别的 schema 追加对应列数。
- **结构迁移**——`--migrate-schema` 将可无损迁移的 6/8 列单日期表头升级为双日期：`发现日期` → 仅写入发现时间；`完成日期` → 仅写入完成时间；**保持日精度**（不补造 `00:00`），**禁止跨语义复制**。`开始日期` / `规划日期` 可识别但拒绝迁移并给出明确「无法映射」说明（文件不变）。
- **维护规则检测**——`standardize` 检查会话结束同步规则与 Stop hook，并做**按工具**的声明 vs 实际校验（Claude hook 不能顶替 Codex 声明）；同时告警规则双写、未使用 `${CLAUDE_PROJECT_DIR}` 的 hook、以及 `.gitignore` 忽略整个 `.claude/`。
- **通用待办状态**——`待办` / `Todo` 覆盖非 Bug 类未完成；非标准状态附带建议映射。
- **自动转义 `|` 与表内空行**——`--apply-safe-fixes` 可合并并转义导致列数错乱的未转义 `|`，并删除数据行之间的空行（**不改围栏代码块**）。
- **条目互引**——`[[BUG-001]]` 语法，`check` 检测悬空引用。
- **归档**——`archive --older-than-days N` 将旧的已完成记录移到 `task-list-archive-YYYYMM.md`。
- **经过测试**——350 个单元测试，覆盖分层 domain/parser/validator/maintenance 模块以及 init、add、update、list、sections、from-json、notes-file、写后校验回滚（基线感知：存量问题不阻断写入）、check、summary、standardize、archive、install-maintenance（含 `CLAUDE_PROJECT_DIR` Stop hook 路径与旧相对路径升级）、分区别名与反向别名、标题空白容错、`--fix-only` 语义、维护规则声明一致性（按工具拆分、规则双写、非便携 hook、`.claude/` gitignore）与跨文件幂等、schema 变体检测、时间戳校验、非法 ID 检出、非标准表头拒绝、归档后 ID 不复用、管道符转义、互引检测、状态建议映射、分区大小写不敏感解析与英文 locale、摘要漂移四字段比较、摘要双口径策略（前缀/分区冲突时 auto 拒绝写入）、check 前缀错位警告、列宽异常行统计排除、`状态=-` 拒绝、install-maintenance/archive 故障注入回滚、evals 元数据占位符守卫、完成率精度上限、时间倒置检测（写入门禁+check 行级存量警告）、ID 行序回退检测、重复记录检测、Codex hook 路径校验、章节顺序建议，以及**预览安全**（表内空行、围栏代码排除、按单元格匹配的裸 HTML、CommonMark 反引号配对、分隔行邻接与列宽），by-prefix 空自定义节省略、报告路径身份拒绝（fleet/standardize `--report` 与输入台账为同一文件即拒绝）、共享归档并发锁、摘要分类标题管道转义、宽行 ID 登记、空摘要完整性门禁（只剩表头与分隔行的摘要会被 `check` 点名缺失分类）。写入/迁移/check 的标题扫描会跳过围栏内示例；混合 dual+single 文件在 `--schema auto` 下通过。

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
| `summary` | 按物理分区统计；`--write` 默认 `auto` 口径，前缀/分区口径冲突时拒绝写入（见下方口径说明） |
| `standardize` | 诊断并可选修复 |
| `archive` | 将旧已完成记录移到归档文件 |
| `install-maintenance` | 安装会话结束同步规则（可选；`--with-hook` 装 Stop hook——需 PATH 上有 bash） |
| `fleet` | 批量巡检根目录下所有 `task-list.md`（`--exclude` glob、`--apply-safe-fixes`、`--format json`、`--report`；任一文件失败或扫描不完整时退出码为 1；根目录不存在或报告写不进去时为 2） |

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

# 重算并回写统计摘要（默认 auto 口径，冲突时拒绝写入）
python3 "$SKILL_CLI" summary --file task-list.md --write

# 诊断已有清单（只出报告，不改文件）
python3 "$SKILL_CLI" standardize \
  --file task-list.md --report task-list-standardize-report.md
```

`init --lang {zh,en}` 选择语言（`zh` 中文简体，默认；`en` 英文）。`add`/`update`/`check`/`summary`/`standardize` 按目标文件自动检测语言，无需传 `--lang`。`add`/`update` 写后默认自动 `check`（新引入的问题回滚，存量问题保留写入并在 stderr 提示存量数量；`--no-check` 可跳过）。`check`/`standardize` 支持 `--schema {auto,dual,single}`（默认 `auto`），对刻意保留兼容单日期 schema（`完成日期` / `发现日期` 等）的文件按此校验。`add` 会按目标分区已识别的 schema 自动输出对应列数。`check` 检出非法 ID（`bug-001`）与非法时间戳；`add` 遇到表头不符合已识别 schema 的分区（如列顺序错位）会拒绝写入而非猜测——请手工修正表头。对可无损迁移的 6/8 列单日期表头（`发现日期` / `完成日期`）使用 `--migrate-schema`。`summary --write` 支持 `--policy auto|by-section|by-prefix`（默认 `auto`）：按前缀与按分区两种口径不一致（存在错放记录）时，`auto` **拒绝写入**（非零退出、文件不变）并打印双口径对比——用 `--policy by-prefix` 保持按前缀统计，或 `--policy by-section` 改按物理分区。`check` 另输出前缀错位警告（警告级：不改变退出码、不自动移动记录）；统计排除列宽与表头不符的行（多为未转义 `|`），只读 `summary` 会提示排除行数。运行各子命令的 `--help` 查看完整参数。

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
| `--apply-safe-fixes` | 低风险修复，如补齐缺失空分区、删除表内空行 |
| `--migrate-schema` | 将受支持的 6/8 列单日期表头迁移为「发现时间 / 完成时间」（先审阅；见下方注意） |
| `--fix-only` | 输出修饰：仅打印修复摘要；需配合 `--apply-safe-fixes` 或 `--migrate-schema` |

未经你同意，它不会重命名章节、移动记录或重写重复 ID——这些属于语义变更，只会作为报告建议出现。

每份报告还包含**维护规则状态**分区，检测项目是否已安装会话结束同步规则（`CLAUDE.md` / `AGENTS.md`）与可选 `Stop` hook。用户同意后优先用 `install-maintenance` 安装（可选 `--with-hook`）；未经同意不要安装。`--with-hook` 要求 `PATH` 上有可用的 `bash`（纯 Windows 默认没有——请先安装 Git Bash 或 WSL）；探测不到时安装器整体拒绝，而不是写入一个永远无法运行的 hook。

项目可以合法保留**兼容的单日期 schema**（`完成日期` / `发现日期`，以及历史的 `开始日期` / `规划日期`；6 列，或 8 列开发扩展）。`check`/`standardize` 自动识别并按此校验（可用 `--schema single|dual` 覆盖）。`--migrate-schema` 仅升级可无损迁移的表头：`发现日期` → 仅发现时间（保持日精度，完成时间=`-`）；`完成日期` → 仅完成时间（发现时间=`-`）；`开始日期` / `规划日期` 拒绝并给出「无法映射」说明，文件不变。检测到重复 ID 时，报告会建议新增 `ADJ-` 记录说明旧号→新号映射，而非静默重编号。`--migrate-schema` 遇到列数与表头不符的数据行（几乎总是单元格里未转义的 `|`）时，会保留原行并在 `--fix-only` / `--format json` 输出中以 `migrate_warnings` 列出，不再静默漏报。

### 测试

```bash
python3 -m unittest discover -s tests/scripts -p 'test_*.py'
```

350 个测试，全部通过。

### 项目结构

```
skills-task-list-initialization/
├── VERSION                                   # V0.3.9
├── skills/task-list-initialization/
│   ├── SKILL.md                              # 技能定义
│   ├── evals/
│   │   ├── evals.json                        # 任务执行评测用例（fixtures 已挂接）
│   │   ├── trigger-evals.json                # 触发/行为评测矩阵（14 例）
│   │   ├── run-evals.py                      # 无头真实 agent 评测运行器
│   │   ├── aggregate-benchmark.py            # 运行遥测汇总（benchmark.json）
│   │   └── fixtures/                         # 评测前置夹具
│   ├── references/
│   │   ├── task-list-standard.md             # 推荐字段 / schema 标准
│   │   ├── cli-reference.md                  # CLI 完整命令、旗标与回滚/口径语义
│   │   ├── task-list-template.md             # 标准模板
│   │   └── maintenance-rule.md               # 会话末同步规则 + Stop hook 模板
│   └── scripts/
│       ├── task_list_cli.py                  # CLI 入口（再导出）
│       └── _tasklist/                        # 实现包（cli/parser/validator/locales/…）
├── tests/
│   └── scripts/                               # 测试套件（全部 test_*.py 与公共助手）
│       ├── helpers.py                         # 测试公共助手
│       └── test_*.py                          # 单元测试（350）
├── LICENSE                                   # MIT
└── README.md
```

### 许可证

[MIT](LICENSE) © 2026 fenix-wangminle。

### 更新日志

#### V0.3.9

- BUG-111：摘要只剩表头和分隔行时仍执行缺失分类检查；已有记录的台账删除全部摘要数据行后，`check` 返回 1 并指出缺少的分类。没有可选摘要章节的台账保持通过。新增 4 项 CLI 回归覆盖中英完整模板、合法统计口径、无摘要对照和 `summary --write` 恢复——**350** 个单元测试。
- DEV-030：新增 `fleet` 批量巡检子命令——指定根目录即递归发现其下所有 `task-list.md`，逐文件完整诊断（`check` + `standardize` 诊断 + 维护规则状态，各按文件自身语言），输出逐文件表格与汇总报告；`--exclude` glob 排除备份/评测/运行时副本（默认已排除 `.git`/`node_modules`/`.stversions`），`--apply-safe-fixes` 持写锁就地修复并复检，`--format json` / `--report` 供自动化消费；退出码（0 全过或空树 / 1 有文件失败、单文件诊断出错或扫描不完整 / 2 根目录不存在或报告写不进去）适配 cron 与 CI 健康门禁——替代手工拼接的多项目巡检脚本
- DEV-031：写路径跨进程锁——所有写命令（`add`/`update`/`archive`/`summary --write`/`standardize` 修复/`init`/`fleet --apply-safe-fixes`）持 `task-list.md.lock` sidecar 排他 advisory 锁（POSIX `flock`、Windows `msvcrt`；10 秒超时输出本地化 `lock_timeout`，进程死亡自动释放，dry-run 与只读命令不持锁），消除两个会话并发写时读-改-写竞态产生的重复 ID
- DEV-033：自定义分区表格约束——标准分区之外的表格若首列是严格任务 ID（`^[A-Z]+-\d{3,}$`）但无标准记录表头，`check` 直接报错；agent 不能再即兴发明以 P2/P3 当状态列的记录表（源自评审日志小节的实战事故）
- DEV-032：时间倒挂比较改为精度感知——双方带时间按分钟比；任一侧仅日期（单→双日期迁移遗留）只比日历日，同日不再永久告警，剩余的倒挂警告都是真问题（BUG-094 修复后显式 date-only 写入按日精度原样落盘，工具自身不再制造假倒挂）
- BUG-094：显式 date-only 的 `--found-time` / `--completed-time` / `--date` 原样落盘（`YYYY-MM-DD`，不再补 `00:00`）——此前补齐的 `00:00` 会制造永久的同日"倒挂"，check 一直报警，还会经由写后回滚阻断后续仅追加备注的 update
- BUG-095/BUG-096：`fleet --apply-safe-fixes` 逐文件隔离失败（锁超时或 I/O 错误 → 该文件记 status=error，巡检继续，退出码仍非零），不再以 traceback 中止整轮并丢弃已扫结果；移除 Python 3.9+ 的 `Path.is_relative_to` 调用，恢复 3.8+ 兼容承诺（含 AST 级回归守卫）
- BUG-097/BUG-100：自定义分区门禁改为校验「受支持的记录 schema」（任一注册分区的双日期/单日期表头形状）而非「有表头即可」——形如 `| ID | 问题 | 结论 |` 的伪表头不能再让 ID 行绕过逐行校验混入按前缀摘要；走私行仍全局登记身份与 `[[引用]]`，跨表重复 ID 会被报出、仅存在于走私表的 ID 引用不算悬空、两位数字 ID 形态也会被标记
- BUG-098/BUG-099/BUG-101：fleet 输出与锁加固——空树 `--format json` 仍输出可解析 JSON；`--report` 报告列入用户 `--exclude` 且转义路径中的 `|`；不可读目录显式报 `scan_errors` 并以退出码 1 失败，不再伪装全通过；`--report` 路径不可写时以本地化消息退出码 2；对不存在的目标加锁不再创建父目录或残留 sidecar；锁创建失败输出指名台账路径的本地化消息；锁超时文案显示台账路径而非内部 `.lock` 路径；本仓忽略 `task-list.md.lock`（消费端建议同样忽略 `*.md.lock`）
- 测试：新增 12 个回归覆盖 BUG-094～101 整批（日精度落盘 + 写后 check + 后续 update、逐文件锁隔离、缺失目标副作用、只读目录锁错误、伪表头走私、走私身份/引用语义、空树 JSON、报告 exclude/不可写路径/竖线转义、不可读目录披露、3.9+ API AST 守卫），另含 msvcrt 分支 mock 与 fleet 英文 locale 矩阵——**324** 个单元测试
- BUG-102/BUG-103/BUG-104：fleet 边界补齐——单个项目的维护文件（`CLAUDE.md` 及同类旁路文件）编码异常记为 status=error 并继续巡检，JSON 仍保留其他项目结果；空目录在默认文本模式下也会写入并覆盖 `--report`；报告路径改走 `escape_cell`，目录名同时含反斜杠与竖线时不再拆列——**327** 个单元测试
- BUG-105：`atomic_write` 改为逐字写出 `\n`，不再按平台翻译行尾——Windows 端安装曾把 CRLF 写进 bash hook 脚本（`fi\r` 不是 `fi`，Stop hook 解析即失败），且安装器幂等比较走 `read_text()`（通用换行读取把 CRLF 归一化成 LF），损坏的脚本被误判为「与模板一致」而永不修复。写入现为字节忠实的 LF（与 BUG-090 回滚孪生一致），比较改为原始字节，重跑 `install-maintenance --with-hook` 即自愈并明确提示「已重写」——**329** 个单元测试
- BUG-106：`fleet --report` 与 `standardize --report` 在报告路径与任一输入台账解析为同一文件时直接拒绝（exit 2、不写任何内容、台账字节不变）——比较前先经 `resolve()` 归并相对路径/`..`/符号链接别名；`fleet` 的检查先于巡检执行，因此报告冲突同样抑制 `--apply-safe-fixes` 的修复，而不是去修复一个即将被报告覆盖的文件
- BUG-107：`archive` 从首读归档到提交全程持有归档文件自身的第二把锁（锁序恒为主表→归档；唯一使用嵌套锁的命令）——过去两个不同主台账并发归档到同一共享归档时，双方都在任一方写入前完成读取，后提交者会静默丢弃对方的记录；查重现移入临界区基于新数据执行，互斥交叉归档退化为干净的 `lock_timeout`，绝不丢数据——由屏障同步的双进程回归钉死，并已在未修复代码上验证失败
- BUG-108：`check` 对记录表头下 GFM 分隔行缺失或列数与表头不符直接判失败（CommonMark 要求分隔行紧邻表头且等宽，否则整表在预览中渲染为纯文本）——两种情况均报行号，围栏内示例表永不计入；`add` 拒绝向坏分区追加（点名行号），同文件其他分区仍可写，缺陷以存量形式披露
- BUG-109：摘要表对分类标题中的 `|` 转义（`研究 \| 调试`），合法的自定义标题（如 `## 研究 | 调试`）不再在 5 列摘要表里产生 6 列行与错位数字；`check` 现在标记历史宽行损坏的摘要行与缺失分类行（先形态后数字；口径不明/过期时保守处理）
- BUG-110：列数异常行仍登记其严格 ID——藏在超宽行里的重复 ID 会被报出，指向仅存在于超宽行的 ID 的 `[[引用]]` 不再误报悬空——同时此类行仍排除在完成率统计之外
- 测试：`tests/scripts/test_cli_bugfix_106_110.py` 新增 17 项回归（报告覆盖拒绝 + 点号别名 + 修复中止 + 独立路径对照、standardize 报告冲突、`commit_all` 汇合屏障的双进程并发归档、分隔行缺失/列宽/空行/围栏豁免/add 拒绝/健康分区可写、管道标题写入 + 幂等 + 历史宽行 + 缺分类、超宽行重复 + 不误报悬空）——**346** 个单元测试

#### V0.3.8

- BUG-089：Stop hook 模板先探测 `python3 -c 'import sys'`，失败自动回退 `python`——Windows 上微软商店 `python3` 桩（exit 非零、无输出）会让 hook 静默失效，且每会话守卫退化为全局共享的 `default`；`install-maintenance --with-hook` 重新部署修复后的脚本，并把旧相对路径命令升级为 `${CLAUDE_PROJECT_DIR}`（幂等）
- BUG-090：回滚改为字节级保真——`_restore` 走二进制原子写，不再解码后经文本模式重写；此前在 Windows 上会二次换行转换，CRLF 文件每次 `commit_all` 回滚都被掺入多余 `\r`（`\r\n` → `\r\r\n`）
- BUG-092：`tests/scripts/test_evals_meta.py` 缺 `from __future__ import annotations`，`Path | None` 注解在 Python 3.9 导入期即抛 `TypeError` 并拖垮整个测试发现，与「3.8+ 全量通过」声明冲突——现已在 3.9 / 3.13 / 3.14 三环境全量通过（全仓审计确认无其他缺延期注解的模块、无运行期求值别名、无 3.9+ 专属 API）
- BUG-093：`install-maintenance --with-hook` 前置探测 `shutil.which("bash")`，无 bash 的机器上整体拒绝（退出码 1、不写任何文件、`--dry-run` 同样拒绝），不再「装得上、每次触发必失败」（纯 Windows 默认无 bash）；安装路径测试以 PATH shim 双向固定、无 bash 主机保持全绿；README / cli-reference / SKILL.md 同步声明 bash 要求
- 测试：hook 执行类用例在 Windows 上定位真实 bash（跳过 System32 的 WSL 启动器桩）；BUG-068 权限断言适配 Windows（只读位而非 mode 位）；新增双语模板解释器回退回归断言、跨平台 CRLF 回滚字节级回归与 bash 探测拒绝/安装对——**290** 个单元测试

#### V0.3.7

- BUG-082：写入回滚改为基线感知--`add`/`update` 把写后问题与写前基线对比：新引入的问题回滚，存量问题保留写入并在 stderr 披露（不再被历史债务卡死）
- BUG-083：预览安全检查的裸 HTML 匹配精确到单元格（行内合法提及 `<title>` 不再误中别处的 `<details>`）
- BUG-084：回滚指纹不再折叠 ID 数字，`[[BUG-002]]` 与 `[[BUG-003]]` 可区分
- BUG-085：`check` 行级警告透出存量时间倒挂（完成早于发现）--警告级、退出码不变，新增倒挂写入门禁本就拒绝
- BUG-086：`check` 警告"已完成状态但完成时间仍为 `-`"的行
- REQ-09：真实 agent 评测设施（`evals/run-evals.py`、`evals/aggregate-benchmark.py`），含工具延迟隔离（headless 运行的工作区级 `ENABLE_TOOL_SEARCH` 覆盖）；产出首份 `evals/benchmark.json`--6 配置 × 3 轮、任务成功率 100%--由 `test_evals_meta.py` 守卫
- 文档：完整 CLI 参考移至 `references/cli-reference.md`，含存量时间倒挂的 git 佐证修正配方
- `ruff check` 清零；**286** 个单元测试

#### V0.3.6

- REQ-12：`-` 仅是时间/可选列的缺失占位符，**不是状态**；`add`/`update` 拒绝 `--status -` 并列出可选枚举，`check` 按行号报出已有 `状态=-` 的行
- REQ-09/10 评测可信：新增 `evals/trigger-evals.json`（按计划矩阵 14 例触发/行为评测）与两个 fixture；`test_evals_meta.py` 增加 benchmark 机械守卫（占位符 / tokens·tool_calls 全零 / 声明运行数与实际不符，`evals/benchmark.json` 产出即失败约束）；评测 workspace 加入 `.gitignore`
- REQ-13/14/15 验收加固：`install-maintenance`（hook 脚本写失败回滚 agent 文件）与 `archive`（归档写失败主表字节不变）CLI 级故障注入；5 个读命令缺失文件固定退出码 1；21/22 渲染 `95.5%`、全部完成渲染 `100%`
- 补齐 BUG-075/076 回归测试（未知前缀不算错位；未注册自定义分区计入写入摘要）
- `ruff check` 清零；**270** 个单元测试

#### V0.3.5

- `summary --policy auto|by-section|by-prefix`（默认 `auto`）：存在错放记录（ID 前缀与物理分区不一致）时两种口径分叉，`auto` **拒绝写入**（非零退出、文件不变）并打印双口径对比与既有摘要匹配的口径；`add` / `update` 摘要自动同步遇口径冲突跳过并告警，不再静默改桶
- `check` 输出前缀错位警告（行号、ID、所在分区、期望前缀）；警告不导致校验失败，也绝不自动移动记录
- 统计排除列宽异常行（单元格数与表头列数不符，多为未转义 `|`）：单元格碎片不再混入状态分布、总数不再计入断行；只读 `summary` 视图提示排除行数
- `ruff check` 清零；**232** 个单元测试

#### V0.3.4

- 将原 `_lib.py` 巨石拆为分层模块：`domain` / `parser` / `renderer` / `schemas` / `summary` / `validator` / `migration` / `maintenance` / `cli`；删除 `_lib.py`
- CLI 入口经 `_tasklist/public_api.py` 显式导出正式兼容清单（含 `detect_locale`；不含 stdlib 星号泄漏）；`_locale.py` 仅为 `locales.py` 的兼容再导出
- 写入/摘要/迁移/safe-fix/重复章节检测的标题扫描全部跳过围栏代码，示例表格不能再劫持真实表
- 混合 dual+single 文件在 `--schema auto` 下通过；`add` 不再对合法混合台账自我回滚
- `--from-json` 拒绝非字符串字段；`escape_cell` 剥离 CR 并转义反斜杠；非法分隔行与非零填充日期会使 `check` 失败
- 归档合并不允许跨 schema 列数错乱；识别无花括号 `$CLAUDE_PROJECT_DIR`；`atomic_write` 保留原文件权限
- 维护规则正文与 `references/maintenance-rule.md` 单一来源；CLI 测试拆为 `test_cli_*.py` 与模块测试
- `ruff check` 清零；**209** 个单元测试

#### V0.3.3

- `check` 成为 Markdown 预览门禁：表内空行（跳过围栏代码）、裸的流式 HTML（`<title>`、`<iframe>`、`<xmp>` 等）、未按 CommonMark 闭合的反引号均失败并给出行号
- `--apply-safe-fixes` 删除数据行之间的空行（章节空行与围栏内示例保留）
- `escape_cell` 写盘时把黑名单裸 HTML 包进行内代码，且不改写已闭合的双反引号 span；`<id>`、`a < b` 不误伤
- `standardize` 按工具校验 hook 声明、告警规则双写/非便携路径/`.claude/` 被 gitignore、以及章节顺序偏离；「开源项目调研」建议含整段后移
- `SKILL.md` / `task-list-standard.md` 补预览安全字段规则；evals 7–8 覆盖预览损坏夹具；**168** 个单元测试

#### V0.3.2

- 摘要漂移校验扩展为四字段比较（总数 / 已完成 / 待开发/待修复 / 内部一致性），并按文件实际口径（by-prefix / by-section）核算
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
