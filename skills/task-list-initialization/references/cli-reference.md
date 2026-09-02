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
CommonMark code spans on a data row, and GFM-invalid table separators. Heading
scans for `add` / `summary --write` / `--migrate-schema` / `--apply-safe-fixes` /
duplicate-section detection skip fenced code blocks so Markdown table *examples*
cannot hijack real tables. `check` additionally prints **prefix-misplacement
warnings** — a record whose ID prefix does not match its physical section (e.g.
`DEV-074` under 检查事项, which expects `CHK-`) — as warnings: exit code stays 0,
records are never auto-moved; reclassify manually after confirmation. `check`
also prints **time-order warnings** for existing records whose completed time is
earlier than found time - line-level with the record ID, warning-class (exit
code unchanged) because the write path already refuses new inversions; fix
legacy rows with git-commit evidence.

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

- `add` / `update` run a structural `check` after writing by default. Issues
  **introduced by the write** roll it back and exit non-zero; pre-existing file
  issues (broken legacy rows elsewhere) no longer block the write — it is kept and
  the residual count is disclosed on stderr, so a broken row cannot deadlock
  repairs of other rows. Pass `--no-check` to skip validation entirely.
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
  that would fail on every Stop event.
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
view reports the excluded-row count. `--write --dry-run` previews the rewritten
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
archived IDs are never reused.

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
