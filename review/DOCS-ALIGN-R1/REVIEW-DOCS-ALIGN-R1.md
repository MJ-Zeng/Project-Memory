# DOCS-ALIGN-001 独立窄复核报告（PM-03，第三轮）

- 复核对象：`origin/docs/align-20261030`
  - 变更提交：`f88aafe341b8d9fb88e668e69e6c7c57830d97cd`（父 `1eaa3f4`）
  - handoff 提交：`15fa8c7e30da39ba1e89090c6cd52f3aeb4c7711`（父 `f88aafe`，分支顶点）
- 基线：`1eaa3f498074d091bb3996faec3534d56ac12f4b`（`origin/dev/v1.0`，提交时实测与派单一致）
- 复核时间：2026-10-30
- 复核环境：Windows 11 AMD64；Python 3.12.4；pytest 9.2.0；解释器位于复核 worktree 之外（`review/HYGIENE-R1/venv/Scripts/python.exe`）
- 隔离方式：在 `pm-pilot-03` 克隆中 `git fetch origin docs/align-20261030 dev/v1.0`，建立 detached worktree：`rel-base`=`1eaa3f4`、`rel-target`=`f88aafe`、`rel-tip`=`15fa8c7`；PM-02 目录未改动。
- 输入边界：PM-02 handoff 仅作输入，未用于任何结论；下列每条结论对应本轮自行执行的命令与输出。
- 结论：**PASS**（附口径偏差，见 §8）

---

## 1. 变更范围（派单第 1 条）

```bash
git show --stat f88aafe
git diff --name-status 1eaa3f4..f88aafe
```

```text
 README.md                                          |  4 +-
 docs/CURRENT_STATE.md                              |  3 +-
 docs/TEST_REPORT.md                                |  3 ++
 pilot/PILOT_R1_CHARTER.md                          | 56 +++++++++++++++++++++++
 pilot/STATUS.md                                    |  3 ++
 skill/project-memory/SKILL.md                      |  3 +-
 skill/project-memory/references/data-contracts.md  |  2 +
 skill/project-memory/references/workflows.md       |  2 +
 8 files changed, 72 insertions(+), 4 deletions(-)
```

恰为任务卡 §2.1–§2.8 的 8 个文件。handoff 提交 `15fa8c7` 另加 `tasks/PM02-docs-align-handoff-20261030T015311Z.md`（+67，属允许项）。

禁止路径检查（基线与顶点两侧均无输出）：

```bash
git diff --name-only 1eaa3f4..f88aafe | grep -E '^(project_memory/|tests/|\.project-memory/|evidence/|bin/|_project_memory_launcher\.py|docs/decisions/)'
git diff --name-only 1eaa3f4..15fa8c7 | grep -E '^(同上)'
# NONE / NONE
```

## 2. 逐条内容核对（派单第 2 条）

### 2.1 README.md

diff 仅 3+/1-：

- 快速开始测试命令 `python3 -m unittest discover -s tests -v` → `python3 -m pytest -q`（第 14 行）；
- `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python3 -m pytest -q` 发布门槛原样保留（第 35 行）；
- audit 段落新增边界句（第 133 行）：`audit` 是本地防篡改检测与文档一致性提示，不构成对外可采信的审计留痕。

其余 `unittest` 出现位置（第 63/74/94/98 行）属 `test-run` 示例命令，按“其余内容不动”保持原样，与“快速开始测试命令”修改不冲突。

### 2.2 docs/TEST_REPORT.md / 2.3 pilot/STATUS.md（只增不改）

```bash
git diff --numstat 1eaa3f4..f88aafe -- docs/TEST_REPORT.md pilot/STATUS.md
# 3  0  docs/TEST_REPORT.md
# 3  0  pilot/STATUS.md
tail -n +4 <target> | cmp - <baseline>
# 两个文件均 IDENTICAL
```

两处均为文件头新增 2 行引用 + 1 行空行分隔，删除 0 行，原有正文逐字节不变。新增文字与任务卡 §2.2/§2.3 完全一致。

### 2.4 skill/project-memory/SKILL.md

diff 仅 1 处 hunk（+1/−2）：原 `externally_verified`、`human_approved` 两条说明替换为任务卡指定的一条，明确 `verify --evidence-level` 只接受 `agent_claimed` 与 `locally_observed`；`agent_claimed`、`locally_observed` 两条原文保留，其它流程未改。

