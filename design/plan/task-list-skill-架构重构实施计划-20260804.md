# Task List Skill 架构重构实施计划（iteration-2）

| 项 | 值 |
| --- | --- |
| 文档性质 | 需求规格 + 实施计划（下一阶段开发的唯一依据） |
| 文档状态 | 已通过三方独立评审；全部事实论断已在本机复现 |
| 起始基线 | `V0.3.0-Build0211-20260804`；98 个单元测试通过；`ruff check` 164 项 |
| 关联台账 | 待修复：`BUG-026`（P0 迁移语义）、`BUG-027`（P1 状态列位置猜测）、`BUG-028`（P2 缺失文件堆栈）；已完成：`CHK-011`、`CHK-012`、`CHK-013`（三轮评估与复现）、`DOC-026`（本文档） |
| 目标交付 | `V0.4.0`：历史台账可安全读写、统计口径可解释、Skill 成熟度可对外宣称 |

> **For Codex / Claude：** 实施本计划必须使用 `executing-plans`；每个任务先写失败测试并确认失败原因，再做最小实现，然后运行定向测试 + 全量回归，最后单独提交。涉及数据语义与文件安全的任务（A2、A3、A5、B1）完成后必须单独代码审查，不与文档调整合并审查。

---

## 0. 文档定位与使用方式

本文档同时承担两个角色，读者按需求进入：

- **需求侧**：§2 缺陷台账（`DEF-xx`）给出问题与证据，§3 需求规格（`REQ-xx`）给出可验证的验收条件，§4 记录已定的设计决策。验收以 §3 和 §8 为准。
- **实施侧**：§7 把需求切成四个阶段、共 17 个任务（A1–A5、B1–B2、C1–C6、D1–D4），每个任务含「需求映射 / 文件 / 步骤 / 验收命令 / 回滚点」。

约定：文中 `$CLI` 指 `skills/task-list-initialization/scripts/task_list_cli.py`；「四份历史样本」指 `design/discussion/{1-skills-pdf-markdown,2-prd-workflow,3-translation-workflow,4-patent-workflow}/task-list(*).md`。

---

## 1. 结论与本版相对初版的调整

### 1.1 保持不变的三条判断（三方一致）

1. **不拆成多个可安装 Skill。** 初始化、追加、更新、校验、标准化、迁移、归档是同一个领域对象的生命周期，拆开会让 agent 面临选择成本，收益为负。
2. **保留现有 CLI 设计。** 诊断优先、维护规则 opt-in、双语、dry-run、写后校验这几条设计是正确的，不动。
3. **重构底层三个核心模型。** 日期语义、schema 识别、统计口径这三处是所有 P0/P1 缺陷的共同根因，必须先建立显式领域模型，而不是搬文件。

### 1.2 相对初版的六处调整

| 调整点 | 初版方案 | 本版方案 | 依据 |
| --- | --- | --- | --- |
| 执行顺序 | 先建模分层，再修数据语义 | **先修数据语义（阶段 A），分层放最后（阶段 C）** | 三方一致：模型层修复成本低、直接消除数据风险，不应被分层工程量拖住 |
| `repository.py` 范围 | 完整多文件事务边界 | **原子写 + 写前备份 + 多文件「全部预校验后逐个提交、失败按备份恢复」** | 评审 A 保留意见；单机 CLI 追求完整事务收益有限 |
| 摘要口径 | 引入 `by-prefix` 并可能改默认 | **默认 `by-section`；`by-prefix` 可选；两种口径冲突时拒绝静默写入** | 评审 A：新规范下两种口径本应一致，差异只在历史错放时出现 |
| `SKILL.md` 精简 | 与其他任务同级 | **降为 P3，阶段 D 可选项** | 评审 B：现有 175 行以决策流程和安全边界为主，质量尚可 |
| fixture 来源 | `docs/discussion/*` | **`design/discussion/*`（该目录已 `.gitignore`，fixture 必须自包含入库）** | 目录已改名；且 CI 不能依赖仅本地留存的目录 |
| 模块拆分粒度 | 9 模块一次到位 | **分批：修复所需的 `schemas` / `migration` / `summary` / `repository` 随阶段 A/B 先落地，纯分层的 `domain` / `parser` / `renderer` / `validator` / `maintenance` / `cli` 留到阶段 C** | 评审 A/B：一次性拆分风险高、审查困难 |

### 1.3 本版新增的两条发现

复现过程中新定位到两个初版报告未收敛的问题，已纳入台账：

- **`DEF-03`（P1）**：摘要与统计按 `cells[-2]` 位置猜测状态列，不按表头字段索引。这是专利样本「代码 Bug 已完成 114 → 111」的真实根因——与统计口径无关，是三行未转义竖线导致的列错位。评审 B 把这个差异归因于口径改变，归因有误。
- **`DEF-10`（P2）**：`check` / `sections` / `list` / `summary` / `standardize` 对不存在的文件抛出原始 Python `Traceback`，而非本地化错误信息。

---

## 2. 缺陷台账（全部已在本机复现）

| 编号 | 级别 | 缺陷 | 代码位置 | 需求 |
| --- | --- | --- | --- | --- |
| `DEF-01` | **P0** | 迁移制造历史事实：补造 `00:00`、把发现日期复制为完成时间，且迁移后 `check` 通过使损坏不可见 | `_lib.py:673-687`、`_lib.py:1727-1752` | `REQ-01` `REQ-02` `REQ-03` |
| `DEF-02` | **P0** | 表头兼容口径三处不一致：`check` / `add` 拒绝真实 `发现日期` 表头，`--migrate-schema` 却接受；四份历史样本 `check` 全部失败 | `_lib.py:90`、`_lib.py:1704` | `REQ-04` `REQ-05` |
| `DEF-03` | **P1** | 统计按 `cells[-2]` 猜状态列位置，列数不符时静默错算并污染状态分布 | `_lib.py:2033-2034` | `REQ-06` |
| `DEF-04` | **P1** | 摘要固定按物理章节汇总，与历史文件的 ID 前缀逻辑口径冲突，`summary --write` 静默改写正确摘要 | `_lib.py:2017-2036` | `REQ-07` `REQ-08` |
| `DEF-05` | **P1** | Skill benchmark 不可信：声明 3 次实为 1 次、模型名与路径为占位符、token / tool_call 全零、`with_skill` 转录仅一次 CLI 调用 | 评测产物（已删除，经 `CHK-012` 从废纸篓复核） | `REQ-09` |
| `DEF-06` | **P1** | `evals.json` 6 个 eval 全部 `"files": []`，但 4 个 eval 的 prompt 假设「task-list.md 已存在」 | `evals/evals.json` | `REQ-10` |
| `DEF-07` | **P1** | 只拆文件未分层：`_lib.py` 2532 行 / 89 个 `def`，入口星号导入，`ruff` 164 项，单个测试文件 1968 行 | `_tasklist/_lib.py`、`task_list_cli.py` | `REQ-11` |
| `DEF-08` | P2 | `-` 同时是缺失值占位符和合法业务状态：`add --status -` 写入成功且 `check` 静默 | `_locale.py:80`、`_locale.py:158` | `REQ-12` |
| `DEF-09` | P2 | 写入非原子：仅覆盖「写后 check 失败」一条回滚路径；`archive` 写 2 文件、`install-maintenance` 写 3 文件均无恢复；全库无 `os.replace` / `tempfile` / 备份 | 12 处 `write_text` 调用 | `REQ-13` |
| `DEF-10` | P2 | 5 个读命令对缺失文件抛原始 `Traceback` | `_lib.py` 各 `command_*` | `REQ-14` |
| `DEF-11` | P3 | 完成率 `round()` 取整与历史文件的一位小数不一致（`95.5%` → `95%`） | `_lib.py:2041` | `REQ-15` |

