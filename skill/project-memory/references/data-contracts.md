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

| kind | 通过条件 | 能否单独满足标准 | 可信级别 |
|---|---|---|---|
| `verification` | 验证记录 `verdict=pass`、`status=VERIFIED`、`verified=true`、`mapping_status=complete`、该 criterion 有 `evidence_matched` 映射，**且**记录带受保护信任锚的分离签名 | 只有签名验证通过时才能 | evidence_matched；本地未签名记录一律 untrusted |
| `commit` | 完整 40 位 SHA，提交存在且在当前 HEAD 历史中 | 不能，只证明提交存在 | artifact |
| `test` | 本地日志存在，`exit_code` 为 0 | 不能，只证明执行过；需要 criterion 映射和 coverage 复核 | locally_observed |
| `manual` | 提供 `approved_by`，且 `ref` 是可追溯的批准链接、PR/Issue 编号或 40 位提交 SHA | 不能；没有可信审批来源时只是未核验声明 | unverified_approval |

`goal evaluate` 只接受已确认覆盖且带可信授权的 criterion 映射。直接 `test`/`commit` 证据会被记录为补充材料，但不会让标准变成 satisfied；`manual` 证据保持 `UNVERIFIED_APPROVAL`。没有配置 `PROJECT_MEMORY_TRUST_ANCHOR` 时，本地写出的验证记录不会满足任何标准，这是预期的 fail-closed 结果。评估状态分为 `satisfied`、`needs_review`、`partial`、`insufficient_evidence` 和 `blocked_by_defect`；Issue 全部关闭不等于目标达成。

### Criterion Evidence Mapping

pass 验证必须提供 `--criterion-evidence` JSON（模板见 `assets/criterion-evidence.schema.json`）。每个必达标准一条：

| 字段 | 说明 |
|---|---|
| `criterion_id` | Goal 中的标准 ID，必须存在 |
| `goal_id` / `task_id` | 必须与验证目标和执行任务一致 |
| `criterion_description` | 必须与 Goal 标准文本一致；不一致不能确认覆盖 |
| `target_repository` | 必须是当前仓库名或路径 |
| `target_commit_sha` | 完整 40 位 SHA，必须等于被验证执行的 head |
| `evidence_id` | 稳定的证据 ID；跨 Goal 复用会被拒绝 |
| `evidence_source` | `test`、`check`、`command`、`ci` 或 `review` |
| `evidence_command` / `evidence_log` | 本地执行证据必须有命令和可读取的非空日志 |
| `evidence_receipt` | 本地执行证据必须提供 `test-run` 生成的执行收据；手写日志不算 |
| `evidence_exit_code` | 本地执行证据必须有整数退出码；`passed` 时必须是 0 |
| `execution_status` | `passed`、`failed`、`error`、`not_run` 或 `unknown` |
| `coverage_claim` | 说明该检查覆盖标准的哪一部分；只是声明，不是证明 |
| `coverage_review_status` | `confirmed` 才能用于 pass；由独立 verifier 复核，但仍属 Agent 声明 |
| `independent_verifier` | 必须等于 verifier run 的 agent；与被验证执行的 agent 相同且 model/session 也相同时拒绝 |
| `verification_result` | `pass`、`fail` 或 `inconclusive`；pass 验证中必须是 `pass` |

映射必须覆盖全部必达标准并绑定同一个 `target_commit_sha`。字段齐全但 coverage 未确认时返回 `INSUFFICIENT_EVIDENCE`；只覆盖部分标准时返回 `PARTIAL_COVERAGE`；存在未关闭 high 缺陷时返回 `BLOCKED_BY_DEFECT`。这些状态都不会写 pass 记录，也不会把执行置为 `verified`。

CLI 不能判断测试与标准的语义相关性；`coverage_claim` 中的关键词相似度不算覆盖证据。确认覆盖必须由独立 verifier 明确写出 `coverage_review_status=confirmed`，并接受人工复核。

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

必填：`verification_id`、`task`、`goal_id`、`target_run`、`verifier_run`、`verifier`、`target_head_sha`、`standard`、`verdict`、`evidence_level`、`trust_level`、`verified`、`checks`、`findings`、`created_at`、`revision`。可选：`current_head_sha`、`stale`、`status`、`mapping_status`、`criterion_evidence`、`covered_criteria`、`missing_criteria`。

`verdict`：`pass`、`fail`、`inconclusive`。

`status`：`VERIFIED`、`MANUAL_REVIEW_REQUIRED`、`INSUFFICIENT_EVIDENCE`、`PARTIAL_COVERAGE`、`BLOCKED_BY_DEFECT`、`FAILED`、`INCONCLUSIVE`。只有 `VERIFIED` 会把目标执行置为 `verified`；本地 CLI 没有受保护签名，写出的完整记录也只能是 `MANUAL_REVIEW_REQUIRED`，`verified=false`。

`mapping_status`：`missing`、`partial`、`complete`、`invalid`。pass 验证要求 `complete`。

`evidence_level` 与可信级别：

| 级别 | 序号 | pass 条件 |
|---|---|---|
| `agent_claimed` | 0 | 永远不能 pass |
| `locally_observed` | 1 | `test-run` 执行收据（命令、整数 exit 0、日志哈希、快照摘要可重算）；手写日志不算 |
| `externally_verified` | 2 | `--pr` 抓取到该提交全绿且 head 匹配；仅声明 CI URL、`ci_status=passed` 只记为 `declared_unfetched` |
| `human_approved` | 3 | review URL、`review_state=approved`；记录标记 `provenance: declared_unfetched`；CLI 不能声明该等级 |

