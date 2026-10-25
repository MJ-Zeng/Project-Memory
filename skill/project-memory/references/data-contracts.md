# 数据契约与状态机

机器可读契约在 `assets/*.schema.json`，使用 JSON Schema 2020-12。所有生成的 JSON 都带 `schema_version`。新记录使用 `1.2`；通用 handoff 兼容 `1.1`，完成报告仍是 `1.1` 并增加 `evidence_levels`。下游必须拒绝不认识的主版本，可以忽略额外的可选字段。

## 来源与记录

| 记录 | 主要来源 | ID | 可变性 |
|---|---|---|---|
| Goal | `.project-memory/goals/<id>.json` | 人为指定的稳定字符串 | 受控状态转换，带 revision |
| 任务 | GitHub Issue / Project，或本地任务 JSON | `ISSUE:<number>` 或稳定的本地字符串 ID | 由授权的人或工具更新 |
| Agent Run | `.project-memory/runs/<task>/<run>.json` | `run_id`，由人指定 | 状态转换和追加证据 |
| 检查点 | `.project-memory/runs/<task>/<run>.checkpoints/NNNN.json` | run ID + 序号 | 不可变，no-clobber |
| 验证记录 | `.project-memory/verifications/<task>/<ver>.json` | `verification_id` | 不可变，no-clobber |
| 缺陷 | `.project-memory/defects/<task>/<def>.json` | `defect_id` | 状态转换，带 revision |
| Handoff | `.project-memory/handoffs/<task>/<run>.json` 或 `--store` | task + run_id | 不可变，no-clobber |
| Canonical 文档 | 配置 `doc_roots` 下经过审查的文档 | `DOC:<repo path>`，另带 frontmatter `id` | 通过 PR 修改 |
| 镜像 | `mirror_roots` 下的只读副本 | `DOC:<repo path>`，authority 为 `mirror` | 不编辑，只报告分歧 |
| ADR | 经过审查的 `adr_dir` | `ADR-0001` | accepted 通过新 ADR 取代 |
| 对账报告 | `reconcile` 派生输出 | task + 生成时间 | 可丢弃重建 |
| 知识图谱 | 从文档和快照派生 | 节点和边 ID | 可丢弃重建 |
| 上下文与完成报告 | 派生 JSON | task + base SHA（可为空） | 可丢弃重生成 |

跨仓库 ID 在外部系统里必须带 repo slug。MVP 以单个仓库为单位，不保证全局唯一。

## 权威标签

- `canonical`：当前内容，经过审查才能写。
- `mirror`：只读副本。
- `legacy`：历史材料。
- `other`：配置根之外。

没有 Git 的工作区也可以使用，此时 `base_sha` 为 `null`，`vcs` 为 `none`。

`mirror_policy` 有两种：

- `active`（默认）：分歧为 high，必须处理。
- `frozen`：人已经接受镜像永久只读；分歧降为 medium，仍然报告，禁止复制回 canonical。

冻结不会把镜像内容升级成 canonical。

## Goal

必填字段：`id`、`title`、`outcome`、`owner`、`success_criteria`、`status`、`created_at`、`updated_at`、`revision`。可选：`background`、`constraints`、`issues`、`adrs`、`prs`、`approved_by`、`history`。

`success_criteria` 至少一条，每条包含：

- `id`：在 Goal 内唯一。
- `statement`：可核验的陈述。
- `required`：布尔值；至少一条为 true，否则创建被拒绝。
- `evidence`：证据数组，元素包含 `kind` 和 `ref`。

成功标准不是 Issue 清单。Issue 全部关闭不构成达成证据。

### Goal 证据

| kind | 通过条件 | 可信级别 |
|---|---|---|
| `verification` | 验证记录 verdict=pass、`verified=true`、未 stale，且 `target_head_sha` 等于被验证执行当前 head | externally_verified 或 human_approved，取决于验证记录 |
| `commit` | 完整 40 位 SHA，提交存在且在当前 HEAD 历史中 | artifact |
| `test` | 本地日志存在，`exit_code` 为 0 | locally_observed，仍是自报 |
| `manual` | 提供 `approved_by` | human_approved |

