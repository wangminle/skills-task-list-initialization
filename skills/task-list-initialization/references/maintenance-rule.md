# 维护规则安装模板（maintenance-rule）

当用户希望「未来的 agent 自动维护 task-list」时，按本模板把维护规则写入项目的 agent 配置文件。这是 skill 工作流（第 5 步）的子任务，目标：让任何后续会话都能可靠地把任务完成情况同步进 `task-list.md`。

本模板分两层：**策略**（写进 CLAUDE.md/AGENTS.md，告诉 agent 做什么）+ **可选保证层**（Stop hook，确保每次会话末都触发）。

## 1. 写入哪个文件

按优先级选择**一个**文件（已存在则用，都不存在则新建第一个）：

1. `CLAUDE.md` —— Claude Code 项目首选，会话开始自动加载。
2. `AGENTS.md` —— 跨工具通用约定。
3. 两者都没有 → 新建 `CLAUDE.md`。

注意：

- 不要同时往两个文件写重复内容；若两者都已存在，优先追加到 `CLAUDE.md`。
- 追加到文件末尾，**保留原有约定**，不破坏现有内容。
- **幂等**：若目标文件已含「会话结束任务同步」标题，不要重复追加。

## 2. 规则正文（写入所选文件）

把下面这段追加到所选文件（可按项目语境微调）：

```markdown
## 会话结束任务同步（必须）

每次会话结束前，若本次涉及任务完成——包括但不限于 bug 修复、功能开发、代码审查、测试数据准备、文档更新、配置运维——必须：

1. 把新增条目与状态变更写入根目录 `task-list.md`，与实际进度同步；
2. 在本次最后一条回复中告知用户：记录/更新了哪些条目（ID + 简述）。

若本次未涉及任何任务完成，无需操作也无需提示。
```

## 3.（可选）保证层：Stop hook

上面的规则只是「策略」，靠 agent 自觉；要做到「每次会话末必触发」，追加一个 `Stop` hook。是否安装由用户决定（默认不装）。

在项目 `.claude/settings.json` 注册：

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

脚本 `.claude/hooks/tasklist_sync_reminder.sh`（每会话首次停止注入 `block` 提醒，用 `session_id` 守卫防死循环）：

```bash
#!/usr/bin/env bash
input="$(cat)"
session_id="$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_id") or "default")' 2>/dev/null || echo default)"
guard="/tmp/claude-tasklist-sync-${session_id}"
[ -f "$guard" ] && exit 0
touch "$guard"
python3 -c 'import json; print(json.dumps({"decision":"block","reason":"会话结束前请按 CLAUDE.md 的「会话结束任务同步」规则：若本次涉及任务完成，把新增条目与状态变更写入根目录 task-list.md 并在回复中告知用户；否则简短说明无需同步。本提醒每会话仅触发一次。"}, ensure_ascii=False))'
```

边界说明：

- hook 只保证「提醒时机」，**不替 agent 写文件**；实际写入仍由 agent 按第 2 步规则正文完成。
- `session_id` 守卫保证每会话只 block 一次，避免「停止→提醒→停止→提醒」死循环。
- `settings.json` / hook 通常需**重启会话**才生效；安装后告知用户开新会话实测。

## 4. 安装时的注意

- **opt-in**：默认不安装；仅当用户明确表示「希望未来 agent 维护 task-list」时才做。
- **记录规范**：写入 `task-list.md` 时遵循 `task-list-standard.md`（只追加、ID 不复用、8 个动作枚举、`YYYY-MM-DD HH:MM` 时间、未完成填 `-`），优先用 CLI `add` 并跑 `check` 校验。
- **告知用户**：安装完成后，在回复中说明写入了哪个文件、是否装了 hook、需要重启会话生效。
- **与 standardize 检测同源**：`standardize` 报告的「维护规则状态」分区靠固定标记判定是否已安装——在 agent 文件里查找标题片段 `会话结束任务同步`、在 `.claude/settings.json` 的 `Stop` hook 命令里查找 `tasklist`。这两个标记就是本模板第 2、3 步正文的固定措辞，因此**不要改动标题与脚本名**；若必须改，需同步更新 `task_list_cli.py` 的 `MAINTENANCE_RULE_MARKER` / `TASKLIST_HOOK_MARKER` 常量，否则检测会误报「未安装」。
