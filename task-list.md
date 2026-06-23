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
| BUG-008 | 修复 | --date 同时作为发现/完成时间回退，导致待修复等未完成记录出现自相矛盾的完成时间 | 2026-06-22 13:30 | 2026-06-22 13:30 | 已修复 | completed_time 计算移除 or args.date；--date 仅回退发现时间（后续 BUG-005 进一步细化为完成态回填）；新增 test_add_date_does_not_seed_completed_time_for_incomplete |
| BUG-009 | 修复 | standardize --dry-run 把修复后文件内容与诊断报告都打到 stdout，重定向会损坏文件 | 2026-06-22 13:30 | 2026-06-22 13:30 | 已修复 | dry-run 预览文件后，报告/摘要改走 stderr（status_stream）；新增 test_standardize_dry_run_stdout_is_only_file_content |
| BUG-010 | 修复 | 维护规则检测在 CLAUDE.md 与 AGENTS.md 同时存在时 false negative：规则仅在 AGENTS.md 时命中 CLAUDE.md 即 break，误报未检测到并建议重复安装 | 2026-06-22 14:50 | 2026-06-22 14:50 | 已修复 | detect_maintenance_rule 改为扫描两个文件，contaming 列表优先返回 CLAUDE.md；未安装时回落到首选现有文件作为安装目标；新增 3 个回归测试（仅 AGENTS/双文件/均无），共 25 测试通过 |
| BUG-011 | 修复 | split_cells 与 escape_cell 转义不幂等：migrate 重建行时把备注里已转义的竖线双重转义成 \\\|，导致该行被解析成 9 列（另一项目迁移 CHK-006/DOC-005 时实测触发） | 2026-06-22 17:51 | 2026-06-22 17:51 | 已修复 | split_cells 改为解码转义竖线为逻辑值（解析器应解码而非保留语法），escape_cell 写回再编码，二者互逆、往返幂等；二次 migrate 零变更；新增幂等回归测试 |
| BUG-012 | 修复 | standardize --migrate-schema 静默跳过列数异常行：表头迁移后，破损数据行被原样漏下且不计入告警 | 2026-06-22 18:10 | 2026-06-22 18:10 | 已修复 | 根因：migrate_legacy_schema 的 fallthrough 分支对「活跃迁移上下文 + 数据行 + 列数与 legacy 表头不符」直接 append 不告警。真实命中：某项目迁移报「修复完成：12 项」却漏掉两行单元格内未转义的 JS \|\| 的记录，靠后续 check 才发现。修复：fallthrough 前记 migrate_skip 告警（ID + 行号 + legacy 列数 + 实际列数），随第三返回值 warnings 返回，在 --fix-only 摘要、--format json、报告三处暴露。与 BUG-011（转义幂等）、DEV-009（schema 变体）同属 migrate 路径的真实脏数据兜底。 |
| BUG-013 | 修复 | command_add 不识别单日期 schema，向 6 列表追加 7 列行导致列数异常 | 2026-06-22 18:12 | 2026-06-22 18:12 | 已修复 | command_add 按表头匹配 dual/single/dev 变体并生成对应列数；新增 single_date_cell 辅助函数与 test_add_to_single_date_schema；record_quality_warnings 改为 len(cells)<6 以覆盖单日期记录 |
| BUG-014 | 修复 | find_section_by_title 对未登记大小写的英文分区名报 not found（如 --section bugs） | 2026-06-22 20:13 | 2026-06-22 20:13 | 已修复 | 根因：_EN.section_aliases 只为部分分区（features/docs）登记了小写复数，bugs/reviews/adjustments 等缺失；find_section_by_title 完全依赖该映射，导致英文文件下 add --section bugs 直接 not found。修复：精确别名与反查均未命中后，加一轮对文件实际标题的大小写不敏感回退（title.lower()==heading.lower()），覆盖 bugs/BUGS/Reviews 等任意大小写，中文（代码 bug→代码 Bug）同样生效。+回归测试 test_add_section_is_case_insensitive。 |
| BUG-015 | 修复 | 时间字段仅做形状正则，非法日期（2026-99-99 99:99）可写入且 check 不拦 | 2026-06-22 20:13 | 2026-06-22 20:13 | 已修复 | 根因：normalize_time 仅 re.match 形状不解析真实日期；check_text 只校验列数/动作/状态，不校验时间值。修复：normalize_time 形状通过后再用 datetime.strptime 真解析，不存在日期直接 bad_time 拒写、文件不变；check_text 对每行 cells[-3]（完成时间）及 dual schema 下 cells[-4]（发现时间）用 _is_valid_time 校验（接受 - / 空 / YYYY-MM-DD HH:MM / YYYY-MM-DD 单日期），不存在日期报 bad_time_line。新增 _is_valid_time/_try_strptime 辅助。+回归测试 test_add_rejects_invalid_date、test_check_flags_invalid_date。 |
| BUG-016 | 修复 | check 对非法 ID（bug-001/BUG-12）静默放行 | 2026-06-23 12:10 | 2026-06-23 12:10 | 已修复 | check_text 字段校验全嵌在合法 ID 分支内，非法 ID 整块跳过致'检查通过'+summary 总计0；新增 _looks_like_id 启发式与 bad_id_line 报错，check_ok 文案补'非法 ID' |
| BUG-017 | 修复 | add 在错位表头下按列数硬回退污染数据 | 2026-06-23 12:10 | 2026-06-23 12:10 | 已修复 | 表头列序错位（ID/状态/动作/...）时按默认列序写值，动作值'修复'落入状态列；改为拒绝写入并提示先 standardize/migrate，补 nonstandard_header 报错 |
| BUG-018 | 修复 | check_text 混合 schema 文件时间校验用错列下标 | 2026-06-23 12:10 | 2026-06-23 12:10 | 已修复 | detect_schema 文件级判定+固定下标 cells[-3]，混合文件6列行被当7列索引致把事项值当时间报错；新增 time_column_indices 按各分区表头列名定位 |
| BUG-019 | 修复 | add --id 指定已存在 ID 时静默追加重复行（rc=0 无提示），违反 ID 唯一不变量 | 2026-06-23 12:24 | 2026-06-23 12:24 | 已修复 | 根因：command_add 采用 args.id 时不检查该 ID 是否已作为记录首列存在，显式 --id 复用既有 ID 会静默写入重复行，check 事后才报。修复：item_id 确定后，若 args.id 命中 collect_records 扫出的现有 ID 集合则 raise dup_id_on_add 拒写（新增中英文案），未占用 ID 仍可正常用。与 next_id/bad_id_line/nonstandard_header 同属写时防线。+回归测试 test_add_refuses_duplicate_explicit_id。 |

