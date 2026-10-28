# B0.1 整改独立复审报告（PM-03）

- 运行：`review-20261028T130230`
- 审查者：PM-03 Independent Reviewer（独立会话；未读取 PM-01/PM-02 会话、终端历史或工作树）
- 日期：2026-10-28
- 仓库：`git@github.com:MJ-Zeng/Project-Memory.git`
- 审查分支：`review/b0-8506dd4`（仅追加 `pilot/review/B0/` 与 `pilot/evidence/B0/review-20261028T130230/`）
- 性质：程序性独立复核，不是安全身份批准；未 Approve、未合并、未修改候选。

## 1. 候选与基线

| 项 | 值 | 核对方式 |
|---|---|---|
| 任务 | `B0` — 可移植仓库身份（B0.1 整改复审） | `pilot/rounds/B0/task.md` |
| 原始基线 | `73be8e3ac4efc04c1811c122eb665344fe8ce4c3` | `git rev-parse` |
| 上一轮候选 | `14cc8fcba367dc36db0706041a21f22e10e3264e` | `git cat-file -t` = commit |
| 本轮候选 | `8506dd4db225ac9d04db1983d7bcfca9db13ee70` | `git cat-file -t` = commit |
| PR head | `8f7a63e7c049638083436fb070fc56d2e56b411b` | 本地对象存在 |
| PR | https://github.com/MJ-Zeng/Project-Memory/pull/5 | — |
| 任务卡 SHA-256 | `81e20cf8c16a30c904e925e195d7748bce5a11f24a62f5c16a3ec15b895061c0` | `sha256sum pilot/rounds/B0/task.md`，一致 |
| PR head 增量 | 仅 `.project-memory/handoffs/B0/run-20261028T1142.json`、`pilot/rounds/B0/handoff-run-20261028T1142.md` | `git diff --name-status 8506dd4 8f7a63e` |

提交链：`73be8e3 → d872de1 → 14cc8fc → b02cc33 → baeb2b9 → 8506dd4 → 8f7a63e`。三条祖先关系均成立（`git merge-base --is-ancestor`）。候选/PR head/任务卡哈希一致，未触发停止条件。

恢复的 6 项事实：任务 B0.1；原始基线 `73be8e3`；本轮候选 `8506dd4`；判据 AC-1..AC-10（重点 F-1/F-2/F-3、AC-1(b)、AC-5）；PM-02 声明 F-2/F-1/F-3 已修、AC-1(b) NOT VERIFIED、164 passed/2 skipped、不声明 PASS；下一步为独立复现并给出程序性结论。接手耗时约 10 分钟；必须追问的问题：无（PR 描述/评论不可读已记录）。

隔离：`.pilot/base`（`73be8e3`）、`.pilot/prev`（`14cc8fc`）、`.pilot/candidate`（`8506dd4`）三个只读 worktree；动态复现全部在自建临时仓库；审查 PM 状态写入独立 `.pilot/review-state-b01`（用 `.pilot/base` 工具生成），快照在 `pilot/review/B0/state-snapshot-b0.1/`。未使用候选树内 `.project-memory/tooling` 或探针。

## 2. 整改项逐项

### F-2 — 验证映射按稳定仓库身份绑定：PASS

静态：`project_memory/coordination.py:360` 的 `_repo_binding` 使用 `from .execution import repo_identity`（第 17 行）计算当前仓库的 `{id, canonical_remote}`，不再读取 `repo.name`；`_repo_matches`（第 408 行）只是非空判断。路径形式必须是 git 顶层目录；路径位于当前仓库内部、不存在、解析失败、或当前用户不是可解析目录时一律返回 `None`（fail-closed）。`_git`（第 163 行）返回 `(code, stdout)`，不抛异常。

动态矩阵（`f2_binding_matrix.json`，6 接受 + 10 拒绝，全部符合预期）：

| 声明 | 结果 |
|---|---|
| 身份 id（含大写形式） | 接受（`identity`） |
| 规范化 remote `github.com/pilot-org/repo-a` | 接受（`identity`） |
| 当前检出绝对路径 | 接受（`path`） |
| 身份相同的另一检出根（A 路径，在 B 中判断） | 接受（`identity`） |
| 不同 remote 的副本 C | 拒绝 |
| 不同根提交、同 remote 的仓库 D | 拒绝 |
| 同名目录的另一仓库 E（`elsewhere/path-b`） | 拒绝 |
| 裸目录名 `path-b` | 拒绝 |
| 当前仓库子目录 `path-b/tests` | 拒绝 |
| 不存在路径、文件路径、相对路径 | 拒绝 |
| 不同仓库的身份 id | 拒绝 |

端到端（`f2_cross_path.json`）：A 建仓、合成 remote、`goal create` → `test-run` → `run start/finish`；整仓复制到 B；在 B 中用 A 的绝对路径作为 `target_repository` 调用 `verify_run`：

