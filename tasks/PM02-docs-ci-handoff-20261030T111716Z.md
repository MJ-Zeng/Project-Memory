# DOCS-CI-001 执行交接（PM-02）

- 任务 ID：`DOCS-CI-001`
- 执行者：PM-02（独立克隆 `pm-pilot-02`）
- 分支：`docs/ci-facts-20261030`
- 基线 SHA：`87600d7854d51b1d6f860382bfe90caaa47d9e9b`（`origin/dev/v1.0`；本地 ref 起初为 `617cdd9`，`git fetch origin` 后与卡一致）
- UTC 时间：`2026-10-30T11:17:16Z`
- 改动文件：`README.md`、`.github/workflows/test.yml`，另加本交接文件

## 1. `git diff --stat origin/dev/v1.0`

```
 .github/workflows/test.yml |  2 +-
 README.md                  | 14 ++++++++++++--
 2 files changed, 13 insertions(+), 3 deletions(-)
```

## 2. 两文件 diff 原文（`git diff --cached`）

```diff
diff --git a/.github/workflows/test.yml b/.github/workflows/test.yml
index c45dd4f..b71cc85 100644
--- a/.github/workflows/test.yml
+++ b/.github/workflows/test.yml
@@ -11,7 +11,7 @@ permissions:
   contents: read

 concurrency:
-  group: test-${{ github.ref }}
+  group: test-${{ github.ref }}-${{ github.event_name }}
   cancel-in-progress: true

 jobs:
diff --git a/README.md b/README.md
index 8de6ba3..bc431bd 100644
--- a/README.md
+++ b/README.md
@@ -42,6 +42,16 @@ Windows 上 `python3` 可能是 Microsoft Store 的别名桩（exit 49），请

 开关取值为 `1`、`true`、`yes`（大小写不敏感）。详见 `docs/OPERATIONS.zh-CN.md`。

+### 仓库自带的 CI
+
+本仓库的 `.github/workflows/test.yml` 在三种情况下运行同一套检查：目标为 `dev/v1.0` 的 pull request、合入 `dev/v1.0` 的 push，以及手动 `workflow_dispatch`。
+
+- 运行器 `windows-latest`，Python 3.12，pytest 固定为 9.1.1。
+- 两道门槛依次执行：默认 `pytest -q`，以及 `PROJECT_MEMORY_REQUIRE_OPENSSL=1 pytest -q`。运行器没有 openssl 时，第二道会在日志里显式打印跳过，不会把跳过当成通过。
+- 权限只有 `contents: read`；checkout 不保留凭据；第三方 Action 按提交 SHA 固定。
+
+当前没有启用分支保护（私有仓库的免费计划不提供该能力），所以 CI 结果是建议性的，不会自动阻断合并。合并规则是：先确认该 pull request 的 CI 运行成功，再看代码；合入后由 push 触发的运行会在合并提交上再验证一次。
+
 ## 目标、执行与独立验证

 目标用可衡量的成功标准描述，不把 Issue 关闭当成完成：
@@ -196,8 +206,8 @@ python3 -m pip install -e '.[semantic]'
 ## 还需要人工完成的事

 1. 检查生成的示例，补全入口文档、架构说明和 ADR 负责人。
-2. 参考 `.github/CODEOWNERS.example` 配置真正的 CODEOWNERS，并在 GitHub 开启分支 Ruleset、必需审查和必需 CI。CLI 不能替你做这些。
-3. 把 Actions 固定到审核过的完整 SHA。
+2. 参考 `.github/CODEOWNERS.example` 配置真正的 CODEOWNERS，并在 GitHub 开启分支 Ruleset、必需审查和必需 CI（私有仓库的免费计划不提供这些能力，需要 GitHub Pro 或改为公开仓库）。CLI 不能替你做这些。
+3. 审核已固定的第三方 Action 代码，并在升级时更新 SHA：当前 `actions/checkout` 固定到 `v4.4.0`、`actions/setup-python` 固定到 `v5.6.0`，只解决了“引用不可变”，没有审核上游代码。
 4. 接入有权限的 GitHub 数据；如果要把完成门禁全自动化，还需要独立核对 CI 和 review 状态，不能只依赖快照声明。
 5. Qoder CN 等客户端目前需要手动切换模型。CLI 只记录实际模型，不调度模型，也不保证跨模型接续。
 6. Goal 的 `approved`/`achieved` 转换、ADR 接受、高风险变更和生产部署仍必须由授权人执行。
```

