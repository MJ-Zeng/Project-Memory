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

`agent_claimed` 不能 pass。`locally_observed` 必须提供 `test-run` 生成的执行收据；手写日志不再算执行证据。外部验证需要 CI URL 和 passed，但 CLI 不联网抓取；人工批准需要 review URL 和 approved，但 CLI 不认证审批人。发现用 `--findings-file` 提交，high 级发现会阻断 pass。`--findings-file` 与 `--criterion-evidence` 的相对路径按 `--repo` 解析，绝对路径原样使用。

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

例外：必达标准集合为空（例如所有判据被改成可选或删除）时，`goal evaluate` 退出 0，但 `satisfied=false`、`evaluation_status=insufficient_evidence`、`status_problems` 含 `no_required_criteria`。自动化不要只看退出码，要读 `satisfied`/`effective_status`/`status_trusted`/`status_problems`；需要纯退出码门禁时，后续版本再提供显式 `--strict`，本版没有。

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
