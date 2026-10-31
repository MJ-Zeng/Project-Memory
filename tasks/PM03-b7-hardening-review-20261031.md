# PM-03 增量复核：B7-HARDEN-001（修复 B-7 偏差 D-1…D-10）

- 日期：2026-10-31
- 复核人：PM-03；执行者：PM-02；合并决定：PM-01 / 人类
- 被复核分支：`feat/b7-ci-anchor`
  - 被复核头（实查）：`cbd9be5179f749a7e46dc81601f42ccc9c26b1d1`
  - 实现提交：`3c765bca0f2b2885042c23a013a121a229f01eca`
  - 实现之后仅追加 handoff：`cbd9be5`（`git diff --name-status 3c765bc..cbd9be5` 仅新增 `tasks/PM02-b7-harden-001-handoff-20261031T050226Z.md`）
  - 树：`cbd9be5` = `a43b923a7e374f84856a6dd1bab7a341e79a9acf`；`3c765bc` = `bfb8998beb02889f790da8fe29a941571095f3d9`
- 基线：`53b11cf789f0c4eee17f68e80e575a35bf46f187`（任务卡给定；`git merge-base cbd9be5 53b11cf` 即该提交）
- 复核分支：`review/b7-hardening`（从 `53b11cf` 新建；本报告提交在此）
- 上一轮报告：`tasks/PM03-b7-ci-second-identity-review-20261031.md` @ `8ec65c4`（PASS WITH DEVIATIONS，D-1 High）
- 工作树（本会话新建）：`C:/Temp/b7h/head` = `cbd9be5`；`C:/Temp/b7h/base` = `53b11cf`
- 环境：Windows 10.0.26300；`C:/SoftWare/Anconda/python.exe`（Python 3.12.4）；pytest 9.1.1；PyYAML 6.0.1；OpenSSL 3.5.9
- 输入边界：PM-02 handoff 只作待核对对象，不是结论依据；以下数字、退出码与输出均为本会话实测。未读取真实 Secret 值，未访问真实 PR / 托管 runner，未使用 `s3-exercise-keys`；签名只使用 `C:/Temp/b7h/sim*/keys` 下本次生成的测试期 RSA 密钥。
- 本报告只作 PM-01 / 人类的合并输入，**不构成合并批准**。

## 1. 结论

**PASS（本卡范围）。**

- **D-1 已真正修复**：门禁只检出 base（`github.event.pull_request.base.sha`，dispatch 回退 `dev/v1.0`），验证器与 workflow 定义都来自 base；PR head 只作为 40 位 SHA 字符串传给 `--commit`，workflow 中不存在检出、执行或安装 PR head 代码的路径；没有残留独立的 `pull_request` 触发；secret 只进入 `verify approval` 步骤；权限仅 `contents: read`。我自建的端到端负对照中，旧形态（检出 PR head、运行 PR 树验证器）在空审批目录下 **exit 0**，新形态在同条件下 **exit 2**，加入针对 PR head 的合法签名审批后新形态 **exit 0**。
- **D-2 / D-3 / D-4 / D-5 / D-7 / D-8 / D-9 / D-10 的处置与任务卡一致**，逐项证据见 §4。
- **D-6（真实 PR / 托管 runner）按卡未处理**，连同托管侧无法本地验证的行为，作为残余列在 §7；它们构成 B-10 的前置验证条件，不构成本卡实现的偏差。

## 2. 范围与变更面

`git diff --stat 53b11cf..cbd9be5`：

```text
 .github/workflows/approval-gate.yml            |  46 +++++++--
 README.md                                      |  12 +-
 docs/OPERATIONS.zh-CN.md                       |   8 +-
 project_memory/authority.py                    |  42 +++---
 project_memory/cli.py                          |  11 +-
 skill/project-memory/references/governance.md  |   6 +-
 .../PM02-b7-harden-001-handoff-...Z.md         | 151 +++++++++++++++++++++
 tests/test_b7_ci_second_identity.py            | 130 +++++++++++++++++++---
 8 files changed, 343 insertions(+), 63 deletions(-)
```

```text
M .github/workflows/approval-gate.yml
M README.md
M docs/OPERATIONS.zh-CN.md
M project_memory/authority.py
M project_memory/cli.py
M skill/project-memory/references/governance.md
A tasks/PM02-b7-harden-001-handoff-20261031T050226Z.md
M tests/test_b7_ci_second_identity.py
```

