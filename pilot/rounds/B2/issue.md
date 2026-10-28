# [B2] 有效签名不得包裹伪造执行收据

> 由 RC3 独立复核 B2 立项；B1 已合并、B0 已合并。

## 问题

`coordination._verification_ok()` 只要求 `checks.tests.receipt_integrity_valid`，不要求可验证的执行来源。手写自洽收据（`valid=true`、`provenance.trusted=false`）+ 有效签名 → `goal evaluate` satisfied → Goal `achieved`。

签名只证明“Verification 记录被签过”，不证明“收据对应的执行真的发生过”。

## 目标

把内容完整性与执行真实性分开：只有“内容完整 + 可验证执行来源/显式人类例外”同时满足，才能满足标准；不能只查自报的 `execution_provenance.trusted=true`。

## 范围

允许修改：

- `project_memory/coordination.py`（`_verification_ok` / `_evidence_result`）
- `project_memory/execution.py`（provenance/attestation，如需要）
- `project_memory/authority.py`（如签名载荷需纳入 provenance/attestation）
- `tests/`、`docs/decisions/`、`pilot/evidence/B2/`、`pilot/rounds/B2/handoff-*`

不允许：

- 修改 B1/B3–B5 行为（必要越界须声明）；
- 删除/跳过既有测试；
- 修改任务卡/判据/探针/评测器；
- 放宽 authority/签名/`execution_provenance.trusted`；
- 只加 `if not trusted: reject` 就算完成。

## 设计选项（详见任务卡 §4）

1. 验证 attestation（launcher/command/commit/snapshot/receipt hash + 签名），`trusted` 只是标签；
2. 把执行来源纳入签名载荷，换收据/改 provenance/换 commit 都失效；
3. 显式人类例外，绑定 receipt hash/commit/原因/范围，不能由 Agent 生成。

## 验收摘要

1. 手写收据（`trusted=false`）+ 有效签名 → 拒绝。
2. 手写收据谎报 `trusted=true`（无 attestation）+ 有效签名 → 拒绝。
3. 真实可信执行（可验证 attestation）+ 有效签名 → 接受。
4. 本地未受信收据 + 有效签名 → 默认拒绝，或仅显式人类例外。
5. 换收据/改 provenance/换 commit/重算内容哈希 → 校验失败。
6. 既有 190 passed / 2 skipped + 新增测试全绿。
7. 无新绕过；authority/签名未放宽。
8. ADR 说明威胁模型、被拒方案、残余风险、迁移。
9. 证据可复现。
10. PM-03 独立复现。
11. 范围纪律。

逐条 AC、fixtures、防作弊判据见 `pilot/rounds/B2/task.md`。

## 任务卡

- 路径：`pilot/rounds/B2/task.md`
- SHA-256：`3617dab01ca01c05ba2cb9ec87b38eae2622a6b69b480b2e7abb1c0881a7900e`
- 基线：`dev/v1.0` 的 B2 dispatch 合并提交；精确 SHA 见本 Issue
- 候选分支：`fix/b2-receipt-provenance`

## Fixtures

`pilot/kit/b2/` 需要：

- `VER-b2-forged-untrusted`：手写收据，`trusted=false`；
- `VER-b2-forged-claimed-trusted`：手写收据，谎报 `trusted=true`，无 attestation；
- `VER-b2-genuine-trusted`：带可验证 attestation 的真实/测试执行；
- `VER-b2-local-untrusted`：本地未受信收据。

由 PM-01/人类用 anchor-a 签名；私钥不入库。正向 fixture 无法生成时标 `NOT VERIFIED`，不得用伪造 `trusted=true` 冒充。

## 阅读顺序

`pilot/README.md` → `pilot/ROLES.md` → `pilot/ROUND_PROTOCOL.md` → `pilot/rounds/B2/task.md` → `pilot/rounds/B2/handoff-dispatch.md` → `pilot/reference/RC3_B1_B3.md` → `pilot/kit/b2/README.md`。

## 标签

`security`、`P0`、`pilot`
