# 工作流与 CLI 操作

CLI 运行在 Python 3.11 及以上，不需要运行时依赖。在分发目录用 `python3 -m project_memory CMD`；在已初始化的仓库里用 `PYTHONPATH=.project-memory/tooling python3 -m project_memory CMD`。

## 默认没有破坏性操作

所有命令要么只读并输出报告，要么创建新文件。`graph --output` 和报告类命令的 `--output` 会覆盖指定的本地报告位置；这些报告是生成产物，不是事实来源。

没有命令会合并、提交、推送、更新 GitHub Issue、批准 ADR、自动把 Goal 标为 achieved 或修改 Ruleset。`run finish`、`verify` 和 `reconcile` 只写 `.project-memory/` 下的本地记录。

## 初始化与工具同步

```bash
python3 -m project_memory init --repo /path/to/repo --install both
```

已有多种文档根的工作区，用 overlay，不要新建 `docs/`：

```bash
python3 -m project_memory init --repo /path/to/workspace --install none --profile overlay \
  --docs-root doc/new_doc \
  --mirror-root pro2-mixed-training/docs/project-docs \
  --legacy-root doc/_legacy_2026-10-23
```

检查 `.project-memory/config.json`、模板、复制进去的 Skill 和 CLI。

`full` 还会写 GitHub 模板、INDEX、CURRENT_STATE、架构占位和 `.github/workflows/project-memory-check.yml`，并把 `entry_doc` 指向生成的 CURRENT_STATE。这个模板不带 `last_verified_at`，填写的人核对之后自己补。

overlay 不写文档占位，所以要自己补一篇当前状态文档，再设置 `entry_doc`。

`init` 不覆盖已有文件，也不配置 GitHub Ruleset。检查 `.github/CODEOWNERS.example`，真正的 CODEOWNERS 通过 PR 单独配置。

分发目录里的 CLI 和 Skill 更新后，先看差异再同步：

```bash
python3 -m project_memory sync-tooling --repo .
python3 -m project_memory sync-tooling --repo . --write
```

第一行只报告 `added`、`changed`、`extra` 和 `unchanged`。`--write` 只更新已跟踪的工具文件，不删除 `extra`，也不覆盖已安装到 `.agents` 或 `.claude` 的 Skill 副本。Skill 和 CLI 变更需要人工审查。

## Goal

创建目标。至少一个必达成功标准；默认 `proposed`：

```bash
python3 -m project_memory goal create --repo . \
  --id G-AUTH --title '修复认证绕过' \
  --background '审查发现缺少令牌时仍可通过' \
  --outcome '未授权请求被拒绝，且凭据不落代码' \
  --owner backend-team \
  --criterion '所有无令牌请求返回 401' \
  --criterion '仓库中不存在硬编码令牌' \
  --issue 325 --adr ADR-0001 --dry-run
```

`--dry-run` 只返回将要写入的记录，不落盘；`goal create`、`goal transition` 和 `defect update` 都支持。`--status approved` 或 `--status active` 必须同时提供 `--approved-by`；HTTP/CLI 参数不是人工批准，批准人必须真实存在。

查看、列出和评估：

```bash
python3 -m project_memory goal show --repo . --id G-AUTH
python3 -m project_memory goal list --repo .
python3 -m project_memory goal evaluate --repo . --id G-AUTH
```

`evaluate` 只看证据，不看 Issue 是否关闭。未满足时退出码为 2，满足时为 0。评估结论有 caveat：它检查证据是否存在并绑定当前提交，不判断证据在语义上是否支持标准。

添加证据：

```bash
python3 -m project_memory goal evidence --repo . --id G-AUTH \
  --criterion C1 --kind verification --ref VER-f17891e6cdd3

python3 -m project_memory goal evidence --repo . --id G-AUTH \
  --criterion C2 --kind test --ref artifacts/tests-auth.log --exit-code 0

python3 -m project_memory goal evidence --repo . --id G-AUTH \
  --criterion C2 --kind manual --ref 'review:https://...' \
  --approved-by 'human-owner'
```

证据类型：

