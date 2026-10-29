# Project Memory 技术设计

## 一、目标与不做什么

目标：在 GitHub 上有多人、多个模型、多个 Agent 协作时，把目标、成功标准、执行记录、独立验证、缺陷、任务、决策、当前知识和执行证据关联起来，让上下文生成、交接、验证和知识对账可以重复执行。工具要能在不连 GitHub 的本地仓库运行，并且始终能说清哪份内容是权威。

不做什么：不替代 GitHub Issues/Projects，不调度模型，不自动审批，不自动发布生产，不保证 LLM 的语义判断正确，不构建多租户服务端，不做 GitHub Projects 双向同步，也不把 Agent 当安全边界。当前所有 GitHub 接口都是只读的。

## 二、逻辑架构

```text
开发者 / Claude Code / Codex / Cursor / Qoder
                   |
            project-memory Skill
                   | 按意图分派 workflow
             Python CLI (stdlib)
           /       |         \
GitHub REST (只读)  Git/worktree   doc_roots + ADR + 快照
           \       |         /
  goal / run / verify / reconcile / context / handoff / finish / audit
                         |
                  派生图与检索
                         |
                  JSON 证据报告
                         |
           GitHub PR + 人/CODEOWNER 审查
```

权威来源：Git commit 是代码变更，PR 是审查和合并记录，Issues/Projects 或本地任务文件是任务状态，`.project-memory/config.json` 里声明的 `doc_roots` 是当前规范，accepted ADR 是人工批准的设计理由。Goal 的成功标准描述意图，Agent Run 记录执行事实，Verification 记录独立检查结果；三者都不是 canonical 文档，也不能替代 Git 和 PR。

`mirror_roots` 只是只读副本，`legacy_roots` 只是历史证据，两者都不是权威。`mirror_policy: frozen` 表示人已经接受镜像永久只读：分歧以 medium 继续报告，仍然可见，但不允许把镜像内容复制回 canonical。

Context Package、Handoff、Audit、Graph、Search results 和 Reconciliation 都是派生或协作数据，可以重建或重新生成，不能直接变成新的正式事实。

## 三、目录结构

```text
project-memory-mvp/
├── project_memory/
│   ├── cli.py              # 命令入口
│   ├── common.py           # 受限 frontmatter 与原子写入
│   ├── gh.py               # GitHub 只读 REST 适配
│   ├── knowledge.py        # ADR 草案与一致性审计
│   ├── graph.py            # 证据图与检索
│   ├── workflows.py        # context、handoff、完成门禁
│   ├── coordination.py     # Goal、Run、验证、缺陷、对账
│   └── bootstrap.py        # 非破坏性初始化与工具同步
├── skill/project-memory/
│   ├── SKILL.md
│   ├── references/         # 治理、契约、工作流
│   ├── scripts/pm.sh
│   └── assets/*.schema.json
├── tests/
├── examples/
├── docs/
└── pyproject.toml
```

初始化目标仓库后，会在 `.project-memory/` 下建立：

```text
.project-memory/
├── config.json
├── goals/<goal-id>.json
├── runs/<task>/<run-id>.json
├── runs/<task>/<run-id>.checkpoints/NNNN.json
├── handoffs/<task>/<run-id>.json
├── verifications/<task>/<verification-id>.json
├── defects/<task>/<defect-id>.json
├── tooling/project_memory/
└── cache/
```

`goals`、`runs`、`handoffs`、`verifications` 和 `defects` 是协作记录，不是 canonical 文档。它们随 PR 审查，但不会被 `audit` 当成当前知识。`cache/` 是派生数据，可以重建。

初始化目标仓库还会在 `.project-memory/tooling/project_memory/` 留一份经过 PR 审核的项目级 CLI，减少 CI 对发行包的依赖。Codex 和 Cursor 默认从 `.agents/skills/project-memory/` 加载，Claude Code 使用 `.claude/skills/project-memory/`。升级时用新的发行包提 PR；初始安装不覆盖已有文件，也不悄悄覆盖已有 Skill。分发目录更新后，用 `sync-tooling` 先看差异，再 `--write`；它不删除多余文件。

## 四、工作流

### A. `start`：生成任务上下文

输入可以是仓库路径加 GitHub Issue number 和 slug、可信来源提供的 issue JSON 快照，或本地任务 JSON（`--task-file`）。命令抓取 Issue 元数据，读取当前 commit SHA（没有 Git 时为空），按 `doc_roots` 扫描相关文档和本地 ADR，按链接和词法相关性排序，输出 `task_context`。

