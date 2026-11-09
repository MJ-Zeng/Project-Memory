---
id: "DOC-CURRENT-STATE"
kind: "canonical"
title: "Project Memory 当前状态"
status: "current"
owner: "MJ-Zeng"
updated_at: "2026-11-09"
last_verified_at: "2026-11-08"
---

# Project Memory 当前状态

## 一句话结论

`v1.2.0` 已正式发布：Tag、GitHub Release 与 6 枚公开可下载的制品（含构建来源证明）都已就位，普通 `pip install` 之后 `init` 可用，跨进程记录锁与写入前仓库边界已进主线；可用于团队内部的记忆记录、跨会话交接与构建来源证明，但它不能作为对外可采信的审计依据，也不证明批准来自独立真人。上一版 `v1.1.0` 的 wheel 缺 Skill 资源、装完 `init` 必失败，那个缺口在 `v1.2.0` 关闭。发布后主线 `dev/v1.0` 会继续前进，本文的发布事实以 tag 为锚，不维护随合并移动的主线 SHA。下列远端事实的核查日期是 2026-11-09，保护与平台配置随时可由仓库管理员改动。

## 当前发布事实

- 当前发布基线：`v1.2.0` 的 annotated tag 对象 `202b496decf3176984d0beeff9620316e99a2263` 剥皮指向 `7d4ae59d7dd92bd89ed766acf8a734e8c162dd2a`（PR #65 的 merge 提交，树 `ae74fac640f82ffd56cc3959ad73d6e80a176a11`，与该 PR 被批准 head `0bbeb13` 的树逐字节相同）。GitHub Release [`v1.2.0`](https://github.com/MJ-Zeng/Project-Memory/releases/tag/v1.2.0)（id 438757506）已发布：`draft=false`、`prerelease=false`、`published_at 2026-11-09T04:58:07Z`，挂 6 枚资产 = `attestation.json`、`BUILD-INFO.json`、`project-memory-7d4ae59-source.tar.gz`、`project_memory_skill-1.2.0-py3-none-any.whl`、`project_memory_skill-1.2.0.tar.gz`、`sha256sums.txt`。发布审批为 `APR-2349a97019f2`（Agent 按所有者明确指令签发，记录 statement 已写明），经 CI `approval` 门禁验签通过后合并。
- 上一版发布基线（历史，保留不改）：`v1.1.0` 的 annotated tag 对象 `a4a1a184e511e6a4e018409e3a99eec5cd06f28a` 剥皮指向 `4918b86466323425ca58894f77dc7955a6122a3d`（PR #57 squash 合并，树 `c7530a01d9b2a3775eb362f3e61b663c48c743f3`）。Release `v1.1.0`（id 433549523）`published_at 2026-11-04T05:37:01Z`，同样 6 枚资产。**那一版的 wheel 里没有 Skill 资源，普通 `pip install` 之后 `init` 必然失败**，且包元数据写 `1.1.0` 而 `__version__` 仍是 `1.0.0`；两个缺陷都在 `v1.2.0` 关闭。`v1.1.0` 与 `v1.2.0` 之间进入主线的是 PR #61（图谱容错与 init 显式失败移植、CI 双平台矩阵）、PR #62（仓库自接入）、PR #63（发布后口径对齐）、PR #64（独立审核修复批次）与 PR #65（打包可用性与并发/边界加固）。
- 版本标签：`v1.0.0`、`v1.1.0` 与 `v1.2.0` 都是 annotated tag，均未签名。`v1.2.0` 的 tagger 是本机 git 身份（`LAPTOP-KNMD5U8F\ZMJ <2427474674@qq.com>`），tag 正文写明治理配置与 tag/Release 由所有者交 Agent 判断、审批记录由 Agent 依所有者明确指令代签，不冒充所有者本人操作 GitHub 审查。`v1.0.0` 原样保留：tag 对象 `c96b871f7753c9a311d5884e33245e93cf8f48f1` 剥皮指向 `f033a6c517cfde3eebb586b07f770d94b2d2c3b7`，其 Release 仍没有资产。
- 测试门槛：`v1.2.0` 的发布提交 `7d4ae59` 上，本机默认运行与设置 `PROJECT_MEMORY_REQUIRE_OPENSSL=1` 运行均通过全量测试（2026-11-09 本地 Windows 实测：两次均 442 passed / 4 skipped / 20 subtests，exit 0；3 个符号链接用例因无法创建链接而 skip，fork 继承用例在没有 `fork` 的平台上 skip）。同一提交在 CI 上独立跑过双平台矩阵：PR #65 head 的 run `42561326362` 与合并后主线的 run `42562511655`，`pytest (ubuntu-latest)`、`pytest (windows-latest)`、`packaging (ubuntu-latest)`、`packaging (windows-latest)` 四个 job 全部 success，`项目记忆审计` 的 knowledge 也 success（run `42562511638`）。补 fork 回归之前曾在解压 sdist 里跑过同一套测试：442 passed / 3 skipped，exit 0；上一版记录为 PR #64 head 的 400 passed / 3 skipped。具体 skip 数随环境与平台变化。CI 的 `test` 工作流自 PR #64 起在探测不到 openssl 时 `exit 1`，不再打印 “SKIPPED” 后成功；2026-11-08 从两个 job 的日志核实 hosted runner 当前都带 openssl（ubuntu job `128715969809` 报 3.5.5，windows job `128715970002` 报 3.5.9），因此该失败分支在现有镜像上不会触发。CI 双平台矩阵的价值本轮又兑现一次：run `42559299111` 的 ubuntu 抓到了 Windows 看不见的 fork 互斥缺陷（详见下文 PR #65 条目）。
- 发布证据：在干净检出上，证据包完整性检查 24/24 通过（2026-11-04 核查结论，本次未重跑）。
- 发布构建：`release` 工作流产出源码归档、sdist、wheel、`sha256sums.txt`、BUILD-INFO.json 与 GitHub artifact attestation，**已在 GitHub-hosted runner 上真实跑过三次**：`workflow_dispatch` 干跑 run `41324143240`（BUILD-INFO.json 记 `generated_at 2026-11-01T16:01:31Z`，绑定提交 `cfdd848d78cd476e3ace1e83be95a11727a7ef84`、树 `9382d8893fbed36b7cd84dc705a659d95c2f0a86`、`ref refs/heads/dev/v1.0`）、`v1.1.0` tag 推送触发的 run `41763116854`（`event: push`、job `build` 16 步全绿、绑定 `4918b86…`），以及 `v1.2.0` tag 推送触发的 run `42563896275`（`event: push`、job `build` `128986077090` 的 13 个步骤全部 success，含 `Checksum self-check` 与 `Attestation self-check`；BUILD-INFO.json 记 `generated_at 2026-11-09T04:49:42Z`、`ref refs/tags/v1.2.0`、绑定提交 `7d4ae59…`、树 `ae74fac…`、Python 3.12.16、build 1.6.1）。
- `v1.2.0` 制品的独立复核（2026-11-09，Agent 实测，非人工验证）：从 workflow artifact 下载 6 个文件后 `sha256sum -c sha256sums.txt` 四条全 OK、exit 0；`attestation.json` 是 DSSE bundle，`payloadType application/vnd.in-toto+json`、`predicateType https://slsa.dev/provenance/v1`，5 个 subject（4 枚 dist 件加 `sha256sums.txt`）的 sha256 摘要与下载件逐一相符。再从**公开 Release 下载地址**匿名取回 wheel 与 `sha256sums.txt`，`cmp` 与 CI artifact 逐字节相同。wheel 内 METADATA 报 `Name: project-memory-skill`、`Version: 1.2.0`、`Requires-Python: >=3.11`，包内 `__version__` 同为 `1.2.0`，50 个条目中 Skill 树占 29 个且含 `SKILL.md`，POSIX 与 Windows 两个启动器脚本都在。**发布制品本身已端到端实测可用**：干净 venv `pip install --no-index` 装该 wheel → `project-memory --version` 报 `project-memory 1.2.0`（exit 0）→ 对新 git 仓库 `init --install both`，`.agents/skills/project-memory/SKILL.md`、`.claude/skills/project-memory/SKILL.md`、`.project-memory/tooling/project_memory/__init__.py`、`.project-memory/config.json` 四项全部生成 → 原生启动器 `audit --scope current --fail-on high`（exit 0，high 0 / medium 0 / low 5，4 篇）与 `search`（exit 0）。四枚 dist 件的 SHA-256：wheel `d453fcece1dac2598eee2d19c30859e58186d52aaee443cad6df8d64135f7044`、sdist `fe56aca9dab9cfa1b97331e565061c74593a02fe556cd51cf6267c9740866819`、源码归档 `3aca912c03328634d357eece6c35f6c00b673002a6e13ee2de29ed5b42821352`、BUILD-INFO.json `a8337d03eec5f6c7307f2868c9d1846283bd7d40f1ef50e1b4b763498abee0bc`。
- 发布制品里的一处文档滞后（已知，不重发）：`v1.2.0` 的 tag 打在文档对齐之前，所以该 tag 树里的 `CHANGELOG.md` 抬头仍是 `## [未发布] …尚未打 tag`，随 tag 构建的 sdist 与源码归档都带着这份滞后文本（实测解包读取）。wheel 的 METADATA 只有 9 行、不含 README 或 CHANGELOG 正文，所以 pip 安装路径看不到它。tag 与 6 枚制品已公开且经独立复核，移动 tag 会破坏已下载者的可复算性，因此**不重打 tag、不重发制品**：对齐后的 CHANGELOG 由 PR #66 落在主线，Release 正文也写明制品内 CHANGELOG 抬头是 tag 前快照、权威发布记录以 Release 页与主线 CHANGELOG 为准。顺序约束已写进 `docs/OPERATIONS.zh-CN.md`：下次发版先落 CHANGELOG 再打 tag。
- `v1.1.0` 的来源证明（历史，2026-11-04 结果，本次未重跑）：产物与来源证明已随 Release `v1.1.0` 公开，本方对 6 枚资产逐件匿名下载后复算 SHA-256，与本地实测逐字相同；`sha256sums.txt` 的 4 条对得上 4 枚 dist 件；`attestation.json` 是 sigstore bundle v0.3 + SLSA provenance v1，5 个 subject 摘要与下载件一致，`runDetails.builder.id` = `…/release.yml@refs/tags/v1.1.0`，证书签发方 `CN=sigstore-intermediate,O=sigstore.dev`。所以 1.1.0 的来源证明状态是**已生成、公开、可第三方独立复算**。干跑那次的证明只属于 `cfdd848`，不能归属到旧发布：`v1.0.0` 原始 Tag 剥皮后指向另一个提交 `f033a6c517cfde3eebb586b07f770d94b2d2c3b7`。签发能力与验证能力要分开说：attestation 只能由 GitHub-hosted runner 用该 run 的 OIDC 令牌签发（干跑那次的签名证书里 runner 环境为 `github-hosted`、令牌签发方为 `token.actions.githubusercontent.com`），本机不能生成、也不得伪称生成；验证侧任何人可匿名下载 Release 资产复算摘要，在线验签走 attestations 端点（按制品摘要索引，查询串要带 `sha256:` 前缀，只给 64 位十六进制会回 404），只有 workflow artifact 才需要仓库读取凭据且保留 90 天。跨主机字节不可复现仍然成立：`git archive` 在 `core.autocrlf=true` 的 Windows 检出与 Linux CI 上逐文件行尾不同，以 CI 构建为权威。发布构建按设计不创建 Release：`v1.2.0` 的 tag、Release 与挂资产由 Agent 执行，依据是所有者把治理配置与 tag/Release 的决定权明确交给 Agent；工作流本身仍然不写回仓库、不读 secret。

