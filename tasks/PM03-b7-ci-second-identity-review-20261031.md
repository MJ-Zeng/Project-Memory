# PM-03 独立复核：B7-CI-SECOND-IDENTITY-001（CI runner 作为第二身份）

- 日期（UTC）：2026-10-31
- 复核人：PM-03；执行者：PM-02；合并决定：PM-01 / 人类
- 被复核分支：`origin/feat/b7-ci-anchor`
- 被复核头（实查）：`53b11cf789f0c4eee17f68e80e575a35bf46f187`
  - 实现提交：`33660e211c962148a921c5904534092418f0429c`
  - 其后仅追加 handoff：`53b11cf`（`git diff --name-status 33660e2..53b11cf` 仅 `tasks/PM02-b7-ci-second-identity-handoff-20261031T042636Z.md`）
- 基线（实查）：`c3dea2a74ce666789e8a521a8eab7bcffe8654f2`（`origin/dev/v1.0`，与任务卡给定值一致）
- merge-base：`c3dea2a74ce666789e8a521a8eab7bcffe8654f2`（分支确实从基线开出）
- 复核 worktree：`C:/Temp/pm03-b7-target`（被复核头，detached → 本报告分支）与 `C:/Temp/pm03-b7-base`（基线）；均为本会话新建，未使用 `pm-pilot-02` 的工作目录
- 环境：Windows 10.0.26300；`C:/SoftWare/Anconda/python.exe`（Python 3.12.4）；pytest 9.1.1；PyYAML 6.0.1；OpenSSL 3.5.9；`PYTHONUTF8=1 PYTHONIOENCODING=utf-8`
- 输入边界：PM-02 handoff 仅作待核对对象，不作为任何结论依据；以下数字、退出码、输出均为本会话在自建 worktree 中实测。未读取真实 secret 值、未使用真实令牌、未访问真实 PR/CI。
- 本报告只作 PM-01 / 人类的合并输入，**不构成合并批准**。

## 1. 结论

**PASS WITH DEVIATIONS（条件式）。**

- 就任务卡 §2–§5 的实现与 §6 可在本地执行的门槛：未发现与卡面不符的失真或回归。26 条新测试、双门槛 `320 passed / 2 skipped`、audit 多重集与基线完全一致、`reconcile --fail-on high` exit 0、负对照与全部 fail-closed 与卡面一致。
- **D-1（High，安全/设计残余）**：`approval-gate` 执行的是 **PR head 检出树里的验证器代码**，且 GitHub 对 `pull_request` 事件使用的是 **PR 合并提交里的 workflow 定义**，不是 base 的定义。因此一个 PR 可以同时修改验证器/流程来让门禁通过，而不需要审批私钥。这与 README / OPERATIONS / governance 宣称的“门禁 job 在 base 提供的 workflow 定义下运行”不符。**在 B-10 把 `approval-gate` 设为必需检查之前，必须修复或由人类明确接受这一残余；仅补文档不足以把它当第二身份依赖。**
- **D-2（Medium）**：`GITHUB_ACTIONS` 是进程自报环境变量；本地进程设置 `GITHUB_ACTIONS=true` 并自带 JSON 锚/密钥可得到 `trusted` / `approved`（本会话已实测 exit 0）。文档“本地设置 JSON 锚不会生效”的说法过强。
- D-3～D-6 为 Low，D-7～D-10 为 Info。详见 §6。

D-1 不改变“实现忠实于卡面”的判断：卡面 §3 的模板本身就是“checkout PR head → 运行仓库里的 CLI”；本报告把该设计缺陷作为必须在依赖门禁前处理的残余记录在案，而不是把它算作 PM-02 的代码失真。

## 2. 范围与 SHA

```text
git diff --stat c3dea2a..53b11cf
 .github/workflows/approval-gate.yml                |  62 +++
 README.md                                          |  13 +-
 docs/OPERATIONS.zh-CN.md                           |  10 +
 project_memory/authority.py                        |  86 +++-
 project_memory/cli.py                              |  16 +-
 project_memory/coordination.py                     |  49 ++-
 skill/project-memory/references/governance.md      |   3 +
 tasks/PM02-b7-ci-second-identity-handoff-...Z.md   | 110 +++++
 tests/test_authority_verifier.py                   |  15 +-
 tests/test_b7_ci_second_identity.py                | 475 +++++++++++++++++++++
 tests/test_b8_signed_approval.py                   |   2 +-
 11 files changed, 824 insertions(+), 17 deletions(-)

git diff --name-status c3dea2a..53b11cf
A  .github/workflows/approval-gate.yml
M  README.md
M  docs/OPERATIONS.zh-CN.md
M  project_memory/authority.py
M  project_memory/cli.py
M  project_memory/coordination.py
M  skill/project-memory/references/governance.md
A  tasks/PM02-b7-ci-second-identity-handoff-20261031T042636Z.md
M  tests/test_authority_verifier.py
A  tests/test_b7_ci_second_identity.py
M  tests/test_b8_signed_approval.py
```

