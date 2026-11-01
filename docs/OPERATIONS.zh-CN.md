# 操作手册

## 接入步骤

1. 在现有 Git 仓库运行：

   ```bash
   python3 -m project_memory init --repo /path/to/repo --install both
   ```

   如果仓库已有自己的文档布局，比如 `doc/new_doc`，改用 overlay，避免新建一棵竞争的 `docs/`：

   ```bash
   python3 -m project_memory init --repo /path/to/workspace --install none --profile overlay \
     --docs-root doc/new_doc \
     --mirror-root path/to/read-only-mirror \
     --legacy-root doc/_legacy_2026-10-23
   ```

2. 检查新增文件，补全架构和负责人，修改示例模板。`full` 会生成 CURRENT_STATE，把它改成真实现状，核对后补 `last_verified_at`；`overlay` 不生成入口，需要自己补建，并在配置里设置 `entry_doc`。
3. 通过 PR 提交。配置 `.github/CODEOWNERS`，开启分支 Ruleset，要求 CI 和人工审查。这些都要在 GitHub 侧完成。
4. 先用一个真实 Issue 或本地任务 JSON 跑一次 `start`，确认检索到的文档、ADR 和 SHA 是对的。
5. 为这项工作总结可核验的成功标准，创建 Goal；由授权人转 `approved`，再转 `active`。
6. Agent 用 `run start` 登记实际模型、会话、分支和 base SHA；换模型或换会话时开新的 run ID。
7. 让第二个 Agent 读同一任务的 `handoff` 或 `run resume` 接手包，不要复制完整聊天上下文。
8. 另一个执行记录用 `verify` 独立检查目标提交；发现转成缺陷，修复后复验。
9. 把 PR 的测试证据带进 `finish`，对照真实的 GitHub 审查状态看一眼。
10. 每次合并前跑 `audit --scope current --fail-on high` 和 `reconcile --fail-on high`。每周再跑一次全量 `audit`，把历史、镜像和证据区的高价值发现转成 Issue，由人决定整改还是忽略。
11. Goal 标准全部满足后，由授权人转 `achieved`。Agent 的评估建议不等于批准。写入的 `achieved` 只是声明；只有仓库外信任锚签名的 checkpoint 覆盖当前审计链时，`effective_status` 才等于 `achieved`。
12. 需要了解知识关系时运行 `graph` 和 `search`。索引不是新的事实来源。

## 可信启动入口（B5A / B5A.1）

`project_memory` 是普通 Python 包，cwd 或 `PYTHONPATH` 中的同名包会先于受信包被导入。启动方式按信任等级区分（详见 `docs/decisions/ADR-0005-cli-bootstrap.md`）：

| 入口 | 信任 | 说明 |
|---|---|---|
| `project-memory ...`（原生包装器：`bin/project-memory`、Windows `bin/project-memory.cmd`） | 受信 | 原生 OS 脚本，经 `PATH`/绝对路径调用，**不经 `sys.path`**；先以 `-I -P` 启动隔离解释器，再按**绝对路径**运行 `_project_memory_launcher.py`，任何顶层模块名都不被 `sys.path` 解析 |
| `python -I -P -m project_memory ...` | 受信 | 解释器级隔离，忽略 `PYTHONPATH`/用户站点且不前置 cwd |
| `python _project_memory_launcher.py ...`（按绝对路径直接运行启动脚本） | 受信 | 启动脚本换成隔离子进程后再导入受信包 |
| `python -m project_memory ...`（未隔离） | 尽力而为 | 受信包已导入但 `sys.path` 上仍有同名包时 exit 3 拒绝；若同名包已在解析阶段胜出，受信代码不会执行（等价于整进程替换，无法进程内防护） |
| `from _project_memory_launcher import main`（旧 pip `module:function` console script 形式） | **不受支持** | 在未隔离解释器里按 `sys.path` 解析顶层模块名，`PYTHONPATH`/cwd 同名文件会抢先执行（B5A.1 已复现 `FAKE_LAUNCHER`）；受支持入口只有原生包装器 |

包装器解释器选择顺序：`PROJECT_MEMORY_PYTHON` → 同目录 venv 解释器 → `PATH` 上的 `python3`/`python`；启动脚本定位顺序：包装器同目录（安装布局）→ 上级目录（checkout 布局）。任一缺失则 exit 3（fail closed）。

`test-run` 子进程固定使用快照树作为 `PYTHONPATH`，并设置 `PYTHONSAFEPATH=1`/`PYTHONNOUSERSITE=1`；收据的 `isolation.python_env` 记录该清理状态。自动化脚本请使用原生包装器 `project-memory` 或带 `-I -P` 的入口，不要用裸 `python -m`。

## 测试期 openssl 与发布门禁（R1）

openssl 只由测试使用（生成测试 RSA 密钥、对测试载荷签名），**不是运行时依赖**：CLI 的验签由 `authority.py` 在进程内完成，不调用外部 openssl。

- 默认：找不到 openssl 时，B2/B3/B4 签名测试以 `SkipTest` 跳过，本地仍可运行其他测试；skip 只表示“未执行”，**不等于通过**。
- 发布/CI：必须设置 `PROJECT_MEMORY_REQUIRE_OPENSSL=1`（也接受 `true`/`yes`，大小写不敏感）。此时找不到 openssl 会让签名测试 failed/error，命令以非零退出，消息同时包含 `openssl` 和 `PROJECT_MEMORY_REQUIRE_OPENSSL`。
- 开关只影响测试，不改变运行时行为、信任根或验签路径，也不新增运行时依赖。

```bash
# 发布门禁（openssl 缺失时不得 skip）
PROJECT_MEMORY_REQUIRE_OPENSSL=1 python3 -m pytest -q

# 本机默认（允许 skip，仅用于开发）
python3 -m pytest -q
```

