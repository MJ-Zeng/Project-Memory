# REVIEW-B1 — PM-03 独立审查报告

- 审查者：PM-03 Independent Reviewer（独立 Clone `pm-pilot-03`）
- 审查 run：`review-20261028T1802`
- 审查分支：`review/b1-1c7ad94`（从候选 `1c7ad94` 检出；审查产物只追加 `pilot/review/B1/`、`pilot/evidence/B1/review-20261028T1802/`、`pilot/rounds/B1/context-recovery-pm03.md`）
- 审查时间：2026-10-28（本机 +08:00）
- 结论：**PASS（程序性独立复核；合并/`achieved` 仍由人类决定）**，附一条 **B1 范围外 HIGH 发现**（见 §7）。

## 1. 对象与哈希

| 项 | 值 | 我的核对 |
|---|---|---|
| 基线 | `25a919d63c7181fd4083e0fc1af33734d74c5515` | `git rev-parse` ✓ |
| 候选 | `1c7ad94f8c3beb369f4a86a33accda6910213105` | `git rev-parse` ✓ |
| 分支头 | `216f154da797a2e5c295e01f11429978796aa7c7` | `git rev-parse` ✓ |
| 分支头 - 候选 | 仅 `+ .project-memory/handoffs/B1/run-20261028T1344.json`、`+ pilot/rounds/B1/handoff-run-20261028T1344.md` | `git diff --name-status 1c7ad94 216f154` ✓ |
| 候选是基线的后代 | 是 | `git merge-base --is-ancestor` ✓ |
| 任务卡 SHA-256 | `0fdc9469456b81bae26a3c29385f1745222e16b19211e27d4d04a418ef3be08d` | `sha256sum` ✓ |
| 冻结参照 | `0d08a1ad85144d11a46d6a361a2a3ce4eadbbed4` | 只解析，未 checkout/改写 |
| 基线探针 SHA-256 | `827ad0c29d50cd15ce345485d24e5a75edf069522c89b048236c08ba9e617c73` | 从 `.pilot/b1-base` 取 ✓ |
| `authority.py` 基线 / 候选 | `4805b06b…a88d` / `163a08ad…18ea` | `sha256sum`，运行期亦复核一致 |
| PR | 未开（`missing_artifacts`，按提示词不构成 FAIL） | — |

所有硬约束满足，未触发任何停止条件（候选/头/任务卡哈希一致；头部只多两个 Handoff 文件）。

## 2. 静态审查结论

`git diff 25a919d..1c7ad94` 的代码改动仅 3 个文件：`project_memory/authority.py`（+325/−48）、`tests/test_authority_verifier.py`（新增 279 行）、`docs/decisions/ADR-0002…`（新增 136 行），另有 `pilot/` 证据与 Handoff。

- **验证路径去环境化**：候选 `authority.py` 不再 `import shutil/subprocess/tempfile`；`grep` 全文件只剩 1 处 `os.environ.get`，即 `load_anchor` 的 `PROJECT_MEMORY_TRUST_ANCHOR`（信任锚路径，属设计允许的调用者输入，由 `anchor_is_protected` 约束）。`PROJECT_MEMORY_OPENSSL`、`PATH`、`powershell.exe`、`shutil.which` 全部消失。
- **进程内验签**：`_verify_signature` 为纯标准库实现（RSA PKCS#1 v1.5 + SHA-256；ECDSA P-256 + SHA-256），自写最小 DER/SPKI 解析；任何解析/算术异常返回 `(False, …)`，**fail closed**，无回退、无子进程。
- **语义保持（AC-9）**：`verification_authority`、`load_anchor`、`untrusted_envelope` 函数体未改；`anchor_id`/`issuer`/`algorithm`/`signed_payload_sha256`/`signature_b64`/`trusted` 判定顺序与语义保持。`_verify_signature` 公共签名 `(anchor, payload, signature_b64, algorithm) -> tuple[bool,str]` 不变（B0 的 `tests/test_repo_identity.py` 依赖）。
- **同族弱点**：Windows 所有者检查由 `powershell.exe` + `USERNAME/USER` 改为 `advapi32` SID API（`GetNamedSecurityInfoW` / `OpenProcessToken`+`GetTokenInformation` / `EqualSid`），失败即拒绝。
- **测试**：`test_authority_verifier.py` 仅新增，含正向/负向向量、假验签器、静态守卫；无 `skip`/`xfail`；既有测试无修改/删除（`git diff --diff-filter=MD -- tests/` 为空）。
- **范围**：未改 `pilot/kit/`、`task.md`、判据、探针、`frozen/`；未夹带 B2/B3/B4/B5 行为变化；`pyproject.toml` 未改（运行依赖仍为空）。
- **ADR-0002**：与实现一致；残余风险明确列出 `LD_PRELOAD`/DLL 侧加载、root 妥协、无吊销、PYTHONPATH/sys.path、时间侧信道、算法收敛。

