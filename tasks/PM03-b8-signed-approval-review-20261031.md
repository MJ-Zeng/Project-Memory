# PM-03 独立复核：B8-SIGNED-APPROVAL-001（签名审批事件）

- 日期（UTC）：2026-10-31
- 复核人：PM-03；执行者：PM-02；合并决定：PM-01
- 复核分支：`review/b8-signed-approval`（从基线 `187f49d` 起，检出被复核头 `1b565c1`）
- 复核方式：只读复核；未改业务代码、未改 `.github/`、未开 PR、未合并、未打 tag
- 本报告不构成合并批准，只作 PM-01 合并输入

## 1. 结论

**PASS WITH DEVIATIONS**（偏差均为 low / info 级，无安全阻断）。

范围：`origin/feat/b8-signed-approval` 的 5 个提交（基线 `187f49d` → 头 `1b565c1`），共 11 个路径；独立复跑 audit / reconcile / 双门槛 pytest / B8 定向测试，并用独立脚本实测 53 项安全语义。**未发现任何能让“无有效签名审批”满足 Goal 判据的路径。**

## 2. 被复核 SHA 与分支

| 项 | 值 |
|---|---|
| 远端分支 | `origin/feat/b8-signed-approval` |
| 远端头（实查） | `1b565c1eeb11c1372ebe6fc7ecdc94062c89cc17` |
| 任务卡给定头 | `1b565c1eeb11c1372ebe6fc7ecdc94062c89cc17`（一致） |
| 基线（实查） | `187f49da4e473440089342b7144b4c6b302acf82`（与任务卡一致） |
| merge-base | `187f49da4e473440089342b7144b4c6b302acf82`（分支确实从基线开出） |
| 复核 worktree | `C:/Temp/pm03-b8-review`（未改 pm-pilot-02 的 clone） |
| `origin/dev/v1.0` 现值 | `999713bdc454b31b1c853a5602fa6cf33d0942b1`（已前于本卡基线；本次仍按任务卡基线复核，未合入/未 rebase） |

提交序列：

```
1b565c1 docs: fix B8 handoff evidence hygiene
adb0036 docs: add PM-02 handoff for B8 signed approvals
137a004 docs: describe signed approval workflow and trust boundaries
7655fa0 test(b8): cover signed approvals, tampering, and fail-closed paths
f861ad0 feat(b8): add signed approval events with anchor-bound identity
```

关键实现位置（行号以被复核头 `1b565c1` 为准）：`project_memory/authority.py:59`（`verification_subject_payload`）、`authority.py:72`（`verification_subject_digest`）、`authority.py:441`（`load_anchor(..., env_name)`）、`authority.py:470`（`load_anchor_document`）、`authority.py:633`（`approval_authority`）、`project_memory/coordination.py:1750`（`_approval_structure_problem`）、`coordination.py:1889`（`write_approval_request`）、`coordination.py:1934`（`attach_approval`）、`coordination.py:1996`（`verify_approval`）、`coordination.py:2056`（`_approval_evidence`）、`coordination.py:3121`（reconcile 审批检查）、`project_memory/cli.py:216`（`approval` 子命令）。

## 3. 实跑表

环境：`C:/SoftWare/Anconda/python.exe`（Python 3.12.4），`PYTHONUTF8=1 PYTHONIOENCODING=utf-8`，worktree `C:/Temp/pm03-b8-review`。

