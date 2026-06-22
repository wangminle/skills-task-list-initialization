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
| BUG-002 | 修复 | prefix_for_section 不解析 SECTION_ALIASES，遗留分区名（如 开源项目调研）无法 add | 2026-06-22 12:10 | 2026-06-22 12:10 | 已修复 | prefix_for_section 先经 SECTION_ALIASES 归一化再查前缀；新增 test_add_to_legacy_aliased_section_name |
| BUG-003 | 修复 | development profile 下 开发/功能 别名失效，无法命中 开发事项 | 2026-06-22 12:10 | 2026-06-22 12:10 | 已修复 | find_section_by_title 让 功能开发/开发事项 互为候选，命中文件实际存在的分区；新增 test_add_dev_alias_works_in_development_profile |
| BUG-004 | 修复 | --fix-only 隐式触发 --apply-safe-fixes，--migrate-schema --fix-only 会意外补齐分区 | 2026-06-22 12:10 | 2026-06-22 12:10 | 已修复 | should_fix 与 add_missing_sections 条件移除 fix_only；--fix-only 现为纯输出修饰；新增 2 个回归测试并同步 help 文案 |
| BUG-005 | 修复 | --date 对已完成状态不再回填完成时间（前一轮修复 --date 未完成项 bug 时引入的回归） | 2026-06-22 12:10 | 2026-06-22 12:10 | 已修复 | 仅完成态回填完成时间，对齐 legacy_completed_time；未完成仍为 -；新增 test_add_date_backfills_completed_time_for_completed_status |
| BUG-006 | 修复 | 调研分区反向别名缺失：文件含 开源项目调研 时 add --section 调研事项 报未找到分区 | 2026-06-22 12:17 | 2026-06-22 12:17 | 已修复 | find_section_by_title 新增 SECTION_ALIASED_FROM 反向查找，使规范名命中文件中的旧标题（调研事项↔开源项目调研、文档维护↔文档事项等）；新增 2 个回归测试 |
| BUG-007 | 修复 | insert_row 用精确字符串匹配标题，## 后多空格时 add 报未找到分区，与 parse_sections 的正则容忍不一致 | 2026-06-22 13:06 | 2026-06-22 13:06 | 已修复 | insert_row 改用 ^##\s+(.+?)\s*$ 正则匹配；新增 test_add_to_heading_with_irregular_whitespace；全部 18 测试通过 |

## 调整事项

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |

## 检查事项

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| CHK-001 | 检查 | 当前项目结构、示例任务清单和任务清单标准已检查 | 2026-06-18 00:00 | 2026-06-18 00:00 | 已完成 | 依据 skills/task-list-initialization/SKILL.md、references/task-list-standard.md、示例 task-list 与 CLI/测试文件确认采用默认 7 分区模板 |
| CHK-002 | 检查 | 复核 CLI 分区别名、--fix-only 语义、--date 完成时间、--project-root 一致性 | 2026-06-22 12:10 | 2026-06-22 12:10 | 已完成 | 依据代码审查反馈逐项确认 5 个问题，全部修复并补回归测试，共 15 个测试通过 |
| CHK-003 | 检查 | 全量审查 CLI/测试/SKILL/标准/模板/README/CLAUDE/hook/维护规则文档与代码一致性 | 2026-06-22 13:06 | 2026-06-22 13:06 | 已完成 | 动态验证 check/summary/竖线转义/中间统计摘要回写/标题空白等边界；仅发现并修复 insert_row 标题匹配不一致 bug |

