---
id: "DOC-CURRENT-STATE"
kind: "canonical"
title: "Project Memory 当前状态（v1.0.0）"
status: "current"
owner: "MJ-Zeng"
updated_at: "2026-11-01"
last_verified_at: "2026-11-01"
---

# Project Memory 当前状态（v1.0.0）

## 一句话结论

v1.0.0 可以用于团队内部的记忆记录与跨会话交接；不能作为可信验证或审计依据。

## 当前发布事实

- 发布基线：`v1.0.0` tag 指向 `f033a6c`；`dev/v1.0` 已领先该发布点，尚未发新版本。
- 版本标签：`v1.0.0` 是 annotated tag，未签名。
- 测试门槛：默认运行与设置 `PROJECT_MEMORY_REQUIRE_OPENSSL=1` 运行均通过全量 370 项测试；Windows 上 3 个符号链接用例因无法创建链接而 skip（其中 1 个来自签名证据清单测试），WSL2 sandbox 用例在 WSL 可用时通过（367 passed / 3 skipped），不可用时 skip（366 passed / 4 skipped），具体 skip 数随环境变化。
- 发布证据：在干净检出上，证据包完整性检查 24/24 通过。

## 预期行为

- 本地执行 `verify` 以退出码 2 结束并记录 `MANUAL_REVIEW_REQUIRED`，这是正确结果，不是故障。
- `achieved` 与 `VERIFIED` 需要仓库外、非当前用户所有且不可写的信任锚；单用户主机上不可达。

## 已知限制

- `approved_by` 只是邮箱声明，记录为 `claimed_unverified`。
- 执行证据与收据只证明内容完整性，不证明由谁生成、由谁提交。
- 签名证据清单只证明锚持有者对「这些文件在这个提交下」负责，不证明文件由受保护执行器产生，也不证明命令真的执行过。
- 沙箱执行依赖 `wsl.exe`，它可被环境变量或 PATH 替换。
- 当前知识审计有 40 条 findings（high 0 / medium 16 / low 24；本文件加入前为 84）；high 已由 ADR 元数据修复清零，其余为引用与状态提示。本轮不修。
- `audit` 是本地防篡改检测与文档一致性提示，不构成对外可采信的审计留痕。

## 历史提示

`pilot/PILOT_CLOSEOUT.md` 中的“v1.0：NO-GO”是 2026-10-28、B0–B2 试点阶段的历史结论，已被 2026-10-29 发布的 v1.0.0 取代；该文件原文保留。

## 阅读顺序

1. `README.md`
2. `CHANGELOG.md`
3. `docs/OPERATIONS.zh-CN.md`
4. `skill/project-memory/SKILL.md`

其他规范文档（补充与历史材料，路径仅供查阅）：`docs/ARCHITECTURE.zh-CN.md`、`docs/TEST_REPORT.md`、`docs/TUTORIAL.zh-CN.md`。
