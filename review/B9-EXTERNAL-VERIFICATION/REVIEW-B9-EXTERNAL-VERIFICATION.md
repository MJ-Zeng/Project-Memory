# B9-EXTERNAL-VERIFICATION-001 独立复核报告（PM-03）

- 复核对象：`origin/feat/b9-external-verification` 顶点 `b5d9ae045121e215b25c768cce13999bf23b017e`
  - `5d0a26c06e3041e636c8751e01d568691ebfa861` feat: read PR CI outcome for B-9 external verification
  - `4fed4425af1ded26bbeeae687f3adcf10fc60dd1` docs: add PM-02 handoff for B-9 external verification
  - `b5d9ae045121e215b25c768cce13999bf23b017e` docs: clarify B-9 handoff tip reference
- 基线：`30ddd1d841eb88f7061806b6378f97c33c683286`（`origin/dev/v1.0`，复核时实测）
- 复核分支：`review/b9-external-verification`（从候选顶点新建；未复用旧分支）
- 复核时间：2026-10-30 / 2026-10-31（本机时钟跨日）
- 复核环境：Windows 11 10.0.26300；`C:/SoftWare/Anconda/python.exe`（Python 3.12.4）；pytest 9.1.1；`PYTHONUTF8=1 PYTHONIOENCODING=utf-8`；未使用仓库内 venv
- 隔离：只读复核。基线/候选各建一个 detached worktree 于 `C:/Temp/b9-review/{base,cand}`；临时仓库均在 C: 盘；未使用任何真实令牌；未对 `dev/v1.0` 写入；未开 PR、未合并、未打 tag、未发布 Release。
- 输入边界：PM-02 handoff 只作为被核对对象，不作为证据来源；下列每条结论都对应本轮自行执行的命令/脚本输出。
- 结论：**PASS WITH DEVIATIONS**（偏差见 §10；不构成合并批准）

---

## 1. 变更范围（派单第 1 条）

```bash
git log --format='%H %P %s' -4 origin/feat/b9-external-verification
# b5d9ae0… 4fed442… docs: clarify B-9 handoff tip reference
# 4fed442… 5d0a26c… docs: add PM-02 handoff for B-9 external verification
# 5d0a26c… 30ddd1d… feat: read PR CI outcome for B-9 external verification
# 30ddd1d… 87600d7… docs(ci): document built-in CI and key concurrency by event (#46)

git rev-list --count origin/dev/v1.0..origin/feat/b9-external-verification
# 3

git diff --name-status origin/dev/v1.0...origin/feat/b9-external-verification
# M  README.md
# M  project_memory/cli.py
# M  project_memory/coordination.py
# M  project_memory/gh.py
# A  tasks/PM02-b9-external-verification-handoff-20261030T151211Z.md
# A  tests/test_b9_external_verification.py

git diff --check origin/dev/v1.0...HEAD; echo $?
# 0
```

结论：父链 `b5d9ae0 → 4fed442 → 5d0a26c → 30ddd1d` 与派单一致；diff 恰为派单列出的 6 个文件；无 `.github/`、`.project-memory/`、`fixtures/` 或其它无关文件改动；`git diff --summary` 仅两条 `create mode 100644`（handoff、测试文件）；`git diff --check` 干净（exit 0）。

## 2. 信任升级判定链（派单第 2 条，重点）

### 2.1 代码路径

