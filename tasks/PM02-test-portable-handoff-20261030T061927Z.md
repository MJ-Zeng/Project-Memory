# 交接 — TEST-PORTABLE-001 修复 CI 暴露的三处测试环境假设

- 任务 ID：`TEST-PORTABLE-001`
- 执行者：PM-02（独立克隆 `pm-pilot-02`）
- 分支：`fix/test-portability-20261030`（从 `44a56954c91899b499dfd010edffbde8b9f8df33`，即 `origin/dev/v1.0`）
- 决策归属：PM-01（2026-10-30 人类授权 CI 由 PM-01 决定）
- 判定：本文件只记录执行事实与实测数字，不给出 PASS/GO 结论。

## 1. 改了什么

仅 3 个测试文件，净 `+21/−5`（`git diff --numstat 44a5695..9a93172`）：

| 文件 | +/− |
|---|---|
| `tests/test_authority_verifier.py` | 6/1 |
| `tests/test_repo_identity.py` | 8/2 |
| `tests/test_security_rc3.py` | 7/2 |

具体三处逐字采用任务卡 §2 “改后”代码：

1. `test_repo_identity.py::test_relative_and_absolute_paths_agree`：先 `os.chdir(Path(self.repo).anchor)`，在仓库自身盘符内计算相对路径，`finally` 恢复原 cwd；绝对路径断言保留。
2. `test_security_rc3.py::test_relative_repo_path_does_not_raise`：同上，在仓库盘符内计算 `relative`，`finally` 恢复。
3. `test_authority_verifier.py::test_owner_identity_comes_from_the_security_api`：`owner == current` 时直接返回（保留原断言语义）；否则仅放宽为 `assertRegex(owner, r'^S-1-5-32-\d+$', (owner, current))`，并要求 SID 仍满足通用格式。

未改 `project_memory/`、其它测试、文档、配置、依赖；无新增 `skip`/`expectedFailure`/删断言；`git diff` 中不含 `project_memory/`。

## 2. 为什么

GitHub Actions 首次运行 `41011745893`（`pull_request`，head `a6c4cb6`）在托管 Windows runner 上 `3 failed, 255 passed, 1 skipped`：

- 工作区在 `D:`、`tempfile.TemporaryDirectory()` 落在 `C:`，`os.path.relpath` 跨盘抛 `ValueError: path is on mount 'C:', start on mount 'D:'`（两处）。
- 提权 runner 将检出文件所有者记为 `S-1-5-32-544`（BUILTIN\Administrators），断言 `owner == current` 失败（一处）。

两类都是测试对环境（同盘 cwd、非提权所有者）的假设，不是产品缺陷；故只改测试。

## 3. 负对照（本机 `subst X:` 模拟异盘）

命令：

```bash
mkdir -p "$TEMP/subst-probe"
cmd //c subst X: "$(cygpath -w "$TEMP/subst-probe")"
# cwd = X:\ ；仓库外解释器 + PYTHONPATH 指向检出
PYTHONPATH="<repo>" C:/SoftWare/Anconda/python.exe -m pytest <三节点> -q
```

| 侧 | 状态 | 三个节点结果 | 退出码 |
|---|---|---|---|
| A 回退修复 | `git checkout 44a5695 -- <三个文件>` | **2 failed, 1 passed**；两处均为 `ValueError: path is on mount 'C:', start on mount 'X:'`（与 CI 同形） | **1** |
| B 恢复修复 | `git checkout HEAD -- <三个文件>` | **3 passed** | **0** |

之后 `cmd //c "subst X: /d"`；`cmd //c subst` 输出为空，无 `X:` 残留，探针目录已删除。

## 4. 验收实测

| # | 项目 | 命令 | 结果 | 退出码 |
|---|---|---|---|---|
| 1 | 范围 | `git diff --name-status 44a5695..9a93172` | 恰 3 个 `M` 测试文件；numstat 合计 21/5 | 0 |
| 2 | 语义 | `git diff 44a5695..9a93172` | 仅上述三段；无 `skip`/`expectedFailure`/`project_memory/` | 0 |
| 3 | 定向（仓库 cwd） | `python -m pytest tests/test_repo_identity.py tests/test_security_rc3.py tests/test_authority_verifier.py -q` | **63 passed, 2 skipped**（23.06s） | **0** |
| 4 | 定向（异盘 cwd `X:\`） | 同上，`PYTHONPATH` 指向检出 | **63 passed, 2 skipped**（22.43s） | **0** |
| 5a | 全量默认 | `python -m pytest -q` | **257 passed, 2 skipped**（156.57s） | **0** |
| 5b | 全量 OpenSSL | `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q` | **257 passed, 2 skipped**（167.19s） | **0** |
| 6 | 审计 | `./bin/project-memory audit --scope current` | 40 条；high/medium/low = 0/16/24；`entry_doc_*` 0；与基线多重集 added 0 / removed 0 | **0** |
| 7 | reconcile | `./bin/project-memory reconcile --fail-on high` | `defects=0`、docs high 0（state=needs_attention） | **0** |
| 8 | 残留 | `git status --porcelain`；`cmd //c subst` | 除两份既有未跟踪文件外无条目；无 `X:` | — |

审计基线的对照方式：在临时 worktree（`git worktree add --detach ... 44a5695`）跑同一 `audit --scope current`，按 `(code, location, severity)` 多重集比较，added=0、removed=0、两侧均 40 条与 0/16/24；用后 `git worktree remove --force` 清理。

skipped 仍为平台限制的两项（符号链接相关），与基线一致，未新增跳过。

## 5. 偏差与 NOT VERIFIED

- **NOT VERIFIED：本地未复现提权 SID 分支。** 本机为非提权环境，SID 用例走 `owner == current` 直接返回分支；`S-1-5-32-*` 放宽分支仅由逻辑审阅，未经本地执行。
- **NOT VERIFIED：未在 GitHub 托管 Windows runner 上验证**；本机用 `subst` 模拟异盘、用非提权身份运行，不能等价替代托管 runner（尤其提权检出）。
- 负对照使用 `git checkout <rev> -- <files>` 回退/恢复，未用 `git stash`；结果与任务卡 §3 一致。
- 未执行不可信代码；`--trusted` 模式未在本任务中使用。
- 未建 PR、未合并、未动 `dev/v1.0`、未打 tag/Release。
- 本文件写作时分支尚未推送；推送后远端状态以 `git ls-remote` 为准（见最终回复）。

## 6. 提交

- 变更提交：`9a9317210dd442ec477ff929d217a8ee698aaa3c`（`test(portable): stop assuming same-drive cwd and non-elevated file owner`）
- handoff 提交：本文件所在提交（单独提交，不含测试改动）