提交序列：

```text
53b11cf docs: add PM-02 handoff for B7 CI second identity
33660e2 docs(b7): document CI second identity and approval gate
143deb7 test(b7): cover CI anchor, records-dir gate, and workflow pins
d22f24f feat(b7): accept CI JSON anchor and add approvals gate
```

## 3. 独立实跑门槛

所有命令在 `C:/Temp/pm03-b7-base`（基线）与 `C:/Temp/pm03-b7-target`（被复核头）执行；两边工作树在测试前 `git status --porcelain` 均为空。

| # | 命令 | exit | 关键结果 |
|---|---|---|---|
| 1 | `git fetch origin --prune`；`git rev-parse origin/feat/b7-ci-anchor` | 0 | `53b11cf789f0c4eee17f68e80e575a35bf46f187`，与派单一致 |
| 2 | `git rev-parse origin/dev/v1.0` | 0 | `c3dea2a74ce666789e8a521a8eab7bcffe8654f2`，与基线一致 |
| 3 | `git diff --name-status c3dea2a..53b11cf` | 0 | 11 个路径，全部在卡面范围内 |
| 4 | `git diff --check c3dea2a..53b11cf` | 0 | 无空白错误 |
| 5 | 基线 `python -m pytest -q` | 0 | **294 passed, 2 skipped in 204.27s** |
| 6 | 目标 `python -m pytest -q` | 0 | **320 passed, 2 skipped in 204.97s**（+26，与卡面新增数一致） |
| 7 | 基线 `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q -rs` | 0 | **294 passed, 2 skipped in 178.63s** |
| 8 | 目标 `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q -rs` | 0 | **320 passed, 2 skipped in 178.95s** |
| 9 | 目标 `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest tests/test_b7_ci_second_identity.py -v -s` | 0 | **26 passed in 4.41s**；签名/负对照用例实际执行（无 skip） |
| 10 | 两侧 `python -m project_memory.cli audit --scope current --output ...` | 0 | 均为 **40 条 = 0 high / 16 medium / 24 low**；`entry_doc=docs/CURRENT_STATE.md`；`entry_doc_*` **0** |
| 11 | `python -m project_memory.cli reconcile --fail-on high`（目标） | 0 | 0 high / 16 medium / 24 low；`defects=0`、`open_defects=0`、`runs=0`、`verifications=0` |
| 12 | 独立行为矩阵 `C:/Temp/pm03-b7-check.py`（见 §5） | — | 25 个场景，fail-closed 全部符合；2 个预期外行为即 D-2/D-3，另记录大小写归一化 |
| 13 | 负对照（测试内 + 独立脚本） | 0→2→0 | 改 `commit_sha` 后 `approval_id 不可重算`，恢复后 exit 0 |

**skip 原因**：两次门禁的 2 个 skip 均为 `tests/test_security_rc3.py:284/295`「当前平台不允许创建符号链接」，与基线相同，**不是 openssl 用例**；B7 的签名/负对照用例在 `PROJECT_MEMORY_REQUIRE_OPENSSL=1` 下真实执行（#9 全 26 条 PASSED）。

**audit 多重集**：在基线 worktree 重跑同一 `audit --scope current`，按 `(severity, code, location)` 比较：

```text
baseline {'high': 0, 'low': 24, 'medium': 16} total 40
target   {'high': 0, 'low': 24, 'medium': 16} total 40
multisets_equal True
added []  removed []
entry_doc_* target 0
```

**耗时说明**：handoff 记录 170.42s / 177.20s；本会话因并行/机器负载为 204s / 205s（默认门槛）与 178.6s / 179.0s（openssl 门槛）。计数与跳过项完全一致，耗时差异不影响判定。

## 4. 复核重点逐项结论

### 4.1 环境变量读取白名单 —— PASS

- `_env_value`（`project_memory/authority.py:444-460`）只对 5 个固定名字调用 `os.environ.get`；`env_name` / `json_env` 不会直接传入，任意名字返回空串。源码中 `os.environ.get` 的出现集合恰为
  `{ANCHOR_ENV, APPROVAL_ANCHOR_ENV, TRUST_ANCHOR_JSON_ENV, APPROVAL_ANCHOR_JSON_ENV, CI_CONTEXT_ENV}`。
