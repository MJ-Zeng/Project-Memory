# PM-02 交接：B8-SIGNED-APPROVAL-001（签名审批事件）

- 日期（UTC）：2026-10-31T02:33:12Z
- 分支：`feat/b8-signed-approval`
- 基线：`187f49da4e473440089342b7144b4c6b302acf82`（`origin/dev/v1.0`，fetch 后与派单一致，未前进）
- 代码/文档头：`137a00463234968366d561ad8ddd46b832ee7d86`
- handoff 提交：`adb00361241bbe67b9c9fd888084c82c57a85e29`（本文件所在提交）
- 增量提交后最终分支头：见 §10
- 执行者：PM-02；独立复核：PM-03；合并：PM-01（等 PR CI 绿后）

## 1. 提交

```
adb0036 docs: add PM-02 handoff for B8 signed approvals
137a004 docs: describe signed approval workflow and trust boundaries
7655fa0 test(b8): cover signed approvals, tampering, and fail-closed paths
f861ad0 feat(b8): add signed approval events with anchor-bound identity
```

§10 记录后续的证据卫生增量提交；本文件的 HEAD 字段与 §10 合起来才是分支最终头。

未开 PR、未合并、未打 tag、未改 `dev/v1.0`；未改 `.github/`。仅动了代码/测试/文档。`docs/sync-b9-20261031` 分支未触碰；两个既有未跟踪文件 `PM02_COLD_START_VALIDATION.md`、`tasks/PM02-cold-start-handoff-20261029T150500Z.md` 保持原样、未提交。

## 2. 变更文件（基线..HEAD）

`git diff --name-only 187f49da4e473440089342b7144b4c6b302acf82..HEAD` 共 11 个路径（其中包含本 handoff 自身）：

```
README.md
docs/ARCHITECTURE.zh-CN.md
docs/OPERATIONS.zh-CN.md
project_memory/authority.py
project_memory/cli.py
project_memory/coordination.py
skill/project-memory/references/data-contracts.md
skill/project-memory/references/governance.md
skill/project-memory/references/workflows.md
tasks/PM02-b8-signed-approval-handoff-20261031T023312Z.md
tests/test_b8_signed_approval.py
```

`git diff --check 187f49d..HEAD`：exit 0（§10 复跑确认）。

## 3. 数据格式与摘要算法

记录目录 `.project-memory/approvals/<approval_id>.json`；顶层 `kind: "approval_event"`、`schema_version: "1.0"`。

必填：`approval_id`、`decision`（`approve`/`reject`）、`approver`（邮箱）、`at`、`repository`（`repo_identity().id` + `remote`）、`commit_sha`（40 位）、`scope`。可选：`statement`。

`scope.kind`：

- `commit`：只批准该提交，供 CI 合并门禁使用（B-7），不参与 Goal 判据。
- `criterion`：额外含 `goal_id`、`criterion_id`、`verification`（`ref`、`verification_id`、`digest`、`target_head_sha`、`evidence_id`）。

摘要：

- 签名载荷 = 记录去掉 `authority` 的规范 JSON 字节（`authority.signed_record_payload`）。
- `approval_id = 'APR-' + sha256(记录去掉 approval_id 与 authority 的规范 JSON)[:12]`，可重算。
- `authority.signed_payload_sha256 = sha256(signed_record_payload(record))`。
- 验证绑定摘要 = `sha256(规范 JSON(验证记录去掉 authority 与 authority_evaluation))`，实现于 `authority.verification_subject_payload` / `verification_subject_digest`，请求生成与评估校验调用同一函数（`authority.py:59-74`）。

`authority` 信封（`status: "signed"`、`anchor_id`、`issuer`、`algorithm`、`signed_payload_sha256`、`signature_b64`）只是标签：读取时始终重新验签，`status` 不参与信任判断。

## 4. 信任决定点

- 审批锚由仓库外 `PROJECT_MEMORY_APPROVAL_ANCHOR` 指定；`PROJECT_MEMORY_TRUST_ANCHOR` 只服务验证记录/attestation/审计 checkpoint，两者互不替代。
- `approval attach` 只做结构、仓库身份与“给定公钥能验通”的本地检查，不构成信任。
- 信任只在 `approval verify`、`goal evaluate`、门禁读取时由受保护审批锚重新做出；锚缺失、验签失败、`approver != anchor.issuer`、提交不匹配、验证摘要变化，一律不 trusted。
- 评估时 `commit_sha` 必须等于当前 HEAD；`scope=criterion` 还要求绑定验证记录仍为 pass、`mapping_status=complete`、`evidence_id` 与 `target_commit_sha` 一致且记录未变。
- 未配置审批锚时记录可登记为证据，但状态为 `UNVERIFIED_APPROVAL`，永不 satisfy。
- `authority.py` 中 `os.environ.get` 仍只有一处（`authority.py:442`），现有测试 `test_module_keeps_no_external_verifier_dependency` 通过。