| 环节 | 位置 | 条件/行为 |
|---|---|---|
| 被验证提交 | `project_memory/coordination.py:2144`、`:2200`、`:2173` | `target_head = target.git.head_sha`；PASS 必须有完整 head；当前 HEAD 变化直接拒绝 PASS |
| 证据声明的提交 | `coordination.py:930-936` | `target_commit_sha` 必须 40 位、必须 `== target_head`、必须存在于仓库；不等时**抛 PMError**（结构性拒绝，不是降级） |
| 抓取时机 | `coordination.py:2219-2220` | 仅在 `verdict == 'pass'` 分支抓取；`_external_ci_status(pr_number)` |
| 抓取入口 | `coordination.py:868-886` | 无 `--pr` 或无 `GITHUB_REPOSITORY` → `None`；任何 `Exception` → `None`；`_provenance != github_api` → `None` |
| 聚合规则 | `project_memory/gh.py:74-84` | 空列表或 `total_count > 返回条数` → `error`；任一 `completed` 且 `conclusion != success` → `failure`；任一未完成 → `pending`；否则 `success` |
| 单条证据升级 | `coordination.py:1018-1025` | `external_ci_verified = 非空 and status=='success' and head_sha == sha`；其中 `sha == target_head`（见上） |
| 映射执行覆盖 | `coordination.py:1127-1134` | `external_ci_verified and description_match and status==passed and result==pass` → `review_required`（`execution_covered`） |
| trust 等级 | `coordination.py:2260-2265` | PASS 路径：`min(声明等级, 各证据最高 observed)` |
| 记录状态 | `coordination.py:2283-2289` | `review_required` → `MANUAL_REVIEW_REQUIRED`；`verified = False` 硬编码 |
| 非 PASS 的 trust | `coordination.py:2262-2263` | `observed_rank = EVIDENCE_TRUST[evidence_level]`（**本次疑点**，见 2.4） |

### 2.2 逐项核对

- **CI 成功是否同时要求 status==success、fetch head==证据 target_commit_sha==被验证执行 head**：是。`coordination.py:1023-1024` 要求 `status=='success'` 且 `head_sha == sha`；`coordination.py:933` 已强制 `sha == target_head`；`target_head` 来自被验证执行记录。任一处不等时，抓取 head 不等 → 不升级（退化为 `agent_claimed`）；映射声明 sha 不等 → 直接 `PMError`（这是既有的映射合法性校验，不是降级路径）。
- **空列表**：`gh.py:76` → `error`，不升级（`test_no_check_runs_is_error_not_success`）。
- **截断（total_count > 返回条数）**：`gh.py:74-77` → `error`（`test_truncated_check_run_list_is_error`，101/100）。
- **有 in_progress**：`gh.py:81-82` → `pending`（`test_incomplete_run_is_pending`）。
- **有 failure**：`gh.py:78-80` 先于 pending 判定 → `failure`；`failure` 优先于 `pending`（`test_failure_dominates_pending`）。
- **升级后是否仍 verified=false、status 至多 MANUAL_REVIEW_REQUIRED**：是。`coordination.py:2283-2289`；`test_green_ci_on_verified_commit_raises_trust` 断言 `verified=False`、`status=MANUAL_REVIEW_REQUIRED`、`evaluate_goal(...)['satisfied']=False`。不存在因 CI 绿而写 `VERIFIED`/`achieved` 的路径：`_verification_ok` 要求 `status == 'VERIFIED'`，而本 CLI 把 `verified` 硬编码为 False。
- **trust = min(声明, 观测)**：PASS 路径成立（见 2.3 演练 B）；非 PASS 路径不成立（见 2.4）。

### 2.3 两种输入演练（自建探针，非仓库文件）

探针位于 `C:/Temp/b9-review/cand/test_b9_drills.py`，复用候选的测试夹具，只读运行。

**A. 声明 externally_verified 但 fetch 失败（映射为本地收据证据）**

```text
DRILL-A declared=external fetch=fail local-evidence:
  status='MANUAL_REVIEW_REQUIRED' verified=False record_status='MANUAL_REVIEW_REQUIRED'
  trust='locally_observed' evidence_level='externally_verified'
  entry_observed='locally_observed' external_ci_verified=False
  ci={'url':'','status':'not_provided','provenance':'none'}
```

结论：未获得外部信任；trust 被观测到的 `locally_observed` 限制，`verified=False`。

**A2. 声明 externally_verified 但 fetch 失败（映射为 ci 证据）**

```text
DRILL-A2 declared=external fetch=fail ci-mapping:
  status='PARTIAL_COVERAGE' verified=False record_status=None trust=None
  entry_observed='agent_claimed' external_ci_verified=False
  ci={'url':'','status':'not_provided','provenance':'none'}
```

结论：不写验证记录，证据降为 `agent_claimed`，命令不阻塞（返回 PARTIAL_COVERAGE）。

