# 最新 issue 与修复复核（2026-10-06）

结论：GitHub #1、#2 的本地修复正确；同批 V0.3.9 改动仍有 BUG-094～BUG-101 八项未修复问题，建议处理主要问题后再发布整个批次。

## 范围与版本

- 通过 GitHub API 查询本仓全部 issue，当前只有 [#1](https://github.com/wangminle/skills-task-list-initialization/issues/1) 和 [#2](https://github.com/wangminle/skills-task-list-initialization/issues/2)，均于 2026-10-06 创建、状态 OPEN、无评论；没有 PR。
- 远端 main 与本地 HEAD 均为 `8f0a0cdc499ec584d34b3d00d3cd6b1393c5b2be`（V0.3.8）。修复存在于未提交工作区；VERSION 已标 V0.3.9，不代表远端已经发布。
- 扩展复核本地台账最新八项缺陷，以及 DOC-040、TST-026；不重新审查全部历史已关闭记录。
- 本次没有修改实现代码、提交、推送、关闭 issue 或同步安装副本。

## 两项 GitHub 修复

| Issue | 修复位置 | 结论与验证 |
| --- | --- | --- |
| #1 新增章节标题紧贴表格 | `_tasklist/renderer.py:89`、`:377` | 正确。新增 `render_section_blocks` 用两个换行拼接，模板与补章节共用；原始 CLI 复现和新增回归通过。临时目录另测中/英、有/无摘要、minimal/extended 共 8 种真实写盘组合，检查所有新增标题前空行、摘要前插入、重复运行幂等，均通过。 |
| #2 建议输出双短横线 | `_tasklist/validator.py:588` | 正确。报告渲染器保留已带 `- ` 的项，仅为无前缀项补前缀；中英文逆序章节报告均无 `- - `，也兼容其他已带前缀的建议文案。locales 中仍保留前缀不构成漏修。 |

两条回归位于 `tests/scripts/test_cli_standardize.py:389`、`:414`。目前是中文 CLI 回归；英文及真实写盘边界由本次临时探针验证，后续可将必要的矩阵案例纳入长期回归。

## 仍需继续修复的事项

| 优先级 | 记录 | 当前问题、影响与建议 |
| --- | --- | --- |
| P1 | BUG-094 | `cli.py:285-298`、`:520-526`：门禁按原始日期精度判断，落盘却补 `00:00`。实际 add 发现时间 `2026-09-30 15:00`、完成日期 `2026-09-30` 成功后，落盘完成时间变为 `00:00`，check 报倒挂；再仅追加备注也被拒绝。应在校验合法日期后保持显式 date-only 的日精度，让门禁、写盘、读侧一致。 |
| P1 | BUG-095 | `fleet.py:178`、`cli.py:1602`：fleet 逐文件修复持锁处缺少异常隔离，单文件 LockTimeout 会终止整个批次。应保存该文件失败信息并继续巡检其他文件，最后统一返回失败退出码。读取/写入期间的 OSError 也应纳入逐文件处理。 |
| P1（兼容性） | BUG-096 | `fleet.py:123` 使用 Python 3.9 才有的 `Path.is_relative_to`，违反 Python 3.8+ 支持承诺。改用 `relative_to` 加 `except ValueError`，并增加最低版本验证。当前主机没有 Python 3.8，本次不宣称在 3.8 上实跑通过。 |
| P2 | BUG-097 | `validator.py:118` 仅在 headers 为空时拦截。自定义表头 `ID / 问题 / 结论` 加行 `DEV-777 / 修复 / 示例`，check 返回 0；在标准功能分区存在时，`summary --policy by-prefix --write` 写出功能开发总数 1、已完成 0、待办 0，污染摘要。必须校验“受支持的记录 schema”，不能把首列为 ID 等同于合法表头。 |
| P2 | BUG-098 | `cli.py:1584-1594`、`fleet.py:87`、`:236`：零文件 JSON 输出文本、报告缺用户排除项、报告路径错误裸 traceback、os.walk 默认吞目录读取错误。需保持机器输出契约并显式报告扫描不完整，避免自动化把未扫描当成全通过。 |
| P2 | BUG-099 | `repository.py:94-96`、`cli.py:1605`：不存在的目标在命令校验前被建父目录并遗留 lock；创建 lock 的 OSError 未本地化处理，超时信息显示内部 lock 路径。存在性检查应先于无意义锁创建，init 保留创建目录能力；正常 sidecar 必须保留以防竞态，可增加忽略说明。 |
| P2/P3 | BUG-100 | `validator.py:118-127`：headerless 分支直接 continue，未登记 ID/引用。探针含标准 BUG-001 与自定义表重复 BUG-001，未报重复；表中独有 DEV-777 被引用时反报悬空；自定义表中的 BUG-01 被漏过。应先统一收集身份与引用，再按 schema 校验；文案需要按实际计数口径说明。 |
| P3 | BUG-101 | `fleet.py:247`：报告直接写入目录路径，路径含竖线时破坏表格列。需统一转义。`*/examples` 不匹配根级 examples 则是已文档化的 fnmatch 语义，不宜改成另一套语义；帮助文本明确推荐裸名 examples 用于任意层级即可。 |

### 对原台账建议的两项校正

1. BUG-097 的“非注册分区里出现任务 ID 一律报错”建议过宽。CLI 参考与 BUG-076 既有测试允许合法自定义记录分区；正确修法应验证完整受支持表头，保留这一兼容面。
2. BUG-101 的排除模式行为属于既定规则，主要整改帮助文本；路径竖线未转义属于实际渲染缺陷。

## 文档与测试缺口

- DOC-040 仍未收口：`task-list-standard.md:18`、`:95`、`:110` 未说明混合日期精度语义；README 中“剩余的倒挂警告都是真问题”仍会被 BUG-094 反例推翻。
- TST-026 仍未收口。特别是 `test_cli_fleet.py:170`、`:189` 两项写路径测试只验证写入成功与跨日拒绝，没有断言落盘仍为日精度、写后 check 无倒挂、后续普通 update 可用，因此全绿仍漏掉 BUG-094。
- README 当前测试数 305 已落后于工作区实际 307（两项 GitHub 回归新增），发布时同步即可。
- 整个技能目录 Ruff 仍有两条既有问题：`evals/run-evals.py:34` 未使用 re（F401），`:68` 未使用 original（F841）；本次 issue 修复没有引入它们。

## 本次验证

| 检查 | 结果 |
| --- | --- |
| Python 3.13.13：`python3 -m unittest discover -s tests/scripts -p 'test_*.py'` | 307 测试通过，无失败或跳过 |
| Python 3.9.6：`/usr/bin/python3 -m unittest discover -s tests/scripts -p 'test_*.py'` | 307 测试通过，无失败或跳过 |
| `ruff check skills/task-list-initialization/scripts tests/scripts` | 通过 |
| `ruff check skills/task-list-initialization tests` | 两条既有评测脚本问题，退出码 1 |
| `git diff --check` | 通过 |
| 根台账 `check` | 通过 |
| GitHub issue 原始场景与额外矩阵 | 两项修复通过 |
| 两项 issue 回归红绿验证（独立临时快照） | 当前实现 2 测试通过；仅在临时快照换回 HEAD 的 renderer/validator 旧实现后，同两测试均失败：标题前缺空行、建议出现双短横线 |
| BUG-094/097/100 临时输入探针 | 问题仍可复现 |
| BUG-095 锁竞争 | 等待 10 秒后 LockTimeout traceback，退出 1、stdout 为空，之前已扫结果丢失 |
| BUG-098 自动化输出与权限 | 空树 JSON 解析失败、用户 exclude 未入报告、报告父路径为文件时报 FileExistsError；chmod 000 根目录仍返回 0、“未找到”、stderr 为空 |
| BUG-099 缺失目标与权限 | 缺失目标 add 后残留父目录和 lock；chmod 555 目录创建 lock 时 PermissionError traceback |
| BUG-101 报告与 glob | 路径 a\|b/task-list.md 未转义，报告列错位；根级/嵌套 glob 行为符合现有文档 |

最低支持版本 Python 3.8 与原 issue 所述 Windows 11 未在本次运行环境实际测试。建议按 BUG-094/095/096 → BUG-097/098/099/100 → BUG-101 的顺序整改，并在每项整改时把本次失败输入固化为有意义的回归。
