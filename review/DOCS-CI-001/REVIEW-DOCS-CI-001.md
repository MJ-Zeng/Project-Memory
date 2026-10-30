# 独立复核报告：DOCS-CI-001

- 复核者：PM-03（独立克隆 `pm-pilot-03`，无执行者上下文）
- 复核日期：2026-10-30
- 复核对象：`origin/docs/ci-facts-20261030` 顶点 `b59b846708634d35f5bcae48639922282f605da9`
- 基线：`origin/dev/v1.0` = `87600d7854d51b1d6f860382bfe90caaa47d9e9b`
- 复核分支：`review/docs-ci`（自候选顶点新建，未复用旧分支）
- 解释器：`C:/SoftWare/Anconda/python.exe`（Python 3.12.4，pytest 9.1.1）；`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`
- 隔离方式：`git archive <sha> | tar -x -C /tmp/docci-{base,cand}` 干净检出；仓库内无 `.venv`，未使用任何工作区虚拟环境
- 证据性质：本报告全部数字与退出码为本会话实测；交接文件只作输入，不采信其结论

本报告不构成合并批准。复核者未开 PR、未合并、未打 tag、未发布 Release、未修改 `dev/v1.0`。

---

## 1. 结论

**PASS WITH DEVIATIONS**

任务卡要求的 9 项复核全部完成并实测通过：范围与父提交、workflow 细节、README 逐句一致性、第 2/3 条改写、文字卫生、审计与对账、双门槛、两项负对照、交接文件准确性。未发现功能性或事实性错误。

偏差 3 项（均为非阻塞的表述/文档精度问题）：

| ID | 偏差 | 严重度 |
|---|---|---|
| D-1 | 交接文件 §1 标注为 `git diff --stat origin/dev/v1.0` 的输出只列 2 文件 / 13 insertions，在候选 HEAD 逐字运行实为 3 文件 / 202 insertions（差一个交接文件自身）。属写入时序造成的不可逐字复现，正文数字本身无误 | 低 |
| D-2 | README 新小节把门槛写成 `pytest -q` / `PROJECT_MEMORY_REQUIRE_OPENSSL=1 pytest -q`，workflow 实为 `python -m pytest -q` / `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q`（省略 `python -m`）。语义相同，但本仓库 README 别处特意提醒裸解释器别名坑，简写不够精确 | 低 |
| D-3 | 新版第 3 条把 `actions/checkout`、`actions/setup-python` 称为“第三方 Action”。两者是 GitHub 官方维护的 Action，称谓不精确；"按提交 SHA 固定"这一事实陈述本身正确 | 低 |

未验证项 2 项，见 §7：

| ID | 未验证项 |
|---|---|
| N-1 | “当前没有启用分支保护（私有仓库的免费计划不提供该能力）”及其推论“CI 结果是建议性的” |
| N-2 | 合并后 `push` 运行“在合并提交上再验证一次”在托管环境的实际行为（依赖 GitHub 事件语义，未实跑） |

---

## 2. 逐项检查

### 2.1 范围与父提交

```
$ git rev-list --parents -n 1 b59b846
b59b846708634d35f5bcae48639922282f605da9 87600d7854d51b1d6f860382bfe90caaa47d9e9b

$ git diff --name-status 87600d7 b59b846
M       .github/workflows/test.yml
M       README.md
A       tasks/PM02-docs-ci-handoff-20261030T111716Z.md

$ git diff --numstat 87600d7 b59b846
1       1       .github/workflows/test.yml
12      2       README.md
189     0       tasks/PM02-docs-ci-handoff-20261030T111716Z.md

$ git diff --check 87600d7 b59b846 ; echo $?
0
```

结论：父提交为 `87600d7`，一致；diff 文件清单恰为 README.md、`.github/workflows/test.yml`、`tasks/PM02-docs-ci-handoff-*.md`，一致；两文件合计 **+13 / −3**（README 单文件 +12 / −2，workflow +1 / −1），与任务卡一致；`--check` 干净。

