# B9-EXTERNAL-VERIFICATION-001 偏差修复增量复审（PM-03）

**结论：PASS。** 本次 delta 完整落实 D-1/D-2/D-4/D-5 的修复，未发现新的高/中等级问题；D-3 按派单延后，D-6 已关闭。本报告只审增量，不构成合并批准。

- 复审对象：`origin/feat/b9-external-verification` 顶点 `b99cac03e0b71f34c87b61186730a397cc107b24`
  - `4410cf9798ee68dcbb0327e0e02582bd69696eec` fix(b9): cap trust level and record CI fetch provenance（3 files，+131/−25）
  - `b99cac03e0b71f34c87b61186730a397cc107b24` docs: add PM-02 handoff for B-9 deviation fixes（1 file，+105）
- 上轮被审顶点：`b5d9ae045121e215b25c768cce13999bf23b017e`；上轮报告 `16498a2` 上的 `review/B9-EXTERNAL-VERIFICATION/REVIEW-B9-EXTERNAL-VERIFICATION.md`
- 基线：`30ddd1d841eb88f7061806b6378f97c33c683286`（`origin/dev/v1.0`）
- 本报告分支：`review/b9-followup`（从 `origin/dev/v1.0` 新建，未带入上轮报告）
- 环境：Windows 11 10.0.26300；`C:/SoftWare/Anconda/python.exe`（Python 3.12.4）；pytest 9.1.1；`PYTHONUTF8=1 PYTHONIOENCODING=utf-8`
- 隔离：只在 `C:/Temp` 建 detached worktree；未使用真实 GitHub 令牌；未访问本仓库真实 PR/CI；未改代码、未开 PR、未合并、未打 tag、未触碰 `dev/v1.0`。证据只来自仓库文件与本轮实跑输出。

---

## 1. 范围与 delta

```text
git diff --stat b5d9ae0..b99cac0
 README.md                                          |   6 +-
 project_memory/coordination.py                     |  65 +++++++++----
 tasks/PM02-b9-deviation-fixes-handoff-...161201Z.md | 105 ++++++++++++++
 tests/test_b9_external_verification.py             |  85 +++++++++++++-
 4 files changed, 236 insertions(+), 25 deletions(-)

git diff --name-status b5d9ae0..b99cac0
M README.md
M project_memory/coordination.py
A tasks/PM02-b9-deviation-fixes-handoff-20261030T161201Z.md
M tests/test_b9_external_verification.py

git show --stat 4410cf9    # 3 files changed, 131 insertions(+), 25 deletions(-)
git show --stat b99cac0    # 1 file changed, 105 insertions(+)
git diff --check b5d9ae0..b99cac0   # exit 0
```

- 仅 `README.md`、`coordination.py`、测试文件与 handoff 任务文件；无 `.github/`、`.project-memory/`、`fixtures/`、`skill/`、`docs/` 改动。
- **D-3 确认保持延后**：`git diff b5d9ae0..b99cac0 --stat -- skill docs` 无输出。
- `b99cac0` 只新增 handoff，未顺带改代码；`git diff --check` 干净。

---

## 2. 逐项判定

### D-1 非 PASS 不得声明 externally_verified —— 已修复

- 校验位于参数校验层 `project_memory/coordination.py:2078` 的 `_verification_inputs`，新增分支在 `coordination.py:2094-2099`：
  `evidence_level == 'externally_verified' and verdict != 'pass'` → `PMError('externally_verified 只适用于 pass；fail/inconclusive 不能声明该等级')`。
- 调用点在 `coordination.py:2194`，早于 PASS 分支的抓取点 `coordination.py:2247`；非 PASS 分支不会调用 `_external_ci_status`。
- 非 PASS 的 `observed_rank = EVIDENCE_TRUST[evidence_level]`（`coordination.py:2292`）未被本次 delta 改动（`git diff b5d9ae0..b99cac0` 不含该行）；基线 `fail + locally_observed → trust_level=locally_observed` 行为由探针 (ii) 复现。
- 探针 (i)：`fail + externally_verified + --pr 42` 抛 `PMError`，抓取桩 `assert_not_called` 通过；CLI 同一场景 `exit=1`，stderr 为 `project-memory: externally_verified 只适用于 pass；fail/inconclusive 不能声明该等级`。

### D-2 caveat 与新行为一致 —— 已修复

`coordination.py:2390-2396` 实际输出（本轮探针抓取）：