### DEF-01（P0）迁移制造历史事实

**复现**（真实 Bug 分区表头，取自四份历史样本共有形态）：

```bash
printf '# 测试台账\n\n## 代码 Bug\n\n| ID | 动作 | 问题描述 | 发现日期 | 状态 | 备注 |\n| --- | --- | --- | --- | --- | --- |\n| BUG-001 | 修复 | 已修示例 | 2026-01-05 | 已修复 | - |\n| BUG-002 | 修复 | 未修示例 | 2026-01-06 | 待修复 | - |\n' > real_found.md
python3 $CLI standardize --file real_found.md --migrate-schema
```

**迁移结果：**

```text
| ID | 动作 | 问题描述 | 发现时间          | 完成时间          | 状态   | 备注 |
| BUG-001 | 修复 | 已修示例 | 2026-01-05 00:00 | 2026-01-05 00:00 | 已修复 | -   |
| BUG-002 | 修复 | 未修示例 | 2026-01-06 00:00 | -                | 待修复 | -   |
```

三重危害，需分别修复：

1. **补造分钟精度**（两行都中招）：`legacy_time()` 把 `2026-01-05` 补成 `2026-01-05 00:00`，把「日精度事实」伪装成「分精度事实」。
2. **跨语义复制**（仅已完成记录）：`legacy_completed_time()` 在状态属于完成态时，把**发现日期**原值复制进完成时间。未完成记录的完成时间保持 `-`，未被复制——初版报告「同时写入两列」的表述对未完成态略超范围，但对完成态完全成立，而历史样本恰以完成态为主（专利样本 114 条 Bug 全为完成态）。
3. **损坏不可见**：迁移后 `check` 输出「检查通过」。工具亲手制造的伪造数据，通过了工具自己的校验。

**语义依据：** `design/discussion/` 下三份原始结构说明明确记载——Bug 分区的旧日期列语义是**发现日期**，其他分区是**完成日期**。因此对 Bug 记录，当前迁移凭空制造了「完成于某日 00:00」这一不存在的事实。

### DEF-02（P0）表头兼容口径三处不一致

同一个真实 `发现日期` 表头，三条代码路径给出三种答案：

| 路径 | 行为 | 输出 |
| --- | --- | --- |
| `check --file real_found.md` | **拒绝** | `表头与标准不一致：代码 Bug` |
| `check --schema single` | **拒绝** | `表头与标准不一致：代码 Bug` |
| `add` | **拒绝** | 同上 |
| `standardize --migrate-schema` | **接受并迁移** | `is_supported_legacy_header()` 认 `发现日期` 别名（`_lib.py:90`、`_locale.py:221`） |

**后果一：四份真实历史台账 `check` 全部失败。**

```text
task-list(pdf-markdown).md   表头与标准不一致：代码 Bug
task-list(prd-workflow).md   重复章节：文档维护 出现 2 次
task-list(translation).md    表头与标准不一致：代码 Bug
task-list(patent).md         表头与标准不一致：代码 Bug
```

（`prd-workflow` 先报出重复章节，属另一类真实问题；其 Bug 分区同样是 `发现日期`。）

**后果二：报错文案把用户直接送进 `DEF-01`。** `add` 的拒绝消息（`_locale.py:303`）实测输出：

```text
分区「代码 Bug」表头与标准 schema 不符（6 列），拒绝写入以免数据落入错误列。
请手工核对列顺序后再 add；若确为受支持的 6/8 列单日期旧 schema，可运行 standardize --migrate-schema。
```

`发现日期` 表头**恰好**是 migrate 支持的 6 列单日期旧 schema，于是用户照提示运行 migrate，直接触发 `DEF-01` 的日期伪造。`add` 拒绝它、`migrate` 接受它、消息又把用户从前者推向后者——这条链路必须一起修，只修一端会留下更隐蔽的坑。

附带问题：`check` 的 `header_mismatch`（`_locale.py:256`）只输出「表头与标准不一致：代码 Bug」，不给列数、不给原因、不给下一步，与 `add` 的详细消息不对等。

**后果三：`开始日期` / `规划日期` 的拒绝理由是错的。** 四份样本共出现 `发现日期` 9 次、`完成日期` 30 次、`开始日期` 3 次、`规划日期` 3 次、`预计时间` 3 次。对 `开始日期` 分区，`migrate` 报：

```text
无法迁移：分区「开发事项」表头（6 列）既不是标准双日期 schema，也不是受支持的 6/8 列单日期旧 schema。
```

它**是**合法的单日期旧 schema，只是日期语义（started）无法映射到双日期模型。理由说错会让用户误以为文件损坏而去手改列顺序——而手改列顺序恰恰是最危险的操作。

### DEF-03（P1）统计按位置猜状态列

`compute_summary_rows()` 用 `cells[-2]` 取状态：

```python
done = sum(1 for cells in section_records if len(cells) >= 2 and cells[-2] in locale.completed_statuses)
```

专利样本 114 条 Bug 中，3 条备注含未转义竖线，被解析成 7 或 8 个单元格，`cells[-2]` 于是落在备注碎片上：

| 行号 | 单元格数 | `cells[-2]` 实际取到 |
| --- | --- | --- |
| 18 | 8 | `'---'` |
| 107 | 8 | `''` |
| 122 | 7 | `'marked 解析前先用 escapeRawHtml() 转义 < > &，使内嵌 <script>'` |

按表头字段索引取状态：114 条全部为完成态（110 `已修复` + 4 `已完成`）。按 `cells[-2]`：111 条。**这 3 条就是「Bug 已完成 114 → 111」的全部来源，与统计口径无关。** 同样的碎片还会出现在 `summary` 的状态分布输出里，把备注文本当成状态名打印。

### DEF-04（P1）摘要口径固定按物理章节

专利样本存在 3 条前缀与章节错位的记录：`DEV-074`、`DEV-075`、`DEV-076` 物理上位于「检查事项」分区。两种口径因此分叉：

| 分类 | 文件自带摘要（前缀口径） | CLI 计算（章节口径） |
| --- | --- | --- |
| 代码 Bug | 114 / 114 / 0 / 100% | 114 / **111** / 0 / **97%** ← `DEF-03` 所致 |
| 开发事项 | **85** / 85 / 0 / 100% | **82** / 82 / 0 / 100% |
| 检查事项 | **27** / 27 / 0 / 100% | **30** / 30 / 0 / 100% |
| 文档事项 | 22 / 21 / 1 / **95.5%** | 22 / 21 / 1 / **95%** ← `DEF-11` 所致 |

专利项目的结构说明文档明确写「采用逻辑分类口径（按 ID 前缀），而不是按物理章节行数汇总」。当前实现固定按章节，于是：`check` 把正确摘要报为漂移，`summary --write` 会把它改写成章节口径——**用户运行一条看起来无害的重算命令，就丢失了原始统计语义**。

