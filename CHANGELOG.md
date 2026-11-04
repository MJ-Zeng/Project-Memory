# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的结构；版本号从 1.0.0 起表示本试点的首个发布门槛。历史以 Git 提交为准。

## [1.1.0] — 2026-11-04（已发布：Tag `v1.1.0`、GitHub Release 与 6 枚公开制品）

本版汇总自 `v1.0.0` 以来进入 `dev/v1.0` 的全部能力：签名审批质量门禁（S3）与发布制品来源证明（S4）。功能面为新增与加固，CLI 既有入口与数据格式向后兼容。

### 新增 — 审批与 CI 质量门禁（S3）

- B-7：CI 审批门禁加固，拒绝由 PR 自身控制的验证器（合并 `77052bf`，PR #50）。
- B-8：签名审批事件，审批身份绑定仓库外信任锚（合并 `c3dea2a`，PR #49）。
- B-9：从 GitHub API 复核 PR 的 CI 结果，作为外部证据而非本地自述（合并 `999713b`，PR #47；行为文档同步 `187f49d`，PR #48）。
- B-10：默认分支启用必需状态检查 `pytest` 与 `approval`，`strict=true`、`enforce_admins=true`；`approvals` 孤儿分支承载审批记录。

### 新增 — 发布制品与来源证明（S4）

- S4-1：绑定 commit 与 tree 的签名证据清单（合并 `40d3f1d`）。
- S4-2：信任锚生命周期（ADR-0008）与 `verify` 时的仓库身份复检（合并 `9aa6af4`，PR #54）。
- S4-3：`release` 工作流构建源码归档、sdist、wheel、`sha256sums.txt`、`BUILD-INFO.json` 与 build provenance attestation；不创建 tag、不发布 Release、不读取仓库 secret（合并 `cfdd848`，PR #55）。已在 GitHub-hosted runner 上真实干跑一次（run `41324143240`）。

### 变更 — CI、可移植性与测试

- 第三方 Action 固定到不可变提交 SHA（合并 `617cdd9`，PR #44）；合入 `dev/v1.0` 的 push 同样触发门禁（合并 `87600d7`，PR #45）。
- `verify` 的输入路径按 `--repo` 解析，不再依赖当前工作目录（合并 `8510919`）。
- 负对照强化：非空诱饵目录与 `findings-file` 覆盖（合并 `165fa55`、`9075012`）。
- 7 个 ADR 补齐元数据（合并 `1eaa3f4`）；文档与实现对齐并新增试点章程（合并 `81c5531`）。

### 已知边界与发布状态（核查日期 2026-11-04）

- 发布状态：`v1.1.0` 的 annotated tag、GitHub Release（id 433549523，`published_at 2026-11-04T05:37:01Z`）与 6 枚制品已发布并公开可下载；`v1.1.0` 与 `v1.0.0` 两个 tag 都未签名，`v1.0.0` 的 Release 仍没有资产。
- `v*` tag 推送触发的发布构建已实测一次：run `41763116854` 绑定 `4918b86`，产物与 attestation 随 Release 公开、可逐件匿名复算；来源证明不等于外部采信，也不证明那个提交被独立真人复核过。
- 跨主机制品字节不可复现：`git archive` 在 `core.autocrlf=true` 的 Windows 检出与 Linux CI 上逐文件行尾不同，以 CI 构建为权威。
- `release` 工作流仍引用一个 node20 时代的 `actions/upload-artifact` 固定 SHA。GitHub 已于 2026-09-23 移除 Node20，旧 pin 被强制跑在 Node24 上并每次留一条 warning annotation；实测没有兼容性故障，本项目据此决定不再重固定、也不再扩大 Actions 维护范围。
- `audit` 是本地防篡改检测与文档一致性提示，不构成对外可采信的审计留痕；`approved_by` 仍是 `claimed_unverified`。

## [1.0.0] — 2026-10-29

### 发布门槛（R1）

- Goal 的必达判据集合为空时 fail closed：`evaluate` 返回 `satisfied=false`、`evaluation_status=insufficient_evidence`、`no_required_criteria=true`；`goal show` 仍可读并给出同一问题标记；`transition --to achieved` 被拒绝并写入 `goal_achieved_unsatisfied` 审计。
- 测试期 openssl 开关：缺失 openssl 时默认仍可 skip；设置 `PROJECT_MEMORY_REQUIRE_OPENSSL=1`（`true`/`yes` 亦可）后签名测试直接失败，发布/CI 必须开启。
- 契约同步：`docs/ARCHITECTURE.zh-CN.md` §5 的 schema 计数与说明、`verification-record.schema.json` 的 `goal_criteria_sha256` 描述、新增 `audit-ledger.schema.json`。
- 新增 `fixtures/b5b/README.md` 与 `evidence/B5B/README.md`（混合行尾、NUL 日志、校验方法；不重写历史证据）。
- 版本号改为 `1.0.0`。`v1.0.0` tag 与 GitHub Release 由发布者在人类 GO 后创建。

### B0 — 可移植仓库身份（ADR-0001，合并 `a70ad19`）

- 执行收据/快照绑定仓库身份（规范化远端 + 根提交）而不是绝对路径；同一仓库的不同 clone 可互认。

