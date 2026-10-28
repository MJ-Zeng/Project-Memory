# B0 独立审查报告（PM-03）

- 运行：`review-20261028T103443`
- 审查者：PM-03 Independent Reviewer（独立会话，未读取 PM-01/PM-02 会话、终端历史或工作树）
- 日期：2026-10-28
- 仓库：`git@github.com:MJ-Zeng/Project-Memory.git`
- 审查分支：`review/b0-14cc8fc`（仅追加 `pilot/review/B0/` 与 `pilot/evidence/B0/review-20261028T103443/`）

## 1. 候选与基线

| 项 | 值 | 核对方式 |
|---|---|---|
| 任务 | `B0` — 可移植的仓库身份，解除执行收据的绝对路径绑定 | `pilot/rounds/B0/task.md` |
| 基线 | `73be8e3ac4efc04c1811c122eb665344fe8ce4c3` | `git rev-parse`；是候选的父提交 |
| 候选 | `14cc8fcba367dc36db0706041a21f22e10e3264e` | `git cat-file -t` = commit；`git log 73be8e3..14cc8fc` 2 个提交 |
| PR head | `b02cc3329774b39db7edcacd5d8fd59fe3abd113` | `git ls-remote origin refs/pull/5/head` 与 `refs/heads/fix/b0-repo-identity` 均为该 SHA |
| PR | https://github.com/MJ-Zeng/Project-Memory/pull/5 | — |
| 任务卡 SHA-256 | `81e20cf8c16a30c904e925e195d7748bce5a11f24a62f5c16a3ec15b895061c0` | `sha256sum pilot/rounds/B0/task.md`（与派发值一致） |
| PR head 相对候选的增量 | 仅 `pilot/rounds/B0/handoff-run-20261028T1010.md` 与 `.project-memory/handoffs/B0/run-20261028T1010.json` | `git diff --name-status 14cc8fc b02cc33` |

候选可解析、是基线后代（直接子提交）、PR head 只多 Handoff 文档、任务卡哈希匹配 —— 未触发停止条件。

隔离：`.pilot/base`（73be8e3）与 `.pilot/candidate`（14cc8fc）两个只读 worktree；审查记录写入独立的 `.pilot/review-state`（用 `.pilot/base` 的工具生成），快照在 `pilot/review/B0/state-snapshot/`。未使用候选树内的 `scripts/` 或探针来得出审查结论。

## 2. 验收标准逐条

| AC | 判据 | 方法 / 证据 | 退出码 | 结论 |
|---|---|---|---|---|
| AC-1(a) | 跨路径正例：A 出收据，复制到 B 仍有效 | 自建 A/B 临时仓库（合成 remote），`test-run`→`run start/finish`→`verify`；B 中 `verify_receipt.valid=true`、`_verification_current=true`；`cross_path.json` | 0 | **PASS** |
| AC-1(b) | `goal evidence` exit 0（已签名） | 无新的 schema 1.1 已签名 fixture，未自行签名；`goal evaluate` 在 A/B 均因无信任锚退出 2（`MANUAL_REVIEW_REQUIRED`） | 2 | **NOT VERIFIED** |
| AC-2 | 跨仓库负例被拒绝且错误指向仓库身份 | 4 个负例（同根不同 remote、不同根无 remote、不同根同 remote、同根缺少 remote）全部 `valid=false`，问题含“仓库”；`cross_repo.json` | 0 | **PASS** |
| AC-3 | 身份定义稳定、无绝对路径 | ADR-0001 §2；`repo_identity` 只由规范化 remote + 根提交组成；A/B 身份相同且 JSON 中不含任一检出路径（`cross_path.identity_contains_path=false`） | 0 | **PASS** |
| AC-4 | 旧收据不静默跨路径通过 | 用**基线代码**生成真实 schema 1.0 收据：原路径 `valid=true`、`legacy_path_bound=true`、`identity.kind=legacy_path_bound`、`portable=false`；复制到 B 后 `valid=false` 且报 legacy 路径绑定；`legacy.json` | 0 | **PASS** |
| AC-5 | 回归 | 基线 `pytest`：145 passed / 2 skipped（147 collected）；候选：156 passed / 2 skipped；无删除测试；`pytest-baseline.log`、`pytest.log` | 0 / 0 | **PASS** |
| AC-6 | 无新伪造路径，authority 不削弱 | `authority.py` 无改动；`verify_receipt` 对 `_provenance` 逻辑无改动；独立篡改 `repo_identity.remote` 并重算内容哈希仍被拒（`tamper.json`）；未引入身份相关的环境变量覆盖（`execution.py` 无新增 `environ` 读取） | 0 | **PASS** |
| AC-7 | ADR 完整 | ADR-0001 含身份定义、4 个被拒方案、信任模型“防/不防”、迁移与残余风险；与实现一致 | — | **PASS** |
| AC-8 | 范围纪律 | `git diff --name-status`：`execution.py` 修改，`tests/test_repo_identity.py` 新增，`docs/decisions/`、`pilot/evidence/B0/`、`pilot/rounds/B0/handoff-*` 允许项；唯一偏差见 F-1 | 0 | **PASS（附低severity偏差）** |
| AC-9 | 证据可复现 | PM-02 证据包 `sha256sum -c` 32 项全部 OK；本报告证据 18 项见 `sha256sums.txt` | 0 | **PASS** |
| AC-10 | PM-03 独立复现 | 本会话从两个独立路径重跑正例与负例（未复用 PM-02 脚本） | 0 | **PASS** |

