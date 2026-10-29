# R1 独立审查报告 — PM-03（第二次独立复核）

- 审查者：PM-03（独立会话）
- 日期：2026-10-29
- 性质：**第二次独立复核**，确认第一次审查（commit `9d30611`，证据 `review-20261029T102343Z/`）的结论
- 对象：PR #32 / 候选 `bb06037c469b6586b95fbcd69b6965585f2c977e`
- 基线：`85bf6a05542aa6bca3ab0d9ef51c6216f76b6080`（B4 合并）
- 任务卡：`tasks/R1.md`，SHA-256 `5949420f784feeb1484c8b8465cec40e7646931d5ff6c0a6af865113f13131f1`
- 审查分支：`review/r1-bb06037`
- 本轮证据目录：`evidence/R1/review-20261029T101815Z/`

---

## 1. 上下文恢复（6 项事实）

1. **候选与基线关系**：`bb06037` 是 `85bf6a0` 的后代（`git merge-base --is-ancestor` 通过）；任务卡哈希与提交 `cf0da82` 一致，未被修改。
2. **空必达问题**：`evaluate_goal` 在 `required=[]` 时返回 `satisfied=true`（`all([])` 真空真），且 `transition --to achieved` 允许通过；B4 的派生状态使其为 `achieved_unverified`，但 evaluator 本身仍误导只看 `satisfied` 的调用方。
3. **openssl 问题**：缺失 openssl 时 37 个签名测试静默 skip、套件 exit 0；发布流程需显式开关让 skip 变 fail。
4. **契约漂移**：架构文档写 19 份 schema，实际 21 份；verification schema 未说明 `goal_criteria_sha256` 语义；缺 B4 audit/checkpoint schema。
5. **证据与版本**：B5B 证据清单混用行尾（19 LF / 22 CRLF / 1 neither）；版本仍 `0.1.0`，无 CHANGELOG。
6. **R1 修复**：空必达结构化失败（`no_required_criteria` 字段）；openssl 开关仅测试层；版本升 `1.0.0`；新增 audit-ledger schema；B5B 证据只读说明。

接手分钟数：约 15 分钟（读 precheck、任务卡、handoff、核心代码、文档）。

必须询问的问题：无（任务卡与代码已自洽）。

污染：无（未读开发/主管会话；未修改候选代码；未使用生产私钥）。

---

## 2. 逐条 AC 表

| AC | 判据 | 实测 | 状态 |
|---|---|---|---|
| AC-1 | 空必达 evaluate fail closed | 路径 A/B：`satisfied=false`、`evaluation_status=insufficient_evidence`、`no_required_criteria=true`、exit 0 | PASS |
| AC-2 | 空必达不能 achieved | 路径 A/B：`transition --to achieved` exit 1、Goal 仍 `evaluating`、无 `head.request.json`、审计新增 `outcome=rejected`、`reason=goal_achieved_unsatisfied`、`no_required_criteria=true` | PASS |
| AC-3 | show 仍可读且不误导 | 路径 A/B：`goal show` exit 0、`status_problems=['no_required_criteria']`、`effective_status=evaluating`（非 achieved） | PASS |
| AC-4 | 创建约束未放宽 | `goal create` 无 `--criterion` exit 1，错误含"必达的成功标准" | PASS |
| AC-5 | openssl 缺失 + 开关 → fail | `PATH=System32 PROJECT_MEMORY_REQUIRE_OPENSSL=1 pytest b2 b3 b4`：37 errors、exit 1、消息含 `openssl` 与 `PROJECT_MEMORY_REQUIRE_OPENSSL` | PASS |
| AC-6 | 默认行为不变 / 有 openssl 正常 | 缺省 + 无 openssl：37 skipped、exit 0；有 openssl：两种设置均 37 passed、exit 0 | PASS |
| AC-7 | openssl 文档 | `README.md`、`docs/OPERATIONS.zh-CN.md` 写明开关、发布/CI 必须设置、skip 不等于通过；未新增运行时依赖 | PASS |
| AC-8 | fixtures README | `fixtures/b5b/README.md` 说明 marker 脚本、宿主 marker、默认拒绝/双 flag/显式 local/trusted/不可用用例、WSL2 依赖；与 `test_security_b5b.py` 行为一致 | PASS |
| AC-9 | B5B 证据说明 | `evidence/B5B/README.md` 记录混合行尾、NUL 日志、逐文件字节校验方法；明确不重写历史证据 | PASS |
| AC-10 | 契约同步 | 架构文档 §5 计数 21；verification schema 补 `goal_criteria_sha256` 描述；新增 `audit-ledger.schema.json`；schema 样例校验 0 problem(s) | PASS |
| AC-11 | 版本与 CHANGELOG | `pyproject.toml`、`__init__.py` 均为 `1.0.0`；CHANGELOG 覆盖 B0–B4、B5A、B5B、H1、已知边界、安装、回滚；未打 tag | PASS |
| AC-12 | 回归 | 默认：253 passed, 2 skipped（rc3 符号链接）；开关：同；定向：57 passed | PASS |
| AC-13 | 证据与交接 | `evidence/R1/20261029T083252Z/` 命令、退出码、JSON、日志、diffstat、sha256sums 齐备；未代下结论 | PASS |

