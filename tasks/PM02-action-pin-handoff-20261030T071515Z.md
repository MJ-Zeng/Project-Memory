# 交接 — ACTION-PIN-001 第三方 Action 按提交 SHA 固定

- 任务 ID：`ACTION-PIN-001`
- 执行者：PM-02（独立克隆 `pm-pilot-02`）
- 基线：`d32e2499bacdabf350f7ce18c7f54c64b1d9bdd3`（`origin/dev/v1.0`）
- 分支：`ci/pin-actions-20261030`
- 决策归属：PM-01（依 readiness §12.8「已知硬化待办」提出；仓库 `allowed_actions: all`、`sha_pinning_required: false`，2026-10-30 只读查询）
- 判定：本文件只记录执行事实与实测数字，不给出 PASS/GO 结论。

## 1. 改了什么

仅 `.github/workflows/test.yml` 两行 `uses:`，其余 0 行改动，净变化恰为 `+2/−2`。

`git diff --stat origin/dev/v1.0`（提交改动后、写入本 handoff 前实测）：

```
warning: in the working copy of '.github/workflows/test.yml', LF will be replaced by CRLF the next time Git touches it
 .github/workflows/test.yml | 4 ++--
 1 file changed, 2 insertions(+), 2 deletions(-)
```

`git diff origin/dev/v1.0` 原文：

```
diff --git a/.github/workflows/test.yml b/.github/workflows/test.yml
index cede684..89725ff 100644
--- a/.github/workflows/test.yml
+++ b/.github/workflows/test.yml
@@ -17,10 +17,10 @@ jobs:
     runs-on: windows-latest
     timeout-minutes: 40
     steps:
-      - uses: actions/checkout@v4
+      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
         with:
           persist-credentials: false
-      - uses: actions/setup-python@v5
+      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
         with:
           python-version: "3.12"
       - name: Install test dependency
```

未改触发条件、权限、并发、runner、超时、其余步骤；未改文档、测试、`pyproject.toml`、`project_memory/`；未新增 `dependabot.yml`。文件仍为 39 行、单一结尾换行、无新增空行。

## 2. 为什么

`actions/checkout@v4` / `actions/setup-python@v5` 是可变标签引用，上游可把标签移动到其他提交。改为引用不可变提交 SHA 并在行尾保留可读版本注释，行为不变、供应链引用不可变。本卡只解决「引用不可变」，不解决「上游可信」。

## 3. 自查输出（原文）

### 3.1 `grep -n "^ *- uses:" .github/workflows/test.yml`

```
20:      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
23:      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
```

（退出码 0；两行均符合 `name@<40 位十六进制> # vX.Y.Z`）

### 3.2 YAML 解析断言（针对已提交 blob `HEAD:.github/workflows/test.yml`）

```
committed blob contains CR: False
assert doc['permissions'] == {'contents': 'read'}: True
assert 'pytest' in doc['jobs']: True
assert len(uses) == 2: True
assert all(pat.match(u) for u in uses): True
parsed uses values (YAML strips trailing comments): ['actions/checkout@11d5960a326750d5838078e36cf38b85af677262', 'actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065']
'on' key present: False | True key present (YAML 1.1 bare 'on'): True
triggers: {'pull_request': {'branches': ['dev/v1.0']}, 'workflow_dispatch': None}
runs-on / timeout-minutes / step count: windows-latest 40 5
ASSERT_SCRIPT_EXIT:0
```

正则 `^[^@]+@[0-9a-f]{40}( # v[0-9]+\.[0-9]+\.[0-9]+)?$`。按任务卡要求未断言存在 `on` 键；`on:` 在 YAML 1.1 下解析为布尔键 `True`，实际触发配置与基线一致。

### 3.3 标签↔SHA 联网核对

命令（经本机代理 `http://127.0.0.1:7688`）：

```
export https_proxy=http://127.0.0.1:7688 http_proxy=http://127.0.0.1:7688
git ls-remote https://github.com/actions/checkout refs/tags/v4.4.0 refs/tags/v4
git ls-remote https://github.com/actions/setup-python refs/tags/v5.6.0 refs/tags/v5
```

输出原文：

```
11d5960a326750d5838078e36cf38b85af677262	refs/tags/v4
11d5960a326750d5838078e36cf38b85af677262	refs/tags/v4.4.0
a26af69be951a213d495a4c3e4e4022e16d87065	refs/tags/v5
a26af69be951a213d495a4c3e4e4022e16d87065	refs/tags/v5.6.0
```

两条命令退出码均为 0。`v4` 与 `v4.4.0`、`v5` 与 `v5.6.0` 各自指向同一提交（轻量标签），与文件中所写 SHA 一致。

### 3.4 行尾

工作树与提交 blob 的该文件均无 `\r`（`grep -c $'\r'` 为 0），CRLF 0 行、39 行、文件以单个 `\n` 结尾，未新增行尾改动。

## 4. 门槛实测

解释器 `C:/SoftWare/Anconda/python.exe`（Python 3.12.4，pytest 9.1.1）；本机 `python` 是 Store 别名，未使用。

| # | 项目 | 命令 | 结果 | 耗时（墙钟） | 退出码 |
|---|---|---|---|---|---|
| 1 | 默认门槛 | `C:/SoftWare/Anconda/python.exe -m pytest -q` | **257 passed, 2 skipped**（pytest 自报 216.91s） | 218s | **0** |
| 2 | OpenSSL 门槛 | `PROJECT_MEMORY_REQUIRE_OPENSSL=1 C:/SoftWare/Anconda/python.exe -m pytest -q` | **257 passed, 2 skipped**（pytest 自报 148.11s） | 149s | **0** |

本机 `openssl`：`/ucrt64/bin/openssl`，`OpenSSL 3.5.9 29 Sep 2026`（门槛 2 的 OpenSSL 前置条件成立，非跳过路径）。两次数量与基线一致；本卡不改代码。

## 5. 未验证项（NOT VERIFIED）

- **未在 GitHub 托管 runner 上运行本次改动**；PR 的 CI 运行由 PM-01 在复核通过后发起。
- **未核验上述 SHA 对应的 Action 代码内容本身是否安全**；本卡只解决「引用不可变」，不解决「上游可信」。
- 标签↔SHA 对照已联网核对（见 §3.3），网络当时可用；但核对反映的是 2026-10-30T07:12Z 左右的远端状态，后续上游若移动标签不在本次核对范围内。
- 未在本机执行 workflow 本身（本地无 Actions runner），YAML 仅做解析级与结构断言，不等于 workflow 在 runner 上的语义验证。

## 6. 提交与推送

- 变更提交：`6268c874aab18abcd33ac473c1d63e4b6f24278c`（`ci(workflow): pin third-party actions to immutable commit SHAs`），仅含 `.github/workflows/test.yml`。
- handoff 提交：本文件所在提交（单独提交，不含 workflow 改动）。
- 分支 `ci/pin-actions-20261030` 推送供核对。
- 未建 PR、未合并、未打 tag/Release，未动 `dev/v1.0`。
- 工作区存在的两份既有未跟踪文件（`PM02_COLD_START_VALIDATION.md`、`tasks/PM02-cold-start-handoff-20261029T150500Z.md`）非本任务产物，未纳入任何提交。

UTC 记录时间：`2026-10-30T07:15:15Z`