合计：11 个子项中 **10 PASS / 1 NOT VERIFIED**。

## 3. 动态复现结果

### 3.1 跨路径正例（独立构造）

A（`.../path-a`，remote `https://github.com/pilot-org/portable-a`）完成 `goal create` → `test-run` → `run start/finish` → `verify`；整仓复制到 B（同 commit）。

| 断言 | A | B |
|---|---|---|
| `verify_receipt.valid` | true | **true** |
| `_verification_current` | true | **true** |
| `repo_identity.id` 相同 | — | **true** |
| 身份 JSON 含检出路径 | — | **false** |

`verify` 在 A/B 均退出 2（`MANUAL_REVIEW_REQUIRED`，本构建无签名者）；`goal evaluate` 在 A/B 输出一致（退出 2，`insufficient_evidence`，`status_authority=local_untrusted`）。除此之外 A 与 B 行为无差异。证据：`cross_path.json`、`commands.jsonl`。

**基线对照**（`baseline_before.py`）：用 `73be8e3` 代码生成收据，`receipt.repo_id == sha256(casefold(绝对路径A))`（断言为 true）；同一收据在 B 中 `valid=false`，问题为“收据属于其他仓库”，`current_repo_id` 等于 B 的路径哈希。P-1 被真实复现。

### 3.2 跨仓库负例

| 用例 | 结果 | 错误指向 |
|---|---|---|
| 同根提交、不同 remote | 拒绝 | “收据属于其他仓库” |
| 不同根提交、无 remote | 拒绝 | 仓库身份 |
| 不同根提交、同 remote | 拒绝 | 仓库身份 |
| 同根提交、副本删除 remote | 拒绝 | 仓库身份 |

证据：`cross_repo.json`。无任何负例被接受。

### 3.3 Legacy 1.0

| 场景 | 结果 |
|---|---|
| 由基线代码生成的真实 1.0 收据，原路径 | `valid=true`，`legacy_path_bound=true`，`portable=false` |
| 同收据复制到新路径 | `valid=false`，问题含 “legacy 路径绑定” |
| 候选是否把旧收据当新 schema 静默放行 | 否（按 `schema_version` 分支，独立标记） |

证据：`legacy.json`。

### 3.4 回归

- 基线：`145 passed, 2 skipped`（147 collected），exit 0。
- 候选：`156 passed, 2 skipped`（+11 新增，无删除/新增跳过），exit 0。
- 2 个 skip 为既有的 Windows 符号链接用例（`tests/test_security_rc3.py:291,304`），与基线一致。

## 4. 新发现

### F-1（Low，范围偏差）
`pilot/rounds/B0/context-recovery-pm02.md` 不在任务卡允许清单内（允许的是 `pilot/rounds/B0/handoff-*`）。内容为 PM-02 冷启动恢复记录，不涉及代码、判据、探针或 B1–B5 行为。不影响任何 AC，但严格按 AC-8 属允许清单外的文档。

### F-2（Low–Medium，既有的验证路径绑定残留）
`project_memory/coordination.py` 未被本候选修改，但“创建验证记录”仍绑定绝对路径：

- `_repo_matches` 要求 criterion evidence 的 `target_repository` 等于当前仓库绝对路径（或仓库目录名）。
- 在 B 中用 A 的映射重跑 `verify` → exit 1：“target_repository ... 不是当前仓库”；改成 B 的路径后结构上可继续（exit 2，无信任锚）。
- `_repo_aliases` 同时接受 `repo.name`，因此另一个同名目录的不同仓库也能通过这项检查。

这**不影响** AC-1(a)/AC-2（读取既有验证记录与收据验证均不经过该检查），也不构成本 diff 引入的回归；但“验证记录可移植”目前仅指读取既有记录，重新验证仍需改本地绝对路径字段。

