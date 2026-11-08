---
id: "DOC-CURRENT-STATE"
kind: "canonical"
title: "Project Memory 当前状态"
status: "current"
owner: "MJ-Zeng"
updated_at: "2026-11-08"
last_verified_at: "2026-11-08"
---

# Project Memory 当前状态

## 一句话结论

`v1.1.0` 已正式发布：Tag、GitHub Release 与 6 枚公开可下载的制品（含构建来源证明）都已就位，可用于团队内部的记忆记录、跨会话交接与构建来源证明；它不能作为对外可采信的审计依据，也不证明批准来自独立真人。发布后主线 `dev/v1.0` 继续前进：v0.3 加固已移植、CI 覆盖 ubuntu+windows、签名审批锚已轮换并经过真实合并验证（PR #61），仓库自接入已补齐（PR #62），发布后口径文档已对齐（PR #63）；本轮独立审核发现的版本自报缺陷与门禁静默跳过已修（PR #64）。下列远端事实的核查日期是 2026-11-08，保护与平台配置随时可由仓库管理员改动。

## 当前发布事实

- 发布基线：`v1.1.0` 的 annotated tag 对象 `a4a1a184e511e6a4e018409e3a99eec5cd06f28a` 剥皮指向 `4918b86466323425ca58894f77dc7955a6122a3d`（PR #57 squash 合并，树 `c7530a01d9b2a3775eb362f3e61b663c48c743f3`）。GitHub Release `v1.1.0`（id 433549523）已发布：`draft=false`、`prerelease=false`、`published_at 2026-11-04T05:37:01Z`，挂 6 枚资产 = `attestation.json`、`BUILD-INFO.json`、`project-memory-4918b86-source.tar.gz`、`project_memory_skill-1.1.0-py3-none-any.whl`、`project_memory_skill-1.1.0.tar.gz`、`sha256sums.txt`（tag 与 Release 事实 2026-11-08 复核一致）。当前主线 `dev/v1.0` = `50ff4fecf5cb8ecf0c4d712faa2cb53d0de54bbc`（PR #63 的 merge 提交，树 `752b8366e2799e06b3f7f9e8b4b283e4f0d66b33`），在发布之上新增 `af0186a`（图谱容错、init 显式失败移植）与 `e8a4f95`（CI 双平台矩阵），再经 PR #62（merge `b2c9e794791d05b2f5c2e731e1a8ff6b98d23dec`，head `46a4d45`，树 `9934647…`，仓库自接入）与 PR #63（head `8c2725a`，同一棵树 `752b8366…`，README/CHANGELOG 口径对齐）；这些改动尚未打 tag 发布。
- 版本标签：`v1.0.0` 与 `v1.1.0` 都是 annotated tag，均未签名。`v1.0.0` 原样保留：tag 对象 `c96b871f7753c9a311d5884e33245e93cf8f48f1` 剥皮指向 `f033a6c517cfde3eebb586b07f770d94b2d2c3b7`，其 Release 仍没有资产。
- 测试门槛：本轮修复分支 `fix/v1.1-audit-findings`（PR #64 head）上，默认运行与设置 `PROJECT_MEMORY_REQUIRE_OPENSSL=1` 运行均通过全量测试（2026-11-08 本地 Windows 实测：两次均 400 passed / 3 skipped，共 403 项；3 个符号链接用例因无法创建链接而 skip）。上一记录为主线 `50ff4fe` 的 390 passed / 3 skipped（同日上午实测，PR #63 口径）；具体 skip 数随环境变化。CI 的 `test` 工作流自 PR #64 起在探测不到 openssl 时 `exit 1`，不再打印 “SKIPPED” 后成功；2026-11-08 从 `50ff4fe` 两个 job 的日志核实 hosted runner 当前都带 openssl（ubuntu job `128715969809` 报 3.5.5，windows job `128715970002` 报 3.5.9），因此该失败分支在现有镜像上不会触发。CI `test` 矩阵 ubuntu+windows 双平台 success（run `42475548459`，对主线 `50ff4fe`）。
- 发布证据：在干净检出上，证据包完整性检查 24/24 通过（2026-11-04 核查结论，本次未重跑）。
- 发布构建：`release` 工作流产出源码归档、sdist、wheel、`sha256sums.txt`、BUILD-INFO.json 与 GitHub artifact attestation，**已在 GitHub-hosted runner 上真实跑过两次**：`workflow_dispatch` 干跑 run `41324143240`（BUILD-INFO.json 记 `generated_at 2026-11-01T16:01:31Z`，绑定提交 `cfdd848d78cd476e3ace1e83be95a11727a7ef84`、树 `9382d8893fbed36b7cd84dc705a659d95c2f0a86`、`ref refs/heads/dev/v1.0`）与 `v1.1.0` tag 推送触发的 run `41763116854`（`event: push`、job `build` 16 步全绿、绑定 `4918b86…`）。后一次的产物与来源证明已随 Release `v1.1.0` 公开：本方对 6 枚资产逐件匿名下载后复算 SHA-256，与本地实测逐字相同；`sha256sums.txt` 的 4 条对得上 4 枚 dist 件；`attestation.json` 是 sigstore bundle v0.3 + SLSA provenance v1，5 个 subject 摘要与下载件一致，`runDetails.builder.id` = `…/release.yml@refs/tags/v1.1.0`，证书签发方 `CN=sigstore-intermediate,O=sigstore.dev`。所以 1.1.0 的来源证明状态是**已生成、公开、可第三方独立复算**（资产下载复核与 attestation 核对为 2026-11-04 结果，本次未重跑）。干跑那次的证明只属于 `cfdd848`，不能归属到旧发布：`v1.0.0` 原始 Tag 剥皮后指向另一个提交 `f033a6c517cfde3eebb586b07f770d94b2d2c3b7`。签发能力与验证能力要分开说：attestation 只能由 GitHub-hosted runner 用该 run 的 OIDC 令牌签发（干跑那次的签名证书里 runner 环境为 `github-hosted`、令牌签发方为 `token.actions.githubusercontent.com`），本机不能生成、也不得伪称生成；验证侧任何人可匿名下载 Release 资产复算摘要，在线验签走 attestations 端点（按制品摘要索引，查询串要带 `sha256:` 前缀，只给 64 位十六进制会回 404），只有 workflow artifact 才需要仓库读取凭据且保留 90 天。跨主机字节不可复现仍然成立：`git archive` 在 `core.autocrlf=true` 的 Windows 检出与 Linux CI 上逐文件行尾不同，以 CI 构建为权威。发布构建按设计不创建 Release，打 tag、建 Release、挂资产仍是人工动作。