- `verification`：必须是已通过、未过期、且 `target_head_sha` 与被验证执行当前 head 一致的验证记录。
- `commit`：完整 40 位 SHA，且在当前 HEAD 历史中。
- `test`：本地日志存在，`exit_code` 为 0。它仍属于自报证据，除非另有独立验证。
- `manual`：必须有 `approved_by`。

受控状态转换：

```bash
python3 -m project_memory goal transition --repo . --id G-AUTH \
  --to approved --approved-by 'human-owner' --reason 'Grooming 通过'
python3 -m project_memory goal transition --repo . --id G-AUTH --to active
python3 -m project_memory goal transition --repo . --id G-AUTH --to evaluating
python3 -m project_memory goal transition --repo . --id G-AUTH \
  --to achieved --approved-by 'human-owner' --reason 'C1-C3 均有独立验证'
```

`blocked` 和 `cancelled` 必须提供 `--reason`。`achieved` 会先评估标准，未满足时拒绝。`evaluate` 给出 `achieved` 建议不等于批准，转换仍需要授权人。

已批准目标和成功标准只能由授权人通过可审查的变更修改。CLI 没有编辑标准的命令；不要直接改 JSON 绕过审批。

## Agent 执行记录

开始一次执行：

```bash
python3 -m project_memory run start --repo . \
  --goal G-AUTH --task 325 --run-id run-dev-1 \
  --agent qoder --model-provider qoder-cn --model-id dfmodel \
  --tool qoder-desktop --session-id <session-id> \
  --role executor --branch fix/auth \
  --base-sha <40位SHA> \
  --authorization 'Issue #325 范围内修改认证代码，不合并、不部署'
```

`--model-id` 填实际使用的模型标识，不要填猜测值；记录只保存 provider 和 id，不保存任何模型密钥。`--role executor` 是默认值；独立验证者用 `--role verifier`。`--status` 可选 `queued`、`running`、`paused`，默认 `running`。`--dry-run` 只返回记录，并如实报告已有记录是否会被新建。

同一任务有多个活跃执行时，命令会警告，但不会强行阻止，因为 CLI 没有分布式锁。GitHub 上的任务认领只是约定。

写检查点：

```bash
python3 -m project_memory run checkpoint --repo . \
  --task 325 --run-id run-dev-1 \
  --completed '定位绕过路径' --remaining '补测试并运行' \
  --evidence 'src/auth.py' --head-sha <40位SHA>
```

检查点是不可变的编号文件。与上一个检查点完全相同会幂等返回原记录；执行已结束时拒绝写入。

结束执行：

```bash
python3 -m project_memory run finish --repo . \
  --task 325 --run-id run-dev-1 \
  --completed '拒绝无令牌请求' --remaining '检查硬编码凭据' \
  --commit <40位SHA> --changed-file src/auth.py \
  --test-command 'python -m unittest tests.test_auth' --test-exit 0 \
  --test-log artifacts/tests-auth.log \
  --open-question '生产令牌轮换流程未确认' \
  --next-action '独立审查凭据处理'
```

`run finish` 生成 schema 1.2 的 handoff 和恢复元数据，把执行置为 `submitted`、`failed` 或 `cancelled`。它不验证工作，也不关闭 Issue。`--tests-file` 可以一次传入多个 `{command, exit_code, log}`。如果同一 run 已有 1.1 handoff，`run finish` 拒绝原地升级，要求使用新的 run ID。

恢复：

```bash
python3 -m project_memory run resume --repo . --task 325
python3 -m project_memory run resume --repo . --task 325 --run-id run-dev-1
python3 -m project_memory run resume --repo . --goal G-AUTH
```

返回状态：

| 状态 | 含义 | 退出码 |
|---|---|---|
| `resume_ready` | 交接和基准检查可继续 | 0 |
| `verified` | 已有通过的验证记录 | 0 |
| `no_run` | 没有执行记录 | 0 |
| `needs_handoff` | 缺 handoff，只能从代码和提交恢复 | 2 |
| `needs_human` | 多个活跃执行或需要人工裁决 | 2 |
| `stale_base` | 基准提交不在当前 HEAD 历史中 | 2 |

