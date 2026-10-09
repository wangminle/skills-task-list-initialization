# CLI Reference — task_list_cli.py

Companion to `SKILL.md` (routed from its CLI section). `$SKILL_CLI` is
`$SKILL_DIR/scripts/task_list_cli.py`, where `$SKILL_DIR` is this skill's install
root — typically `~/.claude/skills/task-list-initialization` (Claude Code) or the
skill folder inside a project's `skills/` tree. On Windows, replace `python3` with
`python`. Implementation lives under `scripts/_tasklist/` (`cli.py` commands,
`parser.py` / `validator.py` / `locales.py`, `public_api.py`, …); the entry script
re-exports the formal public API compat list (including `detect_locale`).

## Command examples

```bash
SKILL_CLI="$SKILL_DIR/scripts/task_list_cli.py"   # or absolute path to task_list_cli.py

python3 "$SKILL_CLI" init --output task-list.md
python3 "$SKILL_CLI" init --lang en --profile extended --with-summary --output task-list.md
python3 "$SKILL_CLI" sections --file task-list.md --format json
python3 "$SKILL_CLI" add --file task-list.md --section "代码 Bug" --action 修复 --description "登录失败" --status 待修复 --notes "复现于本地"
python3 "$SKILL_CLI" add --file task-list.md --section "代码 Bug" --action 修复 --description "含特殊字符" --status 待修复 --notes-file /tmp/notes.txt
python3 "$SKILL_CLI" add --file task-list.md --from-json /tmp/entries.json
python3 "$SKILL_CLI" update --file task-list.md --id BUG-001 --status 已修复 --completed-time "2026-08-04 16:00" --notes-append "测试通过"
python3 "$SKILL_CLI" list --file task-list.md --status 待修复 --keyword sqlite
python3 "$SKILL_CLI" install-maintenance --file task-list.md
python3 "$SKILL_CLI" install-maintenance --file task-list.md --with-hook
python3 "$SKILL_CLI" check --file task-list.md
python3 "$SKILL_CLI" summary --file task-list.md
python3 "$SKILL_CLI" summary --file task-list.md --write
python3 "$SKILL_CLI" standardize --file task-list.md --report docs/task-list-standardize-report.md
python3 "$SKILL_CLI" standardize --file task-list.md --migrate-schema --apply-safe-fixes
python3 "$SKILL_CLI" archive --file task-list.md --older-than-days 90
python3 "$SKILL_CLI" fleet --root ~/projects --exclude '*/evals/*' --report docs/fleet-report.md
python3 "$SKILL_CLI" fleet --root ~/projects --apply-safe-fixes --format json
```

Run `--help` on any subcommand for the full option list. Prefer CLI generation for
new files, then review the result manually for project-specific wording.

## Language, schema, and detection behavior

`init --lang {zh,en}` selects the template language (`zh` = Simplified Chinese,
default). The other subcommands auto-detect the language from the target file.
`check`/`standardize` accept `--schema {auto,dual,single}` (default `auto`) to
validate a file that keeps the legacy single-date schema. `add` auto-matches the
target section's schema and emits the corresponding column count, so no flag is
needed. A file that mixes dual-date and single-date sections is valid in
`--schema auto` (each section is checked against its own header).

`check` also flags malformed IDs (e.g. `bug-001`, `BUG-12`) in the first column
rather than silently skipping them, validates timestamps, reports dangling
`[[ID]]` refs, suggests nearest standard statuses for non-standard values, and
**fails on preview-breaking markup**: blank lines between table rows (fenced code
examples are ignored), per-cell-matched raw flow-breaking HTML tags, unclosed
CommonMark code spans on a data row, and GFM-invalid table separators — including
a record-table header whose delimiter row is missing entirely or whose column
count differs from the header (CommonMark requires the delimiter IMMEDIATELY
after the header with the same width; otherwise the whole table renders as plain
text). Line numbers are reported for both cases. Heading
scans for `add` / `summary --write` / `--migrate-schema` / `--apply-safe-fixes` /
duplicate-section detection skip fenced code blocks so Markdown table *examples*
cannot hijack real tables. `check` additionally prints **prefix-misplacement
warnings** — a record whose ID prefix does not match its physical section (e.g.
`DEV-074` under 检查事项, which expects `CHK-`) — as warnings: exit code stays 0,
records are never auto-moved; reclassify manually after confirmation. `check`
also prints **time-order warnings** for existing records whose completed time is
earlier than found time - line-level with the record ID, warning-class (exit
code unchanged) because the write path already refuses new inversions; fix
legacy rows with git-commit evidence. The comparison is **precision-aware**:
both sides carry a time (`YYYY-MM-DD HH:MM`) → minute-level compare; either
side date-only (`YYYY-MM-DD`, typical after a single→dual-date migration) →
calendar-day compare only, so a same-day pair never warns and only a strictly
earlier day counts as inverted.

