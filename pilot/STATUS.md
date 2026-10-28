# 试点当前状态

> 每个事实带 `as_of` 与 `verified_by`。没有验证命令的“当前状态”不得写入。

## 仓库与分支

| 事实 | 值 | as_of | verified_by |
|---|---|---|---|
| 仓库可见性 | Private | 2026-10-27 | 用户确认 |
| 冻结基线 | `0d08a1ad85144d11a46d6a361a2a3ce4eadbbed4` | 2026-10-27 | `git rev-parse` |
| 开发主线 | `dev/v1.0`（默认 HEAD，指向 `f116269`） | 2026-10-28 | `git ls-remote --symref origin HEAD` |
| `frozen/rc3-0d08a1a` | 存在，指向 `0d08a1a` | 2026-10-27 | `git ls-remote` |
| 脚手架分支 | `pilot/bootstrap` 已推送；PR #2 **已合并** | 2026-10-28 | GitHub PR #2 |
| B1 任务卡 SHA-256 | `0fdc9469456b81bae26a3c29385f1745222e16b19211e27d4d04a418ef3be08d` | 2026-10-28 | `Get-FileHash`；fresh clone 复核一致 |
| B1 基线 | B1 派发准备 PR 的 merge commit（含 `pilot/kit/b1/positive/` fixture）；精确 SHA 见 Issue #1 | 2026-10-28 | Issue #1 |
| B1 Issue | [#1](https://github.com/MJ-Zeng/Project-Memory/issues/1) | 2026-10-28 | GitHub API |
| B1 状态 | `dispatched_pending_pm02_start`；推送已授权（仅 `fix/b1-openssl-verifier`） | 2026-10-28 | 本文件 |
| B0 任务卡 SHA-256 | `81e20cf8c16a30c904e925e195d7748bce5a11f24a62f5c16a3ec15b895061c0` | 2026-10-28 | `sha256sum`；复审复核一致 |
| B0 状态 | `merged`（PR #5，Merge commit `a70ad19`） | 2026-10-28 | GitHub API `merged=true` |
| B0.1 复审 | **PASS（程序性独立复核）**；报告 `review/b0-8506dd4` @ `b1e977c` | 2026-10-28 | 该分支的 `pilot/review/B0/REVIEW-B0.1.md` |

## 工作区

| 工作区 | 状态 | 说明 |
|---|---|---|
| `pm-pilot-01` | 已创建 | PM-01；`dev/v1.0` @ `f116269`，干净 |
| `pm-pilot-02` | 已创建 | PM-02；B1 派发后从 Issue #1 的 base 创建 `fix/b1-openssl-verifier` |
| `pm-pilot-03` | 已创建 | PM-03；`review/b0-8506dd4` @ `b1e977c`，干净 |
| 原始 `project-memory-mvp` | 未修改 | 不是试点工作区 |

## 分支保护（方案 1）

| 设置 | 值 |
|---|---|
| Require a pull request | 开 |
| Required approvals | 0 |
| Merge methods | Merge only |
| Block force pushes | 开 |
| Restrict deletions | 开 |
| Restrict updates | 关 |
| Conversation resolution | 开 |

**限制**：同账号下分支保护只能防误操作，不能强制“只有人类能合并”。人类批准记录在 PR 评论 + `rounds/B1/decision.md`，不是 GitHub 强制。

## 已知阻塞

| ID | 阻塞 | 状态 |
|---|---|---|
| B0-D1 | B0 dispatch PR 未合并 | **已关闭**：PR #5 已合并（`a70ad19`） |
| B0-D2 | B0 base 未写入 B0 Issue | **已关闭**：Issue #3 已记录（comment 6461339461） |
| B0-FIX | B0 修复未开始 | **已完成**：B0.1 复审 PASS |
| B1-W11 | B1 正向 fixture 未生成 | **已完成**：PR #7 合并（`f116269`），AC-1(b) `goal evidence` exit 0 |
| B1-BLOCK | B1 被 B0 阻断 | **已解除**：B1 = `dispatched_pending_pm02_start` |
| B1-DISPATCH | B1 派发待人类同意 | **已授权**（2026-10-28）：PM-02 可启动 |
| B1-PUSH | PM-02 推送权限 | **已授权**：仅 `fix/b1-openssl-verifier`，不推 `dev/v1.0` |

## 环境

| 项 | 值 | verified_by |
|---|---|---|
| Windows Python | `C:\SoftWare\Anconda\python.exe` 3.12.4 | `--version` |
| pytest | 9.1.1 | `pytest --version` |
| 基线测试数 | 164 passed / 2 skipped（B0.1 复审，exit 0） | `review/b0-8506dd4` 的 `pilot/evidence/B0/review-20261028T130230/pytest.log` |
| WSL | Ubuntu；python3 3.14.4；无 pytest | `wsl` 命令 |
| 签名 anchor | `/etc/pm-rc3-review/` 存在 | 目录检查 |
| Git SSH | 当前代理不可用；Clone 使用 `core.sshCommand="ssh -o ProxyCommand=none"` | `git ls-remote` |

## 变更记录

- 2026-10-27：创建三个独立 Clone；初始化 PM；加入 `pilot/` 脚手架；未推送。
- 2026-10-28：脚手架 PR #2 合并（`71b65bd`）；发现 `repo_id` 绝对路径绑定（P-1）；B1 标记 `blocked_by_B0`；创建 B0 dispatch 分支。
- 2026-10-28：B0.1 复审 PASS（`b1e977c`）；PR #5 以 Merge commit 合并（`a70ad19`）；B0 关闭记录写入 Issue #3；B1 基线更新为 `a70ad19`，状态改为 `ready_to_dispatch`（派发仍待人类同意）。
- 2026-10-28：B1 正向签名 fixture 生成并合并（PR #7，`f116269`）；`goal evidence` exit 0、记录哈希不变。B1 基线改为含 fixture 的派发准备提交；人类授权派发并允许 PM-02 推送 `fix/b1-openssl-verifier`。