`resume_ready` 只表示记录齐全，不证明前一个 Agent 的声明为真。继续之前核对 `checks`、handoff 中的提交和测试，以及未关闭的缺陷。默认选择最近的 executor，不会把 verifier run 当成接手对象；没有 handoff 但有检查点时使用最近检查点。1.1 旧 handoff 仍可读，但会降级并给出警告。执行标记为 `verified` 但验证绑定的提交已不是当前 HEAD 时，返回 `needs_human`，不会返回 `verified`。

换模型或换会话时创建新的 run ID，新 run 的 `base-sha` 指向前一个 head。不要覆盖旧 run。

查看和列出：

```bash
python3 -m project_memory run show --repo . --task 325 --run-id run-dev-1
python3 -m project_memory run list --repo . --goal G-AUTH
```

## 独立验证

被验证执行必须已 `run finish`。验证者必须是另一个 run，且必须使用 `--role verifier`。验证者还必须在 agent、model 或 session 上与被验证执行不同；三项都相同会拒绝。只有记录层面的独立性，不代表结论正确。

先跑快照执行，拿到收据：

```bash
python3 -m project_memory test-run --repo . --agent qoder \
  --command 'python -m unittest tests.test_auth' --trusted
# 输出 .project-memory/receipts/EXE-<id>.json
```

```bash
python3 -m project_memory verify --repo . \
  --target-run run-dev-1 --verifier-run run-verify-1 \
  --standard '认证绕过与凭据处理审查' \
  --verdict pass --evidence-level locally_observed \
  --test-receipt .project-memory/receipts/EXE-<id>.json \
  --expected-sha <被验证执行的head SHA>
```

证据级别：

| 级别 | 通过条件 | 能否 pass |
|---|---|---|
| `agent_claimed` | 只有声明 | 不能 |
| `locally_observed` | `test-run` 执行收据（命令、整数退出码、日志哈希和快照摘要可重算）；手写日志不算 | 可以，退出码必须为 0 |
| `externally_verified` | CI URL 和 `--ci-status passed` | 可以，但记录是 `declared_unfetched` |
| `human_approved` | review URL 和 `--review-state approved`；CLI 不认证审批人 | 可以，但仍是调用方声明 |

CLI 离线运行，不联网核对 CI 或 review；`externally_verified` 和 `human_approved` 是声明，不是已抓取的外部事实。验证拒绝的情况：自己验证自己、验证者不是 `role=verifier`、agent/model/session 三项都相同、目标执行还没结束、当前 HEAD 已变化、`--expected-sha` 与目标 head 不一致、有 high 级发现时要求 pass。验证记录绑定 `target_head_sha`；事后改代码不会自动让旧验证继续有效。验证记录只能用于同一 Goal 的证据，不能跨 Goal 复用。

本地 CLI 写出的记录最多是 `MANUAL_REVIEW_REQUIRED`，`verified=false`，不会把执行升级为 `verified`，也不能满足 Goal；只有仓库外受保护信任锚对记录签名并通过 `PROJECT_MEMORY_TRUST_ANCHOR` 验证后，才可能成为 `VERIFIED`。没有配置信任锚时，这是预期的 fail-closed 结果。

发现写入 JSON 文件：

```json
[
  {"severity": "high", "file": "src/auth.py", "line": 12,
   "summary": "凭据硬编码在源码中", "repro": "读取 src/auth.py 第 12 行"}
]
```

```bash
python3 -m project_memory verify --repo . \
  --target-run run-dev-1 --verifier-run run-verify-1 \
  --standard '凭据处理审查' --verdict fail --evidence-level locally_observed \
  --test-receipt .project-memory/receipts/EXE-<id>.json --findings-file findings.json
```

pass 会把目标执行置为 `verified`；fail 置为 `failed` 并创建缺陷。验证命令在未通过时退出码为 2。

## 缺陷

```bash
python3 -m project_memory defect list --repo . --task 325
python3 -m project_memory defect show --repo . --id DEF-1b77a3e93a52
python3 -m project_memory defect update --repo . --id DEF-1b77a3e93a52 \
  --status fixed --fixed-in-sha <40位SHA> --note '改为环境变量并常量时间比较'
python3 -m project_memory defect update --repo . --id DEF-1b77a3e93a52 \
  --status wontfix --note '该路径已删除'
```