---

## 3. #19 矩阵

| 路径 | evaluate | show | transition | create |
|---|---|---|---|---|
| A（required=false） | exit 0, satisfied=false, no_required_criteria=true, status_problems=['no_required_criteria'], effective_status=evaluating | exit 0, readable, status_problems=['no_required_criteria'], effective_status=evaluating | exit 1, goal stays evaluating, no checkpoint request, audit entry with outcome=rejected, reason=goal_achieved_unsatisfied, no_required_criteria=true | N/A |
| B（删除全部 required） | 同 A | 同 A | 同 A | N/A |
| 控制（有 required 但未满足） | exit 2, satisfied=false, no_required_criteria=false | — | — | — |
| 无 --criterion | — | — | — | exit 1, error: 必达的成功标准 |

矩阵完整覆盖任务卡 4.1/4.2 与 AC-1..AC-4。

---

## 4. openssl 矩阵

| 场景 | b2/b3/b4 结果 | exit |
|---|---|---|
| 缺 openssl + 默认 | 37 skipped | 0 |
| 缺 openssl + `PROJECT_MEMORY_REQUIRE_OPENSSL=1` | 37 errors | 1 |
| 有 openssl + 默认 | 37 passed | 0 |
| 有 openssl + `PROJECT_MEMORY_REQUIRE_OPENSSL=1` | 37 passed | 0 |

开关双向正确；消息同时含 `openssl` 与 `PROJECT_MEMORY_REQUIRE_OPENSSL`。

---

## 5. 契约核对

- **schema 计数**：架构文档 §5 写 21 份，实际 `skill/project-memory/assets/` 有 21 份 `.schema.json`（含新增 `audit-ledger.schema.json`）。一致。
- **`goal_criteria_sha256` 语义**：verification schema 补描述，说明覆盖判据定义（`id`/`statement`/`required`），不含 `evidence`；旧格式兼容（ADR-0004）。与代码 `_criteria_definition_digest` 一致。
- **audit-ledger schema**：`oneOf` 审计条目 / checkpoint；字段与真实输出一致（`schema_version=1.3`、`kind=verification_attempt`/`audit_checkpoint`、`seq`/`prev_hash`/`entry_hash`、`checkpoint_id`/`goal_id`/`status`/`chain_head`/`chain_length`/`at`/`approved_by`/`evidence_sha256`/`migration_sha256`/`authority`）。`tracked_changes` 为字符串（`git status --porcelain` 原文），schema 已修正。
- **schema 样例校验**：5 条 B4 审计条目 + 1 条 R1 拒绝条目 + 2 条 checkpoint 全部通过 Draft 2020-12 校验，0 problem(s)。

---

## 6. 历史证据检查

- **R1 证据清单**：`evidence/R1/20261029T083252Z/sha256sums.txt` 经 `tr -d '\r' | sha256sum -c` 验证，全部 OK。
- **add 不重写字节**：`git hash-object --path=<p> <p>` 与 `git rev-parse HEAD:<p>` 逐文件比对 `evidence/R1/**`，全部一致；`.gitattributes` 的 `evidence/R1/** text eol=lf` 未触发字节改写。
- **B5B 未改**：`git diff --name-status 85bf6a0..bb06037 -- evidence/B5B/` 仅新增 `README.md`，既有文件未动。
- **B5B README 校验法**：实测 `evidence/B5B/run-20261029T015035Z/README.md` 的逐文件字节校验方法，LF 归一化后与清单哈希匹配；工作树字节因 `core.autocrlf=true` 检出变换而不匹配，但 README 已说明此差异并给出正确做法。