## 主线加固与审批链（2026-11-08 起）

- 主线决策：`dev/v1.0` 为唯一主线（所有者 2026-11-08 拍板）；v0.3 线 `feat/v0.3-goal-memory` 作 fallback。
- PR #60（v0.3 线，merge `19a6ce62dbd168009e2cc063f2c7b52f01fe63a8`）：仓库边界、跨进程记录锁、图谱容错、init 显式失败四项加固。
- PR #61（主线，head `e8a4f956f194360da59921ae9c43770cffef0534`，merge `34618ba`）：M2/M4 移植到 v1.1，CI 测试矩阵覆盖 ubuntu+windows；`test` run `42443903390` 双平台 success。
- 审批锚轮换：新锚 `ANCHOR-PROD-20261108`（rsa-sha256，公钥 DER SHA-256 `e07ef677d17cc97924f153a759f4c4d2b15168098970c7bdf5a8b2fba5c57d34`），吊销 `ANCHOR-S3-EXERCISE-20261031`（演练私钥已于 2026-11-04 销毁）；CI secret `PROJECT_MEMORY_APPROVAL_ANCHOR_JSON` 于 2026-11-08 更新。新私钥仅存所有者本机用户目录，不在仓库、不入档。
- 首个经真实签名审批合并的 PR：审批 `APR-c2162a31fa50`（Agent 按所有者明确指令签发），记录在 `approvals` 分支 `7da8eb8`；门禁原 run `42443903424` 重跑（attempt 2）success 后合并。
- 分支保护（`dev/v1.0`，2026-11-09 实测）：必需检查五个——`approval`、`pytest (ubuntu-latest)`、`pytest (windows-latest)`、`packaging (ubuntu-latest)`、`packaging (windows-latest)`；`strict=true`、`enforce_admins=true`、`allow_force_pushes=false`、`allow_deletions=false`。两个 `packaging` 上下文是本轮新增（所有者把治理配置交 Agent 判断）：v1.2.0 的核心承诺是「普通 pip 安装可用」，打包不设为必需，将来一个 PR 仍可能带着坏 wheel 进主线。`required_pull_request_reviews` 仍是 `null`，CODEOWNERS 只有 `.github/CODEOWNERS.example`，Ruleset `branch _1`（id 26002815）仍是 disabled、classic 保护在生效。**没有**启用 GitHub 原生 required reviews：那会让所有者每个 PR 都必须点一次批准，与明确要求的「走签批链然后自动完成」冲突；目前的人工批准由仓库外私钥签名的审批记录承载，不是 GitHub 审查 UI。是否改为原生强制由所有者决定。
- 接入补齐：`init` 幂等补齐 `.agents/skills` 安装、`docs/INDEX.md`、PR/Issue 模板、CODEOWNERS 示例与 `项目记忆审计` 工作流；该工作流用仓库自身源码运行（`tooling/` 按既有 `.gitignore` 不入库），`--fail-on high`。
- PR #62（head `46a4d45`，merge `b2c9e79`，审批 `APR-8b4b0b4f3e81`）、PR #63（head `8c2725a`，merge `50ff4fe`，审批 `APR-aee569bf8962`）与 PR #64（merge `e684103`）都走同一条签名审批链：Agent 按所有者明确指令用仓库外私钥签名，记录发布到 `approvals` 孤儿分支，门禁重跑原 `pull_request_target` run 后合并，合并后再核对合并提交的树等于被批准 head 的树。这些审批都是 `scope: commit`。审批记录以 `approvals` 分支本身为唯一来源，本文不维护第二份计数或 head SHA——那类快照每合并一次就过期。
- 本轮独立审核（PR #64，分支 `fix/v1.1-audit-findings`）的结论与修复：唯一 high 是版本双份维护——发布那一份 `pyproject.toml` 写 `1.1.0`、`project_memory.__version__` 仍是 `1.0.0`，而签名证据清单的 `generator.version` 取后者；已改为 `dynamic` 单一来源并加结构守卫。其余修复见 `CHANGELOG.md` 的 `[1.2.0]` 段。审批门禁本身不是空转：`tests/test_b7_ci_second_identity.py` 用一批临时密钥仓库实测 1 条正向（唯一有效记录放行）与 9 组负向——空记录目录、缺失记录目录、记录属于别的提交、`reject` 决定、伪造签名、未配置锚、记录写好后被改写、单一记录模式不受影响、`--require-approve` 在单记录模式被拒绝；锚的过期与吊销由 `tests/test_s4_anchor_lifecycle.py` 覆盖。原列为待办的 M5（接受 ADR）与 M6（批准 Goal）已在 2026-11-09 由所有者明示授权 Agent 代为落盘：8 篇 ADR 全部改为 `accepted`（`approved_by` 为所有者邮箱、`approved_at` 为 2026-11-09），7 个 Goal 由 `proposed` 改为 `approved`。批准记录被工具标为 `approval_authority: claimed_unverified`——它们是「声明」，不是经过独立核验的人工审查。Run/Verify 记录未回填：`.project-memory/handoffs/` 里的 1.1 记录只覆盖 B0/B1/B2 且状态都是 `reported_unverified`，改写成 1.2 执行记录会凭空产生时间戳与来源；对账因此报 7 条 `goal_without_runs`（medium），是准确反映而非新缺陷。ADR-0008（信任锚生命周期）没有对应 Goal，`adrs` 关联不上，保留 1 条 `accepted_adr_unlinked`（low）。
- 「最终可用」批次（PR #65，分支 `fix/v1.1-concurrency-boundaries`，head `0bbeb13`，merge `7d4ae59`，已作为 `v1.2.0` 发布）解决两个真正挡住使用的缺口。其一是普通 `pip install` 之后 `init` 必然失败：wheel 里没有 `skill/`，bootstrap 只查仓库根，所以 README 长期只能写「只支持 editable 安装」。现在 `setup.py` 的 `build_py` 钩子把唯一的 canonical `skill/project-memory` 复制进 `project_memory/_skill/`，`resolve_skill_source` 优先仓库树、回退包内副本，构建缺源树时 `SystemExit`。其二是主线缺跨进程记录锁与写入前边界检查：这两项已在 PR #59 实现并被测试证明，本批以 cherry-pick 搬入三个提交（`fa3bb38`、`47ef9d8`、`8a44914`，作者信息保留），**不改动 PR #59 及其分支**；PR #59 仍开着、由另一会话负责，落地后构成被取代关系，是否关闭由所有者决定。至此 PR #60 的四项加固（仓库边界、记录锁、图谱容错、init 显式失败）全部进入主线。移植不是照搬就算完：PR #59 那份锁在 POSIX `fork` 下互斥失效——子进程继承父进程的可重入计数，直接走进父进程还持着的临界区（CI ubuntu 实测探针报 `acquired=True`，本该超时），继承的锁描述符还会让 `flock` 在父进程被杀后继续存活。本批加 `_after_fork_child` + `os.register_at_fork(after_in_child=...)` 修掉，并在 WSL Ubuntu 上做了只删注册那两行的诱饵负对照：强制 `fork` 启动方式后修复版 10 项全通过、诱饵版 2 项失败。**PR #59 那份实现仍带这个缺陷**，本批不修改它的分支，所有者与该会话需要知道这件事。Windows 单平台测试看不到它，因为 Windows 的 `multiprocessing` 用 spawn；这正是 PR #61 把 CI 扩成双平台的价值。
- 打包完整性是实测出来的，不是推断出来的：`python -m build` 先产 sdist 再从 sdist 构建 wheel，第一版 `MANIFEST.in` 漏了 `examples/`（`ProjectMemoryTest.setUp` 要读 `examples/issue-325.json`），从解压 sdist 跑测试实测 75 failed / 367 passed。补齐后 CI 新增 `packaging` 作业（双平台，自 2026-11-09 起为必需状态检查）真的解压 sdist 跑全量 pytest，并在干净 venv 里离线装 wheel、对新 git 仓库跑 `init --install both`、用原生启动器跑 `audit` 与 `search`。启动口径同时改成启动器优先：pip 安装后再用 `PYTHONPATH` 形式会让 `sys.path` 上出现两份同名包，触发 ADR-0005 守卫并 exit 3，那是设计行为不是故障。