### 2.2 workflow 细节

```
$ git cat-file -p b59b846:.github/workflows/test.yml | wc -l -c
41  1152
CR 计数 = 0；xxd 尾部：... 2020 6669 0a   （单个 LF 收尾）
$ git diff -U0 87600d7 b59b846 -- .github/workflows/test.yml
@@ -14 +14 @@ concurrency:
-  group: test-${{ github.ref }}
+  group: test-${{ github.ref }}-${{ github.event_name }}
```

PyYAML 解析（脚本读取，未按字面 key 名误判）：

```
top_keys = ['name', True, 'permissions', 'concurrency', 'jobs']   # 未加引号的 on 被 PyYAML 1.1 解析为 True
on(True) = {'push': {'branches': ['dev/v1.0']},
            'pull_request': {'branches': ['dev/v1.0']},
            'workflow_dispatch': None}
permissions = {'contents': 'read'}
uses[0] = actions/checkout@11d5960a326750d5838078e36cf38b85af677262      ref_len=40 hex40=True
uses[1] = actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065   ref_len=40 hex40=True
checkout.with = {'persist-credentials': False}
```

结论：候选 blob 41 行、0 个 CR、末尾单个换行；hunk 只动 `group` 一行；YAML 可解析，`on` 下三触发齐全且都限定 `dev/v1.0`；`permissions` 仅 `contents: read`（无 job 级覆盖）；`persist-credentials: false`；两个 `uses` 均为 40 位十六进制 SHA。全部一致。

### 2.3 README 新小节逐句核对

见 §3 逐句表。

### 2.4 第 2、3 条改写

README 第 209、210 行（`## 还需要人工完成的事` 下）：

```
$ grep -n 'v4\.4\.0\|v5\.6\.0' README.md
210:3. 审核已固定的第三方 Action 代码，并在升级时更新 SHA：当前 `actions/checkout` 固定到 `v4.4.0`、
     `actions/setup-python` 固定到 `v5.6.0`，只解决了“引用不可变”，没有审核上游代码。
```

- workflow 中 SHA 后的注释：`# v4.4.0`、`# v5.6.0`，与第 3 条文本一致。
- 联网只读校验（公开仓库 API，非本仓库写操作）：

```
GET https://api.github.com/repos/actions/checkout/commits/v4.4.0        → HTTP 200 sha=11d5960a326750d5838078e36cf38b85af677262  match=True
GET https://api.github.com/repos/actions/setup-python/commits/v5.6.0   → HTTP 200 sha=a26af69be951a213d495a4c3e4e4022e16d87065  match=True
```

- “只解决了引用不可变，没有审核上游代码”：成立。SHA 固定只保证引用不可变，不等于代码审计；仓库内除本行外无任何上游 Action 代码审计记录（`grep -rn 'v4.4.0|setup-python'` 仅命中 README 与历史复核/交接文件，均为“固定/解析”记录，非代码审计）。

结论：版本号与注释一致且可与上游标签互证；“SHA 固定 ≠ 代码审核”表述与事实相符。

### 2.5 文字卫生

```
$ sed -n '45,54p' README.md | grep -nE 'https?://|\]\(|www\.|<http'   → 无匹配（exit 1）
$ git cat-file -p b59b846:README.md | tr -cd '\r' | wc -c             → 0
$ git cat-file -p b59b846:README.md | tail -c 2 | xxd                 → 290a（单个 LF）
$ git diff 87600d7 b59b846 -- README.md | grep -cE '^\+.*[[:blank:]]$' → 0
```

补充：README 工作树因本机 `core.autocrlf=true` 呈现 CRLF（实测 232 个 CR），但提交 blob 为 LF；基线同样如此，交接文件 §4.5 已如实披露。新增小节内无任何 http(s) 链接、Markdown 链接或新增 URL；全文件无行尾空白。

结论：通过。