## 3. §4 自查结果

### 4.1 改动文件恰为两个

`git diff --stat origin/dev/v1.0` 只列出 `README.md`、`.github/workflows/test.yml`（见上）。exit 0。

### 4.2 workflow 只有 `group:` 一行变化

diff 中 `.github/workflows/test.yml` 仅 `-  group: test-${{ github.ref }}` / `+  group: test-${{ github.ref }}-${{ github.event_name }}`，`cancel-in-progress: true` 未动；净 +1 / −1。

### 4.3 README 只有一个新增小节 + 两行列表项替换

diff 中 README 只有 3 处：在 `## 目标、执行与独立验证` 前新增 `### 仓库自带的 CI` 小节（10 行），以及第 2、3 条列表项各 1 行替换。无其他改动。

### 4.4 `git diff --check origin/dev/v1.0`

无输出，`exit=0`（无行尾空白）。

### 4.5 README blob 行尾与行数

- 原始 blob：222 行，0 个 CR，单一结尾换行（`...target)\n`）
- 新 blob（暂存区 `git show :README.md`）：232 行，0 个 CR，结尾 `...target)\n`
- 增加：232 − 222 = **10 行**，恰为新增小节的行数（`### 仓库自带的 CI` 1 行 + 空行 + 段落 + 空行 + 3 条 bullet + 空行 + 段落 + 结尾空行）
- 工作树为 CRLF（`core.autocrlf=true`），暂存区 blob 为 LF，符合卡要求。

### 4.6 README 新小节与 workflow 逐项对照

| README 声称 | workflow 出处（`.github/workflows/test.yml` 行号） |
|---|---|
| 三种触发：push / pull_request / workflow_dispatch | L3–L8（`push:` L4，`branches: [dev/v1.0]` L5；`pull_request:` L6，`branches: [dev/v1.0]` L7；`workflow_dispatch:` L8） |
| 运行器 `windows-latest` | L19 `runs-on: windows-latest` |
| Python 3.12 | L27 `python-version: "3.12"` |
| pytest 固定为 9.1.1 | L29 `pip install ... "pytest==9.1.1"` |
| 两道门槛：默认 `pytest -q` | L30 `- name: Default gate`，L32 `run: python -m pytest -q` |
| 第二道 `PROJECT_MEMORY_REQUIRE_OPENSSL=1 pytest -q` | L33 `- name: OpenSSL gate`，L38 `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q` |
| 缺 openssl 时显式打印跳过、不当作通过 | L39–L40 `else echo "... gate SKIPPED (not passed)"` |
| 权限只有 `contents: read` | L10–L11 `permissions:` / `contents: read` |
| checkout 不保留凭据 | L24 `persist-credentials: false` |
| 第三方 Action 按提交 SHA 固定 | L22 `actions/checkout@11d5960a...`（v4.4.0）、L25 `actions/setup-python@a26af69b...`（v5.6.0） |

### 4.7 结构断言（脚本，候选原样）

```
PASS   | concurrency.group == 'test-${ref}-${event}' | 'test-${{ github.ref }}-${{ github.event_name }}'
PASS   | concurrency.cancel-in-progress is True | True
PASS   | permissions == {'contents': 'read'} | {'contents': 'read'}
PASS   | exactly two uses | ['actions/checkout@11d5960a326750d5838078e36cf38b85af677262', 'actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065']
PASS   | both uses pinned to 40-hex SHA | ['actions/checkout@11d5960a326750d5838078e36cf38b85af677262', 'actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065']
PASS   | checkout@11d5960... (v4.4.0) | actions/checkout@11d5960a326750d5838078e36cf38b85af677262
PASS   | setup-python@a26af69... (v5.6.0) | actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
PASS   | five steps | [None, None, 'Install test dependency', 'Default gate', 'OpenSSL gate']
PASS   | five step identities unchanged | [None, None, 'Install test dependency', 'Default gate', 'OpenSSL gate']
PASS   | README contains '### 仓库自带的 CI'
PASS   | README contains 'pull_request'
PASS   | README contains 'push'
PASS   | README contains 'workflow_dispatch'
PASS   | README contains 'PROJECT_MEMORY_REQUIRE_OPENSSL=1'
PASS   | README contains 'contents: read'
PASS   | new section located
PASS   | new section excludes 'http://'
PASS   | new section excludes 'https://'
PASS   | new section excludes ']('
OVERALL PASS
```