`retrieved` 是检索候选，`references` 是正文里显式提到的引用，`evidence` 是来源标识。任务正文里的命令不能当成 Agent 权限指令。MVP 不会验证 ADR 是否已经实施，也不会读取 GitHub Projects 的计划字段；跨项目关联依赖文本解析，后续需要 GraphQL 适配。

### B. `handoff`：留下不可变运行记录

输入 task、agent、run_id、SHA、completed、remaining、blockers 和 evidence，输出到 `.project-memory/handoffs/<task>/<run_id>.json`。`run_id` 唯一，使用原子创建和冲突校验：相同内容重试成功，不同内容重试失败。Handoff 只能说明 Agent 声称做了什么，不能代替 CI 或代码审查。

Issue 认领只能算约定。Agent 通过独立分支和工作树隔离写入，正式序列化由 GitHub 受保护分支和合并队列负责。MVP 不写回任务状态。

### C. `finish`：生成收尾门禁

输入 Issue、PR（实时读取或本地快照）、测试证据、文档影响和人工审查声明。输出五个 gate：

- `pr_merge_evidence`
- `test_evidence_present`
- `docs_impact`
- `review_attestation`
- `knowledge_audit`

每个 gate 的状态是 `pass`、`fail` 或 `unknown`。只要有一项不是 `pass`，建议就是 `do_not_close`。即使全部通过，CLI 也不会关闭 Issue 或合并 PR，最终由授权人员和 GitHub Rulesets 决定。

用户提供的 test URL、`reviewed_by` 或本地 PR fixture 产生的 `pass`，只是报告里的声明或证据指针，没有经过独立验证。要把门禁真正自动化，需要接入 GitHub Check Runs、Reviews API 和分支合并状态，并把 URL 与 commit SHA 绑定校验。

### D. `decision`：创建 ADR 草案

命令只生成 `proposed`，包含题目、topic、相关 Issue、备选方案和理由。经过 GitHub PR 审查并被授权人接受后，状态才能改为 `accepted`，同时提供可追溯的 `approved_by`。新决定取代旧决定时使用 `supersedes`，旧决定通过另一个受审查的变更标记为 `superseded`。接受 ADR 不等于功能已经上线。

### E. `audit`：检查知识漂移

确定性检查包括：frontmatter 格式、重复 ID、非法状态、accepted ADR 缺少审批来源、`supersedes` 指向不存在的对象、文档断链。

启发式检查包括：同一 topic 有多条 accepted ADR、旧 accepted ADR 没有和新的取代关系对账、当前文档引用了已被取代的 ADR，以及有本地 PR 快照时，已合并 PR 缺少 Issue 链接或代码变更可能漏掉文档更新。

每个 finding 都带 `severity`、`code`、`location` 和说明。这些检查不判断自然语言内容的真假；语义冲突需要提交待确认记录，由人处理。

`--scope current` 只审计 canonical 中状态为 `current`、`draft`、`in_flight`、`unclassified` 的文档，以及全部 ADR；mirror、legacy、evidence、historical、superseded 和 archived 不在范围内。它是 CI 门禁。默认的全量审计覆盖所有材料，用于每周复核。围栏代码块里的示例链接不会被当作文档链接。

配置 `entry_doc` 后，两种范围都会检查入口文档：必须存在、属于 canonical、显式声明 `status: "current"`。缺失、非 canonical 或非 current 报 high；没有 `last_verified_at` 报 low；超过 `max_verified_age_days`（默认 90 天）时，入口报 medium，其他 current 文档报 low。审计只报告年龄，不改写文件，也不提升状态。

### F. `init`：安全初始化

`full` 模式创建缺失的 INDEX、CURRENT_STATE、架构占位、ADR README、GitHub Issue/PR 模板、CODEOWNERS 示例、CI 工作流、项目配置，以及 Skill 和 CLI 副本。CURRENT_STATE 是六段式人工入口模板，包含现状、主线、可信度、未决、去向和接手自检，配置里的 `entry_doc` 会指向它。模板不写 `last_verified_at`，填写的人核对之后自己补。

`overlay` 模式只写配置、ADR README、模板和 CLI 副本，用于已有 `doc/` 布局的工作区，不会新建一棵竞争的 `docs/`。它不生成入口文档，所以报告的手工动作里会明确提示补建并设置 `entry_doc`。

所有写入都是 no-clobber。`init` 不写 GitHub Ruleset，不 commit，不 push，不覆盖已有文件。真正生效仍需要 CODEOWNERS、必需审查和 Actions 权限设置。

