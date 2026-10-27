# B1 轮次协议

## 1. 状态机

```
draft → dispatched → in_dev → candidate_frozen → in_review
      → reviewed → human_decision → closed
```

| 状态 | 进入条件 | 离开条件 |
|---|---|---|
| `draft` | PM-01 起草任务卡 | 判据冻结 + 人类知会 |
| `dispatched` | Issue 创建；任务卡推送；PM-02 启动 | PM-02 开始 Run |
| `in_dev` | PM-02 建分支 | 候选 commit + Handoff + 测试 |
| `candidate_frozen` | PM-01 核对 SHA/字段 | PM-03 开始 |
| `in_review` | PM-03 独立检出 | 审查报告 + 结论 |
| `reviewed` | PM-03 完成 | 人类决定 |
| `human_decision` | 人类审阅 | 合并/拒绝/要求整改 |
| `closed` | 决定记录 | 下一轮或结束 |

## 2. 门禁

- **派发门禁**：Issue、任务卡 SHA-256、基线 SHA、环境、授权、密钥全部就绪。任务卡必须已在 `dev/v1.0` 上合并；Issue 记录该 commit 上的 SHA-256；派发后修改任务卡 = 本轮作废。
- **候选门禁**：候选 SHA 可解析；测试命令/退出码/日志齐全；Handoff 必填字段完整；diff 未越界。
- **审查门禁**：PM-03 从候选 SHA 独立重建；原始探针 + 正向 fixture 重跑；结论明确。
- **人类门禁**：人类确认关键证据；明确批准/拒绝；记录范围（“合并”≠“发布”）。

## 3. 判据冻结

派发前计算任务卡 SHA-256：

```bash
sha256sum pilot/rounds/B1/task.md        # WSL/Linux
# 或 Windows:
Get-FileHash pilot/rounds/B1/task.md -Algorithm SHA256
```

把哈希写入 Issue、Goal 与 `handoff-dispatch.md`。派发后修改任务卡：本轮作废，重新派发并记录原因。

## 4. 统一 Handoff 模板

同一模板用于 PM-01 → PM-02（派发）与 PM-02 → PM-03（交付），由 `from_role` / `to_role` 区分。

- **权威记录**：`.project-memory/handoffs/B1/<run-id>.json`（遵循 `agent-handoff.schema.json`），随分支提交。
- **人类可读视图**：`pilot/rounds/B1/handoff-<run-id>.md`，字段必须与 JSON 一致。
- 冲突时：**JSON 为准**，差异记为 Defect。

```markdown
---
handoff_id: HO-B1-R1-DEV
schema: pilot-handoff/v1
task_id: B1
issue: <GitHub Issue URL>
goal_id: G-B1
round: 1
from_role: PM-02
to_role: PM-03
base_sha: <40 hex>
candidate_sha: <40 hex>
branch: fix/b1-<slug>
pr: <PR URL | "not opened: unauthorized">
criteria_sha256: <task.md 的 SHA-256>
agent_label: "PM-02 Developer <pm02@pilot.invalid>"   # 自述，不是认证
session_id: <会话标识：客户端提供，或启动时间 + 工作目录>
model: <provider/id>
created_at: <ISO 8601>
status: ready_for_review | blocked | needs_info
---

## 1. 任务与范围（一句话 + 任务卡链接）
## 2. 我实际做了什么（文件、commit、diffstat）
## 3. 我运行了什么
| # | 命令 | 目录 | 环境 | 退出码 | 日志 | 日志 SHA-256 |
## 4. 证据索引
| 文件 | SHA-256 | 证明什么 | 不证明什么 |
## 5. 我没有验证什么（NOT VERIFIED）
## 6. 已知风险与可能的绕过（主动披露）
## 7. 给审查者的读法（10 分钟路径）
## 8. 未决问题 / 阻塞
## 9. 下一步
## 10. 事实清单（必须与 JSON 一致）
- base_sha:
- candidate_sha:
- branch:
- tests_summary:
- verdict_claim: (self-claimed, not verified)
- next_action:
## 11. 污染与偏差记录
- human_relay: []
- missing_artifacts: []
- stale_artifacts: []
- unauthorized_reads: []
- time_spent_minutes:
## 12. 签署
我确认以上为我的真实观察；未运行的项目已列为 NOT VERIFIED。
```

必填字段：`handoff_id, schema, task_id, issue, goal_id, round, from_role, to_role, base_sha, candidate_sha, branch, criteria_sha256, agent_label, session_id, model, created_at, status, completed, remaining, blockers, tests, evidence, not_verified, open_questions, next_actions, contamination, facts`。

