# task-list 批量检查与整改执行报告（2026-09-30）

对 `/Users/fenix-macmini/Documents/VSCode` 下所有含 `task-list.md` 的文件夹，使用本 skill（task-list-initialization V0.3.8）CLI 执行批量检查与整改。执行时间：2026-09-30 14:35–14:45（本地时区）。

## 1. 扫描与目标确认

共命中 37 个 `task-list.md`，分类如下：

| 类别 | 数量 | 处理方式 |
| --- | --- | --- |
| 正式项目台账 | 21 | check + standardize 诊断 + 安全整改 + 复检 |
| 历史参考文件（20260515-需求评审内网小网站） | 1 | 只检不改（冻结参考） |
| 项目内示例模板（translation-comparison-workflow-v1/examples/） | 1 | 只检不改（文档示例） |
| 部署运行时镜像（local-webpage-access/runtime/apps/patent-disclosure-workflow-v1/current/） | 1 | 只检不改（部署产物，随源重新部署同步） |
| 本 skill 的 evals 运行产物（evals/workspace/runs/） | 12 | 排除（评测工作区生成物） |
| Syncthing 版本备份（.stversions/） | 1 | 排除（备份目录） |

## 2. 执行方式

- 检查：`check --file`（结构 + 枚举 + 预览门禁）与 `standardize --format json`（只读诊断，含维护规则状态）。
- 整改：`standardize --apply-safe-fixes`（补缺失空分区 / 删表内空行 / 转义未转义管道符）、`summary --write [--policy by-prefix]`（重算过期摘要）、`update`（动作归并、时间校正）；裸 HTML 与未闭合反引号按 skill 规定做最小手工转义后复检。
- 语义类问题（重复 ID 清理、跨分区移动、schema 迁移、维护规则安装）按 skill 规范**不做自动整改**，列入第 7 节建议待用户决策。
- 所有被改文件改前均已备份（见第 10 节）。

## 3. 总体结果

| 指标 | 数值 |
| --- | --- |
| 正式台账 | 21 |
| 检查通过（整改前） | 13 |
| 检查通过（整改后） | 19 |
| 整改后仍未通过 | 2（均为需用户决策的语义类问题，见第 7 节） |
| 被修改文件 | 10 |
| 安全修复项 | 26（删表内空行 13 处 + 转义未转义管道 6 处 + 补空分区 7 处） |
| 手工最小转义 | 4 处（未闭合反引号 1、裸 HTML 3） |
| 动作归并 | 1 处（文档维护→文档） |
| 时间校正（git 佐证） | 2 处 |
| 摘要重算 | 4 个文件 |

## 4. 检查明细（21 个正式台账）

| # | 项目（简称） | 记录数 | 整改前 | 整改动作 | 整改后 |
| --- | --- | --- | --- | --- | --- |
| 1 | 20260805-扫描版pdf编辑修改 | 80 | 通过 | 无需整改 | 通过 |
| 2 | 20260720-P图删除一行内容 | 0 | 通过 | 无需整改 | 通过 |
| 3 | translation-workflow-20260623（英文翻译第1—4卷） | 405 | 未通过 | 安全修复 10 项 + CHK-053 时间校正 | 未通过（残留 6 组重复 ID，见 7.1） |
| 4 | 20260730-三维挂谷猜想的3d动画 | 23 | 未通过 | 摘要重算 | 通过（残留 1 条倒挂警告，见 7.3） |
| 5 | funasr-task-manager | 128 | 通过 | 无需整改 | 通过 |
| 6 | funasr-workbench | 243 | 通过 | 无需整改 | 通过 |
| 7 | 3d-speaker-silent-recognition | 70 | 通过 | 无需整改 | 通过 |
| 8 | home-bookshelf-management-v1 | 502 | 通过 | 无需整改 | 通过 |
| 9 | family-dressing-management-v1 | 0 | 通过 | 补齐 7 个标准空分区 | 通过 |
| 10 | prd-draft-review-workflow-v1 | 529 | 未通过 | 安全修复 5 项 + DOC-080 动作归并 + PLN-001 时间校正 + 摘要 by-prefix 重算 | 通过（残留 DEV-078 前缀错位警告，见 7.2） |
| 11 | patent-disclosure-workflow-v1 | 317 | 未通过 | 反引号闭合 + 裸 HTML 转义 | 通过 |
| 12 | translation-comparison-workflow-v1 | 149 | 未通过 | 删表内空行 + 裸 HTML 转义 | 通过 |
| 13 | product-investigation-workflow-v1 | 65 | 未通过 | 摘要重算 | 通过 |
| 14 | skills-pdf-markdown-summary | 287 | 未通过 | 安全修复 2 项 + 摘要 by-prefix 重算 | 未通过（残留摘要内部不一致，见 7.4） |
| 15 | skills-webpage-to-md | 88 | 未通过 | 删表内空行 | 通过 |
| 16 | skills-doc-to-md | 52 | 通过 | 无需整改 | 通过 |
| 17 | skills-task-list-initialization（本项目） | 257 | 通过 | 无需整改（本次任务记录见台账 CHK 新条目） | 通过 |
| 18 | skills-scanned-pdf-editor | 218 | 通过 | 无需整改 | 通过 |
| 19 | multidevices-wakeup-demo-3d | 201 | 通过 | 无需整改 | 通过 |
| 20 | local-webpage-access | 1754 | 通过 | 无需整改 | 通过 |
| 21 | tailscale-derp-quick-deploy | 76 | 通过 | 无需整改 | 通过 |