变更面只含任务卡 §2 预期的实现、文档、测试与 handoff；未改 `test.yml`、`approvals` 分支、仓库 Secrets、`dev/v1.0`；未新增文档、未加 CODEOWNERS、未引入无关重构。`git diff --check 53b11cf..cbd9be5` exit 0。对 diff 的密钥/令牌扫描（`BEGIN … PRIVATE KEY`、`ghp_`、`github_pat_`、`AKIA…`、`xox…`、`-----BEGIN`）无命中。

## 3. D-1 独立判断（核心）

### 3.1 工作流事实（对 `.github/workflows/approval-gate.yml` @ `cbd9be5` 逐项核对）

| 检查点 | 实际内容 | 判断 |
|---|---|---|
| 触发 | `pull_request_target:`（`dev/v1.0`，`opened/synchronize/reopened/edited`）与 `workflow_dispatch.inputs.pr`；无 `pull_request:` | 通过 |
| checkout | 唯一一次 `actions/checkout`（固定 `11d5960…`），`ref: ${{ github.event.pull_request.base.sha || 'dev/v1.0' }}`（第 30 行），`fetch-depth: 0`，`persist-credentials: false` | 通过 |
| head 来源 | `EVENT_HEAD: ${{ github.event.pull_request.head.sha }}`（第 41 行）；dispatch 分支用认证 fetch `refs/pull/$PR_NUMBER/head`（第 50 行）+ `git rev-parse 'FETCH_HEAD^{commit}'` | 通过（只取对象） |
| head 校验 | `grep -Eq '^[0-9a-f]{40}$'`，不符 `::error::` + exit 1（第 53 行起） | 通过 |
| 执行内容 | 无 `pip install`、无 `pytest`、无 `working-directory`；验证只用 base 树里的 `python -m project_memory.cli`（第 88-90 行） | 通过 |
| 其他检出 | `git --work-tree=.pm-approvals checkout origin/approvals -- records` 只把 `records/` 数据检出到仓库外工作树；无对 `head.sha` / `refs/pull/*` 的 checkout | 通过 |
| secret | `secrets.PROJECT_MEMORY_APPROVAL_ANCHOR_JSON` 只出现在 `verify approval` 步骤的 `env`（第 72 行） | 通过 |
| token | `github.token` 只进入 `resolve head` 与 `fetch approvals` 两步的 `env`；未进入 `verify approval` 步骤 | 通过 |
| 权限 | 仅 `contents: read`（第 17-18 行），已删除 `pull-requests: read`、`checks: read` | 最小 |
| 表达式全集 | `base.sha \|\| 'dev/v1.0'`、`head.sha`、PR number、`github.event_name`、`github.token`×2、secret×1 | 无额外入口 |
| 同名检查污染 | `test.yml` 仍用 `pull_request`，但其 job 是 `pytest`；本门禁 job 是 `approval`，未发现同名 | 通过 |

结论：`pull_request_target` 的 workflow 定义来自 base；checkout 只到 base；PR head 只以字符串参与审批匹配。门禁不再执行 PR 树里的验证器或 workflow。

### 3.2 自建端到端负对照（独立于 PM-02 的 handoff）

脚本：`C:/Temp/b7h/run_sim2.py`（不提交）。做法：

1. 用 `git archive 3c765bc` 导出**已加固**的树作为本地 `dev/v1.0`（模拟合入后的 base；换行符按本机 git 配置规范化），另建空的 `approvals` 分支与 PR 分支。
2. PR 提交同时做两件“攻击”：`project_memory/cli.py` 的 `main()` 首行插入 `return 0`；workflow 触发改回 `pull_request:`。
3. 分别按旧形态（checkout PR head → 运行 PR 树验证器）与新形态（checkout base → 运行 base 验证器，PR head 只作 `--commit`）执行，审批目录先空、后放入针对 PR head 的合法签名记录。

实测（`C:/Temp/b7h/sim2.log` 与 `C:/Temp/b7h/sim2/A-out.json`）：

```text
base    = d04ac9c...（3c765bc 树）
pr_head = 1e19f7f...（main() 首行 return 0；workflow 为 pull_request:）
PR head workflow has pull_request trigger: True

A. 空审批，新形态：exit=2
   problems: 目录中没有审批记录…；没有 trusted+approve+提交匹配的审批记录（提交 1e19f7f…）
B. 空审批，旧形态：exit=0        ← D-1 绕过在旧形态复现
C. 合法审批，新形态：exit=0       ← 门禁对合法审批仍然放行
D. 合法审批，旧形态：exit=0
SUMMARY {"A_new_empty": 2, "B_old_empty": 0, "C_new_valid": 0, "D_old_valid": 0}
EXPECTED A=2,B=0,C=0,D=0 -> MATCH
```

