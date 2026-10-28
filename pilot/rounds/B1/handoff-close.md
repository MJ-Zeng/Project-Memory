---
handoff_id: HO-B1-CLOSE
schema: pilot-handoff/v1
task_id: B1
issue: https://github.com/MJ-Zeng/Project-Memory/issues/1
goal_id: G-B1
round: 1
from_role: PM-01
to_role: Human / next round
base_sha: 25a919d63c7181fd4083e0fc1af33734d74c5515
candidate_sha: 1c7ad94f8c3beb369f4a86a33accda6910213105
branch: fix/b1-openssl-verifier
pr: https://github.com/MJ-Zeng/Project-Memory/pull/9
merge_commit: 15f4b3cd7117b8464c82b4f114e5fbf2336176c1
criteria_sha256: 0fdc9469456b81bae26a3c29385f1745222e16b19211e27d4d04a418ef3be08d
agent_label: "PM-01 Supervisor <pm01@pilot.invalid>"
session_id: pm01-close-20261028T1835+0800
model: dsh/deepseek-flash
created_at: 2026-10-28T18:40:00+08:00
status: closed
---

# B1 收口交接（PM-01 → 人类 / 下一轮）

## 1. 结果

- B1 = **merged**：PR #9，Merge commit `15f4b3c`，parents `25a919d` + `216f154`。
- 审查：PM-03 **PASS**（`review/b1-1c7ad94` @ `09f68d8`，`pilot/review/B1/REVIEW-B1.md`）。
- 缺陷：D-B1-R1-01（审查清单 CRLF/GBK）已整改并复核（干净检出 18/18 OK），Issue #1 comment 6466694289。
- Issue #1：closed（`Closes #1` 随合并自动关闭，人类已知情）。
- Goal `G-B1`：仍为 `proposed`。合并 ≠ `achieved`，Agent 未宣布。

## 2. 这轮证明了什么

1. 验签不再由环境选择：`PATH` 前置假 `openssl`、`PROJECT_MEMORY_OPENSSL=<fake>`、`PROJECT_MEMORY_OPENSSL=/bin/true` 三路在候选上全部被拒（探针 `probe-after.json`）。
2. 打印 `Verified OK` 的假验签器也被拒（PM-03 自建变体）。
3. 攻击链到不了 `achieved`（PM-03 自建链：`goal evidence`=1 → `achieved`=1，Goal 停在 `evaluating`）。
4. 真人预签的有效记录仍可用（AC-1：`goal evidence` exit 0、stderr 0 字节、记录哈希不变）。
5. 合并树与候选树逐字节相同（`2be9fc6…`），合并后回归 190 passed / 2 skipped。

## 3. 没证明什么

- 纯 Windows、非 WSL 的端到端 `goal evidence` 未复跑（Windows SID 检查仅有单测覆盖）。
- DER/SPKI 解析器未 fuzz；无 ECDSA 时序/恒定时间测量；无性能基准。
- 只支持 `rsa-sha256` / `ecdsa-sha256`(P-256)；其它算法一律拒绝（设计如此）。
- `LD_PRELOAD` 未单独植入（验签路径已无子进程，归入“整进程替换”类）。
- root 妥协、anchor 轮换流程仍是部署前提，不在本轮范围。

## 4. 过程可靠性发现（供下一轮改进）

| # | 发现 | 影响 | 建议 |
|---|---|---|---|
| 1 | PM-02 环境无 `gh`，B1 PR 由 PM-01 代开（ROLES §4 程序性例外） | PR 归属与角色边界变模糊 | 给 PM-02 只读/建 PR 的最小凭据，或把“代开”写入 ROLES |
| 2 | 任务卡 AC-8 写“147”，实测基线 164（派发前已陈旧） | 审查需额外解释；判据与事实脱节 | 下一轮派发前用命令生成基线数字，不手写 |
| 3 | 证据行尾/编码：CRLF 哈希 + GBK 日志导致清单不可自校验 | 可复现性下降；首次复核 16/18 | 证据脚本统一 LF + UTF-8，清单从清净检出生成 |
| 4 | PM-02 的 `chain_probe.py` 省略 `goal_criteria_sha256` 修复步骤 | `chain-before` 与真实攻击链不符 | 审查者必须自建链，不采信开发者的链 |
| 5 | `pilot/STATUS.md` 多次滞后（B0 提交后仍写 `blocked_by_B0`） | PM-03 记录了一条过期事实 | 每次状态变更与代码同 PR，不后补 |

## 5. 转下一轮的风险

- **B5 HIGH**：`PYTHONPATH` / cwd 同名 `project_memory/` 可整体顶替模块（基线同样成立，非本轮引入）。建议写成 B5 验收条目，负例“成功即 FAIL”。
- `data-contracts.md:74` 仍允许 `target_repository` 为仓库名（O-2，文档与实现不一致）。
- `project_memory/execution.py` 的 `_SENSITIVE_ENV` 仍列 `PROJECT_MEMORY_OPENSSL`（已无读取方，保留无害）。
- 两个审查日志仍为 GBK（字节校验不受影响，阅读需转码）。
- 合并后未做 release/部署验证；`dev/v1.0` 即当前主线。

## 6. 指标（描述性，n=3，不推导“效率提升”）

| 指标 | 值 | 来源 |
|---|---|---|
| CRR 复述正确率 | PM-02 6/6（10 分钟）；PM-03 6/6（9 分钟） | 两份 `context-recovery-*` |
| RQ 补问率 | 0 / 2 次交接 | 两份 Handoff |
| HR Handoff 完整率 | 27/27 | `.project-memory/handoffs/B1/run-20261028T1344.json` |
| IR 独立复现率 | AC-1..AC-11 全部由 PM-03 重跑 | `REVIEW-B1.md` |
| DY 审查发现数 | 1 HIGH（范围外）/ 1 LOW / 1 INFO | `REVIEW-B1.md` §7 |
| DV 开发-审查分歧 | 0 项观测值冲突；1 项链证据口径差异（已披露） | 两份报告 |
| 任务结果 | PASS | PM-03 + 人类合并 |

## 7. 污染记录

- `human_relay`：人类转述了 PM-02 起草的 Issue 评论原文（6466530363）与“PM-03 已完成”的状态；PM-01 只做事实核对与录入。
- `missing_artifacts`：PM-02/PM-03 均无 GitHub 认证（PR/评论由 PM-01 代执行）。
- `stale_artifacts`：`pilot/STATUS.md`（已在本 PR 修正）、任务卡 AC-8“147”。
- `unauthorized_reads`：无。

## 8. 下一步（均需人类授权）

1. 审阅并合并本收口 PR（Merge commit）。
2. 是否启动 B2、是否创建 B2 Issue：人类决定；B1 已关闭不等于自动进入 B2。
3. B5 条目化（PYTHONPATH/cwd 顶替）与发布/部署验证：另行授权。
