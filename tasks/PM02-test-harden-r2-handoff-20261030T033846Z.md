# PM-02 执行交接：TEST-HARDEN-002（第一轮受控试点第二轮）

- 执行者：PM-02（独立克隆 `pm-pilot-02`）
- 任务卡：`import-workspace/PM02_TEST_HARDEN_R2_TASK_CARD.md`
- 基线：`165fa55e070c622261eaf68bc414a2adbee44c23`（`origin/dev/v1.0`，PR #39 合并头）
- 分支：`test/harden-input-decoys-20261030`
- 本交接文件的结论状态：**执行者如实记录，未下 PASS 结论**；PASS 由 PM-03 独立复核给出。

## 1. 提交

| 提交 | SHA | 内容 |
|---|---|---|
| 测试变更 | `9b0e75fd21bbe9384a062b8b160ec8245b25e4c3` | `tests/test_project_memory.py` 追加 2 个测试方法 |
| 本 handoff | （见该文件所在提交） | `tasks/PM02-test-harden-r2-handoff-20261030T033846Z.md` |

## 2. 改动范围（`git diff 165fa55..9b0e75f`）

- `git diff --numstat 165fa55..9b0e75f` → `44	0	tests/test_project_memory.py`（净增 44 行，0 删除；≤ 60）
- `git diff --name-only 165fa55..9b0e75f` → 仅 `tests/test_project_memory.py`
- `git diff -U0` 显示为纯新增行（一行 `@@ -1870,0 +1871,44 @@`），未改动任何既有方法/helper/测试名
- 新增测试方法恰 2 个（`git show 9b0e75f:tests/test_project_memory.py`）：
  - `test_cli_relative_criterion_evidence_ignores_nonempty_cwd_decoy`（第 1871 行）
  - `test_cli_relative_findings_file_ignores_cwd_decoy`（第 1891 行）
- 代码逐字采用任务卡 §3，未重命名、未改断言、未新增 helper，未改 `_prepare_verify_runs`。

## 3. 负对照（§4，仓库外临时 worktree，detached 于 `165fa55`）

过程：`git worktree add --detach <TEMP>/pm02-nc-20261030 165fa55` → 复制含两条新测试的 `tests/test_project_memory.py` → `git checkout 81c5531 -- project_memory/cli.py`（未修复版）→ 只跑两条新测试；再 `git checkout HEAD -- project_memory/cli.py`（恢复修复版）→ 复跑。

先核实 `81c5531` 的 `cli.py` 确为未修复版：`grep -c "def repo_path" project_memory/cli.py` 在未修复版为 `0`，恢复后为 `1`。`git diff 81c5531 165fa55 -- project_memory/cli.py` 显示差异正是 `repo_path()` 的引入与 verify 分支两行改写。

### 3.1 未修复版（81c5531 cli.py）→ 2 failed，exit 1

```
FF                                                                       [100%]
...
E           AssertionError: 'EV-DECOY' != 'EV-PATH'
...
E           AssertionError: Lists differ: ['cwd decoy finding'] != ['repo finding']
...
FAILED tests/test_project_memory.py::CoordinationTest::test_cli_relative_criterion_evidence_ignores_nonempty_cwd_decoy
FAILED tests/test_project_memory.py::CoordinationTest::test_cli_relative_findings_file_ignores_cwd_decoy
2 failed in 6.09s
```

两条均为可读的 `AssertionError`；**未出现 `TypeError`**；诱饵文件未被改动（断言 `decoy` 内容未被触发失败即说明仍保持原样）。

### 3.2 恢复修复版（HEAD cli.py）→ passed，exit 0

复跑两条新测试 + 两条既有同类测试（`test_cli_relative_criterion_evidence_resolves_against_repo`、`test_cli_absolute_findings_file_unchanged`）：

```
....                                                                     [100%]
4 passed in 11.83s
```

- 负对照回退（`git checkout HEAD -- project_memory/cli.py`）**未提交**；恢复后临时 worktree 内 `git status --porcelain` 只有 ` M tests/test_project_memory.py`（即我复制进去、未提交的测试文件），`cli.py` 无本地改动。
- 临时 worktree 已 `git worktree remove --force` 并 `git worktree prune`，目录已删除。

## 4. 全量双门槛（§5）

解释器：`C:/SoftWare/Anconda/python.exe`（位于仓库外）。

| 门槛 | 命令 | 结果 | 退出码 |
|---|---|---|---|
| 默认 | `C:/SoftWare/Anconda/python.exe -m pytest -q` | `257 passed, 2 skipped in 180.57s` | 0 |
| OpenSSL | `PROJECT_MEMORY_REQUIRE_OPENSSL=1 C:/SoftWare/Anconda/python.exe -m pytest -q` | `257 passed, 2 skipped in 161.21s` | 0 |

合计 259 项（255 基线 + 2 新增 = 257 passed；2 skipped 不变）。

## 5. 审计与 reconcile（§5）

```
PROJECT_MEMORY_PYTHON=C:/SoftWare/Anconda/python.exe ./bin/project-memory audit --scope current
→ counts {'high': 0, 'low': 24, 'medium': 16}  total 40  (exit 0)

PROJECT_MEMORY_PYTHON=C:/SoftWare/Anconda/python.exe ./bin/project-memory reconcile --fail-on high
→ counts {'high': 0, 'low': 24, 'medium': 16}  (exit 0)
```

多重集逐项比对：在 detached 于 `165fa55` 的临时 worktree 内复跑 `audit --scope current`，与当前分支结果按 `(code, location, severity)` 排序比对：

```
cur counts {'high': 0, 'low': 24, 'medium': 16} total 40
base counts {'high': 0, 'low': 24, 'medium': 16} total 40
multisets equal: True
added (in cur not base): 0 removed (in base not cur): 0
```

即 40 条，high 0 / medium 16 / low 24，新增 0、减少 0。该临时 worktree 已删除。

## 6. 残留（§5 第 7 项）

- `git status --porcelain` 输出（跑完全部测试 + 审计后）：
  ```
  ?? PM02_COLD_START_VALIDATION.md
  ?? tasks/PM02-cold-start-handoff-20261029T150500Z.md
  ```
  这两份是任务书明确要求「不要改动」的既有未跟踪文件，非本次产生；**本次任务自身未引入任何工作区改动**（提交后工作树对已跟踪文件干净）。
- 仓库内 `find . -name findings.json -not -path './.git/*'` 无结果；无 `criterion-evidence.json` / 诱饵残留。

## 7. 偏差

- 任务卡 §5 第 7 项文案为「`git status --porcelain` 为空」；实测在提交后仍列出上述两份既有未跟踪文件。因其属于任务书指定的禁区、不得触碰，故未删改。除这两份外无任何条目——偏差仅在于字面「为空」不成立，实质「本次无新增工作区改动」成立。
- 无其它偏差；未修改任何产品代码，未改既有断言。

## 8. NOT VERIFIED

- 未验证推送后的远端状态（尚未 push，见下）。
- 未创建 PR、未合并、未打 tag/Release——按任务要求本就不做，故不属验证缺口。

## 9. 待复核者（PM-03）动作

- 允许的下一步：本分支可 push 供复核（执行者未自动 push，等待指令/流程）。PASS / 合并决定由 PM-03 与人类复核给出，执行者不下结论。