**B. 声明 locally_observed 但 fetch 成功**

```text
DRILL-B declared=local fetch=success ci-mapping:
  status='MANUAL_REVIEW_REQUIRED' verified=False record_status='MANUAL_REVIEW_REQUIRED'
  trust='locally_observed' evidence_level='locally_observed'
  entry_observed='externally_verified' external_ci_verified=True
  ci={'status':'success','provenance':'github_api','pr':42,'head_sha_matches_target':True,...}
```

结论：`min(1, 2) = locally_observed`，声明等级封顶生效；单条证据本身仍是 `externally_verified`；记录仍非 VERIFIED。

### 2.4 已知疑点：非 PASS 分支的 `observed_rank` 独立核实

```text
DRILL-C verdict=inconclusive declared=external:
  status='INCONCLUSIVE' verified=False record_status='INCONCLUSIVE'
  trust='externally_verified' evidence_level='externally_verified'
  entry_observed=None external_ci_verified=None
  ci={'url':'','status':'not_provided','provenance':'none'}
  （fetch 断言 never called）
```

另测得 `verdict=fail` 同样写出 `trust_level=externally_verified`、`status=FAILED`、`verified=False`、`ci.provenance='none'`。

**成立。** `coordination.py:2262-2263` 在非 PASS 时把“声明的等级”直接当作“观测等级”，且非 PASS 分支根本不会调用 `_external_ci_status`（抓取只在 `coordination.py:2219` 的 PASS 分支）。因此：

- `verify --verdict fail|inconclusive --evidence-level externally_verified --pr N` 即使没有 `GITHUB_REPOSITORY`、没有网络、没有任何 CI 结果，记录与审计日志仍写 `trust_level=externally_verified`；
- 违反 README 第 1 条“记录 trust_level 也才能到 externally_verified”（该句只在 CI 全绿时成立）；
- **不能**被当前代码当成通过依据：`verified` 恒为 false，`status` 为 `FAILED`/`INCONCLUSIVE`，`_verification_ok` 要求 `status == 'VERIFIED'`，`evaluate_goal` 不读取 `trust_level`，仓库内也没有其它消费 `trust_level` 的门禁（`grep -rn "trust_level" project_memory/*.py` 仅记录/审计）。
- **但**它会进入验证记录、`_verification_document` 与 `_audit_attempt`，人工复核或外部报告可能把它读成“外部已核验”，属元数据失真。

**严重度评估：低—中**。不构成自动通过或提权，但违反文档化的 `min()` 契约，建议在合并前修：非 PASS 时若 `evidence_level == 'externally_verified'`，应把 `observed_rank` 置 0（或直接禁止非 PASS 声明该等级），并补一条负对照测试。见偏差 D-1。

## 3. 联网与凭据（派单第 3 条）

```bash
grep -rnE "POST|PUT|PATCH|DELETE|method\s*=" project_memory/gh.py project_memory/coordination.py
# （无输出）
```

- **token 来源**：`project_memory/gh.py:16` 只读 `GITHUB_TOKEN`（或构造参数），不写盘、不进记录。
- **是否可能出现在记录/日志/stdout/异常文本**：自建探针验证（`probe_security.py`）：

```text
http_error_no_token: OK {'message': 'GitHub API 返回 HTTP 403：/repos/o/r；请检查仓库可见性和令牌权限', 'contains_token': False}
url_error_no_token: OK {'message': 'GitHub API 请求失败：URLError', 'contains_token': False}
```

  异常信息只含 HTTP 码与 endpoint；`checks.ci` 不写 token；`test_green_ci_on_verified_commit_raises_trust` 还断言记录 JSON 不含测试令牌值。
- **只读**：`urllib.request.Request` 未设置 method、无 `data=`，实际为 GET；`gh.py` 中无任何写方法。
- **endpoint 约束**：`gh.py:20-21` 仍要求以 `/` 开头且非 `//`：

```text
endpoint_relative_only: RAISED PMError: 只允许使用 GitHub API 的相对路径
endpoint_double_slash: RAISED PMError: 只允许使用 GitHub API 的相对路径
endpoint_absolute_url: RAISED PMError: 只允许使用 GitHub API 的相对路径
```