CLI 的 `verify --evidence-level` 接受 `agent_claimed` 与 `locally_observed`；`externally_verified` 仅在同时提供 `--pr` 且 `verdict=pass` 时接受，由 CLI 实际读取；`human_approved` 仍不能通过 CLI 提交。

`evidence_level` 是调用方声明。`trust_level` 取声明级别与实际可观察证据级别的较小值；手工提高声明不会提高 `trust_level`。即使 `trust_level` 较高，没有受保护信任锚签名的记录仍然不能被 `goal evidence` 当作达成依据。

规则：

- `target_run` 和 `verifier_run` 必须不同，且属于同一 Goal 和任务。
- verifier run 的 `role` 必须是 `verifier`；被验证 run 的 `role` 必须是 `executor`。
- 验证者必须在 agent、model 或 session 上与被验证执行不同。三项都相同就拒绝；只有记录层面的独立性，不代表结论正确。
- 被验证执行必须是 `submitted`、`verified` 或 `failed`。
- `target_head_sha` 必须存在且是当前仓库中的提交。
- `current_head_sha` 与 `target_head_sha` 不同时 `stale=true`，不能给出 pass。
- `--expected-sha` 必须等于被验证执行的 head。
- 有 high 级 finding 时不能 pass。
- pass 必须提供 `criterion_evidence`，覆盖全部必达标准，且每条映射 `evidence_matched=true`、`coverage_review_status=confirmed`、`target_commit_sha=target_head_sha`、`criterion_description` 与 Goal 标准一致。
- 存在未关闭 high 缺陷（且未在本次 `--resolves-defect` 中处理）时返回 `BLOCKED_BY_DEFECT`。
- 只有日志和退出码、但没有 criterion 映射时返回 `INSUFFICIENT_EVIDENCE`；只覆盖部分标准时返回 `PARTIAL_COVERAGE`。
- `verified = (verdict == pass) and (evidence_level != agent_claimed) and not stale and mapping_status == complete and no high findings and authority.trusted`。
- 本地 CLI 没有签名能力，所以 `verified` 恒为 false；只有外部签名器对记录做 detached signature 并通过 `PROJECT_MEMORY_TRUST_ANCHOR` 验证后，才可能变成 `VERIFIED`。
- pass 且 `status=VERIFIED` 才把目标执行置为 `verified`；fail 置为 `failed`。
- 验证记录不可变。代码变化后要重新验证，生成新记录。
- 缺少 criterion 映射的旧 pass 记录可读，但 `goal evidence` 不会接受它作为标准达成依据；`reconcile` 会报告 `pass_without_criterion_mapping`。

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
- pass 没有 criterion 映射；
- pass 的 criterion 覆盖不完整；
- 同一 `evidence_id` 跨 Goal 复用；
- criterion 描述与 Goal 标准不一致；
- 进行中的 Goal 证据仍是 `needs_review`、`partial` 或 `insufficient_evidence`；
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

## Current 文档元数据契约

`status=current` 的 canonical 文档建议包含：

- 必填：`status`、`owner`、`last_verified_at`；已有文档还应保留 `id`、`kind`、`title`。
- 推荐：`evidence`、`verified_commit`、`related_decisions`、`superseded_by`。

审计只按以下语义报告，不自动改写字段：

- 没有声明 `status`：`unknown_document_status`（low），按推断状态处理，不证明内容错误。
- current 缺少 `owner`：`current_document_missing_owner`（medium）。
- current 缺少 `last_verified_at`：`current_document_unverified`（low）。
- `last_verified_at` 超过 `max_verified_age_days`：`stale_current_document`（入口 medium，其他 current low）；表示需要重新核验，不代表结论错误。
- `verified_commit` 是当前 HEAD 的祖先：`verified_source_changed`（low）；已分叉：`verified_source_diverged`（medium）；不存在或格式错误：`verified_commit_missing` / `invalid_verified_commit`（medium）。
- `superseded` 缺少 `superseded_by`：medium。
- legacy/mirror 缺少新字段：`legacy_metadata_warning`（low，按根目录聚合），不逐篇判定旧文档错误。
- legacy/mirror 声明 `status=current`：`authority_status_conflict`（medium），不能据此当作当前知识。

这套契约为向后兼容而设计：旧文档不会仅因缺少新字段被自动判错，也不会被批量改写。`evidence`、`verified_commit`、`related_decisions`、`superseded_by` 是推荐字段；缺失只进入 `metadata_contract` 诊断，不单独产生 high/medium finding。

## 可信级别

```text
agent_claimed < locally_observed < externally_verified < human_approved
```

- `agent_claimed`：Agent 的文字声明、自由文本测试证据、单独出现的 `--reviewed-by`。
- `locally_observed`：`test-run` 执行收据、整数退出码和可重算的日志/快照摘要；只证明执行事实。
- `externally_verified`：`--pr` 通过 GitHub API 读取 PR head 的 check runs；抓取成功且该提交全绿、head 匹配时记为 `github_api`，否则降级为 `agent_claimed`。未使用 `--pr` 抓取、只声明 CI URL 时记为 `declared_unfetched`。
- `human_approved`：review URL 和 approved 状态，或明确的 `approved_by`。CLI 不能认证审批人身份，仍属调用方声明。

这四个级别描述证据强度，不等于授权。要把证据用于满足 Goal，还必须通过仓库外受保护信任锚的签名校验；否则一律视为本地声明。

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
