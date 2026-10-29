# v1.0.0 最终安全审查（PM-03，独立）

- 审查对象：`dev/v1.0` @ `f79a85f49cbdf3d0e2804c3485c1ca630a226ec1`（R1 合并提交，PR #32）
- 树校验：`e5dec3fd1201e830768e6960779df372e628bf77`，与候选 `9d5f957` 的树一致
- 审查分支：`review/final-v1.0.0`（从目标 SHA 检出的独立 worktree）
- 审查时间：2026-10-29（UTC 11:35–11:50）
- 环境：Windows 10.0.26300（MINGW64/MSYS），Python 3.12.4（`C:\SoftWare\Anconda\python.exe`），pytest 9.1.1，OpenSSL 3.5.9（Git MSYS），WSL2 Ubuntu 可用
- 证据目录：`evidence/FINAL/20261029T113521Z/`
- 性质：安全意见，不是发布决定；未打 tag、未建 Release、未合并、未 Approve

## 0. 结论摘要

**SECURITY: GO-READY**（无 Critical / High；3 个 Medium 发布文档缺陷不削弱安全语义，属发布前应修项）

安全机制 B0–B4、B5A/B5B、R1 在本机动态验证中按设计 fail closed：

- 来源与签名（B2）：仓库外锚 + 进程内验签；未配置/不匹配/签名错误一律 `untrusted`，无绕过路径；
- 沙箱（B3/B5B）：`test-run` 默认拒绝执行（exit 3，无快照/收据/副作用）；WSL2 用例实际执行（非 skip），宿主 marker 未出现；
- 审计链（B4）：从 genesis 重算；篡改后重算全链被 checkpoint 前缀检出；未签名 checkpoint 被拒；`achieved` 只有在 anchor 签名的 checkpoint 校验通过后才 `status_trusted=true`；
- 启动器（B5A）：`-I -P` + 绝对路径启动；PYTHONPATH/cwd 同名包不生效；缺解释器/缺启动器 exit 3；
- R1 门槛：空必达集合在 evaluate/show/transition/create 四条路径全部 fail closed，且进入机器可读字段；openssl 开关只作用于测试层；
- 跨切面：未发现硬编码私钥/凭据；运行时无 `eval/exec/pickle/yaml.load`；唯一 `shell=True` 是用户显式选择的 `test-run --command` 字符串。

## 1. 审查范围与方法

| 面 | 内容 | 方法 |
|---|---|---|
| A | 来源/签名/信任根、密钥泄漏 | 静态审读 `authority.py` + 全仓秘密扫描 + B2 定向测试 |
| B | 沙箱与不可信执行 | 静态审读 `trusted_exec.py`/`execution.py` + B3/B5B 测试 + 手工 CLI 默认拒绝 + WSL 用例实跑 |
| C | 审计链/checkpoint/派生状态 | 静态审读 `coordination.py` + 临时仓库 E2E（测试密钥）+ 篡改/未签名拒绝 |
| D | 启动器/CLI 隔离 | 静态审读包装器/launcher/`__main__` + 手工 shadow/missing-interpreter 场景 |
| E | R1 发布门槛 | 全量 pytest（开关开/关、openssl 有无）+ 手工 CLI 四路径 + 版本/CHANGELOG/标签 |
| F | 跨切面 | 文档示例、退出码契约、`.gitignore`、原子写、ACL 边界、依赖声明 |

动态环境说明（限制，见 §5）：本机同一 Windows 账户无法满足 `anchor_is_protected` 的“所有者 ≠ 当前用户”条件，因此 E2E 的签名环节用**临时测试 RSA 密钥**并通过与 B4 测试相同的 `authority.load_anchor` 打桩加载测试锚；真实生产锚 ACL 未验证。未使用生产密钥/锚，未联网。

## 2. 分面结论

### A. 来源与签名（B2）— 通过