- `verify_run` 成功（`VER-7e949f175a13`），未出现“不是当前仓库”；
- 记录中 `target_repository` 仍为 A 路径，未改写；
- `_verification_current(B, record) = true`；
- 收据在 B 中 `valid=true`、`portable=true`、`legacy_path_bound=false`。

负例端到端（`f2_negative.json`）：在 B 中把 mapping 指向不同 remote 的 C，`verify_run` 抛 `PMError`：“criterion evidence 的 target_repository '…path-c' 不是当前仓库”。

上一候选对照（`prev_control.json`，同一组临时仓库）：

| 声明 | `14cc8fc`（prev） | `8506dd4`（candidate） |
|---|---|---|
| A 的绝对路径（在 B 中） | `false`（F-2 复现） | `true` |
| 裸目录名 `path-b` | `true`（过宽） | `false` |
| 不同 remote 的 C 路径 | `false` | `false` |

结论：F-2 的两半（跨路径可用、同名/裸名不可绕过）均由本次改动解决，而不是靠改本地路径。

### F-3 — 远程身份归一化：PASS

`project_memory/execution.py:114` 的 `_strip_default_ssh_port` 丢弃显式 `:22`（IPv6 方括号感知），`_canonical_remote`（第 77 行）在剥离 scheme/user 后应用它。动态矩阵（`f3_identity.json`，12 个变体）：

| 变体 | 规范化 remote | 与 https 基线同一 id |
|---|---|---|
| `https://github.com/pilot-org/repo-a` | `github.com/pilot-org/repo-a` | 基线 |
| `…repo-a.git/` | 同上 | 是 |
| `ssh://git@github.com:22/pilot-org/repo-a` | 同上 | 是 |
| `git@github.com:pilot-org/repo-a` | 同上 | 是 |
| `ssh://git@github.com:22/…repo-a.git` | 同上 | 是 |
| `ssh://other@github.com:22/…` | 同上 | 是 |
| `https://user@github.com/…` | 同上 | 是 |
| `ssh://git@github.com:2222/…` | `github.com:2222/pilot-org/repo-a` | 否（独立） |
| IPv6 无端口 / `:22` | `[2001:db8::1]/team/repo` | 二者相同 |
| IPv6 `:2222` | `[2001:db8::1]:2222/team/repo` | 与上不同 |

身份 JSON 不含检出路径。默认端口只影响等价类，不合并不同 host/path。观察项见 §5 O-1。

### F-1 — 改名：PASS

`git diff --summary -M 14cc8fc..8506dd4` 仅一条：
`rename pilot/rounds/B0/{context-recovery-pm02.md => handoff-context-recovery-pm02.md} (100%)`。
改名在 `baeb2b9`，内容零变化；`git diff --diff-filter=D 73be8e3..8506dd4` 为空（无删除文件）。

## 3. AC-1(b) 已签名 fixture：PASS

环境：WSL Ubuntu，**uid 1000（zmj）**，Python 3.14.4；`/etc/pm-rc3-review/anchor-a.json` 为 `root:root 0644`；未读取私钥、未签名。fixture 复制到 `/tmp/pm03-ac1b-run/repo-copy`（HEAD `c3c122c09b231837e549b46d0e4ae93886648dc8`，remote `https://github.com/pilot-org/b0-cross-path`），设置 `core.autocrlf true` / `core.fileMode false`，tracked 工作树干净；`PYTHONDONTWRITEBYTECODE=1` 避免污染候选树。

命令（退出码 0，stderr 0 字节）：

```bash
cd <copy>
PROJECT_MEMORY_TRUST_ANCHOR=/etc/pm-rc3-review/anchor-a.json \
PYTHONPATH=/mnt/c/.../pm-pilot-03/.pilot/candidate \
python3 -m project_memory goal evidence \
  --repo . --id G-B0 --criterion C1 \
  --kind verification --ref VER-B0-XP
```

输出与期望（`ac1b_compare.json`）：

| 字段 | 实际 | 期望 |
|---|---|---|
| `kind` | `goal_evidence_result` | 同 |
| `goal_id` | `G-B0` | 同 |
| `criterion` | `C1` | 同 |
| `schema_version` | `1.2` | 同 |
| 退出码 | 0 | 0 |

完整性：运行前后签名记录 SHA-256 均为 `4ca8ec5d7a0026846061250996ff6b38a915534dc9ccfa0180d143618db3eb30`；只有副本中的 Goal 被追加证据（`8f9e8221…` → `b78add15…`），Goal 状态仍为 `proposed`。fixture 本体未被修改：记录哈希不变，`git status` 仍只有未跟踪的 `.project-memory/`。第一次运行后 WSL `/tmp` 被清理，已用新副本重跑一次，两次均退出 0 且输出一致；前后哈希来自第二次运行。

