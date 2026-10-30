# Handoff：ADR-META-001 补齐 7 个 ADR 的 frontmatter

- 任务卡：`PM02_ADR_METADATA_TASK_CARD.md`（`ADR-META-001`）
- 执行者：PM-02（独立克隆 `pm-pilot-02`）
- 分支：`docs/adr-metadata-20261030`（本地，未 push）
- 基线：`f033a6c517cfde3eebb586b07f770d94b2d2c3b7`（`origin/dev/v1.0` 与本卡一致）
- 变更提交：`342676478864ee91cdc9ae887fb9f34bfa3ef273`
- 提交时间（UTC）：2026-10-30T01:33:47Z

## 1. 改动文件清单

提交恰好 7 个文件，每文件 +7/−0：

| 文件 | id | related_issues |
|---|---|---|
| `docs/decisions/ADR-0001-portable-repository-identity.md` | ADR-0001 | [3] |
| `docs/decisions/ADR-0002-inprocess-signature-verifier.md` | ADR-0002 | [1] |
| `docs/decisions/ADR-0003-execution-provenance.md` | ADR-0003 | [12] |
| `docs/decisions/ADR-0004-criteria-digest.md` | ADR-0004 | [16] |
| `docs/decisions/ADR-0005-cli-bootstrap.md` | ADR-0005 | [20] |
| `docs/decisions/ADR-0006-test-run-isolation.md` | ADR-0006 | [23] |
| `docs/decisions/ADR-0007-audit-integrity.md` | ADR-0007 | [28] |

每个文件在首行前插入：

```yaml
---
id: "ADR-000N"
status: "proposed"
owner: "MJ-Zeng"
related_issues: [N]
---

```

Issue 号取自各文件第 5 行正文「任务：…（Issue #N）」，与任务卡表格逐条核对一致（3/1/12/16/20/23/28）；正文未改，未升格任何 ADR。

## 2. 第 4 节验收实测

| # | 项目 | 实测 |
|---|---|---|
| 1 | `git diff --stat f033a6c..HEAD` | 7 files changed, 49 insertions(+), 0 deletions(-)；每个文件 `7  0` |
| 2 | 正文零改动 | 对 7 个文件逐字节验证：去掉新增 7 行后与基线文件字节完全相同（7/7 True）；`git diff` 仅显示文件顶部新增 |
| 3 | 审计多重集 | 84（14/25/45）→ **42（0/18/24）**；新增三元组 **0**；减少项恰为五项：`adr_invalid_id` 7→0、`adr_invalid_status` 7→0、`adr_missing_provenance` 7→0、`broken_adr_reference` 14→0、`unknown_document_status` 11→4；其余 code 计数不变 |
| 4 | ADR 文件上的 finding 为 0 | **未满足：仍有 25 条**（详见第 3 节） |
| 5 | `reconcile --fail-on high` | exit **0**，`counts = {high: 0, medium: 18, low: 24}`，`state = needs_attention` |
| 6 | 回归 | 默认：253 passed / 2 skipped，197.36s，exit 0；`PROJECT_MEMORY_REQUIRE_OPENSSL=1`：253 passed / 2 skipped，153.69s，exit 0（工作区外解释器 `/c/SoftWare/Anconda/python`） |
| 7 | 前后审计 JSON | `C:\Users\ZMJ\AppData\Local\Temp\adr-meta-before.json`、`C:\Users\ZMJ\AppData\Local\Temp\adr-meta-after.json`（均在仓库外） |

审计命令（两 G 因 `PATH` 中的 `python` 为 Store 占位符，显式指定解释器）：

```bash
PROJECT_MEMORY_PYTHON=/c/SoftWare/Anconda/python ./bin/project-memory audit --scope current
```

## 3. 第 4 节第 4 条与其余验收项的冲突（按第 6 节停止）

任务卡第 4 节第 4 条要求「`location` 为任一 ADR 文件的 finding 必须为 0」，这与第 3 条允许清单冲突：第 3 条要求除五项外其余 code 计数不变，而下列既有 finding 的 location 恰是 ADR 文件：

- `low / ambiguous_reference`：12 条（ADR-0001、ADR-0002、ADR-0004、ADR-0005、ADR-0006，正文中的裸代码文件名如 `authority.py`）
- `medium / reference_authority_mismatch`：12 条（ADR-0002、ADR-0007，正文引用了 evidence 区文件）
- `medium / reference_outside_repository`：1 条（ADR-0005，正文 `../_project_memory_launcher.py`）

合计 **25 条**，与基线中同位置、同 code 的多重集完全一致（即本次改动未新增也未消除它们）。要让这 25 条归零，只能改写 ADR 正文中的路径引用，而第 2 节与第 3 节均禁止改正文——这正是第 6 节第一项停止条件。

处置：已停止在「宣称完成」这一步，未改任何正文、未改审计规则或测试口径，提交仅含任务卡授权的 7 个文件。第 3、5、6 条数字与预期完全一致；第 4 条如何取舍请 PM-01 明确（例如把它解释为「不再有 `adr_*` 元数据类 finding」——该类实测为 0）。

## 4. NOT VERIFIED

- 未在 CI 运行；上述 pytest 结果仅为本机工作区外解释器实测。
- 未复核 7 个 ADR 正文内容是否仍与当前代码一致；本次只核对第 5 行 Issue 号与任务卡一致。
- 未验证 `unknown_document_status` 剩余 4 条（ADR 之外的文档）是否应处理；任务卡明确本轮不处理。
- 未验证 GitHub 渲染、CRLF 重新检出后的结果；插入内容沿用各文件原有 LF 行尾。
- 未 push、未建 PR、未打 tag、未创建 Goal/Run。
- 工作区两份旧未跟踪文件（`PM02_COLD_START_VALIDATION.md`、`tasks/PM02-cold-start-handoff-20261029T150500Z.md`）保持原样。

## 5. 复核入口

- 分支 `docs/adr-metadata-20261030`，提交 `3426764`，基线 `f033a6c`。
- 建议 PM-03 重跑：`git diff f033a6c..3426764`、第 2 节的多重集对比脚本、`reconcile --fail-on high`。
- 本 handoff 只是执行事实记录，不构成 PASS；第 4 条的解释权属 PM-01 / 人类。
