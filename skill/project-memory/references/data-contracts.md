# 数据契约与状态机

机器可读契约在 `assets/*.schema.json`，使用 JSON Schema 2020-12。所有生成的 JSON 都带 `schema_version: "1.1"`。下游必须拒绝不认识的主版本，可以忽略额外的可选字段。

## 来源与记录

| 记录 | 主要来源 | ID | 可变性 |
|---|---|---|---|
| 任务 | GitHub Issue / Project，或本地任务 JSON | `ISSUE:<number>` 或稳定的本地字符串 ID | 由授权的人或工具更新 |
| 实现 | GitHub PR、提交、CI | `PR:<number>` 和 commit SHA | 由 Git/PR 历史决定 |
| Canonical 文档 | 配置 `doc_roots` 下经过审查的文档 | `DOC:<repo path>`，另带 frontmatter `id` | 通过 PR 修改 |
| 镜像 | `mirror_roots` 下的只读副本 | `DOC:<repo path>`，authority 为 `mirror` | 不编辑，只报告分歧 |
| ADR | 经过审查的 `adr_dir` | `ADR-0001` | accepted 通过新 ADR 取代 |
| Handoff | `.project-memory/handoffs/<task>/<run>.json` 或 `--store` | `task + run_id` | 不可变，no-clobber |
| 知识图谱 | 从文档和快照派生 | 节点和边 ID | 可丢弃重建 |
| 上下文与报告 | 派生 JSON | task + base SHA（可为空） | 可丢弃重生成 |

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

## ADR 状态

`proposed -> under-review -> accepted -> superseded`；`proposed` 或 `under-review` 也可以进入 `rejected`。

CLI 只能创建 `proposed`。改成 `accepted` 需要可追溯到授权人批准的 `approved_by`。`accepted` 只表示设计获批，不表示已经实现或部署。

## Canonical 文档状态

状态包括 `draft`、`in_flight`、`current`、`historical`、`superseded`、`archived`、`evidence`、`unclassified`。

还没合并的文档 PR 是提案。`current` 表示作为文档被接受，不表示已经和运行环境核对过。文档、代码和决策之间的差异由审计来对账。

## 文档草稿

`new-doc` 创建一个 `document_draft` 记录和一个文件。允许的初始状态：`kind: canonical` 用 `draft` 或 `in_flight`；`kind: evidence` 用 `evidence`。`current` 永远不会被直接创建。

命令会拒绝重复 ID、已存在路径、ADR 目录、mirror/legacy 根，以及 `doc_roots` 之外的路径。它不填内容，不验证证据，也不提升状态。提升为 `current` 是受审查的变更；`superseded` 和 `historical` 是生命周期标记，不是新建文件。

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

`working_note -> candidate -> verified_evidence -> promoted_knowledge`。升级需要批准和来源。

Handoff 和快照默认是 `reported_unverified`。检索命中不能直接当权威，必须先核对来源状态。

## Gate 状态

`pass`、`fail`、`unknown`。**`unknown` 永远不等于 `pass`。**

完成报告只有在全部 gate 为 pass 时才能给出 ready，但它不是授权，也不证明事实已经核实。CLI 的 `--reviewed-by` 和 `--test-evidence` 是声明，不是实时独立的 CI 检查。更严格的生产环境需要接入经过验证的状态检查。

## Frontmatter 子集

Python 实现只支持受限 YAML：一层 `key: scalar` 和 JSON 兼容的行内数组。不支持嵌套 YAML、多行 YAML、锚点和别名。

`SKILL.md` 由 Agent 阅读，不会被解析成项目 canonical 文档。这个限制是为了避免引入运行时 YAML 依赖。后续升级应该使用真正的解析器和 schema 校验，不要靠猜。

## 图边语义

`references` 和 `supersedes` 是从文档和快照中抽取的显式链接。一条边只证明存在引用，不证明双方一致、已经实现或存在因果关系。

`unresolved` 表示被引用的对象不在本地索引里，不代表它在 GitHub 上一定不存在。
