# [B1] 固定签名验证器，阻断 PATH/环境变量替换

> 这是 Issue 正文草稿。派发时由 PM-01 复制到 GitHub，并填入实际 URL 与合并后的 base SHA。

## 任务

- Task ID：`B1`
- Goal：`G-B1`
- 任务卡：`pilot/rounds/B1/task.md`
- 任务卡 SHA-256：`0fdc9469456b81bae26a3c29385f1745222e16b19211e27d4d04a418ef3be08d`
- 基线：`dev/v1.0` 的脚手架合并提交（派发后填入精确 SHA）
- 冻结参照：`0d08a1ad85144d11a46d6a361a2a3ce4eadbbed4`
- 候选分支：`fix/b1-openssl-verifier`

## 背景

RC3 独立复核 B1：`project_memory/authority.py` 使用 `PATH` / `PROJECT_MEMORY_OPENSSL` 解析验签器，并且只信任其退出码。Agent 控制环境即可替换验签器，使伪造签名被接受，无需私钥即可把 Goal 推到 `achieved`。

## 范围

允许修改：

- `project_memory/authority.py`
- `tests/test_security_rc3.py` 或新增 `tests/test_authority_verifier.py`
- `docs/` 下的 ADR / security note
- 必要的错误消息/帮助文本
- `pilot/evidence/B1/`、`pilot/rounds/B1/handoff-*`、`context-recovery-*`

不允许修改任务卡/判据/探针/评测器，不允许删除/跳过既有测试，不允许读私钥或自行签名。

## 验收摘要

1. PATH 替换被拒（原始探针）。
2. `PROJECT_MEMORY_OPENSSL=/bin/true` 与假 openssl 被拒。
3. 打印 `Verified OK` 的假验签器被拒（PM-03 变体）。
4. 有效签名 fixture 仍能通过。
5. 原始探针攻击链不能到达 `achieved`。
6. 147 项既有测试 + 新增负向测试全绿。
7. 无新绕过；ADR 记录信任根、被拒方案、残余风险。

逐条 AC、防作弊判据、证据包与判定语义见任务卡。

## 阅读顺序

`pilot/README.md` → `pilot/ROLES.md` → `pilot/ROUND_PROTOCOL.md` → `pilot/rounds/B1/task.md` → `pilot/rounds/B1/handoff-dispatch.md` → `pilot/reference/RC3_B1_B3.md` → `pilot/kit/b1/README.md`。

## 约束

- 独立 Clone：`pm-pilot-02`；不得使用原始 `project-memory-mvp`。
- 不读 PM-01/PM-03 聊天、终端历史或工作树。
- 不自行合并 PR、不批准 Goal、不宣布 `achieved`。
- 远端推送仅在授权范围内。

## 标签

`security`、`P0`、`pilot`