- **`GITHUB_REPOSITORY` 缺失或格式非法**：

```text
missing_github_repository: OK None
invalid_slug_degrades: OK None          # GITHUB_REPOSITORY='not a slug'
invalid_slug: RAISED PMError: GitHub 仓库格式应为 owner/name
```

  集成层捕获后降级为 `agent_claimed`，不抛穿。
- **API 报错 / 超时 / 返回结构异常**：均退化，不抛穿（`test_api_error_degrades_without_raising` + 自建探针）：

```text
SHAPE-pull-head-not-dict: status='PARTIAL_COVERAGE' … entry_observed='agent_claimed'
SHAPE-checks-list:        status='PARTIAL_COVERAGE' … entry_observed='agent_claimed'
TIMEOUT:                  status='PARTIAL_COVERAGE' … entry_observed='agent_claimed'
```

- **真实 API 形状（匿名只读，公开仓库 `cli/cli`，未用令牌）**：

```text
repo_ok cli/cli False
pulls [(14878, '0c5e7e910f'), …]
pr 14878 status failure head 0c5e7e910f runs 30 total 30 trunc False
sample [('CodeQL','completed','success'), ('close-unmet-requirements','completed','skipped'), …]
```

  `X-GitHub-Api-Version: 2026-03-10` 被接受；`/pulls/{n}` 与 `/commits/{sha}/check-runs?per_page=100` 字段形状与代码一致；`skipped` 被判为 failure，与 handoff 偏差 4 的“保守处理”一致。
- **审计性缺口**：`_ci_payload`（`coordination.py:2102-2113`）未记录 `GITHUB_REPOSITORY` slug，抓取失败时 `provenance` 回到 `none`/`declared_unfetched`，无法区分“未请求”“请求失败”“读的是哪个仓库的 CI”；也没有校验 `GITHUB_REPOSITORY` 与被验证仓库一致。见偏差 D-4。

## 4. 测试质量（派单第 4 条）

- **数量**：`tests/test_b9_external_verification.py` 共 19 个测试（9 个 `pull_request_ci_status` 单元、8 个 `verify_run` 端到端、2 个 CLI 接线），与 handoff 自述一致。
- **真断言**：逐条检查，所有 19 个测试都有具体字段断言（状态、observed_level、trust_level、provenance、Suspicious 标记、布尔值、异常文本等）；没有只断言“返回 dict”或仅 `assertTrue(result)` 的弱断言。
- **全部 mock 网络**：用 `socket.connect/create_connection/getaddrinfo` 全部抛错的 pytest 插件重跑：

```bash
python -m pytest tests/test_b9_external_verification.py -q -p nonet
# 19 passed in 4.28s
```

  证明测试路径没有任何真实网络连接（唯一的真实 API 调用是本报告 §3 的 PM-03 自身探针，不在仓库测试内）。
- **六类覆盖**：

| 场景 | 测试 |
|---|---|
| failure | `test_any_failure_is_failure`、`test_failing_ci_degrades_to_agent_claimed`、`test_non_success_conclusion_is_not_green` |
| pending | `test_incomplete_run_is_pending`、`test_pending_ci_degrades_to_agent_claimed` |
| truncated | `test_truncated_check_run_list_is_error` |
| 空列表 | `test_no_check_runs_is_error_not_success` |
| head 不匹配 | `test_decoy_head_sha_degrades_to_agent_claimed` |
| `GITHUB_REPOSITORY` 缺失 | `test_missing_github_repository_degrades`（含 `fetch.assert_not_called`） |

  六类齐全；“failure 优先于 pending”也有独立测试。
- **未覆盖/缺口**（不改变结论）：非法 `GITHUB_REPOSITORY` 格式、`locally_observed` 声明 + 抓取成功的 `min()` 封顶、非 PASS + `externally_verified` 的 D-1 问题均无仓库内测试（本轮由 PM-03 探针覆盖）。见偏差 D-5。

## 5. 负对照（派单第 5 条，全部实跑）

### (a) 基线 30ddd1d 上跑同一测试文件

