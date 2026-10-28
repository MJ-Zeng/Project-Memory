# ADR-0003：执行来源与内容完整性分离（B2）

- 状态：`proposed`（Agent 起草；接受需人类批准，见 `docs/decisions/README.md`）
- 日期：2026-10-28
- 任务：B2（Issue #12）
- 基线：`587ac6a5024db3a6076a863876076d7fc7ecdd98`（冻结参照 `0d08a1ad85144d11a46d6a361a2a3ce4eadbbed4`）
- 影响范围：`project_memory/authority.py`（新增只读的执行 attestation/例外验签）、`project_memory/execution.py`（执行来源校验）、`project_memory/coordination.py`（`_verification_ok` 独立门禁）、`tests/test_security_b2.py`（新增）、本文档
- 不涉及：B1/B3–B5 的判定语义、收据/快照格式的强制字段、任务卡/判据/探针/评测器、`pilot/kit/b2/` 的 fixture 生成

## 1. 背景与问题

当前 `project_memory/coordination.py::_verification_ok()` 的判定链路是：

```text
verification_authority(record)             # 受保护 anchor 对整条 verification 记录验签
  → verdict=pass / status=VERIFIED 检查
  → checks.tests.receipt_integrity_valid   # 收据、快照、日志、提交的内容哈希一致
  → criterion_evidence / mapping / _verification_current
```

`receipt_integrity_valid` 只回答“收据与快照/日志/提交是否自洽”，不回答“这份收据是不是一个受保护的执行器真的执行后写出的”。签名只覆盖 **verification 记录**，而 verification 记录可以合法地引用一份手写收据；签名因此只证明“这条记录被签过”，不证明“记录里的执行真的发生过”。

RC3 的 B2 攻击链：

1. 手写一份自洽收据：`valid=true`、`provenance.trusted=false`、`executor=handwritten`；
2. 写一条引用该收据的 Verification，并让受保护签名者对这条记录签名；
3. `goal evidence` 接受、`goal evaluate` satisfied、Goal 到 `achieved`。

第 2 步的签名是“真的”，问题在于第 1 步的执行从未发生或不受保护。**只要门禁只查内容完整性，签名就替伪造执行背书。**

## 2. 两个正交问题

| 维度 | 回答的问题 | 现有证据 | 可信前提 |
|---|---|---|---|
| **内容完整性** | 收据内容是否与快照、日志、提交一致且未被篡改？ | `receipt.content_sha256`、`snapshot_sha256`、`log_sha256`、`tree_sha` | 只能证明“自洽”，不能证明“发生过” |
| **执行真实性** | 这条执行是否由可验证的受保护执行器完成，或由人类显式负责？ | 本 ADR 新增的执行 attestation / 人类例外 | 受保护私钥签名 + 与收据/提交的绑定 |
| **记录授权** | 这条 Verification 是否由受保护主体签署？ | `verification_authority()`（B1 已加固） | 受保护 anchor；不覆盖执行事实 |

三者必须同时满足；任何一个都不能替代另一个。

## 3. 决策

选择 **方案 1 + 方案 3 的组合**，并保留方案 2 的绑定性质：

1. **验证可签名的执行 attestation**（方案 1）；
2. **允许一条受保护签名的人类例外**，仅用于无法 attestation 的本地执行（方案 3）；
3. Verification 的签名载荷本来覆盖 `checks.tests`（含收据哈希与 attestation 引用），因此换收据、改 provenance、换 commit 都会同时破坏签名与实时绑定（方案 2 的实质效果，不需要新增第二套签名格式）。

### 3.1 执行 attestation

受保护执行器（或人类签署的 fixture）在 `.project-memory/` 内写一条 `execution_attestation` 记录：

