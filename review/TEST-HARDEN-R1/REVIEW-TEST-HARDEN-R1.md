# TEST-HARDEN-001 独立窄复核报告（PM-03）

- 复核对象：`origin/test/harden-relpath-20261030`
  - 变更提交：`47b2dd70b1931f18c6dba8f8107165f25844e877`（父 `8510919`）
  - handoff 提交：`5f87c69e8c53b0d14ef5f0b2813d36626bc4f093`（父 `47b2dd7`，分支顶点）
- 基线：`85109195dda74a5b77a11756003686f93c458863`（`origin/dev/v1.0`，实测与派单一致）
- 复核时间：2026-10-30
- 复核环境：Windows 11 AMD64；Python 3.12.4；pytest 9.2.0；解释器位于复核 worktree 之外（`review/HYGIENE-R1/venv/Scripts/python.exe`）
- 隔离方式：在 `pm-pilot-03` 克隆中 `git fetch origin test/harden-relpath-20261030 dev/v1.0`，建立 detached worktree：`rel-base`=`8510919`、`rel-target`=`47b2dd7`、`rel-tip`=`5f87c69`；另建 `control` worktree 做负对照；PM-02 目录未改动。
- 输入边界：PM-02 handoff 仅作输入，未用于任何结论；下列结论均对应本轮自行执行的命令与输出。
- 结论：**PASS**（附测试强度边界，见 §8）

---

## 1. 变更范围（派单第 1 条）

```bash
git show --stat 47b2dd7
git diff --name-status 8510919..47b2dd7
```

```text
 tests/test_project_memory.py | 4 +++-
 1 file changed, 3 insertions(+), 1 deletion(-)

M  tests/test_project_memory.py
```

变更为 **+3/−1（净 +2 ≤ 12）**，仅一个 hunk，落在 `test_cli_relative_criterion_evidence_resolves_against_repo` 函数体内。handoff 提交 `5f87c69` 另加 `tasks/PM02-test-harden-handoff-20261030T025051Z.md`（+111），单独一个 commit。

范围之外零改动：`project_memory/`、其它测试、`pyproject.toml`、`docs/`、`skill/`、ADR、`.project-memory/`、`evidence/`、`pilot/` 均未出现在 diff 中（`8510919..5f87c69` 仅 `tests/test_project_memory.py` 与 handoff 文件）。

## 2. 语义核对（派单第 2 条）

diff 全文：

```diff
         with tempfile.TemporaryDirectory() as outside:
+            decoy = Path(outside) / 'criterion-evidence.json'
+            decoy.write_text('{"criteria": []}', encoding='utf-8')
             result = self._cli_outside_repo(
                 outside, 'verify', '--target-run', 'run-target',
                 ...
                 '--criterion-evidence', 'criterion-evidence.json')
             self.assertEqual(result.returncode, 2, result.stderr)
             payload = json.loads(result.stdout)
             self.assertTrue(payload['verification']['criterion_evidence'])
-            self.assertFalse((Path(outside) / 'criterion-evidence.json').exists())
+            self.assertEqual(json.loads(decoy.read_text(encoding='utf-8')), {'criteria': []})
```

- 诱饵 `criterion-evidence.json`（内容 `{"criteria": []}`，合法空映射）创建在 `TemporaryDirectory()` 的 `outside` 内，调用时 cwd 仍为 `outside`，`--criterion-evidence` 仍为相对路径。
- 关键断言 `self.assertTrue(payload['verification']['criterion_evidence'])`：若实现仍按 cwd 读取，会拿到空诱饵，`criterion_evidence` 为空（负对照实测见 §3），断言失败；只有读到 repo 内完整映射才会非空。该断言与缺陷语义直接相关，不是同义反复。
- 诱饵存在性/内容断言证明测试没有改写或删除 cwd 文件。
- 原空洞断言 `assertFalse((Path(outside) / ...).exists())` 已删除。
- 测试名、`_prepare_verify_runs`、`_cli_outside_repo` 及其它测试均未改。
- `CoordinationTest.setUp` 的 `self.repo` 是 `tempfile.TemporaryDirectory()`，`tearDown` 调用 `tmp.cleanup()`；诱饵所在的 `outside` 也由 `TemporaryDirectory` 自动清理。实测在 `rel-target` 中运行后 `find . -name criterion-evidence.json` 无命中，`git status --porcelain` 为空，无仓库内残留。

## 3. 独立负对照（派单第 3 条）

在独立 `control` worktree（`47b2dd7`）中把 `project_memory/cli.py` 换为未修复的 `81c5531` 版（其余保留）：

```bash
git worktree add --detach control 47b2dd7
git checkout 81c5531 -- project_memory/cli.py
pytest -q tests/test_project_memory.py -k "relative_criterion_evidence_resolves_against_repo" -v
```

结果：**1 failed**。

```text
>           self.assertTrue(payload['verification']['criterion_evidence'])
E           TypeError: 'NoneType' object is not subscriptable
FAILED tests/test_project_memory.py::CoordinationTest::test_cli_relative_criterion_evidence_resolves_against_repo
```

为确认失败确由“读 cwd 诱饵”导致，在 control 的临时副本中打印了 CLI 输出（未提交，随后还原测试文件）：