另以 `53b11cf` 树为 base 的同类对照（`C:/Temp/b7h/run_sim.py` / `sim.log`）得到同一组 `A=2, B=0, C=0, D=0`。旧形态 `gate-old/project_memory/cli.py` 的 `main()` 确为 `return 0`，空目录实测 `OLD_EXIT:0`；新形态 `gate-new/project_memory/authority.py` 的 CI 判定为 `== 'true'`。

“改前失败 / 改后通过”的对应关系：

| 对照 | 改前（旧形态） | 改后（本分支形态） |
|---|---|---|
| PR 篡改 `cli.py` + workflow，空审批 | exit 0（绕过） | exit 2（阻断） |
| 合法审批已发布 | exit 0 | exit 0（不误伤） |

### 3.3 触发退回负对照（测试是否真能抓住回退）

在 head worktree 把 `pull_request_target:` 临时改回 `pull_request:`，运行两条静态测试：`2 failed, 31 deselected`（`test_workflow_exists_and_parses`、`test_uses_pull_request_target_without_a_pull_request_trigger`）；还原后 `2 passed`。还原文件 sha256 与备份一致：`e2ed9a2db5d62edb26a994268f73e84a2042ac546a76942a620d293be9628c14`。

### 3.4 D-1 结论

**已修复。** 代码层面不存在把 PR head 检出、安装或执行到工作区的路径。剩余的是信任前提（base 代码可信、管理员可改写）与托管侧行为（见 §7），不是本实现可再消除的 PR 代码执行面。

## 4. 其余偏差逐项结论

| ID | 结论 | 实测证据 |
|---|---|---|
| D-2 | 处置成立（文档） | README / OPERATIONS / governance 均改为“`GITHUB_ACTIONS=true` 是防误用开关，不是密码学边界；真实边界是锚在仓库 Secret 外 + 门禁代码固定在 base”；`authority.py` 模块与 `load_anchor` docstring 同步。原有“本地设置 JSON 锚永不生效”的绝对说法已删除。本地自签自批属性仍存在，但这是卡面选择的文档处置，且不影响 CI 门禁结论。 |
| D-3 | 处置成立 | `cli.py` 的 records-dir 分支：无 `--require-approve` 一律 `return 0`；带标志按 `approved` 返回 0/2；单记录模式不变，`--require-approve` + `--record` 仍 `PMError`（exit 1）。实测（head 代码，`C:/Temp/b7h/d3/`）：合法记录无标志 `0 / approved=True`；错误提交无标志 `0 / approved=False`；错误提交带标志 `2`；空目录无标志 `0 / scanned=0`；空目录带标志 `2`。help 文本已写明两种模式。 |
| D-4 | 处置成立 | `_is_ci_context()` 为 `os.environ.get(CI_CONTEXT_ENV) == 'true'`，无 strip/casefold。实测：`TRUE`、`True`、`' true '`、`'1'`、空串均 `anchor=None`；仅 `'true'` 得到 `<env:PROJECT_MEMORY_TRUST_ANCHOR_JSON>` 且 `reason=ok`。 |
| D-5 | 处置成立 | `load_anchor()` 在文件锚变量非空时直接返回 `_load_file_anchor(...)`，不再回退 JSON。实测：显式坏文件锚 + 有效 JSON 锚 + CI → `anchor=None`，reason 指向该文件路径，`fell_back_to_json=False`。另有两条测试覆盖“缺失”和“所有者不受保护”两种失败。注：纯空白变量经 `strip()` 后视为未配置（与旧行为一致），不属于显式设置。 |
| D-6 | 按卡未处理（残余） | 真实 PR、托管 runner、私有库认证 fetch 与 Secret 注入均未实测；见 §7。 |
| D-7 | 处置成立 | 两步都用 `auth=$(printf 'x-access-token:%s' "$GH_TOKEN" \| base64 \| tr -d '\n')`、`echo "::add-mask::$auth"`、`git -c http.extraheader="AUTHORIZATION: basic $auth"`，`set -euo pipefail`，无 `\|\| true`。令牌只进入这两步的 `env`，不进入 verify 步骤；`-c` 为单次进程配置，不写入 `.git/config`、`.git-credentials`、reflog 或 `FETCH_HEAD`；checkout `persist-credentials: false`。日志侧：base64 认证串被 mask，原始 token 由 GitHub 自动 mask。残余：base64 认证串出现在 git 的进程参数中（同一 runner 同用户进程可见），但该 job 不运行任何不可信代码，且不进日志/持久文件。放行与失败路径：fetch / rev-parse / 正则校验 / records checkout / 缺锚均有显式失败，错误不被吞。 |
| D-8 | 处置成立 | dispatch 经 checkout 的 `\|\| 'dev/v1.0'` 显式检出 `dev/v1.0`；文档说明 dispatch 仅诊断，且 GitHub 文档明确 `workflow_dispatch` 触发的检查不满足必需状态检查（并从合格事件列表中排除）。残余：dispatch 使用的 workflow 定义仍来自 UI 选择的分支，只有写权限者可派发，且 dispatch 检查不满足必需检查、secret 只有公钥，故不构成合并绕过。 |
| D-9 | 处置成立 | workflow 中已无 `pip install`、无 `pytest`；验证器只用标准库；静态测试 `test_no_pip_install_or_pytest` 覆盖。 |
| D-10 | 处置成立 | `tests/test_b7_ci_second_identity.py` 从 26 条增至 33 条（全套 327 = 基线 320 + 7）。新增/反转覆盖：`pull_request_target` 且无独立 `pull_request:`；checkout 用 base 且任何 `ref:` 都不含 head / `refs/pull/`；无 pip/pytest；事件载荷与 dispatch fetch 两条 head 解析路径 + 40 位校验；认证 fetch 带 `http.extraheader` 且未被 `\|\| true` 吞；`GITHUB_ACTIONS` 四例；坏文件锚 fail-closed（缺失与不受保护两例）；空目录两种退出码。既有负对照 `test_negative_control_edit_commit_then_restore` 与单记录模式测试保留；PyYAML 缺失时仍 skip。未发现删弱断言或以捕获异常代替断言。 |