## 3. AC 逐项结果

| AC | 结果 | 方法与证据 |
|---|---|---|
| **AC-1** 有效签名仍可用 | **PASS** | `positive.json`：manifest 7/7；`template-repo` 解包到仓库外 `/tmp` 并复制后，以 uid 1000 运行 `goal evidence --ref VER-positive` → **exit 0**，**stderr 0 字节**，记录 SHA-256 前后均为 `d6f30d6f…f362`（未变），输出与 `goal-evidence-result.json` 语义一致（仅 `updated_at`/`at` 时间戳不同） |
| **AC-2** PATH 替换被拒 | **PASS** | `probe-after.json`：`path_substitution_exit=1`、`path_substitution_accepted=false` |
| **AC-3** `PROJECT_MEMORY_OPENSSL=/bin/true` 被拒 | **PASS** | `env_true_exit=1`、`env_true_accepted=false` |
| **AC-4** `PROJECT_MEMORY_OPENSSL=<fake openssl>` 被拒 | **PASS** | `env_openssl_exit=1`、`env_openssl_accepted=false` |
| **AC-5** 打印 `Verified OK` 的假验签器被拒 | **PASS** | `ac5_fake_openssl.json`：自建假 `openssl`（内容 `echo "Verified OK"; exit 0`，SHA-256 `e0587183…acd6`）经 PATH 与 `PROJECT_MEMORY_OPENSSL` 两路 → 候选 **exit 1 / accepted=false**；同一假体在基线 `ac5_fake_openssl_before.json` → exit 0（证明向量真实） |
| **AC-6** 验证器身份固定、失败关闭 | **PASS** | 静态 + 26 项新单测 + 探针 control（真实 openssl 拒伪造）；缺 anchor/解析失败/算法不匹配均拒绝（`load_anchor`/`_verify_signature` fail closed） |
| **AC-7** 攻击链不能到 `achieved` | **PASS** | 自建链 `chain-before.json`/`chain-after.json`：基线 `goal evidence`=0→evaluate satisfied→`achieved`=0，**最终 `achieved`**；候选 `goal evidence`=1（untrusted：签名验证失败）→evaluate=2 satisfied=false→`achieved`=1（insufficient_evidence），**最终 `evaluating`，evidence=0** |
| **AC-8** 回归通过 | **PASS** | 候选 `pytest.log`：**190 passed, 2 skipped**；基线 `pytest-baseline.log`：**164 passed, 2 skipped**；差值恰为新增 26 项；skip 均为同一 `tests/test_security_rc3.py:284,295` 平台跳过，无新增/删除 skip |
| **AC-9** 无新绕过 | **PASS** | `bypass.json`：自建一次性 RSA-2048/ECDSA-P256 密钥 → 真签名接受、篡改/换 key/垃圾签名拒绝；攻击者自建 anchor + 密码学自洽伪造记录 → 被 `anchor_is_protected` 拒绝；伪造签名记录（直接写盘）→ 拒绝；既有 RC3 测试全绿 |
| **AC-10** 决策记录 | **PASS** | `ADR-0002` 与实现一致；`LD_PRELOAD`、root、轮换、PYTHONPATH 残余风险明确 |
| **AC-11** 范围纪律 | **PASS** | `diffstat.txt`：代码/测试/文档改动全部落在允许范围；禁止路径为空 |

## 4. 探针 before / after 对照