```text
本地 CLI 写出的验证记录没有受保护信任锚的分离签名，因此 status 最多是 MANUAL_REVIEW_REQUIRED，verified 恒为 false。externally_verified 需要 --pr 并由 GitHub API 实际读取；CI 全绿只证明该提交的构建事实，不证明语义覆盖；review 证据仍只是声明。测试收据只证明内容完整性，不证明来源；PASS 仍要求每个必达标准都有绑定提交、独立复核 coverage 的证据映射。
```

- 包含“CI 全绿只证明该提交的构建事实，不证明语义覆盖”与“review 证据仍只是声明”；未出现“已认证/可信认证”等夸大表述（`grep 认证` 无相关命中）。
- 同一结果仍为 `status=MANUAL_REVIEW_REQUIRED`、`verified=False`，未因文本修改放松门禁。

### D-4 checks.ci 记录仓库与抓取类别 —— 已修复

- `_external_ci_status`（`coordination.py:868-904`）返回 `(status_or_none, info)`；`info={'repository','fetch'}`，`fetch` 七类齐全：`not_requested`(880)、`invalid_pr`(884)、`missing_repository`(887)、`invalid_repository`(891)、`api_error`(898)、`shape_error`(901)、`ok`(903)。
- 失败时不写 `ok`：`ok` 仅在 `_provenance == 'github_api'` 且结构为 dict 后设置；此前各类失败均提前返回。
- `_ci_payload`（`coordination.py:2124-2141`）在两种返回分支都写入 `repository` 与 `fetch`；`provenance` 仍只有 `none` / `declared_unfetched` / `github_api` 三种语义，本次 delta 未改这些取值。
- 实际记录仅含 slug、类别、pr/head/status/runs 等；探针在所有失败类别上断言 `json.dumps(result)` 不含测试令牌 `secret-token`；代码不收集请求头或响应体。
- 未请求抓取时不泄露环境 slug：`fail + locally_observed + GITHUB_REPOSITORY=owner/repo + --pr 42` 实测 `fetch=not_requested`、`repository=''`，抓取桩未调用。
- 非法 slug 保留原值便于排查（`invalid_repository` + 原 slug）；缺配置为 `missing_repository` + 空串。
- README 改动与实际输出一致：`README.md:117` 的 `repository` / `fetch` 字段名、七类取值与代码逐一对应；`README.md:112` 的“仅 pass 路径；非 pass 根本不会抓取”与实现一致。仅做字段一致性核对，未做文风审查。

### D-5 新增 4 条测试且断言有效 —— 已修复

| 测试 | 关键断言 |
|---|---|
| `test_invalid_github_repository_degrades` | `a`、`a/b/c` 不抛穿；`status=PARTIAL_COVERAGE`；`observed_level=agent_claimed`；`provenance=none`；`fetch=invalid_repository`；保留原 slug；抓取桩未调用 |
| `test_locally_observed_declaration_caps_green_ci_trust` | 全绿 CI 下 `trust_level=locally_observed`；单条证据 `observed_level=externally_verified`；`external_ci_verified=True`；`fetch=ok` |
| `test_fail_locally_observed_keeps_locally_observed_trust` | `status=FAILED`、`verified=False`、`trust_level=locally_observed` |
| `test_non_pass_externally_verified_is_rejected` | fail/inconclusive 均抛 `PMError`；错误文本含“只适用于 pass”；抓取桩未调用 |

- 测试文件共 23 条（原 19 + 新 4）；全量 280 = 上轮已核基线 276 + 新增 4。
- **测试不联网**：用 socket `connect/connect_ex/create_connection/getaddrinfo` 全部抛错的插件复跑 `pytest tests/test_b9_external_verification.py -q -p nonet` → **23 passed**；被测路径中的 `GitHubReader.pull_request_ci_status` 全部被 mock 或替换为桩。

---

## 3. D-6 与新发现问题

| 编号 | 级别 | 位置 | 描述 | 处置 |
|---|---|---|---|---|
| D-6 | 提示（已关闭） | 本轮 handoff §1 | 上轮指出的“diff stat 为生成时点值”问题已说明；本轮 `4410cf9` 的 3 文件 +131/−25 与 `git show --stat` 一致，最终 tip 明确以 `rev-parse` 为准 | 无需动作 |
| 新发现 | 无 | — | 未发现新的高/中/低等级偏差 | — |

观察（非偏差）：`invalid_pr` 类别经 `pass + locally_observed + --pr 0` 可达（实测 `PARTIAL_COVERAGE`、`fetch=invalid_pr`）；`externally_verified` 会被更早的 `--pr` 校验拦截。该分支 `repository` 为空串，与 README“未发起抓取时为空串”的字面一致，无需动作。

---

## 4. 负对照（实跑）

### (a) 回退 D-1 新校验后测试必须失败

在独立 worktree（`b99cac0`）把该分支改为 `if False and ...` 后：

