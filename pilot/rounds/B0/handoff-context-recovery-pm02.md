# B0 冷启动恢复记录 — PM-02

- 会话：PM-02 Developer，独立 DSH 会话
- 工作区：`C:/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-02`
- 记录时间：2026-10-28T09:44+08:00

## 1. 六项事实

| # | 事实 | 内容 | 依据 |
|---|---|---|---|
| 1 | 任务一句话 | 把执行收据的仓库身份从“绝对路径哈希”改为不依赖路径的稳定身份，使同一仓库的不同 Clone/路径可互相验证收据，同时仍拒绝不同仓库的收据。 | `pilot/rounds/B0/task.md` §1、§4、§6 |
| 2 | 基线 SHA | `73be8e3ac4efc04c1811c122eb665344fe8ce4c3`（PR #4 merge commit）。`git rev-parse` 可解析，等于 `dev/v1.0` 当前 HEAD 与 `origin/dev/v1.0`。 | `git rev-parse`、`git ls-remote --symref origin HEAD` |
| 3 | 允许修改范围 | `project_memory/execution.py`（`repo_id` 及调用点）、`project_memory/coordination.py`（仅验证路径所需）、`tests/test_security_rc3.py` 或新增 `tests/test_repo_identity.py`、`docs/decisions/` ADR、`pilot/evidence/B0/`、`pilot/rounds/B0/handoff-*`、必要的收据/快照 schema 版本文档。禁止改 B1–B5 行为、任务卡/判据/探针/评测器、删除或跳过既有测试。 | `task.md` §5、§11；Issue `issue.md` “范围” |
| 4 | 验收标准编号 | AC-1 跨路径正例；AC-2 跨仓库负例；AC-3 身份定义（无绝对路径）；AC-4 向后兼容（旧收据不静默跨路径通过、schema 升级）；AC-5 回归（147 + 新增全绿）；AC-6 无新伪造路径；AC-7 ADR；AC-8 范围纪律；AC-9 证据；AC-10 独立复现。 | `task.md` §7 |
| 5 | 当前分支状态 | `dev/v1.0`，工作树干净（`git status --short --branch` 无改动），本地无 `fix/b0-repo-identity` 分支，尚无候选提交。 | 本会话 `git status`、`git branch -a` |
| 6 | 下一步 | 从基线创建 `fix/b0-repo-identity`；先写 ADR/security note；实现稳定仓库身份与 legacy 标记；跑跨路径正例、跨仓库负例、旧收据用例与全量测试；产出 `pilot/evidence/B0/<run-id>/` 证据与 Handoff；推分支并开 PR 到 `dev/v1.0`。 | `task.md` §5、§9；`ROUND_PROTOCOL.md` §4–§5 |

## 2. 环境与门禁核对

| 项 | 结果 |
|---|---|
| 任务卡 SHA-256 | 实测 `81e20cf8c16a30c904e925e195d7748bce5a11f24a62f5c16a3ec15b895061c0`，与 `criteria.sha256`、Issue 记录一致 |
| 冻结参照 `71b65bd…` | `git rev-parse` 可解析 |
| Windows Python | `C:\SoftWare\Anconda\python.exe` 3.12.4 |
| pytest 收集 | 147 collected（`pytest --collect-only -q -p no:cacheprovider`） |
| WSL | `wsl.exe -u root -e python3 --version` → Python 3.14.4 |
| B0 探针/fixture | 不需要（任务明确 B0 不使用 `pilot/kit/b1/`） |
| 远端 | `origin git@github.com:MJ-Zeng/Project-Memory.git`，`core.sshCommand="ssh -o ProxyCommand=none"` |

## 3. 耗时

会话开始（约 09:39）到本记录完成（09:44）：**约 5 分钟**。

期间额外耗时：首次 shell 调用被 Windows 文件权限拒绝（`grantWrite` 失败），用仓库内允许的 ACL 修复流程处理一次后恢复；不计入任务内容。

## 4. 无法从工件确认、必须询问的问题

1. **Issue #3 的在线正文与标签**：仓库为 Private，未认证 `web_fetch` 返回 404，本会话无 `gh`、无可用 GitHub token。已用仓库内 `pilot/rounds/B0/issue.md`（提交在基线中）+ `pilot/STATUS.md` + 派发提示三处交叉确认 Issue 编号与任务卡哈希；**未确认的是 Issue 页面当前是否被派发后修改**。若需以此判定派发有效性，需 PM-01/人类提供带认证的读取或截图。
2. **`pilot/STATUS.md` 与 `pilot/README.md` 过期**：两处仍写“当前轮次 B1 / B0 状态 draft”，而基线上 B0 已派发（`handoff-dispatch.md` status=dispatched）。按事实来源优先级（任务卡 + dispatch handoff > STATUS），不阻塞；但 STATUS 的 “B0 状态” 行在本轮结束后需要 PM-01 更新。
3. 基线 SHA 未写入 Issue #3 正文（`handoff-dispatch.md` 写 “see dispatch Issue”，STATUS 记 B0-D2 未完成）。本会话按派发提示与实际 `dev/v1.0` HEAD 确认基线为 `73be8e3`；若 Issue 后来写入的基线不是该 SHA，需要人类裁决。

## 5. 污染记录

- `human_relay`：无。除启动提示词与本仓库工件外，没有人类或 PM-01/PM-03 向本会话转述任务信息。
- 未读取 PM-01/PM-03 的聊天、终端历史、工作树；未使用 `project-memory-mvp` 或 `pm-import`。
- `unauthorized_reads`：无。Issue #3 的读取尝试为公开 HTTP GET（返回 404），未触及他人会话。

## 6. 结论

工件与门禁一致，可以继续执行 B0。上述第 4 节第 1、3 项记为待确认事项，不构成 BLOCKED：任务卡存在且哈希匹配，基线可解析，环境可用。