`check` also enforces **custom-section table shape**: sections outside the
standard model are free-form, but a Markdown table whose first column holds
strict task IDs (`^[A-Z]+-\d{3,}$`) without a recognized record header (the
standard 7/6/8/9-column layouts) is an **error**, not a warning — agents must
not invent ad-hoc record tables (e.g. using a priority column as 状态). Give
the section a standard header or keep its tables ID-free.

## Correcting legacy time inversions with git evidence

When `check` reports 时间倒挂提醒 (completed earlier than found), recover the real
timestamps from git instead of guessing. Field-tested on 9 projects (58 inversions
corrected); every step uses stock git:

1. **Locate commits in the window** -
   `git log --all --format="%h %ad %s" --date=format:"%Y-%m-%d %H:%M" --since=… --until=…`
   around the claimed dates. Use `--all`: the fix may sit on a side branch or a
   merge that landed later.
2. **Match the fix to a commit** (three probes, weakest to strongest):
   - `git show <commit> --name-only` - do the files named in the record's
     description (or notes) appear in the diff?
   - `git show <commit> | grep <keyword>` - a function/constant/message named in
     the fix, e.g. `enforce_channel_`.
   - `git log --all -S "<keyword>"` (pickaxe) - when you only know a code token
     such as `VITE_BASE` and don't know which commit carries it.
3. **Prove the row's own entry time** - `git log -S "<ID>" -- task-list.md` shows
   when the ledger row first landed. A claimed *found* time later than that commit
   proves a backfill typo: the row cannot have been discovered after it was
   committed. This is the only reliable way to pick which of the two timestamps
   is wrong.
4. **Correct via the CLI, never by hand** - `update --id … --found-time … /
   --completed-time … --notes-append "<evidence>"`. The commit timestamp is the
   defensible completion time; when the row predates its own claimed found time,
   align the found time to the working session (the row's commit gives the upper
   bound). Always append the evidence chain (commit hash + date + what matched)
   into `备注` so the correction stays auditable.
5. **Re-run `check`** and confirm the 时间倒挂 list is empty - warnings never
   change the exit code, so an empty warning list, not `rc=0`, is the success
   signal.

`add` refuses to write into a section whose header does not match a recognized
schema (e.g. a reordered `ID / 状态 / 动作 / …`) instead of guessing the column
layout — fix the header manually. `--migrate-schema` only upgrades supported
6/8-col single-date legacy schemas; it will refuse a reordered dual-date header
rather than shift field meanings. `add`/`update` wrap blacklisted raw HTML tags
(such as `<title>`) as inline code on write; `--from-json` requires string fields
(lists/dicts are rejected).

## Write-path ergonomics

- **Cross-process write lock.** Every write command (`add`, `update`,
  `archive`, `summary --write`, `standardize` repair modes, `init`, and
  `fleet --apply-safe-fixes`) takes an exclusive advisory lock on a
  `<task-list>.lock` sidecar before reading the file and holds it through the
  write (POSIX `flock`, Windows `msvcrt.locking`). A second process that
  arrives while the lock is held waits up to 10 seconds, then exits 1 with a
  localized `lock_timeout` message instead of interleaving a
  read-modify-write into duplicate IDs. The lock is released automatically if
  the process dies; the empty sidecar file is left behind and is safe to
  gitignore (e.g. `task-list.md.lock`). Dry-run and read-only commands never
  lock. Hand-editing the file bypasses the lock — re-run `check` afterwards.
  `archive` holds a **second** lock, on the archive file itself, from its first
  read of the archive through its commit: different main ledgers archiving
  concurrently into one shared archive serialize there, so one side's records
  can never be silently dropped by the other's stale read (the lock order is
  always main → archive; mutual cross-archiving degrades to a clean
  `lock_timeout`, never data loss).