- `tests/test_authority_verifier.py::test_module_keeps_no_external_verifier_dependency` 未删空：仍断言 `authority` 不引入 `shutil`/`subprocess`/`tempfile`、不含 `PROJECT_MEMORY_OPENSSL` / `powershell` / `Get-Acl`，并把“只出现一次 `os.environ.get`”放宽为“固定名字集合”。卡面集合未列 `APPROVAL_ANCHOR_ENV`，但 B-8 本地审批文件锚仍需要该名字；handoff 已披露，属于合理最小放宽。
- 独立验证：把 JSON 锚写入任意变量 `PM03_ARBITRARY_SECRET`，以 `load_anchor(repo, env_name='PM03_ARBITRARY_SECRET', json_env='PM03_ARBITRARY_SECRET')` 在 `GITHUB_ACTIONS=true` 下加载 → 返回 `None` / `未配置受保护的信任锚（PM03_ARBITRARY_SECRET）`。验证器仍只来自进程内实现。

### 4.2 CI JSON 锚 —— PASS（含 D-2 / D-4 / D-5）

- `load_anchor`（`authority.py:506-535`）：受保护文件锚有效时直接返回（文件优先，`test_protected_file_anchor_wins_over_json_anchor` PASS）；文件锚缺失/无效且 `json_env` 有值时，仅在 `_is_ci_context()` 为真时解析 JSON；非 CI 时返回 `json_env 只在 CI（GITHUB_ACTIONS=true）中生效`。
- `_load_json_anchor`（`authority.py:494-503`）复用 `_anchor_document`，kind/schema/algorithm/`anchor_id`/`issuer`/`public_key_pem` 校验与文件锚一致；不跳过任何字段校验，只跳过文件所有者检查（secret 没有文件所有者）。
- 独立矩阵：CI 正确 JSON → trusted；本地仅设 JSON → exit 2；`GITHUB_ACTIONS=false` → exit 2；非法 JSON/kind/schema/algorithm/字段 → unconfigured（测试覆盖）。
- **“文件锚无效时在 CI 回退到 JSON”的绕过评估**：
  - 在卡面预期的 CI 边界内，workflow 只把 `PROJECT_MEMORY_APPROVAL_ANCHOR_JSON` 从 secret 注入，未设置文件锚环境变量；PR 代码/审批记录都不能在加载前改 step 环境。因此该回退**不新增由 PR 数据控制的绕过**。
  - 但它有一个配置风险：如果未来在 CI 中显式设置文件锚（例如轮换/吊销后的锚），而该文件无效，代码会**静默退回** JSON 锚，可能让已应吊销的旧 secret 锚继续生效。建议在“文件锚环境变量已显式设置但无效”时 fail closed（或至少输出显著警告），不要静默降级。记为 **D-5（Low）**。
  - 真正使 JSON 锚可被本地利用的是 D-2（`GITHUB_ACTIONS` 自报），以及 D-1（门禁执行 PR 代码）。两者都不是“文件锚回退”本身引入的。
- **D-4（Low）**：`_is_ci_context` 使用 `.strip().casefold() == 'true'`，因此 `TRUE`、`True`、`" true "` 都会生效；卡面写“字面 true”，测试名 `test_ci_flag_must_be_the_literal_true` 却只测了 `'false'`。GitHub runner 固定注入小写 `true`，实际无安全影响；若坚持字面语义，改为 `== 'true'`，或把测试名/卡面改为“大小写不敏感”。

### 4.3 两个锚仍分离 —— PASS

- 审批：`approval_authority` → `_execution_record_authority(..., env_name=APPROVAL_ANCHOR_ENV, json_env=APPROVAL_ANCHOR_JSON_ENV)`（`authority.py:710-712`）；`_approval_evidence` 同样传 `APPROVAL_ANCHOR_JSON_ENV`（`coordination.py:2154-2156`）。
- 验证 / attestation / 人类例外 / checkpoint：`verification_authority` 与 `_execution_record_authority` 默认 `TRUST_ANCHOR_JSON_ENV`（`authority.py:569`、`:631-634`）；`attach_audit_checkpoint` 显式传 `TRUST_ANCHOR_JSON_ENV`（`coordination.py:723-724`）。
- `approval_authority` 仍在验签后要求 `record.approver == verdict.issuer`（`authority.py:715-718`）；不满足即 `untrusted`。未发现审批路径误用 TRUST 锚或验证路径误用 APPROVAL 锚。

### 4.4 `approval verify --records-dir` —— PASS（含 D-3）