分发目录的 Skill 或 CLI 更新后，用 `sync-tooling` 对比 `added`、`changed`、`extra` 和 `unchanged`。默认只报告；`--write` 用原子替换更新已跟踪文件，不删除 `extra`，也不覆盖已安装的 `.agents`/`.claude` Skill 副本。Skill 和 CLI 变更属于受保护变更。

### G. `graph` 和 `search`：关系与检索

Graph 节点包括 `DOC:<path>`、`ADR-0001`、`ISSUE:<n>`、`PR:<n>`，边是 `references` 和 `supersedes`。输入来自配置的 doc/mirror/legacy 根，以及 `.project-memory/issues`、`.project-memory/prs` 下的本地快照；这两个快照目录默认被 `.gitignore` 排除，避免未经审查就把私有任务内容提交进仓库。`graph.json` 是可重建索引。

节点带 `authority` 和 `status`。默认检索排除 legacy、mirror 和已归档状态；`evidence` 文档仍可能出现，需要按 `status` 判断。没有找到的边放在 `unresolved`，不代表外部对象一定不存在。跨仓库 URI 和 GraphQL/Project 关系留到后续版本。

检索默认按拉丁词和中文双字做词法排序。`semantic` 模式需要用户安装依赖并显式传入本地模型目录，调用 SentenceTransformer 生成嵌入，再对分段文本计算余弦相似度。MVP 没有持久向量库，也不会下载模型。结果返回路径、片段和分数，供人或 Agent 再核对。

### H. `new-doc`：固定格式文档脚手架

输入 ID、标题、`kind`（`canonical` 或 `evidence`）、状态、owner、canonical 根内路径和可选 Issue，输出 `document_draft`。

`canonical` 只能从 `draft` 或 `in_flight` 开始，`evidence` 只能从 `evidence` 开始。命令拒绝直接创建 `current`、重复 ID、已存在路径、ADR 目录、mirror/legacy 根，以及 canonical 根之外的路径。它只生成固定 frontmatter 和章节骨架，不填结论，不验证证据，也不提升状态。规则见 `skill/project-memory/references/document-authoring.md`。

### I. `goal`：目标与成功标准

Goal 记录 `id`、标题、背景、预期结果、负责人、约束、关联 Issue/ADR/PR 和成功标准。标准至少一条，且至少一条必达；每条标准有独立 ID、可核验陈述和证据数组。

创建默认 `proposed`。`approved` 和 `achieved` 必须由授权人提供 `approved_by`；`blocked` 和 `cancelled` 必须写原因。`achieved` 前自动评估，必达标准未满足时拒绝。已批准标准只能由授权人通过可审查变更修改。

证据类型是 `verification`、`commit`、`test`、`manual`。`test` 要求本地日志存在且退出码为 0，但只算 `executed_not_matched`；`manual` 要求 `approved_by`，但只是未核验的批准声明；`commit` 要求完整 SHA 在当前历史中，只算 artifact；`verification` 要求 pass、未 stale、绑定被验证执行的当前 head，并且必须带受保护信任锚的分离签名，否则一律作为 `untrusted` 拒绝。

`goal evaluate` 只检查证据存在性和绑定关系，不判断证据在语义上是否支持标准，也不因为 Issue 关闭而判定达成。

### J. `run`：可恢复的 Agent 执行

Agent Run 记录 Goal、任务、Agent、模型 provider/id、工具、会话 ID、base/head SHA、分支、授权范围、角色和状态。角色是 `executor` 或 `verifier`。独立验证必须使用另一个 verifier run，且验证者的 agent/model/session 至少一项与被验证执行不同。模型身份只保留 provider 和 id，不保存模型密钥。

状态机：`queued -> running -> submitted -> verified`，另有 `paused`、`failed`、`cancelled`、`superseded`。`run finish` 生成 1.2 handoff，包含模型、head、提交、变更文件、测试、文档变化、未决问题和下一步，把执行置为 `submitted`、`failed` 或 `cancelled`。

检查点是递增编号的不可变文件，包含 head、已完成、剩余、阻塞和证据。它与上一个检查点完全相同会幂等返回；执行结束后拒绝写入。

`run resume` 汇总最新检查点、handoff、验证和缺陷，并检查 base 是否为当前 HEAD 的祖先、head 是否变化、是否缺 handoff、是否有多个活跃 executor。默认只选 executor；没有 handoff 的活跃执行可以用最近检查点恢复。状态是 `resume_ready`、`verified`、`no_run`、`needs_handoff`、`needs_human` 或 `stale_base`。执行标为 verified 但提交漂移时返回 `needs_human`。恢复包不证明前任 Agent 的声明为真。

