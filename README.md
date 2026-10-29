# Project Memory：让多个 Agent 共用一套仓库记忆

这是一个本地优先的 Agent Skill 和 Python CLI，用来处理多人和多个 Agent 在同一个 Git 仓库里协作时的记忆问题。它把目标、执行记录、独立验证、缺陷、任务背景、交接状态、设计决策、文档现状和审计结果写成仓库里的文件，跟着代码一起提交和评审。

它不负责审批、合并、关闭 Issue，也不判断文档里的结论是否正确。目标达成、ADR 接受和生产变更仍由人和 GitHub 规则决定。

## 快速开始

需要 Python 3.11 或更高版本。默认功能不依赖第三方库。

```bash
# 在分发目录运行测试
cd project-memory-mvp
python3 -m unittest discover -s tests -v

# 初始化一个已经建好的 Git 仓库；只补缺失文件，不覆盖
python3 -m project_memory init --repo /path/to/git/repo --install both
cd /path/to/git/repo

# 初始化后的仓库自带 CLI，CI 和离线环境都能用
PYTHONPATH=.project-memory/tooling python3 -m project_memory audit --repo . --scope current --fail-on high
PYTHONPATH=.project-memory/tooling python3 -m project_memory search --repo . '项目 状态'
```

也可以从分发目录安装：`python3 -m pip install -e .`，然后直接运行 `project-memory --help`。

Windows 上用 Git Bash 时，先设置 `PYTHONUTF8=1`，并把 `python3` 换成实际可用的解释器路径。

### 测试期 openssl 要求

openssl 只在测试期用于生成测试密钥和签名，**不是运行时依赖**；CLI 的验签在进程内完成。缺少 openssl 时，B2/B3/B4 签名测试默认 `SkipTest`，本地仍可跑其余测试。发布和 CI **必须**设置开关，让缺 openssl 直接失败，避免把 skip 当成通过：

```bash
# 发布/CI：缺 openssl 时签名测试 failed/error，不再 skip
PROJECT_MEMORY_REQUIRE_OPENSSL=1 python3 -m pytest -q

# 本地默认：缺 openssl 时跳过签名测试
python3 -m pytest -q
```

开关取值为 `1`、`true`、`yes`（大小写不敏感）。详见 `docs/OPERATIONS.zh-CN.md`。

## 目标、执行与独立验证

目标用可衡量的成功标准描述，不把 Issue 关闭当成完成：

```bash
# Goal 默认 proposed；approved/achieved 必须由授权人提供 --approved-by
python3 -m project_memory goal create --repo . --id G-AUTH \
  --title '修复认证绕过' --outcome '未授权请求被拒绝' --owner backend-team \
  --criterion '无令牌请求返回 401'

# 每次执行登记真实模型、会话、分支和基准 SHA
python3 -m project_memory run start --repo . --goal G-AUTH --task 325 \
  --run-id run-dev-1 --agent qoder --model-provider qoder-cn --model-id dfmodel \
  --role executor --base-sha <40位SHA>

# 结束时生成 1.2 handoff；换模型或换会话时用新的 run ID
python3 -m project_memory run finish --repo . --task 325 --run-id run-dev-1 \
  --completed '拒绝无令牌请求' --remaining '独立验证' \
  --test-command 'python -m unittest' --test-exit 0 --test-log tests.log
```

验证必须由另一个执行记录完成，并登记为 `role=verifier`；验证者的 agent/model/session 至少一项要不同，不能自验：

```bash
python3 -m project_memory run start --repo . --goal G-AUTH --task 325 \
  --run-id run-verify-1 --agent qoder --model-provider qoder-cn --model-id qfmodel \
  --role verifier --base-sha <40位SHA>

python3 -m project_memory test-run --repo . --agent qoder \
  --command 'python -m unittest' --trusted
# 输出 .project-memory/receipts/EXE-*.json

python3 -m project_memory verify --repo . \
  --target-run run-dev-1 --verifier-run run-verify-1 \
  --standard '认证与凭据审查' --verdict pass --evidence-level locally_observed \
  --test-receipt .project-memory/receipts/EXE-<id>.json \
  --expected-sha <被验证执行的head SHA>
```

`agent_claimed` 不能产生 pass；`locally_observed` 需要 `test-run` 生成的执行收据，手写日志不再算执行证据；外部 CI 需要 URL 和 passed 状态，但 CLI 不联网抓取；人工批准需要 review URL 和 approved 状态，但 CLI 不认证审批人。验证绑定提交 SHA，代码变化后旧验证只作为历史证据，且不能跨 Goal 复用。

### 执行收据与隔离

`test-run` 把提交导出到不可变快照后执行命令，并记录退出码、日志哈希和快照摘要：

