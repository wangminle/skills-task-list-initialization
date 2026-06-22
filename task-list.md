# 任务跟踪列表

记录本项目所有任务：代码 bug、bug 转需求、新增需求、需求调整、功能开发、代码审查、测试数据、文档维护、配置运维等。

> 说明：本文件是当前项目的任务清单。所有新增事项、状态变更和完成记录都应同步写入本文件。
> 字段说明：动作字段只允许以下 8 个固定枚举：修复、开发、优化、调整、规划、检查、文档、运维。
> 时间说明：发现时间和完成时间分开记录，格式为 YYYY-MM-DD HH:MM，使用机器本地时区的 24 小时制时间；未完成事项的完成时间填 -。
> 归并规则：审计、复核、核查、审查、验证、评估统一记为“检查”；重构、清理统一记为“优化”；方案、梳理统一记为“规划”；记录类文档事项统一记为“文档”。

## 代码 Bug

| ID | 动作 | 问题描述 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| BUG-001 | 修复 | 状态枚举不一致：已解决 在 COMPLETED_STATUSES 但不在 STATUSES，check 会误报状态不在枚举中 | 2026-06-21 16:04 | 2026-06-21 16:04 | 已修复 | task_list_cli.py 将 已解决 加入 STATUSES；已解决是翻译案例中排查类事项的真实闭环状态，证据见 docs/discussion/3-translation-workflow |

## 调整事项

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |

## 检查事项

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| CHK-001 | 检查 | 当前项目结构、示例任务清单和任务清单标准已检查 | 2026-06-18 00:00 | 2026-06-18 00:00 | 已完成 | 依据 skills/task-list-initialization/SKILL.md、references/task-list-standard.md、示例 task-list 与 CLI/测试文件确认采用默认 7 分区模板 |

## 测试数据

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| TST-001 | 检查 | 验证新建 task-list.md 的结构、ID 和枚举规则 | 2026-06-18 00:00 | 2026-06-18 00:00 | 已完成 | task_list_cli.py check 通过；python3 -m unittest discover -s tests -p 'test_*.py' 运行 3 个测试全部通过 |
| TST-002 | 检查 | 更新 CLI 单元测试覆盖 7 列时间字段 | 2026-06-18 16:58 | 2026-06-18 16:58 | 已完成 | 先确认旧实现测试失败，再更新实现并运行单元测试 |
| TST-003 | 检查 | 为 standardize 子命令补充报告、修复和 schema 迁移测试 | 2026-06-18 17:08 | 2026-06-18 17:08 | 已完成 | 新增 3 个单元测试覆盖 report-only 不改文件、--apply-safe-fixes 补齐缺失分区、--migrate-schema --fix-only 迁移旧 6 列；另修复 profile 误判并补回归断言 |
| TST-004 | 检查 | 新增 summary --write 两个单元测试并跑通全部测试 | 2026-06-21 16:04 | 2026-06-21 16:04 | 已完成 | test_summary_write_recomputes_statistics_section、test_summary_write_appends_section_when_missing；python -m unittest 共 8 个测试全部通过 |

## 文档维护

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| DOC-001 | 文档 | 创建根目录 task-list.md 作为当前项目任务台账 | 2026-06-18 00:00 | 2026-06-18 00:00 | 已完成 | 使用项目自带 CLI 生成；未发现既有根目录 task-list.md、AGENTS.md 或 CLAUDE.md |
| DOC-002 | 文档 | 将 task-list 标准字段从 6 列调整为 7 列时间模型 | 2026-06-18 16:58 | 2026-06-18 16:58 | 已完成 | SKILL.md、task-list-standard.md、task-list-template.md 已同步为发现时间+完成时间，时间格式为 YYYY-MM-DD HH:MM |
| DOC-003 | 文档 | 补充 standardize 模式的 Skill 与标准参考说明 | 2026-06-18 17:08 | 2026-06-18 17:08 | 已完成 | SKILL.md 说明默认 report-only；task-list-standard.md 补充已有列表标准化维度、修复参数和人工确认边界 |
| DOC-004 | 文档 | 同步 skill 文档：状态表补 已解决、CLI 注记 Windows 用 python、补充 summary --write 用法与模板说明 | 2026-06-21 16:04 | 2026-06-21 16:04 | 已完成 | SKILL.md 字段规则与 CLI 段、task-list-standard.md 状态表与标准化段、task-list-template.md 统计摘要段 |

## 功能开发

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| DEV-001 | 开发 | CLI 支持 7 列模板和分钟级发现/完成时间字段 | 2026-06-18 16:58 | 2026-06-18 16:58 | 已完成 | 新增 --found-time 与 --completed-time；默认使用机器本地时区 YYYY-MM-DD HH:MM；development 扩展表同步为 9 列 |
| DEV-002 | 开发 | 新增 standardize 子命令用于检查和可选规范化已有 task-list | 2026-06-18 17:08 | 2026-06-18 17:08 | 已完成 | 默认只生成诊断报告；--apply-safe-fixes 执行低风险修复；--migrate-schema 迁移旧时间列；--fix-only 只输出修复摘要 |
| DEV-003 | 开发 | summary 子命令新增 --write，按当前记录重算并回写统计摘要表 | 2026-06-21 16:04 | 2026-06-21 16:04 | 已完成 | 新增 compute_summary_rows/render_summary_with_counts/update_summary_text；--dry-run 预览；摘要不存在时自动追加；专利案例 260 条实测总计 256 完成/1 待办/98% |

## 配置运维

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