## 主线加固与审批链（2026-11-08）

- 主线决策：`dev/v1.0` 为唯一主线（所有者 2026-11-08 拍板）；v0.3 线 `feat/v0.3-goal-memory` 作 fallback。
- PR #60（v0.3 线，merge `19a6ce62dbd168009e2cc063f2c7b52f01fe63a8`）：仓库边界、跨进程记录锁、图谱容错、init 显式失败四项加固。
- PR #61（主线，head `e8a4f956f194360da59921ae9c43770cffef0534`，merge `34618ba`）：M2/M4 移植到 v1.1，CI 测试矩阵覆盖 ubuntu+windows；`test` run `42443903390` 双平台 success。
- 审批锚轮换：新锚 `ANCHOR-PROD-20261108`（rsa-sha256，公钥 DER SHA-256 `e07ef677d17cc97924f153a759f4c4d2b15168098970c7bdf5a8b2fba5c57d34`），吊销 `ANCHOR-S3-EXERCISE-20261031`（演练私钥已于 2026-11-04 销毁）；CI secret `PROJECT_MEMORY_APPROVAL_ANCHOR_JSON` 于 2026-11-08 更新。新私钥仅存所有者本机用户目录，不在仓库、不入档。
- 首个经真实签名审批合并的 PR：审批 `APR-c2162a31fa50`（Agent 按所有者明确指令签发），记录在 `approvals` 分支 `7da8eb8`；门禁原 run `42443903424` 重跑（attempt 2）success 后合并。
- 分支保护（`dev/v1.0`，2026-11-08 实测）：必需检查 `pytest (ubuntu-latest)`、`pytest (windows-latest)`、`approval`；`strict=true`、`enforce_admins=true`。Ruleset `branch _1` 仍是 disabled，classic 保护在生效；CODEOWNERS 只有 `.github/CODEOWNERS.example`，是否启用由所有者决定。
- 接入补齐：`init` 幂等补齐 `.agents/skills` 安装、`docs/INDEX.md`、PR/Issue 模板、CODEOWNERS 示例与 `项目记忆审计` 工作流；该工作流用仓库自身源码运行（`tooling/` 按既有 `.gitignore` 不入库），`--fail-on high`。
- PR #62（head `46a4d45`，merge `b2c9e79`，审批 `APR-8b4b0b4f3e81`）与 PR #63（head `8c2725a`，merge `50ff4fe`，审批 `APR-aee569bf8962`）都走同一条签名审批链：Agent 按所有者明确指令用仓库外私钥签名，记录发布到 `approvals` 分支（2026-11-08 该分支 head `27a5828418abf6682c97dd9c0b2c8f9dd05f5a39`，共 11 条记录），门禁重跑原 `pull_request_target` run 后合并。两条审批都是 `scope: commit`。
- 本轮独立审核（PR #64，分支 `fix/v1.1-audit-findings`）的结论与修复：唯一 high 是版本双份维护——发布那一份 `pyproject.toml` 写 `1.1.0`、`project_memory.__version__` 仍是 `1.0.0`，而签名证据清单的 `generator.version` 取后者；已改为 `dynamic` 单一来源并加结构守卫。其余修复见 `CHANGELOG.md` 未发布段。审批门禁本身不是空转：`tests/test_b7_ci_second_identity.py` 用一批临时密钥仓库实测 1 条正向（唯一有效记录放行）与 9 组负向——空记录目录、缺失记录目录、记录属于别的提交、`reject` 决定、伪造签名、未配置锚、记录写好后被改写、单一记录模式不受影响、`--require-approve` 在单记录模式被拒绝；锚的过期与吊销由 `tests/test_s4_anchor_lifecycle.py` 覆盖。未修的是 M5（接受 ADR）与 M6（批准 Goal、写 Run/Verify 记录），那两类需要所有者本人，Agent 不能代填 `approved_by`。