### 2.6 独立审计与对账（基线与候选各一次）

命令（在干净检出内，未用仓库 venv）：

```
$ cd /tmp/docci-base && PYTHONUTF8=1 PYTHONIOENCODING=utf-8 C:/SoftWare/Anconda/python.exe -m project_memory.cli audit --scope current
$ cd /tmp/docci-cand && 同上
$ … -m project_memory.cli reconcile --fail-on high
```

| 指标 | 基线 `87600d7` | 候选 `b59b846` |
|---|---|---|
| audit 退出码 | 0 | 0 |
| findings 总数 | 40 | 40 |
| counts | `{high:0, medium:16, low:24}` | `{high:0, medium:16, low:24}` |
| docs_scanned | 13 | 13 |
| entry_doc | `docs/CURRENT_STATE.md` | `docs/CURRENT_STATE.md` |
| entry_doc_* findings | 0 | 0 |
| code 直方图 | unknown_document_status 4 / broken_document_reference 1 / broken_reference 4 / reference_authority_mismatch 14 / ambiguous_reference 14 / reference_outside_repository 1 / dynamic_artifact_reference 2 | 完全相同 |

`(severity, code, location)` 多重集对比：

```
base_total=40 cand_total=40
identical_multiset: True
added_in_candidate: 0 {}
removed_in_candidate: 0 {}
```

将 audit JSON 去掉易变键（note/path_source/各 roots/manifest/max_verified_age_days）后整体比较：`equal_excluding_volatile: True`。

reconcile：基线 `exit 0`、候选 `exit 0`；两边均 `state=needs_attention`、`summary.docs={high:0, medium:16, low:24}`、`defects 0`。两份输出逐行比较仅 `generated_at` 与 `repo`（临时路径）不同。

结论：audit 40 条、0 high、16 medium、24 low，新增 0、entry_doc_* 为 0；reconcile `--fail-on high` 退出 0。与任务卡期望一致。

### 2.7 双门槛（候选干净检出）

```
$ cd /tmp/docci-cand && PYTHONUTF8=1 PYTHONIOENCODING=utf-8 C:/SoftWare/Anconda/python.exe -m pytest -q
257 passed, 2 skipped in 151.69s (0:02:31)          exit=0

$ … PROJECT_MEMORY_REQUIRE_OPENSSL=1 C:/SoftWare/Anconda/python.exe -m pytest -q
257 passed, 2 skipped in 149.34s (0:02:29)          exit=0
```

- 解释器确认为 `C:\SoftWare\Anconda\python.exe`（`sys.executable` 实测），仓库内无 `.venv`，排除“venv 假失败”。
- 追加 `pytest -q -rs` 定位 2 个 skip：`tests\test_security_rc3.py:284`、`:295`，原因均为“当前平台不允许创建符号链接”（Windows 符号链接权限），与 openssl 门槛无关；两次门槛结果完全相同，说明第二道未落入 workflow 的跳过分支（本机 `openssl 3.5.9` 存在）。
- 未出现 253 或其他异常数字。

结论：两道门槛各 257 passed / 2 skipped，退出码 0，符合期望。

### 2.8 负对照

自建核对脚本 `/tmp/docci_check.py`（45 条断言，覆盖存在性、结构、逐句一致性、卫生）先对候选跑出 `OVERALL PASS`，再在临时副本上做两项对照。

**(a) 删除 README 新增小节（第 45–54 行）**

```
FAILED | README has section '### 仓库自带的 CI' | len=0
FAILED | S1 README says 三种情况 / three triggers
FAILED | S1 mentions 'pull request' / 'push' / 'workflow_dispatch'      （逐句 3 条）
FAILED | S1 says pull request targets dev/v1.0 / push into dev/v1.0    （逐句 2 条）
FAILED | S2 runner windows-latest / Python 3.12 / pytest 9.1.1          （逐句 3 条）
FAILED | S3 two gates in order described
FAILED | S3 skip is printed explicitly, not treated as pass
FAILED | S4 permissions only contents: read / checkout keeps no credentials / actions pinned by commit SHA
FAILED | S5 branch-protection claim marked advisory
FAILED | S5 merge rule is a manual process, not automation
FAILED | S5 push re-run after merge claim backed by push trigger
OVERALL FAILED                                       exit=1
```