Windows 上 `python3` 可能是 Microsoft Store 的别名桩（exit 49），请改用实际解释器（如 `python`、venv 或 Anaconda 路径）执行上述命令。

## 目标、执行与验证

Goal 至少有一条必达成功标准。标准要能用提交、测试日志、验证记录或人工批准判断：

```bash
PYTHONPATH=.project-memory/tooling python3 -m project_memory goal create --repo . \
  --id G-AUTH --title '修复认证绕过' --outcome '未授权请求被拒绝' \
  --owner backend-team --criterion '无令牌请求返回 401' --issue 325
```

默认是 `proposed`。授权人批准后才进入执行：

```bash
PYTHONPATH=.project-memory/tooling python3 -m project_memory goal transition --repo . \
  --id G-AUTH --to approved --approved-by 'owner@example.com' --reason 'Grooming 通过'
PYTHONPATH=.project-memory/tooling python3 -m project_memory goal transition --repo . \
  --id G-AUTH --to active
```

`--approved-by` 必须是邮箱格式（如 `owner@example.com`），否则命令以 exit 1 拒绝。该值只是追溯标识，不是认证：它记录谁声明了这次批准，不校验邮箱归属，也不代替 GitHub 审查或分支保护。

每次执行单独登记，模型 ID 写实际值：

```bash
PYTHONPATH=.project-memory/tooling python3 -m project_memory run start --repo . \
  --goal G-AUTH --task 325 --run-id run-dev-1 --agent qoder \
  --model-provider qoder-cn --model-id dfmodel --tool qoder-desktop \
  --role executor --branch fix/auth --base-sha <40位SHA> \
  --authorization 'Issue #325 范围内修改认证代码，不合并、不部署'
```

有进展就写检查点，结束用 `run finish`。它生成 1.2 handoff，但不验证工作：

```bash
PYTHONPATH=.project-memory/tooling python3 -m project_memory run checkpoint --repo . \
  --task 325 --run-id run-dev-1 --completed '定位绕过路径' --remaining '补测试'

PYTHONPATH=.project-memory/tooling python3 -m project_memory run finish --repo . \
  --task 325 --run-id run-dev-1 --completed '拒绝无令牌请求' \
  --remaining '独立验证' --commit <40位SHA> --changed-file src/auth.py \
  --test-command 'python -m unittest' --test-exit 0 --test-log tests.log
```

接手时先看恢复包，不要直接继续旧会话：

```bash
PYTHONPATH=.project-memory/tooling python3 -m project_memory run resume --repo . --task 325
```

`resume_ready` 只表示记录齐全。`needs_handoff`、`needs_human` 和 `stale_base` 都要人工处理。

独立验证必须使用另一个 run，并登记为 `role=verifier`；验证者的 agent/model/session 至少一项要不同：

```bash
PYTHONPATH=.project-memory/tooling python3 -m project_memory run start --repo . \
  --goal G-AUTH --task 325 --run-id run-verify-1 --agent qoder \
  --model-provider qoder-cn --model-id qfmodel --role verifier --base-sha <40位SHA>

PYTHONPATH=.project-memory/tooling python3 -m project_memory test-run --repo . \
  --agent qoder --command 'python -m unittest' --trusted

PYTHONPATH=.project-memory/tooling python3 -m project_memory verify --repo . \
  --target-run run-dev-1 --verifier-run run-verify-1 \
  --standard '认证与凭据审查' --verdict pass --evidence-level locally_observed \
  --test-receipt .project-memory/receipts/EXE-<id>.json \
  --expected-sha <被验证执行的head SHA>
```

`agent_claimed` 不能 pass。`locally_observed` 必须提供 `test-run` 生成的执行收据；手写日志不再算执行证据。外部验证需要 `verify --pr` 通过 GitHub API 读取该提交的 check runs；全绿且 head 匹配才升级为 `externally_verified`，失败、pending、空或截断、head 不匹配或缺配置都降级为 `agent_claimed`，只声明 CI URL 和 passed 而不加 `--pr` 时仍是 `declared_unfetched`。人工批准需要 review URL 和 approved，但 review 仍是调用方声明，CLI 不抓取也不认证审批人。发现用 `--findings-file` 提交，high 级发现会阻断 pass。`--findings-file` 与 `--criterion-evidence` 的相对路径按 `--repo` 解析，绝对路径原样使用。

`test-run` 必须显式选择执行模式，默认不执行：既无 `--trusted` 也无 `--allow-local-untrusted` 时拒绝执行（exit 3，不建快照、不写收据、无副作用）。`--allow-local-untrusted` 才在宿主上以普通子进程执行，收据标记为 `local_untrusted`，并保留警告。`--trusted` 进入 WSL2 user/mount/PID/network namespace：屏蔽 Windows 盘符、宿主 home、`/root`、`/var`、`/tmp` 和 `/etc/ssh`，只保留快照副本与 `env -i` allowlist，无默认路由；预检失败返回 `BLOCKED`（exit 3），不回退普通子进程。attestation 位于仓库内、没有外部签名，所以收据只标 `isolated_local_attestation`，不代表来源可信。

本地 CLI 写出的验证记录最多是 `MANUAL_REVIEW_REQUIRED`，`verified` 恒为 false；JSON 里自报 `status: VERIFIED` 或 `authority.status: trusted` 不被接受。只有仓库外的受保护信任锚（`PROJECT_MEMORY_TRUST_ANCHOR`）对记录做分离签名，`goal evidence` 才可能把验证当作达成依据。没有配置信任锚时，`goal evaluate` 停在 `needs_review` 是预期的 fail-closed 结果。