`fixed` 必须绑定存在且完整的提交 SHA。`verified` 不能手工设置，`defect update --status verified` 会被拒绝；只能由 pass 验证的 `--resolves-defect` 产生。缺陷必须已经 `fixed` 或 `verified`，且属于同一任务：

```bash
python3 -m project_memory verify --repo . \
  --target-run run-fix-1 --verifier-run run-verify-2 \
  --standard '重新验证凭据处理' --verdict pass --evidence-level locally_observed \
  --test-receipt .project-memory/receipts/EXE-<id>.json \
  --resolves-defect DEF-1b77a3e93a52
```

## 知识对账

```bash
python3 -m project_memory reconcile --repo .
python3 -m project_memory reconcile --repo . --format markdown
python3 -m project_memory reconcile --repo . --fail-on high
```

对账检查：已达成的 Goal 是否仍有未满足标准、有 Goal 但没有执行、高等级缺陷、pass 没有验证记录、孤立执行、未验证提交、验证记录缺失、handoff 缺失、基准不是祖先、多个活跃 executor、旧提交验证、Agent 自报 pass、缺陷标为 verified 但没有有效验证记录、修复提交不在历史中、文档审计发现、accepted ADR 未关联。verifier run 不参与未验证提交和多个活跃执行的判断。

`--fail-on high|medium|low|none` 控制退出码，默认 `none`。对账只报告，不自动改文档、不合并、不关闭任务。报告可以重建，不是第二份权威存储。

## 接手项目

先读 `entry_doc`，再用 `audit --scope current` 确认当前有效文档集合：

```bash
python3 -m project_memory audit --repo . --scope current --fail-on high
python3 -m project_memory search --repo . '要核对的具体说法'
```

不要从 `legacy_roots`、档案、证据快照或计划里推导当前状态。`entry_doc` 必须声明 `status: "current"`；缺少 `last_verified_at` 报 low，超过 `max_verified_age_days` 报 medium。入口缺失或不是 current 报 high。五个接手问题和阅读顺序见 `onboarding.md`。

人接手只读仓库里提交的 Markdown，不应该依赖运行这个 CLI。

## 开始任务

```bash
# 实时 Issue
python3 -m project_memory start --repo . --issue 325 --slug ORG/REPO --output context.json

# 离线快照
python3 -m project_memory start --repo . --issue-file issue.json --output context.json

# 没有 GitHub 的本地任务
python3 -m project_memory start --repo . --task-file task.json --output context.json
```

返回 `task_id`、来源（`github_api`、`local_task_file` 或 `provided_snapshot_unverified`）、可为空的 `base_sha`、`vcs`、证据指针、抽取出的引用和词法匹配到的文档候选。

检索只是启发式，相关决策和文档仍要核对。显式提供的快照没有经过独立确认。

## 通用交接

```bash
python3 -m project_memory handoff --repo . --task 325 --agent codex \
  --run-id codex-325-attempt-01 --completed '实现认证中间件' \
  --remaining '检查管理员绕过路径' --evidence 'PR #342'
```

把记录写到被审计仓库之外：

```bash
python3 -m project_memory handoff --repo /audited/repo --task local-task-id \
  --agent codex --run-id run-01 --completed '读完文档' --remaining '核对结论' \
  --store /tmp/handoffs
```

run ID 不可复用。相同内容重试是幂等的；状态发生变化就换新的 run ID。记录状态始终是未验证，直到有人核对。

`run finish` 会自动写带模型、head SHA、提交、测试和下一步的 1.2 handoff。单独的 `handoff` 用于没有 Agent Run 的通用交接，schema 为 1.1。

## 完成检查

```bash
python3 -m project_memory finish --repo . --issue-file issue.json \
  --pr-file pr.json \
  --test-command 'python -m unittest' --test-exit 0 --test-log tests.log \
  --ci-url 'https://ci.example/run/1' --ci-status passed \
  --docs-impact updated \
  --review-url 'https://github.com/ORG/REPO/pull/342#pullrequestreview-1' \
  --review-state approved
```

支持 `--docs-impact not-applicable --docs-justification '...至少 12 个字符...'`。

`finish` 不执行测试，不独立验证人工声明，也不关闭 Issue。有实时访问时优先用 `--issue 325 --pr 342 --slug ORG/REPO`。

