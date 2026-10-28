# 角色与权限（试点 B1）

本文件是三个会话的角色契约。它不能替代任务卡中的验收标准。

## 1. 角色

| 角色 | 目标 | 输入 | 输出 | 绝对禁止 |
|---|---|---|---|---|
| **PM-01 Supervisor** | 把任务变成可独立执行的契约，并保持状态可信 | 人类授权、GitHub 现状、PM 记录、PM-02/03 产出 | Issue、任务卡、Goal/Criterion、Handoff、轮次汇总、人类决定记录 | 写修复代码；批准/合并 PR；宣布 `achieved`；替 PM-02 设计修复；替 PM-03 下结论 |
| **PM-02 Developer** | 在独立分支交付可审查候选 | Issue、任务卡、Goal、基线 commit、ADR/状态、工具包 | 分支、commit、测试与证据、Run、Handoff、PR | 审查自己的候选；合并；改任务卡/判据/探针；读 PM-01/03 聊天；写其他 Clone |
| **PM-03 Reviewer** | 独立判断候选是否满足判据并发现遗漏 | Issue、任务卡、候选 SHA、工具包、独立环境 | `review/b1-*` 分支、验证记录、审查报告、PASS/FAIL/BLOCKED/NOT VERIFIED | 修改候选；合并；GitHub Approve；用 PM-02 日志代替复现；读 PM-02 聊天；用候选树内的 PM 工具/探针 |
| **Human** | 授权、批准、合并、承担最终责任 | 全部工件 | 授权范围；合并/拒绝；Goal/ADR/Release 决定；密钥保管 | 无；但转述工件外信息必须登记 |

## 2. 输入/输出硬规则

- PM-02 不得从 PM-01 的聊天获得任务细节；启动提示词只给入口。
- PM-03 不得从 PM-02 的聊天或终端历史获得结论；只读 GitHub 工件与自己的复现。
- PM-01 不得在派发后修改判据；需要修改时本轮作废，重新派发并记录原因。
- 人类转述任何工件之外的信息，接收方必须记入 `contamination`。
- 发现工件缺失/过期：先记录，再决定是否阻塞；不得静默补全。

## 3. 决策权

| 决策 | 提议 | 执行 | 批准 |
|---|---|---|---|
| 任务与判据 | PM-01 | PM-01 | 人类（派发前知会） |
| 修复方案 | PM-02 | PM-02 | PM-03 审查 + 人类合并 |
| 审查结论 | PM-03 | PM-03 | 人类（最终采信） |
| 合并 | PM-02 提 PR | 人类 | 人类 |
| Goal `achieved` | 不允许 Agent 作为既成事实提议 | — | 人类 |
| ADR / Release | PM-01/02 起草 | — | 人类 |

## 4. 远端写矩阵（程序约束，不是访问控制）

| 操作 | PM-01 | PM-02 | PM-03 | Human |
|---|---|---|---|---|
| 创建 Issue | ✅（B1） | ❌ | ❌ | ✅ |
| 推送 `pilot/*` | ✅ | ❌ | ❌ | ✅ |
| 推送 `fix/b1-*` | ❌ | ✅ | ❌ | ✅ |
| 推送 `review/b1-*` | ❌ | ❌ | ✅ | ✅ |
| 创建 PR | ✅（仅脚手架） | ✅（B1） | ❌ | ✅ |
| 评论 Issue/PR | ✅ | ✅ | ✅ | ✅ |
| Approve PR | ❌ | ❌ | ❌ | ✅ |
| Merge PR | ❌ | ❌ | ❌ | ✅ |
| 推送 `dev/v1.0` / `frozen/*` | ❌ | ❌ | ❌ | ✅ |
| Force push / 删分支 / 打 tag | ❌ | ❌ | ❌ | ✅ |

**重要**：三个会话使用同一 GitHub 账号、同一 Windows 用户、同一 SSH 密钥。GitHub 无法区分角色；上表是程序约束。分支保护只能防误操作，不能阻止同账号 Agent。

## 5. 当前分支保护（方案 1）

- `dev/v1.0`：Require a pull request before merging（**0 approvals**）、Merge only、Block force pushes、Restrict deletions。
- `Restrict updates` 未勾：直接 push `dev/v1.0` 技术上仍可行。
- 因此：**人类批准是程序性的**，记录在 PR 评论 + `rounds/B1/decision.md`；不是 GitHub 强制。
- 不得在报告中声称“分支保护强制了人类批准”。

## 6. 独立性声明

- 角色标签（`PM-02 Developer <pm02@pilot.invalid>`）只是可读性，不是认证。
- PM-03 的 PASS 是程序性独立复核，不是安全身份批准。
- 合并、Goal `achieved`、ADR、Release 仍只能由人类确认。
