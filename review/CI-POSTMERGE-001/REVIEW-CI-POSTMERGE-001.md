# CI-POSTMERGE-001 独立复核报告（PM-03）

- 任务 ID：`CI-POSTMERGE-001`
- 复核者：PM-03（独立克隆 `pm-pilot-03`，工作分支 `review/postmerge-trigger`）
- 被复核分支：`origin/ci/postmerge-trigger-20261030` @ `43b4131bd5535f496946de01fdc21a73daadd56d`
- 基线：`617cdd90cac96c3619938d96831fcecd2930564f`（`origin/dev/v1.0`）
- 任务卡：`C:/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/PM02_POSTMERGE_TRIGGER_TASK_CARD.md`
- 复核时间（UTC）：`2026-10-30T08:08Z`
- 依据：本报告全部数字均由本机在独立克隆上重算，未采信 PM-02/PM-01 的 handoff 自述；handoff 只作为“待核对的事实清单”使用（见 §7）。

## 0. 结论

**PASS WITH DEVIATIONS**（无阻断问题，2 项非阻断偏差）

- 拓扑、范围、净变化、逐字节一致性、YAML 结构断言、三处负对照、双门槛、审计多重集、对账全部符合任务卡。
- 两处非阻断偏差：① handoff 有 2 行“只含单个空格”的空白行，导致 `git diff --check` 退出码 2；② handoff §3.5 的“new line count (incl trailing empty): 40”表述容易被误读为 40 行（实际 blob 39 行 + 结尾换行）。均不影响 workflow 与门禁。
- **本结论只说明被复核提交满足任务卡与门槛；不等于批准合并，也不代表已在托管 runner 上验证 `push` 触发。**

## 1. 拓扑与范围

```bash
git fetch origin --prune
git rev-parse origin/ci/postmerge-trigger-20261030 origin/dev/v1.0
git rev-list --count 617cdd9..43b4131
git rev-list --merges --count 617cdd9..43b4131
git diff --name-status 617cdd9 43b4131
git diff --numstat   617cdd9 43b4131
```

实测：

| 断言 | 期望 | 实测 |
|---|---|---|
| 候选 SHA | `43b4131…` | `43b4131bd5535f496946de01fdc21a73daadd56d` |
| 基线 SHA | `617cdd9…` | `617cdd90cac96c3619938d96831fcecd2930564f` |
| 提交数 `617cdd9..43b4131` | 2 | **2** |
| merge 提交数 | 0 | **0** |
| 变更文件 | 恰 workflow `M` + handoff `A` | **`M .github/workflows/test.yml`、`A tasks/PM02-postmerge-trigger-handoff-20261030T075914Z.md`** |
| workflow 净变化 | +2/−0 | **`2 0 .github/workflows/test.yml`** |
| handoff 净变化 | +A | `163 0`（新增） |
| 整体 stat | — | `2 files changed, 165 insertions(+)` |

提交链无分叉、无 merge：

```
43b4131 (parent 137f457) docs(ci): hand off CI-POSTMERGE-001 execution record
137f457 (parent 617cdd9) ci(workflow): also run gate on push to dev/v1.0
```

逐提交范围：

- `137f457`：仅 `M .github/workflows/test.yml`。
- `43b4131`：仅 `A tasks/PM02-postmerge-trigger-handoff-20261030T075914Z.md`。

复核期间 `origin/dev/v1.0` 仍为 `617cdd9`（复核结束时再次 `git rev-parse` 确认），基线未移动。

## 2. 内容：除插入两行外逐字节一致

对象取提交 blob（不使用工作树；工作树为 CRLF）：

```bash
git rev-parse 617cdd9:.github/workflows/test.yml   # 89725ff439ff5d1615cc9951295e851bb2076acb
git rev-parse 43b4131:.github/workflows/test.yml   # c45dd4fdf86320274958987859ad8ae10460b61a
git cat-file blob 89725ff > base.yml
git cat-file blob c45dd4f > cand.yml
git diff --no-ext-diff 89725ff c45dd4f
sed '4,5d' cand.yml > cand_minus2.yml
cmp base.yml cand_minus2.yml
```

- 净 diff 只有：

```
@@ -1,6 +1,8 @@
 name: test
 
 on:
+  push:
+    branches: [dev/v1.0]
   pull_request:
     branches: [dev/v1.0]
   workflow_dispatch:
```

- `cmp base.yml cand_minus2.yml` → **exit 0**（逐字节相同）。
- sha256 两边均为 `23eb384871bb0b6f9d34b45bdba0af3c1a834813b88a0d6c4876e79521eb5438`。
- 候选 blob：**41 行、1127 字节、CR=0、最后一个字节 `0a`**；尾部 8 字节 `20 20 20 20 20 66 69 0a`（`     fi\n`），单一结尾换行。
- 基线 blob：39 行、1094 字节、CR=0。
- 插入行位置为第 4–5 行，即 `on:` 块内、`pull_request:` 之前（YAML 映射顺序不影响语义）。