## 5. CLI 示例（本机实跑）

实跑环境：`C:/SoftWare/Anconda/python.exe`、`PYTHONUTF8=1 PYTHONIOENCODING=utf-8`、临时仓库 `C:/Temp/pm02_b8_smoke/repo`、测试私钥 `C:/Temp/pm02_b8_smoke/keys/approver.pem`（openssl 现场生成，非真实凭据）。

```bash
# 1) 未签名请求（输出在仓库外，供外部私钥签名）——exit 0
python -m project_memory.cli approval request --repo . --commit <HEAD> \
  --approver smoke-approver@example.invalid --output C:/Temp/pm02_b8_smoke/request2.json
# 输出路径 C:\Temp\pm02_b8_smoke\request2.json，payload_sha256 5910fd38...

# 2) 外部签名——exit 0
openssl dgst -sha256 -sign keys/approver.pem -out signed.sig request2.json

# 3) 本地验签并附加——exit 0，created=true
python -m project_memory.cli approval attach --repo . \
  --request C:/Temp/pm02_b8_smoke/request2.json \
  --signature C:/Temp/pm02_b8_smoke/signed.sig \
  --anchor C:/Temp/pm02_b8_smoke/keys/anchor.json

# 4) 用受保护审批锚验证——本机 exit 2（fail-closed，见 §8）
PROJECT_MEMORY_APPROVAL_ANCHOR=C:/Temp/pm02_b8_smoke/keys/anchor.json \
python -m project_memory.cli approval verify --repo . \
  --record .project-memory/approvals/APR-8f99e671541a.json --commit <HEAD>
# 输出 authority_status=unconfigured，
# reason=信任锚对当前进程可写；必须由仓库外受保护主体持有；verified=false

# 5) 列表——exit 0
python -m project_memory.cli approval list --repo .
```

criterion 范围与 Goal 挂载（测试中验证，见 §7）：

```bash
python -m project_memory.cli approval request --repo . --commit <HEAD> \
  --goal G-APPROVAL --criterion C1 --verification <verification-id> \
  --approver <email> --output <out>
python -m project_memory.cli goal evidence --repo . --id G-APPROVAL \
  --criterion C1 --kind approval --ref .project-memory/approvals/<id>.json
python -m project_memory.cli goal evaluate --repo . --id G-APPROVAL
```

`approval verify` 只在验签通过、`decision=approve` 且提交一致时 exit 0，否则 exit 2。

## 6. 审计与双门槛（实跑）

| 项目 | 命令 | 结果 |
|---|---|---|
| 基线 audit | `audit --scope current --output C:/Temp/pm02_b8_baseline_audit.json` | 40 条：0 high / 16 medium / 24 low，`entry_doc_*` 0 |
| 本次 audit | `audit --scope current --output C:/Temp/pm02_b8_final_audit.json` | 40 条：0 high / 16 medium / 24 low，`entry_doc_*` 0；与基线按 `(severity, code, location)` 多重集比较 added 0、removed 0 |
| 本次 reconcile | `reconcile --fail-on high --output C:/Temp/pm02_b8_final_reconcile.json` | exit 0；40 项（0 high / 16 medium / 24 low），与基线相同 |
| 默认 pytest | `python -m pytest -q` | **294 passed, 2 skipped in 181.14s** |
| openssl 门槛 | `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q -rs` | **294 passed, 2 skipped in 179.65s**；两处 skip 均为 `tests/test_security_rc3.py:295` / `:284`「当前平台不允许创建符号链接」，与本次改动无关 |
| 新增测试 | `python -m pytest tests/test_b8_signed_approval.py -q` | 14 passed in 14.83s |

基线 pytest 为 280 passed / 2 skipped；新增 14 个测试后为 294 passed / 2 skipped。openssl 门槛下签名测试真实执行（未被 skip）。

## 7. 负对照（实跑）

```bash
python -m pytest tests/test_b8_signed_approval.py -k negative_control -s -q
# exit 0
negative-control before: satisfied=True status=satisfied
negative-control removed: satisfied=False status=insufficient_evidence
negative-control restored: satisfied=True status=satisfied
1 passed, 13 deselected in 1.96s
```