缓和事实（评审 A）：在本 Skill 推荐的新 schema 下，记录按前缀放入对应分区，两种口径本该一致，差异只在历史文件错放时出现。因此正确解法不是改默认口径，而是**默认按章节 + 可选按前缀 + 检测到错位时拒绝静默写入**。

### DEF-05 / DEF-06（P1）评测体系不可信

`CHK-012` 从废纸篓找回已删除的评测 workspace 逐项复核：`runs_per_configuration: 3`，但 12 条记录全部 `run_number: 1`；模型名为 `<model-name>`、skill 路径为 `<path-to-skill>`；`tokens` 与 `tool_calls` 全为 `0`；`with_skill` 转录内容是一次 CLI 调用，不是 agent 运行。因此 README 曾引用的「100% vs 13%」是脚本场景对比，**不构成 Skill 触发或 agent 行为的证据，不能作为发布依据**。

补充缺陷：`evals.json` 6 个 eval 全部 `"files": []`，但 eval 2 / 3 / 4 / 5 的 prompt 都以「task-list.md 已存在」为前提。评测运行时文件不存在，被测 agent 只能自行编造前置状态，评分因此不可比。

### DEF-07（P1）只拆文件未分层

| 指标 | 实测 |
| --- | --- |
| `_tasklist/_lib.py` | 2532 行，89 个 `def` |
| `task_list_cli.py` 导入方式 | 星号导入 |
| `ruff check scripts tests` | 164 项（154 × `F405` + 10 × `F401`） |
| `tests/test_task_list_cli.py` | 1968 行，单文件承载全部 98 个测试 |

一个文件混合解析、schema、校验、迁移、统计、文件写入、CLI 编排七种职责，这是 `DEF-01`~`DEF-04` 能同时存在而互不暴露的结构原因。

### DEF-08 / DEF-09 / DEF-10 / DEF-11（P2/P3）

- **`DEF-08`**：`statuses` 集合含 `-`（zh 与 en 都有）。实测 `add --status -` 写入 `| BUG-001 | 修复 | 占位符状态测试 | 2026-08-04 18:57 | - | - | - |`，`check` 输出「检查通过」。而文档只把 `-` 定义为**完成时间**的缺失占位符。占位符与业务状态未分层。
- **`DEF-09`**：`write_with_optional_check()` 是「先写入 → check 失败 → 写回原文」，非原子。全库检索无 `os.replace`、`tempfile`、`shutil.copy`、`.bak`。`archive` 顺序写 2 个文件（`_lib.py:2352`/`2355`/`2359`），`install-maintenance` 顺序写 3 个文件（`_lib.py:1266`/`1316`/`1342`），中途失败会留下半安装状态。
- **`DEF-10`**：`check` / `sections` / `list` / `summary` / `standardize` 对缺失文件全部抛 `FileNotFoundError` 原始堆栈。对 agent 调用方而言，这既污染上下文又不可本地化。
- **`DEF-11`**：`rate()` 用 `round()` 输出整数百分比，历史文件用一位小数。重算会引入无意义 diff。

---

## 3. 需求规格

每条需求给出**可执行的验收条件**；`§7` 的任务必须逐条对应。

### 迁移保真（对应 DEF-01、DEF-02）

**`REQ-01` 禁止补造时间精度。**
迁移只精确到日的旧值时，目标字段必须保持日精度或标记为未知，不得补 `00:00`。
*验收：* 输入 `2026-01-05`，迁移后该单元格不含 ` 00:00`；`check` 接受日精度值不报格式错误。

**`REQ-02` 禁止跨语义复制日期。**
迁移不得依据状态把一个语义的日期写入另一个语义字段。
*验收：* `发现日期` 旧表（含完成态记录）迁移后，完成时间列全部为缺失值；`完成日期` 旧表迁移后，发现时间列全部为缺失值。

**`REQ-03` 迁移必须先出计划、再决定是否写。**
迁移前生成 `MigrationPlan`，逐分区判定「可无损迁移 / 需用户决策 / 不可迁移」。存在「需用户决策」项时默认只报告、不写入。
*验收：* 含 `开始日期` 分区的文件执行 `--migrate-schema` 后文件字节不变，且报告点名该列与该分区、说明原因是「日期语义无法映射到双日期模型」而非「表头非法」。

**`REQ-04` 表头识别口径单一化。**
`check`、`add`、`standardize --migrate-schema` 必须共用同一个表头解析函数，对同一表头得出同一结论。
*验收：* 对四份历史样本，三条路径对每个分区的 schema 判定完全一致；新增一致性测试遍历全部样本 × 全部路径。

**`REQ-05` 四份历史样本可读可追加。**
真实 `发现日期` Bug 表头必须通过兼容校验，并能按该列语义追加新记录。
*验收：* 四份样本 `check` 均通过（`prd-workflow` 的重复章节属真实问题，应作为独立 issue 报出而非表头错误）；对 `发现日期` 分区 `add` 成功且新行日期写入发现语义列。

### 统计正确性（对应 DEF-03、DEF-04）

**`REQ-06` 字段按表头索引读取，禁止位置猜测。**
所有字段访问必须经由表头解析出的字段索引；列数与表头不符的行必须报为结构问题，不得参与统计。
*验收：* 专利样本的状态统计不再出现备注碎片；3 条未转义竖线行被明确报为列数异常；Bug 完成数按表头索引计为 114。

**`REQ-07` 摘要口径显式化。**
提供 `summary --policy auto|by-section|by-prefix`，`auto` 为默认。`auto` 语义：两种口径一致时直接采用；不一致时与文件现有摘要比对，命中其中一种则采用该口径**但只报告不写入**；都不命中则输出双口径差异、非零退出、拒绝 `--write`。
*验收：* 专利样本 `summary --write --policy auto` 不修改文件且非零退出，报告同时列出 85/27 与 82/30；`--policy by-prefix --write` 保持 85/27；`--policy by-section --write` 才写入 82/30。

**`REQ-08` 前缀与章节错位必须显式报出。**
`check` 报告前缀与章节错位的记录清单（ID + 所在分区 + 期望分区），级别为警告而非错误（不自动移动记录）。
*验收：* 专利样本 `check` 点名 `DEV-074` / `DEV-075` / `DEV-076`。

### 评测可信（对应 DEF-05、DEF-06）

**`REQ-09` benchmark 必须来自真实 agent 运行。**
每个配置至少 3 次真实运行，记录真实模型名、token、工具调用、耗时；禁止占位符与全零指标；benchmark 声明的运行数必须与实际运行目录数一致。
*验收：* 新增机械校验测试——benchmark 文件若包含 `<model-name>` / `<path-to-skill>` 类占位符、或 `tokens`/`tool_calls` 全零、或声明运行数与目录数不符，测试失败。

**`REQ-10` eval 前置状态必须真实提供。**
所有假设「文件已存在」的 eval 必须在 `files` 中提供 fixture。
*验收：* `evals.json` 中不存在「prompt 假设已有文件但 `files` 为空」的条目；新增 schema 校验测试。

### 工程质量（对应 DEF-07、DEF-08、DEF-09、DEF-10）

**`REQ-11` 分层与静态检查。**
按 §6 分层；入口不再星号导入；`ruff check` 零错误；测试按模块拆分。
*验收：* `ruff check skills/task-list-initialization/scripts tests` 退出码 0；`_lib.py` 删除或缩减为兼容转发层；无单个测试文件超过 600 行。