```text
pytest -q tests/test_b9_external_verification.py -k non_pass_externally_verified
FAILED tests/test_b9_external_verification.py::ExternalVerificationTest::test_non_pass_externally_verified_is_rejected
E   AssertionError: PMError not raised
1 failed, 22 deselected        # exit 1
```

`git checkout -- project_memory/coordination.py` 恢复后：

```text
pytest ... -k "non_pass_externally_verified or invalid_github_repository or locally_observed_declaration"
3 passed, 20 deselected        # exit 0
```

### (b) 抓取失败类别（桩构造，不联网）

```text
api_error            fetch=api_error            repository='owner/repo'
missing_repository   fetch=missing_repository   repository=''
invalid_repository   fetch=invalid_repository   repository='a'
shape_error          fetch=shape_error
invalid_pr           fetch=invalid_pr（直接调用内部守卫；CLI 侧 pr=0 走 invalid_pr 实测可达）
```

均非 `ok`，且经 `verify_run` 不抛穿；`secret-token` 未出现在任何记录 JSON 中。

---

## 5. 独立门槛（干净 worktree，`b99cac0`）

| 检查 | 命令 | 实测 |
|---|---|---|
| B9 文件 | `pytest tests/test_b9_external_verification.py -q` | **23 passed**（7.42s，exit 0） |
| 禁网复跑 | 同上 + `-p nonet` | **23 passed**（6.50s，exit 0） |
| 默认全量 | `pytest -q` | **280 passed, 2 skipped**（159.24s，exit 0） |
| OpenSSL 门槛 | `PROJECT_MEMORY_REQUIRE_OPENSSL=1 pytest -q` | **280 passed, 2 skipped**（160.67s，exit 0） |
| audit | `python -m project_memory.cli audit --scope current` | **exit 0**；40 findings；high 0 / medium 16 / low 24；`entry_doc_*` 0 |
| audit 多重集 | 与基线 `30ddd1d` worktree 对比 `(severity, code, location)` | **added 0；removed 0**；两侧均 40 条 |
| reconcile | `python -m project_memory.cli reconcile --fail-on high` | **exit 0**；counts high 0 / medium 16 / low 24 |

基线 audit 自身输出：`base_total 40`、`{high:0, medium:16, low:24}`、`repository_version=30ddd1d…`，与 `b99cac0` 完全一致。

---

## 6. 独立探针（`C:/Temp/b9_probe.py`，不导入仓库测试模块）

| 探针 | 结果 |
|---|---|
| (i) `fail + externally_verified + --pr` | 抛 `PMError`（含“只适用于 pass”）；抓取桩未调用；CLI `exit=1`，stderr 含同一文本；stderr/stdout 无令牌 |
| (ii) `fail + locally_observed` | `status=FAILED`、`trust_level=locally_observed`；`fetch=not_requested`、`repository=''` |
| (iii) `pass + locally_observed + 全绿桩` | `trust_level=locally_observed`（封顶）；单条证据 `observed_level=externally_verified`、`external_ci_verified=True`；`ci.fetch=ok`、`repository=owner/repo` |
| (iv) 无 `--pr` 的 `externally_verified` | 仍被拒绝（`需要 --pr`），与上轮一致 |

另实测：`pass + externally_verified + 全绿` 的 `ci = {provenance: github_api, repository: owner/repo, fetch: ok}`，`status=MANUAL_REVIEW_REQUIRED`、`verified=False`、`trust=externally_verified`——升级仍不产生 VERIFIED。

---

## 7. NOT VERIFIED

- 未对本仓库真实 PR / 托管 CI 取证（仓库非公开、无真实令牌）；所有抓取成功/失败路径均由桩或内部调用验证，未做真实网络端到端。
- 未实测覆盖率百分比（环境无 coverage 模块）；未在 Linux/macOS 复跑。
- 未验证 `invalid_pr` 在真实 GitHubReader 网络路径下的表现（仅验证内部守卫与 `locally_observed + --pr 0` 集成路径）。
- 合并批准、发布授权、`dev/v1.0` 变更不在本报告范围。

---

## 8. 结论

**PASS**（仅针对 `b5d9ae0..b99cac0` 增量）。

- D-1、D-2、D-4、D-5 均已修复并由实跑证据支撑；负对照证明 D-1 测试确实锁定新校验。
- D-3 按派单保持延后，delta 未触碰 `skill/` 或 `docs/`；D-6 已关闭；无新发现偏差。
- 剩余事项：D-3 的文档/技能同步仍是后续独立任务，不影响本轮增量判定。
- 本报告是复核意见，不是合并批准；是否合并、发布由人类与 PM-01 决定。