| # | 命令 | exit | 关键结果 |
|---|---|---|---|
| 1 | `git fetch origin feat/b8-signed-approval`；`git rev-parse origin/feat/b8-signed-approval` | 0 | 头 = `1b565c1eeb11c1372ebe6fc7ecdc94062c89cc17`，与任务卡一致 |
| 2 | `git diff --name-only 187f49d..1b565c1` | 0 | **11 个路径**；全部在任务卡允许范围；**无 `.github/`** |
| 3 | `git diff --check 187f49d..1b565c1` | 0 | 无空白错误 |
| 4 | `python -m project_memory.cli audit --scope current --output C:/Temp/pm03-b8-audit.json` | 0 | **40 条 = 0 high / 16 medium / 24 low**；`entry_doc=docs/CURRENT_STATE.md`；`entry_doc_*` **0** |
| 5 | 基线 audit（worktree `C:/Temp/pm03-b8-baseline`，`187f49d`）→ `C:/Temp/pm03-b8-baseline-audit.json`；按 `(severity, code, location)` 多重集比较 | 0 | 基线同为 40 条（0/16/24）；**多重集完全相同；added 0 / removed 0** |
| 6 | `python -m project_memory.cli reconcile --fail-on high` | 0 | 0 high / 16 medium / 24 low；`summary.defects=0`、`open_defects=0`、`runs=0`、`verifications=0` |
| 7 | `python -m pytest -q` | 0 | **294 passed, 2 skipped** in 182.71s |
| 8 | `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q` | 0 | **294 passed, 2 skipped** in 179.19s |
| 9 | `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q -rs` | 0 | 两处 skip 均为 `tests\test_security_rc3.py:284/295`「当前平台不允许创建符号链接」；该文件不在 11 路径内（基线既有）；**B8 测试无 skip** |
| 10 | `python -m pytest tests/test_b8_signed_approval.py -q` | 0 | **14 passed** in 14.87s |
| 11 | 独立安全语义脚本 `C:/Temp/pm03_b8_verify.py` | 0 | **53 项检查全部 PASS**；结果 `C:/Temp/pm03_b8_verify_results.json`，日志 `C:/Temp/pm03_b8_verify.log` |

实跑日志：`C:/Temp/pm03-b8-pytest-default.log`、`C:/Temp/pm03-b8-pytest-openssl.log`、`C:/Temp/pm03-b8-pytest-openssl-rs.log`、`C:/Temp/pm03-b8-audit.json`、`C:/Temp/pm03-b8-baseline-audit.json`。

## 4. 安全语义逐项结论

独立脚本在临时 git 仓库中运行业务代码；签名用 openssl 现场生成的 RSA 密钥，审批锚为真实公钥文件。**受保护锚的加载在 trusted 场景用 `authority.load_anchor` 的审批分支打桩模拟**（与仓库单测同一接缝，见 §7）；无锚场景用真实 loader 且未设置环境变量。

