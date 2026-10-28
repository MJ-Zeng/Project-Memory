# B2 证据包（run-20261028T110321Z）

- 任务：B2 — 有效签名不得包裹伪造执行收据
- 基线：`587ac6a5024db3a6076a863876076d7fc7ecdd98`
- 分支：`fix/b2-receipt-provenance`
- 候选 SHA：见 Handoff（本目录随候选提交一起入库）
- 任务卡 SHA-256：`3617dab01ca01c05ba2cb9ec87b38eae2622a6b69b480b2e7abb1c0881a7900e`
- 生产私钥：**未读取**；测试使用开放时生成的临时 RSA 测试密钥，仅存在于临时目录。

## 1. 结论边界

本证据包证明的是**单元/集成层**的行为，不是 PM-03 的独立安全验收。PASS/FAIL 由 PM-03 与人类判定。

## 2. 文件

| 文件 | 证明什么 | 不证明什么 |
|---|---|---|
| `environment.txt` | 运行环境、分支、基线与任务卡哈希 | 不代表审查环境 |
| `commands.jsonl` | 本次运行的关键命令、退出码与观察结果 | 不包含本次会话的全部探索命令 |
| `baseline-pytest.log` | 基线 `587ac6a` 独立 worktree：190 passed / 2 skipped | 不证明候选行为 |
| `b2-tests.log` | 新增 B2 测试：13 passed | 不证明 PM-03 的独立 fixture |
| `pytest.log` | 候选树全量：203 passed / 2 skipped | 不证明安全验收通过 |
| `*.exit` | 对应 pytest 命令的退出码（均为 0） | — |
| `diffstat.txt` | 变更文件与行数 | 不列出未跟踪的新文件内容 |
| `sha256sums.txt` | 本目录文件哈希（不含自身） | — |

## 3. 四类 fixture 状态

`pilot/kit/b2/` 的 anchor-a 签名 fixture **尚未生成**。因此任务卡 §8 列表中的：

- `forged-untrusted.json`
- `forged-claimed-trusted.json`
- `genuine-trusted.json`
- `local-untrusted.json`

**没有生成**（状态：`NOT VERIFIED`）。原因：需要 PM-01/人类用生产 anchor 签名；PM-02 不得读取生产私钥或自行签名。这些 E2E 项由 PM-03 使用独立 fixture 复核。

本目录用 `tests/test_security_b2.py` 中的测试期签名者与 patch 的 `authority.load_anchor` 覆盖同等逻辑；生产代码中的 `load_anchor`、`_verify_signature`、`anchor_is_protected` 未被放宽。

## 4. 测试与 AC 对应

| AC | 测试 |
|---|---|
| AC-1 手写 `trusted=false` + 有效签名被拒 | `test_handwritten_untrusted_receipt_with_valid_signature_is_rejected`、`test_local_untrusted_receipt_is_rejected_by_default` |
| AC-2 谎报 `trusted=true`（无 attestation）被拒 | `test_claimed_trusted_boolean_without_attestation_is_rejected`、`test_self_written_launcher_attestation_is_not_execution_proof` |
| AC-3 可验证 attestation + 有效签名被接受 | `test_signed_attestation_is_accepted_and_goal_evidence_succeeds`、`test_signed_attestation_satisfies_bound_criterion` |
| AC-4 本地未受信默认拒绝 / 仅人类例外 | `test_local_untrusted_receipt_is_rejected_by_default`、`test_signed_human_exception_allows_local_execution`、`test_unsigned_exception_is_rejected`、`test_exception_out_of_scope_is_rejected` |
| AC-5 来源绑定 | `test_swapping_the_receipt_is_rejected`、`test_provenance_edit_with_recomputed_hash_is_rejected`、`test_attestation_commit_edit_breaks_signature`、`test_attestation_from_another_receipt_is_rejected` |
| AC-6 回归 | `pytest.log`（203 passed / 2 skipped）、`baseline-pytest.log`（190 passed / 2 skipped） |
| AC-7 无新绕过 | 上述负向用例 + 既有 `test_security_rc3.py`、`test_authority_verifier.py` 全绿 |
| AC-8 ADR | `docs/decisions/ADR-0003-execution-provenance.md` |
| AC-9 证据 | 本目录 |
| AC-10 独立复现 | `NOT VERIFIED`（PM-03） |
| AC-11 范围纪律 | `diffstat.txt`；新增文件：ADR、测试、冷启动记录、本证据包 |

## 5. 未验证项（NOT VERIFIED）

1. 真实 anchor-a 签名的 E2E fixture 与 `goal evidence` / `evaluate` 的 CLI 输出（fixture 未生成）。
2. 在 PM-03 独立 Clone/路径上的复现（AC-10）。
3. WSL 可信启动器真实运行产生的 attestation（本环境未运行 `mode=trusted`；测试 attestation 为测试期构造）。
