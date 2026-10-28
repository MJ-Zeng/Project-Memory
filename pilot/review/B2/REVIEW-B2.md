# PM-03 独立审查报告 — B2

- 审查者：PM-03 Independent Reviewer（独立会话）
- 日期：2026-10-28
- 任务：B2 — 有效签名不得包裹伪造执行收据
- Issue：[#12](https://github.com/MJ-Zeng/Project-Memory/issues/12)
- PR：[#14](https://github.com/MJ-Zeng/Project-Memory/pull/14)
- 审查分支：`review/b2-004a35b`
- 证据：`pilot/evidence/B2/review-20261028T192825/`

## 0. 结论

**VERDICT: NOT VERIFIED（逻辑级全部通过；anchor-a E2E 缺失）。**

- 负向、正向、例外与绕过矩阵在候选代码上全部符合预期（28/28）。
- 未发现新的可利用绕过；B1 的签名信任模型未被放宽。
- 但 `pilot/kit/b2/` 没有 anchor-a 签名 fixture，正向/例外只能用临时 RSA 密钥 + patch `authority.load_anchor` 复现；真实 WSL 启动器与真实人类例外也未运行。按任务卡 §5 与派发提示词 §5，整体不得记 PASS，故为 **NOT VERIFIED**。

## 1. 工件与哈希

| 项 | 值 | 核对 |
|---|---|---|
| 基线 | `587ac6a5024db3a6076a863876076d7fc7ecdd98` | `git rev-parse`；PR #13 merge |
| 候选 | `004a35bd7c6b6584a9054d7b61eca88b44ec25e6` | `git cat-file -t` = commit |
| PR head | `6257fb61cf29974aad32216b24788766bc37d147` | `git diff 004a35b 6257fb6` 仅两个 Handoff 文件 |
| 任务卡 SHA-256 | `3617dab01ca01c05ba2cb9ec87b38eae2622a6b69b480b2e7abb1c0881a7900e` | 基线与候选一致 |
| 基线后代 | 是 | `git merge-base --is-ancestor 587ac6a 004a35b` exit 0 |

候选源文件哈希（工作树 / 提交 blob）：

| 文件 | 工作树（CRLF） | 提交 blob（LF） | Handoff 记录 |
|---|---|---|---|
| `project_memory/authority.py` | `37b81f33…` | `b2b88444…` | `37b81f33…`（工作树） |
| `project_memory/coordination.py` | `0c22efe5…` | `53066b81…` | `0c22efe5…`（工作树） |
| `project_memory/execution.py` | `a722f31c…` | `796de0fc…` | `a722f31c…`（工作树） |
| `tests/test_security_b2.py` | `47b9dbef…` | `f8708a64…` | `f8708a64…`（blob） |
| `ADR-0003` | `61dcd0ba…` | `61dcd0ba…` | `61dcd0ba…` |

> 哈希基准不一致是数据质量缺陷（见 §6.1），不影响安全结论。

## 2. 静态审查

### 2.1 条件是否真的分开

`coordination.py:825` 起，在 `receipt_integrity_valid` 之后增加**独立**执行来源门禁：

1. 必须存在 `checks.tests.receipt`，否则 `untrusted`（fail closed）；
2. `verify_receipt()` 重新校验收据内容完整性，失败报 `invalid`；
3. `verify_execution_provenance()` 校验来源，失败报 `untrusted`；
4. 之后才检查 criterion 覆盖与 `_verification_current`。

**没有读取 `execution_provenance.trusted` 作为门禁。** `verify_execution_provenance()`（`execution.py:659`）只接受：收据内的 `execution_attestation_path`（验签 + 绑定）或 `execution_exception_path`（验签 + 绑定）；两者都没有时直接拒绝。

### 2.2 attestation 是否真的验签并绑定

`authority.py:511` 的 `_execution_record_authority()`：

- 使用受保护 `load_anchor`（不读取记录里自报的 `authority.status`）；
- 校验 `anchor_id`、`issuer`、`algorithm`、`signed_payload_sha256`，再用进程内 `_verify_signature` 验签；任一失败 fail closed。

`execution.py:579` 的 `_verify_execution_attestation()` 逐项绑定：

| 字段 | 与实时收据/提交比较 |
|---|---|
| `receipt_id` | 收据 `receipt_id` |
| `receipt_sha256` | `_canonical_receipt_digest(receipt)`（排除 `content_sha256`，其余字段全包含） |
| `commit_sha` | `verification.target_head_sha` |
| `tree_sha` | 收据 `tree_sha` |
| `snapshot_id` / `snapshot_sha256` | 收据同名字段 |
| `command_sha256` | `sha256(receipt.command)` |

另要求 `schema_version=1.0`、`kind=execution_attestation`、文件位于 `.project-memory/` 内且非符号链接（`execution.py:525` `_resolve_meta_file`）。任一绑定缺失或不符即拒绝。

**隔离断言**（`execution.py:559`）：`launcher_mode == trusted_exec.MODE`、`uid == 0`、`pid_ns_levels >= 1`、`env_count >= 1`。这些是签名者断言，不是独立观测（残余风险，见 §7）。

### 2.3 人类例外

`execution.py:619`：

- 必须由受保护 anchor 验签；
- `reason`、`scope`、`issued_by` 非空；
- `goal_id` 等于当前 Goal；`criterion_ids` 必须包含当前 criterion；
- 绑定 `receipt_id`、`receipt_sha256`、`commit_sha`。

Agent 无私钥，不能生成有效例外；未签名或错误密钥签名一律 `untrusted`。

### 2.4 是否放宽 B1

- `authority.py` 的 diff 只有**追加**（`execution_record_payload/digest`、`_execution_record_authority`、两个公开包装函数）；`load_anchor`、`anchor_is_protected`、`verification_authority`、`_verify_signature` 未修改。
- `coordination.py` 只新增 kind 检查和来源门禁，未删减原有检查。
- 静态 grep：`authority.py` 中无 `shutil`、`subprocess`、`which`、`PROJECT_MEMORY_OPENSSL`（exit 1 = 无匹配）。

### 2.5 范围与测试纪律

- `git diff --name-status 587ac6a..004a35b` 仅 16 个文件，全部在任务卡允许范围；无任务卡/判据/探针/评测器/`frozen/` 修改。
- 既有测试未被删除或修改；新增 `tests/test_security_b2.py`（391 行，13 项，无 skip/xfail）。

### 2.6 ADR

`ADR-0003` 覆盖：威胁模型（签名只证明记录被签，不证明执行发生）、两个正交维度、方案 1+3、被拒方案（只查布尔值/字符串/特判/全拒/新增签名格式/Agent 生成例外/放宽 authority）、残余风险（root、启动器替换、重放、时钟、同 anchor 多用途、anchor 不可用）、迁移（旧记录默认不再满足，属预期）。

## 3. 逐条 AC

| AC | 结论 | 依据 |
|---|---|---|
| AC-1 手写 `trusted=false` + 有效签名被拒 | **PASS（逻辑级）** | 案例 1：`_verification_ok` false、`untrusted`、`add_goal_evidence` 抛 `PMError`、`evaluate` false |
| AC-2 谎报 `trusted=true` 无 attestation 被拒 | **PASS（逻辑级）** | 案例 3：收据内容完整性仍有效，但来源门禁拒绝；证明不是查布尔值 |
| AC-3 可验证 attestation + 有效签名被接受 | **PASS（逻辑级）**；anchor-a E2E = **NOT VERIFIED** | 案例 6：接受、`evidence_matched`、绑定 criterion 后 `evaluate.satisfied=true` |
| AC-4 本地未受信默认拒绝 / 仅显式人类例外 | **PASS（逻辑级）** | 案例 2、8、9–14：默认拒绝；签名例外接受；未签名/错钥/越界拒绝 |
| AC-5 来源绑定 | **PASS** | 案例 15–26：换收据、移 attestation、改 provenance+重算、改 commit、改隔离字段、改收据摘要、缺字段、路径逃逸均拒绝 |
| AC-6 回归 | **PASS** | 候选 203 passed / 2 skipped（exit 0）；基线 190/2；无删除/跳过 |
| AC-7 无新绕过 | **PASS** | 28/28 案例符合预期；B1 probe 全部拒绝；authority 未放宽 |
| AC-8 ADR | **PASS** | 威胁模型、被拒方案、残余风险、迁移齐全，与实现一致 |
| AC-9 证据 | **PASS** | 命令、退出码、UTF-8 日志、干净 archive 可校验的 sha256sums |
| AC-10 独立复现 | **PASS** | 候选 worktree + 第二 Clone（`/tmp/pm-b2-clone` @ `004a35b`）均 13 passed |
| AC-11 范围纪律 | **PASS** | diff 只在允许文件；无 B1/B3–B5 夹带 |

## 4. 动态复现

环境：Windows Python 3.12.4 / pytest 9.1.1；WSL python3 3.14.4（仅 B1 probe）。日志均为 `-X utf8` + `PYTHONIOENCODING=utf-8` 重录，见证据目录。

### 4.1 测试

| 命令 | 目录 | 退出码 | 结果 |
|---|---|---|---|
| `pytest -q -p no:cacheprovider` | `.pilot/candidate` @ 004a35b | 0 | **203 passed, 2 skipped**（98.66s） |
| `pytest -q tests/test_security_b2.py` | 同上 | 0 | **13 passed**（14.14s） |
| 同上 | `/tmp/pm-b2-clone` @ 004a35b | 0 | **13 passed**（12.93s） |
| `pytest -q -p no:cacheprovider -rs` | `.pilot/base` @ 587ac6a | 0 | **190 passed, 2 skipped**（81.71s） |

skip 项与基线一致：`tests/test_security_rc3.py:284,295`（当前平台不允许创建符号链接）。

### 4.2 独立矩阵（28/28）

测试替身：临时 RSA-2048 + patch `authority.load_anchor`；**不是 anchor-a E2E**。所有案例走真实 `_verification_ok` / `add_goal_evidence` / `evaluate_goal`。

| # | 案例 | 预期 | 观察 |
|---|---|---|---|
| 1 | 手写收据（`trusted=false`）+ 有效验证签名 | 拒绝 | `untrusted`；"执行来源不可信…人类例外缺失" |
| 2 | 本地未受信收据 + 有效签名，无例外 | 拒绝 | `untrusted` |
| 3 | 诈报 `trusted=true`，无 attestation | 拒绝 | 收据完整性 `valid=true`，解析器 `provenance.trusted=false`，门禁拒绝 |
| 4 | 自写 legacy launcher attestation（`attestation_path`，无签名） | 拒绝 | 收据完整性有效，门禁拒绝 |
| 5 | `execution_attestation_path` 指向伪造信封 | 拒绝 | `untrusted` |
| 6 | 签名 attestation 完整绑定 | 接受 | `evidence_matched`；`evaluate.satisfied=true` |
| 7 | 同一 attestation 重放到同一收据/提交 | 按设计接受 | 接受（边界，记录） |
| 8 | 签名人类例外，goal/criterion/receipt/commit 匹配 | 接受 | `evidence_matched`；`evaluate.satisfied=true` |
| 9 | 未签名例外 | 拒绝 | `untrusted` |
| 10 | 错误密钥签名例外 | 拒绝 | `untrusted` |
| 11 | 例外绑定其他 Goal | 拒绝 | `untrusted` |
| 12 | 例外不覆盖当前 criterion | 拒绝 | `untrusted` |
| 13 | 例外缺 `issued_by` | 拒绝 | `untrusted` |
| 14 | 例外缺 `reason` | 拒绝 | `untrusted` |
| 15 | 换掉已签名验证下的收据 | 拒绝 | `invalid` |
| 16 | 把 B 的 attestation 移到 A | 拒绝 | `untrusted` |
| 17 | 改 provenance 并重算收据内容哈希 | 拒绝 | `untrusted`（attestation 绑定失效） |
| 18 | 签名后改 `isolation.uid` | 拒绝 | `untrusted`（签名失败） |
| 19 | 签名后改 `receipt_sha256` | 拒绝 | `untrusted`（签名失败） |
| 20 | 非 anchor 密钥签 attestation | 拒绝 | `untrusted` |
| 21 | 签名 attestation 缺 `snapshot_id` | 拒绝 | `untrusted` |
| 22 | `execution_attestation_sha256` 不一致（仍有效签名） | 拒绝 | `untrusted`（显式文件哈希检查） |
| 23 | 指向不存在的 attestation 文件 | 拒绝 | `untrusted` |
| 24 | attestation 路径在 `.project-memory` 外 | 拒绝 | `untrusted` |
| 25 | 签名后更换收据 commit | 拒绝 | `invalid`（收据与预期提交不一致） |
| 26 | 诈报 `trusted=true` + 损坏的签名 attestation | 拒绝 | `untrusted` |
| 27 | Agent 自有 anchor（env 覆盖） | 拒绝 | `untrusted`（`anchor_is_protected` 拒绝可写/同主 anchor） |
| 28 | B1：PATH + `PROJECT_MEMORY_OPENSSL` 指向假 openssl | 有效仍接受、篡改仍拒绝 | 前后一致；篡改被拒 |

统计：**28/28 符合预期**；其中绕过攻击 13/13 拒绝（#15–#27），例外攻击 6/6 拒绝（#9–#14），核心负向 5/5 拒绝（#1–#5）。

### 4.3 B1 回归（CLI / 真实 anchor-a）

在基线树取 probe（`.pilot/base/pilot/kit/b1/openssl_substitution.py`），对候选代码以 WSL root 运行、CLI 以 uid 1000 执行，anchor 为 `/etc/pm-rc3-review/anchor-a.json`（未读取私钥）：

```json
{"control_real_openssl_exit": 1, "control_rejected": true,
 "path_substitution_exit": 1, "path_substitution_accepted": false,
 "env_openssl_exit": 1, "env_openssl_accepted": false,
 "env_true_exit": 1, "env_true_accepted": false,
 "agent_owned_anchor_exit": 1, "agent_owned_anchor_rejected": true}
```

结论：B1 的 in-process 验签仍不可被 `PATH` / `PROJECT_MEMORY_OPENSSL` / `/bin/true` 替换；agent-owned anchor 仍被拒绝。B1 测试（26 项）在 203 项全量中通过。

## 5. 与 PM-02 自报的差异

| 项 | PM-02 | PM-03 |
|---|---|---|
| 全量测试 | 203 passed / 2 skipped | 一致（独立重跑） |
| B2 专项 | 13 passed | 一致（worktree + 第二 Clone） |
| 基线 | 190 passed / 2 skipped | 一致 |
| AC 结论 | 不声称 PASS | 逻辑级通过；整体 NOT VERIFIED（缺 anchor-a E2E） |
| 源文件哈希 | 五项记录 | 四项可复现，但基准混合（§6.1） |
| AC-10 | 未运行 | 已运行（第二 Clone） |
| 正向/例外 | 逻辑级 | 逻辑级（临时密钥 + patch），非 anchor-a |

## 6. 新发现

### 6.1 LOW — Handoff 源文件哈希基准不一致（数据质量）

`pilot/rounds/B2/handoff-run-20261028T110321Z.md` 与 JSON 的 `hashes`/`evidence` 中：

- `authority.py`/`coordination.py`/`execution.py` 记录的是 **CRLF 工作树**哈希；
- `tests/test_security_b2.py` 记录的是 **LF 提交 blob** 哈希；
- `ADR-0003` 两者相同（`.gitattributes` 强制 LF）。

在普通 Windows 检出上 `sha256sum tests/test_security_b2.py` 得 `47b9dbef…`，与 Handoff 的 `f8708a64…` 不符；源文件则相反。复现者若不知道基准会误判“候选被改”。**不影响安全语义**，但影响证据可复现性。建议后续统一记录提交 blob（或干净 archive）哈希。

### 6.2 LOW — `pilot/STATUS.md` 过期

仍写 B2 `dispatch_pending_merge`、PR 待建；实际已有候选与 PR #14。属 F-4 类型，PM-01 更新。

### 6.3 INFO — 可选摘要字段的循环

收据 `execution_attestation_sha256` 与 attestation `receipt_sha256` 同时使用时形成循环（attestation 哈希依赖收据，收据摘要又包含 attestation 哈希）。当前测试省略该可选字段；显式 mismatch 会被拒（#22），但“同时使用”实际不可构造。建议后续规定二选一或排除字段。

### 6.4 INFO — 例外身份只是签名载荷内字符串

`issued_by` 无独立身份核验；有效例外只证明“anchor 私钥持有者写了这个字符串”。ADR §5.7 已披露；迁移期可接受，但不应在报告中称“已验证人类身份”。

### 6.5 INFO — 同一 anchor 多用途

Verification、attestation、exception 共用 anchor，无密钥用途分离；若需更强隔离，后续轮次可引入用途标记/独立密钥。

### 6.6 INFO — attestation 与 exception 同时存在时 attestation 优先

若 attestation 损坏但 exception 有效，门禁先走 attestation 并拒绝，形成拒绝服务而非绕过。记录边界。

### 6.7 INFO — 隔离事实不可独立观测

`uid`、`pid_ns_levels`、`env_count`、`network` 是签名者断言；Windows 侧无法复算 WSL 命名空间。ADR §5.2 已披露。

**未发现 HIGH/MEDIUM 新绕过。**

## 7. 残余风险与 NOT VERIFIED

NOT VERIFIED：

1. **anchor-a E2E**：`pilot/kit/b2/` 无四类 anchor-a 签名 fixture；AC-3/AC-4 正向与例外均为临时测试密钥 + patch `load_anchor` 的逻辑级复现。**E2E_ANCHOR_A = NOT VERIFIED**。
2. **真实 WSL `mode=trusted` 启动器**未运行；attestation 隔离字段未由真实启动器产生。
3. **真实人类签名例外**不可用；测试用临时 anchor 密钥代签。
4. **Issue #12 正文、PR #14 描述/评论**：私有仓库 API 404、本机无 `gh`，未认证读取。
5. **Windows 符号链接拒绝路径**未单独执行（平台不允许创建 symlink；既有测试同样 skip），仅静态确认代码检查 `is_symlink()` 与路径逃逸。
6. **重放边界**：同一 attestation 重放到同一收据/提交被接受（设计等价于同一执行事实），未在真实 anchor-a 上复验。

残余风险（设计内）：

- root/信任根被攻破可签任意 attestation/exception；
- 受保护启动器被替换时，签名者仍需对启动器身份负责；
- 同一 anchor 多用途；
- 例外是“人类负责”，不是“执行被证明”；
- 旧 Verification 记录在门禁升级后默认不再满足 criterion（预期迁移）。

## 8. 污染、偏差与接手耗时

- `human_relay`：none
- `missing_artifacts`：Issue #12 正文、PR #14 描述/评论、anchor-a fixture
- `stale_artifacts`：`pilot/STATUS.md`
- `unauthorized_reads`：none
- 读过的 PM-02 工件仅限提交进候选/PR 的 Handoff、测试、证据与 ADR；未读其会话、终端历史、未提交文件。
- 未修改候选代码、commit、分支；未 Approve、未合并、未宣布 Goal `achieved`。
- `model`/`session` 为自报；Handoff 写 `qoder/qoder-desktop-agent`，与当前环境不一致，记为数据质量问题，不作身份认证。
- 接手分钟数：约 10。

## 9. 最终判定

- 逻辑级：AC-1..AC-11 全部符合预期，负向全拒绝、正向接受、无新绕过、B1 无回归。
- 未验证：anchor-a E2E、真实 WSL 启动器、真实人类签名例外。
- **整体：NOT VERIFIED**（按任务卡 §5，逻辑级测试不得写成 PASS）。
- 合并、Goal `achieved`、ADR 接受仍由人类决定；本报告不是安全身份批准。
