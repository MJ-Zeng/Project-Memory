# B4 独立复核报告 — 审计与 Goal 状态可验证、防篡改

- 复核者：PM-03 独立审查者（独立会话 / 独立 worktree，未读开发或主管会话、终端历史、未提交文件）
- 复核日期：2026-10-29
- 运行 ID：`review-20261029T065012Z`
- 结论：**PASS（程序性独立复核，不是安全认证，不是 v1.0 GO）**
- 本报告只覆盖 B4；合并、Goal 生效与发布由人类决定。

---

## 1. 对象与身份

| 项 | 值 |
|---|---|
| 基线 | `f7c91333bbc999626e87eb29555b2c7c1ccb1a8f` |
| 实现提交 | `544b6d9b0cb59ad19b198b04d9f72e40b234005b`（`fix(b4): bind audit history to a hash chain and anchor achieved status`） |
| Candidate / PR head | `9fa14f853ed1fa8f473238ca1a0765b733711d65`（实现提交 + 1 个 docs 提交） |
| PR | https://github.com/MJ-Zeng/Project-Memory/pull/30 |
| 远端 `origin/fix/b4-audit-integrity` | `9fa14f853ed1fa8f473238ca1a0765b733711d65`（SSH 取回核对，一致） |
| 任务卡 `tasks/B4.md` SHA-256 | `3fcce10bb9b03293358a4beab40c0466bd3e40b59d7c0596d7fb8086d71649eb`（与派发值一致，候选未改） |
| 候选是否基线后代 | 是（`git merge-base --is-ancestor` 通过） |
| 分支 | `fix/b4-audit-integrity` → 复核分支 `review/b4-9fa14f8` |
| 证据包 | 开发：`evidence/B4/20261029T031257Z/`（22/22 自校验 OK）；复核：`evidence/B4/review-20261029T065012Z/` |

身份核对未发现不一致；候选不是基线后代、任务卡哈希不符之类的中止条件均未触发。

---

## 2. 上下文恢复（步骤 1）

按顺序只读了：`pilot/PILOT_CLOSEOUT.md` → `tasks/B4.md` → ADR-0007 → `tasks/B4-handoff-20261029T031257Z.md` → `tasks/B4-context-recovery.md` → `docs/OPERATIONS.zh-CN.md`（含 diff）→ PR #30（**无法读取**，见 §8）→ 证据 README → `coordination.py` / `authority.py` / `cli.py` / `tests/test_security_b4.py`。

**六项事实**

1. 基线、候选、任务卡哈希自洽；候选是基线后代；实现提交是候选的父提交，候选只多一个 docs/证据提交。
2. 两个原始缺口：`goal.status` 是可变 JSON；执行审计是无链 JSONL，且 `audit` 顶层命令是文档审计、没有执行账本 verify。
3. `authority.py` 只有验签路径（`load_anchor` / `_execution_record_authority`），**没有任何生成私钥或签名的代码**；checkpoint 必须由仓库外主体用 anchor 私钥签。
4. 真实解释器是 `C:/SoftWare/Anconda/python.exe`（3.12.4，pytest 9.1.1）；`python` 是 WindowsApps 别名（exit 49）；CLI 输出中文，需 `PYTHONIOENCODING=utf-8`；仓库**没有**任何 GitHub Actions workflow。
5. 既有不变量由 rc3/rc3 相关测试钉住：`status_consistent`、`status_authority=local_untrusted`（proposed 场景）、`recorded_status_consistent`、`goal_achieved_unsatisfied` 的 `reason` 字段；新增链字段只能附加。
6. B4 不得触碰 B5B 默认拒绝、B5A 原生包装器、B3 稳定判据摘要、B2 来源门禁。

**接手分钟数**：约 12 分钟（含 PR 访问受阻的排查）。

**必须询问的问题**（与开发提的一致，另加 1 条）

1. checkpoint 由谁、何时签？本实现假定“`transition_goal` 写 `head.request.json` → 仓库外 anchor 签名 → `audit checkpoint-attach` 只验签”。
2. 生产 anchor 是否接受“对 canonical JSON（`sort_keys`、compact separators、UTF-8、无尾随换行）字节签名”这一载荷约定？
3. `audit verify|head|migrate|checkpoint-*` 作为 `audit` 子命令、无子命令时保持原文档审计，是否可接受？
4. （新增）`evidence/** text eol=lf` 是否意图**追溯**作用于已有证据？它会让两个既有 B5B 二进制/CRLF 证据在 `git add` 时被重写（见 F-1）。

