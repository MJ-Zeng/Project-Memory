# Handoff：DOCS-ALIGN-001 文档与实现对齐 + 首轮试点章程

- 任务卡：`PM02_DOCS_ALIGN_TASK_CARD.md`（`DOCS-ALIGN-001`）
- 执行者：PM-02（独立克隆 `pm-pilot-02`）
- 分支：`docs/align-20261030`（已 push 到 origin 供 PM-03 复核；未建 PR）
- 基线：`1eaa3f498074d091bb3996faec3534d56ac12f4b`（`origin/dev/v1.0`，含 PR #35 与 PR #36）
- 变更提交：`f88aafe341b8d9fb88e668e69e6c7c57830d97cd`
- 提交时间（UTC）：2026-10-30T01:53:11Z

## 1. 改动清单（8 个文件）

| 文件 | 变更 |
|---|---|
| `README.md` | 快速开始测试命令 `python3 -m unittest discover -s tests -v` → `python3 -m pytest -q`（+3/−1）；审计段落补边界句 |
| `docs/TEST_REPORT.md` | 文件头新增 2 行历史标注 + 1 空行（+3/−0），正文未改 |
| `pilot/STATUS.md` | 文件头新增 2 行历史标注 + 1 空行（+3/−0），正文未改 |
| `skill/project-memory/SKILL.md` | verify 第 2 步两条证据级别合并为一条 CLI 约束说明（+1/−2），保留 `agent_claimed`、`locally_observed` 原文 |
| `skill/project-memory/references/data-contracts.md` | 四级证据表后补 CLI 约束一句（+2/−0） |
| `skill/project-memory/references/workflows.md` | 证据级别表后补同一句（+2/−0） |
| `docs/CURRENT_STATE.md` | 审计计数行改为 40/0/16/24（+2/−1）；已知限制补 `audit` 边界句；frontmatter 未动，48 行 |
| `pilot/PILOT_R1_CHARTER.md` | 新增章程 56 行，frontmatter 六项齐全，`status: "current"`，无 Markdown 链接、无 URL |

未改代码、测试、ADR、`.project-memory/`、`evidence/`；未创建 Goal/Run。

## 2. 第 4 节验收实测

| # | 项目 | 实测 |
|---|---|---|
| 1 | `git diff --stat 1eaa3f4..HEAD` | 在变更提交 `f88aafe` 上恰为 **8 files changed, 72 insertions(+), 4 deletions(-)**，文件清单与卡一致（`git diff --numstat` 见下） |
| 2 | TEST_REPORT / STATUS 只增不改 | 两者 `numstat` 均为 `3 0`；去掉新增 3 行后与基线 blob 在行尾归一后逐字节相同（2/2 True） |
| 3 | 章程 | 56 行（≤90）；frontmatter 六项齐全、`status: "current"`；无 `](`、无 `http` |
| 4 | 审计多重集 | 自测基线 **40（0/16/24）** → 改后 **40（0/16/24）**；新增 0、减少 0；`pilot/PILOT_R1_CHARTER.md` 上 finding 0；`entry_doc_*` finding 0；`entry_doc=docs/CURRENT_STATE.md`，导航 `unreachable: []` |
| 5 | 回归 | 默认：253 passed / 2 skipped，207.53s，exit 0；`PROJECT_MEMORY_REQUIRE_OPENSSL=1`：253 passed / 2 skipped，202.42s，exit 0（工作区外解释器 `/c/SoftWare/Anconda/python`） |
| 6 | 前后审计 JSON | `C:\Users\ZMJ\AppData\Local\Temp\docs-align-before.json`、`C:\Users\ZMJ\AppData\Local\Temp\docs-align-after.json`（仓库外） |

补充实测（非卡内验收项）：`reconcile --fail-on high` exit **0**，`state=needs_attention`，`counts={high:0, medium:16, low:24}`。

`git diff --numstat 1eaa3f4..f88aafe`：

```text
3	1	README.md
2	1	docs/CURRENT_STATE.md
3	0	docs/TEST_REPORT.md
56	0	pilot/PILOT_R1_CHARTER.md
3	0	pilot/STATUS.md
1	2	skill/project-memory/SKILL.md
2	0	skill/project-memory/references/data-contracts.md
2	0	skill/project-memory/references/workflows.md
```

说明：分支顶点在变更提交后又追加本 handoff 提交，因此 `1eaa3f4..HEAD` 在顶点会是 9 个文件；第 1 条的数字对应变更提交 `f88aafe`。

## 3. NOT VERIFIED

- 未在 CI 运行；两条 pytest 仅为本机工作区外解释器实测。
- 未验证 README 中其他 `unittest` 提法（`--test-command`、`test-run` 示例）是否需要同步修改；卡只允许改快速开始处的测试命令，其余按要求未动。
- 未验证 GitHub 网页渲染与 CRLF 重新检出后的显示；`docs/TEST_REPORT.md` 工作树为 CRLF，新增 3 行沿用该风格，提交经 git 归一为 LF。
- 未验证 `docs/CURRENT_STATE.md` 中“40 条 findings”在他人环境（不同 Python/openssl）下是否完全一致；本机两门槛均为 40。
- 未验证章程在实际试点执行中的可操作性；本轮只做文档写入。
- 未建 PR、未合并、未碰 `dev/v1.0`、未打 tag。
- 工作区两份旧未跟踪文件（`PM02_COLD_START_VALIDATION.md`、`tasks/PM02-cold-start-handoff-20261029T150500Z.md`）保持原样，未提交。

## 4. 复核入口

- 远端分支：`origin/docs/align-20261030`，变更提交 `f88aafe`，基线 `1eaa3f4`。
- 建议 PM-03 在自己的克隆中：`git fetch origin docs/align-20261030 && git diff 1eaa3f4..f88aafe`；重跑第 4、5 条命令。
- 本 handoff 只是执行事实记录，不构成 PASS。