workflow 结构类与卫生类断言仍 PASS（符合预期：只删了 README 小节）。

**(b) 把 `concurrency.group` 还原为 `test-${{ github.ref }}`**

```
FAILED | group keys by event_name | 'test-${{ github.ref }}'
FAILED | group is the only workflow change vs baseline
（其余 43 条 —— 含 README 全部逐句断言、权限、SHA、触发器、卫生 —— 均 PASS）
OVERALL FAILED                                       exit=1
```

结论：两项负对照都按预期失败，且失败范围精确对应被破坏的部分，说明逐句核对与 existence 检查有效，未出现“删了也 PASS”的伪检查。

### 2.9 交接文件准确性

`tasks/PM02-docs-ci-handoff-20261030T111716Z.md`（189 行、0 CR、无行尾空白）：

| 交接文件陈述 | 实测 | 结论 |
|---|---|---|
| 基线 SHA `87600d7…`，本地 ref 起初 `617cdd9`，fetch 后一致 | 本会话 `git fetch origin` 输出 `617cdd9..87600d7  dev/v1.0` | 属实且已披露 |
| 改动文件恰为两个 + 本交接文件 | `--name-status` 三项 | 一致 |
| §1 diffstat：2 文件、13 insertions / 3 deletions | 候选 HEAD 逐字运行得 3 文件 / 202 insertions / 3 deletions | **不一致（D-1）**；2 文件 / 13 / 3 的数字本身正确，只是当时交接文件尚未跟踪/暂存 |
| §4.2 workflow 净 +1/−1，仅 group 行 | `-U0` 单行 hunk | 一致 |
| §4.3 README 新增小节 10 行 + 两条列表项各 1 行 | 新增块 10 行；第 209/210 行各替换 1 行 | 一致 |
| §4.4 `git diff --check` exit 0 | 实测 exit 0 | 一致 |
| §4.5 README 222 → 232 行、0 CR、单结尾换行、工作树 CRLF | 实测 222/232、0 CR、`0a` 收尾、工作树 232 个 CR | 一致 |
| §4.6 逐项对照表（触发/运行器/Python/pytest/双门槛/跳过/权限/凭据/SHA） | 与 §3 本报告逐句核对结果相同 | 一致 |
| §4.7 结构断言 19 条 OVERALL PASS | 我用自有脚本独立复跑得到等价 PASS | 一致 |
| §4.8 两项负对照 FAILED | 我用自有脚本独立复跑，结果一致（§2.8） | 可复现 |
| §4.9 双门槛 257 passed / 2 skipped，exit 0，耗时 161.96s / 159.65s | 实测 257/2、exit 0，耗时 151.69s / 149.34s | 数字一致；耗时差异属机器负载，不构成不符 |
| §4.10 audit 40 条 `{0,16,24}`、docs_scanned=13、多重集一致、entry_doc_* 0、reconcile exit 0 `needs_attention` | 逐项实测一致 | 一致 |
| §5 未验证项（托管 runner 行为、账户计划、GitHub 事件语义） | 与本次复核的 N-1 / N-2 吻合，交接方已主动披露 | 一致 |

结论：交接文件除 §1 的命令标签外，数字与陈述均可复现；未发现夸大或造假。

---

## 3. README 新小节逐句核对表

新增小节位于 README 第 45–54 行，夹在“开关取值…”与 `## 目标、执行与独立验证` 之间。