说明：`goal-evidence-result.json` 是 UTF-16LE，并夹带一段 PowerShell/WSL 代理告警文本；比对时取其中第一个 JSON 对象（`raw_decode`）。这是 fixture 生成方式的质量问题，不影响命令本身。

## 4. 回归与上一轮 AC

在 `.pilot/candidate`（候选树，`-p no:cacheprovider`、`PYTHONDONTWRITEBYTECODE=1`）独立重跑：

- 全量：`164 passed, 2 skipped`，exit 0（`pytest.log`）；上一候选 `156 passed/2 skipped`，原始基线 147 collected。
- 新增 `tests/test_repo_identity.py`：19 个测试函数全部通过、0 skip（`pytest-identity.log`）。
- 2 个 skip 均为既有 Windows 符号链接用例 `tests/test_security_rc3.py:284,295`（`pytest-security.log`）；无新增 skip、无删除测试。
- 候选 worktree 运行前后 `git status --porcelain` 均为空。

上一轮 AC 复验（`prior_acs.json`）：

| 项 | 结果 |
|---|---|
| AC-1 收据跨路径（A→B） | `valid=true`、`portable=true` |
| AC-2 不同 remote 收据 | 拒绝：“收据属于其他仓库” + 身份字段不一致 |
| 身份字段篡改（改 `repo_identity.remote` 并重算内容哈希） | 拒绝 |
| AC-4 legacy 1.0 原路径 | `valid=true`、`legacy_path_bound=true`、`kind=legacy_path_bound` |
| AC-4 legacy 1.0 复制后 | 拒绝：“legacy 路径绑定，不能跨路径使用” |
| authority/签名/`execution_provenance.trusted` | `authority.py` 无改动；diff 中无 trust/signature 逻辑变化；fixture 记录仍为 `tests.execution_trust=local_untrusted` |

范围：`git diff --name-status 73be8e3..8506dd4` 的代码/测试仅 `project_memory/coordination.py`、`project_memory/execution.py`、`tests/test_repo_identity.py`；文档为 ADR-0001 与 `pilot/` 证据/Handoff；`.project-memory/handoffs/` 仅 Handoff 记录。无 B1–B5 行为文件、无任务卡/判据/探针/评测器改动。

### 证据清单与校验

`pilot/evidence/B0/review-20261028T130230/` 共 31 个受校验文件：驱动与脚本（`driver_b01.py`、`match_control.py`、`assemble.py`、`review_state.py`、`ac1b_run.sh`）、F-2/F-3 结果（`f2_cross_path.json`、`f2_binding_matrix.json`、`f2_negative.json`、`f3_identity.json`、`prior_acs.json`、`control_prev.json`、`control_candidate.json`、`prev_control.json`、`summary.json`）、AC-1(b)（`ac1b_goal_evidence.json`、`ac1b_compare.json`、`ac1b_environment.txt`、`ac1b_exit_code.txt`、`ac1b_stderr.txt`、`ac1b_record_hash_before.txt`、`ac1b_record_hashes_after.txt`、`ac1b_git_status_before.txt`、`ac1b_git_status_after.txt`）、日志（`pytest.log`、`pytest-identity.log`、`pytest-security.log`、`driver.log`、`verify_sha256sums.log`）、`environment.txt`、`diffstat.txt`、`commands.jsonl`、`sha256sums.txt`。

哈希取自提交后的 LF blob（`.gitattributes` 强制 `pilot/**` LF），在新检出 worktree 中 `sha256sum -c sha256sums.txt`：**31 OK / 0 FAILED**（exit 0）。

## 5. 新发现

| ID | 严重度 | 内容 | 影响 |
|---|---|---|---|
| O-1 | Info | `_strip_default_ssh_port` 对所有 scheme 都剥离 `:22`，因此 `https://github.com:22/...` 与 `https://github.com/...` 得到同一身份。ADR §2.1 的措辞也写成通用 `scheme://`。 | 低。scheme 本来就已丢弃，https 使用 22 端口极罕见；不影响 F-3（只要求 ssh）与 AC-2。若未来要区分，可按 scheme 限定只对 ssh 剥离。 |
| O-2 | Info/Low | `skill/project-memory/references/data-contracts.md:74` 仍写 `target_repository` “必须是当前仓库名或路径”，与实现（裸名已拒绝）矛盾。该文件不在任务卡允许范围。 | 文档误导，不是行为缺陷；PM-02 已在 Handoff 披露，建议后续轮次修正。 |
| O-3 | Info | Handoff 写“测试数 12 → 20”，实际测试函数为 11 → 19（文件内 20 处 `def test_` 含样例仓库字符串里的 `def test_ok()`）。 | 仅计数表述偏一；`164/2` 与新增 8 项结果一致。 |
| O-4 | Info | fixture 的 `goal-evidence-result.json` 是 UTF-16LE 且混入 PowerShell/WSL 告警文本。 | 需跳过噪声才能解析；建议 fixture 只保存纯 JSON。 |