| # | 检查项 | 结论 | 证据（独立脚本 check id / 关键输出） |
|---|---|---|---|
| 1 | 未配置 `PROJECT_MEMORY_APPROVAL_ANCHOR`：记录可登记但永不 satisfy；`approval verify` exit 2 | **PASS** | `S1`：`add_goal_evidence` 接受，评估 `state=UNVERIFIED_APPROVAL, authority=unconfigured, satisfies=false`；真 CLI（未打桩、未设环境变量）`exit=2, verified=false, reason=未配置受保护的信任锚（PROJECT_MEMORY_APPROVAL_ANCHOR）` |
| 2 | 伪造/自声明 `authority.status="trusted"` 但无有效签名 → untrusted；verify 不得 exit 0 | **PASS** | `S2`：`approval_authority` 返回 `trusted=False, status=untrusted, reason=签名验证失败`；CLI `exit=2, verified=false`。实现从不读取 `authority.status` 做信任判断（`authority.py` 只比较 anchor_id/issuer/algorithm/digest/签名） |
| 3 | 另一把私钥签名 → attach 拒绝；直接塞入记录 → 评估 untrusted | **PASS** | `S3`：attach `PMError: 审批签名无效：签名验证失败`；直接构造记录 `trusted=False`；把该记录写进 Goal 后评估 `satisfied=False, state=UNVERIFIED_APPROVAL` |
| 4 | 篡改 decision / commit_sha / scope / verification digest / approver / at 任一字段 → 验签失败或摘要/结构不一致，不 satisfy | **PASS** | `S4`（8 项，均先重算 `approval_id` 以绕过结构早退，属“最强攻击者”）：`decision`/`at` → `signed_payload_sha256 与记录内容不一致`；`commit_sha` → 提交不是当前 HEAD；`scope.criterion_id` → Goal/criterion 不一致；`verification.digest` → 摘要已变化；`verification.evidence_id` → 不一致；`approver` → 与锚 issuer 不一致；`scope.kind` → commit 范围不参与判据。全部 `trusted=False` 且评估 `satisfied=False` |
| 5 | `approver != 锚 issuer` → trusted=false | **PASS** | `S5`：attach 拒绝（`approver 与签名锚 issuer 不一致`）；即使签名由锚私钥真实生成，直接注入记录仍 `trusted=False, reason=审批记录的 approver 与审批锚 issuer 不一致` |
| 6 | 提交前进（HEAD 变化）→ 审批 stale，不 satisfy | **PASS** | `S6`：前进前 `satisfied=True`；前进后评估 `reason=审批绑定的提交不是当前 HEAD（审批已过期）`、`satisfied=False`；reconcile 报 `approval_stale_commit`(medium) |
| 7 | 验证记录被重写（字段变化）→ 原审批摘要失效 | **PASS** | `S7`：改写 `standard` 后 `reason=审批指向的验证记录摘要已变化（审批失效）`、不 satisfy；恢复原字节后重新 satisfied |
| 8 | `scope.kind=commit` → 可 `approval verify`，但绝不参与 Goal 判据 | **PASS** | `S8`：verify 正确提交 `exit=0`、错误提交 `exit=2`；`goal evidence` 以 `commit 范围` 拒绝；手工把该证据写进 Goal 文件后评估仍 `satisfied=False`（`commit 范围的审批不参与 Goal 判据`） |
| 9 | `manual` 仍 `UNVERIFIED_APPROVAL`；`--evidence-level human_approved` 仍被拒绝；`verified` 仍恒 false | **PASS** | `S9`：manual 状态仅 `UNVERIFIED_APPROVAL`、不 satisfy；`verify_run(...,'human_approved')` 抛 `PMError`；验证记录 `verified=false`；审批 attach/评估前后验证记录字节未变（`S0`） |
| 10 | `approval_id` 可独立重算；`verification_subject_digest` 排除项与文档一致，且请求生成与评估校验同一函数 | **PASS** | `S10`：独立用 canonical JSON（排除 `approval_id`、`authority`）重算，结果逐字相等。`S11`：给验证记录加 `authority`/`authority_evaluation` 后摘要不变；请求里的 `scope.verification.digest` 等于当前 `verification_subject_digest`；源码检查 `X4` 确认 `_criterion_approval_scope` 与 `_approval_evidence` 都调用同一函数（`authority.py:59-74`；文档 `data-contracts.md`「审批事件」节写明排除项） |
| 11 | reconcile：无 `approvals/` 目录不新增 finding；孤立/不匹配审批按卡面 code/severity 报告；不写 defect | **PASS** | `S12a`：无目录时无 `approval_*` finding、defects=0。`S12b`：改写验证记录 → `approval_subject_mismatch`(high)、defects=0。`S12c`：指向不存在 Goal → `approval_orphan`(high)。`S12d`：reject → `approval_rejected`(low)。`S6`：stale → medium。未配置锚/坏签名 → `approval_not_trusted`(medium)（卡面设计如此）。均未写入 defect |
| 12 | `authority.py` 仍只有一处 `os.environ.get`；未新增外部依赖；未从 PATH 选择验证器 | **PASS** | `X1`：计数 = 1（`authority.py:442`）；`X2`：无 `import subprocess`、无 `shutil.which`；`X3`：`pyproject.toml` 无差异。既有测试 `test_module_keeps_no_external_verifier_dependency` 通过（双门槛整体通过） |
| 13 | 附加契约（卡 §4）：同名同内容幂等；不同内容拒绝覆盖；空签名、仓库身份不符、非 40 位提交被拒 | **PASS** | `S13`：重复 attach `created` 依次 `True/False`；改写已有记录后被拒（`已存在且内容不同，拒绝覆盖`）；空签名 `签名为空`；仓库 id 不符 `仓库身份与当前仓库不一致`；39 位提交 `commit_sha 必须是完整的 40 位 SHA` |

补充结论：`approval verify` 只检查“验签通过 + `decision=approve` + `commit_sha` 等于 `--commit`”，不重新核对 criterion 绑定的验证记录摘要与 stale 状态；这是任务卡 §5 的既定语义（criterion 完整性由 `goal evaluate` 负责），README/OPERATIONS 的描述也与此一致，不构成偏差，但门禁读者不应把 `approval verify` 当作完整的 criterion 校验。

