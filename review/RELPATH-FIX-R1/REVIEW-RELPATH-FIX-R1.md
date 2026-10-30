# RELPATH-FIX-001 独立窄复核报告（PM-03，第四轮）

- 复核对象：`origin/fix/verify-input-paths-20261030`
  - 变更提交：`cac6a94484b305a8f56b6b11ff3cec945d57cfc2`（父 `81c5531`）
  - handoff 提交：`1bcd6d70dbe9eb1efdf4c3212d36ba479a3b57a7`（父 `cac6a94`，分支顶点）
- 基线：`81c553112950d87bcbb72ead6977c5d48e411ab3`（`origin/dev/v1.0`，实测与派单一致）
- 复核时间：2026-10-30
- 复核环境：Windows 11 AMD64；Python 3.12.4；pytest 9.2.0；解释器位于复核 worktree 之外（`review/HYGIENE-R1/venv/Scripts/python.exe`）
- 隔离方式：在 `pm-pilot-03` 克隆中 `git fetch origin fix/verify-input-paths-20261030 dev/v1.0`，建立 detached worktree：`rel-base`=`81c5531`、`rel-target`=`cac6a94`、`rel-tip`=`1bcd6d7`；另建 `control` worktree 用于回退对照；PM-02 目录未改动。
- 输入边界：PM-02 handoff 仅作输入，未用于任何结论；下列结论均对应本轮自行执行的命令与输出。
- 结论：**PASS**（附 2 项口径/验证限制，见 §8）

---

## 1. 变更范围（派单第 1 条）

```bash
git show --stat cac6a94
git diff --name-status 81c5531..cac6a94
```

```text
 docs/OPERATIONS.zh-CN.md     |  2 +-
 project_memory/cli.py        | 10 ++++--
 pyproject.toml               |  1 +
 tests/test_project_memory.py | 84 ++++++++++++++++++++++++++++++++++++++++++++
 4 files changed, 94 insertions(+), 3 deletions(-)

M  docs/OPERATIONS.zh-CN.md
M  project_memory/cli.py
M  pyproject.toml
M  tests/test_project_memory.py
```

handoff 提交 `1bcd6d7` 另加 `tasks/PM02-relpath-fix-handoff-20261030T021142Z.md`（+79），属允许项。

禁止路径检查（目标与顶点两侧均无输出）：

```bash
git diff --name-only 81c5531..cac6a94 | grep -E '^(bin/|_project_memory_launcher\.py|project_memory/coordination\.py|\.project-memory/|evidence/|docs/decisions/|docs/CURRENT_STATE\.md|pilot/)'
# NONE（1bcd6d7 同样 NONE）
```

`cli.py` 净变化 **+8/−2 = 净 +6 行**（≤10），diff 只有两个 hunk：模块级 `repo_path` helper 与 `verify` 分支的两行调用；无其它改动。

## 2. 语义核对（派单第 2 条）

diff 全文（cli.py）：

```diff
+def repo_path(repo: Path, value: Path | None) -> Path | None:
+    if value is None or value.is_absolute():
+        return value
+    return repo / value
...
-        findings = safe_json(args.findings_file) if args.findings_file else []
-        mapping = safe_json(args.criterion_evidence) if args.criterion_evidence else None
+        findings = safe_json(repo_path(repo, args.findings_file)) if args.findings_file else []
+        mapping = safe_json(repo_path(repo, args.criterion_evidence)) if args.criterion_evidence else None
```

- 相对路径按 `--repo` 解析：`repo = require_repo(args.repo)`，而 `project_memory/common.py:25-29` 中 `require_repo` 执行 `expanduser().resolve()`，因此 `repo / value` 得到绝对路径。
- 绝对路径原样返回：`value.is_absolute()` 分支直接返回，`None` 原样返回，与旧行为一致。
- 其它命令未改：diff 仅 `verify` 分支两行；`--test-log`、`--output`、`--pr-file` 等参数未进入 helper，解析方式保持 cwd 语义。`verify_run(...)` 的 `args.test_log` 传参也未改动。
- 未改公开参数名、未动 `coordination.py`。

## 3. 独立复现（派单第 3 条）

在独立 `control` worktree（`cac6a94`）中把 `project_memory/cli.py` 回退到基线（其余文件保留）：

```bash
git worktree add --detach control cac6a94
git checkout 81c5531 -- project_memory/cli.py
pytest -q tests/test_project_memory.py -k "relative_criterion_evidence or absolute_findings_file" -v
```

结果：**1 failed, 1 passed**，失败为测试 1：

```text
FAILED tests/test_project_memory.py::CoordinationTest::test_cli_relative_criterion_evidence_resolves_against_repo
AssertionError: 1 != 2 : project-memory: 无法读取 JSON criterion-evidence.json：
[Errno 2] No such file or directory: 'criterion-evidence.json'
```

即基线确实按进程 cwd 找文件，测试 1 是真实缺陷复现；测试 2（绝对路径护栏）在基线通过。

恢复目标 `cli.py` 后：

```bash
git checkout cac6a94 -- project_memory/cli.py
pytest -q ... -k "relative_criterion_evidence or absolute_findings_file" -v
# 2 passed, 127 deselected
```

工作区随后为 clean（`git status --porcelain` 0 行）。

测试内容核对：测试 1 在仓库外临时 cwd 传相对 `--criterion-evidence`，断言 exit 2（既有语义）且 `verification.criterion_evidence` 非空、cwd 下该文件不存在；测试 2 用仓库外绝对 `--findings-file`（内容 `[]`）并传绝对 `--criterion-evidence`，断言 exit 2、`verified=false`、`status=MANUAL_REVIEW_REQUIRED`。`tests/test_project_memory.py` 为 **+84/−0**，未删除或修改既有测试。