独立脚本在临时 git 仓库中生成两把 RSA 密钥、真实签名记录与真实 CLI 子进程调用（未使用测试内 mock），结果见 §5。逐条：

| 场景 | 期望 | 实测 exit | 结论 |
|---|---|---|---|
| 一条正确审批（CI secret 锚） | 0 | 0，`approved=true, scanned=1` | PASS |
| 空目录（真实存在） | 非 0 | 2，`目录中没有审批记录` | PASS |
| 目录不存在 | 非 0 | 1，`审批记录目录不存在` | PASS |
| 记录指向另一提交 | 非 0 | 2，逐条 `commit_sha 是 ...，不是 ...` | PASS |
| `decision=reject` | 非 0 | 2，`decision 是 reject，不是 approve` | PASS |
| 伪造签名（另一把私钥） | 非 0 | 2，`签名验证失败` / `untrusted` | PASS |
| 缺审批锚 | 非 0 | 2，`unconfigured` / `未配置受保护的信任锚` | PASS |
| 单条 `--record` 正确 | 0 | 0 | PASS（行为未变） |
| 单条 `--record` 错误提交 | 2 | 2 | PASS（行为未变） |
| `--record` + `--require-approve` | 非 0 | 1，`只能与 --records-dir 一起使用` | PASS |
| `--record` + `--records-dir` | argparse 拒绝 | 2 | PASS |

- `verify_approval_records`（`coordination.py:2022-2056`）逐文件隔离 `PMError`，单条坏记录不会中断批次；`approved = any(verified)`，`verified` 只在 trusted + approve + 提交匹配时为真。
- **D-3（Low）**：实现为“无 approved 即 exit 2”，**即使不带 `--require-approve`**；flag 实际只追加一条 problem 文案。实测：不带 flag 时，空目录 2、错误提交 2、reject 2；带 flag 时结果相同。卡面只规定“带 `--require-approve` 时只有存在 … 才 exit 0”，实现是更严格的 fail-closed 超集，**不构成安全偏差**；但 CLI help（`cli.py:239-240`）暗示该 flag 决定 exit 0，实际不是，建议二选一：让无 flag 时“验证跑完即 0，仅报告”，或把 help/文档改为“records-dir 始终要求至少一条 approved；flag 仅用于显式门禁语义”。

### 4.5 workflow 静态安全 —— PASS（含 D-1 High、D-7/D-8/D-9）

`.github/workflows/approval-gate.yml` 实查：

| 检查 | 结果 |
|---|---|
| YAML 可解析（PyYAML 6.0.1） | `name=approval-gate`；`on` 被 PyYAML 1.1 解析为 `True`，测试已兼容；触发 `pull_request` / `workflow_dispatch` |
| `permissions` | `contents: read`、`pull-requests: read`、`checks: read`，无 write |
| Action pin | `actions/checkout@11d5960a326750d5838078e36cf38b85af677262`（v4.4.0）、`actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065`（v5.6.0），均 40 位，与既有 `test.yml` 同一 pin |
| `pull_request_target` | 未出现 |
| `persist-credentials` | `false` |
| fetch 不被吞 | `set -euo pipefail` + 裸 `git fetch origin approvals:...`，无 `\|\| true` |
| 门禁绑定解析后的 head | `PM_HEAD=$(git rev-parse HEAD)` 写入 `$GITHUB_ENV`；`--commit "$PM_HEAD"`（第 35、62 行） |
| checkout ref（两事件） | `github.event.pull_request.head.sha \|\| format('refs/pull/{0}/head', inputs.pr)`：`pull_request` → PR head SHA；`workflow_dispatch` → `refs/pull/<pr>/head`，均指向 PR head（静态核对；未在 GitHub 实跑） |
| 缺锚/缺 records | 缺 `records/` → `::error::` + exit 1；secret 为空 → `::error::` + exit 1 |

**D-1（High）——门禁执行 PR 可修改的验证器代码，且 `pull_request` 的 workflow 定义来自 PR 合并提交：**

1. workflow 先 checkout PR head（第 25-29 行），随后直接运行**该检出树里的** `python -m project_memory.cli approval verify`（第 60-62 行）；没有从 base / 固定 SHA 取验证器代码的步骤。因此 PR 只要修改 `project_memory/cli.py` 或 `authority.py`，就能让门禁恒返回 0（或读取 secret 内容，公钥泄露本身不致命，但门禁判断被接管）。
2. 我做了本地最小演示（scratch 副本 `C:/Temp/pm03-b7-tamper`，未改仓库）：同一空 records 目录、同一假锚环境变量下，
   - 原实现：`exit=2`（`scanned=0`）；
   - 把副本 `cli.py` 的 `main()` 改为直接打印 approved 并返回 0：`exit=0`。
   这说明门禁的“通过/失败”来自 PR 可控代码，而不是独立验证器。