把通过的验证挂到目标标准，评估和对账：

```bash
PYTHONPATH=.project-memory/tooling python3 -m project_memory goal evidence --repo . \
  --id G-AUTH --criterion C1 --kind verification --ref <verification-id>
PYTHONPATH=.project-memory/tooling python3 -m project_memory goal evaluate --repo . --id G-AUTH
PYTHONPATH=.project-memory/tooling python3 -m project_memory reconcile --repo . --fail-on high
```

`goal evaluate` 未满足时退出 2；`verify` 未通过时退出 2；`run resume` 在阻断状态退出 2；`reconcile --fail-on high` 有 high 时退出 2。`reconcile` 只报告，不自动改文档，也不关闭任务。

### 签名审批

人工批准可以是一条由仓库外审批私钥签名的独立记录，绑定审批人、时间和提交：

```bash
PYTHONPATH=.project-memory/tooling python3 -m project_memory approval request --repo . \
  --commit <40位SHA> --approver lead@example.com --output C:/Temp/approval-request.json
# 由持有审批私钥的人在仓库外签名
openssl dgst -sha256 -sign <审批私钥> -out C:/Temp/approval.sig C:/Temp/approval-request.json
PYTHONPATH=.project-memory/tooling python3 -m project_memory approval attach --repo . \
  --request C:/Temp/approval-request.json --signature C:/Temp/approval.sig \
  --anchor /path/outside/repo/approval-anchor.json
export PROJECT_MEMORY_APPROVAL_ANCHOR=/path/outside/repo/approval-anchor.json
PYTHONPATH=.project-memory/tooling python3 -m project_memory approval verify --repo . \
  --record .project-memory/approvals/<approval-id>.json --commit <40位SHA>
```

`approval request` 只写未签名载荷，CLI 不签名也不持有私钥；`approval attach` 只做格式和“给定公钥能验通”的本地检查。信任决定在 `approval verify`、`goal evaluate` 和门禁读取时由 `PROJECT_MEMORY_APPROVAL_ANCHOR` 重新做出；审批人与锚 `issuer` 不一致即不受信。`scope=commit` 只批准提交（供 CI 门禁），`scope=criterion` 才可挂到 Goal 判据，并要求绑定的验证记录仍是 pass、摘要未变、提交等于当前 HEAD。未配置审批锚、签名无效或提交前进时审批只是 `UNVERIFIED_APPROVAL`，不 satisfy。

审批**不会**把验证记录的 `verified=false` 改成 `true`，也不会让 `human_approved` 变成可声明的 `--evidence-level`；它不替代独立验证、Ruleset、CODEOWNERS 或合并权限。审批记录是追加记录，不修改验证记录；验证记录一经改动，原审批摘要失效。证据文件的签名清单见后文「签名证据清单」一节。

### CI 审批门禁（GitHub Actions 第二身份）

1. **配置锚（仓库管理员）**：把审批锚 JSON（只含公钥）整体写入仓库 Actions secret `PROJECT_MEMORY_APPROVAL_ANCHOR_JSON`。不要写私钥、令牌或任何签名文件；私钥留在仓库外。secret 值不在本仓库、日志或 handoff 中出现。
2. **发布审批记录**：`approval request` 生成载荷，由仓库外私钥签名，再执行 `approval attach --output <records>/<40位提交SHA>-<approval_id>.json`，把记录提交到 `approvals` 分支的 `records/`。只提交记录本身；该分支不得放入密钥或私密材料。
3. **门禁运行**：`.github/workflows/approval-gate.yml` 由 `pull_request_target`（目标 `dev/v1.0`，事件 opened/synchronize/reopened/edited）触发，只检出 PR 的 base 提交；workflow 定义和验证器都来自 base，PR head 只作为 `--commit` 字符串，不检出、不执行。门禁在 base 树上执行 `approval verify --records-dir .pm-approvals/records --commit "$PM_HEAD" --require-approve`。`approvals` 分支用一次性 `http.extraheader`（`github.token`，认证串 `::add-mask::`）认证拉取，失败即停止。缺少锚、没有记录、记录不匹配、验签失败或提交不符都会让 job 失败。
4. **重跑门禁**：`workflow_dispatch` 显式检出 `dev/v1.0`，只用于诊断——GitHub 不把 dispatch 运行的检查当作必需状态检查。审批记录发布后，用 PR 事件（编辑、重开、新提交）或重跑原 `pull_request_target` 运行来重新评估；不要为了触发重跑推空提交——空提交会改变 head，原有审批随之失效。
5. **本地限制**：`GITHUB_ACTIONS=true` 是防误用开关，不是密码学边界；非 CI 默认不采用 JSON 锚，本机仍用受保护文件锚。本地用自己的密钥和自己的锚得到 trusted 不影响 CI 门禁，因为门禁的锚来自仓库 Secret、代码来自 base。

门禁成为必需检查需要分支保护或 Branch Ruleset，并设置 `enforce_admins`，这由仓库管理员在 GitHub 侧配置，本仓库不做。管理员始终可以通过 API 关闭保护、改写 workflow 或 Secret，这是被接受的信任前提（S4 残余风险）；门禁保证的是 PR head 不检出、不执行，验证器与 workflow 都来自 base，锚来自 secret，而不是“不可绕过”。

例外：必达标准集合为空（例如所有判据被改成可选或删除）时，`goal evaluate` 退出 0，但 `satisfied=false`、`evaluation_status=insufficient_evidence`、`status_problems` 含 `no_required_criteria`。自动化不要只看退出码，要读 `satisfied`/`effective_status`/`status_trusted`/`status_problems`；需要纯退出码门禁时，后续版本再提供显式 `--strict`，本版没有。

### 信任锚轮换与吊销

