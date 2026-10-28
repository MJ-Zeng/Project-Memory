# [B0] 可移植的仓库身份，解除执行收据的绝对路径绑定

> 由 B1 正向 fixture 准备阶段发现；B1 因此标记 `blocked_by_B0`。

## 问题

`execution.repo_id(repo) = sha256(repo.resolve())` 把仓库**绝对路径**当作身份。执行收据保存该 `repo_id`，`verify_receipt` 要求它与当前路径一致。

同一个仓库、同一个 commit，复制/Clone 到另一个路径后：

```text
receipt_repo_id = 87284aaf...
current_repo_id = ce540af6...
valid = false
problem = 收据不属于本仓库
```

`goal evidence` 最终报：

```text
证据无效：VER-positive 针对的不是当前提交或执行已失效
```

## 影响

- PM-02 在 `pm-pilot-02` 产生收据，PM-03 在 `pm-pilot-03` 无法验证；
- CI checkout、Docker、换机器、git worktree 同样失败；
- 证据包不可移植，独立复核退化为只能看开发自报；
- 这是多 Agent / 多 Clone 协作的核心前提。

## 目标

让执行收据与验证记录在同一仓库的独立 Clone/不同路径之间可移植，同时仍然拒绝来自不同仓库的收据；不削弱签名与内容绑定。

## 范围

允许修改：

- `project_memory/execution.py`（`repo_id` 及调用点）
- `project_memory/coordination.py`（如验证路径需要）
- `tests/test_security_rc3.py` 或新增 `tests/test_repo_identity.py`
- `docs/decisions/` ADR / security note
- `pilot/evidence/B0/`、`pilot/rounds/B0/handoff-*`

不允许：

- 修改 B1–B5 行为；
- 删除/跳过既有测试；
- 修改任务卡/判据/探针/评测器；
- 让不同仓库的收据互相通过；
- 静默重写历史收据。

## 验收摘要

1. 路径 A 生成收据，复制到路径 B，同一 commit 验证通过。
2. 不同 remote/根 commit 的仓库使用该收据，被拒绝。
3. 仓库身份不含绝对路径；Clone/CI 路径变化不影响。
4. 旧路径绑定收据不静默跨路径通过；schema 版本升级。
5. 既有 147 项 + 新增正/负测试全绿。
6. 签名/authority/receipt 内容哈希不被削弱。
7. ADR 说明信任模型、被拒方案、残余风险、迁移。
8. 范围纪律：无 B1–B5 夹带。
9. 证据包完整、可复现。
10. PM-03 从两个不同路径独立复现。

逐条 AC 见 `pilot/rounds/B0/task.md`。

## 任务卡

- 路径：`pilot/rounds/B0/task.md`
- SHA-256：`81e20cf8c16a30c904e925e195d7748bce5a11f24a62f5c16a3ec15b895061c0`
- 基线：`dev/v1.0` 的 B0 dispatch 合并提交；精确 SHA 见本 Issue
- 候选分支：`fix/b0-repo-identity`

## 阅读顺序

`pilot/README.md` → `pilot/ROLES.md` → `pilot/ROUND_PROTOCOL.md` → `pilot/rounds/B0/task.md` → `pilot/rounds/B0/handoff-dispatch.md` → `pilot/reference/RC3_B1_B3.md`。

## 约束

- 独立 Clone：`pm-pilot-02`；不得使用原始 `project-memory-mvp`。
- 不读 PM-01/PM-03 聊天、终端历史或工作树。
- 不自行合并 PR、不批准 Goal、不宣布 `achieved`。
- 远端推送仅在授权范围内。

## 标签

`security`、`P0`、`pilot`
