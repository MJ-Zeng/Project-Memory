---
id: "DOC-PILOT-R1"
kind: "policy"
title: "首轮受控试点章程（R1）"
status: "current"
owner: "MJ-Zeng"
updated_at: "2026-10-30"
last_verified_at: "2026-10-30"
---

# 首轮受控试点章程（R1）

事实依据以 `docs/CURRENT_STATE.md` 为准；本文只把它已核验的结论写成可执行边界，不新增事实。

## 一、适用场景与边界

- 覆盖：人审每个 PR、Agent 只做辅助的协作方式。
- 不覆盖：无人值守合并、CI 自动门禁、合规外部审计。

## 二、角色与独立性

- 执行、复核、中继三权分离：执行者产出候选与证据，复核者独立判断，中继只传递文件。
- 复核必须在独立会话、独立克隆、独立环境中进行；交接只经仓库文件，不靠聊天记录。
- 同一 GitHub 或 OS 身份的多个会话不构成独立批准。

## 三、信任边界

- `approved_by` 只是调用方声明，记录为 `claimed_unverified`，不是批准。
- 执行收据只证明内容完整性与执行事实，不证明由谁生成、由谁提交。
- `externally_verified` 仅在 `verify --pr` 实际抓取到该提交全绿且 head 匹配时可声明；无 `--pr` 或非 `pass` 会被拒绝。`human_approved` 仍不能通过 CLI 声明。

## 四、预期终态

- 单用户主机上 `achieved` 与 `VERIFIED` 不可达：它们需要仓库外、非当前用户所有且不可写的信任锚。
- 首轮以 `MANUAL_REVIEW_REQUIRED` 为正常终态。
- 达成结论只能由人类审阅给出，Agent 不能自行宣布。

## 五、门禁

- `audit --scope current --fail-on high` 与 `reconcile --fail-on high` 均须 exit 0。
- 禁止路径零改动：产品代码、测试、冻结与证据目录不在本轮改动范围。
- 远端写入（push、PR、Release、tag）逐次授权，未授权即视为越权。
- `audit` 只是本地防篡改检测与文档一致性提示，不构成对外可采信的审计留痕。

## 六、度量

- 上下文恢复时间 ≤15 分钟：新会话只读仓库文件即可继续。
- 未授权远端写入 0 次。
- 未经独立验证即宣称达成 0 次。

## 七、退出与停止条件

- 出现 high 缺陷未关闭时停止。
- 复核与执行在同一会话、同一身份且不可区分时停止。
- 出现未授权 push、PR 或 Release 时停止。
- 首轮结束由人类签字；未签字不得宣称多 Agent 协作成功。
