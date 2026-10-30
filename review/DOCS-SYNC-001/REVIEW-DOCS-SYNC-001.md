# DOCS-SYNC-001 独立复核报告（PM-03）

- 复核对象：`origin/docs/state-sync-20261030`
  - 分支 tip：`d4b4b28fe68f96c6ea2a0ef3f5acd78408e3c328`（handoff 提交，父 `de3a480`）
  - 文档变更提交：`de3a480a0fd7eee277a4e1d1d9f28a311bcf1b78`（父 `9075012`）
- 基线：`907501208383c35180e3a1f0dfc1d229854e1831`（`origin/dev/v1.0`，PR #40 合并头）
- 复核时间：2026-10-30
- 复核环境：Windows 11 AMD64；解释器 `C:/SoftWare/Anconda/python.exe`（位于仓库外）；Git Bash
- 隔离方式：在 `pm-pilot-03` 内 `git fetch origin`；于仓库外临时目录建立 detached worktree 两个：`/tmp/pm03-docs-sync-d4b4b28`（=target）与 `/tmp/pm03-docs-sync-base-9075012`（=base）。未修改 `pm-pilot-02`，未使用 `project-memory-mvp`。
- 输入边界：PM-02 handoff 仅作待核对的输入，不作为任何结论依据；每条结论对应本轮自行执行的命令与输出。
- 结论：**PASS**（附非阻断偏差，见 §9）

---

## 1. 变更范围（派单第 1 条）

```bash
git diff --numstat   9075012..d4b4b28
git diff --name-status 9075012..d4b4b28
```

```text
2	2	docs/CURRENT_STATE.md
92	0	tasks/PM02-docs-sync-handoff-20261030T054337Z.md

M	docs/CURRENT_STATE.md
A	tasks/PM02-docs-sync-handoff-20261030T054337Z.md
```

- 仅 2 个文件，无第三个文件；`docs/CURRENT_STATE.md` 恰为 2/2，handoff 新增 92 行。
- 提交拆分核对：`9075012..de3a480` 仅 `M docs/CURRENT_STATE.md`（2/2）；`de3a480..d4b4b28` 仅 `A tasks/PM02-docs-sync-handoff-20261030T054337Z.md`（+92）。两段相加即全范围。
- `git merge-base --is-ancestor 9075012 d4b4b28` → 是（true）；`9075012..d4b4b28` 含 2 个提交。

## 2. 正文改动边界（派单第 2 条）

```bash
git diff -U0 9075012..d4b4b28 -- docs/CURRENT_STATE.md
```

```text
@@ -19 +19 @@ v1.0.0 可以用于团队内部的记忆记录与跨会话交接；不能作为
@@ -21 +21 @@ v1.0.0 可以用于团队内部的记忆记录与跨会话交接；不能作为
```

恰为 `@@ -19 +19 @@` 与 `@@ -21 +21 @@` 两个 hunk；`git diff --check` exit 0；默认上下文下为 1 个 hunk（`grep -c '^@@'` = 1）。

逐行字节比对（读取 `git show 9075012:docs/CURRENT_STATE.md` 与 `git show d4b4b28:docs/CURRENT_STATE.md`）：

```text
base lines 49  target lines 49
differing 1-based line numbers: [19, 21]
frontmatter identical (lines 1-8): True
same total lines: True
```

即：仅第 19、21 行不同，frontmatter（第 1–8 行）与其余行逐字节未变。

两行新文本：

- 第 19 行：``发布基线：`v1.0.0` tag 指向 `f033a6c`；`dev/v1.0` 已领先该发布点，尚未发新版本。``
- 第 21 行：``测试门槛：默认运行与设置 `PROJECT_MEMORY_REQUIRE_OPENSSL=1` 运行均为 257 passed / 2 skipped（2 skipped 为既有 Windows 符号链接用例）。``

## 3. 新表述的事实核对（派单第 3 条）

### 3.1 `v1.0.0` 是 annotated tag 且指向 `f033a6c`

```bash
git cat-file -t v1.0.0          # → tag        （annotated，而非轻量 commit）
git rev-parse 'v1.0.0^{}'       # → f033a6c517cfde3eebb586b07f770d94b2d2c3b7
git cat-file -p v1.0.0          # → object f033a6c…, type commit, tagger PM-01 Supervisor …
git ls-remote --tags origin
# c96b871f7753c9a311d5884e33245e93cf8f48f1  refs/tags/v1.0.0
# f033a6c517cfde3eebb586b07f770d94b2d2c3b7  refs/tags/v1.0.0^{}
```

成立。tag 对象内 **无 PGP 签名块**（`grep -c "BEGIN PGP SIGNATURE"` = 0），与文档“未签名”一致。

### 3.2 `dev/v1.0` 头领先发布点且 `f033a6c` 为祖先