- **Report paths never overwrite their inputs.** `fleet --report` and
  `standardize --report` refuse (exit 2, nothing written, ledger bytes
  untouched) when the report path resolves to the same file as an input ledger
  — relative paths, `..` aliases, and symlinks are collapsed via `resolve()`
  first. For `fleet` the check runs before the sweep, so the refusal also
  protects the file from `--apply-safe-fixes` repairs; for `standardize` it
  runs before any repair or report write.
- `add` / `update` run a structural `check` after writing by default. Issues
  **introduced by the write** roll it back and exit non-zero; pre-existing file
  issues (broken legacy rows elsewhere) no longer block the write — it is kept and
  the residual count is disclosed on stderr, so a broken row cannot deadlock
  repairs of other rows. Pass `--no-check` to skip validation entirely. One
  pre-existing defect `add` does refuse outright: appending into a section whose
  record table has no valid GFM delimiter row under its header (missing or
  wrong-width — the whole table already renders as plain text). The refusal
  names the line; other sections in the same file stay writable.
- When the file already has a `统计摘要` / `Summary` section, `add` / `update`
  recompute it by default (`--no-sync-summary` to skip). If the by-prefix and
  by-section calibers disagree (misplaced rows), the recompute is **skipped with a
  warning** instead of silently re-bucketing the summary; run
  `summary --policy by-prefix|by-section` to recompute explicitly. `check` reports
  stale summary totals (摘要表过期).
- Prefer `--notes-file` / `--description-file` (or `-` for stdin) for long Chinese
  text with quotes, semicolons, or pipes — avoids shell escaping. `--from-json`
  accepts a JSON array/object (or stdin via `-`) for batch adds and the same
  escaping safety.
- `update --id …` patches fields in place (`--status`, `--notes` /
  `--notes-append`, `--completed-time`, …). It does **not** renumber IDs — use an
  `ADJ-` mapping record for ID corrections.
- `sections` lists headings; `list` filters by `--id` / `--status` / `--section` /
  `--keyword`. Section aliases include ID prefixes (`CHK`, `ADJ`, …) and short
  Chinese names (`检查`, `调整`, …).
- `install-maintenance` installs the session-end sync rule into
  `CLAUDE.md`/`AGENTS.md` (idempotent); `--with-hook` also installs the Stop hook
  and requires a real `bash` on `PATH` (plain Windows ships none: install Git Bash
  or WSL first). The installer probes `shutil.which("bash")` up front and refuses —
  exit 1, nothing written, `--dry-run` included — rather than installing a hook
  that would fail on every Stop event. Re-running `--with-hook` is self-healing:
  it upgrades legacy relative-path commands and rewrites a hook script whose bytes
  no longer match the template (e.g. CRLF line endings from a Windows-side write,
  which bash cannot parse). All CLI file writes emit LF verbatim, so hook scripts
  stay parseable and files stay diff-stable across OSes.
- `add --dry-run` prints only the row(s) that would be appended, not the whole file.
- Invalid `--action` / `--status` errors list the allowed enum values.

## summary --write and counting calibers

`summary --write` recomputes the `统计摘要` table from current records (total /
completed / pending / completion rate) and writes it back, appending the section
if it does not exist yet. `--policy auto|by-section|by-prefix` (default `auto`)
picks the counting caliber: when a record's ID prefix doesn't match its physical
section, the by-prefix and by-section counts disagree, and `auto` then **refuses
to write** (non-zero exit, file unchanged) while printing both counts plus which
one the file's existing summary matches. Choose `--policy by-prefix` to keep
prefix-caliber summaries (typical for historical ledgers) or `--policy
by-section` to switch to physical sections. Under `by-prefix`, a custom section
whose records all fold into standard prefixes is omitted once nothing remains in
it (an all-zero row is noise), while custom sections that still hold records —
including unknown-prefix IDs — stay visible. Width-anomalous rows (cell count
differs from the section header, usually an unescaped `|`) are excluded from
statistics so cell fragments cannot surface as statuses; the read-only `summary`
view reports the excluded-row count — but their IDs still count for duplicate
detection and `[[ID]]` reference resolution, so a duplicate hidden in an overwide
row is reported and a reference to it is not falsely dangling. Category titles
containing `|` (legal in a `##` heading like `研究 | 调试`) are written escaped as
`\|`, keeping the summary table a valid 5-column GFM table; `check` flags legacy
summary rows with the wrong cell count and categories missing from the written
table (shape first, numbers second). An existing summary containing only its
header and delimiter still runs the missing-category check; a ledger with records
cannot pass by deleting all summary data rows. Ledgers without a summary section
remain valid. `--write --dry-run` previews the rewritten
table without touching the file; `--dry-run` on its own stays a read-only stats
view.

