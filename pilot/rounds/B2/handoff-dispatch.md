---
handoff_id: HO-B2-R1-SUP
schema: pilot-handoff/v1
task_id: B2
issue: https://github.com/MJ-Zeng/Project-Memory/issues/12
goal_id: G-B2
round: 1
from_role: PM-01
to_role: PM-02
base_sha: see dispatch Issue
candidate_sha: null
branch: fix/b2-receipt-provenance
pr: null
criteria_sha256: 3617dab01ca01c05ba2cb9ec87b38eae2622a6b69b480b2e7abb1c0881a7900e
agent_label: "PM-01 Supervisor <pm01@pilot.invalid>"   # 自述，不是认证
session_id: pm01-b2-dispatch-20261028
model: dsh/deepseek-flash
created_at: 2026-10-28T19:00:00+08:00
status: dispatched
---

# PM-01 → PM-02 派发交接（B2）

> 这是入口，不是修复方案。PM-02 必须自己从任务卡、RC3 摘要和代码得出结论。

## 1. 任务与范围

- 任务卡：`pilot/rounds/B2/task.md`
- 目标：有效签名不得包裹伪造执行收据；内容完整性与执行真实性分开。
- 允许修改：见任务卡 §3。
- 非目标：B1/B3–B5、Release、自动合并。

## 2. 阅读顺序

1. `pilot/README.md`
2. `pilot/ROLES.md`
3. `pilot/ROUND_PROTOCOL.md`
4. `pilot/rounds/B2/task.md`
5. `pilot/reference/RC3_B1_B3.md`
6. `.project-memory/goals/G-B2.json`
7. `pilot/STATUS.md`

## 3. 不得假设

- 不能只检查 `execution_provenance.trusted` 布尔值；手写收据也能写这个字段。
- 不能把“内容哈希一致”当成“执行真实发生过”。
- 不能放宽 authority/签名；不能让 Agent 生成“人类例外”。
- 不能修改任务卡/判据/探针/评测器。
- 不能把“测试通过”写成“安全验收通过”。
- 不能自行合并 PR 或宣布 Goal `achieved`。

## 4. 未决问题（由 PM-02 回答并写 ADR）

- 执行真实性用什么证明：launcher attestation、外部签名、还是显式人类例外？
- attestation 绑定哪些字段：command、commit、snapshot、receipt hash、时间、执行者？
- 如何把来源纳入签名载荷，使换收据/改 provenance/换 commit 都失效？
- 本地未受信执行默认拒绝，还是允许一条人类例外？例外如何签名/记录？
- 残余风险：root 妥协、受保护执行器被替换、attestation 重放。

## 5. 污染记录

- human_relay: []
- missing_artifacts: []
- stale_artifacts: []
- unauthorized_reads: []

## 6. 下一步

- PM-02 先做冷启动恢复，写 `context-recovery-pm02.md`。
- 若 Issue/任务卡/hash/fixture 未就绪：`BLOCKED`。
- 若环境/工具缺失：`BLOCKED`，不要静默绕过。