```bash
# 本地模式：普通子进程，没有操作系统隔离；收据标记为 local_untrusted
python3 -m project_memory test-run --repo . --command 'python -m unittest' --agent qoder

# 可信模式：WSL2 user/mount/PID/network namespace，预检失败即 BLOCKED，不回退
python3 -m project_memory test-run --repo . --command 'python3 -m unittest' \
  --agent qoder --trusted --timeout 900
```

可信模式会屏蔽 Windows 盘符、宿主 home、`/root`、`/var`、`/tmp` 和 `/etc/ssh` 等路径，只保留快照副本和显式环境变量 allowlist；命令在 `env -i` 下运行，无默认路由。收据的完整性可以重算，但收据本身位于仓库内、没有外部签名，所以只标为 `isolated_local_attestation`，不等于可信来源。

### 验证记录不会自证权威

本地 CLI 写出的验证记录最多是 `MANUAL_REVIEW_REQUIRED`，`verified` 恒为 `false`：JSON 里的 `status: VERIFIED` 或 `authority.status: trusted` 都不被接受。只有仓库外受保护信任锚对记录做分离签名，`goal evidence` 才可能把它当作达成依据：

```bash
export PROJECT_MEMORY_TRUST_ANCHOR=/path/outside/repo/trust-anchor.json
```

未配置信任锚时，`goal evaluate` 会停在 `needs_review` / `MANUAL_REVIEW_REQUIRED`，这是 fail-closed 的预期结果，不是可以绕过的错误。

把验证记录挂到目标标准，再评估和对账：

```bash
python3 -m project_memory goal evidence --repo . --id G-AUTH \
  --criterion C1 --kind verification --ref <verification-id>
python3 -m project_memory goal evaluate --repo . --id G-AUTH
python3 -m project_memory reconcile --repo . --fail-on high
```

`goal evaluate` 满足时退出 0，未满足时退出 2（没有可信授权来源时始终属于未满足）；`verify` 未通过时退出 2；`run resume` 在 `needs_handoff`、`needs_human` 或 `stale_base` 时退出 2。`reconcile` 只报告，不自动改 canonical 文档，也不关闭任务。

## 两种审计范围

`--scope current` 只审当前知识：canonical 根下状态为 `current`、`draft`、`in_flight`、`unclassified` 的文档，加上全部 ADR。镜像、历史、证据和已归档文档不参与。它适合放在合并门禁里。

默认的 `audit`（`--scope all`）会扫 canonical、镜像和历史目录，用来做周期复核。镜像和历史里的问题通常不在这次改动范围内，不应为了把数字清零去改旧文档。

## 入口文档与新鲜度

`.project-memory/config.json` 里的 `entry_doc` 指向唯一一篇给人看的入口文档。设置后，审计要求它存在、属于 canonical、显式声明 `status: "current"`。

`last_verified_at` 记录人最后一次核对结论的日期，和只记录编辑的 `updated_at` 分开。入口没有这个日期会报 low；超过 `max_verified_age_days`（默认 90 天）会报 medium。`init --profile full` 生成的 CURRENT_STATE 模板不写核验日期，填完内容并核对过事实之后，再由人补上。

`--profile overlay` 不生成入口文档。接入已有 `doc/` 或 `doc/new_doc` 布局时用它，接入后需要自己补一篇入口并设置 `entry_doc`。

## 已有文档布局

不要为了接入再建一棵 `docs/`。把真实目录声明出来：

```bash
python3 -m project_memory init --repo /path/to/workspace --install none --profile overlay \
  --docs-root doc/new_doc \
  --mirror-root pro2-mixed-training/docs/project-docs \
  --legacy-root doc/_legacy_2026-10-23
```

`overlay` 只创建 `.project-memory/` 和 ADR 目录说明，不改已有文档，也不碰业务代码。`mirror_roots` 只读；`legacy_roots` 默认不参与检索。`mirror_policy: frozen` 表示人已经接受镜像长期只读，镜像漂移会以 medium 继续报告，但仍然不允许把镜像内容复制回 canonical。

## 主要命令

