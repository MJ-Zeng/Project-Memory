---
id: "DOC-CURRENT-STATE"
kind: "canonical"
title: "Project Memory 当前状态"
status: "current"
owner: "MJ-Zeng"
updated_at: "2026-11-03"
last_verified_at: "2026-11-01"
---

# Project Memory 当前状态

## 一句话结论

v1.0.0 可以用于团队内部的记忆记录与跨会话交接；不能作为可信验证或审计依据。

## 当前发布事实

- 发布基线：`v1.0.0` tag 指向 `f033a6c`；`dev/v1.0` 已领先该发布点，尚未发新版本。
- 版本标签：`v1.0.0` 是 annotated tag，未签名。
- 测试门槛：默认运行与设置 `PROJECT_MEMORY_REQUIRE_OPENSSL=1` 运行均通过全量 389 项测试；Windows 上 3 个符号链接用例因无法创建链接而 skip（其中 1 个来自签名证据清单测试），WSL2 sandbox 用例在 WSL 可用时通过（386 passed / 3 skipped），设置 `PROJECT_MEMORY_DISABLE_WSL=1` 后该用例 skip（385 passed / 4 skipped），具体 skip 数随环境变化。
- 发布证据：在干净检出上，证据包完整性检查 24/24 通过。
- 发布构建：`release` 工作流产出源码归档、sdist、wheel、`sha256sums.txt`、BUILD-INFO.json 与 GitHub artifact attestation，**已在 GitHub-hosted runner 上真实跑过一次**：`workflow_dispatch` 干跑 run `41324143240`（BUILD-INFO.json 记 `generated_at 2026-11-01T16:01:31Z`）产出 `dist/` 下 5 个文件（`sha256sums.txt` 4 行，按设计不含自身）与一份 attestation；`v*` tag 推送的触发路径仍为 NOT VERIFIED。那次构建绑定提交 `cfdd848d78cd476e3ace1e83be95a11727a7ef84`（树 `9382d8893fbed36b7cd84dc705a659d95c2f0a86`、`ref refs/heads/dev/v1.0`）。这份来源证明只属于该次干跑，不能归属到旧发布：`v1.0.0` 原始 Tag 剥皮后指向另一个提交 `f033a6c517cfde3eebb586b07f770d94b2d2c3b7`。签发能力与验证能力要分开说：attestation 只能由 GitHub-hosted runner 用该 run 的 OIDC 令牌签发（干跑那次的签名证书里 runner 环境为 `github-hosted`、令牌签发方为 `token.actions.githubusercontent.com`），本机不能生成、也不得伪称生成；验证侧本机可做的是对已取得的制品副本逐字节复算 `sha256sums.txt`、离线解开 bundle 复算 statement 摘要，在线验签可匿名查询 `gh attestation verify` 与 attestations 端点（按制品摘要索引），但取得制品字节本身需要仓库读取凭据。`v1.0.0` 仍是未签名的 annotated tag，Release 没有资产，发布构建也不创建 Release。

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