只有同时有测试命令、整数退出码 0 和存在的本地日志，测试门禁才 pass。单独的 `--test-evidence` 文本只是 `agent_claimed`。PR 合并门禁只有在实时 GitHub API 确认时才 pass，离线快照报 unknown。文档影响使用实时 API 文件列表，快照报 unknown。审查只有 review URL 加 `approved` 才 pass，单独的 `--reviewed-by` 报 unknown。`ci_evidence` 缺失或失败会阻断 ready。即使建议是 ready，也仍然从属于 GitHub 审查和分支保护。

## 决策

```bash
python3 -m project_memory decision --repo . --title 'Redis 缓存策略' \
  --topic caching --issue 325 --owner backend-team \
  --options '本地缓存; Redis; 不用缓存' --rationale '多节点需要共享失效'
```

在 `docs/decisions/ADR-NNNN-*.md` 创建 `status=proposed` 的 ADR。改成 `accepted` 和填写 `approved_by` 需要经过人工批准的变更。不要改写已经接受的旧 ADR。

## 写文档

```bash
python3 -m project_memory new-doc --repo . \
  --id DOC-CACHE-001 --title '缓存口径' \
  --kind canonical --status draft \
  --owner backend-team --path docs/topics/cache.md --issue 325

python3 -m project_memory new-doc --repo . \
  --id EVID-CACHE-2026-10 --title '缓存基准原始记录' \
  --kind evidence --status evidence \
  --owner backend-team --path docs/evidence/cache-2026-10.md
```

命令写入固定 frontmatter 和章节骨架，使用 no-clobber 语义。canonical 只能从 `draft` 或 `in_flight` 开始，evidence 只能用 `evidence`。它会拒绝 `current`、重复 ID、已存在路径、ADR 目录、mirror/legacy 根，以及配置文档根之外的路径。它不填结论，不验证证据，也不提升状态。

写之前先读 `document-authoring.md` 里的写入门禁、目标与状态对照表和审查清单。

## 审计、图谱与检索

```bash
python3 -m project_memory audit --repo . --scope current --fail-on high
python3 -m project_memory audit --repo .
python3 -m project_memory graph --repo .
python3 -m project_memory search --repo . '角色权限兼容'
python3 -m project_memory search --repo . --backend semantic \
  --model /models/local-sentence-transformer 'role authorization'
```

`semantic` 模式需要可选依赖 `sentence-transformers` 和预先准备好的模型目录，不会自动下载模型。词法模式使用中文字符双字加拉丁词 TF-IDF，不要把词法模式说成语义嵌入。

`audit --scope current --fail-on high` 在 current canonical 文档和全部 ADR 中出现 high 时返回非零。范围内的 canonical 文档为零本身也是 high，除非显式传 `--allow-empty`。配置了 `entry_doc` 时，两种范围都要求它存在、属于 canonical、声明 `status: "current"`；年龄与 `max_verified_age_days`（默认 90）比较。

默认全量审计还会扫 mirror、legacy 和 evidence，用于复核，不作为 CI 门禁。

`search` 默认排除 legacy、mirror 和已归档状态；`evidence` 文档仍可能出现。要查看历史或镜像副本，加 `--include-archived` 或 `--include-mirror`，并看返回的 `authority` 和 `status`。

## 团队日常流程

1. 创建 Issue，写清负责人、验收标准和相关 ADR；必要时创建 Goal 和可核验的成功标准。
2. 用 `start` 取当前 SHA 和可追溯的上下文。
3. Agent 在独立分支或工作树上开发，`run start` 登记模型、会话和授权范围，PR 关联 Issue。
4. 换工具或换人之前写 `run checkpoint` 或 `run finish`。
5. 另一个会话或人用 `run resume` 接手；用 `verify` 独立检查提交和证据，发现转成缺陷。
6. 走 PR 的 CI 和人工审查。重要 ADR 变更单独提一个受审查的 PR。
7. 用 `finish` 检查证据，不自动关闭；用 `goal evaluate` 检查标准，不自动标为 achieved。
8. 合并后和每周复核时用 `reconcile` 和 `audit` 检查知识漂移。
9. 任何发现都转成 Issue，不要未经审查直接重写 canonical 文档。