| 用途 | 命令 | 是否写入 |
|---|---|---|
| 初始化与工具同步 | `init --repo . --install both`，`sync-tooling [--write]` | 只创建或更新缺失/已跟踪工具 |
| 定义与评估目标 | `goal create/show/list/evaluate/evidence/transition` | 写 `.project-memory/goals/` |
| 登记执行 | `run start/checkpoint/finish/show/list` | 写 `.project-memory/runs/` 和 handoff |
| 恢复执行 | `run resume --task 325 [--run-id run-1]` | 否 |
| 独立验证 | `verify --target-run A --verifier-run B --standard '...' --verdict pass --evidence-level locally_observed --test-receipt .project-memory/receipts/EXE-*.json ...` | 写验证和缺陷记录 |
| 快照执行 | `test-run --command '...' [--trusted] [--wsl-distro Ubuntu]` | 写快照、日志和收据 |
| 缺陷跟踪 | `defect list/show/update` | 更新缺陷状态 |
| 知识对账 | `reconcile [--format markdown] [--fail-on high]` | 否，或写指定报告 |
| 取任务上下文 | `start --issue 325 --slug ORG/REPO` 或 `start --task-file task.json` | 否 |
| 通用交接 | `handoff --task 325 --agent codex --run-id run-1 --remaining 'test' [--store PATH]` | 写本地不可变记录 |
| 完成检查 | `finish --issue 325 --pr 342 --slug ORG/REPO --docs-impact unknown` | 否 |
| 起草 ADR | `decision --title 'Cache' --topic cache --issue 325 --owner team --rationale '...'` | 创建 proposed ADR |
| 新建文档 | `new-doc --id DOC-CACHE-001 --title 'Cache' --kind canonical --status draft --owner team --path docs/topics/cache.md` | 创建固定格式草稿，不覆盖 |
| 文档审计 | `audit --scope current --fail-on high`（门禁）/ `audit`（全量复核） | 否 |
| 图谱与检索 | `graph`、`search 'query'`、`search --backend semantic --model /local/model 'query'` | 只写图谱缓存 |

本地或离线时，`start` 和 `finish` 可以用 `--issue-file`、`--pr-file` 替代 `--issue` / `--pr` 与 `--slug`。本地任务文件至少要有 `id`，以及 `title` 或 `body` 之一。任务 ID 可以是字符串；没有 Git 的工作区会返回 `base_sha: null`。

`new-doc` 不能直接创建 `current`：canonical 文档只能从 `draft` 或 `in_flight` 开始，证据文档只能从 `evidence` 开始。它会拒绝重复 ID、ADR 目录、镜像/历史根和配置文档根之外的路径。写入规则见 `skill/project-memory/references/document-authoring.md`。

## 凭据与权限

只有 `start` 和 `finish` 会访问 GitHub API，而且只调只读接口。凭据从环境变量 `GITHUB_TOKEN` 读取，不放在命令行参数里。建议使用 GitHub App 安装令牌，或限制到具体仓库的 fine-grained token。

`decision`、`goal`、`run`、`verify`、`test-run`、`defect`、`reconcile`、`handoff` 和 `init` 只写本地文件，不推送、不合并、不审批、不关闭 Issue、不部署。`--reviewed-by` 和 `--test-evidence` 是声明，不是独立验证；真正的权限仍由 GitHub 规则和 CI 决定。`test-run --trusted` 只在 WSL2 可用时执行，隔离预检失败会返回 BLOCKED，不会退回普通子进程。

## 语义检索的限制

默认 `search` 是词法匹配，英文按 token，中文按双字，不涉及模型。`--backend semantic` 需要额外安装 `sentence-transformers`，并提供一个本地的模型目录：

```bash
python3 -m pip install -e '.[semantic]'
```

代码不会自动下载模型，也不会把私有文档发给第三方嵌入服务。当前没有向量持久化、批处理服务或组织级知识图谱。

## 还需要人工完成的事

1. 检查生成的示例，补全入口文档、架构说明和 ADR 负责人。
2. 参考 `.github/CODEOWNERS.example` 配置真正的 CODEOWNERS，并在 GitHub 开启分支 Ruleset、必需审查和必需 CI。CLI 不能替你做这些。
3. 把 Actions 固定到审核过的完整 SHA。
4. 接入有权限的 GitHub 数据；如果要把完成门禁全自动化，还需要独立核对 CI 和 review 状态，不能只依赖快照声明。
5. Qoder CN 等客户端目前需要手动切换模型。CLI 只记录实际模型，不调度模型，也不保证跨模型接续。
6. Goal 的 `approved`/`achieved` 转换、ADR 接受、高风险变更和生产部署仍必须由授权人执行。
7. 把 Skill 和 CLI 的改动当作受保护变更来审查，不要在不信任的仓库工作流里跑带密钥的任务。

## 文档

- [教程与工作流](docs/TUTORIAL.zh-CN.md)：从临时仓库试跑到真实仓库接入，以及日常协作节奏。
- [技术设计](docs/ARCHITECTURE.zh-CN.md)：模块、目录模型、数据契约和后续门槛。
- [操作手册](docs/OPERATIONS.zh-CN.md)：接入步骤、文档写入、新人接手和上线检查。
- [验证记录](docs/TEST_REPORT.md)：跑过的测试、真实仓库结果和未验证项。
- [Skill 说明](skill/project-memory/SKILL.md) 与 `skill/project-memory/references/`：Agent 执行时读的规则和字段契约。

## 参考

- [Agent Skills specification](https://agentskills.io/specification)
- [Codex skill locations](https://learn.chatgpt.com/docs/customization/overview)
- [Claude Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Cursor Skills](https://cursor.com/docs/skills)
- [GitHub REST API](https://docs.github.com/en/rest)
- [GitHub Rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- [GitHub Actions pull_request_target 的安全用法](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)