## 调整事项

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| ADJ-001 | 调整 | README 测试数量文案不一致（badge 38、正文 36/38 混用） | 2026-06-22 18:12 | 2026-06-22 18:12 | 已完成 | 统一为 39（含新增单日期 add 回归测试） |

## 检查事项

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| CHK-001 | 检查 | 当前项目结构、示例任务清单和任务清单标准已检查 | 2026-06-18 00:00 | 2026-06-18 00:00 | 已完成 | 依据 skills/task-list-initialization/SKILL.md、references/task-list-standard.md、示例 task-list 与 CLI/测试文件确认采用默认 7 分区模板 |
| CHK-002 | 检查 | 复核 CLI 分区别名、--fix-only 语义、--date 完成时间、--project-root 一致性 | 2026-06-22 12:10 | 2026-06-22 12:10 | 已完成 | 依据代码审查反馈逐项确认 5 个问题，全部修复并补回归测试，共 15 个测试通过 |
| CHK-003 | 检查 | 全量审查 CLI/测试/SKILL/标准/模板/README/CLAUDE/hook/维护规则文档与代码一致性 | 2026-06-22 13:06 | 2026-06-22 13:06 | 已完成 | 动态验证 check/summary/竖线转义/中间统计摘要回写/标题空白等边界；仅发现并修复 insert_row 标题匹配不一致 bug |
| CHK-004 | 检查 | 全量回归+边界探测核查 CLI 是否仍有 bug | 2026-06-23 11:35 | 2026-06-23 11:35 | 已完成 | 44 项 pytest 全通过；动态探测 next_id 引用隔离/开发档9列/单日期/竖线转义往返/摘要中部回写/8列旧开发档迁移均正常；未发现可执行 bug |
| CHK-005 | 检查 | 复核全部文档与最新实现一致性并登记本轮bug修复 | 2026-06-23 12:10 | 2026-06-23 12:10 | 已完成 | 逐项核对SKILL/README/references与CLI实现；发现文档未体现非法ID检测与表头拒绝两项新行为，已补齐；task-list.md历史记录按追加式规则保留不改，本轮工作以新记录登记 |

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
| TST-008 | 检查 | 为 standardize 维护规则检测补充回归测试 | 2026-06-22 14:23 | 2026-06-22 14:23 | 已完成 | 4 个测试：缺失/规则+hook 齐全/仅规则缺 hook/JSON 输出；python3 -m unittest 共 22 个测试全部通过 |
| TST-009 | 检查 | 为双 agent 文件维护规则检测补充回归测试 | 2026-06-22 14:50 | 2026-06-22 14:50 | 已完成 | 3 个测试：两文件均在但规则仅在 AGENTS.md（核心回归）/两文件均含规则优先 CLAUDE.md/两文件均无规则回落 CLAUDE.md 目标；python3 -m unittest 共 25 个测试全部通过 |
| TST-010 | 检查 | 为中英双语支持补充回归测试 | 2026-06-22 17:13 | 2026-06-22 17:13 | 已完成 | 6 个测试：init --lang en/默认中文/add 英文分区自动检测/check 英文枚举校验/standardize 英文报告/summary 英文回写；python3 -m unittest 共 31 个测试全部通过 |
| TST-011 | 检查 | 为日期 schema 变体检测与重复 ID 映射建议补充回归测试 | 2026-06-22 17:40 | 2026-06-22 17:40 | 已完成 | 5 个测试：check 接受单日期 schema/check --schema single 强制/standardize 单日期升级建议且不报表头不一致/standardize 重复 ID 建议 ADJ 映射/JSON 含 schema 字段；python3 -m unittest 共 36 个测试全部通过 |
| TST-012 | 检查 | 为转义竖线 migrate 幂等性补充回归测试 | 2026-06-22 17:52 | 2026-06-22 17:52 | 已完成 | 6 列含转义竖线备注 migrate 后保留单层转义、二次 migrate 无变更、无 9 列异常；python3 -m unittest 共 37 个测试全部通过 |
| TST-013 | 检查 | migrate 跳行告警回归测试 test_migrate_warns_on_skipped_malformed_row | 2026-06-22 18:10 | 2026-06-22 18:10 | 已完成 | 断言 --migrate-schema --fix-only 输出含「ID + 第 N 行 + 实际 X 列 + legacy 表头 Y 列」的跳行告警，且 --format json 的 migrate_warnings 非空；干净文件无误报。全套 38 通过（37 增至 38）。 |
| TST-014 | 检查 | 分区大小写不敏感 + 时间校验回归测试（3 条） | 2026-06-22 20:13 | 2026-06-22 20:13 | 已完成 | test_add_section_is_case_insensitive（bugs/BUGS→Bugs）、test_add_rejects_invalid_date（2026-99-99 99:99 拒写且文件不变）、test_check_flags_invalid_date（坏日期被 check 拦 + 单日期 date-only 不误报）。全套 42 通过（39 增至 42）。 |
| TST-015 | 检查 | add --id 重复 ID 拒写回归测试 | 2026-06-23 12:24 | 2026-06-23 12:24 | 已完成 | test_add_refuses_duplicate_explicit_id：--id 指定已存在的 BUG-001 时 rc!=0、文案含 BUG-001、文件不变（DUPE 未写入、BUG-001 计数仍 1）；未占用的 --id 仍可正常追加。全套 48 通过（47 增至 48）。 |

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
| DOC-010 | 文档 | 创建 README.md 双语文档（英文在上、中文在下、顶部语言切换） | 2026-06-22 13:30 | 2026-06-22 13:30 | 已完成 | 含概览/特性/标准/CLI/profiles/标准化/测试/结构/许可证；badge 与测试数随修复同步至 18 |
| DOC-011 | 文档 | 同步维护规则检测文档：SKILL/standard/maintenance-rule/README 四处双语同步 | 2026-06-22 14:23 | 2026-06-22 14:23 | 已完成 | SKILL.md standardize 段新增 Maintenance-rule check；standard 报告表新增维护规则状态行；maintenance-rule.md 第 4 节标注检测标记与 CLI 常量同源；README badge/特性/标准化/结构树/测试数 22 双语同步 |
| DOC-012 | 文档 | 同步双语能力文档：SKILL/standard/template/maintenance-rule/README 五处双语 | 2026-06-22 17:13 | 2026-06-22 17:13 | 已完成 | SKILL.md 新增 Language 段+工作流语言步骤+--lang 示例；task-list-standard.md 新增语言版本映射表；task-list-template.md 新增 English templates；maintenance-rule.md 改为双语（规则正文/hook reason 中英二选一+语言选择说明）；README 双语特性/--lang/测试数 31 |
| DOC-013 | 文档 | 同步日期 schema 变体与重复 ID 建议文档：README/SKILL/standard 三处双语 | 2026-06-22 17:40 | 2026-06-22 17:40 | 已完成 | README 增 schema 变体特性、--schema 示例、测试数 36、标准化段双注；SKILL.md Standardizing 增 schema 变体与重复 ID 两段、CLI 增 --schema；task-list-standard.md 报告维度增日期 schema 变体行、新增日期 schema 变体小节 |
| DOC-014 | 文档 | migrate 跳行告警的文档同步：README 中英文 + task-list-standard.md | 2026-06-22 18:10 | 2026-06-22 18:10 | 已完成 | README 测试徽标 36 改 38、中英文 schema 变体段补充 migrate_warnings 行为说明；task-list-standard.md 的 --migrate-schema 表后补「跳行告警语义 + 先手工转义再重跑」处理建议。 |
| DOC-015 | 文档 | 文档同步至最新 CLI 能力：add 的 schema 自动识别、migrate 跳行告警 | 2026-06-22 18:21 | 2026-06-22 18:21 | 已完成 | 补齐 BUG-013（add 单日期）与 BUG-012（migrate 跳行告警）的文档缺口：SKILL.md 的 --migrate-schema 条补 migrate_warnings 跳行语义、Schema variants 段与 CLI 段补 add 按分区 schema 输出对应列数；README 中英文特性列表与 CLI 段同步 add schema 说明；task-list-standard.md 日期 schema 变体段补 add 行为条目（含 --date 填充规则）。 |
| DOC-016 | 文档 | README 英文段改用英文 schema 标签，与 init --lang en 产物一致 | 2026-06-22 18:44 | 2026-06-22 18:44 | 已完成 | 双语支持后英文段仍用中文标签（代码 Bug/修复/待修复）且含已失效的 intentionally Chinese 说明，与 init --lang en 生成的全英文文件矛盾。改：表头/字段表/分区表/动作枚举/状态/profiles/migrate 目标列/add 示例全部转英文（取自 _EN locale 权威值 Bugs/Adjustments/Reviews/.../Fix/Develop/.../Pending Fix/Fixed/...）；intentionally Chinese 改为 localization 说明（前缀与列模型跨语言一致，仅标签不同，指向 bilingual 表）。中文段不动；英文 add 示例已 e2e 验证可跑通。 |
| DOC-017 | 文档 | 文档同步：测试数 39 改 42、check 行为补时间戳校验、覆盖列表补两项 | 2026-06-22 20:13 | 2026-06-22 20:13 | 已完成 | README badge/英文正文/中文正文测试数 39 改 42；中英文 check 命令行补时间戳校验；Tested 覆盖列表补时间戳校验 + 分区别名大小写不敏感。 |
| DOC-018 | 文档 | 文档与最新实现同步：非法ID检测、表头拒绝、测试数47 | 2026-06-23 12:10 | 2026-06-23 12:10 | 已完成 | README中英文badge/特性/Tested/命令说明补非法ID检测+非标准表头拒绝+测试数42改47；SKILL.md workflow step6+CLI段补两项行为；task-list-standard.md check维度表+常见问题表补非法ID与add拒绝条目 |
| DOC-019 | 文档 | README 同步 add --id 重复拒绝 + 测试数 47 改 48 | 2026-06-23 12:24 | 2026-06-23 12:24 | 已完成 | 中英文「Safe add / 严格 check」bullet 补「显式 --id 指定已存在 ID 时拒写而非静默制造重复」；测试数 badge/英文正文/中文正文 47 改 48。 |