| 键 | 基线（b1-base） | 候选（b1-candidate） |
|---|---|---|
| `control_rejected` | true (exit 1) | **true (exit 1)** |
| `path_substitution_exit` / `_accepted` | 0 / **true** | **1 / false** |
| `path_evaluate_exit` | 0 | 不存在（首步被拒） |
| `path_achieved_exit` | 0 | 不存在（首步被拒） |
| `path_goal_status` | **achieved** | 不存在（首步被拒） |
| `env_openssl_exit` / `_accepted` | 0 / **true** | **1 / false** |
| `env_true_exit` / `_accepted` | 0 / **true** | **1 / false** |
| `agent_owned_anchor_rejected` | true (exit 1) | **true (exit 1)** |

候选被拒原因（`probe-after.json` 的 stderr）为应得的 fail-closed 文本：`…没有可信授权来源（untrusted）：签名验证失败`；agent 自有 anchor 为 `unconfigured：…信任锚所有者是当前用户…`。均非崩溃。

## 5. 攻击链 before / after（自建，非 PM-02 脚本）

链：伪造签名记录（假 `openssl` 在 PATH）→ `goal evidence`（带 Goal 摘要重绑）→ `goal evaluate` → `approved`→`active`→`evaluating`→`achieved`。

| 步骤 / 观测 | 基线 | 候选 |
|---|---|---|
| `goal_evidence_exit` | **0（接受）** | **1（untrusted：签名验证失败）** |
| `goal_evaluate` | exit 0，`satisfied=true` | exit 2，`satisfied=false` |
| approved/active/evaluating | 0/0/0 | 0/0/0 |
| `transition_achieved_exit` | **0** | **1（insufficient_evidence）** |
| 最终 Goal 状态 / evidence 数 | **achieved / 1** | **evaluating / 0** |

结论：修复前无需私钥即可把 Goal 推到 `achieved`；修复后同一链停在 `evaluating`。

## 6. 正向 fixture 与回归

- 正向 fixture：`pilot/kit/b1/positive/sha256sums.txt` 在仓库外解包目录 **7/7 OK**；以 uid 1000、root 持有的 `/etc/pm-rc3-review/anchor-a.json` 运行 `goal evidence` → **exit 0、stderr 0 字节、记录 SHA-256 不变**。未修改 fixture、未签名。
- 回归：Windows `C:\SoftWare\Anconda\python.exe` 3.12.4 / pytest 9.1.1。
  - 基线实测 **164 passed / 2 skipped**（我独立重跑）。
  - 候选实测 **190 passed / 2 skipped**；新增 26 项恰为 `test_authority_verifier.py`。
  - **AC-8 的“147”偏差**：任务卡 §4 AC-8 与 Issue 写“147 项既有测试”，实测基线为 **164**（`STATUS.md` 的“147 collected”为旧值）。此为派发前既有的过期数字，**我没有修改任务卡**，按实测基线判定；建议后续在非冻结轮次更正文档。

## 7. 新发现与我自己尝试的绕过

按严重度：

1. **[HIGH，B1 范围外]** `PYTHONPATH` / 当前工作目录中的同名 `project_memory/` 可整体顶替候选模块（`pythonpath_shadow.txt`：shadow 包先于候选被导入，`python -m project_memory` 直接执行 shadow 并以 exit 0 返回）。这是一种“整程序替换”，等于替换 `python3` 或磁盘上的源码，**任何进程内验签实现都无法防御**；它在基线同样成立（非本次修复引入），且 `ADR-0002 §6.2` 已明确列为残余风险并归属 B5/沙箱。**它不改变候选验签器本身的判定**，因此不构成本轮 B1 的功能回归；但它是真实的部署/调用加固缺口，建议由 B5 或启动器/打包层处理（例如固定入口、`-P`/`-I` 隔离、校验模块来源）。
   - 对 §4.7 “成功即 FAIL”的说明：我把“成功”定义为“在运行候选代码的前提下使伪造签名被接受”。PYTHONPATH/cwd 顶替并未让候选的 `authority` 判定被绕过，而是替换了整段程序，故不按 B1 FAIL 处理；此判断已显式记录，供人类复核与推翻。
