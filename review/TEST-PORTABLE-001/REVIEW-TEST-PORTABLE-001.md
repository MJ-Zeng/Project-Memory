# 独立复核报告 — TEST-PORTABLE-001

- 复核者：PM-03（独立会话，无历史上下文）
- 复核时间：2026-10-30
- 复核对象：分支 `fix/test-portability-20261030`，tip `cc6bceba0ce66f2210d25957f2d5cc2562da5172`
- 基线：`44a56954c91899b499dfd010edffbde8b9f8df33`（`origin/dev/v1.0`，PR #42 合并头）
- 变更提交：`9a9317210dd442ec477ff929d217a8ee698aaa3c`（测试改动）；`cc6bceb`（handoff，单独提交）
- 环境：Windows 10.0.26300 x64；Python 3.12.4；pytest 9.1.1；非提权普通用户会话

> 本报告只是技术复核结论。**没有人类批准，也不代表人类已批准**；合并与发布由 PM-01/人类决定。

## 结论：PASS

三处修改仅针对测试的环境假设，保住了原有断言覆盖；反向验证证明放宽后的断言仍能拒绝错误输入；范围、双门槛、审计多重集均与门槛一致。发现的差异全部为非阻断项（见 §7）。残余风险见 §9。

## 1. 复核方式

- 复核对象与基线各自在 `pm-pilot-03` 之外的临时 worktree 干净检出：
  - `git worktree add --detach "$TEMP/pm03-tp-cc6bceb" cc6bceb`
  - `git worktree add --detach "$TEMP/pm03-tp-base" 44a5695`
- 异盘模拟：`cmd //c subst Y: "C:\Users\ZMJ\AppData\Local\Temp\subst-probe-y"`（不复用刚被清理的 `X:`）；结束后 `cmd //c "subst Y: /d"`，`cmd //c subst` 输出为空。
- 所有数字均为本会话实测；未复用任何未提交的中间产物。

## 2. 范围（实测）

命令与退出码均为 0：

```
$ git diff --name-status 44a5695..cc6bceb
A	tasks/PM02-test-portable-handoff-20261030T061927Z.md
M	tests/test_authority_verifier.py
M	tests/test_repo_identity.py
M	tests/test_security_rc3.py

$ git diff --numstat 44a5695..cc6bceb
84	0	tasks/PM02-test-portable-handoff-20261030T061927Z.md
6	1	tests/test_authority_verifier.py
8	2	tests/test_repo_identity.py
7	2	tests/test_security_rc3.py
```

- 测试文件恰 3 个 `M`，合计 **+21/−5**；handoff 为新增 84 行。
- `git diff --name-only 44a5695..cc6bceb -- project_memory/` → 0 条（产品代码零改动）。
- 全量 diff 中 `skipTest|expectedFailure|@unittest.skip` 命中 2 处，均为 handoff 正文句子；**tests/ 内命中 0**。
- 提交拆分：`9a93172` 仅 3 个测试文件（21/5）；`cc6bceb` 仅 handoff（84 行）。

## 3. 语义（逐字比对）

从任务卡 MD 解析 §2.1/§2.2/§2.3 的“改后”代码块，与 `git show cc6bceb:<file>` 的 blob（LF）做逐字包含比对：

| 文件 | “改后”块出现次数 | “改前”块仍在 | 改前块在基线存在 |
|---|---|---|---|
| `tests/test_repo_identity.py` | 1 | 否 | 是 |
| `tests/test_security_rc3.py` | 1 | 否 | 是 |
| `tests/test_authority_verifier.py` | 1 | 否 | 是 |

覆盖面对照：

- `test_relative_and_absolute_paths_agree`：相对路径断言移入“仓库盘符 cwd + try/finally”，**绝对路径断言保留**。
- `test_relative_repo_path_does_not_raise`：仅包一层 chdir/try/finally，`checked['valid']` 断言不变。
- `test_owner_identity_comes_from_the_security_api`：`owner == current` 时直接返回（原等式断言）；不等时仍要求 `assertRegex(owner, r'^S-1-5-32-\d+$')`，且前面的通用 SID 格式断言仍在。**不是无条件跳过**。