- 信任根只来自仓库外 `PROJECT_MEMORY_TRUST_ANCHOR`；`load_anchor` 拒仓库内路径、非文件、非法 JSON、未知 kind/schema/算法、缺字段，并要求 `anchor_is_protected`（`project_memory/authority.py:408`；保护检查 `:378`）。
- 验签为进程内实现：PKCS#1 v1.5 SHA-256 全填充校验、ECDSA P-256 严格 DER/范围/曲线点检查；RSA 模数 ≥2048；常数时间比较；任一失败返回 `(False, reason)`（`authority.py` 验签段）。
- `verification_authority`/`signed_record_authority` 要求 envelope 的 `anchor_id/issuer/algorithm` 与锚一致、`signed_payload_sha256` 等于实际载荷摘要、签名非空；不接受自报 `status=trusted`（`authority.py:443,571`）。
- 收据来源与内容完整性分离：本地执行 `execution_provenance.kind=local_untrusted`、`trusted=false`；`_provenance` 从不返回 trusted（`execution.py`）。
- 秘密扫描：无 `PRIVATE KEY` 块；测试中仅 `token='super-secret-token'` 之类假值。

备注（非缺陷）：`_verify_execution_attestation` 校验 attestation 自身隔离声明与收据/提交绑定（`execution.py:595-616`），但不比对收据自报的 `isolation.mode`（本地执行可为 `none`）。attestation 必须由 anchor 签名，属信任根的声明能力，见 I-2。

### B. 沙箱与不可信执行（B3/B5B）— 通过

- `test-run` 无模式/双模式 → exit 3，拒绝执行且不写快照/收据（`project_memory/cli.py:524-536`；动态：`openssl` 无关，B5B 测试 + 手工）。
- `--allow-local-untrusted`：普通子进程，收据 `trust=local_untrusted`、`isolation.mode=none`；子进程剥离宿主 `PYTHONPATH` 等敏感变量并设 safe-path（`execution.py:678-686, 771`）。
- `--trusted`：`wsl_available` 预检先行，失败即 `BLOCKED` exit 3，不回落本地（`trusted_exec.py:90,206`）；内部脚本用 `env -i` allowlist、tmpfs 屏蔽 `/mnt /home /root /var /tmp /etc/ssh ...`、PID/网络命名空间与 canary 校验。
- 动态：`tests/test_security_b5b.py::B5BTest::test_trusted_runs_isolated_and_host_marker_absent` 实际执行并 **1 passed**（2.70s，非 skip）；沙箱内看不到宿主路径。

### C. 审计链与 checkpoint（B4）— 通过

临时仓库 E2E（`e2e-summary.json`，测试密钥）：

1. `init` → `goal create` → `goal evaluate`（无证据，exit 2，`satisfied=false`）；
2. 本地收据 + anchor 签名 attestation + 签名验证记录 → `evaluate` exit 0、`satisfied=true`；
3. 状态转换 `approved → active → evaluating → achieved` 全 exit 0；`audit checkpoint-request` 生成 `chain_length=5` 的未签名载荷；
4. 未配置锚时 `checkpoint-attach` 拒绝（`无法验证 checkpoint：未配置受保护的信任锚`，`head.json` 不存在）；
5. 另一把密钥签名 → 拒绝（`签名无效`），`head.json` 不存在；
6. 测试锚签名 → `trusted=true`，`audit verify` `status=valid`、`authoritative=true`，checkpoint `chain_head` 与链头一致；`goal show` `effective_status=achieved`、`status_trusted=true`、`status_authority=anchor_signed_checkpoint`；
7. 篡改一条记录并重算全链 → `audit verify` `invalid`（`checkpoint_chain_mismatch`），`effective_status=achieved_unverified`、`status_trusted=false`；
8. 去掉 checkpoint 的 `authority`（未签名）→ `invalid`（`checkpoint_untrusted`）；
9. 恢复后重新 `valid`/`authoritative`。

CLI 层面：带测试锚（进程内）`audit verify` exit 0；**不带锚（真实子进程）exit 2 + `checkpoint_untrusted`**，证明仓库内 checkpoint 不能自证可信。

