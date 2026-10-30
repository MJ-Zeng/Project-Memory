# 独立复核报告：TEST-HARDEN-002（TEST-HARDEN-R2）

- 复核者：PM-03（独立会话，无历史上下文）
- 复核日期：2026-10-30
- 复核依据：`import-workspace/PM02_TEST_HARDEN_R2_TASK_CARD.md`（唯一判据）
- 执行者交接：`tasks/PM02-test-harden-r2-handoff-20261030T033846Z.md`（仅作输入，未采信其结论）

## 0. 复核对象与隔离

| 项 | 值 |
|---|---|
| 私库 | `git@github.com:MJ-Zeng/Project-Memory.git` |
| 基线 | `165fa55e070c622261eaf68bc414a2adbee44c23`（`dev/v1.0`） |
| 测试变更提交 | `9b0e75fd21bbe9384a062b8b160ec8245b25e4c3` |
| 分支顶点（含 handoff） | `ba3589e0a56af541ba92762b2b2001b863a4e5ec` |
| 复核工作区 | `pm-pilot-03` 内 `review/TEST-HARDEN-R2/{rel-base,rel-target,rel-tip}`（detached） |
| 解释器 | `C:/SoftWare/Anconda/python.exe`（Python 3.12.4 / pytest 9.1.1，位于复核 worktree 之外） |

所有数字与退出码均为本会话在自建 worktree 中实测；未采信执行者 handoff 中的任何数字。
原始日志保存在 `review/TEST-HARDEN-R2/out/`（本地未跟踪，不入库）。

---

## 1. 结论

**PASS（仅就任务卡 §5 的 1–7 项验收门槛而言）。**

任务卡 §5 的 7 项门槛全部实测通过：改动范围合规、新增测试逐字等于 §3、负对照按预期先失败后通过、默认与 OpenSSL 双门槛均 257 passed / 2 skipped、审计多重集与基线完全一致、reconcile `--fail-on high` 退出 0、无残留。

另有 **1 项非阻塞偏差（D-1）**：执行者 handoff §8/§9 自称“尚未 push”，但远端 `test/harden-input-decoys-20261030` 已经存在且指向 `ba3589e`。该分支在任务卡 §6 中是**允许** push 的，故不构成流程越界；但 handoff 的远端状态陈述与实际不符。

**本报告不构成合并批准。** 合并决定由人类复核者作出；本报告不对 `dev/v1.0` 的合并作任何授权。

---

## 2. 逐条核对

### 2.1 范围（任务卡 §2 / §5-1）

命令与输出：

```
$ git show --stat 9b0e75f
 tests/test_project_memory.py | 44 ++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 44 insertions(+)

$ git show --stat ba3589e
 ...PM02-test-harden-r2-handoff-20261030T033846Z.md | 114 +++++++++++++++++++++
 1 file changed, 114 insertions(+)

$ git diff --name-status 165fa55..9b0e75f
M	tests/test_project_memory.py

$ git diff --numstat 165fa55..9b0e75f
44	0	tests/test_project_memory.py
```

- 变更提交只含 `tests/test_project_memory.py`：**+44 / -0**，净增 44 ≤ 60。✅
- handoff 为**单独一个提交** `ba3589e`，只新增 `tasks/PM02-test-harden-r2-handoff-20261030T033846Z.md`（+114）。✅
- `165fa55..ba3589e` 共 2 个提交，顺序为测试提交 → handoff 提交。✅
- 禁止路径逐项检查：`project_memory/`、其它测试、`pyproject.toml`、`docs/`、`skill/`、`docs/decisions/`、`.project-memory/`、`evidence/`、`bin/`、`_project_memory_launcher.py`、`pilot/` **全部零改动**（`--name-status` 仅有上述 1 个文件）。✅

### 2.2 语义（任务卡 §3 / §5-2）

- 新增测试方法**恰 2 个**：
  - `test_cli_relative_criterion_evidence_ignores_nonempty_cwd_decoy`（目标文件第 1871 行）
  - `test_cli_relative_findings_file_ignores_cwd_decoy`（目标文件第 1891 行）
