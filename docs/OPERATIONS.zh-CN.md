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
11. Goal 标准全部满足后，由授权人转 `achieved`。Agent 的评估建议不等于批准。
12. 需要了解知识关系时运行 `graph` 和 `search`。索引不是新的事实来源。

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
  --id G-AUTH --to approved --approved-by 'human-owner' --reason 'Grooming 通过'
PYTHONPATH=.project-memory/tooling python3 -m project_memory goal transition --repo . \
  --id G-AUTH --to active
```

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

PYTHONPATH=.project-memory/tooling python3 -m project_memory verify --repo . \
  --target-run run-dev-1 --verifier-run run-verify-1 \
  --standard '认证与凭据审查' --verdict pass --evidence-level locally_observed \
  --test-command 'python -m unittest' --test-exit 0 --test-log verify.log \
  --expected-sha <被验证执行的head SHA>
```

`agent_claimed` 不能 pass。本地观察需要命令、整数退出码和存在的非空证据日志（不能是 canonical 文档）；外部验证需要 CI URL 和 passed，但 CLI 不联网抓取；人工批准需要 review URL 和 approved，但 CLI 不认证审批人。发现用 `--findings-file` 提交，high 级发现会阻断 pass。

把通过的验证挂到目标标准，评估和对账：

```bash
PYTHONPATH=.project-memory/tooling python3 -m project_memory goal evidence --repo . \
  --id G-AUTH --criterion C1 --kind verification --ref <verification-id>
PYTHONPATH=.project-memory/tooling python3 -m project_memory goal evaluate --repo . --id G-AUTH
PYTHONPATH=.project-memory/tooling python3 -m project_memory reconcile --repo . --fail-on high
```

`goal evaluate` 未满足时退出 2；`verify` 未通过时退出 2；`run resume` 在阻断状态退出 2；`reconcile --fail-on high` 有 high 时退出 2。`reconcile` 只报告，不自动改文档，也不关闭任务。

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
