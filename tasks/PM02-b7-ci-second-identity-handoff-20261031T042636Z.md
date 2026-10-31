# PM-02 Handoff — B7-CI-SECOND-IDENTITY-001

- 任务卡：`import-workspace/PM02_B7_CI_SECOND_IDENTITY_TASK_CARD.md`
- 分支：`feat/b7-ci-anchor`
- 基线：`c3dea2a74ce666789e8a521a8eab7bcffe8654f2`（`origin/dev/v1.0`，B-8 PR #49 合并头，与任务卡预期一致）
- 实现 HEAD：`33660e211c962148a921c5904534092418f0429c`（本 handoff 提交在其后）
- 执行者：PM-02；复核：PM-03；合并/远端配置：PM-01
- 工作目录：`C:/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-02`

## 变更文件

`git diff --name-only c3dea2a74ce666789e8a521a8eab7bcffe8654f2..HEAD`：

```text
.github/workflows/approval-gate.yml
README.md
docs/OPERATIONS.zh-CN.md
project_memory/authority.py
project_memory/cli.py
project_memory/coordination.py
skill/project-memory/references/governance.md
tests/test_authority_verifier.py
tests/test_b7_ci_second_identity.py
tests/test_b8_signed_approval.py
```

提交拆分：

```text
33660e2 docs(b7): document CI second identity and approval gate
143deb7 test(b7): cover CI anchor, records-dir gate, and workflow pins
d22f24f feat(b7): accept CI JSON anchor and add approvals gate
```

未跟踪的 B-8 遗留文件 `PM02_COLD_START_VALIDATION.md`、`tasks/PM02-cold-start-handoff-20261029T150500Z.md` 保持原样，未提交、未删除。

## 实现要点

- `authority.py`
  - 新增 `TRUST_ANCHOR_JSON_ENV`、`APPROVAL_ANCHOR_JSON_ENV`、`CI_CONTEXT_ENV`。
  - `load_anchor(repo, env_name=ANCHOR_ENV, json_env=None)`：受保护文件锚优先；文件锚缺失/不合规时，仅在 `GITHUB_ACTIONS=true` 下接受 JSON 锚，跳过文件所有者检查，但仍做同一套 kind/schema/algorithm/字段校验，返回 `path='<env:NAME>'`、`protection='ci-secret'`。非 CI 设置 JSON 环境变量只得到 unconfigured。
  - 环境变量读取集中在固定白名单 `_env_value`；`env_name`/`json_env` 变量不会直接传给 `os.environ.get`，无法读取任意环境变量，验证器仍只来自进程内实现。
  - `verification_authority`、执行记录、审计 checkpoint 使用 `TRUST_ANCHOR_JSON_ENV`；审批使用 `APPROVAL_ANCHOR_JSON_ENV`，两个锚仍分开。
- `coordination.py` / `cli.py`
  - 新增 `verify_approval_records(repo, records_dir, commit_sha, require_approve)`，逐条输出 `*.json` 的验签、decision、提交匹配和 problems。
  - `approval verify --records-dir DIR --commit SHA [--require-approve]`；有至少一条 trusted+approve+提交匹配才 exit 0，空目录/缺目录/无匹配均非 0。`--record` 单条模式不变；`--require-approve` 与 `--record` 同用会被拒绝（exit 1）。
- `.github/workflows/approval-gate.yml`
  - `pull_request`（`dev/v1.0`）+ `workflow_dispatch(pr)`；`permissions` 为只读；checkout/setup-python 沿用现有 40 位提交 SHA；`persist-credentials: false`；全部 `shell: bash`；无 `pull_request_target`。
  - 固定 PR head 后 `git fetch origin approvals`（fetch 失败即失败，不吞掉），把 `records/` checkout 到 `.pm-approvals`，再执行 `approval verify --records-dir .pm-approvals/records --commit "$PM_HEAD" --require-approve`。
  - 缺 secret 锚、缺 `records/`、无记录、记录不匹配、验签失败、提交不符都会输出明确失败信息。

## 测试

新增 26 个测试（`tests/test_b7_ci_second_identity.py`）：