**`REQ-12` `-` 不是业务状态。**
`-` 从合法状态集合移除；缺失值由独立占位规则表达。
*验收：* `add --status -` 失败并给出可选状态列表；已有 `状态=-` 的行被 `check` 报为非法状态。

**`REQ-13` 写入原子且可恢复。**
单文件写入走「同目录临时文件 → flush →（必要时）fsync → `os.replace`」。多文件操作走「全部内容预生成并校验 → 备份原文 → 逐个原子提交 → 任一步失败按备份恢复」。
*验收：* 注入替换失败后原文件字节不变；注入 `install-maintenance` 第二个文件失败后第一个文件无残留内容；注入 `archive` 归档文件写入失败后主文件未被截断。

**`REQ-14` 缺失文件给出本地化错误。**
读命令对不存在或不可读的文件返回本地化单行错误与稳定退出码，不抛原始堆栈。
*验收：* 5 个读命令对缺失文件的 stderr 不含 `Traceback`；退出码稳定且有测试固定。

### 输出细节（对应 DEF-11）

**`REQ-15` 完成率格式与历史一致。**
完成率保留一位小数并去除多余零，重算不产生纯格式 diff。
*验收：* 文档事项 21/22 输出 `95.5%`；114/114 输出 `100%`。

---

## 4. 关键设计决策

以下决策在评审中有过分歧，此处定稿，实施时不再重开：

**`D1` 摘要默认口径为 `by-section`，不改默认。**
理由：新推荐 schema 下两种口径一致，差异只是历史错放的症状。改默认会让新文件承担历史包袱。安全性靠「冲突时拒绝静默写入」而非「猜一个更常见的口径」。

**`D2` 不做通用事务框架。**
`repository.py` 只提供原子写、写前备份、多文件「预校验后提交 + 失败恢复」三件事。单机 CLI 追求完整事务边界收益有限，复杂度会拖慢阶段 A。

**`D3` 表头解析收敛为单一函数。**
新增 `resolve_header(cells, section, locale) -> HeaderKind`，返回 `STANDARD_DUAL` / `LEGACY_SINGLE(semantic)` / `LEGACY_EXTENDED(semantic)` / `UNKNOWN`。`check` / `add` / `migrate` 全部改为消费它的结论。这是 `DEF-02` 三口径不一致的根治手段。

**`D4` `开始日期` / `规划日期` 本期只报告，不迁移。**
双日期模型无法表达 started / planned 语义。本期给出准确的拒绝理由和人工映射建议；是否引入第五种日期语义列见 §11 未决问题。

**`D5` fixture 必须自包含入库。**
`design/discussion/` 已在 `.gitignore` 中（仅本地留存）。fixture 需从四份样本提取最小化、可公开的等价内容，提交到 `tests/fixtures/legacy/`。测试与 CI 不得引用 `design/discussion/`。

**`D6` `SKILL.md` 精简降级为 P3。**
现有 175 行以触发条件、决策流程、安全边界为主，质量可接受。CLI 细节段（约 127–167 行）可下沉 references，但排在所有正确性工作之后。

**`D7` 模块分批迁移，`_lib.py` 最后删除。**
每阶段保留显式兼容导出，让旧 import 持续可用；`_lib.py` 只在阶段 C 末尾删除或缩减为转发层。

---

## 5. 不变量与非目标

### 5.1 必须保持

- 入口路径不变：`skills/task-list-initialization/scripts/task_list_cli.py`。
- 子命令名与主要参数不变：`init`、`add`、`update`、`sections`、`list`、`install-maintenance`、`check`、`summary`、`standardize`、`archive`。
- 新文件默认双日期 7 列 schema。
- 历史单日期文件允许继续使用，不强制迁移。
- `standardize` 默认只诊断；语义变更必须用户明确批准。
- ID 只增不改、不复用；归档文件中的 ID 参与下一编号计算。
- 中英文台账共享 ID 前缀与结构能力。
- 不自动重命名章节、移动记录或重写重复 ID。

### 5.2 本次新增

- 不得根据一个旧日期推造另一个日期（`REQ-02`）。
- 不得把日精度数据伪装成分精度（`REQ-01`）。
- `-` 是缺失值占位符，不是业务状态（`REQ-12`）。
- 字段访问必须经表头索引，禁止位置猜测（`REQ-06`）。
- 摘要写入前口径必须确定；无法唯一判断时只报告（`REQ-07`）。
- 所有写入先在内存生成并校验，再原子替换（`REQ-13`）。
- 多文件操作不得留下半安装状态（`REQ-13`）。
- benchmark 必须来自真实 agent 运行（`REQ-09`）。

### 5.3 非目标

- 不扩展到 GitHub Issues、Jira 或通用项目管理系统。
- 不新增中英之外的 locale。
- 不实现完整 CommonMark AST，只保证本 Skill 支持的表格子集。
- 不在本次重构中自动清理四份历史样本的数据问题（只保证工具不再加重损坏）。
- 不重命名 `task-list-initialization`。

---

## 6. 目标模块结构

```text
skills/task-list-initialization/scripts/
├── task_list_cli.py          # 稳定入口：修正 sys.path、显式 import main
└── _tasklist/
    ├── __init__.py           # 显式公开 API，无 import *
    ├── domain.py             # TaskRecord、SectionSchema、DateSemantic、ValidationIssue、Ledger   [阶段 C1]
    ├── schemas.py            # profile、表头注册表、resolve_header、日期语义映射                  [阶段 A2]
    ├── locales.py            # 仅显示标签、别名、消息（业务数据迁出）                             [阶段 C1]
    ├── parser.py             # Markdown → 领域对象（按表头索引）                                  [阶段 C2]
    ├── renderer.py           # 领域对象 → Markdown                                              [阶段 C2]
    ├── validator.py          # 结构与业务不变量 → ValidationIssue                                [阶段 C3]
    ├── migration.py          # MigrationPlan + 保真迁移                                          [阶段 A3]
    ├── summary.py            # SummaryPolicy 与双口径汇总                                        [阶段 B1]
    ├── maintenance.py        # agent 规则与 Stop hook 单一来源                                   [阶段 C4]
    ├── repository.py         # 原子写、备份、多文件预校验提交                                     [阶段 A5]
    └── cli.py                # argparse 与命令编排                                               [阶段 C5]

tests/
├── helpers.py                # 公共 subprocess / 临时目录 helper
├── fixtures/legacy/          # 四份样本的最小化自包含等价 fixture
├── test_schemas.py  test_domain.py   test_parser.py     test_validator.py
├── test_migration.py test_summary.py test_repository.py test_maintenance.py
├── test_cli.py      test_legacy_fixtures.py             test_evals_meta.py
```

核心类型（阶段 A2 先落 `DateSemantic` 与 `HeaderKind`，其余随阶段 C1 补全）：

