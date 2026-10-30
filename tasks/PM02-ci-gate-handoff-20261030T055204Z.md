# PM-02 执行交接：CI-GATE-001 最小权限 CI 门禁

- 执行者：PM-02（独立克隆 `pm-pilot-02`）
- 任务卡：`import-workspace/PM02_CI_GATE_TASK_CARD.md`
- 基线：`907501208383c35180e3a1f0dfc1d229854e1831`（`origin/dev/v1.0`）
- 分支：`ci/minimal-gate-20261030`（从 `origin/dev/v1.0` 新建）
- 本交接文件的结论状态：**执行者如实记录，未下 PASS 结论**；复核结论由 PM-03/人类给出。

## 1. 提交

| 提交 | SHA | 内容 |
|---|---|---|
| 变更 | `9148c97d0b27af0c86c8846b32eb2798da1f36bf` | 新增 `.github/workflows/test.yml`（39 行） |
| 本 handoff | （见该文件所在提交） | `tasks/PM02-ci-gate-handoff-20261030T055204Z.md` |

## 2. 改动范围（§4 第 1 项）

```
$ git diff --name-status 9075012..9148c97
A	.github/workflows/test.yml

$ git diff --numstat 9075012..9148c97
39	0	.github/workflows/test.yml
```

仅新增 1 个文件，净增 39 行、0 删除（≤ 60）。提交 blob：`cede6848aa84d43bc97e31bb14e8aadb99e94eec`，1000 字节，LF 行尾（`grep -c $'\r'` = 0）。仓库此前无 `.github/` 目录。

文件内容与任务卡 §3 逐字一致：

```
$ diff -u <(sed -n '33,71p' PM02_CI_GATE_TASK_CARD.md) .github/workflows/test.yml
（无输出，exit 0）
```

实测所跑文件与提交 blob 的 SHA-256 相同：`be98ad90f394157faa7bc0c9960fd451c0f335a872e3362ac6321f2da42e8734`。

## 3. YAML 解析与结构（§4 第 2 项）

```
$ C:/SoftWare/Anconda/python.exe -c "import yaml;d=yaml.safe_load(open('.github/workflows/test.yml',encoding='utf-8'));assert isinstance(d,dict);assert d['permissions']=={'contents':'read'};assert 'pytest' in d['jobs'];print(sorted(map(str,d)))"
['True', 'concurrency', 'jobs', 'name', 'permissions']
assert_exit=0
```

键集含 `name`/`permissions`/`concurrency`/`jobs` 与 YAML 1.1 布尔键 `True`（裸 `on:` 的预期解析结果）；**未**断言存在名为 `on` 的键。PyYAML 6.0.1（环境自带，未安装）。

附加结构核对（同一解析结果）：

- 触发：`pull_request`（`branches: ['dev/v1.0']`）、`workflow_dispatch`；无 `pull_request_target`
- `permissions: {'contents': 'read'}`，无 `write`
- `jobs.pytest.runs-on = windows-latest`，`timeout-minutes = 40`
- 步骤 5 个：`actions/checkout@v4`（`persist-credentials: false`）、`actions/setup-python@v5`（3.12）、安装 `pytest==9.1.1`、`Default gate`（bash）、`OpenSSL gate`（bash）
- `concurrency = {'group': 'test-${{ github.ref }}', 'cancel-in-progress': True}`

## 4. 本地等价门槛（§4 第 3 项）

在该检出（含该文件）中，解释器位于仓库外 `C:/SoftWare/Anconda/python.exe`：

| 门槛 | 命令 | 结果 | 退出码 |
|---|---|---|---|
| 默认 | `C:/SoftWare/Anconda/python.exe -m pytest -q` | `257 passed, 2 skipped in 169.38s` | 0 |
| OpenSSL | `PROJECT_MEMORY_REQUIRE_OPENSSL=1 C:/SoftWare/Anconda/python.exe -m pytest -q` | `257 passed, 2 skipped in 177.24s` | 0 |

本机 `openssl version` → `OpenSSL 3.5.9`（exit 0），故 OpenSSL 门槛实跑而非跳过。两条均为 257 passed / 2 skipped、exit 0，与该文件不在时无差异。

## 5. 审计与 reconcile（§4 第 4、5 项）

```
PROJECT_MEMORY_PYTHON=/c/SoftWare/Anconda/python ./bin/project-memory audit --scope current
→ counts {'high': 0, 'low': 24, 'medium': 16}  total 40  (exit 0)
```

基线比对：在仓库外 detached 于 `9075012` 的临时 worktree 内复跑同一命令，按 `(severity, code, location)` 多重集比较：

```
current  counts {'high': 0, 'low': 24, 'medium': 16} total 40
baseline counts {'high': 0, 'low': 24, 'medium': 16} total 40
added: 0  removed: 0   multiset_equal: True
location 以 .github 开头的 finding: []
```

即 40 条、high 0 / medium 16 / low 24、新增 0、减少 0，`.github` 下无 finding。临时 worktree 已 `git worktree remove --force`。

```
PROJECT_MEMORY_PYTHON=/c/SoftWare/Anconda/python ./bin/project-memory reconcile --fail-on high
→ counts {'high': 0, 'low': 24, 'medium': 16}  exit 0
```

## 6. 残留（§4 第 7 项）

提交后 `git status --porcelain`：

```
?? PM02_COLD_START_VALIDATION.md
?? tasks/PM02-cold-start-handoff-20261029T150500Z.md
```

仅任务书指定「不要触碰」的两份既有未跟踪文件；本次任务自身未引入任何工作区改动（审计/测试产物均写在仓库外临时目录）。

## 7. 未在 GitHub Actions 上真实运行

**本文件未在 GitHub Actions 托管运行器上执行过。** 本地无法验证 `windows-latest` 运行器上的 checkout、setup-python、pip、openssl 可用性及 `shell: bash` 行为；所有结论仅限本地同等命令的等价结果。托管运行器首跑结果以实际 CI 日志为准。

## 8. 偏差

- 无功能性偏差。pytest 两条门槛在该文件中已存在于工作树、提交前执行；提交 blob 与实测文件 SHA-256 相同，故结果对应同一内容。
- 未做任务卡禁止的动作：未创建/启用 workflow（未调用 `gh`/GitHub API）、未开启分支保护、未建 PR、未合并、未动 `dev/v1.0`、未打 tag/Release。

## 9. NOT VERIFIED

- 远端分支推送后的状态（push 前先 `git ls-remote` 确认不存在，push 后实际值见 §10）。
- GitHub Actions 上的实际运行与状态（见 §7）。
- 分支保护与「连续 3 次绿」——本轮按任务卡明确不做。

## 10. 远端状态

写本文件前已确认远端无该分支：

```
$ git ls-remote origin refs/heads/ci/minimal-gate-20261030
（无输出，exit 0）
```

按任务卡 §4 第 6 项「只用一次 `git push`」，本 handoff 先于 push 定稿；push 后的实际远端 SHA 未写回本文件，属 NOT VERIFIED（复核时以 `git ls-remote` 为准）。
