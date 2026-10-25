# 工作流与 CLI 操作

CLI 运行在 Python 3.11 及以上，不需要运行时依赖。在分发目录用 `python3 -m project_memory CMD`；在已初始化的仓库里用 `PYTHONPATH=.project-memory/tooling python3 -m project_memory CMD`。

## 默认没有破坏性操作

所有命令要么只读并输出报告，要么创建新文件。`graph --output` 和报告类命令的 `--output` 会覆盖指定的本地报告位置；这些报告是生成产物，不是事实来源。

没有命令会合并、提交、推送、更新 GitHub Issue、批准 ADR 或修改 Ruleset。

## 初始化

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

## 交接

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

## 完成检查

```bash
python3 -m project_memory finish --repo . --issue-file issue.json \
  --pr-file pr.json --test-evidence 'CI https://...' \
  --docs-impact updated --reviewed-by 'reviewer; 证据在 PR review'
```

支持 `--docs-impact not-applicable --docs-justification '...至少 12 个字符...'`。

`finish` 不执行测试，不独立验证人工声明，也不关闭 Issue。有实时访问时优先用 `--issue 325 --pr 342 --slug ORG/REPO`。即使建议是 ready，也仍然从属于 GitHub 审查和分支保护。

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

1. 创建 Issue，写清负责人、验收标准和相关 ADR。
2. 用 `start` 取当前 SHA 和可追溯的上下文。
3. Agent 在独立分支或工作树上开发，PR 关联 Issue。
4. 换工具或换人之前写 `handoff`。
5. 走 PR 的 CI 和人工审查。重要 ADR 变更单独提一个受审查的 PR。
6. 用 `finish` 检查证据，不自动关闭。
7. 合并后和每周复核时用 `audit` 检查知识漂移。
8. 任何发现都转成 Issue，不要未经审查直接重写 canonical 文档。