### D. 启动器/CLI 隔离（B5A）— 通过

- 包装器以绝对路径定位 launcher，解释器选择 `PROJECT_MEMORY_PYTHON → 同目录 venv → PATH`，缺失 exit 3（`bin/project-memory`、`bin/project-memory.cmd`）。
- 手工：cmd 包装器正常 `--help` exit 0；PATH 无解释器 exit 3；复制包装器但无 launcher exit 3；sh 包装器在无 python 的 POSIX PATH 下 exit 3。
- `PYTHONPATH` 影子包：包装器 exit 0 且无 `SHADOW_*` 输出、无 marker；裸 `python -m` 在仓库根（受信包先导入、影子在 sys.path 上）exit 3（`同名`）；影子包排在解析最前时由影子执行——这是 `-m` 的固有行为，已在 `docs/OPERATIONS.zh-CN.md:41` 明确，包装器不受影响。

### E. R1 发布门槛 — 通过（含一处文档契约偏差 M-3）

- 全量：默认 **253 passed / 2 skipped，exit 0**；`PROJECT_MEMORY_REQUIRE_OPENSSL=1` 同样 **253 passed / 2 skipped，exit 0**（2 个 skip 仅因平台不允许创建符号链接：`tests/test_security_rc3.py:284,295`）。
- 缺 openssl：默认 **37 skipped exit 0**（13 B2 + 10 B3 + 14 B4）；开关开启 **37 errors exit 1**，消息同时含 `openssl` 与开关名。
- 空必达集合（手工 CLI，临时仓库）：
  - `required=false` → `goal evaluate` exit 0，`satisfied=false`，`evaluation_status=insufficient_evidence`，`no_required_criteria=true`，`status_problems=["no_required_criteria"]`；
  - `goal show` 正常可读，problems 同上，`effective_status` 非 achieved；
  - 删除全部必达判据 → 同上；
  - `transition --to achieved` exit 1，Goal 仍为 `evaluating`，无 `head.request.json`，审计末条 `outcome=rejected`、`reason=goal_achieved_unsatisfied`、`no_required_criteria=true`、`evaluation_status=insufficient_evidence`；
  - `goal create` 无判据/仅可选判据 → exit 1（`至少需要一个必达的成功标准`）。
- openssl 开关只在 `tests/openssl_support.py` 与 `tests/test_security_r1.py` 出现；运行时包内无 `openssl` 字样；`dependencies = []`。
- 版本：`pyproject.toml:7` 与 `project_memory/__init__.py:2` 均为 `1.0.0`；`CHANGELOG.md` 首条 `[1.0.0] — 2026-10-29`；本地无 tag（0 个）。
- 契约：`skill/project-memory/assets/` 共 **21** 份 schema，与 `docs/ARCHITECTURE.zh-CN.md:198` 一致；`audit-ledger.schema.json` 的入口/checkpoint 必需字段与真实样本（`schema-samples/`）一致；verification schema 注明 `goal_criteria_sha256`。

### F. 跨切面 — 通过（发现见 §3）

- 秘密/私钥：无。
- 危险构造：运行时无 `eval/exec/pickle/marshal/yaml.load`；`subprocess` 8 处，除 `test-run` 外均为列表参数；唯一 `shell=True` 位于 `execution.py:771`，仅用于用户显式选择的命令字符串。
- 原子写：`common.atomic_replace` 用同目录 `NamedTemporaryFile` + `os.replace`；`write_new` 用硬链接/`O_EXCL` 防覆盖；无固定临时名。
- 错误信息：未发现回显私钥或 anchor 内容；`untrusted` 原因只含路径/状态。
- 发布文档：见 M-1/M-2/M-3。

## 3. 发现清单

### Critical

无。

### High

无。

### Medium