```bash
git rev-parse origin/dev/v1.0          # → 907501208383c35180e3a1f0dfc1d229854e1831
git cat-file -t f033a6c                # → commit
git merge-base --is-ancestor f033a6c 9075012   # → yes
git rev-list --count f033a6c..9075012  # → 21   （领先 21）
git rev-list --count 9075012..f033a6c  # → 0    （无落后）
```

成立：`dev/v1.0` 头 `9075012` 领先 `f033a6c` 21 个提交且无回退，`f033a6c` 是其祖先。

### 3.3 `257 passed / 2 skipped` 与本检出双门槛实测一致

见 §6：默认与 `PROJECT_MEMORY_REQUIRE_OPENSSL=1` 两条均为 `257 passed, 2 skipped`，exit 0。目标与基线之间仅文档/任务文件差异，代码与测试目录逐字节相同，故该计数对 `9075012` 与 `d4b4b28` 同样成立。

2 个 skip 的原因：

```bash
C:/SoftWare/Anconda/python.exe -m pytest tests/test_security_rc3.py -q -rs
# 18 passed, 2 skipped
# SKIPPED [1] tests\test_security_rc3.py:295: 当前平台不允许创建符号链接
# SKIPPED [1] tests\test_security_rc3.py:284: 当前平台不允许创建符号链接
```

源码中对应 `self.skipTest('当前平台不允许创建符号链接')`（`tests/test_security_rc3.py:291`、`:304`），与文档括注“既有 Windows 符号链接用例”一致。

### 3.4 仓库内没有比 `v1.0.0` 更新的 tag

```bash
git tag -l     # → v1.0.0（唯一）
git for-each-ref refs/tags --format='%(refname:short) | %(objecttype) | %(objectname:short) | %(taggerdate:iso)'
# v1.0.0 | tag | c96b871 | 2026-10-29 21:07:39 +0800
git ls-remote --tags origin   # 仅 refs/tags/v1.0.0 及其 ^{}
```

成立（tag 维度）。GitHub Release 未能只读核验，见 §10 NOT VERIFIED。

## 4. 审计多重集（派单第 4 条）

在 `base` 与 `target` 两个干净 worktree 各跑：

```bash
PROJECT_MEMORY_PYTHON=C:/SoftWare/Anconda/python.exe ./bin/project-memory audit --scope current
# 两侧均 exit 0
```

| 指标 | 基线 9075012 | 目标 d4b4b28 |
|---|---|---|
| 总数 | 40 | 40 |
| high | 0 | 0 |
| medium | 16 | 16 |
| low | 24 | 24 |
| 新增 | — | **0** |
| 减少 | — | **0** |
| `entry_doc_*` finding | 0 | 0 |

多重集按 `(severity, code, location)` 计数后排序（`severity\tcode\tlocation\tcount`，LF 连接）取 sha256：

```text
TARGET multiset sha256: 44e5f02b00b91df52a5e6ee81ffa1fbdd13f99d1257d71c65ef224f1f3b942c7
BASE   multiset sha256: 44e5f02b00b91df52a5e6ee81ffa1fbdd13f99d1257d71c65ef224f1f3b942c7
MULTISET EQUAL: True
added: 0  removed: 0
```

两侧 findings 多重集完全相同；`docs/CURRENT_STATE.md` 无 `entry_doc_*` finding。原始 JSON 文件 sha256 不同（`04c773b6…` vs `7a916e95…`）是可预期的：JSON 内嵌 `repo` 绝对路径不同，不影响 findings 多重集。

## 5. reconcile（派单第 5 条）

```bash
PROJECT_MEMORY_PYTHON=C:/SoftWare/Anconda/python.exe ./bin/project-memory reconcile --fail-on high
# EXIT=0
# state: needs_attention
# summary.defects: 0
# docs counts: {high: 0, medium: 16, low: 24}
```

`reconcile --fail-on high` exit 0。另，`audit --scope current`（默认 `--fail-on`）亦 exit 0，计数 40（0/16/24）。

## 6. 全量双门槛（派单第 6 条）

在 `target` worktree 内、仓库外解释器，现场执行：

| 门槛 | 结果 | 耗时 | 退出码 |
|---|---|---|---|
| 默认 `C:/SoftWare/Anconda/python.exe -m pytest -q` | `257 passed, 2 skipped` | 168.18s（墙钟 168s） | 0 |
| `PROJECT_MEMORY_REQUIRE_OPENSSL=1 … -m pytest -q` | `257 passed, 2 skipped` | 171.57s（墙钟 172s） | 0 |

两条均 exit 0，计数与文档第 21 行一致。

## 7. handoff 事实一致性（派单第 7 条）

逐条比对本轮实测：

