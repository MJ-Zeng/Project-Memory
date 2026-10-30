# Handoff：HYGIENE-R1-001 文档与入口卫生

- 任务卡：`PM02_DOCS_HYGIENE_TASK_CARD.md`（`HYGIENE-R1-001`）
- 执行者：PM-02（独立克隆 `pm-pilot-02`）
- 分支：`docs/hygiene-20261030`（本地，未 push）
- 基线：`f033a6c517cfde3eebb586b07f770d94b2d2c3b7`（`v1.0.0`）
- 变更提交：`6d85016038e084849780a2523953f41e1de65c03`
- 提交时间（UTC）：2026-10-30T01:05:38Z

## 1. 改动文件清单

本提交只含三个文件：

| 文件 | 变更 |
|---|---|
| `docs/CURRENT_STATE.md` | 新增，47 行；frontmatter 按任务卡固定（`status: "current"`、`last_verified_at: "2026-10-30"`）；无 Markdown 链接、无 URL、无 ADR 编号 |
| `pilot/PILOT_CLOSEOUT.md` | 仅在第 1 行前插入 1 段历史标注 + 1 空行；原文未删改 |
| `.project-memory/config.json` | `entry_doc`: `null` → `"docs/CURRENT_STATE.md"`，其余键不变 |

`pilot/PILOT_CLOSEOUT.md` 的 `git diff --numstat f033a6c --` 为 `2	0`（新增 2 行、删除 0 行）；第 119 行原文 `- **v1.0：NO-GO。**` 仍在。

## 2. 审计对比（改前 / 改后）

命令（在本机 Git Bash 中，`PATH` 里的 `python` 是 Microsoft Store 占位符，故显式指定解释器）：

```bash
PROJECT_MEMORY_PYTHON=/c/SoftWare/Anconda/python ./bin/project-memory audit --scope current > <仓库外临时目录>/hygiene-before.json
# 改动后同一命令 > hygiene-after.json
```

- 改前（干净基线 `f033a6c`）：**84** 条 → high 14 / medium 25 / low 45，`entry_doc: null`，audit exit 0。
- 改后（`6d85016`）：**82** 条 → high 14 / medium 23 / low 45，`entry_doc: docs/CURRENT_STATE.md`，audit exit 0。
- 按任务卡要求用 Python 比较 `(severity, code, location)` 三元组集合：**新增 0 项**。
- 减少 2 项：`medium/broken_document_reference` at `docs/TEST_REPORT.md` 与 `docs/TUTORIAL.zh-CN.md`，消息均为「缺失：docs/CURRENT_STATE.md」。这两份文档原本就引用安装模板生成的入口文档，文件创建后坏链自然消解；不是掩盖或修改既有 finding。
- `location == docs/CURRENT_STATE.md` 的 finding：**0**；`entry_doc_*` 类 finding：**0**。
- 导航：`entry_links: 4`，`reachable` 覆盖 `docs/ARCHITECTURE.zh-CN.md`、`docs/OPERATIONS.zh-CN.md`、`docs/TEST_REPORT.md`、`docs/TUTORIAL.zh-CN.md`，`unreachable: []`。

**与任务卡验收第 2 条字面值的偏差需要 PM-01 / PM-03 知晓**：任务卡预期总数「仍为 84」，实测为 82（medium 25→23）。偏差方向为 finding 减少，且无任何新增三元组，未触发停止条件。

## 3. 测试门槛（本机实测）

解释器：`/c/SoftWare/Anconda/python`（Python 3.12.4），在 `6d85016` 工作树上运行。

| 命令 | 结果 | 耗时 | exit |
|---|---|---|---|
| `python -m pytest -q` | 253 passed, 2 skipped | 149.89s | 0 |
| `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q` | 253 passed, 2 skipped | 149.78s | 0 |

与发布报告口径一致（253/2，exit 0）。未修改任何代码或测试来达成该结果。

## 4. reconcile 状态

```bash
PROJECT_MEMORY_PYTHON=/c/SoftWare/Anconda/python ./bin/project-memory reconcile --fail-on high
```

- exit **2**，`state: needs_attention`，`summary.docs`: high 14 / medium 23 / low 45。
- 属任务卡第 7 条描述的预期结果（既有 14 high 来自 ADR 元数据），未调整审计规则。

## 5. 未做 / 未验证（NOT VERIFIED）

- 未在 CI 运行：仓库 workflow 未触发，本机两条 pytest 不能证明 CI 结论。
- 未验证其他文档过期项：`README.md` 仍写 unittest discover、`docs/TEST_REPORT.md` 仍为 2026-10-25 的 74 项记录、`pilot/STATUS.md` 仍停在 B2 时代——均属任务卡禁止修改范围，本轮未改、未逐条复核。
- 未独立复跑「发布证据在干净检出上 24/24 完整性通过」；该事实取自任务卡与发布文档，本轮只复跑了测试门槛。
- 未验证 `docs/CURRENT_STATE.md` 在 GUI/GitHub 渲染下的显示效果；只确认了仓库内文本与审计结果。
- 未验证 Windows 换行转换后的再次检出结果；提交 blob 为 LF，本机 `core.autocrlf` 会在下次检出时转 CRLF（行数与内容不变，未实测）。
- 未 push、未建 PR、未打 tag、未建 Issue、未创建 Goal/Run。
- 工作区仍有两份上一轮遗留的未跟踪文件（`PM02_COLD_START_VALIDATION.md`、`tasks/PM02-cold-start-handoff-20261029T150500Z.md`），按任务卡保持原样，未提交、未删除、未改写。

## 6. 给 PM-03 复核的入口

- 分支：`docs/hygiene-20261030`，提交 `6d85016`，基线 `f033a6c`。
- 复核命令：`git diff f033a6c..6d85016`；`git diff --stat f033a6c..6d85016`（应恰为本文所列 4 个文件，含本 handoff 的后续提交）；重跑第 2、5 条验收命令。
- 本 handoff 只是执行事实记录，不构成 PASS；是否接受 84→82 的偏差由人类决定。