## 测试数据

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| TST-001 | 检查 | 验证新建 task-list.md 的结构、ID 和枚举规则 | 2026-06-18 00:00 | 2026-06-18 00:00 | 已完成 | task_list_cli.py check 通过；python3 -m unittest discover -s tests -p 'test_*.py' 运行 3 个测试全部通过 |
| TST-002 | 检查 | 更新 CLI 单元测试覆盖 7 列时间字段 | 2026-06-18 16:58 | 2026-06-18 16:58 | 已完成 | 先确认旧实现测试失败，再更新实现并运行单元测试 |
| TST-003 | 检查 | 为 standardize 子命令补充报告、修复和 schema 迁移测试 | 2026-06-18 17:08 | 2026-06-18 17:08 | 已完成 | 新增 3 个单元测试覆盖 report-only 不改文件、--apply-safe-fixes 补齐缺失分区、--migrate-schema --fix-only 迁移旧 6 列；另修复 profile 误判并补回归断言 |
| TST-004 | 检查 | 新增 summary --write 两个单元测试并跑通全部测试 | 2026-06-21 16:04 | 2026-06-21 16:04 | 已完成 | test_summary_write_recomputes_statistics_section、test_summary_write_appends_section_when_missing；python -m unittest 共 8 个测试全部通过 |
| TST-005 | 检查 | 为分区别名、development 别名、--fix-only 语义、--date 完成时间回填补充回归测试 | 2026-06-22 12:10 | 2026-06-22 12:10 | 已完成 | 新增 5 个测试（legacy 别名 add、development 别名、fix-only 不补齐、migrate+fix-only 不补齐、date 完成态回填）；python3 -m unittest 共 15 个测试全部通过 |
| TST-006 | 检查 | 为调研/文档分区反向别名补充回归测试 | 2026-06-22 12:17 | 2026-06-22 12:17 | 已完成 | 新增 test_add_canonical_name_matches_legacy_research_heading、test_add_canonical_name_matches_legacy_doc_heading；python3 -m unittest 共 17 个测试全部通过 |
| TST-007 | 检查 | 为标题空白容错补充回归测试 | 2026-06-22 13:06 | 2026-06-22 13:06 | 已完成 | test_add_to_heading_with_irregular_whitespace；python3 -m unittest 共 18 个测试全部通过 |

## 文档维护

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| DOC-001 | 文档 | 创建根目录 task-list.md 作为当前项目任务台账 | 2026-06-18 00:00 | 2026-06-18 00:00 | 已完成 | 使用项目自带 CLI 生成；未发现既有根目录 task-list.md、AGENTS.md 或 CLAUDE.md |
| DOC-002 | 文档 | 将 task-list 标准字段从 6 列调整为 7 列时间模型 | 2026-06-18 16:58 | 2026-06-18 16:58 | 已完成 | SKILL.md、task-list-standard.md、task-list-template.md 已同步为发现时间+完成时间，时间格式为 YYYY-MM-DD HH:MM |
| DOC-003 | 文档 | 补充 standardize 模式的 Skill 与标准参考说明 | 2026-06-18 17:08 | 2026-06-18 17:08 | 已完成 | SKILL.md 说明默认 report-only；task-list-standard.md 补充已有列表标准化维度、修复参数和人工确认边界 |
| DOC-004 | 文档 | 同步 skill 文档：状态表补 已解决、CLI 注记 Windows 用 python、补充 summary --write 用法与模板说明 | 2026-06-21 16:04 | 2026-06-21 16:04 | 已完成 | SKILL.md 字段规则与 CLI 段、task-list-standard.md 状态表与标准化段、task-list-template.md 统计摘要段 |
| DOC-005 | 文档 | 同步 README 测试数量为 15，更新 --date 与 --fix-only help 文案，移除未实现的 --project-root | 2026-06-22 12:10 | 2026-06-22 12:10 | 已完成 | README 英中两区 badge 与正文测试数同步；help 文案澄清 --date 仅回退发现时间、--fix-only 需配合修复参数 |
| DOC-006 | 文档 | 收紧 SKILL.md / task-list-standard.md / README 对 --fix-only 的表述，明确其为输出修饰 | 2026-06-22 12:17 | 2026-06-22 12:17 | 已完成 | 三处文档统一改为「输出修饰，本身不触发修复，需配合 --apply-safe-fixes 或 --migrate-schema」，与 CLI help 与实现一致 |
| DOC-007 | 文档 | 创建 CLAUDE.md，写入会话结束任务同步规则与记录规范摘要 | 2026-06-22 12:50 | 2026-06-22 12:50 | 已完成 | CLAUDE.md 含必须遵守的会话末同步规则（写 task-list.md + 通知用户）与记录规范摘要；规则按 SKILL.md 工作流第 5 步落到 AGENTS/CLAUDE 等价文件 |
| DOC-008 | 文档 | 新增 references/maintenance-rule.md 维护规则安装模板 | 2026-06-22 12:58 | 2026-06-22 12:58 | 已完成 | 含文件选择优先级、规则正文、可选 Stop hook（settings.json+脚本，session_id 守卫防死循环）、安装注意事项；SKILL.md References 同步登记 |
| DOC-009 | 文档 | 同步 README 测试数量 17→18 并补充覆盖项描述 | 2026-06-22 13:06 | 2026-06-22 13:06 | 已完成 | badge、英文 Tested、中文经过测试、英中各一处测试结论；新增标题空白容错覆盖说明 |