```python
from dataclasses import dataclass, field
from enum import Enum


class DateSemantic(str, Enum):
    FOUND = "found"
    COMPLETED = "completed"
    STARTED = "started"
    PLANNED = "planned"


class HeaderKind(str, Enum):
    STANDARD_DUAL = "standard_dual"
    LEGACY_SINGLE = "legacy_single"
    LEGACY_EXTENDED = "legacy_extended"   # 含 优先级 / 预计时间 的 8 列变体
    UNKNOWN = "unknown"


class SummaryPolicy(str, Enum):
    AUTO = "auto"
    BY_PREFIX = "by-prefix"
    BY_SECTION = "by-section"


class MigrationVerdict(str, Enum):
    LOSSLESS = "lossless"          # 可自动迁移
    NEEDS_DECISION = "needs_decision"  # 语义无法映射，报告并停止
    NOT_LEGACY = "not_legacy"      # 表头无法识别，报告并停止


@dataclass(frozen=True)
class SectionSchema:
    title: str
    prefix: str | None
    columns: tuple[str, ...]
    date_semantics: tuple[DateSemantic, ...]
    field_index: dict[str, int]     # 字段名 -> 列下标，禁止 cells[-2] 式访问


@dataclass
class TaskRecord:
    item_id: str
    action: str
    description: str
    status: str
    notes: str
    section_title: str
    dates: dict[DateSemantic, str | None] = field(default_factory=dict)
    source_line: int | None = None


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: str       # error | warning | info
    line: int | None = None
    safe_fix: bool = False
```

---

## 7. 实施任务

四个阶段，阶段之间可独立发布；阶段内任务顺序不可颠倒。

### 阶段 A — 数据安全（P0，必须先做）

目标：让工具停止损坏历史数据。完成后达到发布可信度 **L2**（见 §8）。

---

#### A1 · 建立自包含历史 fixture 与失败测试

**需求：** `REQ-05` 前置；为 `REQ-01`~`REQ-08` 提供 golden 基准
**文件：** 新建 `tests/fixtures/legacy/{pdf-markdown,prd-workflow,translation,patent}-task-list.md`、`tests/test_legacy_fixtures.py`、`tests/helpers.py`
**参考（只读，不得被测试引用）：** `design/discussion/*/task-list(*).md`

**步骤：**

1. 从四份样本提取最小化 fixture，必须完整保留这些关键差异：`发现日期`（Bug 分区）、`完成日期`（其他分区）、`开始日期`、`规划日期`、8 列 `优先级`/`预计时间` 变体、跨章节前缀错位（`DEV-074`~`076` 在检查事项）、未转义竖线行（7 列与 8 列各一）、重复章节（`prd-workflow` 的「文档维护」×2）、按前缀口径的既有摘要表。
2. fixture 内容需可公开：描述与备注做等价改写，去除具体项目细节，但保留列结构、行数关系与状态分布。
3. 写失败测试固定当前缺陷（每条对应一个 `DEF`）：
   - `check` 拒绝真实 `发现日期` 表头（`DEF-02`）
   - `--migrate-schema` 产出 `00:00` 与跨语义复制（`DEF-01`）
   - 状态统计取到备注碎片、Bug 完成数为 111 而非 114（`DEF-03`）
   - 摘要按章节算出 82/30 而文件自带 85/27（`DEF-04`）
   - `add --status -` 成功且 `check` 通过（`DEF-08`）
   - 5 个读命令对缺失文件抛 `Traceback`（`DEF-10`）
4. 每条失败测试用 `self.assertEqual` 断言**当前**的错误行为，并在注释中标注对应 `REQ`；阶段 A~C 逐条把断言翻转为期望行为。

**验收：**

```bash
python3 -m unittest tests.test_legacy_fixtures -v
```

预期：全部通过（此时它们断言的是「当前缺陷行为」），并且注释清晰标出将在哪个任务翻转。

**回滚点：** 仅新增 fixture 与测试，无行为变更，可独立提交。

---

#### A2 · 表头识别口径单一化

**需求：** `REQ-04`
**文件：** 新建 `_tasklist/schemas.py`、`tests/test_schemas.py`；修改 `_tasklist/_lib.py`、`_tasklist/_locale.py`

**步骤：**

1. 写失败测试：`resolve_header()` 对四份 fixture 每个分区返回正确的 `HeaderKind` + `DateSemantic`，包括 `发现日期` → `LEGACY_SINGLE(FOUND)`、`完成日期` → `LEGACY_SINGLE(COMPLETED)`、`开始日期` → `LEGACY_SINGLE(STARTED)`、8 列变体 → `LEGACY_EXTENDED(COMPLETED)`。
2. 写一致性测试：遍历「四份 fixture × 全部分区 × {check, add, migrate} 三条路径」，断言三条路径对每个分区得出同一 `HeaderKind`。这条测试是本任务的核心防回归手段。
3. 实现 `schemas.py`：`SectionSchema`（含 `field_index`）、表头注册表、`resolve_header()`、日期列别名表。
4. 把 `_locale.py` 中的 Section / schema 业务数据迁入 `schemas.py`；`_locale.py` 只留显示标签、别名与消息。保留旧名兼容导出。
5. 改造 `check`、`add`、`standardize --migrate-schema` 全部消费 `resolve_header()`；删除 `is_supported_legacy_header()` 与 `check` 侧各自的表头判定分支。
6. 修正报错文案：非标准表头与「合法但语义不可迁移」必须是两条不同消息（`DEF-02` 后果三）。zh / en 同步。

**验收：**

```bash
python3 -m unittest tests.test_schemas tests.test_legacy_fixtures -v
python3 -m unittest discover -s tests -p 'test_*.py'
```

预期：四份 fixture `check` 通过（`prd-workflow` 只报重复章节）；`REQ-04` `REQ-05` 断言翻转；98 个既有测试仍通过。

**回滚点：** 独立提交。若一致性测试暴露不可调和的口径差异，先记录为新 `DEF` 再决定，不得靠特例分支绕过。

---

#### A3 · 保真日期迁移

**需求：** `REQ-01` `REQ-02` `REQ-03`
**文件：** 新建 `_tasklist/migration.py`、`tests/test_migration.py`；修改 `_tasklist/_lib.py`、`references/task-list-standard.md`

**迁移矩阵（定稿）：**

| 旧列 | 语义 | 迁移结果 |
| --- | --- | --- |
| `发现日期` / `Found Date` | FOUND | 原值写入发现时间，**保持日精度**；完成时间为缺失值 |
| `完成日期` / `Done Date` | COMPLETED | 原值写入完成时间，**保持日精度**；发现时间为缺失值 |
| `开始日期` / `Start Date` | STARTED | `NEEDS_DECISION`：只报告，指明列名、分区与人工映射建议 |
| `规划日期` / `Plan Date` | PLANNED | `NEEDS_DECISION`：同上 |
| 8 列 `优先级`+`预计时间`+`完成日期` | COMPLETED | 按 COMPLETED 规则迁移日期列；`优先级` / `预计时间` 保留原列 |

**步骤：**

1. 写失败测试逐条覆盖矩阵四行；断言迁移后无 ` 00:00`、无跨语义复制。
2. 写测试：含 `NEEDS_DECISION` 分区的文件执行 `--migrate-schema` 后文件字节完全不变，报告点名列与分区。
3. 写测试：迁移后再次 `check` 通过，且**发现时间保持日精度不被判为格式错误**——这要求同步放宽日期格式校验以接受 `YYYY-MM-DD`（写入新记录仍用 `YYYY-MM-DD HH:MM`）。
4. 写幂等测试：连续两次 `--migrate-schema` 第二次零变更。
5. 实现 `MigrationPlan`：先对全文件逐分区判定 `MigrationVerdict`，只有全部为 `LOSSLESS` 才允许写入；否则输出计划并退出。
6. 删除 `legacy_time()` 的 `00:00` 补造与 `legacy_completed_time()` 的跨语义复制。
7. 更新 `references/task-list-standard.md`：明确区分「兼容校验」（能读能追加）与「可无损迁移」（能改写 schema），并列出上表。