**Contamination**：无。本会话只读本 Clone / 本 worktree 与本地 ref；未读开发或主管会话、终端历史、未提交文件；未读 `/etc/pm-rc3-review/`；未使用 `project-memory-mvp`。

---

## 3. 逐条 AC 表（全部由本会话独立复现）

| AC | 判据 | 我的做法 | 观察（复核证据） | 结果 |
|---|---|---|---|---|
| AC-1 | 手改 status 不被信任 | 新建 Goal 后直接把 `goals/G-B4.json` 的 `status` 改为 `achieved`，跑 `goal show` / `evaluate` | `raw_status=achieved`、`effective_status=achieved_unverified`、`status_trusted=false`、problems=`goal_not_satisfied,audit_missing,checkpoint_missing,status_history_mismatch`；evaluate `satisfied=false`。另有“证据已满足但无 checkpoint”变体：`satisfied=true` 但 `effective_status=achieved_unverified`、problems=`checkpoint_missing,status_history_mismatch`、`recommendation=checkpoint_required` | **PASS** |
| AC-2 | 删中间行可检测 | 5 条链删第 2 条 | `invalid`，`seq_mismatch_at:2`，退出码 2 | **PASS** |
| AC-3 | 重写行可检测 | (a) 改字段不重算；(b) 只重算该行 `entry_hash` | (a) `entry_hash_mismatch_at:2`；(b) `prev_hash_mismatch_at:3`；均 `invalid` | **PASS** |
| AC-4 | 整链重建可检测 | 改第 3 条内容后重算**全部** `entry_hash`/`prev_hash`，链自洽、不更新 checkpoint | `chain_problems=[]` 但 `problems=[checkpoint_chain_mismatch]`、`valid=false`、`authoritative=false`；evaluate `satisfied=true` 但 `effective_status=achieved_unverified` | **PASS** |
| AC-4b | 截断为更短链 | 开发未留证，**由我构造两种**：(a) 直接截到前 3 行；(b) 截到前 3 行并重建自洽链 | 两者均 `invalid`、`checkpoint_chain_mismatch`、`effective_status=achieved_unverified` | **PASS** |
| AC-5 | 合法流程通过 | 真实执行收据 → 签名 attestation → 签名 verification → 证据 → 4 次 transition → 生成 checkpoint 请求 → 测试 RSA key 签名 → attach | attach 前 `valid_unanchored` / `achieved_unverified`；attach 后 `valid`、`authoritative=true`、`entries=5`、`checkpoint.chain_head==head`、`goal_id=G-B4`、`effective_status=achieved`、`status_trusted=true` | **PASS** |
| AC-6 | Agent 不能签 checkpoint | 三种尝试：签名文件缺失 / 用另一把未受信密钥签 / 不配置 anchor | 三种均 `PMError` 拒绝；`head.json` 不生成；Goal 保持 `achieved_unverified`、`status_trusted=false`；`project_memory/` 内无任何签名/生成私钥代码 | **PASS** |
| AC-7 | 空/缺审计不当通过 | 删 `.project-memory/audit` 目录；另建空 `verification_attempts.jsonl` | `invalid` + `audit_missing` / `audit_empty`；`effective_status=achieved_unverified` | **PASS** |
| AC-8 | 回归 | 候选树全量 `pytest tests/`，另在基线树跑对照 | 候选 **247 passed / 2 skipped**（exit 0）；基线 **233 passed / 2 skipped**；增量 14 = 新增 B4 测试数 | **PASS** |
| AC-9 | B5B/B5A/B3 不回归 | 定向跑 b5b/b5a/b3/b2/rc3 | **61 passed / 2 skipped**（exit 0），与开发自报一致 | **PASS** |
| AC-10 | ADR/文档 | 通读 ADR-0007 与 OPERATIONS 增补，对照实现 | 威胁模型、为何仅哈希不够、被拒方案、迁移/回滚、残余风险、AC 映射齐全且与实现一致；两处轻微文档与实现不符（F-3） | **PASS（附注）** |
| AC-11 | 证据 | 开发证据包 `sha256sum -c` 22/22 OK；我另建独立证据包 | `sha256sums.txt` 全 OK（`sha256sums.txt` 自身不在清单内，属正常） | **PASS** |
| AC-12 | 独立复核 | 本报告 | 篡改/删除/重建/截断/手改/空账本矩阵见 §4 | **PASS** |

