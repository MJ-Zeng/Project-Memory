# Handoff — PM-02 执行 B-9 外部取证（B9-EXTERNAL-VERIFICATION-001）

- 任务卡：`import-workspace/PM02_B9_EXTERNAL_VERIFICATION_TASK_CARD.md`
- 执行者：PM-02 Developer（`pm02@pilot.invalid`）
- 基线：`30ddd1d841eb88f7061806b6378f97c33c683286`（`dev/v1.0`，即任务卡所述 `30ddd1d`）
- 分支：`feat/b9-external-verification`（已推送 origin）
- 代码顶点提交：`5d0a26c06e3041e636c8751e01d568691ebfa861`（本交接文件随后单独提交；分支最终 tip 以 `git rev-parse feat/b9-external-verification` 为准）
- 生成时间：2026-10-30T15:12Z
- 本文件只记录执行事实与实测命令结果，不给出 PASS/GO 结论；判定属于 PM-03 / PM-01 / 人类审批者。

## 1. 变更清单（`git diff --stat 30ddd1d..HEAD`）

```
 README.md                              |  29 ++-
 project_memory/cli.py                  |  13 +-
 project_memory/coordination.py         | 100 ++++++++--
 project_memory/gh.py                   |  36 ++++
 tests/test_b9_external_verification.py | 328 +++++++++++++++++++++++++++++++++
 5 files changed, 482 insertions(+), 24 deletions(-)
```

| 文件 | 变更 |
|---|---|
| `project_memory/gh.py` | 新增 `GitHubReader.pull_request_ci_status(pr_number)`：读 PR head SHA，聚合该提交全部 check runs |
| `project_memory/coordination.py` | 新增 `_external_ci_status()` / `_ci_payload()`；`_criterion_evidence_entries()` 支持 `external_ci`；`_mapping_summary()` 接收外部验证的 CI 证据；`verify_run()` 新增 `pr_number`，`checks.ci` 记录抓取结果 |
| `project_memory/cli.py` | `verify` 新增 `--pr`，`--evidence-level` 允许 `externally_verified` |
| `tests/test_b9_external_verification.py` | 新增 19 个测试（9 个 API 聚合 + 8 个端到端 + 2 个 CLI 接线） |
| `README.md` | 新增「外部取证（--pr）」小节，更新命令表与凭据说明 |

未改动：`dev/v1.0`、`.github/workflows/`、Goal/审计数据；未开 PR、未合并、未打 tag、未发布 Release。

## 2. 实现要点

- **trust 升级条件**：`status == 'success'` 且 PR head SHA == 被验证执行的 head SHA，才把 `evidence_source: ci` 的 criterion 证据记为 `observed_level: externally_verified` 并置 `external_ci_verified: true`；记录 `trust_level` 才可能达到 `externally_verified`（`min(声明等级, 观测等级)`）。
- **降级条件**：CI 失败/pending/无 check run/列表被截断、head SHA 不匹配、缺少 `GITHUB_REPOSITORY`、网络或 API 错误 → 一律 `agent_claimed`，不抛错、不阻塞。
- **不自动达成**：即使 CI 全绿，记录仍是 `MANUAL_REVIEW_REQUIRED`、`verified=false`，`goal evaluate` 不会满足；`_verification_ok` 仍要求 `mapping_status == 'complete'`，而外部 CI 只给出 `review_required`（CI 成功只证明构建事实，不证明语义覆盖）。
- `checks.ci.provenance` 从 `declared_unfetched` 变为 `github_api`，记录 `pr`、`head_sha`、`head_sha_matches_target`、`truncated`、`runs`；不写入 token（测试断言记录 JSON 不含令牌值）。

## 3. 本地验证实际结果

命令统一 `PYTHONUTF8=1 PYTHONIOENCODING=utf-8`，解释器 `C:/SoftWare/Anconda/python.exe`。

| 检查 | 命令 | 实测结果 |
|---|---|---|
| 新增测试 | `-m pytest tests/test_b9_external_verification.py -v` | **19 passed**（exit 0） |
| 全量测试 | `-m pytest -q` | **276 passed, 2 skipped**（exit 0）；基线为 257 passed + 2 skipped，差值 19 即新增测试 |
| 文档审计 | `-m project_memory.cli audit --scope current` | exit 0；findings **40**（high 0 / medium 16 / low 24），与基线一致 |
| 对账 | `-m project_memory.cli reconcile --fail-on high` | exit 0；仅 low/medium（`docs_*` 既有项），无 high |
| CLI 帮助 | `-m project_memory.cli verify --help` | 显示 `--evidence-level {agent_claimed,locally_observed,externally_verified}` 与 `--pr PR_NUMBER` |

覆盖率：本机 `C:/SoftWare/Anconda/python.exe` 未安装 `coverage` / `pytest-cov`（`No module named coverage`），本轮**未实测覆盖率百分比**，也未联网安装。新增分支与测试的对应关系：