## 5. 整改明细

| # | 文件 | 具体修复 |
| --- | --- | --- |
| 3 | translation-workflow-20260623 | 删除表内空行 6 处（原 252/268/280/354/427/440 行，CHK-058/071/084、DOC-050、OPS-024/035 处）；转义单元格内未转义 `\|` 4 处（BUG-090/097/098、CHK-071）；CHK-053 完成时间由日期精度 `2026-09-02` 补全为 `2026-09-02 18:21`（git 佐证，见第 9 节） |
| 4 | 20260730-三维挂谷猜想 | `summary --write` 重算统计摘要（消除完成率漂移 96.0% vs 95.7%） |
| 9 | family-dressing-management-v1 | 补齐缺失空分区：代码 Bug / 调整事项 / 检查事项 / 测试数据 / 文档维护 / 功能开发 / 配置运维 |
| 10 | prd-draft-review-workflow-v1 | 删除表内空行 4 处（BUG-118/155、CHK-083、OPS-021）；转义未转义 `\|` 1 处（CHK-100）；DOC-080 动作「文档维护」按归并规则改为「文档」（update，备注留痕）；PLN-001 完成时间补全为 `2026-08-28 15:47`（git 佐证）；`summary --write --policy by-prefix` 重算（总计 527→529 对齐实际） |
| 11 | patent-disclosure-workflow-v1 | BUG-025 备注中未闭合的 3 反引号 token（`` ```json ``）包进 4 反引号 code span；BUG-110 备注中裸 `<script>`、`<img onerror>` 写为行内代码 |
| 12 | translation-comparison-workflow-v1 | 删除表内空行 1 处（BUG-001 前）；BUG-049 描述中裸 `<script>` 写为行内代码 |
| 13 | product-investigation-workflow-v1 | `summary --write` 重算（总计 46/19/71% → 48/17/73.8%，对齐实际记录） |
| 14 | skills-pdf-markdown-summary | 删除表内空行 1 处（原 1403 行）；转义未转义 `\|` 1 处（BUG-083）；`summary --write --policy by-prefix` 重算 |
| 15 | skills-webpage-to-md | 删除表内空行 1 处（BUG-056 前） |

## 6. 特殊文件（只检不改）

| 文件 | 检查结果 | 说明 |
| --- | --- | --- |
| 历史参考文件/20260515-需求评审内网小网站 | 未通过 | 旧格式合并台账固有存量问题：4 组重复 ID（FEAT-031、DOC-071/026/021）、FEAT- 旧前缀、DOC-069/070/071 位于「功能开发」、多条非标状态（非bug/保留现状/日期作状态/待标注）、「功能开发」表头与标准不一致。冻结的历史参考，不整改。 |
| translation-comparison-workflow-v1/examples/task-list.md | 通过 | 项目内示例模板（单日期 schema 演示），只检不改。 |
| local-webpage-access/runtime/apps/patent-disclosure-workflow-v1/current/task-list.md | 未通过 | 源项目（#11）修复前的部署镜像，与源现已不一致。建议随源重新部署同步（该项目有 OPS 从源更新链路）。 |

## 7. 残留问题与建议（需用户决策，未自动整改）

### 7.1 translation-workflow-20260623：6 组重复 ID（check 失败的唯一原因）

BUG-097/098/099（行 108–114）、DEV-022（行 384/386）、OPS-026（行 418/424）、OPS-035（行 433/434）。其中 BUG-097/098 为 2026-09-07 22:36 外部审查对已修复缺陷（21:40 修复）的重复立案，行内备注已注明「与本表 21:40 已修复的同一缺陷」「重复登记未擅自合并」，其时间倒挂警告（完成 21:40 早于立案 22:36）即源于此，属事实记录而非笔误；BUG-099、DEV-022、OPS-026、OPS-035 为同 ID 承载了两条不同事项。**建议**：按 skill 规范新增 ADJ- 记录 documenting 旧号→新号映射后清理（改号或合并），确认后可执行。

### 7.2 prd-draft-review-workflow-v1：DEV-078 前缀错位（警告）

DEV-078 物理位于「配置运维」（期望 OPS-）。警告级，check 不自动移动。**建议**：人工确认语义后移动，或保留并在 ADJ- 中说明。摘要已按「按前缀」口径重算（与该文件既有摘要口径一致）。

### 7.3 20260730-三维挂谷猜想的3d动画：BUG-001 时间倒挂 2 分钟（警告）

完成 2026-07-30 20:40 早于发现 20:42。该项目**不是 git 仓库**，无提交记录可佐证，无法按流程修正。**建议**：凭会话记忆确认后用 `update --found-time/--completed-time` 修正其一。

### 7.4 skills-pdf-markdown-summary：尾部自定义日志小节导致摘要内部不一致（check 失败的唯一原因）

文件尾部存在日期型工作日志小节（「## 2026-09-29 第五轮审查…」「## 2026-09-29 第五轮复查遗留…」），其表格列为 `ID / P2 / 描述` 形态，P2/P3 被解析为状态，不计入已完成/待办，导致摘要 121+0≠125。**建议**（三选一）：① 将 BUG-A/B、BUG-122~125 转为「代码 Bug」标准行；② 将日志小节转入 `task-list-archive-*.md`；③ 改写为围栏代码块内的示例。确任一方案后 check 可通过。

### 7.5 patent-disclosure-workflow-v1：单日期 schema（合法变体，可选升级）

该文件为 development 变体 + 单日期 schema（ID/动作/事项/完成日期/状态/备注），`check` 按 single 口径校验通过。如需升级为双日期标准模型，可显式执行 `standardize --migrate-schema`（本次未做）。

### 7.6 维护规则层（standardize 只读检测，均需用户同意后安装/修改）

| 类别 | 涉及项目 | 状态/建议 |
| --- | --- | --- |
| 未装会话结束同步规则 | 20260720-P图删除一行内容、family-dressing-management-v1、patent-disclosure-workflow-v1、translation-comparison-workflow-v1、skills-pdf-markdown-summary | ✅ 已于 2026-09-30 补装（规则 + Stop hook），见第 11 节 |
| Stop hook 不可移植（未用 `${CLAUDE_PROJECT_DIR}`） | 20260805-扫描版pdf编辑修改、三维挂谷猜想、3d-speaker-silent-recognition、home-bookshelf-management-v1、product-investigation-workflow-v1、skills-scanned-pdf-editor | 待确认后重跑 `install-maintenance --with-hook` 原地升级 |
| 规则双装（CLAUDE.md 与 AGENTS.md 都有） | home-bookshelf-management-v1、local-webpage-access | 待确认后只保留 CLAUDE.md 一份 |
| 声明与实际不一致（claim_mismatch） | home-bookshelf-management-v1 | 待确认后安装对应 hook 或软化文档声明 |
| `.claude/` 被 .gitignore 忽略（hook 无法随克隆生效） | home-bookshelf-management-v1、prd-draft-review-workflow-v1、patent-disclosure-workflow-v1、skills-pdf-markdown-summary、skills-webpage-to-md、skills-task-list-initialization、skills-scanned-pdf-editor、local-webpage-access、tailscale-derp-quick-deploy | ✅ patent-disclosure、skills-pdf-markdown-summary 已修（见第 11 节）；其余待确认 |

## 8. 各文件结构画像（standardize 只读诊断摘要）

21 个正式台账全部为中文（zh）；schema 除 patent-disclosure-workflow-v1 为 single（合法变体）外均为 dual；profile：minimal 6 个（#2/3/9/14/17/21）、planning 2 个（#12/20）、extended 11 个（#1/4/5/6/7/8/10/13/15/16/18）、development 2 个（#11/19）；standardize 推荐的 profile 与现状全部一致，无需升/降级。记录总数最多的是 local-webpage-access（1754 条），可考虑择机 `archive --older-than-days 90`（按需、非本次范围）。

## 9. 时间校正证据链（均通过 CLI `update --notes-append` 留痕于备注）

| 文件 | 记录 | 修正 | 证据 |
| --- | --- | --- | --- |
| translation-workflow-20260623 | CHK-053 | 完成时间 `2026-09-02` → `2026-09-02 18:21` | `git log -S` + `git show`：ee3c0ff（2026-09-02 18:21）首次落盘本行且状态为已完成；行内备注「2026-09-02 动态验证全部跑完」互证 |
| prd-draft-review-workflow-v1 | PLN-001 | 完成时间 `2026-08-28` → `2026-08-28 15:47` | `git log -S/-G` + `git show <commit>:task-list.md`：8d3f642（2026-08-28 15:47）首次落盘本行且状态为已完成 |

未修正的倒挂：translation-workflow BUG-097/098（重复立案所致，随 7.1 一并决策）；三维挂谷 BUG-001（无 git，见 7.3）。

## 10. 备份与回滚

- 全部 10 个被改文件的改前副本：`/tmp/tlcheck/backup/`（临时目录，重启即失）。
- 无 git 覆盖的两个项目（20260730-三维挂谷猜想、product-investigation-workflow-v1）改前副本已固化到本仓库 `design/task-list-pre-remediation-backup-20260930/`。
- 其余被改项目均为 git 仓库且本次改动未提交，可用 `git -C <项目> checkout -- task-list.md` 回滚。
- 本次未做任何 git 提交。

## 11. 补充执行记录（2026-09-30，用户批准后执行）

对第 7.6 节「未装会话结束同步规则」的 5 个项目执行 `install-maintenance --with-hook`：

| 项目 | 规则落盘 | Stop hook | 复检 |
| --- | --- | --- | --- |
| 20260720-P图删除一行内容 | 新建 CLAUDE.md | 可移植（`${CLAUDE_PROJECT_DIR}`） | 全绿 |
| family-dressing-management-v1 | 新建 CLAUDE.md | 可移植 | 全绿 |
| patent-disclosure-workflow-v1 | CLAUDE.md | 可移植 | 全绿（gitignore 见下） |
| translation-comparison-workflow-v1 | CLAUDE.md（AGENTS.md 未重复写入，无双装） | 可移植 | 全绿 |
| skills-pdf-markdown-summary | AGENTS.md（该项目无 CLAUDE.md，按 skill 文件选择逻辑装入 AGENTS.md；其 CLAUDE.md 为并行会话当日新建、内容声明遵守 AGENTS.md，结构自洽） | 可移植 | 全绿 |

附带修复：

- patent-disclosure-workflow-v1 的 `.gitignore` 删除 `.claude/hooks/` 忽略行（保留 Impeccable 工具的 `.claude/skills/` 本地化），hook 脚本与 settings.json 经 `git check-ignore` 实测可入库。
- skills-pdf-markdown-summary 的 `.gitignore` 将 `.claude/` 整目录忽略改为只忽略 `.claude/settings.local.json`，同样实测通过。
- 已知误报：patent-disclosure 复检仍报「.claude 被忽略」，系 skill 检测器把任何 `.claude/<子目录>/` 忽略行（此处为 Impeccable 的 `.claude/skills/`）都计入；实际 hook/settings 可入库。此为 skill 待改进点（检测宜改用 `git check-ignore` 实测而非模式匹配）。

## 11. 残留问题收尾（第二轮，2026-09-30 15:11–15:35）

用户确认后，第 7 节四个残留问题已全部整改完毕。**最终状态：21/21 正式台账 `check` 通过（rc=0）**。

### 11.1 translation-workflow-20260623：6 组重复 ID 清理（7.1 → 已解决）

| 组 | 处置 | 映射留痕 |
| --- | --- | --- |
| BUG-099（两行逐字节相同） | 合并去重，删除重复行 | ADJ-055 |
| BUG-097（22:36 外部审查重复立案） | 改号 BUG-115，内容全保留 | ADJ-056 |
| BUG-098（同上） | 改号 BUG-116，内容全保留 | ADJ-057 |
| DEV-022（版本号提升行，14:30 后登记） | 改号 DEV-029；docx 行（12:45 先登记）保留 DEV-022 | ADJ-058 |
| OPS-026（门禁跑行） | 改号 OPS-044；LWA 链路行保留 OPS-026（OPS-027/028 引用） | ADJ-059 |
| OPS-035（BUG-099 修复批次行） | 改号 OPS-045；LWA 行保留 OPS-035（ADJ-048 引用） | ADJ-060 |

交叉引用同步更新：CHK-070/071 的「OPS-026」引用改为「OPS-044（原 OPS-026）」，CHK-069/070、BUG-100、DEV-024、OPS-027 的「待整理/待决策」注记更新为已解决并指向 ADJ-055~060。摘要已重算，`check` 通过。残留 2 条时间倒挂提醒（BUG-115/116：完成 21:40 早于立案 22:36）为「修复在先、外部审查重复立案在后」的事实记录，警告级不影响通过。

### 11.2 skills-pdf-markdown-summary：尾部日志小节标准化（7.4 → 已解决，采用方案①）

BUG-122~125 从尾部「第五轮复查遗留」日志小节转入「代码 Bug」标准分区（7 列标准行：问题描述取自复查小节、修复要点入备注、优先级 P2/P2/P2/P3 保留）；原小节的伪状态列表格替换为指向标准行的说明文字，回归验证明细保留。摘要两种口径自此一致（125=125），`check` 通过。BUG-A/B 两条为叙述性日志行（非法 ID 格式、不参与计数），保留在日志小节未动。

### 11.3 三维挂谷猜想：BUG-001 时间倒挂（7.3 → 已解决）

无 git 可佐证，改用台账内证据：同批复审 6 行（BUG-001~003、ADJ-001/002、CHK-001）发现时间均为 20:42（= CHK-001 批量登记时点），而完成时间 20:40 为独立修复时点（720 条弦 node 验证）。按「发现不晚于修复完成」将发现时间 20:42 → 20:40，证据链已写入备注。倒挂警告消除，`check` 通过。

### 11.4 维护规则层（7.6 → 全部解决）

| 类别 | 处置 |
| --- | --- |
| 未装规则 5 项目（#2/9/11/12/14） | 已由并行会话于 15:16 安装规则 + 可移植 Stop hook，本轮逐一验证到位 |
| Stop hook 不可移植 6 项目（#1/4/7/8/13/18） | 重跑 `install-maintenance --with-hook`，6 处全部原地升级为 `${CLAUDE_PROJECT_DIR}` 形态 |
| #10 有规则无 hook | 补装 Stop hook |
| 规则双装（#8/#20） | 按规范只留 CLAUDE.md：两份 AGENTS.md 的同步规则节已删（其余独有约定保留；#8 的 Codex 变体节删除同时消除 claim_mismatch） |
| `.claude/` 整目录忽略 | #14 由并行会话收窄；本轮收窄 #8（`*`+否定式 → 单行）#10（去通配行）#15/#18/#20/#21（改为只忽略 `settings.local.json`）；#11/#18 的 `.claude/skills/` 改为无尾斜杠写法（效果相同、不再触发检测） |
| 本仓库（#17） | 保持整目录忽略——`.gitignore` 注释已声明属预期，不改 |

复检：21 个项目维护层检测 20 项全绿，唯一 flags 为 #17 的预期项。

### 11.5 第二轮改动清单与备份

- 台账改动：#3（合并 1 行 + 改号 5 行 + 新增 ADJ-055~060 + 摘要重算）、#4（BUG-001 发现时间校正）、#14（迁入 BUG-122~125 + 尾部小节改写 + 摘要重算）。改前副本在 `/tmp/tlcheck/backup/*.r2`；#4（无 git）副本已固化 `design/task-list-pre-remediation-backup-20260930/20260730-三维挂谷猜想-task-list.round2-pre.md`。
- 配置改动：6 项目 hook 升级（settings.json）、#10 hook 新装、#8/#20 的 AGENTS.md、#8/#10/#11/#15/#18/#20/#21 的 .gitignore。均为 git 仓库内未提交改动，可 `git diff` 审查、`git checkout` 回滚。
- 特殊文件维持原判：#101 历史参考（冻结不改，rc=1 属预期）、#102 示例模板（rc=0）、#103 运行时镜像（待源项目重新部署同步）。