3. 文档宣称“门禁 job 在 base 提供的 workflow 定义下运行”（`README.md:208`、`docs/OPERATIONS.zh-CN.md:180`、`skill/project-memory/references/governance.md:41`）。GitHub 官方文档明确：`pull_request` 事件使用 **PR 合并提交里的 workflow 文件**运行（https://docs.github.com/zh/enterprise-server@3.18/actions/reference/security/securely-using-pull_request_target ：“它会使用来自拉取请求中的合并提交的工作流文件来运行工作流”）。同一仓库内分支的 PR 可获得 secret；因此 PR 既能改 workflow，也能改验证器。该宣称不准确。
4. 这不意味着卡面实现“跑偏”：卡面 §3 的模板就是 checkout PR head 再运行仓库 CLI。但作为第二身份的**安全属性**，当前门禁不能抵抗“PR 修改验证器”这一路径；它比“账户所有者改 workflow”更隐蔽（后者通常显眼，前者可以藏在大 PR 里）。**必须在 B-10 将其设为必需检查前处理，或由人类明确接受。**

最小修复建议（不要求本次 PR 立即完成，但必须排期）：

- B-7 合入 `dev/v1.0` 后，把门禁的验证器固定到受信任代码：例如 `git archive origin/dev/v1.0 project_memory | tar -x -C .pm-verifier`，然后 `PYTHONPATH=.pm-verifier python -m project_memory.cli approval verify --records-dir ... --commit "$PM_HEAD" --require-approve`；或用固定 SHA 的受保护 reusable workflow。这样 PR 只提供数据（head SHA、approvals 分支记录），不提供验证器。
- 对 `.github/workflows/**` 与 `project_memory/{authority,coordination,cli}.py` 使用 CODEOWNERS / 受保护规则，避免“改验证器”混入普通 PR。
- 把文档改为准确表述：`pull_request` 的 workflow 来自 PR 合并提交；门禁当前仍执行 PR 代码，因此不是独立验证；在 B-10 前不能把它当“不可绕过”的第二身份。

**D-7（Info）**：仓库当前为 private，而 step 在 `persist-credentials: false` 后裸跑 `git fetch origin approvals`，没有显式 token；私有仓库下该 fetch 会失败（fail closed）。这与“B-10 转 public 前不能真正跑通”的已知事实一致；建议在文档注明，或改用第二个 `actions/checkout`（`ref: approvals`、`path:`）由 action 自行认证。

**D-8（Info）**：`workflow_dispatch` 的 workflow 定义来自“运行时所选分支”。文档（`docs/OPERATIONS.zh-CN.md:177`）只说填 PR 号，未说明应在 `dev/v1.0` 上派发；若在 PR 分支上派发，等于运行 PR 的 workflow。建议明确“在 dev/v1.0 上运行 workflow_dispatch”。

**D-9（Info）**：门禁 step 安装了 `pytest==9.1.1`（第 48 行），但 `approval verify` 不使用 pytest；这是卡面模板遗留，增加不必要的供应链面，建议删除。

### 4.6 测试 —— PASS（含 D-10）

- `tests/test_b7_ci_second_identity.py` 收集 **26 条**（8 条 CI JSON 锚、10 条 records-dir、8 条 workflow 静态）；目标双门槛 320/2 相对基线 294/2 恰为 +26。
- 覆盖卡面 §4：CI/非 CI JSON、`GITHUB_ACTIONS` 必须为 `true`（只测 `false`）、非法 JSON、kind/schema/algorithm/字段、文件锚优先、文件锚失败回退、records-dir 的“别人的审批/错误提交/篡改/空目录/缺目录/伪造签名/缺锚”、单条模式不变、`--require-approve` 与 `--record` 互斥、workflow 静态项、负对照。
- OpenSSL 门槛下 26 条全部 PASSED（`test_security_rc3.py` 的 2 个符号链接 skip 与 openssl 无关）；签名/负对照真实执行，无 skip。
- 负对照实际输出（测试内与本会话复跑一致）：

```text
negative-control before: exit=0 approved=True
negative-control edited: exit=2 problems=['审批记录不合规：approval_id 不可重算（记录被修改或格式错误）']
negative-control restored: exit=0 approved=True
```