| # | 原句（行号） | 依据（文件/行号、命令输出） | 结论 |
|---|---|---|---|
| S1 | 本仓库的 `.github/workflows/test.yml` 在三种情况下运行同一套检查：目标为 `dev/v1.0` 的 pull request、合入 `dev/v1.0` 的 push，以及手动 `workflow_dispatch`。（L47） | test.yml L3–L8；YAML 解析得 `push.branches=[dev/v1.0]`、`pull_request.branches=[dev/v1.0]`、`workflow_dispatch`；全文件只有一个 job、一套 steps | 一致 |
| S2 | 运行器 `windows-latest`，Python 3.12，pytest 固定为 9.1.1。（L49） | L19 `runs-on: windows-latest`；L27 `python-version: "3.12"`；L29 `pip install ... "pytest==9.1.1"`；`pyproject.toml` dev extra 亦为 `pytest==9.1.1` | 一致 |
| S3a | 两道门槛依次执行：默认 `pytest -q`，以及 `PROJECT_MEMORY_REQUIRE_OPENSSL=1 pytest -q`。（L50） | L30–L32 Default gate 在前，L33–L38 OpenSSL gate 在后；env 名一致；但实际命令为 `python -m pytest -q` / `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python -m pytest -q` | 基本一致（D-2：省略 `python -m`） |
| S3b | 运行器没有 openssl 时，第二道会在日志里显式打印跳过，不会把跳过当成通过。（L50） | L36 `if command -v openssl >/dev/null 2>&1`；L39–L40 `else echo "openssl not found on runner; PROJECT_MEMORY_REQUIRE_OPENSSL gate SKIPPED (not passed)"` | 一致 |
| S4a | 权限只有 `contents: read`（L51） | L10–L11；无 job 级 `permissions` 覆盖 | 一致 |
| S4b | checkout 不保留凭据（L51） | L22–L24 `persist-credentials: false` | 一致 |
| S4c | 第三方 Action 按提交 SHA 固定（L51） | L22 `actions/checkout@11d5960a…`（40 hex，注释 v4.4.0）、L25 `actions/setup-python@a26af69b…`（40 hex，注释 v5.6.0） | 事实一致；称谓不精确（D-3：二者为 GitHub 官方 Action） |
| S5a | 当前没有启用分支保护（私有仓库的免费计划不提供该能力）（L53） | 仓库内无任何配置文件可自证；只读 API 无法取得凭据（见 §7 N-1） | **依赖外部事实，未在仓库内自证 → NOT VERIFIED** |
| S5b | 所以 CI 结果是建议性的，不会自动阻断合并（L53） | 由 S5a 推出；仓库内确无强制门禁配置 | 表述为“建议性”，与 S5a 逻辑自洽；前提未验证（绑定 N-1） |
| S5c | 合并规则是：先确认该 pull request 的 CI 运行成功，再看代码；合入后由 push 触发的运行会在合并提交上再验证一次。（L53） | 属流程约定；`push: branches: [dev/v1.0]` 确实存在（L4–L5）；原文以“合并规则是”的叙述口吻给出，未声称自动阻断 | 表述为人工/建议性约定，不是自动门禁，符合任务卡要求；实际事件行为见 N-2 |

补充说明：

- S5a 的括号内还断言“需要 GitHub Pro 或改为公开仓库”（第 209 行同样如此），同属外部事实，一并计入 N-1。
- S1–S5c 未出现把流程约定写成“自动阻断”的表述；L53 明确写“不会自动阻断合并”，与“建议性”一致。
- 新增小节未涉及 `.project-memory/`、审计计数等易漂移数字，不存在“文档与实测计数不一致”的风险面。

---

## 4. 负对照结论

| 对照 | 破坏点 | 预期 | 实测 |
|---|---|---|---|
| (a) | 删除 README 第 45–54 行新增小节 | 存在性与逐句检查 FAILED | 18 条 FAILED（共 45 条断言），`OVERALL FAILED`，exit 1；workflow/卫生类 27 条仍 PASS |
| (b) | `group` 还原为 `test-${{ github.ref }}` | 仅 `github.event_name` 相关断言 FAILED | 2 条 FAILED，其余 43 条 PASS，`OVERALL FAILED`，exit 1 |

