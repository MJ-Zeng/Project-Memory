# HYGIENE-R1-001 窄复核报告（PM-03）

- 复核对象：`docs/hygiene-20261030` @ `fd12d9a882edfcc8aaac169dac2f5b7ad21c9af5`
- 基线：`f033a6c517cfde3eebb586b07f770d94b2d2c3b7`（`v1.0.0`）
- 提交链：`6d85016` → `13dd717` → `6889ec6` → `fd12d9a`（父链已用 `git rev-list --parents` 逐项确认）
- 复核时间：2026-10-30
- 复核环境：Windows 11 AMD64；Python 3.12.4（Anaconda 打包）；pytest 9.2.0；独立 venv 位于 `review/HYGIENE-R1/venv`
- 隔离方式：以临时对等远端把 PM-02 的本地分支 `docs/hygiene-20261030` 取到 `pm-pilot-03` 的独立克隆，检出 detached worktree `review/HYGIENE-R1/rel-base`（`f033a6c`）与 `rel-head`（`fd12d9a`）；PM-02 工作区未被改动。
- 输入边界：PM-02 的 handoff 仅作为输入，未作为本报告任一结论的依据；以下每条结论都对应本报告内自行执行的命令与输出。
- 结论：**PASS**（附一项口径差异说明，见 §9）

---

## 1. 变更范围（dispatch 第 1、7 条）

命令：

```bash
git diff --stat f033a6c..fd12d9a
git diff --name-status f033a6c..fd12d9a
git diff --name-only f033a6c..fd12d9a | grep -E '^(project_memory/|tests/|bin/|skill/|evidence/)'
```

输出：

```text
 .project-memory/config.json                        |  2 +-
 docs/CURRENT_STATE.md                              | 47 ++++++++++++
 pilot/PILOT_CLOSEOUT.md                            |  2 +
 .../PM02-docs-hygiene-handoff-20261030T010538Z.md  | 84 ++++++++++++++++++++++
 4 files changed, 134 insertions(+), 1 deletion(-)

M	.project-memory/config.json
A	docs/CURRENT_STATE.md
M	pilot/PILOT_CLOSEOUT.md
A	tasks/PM02-docs-hygiene-handoff-20261030T010538Z.md
```

禁止路径检查结果为 `NONE`：`project_memory/`、`tests/`、`bin/`、`skill/`、`evidence/` 零改动。唯一删除行是 `config.json` 中 `"entry_doc": null` 的替换，符合任务卡变更 3。

分支未推送：

```bash
git -C rel-head ls-remote origin 'refs/heads/docs/*'   # 无输出
git -C rel-head ls-remote origin | grep -i hygiene      # NONE
```

## 2. 入口文档契约（dispatch 第 2 条）

`docs/CURRENT_STATE.md` 共 47 行（≤80）。frontmatter 实测：

```yaml
id: "DOC-CURRENT-STATE"
kind: "canonical"
title: "Project Memory 当前状态（v1.0.0）"
status: "current"
owner: "MJ-Zeng"
updated_at: "2026-10-30"
last_verified_at: "2026-10-30"
```

机械检查：Markdown 链接 0、URL 0、`ADR-[0-9]` 编号引用 0（`grep -Eic` 均为 0）。正文含任务卡要求的 6 节（一句话结论、当前发布事实、预期行为、已知限制、历史提示、阅读顺序），路径均以反引号包裹。未发现与已核验事实冲突的内容：发布基线、annotated 未签名 tag、两条门槛 253/2、证据 24/24、`verify` exit 2 与 `MANUAL_REVIEW_REQUIRED`、信任锚约束、`claimed_unverified`、`wsl.exe` 可被环境变量/PATH 替换、审计 82 条分布，均与本轮独立测量或 v1.0.0 复核记录一致。

配置：

```text
8:  "entry_doc": "docs/CURRENT_STATE.md",
```

`json.load` 解析成功，`entry_doc = docs/CURRENT_STATE.md`。diff 中该键之外无其它改动。

## 3. 历史文件只增不改（dispatch 第 3 条）

```bash
git diff f033a6c..fd12d9a -- pilot/PILOT_CLOSEOUT.md
```

输出为 2 行新增（历史标注 + 空行）、0 行删除：

```text
@@ -1,3 +1,5 @@
+> 历史结论（2026-10-28，B0–B2 试点阶段）：“v1.0：NO-GO”仅针对该阶段，已被 2026-10-29 发布的 v1.0.0 取代。原文保留，不作修改。
+
 # Project Memory 多 Agent 协作试点 — 收尾报告
```

原文仍在：

```text
119:- **v1.0：NO-GO。**
```

## 4. 审计多重集对比（dispatch 第 4 条）

命令（各自在对应 worktree 内、使用独立 venv）：

```bash
./bin/project-memory audit --scope current > out/audit-base.json   # f033a6c, exit 0
./bin/project-memory audit --scope current > out/audit-head.json   # fd12d9a, exit 0
```

按 `(severity, code, location)` 多重集比较（`location` 归一为正斜杠；仅比较三元组，不比较 `generated_at` 等易变字段）：

| 指标 | 基线 f033a6c | 头部 fd12d9a |
|---|---|---|
| 总数 | 84 | 82 |
| high | 14 | 14 |
| medium | 25 | 23 |
| low | 45 | 45 |
| 新增 | — | **0** |
| 减少 | — | **2** |