## 4. 负对照（异盘实测）

在 worktree 内 `git checkout 44a5695 -- <三个文件>`（未提交），cwd = `Y:\`，`PYTHONPATH` 指向检出：

A 侧（回退修复）：

```
E   ValueError: path is on mount 'C:', start on mount 'Y:'
FAILED ...\tests\test_repo_identity.py::RepoIdentityTest::test_relative_and_absolute_paths_agree
FAILED ...\tests\test_security_rc3.py::SecurityRc3Test::test_relative_repo_path_does_not_raise
2 failed, 61 passed, 2 skipped in 21.98s
退出码 1
```

与 CI 首轮同形（CI 为 `'C:'` / `'D:'`）。

B 侧（`git checkout cc6bceb -- <三个文件>` 恢复，cwd = `Y:\`，三个节点）：

```
...\test_repo_identity.py::RepoIdentityTest::test_relative_and_absolute_paths_agree PASSED
...\test_security_rc3.py::SecurityRc3Test::test_relative_repo_path_does_not_raise PASSED
...\test_authority_verifier.py::AnchorIdentityTest::test_owner_identity_comes_from_the_security_api PASSED
3 passed in 1.11s
退出码 0
```

回退/恢复均未提交，恢复后 `git status --porcelain` 为空，worktree 仍停在 `cc6bceb`。

## 5. 反向验证（关键，mock SID）

用 `unittest.mock.patch.object` 固定 `project_memory.authority._file_owner_sid` 与 `_current_user_sid`（`authority.__file__` 已确认来自被复核检出），单跑 `AnchorIdentityTest::test_owner_identity_comes_from_the_security_api`：

1) owner `S-1-5-21-1-2-3-500`、current `S-1-5-21-9-9-9-500` → 应失败：

```
FAIL: test_owner_identity_comes_from_the_security_api
  File "...\tests\test_authority_verifier.py", line 280, in test_owner_identity_comes_from_the_security_api
    self.assertRegex(owner, r'^S-1-5-32-\d+$', (owner, current))