## 3. YAML 结构断言

用 PyYAML 6.0.1 `safe_load` 解析**提交 blob**，独立断言脚本（19 条）：

```bash
C:/SoftWare/Anconda/python.exe assert_workflow.py "original candidate" cand.yml
```

实测：**PASSED 19 / FAILED 0**。关键取值：

| 断言 | 实测 |
|---|---|
| 顶层键含布尔 `True` | `doc keys = ['name', True, 'permissions', 'concurrency', 'jobs']` |
| `True` 的值键集合 | 恰 `{push, pull_request, workflow_dispatch}` |
| `True['push']['branches']` | `['dev/v1.0']` |
| `True['pull_request']['branches']` | `['dev/v1.0']` |
| `permissions` | `{'contents': 'read'}`（无其他键） |
| `jobs` 键 | 恰 `{'pytest'}` |
| `runs-on` | `windows-latest` |
| `timeout-minutes` | `40`（整数） |
| 步数 | 恰 5 |
| `uses` 数量 | 恰 2，均匹配 `^[^@]+@[0-9a-f]{40}( # v[0-9]+\.[0-9]+\.[0-9]+)?$` |
| checkout SHA | `actions/checkout@11d5960a326750d5838078e36cf38b85af677262`（`11d5960a…` 未变） |
| setup-python SHA | `actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065`（`a26af69b…` 未变） |
| 步骤名顺序 | `checkout / setup-python / Install test dependency / Default gate / OpenSSL gate` |
| OpenSSL 门内容 | 含 `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q` |
| 并发组 | `test-${{ github.ref }}` |
| `secrets.` 引用 | 无 |

（`uses` 步骤名按 `owner/repo@sha` 的 repo 段取 `checkout` / `setup-python`，与基线命名一致。）

## 4. 负对照（三处变异，均须 FAILED）

在提交 blob 的临时副本上做三处变异，各自单独运行同一断言脚本：

| # | 变异 | 变异内容 | 结果 | 预期失败断言 |
|---|---|---|---|---|
| 原样 | 候选 | 无 | **19 PASS / 0 FAILED** | — |
| ① | 删除新增两行 | `4,5d`（删 `push:` 与 `branches:`） | **16 PASS / 3 FAILED** | `push_present`、`push_branches_dev_v1.0`、`trigger_keys_exactly_three` 全部 FAILED，其余断言仍 PASS |
| ② | `push.branches` 改 `[master]` | 第 5 行替换 | **18 PASS / 1 FAILED** | `push_branches_dev_v1.0` FAILED（`actual=['master']`） |
| ③ | `permissions.contents` 改 `write` | 第 11 行替换 | **18 PASS / 1 FAILED** | `permissions_contents_read` FAILED（`actual={'contents': 'write'}`） |

结论：断言可被真实缺陷触发，不是恒真；且变异范围精确（②③ 只打掉对应一条），说明断言之间无意外耦合。附加验证：变异①的副本与基线 blob `cmp` 逐字节相同（§2），即“删掉新增两行”确实还原到基线。

## 5. 风险审查

| 问题 | 结论 | 依据 |
|---|---|---|
| 权限是否变大 | **否** | 顶层 `permissions: {'contents': 'read'}` 未改；无 `id-token`/`packages`/`actions: write`；`push` 事件沿用同一最小权限 |
| 是否引入 secret | **否** | 全文件无 `secrets.`；checkout 仍 `persist-credentials: false` |
| 是否引入危险触发 | **否** | 无 `pull_request_target`、无 `workflow_run`；仅 `push`/`pull_request`/`workflow_dispatch` |
| `push` 与 `pull_request` 并发组是否互相干扰 | **不干扰** | 组为 `test-${{ github.ref }}`：push → `refs/heads/dev/v1.0`，PR → `refs/pull/N/merge`，二者不同组，可并行，不会互相取消 |
| 是否重复运行 | **不会重复同一提交** | 合入后仅产生 1 次 `push` 运行（merge commit）；PR 合并前的 `pull_request` 运行针对 `refs/pull/N/merge`，属另一 ref、另一事件，正是本卡要补的“合入后复验” |
| 合并后是否两次跑 | **同一 ref 只跑一次**；但若短时间内连续两次合入，`cancel-in-progress: true` 会**取消较早的 push 运行**（见 §8 残余风险） |
| `workflow_dispatch` 与 `push` 的关系 | **同组** | 在 `dev/v1.0` 上手动 dispatch 与 push 运行同属 `test-refs/heads/dev/v1.0`，`cancel-in-progress: true` 会使二者互相取消（见 §8） |
| Actions 分钟数 | 每合入 1 次额外 Windows 运行（本机实测单门约 2.6 分钟）；计费影响未验证（卡面已列） |

