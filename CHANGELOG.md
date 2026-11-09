# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的结构；版本号从 1.0.0 起表示本试点的首个发布门槛。历史以 Git 提交为准。

## [未发布] — 自 `v1.1.0` 起进入 `dev/v1.0` 的改动（代码已自报 `1.2.0`，尚未打 tag）

### 修复

- `build_graph` 遇到 frontmatter 损坏的文档不再整体崩溃，改为跳过并在结果的 `skipped` 中报告路径与原因（合并 `34618ba`，PR #61）。
- `init` 在 Skill 资源目录缺失时显式报错并指引用 editable 安装，不再静默产出半成品工作区（合并 `34618ba`，PR #61）。
- 版本号只有一个来源：`project_memory/__init__.py` 的 `__version__` 修正为 `1.1.0`，`pyproject.toml` 改用 `dynamic = ["version"]` + `[tool.setuptools.dynamic] attr = "project_memory.__version__"`。这是影响已发行制品的真实缺陷——`v1.1.0` 那一份里包元数据写 `1.1.0`、`__version__` 仍是 `1.0.0`，而 `evidence.py` 把 `__version__` 写进签名证据清单的 `generator.version`，清单因此自报错误版本（PR #64）。
- `search` 的输出补上 `skipped` 字段并写进 caveat：frontmatter 解析失败的文档没建节点、也不参与检索，调用方必须看得见。`knowledge-graph` 与 `search-results` 两个 schema 和字段契约同步声明该字段（PR #64）。
- CI 的 openssl 门禁不再静默放行：runner 上探测不到 openssl 时步骤 `exit 1`。原写法只打印一行 “SKIPPED (not passed)” 后成功退出，与 README「发布和 CI 必须让缺 openssl 直接失败」的口径矛盾。2026-11-08 从两个 hosted runner 的 job 日志核实当前都有 openssl（ubuntu 3.5.5、windows 3.5.9），所以该分支在现有镜像上不会触发；将来镜像去掉 openssl 时门禁会变红，而不是假装通过（PR #64）。
- `test-run` 的子进程环境把 `PROJECT_MEMORY_APPROVAL_ANCHOR` 及其 `_JSON` 变体也当作凭据类变量剥离并拒绝注入；此前名单只覆盖 `PROJECT_MEMORY_TRUST_ANCHOR`（PR #64）。
- 跨进程记录丢更新：`coordination._mutate` 的乐观 revision 循环、审计账本追加与迁移此前都是「读全部 → 改 → 写全部」，两个进程同时写同一记录会丢掉一方的更新。现在统一走 `common.record_lock`：锁文件按 `sha256(normcase(realpath))[:16]` 命名放在 `.project-memory/cache/locks/`，POSIX 用 `fcntl.flock`、Windows 用 `msvcrt.locking`，线程内可重入，10 秒超时后失败而不是无限等待；锁文件永不删除，避免「删锁即解锁」的竞态（PR #65，cherry-pick `fa3bb38`、`8a44914`）。
- 移植过来的锁在 POSIX `fork` 下互斥失效：子进程继承父进程的 `_lock_holds` 线程局部可重入计数，于是直接走可重入分支、根本不抢锁（CI ubuntu 实测探针报 `acquired=True`，本该超时）；同时继承的锁描述符会让 `flock` 在父进程被杀且没解锁之后继续存活，因为 flock 挂在 open file description 上，只有引用它的描述符全部关闭才消失。新增 `_after_fork_child` 并用 `os.register_at_fork(after_in_child=...)` 注册：在子进程里关掉继承的描述符、清空登记与可重入计数，父进程自己的持有不受影响。这是 Windows 单平台测试看不到的缺陷——Windows 的 `multiprocessing` 用 spawn，线程局部状态天然是新的（PR #65）。
- 写入前的仓库边界：`normalize_repo_relative` / `ensure_inside_repo` 在任何写入之前做词法拼接、逐级已存在父目录与 realpath 三重检查，Windows junction/reparse point（tag `0xA0000003`）按链接处理，不再允许绝对路径、盘符、`..` 或链接把写入目标带出 `--repo`（PR #65，cherry-pick `47ef9d8`）。
- 普通 `pip install` 之后 `init` 必然失败：wheel 里没有 `skill/`，而 bootstrap 只查仓库根的 `skill/project-memory`，所以此前 README 只能写「只支持 editable 安装」。新增 `setup.py` 的 `build_py` 钩子把同一棵 canonical `skill/` 复制进 `project_memory/_skill/`，`resolve_skill_source` 优先仓库树、回退包内副本；构建时源树缺失则 `SystemExit`，不产出装得起却 `init` 不了的 wheel（PR #65）。
- sdist 清单漏目录：`python -m build` 先产 sdist 再从 sdist 构建 wheel，而第一版 `MANIFEST.in` 没有 `examples/`，`ProjectMemoryTest.setUp` 要读 `examples/issue-325.json`，从解压的 sdist 跑测试实测 75 failed / 367 passed。补齐后同一套测试在 sdist 里 442 passed / 3 skipped；CI 的 `packaging` 作业现在真的解压 sdist 跑全量 pytest，用行为而不是清单字符串证明完整性（PR #65）。
- `init` 生成的 `.project-memory/.gitignore` 补 `approvals/`：`approval attach` 写出的本地记录是发布到 `approvals` 分支前的暂存，不该弄脏工作区（PR #65）。