2. **[LOW]** 任务卡 AC-8 的“147”与实测 164 不一致（见 §6）。不阻塞，属文档陈旧。
3. **[INFO]** `pilot/STATUS.md` 仍为 `blocked_by_B0` 的过期快照，未反映本轮候选。

我实际尝试并记录的绕过面：伪造签名写盘（拒绝）、攻击者自建 anchor + 自洽自签记录（拒绝）、自建一次性密钥的 RSA/ECDSA 交叉验证（正确接受真签名、拒绝篡改/换 key/垃圾）、`PATH`/`PROJECT_MEMORY_OPENSSL` 假验签器（拒绝）、PYTHONPATH/cwd 模块顶替（成功，但属整程序替换，范围外）。
`LD_PRELOAD` 未单独植入：候选验签路径已无子进程，纯 Python 运算不经外部二进制；其影响与 PYTHONPATH 同属“整进程/整程序”层，归 B5。

## 8. 残余风险 / NOT VERIFIED

- 未在**纯 Windows（非 WSL）** CLI 路径端到端复跑 `goal evidence`；WSL 端到端已跑。Windows 的 SID 所有者检查仅由 Windows pytest 单测覆盖（本次 pytest 在 Windows 3.12.4 上运行，`AnchorIdentityTest` 的 Windows 分支实际执行）。
- DER/SPKI 解析器未做随机 fuzz；仅测了自测向量与退化/越界输入。
- 未做 ECDSA 恒定时间/时序测量（ADR 已声明验证只用公钥、可接受）。
- 仅支持 `rsa-sha256`、`ecdsa-sha256`(P-256)；Ed25519/PSS/其它曲线一律拒绝（设计如此，非缺陷）。
- 未认证读取 GitHub Issue #1 正文/PR（本机无 `gh` 认证）；以仓库内任务卡/派发件为准。
- 私钥 `/etc/pm-rc3-review/key-a.pem`、`key-b.pem` 未读取；未用其签名。
- root 妥协、验签实现自身正确性的完整形式化证明不在本轮范围（ADR §6）。

## 9. 与 PM-02 自报的差异

- 探针、正向 fixture、回归计数、`authority.py` 哈希与运行期代码 SHA 全部一致。
- **AC-7 证据更强**：PM-02 的 `chain-before.json` 因省略摘要重绑步骤，基线链也未到 `achieved`（其已披露）；我用自建链完成摘要重绑，基线链确达 `achieved`，候选链停在 `evaluating`，因此 AC-7 有正面“攻击成功/被阻断”对照。
- 其余无实质分歧。

## 10. 最终 verdict

**PASS**（AC-1..AC-11 全部满足；三种替换与打印 `Verified OK` 的假验签器全部被拒；正向 fixture 独立通过；攻击链到不了 `achieved`；回归全绿；无 B1 范围内新绕过）。
此 PASS 是程序性独立复核，**不是**安全身份批准；合并、`Goal achieved`、ADR/Release 仍只能由人类确认。范围外 HIGH 发现见 §7。

## 11. 污染 / 偏差 / 耗时

- contamination：**无**。未读 PM-01/PM-02 会话、终端历史或工作树；未读 `/etc/pm-rc3-review/key-*.pem`；未使用 `project-memory-mvp` / `pm-import`。读取了 PM-02 提交进仓库的 Handoff/context/evidence（允许的仓库工件），但**未用其日志代替我的复现**。
- 偏差：任务卡 AC-8“147”与实测 164 不一致；`STATUS.md` 过期；PR 未开。均为已有/派发前状态，未修改任务卡。
- 上下文恢复（接手 → 正确复述 6 项事实）：约 **9 分钟**。

## 证据索引（`pilot/evidence/B1/review-20261028T1802/`）

`environment.txt`、`commands.jsonl`、`diffstat.txt`、`probe-before.json`、`probe-after.json`、`chain-before.json`、`chain-after.json`、`ac5_fake_openssl.json`、`ac5_fake_openssl_before.json`、`positive.json`、`pytest.log`、`pytest-baseline.log`、`bypass.json`、`pythonpath_shadow.txt`、`scripts/`、`sha256sums.txt`（清单最后写入，不覆盖自身）。