**M-1 README 的本地 `test-run` 示例与命令表未体现 B5B 的强制模式参数** — `README.md:92`（示例仅有 `--command/--agent`）与 `README.md:158`（`test-run --command '...' [--trusted]`）。照抄示例会 exit 3（默认拒绝），首次使用失败。
可利用性：无安全影响（fail closed），但 v1.0.0 快速上手路径不可用。
修复：示例补 `--allow-local-untrusted` 或改用 `--trusted`；命令表标注“必须二选一”。

**M-2 OPERATIONS 与 Skill 参考中的 `--approved-by 'human-owner'` 不是合法邮箱，命令必被拒绝** — `docs/OPERATIONS.zh-CN.md:80,170`；`skill/project-memory/references/workflows.md:81,95,99`。实测 `goal transition --to approved --approved-by 'human-owner'` 返回 exit 1（`approved_by 必须是邮箱地址格式…`）。
可利用性：无（拒绝方向正确），但文档给出的批准/checkpoint 请求流程无法执行。
修复：示例改为 `reviewer@example.com` 等邮箱，并说明该值用于追溯而不是认证。

**M-3 `goal evaluate` 的“空必达集合 exit 0”未在运维文档中说明，且与现有退出码说明冲突** — 实现见 `project_memory/cli.py:467-472`（R1 有意 exit 0）；`docs/OPERATIONS.zh-CN.md:147` 仍写“未满足时退出 2”。
影响：只看退出码的 CI/脚本会把 `insufficient_evidence` 当作通过；JSON 中 `satisfied=false` 与 `no_required_criteria=true` 是机器可读的，但退出码契约有歧义。仓库内随附的 workflow 模板只运行 `audit --fail-on high`，不存在已知的门禁误用。
修复：在 OPERATIONS/README 明确该例外，并要求自动化消费 `satisfied`/`effective_status`/`status_trusted`；如需退出码门禁，后续版本增加显式 `--strict`（不在本版范围）。

### Low

**L-1 `.project-memory/.gitignore` 只忽略 `cache/issues/prs/`** — `project_memory/bootstrap.py:142`。执行日志（可能含命令输出）与快照/收据默认不被忽略，`git add -A` 可能把它们带入历史。
可利用性：低（需用户误提交；本地环境已剥离敏感变量，但日志内容不受控）。
修复：把 `logs/ snapshots/ attest/ verifications/` 等运行产物加入默认忽略项，收据是否入库由项目显式决定。

### Info

**I-1 `status_trusted` 在非终态为 `null`，ADR-0007 写“为 true 且 problems 标注非终态声明”** — 实现 `coordination.py::_achieved_status` 对非 `achieved` 返回 `(raw, None, [])`；实测 proposed Goal：`status_trusted=null, status_problems=[]`。文档 `docs/decisions/ADR-0007-audit-integrity.md:164` 与实现不一致（实现更保守）。建议改文档或改字段语义，二者择一。

**I-2 执行 attestation 不交叉校验收据自报的隔离事实** — `execution.py:595` 只校验 attestation 自身 `isolation` 合法性与收据/提交绑定；本地执行的收据 `isolation.mode=none` 仍可配一份“已隔离”的 anchor 签名 attestation。因签名者是信任根，属“信任根可作任何声明”的已接受边界；建议在收据与 attestation 隔离字段冲突时给出显式 `provenance_inconsistent`。

**I-3 审计追加为单写者假设** — `coordination.py:553-571` 读全量→重算→原子替换，无跨进程锁；已在 ADR-0007 §7.7 与 `docs/OPERATIONS.zh-CN.md:291` 披露。多 Agent 并发写可能丢一条记录（链仍自洽）。

**I-4 checkpoint 前缀锚** — checkpoint 之后的追加不受签名保护；删除/重写这些条目只能靠链链接检测，重算则不可检测，但不影响已签前缀的 `achieved`。ADR-0007 §7.4 已作为有意取舍披露。