### 变更

- CI 测试矩阵从单一 `windows-latest` 扩展为 `ubuntu-latest` + `windows-latest`（`fail-fast: false`），关闭 Linux/`fcntl` 路径从未被门禁覆盖的空白；必需状态检查上下文随之改为 `pytest (ubuntu-latest)`、`pytest (windows-latest)`、`approval`（合并 `34618ba`，PR #61）。
- 审批信任锚轮换为 `ANCHOR-PROD-20261108`，`ANCHOR-S3-EXERCISE-20261031` 进入 `revoked_anchor_ids`；CI secret 已同步。PR #61、#62 是首批经真实签名审批合并的 PR。
- CLI 新增 `--version`，打印 `project-memory <__version__>`，用于确认装的是哪一份（PR #64）。
- `init --profile full` 生成的架构总览占位稿改为 `status: "draft"`：未核实内容的骨架不能自称 current 知识，提升为 `current` 仍由人做。init 报告在 `.project-memory/tooling` 被仓库忽略规则排除时新增一条 manual action，说明生成的审计工作流取不到这份副本；生成的工作流模板把 `actions/checkout` 固定到 `v4.4.0`（与本仓 CI 同一提交）并加上 `persist-credentials: false`（PR #64）。
- 文档口径：`docs/ARCHITECTURE.zh-CN.md`、`docs/OPERATIONS.zh-CN.md`、`docs/TUTORIAL.zh-CN.md` 补齐 frontmatter（显式 `status: current` 与 `last_verified_at`），`docs/TEST_REPORT.md` 按正文自述标成 `kind: evidence` + `status: historical`，因此不再计入 `--scope current`；`docs/decisions/README.md` 补全 8 篇 ADR 的索引表；README 修正「tag 触发路径要等第一个 `v*` tag 才算实测」的旧口径，并补 `--version`、知识索引与 ADR 索引导航。补齐后 `audit --scope current` 实测 high 0 / medium 17 / low 19（14 篇当前文档；此前为 0 / 18 / 25，15 篇）（PR #64）。
- Skill：`SKILL.md` 的 CLI 自检步骤补 `--version` 与 Windows 解释器说明（Git Bash 要先设 `PYTHONUTF8=1`，`python3` 可能是 Store 占位别名）；仓库内已安装的 `.agents/skills/project-memory/` 同步为逐字节一致（PR #64）。
- 版本号推进到 `1.2.0`，唯一来源仍是 `project_memory/__init__.py` 的 `__version__`，`pyproject.toml` 保持 `dynamic`（PR #65）。
- 启动口径改为启动器优先：pip 安装后用原生 `project-memory`；`PYTHONPATH=.project-memory/tooling python3 -m project_memory` 只适用于没有 pip 安装本项目的解释器（CI、离线）。两者混用会让 `sys.path` 上出现两份同名包，触发 ADR-0005 的防篡改守卫并 exit 3——那是设计行为，不是故障。README 与 `SKILL.md` 同步，`.agents` 副本逐字节一致（PR #65）。
- README 修掉与 PR #64 矛盾的 openssl 口径：第二道门槛先探测 openssl，探测不到就 `exit 1` 直接失败，不再写「打印跳过」（PR #65）。
- `docs/OPERATIONS.zh-CN.md` 的发布构建节补构建输入说明：`MANIFEST.in` 为什么是承重墙、必须覆盖哪些目录、`setup.py` 钩子与 `resolve_skill_source` 的分工，以及漏料会在 `packaging` 作业变红而不是等用户安装后才报错（PR #65）。
- `.gitignore` 补 `build/`、`dist/`、`*.egg-info/`，构建产物不再弄脏工作区（PR #65）。