## 功能开发

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| DEV-001 | 开发 | CLI 支持 7 列模板和分钟级发现/完成时间字段 | 2026-06-18 16:58 | 2026-06-18 16:58 | 已完成 | 新增 --found-time 与 --completed-time；默认使用机器本地时区 YYYY-MM-DD HH:MM；development 扩展表同步为 9 列 |
| DEV-002 | 开发 | 新增 standardize 子命令用于检查和可选规范化已有 task-list | 2026-06-18 17:08 | 2026-06-18 17:08 | 已完成 | 默认只生成诊断报告；--apply-safe-fixes 执行低风险修复；--migrate-schema 迁移旧时间列；--fix-only 只输出修复摘要 |
| DEV-003 | 开发 | summary 子命令新增 --write，按当前记录重算并回写统计摘要表 | 2026-06-21 16:04 | 2026-06-21 16:04 | 已完成 | 新增 compute_summary_rows/render_summary_with_counts/update_summary_text；--dry-run 预览；摘要不存在时自动追加；专利案例 260 条实测总计 256 完成/1 待办/98% |
| DEV-004 | 开发 | 修复 CLI 分区别名解析、development 别名、--fix-only 语义、--date 完成时间回填 | 2026-06-22 12:10 | 2026-06-22 12:10 | 已完成 | task_list_cli.py 7 处改动（含移除 --project-root）；test_task_list_cli.py 新增 5 个回归测试；共 15 个测试通过 |
| DEV-005 | 开发 | 调研/文档等分区反向别名机制，并收紧 --fix-only 文档表述 | 2026-06-22 12:17 | 2026-06-22 12:17 | 已完成 | 新增 SECTION_ALIASED_FROM 反向查找并接入 find_section_by_title；SKILL/standard/README 三处 --fix-only 表述统一为输出修饰；新增 2 个回归测试，共 17 个通过 |
| DEV-006 | 开发 | 将维护规则安装补充为 skill 工作流第 5 步子任务 | 2026-06-22 12:58 | 2026-06-22 12:58 | 已完成 | SKILL.md 第 5 步从一句话扩展为：按 CLAUDE.md>AGENTS.md>新建 CLAUDE.md 优先级写入规则正文，可选装 Stop hook 保证层；指向 references/maintenance-rule.md |
| DEV-007 | 开发 | standardize 增加「维护规则状态」检测分区：扫描项目根的 CLAUDE.md/AGENTS.md 标题与 .claude/settings.json 的 Stop hook，只读检测不安装 | 2026-06-22 14:23 | 2026-06-22 14:23 | 已完成 | 新增 detect_maintenance_rule/render_maintenance_lines；analyze_standardization 增 project_root 参数与 maintenance 字段；report 新增维护规则状态分区；JSON 格式自动携带 |
| DEV-008 | 开发 | task-list 支持中英双语：init --lang zh\|en 选择语言（默认中文简体），英文为中文忠实翻译；add/check/summary/standardize 按文件结构自动检测语言 | 2026-06-22 17:13 | 2026-06-22 17:13 | 已完成 | CLI 重构为 Locale 驱动（_ZH/_EN 两套 schema+T 文案表）；新增 detect_locale/get_locale；init 增 --lang；英文分区/列/动作/状态/报告/摘要全量翻译；ID 前缀跨语言一致；英文维护规则标记 Session-end Task Sync 接入检测 |
| DEV-009 | 开发 | check/standardize 支持日期 schema 变体：自动识别双日期(发现时间+完成时间)与合法单日期(完成日期 6列/8列dev)，按文件实际 schema 校验，单日期好文件不再全量报表头不一致 | 2026-06-22 17:39 | 2026-06-22 17:39 | 已完成 | 新增 detect_schema/to_single_date_columns；check_text 与 analyze_standardization 增 schema 参数；check/standardize 增 --schema auto\|dual\|single(默认auto)；报告 schema 字段+单日期升级提示 |
| DEV-010 | 开发 | standardize 检测到重复 ID 时建议新增 ADJ- 记录说明旧号→新号映射，避免静默重编号导致历史引用断裂 | 2026-06-22 17:40 | 2026-06-22 17:40 | 已完成 | analyze_standardization 增 rec_dup_id_mapping；report-only 不自动改号，清理仍需用户批准；对应 standard 常见问题表既有规则，工具现主动提示 |

## 配置运维

| ID | 动作 | 事项 | 发现时间 | 完成时间 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| OPS-001 | 运维 | 配置 Stop hook 保证会话末任务同步时机 | 2026-06-22 12:50 | 2026-06-22 12:50 | 已完成 | .claude/settings.json 注册 Stop hook；hooks/tasklist_sync_reminder.sh 每会话首次停止注入 block 提醒，session_id 守卫防死循环；模拟 fresh/重复/缺 session_id 三场景通过 |
| OPS-002 | 运维 | 裁剪 .gitignore 为项目精简规则并排除 docs/discussion | 2026-06-22 13:30 | 2026-06-22 13:30 | 已完成 | 移除无关 Web 框架条目；新增 macOS/IDE/Python/密钥/日志分类；排除 docs/discussion 参考工作流分析文档不入库 |