锚文档的必填字段之外，有四个可选字段（`schema_version` 仍是 `1.0`，未识别的额外字段被忽略但不会带来信任）：

```json
{
  "not_before": "2026-11-01T00:00:00Z",
  "not_after": "2027-11-01T00:00:00Z",
  "revoked_anchor_ids": ["ANCHOR-DRILL-20261031"],
  "fingerprint_sha256": "sha256:3f2a…（64 位十六进制）"
}
```

`not_before`/`not_after` 必须是带时区的 ISO-8601 字符串（`Z` 或 `±HH:MM`），判定用当前 UTC 时间、闭区间，只给一端时另一端不限制；`revoked_anchor_ids` 必须是非空字符串数组；`fingerprint_sha256` 必须等于 `public_key_pem` 解出的 DER SubjectPublicKeyInfo 字节的 SHA-256（哈希 DER 而不是 PEM 文本，避免换行差异），可用 `openssl pkey -pubin -outform DER | openssl dgst -sha256` 独立核对。格式非法、时间无时区、`not_before > not_after`、指纹与公钥不一致都让锚文档直接非法。四个字段都可选：写成 JSON `null` 与不提供该字段等同，按「未启用」处理；但值一旦给出就必须合规，空字符串 `""` 判非法。

锚失效之后各链的退出码不是一个数，别按一个数写自动化：`approval verify`（含 `--records-dir --require-approve`）与 `evidence verify` 是 exit 2；`audit checkpoint-attach` 在读取受保护锚失败时抛 `PMError`，CLI 统一映射为 exit 1；`goal evaluate` 只跟随 `satisfied`（判据不满足 exit 2，判据集合为空时 exit 0 + `satisfied=false`，见上文）。分两层看：判定层（`approval_authority`、`evidence_authority`、`verification_authority`、`signed_record_authority`）给出的结论一律 `trusted=false` 并 fail closed；`audit checkpoint-attach` 拿不到可信锚时**不返回**带 `trusted` 字段的 JSON，直接抛错退出，只能读 exit 1 与 stderr 文本。所以仍按上文那条老规矩办：不要只看退出码，要读 JSON 里的 `reason`/`trusted`/`satisfied`，才能区分「锚失效」与「根本没配锚」。

轮换步骤：

1. 用新密钥生成新锚，`anchor_id` 必须换（例如 `ANCHOR-PROD-20261101`），并按需要设置 `not_after`。
2. 把新的锚文档写进受保护锚文件（`PROJECT_MEMORY_APPROVAL_ANCHOR` 指向的仓库外文件）或仓库 Actions secret `PROJECT_MEMORY_APPROVAL_ANCHOR_JSON`；`--anchor` 只是本地校验用的公钥，可以同步更新。
3. 旧私钥停止签名。旧记录携带旧 `anchor_id`，与当前锚不一致，本来就 `untrusted`，所以轮换不需要吊销列表；需要重签的历史证据用新锚重新 `attach` 即可。
4. 想让旧锚在还作为当前锚时被停用，把它的 `anchor_id` 写进 `revoked_anchor_ids`；数组里只有别的 id 不影响当前锚。

谁能吊销、吊销列表写在哪：只有受保护锚文件或 CI secret 的持有者能改这两个 JSON；吊销列表就写在同一个锚文档的 `revoked_anchor_ids` 里。仓库内普通文件、审批记录、清单、环境变量以外的任何位置都不能作为吊销来源——否则 Agent 改写一个文件就能宣布自己的审批作废或生效。

吊销与过期**不能**做什么：

- 不能撤回已合并的提交，也不能让合并失效；
- 不能删除或改写任何已写出的记录、清单或账本；
- 不能让历史验证「重新变成通过」，也不能反过来把当时合法的验证说成伪造——它只让**之后**的信任判定 fail closed；
- 不改变记录本身：同一份审批文件在锚被吊销前 `exit 0`、之后 `exit 2`，字节不变。
- 不是一次写入就不可撤销：吊销列表由受保护锚文件或 CI secret 的持有者维护，**能编辑这份锚的人从 `revoked_anchor_ids` 里删掉一条，那个锚就重新可信**。它是运维手段，不是不可篡改的公开 CRL；防的是「改写仓库就能宣布吊销」，不是「锚的持有者反悔」。

过期对历史证据的影响：到期后所有依赖该锚的记录在下一次验证时都不可信，包括曾经通过的门禁重跑。需要长期可验证的证据，把 `not_after` 设得足够长，或在轮换后用新锚重新签署同一载荷。

本地调试时可以用 `GITHUB_ACTIONS=true` 加 `PROJECT_MEMORY_APPROVAL_ANCHOR_JSON` 让 JSON 锚生效，这是观察生命周期行为的最快办法；该开关只是防误用闸门，不是密码学边界，CI 门禁里的锚来自仓库 Secret 且验证器来自 base 提交。

## 审计链与 Goal 状态可信度

`.project-memory/audit/verification_attempts.jsonl` 是哈希链账本，每条记录带 `seq`、`prev_hash`、`entry_hash`；首条 `prev_hash` 为 64 个 `0`。`audit verify` 从 genesis 逐条重算，任何删除、改写或顺序调整都会报出精确的 `*_at` 位置。哈希链只能证明内部自洽，不能证明记录来自谁：整链重建后依然自洽，所以还需要 checkpoint。

`.project-memory/audit/head.json` 是 checkpoint，由仓库外的受保护主体的私钥对 `chain_head`、`chain_length`、`goal_id`、`status`、证据摘要和迁移摘要做分离签名。checkpoint 绑定的是**前缀**而不是最新 head，之后新增审计记录不会让已签名的 `achieved` 失效。