- 插入位置正确：位于既有 `test_cli_relative_criterion_evidence_resolves_against_repo`（1855）之后、`test_cli_absolute_findings_file_unchanged`（1915）之前。✅
- **逐字比对**：把任务卡 §3 代码块（43 行）与提交内容的前 43 行做 `diff`：
  ```
  43/43 IDENTICAL
  sha256 均为 e93a1dcc04ca1204d33bf9cf8723eb1adb3f3643ff79b37389819f00ec976f94
  ```
  第 44 行只是两方法之间的标准空行分隔符（`\n\n` 结尾）。✅
- **既有测试与 helper 未改动**：`git diff -U0 165fa55..9b0e75f` 只有一个纯新增 hunk（`@@ -1870,0 +1871,44 @@`），0 删除；`_prepare_verify_runs`、`_cli_outside_repo` 与既有测试体逐字未变。✅
- **测试数量净增**：`pytest --collect-only -q` 基线 257 → 目标 259，恰 +2。✅
- **断言区分力（非同义反复）**：
  - 测试 1 的诱饵是从 repo 映射深拷贝后仅把 `evidence_id` 改为 `EV-DECOY` 的**合法非空完整映射**，断言比对 `evidence_id` 的**身份**（必须为 `EV-PATH`），并额外断言 cwd 诱饵文件未被改动。
  - 测试 2 在 repo 内写 `findings.json`（`repo finding`）、在 cwd 写内容不同的 `findings.json`（`cwd decoy finding`），断言 `payload['defects']` 的 summary 来自 **repo** 那份。
  - 代码数据流佐证：`cli.py:519-520` 把 `--findings-file` / `--criterion-evidence` 交给 `repo_path()` 解析后传入 `verify_run`；`coordination.py:2107/2154/2241/2252+` 分别由 `findings` 生成 defects、由 mapping 生成 `criterion_evidence`。身份断言与 defects 来源断言都不是“非空即通过”。
  - 经验证据见 §2.3 负对照：两条断言在未修复实现下确实分别以 `EV-DECOY` 与 `cwd decoy finding` 失败。

### 2.3 独立负对照（任务卡 §4 / §5-3）

自建 worktree `review/TEST-HARDEN-R2/control`（detached 于 `165fa55`），复制含两条新测试的测试文件，`git checkout 81c5531 -- project_memory/cli.py`（`grep -c 'def repo_path'` = 0，确认未修复）。

**未修复版（81c5531 cli.py）→ 2 failed，exit 1，5.63s：**

```
E           AssertionError: 'EV-DECOY' != 'EV-PATH'
E           - EV-DECOY
E           + EV-PATH
tests\test_project_memory.py:1887: AssertionError

E           AssertionError: Lists differ: ['cwd decoy finding'] != ['repo finding']
E            First differing element 0:
E           'cwd decoy finding'
E           'repo finding'
tests\test_project_memory.py:1911: AssertionError

FAILED ...::test_cli_relative_criterion_evidence_ignores_nonempty_cwd_decoy
FAILED ...::test_cli_relative_findings_file_ignores_cwd_decoy
2 failed in 5.63s
```

- 两条均为**可读 AssertionError**，**未出现 TypeError**（说明非空诱饵被读到，正是本轮要关闭的边界）。✅
- 诱饵内容断言未触发失败，说明失败点在于“读错来源”，而非“诱饵被改动”。

**恢复修复版（`git checkout HEAD -- project_memory/cli.py`，`repo_path` count = 1，`git diff HEAD -- cli.py` 0 行）→ 4 passed，exit 0，10.67s**（含两条新测试 + 两条既有同类测试）。✅

回退**未提交**：`git status --porcelain` 只剩我复制进去的 ` M tests/test_project_memory.py`，`cli.py` 无差异。对照 worktree 已删除（目录已清空并移除注册）。

### 2.4 全量双门槛（任务卡 §5-4）

在 `rel-target`（`9b0e75f`）内执行：

| 门槛 | 结果 | 退出码 | pytest 耗时 | 墙钟 |
|---|---|---|---|---|
| `python -m pytest -q` | **257 passed, 2 skipped** | **0** | 203.68s | 204s |
| `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q` | **257 passed, 2 skipped** | **0** | 165.17s | 167s |

与期望 257 passed / 2 skipped、exit 0 完全一致。✅

### 2.5 审计（任务卡 §5-5）

`PROJECT_MEMORY_PYTHON=C:/SoftWare/Anconda/python.exe ./bin/project-memory audit --scope current`，三侧各跑一次，均 exit 0：

