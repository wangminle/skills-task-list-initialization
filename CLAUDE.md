# CLAUDE.md

本项目是 **task-list-initialization** skill——用于创建、标准化、校验、维护项目级 `task-list.md`。完整定义见 `skills/task-list-initialization/SKILL.md`，字段标准见 `references/task-list-standard.md`。

## 会话结束任务同步（必须）

每次会话结束前，若本次涉及任务完成——包括但不限于 **bug 修复、功能开发、代码审查、测试数据准备、文档更新、配置运维**——必须：

1. 把新增条目与状态变更写入根目录 `task-list.md`，与实际进度同步；
2. 在本次最后一条回复中告知用户：记录/更新了哪些条目（ID + 简述）。

若本次未涉及任何任务完成，无需操作也无需提示。该时机由 `.claude/settings.json` 的 `Stop` hook 保证触发（每会话一次）。

## 记录规范（摘要，详情见 references）

- **只追加**：历史记录不改写；ID 递增、不复用、不跨语义移动。
- **优先用 CLI 写入**：`python3 skills/task-list-initialization/scripts/task_list_cli.py add ...`，写完跑 `... check --file task-list.md` 校验。
- **8 个动作枚举**：修复 / 开发 / 优化 / 调整 / 规划 / 检查 / 文档 / 运维；近义词先归并（如 重构→优化、审计→检查）。
- **时间**：发现时间与完成时间分列，`YYYY-MM-DD HH:MM` 本地时区 24 小时制；未完成填 `-`。