| 新增分支 | 覆盖测试 |
|---|---|
| `pull_request_ci_status` 成功/失败/pending，且失败优先于 pending | `test_all_success_is_success`、`test_any_failure_is_failure`、`test_incomplete_run_is_pending`、`test_failure_dominates_pending` |
| 空/截断/非 success 结论 → error 或 failure | `test_no_check_runs_is_error_not_success`、`test_truncated_check_run_list_is_error`、`test_non_success_conclusion_is_not_green` |
| 非法 PR 号、缺 head SHA | `test_invalid_pr_number_is_rejected`、`test_missing_head_sha_is_rejected` |
| CI 绿 + SHA 匹配 → externally_verified | `test_green_ci_on_verified_commit_raises_trust` |
| 诱饵 SHA / 失败 / pending / 缺仓库变量 / API 异常 → agent_claimed | `test_decoy_head_sha_degrades_to_agent_claimed`、`test_failing_ci_degrades_to_agent_claimed`、`test_pending_ci_degrades_to_agent_claimed`、`test_missing_github_repository_degrades`（含 `fetch.assert_not_called`）、`test_api_error_degrades_without_raising` |
| 声明 externally_verified 必须有 --pr | `test_externally_verified_without_pr_is_rejected` |
| 旧行为（无 --pr 只声明 CI）保持 agent_claimed | `test_declared_ci_without_external_fetch_stays_agent_claimed` |
| CLI `--pr` 透传 | `test_parser_accepts_pr_and_externally_verified`、`test_cli_threads_pr_into_verify` |

## 4. 负对照

**离线回退对照**：在基线 `30ddd1d` 的临时 worktree（`git worktree add --detach`）里放入同一份 `tests/test_b9_external_verification.py`：

```
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 C:/SoftWare/Anconda/python.exe -m pytest tests/test_b9_external_verification.py -q
=> 18 failed, 1 passed in 3.79s
   baseline_pytest_exit=1
```

- 唯一在基线通过的是 `test_externally_verified_without_pr_is_rejected`——它断言的正是旧行为（基线无条件拒绝 `externally_verified`），符合预期。
- 其余 18 个测试在基线失败（`GitHubReader` 无 `pull_request_ci_status`、`verify_run` 不接受 `pr_number`、CLI 无 `--pr`），证明这些测试锁的是本分支的新行为而非空断言。
- worktree 用完已删除（`git worktree remove --force`）。

**带内对照（诱饵）**：`test_decoy_head_sha_degrades_to_agent_claimed` 使用非空且与真源不同的诱饵 SHA `f*40`：API 报 success，但 `head_sha` 不等于被验证提交，断言 `observed_level == agent_claimed`、`external_ci_verified is False`、`result['verification'] is None`，且 `result['ci']['head_sha_matches_target'] is False`。

## 5. 偏差与注意事项

1. **函数名与任务卡不符**：任务卡要求修改 `coordination.py` 的 `verify_goal_achievement`（约 991-996 行），但该函数在本仓库不存在（`grep` 无匹配）。同一行号范围实际属于 `_criterion_evidence_entries()`，因此按真实代码结构在 `_criterion_evidence_entries()` + `_mapping_summary()` + `verify_run()` 中实现同样语义。请 PM-03 按此审阅。
2. **CLI 形状**：任务卡示例 `verify --pr 42 <target> <verifier> <standard>` 省略了现行必填的 `--evidence-level`。保持必填，改为把 `externally_verified` 加入可选值，并要求它必须配合 `--pr`；不满足时直接报错（保留 R-1 的「不能只靠声明」）。
3. **聚合优先级修正**：任务卡伪代码按循环「后写覆盖前写」，结果依赖 check run 顺序。实现改为确定性优先级：失败（已完成的非 success）> pending > success；**空 check runs 或 `total_count` 大于返回条数（截断）返回 `error` 而不是 `success`**，避免「没配 CI」被读成绿。结论只有 `success` 才升级信任。
4. **`skipped`/`neutral` 视为非绿**：按任务卡「结论必须为 success」的字面语义处理，偏保守。
5. **记录仍不自证**：B-9 只把 CI 结论变成机器可读事实，记录依旧 `verified=false`、`MANUAL_REVIEW_REQUIRED`；如需真正达成 Goal，仍需仓库外信任锚签名（B-8 范围）。
6. **提交范围**：未使用 `git add -A`。工作区原有未跟踪文件 `PM02_COLD_START_VALIDATION.md` 与 `tasks/PM02-cold-start-handoff-20261029T150500Z.md`（上一轮冷启动任务遗留）**未纳入本次提交**，仍保持未跟踪。
7. **未验证项**：未对真实 GitHub PR 发起联网抓取（离线、无凭据）；API 形状按 GitHub REST `GET /repos/{owner}/{repo}/pulls/{n}` 与 `GET /repos/{owner}/{repo}/commits/{sha}/check-runs` 的文档字段实现，并用桩响应测试。托管 runner 上的 CI 结果需 PM-01 触发 PR 后确认。

## 6. 后续（不属于本执行者）

- PM-03 独立复核（必须包含对本分支负对照的复跑）。
- PM-01 建 PR → 等托管 CI 绿 → 合并 → 合并头复跑；人类按 S2 纪律审阅 PR。
- 未做：PR、合并、tag、Release。