### 新增

- 仓库自接入：`init` 补齐 `.agents/skills` 安装、`docs/INDEX.md`、PR/Issue 模板、CODEOWNERS 示例，以及 `项目记忆审计` 工作流（跑本仓自身源码，`--fail-on high`，非必需检查）；`docs/CURRENT_STATE.md` 刷新到实测事实（合并 `b2c9e79`，PR #62）。
- CI 新增 `packaging` 作业（ubuntu + windows，`fail-fast: false`，非必需状态检查）：`python -m build` → 断言 wheel 内含 `project_memory/_skill/project-memory/SKILL.md` → 干净 venv `--no-index` 装 wheel → 对新 git 仓库跑 `init --install both` → 用原生启动器跑 `audit --scope current --fail-on high` 与 `search`；ubuntu 上再解压 sdist 跑全量 pytest。venv 步骤先离开检出目录，否则 cwd 里的源码包会与 site-packages 副本同名并触发 B5A 守卫（PR #65）。
- 新增 `setup.py` 与 `MANIFEST.in` 两个构建输入，wheel 与 sdist 都自带 Skill 资源（PR #65）。

### 测试

- 新增回归固定：含冒号的任务 ID 走 `path_component` 净化、净化后同名冲突失败关闭（该行为自 `v1.1.0` 即存在，`common.py` 的 `path_component`，本轮只补测试，不是修复）；图谱坏 frontmatter 与 init 缺 Skill 资源两项均先在基线上做过负对照（合并 `34618ba`，PR #61）。
- PR #64 新增并全部做过基线负对照（改动前失败、改动后通过）：版本单一来源三项结构断言与 `--version` 输出、`search` 暴露 `skipped`、审批锚环境变量被过滤、init 生成的架构稿为 draft、生成工作流的 checkout 固定与 `persist-credentials`、tooling 被忽略时的 manual action、CI openssl 步骤 `exit 1`。
- PR #65 移植 `tests/test_record_lock_race.py` 与 `tests/test_repo_boundary.py`（632 行，与 PR #59 head 逐字节一致），用真实 `multiprocessing.Process` 竞争、Barrier 放在临界区内。负对照：保留新的 `common.py`（helper 存在）、只回退三个调用点文件，19 项行为断言在基线失败。第一版负对照只产生 ImportError，不构成行为证明，已废弃重做。
- fork 继承缺陷的负对照在 Linux 上真跑过，不靠推断：WSL Ubuntu（Python 3.14.4、git 2.53.0）里两份副本只差一行——诱饵把 `os.register_at_fork` 注册删掉，其余逐字节相同。把启动方式强制成 `fork` 后，修复版 10 项全通过，诱饵版 2 项失败，其中一项正是 CI ubuntu 上那条 `assertFalse(outcome['acquired'])` → `AssertionError: True is not false`。新增的 `test_forked_child_inherits_neither_the_hold_nor_the_descriptor` 直接用 `os.fork()`，因此不受 `multiprocessing` 默认启动方式影响：Python 3.14 的 Linux 默认已改成 `forkserver`（实测），同一条诱饵在默认方式下只失败 1 项，强制 `fork` 后失败 2 项；CI 用的是 Python 3.12，默认仍是 `fork`。该用例在没有 `fork` 的平台上 skip。
- PR #65 新增 `tests/test_packaging.py` 6 项：Skill 源解析三态（仓库树优先、包内回退、两处都缺时仍报出查找路径）、构建钩子的复制目标与 bootstrap 回退目录一致、缺源树 fail-closed、清单覆盖构建与测试所需目录；另加一项断言 `init` 生成的 gitignore 含 `approvals/`。诱饵负对照：把生成的 gitignore 模板换成不含 `approvals/` 的非空诱饵，4 failed / 142 passed，恢复后 6 项通过。诱饵脚本第一版因转义层（JSON→bash→Python）在写入前就抛错、根本没跑起来，已用 `chr(92)` 构造字面量修正。
- PR #65 端到端实测：`python -m build` exit 0（wheel 191344 B、sdist 386855 B、sdist 124 个文件）；干净 venv `--no-index` 装 wheel 后 `--version` 报 `project-memory 1.2.0`、对新 git 仓库 `init --install both` exit 0、原生启动器 `audit --scope current --fail-on high` 与 `search` 均 exit 0；仓库与解压 sdist 两处各跑全量 pytest，均 442 passed / 3 skipped / 20 subtests、exit 0。