```text
git worktree add --detach C:/Temp/b9-review/base 30ddd1d
cp tests/test_b9_external_verification.py C:/Temp/b9-review/base/tests/
cd C:/Temp/b9-review/base && python -m pytest tests/test_b9_external_verification.py -q
=> 18 failed, 1 passed in 4.57s (exit 1)
```

- 唯一通过：`test_externally_verified_without_pr_is_rejected`——它断言的正是基线行为（无条件拒绝）。与 PM-02 自报的 18/1 一致。
- 失败原因分组：`GitHubReader` 无 `pull_request_ci_status`（9 个单元测试）；`verify_run` 不接受 `pr_number` / 无 `external_ci_verified` 字段（7 个端到端）；CLI 无 `--pr`、`--evidence-level` 不接受 `externally_verified`（2 个 CLI 接线）。9 + 7 + 2 = 18。典型输出：

```text
project-memory verify：错误：argument --evidence-level: 无效选项：'externally_verified'
(choose from 'agent_claimed', 'locally_observed')   # SystemExit: 2
```

结论：新增测试锁的是新行为，不是空断言；检查有效。

### (b) 候选副本：把一个 check run 改成 failure

用真实 `GitHubReader.get` 桩返回“1 success + 1 failure”（head 匹配）：

```text
RC-B status='PARTIAL_COVERAGE' verification=None
     ci_status='failure' head_match=True observed='agent_claimed'
```

结论：不升级、不写验证记录；failure 优先。检查有效。

### (c) 候选副本：fetch head 与被验证提交不一致

PR head = `f*40`（非空诱饵），check runs 全绿：

```text
RC-C status='PARTIAL_COVERAGE' verification=None
     ci_status='success' head_match=False observed='agent_claimed'
```

结论：即使 CI 绿，head 不匹配也不升级。检查有效。

### (d) 不设置 `GITHUB_REPOSITORY` 且带 `--pr` 跑 CLI

```text
RC-D exit=2 status='PARTIAL_COVERAGE' provenance='none' observed='agent_claimed'
     （fetch.assert_not_called 通过；无异常）
```

结论：降级而非报错或升级。检查有效。

## 6. 文档一致性（派单第 6 条）

README `### 外部取证（--pr）`（`README.md:96-117`）四条规则逐条对照：

1. “所有 check run 完成且均为 success + PR head == 被验证 head → ci 证据 externally_verified；trust_level 也才能到 externally_verified”——PASS 路径成立；**非 PASS 路径不成立**（D-1）。
2. “失败/pending/无 check run/head 不匹配/缺 `GITHUB_REPOSITORY`/网络或 API 错误 → agent_claimed、不阻塞”——PASS 路径成立；非 PASS 路径不经过该降级逻辑（D-1）。
3. “即使全绿仍最多 MANUAL_REVIEW_REQUIRED、verified 恒 false”——成立（`coordination.py:2283-2289`）。
4. “声明 externally_verified 必须同时给 --pr”——成立（`coordination.py:2075-2077`；`test_externally_verified_without_pr_is_rejected`）。
- **命令示例可执行性**：`verify --help` 实测包含 `--evidence-level {agent_claimed,locally_observed,externally_verified}` 与 `--pr PR_NUMBER`；示例参数名真实存在，且 CI 映射不要求 `--test-receipt`。
- **“凭据与权限”**（`README.md:213-215`）：`GITHUB_TOKEN` 仅环境变量、只读接口、`verify --pr` 还需 `GITHUB_REPOSITORY`——与代码一致。
- **仍有过时表述**：
  - 每条 verify 结果里的 `caveat` 仍写“CLI 不再接受 externally_verified……CI/review 证据只获得 agent_claimed 信任”（`coordination.py:2363-2367`，基线即存在、本分支未更新），与新行为直接矛盾（D-2）。
  - `skill/project-memory/SKILL.md:110`、`references/data-contracts.md:206,332`、`references/workflows.md:211,213`、`references/governance.md:27`、`docs/ARCHITECTURE.zh-CN.md:172`、`docs/OPERATIONS.zh-CN.md:134`、`docs/TEST_REPORT.md:104,152` 仍称 CLI 离线、不接受 `externally_verified`（D-3）。这些不在任务卡 6 文件范围内，但会造成仓库内文档互斥。

