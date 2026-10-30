# Handoff：RELPATH-FIX-001 verify 输入路径按 `--repo` 解析 + 固定 pytest 版本

- 任务卡：`PM02_RELPATH_FIX_TASK_CARD.md`（`RELPATH-FIX-001`）
- 执行者：PM-02（独立克隆 `pm-pilot-02`）
- 分支：`fix/verify-input-paths-20261030`（已 push 到 origin 供 PM-03 复核；未建 PR）
- 基线：`81c553112950d87bcbb72ead6977c5d48e411ab3`（`origin/dev/v1.0`，DOCS-ALIGN-001 合并后）
- 变更提交：`cac6a94484b305a8f56b6b11ff3cec945d57cfc2`
- 提交时间（UTC）：2026-10-30T02:11:42Z

## 1. 改动清单（4 个文件）

| 文件 | 变更 |
|---|---|
| `project_memory/cli.py` | 新增 `repo_path(repo, value)` helper（4 行）；`verify` 分支的 `findings` / `mapping` 两行改用该 helper（+8/−2，净增 6） |
| `tests/test_project_memory.py` | `CoordinationTest` 内新增 `_prepare_verify_runs`、`_cli_outside_repo` 两个 helper 与 2 个测试（+84/−0） |
| `pyproject.toml` | `[project.optional-dependencies]` 新增 `dev = ["pytest==9.1.1"]`（保留 `semantic`；+1/−0） |
| `docs/OPERATIONS.zh-CN.md` | 第 134 行段落末尾补一句 CLI 路径语义（+1/−1，其余未动） |

未改 `coordination.py` 或其他模块；未改 `bin/`、launcher、`.project-memory/`、`evidence/`、ADR、`CURRENT_STATE.md`、`pilot/`；未创建 Goal/Run。

## 2. 改动前失败证据（基线上运行新测试）

测试在改动前先写入，随后把 `cli.py` 临时回到基线（`git stash push -- project_memory/cli.py`）运行：

```text
.F                                                                       [100%]
================================== FAILURES ===================================
_ CoordinationTest.test_cli_relative_criterion_evidence_resolves_against_repo _
>           self.assertEqual(result.returncode, 2, result.stderr)
E           AssertionError: 1 != 2 : project-memory: 无法读取 JSON criterion-evidence.json：[Errno 2] No such file or directory: 'criterion-evidence.json'
tests\test_project_memory.py:1864: AssertionError
FAILED tests/test_project_memory.py::CoordinationTest::test_cli_relative_criterion_evidence_resolves_against_repo
1 failed, 1 passed, 127 deselected in 5.12s
```

- 完整日志：`C:\Users\ZMJ\AppData\Local\Temp\relpath-tests-before.log`
- 修复后同一命令：`2 passed, 127 deselected in 5.66s`，日志 `C:\Users\ZMJ\AppData\Local\Temp\relpath-tests-after.log`
- 说明差异：第 2 个测试（绝对值 `--findings-file`）在基线即通过——它守护“绝对路径行为不变”，按定义不会因该缺陷失败；卡 §2.2 写“两个都必须失败”，与 AC 第 4 条“至少 1 个用例失败”相比更严，此处如实记录：**改动前 1 failed / 1 passed**。
- 断言字段：任务卡写 `result['criterion_evidence']`，实际 CLI 返回把该字段放在 `verification` 下；测试断言为 `payload['verification']['criterion_evidence']`，未改动产品结构。

## 3. 第 4 节验收实测

| # | 项目 | 实测 |
|---|---|---|
| 1 | 改动范围 | `git diff --numstat 81c5531..cac6a94` 仅 4 个授权文件：OPERATIONS（1/1）、cli.py（8/2）、pyproject（1/0）、tests（84/0）；禁止路径 0 改动 |
| 2 | cli.py 改动 | helper + `verify` 两行；净增 6 行（≤10） |
| 3 | 回归 | 默认：**255 passed / 2 skipped**，142.71s，exit 0；`PROJECT_MEMORY_REQUIRE_OPENSSL=1`：**255 passed / 2 skipped**，144.37s，exit 0（工作区外解释器 `/c/SoftWare/Anconda/python`，pytest 9.1.1，与新增 pin 一致） |
| 4 | 改动前失败 | 见第 2 节，1 个用例失败（exit 1 vs 期望 2，文件按 cwd 解析失败） |
| 5 | 审计 | 自测基线 **40（0/16/24）** → 改后 **40（0/16/24）**；新增三元组 0、减少 0；`docs/OPERATIONS.zh-CN.md` 未新增引用类 finding |
| 6 | reconcile | `--fail-on high` exit **0**，`state=needs_attention`，`counts={high:0, medium:16, low:24}` |

审计 JSON（仓库外）：
- 基线：`C:\Users\ZMJ\AppData\Local\Temp\relpath-before.json`
- 改后：`C:\Users\ZMJ\AppData\Local\Temp\relpath-after.json`
- reconcile（改后）：`C:\Users\ZMJ\AppData\Local\Temp\relpath-reconcile-after.json`

审计命令：

```bash
PROJECT_MEMORY_PYTHON=/c/SoftWare/Anconda/python ./bin/project-memory audit --scope current
```

说明：分支顶点含本 handoff 提交，`81c5531..HEAD` 会多 1 个文件；第 1 条数字对应变更提交 `cac6a94`。

## 4. NOT VERIFIED

- 未在 CI 运行；两条 pytest 仅为本机工作区外解释器实测。
- 未安装或验证 `dev = ["pytest==9.1.1"]` extra 的解析/解析锁（未运行 pip install）；仅确认本机现有 pytest 版本已是 9.1.1。
- 未验证 `--test-log`、`--output`、`--pr-file` 等其它 `type=Path` 参数的 cwd 语义；卡明确要求保持现状，本轮未改动、未新增覆盖。
- 未验证 Windows/WSL2 下不同 cwd 盘符（如 `D:\`）组合的路径解析；本机测试使用系统临时目录，与仓库同盘。
- 未验证该修复对 `verify` 之外命令的影响（helper 仅用于 `verify` 分支）。
- 未建 PR、未合并、未碰 `dev/v1.0`、未打 tag。
- 工作区两份旧未跟踪文件（`PM02_COLD_START_VALIDATION.md`、`tasks/PM02-cold-start-handoff-20261029T150500Z.md`）保持原样，未提交。

## 5. 复核入口

- 远端分支：`origin/fix/verify-input-paths-20261030`，变更提交 `cac6a94`，基线 `81c5531`。
- 建议 PM-03：`git fetch origin fix/verify-input-paths-20261030 && git diff 81c5531..cac6a94`；重跑两个新测试与两条全量门槛。
- 本 handoff 只是执行事实记录，不构成 PASS。