同期在 v0.3 线 `feat/v0.3-goal-memory` 上合并的 PR #60（merge `19a6ce6`：仓库边界、记录锁、图谱容错、init 显式失败）不在 `dev/v1.0` 历史内，其图谱与 init 两项已由 PR #61 移植，仓库边界与记录锁两项已由 PR #65 从 PR #59 cherry-pick 移植，四项至此全部进入主线。PR #59（分支 `fix/concurrency-and-path-boundaries`）仍然开着、由另一会话负责，本批改动不触碰它；落地后它与主线构成被取代关系，是否关闭由所有者决定。

## [1.1.0] — 2026-11-04（已发布：Tag `v1.1.0`、GitHub Release 与 6 枚公开制品）

本版汇总自 `v1.0.0` 以来进入 `dev/v1.0` 的全部能力：签名审批质量门禁（S3）与发布制品来源证明（S4）。功能面为新增与加固，CLI 既有入口与数据格式向后兼容。

### 新增 — 审批与 CI 质量门禁（S3）

- B-7：CI 审批门禁加固，拒绝由 PR 自身控制的验证器（合并 `77052bf`，PR #50）。
- B-8：签名审批事件，审批身份绑定仓库外信任锚（合并 `c3dea2a`，PR #49）。
- B-9：从 GitHub API 复核 PR 的 CI 结果，作为外部证据而非本地自述（合并 `999713b`，PR #47；行为文档同步 `187f49d`，PR #48）。
- B-10：默认分支启用必需状态检查 `pytest` 与 `approval`，`strict=true`、`enforce_admins=true`；`approvals` 孤儿分支承载审批记录。

### 新增 — 发布制品与来源证明（S4）

- S4-1：绑定 commit 与 tree 的签名证据清单（合并 `40d3f1d`）。
- S4-2：信任锚生命周期（ADR-0008）与 `verify` 时的仓库身份复检（合并 `9aa6af4`，PR #54）。
- S4-3：`release` 工作流构建源码归档、sdist、wheel、`sha256sums.txt`、`BUILD-INFO.json` 与 build provenance attestation；不创建 tag、不发布 Release、不读取仓库 secret（合并 `cfdd848`，PR #55）。已在 GitHub-hosted runner 上真实干跑一次（run `41324143240`）。

### 变更 — CI、可移植性与测试

- 第三方 Action 固定到不可变提交 SHA（合并 `617cdd9`，PR #44）；合入 `dev/v1.0` 的 push 同样触发门禁（合并 `87600d7`，PR #45）。
- `verify` 的输入路径按 `--repo` 解析，不再依赖当前工作目录（合并 `8510919`）。
- 负对照强化：非空诱饵目录与 `findings-file` 覆盖（合并 `165fa55`、`9075012`）。
- 7 个 ADR 补齐元数据（合并 `1eaa3f4`）；文档与实现对齐并新增试点章程（合并 `81c5531`）。