附加（非 AC，任务卡要求说明）：

- **迁移**：旧无链账本 verify → `invalid` + `legacy_entries_without_chain`；`audit migrate` 后 → `valid_unanchored`、`authoritative=false`，写出 `verification_attempts.pre-chain.jsonl` 备份与 `migration.json`，迁移本身不被当信任锚。
- **换目标（重放）**：把已签名 checkpoint 对应的 Goal 换成另一个 id（签名不变），`effective_status=achieved_unverified`，problems 含 `checkpoint_goal_mismatch`。
- **前缀语义**：达成后追加一条审计，`audit verify` 仍 `valid`/`authoritative`，`effective_status` 仍 `achieved`（checkpoint 绑定 5 条前缀，当前 6 条）。
- **回滚**：删除 `head.json` → `achieved` 立即降级为 `achieved_unverified`。
- **reconcile**：新增 `achieved_goal_untrusted`（high），只在 raw `achieved` 且 `status_trusted is False` 时触发。

---

## 4. 篡改矩阵（独立复现）

| 场景 | 结果 | 具体位置/理由 | 证据 |
|---|---|---|---|
| 删中间行（5→4） | `invalid` | `seq_mismatch_at:2`，exit 2 | `tamper-delete.json` |
| 改字段不重算 | `invalid` | `entry_hash_mismatch_at:2` | `tamper-rewrite-field.json` |
| 只重算该行 hash | `invalid` | `prev_hash_mismatch_at:3` | `tamper-rewrite-hash.json` |
| 整链重建（自洽、同长度） | `invalid` | 链自洽但 `checkpoint_chain_mismatch` | `tamper-rebuild.json` |
| 截断（不重算） | `invalid` | `checkpoint_chain_mismatch`（`chain_length` 失配） | `tamper-truncate.json` |
| 截断并重建自洽短链 | `invalid` | `checkpoint_chain_mismatch` | `tamper-truncate.json` |
| 手改 Goal status（无证据） | 未生效 | `achieved_unverified` + 4 项 problems | `goal-status-edit.json` |
| 手改 Goal status（有证据） | 未生效 | `satisfied=true` 但 `achieved_unverified` | `goal-status-edit-with-evidence.json` |
| 删 checkpoint（回滚） | 未生效 | `checkpoint_missing` | `legitimate.json` 的 attach 前状态 |
| 换 Goal id 重放 | 未生效 | `checkpoint_goal_mismatch`、`checkpoint_evidence_mismatch` | `tamper-replay.json` |
| 空账本 | `invalid` | `audit_empty` | `tamper-empty.json` |
| 缺目录 | `invalid` | `audit_missing` | `tamper-missing.json` |
| 旧无链账本 | `invalid` | `legacy_entries_without_chain` | `migration.json` |
| **删除 checkpoint 之后的尾部行** | **未检测（已知残余风险）** | `valid`/`authoritative` 保持，`effective` 仍 `achieved` | `prefix-anchor.json` |

**链字段核对**：我用自己的实现（`json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=False)` → UTF-8 → SHA-256）对 5 条记录逐条复算，`seq`、`prev_hash`、`entry_hash` 全部吻合；首条 `prev_hash` 为 64 个 `0`；`entry_hash` 覆盖除自身外的**全部**字段（含 `seq`、`prev_hash`、`timestamp` 和所有原始字段）。这说明哈希算法是标准可复算的，外部验证器可独立重算。

`audit verify` 从 genesis 逐条遍历并在**第一处**断链处停下并报位置，不是只查最后一行（`coordination.py` 中 `_audit_chain` 的循环）。

---

## 5. checkpoint 前后缀行为与字段对照

| 观察 | 结果 |
|---|---|
| checkpoint 绑定字段 | `goal_id`、`status`、`chain_head`、`chain_length`、`at`、`approved_by`、`evidence_sha256`、`migration_sha256`（签名覆盖除 `authority` 外全部字段） |
| 前缀锚语义 | 绑定“截至 `chain_length` 的链头”；`anchored = entries[chain_length-1].entry_hash`，要求等于 `checkpoint.chain_head` |
| 达成后新增审计 | 6 条时 `valid`/`authoritative`，`checkpoint.chain_length=5`，`effective=achieved` |
| 前缀被改写/截短 | 失配 → `checkpoint_chain_mismatch` |
| 尾部（前缀之后）被删 | **仍 `valid`** —— 见 F-2（ADR §7.4 已披露） |
| 证据摘要 | 由 `goal_id` + 判据定义摘要 + 满足证据引用集合决定；改证据/判据 → `checkpoint_evidence_mismatch` |

