# PM-02 handoff：B-9 复核偏差修复（D-1/D-2/D-4/D-5）

- 任务：B9-EXTERNAL-VERIFICATION-001（接续 PM-03 复核偏差修复）
- 分支：`feat/b9-external-verification`
- 基线：`30ddd1d`（`origin/dev/v1.0`）
- 修复前顶点：`b5d9ae0`
- 修复提交：`4410cf9798ee68dcbb0327e0e02582bd69696eec`（`fix(b9): cap trust level and record CI fetch provenance`）
- 分支新 tip：`4410cf9`（随后 handoff 单独提交，最终 tip 以 `git rev-parse HEAD` 为准）
- 复核报告：`origin/review/b9-external-verification` 上 `review/B9-EXTERNAL-VERIFICATION/REVIEW-B9-EXTERNAL-VERIFICATION.md`（`16498a2`），只读引用，未修改

## 1. 变更范围

```text
git show --stat 4410cf9
 README.md                              |  6 +--
 project_memory/coordination.py         | 65 +++++++++++++++++++-------
 tests/test_b9_external_verification.py | 85 ++++++++++++++++++++++++++++++++--
 3 files changed, 131 insertions(+), 25 deletions(-)
```

- 未改 `project_memory/gh.py`（无需改）。
- 未改 `skill/`、`docs/`（D-3 文档互斥问题不在本次范围）。
- 未开 PR、未合并、未打 tag、未触碰 `dev/v1.0`。
- `git diff --check` exit 0。

## 2. 偏差处理

### D-1（已修）：非 PASS 不得声明 externally_verified

- `project_memory/coordination.py::_verification_inputs` 新增校验：`evidence_level == 'externally_verified'` 且 `verdict != 'pass'` → `PMError('externally_verified 只适用于 pass；fail/inconclusive 不能声明该等级')`。
- 未改动非 PASS 分支的 `observed_rank = EVIDENCE_TRUST[evidence_level]`，基线 `fail + locally_observed` 的 `trust_level=locally_observed` 保持不变（有回归测试锁定）。
- 校验位于 `verify_run` 的输入校验阶段，早于任何抓取；非 PASS 不会调用 `_external_ci_status`。

### D-2（已修）：caveat 文本与新行为一致

`verify` 结果的 `caveat` 改为：externally_verified 需 `--pr` 并由 GitHub API 实际读取；CI 全绿只证明该提交的构建事实，不证明语义覆盖；review 证据仍只是声明。未使用“已认证”等夸大表述。

### D-4（已修，最小可用）：checks.ci 记录仓库与抓取结果

- `_external_ci_status` 返回 `(status_or_none, info)`；`info = {'repository': slug, 'fetch': 类别}`。
- `_ci_payload` 新增 `repository` 与 `fetch` 字段；`provenance` 语义不变（`declared_unfetched` / `none` / `github_api`）。
- `fetch` 类别：`not_requested` / `ok` / `missing_repository` / `invalid_repository` / `invalid_pr` / `api_error` / `shape_error`。
- 记录只含 slug、pr、head_sha、状态与类别；不含 token、请求头或响应体。

### D-5（已补测试）

新增 4 条仓库内测试：

1. `test_invalid_github_repository_degrades` —— `a`、`a/b/c` 不抛穿、降级为 `agent_claimed`，`ci.fetch='invalid_repository'` 且保留非法 slug。
2. `test_locally_observed_declaration_caps_green_ci_trust` —— 声明 locally_observed + 抓取全绿，`trust_level` 仍为 `locally_observed`，单条证据为 `externally_verified`。
3. `test_fail_locally_observed_keeps_locally_observed_trust` —— 基线行为回归锁定。
4. `test_non_pass_externally_verified_is_rejected` —— fail/inconclusive + externally_verified 在参数校验层被拒绝，且 fetch 从未调用。

同时扩充既有断言：

- `test_green_ci_on_verified_commit_raises_trust`：`ci.repository='owner/repo'`、`ci.fetch='ok'`、caveat 含“不证明语义覆盖”和“review 证据仍只是声明”。
- `test_missing_github_repository_degrades`：`ci.fetch='missing_repository'`、`ci.repository=''`。
- `test_api_error_degrades_without_raising`：`ci.fetch='api_error'`、`ci.repository='owner/repo'`。

测试文件总计 23 条（原 19 + 新 4）。

## 3. 本地验证（干净工作树，`C:/SoftWare/Anconda/python.exe`，`PYTHONUTF8=1 PYTHONIOENCODING=utf-8`）

```text
B9 文件：23 passed in 6.63s
全量 pytest：280 passed, 2 skipped in 160.40s（基线 276 + 新 4）
audit --scope current：exit 0；total 40；high 0 / medium 16 / low 24；entry_doc 0
audit 多重集 vs 基线 30ddd1d：multiset_equal True；added []；removed []
reconcile --fail-on high：exit 0；counts {'high': 0, 'medium': 16, 'low': 24}
```

## 4. 负对照（实跑）

### D-1：回退新增校验后新测试必须失败

临时注释 `_verification_inputs` 中的 D-1 校验后：

```text
pytest -k non_pass_externally_verified
FAILED tests/test_b9_external_verification.py::ExternalVerificationTest::test_non_pass_externally_verified_is_rejected
AssertionError: PMError not raised
1 failed, 22 deselected
```

恢复校验后：

```text
23 passed
```

### D-4：抓取失败时 ci.fetch 必须是类别字符串而非 ok

```text
pytest -k "api_error or missing_github_repository or invalid_github_repository" -v
3 passed, 20 deselected
```

对应断言分别为 `api_error`、`missing_repository`、`invalid_repository`（均非 `ok`）。

## 5. 未验证 / 边界

- 未对真实 PR 或托管 CI 取证（无真实令牌、仓库非公开）；沿用 PM-03 报告第 11 节边界。
- D-3（skill/docs 中仍称 CLI 离线、不接受 externally_verified）按派单约束未处理，建议后续单独任务同步。
- 覆盖率未实测（环境无 coverage 模块）。
- 合并批准与发布不在本 handoff 范围。