---

## 7. 文档可执行性

- **openssl 命令**：`README.md` 与 `OPERATIONS.zh-CN.md` 的 `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python3 -m pytest -q` 按原样执行，exit 1（缺 openssl）或 0（有 openssl）。
- **fixtures/b5b/README.md**：命令与用例与 `test_security_b5b.py` 实际行为一致（默认拒绝 exit 3、双 flag 拒绝、显式 local exit 0、trusted 沙箱路径 exit 0、trusted 宿主路径失败、trusted 不可用 exit 3 BLOCKED 不回退）。

---

## 8. 回归结果

- **默认全量**：253 passed, 2 skipped（`test_security_rc3.py:284/295` 符号链接用例），exit 0。
- **开关全量**：253 passed, 2 skipped，exit 0。
- **定向回归**：`test_security_b5b.py b5a.py b3.py b2.py b4.py` 57 passed，exit 0。
- **2 个 skip 来源**：rc3 符号链接用例（平台限制），非签名测试。

---

## 9. 新发现

无高危发现。低严重度观察：

1. **`evaluate_goal` 语义微调**：当 `no_required_criteria` 与 `open_high` 同时存在时，`state` 从 `blocked_by_defect` 变为 `insufficient_evidence`。两者均 fail closed，不影响安全语义，但可能影响下游对 `evaluation_status` 的分类统计。
2. **未使用 import**：`tests/test_security_b2.py` 与 `test_security_b3.py` 的 `import shutil` 在 R1 改动后未使用（b4 仍用）。无功能影响，属 lint 问题。
3. **PR #32 描述不可得**：本会话无 `gh` 且 WebFetch 返回 404（私有仓库），PR 描述未读取；审查完全基于候选代码、任务卡与 handoff。

---

## 10. 残余风险 / NOT VERIFIED

- **生产 anchor 端到端签名**：未在本仓库内验证 `anchor-a` 的真实签名流程（测试使用测试密钥并 patch `authority.load_anchor`）。
- **POSIX 实装**：未验证 Linux/macOS 上的 `pip install` 与 openssl 开关行为（仅 Windows）。
- **真实第二主体 ACL**：未验证跨主体的 Goal 审批与 checkpoint 签名。
- **PR #32 描述**：未读取（私有仓库 404）。

以上均为任务卡明示不在范围的项，不影响 R1 PASS 判定。

---

## 11. 与开发自报的差异

- **AC-6 计数**：任务卡写"82 passed"，实测 b2/b3/b4 共 37 项（b2=13、b3=10、b4=14）。开发 handoff 已披露此差异并按实测记录。
- **B5B 行尾**：任务卡观测 19 LF / 22 CRLF / 1 neither；开发 handoff 记录 worktree 42 CRLF、git blob 42 LF、29/42 直接匹配、17/42 LF 归一化后匹配。差异来自 `core.autocrlf=true` 的检出变换，开发已说明。
- **evaluate 退出码特例**：空必达返回 0 是 AC-1 明确要求；开发已说明既有测试依赖"普通未满足返回 2"，因此仅对 `no_required_criteria` 走 0。

无实质性差异；开发自报与实测一致。

---

## 12. 最终判定

**VERDICT: PASS**

空必达两条路径均 fail closed（evaluate/show/transition 一致）；创建约束未放宽；openssl 双向正确；契约与实现一致；历史证据未改；253+ 测试全绿；无新高危。

本判定是程序性独立复核，不是安全认证，不是 v1.0 GO；合并由人类决定。

---

## 13. 污染 / 偏差 / 接手耗时

- **污染**：无（未读开发/主管会话；未修改候选代码；未使用生产私钥）。
- **偏差**：PR #32 描述未读取（私有仓库 404）。
- **接手耗时**：约 15 分钟（上下文恢复）+ 约 45 分钟（静态检查与动态复现）= 约 60 分钟。
