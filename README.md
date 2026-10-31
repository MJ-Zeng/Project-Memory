# Project Memory：让多个 Agent 共用一套仓库记忆

这是一个本地优先的 Agent Skill 和 Python CLI，用来处理多人和多个 Agent 在同一个 Git 仓库里协作时的记忆问题。它把目标、执行记录、独立验证、缺陷、任务背景、交接状态、设计决策、文档现状和审计结果写成仓库里的文件，跟着代码一起提交和评审。

它不负责审批、合并、关闭 Issue，也不判断文档里的结论是否正确。目标达成、ADR 接受和生产变更仍由人和 GitHub 规则决定。

## 快速开始

需要 Python 3.11 或更高版本。默认功能不依赖第三方库。

```bash
# 在分发目录运行测试
cd project-memory-mvp
python3 -m pytest -q

# 初始化一个已经建好的 Git 仓库；只补缺失文件，不覆盖
python3 -m project_memory init --repo /path/to/git/repo --install both
cd /path/to/git/repo

# 初始化后的仓库自带 CLI，CI 和离线环境都能用
PYTHONPATH=.project-memory/tooling python3 -m project_memory audit --repo . --scope current --fail-on high
PYTHONPATH=.project-memory/tooling python3 -m project_memory search --repo . '项目 状态'
```

也可以从分发目录安装：`python3 -m pip install -e .`，然后直接运行 `project-memory --help`。

Windows 上用 Git Bash 时，先设置 `PYTHONUTF8=1`，并把 `python3` 换成实际可用的解释器路径。

### 测试期 openssl 要求

openssl 只在测试期用于生成测试密钥和签名，**不是运行时依赖**；CLI 的验签在进程内完成。缺少 openssl 时，B2/B3/B4 签名测试默认 `SkipTest`，本地仍可跑其余测试。发布和 CI **必须**设置开关，让缺 openssl 直接失败，避免把 skip 当成通过：

```bash
# 发布/CI：缺 openssl 时签名测试 failed/error，不再 skip
PROJECT_MEMORY_REQUIRE_OPENSSL=1 python3 -m pytest -q

# 本地默认：缺 openssl 时跳过签名测试
python3 -m pytest -q
```

Windows 上 `python3` 可能是 Microsoft Store 的别名桩（exit 49），请改用实际解释器（如 `python`、venv 或 Anaconda 路径）执行上述命令。

开关取值为 `1`、`true`、`yes`（大小写不敏感）。详见 `docs/OPERATIONS.zh-CN.md`。

### 仓库自带的 CI

本仓库的 `.github/workflows/test.yml` 在三种情况下运行同一套检查：目标为 `dev/v1.0` 的 pull request、合入 `dev/v1.0` 的 push，以及手动 `workflow_dispatch`。

- 运行器 `windows-latest`，Python 3.12，pytest 固定为 9.1.1。
- 两道门槛依次执行：默认 `pytest -q`，以及 `PROJECT_MEMORY_REQUIRE_OPENSSL=1 pytest -q`。运行器没有 openssl 时，第二道会在日志里显式打印跳过，不会把跳过当成通过。
- 权限只有 `contents: read`；checkout 不保留凭据；第三方 Action 按提交 SHA 固定。

当前没有启用分支保护（私有仓库的免费计划不提供该能力），所以 CI 结果是建议性的，不会自动阻断合并。合并规则是：先确认该 pull request 的 CI 运行成功，再看代码；合入后由 push 触发的运行会在合并提交上再验证一次。

## 目标、执行与独立验证

目标用可衡量的成功标准描述，不把 Issue 关闭当成完成：

```bash
# Goal 默认 proposed；approved/achieved 必须由授权人提供 --approved-by
python3 -m project_memory goal create --repo . --id G-AUTH \
  --title '修复认证绕过' --outcome '未授权请求被拒绝' --owner backend-team \
  --criterion '无令牌请求返回 401'

# 每次执行登记真实模型、会话、分支和基准 SHA
python3 -m project_memory run start --repo . --goal G-AUTH --task 325 \
  --run-id run-dev-1 --agent qoder --model-provider qoder-cn --model-id dfmodel \
  --role executor --base-sha <40位SHA>

# 结束时生成 1.2 handoff；换模型或换会话时用新的 run ID
python3 -m project_memory run finish --repo . --task 325 --run-id run-dev-1 \
  --completed '拒绝无令牌请求' --remaining '独立验证' \
  --test-command 'python -m unittest' --test-exit 0 --test-log tests.log
```

