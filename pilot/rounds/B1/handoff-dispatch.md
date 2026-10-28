---
handoff_id: HO-B1-R1-SUP
schema: pilot-handoff/v1
task_id: B1
issue: see dispatch Issue
goal_id: G-B1
round: 1
from_role: PM-01
to_role: PM-02
base_sha: see dispatch Issue
candidate_sha: null
branch: fix/b1-openssl-verifier
pr: null
criteria_sha256: 0fdc9469456b81bae26a3c29385f1745222e16b19211e27d4d04a418ef3be08d
agent_label: "PM-01 Supervisor <pm01@pilot.invalid>"   # 自述，不是认证
session_id: pm01-setup-20261028
model: dsh/deepseek-flash
created_at: 2026-10-28T09:10:00+08:00
status: draft
---

# PM-01 → PM-02 派发交接（B1）

> 这是**入口**，不是修复方案。PM-02 必须自己从任务卡、探针、RC3 摘要和代码得出结论。

## 1. 任务与范围

- 任务卡：`pilot/rounds/B1/task.md`
- 目标：阻断 `PATH` / `PROJECT_MEMORY_OPENSSL` 替换验签器，同时保持有效签名可用。
- 允许修改：见任务卡 §3。
- 非目标：B2/B3/B4/B5、Release、自动合并。

## 2. 阅读顺序

1. `pilot/README.md`
2. `pilot/ROLES.md`
3. `pilot/ROUND_PROTOCOL.md`
4. `pilot/rounds/B1/task.md`
5. `pilot/reference/RC3_B1_B3.md`
6. `pilot/kit/b1/README.md`
7. `.project-memory/goals/G-B1.json`
8. `pilot/STATUS.md`

## 3. 不得假设

- 不存在 `main` 分支；基线是 `dev/v1.0` 的脚手架提交。
- 不能读 `/etc/pm-rc3-review/key-a.pem`，不能自行签名。
- 不能修改任务卡、判据、探针、评测器。
- PM-01 不会通过聊天补充设计；需要的信息必须在工件里，缺失就记 `BLOCKED`/`NEEDS_INFO`。
- 不能把“测试通过”写成“安全验收通过”。
- 不能自行合并 PR 或宣布 Goal `achieved`。

## 4. 未决问题（故意不在提示词里回答）

- 验签器应该固定在哪个路径？如何校验其完整性？
- 如果固定二进制缺失或被替换，应该 fail closed 还是回退？为什么？
- 如何在不破坏既有测试的前提下证明“有效签名仍可用”？
- 哪些残余风险（如 `LD_PRELOAD`、root 妥协）必须写进 ADR？

这些问题由 PM-02 从任务卡、代码与探针中自行回答，并写进 ADR/Handoff。

## 5. 污染记录

- human_relay: []
- missing_artifacts: []
- stale_artifacts: []
- unauthorized_reads: []

## 6. 下一步

- PM-02 先做冷启动恢复，写 `context-recovery-pm02.md`。
- 若 Issue/任务卡/hash 未就绪：`BLOCKED`，不要自行补建。
- 若环境/工具包缺失：`BLOCKED`，不要用替代路径静默绕过。
