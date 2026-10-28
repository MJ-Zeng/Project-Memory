---
handoff_id: HO-B2-CLOSE
schema: pilot-handoff/v1
task_id: B2
issue: https://github.com/MJ-Zeng/Project-Memory/issues/12
goal_id: G-B2
round: 1
from_role: PM-01
to_role: Human / product backlog
base_sha: 587ac6a5024db3a6076a863876076d7fc7ecdd98
candidate_sha: 004a35bd7c6b6584a9054d7b61eca88b44ec25e6
branch: fix/b2-receipt-provenance
pr: https://github.com/MJ-Zeng/Project-Memory/pull/14
merge_commit: 5a5abddfc35161c290537c8e009352e7b52960bd
criteria_sha256: 3617dab01ca01c05ba2cb9ec87b38eae2622a6b69b480b2e7abb1c0881a7900e
agent_label: "PM-01 Supervisor <pm01@pilot.invalid>"
session_id: pm01-b2-close-20261028T2145+0800
model: dsh/deepseek-flash
created_at: 2026-10-28T21:45:00+08:00
status: closed
---

# B2 收口交接（PM-01 → 人类 / 产品 backlog）

## 1. 结果

- B2 = **merged**：PR #14，Merge commit `5a5abddf`，parents `587ac6a` + `6257fb6`。
- PM-03：**PASS**（逻辑级 28/28 + anchor-a E2E 4/4）；报告 `review/b2-004a35b` @ `6cbdc76` 的 `pilot/review/B2/REVIEW-B2-E2E.md`；证据 `pilot/evidence/B2/review-e2e-20261028T213532Z/`，25/25 OK。
- 合并后回归：203 passed / 2 skipped（候选树；基线 190/2）。
- Issue #12：closed（`state_reason=completed`）。
- Goal `G-B2`：仍为 `proposed`；合并 ≠ `achieved`，Agent 未宣布。

## 2. 这轮证明了什么

1. 有效签名不能包裹手写/自洽收据：两个伪造 case 在真实 anchor-a 下 exit 1，错误指向“执行来源不可信”。
2. 谎报 `trusted=true` 也无效：`forged-claimed-trusted` 内容完整、布尔为真，仍被拒；门禁不查布尔值。
3. 真实 anchor-a 签名的 attestation / 人类例外可用：两个正例 `goal evidence` exit 0。
4. 绑定字段有效：换收据/改 provenance/换 commit/重算哈希/换 attestation 均失败（28/28 矩阵）。
5. B1 无回归：`authority` 只追加，未放宽签名信任模型。

## 3. 没证明什么 / AC-3 caveat

- 任务卡 AC-3 写“接受；`satisfied=true`”。正例 `goal evidence` exit 0，但 `goal evaluate` 仍 `satisfied=false`——这是 **B3 正向自失效**，不是 B2 来源门禁问题。
- 按任务卡字面，AC-3 的 `evaluate` 子项是 **NOT VERIFIED，B3 范围**。人类已接受该 scope split（见 `decision.md`）。
- attestation 的 `uid`/`pid_ns_levels`/`env_count`/`network` 是签名者断言，未由真实 WSL `trusted_exec` 观测；真实启动器隔离仍未验证。
- 真实人类签名例外：签名者仍是持有 anchor-a 密钥的 PM-01，无法区分“人类本人”与“持有密钥的自动化”；`issued_by` 只是字符串。
- 重放同一 attestation 到同一收据/提交按设计接受，未单独复验。
- Windows 符号链接拒绝路径未单独执行（平台限制）。
- 私有仓库 Issue/PR 未由 PM-02/PM-03 认证读取（无 token/gh）；PM-01 转发。

## 4. 指标（描述性，n=1 轮 B2）

| 指标 | 值 |
|---|---|
| 逻辑级矩阵 | 28/28 |
| E2E anchor-a | 4/4 |
| B2 专项测试 | 13 passed |
| 全量回归 | 203 passed / 2 skipped |
| 新可利用绕过 | 0 |
| 审查发现 | 0 阻断；6 项 Low/Info（CRLF 哈希、context-recovery 越界、model 自报 qoder、attestation 断言、重放、文档） |
| 接手耗时 | PM-02 19 分钟；PM-03 约 10 分钟 |
| PR 评论 | PM-03 无 token，未能自行发；PM-01 转发 |

## 5. 残余风险

- root/信任根被攻破可签任意 attestation/exception；设计不防御。
- 受保护启动器被替换时，签名者仍需对启动器身份负责。
- 同一 anchor 多用途（Verification/attestation/exception），未做用途分离。
- 例外是“人类负责”，不是“执行被证明”。
- 旧 Verification 在门禁升级后默认不再满足 criterion（预期迁移）。
- `execution_attestation_sha256` 可选字段的摘要循环策略未定。

## 6. 过程发现

1. PM-02/PM-03 无 GitHub token：PR/评论/Issue 由 PM-01 代执行；角色边界变模糊。
2. `context-recovery-pm02.md` 再次越界（同 B0 F-1 类型）；任务卡允许清单没有它。
3. Handoff 的 `model` 写 `qoder/qoder-desktop-agent`，与当前环境不一致；model/session 是自报，不是认证。
4. 任务卡 AC-3 把 B3 的 `evaluate` 写进 B2；派发前未拆开，导致后验 scope split。
5. `pilot/STATUS.md` 多次滞后；本轮由 PM-01 收口时更新。
6. 分支保护 0 approvals：同账号 Agent 技术上可自合并；人类批准是程序性的，不是强制。

## 7. 下一步

- **B3**：修正向流程自失效，使正例 `goal evaluate satisfied=true`；这是 B2 AC-3 的遗留子项。
- **B4/B5**：按原产品计划；含 `PYTHONPATH`/cwd 同名模块顶替 HIGH（B1 发现，范围外）。
- **v1.0**：仍未 GO；B3/B4/B5、WSL_EXE、人类身份/审批、发布工程未完成。
- **试点**：三轮 B0/B1/B2 已完成，收尾报告见 `pilot/PILOT_CLOSEOUT.md`；不再派发新的试点轮次，除非人类另行授权。

## 8. 污染记录

- human_relay：PM-01 转发了 PM-03 的报告/评论；PM-02/03 未读彼此会话。
- missing_artifacts：PM-02/03 无 GitHub API 访问。
- stale_artifacts：`pilot/STATUS.md`（本轮已修）、`data-contracts.md:74`（O-2）。
- unauthorized_reads：none。