- **D-10（Info）**：测试缺口：① 未测 `GITHUB_ACTIONS` 的 `TRUE/True/" true "`（实现实际接受，见 D-4）；② 未测“records-dir 不带 `--require-approve`”的退出语义（D-3）；③ workflow 测试未断言 checkout ref 在两种事件下都指向 PR head；④ `test_workflow_exists_and_parses` 在无 PyYAML 时 skip（本机有 PyYAML，已真实解析；发布门槛应确保 PyYAML 存在或改为硬失败）。

### 4.7 文档 —— PASS（含 D-1/D-2/D-8 的准确性偏差）

- 准确项：README（`:199-208`）、OPERATIONS（`:172-180`）、governance（`:39-41`）都写出 secret **名称** `PROJECT_MEMORY_APPROVAL_ANCHOR_JSON`，未写值；说明 approvals 分支记录命名、由仓库外私钥签名后发布；说明 `workflow_dispatch` 重跑而不要推空提交；说明需 B-10 配分支保护；说明不能防御账户所有者改写 workflow（S4 残余）。
- 未发现“不可伪造/已认证/tamper-proof/unforgeable”类夸大；全文扫描只命中否定句“不是‘不可绕过’”。
- 不准确/不完整：
  - “门禁 job 在 base 提供的 workflow 定义下运行”（README `:208`、OPERATIONS `:180`、governance `:41`）与 GitHub 实际语义不符（D-1）。
  - “本地设置 JSON 锚环境变量也不会生效”（README `:205`、OPERATIONS `:178`、governance `:41`）：严格说只有**不设置** `GITHUB_ACTIONS=true` 时才不生效；本地设置 `GITHUB_ACTIONS=true` 后 JSON 锚会生效（D-2）。
  - `workflow_dispatch` 未指定应在 `dev/v1.0` 上派发（D-8）。

### 4.8 边界 —— PASS

- `origin/approvals` 实查为 `0b46e65b3dcddec8de390aee085397fe41d3960a`，树仅 `README.md` + `records/.gitkeep`；未见 PM-02 推送的记录。
- `origin/dev/v1.0` 仍为 `c3dea2a...`；本分支未改 `dev/v1.0`。
- `git diff c3dea2a..53b11cf` 与 `HEAD` 树中未发现私钥/令牌/secret 值（`BEGIN ... PRIVATE KEY`、`ghp_`、`github_pat_` 均无）；唯一的 `.pem` 是基线既有的 `pilot/kit/b1/positive/pub-a.pem`（非本分支新增）。
- 只读检查 PM-02 的工作树（`git -C ../pm-pilot-02 status --porcelain`）：仅 `PM02_COLD_START_VALIDATION.md` 与 `tasks/PM02-cold-start-handoff-20261029T150500Z.md` 两个既有未跟踪文件，无新增残留。
- 未改仓库可见性、未开分支保护、未合并 PR、未打 tag；这些 GitHub 侧设置无法从 git 树验证（见 §7）。

## 5. 独立行为矩阵（本会话实跑）

脚本 `C:/Temp/pm03-b7-check.py`：临时 git 仓库（两个相邻提交）、openssl 现场生成两把 RSA 密钥、真实签名记录、真实 CLI 子进程；每个场景使用独立 records 目录，避免状态污染。

| # | 场景 | 期望 | 实测 exit | 备注 |
|---|---|---|---|---|
| 1 | 正确记录 + CI secret 锚 | 0 | 0 | approved=true, scanned=1 |
| 2 | 空目录（已存在） | 非 0 | 2 | `目录中没有审批记录` |
| 3 | 缺目录 | 非 0 | 1 | PMError |
| 4 | 记录指向另一提交 | 非 0 | 2 | 逐条 commit 不匹配 |
| 5 | `reject` | 非 0 | 2 | — |
| 6 | 伪造签名 | 非 0 | 2 | untrusted / 签名验证失败 |
| 7 | 缺锚 | 非 0 | 2 | unconfigured |
| 8 | 本地只设 JSON 锚（无 CI 标志） | 2 | 2 | `只在 CI` |
| 9 | 本地 JSON + `GITHUB_ACTIONS=false` | 2 | 2 | — |
| 10 | **本地自造密钥+自造锚 + `GITHUB_ACTIONS=true`** | 2（按卡面意图） | **0** | **D-2：approved=true** |
| 11 | `GITHUB_ACTIONS=TRUE` | 2（字面 true） | **0** | D-4 |
| 12 | `GITHUB_ACTIONS=True` | 2 | **0** | D-4 |
| 13 | `GITHUB_ACTIONS=" true "` | 2 | **0** | D-4 |
| 14 | records-dir 不带 flag，正确记录 | 0 | 0 | — |
| 15 | records-dir 不带 flag，空目录 | 0（报告模式） | **2** | D-3 |
| 16 | records-dir 不带 flag，错误提交 | 0（报告模式） | **2** | D-3 |
| 17 | records-dir 不带 flag，reject | 0（报告模式） | **2** | D-3 |
| 18 | 单条 `--record` 正确 | 0 | 0 | 行为未变 |
| 19 | 单条 `--record` 错误提交 | 2 | 2 | 行为未变 |
| 20 | `--record` + `--require-approve` | 非 0 | 1 | PMError |
| 21 | `--record` + `--records-dir` | 非 0 | 2 | argparse 互斥 |
| 22 | 负对照：改 `commit_sha` 前 | 0 | 0 | — |
| 23 | 负对照：改 `commit_sha` 后 | 非 0 | 2 | `approval_id 不可重算` |
| 24 | 负对照：恢复后 | 0 | 0 | — |
| 25 | 任意环境变量名（非白名单） | 不读取 | None | `未配置...` |