```json
{
  "schema_version": "1.0",
  "kind": "execution_attestation",
  "attestation_id": "ATT-...",
  "receipt_id": "EXE-...",
  "receipt_sha256": "<receipt.content_sha256>",
  "commit_sha": "<40 hex>",
  "tree_sha": "<40 hex>",
  "snapshot_id": "...",
  "snapshot_sha256": "...",
  "command_sha256": "<sha256(receipt.command)>",
  "launcher": "project_memory.trusted_exec",
  "launcher_mode": "wsl2-user-mount-pid-net-namespace",
  "isolation": {"mode": "wsl2-...", "uid": 0, "pid_ns_levels": 1, "env_count": 5, "network": "isolated"},
  "created_at": "...",
  "authority": {
    "status": "trusted",
    "anchor_id": "...",
    "issuer": "...",
    "algorithm": "rsa-sha256",
    "signed_payload_sha256": "<sha256(canonical payload without authority)>",
    "signature_b64": "..."
  }
}
```

- 引用方式：收据新增可选字段 `execution_attestation_path`（相对仓库、必须位于 `.project-memory/` 内、不得是符号链接）与可选的 `execution_attestation_sha256`（文件内容哈希）。
- 校验（`authority.py::verify_execution_attestation_authority` + `execution.py::verify_execution_provenance`）：
  1. 文件存在、在 `.project-memory/` 内、非符号链接、JSON 合法、`kind`/`schema_version` 正确；
  2. `authority` 信封用**与 Verification 相同的受保护 anchor** 验签（`load_anchor` + `_verify_signature`，失败一律 fail closed）；
  3. `receipt_id`、`receipt_sha256`、`commit_sha`、`tree_sha`、`snapshot_id`、`snapshot_sha256`、`command_sha256` 与实时收据/目标提交逐项绑定；
  4. attestation 自身声明的隔离事实必须满足启动器的最低要求：`launcher_mode == trusted_exec.MODE`、`uid == 0`、`pid_ns_levels >= 1`、`env_count >= 1`；
  5. 记录内 `authority.status` 字符串不作数，只看验签结果。
- `execution_provenance.trusted` 布尔值**不参与判定**；它只是展示标签。攻击者写 `trusted=true` 不会让门禁通过。

### 3.2 人类例外（显式、非自动）

对确实无法 attestation 的本地执行，允许一条由人类私钥签名的例外记录：

```json
{
  "schema_version": "1.0",
  "kind": "execution_exception",
  "exception_id": "EXC-...",
  "goal_id": "G-B2",
  "criterion_ids": ["C1"],
  "receipt_id": "EXE-...",
  "receipt_sha256": "<receipt.content_sha256>",
  "commit_sha": "<40 hex>",
  "reason": "为什么该执行无法 attestation，以及为什么仍可采信",
  "scope": "one-off local execution for B2 fixture",
  "issued_by": "human@example.com",
  "created_at": "...",
  "authority": { "...": "同上，受保护 anchor 签名" }
}
```

- 引用方式：收据可选字段 `execution_exception_path`（+ 可选 `execution_exception_sha256`）。
- 校验：
  1. 与 attestation 相同的文件、信封、验签规则；
  2. 绑定 `receipt_id`、`receipt_sha256`、`commit_sha`；
  3. `goal_id` 等于当前 Goal，`criterion_ids` 覆盖当前 criterion；
  4. `reason`、`scope`、`issued_by` 非空。
- 例外必须由人类私钥签名；Agent 没有私钥，不能生成有效例外。没有有效签名时，**本地未受信执行默认拒绝**。

### 3.3 门禁位置与错误分类

`_verification_ok()` 在 `receipt_integrity_valid` 之后、criterion 覆盖检查之前增加一个**独立的执行来源条件**（不依赖 `execution_provenance.trusted`）：

```text
内容完整性失败        → “执行收据没有通过完整性校验”（保持原有语义）
来源不可信 / 签名失败 → “执行来源不可信：……”
既无 attestation 也无例外 → “执行来源不可信：人类例外缺失”（fail closed）
```

`_evidence_result()` 对 `verification` 证据把来源失败映射为 `ok=False, trust='untrusted'`，因此 `satisfies=False`，不能贡献 `satisfied`，也不会被 `add_goal_evidence` 接受。