### F-3（Low，身份归一化的边界）
`ssh://git@host:22/path` 归一到 `host:22/path`，而 scp 形式 `git@host:path` 归一到 `host/path`，两者被当作不同身份。ADR 已声明“不猜测等价关系”，但同一仓库用带端口的 ssh URL 与 scp URL 分别 Clone 时会误判为不同仓库（假阴性）。

### F-4（Info，已知过期工件）
`pilot/README.md`、`pilot/STATUS.md` 仍写 B1 当前轮次 / B0 `draft`。PM-02 已在 `stale_artifacts` 披露；按任务约定不单独构成 FAIL，但应更新。

### F-5（Info，残留在设计中的伪造面）
收据与仓库身份都无密钥；把 1.1 收据改标为 1.0 并重算 `repo_id` 与内容哈希，在同一路径下仍会“自洽通过”。这在基线版本同样成立（当时只需重写 `repo_id` 与内容哈希），不是本候选新增的绕过；ADR §5.6 已声明身份不是来源证明。

## 5. 残余风险与 NOT VERIFIED

- **NOT VERIFIED：AC-1(b) 已签名 `goal evidence` exit 0** —— 无新的 schema 1.1 已签名 fixture，未自行签名（按任务指引）。
- NOT VERIFIED：浅克隆（`--depth`）时根提交被截断，身份与完整 Clone 不同（ADR 已记录，需 `--unshallow`）。
- NOT VERIFIED：真实远端 fetch、WSL/trusted 执行、跨 OS 文件系统。
- 残余风险（与 ADR 一致）：`execution_provenance.trusted` 仍恒为 false，签名/authority 仍是唯一信任门槛；无 remote 或本地路径 remote 的仓库退化为 `root-only`，同根提交的不同来源无法区分；`ssh://` 显式端口见 F-3。
- PR 描述与评论：本会话无 `gh`，私有仓库未认证读取不可用；只通过 `git ls-remote`（PR head/分支一致）与仓库内 Handoff 交叉核对。GFM 评论无法读取，记录为工件缺失，不阻塞结论。

## 6. 与 PM-02 自报的差异

| 项 | PM-02 自报 | PM-03 复现 | 一致性 |
|---|---|---|---|
| 测试 | 156 passed / 2 skipped | 156 passed / 2 skipped，exit 0 | 一致 |
| 跨路径 | B 中 valid/current 均 true | 同 | 一致 |
| 跨仓库 | 不同 remote/根均拒绝 | 4 例全拒绝 | 一致（多 2 例） |
| Legacy | 原路径有效且标 legacy，跨路径拒绝 | 同（用基线代码生成真实 1.0 收据） | 一致 |
| 身份无路径 | 声明 | 断言为 true | 一致 |
| AC-1(b) | 主动列为 NOT VERIFIED | 同（无法补签名） | 一致 |
| 范围 | 未提及 `context-recovery-pm02.md` 越界 | F-1 | **PM-02 未报告** |
| 验证创建路径绑定 | 未报告 | F-2 | **PM-02 未报告** |
| ssh 端口归一化 | 未报告（ADR 只写“不猜测等价”） | F-3 | **PM-02 未报告** |

PM-02 未声明 PASS/VERIFIED，自报与复现无实质性夸大；证据包哈希全部可复核。

## 7. 最终结论

**NOT VERIFIED**（核心修复通过程序性独立复核，但存在未运行的 AC）。

- AC-1(a) 与 AC-2..AC-10 满足；跨路径正例、4 个跨仓库负例、legacy 三态、回归全绿、无新绕过。
- AC-1(b) 未运行，因此本轮不能记 PASS；是否接受核心修复并延后签名项由人类决定。
- 本结论是程序性独立复核，不是安全身份批准；合并、Goal `achieved`、ADR 接受仍由人类决定。未 Approve、未合并。

## 8. 污染与偏差

- `human_relay`: 无。
- `stale_artifacts`: `pilot/README.md`、`pilot/STATUS.md`（B1 当前轮次 / B0 draft）。
- `missing_artifacts`: PR #5 描述/评论、Issue #3 正文无法在本环境读取（无 `gh`，私有仓库未认证）；以 `git ls-remote` + 仓库内 Handoff 交叉核对。
- `unauthorized_reads`: 无。未读 PM-01/PM-02 聊天、终端、未提交文件；未使用候选树内探针/`.project-memory` 工具；未读签名私钥，未签名。
- 偏差：`git diff` 的首个静态检查在 `.pilot/candidate` worktree 进行；动态复现全部在临时目录新构造，未复用 PM-02 脚本。
- 接手耗时：约 8 分钟（首次正确复述 6 项事实 + 哈希核对）；必须追问的问题：无（Issue 正文不可读已记录）。
- 上下文恢复：6/6（任务、基线、候选、判据编号、PM-02 声明、下一步）。