## 功能开发

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| DEV-001 | 开发 | CLI 支持 7 列模板和分钟级发现/完成时间字段 | 2026-06-18 16:58 | 2026-06-18 16:58 | 已完成 | 新增 --found-time 与 --completed-time；默认使用机器本地时区 YYYY-MM-DD HH:MM；development 扩展表同步为 9 列 |
| DEV-002 | 开发 | 新增 standardize 子命令用于检查和可选规范化已有 task-list | 2026-06-18 17:08 | 2026-06-18 17:08 | 已完成 | 默认只生成诊断报告；--apply-safe-fixes 执行低风险修复；--migrate-schema 迁移旧时间列；--fix-only 只输出修复摘要 |
| DEV-003 | 开发 | summary 子命令新增 --write，按当前记录重算并回写统计摘要表 | 2026-06-21 16:04 | 2026-06-21 16:04 | 已完成 | 新增 compute_summary_rows/render_summary_with_counts/update_summary_text；--dry-run 预览；摘要不存在时自动追加；专利案例 260 条实测总计 256 完成/1 待办/98% |
| DEV-004 | 开发 | 修复 CLI 分区别名解析、development 别名、--fix-only 语义、--date 完成时间回填 | 2026-06-22 12:10 | 2026-06-22 12:10 | 已完成 | task_list_cli.py 7 处改动（含移除 --project-root）；test_task_list_cli.py 新增 5 个回归测试；共 15 个测试通过 |
| DEV-005 | 开发 | 调研/文档等分区反向别名机制，并收紧 --fix-only 文档表述 | 2026-06-22 12:17 | 2026-06-22 12:17 | 已完成 | 新增 SECTION_ALIASED_FROM 反向查找并接入 find_section_by_title；SKILL/standard/README 三处 --fix-only 表述统一为输出修饰；新增 2 个回归测试，共 17 个通过 |
| DEV-006 | 开发 | 将维护规则安装补充为 skill 工作流第 5 步子任务 | 2026-06-22 12:58 | 2026-06-22 12:58 | 已完成 | SKILL.md 第 5 步从一句话扩展为：按 CLAUDE.md>AGENTS.md>新建 CLAUDE.md 优先级写入规则正文，可选装 Stop hook 保证层；指向 references/maintenance-rule.md |

## 配置运维

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| OPS-001 | 运维 | 配置 Stop hook 保证会话末任务同步时机 | 2026-06-22 12:50 | 2026-06-22 12:50 | 已完成 | .claude/settings.json 注册 Stop hook；hooks/tasklist_sync_reminder.sh 每会话首次停止注入 block 提醒，session_id 守卫防死循环；模拟 fresh/重复/缺 session_id 三场景通过 |