**I-5 库入口默认 `mode='local'`** — `execution.run_command(..., mode='local')`（`execution.py:714`）。CLI 已强制显式模式，但库调用方若省略参数仍会在宿主执行；属 B5B 的已知边界，所有库调用方未逐一审计（见 §5）。

**I-6 Windows 锚保护仅检查文件所有者与可写性** — `authority.py:378-405` 不检查父目录 ACL；替换后新文件所有者会变为当前用户而被拒，因此未发现可利用路径，但“第二主体 ACL”本身未验证（见 §5）。

## 4. 发布阻断项（仅 Critical/High）

无。

M-1/M-2/M-3 建议在人类发布决定前修复（文档/退出码契约），不影响安全结论：相关行为均 fail closed。

## 5. 未验证（NOT VERIFIED）

1. **生产 anchor 端到端签名**：本机同一 Windows 账户无法满足“所有者 ≠ 当前用户”，E2E 使用测试密钥 + 打桩锚；真实受保护锚的 attach/verify 未跑。
2. **真实第二主体 ACL**：未建立第二个 OS 主体/权限模型，锚保护只在同用户场景验证了“拒绝”。
3. **POSIX `pip install`**：只在 Windows 上验证安装与包装器；POSIX 安装布局未验证。
4. **WSL2 启动器真实性**：沙箱行为已实跑，但生产环境“attestation 由谁签名/私钥如何保管”的端到端真实性未验证（E2E 的 attestation 用测试锚签名）。
5. **远程 tag / Release**：按约束未联网查询远端；仅确认本地无 tag。
6. **B5B 库默认 local 边界**：`run_command` 默认 `local` 的所有库调用方未逐一审计（CLI 路径已强制显式模式）。
7. **多写者并发审计**：单写者假设下未做并发压测（ADR 已披露）。
8. **Python 3.11 / macOS / 其他 OpenSSL 版本**：本次仅 Python 3.12.4 + OpenSSL 3.5.9。
9. **本地状态目录 ACL**：`.project-memory/` 在 Windows 上按默认继承 ACL 创建，未验证部署侧加固。

## 6. 回归与证据索引

| 项 | 结果 | 证据 |
|---|---|---|
| 全量 pytest（默认） | 253 passed / 2 skipped，exit 0 | `pytest-default.log` |
| 全量 pytest（REQUIRE_OPENSSL=1） | 253 passed / 2 skipped，exit 0 | `pytest-require-openssl.log` |
| 缺 openssl（默认） | 37 skipped，exit 0 | `openssl-missing-default.log` |
| 缺 openssl（开关开） | 37 errors，exit 1 | `openssl-missing-required.log` |
| B2/B3/B4/B5A/B5B/R1 定向 | 63 passed / 0 skipped | `regression-security-targeted.log` |
| WSL2 trusted 用例 | 1 passed（实际执行） | `wsl-trusted-exec.log` |
| 审计链 E2E（测试密钥） | 全流程符合预期，篡改/未签名被拒 | `e2e-run.log`、`e2e-summary.json`、`schema-samples/` |
| R1 四路径 CLI | evaluate/show/transition/create 全部 fail closed | `r1-gates.log`、`r1-gates-summary.json` |
| 启动器隔离 | 正常/缺解释器/缺 launcher/shadow 场景符合预期 | `launcher-isolation.log` |
| 静态扫描 | 无密钥、无危险构造、版本/标签 | `static-scans.log` |
| 环境 | Python/OpenSSL/WSL/树校验 | `environment.txt` |
| 校验和 | 证据文件 sha256 | `sha256sums.txt` |

复现：`evidence/FINAL/20261029T113521Z/e2e_run.py` 与 `r1_gates.py` 为只读审查脚本（临时仓库位于系统临时目录，测试密钥不落证据）。

## 7. 结论

安全机制在本机按设计工作，未发现 Critical/High；发布文档存在 3 处 Medium 不一致（M-1/M-2/M-3），建议在人类 GO/NO-GO 决定前修正，但不构成安全阻断。以上为安全意见，不代表人类发布批准。
