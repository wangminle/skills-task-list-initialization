# BUG-094～101 修复复核（2026-10-07）

结论：八项缺陷的原始复现场景已修复，日期精度与合法自定义分区兼容面修复正确。仍有三项已复现的边界缺口，其中两项影响自动化巡检完整性和报告输出，需要继续处理后再认为整批完全收口。

## 本次依据

以当前未提交工作区为准，不依赖用户提供的执行摘要。台账已包含后续 CHK-120/121，测试已从摘要中的 319 增加至 324；msvcrt mock 与英文输出用例已经补充。此次未修改实现代码或现有测试。

## 剩余发现

### BUG-102（P2）：单项目维护文件解码异常仍会终止整轮 fleet

位置：`skills/task-list-initialization/scripts/_tasklist/fleet.py:230`、`:246`；下游 `maintenance.py:240`、`:244`。

两个项目各有有效 UTF-8 台账，其中一个项目的 `CLAUDE.md` 为 UTF-16/非法 UTF-8，即可复现：

```python
(root / "a" / "CLAUDE.md").write_bytes(b"\xff\xfe")
```

执行 `fleet --root ROOT --format json`，退出码 1、stdout 为空，stderr 是 UnicodeDecodeError traceback，其余项目结果也丢失。初始 inspect_file 与修复后 inspect_file 都在逐文件 try/except 之外；inspect_file 自身只保护台账 read_text，没有保护维护检测。维护检测 catch OSError 也没有覆盖 UnicodeDecodeError。同类情况还可能来自 AGENTS.md、settings.json、hooks.json 等维护文件。

BUG-095 的锁超时和修复写入 OSError 已正确隔离，但并未隔离整个文件诊断生命周期。建议将初检、加锁修复、复检统一放入逐文件异常边界，针对可预期的 OSError / UnicodeError 生成错误结果并继续扫描；保留正确 JSON 及其他项目结果，避免无差别吞掉编程错误。回归必须构造至少一个正常项目和一个维护文件编码异常项目。

### BUG-103（P2）：空目录默认文本输出忽略 --report

位置：`skills/task-list-initialization/scripts/_tasklist/cli.py:1595-1597`。

```bash
python3 skills/task-list-initialization/scripts/task_list_cli.py fleet --root EMPTY_DIR --report out.md
```

实际退出码 0，输出“未找到任何 task-list.md”，但 out.md 不生成；若已有旧报告，也不会更新，容易使自动化继续读取旧结果。添加 `--format json` 才能走到报告写入，报告行为不应受 stdout 格式影响。

BUG-098 的空 JSON、exclude 报告、报告写入异常处理和扫描权限披露均已修复；空文本分支仍在写报告前提前 return。建议移除该提前返回，让空结果也写空报告；同时验证空 JSON、空文本、已有旧报告覆盖和不可写报告路径。

### BUG-104（P3）：报告路径含反斜杠加竖线时仍拆列

位置：`skills/task-list-initialization/scripts/_tasklist/fleet.py:336`。

普通 `a|b/task-list.md` 已正确转义，但报告只执行 `rel.replace("|", "\\|")`，没有先转义已有反斜杠。POSIX 实际目录名 `a\|b` 下运行 fleet --report，命令成功退出，报告数据行却包含偶数反斜杠后接竖线，竖线仍是表格分隔符。用项目的转义感知 `split_cells` 解析得到 9 列，而表头是 8 列。

建议复用 renderer.escape_cell；该函数已处理反斜杠、竖线、换行和预览安全，避免另建一套转义规则。新增真实路径用例验证报告列数及路径内容。

## 八项原始问题逐项结论

| 记录 | 复核结果 |
| --- | --- |
| BUG-094 | 正确。显式 date-only 通过有效日期校验后保留日精度；原始发现 15:00、同日完成日期场景落盘为日期，check 无倒挂，后续仅追加备注成功。单日期和 update 写入已使用同一保精度函数。 |
| BUG-095 | 原始锁竞争场景正确，批次继续处理；诊断阶段编码异常仍未隔离，见上述 P2。 |
| BUG-096 | 正确移除 is_relative_to，改 relative_to/ValueError；AST 守卫可防已列明 API 回归，但不是 Python 3.8 实机测试。 |
| BUG-097 | 伪表头被拒绝；完整标准表头的自定义分区保持通过，符合 BUG-076 兼容要求。 |
| BUG-098 | 四项原始缺口修复正确；新增发现空文本结果不生成报告。 |
| BUG-099 | 缺失目标先校验，父目录和 lock 不再被创建；LockCreateError、本地化错误和台账路径提示已落实。正常 sidecar 保留，未删除锁文件重引入竞态。 |
| BUG-100 | headerless/pseudo 表中的身份与引用已登记，跨表重复 ID、独有 ID 引用、两位数字 ID 的原始场景已覆盖。 |
| BUG-101 | 普通竖线转义和 glob 帮助澄清正确；复合反斜杠转义仍不完整，见上述 P3。 |

## 验证结果与限制

- Python 3.13.13：`python3 -m unittest discover -s tests/scripts -p 'test_*.py'`，324 项通过。
- Python 3.9.6：`/usr/bin/python3 -m unittest discover -s tests/scripts -p 'test_*.py'`，324 项通过；unittest 不依赖 pytest，该解释器没有 pytest 不妨碍此次实跑。
- `ruff check skills/task-list-initialization/scripts tests/scripts` 通过。
- 全技能目录 Ruff 仍有评测脚本既有 F401/F841 两项，未引入于本次修复。
- `git diff --check` 通过；根台账复检通过。
- 上述三项发现使用临时目录/真实 CLI 或项目解析器复现，未改工作区实现。
- Python 3.8 与 Windows 实机未运行；msvcrt 分支 mock 已补，不能等同于 Windows 实机验证。

文档轻微缺口：README.md:512 中文 V0.3.9 changelog 仍为 319，与实际 324、徽章和英文 changelog 不一致；该问题已在 CHK-121 记录。CLI 参考的 fleet 退出码描述仍只把 2 归于根目录错误，发布前应同步报告写入失败也返回 2、扫描错误返回 1 的新契约。

本次登记 BUG-102/103/104 为待修复，CHK-122 为已完成审查记录；保留 BUG-094～101 已修复状态，台账写后 check 通过。