门禁每次从磁盘**重新校验**收据与 attestation/例外，不信任 verification 记录里写死的布尔值（那些值只用于展示与审计）。

## 4. 被拒绝的方案

| 方案 | 拒绝原因 |
|---|---|
| 只检查 `execution_provenance.trusted` | 手写收据可以写 `trusted=true`；这是任务卡明确列为 FAIL 的修复 |
| 只检查 `executor.name` / `launcher` 字符串 | 字符串可由任何写仓库的人填写，不构成证据 |
| 只给 B2 fixture 的 receipt id/路径特判 | 绕过与 fixture 绑死，不是产品修复 |
| 让所有执行都失败 | AC-3 要求真实可信执行仍被接受；这是拒绝服务式“修复” |
| 新增一套 Verification 签名格式 | 现有签名已覆盖 `checks.tests`；新增格式会扩大 B1 的信任面并增加迁移成本 |
| 由 Agent 生成“人类例外” | 例外失去人类授权语义；必须由受保护私钥签名 |
| 放宽 authority/签名/`trusted` 语义 | 会让 B1 的加固失效，任务卡禁止 |

## 5. 残余风险（必须披露）

1. **root/管理员妥协**：能读取 `/etc/pm-rc3-review/key-a.pem` 的主体可以签任何 attestation/例外；本设计不防御信任根本身被攻破。
2. **受保护执行器被替换**：attestation 的语义依赖 `launcher_mode` 与隔离事实，但本仓库无法在 Windows 侧独立重放 WSL 命名空间；签名者仍需对执行器身份负责。
3. **attestation 重放**：已用 `receipt_sha256`、`commit_sha`、`tree_sha`、`snapshot_sha256`、`command_sha256` 绑定；重放到另一份收据/提交会失败。重放同一收据到同一提交等价于同一执行事实，按设计接受。
4. **本地未受信执行**：默认拒绝；只有人类签名例外才能通过。例外是“人类负责”而不是“执行被证明”。
5. **anchor 不可用**：`load_anchor` 失败时所有 attestation/例外都不可信，门禁 fail closed；旧记录会从“可满足”降为“不可满足”，这是预期的迁移行为。
6. **时钟**：attestation/例外的 `created_at` 不参与安全判定，避免依赖不可信时钟；审计时可人工核对。
7. **同一 anchor 同时签 Verification、attestation 与例外**：本设计接受这一点；隔离由 `PILOT` 流程与人类私钥保管约束，不由密码学区分密钥用途。

## 6. 迁移

- 旧 Verification 记录、旧收据继续可读、可展示、可审计；但**不再满足** Goal criterion，除非其收据带可验证 attestation 或人类例外。
- 旧记录不会被篡改或批量重写；这是 fail closed 的语义变化，必须在 Handoff 与审查报告中明确。
- `pilot/kit/b2/` 的正向 fixture 需由 PM-01/人类用 anchor-a 生成签名 attestation；PM-02 不读私钥、不自行签名。fixture 未就绪时，E2E 项标 `NOT VERIFIED`。
- 单元测试用测试替身（patch `authority.load_anchor`）与测试期临时 RSA 密钥验证密码学路径；生产代码不因测试而放宽。

## 7. 兼容性与回归

- 不改 `authority` 的签名信任模型、`load_anchor`、`anchor_is_protected` 的语义。
- 不改 `execution_provenance.trusted` 的写入语义；它仍是展示标签。
- 既有收据格式只新增可选字段，旧收据不受结构影响；但旧收据在 Goal 门禁上默认不再满足。
- 既有 190 passed / 2 skipped 必须保持；新增测试全部通过。

## 8. 验证要点（对应任务卡）

- AC-1/AC-2：手写 `trusted=false` 与谎报 `trusted=true` 都被拒；
- AC-3：带有效签名 attestation 的收据被接受；
- AC-4：本地未受信默认拒绝，只有有效人类例外可通过；
- AC-5：换收据、改 provenance、换 commit、重算内容哈希都会失败；
- AC-6：全量回归；
- AC-7：不新增绕过，不放宽 authority。