并发控制是乐观的：Run、Goal 和 Defect 用 revision 检查，Handoff 和验证记录用原子 no-clobber。没有分布式锁；GitHub 任务认领只是约定。

### K. `verify` 与 `defect`：执行之后的独立检查

验证记录独立于执行，包含验证 ID、目标 run、验证者 run、验证者模型/工具/会话、目标 head、当前 head、标准、证据级别、测试/CI/审查结果、发现、结论和可信级别。

证据级别从低到高是 `agent_claimed`、`locally_observed`、`externally_verified`、`human_approved`。`agent_claimed` 不能产生 pass。本地观察必须绑定 `test-run` 生成的执行收据（命令、整数退出码、日志哈希和快照摘要可重算），手写日志不再算执行证据；外部验证需要 CI URL 和 passed；人工批准需要 review URL 和 approved。CLI 离线时不抓取 CI 或 review，后两者标为 `declared_unfetched`，仍属调用方声明。

验证记录把四层事实分开：

1. **内容完整性**：收据、日志和快照摘要可以重算，能发现后续修改。
2. **执行事实**：收据记录了该命令在该快照内以该退出码执行过。
3. **来源与权威**：本地 CLI 写出的 JSON 没有分离签名，只能算调用方声明。
4. **标准的达成依据**：只有受保护信任锚签名的记录才能进入 `goal evidence`。

因此本地记录最多是 `MANUAL_REVIEW_REQUIRED`，`verified` 恒为 `false`；`goal evidence` 会拒绝自报 `status: VERIFIED` 的记录。信任锚通过仓库外的 `PROJECT_MEMORY_TRUST_ANCHOR` 配置，用 OpenSSL 验证 detached signature；未配置时一律 fail-closed。

`test-run` 必须显式选择模式，默认不执行（无 `--trusted`/`--allow-local-untrusted` 即 exit 3）。`local`（`--allow-local-untrusted`）是普通子进程，收据标 `local_untrusted`，只用于本地开发。`trusted`（`--trusted`）只在 WSL2 可用时进入 user/mount/PID/network namespace：把快照复制到 tmpfs，屏蔽 Windows 盘符、宿主 home、`/root`、`/var`、`/tmp`、`/run` 和 `/etc/ssh`，挂载新的 `/proc`，用 `env -i` allowlist 执行，并在沙箱内写 attestation。预检失败返回 `BLOCKED`，不回退普通子进程；attestation 在仓库内且无外部签名，所以只代表隔离事实，不代表来源可信。

pass 条件还要求没有 high 级发现、目标 head 未变化、验证记录属于同一 Goal。验证绑定 `target_head_sha`；代码变化后旧验证不自动有效。pass 把目标执行置为 `verified`，fail 置为 `failed`。

每条 finding 生成一个缺陷，记录任务、验证来源、代码位置、复现、严重度和状态。缺陷状态是 `open`、`fixed`、`verified`、`wontfix`、`closed`。`fixed` 必须绑定存在的完整提交 SHA；`verified` 由复验的 `--resolves-defect` 产生，不能直接更新；修复提交必须在被验证提交的历史中。

### L. `reconcile`：知识对账

`reconcile` 关联 Goal、Issue 引用、Agent Run、验证、缺陷、ADR 和当前文档，输出带 severity 的 JSON 或 Markdown 报告。检查包括：已达成的 Goal 仍有未满足标准、有 Goal 没有执行、高等级缺陷、pass 没有验证记录、孤立执行、未验证提交、验证记录缺失、handoff 缺失、base 不是祖先、多个活跃 executor、旧提交验证、Agent 自报 pass、缺陷标为 verified 却没有有效验证记录、修复提交不在历史中、文档审计发现、accepted ADR 未关联。verifier run 不参与未验证提交和并发判断。

对账只报告，不自动改 canonical 文档、不合并、不关闭任务。报告是可重建的派生数据，不是第二份权威存储。

## 五、数据与引用契约