AssertionError: Regex didn't match: '^S-1-5-32-\\d+$' not found in 'S-1-5-21-1-2-3-500' : ('S-1-5-21-1-2-3-500', 'S-1-5-21-9-9-9-500')
Ran 1 test in 0.039s
FAILED (failures=1)
退出码 1
```

2) owner `S-1-5-32-544`、current `S-1-5-21-9-9-9-500` → 应通过：

```
test_owner_identity_comes_from_the_security_api ... ok
Ran 1 test in 0.035s
OK
退出码 0
```

说明放宽分支只在“所有者是内置组 SID”时放行，普通用户 SID 不匹配仍失败。

## 6. 定向与全量

| 项 | 命令 | 结果 | 退出码 | 耗时 |
|---|---|---|---|---|
| 定向（仓库 cwd） | `python -m pytest -q tests/test_repo_identity.py tests/test_security_rc3.py tests/test_authority_verifier.py` | **63 passed, 2 skipped** | 0 | 21.49s |
| 定向（`Y:\` cwd） | 同上，绝对路径 + `PYTHONPATH` 指向检出 | **63 passed, 2 skipped** | 0 | 20.98s |
| 全量默认 | `python -m pytest -q` | **257 passed, 2 skipped** | 0 | 168.23s |
| 全量 OpenSSL | `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q` | **257 passed, 2 skipped** | 0 | 161.78s |

两项跳过为 `tests/test_security_rc3.py:284/:295` 的“当前平台不允许创建符号链接”，与基线同类平台限制一致，未新增跳过。

## 7. 审计与 reconcile

```
$ PROJECT_MEMORY_PYTHON=C:/SoftWare/Anconda/python.exe ./bin/project-memory audit --scope current
（fix 与基线 worktree 各自运行，均退出码 0）
```

两侧均为 40 条，high/medium/low = **0/16/24**；`entry_doc_*` 0 条。

按 `(severity, code, location)` 排序多重集计算 sha256：

| 侧 | 多重集 sha256 |
|---|---|
| `cc6bceb` | `dde7c4d20e3e4c5baa56c389afa12161c6c941ce64c85e8c34ad9d92009a2385` |
| `44a5695` | `dde7c4d20e3e4c5baa56c389afa12161c6c941ce64c85e8c34ad9d92009a2385` |

两侧完全一致；added 0 / removed 0。findings 按 code 分布：`reference_authority_mismatch` 14、`ambiguous_reference` 14、`unknown_document_status` 4、`broken_reference` 4、`dynamic_artifact_reference` 2、`broken_document_reference` 1、`reference_outside_repository` 1。

```
$ ./bin/project-memory reconcile --fail-on high
退出码 0；summary: defects=0, open_defects=0, docs={high:0, medium:16, low:24}, state=needs_attention
```

## 8. handoff 事实一致性

| handoff 声明 | 实测 | 判定 |
|---|---|---|
| 3 文件 21/5，handoff 84 行 | 一致 | ✅ |
| 负对照 A：2 failed / 1 passed，`ValueError ... 'C:' / 'X:'`，exit 1 | 整文件跑法 2 failed / 61 passed / 2 skipped，失败节点与报错同形，exit 1 | ✅（跑法不同，不矛盾） |
| 负对照 B：3 passed，exit 0 | 一致（1.11s） | ✅ |
| 定向 63/2（两种 cwd） | 一致（21.49s / 20.98s） | ✅ |
| 全量 257/2 ×2，exit 0 | 一致（168.23s / 161.78s；handoff 156.57s / 167.19s） | ✅（耗时环境波动） |
| 审计 40 条 0/16/24，added/removed 0 | 一致，两侧多重集 sha256 相同 | ✅ |
| reconcile defects=0、state=needs_attention、exit 0 | 一致 | ✅ |
| 未新增跳过，仍是两项符号链接 | 一致 | ✅ |
| NOT VERIFIED：本地未复现提权 SID 分支 | 已如实写入 | ✅ |
| NOT VERIFIED：未在 GitHub 托管 runner 验证 | 已如实写入 | ✅ |
| 未建 PR/未合并/未动 `dev/v1.0`/未打 tag | `git ls-remote origin`：`dev/v1.0`=44a5695、fix 分支=cc6bceb、无 tag | ✅ |

## 9. 非阻断偏差

1. handoff 的耗时数字与本机实测相差约 ±10s，属机器负载差异；计数与退出码完全一致。
2. handoff 记负对照 A 为“2 failed, 1 passed”（只跑三节点）；本复核跑整个三文件为“2 failed, 61 passed, 2 skipped”。失败节点、异常类型与盘符形态一致，不构成事实冲突。
3. handoff 明确把“推送后的远端状态”留给最终回复；实测远端分支已在 `cc6bceb`，无 tag、`dev/v1.0` 未移动。
4. `os.chdir` 是进程级全局状态改动；当前测试串行运行，无问题，但记为残余风险。

## 10. NOT VERIFIED

- **未在 GitHub 托管 Windows runner 上验证**：本机用 `subst Y:` 模拟异盘、以普通用户身份运行，不能等价替代 runner 的真实 `D:` 工作区与提权检出。
- **提权 SID 形态本地未真实复现**：本机非提权，真实 `owner != current` 的提权路径只通过 mock 注入做了两侧逻辑验证（见 §5），未在真实提权 shell 中执行。
- 未复核 PR/CI 流水线配置与合并许可（不在本次范围）。

## 11. 残余风险（一句）

若仓库根无法 `chdir`（权限、盘符失效）或测试改为并行执行（全局 chdir 竞态），两处异盘测试仍会失败；SID 用例在提权但所有者既非当前用户也非 `S-1-5-32-*` 的环境（如 SYSTEM 或其他用户 SID）仍会失败。

## 12. 清理

- `git worktree remove --force` 删除 `$TEMP/pm03-tp-cc6bceb`、`$TEMP/pm03-tp-base`，`git worktree prune`；复核用 worktree 均已不在 `git worktree list`。
- `cmd //c "subst Y: /d"` 退出码 0；`cmd //c subst` 输出为空；探针目录已删除。
- 被测分支未做任何提交或修改；`pm-pilot-01` / `pm-pilot-02` 未触碰。