减少的两条（完整 finding）：

```text
('medium','broken_document_reference','docs/TEST_REPORT.md')      message: 缺失：docs/CURRENT_STATE.md
('medium','broken_document_reference','docs/TUTORIAL.zh-CN.md')   message: 缺失：docs/CURRENT_STATE.md
```

减少原因已独立确认，不是规则放宽：基线中 3 条 `broken_document_reference`，其中 2 条的 message 明确为“缺失：docs/CURRENT_STATE.md”；这两份文档在基线中已写入对该路径的引用，而文件此前不存在。`fd12d9a` 创建了该文件，这两条引用自然可解析。剩余 1 条仍指向 `doc/new_doc/00_项目总览.md`，与本次变更无关，保留。

头部其它必要条件：

- `location == docs/CURRENT_STATE.md` 的 finding：0 条。
- `entry_doc_*` 类 finding：0 条。

头部 82 条分布（自证入口文档第 34 行陈述）：

- high 14 = `adr_invalid_id` 7 + `adr_invalid_status` 7，均为 7 个 ADR 文件各 1 条；
- medium 23 = `adr_missing_provenance` 7 + `reference_authority_mismatch` 14 + `reference_outside_repository` 1 + `broken_document_reference` 1；
- low 45。

## 5. 回归测试（dispatch 第 5 条）

在 `rel-head`（`fd12d9a`）内、worktree 之外的解释器路径 `review/HYGIENE-R1/venv/Scripts/python.exe` 运行：

| 门槛 | 命令 | 结果 | 耗时 | 退出码 |
|---|---|---|---|---|
| 默认 | `python -m pytest -q` | 253 passed, 2 skipped | 160.74s | 0 |
| OpenSSL 强制 | `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q` | 253 passed, 2 skipped | 159.46s | 0 |

2 个 skip 为既有的 Windows 符号链接相关跳过，与基线一致。

## 6. reconcile 状态（dispatch 第 6 条）

```bash
./bin/project-memory reconcile --fail-on high
```

结果：退出码 **2**，`state = "needs_attention"`，`counts = {high:14, medium:23, low:45}`，`items` 82 条，`defects: 0`。与既有 14 条 high（ADR 元数据）一致，属预期结果，不视为本轮失败。

审计规则与冻结区未被调整：变更仅 4 个文件，`project_memory/`、`.project-memory/` 下除 `config.json` 的 `entry_doc` 外无改动；`config.json` diff 仅一行键值替换。

## 7. 污染与越界检查（dispatch 第 7 条）

- 禁止路径（`project_memory/`、`tests/`、`bin/`、`skill/`、`evidence/`）：0 改动。
- 任务卡禁止改动的 `README.md`、`CHANGELOG.md`、`docs/OPERATIONS.zh-CN.md`、`docs/TEST_REPORT.md`、`pilot/STATUS.md`：0 改动。
- 分支未推送到 `origin`（`git ls-remote` 无匹配）。
- 未创建 Goal/Run；复核全程未写入 PM-02 工作区。

## 8. 交叉核对任务卡与 dispatch 的口径差异

- 任务卡验收第 2 条写作“findings 总数与分布仍为 84 / 14 / 25 / 45”，而 dispatch 预期 “84/14/25/45 → 82/14/23/45”。
- 实测为 **82 / 14 / 23 / 45**，新增 0，减少 2 条且原因已确认（见 §4）。任务卡该条在“新增 `docs/CURRENT_STATE.md`”这一前提下无法同时成立——文件创建必然消解指向它的坏链。因此按 dispatch 口径判定通过，同时提示 PM-01：任务卡该条措辞需以实测口径修订，避免后续复核误判为回归。
- 入口文档第 34 行已如实写明“82 条（本文件加入前为 84）”，与实际一致。

## 9. 结论与限制

**结论：PASS。** 八项 dispatch 检查全部由本轮独立命令复现：范围 4 文件、入口文档契约成立、历史文件只增不改、审计新增 0（2 条减少为预期坏链消解）、两条测试门槛 253/2 且 exit 0、reconcile 保持 exit 2 `needs_attention`、无禁止路径改动、分支未推送。唯一偏差是任务卡验收第 2 条的字面数字（84），已在 §8 说明其不可满足性与实测依据；是否据此调整任务卡由 PM-01 决定。

本报告不构成合并批准。合并与发布决策权在人类。

**NOT VERIFIED**

- 未在 CI 中运行：仅在本机独立 venv 执行，未观察 GitHub Actions 结果。
- 未复验其他文档的过期内容：`README.md`、`CHANGELOG.md`、`docs/OPERATIONS.zh-CN.md` 等的语义准确性不在本次窄复核范围；仅验证审计层面无新增 finding。
- 未重新核验 v1.0.0 的 release 身份（tag 对象、GitHub Release 状态）与证据包：本窄复核引用的是本工作区先前 v1.0.0 复核的已核验记录，入口文档中的发布事实未在本轮重新取证。
- 未验证 PM-02 工作区的实时状态：仅验证经对等远端取到的 `fd12d9a`；其后 PM-02 本地分支是否移动、工作区是否干净，均未观察。
- 未验证提交作者身份真实性：提交未签名，`author` 仅为声明。
- 未在其他操作系统验证：测试仅 Windows 11 AMD64。
- 未验证 `docs/hygiene-20261030` 在未来推送后的远端内容（当前远端无此分支）。