## 预期行为

- 本地执行 `verify` 以退出码 2 结束并记录 `MANUAL_REVIEW_REQUIRED`，这是正确结果，不是故障。
- `achieved` 与 `VERIFIED` 需要仓库外、非当前用户所有且不可写的信任锚；单用户主机上不可达。

## 已知限制

- `approved_by` 只是邮箱声明，记录为 `claimed_unverified`。
- 执行证据与收据只证明内容完整性，不证明由谁生成、由谁提交。
- 签名证据清单只证明锚持有者对「这些文件在这个提交下」负责，不证明文件由受保护执行器产生，也不证明命令真的执行过。
- 沙箱执行依赖 `wsl.exe`，它可被环境变量或 PATH 替换。
- 当前知识审计有 36 条 findings（high 0 / medium 17 / low 19；2026-11-08 在 PR #64 head 实测，`--scope current` 扫 14 篇文档）。相比上一记录的 43 条（0/18/25，15 篇）减少 7 条，原因是两件事：4 篇文档补齐显式 `status` 后不再有 `unknown_document_status`，`docs/TEST_REPORT.md` 按正文自述改成 `kind: evidence` + `status: historical` 后不再计入 current（连带它的 1 条 medium 与 2 条 low）。剩下的是引用解析提示（裸文件名引用、指向 evidence 路径的引用、镜像外引用），不是内容错误；没有任何历史或镜像文档被为了清零而改写。
- `audit` 是本地防篡改检测与文档一致性提示，不构成对外可采信的审计留痕。

## 历史提示

`pilot/PILOT_CLOSEOUT.md` 中的“v1.0：NO-GO”是 2026-10-28、B0–B2 试点阶段的历史结论，已被 2026-10-29 发布的 v1.0.0 取代；该文件原文保留。

## 阅读顺序

1. `README.md`
2. `docs/INDEX.md`
3. `CHANGELOG.md`
4. `docs/OPERATIONS.zh-CN.md`
5. `skill/project-memory/SKILL.md`

其他规范文档（补充与历史材料，路径仅供查阅）：`docs/ARCHITECTURE.zh-CN.md`、`docs/TEST_REPORT.md`、`docs/TUTORIAL.zh-CN.md`。

## 变更记录

只追加，不改写历史；本节约自 2026-11-08 起。

- 2026-11-08：复核 tag/Release/主线/CI/分支保护；记录 PR #60/#61、审批锚轮换与接入补齐；更新测试与审计实测数。证据：本文各节所引提交与 run ID；本地 `pytest` 与 `audit --scope current` 实测。
- 2026-11-08（同日第二轮）：独立审核后落地修复批次 PR #64。主线记录更新到 `50ff4fe`（树 `752b8366…`），补 PR #62/#63 的审批记录 ID；版本改为单一来源（`v1.1.0` 制品自报 `1.0.0` 是真实缺陷）；CI 的 openssl 步骤缺 openssl 时改为失败（附两个 runner 的 openssl 版本与 job ID 实测）；`search` 输出 `skipped`；`test-run` 环境过滤审批锚变量；`init` 的架构占位改 draft、生成工作流固定 checkout 并 `persist-credentials: false`、tooling 被忽略时给 manual action；CLI 加 `--version`；文档补 frontmatter 与 ADR 索引、修 README 旧口径。证据：本地 `pytest`（默认与 `PROJECT_MEMORY_REQUIRE_OPENSSL=1` 各 400 passed / 3 skipped）、`audit --scope current`（0/17/19，14 篇）、`sync-tooling` dry-run（0 added/changed/extra）、`python -m build` 产出 1.1.0 wheel/sdist 且 METADATA 与 `project_memory/__init__.py` 的版本一致；每条新测试都在改动基线上失败过一次。