第 10 行是本轮发现 D-2 的直接证据：临时仓库的密钥与 JSON 锚都是脚本现场生成，**没有任何受保护文件锚**；本地进程只设置 `GITHUB_ACTIONS=true` + `PROJECT_MEMORY_APPROVAL_ANCHOR_JSON`，真实 CLI 即给出 `trusted/approved` 并 exit 0。

## 6. 偏差清单

| ID | 严重度 | 结论 | 证据 | 影响 | 最小修复 |
|---|---|---|---|---|---|
| D-1 | **High** | 门禁执行 PR head 的验证器代码；`pull_request` 的 workflow 定义来自 PR 合并提交而非 base；文档宣称不符 | workflow `:25-29` checkout head、`:60-62` 运行该树 CLI；GitHub 文档；scratch 演示 原 2 / 篡改 0 | PR 不改 workflow、不需要审批私钥，只改 `project_memory/{cli,authority}.py` 即可让门禁通过；第二身份被接管 | B-7 合入后把验证器固定到 base/固定 SHA（`git archive` 到独立目录 + `PYTHONPATH`）；`.github/workflows/**` 与验证器走 CODEOWNERS/受保护规则；文档改准确。**必须在 B-10 启用必需检查前完成或由人类明确接受** |
| D-2 | **Medium** | `GITHUB_ACTIONS` 自报；本地自造锚+密钥+该标志可得到 trusted/approved | §5 第 10 行；README `:205`、OPS `:178`、gov `:41` | 本地流程（如 `goal evaluate` 消费 `approval_authority`）可被同一账户的 Agent 自签自批；卡面“本地 JSON 不得生效”只在未设置该标志时成立 | 文档明确“GITHUB_ACTIONS 是进程自报，本地结果不作为独立证据；只有 CI runner 上的 secret 锚结果有意义”；可选：仅门禁命令路径接受 JSON 锚，本地评估路径保持受保护文件锚 |
| D-3 | Low | `--require-approve` 对 exit code 无影响；records-dir 始终“无 approved 即 2” | `cli.py:531-534`；§5 第 14-17 行 | 安全上 fail-closed，无绕过；但 flag/help 语义误导，报告模式无法只输出结果 | 无 flag 时“验证跑完即 0，仅报告”，有 flag 时才要求 approved；或改 help/文档为“始终要求” |
| D-4 | Low | `GITHUB_ACTIONS` 大小写/空白归一化，不是字面 `true` | `authority.py:464`；§5 第 11-13 行 | GitHub 固定小写，实际无影响；与测试名/卡面措辞不一致 | 改为 `== 'true'`，或把测试名/卡面改为“大小写不敏感”并补测试 |
| D-5 | Low | CI 文件锚显式设置但无效时静默回退 JSON 锚 | `authority.py:520-528` | 不构成 PR 数据控制的绕过；可能掩盖锚轮换/吊销配置错误 | 文件锚显式设置且无效时 fail closed（或至少输出显著 warning），仅在“未设置文件锚”时允许 JSON |
| D-6 | Low（验收缺口） | 卡面 §6“真实 PR 上验证”（无审批失败→加审批 dispatch 成功→提交不匹配失败）未执行 | handoff §未验证项；仓库 private、fetch 不可用 | 门禁的端到端行为没有真实 runner 证据 | PM-01 在 B-10/转 public 后补做，记录 run id；在此之前不声称门禁已在真实 PR 通过 |
| D-7 | Info | private + `persist-credentials:false` 下 `git fetch origin approvals` 无认证 | workflow `:36-41` | B-10 前门禁无法真正跑通（fail closed） | 文档注明，或改用第二个 `actions/checkout`（`ref: approvals`、`path:`）由 action 认证 |
| D-8 | Info | `workflow_dispatch` 未指定在 `dev/v1.0` 上派发 | OPS `:177` | 在 PR 分支上派发会运行 PR 的 workflow 定义 | 文档明确“从 dev/v1.0 派发” |
| D-9 | Info | 门禁安装未使用的 pytest | workflow `:48` | 增加供应链面 | 删除该行 |
| D-10 | Info | 测试缺口（大小写、无 flag 语义、两事件 checkout ref、PyYAML skip） | §4.6 | 不阻断，但降低回归覆盖 | 补 4 条断言；PyYAML 缺失时硬失败 |