两项均按预期失败，检查有效。

---

## 5. 偏差清单（非阻塞）

- **D-1｜交接文件 §1 命令输出不可逐字复现。** 标题写 `git diff --stat origin/dev/v1.0`，正文只列 2 文件 / 13 insertions；在候选 HEAD 逐字运行得 3 文件 / 202 insertions（含交接文件自身 189 行）。属写入时序（交接文件当时尚未跟踪/暂存）造成，正文数字无误，但读者照抄命令会得到不同结果。建议后续交接把命令标注为“仅两文件”或加 pathspec。
- **D-2｜README 门槛命令简写。** 新小节写 `pytest -q`，workflow 实为 `python -m pytest -q`。语义相同，但 README 第 41 行专门提醒 Windows 上裸解释器别名坑，文档建议与 workflow 保持同一写法，避免读者在本机复现时踩 PATH 问题。
- **D-3｜“第三方 Action”称谓。** `actions/checkout`、`actions/setup-python` 为 GitHub 官方维护，称“第三方”不精确；改为“所用 Action”或“外部 Action”即可。“按提交 SHA 固定”的事实陈述正确。

---

## 6. 未验证项（NOT VERIFIED）

**N-1｜分支保护状态与账户计划能力。**

- 仓库内无任何分支保护配置可自证（保护规则只存在于 GitHub 服务端）。
- 只读探测（未携带任何凭据、未做写操作）：

```
GET https://api.github.com/repos/MJ-Zeng/Project-Memory                          → HTTP 404
GET https://api.github.com/repos/MJ-Zeng/Project-Memory/branches/dev/v1.0/protection → HTTP 401 {"message":"Requires authentication"}
GET https://api.github.com/repos/MJ-Zeng/Project-Memory/rulesets                 → HTTP 404
```

- 未复现任务卡预期的 403：无凭据时得到 404/401，无法区分“仓库私有/未启用保护/无权读取”三种情况，因此“当前没有启用分支保护”与“免费计划不提供该能力”均标为 **NOT VERIFIED**。该结论只影响 S5a/S5b 的前提，不影响代码与文档一致性。
- 本机无 `gh` CLI，环境无 `GH_TOKEN`/`GITHUB_TOKEN`，按约束不获取、不上传任何凭据。

**N-2｜托管环境事件行为。**

- `push` 触发（`branches: [dev/v1.0]`）在合并后是否确实在合并提交上重跑、以及 `concurrency.group` 加入 `github.event_name` 后 `workflow_dispatch` 与 `push` 运行是否互不取消，均需真实 GitHub Actions 运行观察；本次仅做静态结构与语义核对，未在托管 runner 实跑。

**补充（非 NOT VERIFIED，仅说明边界）：** README 第 3 条“没有审核上游代码”是对“未做审计”的否定性陈述。我验证了 SHA 与上游标签一一对应，但无法证明“历史上从未有人阅读过上游代码”；仓库内无相反证据，且本条本身把“审核上游代码”列为待办，表述自洽，故按事实陈述接受。

---

## 7. 复核边界与未做事项

- 只读复核：仅创建功能分支 `review/docs-ci` 与 `/tmp/docci-*`、`/tmp/neg*` 临时目录；未改 `dev/v1.0`、未改候选分支、未 rebase、未 merge。
- 未开 PR、未合并、未打 tag、未发布 Release、未对任何 GitHub 端点做写操作。
- 未上传凭据，未打印 token；只读 API 均为匿名请求。
- 未在 GitHub 托管 runner 上运行 workflow（N-2）。

---

## 8. 本报告提交

- 分支：`review/docs-ci`
- 报告正文提交：`0ddd77f798a6251e5fb1e1c1eedfe39b9921f8dc`
- 其后仅回填本行，回填提交即分支顶点（SHA 见 PM-03 交付消息）