**收据/派生字段对照**（消费方视角，`goal show` / `goal evaluate` JSON）

| 字段 | proposed（对照） | 手改 achieved（无证据） | 合法流程 |
|---|---|---|---|
| `raw_status` | `proposed` | `achieved` | `achieved` |
| `effective_status` | `proposed` | `achieved_unverified` | `achieved` |
| `status_trusted` | `null` | `false` | `true` |
| `status_problems` | `[]` | `goal_not_satisfied,audit_missing,checkpoint_missing,status_history_mismatch` | `[]` |
| `status_authority` | `local_untrusted` | `local_untrusted` | `anchor_signed_checkpoint` |
| `status_consistent` | `true` | `false` | `true` |

可信结论只能从 `effective_status`/`status_trusted` 得到；raw `status`/`goal_status` 仅作声明，代码里没有任何以 raw `status` 作为生效依据的路径。`effective_status=achieved` 需同时满足：raw `achieved` + `evaluate.satisfied` + 链完整非空 + checkpoint 验签通过 + `goal_id`/`status`/证据摘要/链前缀一致 + `history[-1].to == achieved`。

---

## 6. B5B / B5A / B2 / B3 回归（独立重跑）

| 项 | 结果 |
|---|---|
| `pytest tests/test_security_b5b.py tests/test_security_b5a.py tests/test_security_b3.py tests/test_security_b2.py tests/test_security_rc3.py -q -rs` | **61 passed, 2 skipped**，exit 0 |
| 2 个 skip 的原因 | `tests/test_security_rc3.py:284/295`：`当前平台不允许创建符号链接`（既有 Windows 限制，与 B4 无关） |
| B5B 默认拒绝 | 相关用例全绿；`--trusted` 的 WSL 用例未在 skip 列表 → 实际运行 |
| B5A 包装器 / B3 摘要 / B2 来源门禁 | 全绿；`project_memory/execution.py`、`trusted_exec.py`、`knowledge.py` 在本候选 diff 中**未改动** |
| 全量 | 候选 247/2；基线 233/2；skip 数与基线相同，无新增跳过 |

---

## 7. 新发现（按严重度）

### F-1（MEDIUM）`.gitattributes: evidence/** text eol=lf` 追溯作用于既有 B5B 证据，`git add` 会重写其字节并破坏已记录哈希

- 位置：`.gitattributes`（新增一行）。
- 事实：`evidence/B5B/run-20261029T015035Z/receipts/trusted/run.log` 与 `.../trusted-host-attempt/run.log` 是含 NUL/CRLF 的产物文件，且其哈希已被 `evidence/B5B/run-20261029T015035Z/sha256sums.txt` 固定（`d4b0a4e9…`、`2b999512…`，当前字节与清单一致）。
- 复现：在候选提交的干净检出上执行
  `git hash-object --path=<file> <file>` ≠ `git rev-parse HEAD:<file>`
  → 说明 `git add` 会把 CRLF 归一为 LF，字节改变、已记录 sha256 失效。
- 附带影响：这两个文件在候选检出中一旦 stat 变化就永久显示为 modified（内容其实与 HEAD 完全一致），容易诱导别人“顺手提交”而固化损坏。
- 判断：无运行时/安全影响，但会破坏 B5B 证据链的可复算性，且 `.gitattributes` 不在 `tasks/B4.md` §3 允许改动清单内（见 F-4）。建议改为 `evidence/B4/** text eol=lf`，或对二进制证据加 `-text`，或明确接受并重新登记 B5B 哈希。

### F-2（MEDIUM，已披露）checkpoint 前缀之后的尾部记录可被无成本删除