## 5. 门槛复跑（head = `cbd9be5`，worktree `C:/Temp/b7h/head`）

| # | 命令 | exit | 结果 |
|---|---|---|---|
| 1 | `git fetch origin feat/b7-ci-anchor`；`git rev-parse cbd9be5` | 0 | `53b11cf..cbd9be5`；head 与派单一致 |
| 2 | `git diff --check 53b11cf cbd9be5` | 0 | 无输出、无空白错误 |
| 3 | `C:/SoftWare/Anconda/python.exe -m pytest -q` | 0 | **327 passed, 2 skipped in 179.59s** |
| 4 | `PROJECT_MEMORY_REQUIRE_OPENSSL=1 C:/SoftWare/Anconda/python.exe -m pytest -q` | 0 | **327 passed, 2 skipped in 181.95s** |
| 5 | `… -m pytest tests/test_b7_ci_second_identity.py -v` | 0 | **33 passed in 4.44s** |
| 6 | `… audit --scope current --output C:/Temp/b7h/audit-head.json` | 0 | `{'high': 0, 'medium': 16, 'low': 24}`，40 条 findings |
| 7 | 基线 `… audit --scope current --output C:/Temp/b7h/audit-base.json` | 0 | `{'high': 0, 'medium': 16, 'low': 24}`，40 条 |
| 8 | 多重集比较（键 `severity, code, location, message`） | — | `multiset equal: True`；only head `[]`；only base `[]`；`entry_doc_*` findings 0 |
| 9 | `… reconcile --fail-on high` | 0 | counts 与 audit 一致（0/16/24） |
| 10 | `git diff --name-status 3c765bc cbd9be5` | 0 | 仅 handoff 文件 |

2 skipped 与基线相同（`tests/test_security_rc3.py` 的 Windows 符号链接用例），不是本次新增。PyYAML 6.0.1 已安装，`test_workflow_exists_and_parses` 实际执行了 YAML 解析而非跳过。

## 6. 负对照汇总（改前失败 / 改后通过）

| 对照 | 改前 | 改后 | 说明 |
|---|---|---|---|
| PR 篡改 `cli.py` + workflow，空审批（加固 base） | 旧形态 exit 0 | 新形态 exit 2 | `C:/Temp/b7h/sim2.log`：A=2, B=0, C=0, D=0 |
| 同上（`53b11cf` base） | 旧形态 exit 0 | 新形态 exit 2 | `C:/Temp/b7h/sim.log`：A=2, B=0, C=0, D=0 |
| 合法审批已发布 | exit 0 | exit 0 | 不误伤 |
| 触发退回 `pull_request` | — | 2 条静态测试失败 | 还原后 2 条通过，sha256 与备份一致 |
| `GITHUB_ACTIONS` 拼写 | 旧实现接受 `TRUE`/`True`/空白 | 仅 `'true'` 生效 | 实测 4 个非字面量全部 `anchor=None` |
| 显式坏文件锚 + 有效 JSON + CI | 旧实现回退 JSON | `anchor=None`，reason 指向文件锚 | 实测 `fell_back_to_json=False` |
| records-dir 退出码 | 无标志也始终“无 approved 即 2” | 无标志 0；带标志 0/2 | 实测 5 组退出码 |