```bash
# 只读检查：valid / valid_unanchored / invalid
PYTHONPATH=.project-memory/tooling python3 -m project_memory audit verify --repo .
PYTHONPATH=.project-memory/tooling python3 -m project_memory audit head --repo .
# 旧版无哈希账本一次性迁移（写备份 verification_attempts.pre-chain.jsonl）
PYTHONPATH=.project-memory/tooling python3 -m project_memory audit migrate --repo .
```

`valid_unanchored` 表示链自洽但没有可信 checkpoint，退出 0 只说明结构没问题，不足以支撑任何 `achieved`。`audit verify` 在 `invalid` 时退出 2；`audit head` 只在 `valid`/`valid_unanchored` 时退出 0。

`achieved` 的签名由 PM-01/人类在仓库外完成；Agent 只有请求和附加两步，且 `checkpoint-attach` 只验签，不生成私钥、不产生签名：

```bash
# 1. 由 CLI 写出待签名载荷（要求 Goal 当前为 achieved 且标准已满足）
PYTHONPATH=.project-memory/tooling python3 -m project_memory audit checkpoint-request --repo . \
  --goal G-AUTH --approved-by 'owner@example.com'
# 2. 人类/CI 对 .project-memory/audit/head.request.json 的规范字节签名后
PYTHONPATH=.project-memory/tooling python3 -m project_memory audit checkpoint-attach --repo . \
  --signature /secure/path/head.sig
```

`goal show` 与 `goal evaluate` 不再把 JSON 里的 `status` 当结论，而是同时给出：

- `raw_status`：文件里写的状态，只是声明；
- `effective_status`：`achieved` 仅在被签名 checkpoint 覆盖、标准满足且链完整时为 `achieved`，否则为 `achieved_unverified`；
- `status_trusted`：`effective_status` 是否来自可信 checkpoint；
- `status_problems`：具体缺什么，如 `audit_missing`、`audit_chain_invalid`、`checkpoint_missing`、`checkpoint_untrusted`、`checkpoint_chain_mismatch`、`status_history_mismatch`、`no_required_criteria`。

自动化脚本请消费 `effective_status`/`status_trusted`，不要 grep `status`。审计目录为空或缺失一律 `invalid`，不会因为“没有记录”而被当作干净。checkpoint 私钥丢失或签名人不可用时，`achieved` 停在 `achieved_unverified` 是预期的 fail-closed 结果。

## 签名证据清单

证据清单把「文件哈希一致」升级为「锚持有者对这份清单负责，且清单只对某个提交有效」。它与审批共用同一把仓库外审批锚，但不含审批人字段：

```bash
# 1. 生成未签名清单请求；目录递归展开，只收录普通文件
PYTHONPATH=.project-memory/tooling python3 -m project_memory evidence request --repo . \
  --commit <40位SHA> --path evidence/B8 --statement 'B8 交付证据' \
  --output C:/Temp/evidence-request.json

# 2. 由仓库外审批私钥对请求文件的规范 JSON 字节签名
openssl dgst -sha256 -sign <审批私钥> -out C:/Temp/evidence.sig C:/Temp/evidence-request.json

# 3. 本地校验签名并写出带 authority 信封的清单；--output 必填
PYTHONPATH=.project-memory/tooling python3 -m project_memory evidence attach --repo . \
  --request C:/Temp/evidence-request.json --signature C:/Temp/evidence.sig \
  --anchor /path/outside/repo/approval-anchor.json \
  --output C:/Temp/evidence-manifest.json

# 4. 用受保护审批锚重新验签，并逐一重算文件哈希与大小
export PROJECT_MEMORY_APPROVAL_ANCHOR=/path/outside/repo/approval-anchor.json
PYTHONPATH=.project-memory/tooling python3 -m project_memory evidence verify --repo . \
  --manifest C:/Temp/evidence-manifest.json --commit <40位SHA> --json
```

清单记录 `commit_sha`、`tree_sha`、`files[{path, sha256, bytes}]`、`generator`（工具版本、Python、平台、生成命令）和 `authority` 信封。`manifest_id` 是记录去掉 `manifest_id` 与 `authority` 后规范 JSON 的 SHA-256 前 12 位，可随时重算；签名载荷是去掉 `authority` 的规范 JSON 字节，复用审批同一套验签实现。

`evidence request` 只写未签名文件，报告 `manifest_id`、`payload_sha256` 和可复制的 `openssl dgst -sha256 -sign` 命令，**不签名**。输出采用 no-clobber：`--output` 已存在且内容不同即 exit 1，不覆盖既有文件（包括已签清单），内容完全相同则原样保留。`evidence attach` 只用 `--anchor` 校验格式与签名，不构成信任；幂等判断比较签名载荷与 `anchor_id`/`issuer`/`algorithm`，忽略 ECDSA 签名因随机数产生的字节差异，同一锚同一载荷返回 `created=false`，不同锚或不同载荷仍拒绝覆盖。命中已有清单时还会用给定锚重新校验其 `authority.signature_b64`，签名已损坏则 exit 1，不视为幂等。信任只在 `evidence verify` 时由 `PROJECT_MEMORY_APPROVAL_ANCHOR` 重新决定。

`evidence verify` 校验清单结构、`manifest_id`、签名、`repository.id`/`remote` 与当前仓库 `repo_identity` 一致（沿用审批的仓库绑定，防止把别的仓库的清单搬来当证据）、`commit_sha`、`tree_sha`（必须等于该提交的树）以及每个文件的 `sha256` 与 `bytes`。全部通过才 exit 0；无受保护锚、清单未签名、签名无效、清单被改、仓库身份不符、提交或树不符、文件缺失或变化一律 exit 2，并在 JSON 的 `problems` 中逐条说明，`signed`/`trusted`/`verified` 不会降级为“仅提示”。

