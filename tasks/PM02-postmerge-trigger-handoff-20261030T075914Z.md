# 交接 — CI-POSTMERGE-001 默认分支合入后自动跑门禁

- 任务 ID：`CI-POSTMERGE-001`
- 执行者：PM-02（独立克隆 `pm-pilot-02`）
- 基线：`617cdd90cac96c3619938d96831fcecd2930564f`（`origin/dev/v1.0`）
- 分支：`ci/postmerge-trigger-20261030`
- 决策归属：人类 2026-10-30 选定「维持现状、流程兜底」（readiness §12.12）；Free 私有库无法开分支保护，本卡只补「合入后」自动验证
- 判定：本文件只记录执行事实与实测数字，不给出 PASS/GO 结论。

## 1. 改了什么

仅 `.github/workflows/test.yml` 的 `on:` 块插入两行 `push:` / `branches: [dev/v1.0]`，其余 0 行改动，净变化恰为 `+2/−0`；提交 blob 由 39 行变为 41 行。

`git diff --stat origin/dev/v1.0`（提交 workflow 改动后、写入本 handoff 前实测）：

```
warning: in the working copy of '.github/workflows/test.yml', LF will be replaced by CRLF the next time Git touches it
 .github/workflows/test.yml | 2 ++
 1 file changed, 2 insertions(+)
```

`git diff origin/dev/v1.0` 原文：

```
warning: in the working copy of '.github/workflows/test.yml', LF will be replaced by CRLF the next time Git touches it
diff --git a/.github/workflows/test.yml b/.github/workflows/test.yml
index 89725ff..c45dd4f 100644
--- a/.github/workflows/test.yml
+++ b/.github/workflows/test.yml
@@ -1,6 +1,8 @@
 name: test
 
 on:
+  push:
+    branches: [dev/v1.0]
   pull_request:
     branches: [dev/v1.0]
   workflow_dispatch:
```

未改 `permissions`、并发组、`windows-latest`、`timeout-minutes: 40`、五个步骤及其内容、两个 Action 的 SHA 与版本注释；未改任何文档、测试、`pyproject.toml`、`project_memory/`；未新增 `dependabot.yml`。

## 2. 为什么

仓库无法启用分支保护（Free 私有库，API 403），合并前的 CI 绿只能人工把关。加 `push` 触发后，合入 `dev/v1.0` 的提交会自动重跑默认门与 OpenSSL 门，「合并头是否真的绿」不再依赖人工记得复跑。

## 3. 自查输出（原文）

### 3.1 `git diff --stat origin/dev/v1.0`

见 §1：`1 file changed, 2 insertions(+)`，无 deletions；仅 `.github/workflows/test.yml`。

### 3.2 `git diff origin/dev/v1.0`

见 §1 原文：仅显示 `+  push:` / `+    branches: [dev/v1.0]` 两行。

### 3.3 提交 blob 行属性（`HEAD:.github/workflows/test.yml` = `c45dd4fdf86320274958987859ad8ae10460b61a`，父 blob `89725ff439ff5d1615cc9951295e851bb2076acb`）

```
=== lines ===
41
=== bytes ===
1127
=== CR byte count ===
0
=== trailing bytes (od) ===
 20 66 69 0a
=== last 2 lines repr ===
            echo "openssl not found on runner; PROJECT_MEMORY_REQUIRE_OPENSSL gate SKIPPED (not passed)"$
          fi$
=== sha256 blob ===
f40f81926a3df351fb773abd18db8a81f3aeabb815baac84e605374115545d95 *-
```

41 行、0 个 `\r`、以单个 `0a` 结尾（无多余空行），符合「39→41、LF、单一结尾换行」。判断依据为提交 blob，非工作树（工作树为 CRLF）。

### 3.4 YAML 解析断言（PyYAML 6.0.1，`yaml.safe_load`，对象为上述提交 blob）

```
PASS    top-level trigger key resolves to boolean True   [doc keys=['name', True, 'permissions', 'concurrency', 'jobs']]
PASS    trigger keys == {push, pull_request, workflow_dispatch}   [actual=['pull_request', 'push', 'workflow_dispatch']]
PASS    True['push']['branches'] == ['dev/v1.0']   [actual={'branches': ['dev/v1.0']}]
PASS    True['pull_request']['branches'] == ['dev/v1.0']   [actual={'branches': ['dev/v1.0']}]
PASS    permissions == {'contents': 'read'}   [actual={'contents': 'read'}]
PASS    jobs.keys() == {'pytest'}   [actual=['pytest']]
PASS    runs-on == 'windows-latest'   [actual='windows-latest']
PASS    timeout-minutes == 40   [actual=40]
PASS    both uses fields pinned to 40-hex SHA (+optional version comment)   [actual=['actions/checkout@11d5960a326750d5838078e36cf38b85af677262', 'actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065']]
PASS    step names in order: checkout / setup-python / Install test dependency / Default gate / OpenSSL gate   [actual=['checkout', 'setup-python', 'Install test dependency', 'Default gate', 'OpenSSL gate']]
PASS    concurrency['group'] == 'test-${{ github.ref }}'   [actual='test-${{ github.ref }}']
---
total=11 passed=11 failed=0
EXIT=0
```