```text
DEBUG_STDOUT: {
  "criterion_evidence": [],
  "dry_run": false,
  "kind": "verify_result",
  "mapping": {"covered": [], "execution_covered": [], ...}
```

即未修复版读到 cwd 空诱饵，`criterion_evidence` 为空，`verification` 为 `null`，断言失败。确认负对照有效。

换回 `8510919` 版（`git checkout 8510919 -- project_memory/cli.py`）：

```text
1 passed, 128 deselected
```

control 工作区恢复 clean（`git status --porcelain` 0 行）；负对照改动未提交到任何分支。另核验 `8510919` 的 `cli.py` 与 `cac6a94`（修复版）一致（`git diff cac6a94..8510919 -- project_memory/cli.py` 为空），与 `81c5531` 不同。

## 4. 双门槛回归（派单第 4 条）

在 `rel-target` 内、worktree 外解释器：

| 门槛 | 结果 | 耗时 | 退出码 |
|---|---|---|---|
| 默认 `pytest -q` | 255 passed, 2 skipped | 149.57s | 0 |
| `PROJECT_MEMORY_REQUIRE_OPENSSL=1 pytest -q` | 255 passed, 2 skipped | 146.57s | 0 |

测试总数保持 255（未新增测试函数），2 个 skip 为既有 Windows 符号链接跳过。

## 5. 审计与 reconcile（派单第 5 条）

```bash
# rel-base 8510919 与 rel-tip 5f87c69
./bin/project-memory audit --scope current      # 均 exit 0
./bin/project-memory reconcile --fail-on high   # rel-tip, exit 0
```

| 指标 | 基线 8510919 | 顶点 5f87c69 |
|---|---|---|
| 总数 | 40 | 40 |
| high | 0 | 0 |
| medium | 16 | 16 |
| low | 24 | 24 |
| 新增三元组 | — | **0** |
| 减少三元组 | — | **0** |

- 多重集逐项相同；减少为 0，无条目可列。
- `entry_doc_*` finding：0；`tests/` 下 finding：0。
- `reconcile --fail-on high`：**exit 0**，`state=needs_attention`，`counts={high:0, medium:16, low:24}`，items 40。

## 6. 分支与远端状态

```bash
git ls-remote origin refs/heads/test/harden-relpath-20261030 refs/heads/dev/v1.0
# 5f87c69...  refs/heads/test/harden-relpath-20261030
# 8510919...  refs/heads/dev/v1.0
```

任务卡允许 push 供复核；实测分支已推送至 `5f87c69`，`dev/v1.0` 仍为 `8510919`，未见合并/改写。未见 PR/tag/Release 动作（未通过 GitHub API 核验，见 NOT VERIFIED）。

## 7. 交付边界

- 变更提交 1 个（`47b2dd7`）+ handoff 1 个（`5f87c69`）。
- 未改动产品代码、其它测试、pyproject、docs、skill、ADR、`.project-memory/`、`evidence/`、`pilot/`。
- 未创建 Goal/Run；未新增仓库内 fixture。
- 本报告不构成合并批准。

## 8. 口径偏差与测试强度边界

1. **负对照的失败形态是 `TypeError` 而非普通断言失败**：未修复版输出的 `verification` 为 `null`，测试直接下标 `payload['verification']['criterion_evidence']` 触发 `TypeError`。测试确实失败，满足卡要求；但若要更清晰的失败信息，可先断言 `payload.get('verification')` 非空。属可读性改进，不影响“能区分”的结论。
2. **诱饵为“空映射”而非“完整映射”**：该测试能区分“读 repo 完整映射”与“读 cwd 空诱饵”；若 cwd 诱饵恰好包含与 repo 等价的完整映射，未修复实现仍可能通过。这是卡面指定的诱饵形态，属测试强度边界，不是本次改动的缺陷；后续如需更强保证，可让诱饵与 repo 映射内容不同且均非空。
3. 卡要求“净增 ≤12”，实际净 +2；测试函数数量不变（仍 255 项）。
4. handoff 路径/内容未作为证据采用；任务卡与派单在范围、负对照基线上一致。

## 9. 结论

**PASS。** 变更仅 `tests/test_project_memory.py` 一个函数体（+3/−1，净 +2），范围与禁止路径均符合；诱饵位于 `TemporaryDirectory`、无仓库残留；新断言能真实区分 repo 映射与 cwd 空诱饵，独立负对照在未修复版失败、修复版通过；双门槛 255/2、exit 0；审计 `40/0/16/24` 完全不变、新增 0、减少 0；reconcile exit 0。偏差与边界见 §8，不影响验收。

本报告仅为复核结论，不是合并批准或人类批准。

**NOT VERIFIED**

- 未在 CI 中运行；仅本机独立 worktree 验证。
- 未在 `pytest==9.1.1` 下重跑（复核 venv 为 9.2.0）；本分支未改 pyproject。
- 未通过 GitHub API 核验 PR/tag/Release 状态；仅以 `git ls-remote` 确认 ref。
- 未验证其它 OS 上 `TemporaryDirectory`/路径行为；仅 Windows 11 AMD64。
- 未验证“cwd 诱饵与 repo 映射均为非空且不同”这一更强场景（卡面未要求）；§8 已记录该强度边界。
- 未观察 PM-02 工作区实时状态；未验证提交签名（仅为身份声明）。