同一 Goal 下移除 `--kind approval` 证据后判据立即回到未满足，恢复后重新 satisfied；证明满足来自审批证据本身，而不是其它证据或缓存。

## 8. 需要复核者注意的偏差与未验证项

偏差：

1. `approval_id` 的摘要输入同时排除 `approval_id` 与 `authority`。卡面写“不含 `authority`”，但 `approval_id` 本身在记录里，若纳入会自引用；排除两者才能可重算且改任一字段即变 ID。文档已按实际算法写明。
2. `scope=criterion` 的审批要求绑定验证记录 `mapping_status=complete`，而本地 CLI 写出的验证映射上限是 `review_required`（`evidence_matched` 无法由本地 CLI 置 True）。测试按 B4 的既有做法模拟“外部已确认映射”的验证记录；真实部署需要外部签名/确认流程。这是既有边界，不是本卡绕过项。
3. `approval request --output` 允许在仓库外（供外部签名）；结果里的 `path`/`sign_command` 对仓库外文件返回绝对路径，对仓库内文件仍返回相对路径。为此新增 `_approval_display_path`，并让测试真实使用仓库外目录，回归覆盖该行为。

未验证项：

1. 没有真实审批密钥，也没有受保护的外部审批锚：本机单用户 Windows 上锚文件可写且属主是当前用户，`load_anchor` 的保护检查会拒绝，因此实际 CLI 的 `approval verify` 只能验证 fail-closed（exit 2）。trusted 路径仅通过测试中 patch `authority.load_anchor` + openssl 现场密钥验证。
2. 未联网、未使用任何真实令牌/凭据；未在托管 CI 上运行；未验证 key custody、分支保护、Ruleset、CODEOWNERS。
3. 未建真实密钥仓库；`C:/Temp` 下的测试密钥仅用于本轮冒烟，之后可丢弃。
4. 观察到但未修改：`docs/CURRENT_STATE.md` 记录的测试数是 257 passed / 2 skipped，而基线实测为 280 / 2。该文档不在本卡范围，未改动，交由复核者决定是否另开任务。

## 9. 这关闭了 B-8 的哪一部分

关闭：审批从“邮箱正则 + 代理黑名单的自报”变成可验签、绑定审批人与提交、可绑定验证摘要的签名事件；无锚/坏签名/篡改/提交前进一律 fail closed；审批不再能自证权威，也不会改变 `verified=false`。

仍属其它阻断：审批私钥的托管、签名主体的部署保护、CI 合并门禁（必需审批/Ruleset）属于 B-7/B-10；本卡只提供事件格式、验签与评估联动。

## 10. 增量：证据卫生修正（本 handoff 之后）

PM-01 独立门禁在 `adb0036` 发现两项证据卫生问题，本增量只改本 handoff，不改代码、测试或文档正文：

1. 删除 §5 criterion 示例 `--output <out>` 行尾的多余空格（此前使 `git diff --check` exit 2）。
2. §2 文件清单补上本 handoff 自身，与实际 11 个路径逐字一致。
3. HEAD 字段拆成“代码/文档头”“handoff 提交”和“增量后最终头”，避免误读。

增量实跑（Windows，`C:/SoftWare/Anconda/python.exe`）：

```text
git diff --name-only 187f49da4e473440089342b7144b4c6b302acf82..HEAD
→ 11 个路径：README.md, docs/ARCHITECTURE.zh-CN.md, docs/OPERATIONS.zh-CN.md,
  project_memory/authority.py, project_memory/cli.py, project_memory/coordination.py,
  skill/project-memory/references/data-contracts.md,
  skill/project-memory/references/governance.md,
  skill/project-memory/references/workflows.md,
  tasks/PM02-b8-signed-approval-handoff-20261031T023312Z.md,
  tests/test_b8_signed_approval.py

git diff --check 187f49da4e473440089342b7144b4c6b302acf82..HEAD
→ exit 0

audit --scope current --output C:/Temp/pm02_b8_incremental_audit.json
→ exit 0；40 条（0 high / 16 medium / 24 low），entry_doc_* 0；
  与基线按 (severity, code, location) 多重集比较 added 0、removed 0

reconcile --fail-on high --output C:/Temp/pm02_b8_incremental_reconcile.json
→ exit 0；40 项，counts high=0 / medium=16 / low=24
```

双门槛 pytest：增量只改 handoff，未重跑；代码与测试自 §6 的 294 passed / 2 skipped 起未变。

`docs/CURRENT_STATE.md` 的测试计数过时问题不在本卡处理，未改动该文件。
