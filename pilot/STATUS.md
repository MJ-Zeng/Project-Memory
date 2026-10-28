# 试点当前状态

> 每个事实带 `as_of` 与 `verified_by`。没有验证命令的“当前状态”不得写入。

## 仓库与分支

| 事实 | 值 | as_of | verified_by |
|---|---|---|---|
| 仓库可见性 | Private | 2026-10-27 | 用户确认 |
| 冻结基线 | `0d08a1ad85144d11a46d6a361a2a3ce4eadbbed4` | 2026-10-27 | `git rev-parse` |
| 开发主线 | `dev/v1.0`（默认 HEAD，指向 `71b65bd`） | 2026-10-28 | `git ls-remote --symref origin HEAD` |
| `frozen/rc3-0d08a1a` | 存在，指向 `0d08a1a` | 2026-10-27 | `git ls-remote` |
| 脚手架分支 | `pilot/bootstrap` 已推送；PR #2 **已合并** | 2026-10-28 | GitHub PR #2 |
| B1 任务卡 SHA-256 | `0fdc9469456b81bae26a3c29385f1745222e16b19211e27d4d04a418ef3be08d` | 2026-10-28 | `Get-FileHash`；fresh clone 复核一致 |
| B1 基线 | `71b65bd26356df41efbb566bd8fe5e8648394bd9`（PR #2 merge commit） | 2026-10-28 | Issue #1 / `git ls-remote` |
| B1 Issue | [#1](https://github.com/MJ-Zeng/Project-Memory/issues/1) | 2026-10-28 | GitHub API |
| B1 状态 | `blocked_by_B0`；PM-02 不得开始 | 2026-10-28 | 本文件 |
| B0 任务卡 SHA-256 | `81e20cf8c16a30c904e925e195d7748bce5a11f24a62f5c16a3ec15b895061c0` | 2026-10-28 | `Get-FileHash` |
| B0 状态 | `draft`；dispatch PR 待合并 | 2026-10-28 | 本文件 |

## 工作区

| 工作区 | 状态 | 说明 |
|---|---|---|
| `pm-pilot-01` | 已创建 | PM-01；当前在 `pilot/b0-dispatch` |
| `pm-pilot-02` | 已创建 | PM-02；`dev/v1.0`，干净 |
| `pm-pilot-03` | 已创建 | PM-03；`dev/v1.0`，干净 |
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
| B0-D1 | B0 dispatch PR 未合并 | 人类点 Merge（Merge commit） |
| B0-D2 | B0 base 未写入 B0 Issue | dispatch PR 合并后记录 |
| B0-FIX | B0 修复未开始 | B0 修复与独立复核 |
| B1-W11 | B1 正向 fixture 未生成 | B0 完成后按 Clone 生成 |
| B1-BLOCK | B1 被 B0 阻断 | B0 关闭后重新派发 B1 |

## 环境

| 项 | 值 | verified_by |
|---|---|---|
| Windows Python | `C:\SoftWare\Anconda\python.exe` 3.12.4 | `--version` |
| pytest | 9.1.1 | `pytest --version` |
| 基线测试数 | 147 collected | `pytest --collect-only` |
| WSL | Ubuntu；python3 3.14.4；无 pytest | `wsl` 命令 |
| 签名 anchor | `/etc/pm-rc3-review/` 存在 | 目录检查 |
| Git SSH | 当前代理不可用；Clone 使用 `core.sshCommand="ssh -o ProxyCommand=none"` | `git ls-remote` |

## 变更记录

- 2026-10-27：创建三个独立 Clone；初始化 PM；加入 `pilot/` 脚手架；未推送。
- 2026-10-28：脚手架 PR #2 合并（`71b65bd`）；发现 `repo_id` 绝对路径绑定（P-1）；B1 标记 `blocked_by_B0`；创建 B0 dispatch 分支。
