# Handoff：TEST-HARDEN-001 强化相对路径测试的负对照

- 任务卡：`PM02_TEST_HARDEN_TASK_CARD.md`（`TEST-HARDEN-001`，PILOT-R1）
- 执行者：PM-02（独立克隆 `pm-pilot-02`）
- 分支：`test/harden-relpath-20261030`（允许 push 供 PM-03 复核；未建 PR）
- 基线：`85109195dda74a5b77a11756003686f93c458863`（`origin/dev/v1.0`）
- 变更提交：`47b2dd7`（`test(harden): prove relative verify input reads repo mapping, not cwd decoy`）
- 提交时间（UTC）：2026-10-30T02:50:51Z

## 1. 改动清单（1 个文件）

只改 `test_cli_relative_criterion_evidence_resolves_against_repo` 函数体；测试名、helper、其它测试未动。

```diff
     def test_cli_relative_criterion_evidence_resolves_against_repo(self):
         run_out = self._prepare_verify_runs()
         with tempfile.TemporaryDirectory() as outside:
+            decoy = Path(outside) / 'criterion-evidence.json'
+            decoy.write_text('{"criteria": []}', encoding='utf-8')
             result = self._cli_outside_repo(
                 outside, 'verify', '--target-run', 'run-target',
                 '--verifier-run', 'run-verifier', '--standard', 'relative path',
                 '--verdict', 'pass', '--evidence-level', 'locally_observed',
                 '--test-receipt', run_out['path'],
                 '--criterion-evidence', 'criterion-evidence.json')
             self.assertEqual(result.returncode, 2, result.stderr)
             payload = json.loads(result.stdout)
             self.assertTrue(payload['verification']['criterion_evidence'])
-            self.assertFalse((Path(outside) / 'criterion-evidence.json').exists())
+            self.assertEqual(json.loads(decoy.read_text(encoding='utf-8')), {'criteria': []})
```

`git diff --numstat 8510919..47b2dd7`：`tests/test_project_memory.py 3/1`（净增 2 行，≤12）；无其它文件。
空洞断言已删除；诱饵在 `TemporaryDirectory()` 内创建，未新增 fixture；未改产品代码。

## 2. 负对照（未修复版必须失败）

临时 detached worktree `C:/Users/ZMJ/AppData/Local/Temp/harden-negctl-20261030`（置 `47b2dd7`），把 `project_memory/cli.py` 换成 `81c5531` 版本：

```bash
git worktree add --detach /c/Users/ZMJ/AppData/Local/Temp/harden-negctl-20261030 47b2dd7
git -C /c/Users/ZMJ/AppData/Local/Temp/harden-negctl-20261030 \
    show 81c5531:project_memory/cli.py > .../project_memory/cli.py   # 工作树 diff: 2/8
python -m pytest -q tests/test_project_memory.py::CoordinationTest::test_cli_relative_criterion_evidence_resolves_against_repo
```

未修复版输出（exit 1）：

```text
_ CoordinationTest.test_cli_relative_criterion_evidence_resolves_against_repo _
            self.assertEqual(result.returncode, 2, result.stderr)
            payload = json.loads(result.stdout)
>           self.assertTrue(payload['verification']['criterion_evidence'])
                            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E           TypeError: 'NoneType' object is not subscriptable
tests\test_project_memory.py:1868: TypeError
FAILED tests/test_project_memory.py::CoordinationTest::test_cli_relative_criterion_evidence_resolves_against_repo
1 failed in 2.76s
```

失败原因符合预期：未修复版按 cwd 读到空诱饵 `{"criteria": []}`，mapping 不完整，`verify` 返回 `verification: null`，因此取 `criterion_evidence` 失败。完整日志：`C:\Users\ZMJ\AppData\Local\Temp\harden-negctl-unfixed.log`。

换回基线 `8510919` 版（`git checkout -- project_memory/cli.py`，工作树 diff 为 0）后：

```text
.                                                                        [100%]
1 passed in 2.59s
```

日志：`C:\Users\ZMJ\AppData\Local\Temp\harden-negctl-restored.log`。
负对照的回退未提交（临时 worktree 已 `git worktree remove --force` 删除）；分支中的 `project_memory/cli.py` 与 `8510919` 一致。

## 3. 验收实测

| # | 项目 | 实测 |
|---|---|---|
| 1 | 改动范围 | 仅 `tests/test_project_memory.py`，3/1（净增 2）；handoff 单独提交 |
| 2 | 负对照 | 未修复 `81c5531` cli：**1 failed**（TypeError，verification=null）；恢复 `8510919`：**1 passed**；回退未提交 |
| 3 | 双门槛 | 默认：**255 passed / 2 skipped**，157.64s，exit 0；`PROJECT_MEMORY_REQUIRE_OPENSSL=1`：**255 passed / 2 skipped**，156.23s，exit 0 |
| 4 | 审计 | 自测基线 **40（0/16/24）** → 改后 **40（0/16/24）**；多重集新增 **0**、减少 **0** |
| 5 | reconcile | `--fail-on high` exit **0**，`state=needs_attention`，counts `{high:0, medium:16, low:24}` |

解释器：`/c/SoftWare/Anconda/python`（3.12.4，pytest 9.1.1）；测试总数不变（253 原有 + 2 上一轮新增）。

审计 JSON 与日志（仓库外）：
- 基线审计：`C:\Users\ZMJ\AppData\Local\Temp\harden-before.json`
- 改后审计：`C:\Users\ZMJ\AppData\Local\Temp\harden-after.json`
- 基线 reconcile：`C:\Users\ZMJ\AppData\Local\Temp\harden-reconcile-before.json`
- 改后 reconcile：`C:\Users\ZMJ\AppData\Local\Temp\harden-reconcile-after.json`
- 双门槛日志：`harden-tests-default.log`、`harden-tests-openssl.log`

审计命令：

```bash
PROJECT_MEMORY_PYTHON=/c/SoftWare/Anconda/python ./bin/project-memory audit --scope current
PROJECT_MEMORY_PYTHON=/c/SoftWare/Anconda/python ./bin/project-memory reconcile --fail-on high
```

## 4. NOT VERIFIED

- 未在 CI 运行；两条门槛仅为本机工作区外解释器实测。
- 未修复版失败表现为 `TypeError`（`verification: null`）而非断言消息；这是未修复代码读到空诱饵后的真实输出，未为美化失败而增加额外断言。
- 只验证了 `--criterion-evidence` 的相对路径；`--findings-file` 的同类强化不在本卡范围。
- 未建 PR、未合并、未碰 `dev/v1.0`、未打 tag。
- 工作区两份旧未跟踪文件（`PM02_COLD_START_VALIDATION.md`、`tasks/PM02-cold-start-handoff-20261029T150500Z.md`）保持原样，未提交。

## 5. 复核入口

- 远端分支：`origin/test/harden-relpath-20261030`，变更提交 `47b2dd7`，基线 `8510919`。
- 建议 PM-03：`git diff 8510919..47b2dd7`；按第 2 节复现负对照（临时 worktree + `81c5531` cli），并重跑单测与两条门槛。
- 本 handoff 只是执行事实记录，不构成 PASS。
