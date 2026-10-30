# 独立复核：CI-GATE-001 最小权限 CI 门禁

- 复核者：PM-03（独立会话，仅依据文件与本机实测）
- 复核日期：2026-10-30
- 复核对象：分支 `ci/minimal-gate-20261030`，tip `a6c4cb6d19937761b8274e7af9883bc16c63b1cb`
- 变更提交：`9148c97d0b27af0c86c8846b32eb2798da1f36bf`（交接提交为其子 `a6c4cb6`）
- 基线：`907501208383c35180e3a1f0dfc1d229854e1831`
- 解释器：`C:/SoftWare/Anconda/python.exe`（3.12.4）
- 复核方式：在 `pm-pilot-03` 之外用 `git worktree add --detach` 做干净检出；未使用 `gh`、未调用 GitHub API、未建 PR、未合并、未 push `dev/v1.0`、未打 tag/Release、未启用分支保护。
- 角色边界：本报告只给出技术复核结论，不代表人类审阅/发布结论。

## 1. 改动范围

```
$ git diff --numstat 9075012..a6c4cb6
39	0	.github/workflows/test.yml
124	0	tasks/PM02-ci-gate-handoff-20261030T055204Z.md

$ git diff --name-status 9075012..a6c4cb6
A	.github/workflows/test.yml
A	tasks/PM02-ci-gate-handoff-20261030T055204Z.md

$ git log --oneline 9075012..a6c4cb6
a6c4cb6 docs(ci): hand off CI-GATE-001 execution record
9148c97 ci(gate): add minimal-permission GitHub Actions test workflow
```

- 只有两个新增文件，无第三个文件；`39 + 124` 行新增、0 删除。
- `.github/` 首次出现：`git log --all --oneline -- .github` 仅命中 `9148c97`；`git ls-tree -r 9075012` 中无 `.github/`。
- 分支基线正确：`9148c97` 父提交为 `9075012`，`a6c4cb6` 父提交为 `9148c97`；`9075012` 是 `a6c4cb6` 的祖先。

结论：**符合**。

## 2. 与任务卡 §3 逐字比对

任务卡 `PM02_CI_GATE_TASK_CARD.md` 的 yaml 代码块位于第 33–71 行（39 行）。

```
$ sed -n '33,71p' PM02_CI_GATE_TASK_CARD.md > card_block.txt
$ wc -c card_block.txt; wc -l card_block.txt
1000
39

$ sha256sum card_block.txt
be98ad90f394157faa7bc0c9960fd451c0f335a872e3362ac6321f2da42e8734

$ git show a6c4cb6:.github/workflows/test.yml | sha256sum
be98ad90f394157faa7bc0c9960fd451c0f335a872e3362ac6321f2da42e8734

$ git show a6c4cb6:.github/workflows/test.yml > reviewed.yml
$ diff card_block.txt reviewed.yml
（无输出，exit 0）
```

- 提交 blob：`cede6848aa84d43bc97e31bb14e8aadb99e94eec`，1000 字节，39 行。
- 行尾：提交 blob 中 CR 数为 **0**（LF）；`.github/` 未在 `.gitattributes` 中声明 `eol=lf`，本机 `core.autocrlf=true` 使工作区检出为 CRLF（1039 字节 / 39 CR），但这是检出转换，**不影响提交内容**，也不影响 pytest 语义（见 §9）。

结论：**逐字一致**，sha256 = `be98ad9…`。

## 3. 安全项逐条

| # | 检查项 | 实测 | 结论 |
|---|---|---|---|
| 1 | 仅 `pull_request`（限 `branches: [dev/v1.0]`）与 `workflow_dispatch` | 第 3–6 行，无其它触发器 | 通过 |
| 2 | 无 `pull_request_target` | `grep -n pull_request_target` → 无 | 通过 |
| 3 | `permissions: contents: read` | 第 8–9 行，仅此一项 | 通过 |
| 4 | 不引用 `secrets.` | `grep -n 'secrets\.'` → 无 | 通过 |
| 5 | 不用不可信 PR 输入做 run 注入 | `grep -nE 'github\.event\.'` → 无；仅在 `concurrency.group` 使用 `github.ref`（非 run 注入面） | 通过 |
| 6 | `actions/checkout@v4` 带 `persist-credentials: false` | 第 20–22 行 | 通过 |
| 7 | 无 `contents: write`、无自动合并/评审/标签/评论写入 | `grep -nE 'write|merge|label|review|comment'` → 无 | 通过 |
| 8 | 仅使用 `actions/checkout@v4`、`actions/setup-python@v5` | `grep -n 'uses:'` → 两处 | 通过 |

结论：**安全项全部通过**。

## 4. 语义正确性

- 默认门槛：`Default gate` → `shell: bash`、`python -m pytest -q`（第 28–30 行）。
- OpenSSL 门槛：`command -v openssl` 可用时以 `PROJECT_MEMORY_REQUIRE_OPENSSL=1` 跑 pytest；不可用时 `else` 分支 **显式 `echo ... SKIPPED (not passed)`**，非静默通过（第 31–39 行）。
- `runs-on: windows-latest`（第 17 行）、`timeout-minutes: 40`（第 18 行）。
- `python-version: "3.12"`（第 25 行）。
- pytest pin `pytest==9.1.1`（第 27 行），与 `pyproject.toml` 第 14 行 `dev = ["pytest==9.1.1"]` 一致。
- YAML 解析：`['True', 'concurrency', 'jobs', 'name', 'permissions']`，`permissions == {'contents':'read'}`，含 `jobs.pytest`；`on:` 被 PyYAML 1.1 解析为布尔键 `True` 属预期；PyYAML 6.0.1。