## 预期行为

- 本地执行 `verify` 以退出码 2 结束并记录 `MANUAL_REVIEW_REQUIRED`，这是正确结果，不是故障。
- `achieved` 与 `VERIFIED` 需要仓库外、非当前用户所有且不可写的信任锚；单用户主机上不可达。

## 已知限制

- `approved_by` 只是邮箱声明，记录为 `claimed_unverified`。
- 执行证据与收据只证明内容完整性，不证明由谁生成、由谁提交。
- 签名证据清单只证明锚持有者对「这些文件在这个提交下」负责，不证明文件由受保护执行器产生，也不证明命令真的执行过。
- 沙箱执行依赖 `wsl.exe`，它可被环境变量或 PATH 替换。
- 当前知识审计有 37 条 findings（high 0 / medium 18 / low 19；2026-11-09 在发布后对齐分支与治理收口分支各实测一次，两次一致，`--scope current` 扫 14 篇文档，exit 0）。比 PR #65 head 的 36 条（0/17/19）多 1 条 medium，原因是本文新增的 `v1.2.0` 制品复核条目引用了那枚 DSSE 来源证明制品，它按目录归属算 evidence，于是触发同一条 `reference_authority_mismatch` 启发式——当前状态文档引用 evidence 制品是正当写法，不为清零而改写。该启发式按裸文件名匹配，连描述它的文字也会命中，所以本条不复现那个文件名；计数以最终文本的实测为准。再往前一版是 43 条（0/18/25，15 篇），减少的原因是 4 篇文档补齐显式 `status` 后不再有 `unknown_document_status`，`docs/TEST_REPORT.md` 按正文自述改成 `kind: evidence` + `status: historical` 后不再计入 current（连带它的 1 条 medium 与 2 条 low）。剩下的全是引用解析提示（裸文件名引用、指向 evidence 路径的引用、镜像外引用），不是内容错误；其中 ADR-0005 第 108 行的 `../_project_memory_launcher.py` 被标成「指向仓库之外」是误报——那描述的是包装器从 `bin/` 出发的运行时定位，不是文档链接。没有任何历史或镜像文档被为了清零而改写。
- 跨进程记录锁与写入前路径检查都是**同用户进程间的防误用与确定性逃逸封堵**，不是对抗恶意本地进程的密码学边界：忽略锁的同用户进程拦不住，检查与写入之间被换掉路径组件的 TOCTOU 竞态仍然存在。锁文件放在 `.project-memory/cache/locks/` 且永不删除，删除会重新打开竞态。
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
- 2026-11-09：「最终可用」批次 PR #65。主线基线记录到 `e684103`（树 `ac360787…`，PR #64 合并）；审批记录不再在本文维护第二份计数与 head SHA，改以 `approvals` 分支为唯一来源。落地：wheel/sdist 自带 Skill（`setup.py` 构建钩子 + `resolve_skill_source` 回退）、`MANIFEST.in` 补齐 (`examples/` 漏料实测 75 failed)、CI 新增 `packaging` 作业并真的从 sdist 跑全量测试、启动器优先口径、`init` 生成的 gitignore 补 `approvals/`、版本 `1.2.0`；cherry-pick PR #59 的记录锁与写入边界三个提交，并修掉其中 POSIX `fork` 继承导致的互斥失效。证据：`python -m build` exit 0（wheel 191344 B / 50 个文件，其中 Skill 29 个；sdist 386855 B / 124 个文件）；干净 venv `--no-index` 装 wheel → `--version` 报 `project-memory 1.2.0` → 新 git 仓库 `init --install both` → `.agents`/`.claude`/`tooling` 三处副本齐全 → 原生启动器 `audit --scope current --fail-on high`（high 0 / medium 0 / low 5）与 `search`，全部 exit 0；仓库与解压 sdist 两处全量 pytest 均 442 passed / 3 skipped / 20 subtests、exit 0（此为补 fork 回归前的计数）；`audit --repo . --scope current` 36 条 = 0/17/19、14 篇；`sync-tooling` dry-run 43 unchanged、0 added/changed/extra；WSL Ubuntu 诱饵负对照（只删 `register_at_fork` 注册）在强制 `fork` 下修复版 10 项通过、诱饵版 2 项失败；CI run `42559299111` 的 ubuntu 失败（job `128971975670`、`128971975345`）是 fork 缺陷的基线证据，同 run 的 windows `packaging` 已 success。
- 2026-11-09（同日发布轮）：`v1.2.0` 正式发布，本文改为以 tag 为锚记录发布事实，不再维护随合并移动的主线 SHA。PR #65 经审批 `APR-2349a97019f2` 合并为 `7d4ae59`（树 `ae74fac…` 与被批准 head 逐字节相同），合并后主线双平台矩阵与 knowledge 全绿（run `42562511655`、`42562511638`）；本机在合并提交上复跑两道全量门禁均 442 passed / 4 skipped / 20 subtests、exit 0。打 annotated tag `v1.2.0`（对象 `202b496…`）触发 release run `42563896275`，13 步全绿；建 Release id 438757506 并挂 6 枚资产。制品独立复核与端到端实测见「当前发布事实」节：哈希、attestation subject 摘要、公开下载字节相等、干净 venv 安装后 `init`/`audit`/`search` 全部 exit 0。治理配置按所有者授权把两个 `packaging` 上下文加进必需检查（共五个），未启用 GitHub 原生 required reviews。证据：本文所引 run/job/Release ID 与 SHA-256；`sha256sum -c` exit 0；`cmp` 逐字节相同；本机 pytest 与 `audit --scope current` 实测。本轮所有测量均为 Agent 执行，`last_verified_at` 仍保留 2026-11-08 的人工核查日期，不由 Agent 自行推进。
- 2026-11-09（发布后对齐轮，PR #66）：`CHANGELOG.md` 的 `[未发布]` 落成 `[1.2.0]`；本文补制品下载地址与「发布制品内 CHANGELOG 滞后」条目；README 补版本无关的 releases 链接与 `packaging` 升为必需的口径；OPERATIONS 补发版顺序约束、两次 tag 触发实测与按真实引入时间分开的作业名。证据：`audit --scope current` exit 0（0/18/19，14 篇）、`sync-tooling` dry-run 43 unchanged、`releases/latest` 匿名访问 302 到 `releases/tag/v1.2.0` 且该页 200；本机两道全量门禁与 CI 双平台结果见 PR #66。`last_verified_at` 同样不推进。
