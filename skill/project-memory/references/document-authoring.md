# 文档撰写规则

创建或大幅修改 canonical 文档之前，先读这一篇。目标是每个主题只有一份权威文档，状态明确，证据可追溯。

## 写入门禁

1. **先搜索。** 运行 `search`；关系复杂时再跑 `graph`。已有 canonical 文档覆盖同一主题时，修改它，不要另写一份平行摘要。
2. **分清内容类型。** 当前知识写 canonical 文档，设计选择写 ADR，原始调查写 evidence 文档。过时材料做标记，不删除。
3. **使用配置里的根目录。** 读 `.project-memory/config.json`。不要写进 `mirror_roots` 或 `legacy_roots`，也不要在已有 `doc/` 旁边新建 `docs/`。
4. **附上证据。** 每条事实都要能指到文件、提交、日志或可复现命令。没解决的点明确标出来。“代码看起来正确”不算测试通过的证据。
5. **不要声称自己没有的权限。** 讨论不是批准，Agent 的报告不是人工审查。没有可核实证据时，不要写 `accepted`、`approved_by`、测试成功或部署状态。

## 内容去哪里、用什么状态

| 内容 | 位置 | 初始状态 | 后续 |
|---|---|---|---|
| 当前结论或状态 | canonical 根下的普通文档 | `draft` 或 `in_flight` | 人工审查后改为 `current` |
| 设计或政策决策 | `adr_dir`，通过 `decision` 创建 | `proposed` | `under-review`，再到 `accepted`，并填 `approved_by` |
| 调查、快照、日志摘要 | canonical 根下，`kind: evidence` | `evidence` | 不会自动变成 current |
| 被取代的结论 | 现有文档 | `superseded` | 链接到新文档 |
| 不再代表现状的材料 | 现有文档 | `historical` | 写清原因和从什么时候开始 |

`new-doc` 不能创建 `current`，只接受两种组合：

- `kind: canonical` 配 `status: draft` 或 `in_flight`
- `kind: evidence` 配 `status: evidence`

## 固定格式

用 `assets/document.template.md` 作为骨架。frontmatter 字段：

```yaml
id: "DOC-TOPIC-001"
kind: "canonical"
title: "主题"
status: "draft"
owner: "human-owner"
updated_at: "YYYY-MM-DD"
related_issues: [325]
```

只支持文档里写明的 YAML 子集：一层 `key: scalar` 和 JSON 兼容的行内数组。字符串加引号，不要用嵌套 YAML。

需要人工核验的当前文档可以加 `last_verified_at`，格式为 `YYYY-MM-DD`。只有实际核对过结论之后才写这个日期；`updated_at` 不能代替它。

canonical 正文分四节：

- `## 结论`：当前主张，一段短文字。
- `## 证据`：按 L（本地运行）、S（服务器）、D（文档或提交）标注来源。
- `## 适用范围与未决`：边界、限制、仍需确认的问题。
- `## 变更记录`：日期、改动、证据。只追加，不改写历史。

evidence 文档使用 `## 记录`、`## 来源与采集方式`、`## 可复现性`、`## 变更记录`。

## 生成文档骨架

```bash
python3 -m project_memory new-doc --repo . \
  --id DOC-CACHE-001 --title '缓存口径' \
  --kind canonical --status draft \
  --owner backend-team --path docs/topics/cache.md --issue 325
```

```bash
python3 -m project_memory new-doc --repo . \
  --id EVID-CACHE-2026-10 --title '缓存基准原始记录' \
  --kind evidence --status evidence \
  --owner backend-team --path docs/evidence/cache-2026-10.md
```

命令使用 no-clobber：路径已存在或文档 ID 已用过都会被拒绝。它只生成骨架，不填结论，不验证证据，也不提升状态。

## 状态流转

- `draft` / `in_flight` → `current`：人工审查内容和证据之后。
- `current` → `superseded`：已经有受审查的替代文档；链接过去，保留旧文档。
- `current` → `historical`：结论不再代表现状；写清原因。
- `evidence` → `archived`：保留备查，不要悄悄删除。
- ADR 的状态单独管理：CLI 只创建 `proposed`；只有受审查的变更才能改成 `accepted` 或 `superseded`。

## 审查清单

- [ ] 这个主题还没有被 canonical 文档覆盖。
- [ ] 路径在配置的 canonical 根下。
- [ ] ID 唯一，状态和内容类型匹配。
- [ ] 每条主张都有证据，或者明确标为未验证。
- [ ] 链接能打开；命令示例放在围栏代码块里，避免被审计当成断链。
- [ ] 变更记录写了日期和证据来源。
- [ ] 没有修改 mirror、legacy 或无关的业务文件。

## 为什么还没有做成强制门禁

审计已经会拒绝重复 ID，也会报告断链。要求所有历史文档立刻补齐 frontmatter，会产生大量误报。现在先用 `new-doc` 约束新文件；等存量文档迁移之后，再考虑严格的前置校验。