## 5. 负对照

同一 Goal、同一验证记录，只改审批证据的有无（`C:/Temp/pm03_b8_verify.log` 实际输出）：

```
negative-control before: satisfied=True status=satisfied
negative-control removed: satisfied=False status=insufficient_evidence
negative-control restored: satisfied=True status=satisfied
PASS | S14 negative control remove then restore | True->False->True
```

另做两次交叉对照：`S6` 在提交前进后由 satisfied 变 stale；`S7` 在重写验证记录后由 satisfied 变摘要失效、恢复后重新 satisfied。三者都证明满足来自审批事件本身，而不是缓存或其它证据。

## 6. 偏差

| 编号 | 严重度 | 证据 | 建议 |
|---|---|---|---|
| D-1 | low | `iter_approvals`（`coordination.py:2021`）对 `.project-memory/approvals/` 内不可解析的 JSON 静默 `continue`。独立实测：放入 `{not json` 后，`reconcile` 的 `approval_*` findings 为空、`approval list` 计数为 0。 | 不阻断：损坏记录无法 satisfy（解析失败即无法引用）。后续可考虑新增 `approval_unreadable` 之类的 code；本卡未定义，不建议在本卡扩范围。 |
| D-2 | info | trusted 路径的单测与本次独立脚本都通过 patch `authority.load_anchor` 的审批分支模拟受保护锚；真实 `anchor_is_protected`（非当前用户所有、不可写）未做端到端。单用户 Windows 上真实 CLI 只能验证 fail-closed（exit 2）。PM-02 handoff §8「未验证项」第 1 条已披露。 | 与 B-7/B-10（密钥托管、独立主体）一起在具备独立属主的 CI/主机上补端到端；本卡范围内可接受。 |
| D-3 | info | `scope=criterion` 要求绑定验证记录 `mapping_status=complete`，而本地 CLI 写出的映射上限是 `review_required`；测试通过模拟“外部已确认”的验证记录来满足前置条件。PM-02 handoff §8「偏差」第 2 条已披露。 | 属既有 B-4 边界，不是 B8 绕过；真实使用依赖外部确认流程。 |
| D-4 | info | `approval_id` 的摘要输入排除 `approval_id` 与 `authority`（卡面字面只写“不含 authority”）。若把 `approval_id` 纳入会自引用，实现与文档均按“排除两者”写明。PM-02 handoff §8「偏差」第 1 条已披露。 | 接受；文档 `data-contracts.md` 与实际算法一致。 |
| D-5 | info | 未配置审批锚时，reconcile 对每条 `approve` 审批报 `approval_not_trusted`(medium)。这是卡面表格的设计；`--fail-on high` 不受影响。 | 无需处理；部署时配置锚后自然消失。 |

没有 high/medium 级功能或安全偏差。未触发“可直接判 FAIL”的条件。

## 7. 未验证项

1. **无真实审批密钥、无受保护外部审批锚**：受任务约束未建真实密钥、未联网；trusted 端到端仅以 openssl 测试密钥 + 打桩锚完成，真实 `anchor_is_protected`（文件属主/权限）路径未在本机复现。
2. **未跑托管 CI、未验证 key custody / Ruleset / CODEOWNERS / 合并权限**；这些属 B-7/B-10。
3. **未复跑基线 pytest 的 280 passed 计数**（handoff 的陈述）；本次只按任务卡要求复跑头部的双门槛与定向测试。基线 audit 的多重集已独立复跑。
4. 未验证 `origin/dev/v1.0` 前进（`999713b`）后与本分支的合并冲突；本次未合并、未 rebase，PM-01 合并时需按当时的 `dev/v1.0` 重新跑门禁。
5. 未在 POSIX（非 Windows）上复跑属主保护路径。

## 8. 声明

**本报告不构成合并批准。** 它只记录 PM-03 的独立实跑事实与偏差，合并决定、PR 审批与后续 tag/Release 由 PM-01/人类按流程执行。