### 已知边界与发布状态（核查日期 2026-11-04）

- 发布状态：`v1.1.0` 的 annotated tag、GitHub Release（id 433549523，`published_at 2026-11-04T05:37:01Z`）与 6 枚制品已发布并公开可下载；`v1.1.0` 与 `v1.0.0` 两个 tag 都未签名，`v1.0.0` 的 Release 仍没有资产。
- `v*` tag 推送触发的发布构建已实测一次：run `41763116854` 绑定 `4918b86`，产物与 attestation 随 Release 公开、可逐件匿名复算；来源证明不等于外部采信，也不证明那个提交被独立真人复核过。
- 跨主机制品字节不可复现：`git archive` 在 `core.autocrlf=true` 的 Windows 检出与 Linux CI 上逐文件行尾不同，以 CI 构建为权威。
- `release` 工作流仍引用一个 node20 时代的 `actions/upload-artifact` 固定 SHA。GitHub 已于 2026-09-23 移除 Node20，旧 pin 被强制跑在 Node24 上并每次留一条 warning annotation；实测没有兼容性故障，本项目据此决定不再重固定、也不再扩大 Actions 维护范围。
- `audit` 是本地防篡改检测与文档一致性提示，不构成对外可采信的审计留痕；`approved_by` 仍是 `claimed_unverified`。

## [1.0.0] — 2026-10-29

### 发布门槛（R1）

- Goal 的必达判据集合为空时 fail closed：`evaluate` 返回 `satisfied=false`、`evaluation_status=insufficient_evidence`、`no_required_criteria=true`；`goal show` 仍可读并给出同一问题标记；`transition --to achieved` 被拒绝并写入 `goal_achieved_unsatisfied` 审计。
- 测试期 openssl 开关：缺失 openssl 时默认仍可 skip；设置 `PROJECT_MEMORY_REQUIRE_OPENSSL=1`（`true`/`yes` 亦可）后签名测试直接失败，发布/CI 必须开启。
- 契约同步：`docs/ARCHITECTURE.zh-CN.md` §5 的 schema 计数与说明、`verification-record.schema.json` 的 `goal_criteria_sha256` 描述、新增 `audit-ledger.schema.json`。
- 新增 `fixtures/b5b/README.md` 与 `evidence/B5B/README.md`（混合行尾、NUL 日志、校验方法；不重写历史证据）。
- 版本号改为 `1.0.0`。`v1.0.0` tag 与 GitHub Release 由发布者在人类 GO 后创建。

### B0 — 可移植仓库身份（ADR-0001，合并 `a70ad19`）

- 执行收据/快照绑定仓库身份（规范化远端 + 根提交）而不是绝对路径；同一仓库的不同 clone 可互认。

### B1 — 进程内验签（ADR-0002，合并 `15f4b3c`）

- 签名验证不再通过 PATH 查找外部 openssl；验签在进程内完成，缺失信任锚时 fail closed。

### B2 — 执行来源与内容完整性分离（ADR-0003，合并 `5a5abdd`）

- 有效签名不能包装手写收据；收据需要受保护启动器生成的执行 attestation 或已签名人工例外；仅 `locally_observed` 保持不可升级为独立验证通过。

### B3 — 判据定义摘要（ADR-0004，合并 `1930fa5`）

- `goal_criteria_sha256` 绑定判据定义（`id`/`statement`/`required`），追加证据不再使已签名验证失效；旧摘要格式在判据不变时继续接受。

### B4 — 审计链与 Goal 状态可信度（ADR-0007，合并 `85bf6a0`）

- 执行审计改为 1.3 哈希链（`seq`/`prev_hash`/`entry_hash`），`audit verify` 从 genesis 重算。
- `achieved` 需要仓库外 anchor 签名的 checkpoint（`audit/head.json`）；Agent 无签名路径。
- `goal show`/`evaluate` 输出 `effective_status`/`status_trusted`/`status_problems`，raw `status` 只作声明。