结论：**符合任务卡语义**。

## 5. 本地双门槛实测

在干净检出（tip `a6c4cb6`，含该文件）内，使用 `C:/SoftWare/Anconda/python.exe`：

| 门槛 | 命令 | 结果 | 耗时 | 退出码 |
|---|---|---|---|---|
| 默认 | `python -m pytest -q` | `257 passed, 2 skipped` | 152.05s | 0 |
| OpenSSL | `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q` | `257 passed, 2 skipped` | 150.77s | 0 |

本机 `openssl version` → `OpenSSL 3.5.9`（可用），故 OpenSSL 门槛为**实跑**而非跳过。

**说明**：该结果证明新增文件不改变本地测试结果；**不等于** GitHub 托管运行器上的结果（见 §10）。

## 6. 审计与 reconcile

命令（两份都在 `pm-pilot-03` 外的 detached worktree 中执行）：

```
$ python -m project_memory audit --repo . --scope current      # 评审树 a6c4cb6
$ python -m project_memory audit --repo . --scope current      # 基线树 9075012
```

| 指标 | 评审树 a6c4cb6 | 基线 9075012 |
|---|---|---|
| counts | high 0 / medium 16 / low 24 | high 0 / medium 16 / low 24 |
| 总数 | 40 | 40 |
| `(severity, code, location)` 排序多重集 sha256 | `626e01fb28be488640767661305343aec8e86a594122ca127ce58dcd2c164843` | `626e01fb28be488640767661305343aec8e86a594122ca127ce58dcd2c164843` |
| added / removed | 0 / 0 | — |
| `location` 以 `.github` 开头的 finding | 无 | 无 |
| exit | 0 | 0 |

```
$ python -m project_memory reconcile --repo . --fail-on high
（state = needs_attention；counts high 0 / medium 16 / low 24；exit 0）
```

`state=needs_attention` 由既有 medium/low 导致；`--fail-on high` 在 high 为 0 时返回 0，符合门槛。

结论：**多重集完全一致，新增 0；`.github/` 无 finding；reconcile exit 0**。

## 7. 执行者 handoff 事实一致性

| handoff 声明 | 实测 | 结论 |
|---|---|---|
| 变更提交 `9148c97…`，handoff 为其子 | `rev-list --parents` 证实 | 一致 |
| blob `cede6848…`、1000 字节、39 行、LF 无 CR | 全部证实 | 一致 |
| 与卡 §3 逐字一致（diff 无输出） | diff 无输出，sha256 相同 | 一致 |
| YAML 键集与结构 | 与实测一致 | 一致 |
| 默认/OpenSSL 257 passed / 2 skipped、exit 0 | 一致（耗时不同：169.38s/177.24s vs 152.05s/150.77s，属机器差异） | 一致 |
| openssl 3.5.9 可用 | 一致 | 一致 |
| 审计 40 条、0/16/24、新增 0、`.github` 无 finding | 一致 | 一致 |
| 明确写有「未在 GitHub Actions 上真实运行」 | §7 明确声明，未夸大 | 一致（如实） |
| 远端状态写为 NOT VERIFIED、push 后未回写 | 现 `git ls-remote` → `a6c4cb6…`，与复核对象一致 | 一致（如实） |
| 残留两份未跟踪文件 | 属执行者克隆特有，本机无法复现 | 无法独立核实（见 §10） |

未发现「把未跑写成已跑」或远端状态写错的情况；执行者未自下 PASS 结论。

## 8. 结论

**PASS**（技术复核）。

阻断项：无。

本结论仅覆盖本报告所列的本地等价实测；发布/合并等决定由人类审阅者作出，本报告不代为下结论。

## 9. 非阻断偏差 / 观察

1. **耗时差异**：handoff 记录 169.38s / 177.24s，本次 152.05s / 150.77s，属机器负载差异，不影响计数与退出码。
2. **检出 CRLF vs 提交 LF**：提交 blob 为 LF/0 CR；因 `.github/**` 未纳入 `.gitattributes` 的 `eol=lf` 且本机 `core.autocrlf=true`，工作区检出为 CRLF。对 Actions（按 blob 检出）与 pytest 语义均无影响；若希望跨平台统一 LF，可另立卡补 `.gitattributes`，本轮不属范围。
3. **Action 版本固定方式**：`actions/checkout@v4`、`actions/setup-python@v5` 用主版本标签而非提交 SHA 固定，存在上游标签可变的供应链风险；但这是任务卡 §3 的逐字要求，非执行偏差，仅作提示。
4. **reconcile 状态名**：`state=needs_attention` 与 `--fail-on high` exit 0 并存，源于既有 medium/low，非本次引入。
5. **handoff 残留文件**：执行者克隆中的两份未跟踪文件无法在本机核实，不据此判定。

## 10. NOT VERIFIED

- **未在 GitHub Actions 托管运行器上实际执行**：`windows-latest` 上的 `actions/checkout`、`actions/setup-python`、`pip install`、`openssl` 可用性、`shell: bash` 行为均未验证；本地结果不等价于托管运行器结果，首跑以实际 CI 日志为准。
- 执行者克隆 `pm-pilot-02` 中「仅两份既有未跟踪文件」的残留状态未在本机核实。
- handoff 定稿时（push 前）的远端无分支状态未回放；仅核实当前远端 tip = `a6c4cb6…`。
- 分支保护与「连续 3 次绿」：任务卡明确本轮不做，未验证。
- 本复核未启用/创建任何 workflow、未开启分支保护、未触发任何 CI 运行。