## 6. 门槛与审计（候选 `43b4131` 干净 worktree）

干净 worktree：`git worktree add --detach $TEMP/pm03-cand 43b4131`，复核前 `git status --porcelain` 为空；所有命令执行后 worktree 仍为空（测试与审计不写工作树）。

解释器：`C:/SoftWare/Anconda/python.exe`（Python 3.12.4，pytest 9.1.1）；未使用 Store 别名 `python`。

| # | 项目 | 命令 | 期望 | 实测 | 墙钟 | 退出码 |
|---|---|---|---|---|---|---|
| 1 | 默认门 | `C:/SoftWare/Anconda/python.exe -m pytest -q` | 257 passed / 2 skipped | **257 passed, 2 skipped**（pytest 自报 154.08s） | 154.7s | **0** |
| 2 | OpenSSL 门 | `PROJECT_MEMORY_REQUIRE_OPENSSL=1 C:/SoftWare/Anconda/python.exe -m pytest -q` | 257 passed / 2 skipped | **257 passed, 2 skipped**（pytest 自报 163.24s） | 163.9s | **0** |
| 3 | 审计 | `./bin/project-memory audit --scope current --output audit_cand.json` | 40/0/16/24，`entry_doc_*` 0 | **40 项：high 0 / medium 16 / low 24**；`entry_doc_findings=0`；`docs_scanned=13` | 0.66s | **0** |
| 4 | 对账 | `./bin/project-memory reconcile --fail-on high --format json --output reconcile_cand.json` | exit 0 | **exit 0**；counts `{high:0, medium:16, low:24}` | 0.62s | **0** |

（CLI 通过受信包装器执行：`PROJECT_MEMORY_PYTHON=C:/SoftWare/Anconda/python.exe ./bin/project-memory …`，走 `-I -P` 隔离路径。）

本机 `openssl`：`/ucrt64/bin/openssl`，OpenSSL 3.5.9；门槛 2 走真实执行分支而非跳过分支。

### 6.1 审计与基线逐项一致（多重集）

在基线 `617cdd9` 的独立干净 worktree 上运行同一条审计命令，按 `(severity, code, location)` 做多重集对比：

```
candidate counts: {'high': 0, 'low': 24, 'medium': 16} total: 40
baseline  counts: {'high': 0, 'low': 24, 'medium': 16} total: 40
multisets equal: True
added (cand-base): {}
removed (base-cand): {}
entry_doc_findings: cand 0 / base 0
```

代码分布（两侧相同）：`ambiguous_reference` 14、`reference_authority_mismatch` 14、`broken_reference` 4、`unknown_document_status` 4、`dynamic_artifact_reference` 2、`broken_document_reference` 1、`reference_outside_repository` 1。

附加：审计的 `reference_audit` 次级区块在把 40 位 SHA 归一化后两侧完全相等（`entries`/`summary`/`source`/`manifest_complete` 均相等）；顶层差异仅 `repository_version`（即候选/基线 SHA 本身）。对账两侧 `counts` 与 `state`（`needs_attention`，既存状态）一致，`--fail-on high` 均 exit 0。

## 7. handoff 事实比对

对照 `tasks/PM02-postmerge-trigger-handoff-20261030T075914Z.md`（163 行、LF、CR=0）。

| handoff 陈述 | 独立实测 | 判定 |
|---|---|---|
| 基线 `617cdd9…` | 一致 | 符合 |
| 净变化 `+2/−0`、39→41 行 | 一致 | 符合 |
| `git diff --stat` → `1 file changed, 2 insertions(+)` | 对变更提交 `137f457` 成立（当时尚未含 handoff） | 符合 |
| 父 blob `89725ff…`、候选 blob `c45dd4f…` | 一致 | 符合 |
| 41 行 / 1127 字节 / CR=0 / 尾字节 `20 66 69 0a` | 一致（尾部 8 字节 `20 20 20 20 20 66 69 0a`） | 符合 |
| 候选 blob sha256 `f40f8192…` | 一致 | 符合 |
| YAML 断言 11 条全 PASS | 本复核另用 19 条断言独立重跑，全 PASS | 符合 |
| 负对照删两行 → 2 条 FAILED / 其余 PASS | 独立重跑为 3 条 FAILED（另有独立 `push_present` 断言）/ 其余 PASS；失败项均与 `push` 相关 | 符合（断言集不同，结论一致） |
| “负对照副本与基线 blob `cmp` 逐字节相同” | 独立 `cmp` exit 0 | 符合 |
| 门槛各 257 passed / 2 skipped，exit 0 | 一致（耗时数值不同属正常波动） | 符合 |
| 变更提交 `137f457` 仅含 workflow；handoff 单独提交 | 一致 | 符合 |
| 未建 PR / 未合并 / 未打 tag、未动 `dev/v1.0` | `origin/dev/v1.0` 仍为 `617cdd9`，无 PR 迹象可查到的矛盾 | 符合（PR/tag 状态超出本地可证范围） |
| UTC `2026-10-30T07:59:14Z` | 与文件名一致 | 符合 |