`goal evaluate` 只判断证据是否存在、是否绑定当前提交，不判断证据在语义上是否真的支持标准。

### Goal 状态

```text
proposed -> approved -> active -> evaluating -> achieved
     |          |          |          |
     +-> cancelled         +-> blocked --+
```

允许的转换为：

- `proposed -> approved | cancelled`
- `approved -> active | blocked | cancelled`
- `active -> evaluating | blocked | cancelled`
- `evaluating -> achieved | active | blocked | cancelled`
- `blocked -> active | cancelled`
- `achieved` 和 `cancelled` 是终态。

规则：

- 创建时默认 `proposed`。创建为 `approved` 或 `active` 必须提供 `approved_by`。
- 转 `approved` 或 `achieved` 必须提供 `approved_by`，表示人工批准。
- 转 `blocked` 或 `cancelled` 必须提供 `reason`。
- 转 `achieved` 前自动评估；有必达标准未满足时拒绝。
- 每次转换追加 `history`，批准追加 `approvals`。不覆盖旧记录。
- 已批准目标和成功标准只能由授权人通过可审查变更修改。CLI 没有编辑标准的接口。

`achieved` 只表示目标标准已满足并获人工批准，不表示已经部署或生产验证。

## Agent Run

必填字段：`run_id`、`goal_id`、`task`、`agent`、`model`、`git`、`status`、`created_at`、`updated_at`、`revision`。可选：`role`、`tool`、`session_id`、`authorization`、`started_at`、`ended_at`、`artifacts`、`evidence`、`blockers`、`handoff`。

`model` 包含 `provider` 和 `id`。`key` 不写入记录：它可能是凭据或其他机密，模型身份只保留公开标识。

`role`：

- `executor`（默认）：实现或调查。
- `verifier`：独立验证。verifier run 不参与 `unverified_submission` 和 `verified_without_record` 对账。

`git` 至少包含 `base_sha`，可选 `head_sha` 和 `branch`。SHA 必须是完整 40 位小写十六进制。

### Run 状态

```text
queued -> running -> submitted -> verified
   |         |  \        |
   |         |   +-> failed -> running
   |         +-> paused -> running | submitted | failed | cancelled
   +-> cancelled
```

允许的转换为：

- `queued -> running | cancelled`
- `running -> paused | submitted | failed | cancelled`
- `paused -> running | submitted | failed | cancelled`
- `submitted -> verified | failed | superseded | cancelled`
- `verified -> failed | superseded`
- `failed -> running | verified | cancelled | superseded`
- `cancelled` 和 `superseded` 是终态。

规则：

- 同一 run ID 和相同身份内容重试是幂等的；内容不同会失败。
- `run_id` 在仓库内全局唯一；不能同时用于两个任务。
- 状态已经变化就换新的 run ID，不要复用。
- 多个活跃 executor 不会自动阻止，但 `run resume` 报 `needs_human`，`reconcile` 报 medium。verifier 不计入“多个活跃执行”。
- GitHub 上的任务认领只是约定，不是分布式锁。

### 检查点

必填：`run_id`、`task`、`head_sha`、`completed`、`remaining`、`created_at`。可选：`goal_id`、`blockers`、`evidence`、`note`。

- 只有 `queued`、`running`、`paused` 可以写检查点。
- `completed` 和 `remaining` 至少一个非空。
- 检查点按 `0001.json` 递增，no-clobber。
- 与上一个检查点完全相同会幂等返回原记录。

### Handoff 1.2

`run finish` 生成 `schema_version: "1.2"` 的 handoff，除 1.1 字段外增加：

- `goal_id`
- `from_run`
- `model`：provider、id
- `session_id`
- `head_sha`
- `commits`：完整 SHA 数组
- `changed_files`
- `tests`：`{command, exit_code, log}` 数组
- `docs_changed`
- `open_questions`
- `next_actions`

