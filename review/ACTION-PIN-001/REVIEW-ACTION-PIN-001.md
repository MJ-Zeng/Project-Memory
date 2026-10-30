# 独立复核：ACTION-PIN-001 第三方 Action 按提交 SHA 固定

- 复核者：PM-03（独立克隆 `pm-pilot-03`；仅依据文件与本机实测，不采信执行者/协调者自述）
- 复核日期：2026-10-30
- 复核对象：`origin/ci/pin-actions-20261030` @ `fa086c1f9e164b58e1106fe2daa978451765b479`
- 变更提交：`6268c874aab18abcd33ac473c1d63e4b6f24278c`（handoff 提交为其子 `fa086c1`）
- 基线：`d32e2499bacdabf350f7ce18c7f54c64b1d9bdd3`（`origin/dev/v1.0`）
- 解释器：`C:/SoftWare/Anconda/python.exe`（Python 3.12.4，pytest 9.1.1，PyYAML 6.0.1）
- 复核方式：在 `$TEMP` 下用 `git worktree add --detach` 做候选/基线两棵干净检出；复核期间未建 PR、未合并、未打 tag/Release，未修改被复核分支。
- 角色边界：本报告只给出技术复核结论，**不等于**批准合并；合并、发布等决定由人类审阅者作出。
- 结论口径：只针对「这份改动是否可合并」。

## 0. 结论

**PASS（技术复核）**。

- 改动与任务卡 §3 逐字一致：仅第 20、23 行两处 `uses:`，其余字节与基线完全一致，净变化恰 `+2/−2`。
- 两个 SHA 在位、格式合法；经联网独立解析，`v4`=`v4.4.0`=`11d5960a…`、`v5`=`v5.6.0`=`a26af69b…`，均为轻量标签直接指向该提交。
- YAML 结构断言全部通过；三处负对照均按预期 FAILED，证明检查非恒真。
- 两档门槛均 `257 passed, 2 skipped`、exit 0；`audit --scope current` 与基线 40 条 findings 完全一致（新增 0），`reconcile --fail-on high` exit 0，`entry_doc_*` 为 0。
- 无阻断项；handoff 存在若干非阻断偏差（见 §8），不影响改动可合并性。

## 1. 拓扑与改动范围

```
$ git rev-parse origin/ci/pin-actions-20261030 origin/dev/v1.0
fa086c1f9e164b58e1106fe2daa978451765b479
d32e2499bacdabf350f7ce18c7f54c64b1d9bdd3

$ git rev-list --parents -n 3 fa086c1
fa086c1f9e164b58e1106fe2daa978451765b479 6268c874aab18abcd33ac473c1d63e4b6f24278c
6268c874aab18abcd33ac473c1d63e4b6f24278c d32e2499bacdabf350f7ce18c7f54c64b1d9bdd3
d32e2499bacdabf350f7ce18c7f54c64b1d9bdd3 44a56954c91899b499dfd010edffbde8b9f8df33 cc6bceba0ce66f2210d25957f2d5cc2562da5172

$ git merge-base --is-ancestor d32e249 fa086c1  → exit 0（d32e249 是祖先）
$ git rev-list --count d32e249..fa086c1          → 2
$ git rev-list --merges d32e249..fa086c1 | wc -l → 0

$ git diff --name-status d32e249 fa086c1
M	.github/workflows/test.yml
A	tasks/PM02-action-pin-handoff-20261030T071515Z.md

$ git diff --numstat d32e249 fa086c1
2	2	.github/workflows/test.yml
129	0	tasks/PM02-action-pin-handoff-20261030T071515Z.md

$ git diff --shortstat d32e249 fa086c1
 2 files changed, 131 insertions(+), 2 deletions(-)

$ git diff --name-status d32e249 6268c87   → 仅 M .github/workflows/test.yml
$ git diff --name-status 6268c87 fa086c1   → 仅 A tasks/PM02-action-pin-handoff-20261030T071515Z.md
```

- 父链 `fa086c1 → 6268c87 → d32e249` 与任务卡一致；无合并提交、无第三个文件。
- workflow 净变化恰 `+2/−2`；handoff 为独立提交、单文件新增。
- 远端 tip：`git ls-remote origin refs/heads/ci/pin-actions-20261030` → `fa086c1…`，与复核对象一致。

结论：**符合**。

## 2. 内容逐字节