exit=0。说明：`five steps` 的两个 `None` 为两个 `uses` 步骤（checkout / setup-python）无显式 `name`，其后三条为命名步骤，共 5 步、名称未变。

### 4.8 负对照（临时副本）

**对照①：删除新增小节**（`neg1_README.md`，仅删 `### 仓库自带的 CI` 至 `## 目标、执行与独立验证` 之间的内容）：

```
FAILED | README contains '### 仓库自带的 CI'
FAILED | README contains 'push'
FAILED | README contains 'workflow_dispatch'
FAILED | README contains 'contents: read'
FAILED | new section located
OVERALL FAILED
```

exit=1。其余断言仍 PASS（`pull_request`、`PROJECT_MEMORY_REQUIRE_OPENSSL=1` 等内容在 README 其他小节本就存在，故未随小节删除而消失），但小节相关断言按预期 FAILED。

**对照②：把 `group:` 还原为 `test-${{ github.ref }}`**（`neg2_workflow.yml`）：

```
FAILED | concurrency.group == 'test-${ref}-${event}' | 'test-${{ github.ref }}'
OVERALL FAILED
```

exit=1。其余断言 PASS。

结论：两处负对照都使对应断言 FAILED，候选上全部 PASS，说明断言可区分正误。

### 4.9 两道本地门槛（解释器 `C:/SoftWare/Anconda/python.exe`，`PYTHONUTF8=1`）

- `python -m pytest -q` → `257 passed, 2 skipped in 161.96s`，**exit 0**
- `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q` → `257 passed, 2 skipped in 159.65s`，**exit 0**
- 本机 openssl：`/ucrt64/bin/openssl`（存在，故第二道未触发跳过分支）

### 4.10 审计与对账

命令：`PROJECT_MEMORY_PYTHON=C:/SoftWare/Anconda/python.exe ./bin/project-memory audit --scope current`

- 当前工作树：`counts = {high: 0, medium: 16, low: 24}`，共 **40 条**，`docs_scanned=13`，exit 0
- 基线（独立 worktree @ `87600d7` 上跑同一命令）：`counts = {high: 0, medium: 16, low: 24}`，共 40 条
- `(severity, code, location)` 多重集对比：**完全一致（multiset equal: True）**，仅基线 / 仅当前两个方向的差集均为空
- code 直方图两边一致：`unknown_document_status 4, broken_document_reference 1, broken_reference 4, reference_authority_mismatch 14, ambiguous_reference 14, reference_outside_repository 1, dynamic_artifact_reference 2`
- `entry_doc_*` 类 finding：0 条

对账：`./bin/project-memory reconcile --fail-on high` → **exit 0**，`state=needs_attention`，`summary.docs = {high: 0, medium: 16, low: 24}`，`defects 0`。未因 high 失败。

## 4. 未验证项（与卡 §6 一致）

- 未在托管 runner 上验证 `group` 变更后的实际行为（手动 `workflow_dispatch` 是否与 `push` 运行互不取消，只能在真实运行中观察）。
- 未验证 GitHub 免费计划之外的分支保护能力（README 中“免费计划不提供分支保护”为按卡撰写的事实陈述，本环境无法验证账户计划）。
- 只核对了 README 与 workflow 文件之间的一致性；未验证 GitHub 对 `pull_request` / `push` / `workflow_dispatch` 事件语义是否有额外限制。

## 5. 明确未做

- 未建 PR、未合并、未打 tag、未改 Release。
- 未改 `docs/`、`CHANGELOG.md`、`.project-memory/`、`project_memory/`、`tests/` 等。
- 新增 README 文本不含任何链接 / URL。