## Archiving long-lived lists

For large ledgers, archive completed records on demand (never automatic):

```bash
python3 "$SKILL_CLI" archive --file task-list.md --older-than-days 90
```

Moves completed rows whose Done time is on/before `as-of − N days` into
`task-list-archive-YYYYMM.md` (or `--output`). Active and recent completed rows
stay in the main table. Subsequent `add` scans sibling `*archive*.md` files so
archived IDs are never reused. The archive file is locked for the whole
read-merge-commit sequence, so different main ledgers archiving into the same
shared archive take turns instead of dropping one side's records; duplicate IDs
already present (or repeated within the batch) abort the move with an
`archive_dupe` error and no writes.

## Fleet batch inspection

`fleet` audits every `task-list.md` under a directory tree in one run — the
institutionalized form of a hand-rolled check loop:

```bash
python3 "$SKILL_CLI" fleet --root ~/projects
python3 "$SKILL_CLI" fleet --root ~/projects --exclude 'evals/workspace/runs' --exclude '*/runtime'
python3 "$SKILL_CLI" fleet --root ~/projects --apply-safe-fixes --report docs/fleet-report.md
```

- **Discovery**: recursive walk from `--root`; the default excludes are
  `.git`, `.hg`, `.svn`, `node_modules`, `.stversions`. `--exclude <glob>`
  (repeatable) is matched with `fnmatch` against the root-relative path (and
  the path plus `/*`) and against the bare directory name; `*` crosses path
  separators. A leading-anchored pattern like `evals/workspace/runs` excludes
  only that exact root-relative subtree — use `*/evals/workspace/runs` to
  exclude it wherever it nests, or a bare name like `examples` to exclude
  every directory so named. Frozen historical ledgers, example templates,
  and deployed runtime copies are typical exclusions (inspect them once,
  don't repair).
- **Per-file diagnosis**: the same pipeline as `check` (structure, preview
  safety, duplicate IDs, precision-aware time inversions, custom-section ID
  tables, dangling refs) plus `standardize` diagnostics and the
  maintenance-rule status, each in the file's own detected language.
- **`--apply-safe-fixes`**: applies the same safe fixes as `standardize`
  (missing empty standard sections, intra-table blank lines, unescaped `|`)
  under the per-file write lock, then re-checks; results report fixed counts.
  Semantic issues (duplicate IDs, misplaced prefixes, summary conflicts) are
  reported, never auto-repaired.
- **Output**: text table by default; `--format json` for machine consumption;
  `--report <path>` also writes a Markdown report. `--lang zh|en` sets the
  language of the fleet output itself (per-file diagnostics follow each
  file's language).
- **Exit codes**: `0` all files pass, or none were found; `1` at least one
  file fails, one file's diagnosis hits an I/O or decode error (that file is
  `status=error` and the other results are kept), or the directory walk was
  incomplete (`scan_errors`); `2` the root directory does not exist,
  `--report` cannot be written, or `--report` resolves to one of the scanned
  ledgers (refused before the sweep — including `--apply-safe-fixes` runs — so
  diagnostics can never overwrite the records they describe).
  `--report` is written for an empty tree too,
  in both text and JSON modes, and replaces any previous report at that path.
  Suitable for cron/CI health gates.

## Migration details

The single source of truth for the migration matrix (`发现日期` → Found only,
`完成日期` → Done only, day precision kept, never copied across semantics;
`开始日期` / `规划日期` unmappable) is `references/task-list-standard.md` — see
the「修复必须显式开启」table there. CLI-side behaviors worth knowing: data rows
whose cell count doesn't match the header (usually an unescaped `|` in a cell)
are left untouched and reported as `migrate_warnings` (in `--fix-only` and
`--format json` output) instead of being silently skipped — prefer
`--apply-safe-fixes` first when the issue is only unescaped pipes. After
`--fix-only` writes, any residual issues that still fail `check` (e.g. legacy
`状态=-` rows kept verbatim) are disclosed on stderr with a pointer to run
`check` for line-level details.