## 7. 独立门槛（派单第 7 条，干净检出）

候选顶点工作树，解释器 `C:/SoftWare/Anconda/python.exe`：

| 检查 | 命令 | 实测 |
|---|---|---|
| audit | `python -m project_memory.cli audit --scope current` | exit 0；40 findings；high 0 / medium 16 / low 24 |
| audit 多重集 | 与基线 `30ddd1d` 的 worktree 对比 `(severity, code, location)` | `multiset_equal True`；`added []`；`removed []` |
| entry_doc | 统计 `code` 以 `entry_doc` 开头 | 0 |
| reconcile | `python -m project_memory.cli reconcile --fail-on high` | exit 0；counts high 0 / medium 16 / low 24 |
| 默认 pytest | `python -m pytest -q` | **276 passed, 2 skipped**（160.11s，exit 0） |
| OpenSSL 门槛 | `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q` | **276 passed, 2 skipped**（158.74s，exit 0） |
| 基线 pytest | 同解释器在 `30ddd1d` worktree | **257 passed, 2 skipped**（155.62s） |

结论：40/0/16/24 与基线按多重集完全相同、新增 0、`entry_doc_*` 为 0；276 = 257 + 19；两种门槛一致，未出现 venv 假失败或联网差异。

## 8. 回归：不给 `--pr` 的行为（派单第 8 条）

同一探针分别在基线 worktree 与候选 worktree 运行，输出 JSON 逐字节相同（`diff` 为空）：

| 场景 | 基线 = 候选 |
|---|---|
| `pass` + `locally_observed`（有效收据） | exit 2；`MANUAL_REVIEW_REQUIRED`；`verified=False`；`trust=locally_observed`；entry `locally_observed` |
| `pass` + `agent_claimed` | exit 1；stderr `project-memory: Agent 自报不能作为 pass；请提供本地日志、外部 CI 或人工批准` |
| `fail` + `locally_observed` | exit 2；`FAILED`；`verified=False`；`trust=locally_observed` |
| `inconclusive` + `locally_observed` | `INCONCLUSIVE`；`verified=False`；`trust=locally_observed` |

- `EVIDENCE_TRUST`/`EVIDENCE_LEVELS` 与基线逐字相同（基线 `coordination.py:53-54`）。
- `human_approved` 仍被拒绝：`PMError: human_approved 不能作为声明的 evidence level…`；CLI choices 仍不含 `human_approved`；未放宽。
- `externally_verified` 无 `--pr` 仍被拒绝，错误文本明确要求 `--pr`。

## 9. handoff 准确性（派单第 9 条）

| handoff 声明 | 实测 | 结论 |
|---|---|---|
| 父链/基线 `30ddd1d`、分支顶点 `5d0a26c`（随后单独提交 handoff） | 一致；`b5d9ae0` 只改 handoff 一行 | 准确 |
| `git diff --stat` 5 files / 482+/24− | `git show 5d0a26c --stat` 正是 5 files / 482+/24− | 在该提交时准确；最终 tip 为 6 files / 576+/24−（handoff 自身），且 `b5d9ae0` 已注明“最终 tip 以 rev-parse 为准” |
| 19 个测试（9+8+2） | 19；9+8+2 | 准确 |
| 全量 276 passed / 2 skipped，基线 257+2 | 复现 | 准确 |
| audit 40（0/16/24）、reconcile exit 0 | 复现 | 准确 |
| 负对照 18 failed / 1 passed，唯一通过项 | 复现，唯一通过项一致 | 准确 |
| 覆盖率未实测（无 coverage 模块） | `ModuleNotFoundError: No module named 'coverage'` | 如实披露 |
| 未改 `.github/workflows/`、Goal/审计数据；未开 PR/合并/tag/Release | diff 无相关路径；`git ls-remote` 的 `refs/pull/*` 无 b5d9ae0，tag 仍只有既有 `v1.0.0`；本地无 merge/tag 动作 | 准确（PR 状态见 §11 限制） |
| 未对真实 PR 抓取（离线） | 与本轮一致；PM-03 只对公开 `cli/cli` 做了匿名形状探测 | 准确 |