- 结构化输出都带 `schema_version` 和 `kind`。新记录使用 `1.2`；通用 handoff 兼容 `1.1`，完成报告仍是 `1.1` 并增加 `evidence_levels`。下游拒绝未知主版本，忽略额外字段。
- JSON Schema（Draft 2020-12）放在 `skill/project-memory/assets/`，共 19 份：Task Context、Handoff、Completion、Audit、Graph、Config、Init、ADR proposal/metadata、Search results、Issue/PR snapshot、Document draft，以及 Goal、Agent Run、Run Checkpoint、Verification Record、Defect、Knowledge Reconciliation。当前只验证 JSON 能解析，还没有接入 Draft 2020-12 实例校验器。
- Goal 记录成功标准和证据，状态为 `proposed`、`approved`、`active`、`evaluating`、`achieved`、`blocked`、`cancelled`；`approved` 和 `achieved` 需要 `approved_by`。
- Agent Run 记录模型 provider/id、工具、会话、base/head SHA、分支、授权范围、角色和状态。检查点不可变；handoff 1.2 增加模型、head、提交、测试和下一步。
- Verification Record 独立于执行，绑定 `target_head_sha`，证据级别为 `agent_claimed`、`locally_observed`、`externally_verified`、`human_approved`。Defect 记录位置、复现、严重度和修复提交。
- ADR frontmatter 使用 `id`、`kind`、`title`、`topic`、`status`、`owner`、`updated_at`、`related_issues`、`supersedes`、`approved_by` 等键。脚本只支持受限 YAML 子集。
- 文档 frontmatter 可以带 `last_verified_at`，表示人重新核对结论的日期，与只记录编辑的 `updated_at` 不同。`entry_doc` 指向唯一人工入口，`max_verified_age_days` 控制过期阈值。
- Git SHA 是工作基准，40 位，可以为空。任务 ID 可以是数字 Issue，也可以是稳定字符串。`run_id` 唯一，但不是业务事务 ID；复验要生成新的验证 ID。
- 搜索结果必须显示原文件路径。链接边只证明存在引用，不证明实现一致或结论正确。
- 1.1 数据保持可读，不批量重写。下一次 `run finish` 会生成 1.2 handoff；批量迁移需要受审查的一次性脚本。

## 六、权限模型与失败处理

| 操作 | Planner Agent | Dev Agent | Review Agent | 授权人 |
|---|---|---|---|---|
| 读取仓库和 Issue | 允许 | 允许 | 允许 | 允许 |
| 修改任务分支 | 默认不允许 | 在受控范围内允许 | 默认不允许 | 按仓库策略 |
| 登记 Agent Run | 禁止 | 允许（executor） | 允许（verifier） | 允许 |
| 独立验证 | 禁止 | 禁止自验 | 允许（`role=verifier`，且 agent/model/session 至少一项不同） | 允许 |
| 生成 ADR 草案 | 允许 | 允许 | 允许 | 允许 |
| 批准 Goal 达成、审批 ADR、合并 PR | 禁止 | 禁止 | 禁止 | 受 GitHub Ruleset 约束 |
| 生产部署 | 禁止 | 禁止 | 禁止 | 受环境审批控制 |

这些是治理目标，必须靠 GitHub 权限、CODEOWNERS、Rulesets、CI 和独立的 Agent 凭据来执行。单独的 Skill 指令、任务标签或本地脚本挡不住越权。

失败时的处理方式：

- 缺令牌或没有 Issue：列出需要的参数并停止。
- Git SHA 无效、不是完整 40 位、或不在当前历史中：停止。
- 同一个 run-id 的交接内容变了：报错，换新的 run ID。
- base 不是当前 HEAD 的祖先：报 `stale_base`，请人对齐分支。
- 同一任务有多个活跃 executor：报 `needs_human`，不自行覆盖；verifier 不计入。
- 验证时 HEAD 已变化：拒绝 pass，要求重新对齐和复验。
- Agent 自报证据：记录为 `agent_claimed`，不能 pass。
- 有 high 级发现：拒绝 pass，生成缺陷。
- frontmatter 不在支持的 YAML 子集内：按高风险报告。
- 语义检索模型不可用：明确报错，不悄悄退回并声称是语义结果。
- 证据缺失：记为 `unknown`，不假设成功。

## 七、后续生产化门槛

1. 用 GitHub App 做细粒度认证，读写服务隔离。
2. 用 Checks 和 Reviews API 核验 CI、审查身份和目标 SHA，替代口头声明。
3. 接入 GitHub Projects GraphQL 和带条件更新的任务认领。
4. 文档索引按 commit SHA 做增量缓存；检索使用私有本地 embedding 或 reranker，并带上证据级别和失效标记。
5. 更严格的 schema validator、循环引用检测、frontmatter 解析和迁移工具。
6. 多仓库知识 URI、审计日志，以及防止敏感文件进入检索索引的规则。
7. 多模型编排只保留接口设计：客户端不支持自动切换时，由人生成 handoff 并在新会话继续；不要做后台调度器。自动编排需要显式的模型能力探测、授权和审计轨迹。