**验收：**

```bash
python3 -m unittest tests.test_migration tests.test_legacy_fixtures -v
python3 -m unittest discover -s tests -p 'test_*.py'
```

预期：`REQ-01`~`REQ-03` 断言翻转；四份 fixture 的迁移 dry-run 报告与矩阵一致。

**回滚点：** 独立提交 + 单独代码审查（数据语义变更）。

---

#### A4 · `-` 从状态集合移除

**需求：** `REQ-12`
**文件：** 修改 `_tasklist/_locale.py`、`_tasklist/_lib.py`；新增 `tests/test_validator.py`（先只放状态相关用例）

**步骤：**

1. 写失败测试：`add --status -` 必须以非零退出并列出可选状态；已有 `状态=-` 的行被 `check` 报为非法状态且给出行号。
2. 从 zh / en `statuses` 移除 `-`；缺失值改由字段级占位规则表达（只有时间列允许 `-`）。
3. 检查 `completed_statuses` / `pending_statuses` 及所有依赖 `statuses` 的分支，确认无处依赖 `-` 的存在。
4. 更新 `references/task-list-standard.md` 与 `SKILL.md` 中「`-` 的含义」表述：`-` 仅用于时间列缺失。

**验收：**

```bash
python3 -m unittest tests.test_validator tests.test_legacy_fixtures -v
python3 -m unittest discover -s tests -p 'test_*.py'
```

**回滚点：** 独立提交。

---

#### A5 · 原子写入与多文件恢复

**需求：** `REQ-13`
**文件：** 新建 `_tasklist/repository.py`、`tests/test_repository.py`；修改 `_tasklist/_lib.py`

**步骤：**

1. 写失败测试：`monkeypatch`/注入 `os.replace` 失败，断言目标文件字节不变。
2. 写失败测试：注入 `install-maintenance` 第二个文件写入失败，断言第一个文件无残留标记标题。
3. 写失败测试：注入归档文件写入失败，断言主文件未被截断、记录未丢失。
4. 实现 `repository.py` 三个能力（`D2` 范围）：
   - `atomic_write(path, text)`：同目录 `tempfile` → `flush` → `os.fsync` → `os.replace`。
   - `backup(path) -> bytes`：写前读取原文留存内存。
   - `commit_all(plans)`：全部内容预生成并校验 → 逐个 `atomic_write` → 任一失败按备份逐个恢复已提交项。
5. 把 12 处 `write_text` 全部改为经 `repository`；`add`、`update`、`standardize`、`summary --write`、`archive`、`install-maintenance` 统一入口。
6. `archive` 与 `install-maintenance` 改走 `commit_all`。

**验收：**

```bash
python3 -m unittest tests.test_repository -v
python3 -m unittest discover -s tests -p 'test_*.py'
rg -n 'write_text\(' skills/task-list-initialization/scripts/_tasklist/ | rg -v repository.py
```

预期：最后一条无输出（除 `repository.py` 外无直接 `write_text`）。

**回滚点：** 独立提交 + 单独代码审查（文件安全）。

---

### 阶段 B — 统计正确性（P1）

---

#### B1 · 字段索引化与摘要双口径

**需求：** `REQ-06` `REQ-07` `REQ-08` `REQ-15`
**文件：** 新建 `_tasklist/summary.py`、`tests/test_summary.py`；修改 `_tasklist/_lib.py`、`SKILL.md`、`references/task-list-standard.md`

**步骤：**

1. 写失败测试：状态必须经 `SectionSchema.field_index["状态"]` 读取；专利 fixture 的 3 行未转义竖线被报为列数异常且不参与完成数统计；按表头索引 Bug 完成数为 114。
2. 写失败测试：`summary` 状态分布输出不含备注碎片。
3. 写失败测试覆盖 `auto` 三分支（`REQ-07` 验收条件的三条）。
4. 写失败测试：`check` 点名 `DEV-074`/`075`/`076` 前缀错位，级别为 warning，且不移动记录。
5. 写失败测试：完成率 21/22 输出 `95.5%`、114/114 输出 `100%`。
6. 实现 `summary.py`：`SummaryPolicy`、双口径计算、差异报告渲染、`auto` 决策逻辑。
7. 全面替换 `cells[-2]` 等位置访问为字段索引访问（全库检索确认无残留）。
8. 新增 CLI 参数 `summary --policy auto|by-section|by-prefix`，默认 `auto`；`SKILL.md` 与 reference 同步说明「什么时候会拒绝写入、用户该怎么选」。

**验收：**

```bash
python3 -m unittest tests.test_summary tests.test_legacy_fixtures -v
python3 -m unittest discover -s tests -p 'test_*.py'
rg -n 'cells\[-\d\]' skills/task-list-initialization/scripts/
```

预期：最后一条无输出；专利 fixture `summary --write --policy auto` 不改文件且非零退出。

**回滚点：** 独立提交 + 单独代码审查（统计语义）。

---

#### B2 · 缺失文件与不可读文件的错误处理

**需求：** `REQ-14`
**文件：** 修改 `_tasklist/_lib.py`（或阶段 C 后的 `cli.py`）、`_tasklist/_locale.py`；新增 `tests/test_cli.py` 相关用例

**步骤：**

1. 写失败测试：5 个读命令 + 3 个写命令对缺失文件的 stderr 不含 `Traceback`，退出码固定。
2. 新增本地化消息 `file_not_found` / `file_not_readable`（zh / en）。
3. 在命令入口统一做一次文件可读性前置检查，不在每个 handler 重复。
4. 顺带检查其他会逃逸的异常类型（编码错误、权限错误），统一为本地化消息。

**验收：**

```bash
python3 -m unittest tests.test_cli -v
for c in check sections list summary standardize; do python3 $CLI $c --file /tmp/nope.md 2>&1 | rg -q Traceback && echo "FAIL $c"; done
```

预期：无 `FAIL` 输出。

**回滚点：** 独立提交。

---

### 阶段 C — 分层与工程质量（P1）

目标：让阶段 A/B 的修复可持续维护。本阶段**不引入任何行为变更**——每个任务的验收都包含「全量回归零变化」。

---

#### C1 · 领域模型与 locale 瘦身

**需求：** `REQ-11`
**文件：** 新建 `_tasklist/domain.py`、`tests/test_domain.py`；新建 `_tasklist/locales.py`；修改 `_tasklist/_locale.py`（转为兼容转发）

**步骤：** 落地 §6 的 `TaskRecord`、`Ledger`、`ValidationIssue`；`DateSemantic` / `HeaderKind` 从 `schemas.py` 迁入或重导出；`locales.py` 只保留显示标签、别名、消息；`_locale.py` 保留兼容导出。测试覆盖四种日期语义，而不是只测「单/双日期」两个列数标签。

**验收：** `python3 -m unittest tests.test_domain -v` 通过；全量回归无变化。

---

#### C2 · 解析器与渲染器

**需求：** `REQ-11` `REQ-06`（结构保障）
**文件：** 新建 `_tasklist/parser.py`、`_tasklist/renderer.py`、`tests/test_parser.py`