```
$ git rev-parse d32e249:.github/workflows/test.yml fa086c1:.github/workflows/test.yml
cede6848aa84d43bc97e31bb14e8aadb99e94eec
89725ff439ff5d1615cc9951295e851bb2076acb

$ git cat-file -s …（字节数）
基线 1000    候选 1094    差值 +94（= 47 + 47，两行各新增 47 字节）

$ 行数：基线 39，候选 39（wc -l，blob）
$ CR 数：基线 0，候选 0
$ 末字节：… "  f i \n（单个 \n 结尾，无结尾空行/无额外空行）

$ diff <(git show d32e249:...) <(git show fa086c1:...)
20c20
<       - uses: actions/checkout@v4
>       - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
23c23
<       - uses: actions/setup-python@v5
>       - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
```

- 除第 20、23 行外，其余 37 行与基线逐字节一致（行号与任务卡 §3 一致）。
- 提交 blob 为 39 行、LF、0 CR、单一结尾换行；触发条件、权限、并发、runner、超时、其余步骤内容均未变。

结论：**逐字节符合**。

## 3. 引用与标签解析（联网独立核对）

格式断言（见 §4）通过：两行均匹配 `^[^@]+@[0-9a-f]{40}( # v\d+\.\d+\.\d+)?$`。

联网解析（经本机代理，退出码均为 0）：

```
$ git -c http.proxy=http://127.0.0.1:7688 ls-remote https://github.com/actions/checkout 'refs/tags/v4' 'refs/tags/v4.4.0'
11d5960a326750d5838078e36cf38b85af677262	refs/tags/v4
11d5960a326750d5838078e36cf38b85af677262	refs/tags/v4.4.0

$ git -c http.proxy=http://127.0.0.1:7688 ls-remote https://github.com/actions/setup-python 'refs/tags/v5' 'refs/tags/v5.6.0'
a26af69be951a213d495a4c3e4e4022e16d87065	refs/tags/v5
a26af69be951a213d495a4c3e4e4022e16d87065	refs/tags/v5.6.0
```

补充核对：

- 以 `refs/tags/v4.4.0*`、`refs/tags/v5.6.0*` 再查，**无 `^{}` 剥离行**，说明是轻量标签、直接指向提交对象（不是 tag 对象），可直接用于 `uses:`。
- GitHub API 确认两 SHA 均为真实提交：`actions/checkout@11d5960a…`（提交时间 2026-07-16T19:43:47Z）、`actions/setup-python@a26af69b…`（2025-04-24T02:42:27Z）。

结论：**联网核对成立**，文件中 SHA 与 `v4`/`v4.4.0`、`v5`/`v5.6.0` 当前指向一致。本结论反映 2026-10-30 复核时刻的远端状态。

## 4. YAML 结构断言（候选 blob）

```
CR present: False
line count (splitlines): 39
ends with exactly one LF, no trailing blank: True
PASS permissions=={'contents':'read'} :: {'contents': 'read'}
PASS jobs keys == {'pytest'} :: ['pytest']
PASS runs-on==windows-latest
PASS timeout-minutes==40
PASS trigger keys == pull_request+workflow_dispatch :: ['pull_request','workflow_dispatch']
PASS pull_request branches == ['dev/v1.0'] :: {'branches': ['dev/v1.0']}
PASS workflow_dispatch present
steps: [None, None, 'Install test dependency', 'Default gate', 'OpenSSL gate']
uses : ['actions/checkout@11d5960a…', 'actions/setup-python@a26af69b…', None, None, None]
PASS 5 steps
PASS step order
PASS concurrency group == test-${{ github.ref }}
PASS 2 uses lines
PASS uses match SHA pattern
PASS checkout SHA
PASS setup-python SHA
PASS no 'on' string key（顶层键：name, True, permissions, concurrency, jobs）
RESULT: ALL PASS   EXIT=0
```

- `on:` 在 YAML 1.1 下被解析为布尔键 `True`，按任务卡要求未断言存在字符串键 `on`；触发配置实测为 `pull_request(branches=[dev/v1.0]) + workflow_dispatch`。
- 步骤顺序：checkout → setup-python → Install test dependency → Default gate → OpenSSL gate。
- 同一断言脚本跑基线 blob：`uses match SHA pattern` / `checkout SHA` / `setup-python SHA` 三项 **FAILED**（这是天然对照，见 §5）。