## 7. 未验证项与 B-10 建议

### 7.1 本地无法验证（本卡 D-6 范围）

1. **真实 PR 上 `approval` 检查是否出现在必需检查候选、是否按最新 head SHA 阻断合并。** GitHub 文档把 `pull_request_target` 列为可针对 PR 评估检查的合格事件，并明确 `workflow_dispatch` 不满足必需检查（https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks）。但检查具体挂在 head、base 还是 test merge commit，以及 Ruleset 候选里显示的名称（`approval` 还是 `approval-gate / approval`），必须在真实 PR 上观察。
2. **托管 runner 上的认证 fetch 与 Secret 注入。** 私有库 `http.extraheader` 是否按预期工作、`secrets.PROJECT_MEMORY_APPROVAL_ANCHOR_JSON` 是否注入、mask 是否覆盖所有输出，本地无法证明。
3. **`pull_request_target` 的 check 归属与 `enforce_admins` 组合行为。** 包括 check 运行是否绑定到 PR 的可合并提交、管理员绕过是否按预期被 `enforce_admins` 关闭。
4. **fork PR 行为。** fork PR 是否自动触发 `pull_request_target`、是否拿到 base 仓库 secret、head SHA 如何映射、首次贡献者是否需要人工批准运行，均未实测。
5. **审批发布后的重新评估路径。** 用 PR `edited` / 重开 / 新提交，或重跑原 `pull_request_target` 运行，能否在同一 head SHA 上得到新结论。
6. **PR 修改 `approval-gate.yml` 时，真实 GitHub 是否确实使用 base 的 workflow 定义**（本地已用静态与模拟证明设计意图，托管侧仍需一次实证）。

### 7.2 对 B-10 的建议

1. 先在 `dev/v1.0` 上开一个**不带审批**的真实 PR，确认 `approval-gate` 运行、失败原因正确，并确认 `approval` 出现在必需检查候选中且合并被阻断（`enforce_admins=true`）。
2. 对同一 head 发布合法审批，用 PR `edited` 或重跑原运行，确认同一 SHA 转为成功；再推一个新提交，确认旧审批失效、门禁重新失败。
3. 用一个 fork PR（无审批）验证：门禁失败、日志无 token 泄露、`approvals` 分支能被认证拉取；再决定是否需要为 fork 场景单独说明。
4. 开一个专门修改 `.github/workflows/approval-gate.yml` 或 `project_memory/{authority,cli}.py` 的 PR，确认它仍被同一条审批门禁阻断（这是 D-1 修复的直接验收）。
5. 记录真实 run id、检查名称与 commit SHA 到 S3 证据；在完成前，不要对外声称门禁已在真实 PR 上验证为第二身份。
6. 可选加固：给 job 加 `timeout-minutes`；`verify approval` 步骤可改用 `set -euo pipefail`（当前为 `set -uo pipefail`，关键命令均已显式处理失败，最后一行的退出码即门禁结果，行为仍是 fail-closed）。
7. 如果实测发现 `pull_request_target` 的检查无法进入必需检查候选，备选方案是：由一个最小 `pull_request` 作业只校验已存在的审批记录（不读 secret、不执行 head 代码），或由 GitHub App 在 head SHA 上提交 commit status；两条路线都要重新复核，不能直接沿用本结论。

## 8. 边界声明

- 本报告是 PM-03 的独立复核意见，不是合并批准；未开 PR、未合并、未改 `dev/v1.0` / `approvals` / 仓库 Secrets。
- 未使用 `s3-exercise-keys`；签名只使用 `C:/Temp/b7h/sim*/keys` 下本次生成的测试期临时 RSA 密钥，未提交到仓库，也未用于任何真实审批。
- 复核过程未写入 `pm-pilot-01`、`pm-pilot-02`；`pm-pilot-03` 中既有的未跟踪复核产物保持原样，本复核分支只新增/修改本报告。