**步骤：** 实现 `parse_ledger(text, locale) -> Ledger` 与 `render_ledger(ledger) -> str`。覆盖转义 `\|`、缺末尾 `|`、重复章节、空表头、过宽行、混合 schema、`##\t` 制表符标题。增加 round-trip 测试：合法输入 `parse → render → parse` 领域数据不变、且字节幂等。旧 `_lib.py` 函数改为委托。

**验收：** `tests.test_parser` 通过；全量回归无变化。

---

#### C3 · validator 结构化

**需求：** `REQ-11`
**文件：** 新建 `_tasklist/validator.py`；扩充 `tests/test_validator.py`

**步骤：** 实现 `validate_ledger(ledger) -> list[ValidationIssue]`，为每类问题定义稳定 `code`（ID 非法、重复 ID、重复章节、列数异常、状态枚举、时间格式、悬空互引、摘要漂移、前缀错位、`-` 状态）。CLI 只负责本地化与退出码映射。结构化结果先在内部保留，不急于新增 `--format json`（`SKILL.md` 未承诺则不扩张）。

**验收：** `tests.test_validator` 通过；全量回归无变化。

---

#### C4 · 维护规则单一来源

**需求：** `REQ-11`
**文件：** 新建 `_tasklist/maintenance.py`、`tests/test_maintenance.py`；修改 `references/maintenance-rule.md`

**步骤：** 规则正文与 hook 生成逻辑集中到 `maintenance.py`。新增一致性测试：代码生成的中英文规则正文、标记标题、hook 脚本名必须与 reference 中展示的内容逐字一致。reference 改为「解释策略 + 引用由代码生成的规范内容」，不再维护两套易漂移的长字符串。保留跨 `CLAUDE.md` / `AGENTS.md` 的幂等检查与优先级规则，以及 `settings.json` 异常形状（`hooks: null`、`Stop` 为 dict）的拒绝逻辑。

**验收：** `tests.test_maintenance` 通过；全量回归无变化。

---

#### C5 · CLI 收敛与 ruff clean

**需求：** `REQ-11`
**文件：** 新建 `_tasklist/cli.py`；修改 `_tasklist/__init__.py`、`task_list_cli.py`；删除或缩减 `_tasklist/_lib.py`

**步骤：**

1. 列出当前被测试与外部依赖的公开名称（`split_cells`、`collect_records`、`detect_locale` 等），形成兼容清单。
2. `__init__.py` 改为显式导出，删除 `import *`。
3. `task_list_cli.py` 只负责修正 `sys.path`、显式 `from _tasklist.cli import main`、`raise SystemExit(main())`。
4. argparse 构建与各 handler 移入 `cli.py`；领域层不再 `print` 或 `raise SystemExit`。
5. 逐项消除 164 项 ruff 错误（154 `F405` 随星号导入消失，10 `F401` 逐个判断是保留为公开 API 还是删除）。

**验收：**

```bash
ruff check skills/task-list-initialization/scripts tests
python3 -m unittest discover -s tests -p 'test_*.py'
python3 /absolute/path/to/task_list_cli.py check --file /tmp/x/task-list.md   # 项目目录外可运行
```

预期：ruff 退出码 0；全量回归无变化；绝对路径调用正常。

---

#### C6 · 测试拆分

**需求：** `REQ-11`
**文件：** 拆分 `tests/test_task_list_cli.py`（1968 行）；充实 `tests/helpers.py`

**步骤：** 按 §6 的模块边界把用例迁到对应 `test_*.py`；公共 subprocess / 临时目录 helper 集中到 `helpers.py`；确认无用例在迁移中丢失（迁移前后测试总数与用例名集合比对）。

**验收：** 全量测试数不减少、名称集合一致；无单文件超过 600 行。

---

### 阶段 D — 可信度与发布（P1 + P3）

---

#### D1 · 重建 Skill eval 与 benchmark

**需求：** `REQ-09` `REQ-10`
**文件：** 修改 `evals/evals.json`；新建 `evals/trigger-evals.json`、`evals/fixtures/`、`tests/test_evals_meta.py`；新建评测 workspace（并加入 `.gitignore`）

**评测覆盖矩阵：**

| 类别 | 场景 |
| --- | --- |
| 应触发 | 初始化任务台账；整理历史 task-list；迁移旧账本；安装会话结束同步规则；归档长期台账 |
| 隐式应触发 | 用户只说「想用一个 Markdown 文件统一跟踪 bug、功能和文档」，不提 `task-list` |
| 不应触发 | 临时 TODO；GitHub Issues 操作；Jira / Notion 管理；仅生成 changelog |
| 行为评测 | 真实 `发现日期` / `开始日期` / `规划日期` fixture；摘要口径冲突；用户未批准迁移；维护规则未确认 |

**步骤：**

1. 为所有假设「文件已存在」的 eval 配置真实 fixture（复用 `tests/fixtures/legacy/`），消除 `"files": []`。
2. 新增 `tests/test_evals_meta.py`：校验 `evals.json` schema、禁止「prompt 假设已有文件但 `files` 为空」、禁止占位符字符串。
3. 同时运行 with-skill 与 baseline agent；禁止用直接调用 CLI 的脚本结果代替 agent 行为。
4. 每个配置至少 3 次真实运行，记录真实模型名、token、工具调用、耗时。
5. 用 Skill Creator 的聚合器生成 benchmark，不手工填写。
6. 新增机械校验（`REQ-09` 验收）：benchmark 含占位符、全零指标或声明运行数与目录数不符时测试失败。
7. 生成 review HTML，完成一次人工输出审查并记录结论。
8. 把新 workspace 目录加入 `.gitignore`（当前 `.gitignore` 缺少该条目）。

**验收：** `tests.test_evals_meta` 通过；benchmark 的声明运行数、实际目录数、指标三者一致；人工审查结论已记录到台账。

---

#### D2 · 文档收敛与事实校准

**需求：** 支撑 §8 的 L3 门槛
**文件：** 修改 `README.md`、`SKILL.md`、`references/task-list-standard.md`、`references/task-list-template.md`、`VERSION`

**步骤：**

1. 把「四项目观察到的历史格式」与「本 Skill 推荐的新规范」拆成两个独立章节；**禁止再把双日期写成四项目共同点**（四份样本无一使用双日期）。
2. 明确「单日期兼容」是按**日期语义**兼容，不是只按列数兼容（`DEF-02` 的文档面）。
3. README 的每条功能承诺逐条对应到测试；删除无测试支撑的绝对化表述。
4. 用 `D1` 产出的真实 benchmark 替换旧数据；若某项指标缺失则删除该声明，不留旧值。
5. 更新测试数量与 `VERSION` 至 `V0.4.0`。
6. 迁移矩阵只在 `references/task-list-standard.md` 维护一份，`SKILL.md` 与 README 只引用不复制。

**验收：** README / `SKILL.md` / reference / 代码四处对 schema、迁移、口径的表述一致；新增或更新的文档声明均可追溯到测试或 benchmark。

---

#### D3 · `SKILL.md` 精简（P3，可选）

**需求：** `D6`
**步骤：** 把 CLI 细节段（现约 127–167 行）下沉到 `references/`，`SKILL.md` 保留触发条件、决策流程、安全边界与 references 路由。仅在阶段 A~D2 全部完成后执行。

---

#### D4 · 发布回归

**文件：** 修改 `README.md`；可选新建 `.github/workflows/test.yml`

**步骤：**