- 事实：完成 `achieved` 后再追加的审计行不在已签前缀内；把尾部行删掉，`audit verify` 仍 `valid`/`authoritative`、`effective_status` 仍 `achieved`（`prefix-anchor.json`），且**无需重算任何哈希**。
- 边界：`achieved` 转换本身在前缀内（删除它 → `chain_length` 失配被拒，已由 AC-4b 覆盖），所以不影响“达成”结论；受影响的是“达成之后发生了什么”的审计完整性。
- 判断：ADR §7.3/§7.4 已写明前缀锚的取舍与残余风险，属**已披露**取舍，不构成 AC 失败；但建议运维文档明确“前缀之后的记录只在下次 checkpoint 前受链链接保护”，并约定关键动作后再 checkpoint。

### F-3（LOW）ADR 与实现对非终态 `status_trusted` / `status_problems` 的描述不一致

- ADR §3.5 写：其它状态“为 true，但 `status_problems` 会标注‘非终态仅本地工作流声明’”。
- 实现：`raw != achieved` 时返回 `status_trusted=null`、`status_problems=[]`（我用 proposed Goal 实测）。
- 影响：方向更保守（`null` 不会被误当可信），无安全影响，但文档需与实现对齐。

### F-4（LOW）改动范围超出任务卡允许清单

- `tasks/B4.md` §3 允许：`coordination.py`、新的 audit helper、`authority.py`、`cli.py`、`tests/`、`docs/decisions/`、`docs/`、`evidence/B4/`。
- 实际还包括 `.gitattributes`、`tasks/B4-context-recovery.md`、`tasks/B4-handoff-*.md`（后两者是新文件，未改判据）。
- 与 `PILOT_CLOSEOUT.md` §8.3「允许路径要可执行」是同一个老问题；不阻断，但应在下一轮把 `tasks/` 交接件与 `.gitattributes` 写进允许清单或明确禁止。

### F-5（INFO）`audit checkpoint-request` 依赖进程内可读的 anchor

- 无 anchor 时 `evaluate` 不满足 → CLI 以 exit 1 拒绝生成请求（我实测）。这是正确的 fail-closed，但意味着该子命令的成功路径只能在配置了 anchor 的环境运行；OPERATIONS 未显式点出这层依赖。

### F-6（INFO）单写者假设未测

- `_append_audit_entry` 采用读全量→重算→原子替换；并发写者可能丢一条记录（链仍自洽）。ADR §7.7 已披露，本轮未构造并发用例。

---

## 8. 残余风险 / NOT VERIFIED

**NOT VERIFIED（本会话未运行或无法运行）**

1. **PR #30 的描述与评论未读**：本 Clone 无 GitHub API 凭据（`gh` 不存在，credential manager 无 `api.github.com` 条目，未认证 API 返回 404），与 `PILOT_CLOSEOUT.md` §7.7 一致。我用 SSH 核对了 `origin/fix/b4-audit-integrity` == `9fa14f8`，但 PR 正文/门禁评论需 PM-01 转述。**因此 §7 的分支头一致性成立，PR 级一致性未验证。**
2. **生产 anchor-a 端到端签名**：按要求未读生产密钥、未配置生产 anchor；全部签名用一次性测试 RSA key + 进程内 `authority.load_anchor` stub。
3. **真实 anchor 保护属性**（独立账户持有、ACL 不可写）：未用第二个真实主体部署验证。
4. **跨两个真实仓库的 checkpoint 重放**：用同仓库换 Goal id 近似验证（`checkpoint_goal_mismatch`），未做双仓库复制。
5. **并发写审计**：未测（F-6）。
6. **GitHub Actions / CI**：仓库不存在 workflow，全部本地验证。

**残余风险（属设计边界，非缺陷）**

- anchor 私钥被攻破 → 可签任意 checkpoint（ADR §7.1，与 ADR-0002/0003 同一边界）。
- 能重写 Git 历史的主体：本设计不把 Git 当锚（ADR §7.2）。
- 整体复制仓库：checkpoint 证明“这份历史被签过”，不证明“仓库未被整体复制”（ADR §7.3）。
- 前缀之后的追加记录（F-2）。
- 迁移前的旧审计删改不可检测（ADR §7.6）。
- 回滚到 B4 之前代码会失去 B4 保证（ADR §4.3，需在发布说明标注）。

---

## 9. 与开发自报的差异

