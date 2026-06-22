#!/usr/bin/env bash
# Stop hook — project: skills-task-list-initialization
# Once per session, remind the agent to sync task-list.md before truly stopping.
# Guarded by session_id so it can never cause an infinite stop loop.

input="$(cat)"
session_id="$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_id") or "default")' 2>/dev/null || echo default)"
guard="/tmp/claude-tasklist-sync-${session_id}"

# Already reminded this session → allow the stop (no output, exit 0).
if [ -f "$guard" ]; then
  exit 0
fi
touch "$guard"

# Block once: this JSON reason is fed back to the agent so it acts before stopping.
# (decision:block on stdout + exit 0; the agent then continues for one more turn.)
python3 -c 'import json; print(json.dumps({"decision": "block", "reason": "会话结束前请按 CLAUDE.md 的「会话结束任务同步」规则执行：若本次涉及任务完成（bug 修复 / 功能开发 / 代码审查 / 测试数据 / 文档更新 / 配置运维），把新增条目与状态变更写入根目录 task-list.md（追加，优先用 CLI add 并跑 check），并在回复中告知用户记录了哪些条目；若无任务完成则简短说明无需同步。本提醒每会话仅触发一次。"}, ensure_ascii=False))'
