# 维护规则安装模板（maintenance-rule）· Maintenance Rule Install Template

当用户希望「未来的 agent 自动维护 task-list」时，按本模板把维护规则写入项目的 agent 配置文件。这是 skill 工作流（第 5 步）的子任务，目标：让任何后续会话都能可靠地把任务完成情况同步进 `task-list.md`。

When the user wants future agents to maintain the task-list automatically, install the maintenance rule into the project's agent config file using this template. It is a sub-task of the skill workflow (step 5): every later session reliably syncs task completions into `task-list.md`.

本模板分两层：**策略**（写进 CLAUDE.md/AGENTS.md，告诉 agent 做什么）+ **可选保证层**（Stop hook，确保每次会话末都触发）。Two layers: **policy** (written into CLAUDE.md/AGENTS.md, telling the agent what to do) + **optional guarantee** (a Stop hook that fires every session end).

## 语言选择 · Language selection

规则与 hook 的语言应与项目 `task-list.md` 的语言一致：中文 task-list 配中文规则，英文 task-list 配英文规则。`init --lang` 决定 task-list 语言，安装规则时取同一语言。Match the rule/hook language to the project's `task-list.md`: a Chinese task-list gets the Chinese rule, an English task-list gets the English rule. `init --lang` decides the task-list language; install the rule in the same language.

- 用户用**中文**交互 → 中文 task-list（`--lang zh`，默认）+ 中文规则。
- 用户用**其他语言**交互 → 先告知用户「将输出英文版 task-list」，再建英文 task-list（`--lang en`）+ 英文规则。
- **检测不到**语言 → 默认中文。

## 1. 写入哪个文件 · Which file

按优先级选择**一个**文件（已存在则用，都不存在则新建第一个）。Pick **one** file by priority (use if it exists; if neither exists, create the first):

1. `CLAUDE.md` —— Claude Code 项目首选，会话开始自动加载。Claude Code default, auto-loaded at session start.
2. `AGENTS.md` —— 跨工具通用约定。Cross-tool convention.
3. 两者都没有 → 新建 `CLAUDE.md`。Neither exists → create `CLAUDE.md`.

注意 · Notes:

- 不要同时往两个文件写重复内容；若两者都已存在，优先追加到 `CLAUDE.md`。Do not duplicate into both; if both exist, prefer `CLAUDE.md`.
- 追加到文件末尾，**保留原有约定**，不破坏现有内容。Append at the end; keep existing content intact.
- **幂等**：若目标文件已含规则标记标题（中文「会话结束任务同步」/ 英文 `Session-end Task Sync`），不要重复追加。Idempotent: if the file already contains the rule's marker heading, do not append again.

## 2. 规则正文 · Rule text

把下面**对应语言**的段落追加到所选文件（可按项目语境微调）。Append the block matching the task-list's language to the chosen file (tweak for project context if needed).

### 中文 · Chinese

```markdown
## 会话结束任务同步（必须）

每次会话结束前，若本次涉及任务完成——包括但不限于 bug 修复、功能开发、代码审查、测试数据准备、文档更新、配置运维——必须：

1. 把新增条目与状态变更写入根目录 `task-list.md`，与实际进度同步；
2. 在本次最后一条回复中告知用户：记录/更新了哪些条目（ID + 简述）。

若本次未涉及任何任务完成，无需操作也无需提示。该时机由 `.claude/settings.json` 的 `Stop` hook 保证触发（每会话一次）。
```

### English

```markdown
## Session-end Task Sync (Required)

Before each session ends, if this session involved completing work — including but not limited to bug fixes, feature development, code review, test-data preparation, documentation updates, or operations — you must:

1. Sync new entries and status changes into the root `task-list.md`, keeping it in step with actual progress;
2. Tell the user in your final reply which entries you recorded/updated (ID + short note).

If this session completed no work, do nothing and say nothing. The timing is guaranteed by the `Stop` hook in `.claude/settings.json` (once per session).
```

## 3.（可选）保证层：Stop hook · Optional guarantee

规则只是「策略」，靠 agent 自觉；要做到「每次会话末必触发」，追加一个 `Stop` hook。是否安装由用户决定（默认不装）。The rule is only a "policy" relying on the agent; to force a trigger every session end, add a `Stop` hook. Installation is opt-in (off by default).