**偏差（均非阻断）**

1. handoff 第 32、108 行为“只含一个空格”的空白行，`git diff --check 617cdd9 43b4131` → **exit 2**（`trailing whitespace`）。不影响 workflow、不影响门禁；仅属提交卫生问题。
2. handoff §3.5 写“new line count (incl trailing empty): 40”。该计数把结尾换行后的空段也算进去；提交 blob 实际是 **39 行**（`wc -l`）/40 个 `splitlines` 片段。原文已注明 `incl trailing empty`，但容易被误读为“40 行”，建议后续 handoff 统一用 `wc -l` 口径。

未发现 handoff 中与实测矛盾的事实陈述；未发现夸大或替审查者下结论的表述（其 §0 明确声明只记录事实、不给 PASS/GO）。

## 8. 残余风险（不因本次 PASS 消失）

1. **托管 runner 上的真实触发未验证**：本复核只能证明配置结构正确；`push` 事件是否真的产生运行，只能在本分支合入 `dev/v1.0` 后由运行记录证明（需 PM-01 事后核对）。
2. **快速连续合入会取消较早的 push 运行**：`cancel-in-progress: true` + 组 `test-${{ github.ref }}` 意味着两次相隔小于单次运行时长（约 2.6–3 分钟）的合入中，较早那次 push 运行会被取消，其“合并头绿”的证据会缺失（记录为 cancelled 而非 failure）。若需要逐次合并都有绿证据，需另开任务评估（本卡明确“其余不变”，故不在本次范围内）。
3. **手动 dispatch 与 push 互相取消**：两者在 `dev/v1.0` 上同组。PM 用 `workflow_dispatch` 补验证时可能取消刚发生的 push 运行（或反之），事后核对运行记录时需注意区分 `event`。
4. **计费**：每次合入新增一次 Windows 运行，分钟数影响未验证。
5. **分支保护仍缺失**：Free 私有库 API 403，本改动不提供“禁止红灯合并”的能力，只提供合入后的自动验证。
6. **审计/对账结论依赖本机文件系统路径解析**：本次两侧一致，但不代表远端或 CI 环境同样一致。

## 9. 范围声明

- 本次复核**未**创建 PR、**未**合并、**未**修改被复核分支，**未**打 tag/Release。
- 本报告所在分支 `review/postmerge-trigger` 从基线 `617cdd9` 单独开出，只新增本报告文件。
- **本结论（PASS WITH DEVIATIONS）不等于批准合并。** 合并决定权在人类/PM-01；合并后仍需按 §8.1 核对首次 `push` 运行记录。

## 附录：复现命令

```bash
# 拓扑
git fetch origin --prune
git rev-list --count 617cdd9..43b4131              # 2
git rev-list --merges --count 617cdd9..43b4131     # 0
git diff --numstat 617cdd9 43b4131                 # 2 0 workflow; 163 0 handoff

# 逐字节
git cat-file blob 89725ff… > base.yml
git cat-file blob c45dd4f… > cand.yml
sed '4,5d' cand.yml > cand_minus2.yml
cmp base.yml cand_minus2.yml                        # exit 0

# 结构断言 + 三处负对照
C:/SoftWare/Anconda/python.exe assert_workflow.py "original" cand.yml
C:/SoftWare/Anconda/python.exe assert_workflow.py "mut1" mut1_no_push.yml push_present push_branches_dev_v1.0 trigger_keys_exactly_three
C:/SoftWare/Anconda/python.exe assert_workflow.py "mut2" mut2_push_master.yml push_branches_dev_v1.0
C:/SoftWare/Anconda/python.exe assert_workflow.py "mut3" mut3_perm_write.yml permissions_contents_read

# 门槛（候选干净 worktree）
C:/SoftWare/Anconda/python.exe -m pytest -q
PROJECT_MEMORY_REQUIRE_OPENSSL=1 C:/SoftWare/Anconda/python.exe -m pytest -q

# 审计/对账（受信包装器）
PROJECT_MEMORY_PYTHON=C:/SoftWare/Anconda/python.exe ./bin/project-memory audit --scope current --output audit_cand.json
PROJECT_MEMORY_PYTHON=C:/SoftWare/Anconda/python.exe ./bin/project-memory reconcile --fail-on high --format json --output reconcile_cand.json
```
