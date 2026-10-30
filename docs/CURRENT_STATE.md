---
id: "DOC-CURRENT-STATE"
kind: "canonical"
title: "Project Memory 当前状态（v1.0.0）"
status: "current"
owner: "MJ-Zeng"
updated_at: "2026-10-30"
last_verified_at: "2026-10-30"
---

# Project Memory 当前状态（v1.0.0）

## 一句话结论

v1.0.0 可以用于团队内部的记忆记录与跨会话交接；不能作为可信验证或审计依据。

## 当前发布事实

- 发布基线：`dev/v1.0` 位于 `f033a6c`。
- 版本标签：`v1.0.0` 是 annotated tag，未签名。
- 测试门槛：默认运行与设置 `PROJECT_MEMORY_REQUIRE_OPENSSL=1` 运行均为 253 passed / 2 skipped。
- 发布证据：在干净检出上，证据包完整性检查 24/24 通过。

## 预期行为

- 本地执行 `verify` 以退出码 2 结束并记录 `MANUAL_REVIEW_REQUIRED`，这是正确结果，不是故障。
- `achieved` 与 `VERIFIED` 需要仓库外、非当前用户所有且不可写的信任锚；单用户主机上不可达。

## 已知限制

- `approved_by` 只是邮箱声明，记录为 `claimed_unverified`。
- 执行证据与收据只证明内容完整性，不证明由谁生成、由谁提交。
- 沙箱执行依赖 `wsl.exe`，它可被环境变量或 PATH 替换。
- 当前知识审计有 84 条 findings，其中 14 条 high 来自 ADR 元数据（id、status、provenance 不合规）；本轮不修。

## 历史提示

`pilot/PILOT_CLOSEOUT.md` 中的“v1.0：NO-GO”是 2026-10-28、B0–B2 试点阶段的历史结论，已被 2026-10-29 发布的 v1.0.0 取代；该文件原文保留。

## 阅读顺序

1. `README.md`
2. `CHANGELOG.md`
3. `docs/OPERATIONS.zh-CN.md`
4. `skill/project-memory/SKILL.md`

其他规范文档（补充与历史材料，路径仅供查阅）：`docs/ARCHITECTURE.zh-CN.md`、`docs/TEST_REPORT.md`、`docs/TUTORIAL.zh-CN.md`。
