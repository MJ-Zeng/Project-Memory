---
handoff_id: HO-B0-R1-SUP
schema: pilot-handoff/v1
task_id: B0
issue: see dispatch Issue
goal_id: G-B0
round: 1
from_role: PM-01
to_role: PM-02
base_sha: see dispatch Issue
candidate_sha: null
branch: fix/b0-repo-identity
pr: null
criteria_sha256: 81e20cf8c16a30c904e925e195d7748bce5a11f24a62f5c16a3ec15b895061c0
agent_label: "PM-01 Supervisor <pm01@pilot.invalid>"   # 自述，不是认证
session_id: pm01-setup-20261028
model: dsh/deepseek-flash
created_at: 2026-10-28T09:35:00+08:00
status: draft
---

# PM-01 → PM-02 派发交接（B0）

> 这是入口，不是修复方案。PM-02 必须自己从任务卡、复现步骤与代码得出结论。

## 1. 任务与范围

- 任务卡：`pilot/rounds/B0/task.md`
- 目标：让执行收据在同一仓库的不同 Clone/路径之间可移植，同时拒绝不同仓库的收据。
- 允许修改：见任务卡 §5。
- 非目标：B1–B5、Release、自动合并。

## 2. 阅读顺序

1. `pilot/README.md`
2. `pilot/ROLES.md`
3. `pilot/ROUND_PROTOCOL.md`
4. `pilot/rounds/B0/task.md`
5. `pilot/reference/RC3_B1_B3.md`
6. `.project-memory/goals/G-B0.json`
7. `pilot/STATUS.md`

## 3. 不得假设

- 不存在 `main` 分支；基线是 B0 dispatch 合并提交。
- 不能修改任务卡、判据、探针、评测器。
- 不能删除/跳过既有测试。
- 不能通过环境变量静默覆盖仓库身份而不写 ADR。
- 不能让不同仓库的收据互相通过。
- 不能把“测试通过”写成“安全验收通过”。
- 不能自行合并 PR 或宣布 Goal `achieved`。

## 4. 未决问题（由 PM-02 回答并写 ADR）

- 稳定仓库身份用 remote+root commit、config UUID，还是移除 `repo_id`？
- 无 remote 的本地仓库如何回退？
- 旧收据如何标记/迁移，才不会被误当作跨路径证据？
- 残余风险是什么（仓库复制、remote 伪造、config 篡改）？

## 5. 污染记录

- human_relay: []
- missing_artifacts: []
- stale_artifacts: []
- unauthorized_reads: []

## 6. 下一步

- PM-02 先做冷启动恢复，写 `context-recovery-pm02.md`。
- 若 Issue/任务卡/hash 未就绪：`BLOCKED`。
- 若环境/工具缺失：`BLOCKED`，不要静默绕过。