正则 `^[^@]+@[0-9a-f]{40}( # v[0-9]+\.[0-9]+\.[0-9]+)?$`。`on:` 在 YAML 1.1 下解析为布尔键 `True`；步骤名对 `uses` 步骤取 `owner/repo@…` 的 repo 段（`checkout` / `setup-python`），与基线命名一致。

### 3.5 负对照（在临时副本里删掉新增两行）

```
removed: '  push:' '    branches: [dev/v1.0]'
new line count (incl trailing empty): 40
=== diff vs committed ===
--- committed.yml
+++ negative_control.yml
@@ -1,8 +1,6 @@
 name: test
 
 on:
-  push:
-    branches: [dev/v1.0]
   pull_request:
     branches: [dev/v1.0]
   workflow_dispatch:
=== run assertions on negative control ===
PASS    top-level trigger key resolves to boolean True   [doc keys=['name', True, 'permissions', 'concurrency', 'jobs']]
FAILED  trigger keys == {push, pull_request, workflow_dispatch}   [actual=['pull_request', 'workflow_dispatch']]
FAILED  True['push']['branches'] == ['dev/v1.0']   [actual=None]
PASS    True['pull_request']['branches'] == ['dev/v1.0']   [actual={'branches': ['dev/v1.0']}]
PASS    permissions == {'contents': 'read'}   [actual={'contents': 'read'}]
PASS    jobs.keys() == {'pytest'}   [actual=['pytest']]
PASS    runs-on == 'windows-latest'   [actual='windows-latest']
PASS    timeout-minutes == 40   [actual=40]
PASS    both uses fields pinned to 40-hex SHA (+optional version comment)   [actual=['actions/checkout@11d5960a326750d5838078e36cf38b85af677262', 'actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065']]
PASS    step names in order: checkout / setup-python / Install test dependency / Default gate / OpenSSL gate   [actual=['checkout', 'setup-python', 'Install test dependency', 'Default gate', 'OpenSSL gate']]
PASS    concurrency['group'] == 'test-${{ github.ref }}'   [actual='test-${{ github.ref }}']
---
total=11 passed=9 failed=2
EXIT=1
```

两条与 `push` 直接相关的断言 FAILED（`trigger keys` 集合、`True['push']['branches']`），其余 9 条仍 PASS，退出码 1 → 断言非恒真。

补充交叉核对：对基线 blob（`origin/dev/v1.0:.github/workflows/test.yml`，39 行）跑同一脚本，得到完全相同的 2 FAILED / 9 PASS，且负对照副本与基线 blob 逐字节相同（`cmp` IDENTICAL），说明负对照等价于基线状态、删掉的正是新增内容。

## 4. 门槛实测

解释器 `C:/SoftWare/Anconda/python.exe`（Python 3.12.4，pytest 9.1.1）；本机 `python` 是 Store 别名，未使用。

| # | 项目 | 命令 | 结果 | 耗时（墙钟） | 退出码 |
|---|---|---|---|---|---|
| 1 | 默认门槛 | `C:/SoftWare/Anconda/python.exe -m pytest -q` | **257 passed, 2 skipped**（pytest 自报 166.25s） | 167s | **0** |
| 2 | OpenSSL 门槛 | `PROJECT_MEMORY_REQUIRE_OPENSSL=1 C:/SoftWare/Anconda/python.exe -m pytest -q` | **257 passed, 2 skipped**（pytest 自报 159.69s） | 161s | **0** |

本机 `openssl`：`/ucrt64/bin/openssl`，`OpenSSL 3.5.9 29 Sep 2026`（门槛 2 的前置条件成立，非跳过路径）。两次数量与基线一致；本卡不改代码。

## 5. 未验证项（NOT VERIFIED）

- **未在托管 runner 上验证 `push` 触发真的会触发**：该验证只能在本分支合并进 `dev/v1.0` 后由 push 事件自然产生，需 PM-01 事后核实运行记录。
- **未验证 GitHub 对 `push` 事件的 Actions 分钟计费影响**（私有库按分钟计费；本卡不改触发范围之外的任何设置）。
- 未改动、也未验证任何分支保护设置（本仓库为 Free 私有库，相关 API 返回 403）。
- 未在本机执行 workflow 本身（本地无 Actions runner）；YAML 仅做解析级与结构断言，不等于 runner 上的语义验证。
- 工作树为 CRLF、提交 blob 为 LF：所有行尾结论均基于 blob，未以工作树判断。

## 6. 提交与推送

- 变更提交：`137f457a14160afa7f40be7f1398dcb1d7084e37`（`ci(workflow): also run gate on push to dev/v1.0`），仅含 `.github/workflows/test.yml`。
- handoff 提交：本文件所在提交（单独提交，不含 workflow 改动）。
- 分支 `ci/postmerge-trigger-20261030` 推送供核对。
- 未建 PR、未合并、未打 tag/Release，未动 `dev/v1.0`。
- 工作区存在的两份既有未跟踪文件（`PM02_COLD_START_VALIDATION.md`、`tasks/PM02-cold-start-handoff-20261029T150500Z.md`）非本任务产物，未纳入任何提交。

UTC 记录时间：`2026-10-30T07:59:14Z`