1. `ruff check skills/task-list-initialization/scripts tests`
2. `python3 -m unittest discover -s tests -p 'test_*.py'`
3. 对四份 legacy fixture 依次运行 `check`、`standardize`、`summary --policy auto`、`--migrate-schema` dry-run；确认有损或歧义迁移只报告不写入。
4. 确认入口脚本在项目目录外通过绝对路径可运行。
5. 确认中英文最小模板、`development` profile、摘要、维护规则安装均通过回归。
6. 核对 README 的测试数量、功能声明、benchmark 均来自当前运行。
7. 若使用 GitHub，增加 Python 3.8 与当前稳定版的 CI；否则在 README 保留本地验证命令。
8. 最终代码审查后发布 `V0.4.0`。

---

## 8. 发布门槛：三级可信度

不要用一个笼统的「重构完成」判断能否对外。按用途分三级，每级独立可发布：

| 级别 | 含义 | 门槛 | 当前状态 |
| --- | --- | --- | --- |
| **L1 · CLI 可用** | 可用于**新建**台账的日常增删改查 | 已有 98 测试通过；`init` / `add` / `update` / `check` 正确 | ✅ 已达成（`V0.3.0`） |
| **L2 · 历史台账可信** | 可对**已存在**台账做 `standardize` / `--migrate-schema` / `summary --write` | 阶段 A 全部 + B1 完成；`REQ-01`~`REQ-08`、`REQ-12`~`REQ-15` 验收通过 | ❌ 未达成。**在此之前，文档必须明示「不要对重要历史台账运行 `--migrate-schema` 与 `summary --write`」** |
| **L3 · Skill 成熟度可宣称** | README / benchmark 可对外引用 | 阶段 C + D 完成；`REQ-09`~`REQ-11` 验收通过 | ❌ 未达成。旧「100% vs 13%」结论不得再引用 |

**这是本文档最重要的一条约束：** L2 未达成前，不得在任何文档中鼓励用户对真实历史台账执行写操作。

---

## 9. 风险与回滚

| 风险 | 控制措施 |
| --- | --- |
| 模块拆分破坏旧 import | 每阶段保留显式兼容导出；`_lib.py` 到 C5 才删除；C 阶段每个任务验收都要求「全量回归无变化」 |
| 迁移规则变化影响已有用户 | 默认 report-only；新行为先经 dry-run 展示；`MigrationPlan` 全部 `LOSSLESS` 才写 |
| 放宽日期格式校验引入新歧义 | 只对**已迁移的历史日精度值**放宽；新写入记录仍强制 `YYYY-MM-DD HH:MM`，由测试固定两条路径 |
| 摘要新增参数抬高复杂度 | 默认 `auto`；只有检测到歧义才要求用户选择；`SKILL.md` 只写「什么时候会被拒绝、怎么选」 |
| 原子写在 Windows 行为不同 | 用标准库同目录 `tempfile` + `os.replace`；在 POSIX 与 Windows 都跑 `test_repository` |
| fixture 泄露项目细节 | fixture 做等价改写，只保留结构；`design/discussion/` 保持 `.gitignore`，测试不得引用 |
| 文档与代码再次漂移 | schema 与维护模板建立单一代码来源 + 一致性测试（A2、C4）；README 声明必须可追溯到测试 |
| eval 成本上升 | 核心行为用单元测试覆盖；只有触发判断与 agent 决策使用多轮模型 eval |

每个阶段保持可独立回滚。**不要把领域模型、文件事务和文档重写压进同一个提交。**

---

## 10. 推荐提交顺序

```text
# 阶段 A — 数据安全
test: add self-contained legacy task-list fixtures and defect baselines
refactor: unify task-list header resolution across check/add/migrate
fix: preserve legacy date semantics and precision during migration
fix: reject "-" as a task status
refactor: route all task-list writes through atomic repository

# 阶段 B — 统计正确性
fix: read task fields by header index and make summary policy explicit
fix: report missing task-list files without a traceback

# 阶段 C — 分层
refactor: introduce task-list domain model and slim locales
refactor: split task-list parser and renderer
refactor: extract structured task-list validator
refactor: isolate maintenance rule installation
refactor: simplify task-list CLI entrypoint and clear ruff findings
test: split task-list test suite by module

# 阶段 D — 可信度
test: rebuild task-list skill evaluations on real agent runs
docs: separate observed legacy formats from recommended schema
ci: verify task-list skill and CLI
```

---

## 11. 未决问题（需产品决策，不阻塞阶段 A）

| 编号 | 问题 | 影响 | 建议 |
| --- | --- | --- | --- |
| `Q1` | 是否为 `开始日期` / `规划日期` 引入第五种日期语义列（如 planning profile 的 8 列变体）？ | 影响 translation 样本 3 处 `开始日期` + 3 处 `规划日期` 能否自动迁移 | 本期按 `D4` 只报告；若用户明确需要，作为 `V0.5.0` 的 profile 扩展而非迁移特例 |
| `Q2` | `prd-workflow` 样本的重复章节（「文档维护」×2）是否需要 CLI 提供合并能力？ | 当前只报告，不合并 | 保持只报告。章节合并涉及记录移动，属语义变更，必须人工 |
| `Q3` | 评测 workspace 是否入库？ | 影响仓库体积与可复现性 | 建议不入库（加 `.gitignore`），但 benchmark 汇总 JSON 与 review 结论入库，保证声明可追溯 |
| `Q4` | 是否新增 `check --format json`？ | `validator` 已有结构化结果，暴露成本低 | 暂不新增。等出现真实自动化消费方再开，避免无需求扩张 |
| `Q5` | 是否重命名为 `task-list-management`？ | 影响已安装用户 | 本期不改。若改，需单独设计目录别名与兼容迁移 |

---

## 12. 评审记录

| 来源 | 结论 | 本文档采纳点 |
| --- | --- | --- |
| 架构审查报告（初版） | 提出 P0 迁移语义、P1 统计口径 / benchmark / 分层、P2 状态 / 写入安全 | 全部纳入 `DEF-01`~`DEF-09` |
| 评审 A | 全部成立；指出 `migrate` 与 `check` 对 `发现日期` 别名口径不一致；建议先修模型层、摘要保持章节默认；对多文件事务持保留意见 | `DEF-02`、`D1`、`D2`、§1.2 执行顺序调整 |
| 评审 B（4 路并行复核） | 全部成立；精确化 P0 对未完成态的边界；实测 `summary --write` 改动面更大；从废纸篓复核 benchmark；指出引用路径已改名（`docs/discussion/` → `design/discussion/`）；建议 `SKILL.md` 精简降级 | `DEF-01` 三重危害拆分、`DEF-05` 证据、`D5`、`D6` |
| 本次复现（`CHK-013`） | 新定位 `DEF-03`（状态列位置猜测，是 114→111 的真实根因，评审 B 归因有误）与 `DEF-10`（缺失文件抛 `Traceback`）；确认四份样本 `check` 全部失败；确认 `add` 的拒绝文案把用户直接指向 `DEF-01` | `DEF-03`、`DEF-10`、`REQ-06`、`REQ-14`；已登记 `BUG-027`、`BUG-028` |

**实施起点：** 阶段 A 任务 A1。台账关闭条件：`BUG-026` 在 A3 完成后可标记已修复；`BUG-027` 在 B1 完成后；`BUG-028` 在 B2 完成后。
