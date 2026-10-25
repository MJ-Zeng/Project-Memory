# Project Memory 技术设计

## 一、目标与不做什么

目标：在 GitHub 上有多人、多个模型、多个 Agent 协作时，把任务、决策、当前知识和执行证据关联起来，让上下文生成、交接和知识对账可以重复执行。工具要能在不连 GitHub 的本地仓库运行，并且始终能说清哪份内容是权威。

不做什么：不替代 GitHub Issues/Projects，不自动审批，不自动发布生产，不保证 LLM 的语义判断正确，不构建多租户服务端，不做 GitHub Projects 双向同步，也不把 Agent 当安全边界。当前所有 GitHub 接口都是只读的。

## 二、逻辑架构

```text
开发者 / Claude Code / Codex / Cursor
                   |
            project-memory Skill
                   | 按意图分派 workflow
             Python CLI (stdlib)
           /       |         \
GitHub REST (只读)  Git/worktree   doc_roots + ADR + 快照
           \       |         /
            context / handoff / finish / audit
                         |
                  派生图与检索
                         |
                  JSON 证据报告
                         |
           GitHub PR + 人/CODEOWNER 审查
```

权威来源：Git commit 是代码变更，PR 是审查和合并记录，Issues/Projects 或本地任务文件是任务状态，`.project-memory/config.json` 里声明的 `doc_roots` 是当前规范，accepted ADR 是人工批准的设计理由。

`mirror_roots` 只是只读副本，`legacy_roots` 只是历史证据，两者都不是权威。`mirror_policy: frozen` 表示人已经接受镜像永久只读：分歧以 medium 继续报告，仍然可见，但不允许把镜像内容复制回 canonical。

Context Package、Handoff、Audit、Graph 和 Search results 都是派生数据，可以重建，不能直接变成新的正式事实。

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
│   └── bootstrap.py        # 非破坏性初始化
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

初始化目标仓库后，会在 `.project-memory/tooling/project_memory/` 留一份经过 PR 审核的项目级 CLI，减少 CI 对发行包的依赖。Codex 和 Cursor 默认从 `.agents/skills/project-memory/` 加载，Claude Code 使用 `.claude/skills/project-memory/`。升级时用新的发行包提 PR；初始安装不覆盖已有文件，也不悄悄覆盖已有 Skill。

## 四、八个工作流

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

### G. `graph` 和 `search`：关系与检索

Graph 节点包括 `DOC:<path>`、`ADR-0001`、`ISSUE:<n>`、`PR:<n>`，边是 `references` 和 `supersedes`。输入来自配置的 doc/mirror/legacy 根，以及 `.project-memory/issues`、`.project-memory/prs` 下的本地快照；这两个快照目录默认被 `.gitignore` 排除，避免未经审查就把私有任务内容提交进仓库。`graph.json` 是可重建索引。

节点带 `authority` 和 `status`。默认检索排除 legacy、mirror 和已归档状态；`evidence` 文档仍可能出现，需要按 `status` 判断。没有找到的边放在 `unresolved`，不代表外部对象一定不存在。跨仓库 URI 和 GraphQL/Project 关系留到后续版本。

检索默认按拉丁词和中文双字做词法排序。`semantic` 模式需要用户安装依赖并显式传入本地模型目录，调用 SentenceTransformer 生成嵌入，再对分段文本计算余弦相似度。MVP 没有持久向量库，也不会下载模型。结果返回路径、片段和分数，供人或 Agent 再核对。

### H. `new-doc`：固定格式文档脚手架

输入 ID、标题、`kind`（`canonical` 或 `evidence`）、状态、owner、canonical 根内路径和可选 Issue，输出 `document_draft`。

`canonical` 只能从 `draft` 或 `in_flight` 开始，`evidence` 只能从 `evidence` 开始。命令拒绝直接创建 `current`、重复 ID、已存在路径、ADR 目录、mirror/legacy 根，以及 canonical 根之外的路径。它只生成固定 frontmatter 和章节骨架，不填结论，不验证证据，也不提升状态。规则见 `skill/project-memory/references/document-authoring.md`。

## 五、数据与引用契约

- 所有结构化输出都带 `schema_version: "1.1"` 和 `kind`。
- JSON Schema（Draft 2020-12）放在 `skill/project-memory/assets/`，共 13 份：Task Context、Handoff、Completion、Audit、Graph、Config、Init、ADR proposal/metadata、Search results、Issue/PR snapshot、Document draft。当前只验证 JSON 能解析，还没有接入 Draft 2020-12 实例校验器。
- ADR frontmatter 使用 `id`、`kind`、`title`、`topic`、`status`、`owner`、`updated_at`、`related_issues`、`supersedes`、`approved_by` 等键。脚本只支持受限 YAML 子集。
- 文档 frontmatter 可以带 `last_verified_at`，表示人重新核对结论的日期，与只记录编辑的 `updated_at` 不同。`entry_doc` 指向唯一人工入口，`max_verified_age_days` 控制过期阈值。
- Git SHA 是工作基准，40 位，可以为空。任务 ID 可以是数字 Issue，也可以是稳定字符串。`run_id` 唯一，但不是业务事务 ID。
- 搜索结果必须显示原文件路径。链接边只证明存在引用，不证明实现一致或结论正确。

## 六、权限模型与失败处理

| 操作 | Planner Agent | Dev Agent | Review Agent | 授权人 |
|---|---|---|---|---|
| 读取仓库和 Issue | 允许 | 允许 | 允许 | 允许 |
| 修改任务分支 | 默认不允许 | 在受控范围内允许 | 默认不允许 | 按仓库策略 |
| 生成 ADR 草案 | 允许 | 允许 | 允许 | 允许 |
| 审批 ADR、合并 PR | 禁止 | 禁止 | 禁止 | 受 GitHub Ruleset 约束 |
| 生产部署 | 禁止 | 禁止 | 禁止 | 受环境审批控制 |

这些是治理目标，必须靠 GitHub 权限、CODEOWNERS、Rulesets、CI 和独立的 Agent 凭据来执行。单独的 Skill 指令、任务标签或本地脚本挡不住越权。

失败时的处理方式：

- 缺令牌或没有 Issue：列出需要的参数并停止。
- Git SHA 无效：停止。
- 同一个 run-id 的交接内容变了：报错。
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
