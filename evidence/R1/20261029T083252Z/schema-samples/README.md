# R1 schema 样例

本目录用于核对 `skill/project-memory/assets/audit-ledger.schema.json` 与真实输出一致。样例来自已生成的 B4 证据链，**只读复制，不重新生成、不使用生产私钥**。

| 文件 | 来源 | 用途 |
|---|---|---|
| `audit-entries.jsonl` | `evidence/B4/20261029T031257Z/chain/verification_attempts.jsonl`（原样复制） | 5 条真实审计条目：`seq` 连续、`prev_hash` 链接、`entry_hash` |
| `checkpoint-head.json` | `evidence/B4/20261029T031257Z/chain/head.json`（原样复制） | 已签名 checkpoint：`checkpoint_id`/`goal_id`/`status`/`chain_head`/`chain_length`/`at`/`approved_by`/`evidence_sha256`/`migration_sha256`/`authority` |
| `checkpoint-request.json` | `evidence/B4/20261029T031257Z/chain/head.request.json`（原样复制） | 未签名载荷：同样字段但没有 `authority` |
| `audit-entry-r1-refusal.json` | 本次 R1 手工探针临时仓库的审计最后一行 | 拒绝 `achieved` 的条目：`reason=goal_achieved_unsatisfied`、`no_required_criteria=true`、`evaluation_status=insufficient_evidence` |
| `goal-evaluation-vacuous.json` | 本次 R1 手工探针 `evaluate-vacuous.json` | `no_required_criteria=true`、`evaluation_status=insufficient_evidence`、`status_problems` 的结构 |
| `validate.py` / `schema-validation.log` | 本次 R1 运行 | 用 Draft 2020-12 校验器逐条验证上述记录 |

## 字段核对方式

```bash
cd <repo>
PYTHONIOENCODING=utf-8 C:/SoftWare/Anconda/python.exe \
  evidence/R1/20261029T083252Z/schema-samples/validate.py
```

- 审计条目：每行一个 JSON，必须命中 `$defs/verification_attempt`；核心字段 `schema_version=1.3`、`kind=verification_attempt`、`seq`、`timestamp`、`prev_hash`、`entry_hash`、`outcome`、`reason`。
- checkpoint：`audit/head.json` 命中 `$defs/audit_checkpoint`，包含签名信封 `authority`（`status=trusted`、`anchor_id`、`issuer`、`algorithm`、`signed_payload_sha256`、`signature_b64`）；`head.request.json` 是同一载荷去掉 `authority`，仍可被 schema 接受。
- `tracked_changes` 是 `git status --porcelain` 的原始文本（字符串），不是数组——这是校验时发现并修正的一个真实字段类型，说明 schema 以代码输出为准。

校验结果：5 条 B4 审计条目 + 1 条 R1 拒绝条目 + 2 条 checkpoint 记录全部通过，`0 problem(s)`，见 `schema-validation.log`。checkpoint 的签名本身由 B4 测试密钥产生；本目录不包含私钥，也不证明生产 anchor 可用（生产端到端仍为未验证项）。
