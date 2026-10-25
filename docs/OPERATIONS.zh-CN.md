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
5. 让第二个 Agent 读同一任务的 `handoff`，不要复制完整聊天上下文。
6. 把 PR 的测试证据带进 `finish`，对照真实的 GitHub 审查状态看一眼。
7. 每次合并前跑 `audit --scope current --fail-on high`。每周再跑一次全量 `audit`，把历史、镜像和证据区的高价值发现转成 Issue，由人决定整改还是忽略。
8. 需要了解知识关系时运行 `graph` 和 `search`。索引不是新的事实来源。

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
PYTHONPATH=.project-memory/tooling python3 -m project_memory graph --repo .
```

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
| 单测 | 文档断链和冲突 | Finding 带精确位置和 code |
| 单测 | 中英混合检索 | 返回源路径、分数和原文片段 |
| 集成 | Git 快照前后变动 | Context 的 base SHA 反映最新提交 |
| 集成 | 同一任务两个 Agent | 不同 run-id 不互相覆盖 |
| 集成 | GitHub 无权限或 404 | 清晰失败，不凭空生成 |
| 安全 | Issue 提示注入 | 只当数据，不改变 Skill 权限 |
| 安全 | Actions fork PR | 不提权运行，不泄漏令牌 |
| 验收 | 十个真实任务 A/B | 减少交接遗漏、过期文档和找资料成本 |

## 已知限制

- 没有在实际 GitHub 仓库上在线运行过，因为没有提供仓库和 Token。
- 没有 GitHub Projects GraphQL 状态读写，也不自动更新 Issue/PR。
- 不自动判断所有自然语言矛盾，语义冲突要人工对账。
- `finish` 不独立请求 CI 或 Review API。人工声明和快照只能标成“报告里有这个字段”，不是独立验证。
- 语义嵌入依赖预装本地模型，自动下载和第三方 API 都被禁用。
- 大仓库的全文检索还需要索引缓存和文档分段优化。
- Windows 上硬链接不可用时，写入会退回到 `O_CREAT|O_EXCL`，no-clobber 语义保留，但没有测试断电恢复。