## 4. 双门槛回归（派单第 4 条）

在 `rel-target` 内、worktree 外解释器：

| 门槛 | 结果 | 耗时 | 退出码 |
|---|---|---|---|
| 默认 `pytest -q` | 255 passed, 2 skipped | 153.98s | 0 |
| `PROJECT_MEMORY_REQUIRE_OPENSSL=1 pytest -q` | 255 passed, 2 skipped | 148.97s | 0 |

253 + 2 新增，符合任务卡预期；2 个 skip 为既有 Windows 符号链接跳过。

## 5. 审计与 reconcile（派单第 5 条）

```bash
# rel-base 81c5531 与 rel-tip 1bcd6d7
./bin/project-memory audit --scope current   # 均 exit 0
./bin/project-memory reconcile --fail-on high  # rel-tip, exit 0
```

| 指标 | 基线 81c5531 | 顶点 1bcd6d7 |
|---|---|---|
| 总数 | 40 | 40 |
| high | 0 | 0 |
| medium | 16 | 16 |
| low | 24 | 24 |
| 新增三元组 | — | **0** |
| 减少三元组 | — | **0** |

- 多重集逐项相同；减少为 0，无条目可列。
- `entry_doc_*` 类 finding：0；`project_memory/cli.py` 上 finding：0。
- `reconcile --fail-on high`：**exit 0**，`state=needs_attention`，`counts={high:0, medium:16, low:24}`，items 40。medium/low 尚存属预期。

## 6. 事实核对（派单第 6 条）

### docs/OPERATIONS.zh-CN.md

第 134 行末尾新增句与实现一致：`--findings-file` 与 `--criterion-evidence` 经 `repo_path()` 处理，相对路径拼到已 `resolve()` 的 repo 根，绝对路径原样。新增句不含 Markdown 链接或 URL；文件为 1+/1−，其余内容未动。

### pyproject.toml

- `[project] dependencies = []` 未变；新增仅位于 `[project.optional-dependencies]`：`dev = ["pytest==9.1.1"]`（原有 `semantic` 保留）。
- 运行时代码不读取 pyproject / optional-dependencies（`project_memory/`、`bin/` 内 grep `pyproject|optional-dependencies` 无命中）；`project_memory/` 内无 `import pytest`。
- 因此该行只声明开发依赖，不影响运行时依赖解析或 CLI 行为。

## 7. 分支与远端状态

```bash
git ls-remote origin refs/heads/fix/verify-input-paths-20261030 refs/heads/dev/v1.0
# 1bcd6d7...  refs/heads/fix/verify-input-paths-20261030
# 81c5531...  refs/heads/dev/v1.0
```

任务卡允许 push 供复核；实测分支已推送，顶点 `1bcd6d7`；`dev/v1.0` 仍为 `81c5531`，未见合并/改写。未见 PR/tag/Release 动作（未通过 GitHub API 核验，见 NOT VERIFIED）。

## 8. 口径偏差与验证限制

1. **pytest 版本未按 pin 演练**：`pyproject.toml` 声明 `pytest==9.1.1`，本轮复核 venv 为 **pytest 9.2.0**。声明本身已核对；未在 9.1.1 下重跑全量。若需以 pin 为准，应另建干净 venv 安装 dev extra 后复跑。
2. **findings-file 相对路径无专项用例**：测试 1 覆盖 `--criterion-evidence` 相对路径，测试 2 覆盖两个参数的绝对路径；`--findings-file` 的相对路径未单独跑用例，但其调用与 criterion 分支共用同一 helper（代码级核对），语义一致。任务卡 §2.2 只要求 criterion 相对路径用例，故不构成验收缺口。
3. 测试 1 断言的是既有语义 **exit 2**（而非 exit 0），与卡“exit 0 或既有语义 exit 2”一致。
4. 回退对照在 `control` worktree 完成，未改动 `rel-target` 或 PM-02 目录；测试产生的 `__pycache__` 为未跟踪文件，未提交。
5. 任务卡 §2.2 的原文矛盾已由 PM-01 修正为“测试 1 先失败、测试 2 是护栏”，本轮按修正口径复核通过。

## 9. 结论

**PASS。** 变更范围恰为 4 文件 + handoff，禁止路径零改动；`cli.py` 只含 helper 与 `verify` 两行、净 +6；相对路径按 `--repo` 解析、绝对路径不变，其它命令 cwd 语义未动；独立回退对照复现测试 1 基线失败、恢复后 2/2 通过；双门槛 255/2、exit 0；审计 `40/0/16/24` 完全不变、新增 0、减少 0；reconcile exit 0；OPERATIONS 新句与实现一致，pyproject 仅声明开发依赖。偏差仅为 pytest pin 未实际演练等验证限制（§8），不影响验收。

本报告仅为复核结论，不是合并批准或人类批准。

**NOT VERIFIED**

- 未在 CI 中运行；仅本机独立 worktree 验证。
- 未在 `pytest==9.1.1` 下重跑全量（实际使用 9.2.0）；未安装/验证新 dev extra。
- 未通过 GitHub API 核验 PR/Release/tag 状态；仅以 `git ls-remote` 确认 ref。
- `--findings-file` 相对路径未单独跑用例，仅代码级确认与 criterion 共用 helper。
- 未验证 POSIX/其它 OS 下绝对路径判定；仅 Windows 11 AMD64。
- 测试 venv 为先前复核复用，未为本轮重新安装依赖。
- 未观察 PM-02 工作区实时状态；未验证提交签名（仅为身份声明）。