- CI/非 CI JSON 锚、`GITHUB_ACTIONS` 必须为字面 `true`、非法 JSON、kind/schema/algorithm/字段非法、文件锚优先、文件锚失败后 CI JSON 回退。
- `records-dir`：一条正确审批→0；空目录→2；缺目录→1；错误提交→2；reject→2；伪造签名→2；缺锚→2；单条模式不变；`--require-approve` 与 `--record` 同用被拒。
- workflow 静态检查：YAML 可解析（本机 PyYAML 6.0.1 实际执行）、Action 40 位 SHA、无 `pull_request_target`、只读 permissions、`persist-credentials: false`、`shell: bash`、fetch 未被 `|| true` 吞掉、门禁命令绑定 `PM_HEAD`。
- 负对照：修改审批记录 `commit_sha` 为相邻提交→失败；恢复→成功。

`tests/test_authority_verifier.py::test_module_keeps_no_external_verifier_dependency` 已按卡放宽为固定环境变量名字集合检查，测试保留。**披露**：卡面集合写的是 `{ANCHOR_ENV, TRUST_ANCHOR_JSON_ENV, APPROVAL_ANCHOR_JSON_ENV, CI_CONTEXT_ENV}`，未列 `APPROVAL_ANCHOR_ENV`；但 B-8 本地审批文件锚仍必须读取该名字，因此测试断言集合额外包含 `APPROVAL_ANCHOR_ENV`，同时断言不存在 `env_name`/`json_env` 这类变量名，保证没有任意 `os.environ.get`。`tests/test_b8_signed_approval.py` 的 `fake_anchor` 仅增加 `json_env=None` 形参以匹配新调用。

## 验收命令与实际结果

工作区已提交；命令均使用 `C:/SoftWare/Anconda/python.exe`，`PYTHONUTF8=1 PYTHONIOENCODING=utf-8`。

| 命令 | 结果 |
|---|---|
| `git diff --name-only c3dea2a..HEAD` | 见上方 10 个文件 |
| `git diff --check c3dea2a..HEAD` | exit 0 |
| `python -m project_memory.cli audit --scope current --output C:/Temp/pm02-b7-current-final.json` | exit 0 |
| `python -m project_memory.cli reconcile --fail-on high` | exit 0 |
| `python -m pytest -q` | `320 passed, 2 skipped in 170.42s` |
| `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q` | `320 passed, 2 skipped in 177.20s` |
| workflow 静态检查（`pytest tests/test_b7_ci_second_identity.py::WorkflowStaticTest -v`） | `8 passed in 0.12s` |
| 负对照（见下） | 0 → 2 → 0 |

B-8 后基线为 294 passed / 2 skipped；本卡新增 26 个测试。两次门禁的 2 skipped 均为非 openssl 用例（与基线相同），openssl 签名用例实际执行。

### audit 多重集

在基线 `c3dea2a` 的独立 worktree（`C:/Temp/pm-b7-baseline`）重跑同一 audit 做对照：

```text
baseline {'high': 0, 'low': 24, 'medium': 16} total 40
current  {'high': 0, 'low': 24, 'medium': 16} total 40
added 0 removed 0
entry_doc_* current []
multisets_equal True
```

结论：`(severity, code, location)` 多重集与基线完全一致；added 0；无 `entry_doc_*`；总量 40 = 0 high / 16 medium / 24 low。审计文件：`C:/Temp/pm02-b7-baseline.json`、`C:/Temp/pm02-b7-current-final.json`。

### 负对照实际输出

```text
negative-control before: exit=0 approved=True
negative-control edited: exit=2 problems=['审批记录不合规：approval_id 不可重算（记录被修改或格式错误）']
negative-control restored: exit=0 approved=True
1 passed in 0.73s
```

## 未验证项与边界

- **真实 secret 值未配置、未读取**；真实 PR 上的 `approval-gate` 运行（无审批→失败、加审批后 `workflow_dispatch` 重跑→成功、提交不匹配→失败）未执行。任务卡 §6 要求该实测，但按本卡边界由 PM-01 在 B-10 前后完成；本 handoff 不声称门禁已在真实 PR 上通过。
- `approvals` 分支未创建、未推送；secret、仓库可见性、分支保护/Branch Ruleset 均未修改（PM-01 用 REST 负责）。
- 审批私钥/密钥托管不在本卡范围。
- 未建 PR、未合并、未打 tag；未推送 `dev/v1.0`。
- 本分支只推送 `feat/b7-ci-anchor`。
- 已知残余：门禁不能防御仓库账户所有者改写 workflow（S4 残余），文档已按此边界描述，未使用“不可伪造/已认证”表述。