### 2.5 / 2.6 两份 references

`data-contracts.md`、`workflows.md` 各在证据级别表后新增同一句 CLI 约束（各 +2，含空行），表中其余描述未改。

### 2.7 docs/CURRENT_STATE.md（仅一行 + 允许的边界句）

- 审计计数行替换为任务卡 §2.7 指定文本（第 34 行），与实测 `40 / high 0 / medium 16 / low 24` 一致；
- “已知限制”原无 audit 边界表述，按 §2.7 补一句，与 README 新增句一致；
- frontmatter 与基线逐行相同（`diff` 前 9 行无差异）；总行数 48（≤80）。
- 净改动 +2/−1，未触及其它行。

### 2.8 pilot/PILOT_R1_CHARTER.md（新增）

- 行数 **56**（≤90）；
- frontmatter 与任务卡块逐字段一致：`id` / `kind` / `title` / `status` / `owner` / `updated_at` / `last_verified_at`，`status: "current"`；
- Markdown 链接 0、URL 0（`grep -Eic` 均为 0）；
- 七节齐全：适用场景与边界、角色与独立性、信任边界、预期终态、门禁、度量、退出与停止条件；
- 路径仅引用 `docs/CURRENT_STATE.md`。

## 3. 审计多重集（派单第 3 条）

```bash
# rel-base (1eaa3f4) 与 rel-target (f88aafe)
./bin/project-memory audit --scope current   # 均 exit 0
```

| 指标 | 基线 1eaa3f4 | 目标 f88aafe |
|---|---|---|
| 总数 | 40 | 40 |
| high | 0 | 0 |
| medium | 16 | 16 |
| low | 24 | 24 |
| 新增三元组 | — | **0** |
| 减少三元组 | — | **0** |

两份 findings 的 `(severity, code, location)` 多重集逐项相同；减少项为 0，无需列因。code 分布：medium `reference_authority_mismatch` 14、`reference_outside_repository` 1、`broken_document_reference` 1；low `ambiguous_reference` 14、`broken_reference` 4、`dynamic_artifact_reference` 2、`unknown_document_status` 4。

- `location == pilot/PILOT_R1_CHARTER.md` 的 finding：**0**；
- `entry_doc_*` 类 finding：**0**；
- 顶点 `15fa8c7`（含 handoff）审计同为 40（0/16/24），handoff 未引入 finding。

`reconcile --fail-on high`（rel-target）：

```text
EXIT=0
state: needs_attention
counts: {'high': 0, 'medium': 16, 'low': 24}
items: 40
```

`audit --scope current --fail-on high` 亦 exit 0、stderr 为空。

## 4. 双门槛回归（派单第 4 条）

在 `rel-target` 内、worktree 外解释器：

| 门槛 | 结果 | 耗时 | 退出码 |
|---|---|---|---|
| 默认 `pytest -q` | 253 passed, 2 skipped | 206.60s | 0 |
| `PROJECT_MEMORY_REQUIRE_OPENSSL=1 pytest -q` | 253 passed, 2 skipped | 147.60s | 0 |

2 个 skip 为既有 Windows 符号链接跳过。

## 5. 事实核对（派单第 5 条）

以 `rel-target` 的实现代码为证据：

- `project_memory/cli.py:267-271`：`verify --evidence-level` 的 `choices` 只有 `agent_claimed`、`locally_observed`，注释标明 R-1 有意收紧。与 SKILL、两份 references、章程所述一致。
- `project_memory/coordination.py:2216-2220`：本地写出的 pass 记录状态最多为 `MANUAL_REVIEW_REQUIRED`，`verified = False`；`coordination.py:2295-2298` 的 caveat 明示“最多 `MANUAL_REVIEW_REQUIRED`，verified 恒为 false”，且 CLI 不接受 `externally_verified` / `human_approved` 作为证据级别。与章程第四节一致。
- `project_memory/coordination.py:1545`：`approved_by` 记录为 `claimed_unverified`。与章程第三节一致。
- `coordination.py:112-114`、`1276-1278`：验证记录仅在受保护信任锚签名且 `verification_authority` 判定 trusted 时才计为已验证；`_achieved_status` 需 anchor 签名的 checkpoint。与章程第四节“单用户主机上 `achieved`/`VERIFIED` 不可达”的表述一致（该结论在 v1.0.0 复核中已做运行时验证，本轮仅做代码级复核）。
- 实测：基线审计恰为 `40/0/16/24`，`reconcile --fail-on high` 与 `audit --scope current --fail-on high` 均 exit 0。与 CURRENT_STATE 第 34 行及章程第五节一致。
- `audit` 的“本地防篡改检测与文档一致性提示”表述与实现范围一致（审计只在本地读仓库并输出提示，不做外部留痕）。