| 侧 | total | high | medium | low | 退出码 |
|---|---|---|---|---|---|
| 基线 `rel-base`（165fa55） | 40 | 0 | 16 | 24 | 0 |
| 目标 `rel-target`（9b0e75f） | 40 | 0 | 16 | 24 | 0 |
| 顶点 `rel-tip`（ba3589e） | 40 | 0 | 16 | 24 | 0 |

按 `(severity, code, location)` 多重集精确比对：

```
base==target: True
target==tip:  True
added (target-base): 0  {}
removed (base-target): 0  {}
（每侧 40 条，21 个不同键）
```

新增 0、减少 0、high 0 / medium 16 / low 24。✅

### 2.6 reconcile（任务卡 §5-6）

`./bin/project-memory reconcile --fail-on high`（目标侧）：

```
EXIT=0
state: needs_attention
counts: {'high': 0, 'low': 24, 'medium': 16}
items: 40
```

`--fail-on high` 退出 0；`state=needs_attention` 与 16 medium / 24 low 一致（未触发 high 门槛）。✅

### 2.7 残留（任务卡 §5-7）

跑完全量测试 + 审计 + reconcile 后，三个 worktree 分别检查：

```
rel-base / rel-target / rel-tip:
  git status --porcelain            → 空
  find . -name findings.json        → 无
  find . -name criterion-evidence.json → 无
```

测试 fixture 的 `self.repo` 是 `tempfile.TemporaryDirectory()`，写入的 `findings.json` / `criterion-evidence.json` 均随临时目录清理；仓库树无任何诱饵残留。✅

### 2.8 远端状态（任务卡 §8）

```
$ git ls-remote origin refs/heads/test/harden-input-decoys-20261030 refs/heads/dev/v1.0
165fa55e070c622261eaf68bc414a2adbee44c23	refs/heads/dev/v1.0
ba3589e0a56af541ba92762b2b2001b863a4e5ec	refs/heads/test/harden-input-decoys-20261030
```

- `dev/v1.0` 仍为基线 `165fa55`，**未见合并**。✅
- 执行者分支已在远端，顶点 `ba3589e`（与本地一致），**2 个提交**（测试 + handoff）。
- **与 handoff 矛盾**：handoff（提交内文件与 `pm-pilot-02` 副本 sha256 相同，`6540cd8a…`）§8 写“尚未 push”，§9 写“执行者未自动 push”；但远端 ref 已存在。属陈述与实际不符（见 D-1）。

---

## 3. 偏差清单

| ID | 偏差 | 影响 | 处置建议 |
|---|---|---|---|
| D-1 | handoff §8/§9 称“尚未 push / 执行者未自动 push”，但远端 `test/harden-input-decoys-20261030` 已指向 `ba3589e` | 非阻塞：push 本身是任务卡 §6 允许的动作；仅 handoff 的远端状态陈述不准确，不影响代码与测试判据 | 由执行者/人类说明“由谁、何时 push”；后续 handoff 应在 push 后更新该节，或明确“未验证远端” |

未发现其它偏差。执行者 handoff 中的负对照片段、双门槛计数、审计计数与本会话实测一致；耗时数值因机器负载不同略有差异（不影响判定）。

---

## 4. NOT VERIFIED

- 未核实该远端分支 push 的**操作者身份与时间**（只读取了 ref，不查 GitHub 审计日志）。
- 未复跑执行者当时的临时 worktree 路径；负对照使用本会话自建 worktree，结论独立。
- 未单独跑基线全量 `pytest`（仅 `--collect-only` 得 257；目标实测 257 passed / 2 skipped 且净增恰 2，基线通过数据此推得）。
- 未验证 push 授权链条是否符合团队流程（超出任务卡判据）。
- 未做 Windows 以外平台或不同 Python 版本的交叉验证。

---

## 5. 复核行为边界

- 仅在 `pm-pilot-03` 内工作；未写入 `pm-pilot-02`，未使用 `project-memory-mvp`。
- 未修改执行者分支、未合并、未打 tag/Release、未建 PR。
- 负对照的 `cli.py` 回退未提交；临时 worktree 已删除。
- 本报告提交在独立分支 `review/test-harden-r2`（基于基线 `165fa55`），仅含本文件。

---

**本报告不构成合并批准，也不代表对 `dev/v1.0` 的任何合并授权。**
