# Project Memory 多 Agent 协作试点 — 仓库内入口

本目录是三个独立会话（PM-01 主管、PM-02 开发、PM-03 审查）在仓库内的唯一协作入口。

- 试点策略与完整计划在实验室 `verification-lab/import-workspace/`，**不在本仓库**。
- 本目录只放三个会话必须读到的最小工件：角色、轮次协议、B1 任务卡、验证工具包、当前状态。
- 不要从其他会话的聊天、终端历史或工作树补信息。

## 阅读顺序

| 角色 | 顺序 |
|---|---|
| PM-01 | `README.md` → `ROLES.md` → `ROUND_PROTOCOL.md` → `rounds/B1/task.md` → `STATUS.md` |
| PM-02 | `README.md` → `ROLES.md` → `ROUND_PROTOCOL.md` → `rounds/B1/task.md` → `rounds/B1/handoff-dispatch.md` → `kit/b1/README.md` |
| PM-03 | 同上，另加 `rounds/B1/handoff-*.md`、`review/B1/REVIEW.md`（如已有） |

## 事实来源

1. **代码事实**：不可变 commit SHA > 分支名 > 文档。
2. **任务事实**：Issue + 已冻结任务卡 > Handoff > 聊天/口头。
3. **证据事实**：可复现命令 + 退出码 + 日志 + 哈希 > `VERIFIED` 字段 > 自报。
4. **授权事实**：人类决定 > 任何 Agent 声明。

## 硬规则

- PM-02 不审查自己的候选，不合并 PR，不修改任务卡/判据/探针。
- PM-03 不修改候选，不 Approve，不合并，不使用候选树里的 PM 工具或探针。
- PM-01 不写修复代码，不批准/合并，不宣布 `achieved`。
- 三个会话不读取彼此的聊天、终端历史、未提交文件。
- 任何角色发现工件缺失/过期，先记录，再决定是否阻塞。
- 不得提交私钥、token 或其他项目数据。

## 当前轮次

- 轮次：**B1**（`dispatched_pending_pm02_start`）
- 基线：B1 派发准备提交（含 `pilot/kit/b1/positive/`）；精确 SHA 见 Issue #1；冻结参照 `0d08a1a`
- 上一轮：B0 已合并（`a70ad19`），B0.1 复审 PASS（`review/b0-8506dd4` 的 `pilot/review/B0/REVIEW-B0.1.md`）
- 状态：见 `STATUS.md`

## 目录

```
pilot/
  README.md                 本文件
  ROLES.md                  角色、输入输出、禁止项、远端写矩阵
  ROUND_PROTOCOL.md         状态机、门禁、Handoff/PR 模板、决定记录
  STATUS.md                 当前状态（带 as_of / verified_by）
  rounds/B0/task.md         B0 任务卡（已完成、已合并）
  rounds/B0/handoff-*.md    B0 Handoff
  rounds/B1/task.md         B1 任务卡与验收标准
  rounds/B1/handoff-dispatch.md  PM-01 → PM-02 派发交接
  reference/RC3_B1_B3.md    B1–B3 的脱敏摘要与复现要点
  kit/b1/                   B1 原始探针与使用说明
  kit/b1/positive/          正向签名 fixture（由人类生成）
  review/B1/                PM-03 审查报告与证据（审查时创建）
  evidence/B1/              PM-02/PM-03 证据（运行时创建）
```