`status` 始终是 `reported_unverified`。1.1 handoff 仍可读，但恢复时降级并给出警告。1.1 不能原地升级：同一 run 已经存在 1.1 handoff 时，`run finish` 会要求改用新的 run ID。

## 验证记录

必填：`verification_id`、`task`、`goal_id`、`target_run`、`verifier_run`、`verifier`、`target_head_sha`、`standard`、`verdict`、`evidence_level`、`verified`、`checks`、`findings`、`created_at`、`revision`。可选：`current_head_sha`、`stale`。

`verdict`：`pass`、`fail`、`inconclusive`。

`evidence_level` 与可信级别：

| 级别 | 序号 | pass 条件 |
|---|---|---|
| `agent_claimed` | 0 | 永远不能 pass |
| `locally_observed` | 1 | test command、整数 exit 0、存在的本地非空证据日志（`.log`/`.txt`/`.json` 等，不能是 canonical 文档） |
| `externally_verified` | 2 | CI URL、`ci_status=passed`；记录标记 `provenance: declared_unfetched` |
| `human_approved` | 3 | review URL、`review_state=approved`；记录标记 `provenance: declared_unfetched` |

规则：

- `target_run` 和 `verifier_run` 必须不同。
- verifier run 的 `role` 必须是 `verifier`；被验证 run 的 `role` 必须是 `executor`。
- 验证者必须在 agent、model 或 session 上与被验证执行不同。三项都相同就拒绝；只有记录层面的独立性，不代表结论正确。
- 被验证执行必须是 `submitted`、`verified` 或 `failed`。
- `target_head_sha` 必须存在且是当前仓库中的提交。
- `current_head_sha` 与 `target_head_sha` 不同时 `stale=true`，不能给出 pass。
- `--expected-sha` 必须等于被验证执行的 head。
- 有 high 级 finding 时不能 pass。
- `verified = (verdict == pass) and (evidence_level != agent_claimed) and not stale and no high findings`。
- pass 把目标执行置为 `verified`；fail 置为 `failed`。
- 验证记录不可变。代码变化后要重新验证，生成新记录。

`findings` 在验证记录里是缺陷 ID 数组。缺陷记录保留原始位置、复现和严重度。

## 缺陷

必填：`defect_id`、`task`、`goal_id`、`verification_id`、`target_run`、`severity`、`location`、`summary`、`status`、`created_at`、`updated_at`、`revision`。可选：`repro`、`fixed_in_sha`、`verified_by`、`history`。

`severity`：`high`、`medium`、`low`。

状态转换：

- `open -> fixed | wontfix | closed`
- `fixed -> open | wontfix`
- `verified -> open`（复验失败或新证据推翻）
- `wontfix -> open`
- `closed -> open`

规则：

- `fixed` 必须提供存在的完整提交 SHA。
- `verified` 不能手工设置；只能由 pass 验证的 `--resolves-defect` 产生，并写入 `verified_by`。对账会检查该引用是否存在、是否通过、是否针对同一执行。
- 不删除缺陷记录。`wontfix` 和 `closed` 要写理由。

## 对账报告

必填：`generated_at`、`state`、`counts`、`items`、`summary`、`goals`、`recommended_next_actions`。

`state`：`clean` 或 `needs_attention`。

每个 item 包含 `severity`、`code`、`message`、`refs`、`action`。对账检查：

- 已达成的 Goal 是否仍有未满足标准；
- 有 Goal 但没有执行；
- 高等级缺陷；
- pass 没有验证记录；
- 孤立执行；
- 未验证提交；
- 验证记录缺失；
- handoff 缺失；
- 基准不是祖先；
- 多个活跃执行；
- 旧提交验证；
- Agent 自报 pass；
- 修复提交不在历史中；
- 文档审计发现；
- accepted ADR 未关联。

对账报告是建议，不是授权，也不自动改 canonical 文档。