结论：**结构全部符合**。

## 5. 负对照（三处变异，证明断言非恒真）

在临时副本中对候选 workflow 做单点变异，用同一断言脚本运行：

| 变异 | 具体改动 | 权限断言 | SHA 断言 | 总体 |
|---|---|---|---|---|
| 原候选 | 无 | PASS | PASS | **PASS** |
| ① 还原标签 | 两行改回 `actions/checkout@v4` / `actions/setup-python@v5` | PASS | **FAILED** | **FAILED** |
| ② 截短 SHA | checkout 的 40 位 SHA 截为 39 位 `…af67726` | PASS | **FAILED** | **FAILED** |
| ③ 放宽权限 | `permissions.contents: read` → `write` | **FAILED**（`{'contents':'write'}`） | PASS | **FAILED** |

```
===== m1（还原 @v4/@v5）=====
SHA assertion: FAILED ['actions/checkout@v4', 'actions/setup-python@v5']
===== m2（39 位 SHA）=====
SHA assertion: FAILED ['actions/checkout@11d5960a326750d5838078e36cf38b85af67726', …]
===== m3（contents: write）=====
permissions assertion: FAILED {'contents': 'write'}
```

结论：**三处变异均被对应断言捕获**，检查不是恒真；同一断言在原候选与提交 blob 上全部通过。

## 6. 本地双门槛（候选 `fa086c1` 干净检出）

| # | 门槛 | 命令 | 结果 | pytest 自报 | 墙钟 | 退出码 |
|---|---|---|---|---|---|---|
| 1 | 默认 | `python -m pytest -q` | **257 passed, 2 skipped** | 170.15s | 171s | **0** |
| 2 | OpenSSL | `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q` | **257 passed, 2 skipped** | 158.08s | 159s | **0** |

`command -v openssl` → `/ucrt64/bin/openssl`；`openssl version` → `OpenSSL 3.5.9 29 Sep 2026`，故门槛 2 为实跑而非跳过路径。计数与基线一致（本卡不改代码）。

## 7. 审计与 reconcile（候选 vs 基线，独立树）

```
$ python -m project_memory audit --repo . --scope current    # 候选 fa086c1 → exit 0
$ python -m project_memory audit --repo . --scope current    # 基线 d32e249 → exit 0
```

| 指标 | 候选 `fa086c1` | 基线 `d32e249` |
|---|---|---|
| counts | high 0 / medium 16 / low 24 | high 0 / medium 16 / low 24 |
| 总数 | 40 | 40 |
| `(severity, code, location)` 排序多重集 sha256 | `626e01fb28be488640767661305343aec8e86a594122ca127ce58dcd2c164843` | `626e01fb28be488640767661305343aec8e86a594122ca127ce58dcd2c164843` |
| added / removed | 0 / 0 | — |
| `entry_doc_*` finding | 0 | 0 |
| `location` 以 `.github` 开头 | 无 | 无 |
| exit | 0 | 0 |

code 分布（两棵树完全一致）：

```
ambiguous_reference 14, broken_document_reference 1, broken_reference 4,
dynamic_artifact_reference 2, reference_authority_mismatch 14,
reference_outside_repository 1, unknown_document_status 4
```

```
$ python -m project_memory reconcile --repo . --fail-on high   # 候选 → exit 0
$ python -m project_memory reconcile --repo . --fail-on high   # 基线 → exit 0
counts: high 0 / medium 16 / low 24
```

结论：**多重集完全一致、新增 0、entry_doc 0、reconcile exit 0**。

## 8. handoff 与事实比对