在项目 `.claude/settings.json` 注册（语言无关）· Register in `.claude/settings.json` (language-neutral):

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          { "type": "command", "command": "bash .claude/hooks/tasklist_sync_reminder.sh" }
        ]
      }
    ]
  }
}
```

脚本 `.claude/hooks/tasklist_sync_reminder.sh`（每会话首次停止注入 `block` 提醒，用 `session_id` 守卫防死循环；`reason` 文案按 task-list 语言二选一）· The script injects a one-shot `block` reminder per session, guarded by `session_id` to avoid loops; pick the `reason` text matching the task-list language:

```bash
#!/usr/bin/env bash
input="$(cat)"
session_id="$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_id") or "default")' 2>/dev/null || echo default)"
guard="/tmp/claude-tasklist-sync-${session_id}"
[ -f "$guard" ] && exit 0
touch "$guard"
# 中文项目用这一行（English projects: replace reason with the English version below）:
python3 -c 'import json; print(json.dumps({"decision":"block","reason":"会话结束前请按 CLAUDE.md 的「会话结束任务同步」规则：若本次涉及任务完成，把新增条目与状态变更写入根目录 task-list.md 并在回复中告知用户；否则简短说明无需同步。本提醒每会话仅触发一次。"}, ensure_ascii=False))'
```

英文项目的 `reason` 文案 · English `reason` text (for English projects):

```bash
python3 -c 'import json; print(json.dumps({"decision":"block","reason":"Before this session ends, follow the Session-end Task Sync rule in CLAUDE.md: if this session completed work, sync new entries and status changes into the root task-list.md and tell the user in your reply; otherwise briefly state there is nothing to sync. This reminder fires once per session."}))'
```

边界说明 · Boundaries:

- hook 只保证「提醒时机」，**不替 agent 写文件**；实际写入仍由 agent 按第 2 步规则正文完成。The hook only guarantees the reminder timing; it does not write the file for the agent.
- `session_id` 守卫保证每会话只 block 一次，避免死循环。The `session_id` guard blocks once per session to avoid loops.
- `settings.json` / hook 通常需**重启会话**才生效；安装后告知用户开新会话实测。`settings.json` / hook usually need a session restart; tell the user to start a new session to test.

## 4. 安装时的注意 · Install notes

- **opt-in**：默认不安装；仅当用户明确表示「希望未来 agent 维护 task-list」时才做。Off by default; install only when the user clearly wants future agents to maintain the task-list.
- **语言一致**：规则正文与 hook `reason` 的语言必须与 `task-list.md` 一致（由 `init --lang` 决定）。Match the language of the rule text and hook `reason` to the `task-list.md` (decided by `init --lang`).
- **记录规范**：写入 `task-list.md` 时遵循 `task-list-standard.md`（只追加、ID 不复用、8 个动作枚举、`YYYY-MM-DD HH:MM` 时间、未完成填 `-`），优先用 CLI `add` 并跑 `check` 校验。Follow `task-list-standard.md` when writing (append-only, IDs never reused, 8-action enum, `YYYY-MM-DD HH:MM` times, `-` for incomplete); prefer CLI `add` then `check`.
- **告知用户**：安装完成后，在回复中说明写入了哪个文件、用了哪种语言、是否装了 hook、需要重启会话生效。After install, tell the user which file was written, in which language, whether the hook was added, and that a restart is needed.
- **与 standardize 检测同源**：`standardize` 报告的「维护规则状态」分区靠固定标记判定是否已安装——在 agent 文件里查找中文标题片段 `会话结束任务同步` 或英文 `Session-end Task Sync`、在 `.claude/settings.json` 的 `Stop` hook 命令里查找 `tasklist`。这些标记就是本模板第 2、3 步正文的固定措辞，因此**不要改动标题与脚本名**；若必须改，需同步更新 `task_list_cli.py` 的 `MAINTENANCE_RULE_MARKER` / `MAINTENANCE_RULE_MARKER_EN` / `TASKLIST_HOOK_MARKER` 常量，否则检测会误报「未安装」。