验证必须由另一个执行记录完成，并登记为 `role=verifier`；验证者的 agent/model/session 至少一项要不同，不能自验：

```bash
python3 -m project_memory run start --repo . --goal G-AUTH --task 325 \
  --run-id run-verify-1 --agent qoder --model-provider qoder-cn --model-id qfmodel \
  --role verifier --base-sha <40位SHA>

python3 -m project_memory test-run --repo . --agent qoder \
  --command 'python -m unittest' --trusted
# 输出 .project-memory/receipts/EXE-*.json

python3 -m project_memory verify --repo . \
  --target-run run-dev-1 --verifier-run run-verify-1 \
  --standard '认证与凭据审查' --verdict pass --evidence-level locally_observed \
  --test-receipt .project-memory/receipts/EXE-<id>.json \
  --expected-sha <被验证执行的head SHA>
```

`agent_claimed` 不能产生 pass；`locally_observed` 需要 `test-run` 生成的执行收据，手写日志不再算执行证据；外部 CI 需要 URL 和 passed 状态，默认只是声明；人工批准需要 review URL 和 approved 状态，但 CLI 不认证审批人。验证绑定提交 SHA，代码变化后旧验证只作为历史证据，且不能跨 Goal 复用。

### 外部取证（--pr）

`verify` 加 `--pr` 并设置 `GITHUB_REPOSITORY`（`owner/repo`）后，会通过 GitHub API 读取该 PR head 提交的 check runs，把“人肉看 CI 绿”换成机器判定：

```bash
export GITHUB_TOKEN="<你的令牌>"      # 只读仓库即可
export GITHUB_REPOSITORY="owner/repo"

python3 -m project_memory verify --repo . \
  --target-run run-dev-1 --verifier-run run-verify-1 \
  --standard 'CI 与凭据审查' --verdict pass --evidence-level externally_verified \
  --pr 42 --criterion-evidence criterion-evidence.json
```

判定规则（fail-closed）：

- 仅当所有 check run 完成且结论均为 `success`、且 PR head SHA 等于被验证执行的 head SHA 时，criterion mapping 中 `evidence_source: ci` 的证据才记为 `externally_verified`；记录 `trust_level` 也才能到 `externally_verified`（仅 `pass` 路径；非 `pass` 根本不会抓取）。
- CI 失败、仍有进行中的任务、没有 check run、head SHA 不匹配、缺少 `GITHUB_REPOSITORY`、网络或 API 错误，都降级为 `agent_claimed`，不阻塞命令。
- 即使 CI 全绿，记录仍然最多是 `MANUAL_REVIEW_REQUIRED`、`verified` 恒为 `false`：CI 成功只证明该提交的构建事实，不证明语义覆盖。
- 声明 `--evidence-level externally_verified` 必须同时给 `--pr`；不给 `--pr` 时该等级会被直接拒绝。该等级只适用于 `pass`，`fail`/`inconclusive` 声明它会被拒绝。

`checks.ci.provenance` 会从 `declared_unfetched` 变成 `github_api`，并记录 `head_sha`、`head_sha_matches_target` 和每个 run 的结论，便于复核。`checks.ci.repository` 记录尝试读取的仓库 slug（未发起抓取或缺少配置时为空串；仓库格式非法时保留原值便于排查），`checks.ci.fetch` 记录抓取结果类别：`not_requested`（未请求）、`ok`（成功）、`missing_repository` / `invalid_repository`（仓库配置问题）、`invalid_pr`、`api_error`（网络或 API 错误）、`shape_error`（响应结构异常）。这些字段只含类别与 slug，不含令牌、请求头或响应体。

### 执行收据与隔离

`test-run` 把提交导出到不可变快照后执行命令，并记录退出码、日志哈希和快照摘要：

```bash
# 本地模式：普通子进程，没有操作系统隔离。必须显式加 --allow-local-untrusted，
# 否则拒绝执行（exit 3）；收据标记为 local_untrusted。命令以当前用户权限直接在宿主
# 上运行，不可信，仅在了解风险时使用；需要隔离时改用 --trusted。
python3 -m project_memory test-run --repo . --command 'python -m unittest' \
  --agent qoder --allow-local-untrusted

# 可信模式：WSL2 user/mount/PID/network namespace，预检失败即 BLOCKED，不回退
python3 -m project_memory test-run --repo . --command 'python3 -m unittest' \
  --agent qoder --trusted --timeout 900
```