## 7. 未验证项

- 真实 PR 上的 `approval-gate` 运行（无审批 → 失败；加审批后 `workflow_dispatch` → 成功；审批提交不匹配 → 失败）**未执行**；仓库仍 private，`git fetch origin approvals` 在 `persist-credentials:false` 下预计失败。handoff 也明确未验证。
- 真实 secret 值、锚内容、审批私钥均未读取/未验证；只核对 secret **名称**与文档。
- GitHub 侧设置（仓库可见性、secret 是否已设置、分支保护/Ruleset）未通过 API 查询；本报告采用派单给出的外部事实（approvals 分支 `0b46e65...`、secret 已设置、仓库仍 private）。
- Action pin 的版本注释（v4.4.0 / v5.6.0）未向上游独立核验；只核对了 40 位 SHA 且与既有 `test.yml` 相同。
- `workflow_dispatch` 在 GitHub 上的 ref 解析未实跑，只做静态核对。
- audit 只比较多重集/计数，不判断文档语义正确性。
- 未在真实 GitHub runner 上验证 D-1 的 workflow 定义来源；引用的是 GitHub 官方文档语义。

## 8. 复核边界与纪律

- 只在 `C:/Temp/pm03-b7-target`、`C:/Temp/pm03-b7-base` 两个自建 worktree 中运行；未修改 `pm-pilot-01` / `pm-pilot-02`，未使用 `project-memory-mvp`。
- 未改被复核代码；本报告是唯一新增文件，提交在 `review/b7-ci-anchor`，只推送该分支。
- 未联网取凭据、未使用真实令牌/私钥、未读取其他会话聊天记录；D-1 的“篡改验证器”演示只在 `C:/Temp/pm03-b7-tamper` scratch 副本中进行，未进入仓库。
- 本报告不构成合并批准、发布批准或人类批准；合并、分支保护、tag/Release 由 PM-01 与人类决定。

## 9. 复现命令（关键）

```bash
# 独立检出
git fetch origin --prune
git worktree add --detach C:/Temp/pm03-b7-base c3dea2a74ce666789e8a521a8eab7bcffe8654f2
git worktree add --detach C:/Temp/pm03-b7-target 53b11cf789f0c4eee17f68e80e575a35bf46f187

# 双门槛（每个 worktree 各跑一次）
cd C:/Temp/pm03-b7-base   && PYTHONUTF8=1 PYTHONIOENCODING=utf-8 C:/SoftWare/Anconda/python.exe -m pytest -q
cd C:/Temp/pm03-b7-target && PYTHONUTF8=1 PYTHONIOENCODING=utf-8 C:/SoftWare/Anconda/python.exe -m pytest -q
cd C:/Temp/pm03-b7-base   && PROJECT_MEMORY_REQUIRE_OPENSSL=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8 C:/SoftWare/Anconda/python.exe -m pytest -q -rs
cd C:/Temp/pm03-b7-target && PROJECT_MEMORY_REQUIRE_OPENSSL=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8 C:/SoftWare/Anconda/python.exe -m pytest -q -rs

# audit / reconcile / diff
cd C:/Temp/pm03-b7-base   && C:/SoftWare/Anconda/python.exe -m project_memory.cli audit --scope current --output C:/Temp/pm03-b7-base-audit.json
cd C:/Temp/pm03-b7-target && C:/SoftWare/Anconda/python.exe -m project_memory.cli audit --scope current --output C:/Temp/pm03-b7-target-audit.json
cd C:/Temp/pm03-b7-target && C:/SoftWare/Anconda/python.exe -m project_memory.cli reconcile --fail-on high
git diff --check c3dea2a..53b11cf

# 行为矩阵/负对照/D-1 演示
PYTHONUTF8=1 C:/SoftWare/Anconda/python.exe C:/Temp/pm03-b7-check.py
```