- 缺任一字段：Handoff 不完整，交接不计成功。
- `N/A` 只在有原因时允许；空数组表示“确实没有”，不是“忘了写”。
- 每个 SHA 必须能 `git cat-file -t <sha>` 解析；每个证据路径必须在候选 SHA 上存在。
- 每个测试必须有 `command + exit_code`；没有退出码的“通过”按 E0 处理。

## 5. PR 模板

```markdown
## 关联 Issue
Closes #<issue>

## 基线 / 候选
- Base SHA: <base>
- Candidate SHA: <candidate>
- Task card SHA-256: <criteria>

## 修改内容
- `<file>`: 原因

## 测试
- 命令:
- 环境: Windows / WSL / Python
- 结果: <n> passed, <n> failed, <n> skipped
- 退出码:
- 日志: <path> (SHA-256: <hash>)

## 证据清单
| 文件 | SHA-256 |
|---|---|

## NOT VERIFIED
- ...

## Handoff
- <path>

## 人类批准
- [ ] 人类已批准（程序记录，不是 GitHub approval）
```

## 6. 人类决定记录

`pilot/rounds/B1/decision.md`：

```markdown
Decision: APPROVE_MERGE | REJECT | REQUEST_CHANGES | ACCEPT_AS_PILOT_EVIDENCE | BLOCKED
By: <human>
Date: <ISO>
Basis: <reviewed evidence: PR, review report, probe JSON, ...>
Scope: <what this authorizes; explicitly not a release approval>
Conditions: <if any>
```

`ACCEPT_AS_PILOT_EVIDENCE` 只表示“接受本轮试点证据”，不等于合并，也不等于 Goal `achieved`。

## 7. 冷启动检查（每轮一次）

- 执行者：未参与本轮的临时只读会话，或人类本人。
- 输入：Issue、任务卡、PR、Handoff、`STATUS.md`、候选 SHA；不得读三个角色的聊天。
- 任务：回答 6 项事实（任务、基线、候选、判据、当前结论、下一步），指出决定性工件。
- 记录：正确数 / 6、耗时、必须追问的问题、过期/矛盾记录。
- 不写入仓库；结果由 PM-01 记入轮次记录。

## 8. 关闭与下一轮

人类决定后，PM-01：

1. 写 `decision.md`。
2. 更新 Issue（评论、标签；仅授权时关闭）。
3. 更新 `STATUS.md`，每个事实带 `as_of`、`verified_by`。
4. 写 `handoff-close.md`。
5. 若 FAIL/REQUEST_CHANGES：创建 Defect 与 **B1 的下一整改轮次**；不得降判据、删失败记录。B2 仍需 B1 关闭后另行授权。
6. 若 PASS 且人类合并：记录合并 commit SHA；仍不得宣布 Goal `achieved` 或 Release。
7. 只有人类明确同意后，才创建 B2 Issue。

## 9. 指标采集

每轮记录以下字段（分子/分母 + 数据源）：

| 指标 | 分子/分母 | 采集时点 |
|---|---|---|
| CRR 复述正确率 | 正确事实数 / 6 | 接手开场 |
| TT 接手时间 | 会话开始 → 首次正确复述（分钟） | 接手开场 |
| RQ 补问率 | 本应存在于工件的补问次数 / 交接次数 | 轮末 |
| HR Handoff 完整率 | 存在必填字段数 / 必填字段总数 | 候选门禁 |
| HS 错误/过期字段 | 绝对数 | 候选门禁 |
| IR 独立复现率 | PM-03 成功复现项 / 必测项 | 审查门禁 |
| FA 事实一致率 | 三角色一致事实项 / 6 | 轮末 |
| DT 分歧定位时间 | 发现分歧 → 找到来源（分钟） | 事件时 |
| EI 错误升级率 | 错误升级证据数 / 被检查证据数 | 轮末 |
| UW 未授权远端写 | 绝对数 | 持续 |
| TC 链路完整率 | 存在链路段 / 应存在链路段 | 轮末 |
| DY 审查发现数 | 可复现新问题数 / 轮 | 审查结束 |
| DV 开发-审查分歧 | 不一致项 / 对比项 | 轮末 |
| 任务结果 | PASS/FAIL/BLOCKED/NOT VERIFIED | 审查结束 |

不计算“效率提升”；n=3 只做描述性汇总。

## 10. 停止条件

- 发现新的高危绕过；
- 未授权远端写 / 自批准 / 自动合并；
- 越界修改任务卡、判据、探针、测试；
- 测试环境不可用且 15 分钟内无法恢复；
- 连续两轮结论相同且 Defect 未减少（无进展）；
- 需要人类授权才能继续（推送、密钥、合并）。