### B1 — 进程内验签（ADR-0002，合并 `15f4b3c`）

- 签名验证不再通过 PATH 查找外部 openssl；验签在进程内完成，缺失信任锚时 fail closed。

### B2 — 执行来源与内容完整性分离（ADR-0003，合并 `5a5abdd`）

- 有效签名不能包装手写收据；收据需要受保护启动器生成的执行 attestation 或已签名人工例外；仅 `locally_observed` 保持不可升级为独立验证通过。

### B3 — 判据定义摘要（ADR-0004，合并 `1930fa5`）

- `goal_criteria_sha256` 绑定判据定义（`id`/`statement`/`required`），追加证据不再使已签名验证失效；旧摘要格式在判据不变时继续接受。

### B4 — 审计链与 Goal 状态可信度（ADR-0007，合并 `85bf6a0`）

- 执行审计改为 1.3 哈希链（`seq`/`prev_hash`/`entry_hash`），`audit verify` 从 genesis 重算。
- `achieved` 需要仓库外 anchor 签名的 checkpoint（`audit/head.json`）；Agent 无签名路径。
- `goal show`/`evaluate` 输出 `effective_status`/`status_trusted`/`status_problems`，raw `status` 只作声明。

### B5A / B5A.1 — CLI 启动隔离（ADR-0005，合并 `4ad3a3b`）

- 新增原生 OS 包装器（`bin/project-memory`、`bin/project-memory.cmd`）与绝对路径启动脚本，先以 `-I -P` 隔离解释器再导入受信包；移除 pip `module:function` console script。

### B5B — `test-run` 默认拒绝未隔离执行（ADR-0006，合并 `c49a436`）

- `test-run` 必须显式选择 `--allow-local-untrusted` 或 `--trusted`；无 flag 或双 flag 均 exit 3，不产生快照/收据、不执行命令。
- `--trusted` 失败（如 WSL2 不可用）返回 `BLOCKED`，不静默回退 local。

### H1 — pytest 收集范围（合并 `3ee7afe`）

- `pyproject.toml` 的 `testpaths=["tests"]`，避免把 `evidence/` 下历史探针当作测试收集。

### 已知边界

- **B5A 裸 `-m` 入口**：`python -m project_memory` 在 `sys.path` 已被同名包占据时不提供保护；受支持入口是原生包装器或 `python -I -P -m project_memory`。
- **B5B 库层默认**：默认拒绝在 CLI `test-run` 层；库函数 `execution.run_command` 仍默认本地执行并标记 `local_untrusted`，调用方需自行选择隔离。
- **openssl 开关**：只影响测试；默认关闭时缺 openssl 会 skip，skip 不等于通过；发布/CI 必须设 `PROJECT_MEMORY_REQUIRE_OPENSSL=1`。
- **B5B 清单行尾**：`evidence/B5B/run-20261029T015035Z/sha256sums.txt` 记录的是生成时字节，含混合行尾与两个 NUL 日志；不同检出下的 `sha256sum -c` 可能失败，需逐文件按字节核对（见 `evidence/B5B/README.md`），不得重写历史证据。
- **生产 anchor**：`anchor-a` 的端到端 checkpoint 签名尚未在本仓库内验证；测试使用测试密钥并 patch `authority.load_anchor`。
- **B4 威胁边界**：本地 hash 链不能防御能重算整条链的攻击者；权威性依赖仓库外 anchor 签名。anchor 私钥被攻破后签名保证失效。

### 安装

```bash
python3 -m pip install -e .
# 或在目标仓库内安装 Skill 与工具：
python3 -m project_memory init --repo /path/to/repo --install both
```

运行时不需要 openssl 或第三方库；语义检索是可选依赖（`pip install -e '.[semantic]'`）。

### 回滚

回滚单个里程碑优先用 `git revert -m 1 <merge-commit>` 生成新的回滚提交，不要改写共享历史：

| 里程碑 | 合并提交 | 回滚后果 |
|---|---|---|
| R1 | 本分支合并提交（发布时补） | 恢复空必达可被判 satisfied、openssl 缺失可静默 skip、版本回到 0.1.0/无 CHANGELOG |
| B4 | `85bf6a0` | 失去审计链/签名 checkpoint；`achieved` 退回仅本地声明，旧代码仍能读链式 JSONL |
| B5B | `c49a436` | `test-run` 无 flag 时重新默认为本地执行（不安全），只打印警告 |
| B5A | `4ad3a3b` | 恢复按 `sys.path` 解析的入口，同名包顶替风险回归 |
| B3 | `1930fa5` | 恢复整份判据（含证据）摘要，追加证据会使旧签名失效 |
| B2 | `5a5abdd` | 恢复仅凭收据完整性放行，手写收据可被签名包装 |
| B1 | `15f4b3c` | 恢复外部 openssl 查找，PATH 可影响验签器 |
| B0 | `a70ad19` | 收据重新绑定绝对路径，跨 clone 不可用 |

回滚审计文件时：恢复到迁移前副本会使链变为 `valid_unanchored`（或验证失败），不会静默恢复信任；删除 `audit/head.json` 会立即把 `achieved` 降级为 `achieved_unverified`。