| 项 | 开发自报 | 复核观察 |
|---|---|---|
| 全量测试 | 247 passed / 2 skipped | **一致**（基线对照 233/2，增量恰为 14 个 B4 测试） |
| 回归子集 | 61 passed / 2 skipped | **一致** |
| B4 测试数 | 14 | **一致**（文件里另有一个 `def test_ok` 在 fixture 字符串内，不是测试） |
| AC-1 problems | 含 4 项 | **一致**（复现完全相同） |
| AC-2/3 位置 | `seq_mismatch_at:2`、`entry_hash_mismatch_at:2`、`prev_hash_mismatch_at:3` | **一致** |
| AC-4 | `checkpoint_chain_mismatch` | **一致** |
| AC-5 | `valid`、`authoritative=true`、长度 5 | **一致**（head 值因时间戳不同而不同，属正常） |
| AC-6 | 三种均拒 | **一致** |
| AC-7 | `audit_missing` / `audit_empty` | **一致** |
| AC-4b 截断 | 声明 NOT VERIFIED、未留证 | **我补做**：截断与“截断+重建”均被拒 → PASS |
| 证据清单 | 单个 `tamper-rewrite.json`、cli 3 个用例 | 我将改写拆成 field/hash 两文件，并补充 head/migrate/checkpoint-request/checkpoint-attach 的退出码 |
| `.gitattributes` | “只影响证据换行，未改运行时行为” | 运行时确实未变，但**追溯影响既有 B5B 证据**（F-1），自报未提 |
| PR/CI | 未创建、未运行 | 一致（仓库无 workflow；我无法读 PR） |

未发现开发把未运行项写成 PASS 的情况；handoff 的 NOT VERIFIED 清单与我的观察吻合。

---

## 10. 最终判定

**PASS**（B4 范围内、程序性独立复核）。

理由：

- AC-1..AC-12 全部独立满足：删行/改字段/重算单行/整链重建/截断/空账本/缺目录/手改 status/换目标全部被拒；合法流程通过；Agent 无法签 checkpoint；raw `status` 不被信任。
- 全量 247 passed / 2 skipped（skip 为既有 Windows 符号链接限制），基线 233/2；B5B/B5A/B2/B3 定向 61 passed / 2 skipped，无回归、无删测、无跳过、无放宽门禁。
- 防作弊判据 1–7 均未触发：有 `audit verify` 且逐条复算；空链不通过；无 Agent 签名路径；`status` 不再被信任；未删/跳测试；未放宽 B5B/B5A/B2。

不影响 PASS 但需跟进：**F-1（MEDIUM，`.gitattributes` 追溯归一化既有 B5B 证据）** 建议在合并前后单独修正；F-2 属已披露取舍，建议补一句运维说明；F-3 文档对齐；F-4 允许清单补充。

本 PASS 不覆盖：生产 anchor 端到端、PR 正文一致性、Release/部署、人类身份与审批，**也不构成 v1.0 GO**。

---

## 11. 污染 / 偏差 / 耗时

- **污染**：无（只读本 Clone/worktree 与本地 ref；未读开发/主管会话、终端历史、未提交文件；未读生产密钥）。
- **偏差**：
  1. PR #30 正文/评论无法读取（无凭据），改用 SSH 核对分支头；报告 §8 已标注。
  2. 在复核 worktree 跑测试后，两个 B5B 证据文件因 F-1 的属性规则显示为 modified（内容与 HEAD 逐字节一致，已在干净检出上复核确认与测试执行无关）；提交时只 `git add` 复核自有路径，**未提交这两个文件**。
  3. 场景探针复用 B2/B3 已有的“签名 verification 记录”构造方式以获得 `satisfied=true`（这是 B2/B3 门禁，不是 B4 被测逻辑）。
- **耗时**：上下文恢复约 12 分钟；静态审查约 40 分钟；动态复现与证据整理约 35 分钟。

## 12. 复核证据索引

`evidence/B4/review-20261029T065012Z/`

```text
environment.txt  diffstat.txt  commands.jsonl  summary.json
chain/                      # 我构造的合法链：entries / head.json / head.request.json
legitimate.json  consumer-view.json  prefix-anchor.json
goal-status-edit.json  goal-status-edit-with-evidence.json
tamper-delete.json  tamper-rewrite-field.json  tamper-rewrite-hash.json
tamper-rebuild.json  tamper-truncate.json  tamper-replay.json
tamper-empty.json  tamper-missing.json
agent-checkpoint-attempts.json  cli-compat.json  migration.json  reconcile.json
pytest.log  regression.log
review_probe.py             # 复核者自写探针（非开发 probe.py）
sha256sums.txt
```