exit 码约定：只有 `evidence verify` 的信任或内容失败是 exit 2；`evidence request` 与 `evidence attach` 的本地校验失败（参数、结构、路径、签名格式、覆盖冲突）是 exit 1。`evidence verify` 始终输出 JSON，`--json` 仅为兼容保留。

路径规则：清单中的 `path` 必须是仓库相对路径并用 `/` 分隔；绝对路径、盘符、`..`、空段、符号链接、目录联接（junction）、挂载点或任何 reparse point，以及非常规文件一律拒绝。除按组件拒绝链接外，还会把路径规范化（realpath）后要求仍位于 `repo.resolve()` 之下。目录会递归展开，文件按 `path` 升序存放且不得重复，`files` 不得为空。

它证明什么：锚持有者对「这些文件在这个提交和树下的这些字节」负责。清单绑定 `commit_sha` 和 `tree_sha`，但 `files` 的 `sha256`/`bytes` 来自 `evidence request` 执行时的工作区字节，**不要求**这些文件已经提交进该提交的树（未跟踪的发布产物也可作为证据文件）。它**不**证明文件由受保护执行器产生，也**不**证明清单里的命令真的执行过；构建来源证明属于后续工作，不在本命令范围。

## 写文档

先 `search` 查重。能改现有文档，就不要新建一份平行摘要。设计决策用 `decision`，不写普通文档；调查记录用 `kind: evidence`；不再有效的结论标 `superseded` 或 `historical`，不要删除。

```bash
PYTHONPATH=.project-memory/tooling python3 -m project_memory new-doc --repo . \
  --id DOC-CACHE-001 --title '缓存口径' --kind canonical --status draft \
  --owner backend-team --path doc/new_doc/topics/cache.md --issue 325
```

`new-doc` 只生成固定 frontmatter 和章节骨架，不覆盖已有文件，不允许直接创建 `current`，也会拒绝 ADR 目录、mirror/legacy 根和 canonical 根之外的路径。`current` 必须由人审查后修改，Agent 不能自己晋升状态。完整规则见 `skill/project-memory/references/document-authoring.md`。

## 新人接手

人接手项目不需要运行 CLI，按仓库里提交的 Markdown 读就行。

1. 打开 `.project-memory/config.json` 里的 `entry_doc`。这是唯一入口，必须声明 `status: "current"` 并带 `last_verified_at`。
2. 按入口给出的顺序读，通常 30 到 40 分钟。不要先读 `90_原始档案`、证据快照、旧 handover 或重构方案。
3. 每读三篇，核对一个事实：跑一条命令、看一份日志、对一个数字。只读不核对，很容易把旧计划当成现状。
4. 能回答五个问题再动手：当前可信基线和评测集是什么；各条线状态和决策人是谁；复现一次评测需要哪些数据和命令；最大的未决项和负责人是谁；改代码会影响哪些结论。
5. 入口缺失或过期时，先报告 `entry_doc_missing` / `entry_doc_stale`，不要用历史文档替代。补建走 `new-doc`；`current` 和 `last_verified_at` 只能由实际核对过的人设置。

入口文档控制在 2k tokens 左右。它几乎每次都会被读，写长会持续增加上下文成本。完整规则见 `skill/project-memory/references/onboarding.md`。

## 常用命令

```bash
# 分发目录
python3 -m unittest discover -s tests -v
python3 -m project_memory init --repo /path/to/repo --install both

# 已初始化仓库内
PYTHONPATH=.project-memory/tooling python3 -m project_memory start \
  --repo . --issue 325 --slug YOUR_ORG/YOUR_REPO

# 无 GitHub 时
PYTHONPATH=.project-memory/tooling python3 -m project_memory start \
  --repo . --task-file task.json

PYTHONPATH=.project-memory/tooling python3 -m project_memory handoff \
  --repo . --task local-task-id --agent codex --run-id dev-01 \
  --completed '增加单测' --remaining '检查错误路径' --evidence 'PR #342' \
  --store /tmp/handoffs

PYTHONPATH=.project-memory/tooling python3 -m project_memory audit \
  --repo . --scope current --fail-on high
PYTHONPATH=.project-memory/tooling python3 -m project_memory audit --repo .
PYTHONPATH=.project-memory/tooling python3 -m project_memory audit verify --repo .
PYTHONPATH=.project-memory/tooling python3 -m project_memory audit head --repo .
PYTHONPATH=.project-memory/tooling python3 -m project_memory goal list --repo .
PYTHONPATH=.project-memory/tooling python3 -m project_memory run list --repo .
PYTHONPATH=.project-memory/tooling python3 -m project_memory reconcile \
  --repo . --format markdown --fail-on high
PYTHONPATH=.project-memory/tooling python3 -m project_memory graph --repo .
PYTHONPATH=.project-memory/tooling python3 -m project_memory sync-tooling --repo .
```

`sync-tooling` 默认只报告差异；确认后再加 `--write`。它不删除多余文件，也不覆盖已安装的 Skill 副本。

Windows 上用 Git Bash 时，先 `export PYTHONUTF8=1`，并把 `python3` 换成实际可用的解释器路径。

## 发布构建与来源证明

`.github/workflows/release.yml` 只做「构建 + 证明来源」，发布仍是人工动作。它有两个入口：推送形如 `v*` 的 tag，或手动 `workflow_dispatch`（`tag` 输入留空则构建 dispatch 当下选中的 ref，填了就先按 `^[A-Za-z0-9][A-Za-z0-9._-]*$` 校验形状，再进入 `git fetch` 与 `$GITHUB_ENV`）。被构建的 commit、tree、ref 会写进 run summary，和决定这次运行的 workflow 提交（`GITHUB_SHA`）分开列出——给 tag 输入时两者不同。