## 10. 偏差清单

| 编号 | 级别 | 位置 | 描述 | 影响/建议 |
|---|---|---|---|---|
| D-1 | 低—中 | `coordination.py:2262-2263` | 非 PASS（`fail`/`inconclusive`）声明 `externally_verified` 时，`observed_rank` 直接用声明值，且该分支不做抓取；记录与审计日志写 `trust_level=externally_verified`，`ci.provenance=none` | 不构成通过依据（`verified=false`、`status` 非 VERIFIED、无代码消费该字段），但违反文档化 `min()` 契约、会误导人工复核。建议非 PASS 时把观测等级置 0 或禁止该声明，并补负对照测试 |
| D-2 | 低 | `coordination.py:2363-2367` | 用户可见 `caveat` 仍称“CLI 不再接受 externally_verified；CI/review 只获得 agent_claimed” | 与新行为/README 矛盾；建议同步更新 |
| D-3 | 中低 | `skill/project-memory/SKILL.md:110`、`references/data-contracts.md:206,332`、`references/workflows.md:211,213`、`references/governance.md:27`、`docs/ARCHITECTURE.zh-CN.md:172`、`docs/OPERATIONS.zh-CN.md:134`、`docs/TEST_REPORT.md:104,152` | 仍称 CLI 离线、不接受/不抓取 `externally_verified` | 超出任务卡 6 文件范围，但仓库文档互斥；建议后续同步 |
| D-4 | 低 | `coordination.py:2102-2113`、`gh.py:62-66` | `checks.ci` 不记录 `GITHUB_REPOSITORY` slug；抓取失败时无法区分“未请求/失败/读了哪个仓库”；未校验该 slug 与被验证仓库绑定 | 审计性缺口；同 SHA 在他人仓库的绿色 CI 可经环境变量被读入。建议记录 slug 并在文档中明确操作者责任 |
| D-5 | 低 | `tests/test_b9_external_verification.py` | 未覆盖：非法 `GITHUB_REPOSITORY` 格式、`locally_observed` + 抓取成功的 `min()` 封顶、非 PASS + `externally_verified` | 建议补 3 条；本轮已由 PM-03 探针验证行为符合预期（除 D-1） |
| D-6 | 提示 | handoff §1 | diff stat 为生成时点的 5 文件，最终 tip 为 6 文件 | 已由 `b5d9ae0` 与文中“随后单独提交”说明，无需动作 |

## 11. NOT VERIFIED

- 未对本仓库真实 PR / 托管 CI 做取证：仓库非公开（匿名 API 返回 404），且约束禁止使用真实令牌。故“本仓库 PR 的 check runs 会如何聚合”“哪些 check 是必需项”“verify 时刻 PR head 是否已有 check runs”均未实测；只验证了公开 `cli/cli` 的字段形状与本仓库单测/桩。
- 未验证 GitHub 上该分支是否存在已关闭/已合并的 PR 元数据（匿名不可达）；仅通过 `git ls-remote` 确认 `refs/pull/*` 中没有 b5d9ae0、没有新 tag。
- 覆盖率百分比未实测（环境无 coverage；与 handoff 披露一致）。
- “真实网络下超时 12s 的行为”只用异常注入验证了退化路径，未做真实慢网实验。
- 合并批准、发布授权不在本报告范围；本报告不构成合并批准。

## 12. 结论

**PASS WITH DEVIATIONS。**

- 实现与任务卡主目标一致：CI 结果由 GitHub API 机器读取；成功、空、截断、pending、failure、head 不匹配、缺仓库变量、网络/API/结构异常的分支均按 fail-closed 处理；升级后仍 `verified=false`、最多 `MANUAL_REVIEW_REQUIRED`；无 `--pr` 的旧行为（探针输出）与基线逐字节一致；两道独立门槛与基线多重集相同；19 个新增测试真实锁定新行为且全部不联网。
- 需在合并前至少修复 **D-1**（非 PASS 的 `trust_level` 失真），并同步 **D-2** 的 caveat 文本；D-3/D-4/D-5 可作为后续文档与测试补强。