未发现 `docs/CURRENT_STATE.md` 或章程与实现冲突的事实。

## 6. 分支与远端状态

```bash
git ls-remote origin refs/heads/docs/align-20261030 refs/heads/dev/v1.0
# 15fa8c7...  refs/heads/docs/align-20261030
# 1eaa3f4...  refs/heads/dev/v1.0
```

任务卡 §3 明确允许 push 该分支；实测已推送且顶点为 `15fa8c7`。`dev/v1.0` 仍为基线 `1eaa3f4`，未见合并或改写。未见 PR/Release/tag 动作（远端 ref 未显示；未通过 API 核验，见 NOT VERIFIED）。

## 7. 交付与边界

- 变更提交 `f88aafe` 为 1 个 commit；handoff 为单独 commit。
- 未改动产品代码、测试、`.project-memory/`、`evidence/`、`bin/`、启动器、ADR、`pilot/PILOT_CLOSEOUT.md`。
- 未创建 Goal/Run。
- 本报告不构成合并批准；PR 与合并由 PM-01/人类处理。

## 8. 口径偏差清单

1. **章程 frontmatter 数量表述**：派单称“六项”，任务卡 §2.8 的 YAML 块实际列 7 个字段（`id`、`kind`、`title`、`status`、`owner`、`updated_at`、`last_verified_at`）。实测 7 项全部存在且取值与卡一致；按 7 项验收。建议后续统一为“七项”。
2. **TEST_REPORT/STATUS 行数**：卡写“最前面加两行（空行分隔）”，实际为 2 行引用 + 1 行空行 = 3 行新增。语义一致，删除 0 行、正文逐字节不变。
3. **CURRENT_STATE 改动**：卡 §2.7 首句称“仅一行”，随后又允许补边界句；实际为 1 行替换 + 1 行新增（净 +1）。符合 §2.7 全文，建议卡面措辞统一。
4. **README 中残留 `unittest`**：快速开始命令已改 pytest；`test-run` 示例仍用 `python -m unittest`，属“其余内容不动”的保留项，不作为偏差缺陷，仅记录以免后续误判。
5. **派单“减少逐条列因”**：实测减少为 0，无条目可列。

## 9. 结论

**PASS。** 8 文件范围与内容逐条符合任务卡；两份历史文件只增不改且正文逐字节不变；章程 frontmatter、行数、七节、无链接/URL 均满足；审计基线 `40/0/16/24` 与目标完全一致，新增 0、减少 0，章程无 finding、无 `entry_doc_*`；`reconcile --fail-on high` 与审核门槛 exit 0；双门槛 253/2、exit 0；文档事实与实现代码一致。偏差均为卡面/派单措辞层面（§8），不影响验收。

本报告仅为复核结论，不是合并批准或人类批准。

**NOT VERIFIED**

- 未在 CI 中运行；仅本机独立 worktree 验证。
- 测试所用 venv 为先前复核已创建的 worktree 外解释器，未为本轮重新安装依赖。
- 未通过 GitHub API 核验是否存在 PR/Release/tag；仅以 `git ls-remote` 确认 `dev/v1.0` 与分支 ref 状态。
- 未在本轮端到端执行 `verify` 观察 exit 2；该行为在 v1.0.0 复核中做过运行时验证，本轮仅做代码级核对。
- 未重新验证 `wsl.exe` 可被环境变量/PATH 替换这一历史事实；本轮只确认入口文档未改动该表述。
- 未验证章程中的过程性度量（上下文恢复 ≤15 分钟、未授权写入 0 次等）——属人类执行记录，不可由仓库静态验证。
- 未观察 PM-02 工作区实时状态；未验证提交签名（提交仅为身份声明）。
- 未在其他操作系统验证；仅 Windows 11 AMD64。