| handoff 项 | handoff 声称 | 本轮实测 | 判定 |
|---|---|---|---|
| 文档变更提交 | `de3a480…` | 一致 | 符合 |
| 范围 numstat | `2 2 docs/CURRENT_STATE.md` | 一致（另 handoff +92/0） | 符合 |
| `-U0` hunk | 2 个；默认 1 个 | 一致（2 个 / 1 个） | 符合 |
| audit 计数 | 40，0/16/24，exit 0 | 一致 | 符合 |
| 基线对比 | 40，0/16/24，多重集相等，新增/减少 0 | 一致（独立复算） | 符合 |
| reconcile | exit 0，needs_attention，defects 0 | 一致 | 符合 |
| 双门槛 | 257/2，exit 0；192.62s / 167.97s | 257/2，exit 0；168.18s / 171.57s | 符合（耗时属环境差异） |
| 旧计数排查 | docs 无 253/255；ADR-0003 “190 passed” | 一致（`docs`/`README`/`CHANGELOG`/`skill` 均无 253/255） | 符合 |
| 推送状态 | 写文件时远端 tip 为 `de3a480`，handoff 稍后单独推送 | 当前远端 tip=`d4b4b28`（即 handoff 提交），父为 `de3a480` | 符合 |

未发现“自称未推送但远端已有”或“把未跑的东西写成已跑”这类偏差。handoff §8 对“`-U0` 不是单 hunk”的自我披露属实；§10 中“未验证 tag 为 annotated”“未逐条核对 skip 原因”两项，本轮已补验（annotated 且未签名；2 个 skip 均为符号链接用例）。

## 8. 不扩大范围（派单第 8 条）

- 变更行仅涉及发布基线与测试门槛两句，均与实测一致。
- 抽查其它“当前”表述：`docs/CURRENT_STATE.md` “已知限制”所述“40 条 findings（high 0 / medium 16 / low 24）”与本次审计一致；`docs/TEST_REPORT.md` 以“历史记录（v0.3 阶段）”自我标注并指向 `docs/CURRENT_STATE.md`，不与 257 计数冲突；`docs/decisions/ADR-0003…:174` 的“190 passed”为 ADR 历史表述。
- 未发现本次文档改动引入与实现不符的新表述。

## 9. 非阻断偏差

1. **handoff 多重集 sha256 不可独立复现**：handoff §3 给出 `2da9f558…`，但其声明的“`(code, location, severity)` + 计数排序”配合常见分隔/换行序列化均未得到该值。结论（两侧相等、新增/减少 0）已被本轮独立复算确认；该 sha 仅在特定序列化脚本下成立，建议 handoff 附上生成脚本或序列化口径。
2. **handoff 文件无末尾换行**：文件共 92 行（numstat +92 一致），最后一字节非 `\n`（`LF=91`）。纯格式小瑕疵，不影响内容。
3. **派单/卡面措辞**：派单括注“`-U0` 自证只有一个 hunk”在本布局下不成立（第 19、21 行间夹第 20 行，零上下文自然成 2 个 hunk；默认上下文为 1 个）。改动内容与 +2/−2 符合要求，属卡面措辞问题。
4. **语义提示（非本轮引入）**：文档标题为“当前状态（v1.0.0）”，而 257 计数对应 `dev/v1.0` 头（领先 tag 21 个提交）；`v1.0.0` tag 对象消息记录的是发布时的 253。新增第 19 行已区分 tag 与领先头，文档内部自洽；仅提示后续读者勿把 257 当作 tag 自身的发布计数。

## 10. 结论

**PASS。** 范围仅 `docs/CURRENT_STATE.md`（2/2，仅第 19、21 行）与 handoff（+92），无第三文件；正文逐行比对仅两行变化，frontmatter 与其余行逐字节未变；`v1.0.0` 确为 annotated、未签名、指向 `f033a6c`，`dev/v1.0` 领先 21 且 `f033a6c` 为祖先，仓库无更新 tag；审计两侧多重集完全相同（sha256 均为 `44e5f02b…`），40 条、0/16/24、新增 0/减少 0、`entry_doc_*` 为 0；`reconcile --fail-on high` 与默认 audit 均 exit 0；双门槛现场均 `257 passed, 2 skipped`、exit 0。handoff 事实与实测一致，偏差均为文档/卡面层面（§9），不阻断。

本报告仅为独立复核结论，不构成合并批准、发布批准或人类批准；合并、tag/Release 由 PM-01 与人类决定。

**NOT VERIFIED**

- GitHub Release：仓库为私有，未认证的 `api.github.com/.../releases` 返回 HTTP 404，无法只读核验是否另发 Release；tag 维度已用 `git ls-remote --tags` 确认为唯一 `v1.0.0`。
- PM-02 工作区残留状态（handoff §6 的两份未跟踪文件）：属另一克隆，未读取/未写入，无法核验。
- 提交者身份与签名：提交仅为身份声明，未做 GPG 验证。
- 未在 CI 或其它操作系统运行；仅本机 Windows 11 AMD64 独立 worktree。
- “证据包完整性检查 24/24”为基线既有文档表述，本轮未重跑证据包校验。