| handoff 声明 | 独立实测 | 结论 |
|---|---|---|
| 基线 `d32e249…`、分支 `ci/pin-actions-20261030` | 一致 | 一致 |
| 变更提交 `6268c87…` 仅含 workflow；handoff 为其子 | `rev-list --parents`、逐提交 `name-status` 证实 | 一致 |
| `git diff --stat` → 1 file changed, 2+/2− | workflow numstat 2/2（handoff 未提交时） | 一致 |
| 两处 `uses` 位于第 20、23 行 | `grep -n` 实测 20/23 | 一致 |
| blob 无 CR、39 行、单一结尾换行 | 实测 39 行、0 CR、单 `\n`、1000→1094 字节 | 一致 |
| YAML 断言输出（permissions/jobs/uses/触发器/runs-on/timeout/step count） | 全部复现 | 一致 |
| `ls-remote` 四条结果（v4/v4.4.0/v5/v5.6.0） | 独立重跑，输出逐字相同，exit 0 | 一致 |
| 默认门槛 257 passed / 2 skipped / exit 0（pytest 216.91s，墙钟 218s） | 257/2 / exit 0，pytest 170.15s，墙钟 171s | 计数与退出码一致；耗时不同（机器负载，非阻断） |
| OpenSSL 门槛 257/2 / exit 0（pytest 148.11s） | 257/2 / exit 0，pytest 158.08s | 同上 |
| 解释器 Python 3.12.4、pytest 9.1.1；openssl 3.5.9 | 全部一致 | 一致 |
| 审计 40 条 0/16/24、新增 0、`.github` 无 finding | 一致（多重集哈希相同） | 一致 |
| 未在托管 runner 运行、未核验上游代码安全 | handoff §5 明确声明，未夸大为已验 | 一致（如实） |

### 非阻断偏差 / 观察

1. **耗时差异**：handoff 记录 pytest 216.91s / 148.11s，本次 170.15s / 158.08s；计数与退出码相同，属机器负载差异，不影响结论。
2. **worktree 行尾表述**：handoff §3.4 称「工作树与提交 blob 均无 `\r`」。本次独立**全新检出**的候选工作树为 CRLF（1133 字节、39 CR），原因是本机 `core.autocrlf=true` 且 `.gitattributes` 未覆盖 `.github/**`；提交 blob 仍为 LF（1094 字节、0 CR）。CI 使用 blob，故无影响；handoff 的表述仅在其“原地编辑后、未被 Git 重新检出”的时刻成立（其自身引用的 `LF will be replaced by CRLF` 警告也印证了 autocrlf 生效）。建议措辞改为“提交 blob 无 CR”，避免误导。
3. **无法核实的执行者环境**：handoff §6 称 `pm-pilot-02` 克隆另有两份既有未跟踪文件（`PM02_COLD_START_VALIDATION.md`、`tasks/PM02-cold-start-handoff-20261029T150500Z.md`），本机无法核实；不影响改动内容。
4. **任务卡外无越界改动**：未新增 `dependabot.yml`、未改测试/文档计数、未改 workflow 其余行，符合 §2/§7。

## 9. 残余风险

- **未在 GitHub 托管 runner 上运行**：`windows-latest` 上的 checkout/setup-python/pip/openssl 行为未实测，首跑以 PR CI 日志为准。
- **只解决“引用不可变”，不解决“上游可信”**：两个 SHA 对应的 Action 源码安全性未审计；固定 SHA 只是防止标签移动导致的静默变更。
- **版本冻结**：固定到 `v4.4.0` / `v5.6.0` 后，上游后续补丁不会自动进入；需要人工（或后续 Dependabot 立项）定期升级。`setup-python@v5.6.0` 提交时间为 2025-04-24，非当前最新补丁，属预期内的固定点。
- **注释可能过期**：行尾 `# v4.4.0` / `# v5.6.0` 只是可读提示；若将来改 SHA 需同步更新注释，否则注释与 SHA 可能不一致（SHA 本身仍不可变）。
- **审计口径**：handoff 位于 `tasks/`，不在 current 规范文档集合内，故审计计数不变；这符合本卡“不改计数”的要求，但也意味着该 handoff 不受文档审计覆盖。

## 10. NOT VERIFIED

- 未在 GitHub Actions 托管运行器上实际执行本次 workflow。
- 未审计两个 Action 的源码内容与供应链可信度。
- 未核实执行者克隆 `pm-pilot-02` 的工作区状态与未跟踪文件。
- 未验证分支保护、PR CI 运行结果（任务卡明确由 PM-01 在复核通过后发起）。
- 本次复核未建 PR、未合并、未启用分支保护、未触发任何 CI 运行。

## 11. 复核产物

- 本报告：`review/ACTION-PIN-001/REVIEW-ACTION-PIN-001.md`，位于分支 `review/action-pin`（自 `d32e249` 开出），已推送 origin。
- 复核期间的临时 worktree 与本机临时文件已在结束后清理（含 `git worktree prune`）。

**结论重申：PASS（仅指该改动可合并）。本报告不构成合并批准，合并与否由人类审阅者与 PM-01 决定。**