产物都在 `dist/`：

| 文件 | 来源 |
| --- | --- |
| `project-memory-<short>-source.tar.gz` | `git archive` 直接打包被构建的 commit |
| `*.whl` / `*.tar.gz`（sdist） | `python -m build` |
| `sha256sums.txt` | 对 `dist/` 内除自身外的每个文件跑 `sha256sum --text` |
| BUILD-INFO.json | commit / tree / ref / event / run id / run url / workflow 提交 / Python 与 build 版本 / 生成时间 + 写它那一刻 `dist/` 里的制品名单，按工作流的先后恰好 3 项（源码归档、wheel、sdist）——不含 sha256sums.txt（它在这之后才生成）、不含 BUILD-INFO.json 自身（枚举时还没落盘）、不含 attestation bundle（从不进 `dist/`） |

sdist 和源码归档都是 `.tar.gz`，靠 `project-memory-<short>-source` 前缀区分。attestation bundle 单独放在 attestation/attestation.json，不进 `dist/`：它由 `actions/attest-build-provenance` 的 `bundle-path` **输出**给出（这个 action 没有 `bundle-path` 输入），拷进 `dist/` 会让它出现在自己的哈希清单里。output 为空或指向的文件不存在时该步骤直接报错，不会留下一个自称已生成的空目录。

**不创建 Release。** 权限只有 `contents: read`、`id-token: write`、`attestations: write`；没有 `gh release create`、没有 Release API、不读任何仓库 secret（`gh attestation verify` 用的是当次 run 自带的 `github.token`）。打 tag、建 Release、挂资产留给 S4-5 人工执行。

外部验证一次已完成的 run：

```bash
# 1. 下载 run 的 workflow artifact（名形如 release-artifacts-<short>）
gh run download RUN_ID --repo MJ-Zeng/Project-Memory \
  --name release-artifacts-<short>
# 2. 先核对哈希清单
( cd ARTIFACT_DIR/dist && sha256sum -c -- sha256sums.txt )
# 3. 再逐个验证 GitHub 签发的 attestation
for file in ARTIFACT_DIR/dist/*; do
  gh attestation verify "$file" --repo MJ-Zeng/Project-Memory
done
```

`gh attestation verify` 一次只接受一个文件，所以必须循环。

失败判读：

- run 不是 success：这批制品不构成证据，不下载、不引用。summary 末尾会标出 `sha256sum -c` 与每个文件的 `gh attestation verify` 各自的退出码。
- `sha256sum -c` 不符：artifact 被改动过，或清单与制品不是同一次构建。弃用这批，不要试图解释差异。
- run success 但 `gh attestation verify` 失败：先确认 `--repo` 和文件来自同一次 run（跨仓库、跨 run 都会失败）；刚跑完时索引可能还读不到，工作流内部已按 5 次 × 10 秒重试过，外部仍然验证不过就按「没有 attestation」处理。
- artifact 里没有 attestation/attestation.json：那次 run 没有可下载的 bundle。attestation 步骤 success 只说明签发成功，不说明你之后还能离线复现验证。