无阻断性新发现，未发现新的伪造/绕过路径。

## 6. 残余风险与 NOT VERIFIED

- PASS 是程序性复核，不是安全身份批准；`repo_id` 与收据内容哈希仍无密钥，`execution_provenance.trusted` 仍恒为 false，`VERIFIED` 仍依赖 authority 签名。合并、Goal `achieved`、ADR 接受由人类决定。
- 未运行：浅克隆（`--depth`）根提交截断、真实远端 fetch、跨 OS 文件系统、`git worktree` 场景（ADR §5 已记录限制）。
- 映射写绝对路径且原检出被删除时，B 无法解析旧路径身份，失败关闭（ADR §5.7）；长期可移植应写身份 id 或规范化 remote。
- 上一轮 F-5（把 1.1 收据改标 1.0 并重算本地哈希，可在同路径“自洽”）由设计决定，仍存在但非本次新增。
- PR #5 描述与评论无法读取（本环境无 `gh`/token，私有仓库未认证），记为工件缺失；已用本地提交链、PR head 增量与仓库内 Handoff 交叉核对，不影响结论。
- `pilot/STATUS.md` / `pilot/README.md` 仍为 B1 当前轮次的过期工件（上一轮 F-4），不单独构成失败。

## 7. 与 PM-02 自报的差异

| 项 | PM-02 自报 | 本次复现 | 一致性 |
|---|---|---|---|
| F-2 跨路径 mapping | 通过，进入 `MANUAL_REVIEW_REQUIRED` | 通过；`VER-7e949f175a13`，`_verification_current=true` | 一致 |
| F-2 负例 | 不同 remote/根、同名目录、裸名均拒绝 | 全部拒绝；另测子目录、不存在、文件、相对路径 | 一致（更多负例） |
| F-3 | `:22` 归一、`:2222` 独立 | 同，并覆盖 IPv6、user、`.git/` | 一致 |
| F-1 | `R100` | `R100`，0 内容变化 | 一致 |
| AC-1(b) | NOT VERIFIED（无受保护 anchor 所有权） | **PASS**（人类提供 anchor-a + 签名 fixture；uid 1000 运行 exit 0） | **PM-02 保守；本轮补上** |
| 回归 | 164 passed / 2 skipped | 同 | 一致 |
| 新增测试数 | 12 → 20 | 11 → 19 个测试函数（+8） | 计数表述偏一（O-3） |
| 范围 | 未夹带 B1–B5 | 同 | 一致 |
| `data-contracts.md` 过期 | 已披露、未改 | 确认仍过期（O-2） | 一致 |

PM-02 未声明 PASS/VERIFIED，自报与复现无实质性夸大。

## 8. 最终结论

**PASS（程序性独立复核）**。

- F-2、F-3、F-1 整改满足；跨路径 mapping 可用，跨仓库/同名目录/裸名不可绕过。
- AC-1(b) 已签名 fixture 在独立副本、uid 1000、受保护 anchor 下 exit 0，输出与期望一致，签名记录未被改动。
- 全量回归 164 passed / 2 skipped；上一轮 AC（跨路径、跨仓库、legacy、篡改拒绝）无退化；authority/签名未被放宽。
- 新发现均为 Info/Low 文档或边界观察，无阻断项。
- 本结论不构成 Approve 或合并授权；未点击 Approve、未合并、未 force push。

## 9. 污染、偏差与耗时

- `human_relay`: 无。
- `missing_artifacts`: PR #5 描述/评论（无 `gh`/token，私有仓库未认证）；Issue #3 正文未认证读取，沿用仓库内 `pilot/rounds/B0/issue.md`。
- `stale_artifacts`: `pilot/STATUS.md`、`pilot/README.md`（B1 当前轮次）；`skill/project-memory/references/data-contracts.md`（O-2）。
- `unauthorized_reads`: 无。未读 PM-01/PM-02 聊天、终端、未提交文件；未使用候选树 `.project-memory/tooling` 或候选探针；未读签名私钥，未签名。
- 偏差：动态复现全部在 `%TEMP%` 新建仓库；AC-1(b) 使用 fixture 的新副本（未在原 `repo/` 运行）；上一候选对照使用 `.pilot/prev` 只读代码；pytest 禁用缓存与字节码以保持候选树干净。第一次 AC-1(b) 后 WSL `/tmp` 被系统清理，已重建副本重跑并补充前后哈希。
- 接手耗时：约 10 分钟（6/6 事实恢复 + 哈希核对；无必须追问的问题）。