执行模式必须二选一：`--allow-local-untrusted`（宿主本地、无隔离）或 `--trusted`（WSL2 隔离）。两者都不给或同时给出都会被拒绝（exit 3，不建快照、不写收据）。

可信模式会屏蔽 Windows 盘符、宿主 home、`/root`、`/var`、`/tmp` 和 `/etc/ssh` 等路径，只保留快照副本和显式环境变量 allowlist；命令在 `env -i` 下运行，无默认路由。收据的完整性可以重算，但收据本身位于仓库内、没有外部签名，所以只标为 `isolated_local_attestation`，不等于可信来源。

### 验证记录不会自证权威

本地 CLI 写出的验证记录最多是 `MANUAL_REVIEW_REQUIRED`，`verified` 恒为 `false`：JSON 里的 `status: VERIFIED` 或 `authority.status: trusted` 都不被接受。只有仓库外受保护信任锚对记录做分离签名，`goal evidence` 才可能把它当作达成依据：

```bash
export PROJECT_MEMORY_TRUST_ANCHOR=/path/outside/repo/trust-anchor.json
```

未配置信任锚时，`goal evaluate` 会停在 `needs_review` / `MANUAL_REVIEW_REQUIRED`，这是 fail-closed 的预期结果，不是可以绕过的错误。

把验证记录挂到目标标准，再评估和对账：

```bash
python3 -m project_memory goal evidence --repo . --id G-AUTH \
  --criterion C1 --kind verification --ref <verification-id>
python3 -m project_memory goal evaluate --repo . --id G-AUTH
python3 -m project_memory reconcile --repo . --fail-on high
```

`goal evaluate` 满足时退出 0，未满足时退出 2（没有可信授权来源时始终属于未满足）；例外是必达标准集合为空（例如所有判据被改成可选或删除）：此时退出 0，但 `satisfied=false`、`evaluation_status=insufficient_evidence`、`status_problems` 含 `no_required_criteria`，自动化必须读 `satisfied`/`effective_status`/`status_trusted`/`status_problems` 而不是只看退出码；`verify` 未通过时退出 2；`run resume` 在 `needs_handoff`、`needs_human` 或 `stale_base` 时退出 2。`reconcile` 只报告，不自动改 canonical 文档，也不关闭任务。

### 签名审批

审批是一件独立的签名事件：谁（`approver`）、何时（`at`）、对哪个提交（`commit_sha`）。审批人身份取自审批锚的 `issuer`，不是命令行自报；载荷被改动、签名不正确或提交不匹配时一律视为未受信，不会满足任何判据。

```bash
# 1. 生成未签名请求；CLI 不持有私钥，也不签名
python3 -m project_memory approval request --repo . --commit <40位SHA> \
  --approver lead@example.com --output C:/Temp/approval-request.json

# 2. 由仓库外审批私钥对请求文件的规范 JSON 字节签名
openssl dgst -sha256 -sign <审批私钥> -out C:/Temp/approval.sig C:/Temp/approval-request.json

# 3. 本地校验签名并写入 .project-memory/approvals/
python3 -m project_memory approval attach --repo . \
  --request C:/Temp/approval-request.json --signature C:/Temp/approval.sig \
  --anchor /path/outside/repo/approval-anchor.json

# 4. 再用受保护的审批锚验证记录
export PROJECT_MEMORY_APPROVAL_ANCHOR=/path/outside/repo/approval-anchor.json
python3 -m project_memory approval verify --repo . \
  --record .project-memory/approvals/<approval-id>.json --commit <40位SHA>
```

两个锚分工不同：`PROJECT_MEMORY_TRUST_ANCHOR` 只用于验证记录、执行 attestation 和审计 checkpoint；`PROJECT_MEMORY_APPROVAL_ANCHOR` 只用于审批事件。`approval attach` 只校验“这份公钥能验通这个签名、格式是否正确”，**信任决定**发生在 `approval verify`、`goal evaluate` 和门禁读取时，由受保护审批锚重新做出。未配置审批锚时审批仍可登记，但状态是 `UNVERIFIED_APPROVAL`，绝不满足判据。