已知限制：workflow artifact 不是 Release 资产，保留 90 天后就要重新构建；attestation 声明的是「这些文件由该仓库这次 run 构建」，不声明 SLSA 等级，也不独立证明 BUILD-INFO.json 自报的 commit 与外部记录一致；tag 触发路径在人类打下第一个 `v*` tag 之前没有被真实执行过——本仓库的静态测试只锁工作流的形状（触发、权限、固定 SHA、产物与上传清单），不证明 hosted runner 一定成功。来源证明也不等于评审证据：`v*` tag 触发跑的是 tag 所指提交里的那份 `.github/workflows/release.yml`，而 tag 可以指向一个从未走过「PR + 双门禁」的提交——`.github/workflows/test.yml` 监听 `dev/v1.0` 的 push 与 `pull_request`，另有 `workflow_dispatch`；`.github/workflows/approval-gate.yml` 监听 `pull_request_target` 与 `workflow_dispatch`；两者都不监听 tag，所以 tag 触发的发布构建本身不携带评审证据：attestation 只说明「这些文件由本仓库这次 run 构建」，不说明那个提交被独立复核过。核对评审状态要认**两个** SHA、分两步做，因为两类检查本来就不挂在同一个 SHA 上。第一步定锚点：`v*` tag 是带注解标签，必须先剥皮得到它指向的提交 T（`git rev-parse vX.Y.Z^{commit}`；只看 `refs/tags/vX.Y.Z` 的第一列会拿到 tag 对象），或按分支合并点解出 T。第二步分头核：在 **T** 上核 `test`（作业 `pytest`）completed 且 success——这条由落地时的 push 事件产生；用服务端的提交↔PR 绑定 `GET /repos/{owner}/{repo}/commits/{T}/pulls` 取回 PR 号及其 `head_sha`，记为 P（合并式提交里 P 就是 T 的第二父；squash 合并后 P **不是** T 的祖先，此时只能靠这条服务端绑定加「T 的树 == P 的树」说明审过的就是落地的），再在 **P** 上核 `approval-gate`（作业 `approval`）completed 且 success——它由 `pull_request_target` 产生，永远不挂 T。写条件要写成「**最新一次** completed 且 conclusion=success」，不要写成「所有记录都 success」：同一个 SHA 可以同时留有一次 failure 和一次较新的 success。**不要**把「`pytest` 与 `approval` 都跑在同一个 SHA 上且都成功」当条件——这是做不到的动作：`dev/v1.0` 上四个落地提交（squash 与真合并两种形态都有）的检查记录都只有 `pytest` 一条，`approval` 只出现在 PR 头提交上；本仓库现存的 `v1.0.0` 剥皮后（`f033a6c5…`）更是**一条检查都没有**（total=0），因为那条提交早于双门禁落地。BUILD-INFO.json 里的 commit、tree、run_id、run_url 一律由工作流自己从环境变量写入，属自报字段：attestation 证明的是 dist/* 的字节，不证明这些字段。所以 run_id、run_url 只能当作文本线索，一旦引用就要反向核那次 run 的 `head_sha` 是否等于 P（评审证据挂在那儿）或 T（落地与构建证据挂在那儿），两者不是同一个 SHA——相等是核对得到的结果，不是可以预设的前提。源码归档的字节还依赖产出机器的 git 配置，不跨机器可比：`git archive` 按当次环境的行尾设置落地，本机在 `core.autocrlf=true` 下实测 `README.md`、`docs/OPERATIONS.zh-CN.md`、`project_memory/authority.py` 解出的是 CRLF（与仓库 blob 字节不同），而 `.gitattributes` 声明 `text eol=lf` 的 `bin/project-memory` 保持 LF、与 blob 逐字节相同；因此别指望本地重新打包的源码归档能对上制品清单里的那个 SHA-256——外部复核认的是那次 run 自己的哈希清单与 attestation，不是重打包的哈希。

## 上线检查

- [ ] Agent 不共享管理员 PAT。使用最小权限的 GitHub App 令牌，令牌不写进 handoff。
- [ ] 默认分支禁止直接推送，至少要求一名真实人类审查，并启用 CODEOWNERS。
- [ ] Skill、CLI 和 Actions 配置纳入受保护的 CODEOWNERS 路径。
- [ ] CI 在 `pull_request` 上以只读权限运行，不执行带生产密钥的不可信 fork 代码。
- [ ] Actions 固定到审核过的完整 SHA，审计规则作为必需状态检查。
- [ ] 核对任务和 PR 的仓库归属、base SHA、关闭条件和部署状态。
- [ ] 确认语义检索模型不把私有文档发到外部，并维护索引黑名单。

## 测试计划

| 类型 | 场景 | 预期 |
|---|---|---|
| 单测 | 第二次初始化 | 不覆盖已有文件，返回 skipped |
| 单测 | ADR 状态与引用 | 只创建 proposed；重复 ID 或缺少审批会被审计提醒 |
| 单测 | Handoff 重试 | 相同内容幂等，不同内容拒绝 |
| 单测 | 缺 PR 或测试证据 | Completion 含 unknown，建议 do_not_close |
| 单测 | Agent 自报测试或审查 | 只能是 agent_claimed，不能 pass |
| 单测 | 验证提交已变化 | 拒绝 pass，标记 stale |
| 单测 | 重复 run ID | 相同内容幂等，不同内容报错 |
| 单测 | 中断恢复 | 检查点齐全时 resume_ready；缺 handoff 时 needs_handoff |
| 单测 | 同一任务多个活跃 executor | resume 报 needs_human，对账报告 |
| 单测 | 缺陷生命周期 | fixed 必须绑定 SHA，verified 只能由复验产生，修复提交必须在被验证历史中 |
| 单测 | Goal 未满足 | evaluate 返回 2，achieved 转换被拒绝 |
| 单测 | Goal 已达成但证据过期 | 对账报 high/medium，不自动改状态 |
| 单测 | 手改 Goal `status=achieved` | `effective_status=achieved_unverified`，`status_trusted=false` |
| 安全 | 审计记录删除/改写/整链重建 | `audit verify` 为 invalid 并给出行号；checkpoint 不匹配 |
| 安全 | 审计目录缺失或为空 | invalid，不视为干净 |
| 安全 | Agent 或错误密钥签 checkpoint | 拒绝附加，`achieved` 不生效 |
| 集成 | 合法流程 + 受信 checkpoint | `audit verify` valid，`effective_status=achieved` |
| 单测 | 文档断链和冲突 | Finding 带精确位置和 code |
| 单测 | 中英混合检索 | 返回源路径、分数和原文片段 |
| 集成 | Git 快照前后变动 | Context 的 base SHA 反映最新提交 |
| 集成 | 同一任务两个 Agent | 不同 run-id 不互相覆盖 |
| 集成 | GitHub 无权限或 404 | 清晰失败，不凭空生成 |
| 安全 | Issue 提示注入 | 只当数据，不改变 Skill 权限 |
| 安全 | Actions fork PR | 不提权运行，不泄漏令牌 |
| 验收 | 十个真实任务 A/B | 减少交接遗漏、过期文档和找资料成本 |

## 已知限制

- 没有在实际 GitHub 仓库上在线运行过，因为没有提供仓库和 Token。Issue、PR、review 和 CI 证据均为 NOT RUN。
- 没有完成跨模型接续实验。Qoder CN 客户端需要手动切换模型，CLI 不调度模型；真实实验只验证了同一模型的独立会话。
- 没有把 Skill 安装到全局目录；需要用户确认后才执行。
- 没有自动模型编排、后台调度器或并发锁。多 Agent 同时写仍靠乐观检查和人工裁决。
- 没有 GitHub Projects GraphQL 状态读写，也不自动更新 Issue/PR。
- 不自动判断所有自然语言矛盾，语义冲突要人工对账。
- `finish` 不独立请求 CI 或 Review API。人工声明和快照只能标成“报告里有这个字段”，不是独立验证。
- 语义嵌入依赖预装本地模型，自动下载和第三方 API 都被禁用。
- 大仓库的全文检索还需要索引缓存和文档分段优化。
- Windows 上硬链接不可用时，写入会退回到 `O_CREAT|O_EXCL`，no-clobber 语义保留，但没有测试断电恢复。