## 任务状态

建议在 GitHub Project 中使用：`proposed -> ready -> in-progress -> in-review -> verification -> done`。`blocked` 是独立的标签，`cancelled` 是终态。CLI 不修改 GitHub 状态。

## 审计范围

`scope: all`（默认）扫描 canonical、mirror 和 legacy，用于完整复核。

`scope: current` 扫描 canonical 中状态为 `current`、`draft`、`in_flight`、`unclassified` 的文档，以及全部 ADR；排除 mirror、legacy、evidence、historical、superseded 和 archived。

`docs_scanned` 是范围内的记录数，`docs_scanned_total` 是考虑过的候选数，`docs_excluded` 是两者之差。CI 门禁用 `current`，周期对账用 `all`。配置了 `entry_doc` 时，两种范围都会检查入口。

## 入口文档与新鲜度

`entry_doc` 指向人最先读的那一篇文档。设置后，审计要求它存在于扫描范围内、authority 为 `canonical`、显式声明 `status: "current"`，并检查 `last_verified_at`。

缺失、非 canonical 或非 current 报 high。入口没有 `last_verified_at` 报 low。日期超过 `max_verified_age_days`（默认 90 天）时，入口报 medium，其他 current 文档报 low。

`last_verified_at` 表示人在这天重新核对过结论；`updated_at` 只记录编辑。审计只报告年龄，不改写，也不提升状态。

入口文档应控制在几分钟内能读完，大约 2k tokens。它是阅读路径，不是文档的第二份副本。

## 可信级别

```text
agent_claimed < locally_observed < externally_verified < human_approved
```

- `agent_claimed`：Agent 的文字声明、自由文本测试证据、单独出现的 `--reviewed-by`。
- `locally_observed`：本地命令、整数退出码和存在的非空证据日志。
- `externally_verified`：外部 CI 声明。CLI 离线时不联网，记录为 `declared_unfetched`。
- `human_approved`：review URL 和 approved 状态，或明确的 `approved_by`。CLI 不能认证审批人身份，仍属调用方声明。

Handoff 和快照默认是 `reported_unverified`。检索命中不能直接当权威，必须先核对来源状态。

## Gate 状态

`pass`、`fail`、`unknown`。**`unknown` 永远不等于 `pass`。**

完成报告只有在全部 gate 为 pass 时才能给出 ready，但它不是授权，也不证明事实已经核实。CLI 的 `--reviewed-by` 和 `--test-evidence` 是声明，不是实时独立的 CI 检查。更严格的生产环境需要接入经过验证的状态检查。

## 兼容与迁移

- 新记录只写 `1.2`。旧 1.1 数据保持可读，不批量重写。
- 通用 `handoff` 在没有 metadata 时仍写 1.1；`run finish` 写 1.2。
- 完成报告仍是 1.1，新增 `evidence_levels` 是可选字段。
- 下游遇到未知主版本应拒绝，遇到额外字段应忽略。
- 从 1.1 迁移到 1.2 不需要改历史 handoff；下一次 `run finish` 会生成 1.2。若同一 run 已有 1.1 handoff，改用新的 run ID，不要原地覆盖。
- 迁移脚本不在本次范围内。需要批量迁移时先写受审查的一次性脚本，并保留原始文件。

## Frontmatter 子集

Python 实现只支持受限 YAML：一层 `key: scalar` 和 JSON 兼容的行内数组。不支持嵌套 YAML、多行 YAML、锚点和别名。

`SKILL.md` 由 Agent 阅读，不会被解析成项目 canonical 文档。这个限制是为了避免引入运行时 YAML 依赖。后续升级应该使用真正的解析器和 schema 校验，不要靠猜。

## 图边语义

`references` 和 `supersedes` 是从文档和快照中抽取的显式链接。一条边只证明存在引用，不证明双方一致、已经实现或存在因果关系。

`unresolved` 表示被引用的对象不在本地索引里，不代表它在 GitHub 上一定不存在。