### B5A / B5A.1 — CLI 启动隔离（ADR-0005，合并 `4ad3a3b`）

- 新增原生 OS 包装器（`bin/project-memory`、`bin/project-memory.cmd`）与绝对路径启动脚本，先以 `-I -P` 隔离解释器再导入受信包；移除 pip `module:function` console script。

### B5B — `test-run` 默认拒绝未隔离执行（ADR-0006，合并 `c49a436`）

- `test-run` 必须显式选择 `--allow-local-untrusted` 或 `--trusted`；无 flag 或双 flag 均 exit 3，不产生快照/收据、不执行命令。
- `--trusted` 失败（如 WSL2 不可用）返回 `BLOCKED`，不静默回退 local。

### H1 — pytest 收集范围（合并 `3ee7afe`）

- `pyproject.toml` 的 `testpaths=["tests"]`，避免把 `evidence/` 下历史探针当作测试收集。

### 已知边界

- **B5A 裸 `-m` 入口**：`python -m project_memory` 在 `sys.path` 已被同名包占据时不提供保护；受支持入口是原生包装器或 `python -I -P -m project_memory`。
- **B5B 库层默认**：默认拒绝在 CLI `test-run` 层；库函数 `execution.run_command` 仍默认本地执行并标记 `local_untrusted`，调用方需自行选择隔离。
- **openssl 开关**：只影响测试；默认关闭时缺 openssl 会 skip，skip 不等于通过；发布/CI 必须设 `PROJECT_MEMORY_REQUIRE_OPENSSL=1`。
- **B5B 清单行尾**：`evidence/B5B/run-20261029T015035Z/sha256sums.txt` 记录的是生成时字节，含混合行尾与两个 NUL 日志；不同检出下的 `sha256sum -c` 可能失败，需逐文件按字节核对（见 `evidence/B5B/README.md`），不得重写历史证据。
- **生产 anchor**：`anchor-a` 的端到端 checkpoint 签名尚未在本仓库内验证；测试使用测试密钥并 patch `authority.load_anchor`。
- **B4 威胁边界**：本地 hash 链不能防御能重算整条链的攻击者；权威性依赖仓库外 anchor 签名。anchor 私钥被攻破后签名保证失效。

### 安装

```bash
python3 -m pip install -e .
# 或在目标仓库内安装 Skill 与工具：
python3 -m project_memory init --repo /path/to/repo --install both
```

运行时不需要 openssl 或第三方库；语义检索是可选依赖（`pip install -e '.[semantic]'`）。

### 回滚

回滚单个里程碑优先用 `git revert -m 1 <merge-commit>` 生成新的回滚提交，不要改写共享历史：

| 里程碑 | 合并提交 | 回滚后果 |
|---|---|---|
| R1 | 本分支合并提交（发布时补） | 恢复空必达可被判 satisfied、openssl 缺失可静默 skip、版本回到 0.1.0/无 CHANGELOG |
| B4 | `85bf6a0` | 失去审计链/签名 checkpoint；`achieved` 退回仅本地声明，旧代码仍能读链式 JSONL |
| B5B | `c49a436` | `test-run` 无 flag 时重新默认为本地执行（不安全），只打印警告 |
| B5A | `4ad3a3b` | 恢复按 `sys.path` 解析的入口，同名包顶替风险回归 |
| B3 | `1930fa5` | 恢复整份判据（含证据）摘要，追加证据会使旧签名失效 |
| B2 | `5a5abdd` | 恢复仅凭收据完整性放行，手写收据可被签名包装 |
| B1 | `15f4b3c` | 恢复外部 openssl 查找，PATH 可影响验签器 |
| B0 | `a70ad19` | 收据重新绑定绝对路径，跨 clone 不可用 |

回滚审计文件时：恢复到迁移前副本会使链变为 `valid_unanchored`（或验证失败），不会静默恢复信任；删除 `audit/head.json` 会立即把 `achieved` 降级为 `achieved_unverified`。