`scope.kind=commit` 的审批只证明“批准了这个提交”，供后续 CI 合并门禁使用，不参与 Goal 判据；`scope.kind=criterion` 额外绑定一个已验证记录（`goal_id`、`criterion_id`、验证摘要、`evidence_id`、提交），只有该验证记录仍是 pass、映射完整、摘要未变且提交等于当前 HEAD 时才可能让判据达成：

```bash
python3 -m project_memory approval request --repo . --commit <40位SHA> \
  --goal G-AUTH --criterion C1 --verification <verification-id> \
  --approver lead@example.com --output C:/Temp/approval-request.json
python3 -m project_memory goal evidence --repo . --id G-AUTH --criterion C1 \
  --kind approval --ref .project-memory/approvals/<approval-id>.json
```

审批是追加记录，不修改验证记录；验证记录内容一旦变化，原审批的摘要即失效。审批不会把 `verified=false` 改成 `true`，也不替代独立验证或人工审批权限。

`approval verify` 只在记录通过审批锚验签、`decision=approve` 且 `commit_sha` 与 `--commit` 一致时 exit 0，否则 exit 2。`approval verify --records-dir DIR --commit SHA [--require-approve]` 批量验签目录下的 `*.json` 并逐条输出结论：不带 `--require-approve` 时扫描完成即 exit 0，只在报告中如实给出 `approved`/`problems`；带 `--require-approve` 时，只有存在至少一条 trusted+approve+提交匹配的记录才 exit 0，否则 exit 2。`approval list [--commit SHA] [--goal G]` 只读列出记录、范围与验签状态。

### 签名证据清单

`evidence request` 生成未签名清单，仓库外审批私钥签名后由 `evidence attach` 附加，`evidence verify` 用受保护审批锚复检清单、仓库身份、提交/树和工作区文件哈希，任一不符 exit 2。命令入口：`python3 -m project_memory evidence {request,attach,verify} --repo .`；完整步骤与路径规则见 [OPERATIONS](docs/OPERATIONS.zh-CN.md#签名证据清单)。

它只证明锚持有者对这份清单负责，不证明文件由受保护执行器产生或命令真的执行过；文件哈希取自 request 时的工作区字节，不要求文件已提交进树。

### CI 第二身份与审批门禁

单用户主机没有独立的 OS 主体，本地文件锚无法自证。`approval-gate` 工作流让 GitHub Actions runner 作为第二身份：runner 用仓库 secret 里的审批公钥验证 `approvals` 分支上的审批记录，并要求 PR head 的具体提交上至少有一条 `approve`。

- 工作流由 `pull_request_target` 触发，并且只检出 PR 的 base 提交：workflow 定义和 `project_memory` 验证器都来自 base，PR head 只作为 `--commit` 字符串使用，从不检出、从不执行。因此修改 `.github/workflows/**` 或 `project_memory/{authority,coordination,cli}.py` 的 PR 同样要过审批门禁，门禁代码不受 PR 影响。
- 审批锚由仓库管理员放进 Actions secret `PROJECT_MEMORY_APPROVAL_ANCHOR_JSON`（值是审批锚 JSON 本身），不落在仓库树里；PR 代码不能改写它。secret 里只有公钥，泄露不等于私钥泄露。
- `approvals` 分支只存放审批事件（`records/<40位提交SHA>-<approval_id>.json`），由持有私钥的人在仓库外签名后发布；门禁只读该分支，不写回，也不放密钥。私有库拉取该分支时，用一次性 `http.extraheader` 携带本次运行的 `github.token`，并把认证串 `::add-mask::`，令牌不会出现在日志里。
- `GITHUB_ACTIONS=true` 只是防误用开关，不是密码学边界：本机可以伪造它，所以本地默认不采用 JSON 锚，非 CI 运行仍使用受保护文件锚 `PROJECT_MEMORY_APPROVAL_ANCHOR`。本地用自己的密钥和自己的锚得到 trusted 不影响 CI 门禁，因为门禁的锚来自仓库 Secret、代码来自 base。验证记录与 checkpoint 的 `PROJECT_MEMORY_TRUST_ANCHOR_JSON` 遵循同样的规则。
- `workflow_dispatch` 运行的检查**不满足**必需状态检查（GitHub 文档明示），只作诊断，并显式检出 `dev/v1.0`；审批记录发布后，用 PR 事件（编辑、重开、新提交）或重跑原 `pull_request_target` 运行来重新评估。
- 门禁结果要成为合并必需检查，还需要仓库管理员在 GitHub 侧开启分支保护或 Branch Ruleset，并设置 `enforce_admins`；CLI 和本仓库不配置这些。

边界：管理员始终可以通过 API 关闭分支保护、改写 workflow 或 Secret，这是被接受的信任前提（S4 残余风险）。审批记录也只是签名声明，不替代独立验证、CODEOWNERS 或合并权限。

## 两种审计范围

`--scope current` 只审当前知识：canonical 根下状态为 `current`、`draft`、`in_flight`、`unclassified` 的文档，加上全部 ADR。镜像、历史、证据和已归档文档不参与。它适合放在合并门禁里。

默认的 `audit`（`--scope all`）会扫 canonical、镜像和历史目录，用来做周期复核。镜像和历史里的问题通常不在这次改动范围内，不应为了把数字清零去改旧文档。

`audit` 是本地防篡改检测与文档一致性提示，不构成对外可采信的审计留痕。

## 入口文档与新鲜度

`.project-memory/config.json` 里的 `entry_doc` 指向唯一一篇给人看的入口文档。设置后，审计要求它存在、属于 canonical、显式声明 `status: "current"`。

`last_verified_at` 记录人最后一次核对结论的日期，和只记录编辑的 `updated_at` 分开。入口没有这个日期会报 low；超过 `max_verified_age_days`（默认 90 天）会报 medium。`init --profile full` 生成的 CURRENT_STATE 模板不写核验日期，填完内容并核对过事实之后，再由人补上。

`--profile overlay` 不生成入口文档。接入已有 `doc/` 或 `doc/new_doc` 布局时用它，接入后需要自己补一篇入口并设置 `entry_doc`。

## 已有文档布局

不要为了接入再建一棵 `docs/`。把真实目录声明出来：

```bash
python3 -m project_memory init --repo /path/to/workspace --install none --profile overlay \
  --docs-root doc/new_doc \
  --mirror-root pro2-mixed-training/docs/project-docs \
  --legacy-root doc/_legacy_2026-10-23
```

`overlay` 只创建 `.project-memory/` 和 ADR 目录说明，不改已有文档，也不碰业务代码。`mirror_roots` 只读；`legacy_roots` 默认不参与检索。`mirror_policy: frozen` 表示人已经接受镜像长期只读，镜像漂移会以 medium 继续报告，但仍然不允许把镜像内容复制回 canonical。

## 主要命令

| 用途 | 命令 | 是否写入 |
|---|---|---|
| 初始化与工具同步 | `init --repo . --install both`，`sync-tooling [--write]` | 只创建或更新缺失/已跟踪工具 |
| 定义与评估目标 | `goal create/show/list/evaluate/evidence/transition` | 写 `.project-memory/goals/` |
| 登记执行 | `run start/checkpoint/finish/show/list` | 写 `.project-memory/runs/` 和 handoff |
| 恢复执行 | `run resume --task 325 [--run-id run-1]` | 否 |
| 独立验证 | `verify --target-run A --verifier-run B --standard '...' --verdict pass --evidence-level locally_observed --test-receipt .project-memory/receipts/EXE-*.json ...`；外部取证时加 `--pr 42 --evidence-level externally_verified` | 写验证和缺陷记录 |
| 快照执行 | `test-run --command '...' (--trusted \| --allow-local-untrusted) [--wsl-distro Ubuntu]`，执行模式必须二选一 | 写快照、日志和收据 |
| 缺陷跟踪 | `defect list/show/update` | 更新缺陷状态 |
| 知识对账 | `reconcile [--format markdown] [--fail-on high]` | 否，或写指定报告 |
| 取任务上下文 | `start --issue 325 --slug ORG/REPO` 或 `start --task-file task.json` | 否 |
| 通用交接 | `handoff --task 325 --agent codex --run-id run-1 --remaining 'test' [--store PATH]` | 写本地不可变记录 |
| 完成检查 | `finish --issue 325 --pr 342 --slug ORG/REPO --docs-impact unknown` | 否 |
| 起草 ADR | `decision --title 'Cache' --topic cache --issue 325 --owner team --rationale '...'` | 创建 proposed ADR |
| 新建文档 | `new-doc --id DOC-CACHE-001 --title 'Cache' --kind canonical --status draft --owner team --path docs/topics/cache.md` | 创建固定格式草稿，不覆盖 |
| 文档审计 | `audit --scope current --fail-on high`（门禁）/ `audit`（全量复核） | 否 |
| 图谱与检索 | `graph`、`search 'query'`、`search --backend semantic --model /local/model 'query'` | 只写图谱缓存 |

本地或离线时，`start` 和 `finish` 可以用 `--issue-file`、`--pr-file` 替代 `--issue` / `--pr` 与 `--slug`。本地任务文件至少要有 `id`，以及 `title` 或 `body` 之一。任务 ID 可以是字符串；没有 Git 的工作区会返回 `base_sha: null`。

`new-doc` 不能直接创建 `current`：canonical 文档只能从 `draft` 或 `in_flight` 开始，证据文档只能从 `evidence` 开始。它会拒绝重复 ID、ADR 目录、镜像/历史根和配置文档根之外的路径。写入规则见 `skill/project-memory/references/document-authoring.md`。

## 凭据与权限

只有 `start`、`finish` 和 `verify --pr` 会访问 GitHub API，而且只调只读接口。凭据从环境变量 `GITHUB_TOKEN` 读取，不放在命令行参数里。建议使用 GitHub App 安装令牌，或限制到具体仓库的 fine-grained token。`verify --pr` 还需要 `GITHUB_REPOSITORY`（`owner/repo`）指定读取哪个仓库。

`decision`、`goal`、`run`、`verify`、`test-run`、`defect`、`reconcile`、`handoff` 和 `init` 只写本地文件，不推送、不合并、不审批、不关闭 Issue、不部署。`--reviewed-by` 和 `--test-evidence` 是声明，不是独立验证；真正的权限仍由 GitHub 规则和 CI 决定。`test-run --trusted` 只在 WSL2 可用时执行，隔离预检失败会返回 BLOCKED，不会退回普通子进程。

## 语义检索的限制

默认 `search` 是词法匹配，英文按 token，中文按双字，不涉及模型。`--backend semantic` 需要额外安装 `sentence-transformers`，并提供一个本地的模型目录：

```bash
python3 -m pip install -e '.[semantic]'
```

代码不会自动下载模型，也不会把私有文档发给第三方嵌入服务。当前没有向量持久化、批处理服务或组织级知识图谱。

## 还需要人工完成的事

1. 检查生成的示例，补全入口文档、架构说明和 ADR 负责人。
2. 参考 `.github/CODEOWNERS.example` 配置真正的 CODEOWNERS，并在 GitHub 开启分支 Ruleset、必需审查和必需 CI（私有仓库的免费计划不提供这些能力，需要 GitHub Pro 或改为公开仓库）。CLI 不能替你做这些。
3. 审核已固定的第三方 Action 代码，并在升级时更新 SHA：当前 `actions/checkout` 固定到 `v4.4.0`、`actions/setup-python` 固定到 `v5.6.0`，只解决了“引用不可变”，没有审核上游代码。
4. 接入有权限的 GitHub 数据；如果要把完成门禁全自动化，还需要独立核对 CI 和 review 状态，不能只依赖快照声明。
5. Qoder CN 等客户端目前需要手动切换模型。CLI 只记录实际模型，不调度模型，也不保证跨模型接续。
6. Goal 的 `approved`/`achieved` 转换、ADR 接受、高风险变更和生产部署仍必须由授权人执行。
7. 把 Skill 和 CLI 的改动当作受保护变更来审查，不要在不信任的仓库工作流里跑带密钥的任务。

## 文档

- [教程与工作流](docs/TUTORIAL.zh-CN.md)：从临时仓库试跑到真实仓库接入，以及日常协作节奏。
- [技术设计](docs/ARCHITECTURE.zh-CN.md)：模块、目录模型、数据契约和后续门槛。
- [操作手册](docs/OPERATIONS.zh-CN.md)：接入步骤、文档写入、新人接手和上线检查。
- [验证记录](docs/TEST_REPORT.md)：跑过的测试、真实仓库结果和未验证项。
- [Skill 说明](skill/project-memory/SKILL.md) 与 `skill/project-memory/references/`：Agent 执行时读的规则和字段契约。

## 参考

- [Agent Skills specification](https://agentskills.io/specification)
- [Codex skill locations](https://learn.chatgpt.com/docs/customization/overview)
- [Claude Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Cursor Skills](https://cursor.com/docs/skills)
- [GitHub REST API](https://docs.github.com/en/rest)
- [GitHub Rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- [GitHub Actions pull_request_target 的安全用法](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)
