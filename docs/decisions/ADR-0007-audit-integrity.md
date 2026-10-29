# ADR-0007：审计账本与 Goal 状态的可验证性（B4）

- 状态：`proposed`（Agent 起草；接受需人类批准，见 `docs/decisions/README.md`）
- 日期：2026-10-29
- 任务：B4（Issue #28）
- 基线：`f7c91333bbc999626e87eb29555b2c7c1ccb1a8f`
- 影响范围：`project_memory/coordination.py`（`_audit_attempt`、`goal_show`、`evaluate_goal`、`transition_goal`、新增账本/ checkpoint helper）、`project_memory/authority.py`（新增通用“记录签名信封”校验入口，复用现有 in-process 验签）、`project_memory/cli.py`（`audit verify`/`audit head`/`audit migrate`/`audit checkpoint-request`/`audit checkpoint-attach`）、`tests/test_security_b4.py`（新增）、`docs/` 运维说明、`evidence/B4/`、本文档
- 不涉及：B5B 默认拒绝、B5A 原生包装器、B3 稳定判据摘要、B2 来源门禁、Release/部署、人类身份认证、外部不可变存储

## 1. 背景与实测缺口

### 1.1 Goal 状态是可变 JSON

`goal.status` 直接写在 `.project-memory/goals/G-*.json`。把 `status` 手改为 `achieved` 后：

- `goal_show` 原样返回 `goal.status == "achieved"`，只附带 `status_consistent=false`；
- `evaluate_goal` 返回 `satisfied=false`、`recorded_status_consistent=false`，但没有“有效状态”字段；
- 消费方（脚本、看板、下一个 Agent）读取 `status` 就会把本地声明当成达成事实。

### 1.2 执行审计不是账本

`_audit_attempt` 只向 `.project-memory/audit/verification_attempts.jsonl` 追加普通 JSON：

- 没有 `prev_hash`/`entry_hash`，没有链头；
- 删除一行、重写一行、整文件重建都无法检测；
- 顶层 `audit` 命令是**文档元数据审计**，不存在执行账本 `audit verify`；
- 关键转换 `achieved` 没有签名或外部锚，无法证明“这条历史没有被重建”。

## 2. 威胁模型

| # | 威胁 | 能力 | 本 ADR 的目标 |
|---|---|---|---|
| T1 | 本地手改 | 能改 `.project-memory/` 下任意 JSON/JSONL | 手改 Goal status、删/改/重建审计必须被检测；`achieved` 不得生效 |
| T2 | 重算整条链 | 知道链算法，可重写所有 `prev_hash`/`entry_hash` | 纯 hash 链不够；必须由仓库外 anchor 签名 checkpoint 锚定链头 |
| T3 | Agent 自动写 | Agent 能运行任何 CLI 命令、写仓库内文件 | 仓库内没有任何“生成有效 checkpoint”的代码路径；Agent 无私钥 |
| T4 | 删除审计 | 删除文件或整个目录 | 缺文件/空文件不得 verify 通过，`achieved` 不得生效 |
| T5 | checkpoint 重放 | 复制旧 checkpoint 到新仓库/新链 | checkpoint 绑定 goal id、状态、链长度、链头、证据摘要、迁移摘要；不匹配即拒绝 |
| T6 | root/私钥被攻破 | 可签任意记录、可改 anchor | **不防御**。与 ADR-0002/0003 一致：信任根被攻破后一切签名保证失效；只能靠仓库外审计与轮换 |
| T7 | 重写 Git 历史 | 可改写仓库历史、伪造 commit/tag | 外部锚若只依赖 Git 历史，则不可信；本设计不把 Git commit/tag 当作唯一锚（见 §4） |

### 2.1 为什么只加 hash 不够

Hash 链只能检测**不知道算法或懒得重算**的修改。T2 的攻击者可以：

1. 删除/改写的条目之后，重算所有 `entry_hash`；
2. 修正后续条目的 `prev_hash`；
3. 得到一条“自洽”的链。

因此必须引入**仓库内无法伪造的锚**：由仓库外受保护主体（anchor/人类）签名的 checkpoint，或真正不可变的外部存储。B4 选择签名 checkpoint（可选叠加 Git 外部锚）。

## 3. 决策

选择任务卡 §4 的**方案 1 + 方案 3 组合**：

1. **Hash 链**：每条审计条目写 `seq`、`prev_hash`、`entry_hash`；`audit verify` 从 genesis 重算；
2. **签名 checkpoint**：关键转换（本轮为 `achieved`）由 anchor 签署 `audit/head.json`，绑定链头、链长度、goal、状态、时间、证据摘要、迁移摘要；
3. **派生 Goal 状态**：`goal_show`/`evaluate_goal` 返回 `effective_status`/`status_trusted`/`status_problems`，raw `status` 只作声明；
4. **外部锚（可选）**：运维文档说明可把 `audit head` 写入受保护的 Git tag/PR 作为第二锚；本轮不自动实现，不把 Git 当唯一锚。

不选纯方案 2（只用 Git commit/tag）的原因：本试点同一 OS 用户/同一账号，Agent 技术上可改写分支历史或创建提交；Git 历史不是不可变外部存储，单独使用会在 T7 下失效。

### 3.1 审计条目格式

```json
{
  "schema_version": "1.3",
  "kind": "verification_attempt",
  "seq": 7,
  "timestamp": "2026-10-29T...Z",
  "prev_hash": "<前一条 entry_hash 或 64 个 0>",
  "entry_hash": "<sha256(canonical(条目去掉 entry_hash))>",
  "...": "原有字段保持不变"
}
```

- `genesis = "0" * 64`；
- `entry_hash = sha256(canonical_json(entry without entry_hash))`，canonical 与 `authority.canonical_bytes` 一致（`sort_keys=True`、无多余空白、UTF-8）；
- `seq` 从 1 连续递增；断号即失败；
- 追加采用“读全量 → 重算链尾 → 原子替换”，不原地 append，避免半行/并发错位；
- 保留原有字段与顺序语义；新增字段只追加，不删除既有字段。

### 3.2 `audit verify`

从 genesis 重算并输出：

```json
{
  "kind": "audit_chain_verification",
  "status": "valid | valid_unanchored | invalid",
  "valid": true,
  "authoritative": false,
  "entries": 7,
  "head": "<sha>",
  "checkpoint": {"present": true, "trusted": true, "matches": true, "..." : "..."},
  "migration": null,
  "problems": []
}
```

- `valid`：链完整、条目哈希/链接/序号全部正确，且（若存在 checkpoint）checkpoint 可信并与链一致；
- `valid_unanchored`：链完整但无 checkpoint。**不是**权威；不能支撑 `achieved`；
- `authoritative`：`valid` 且 checkpoint 存在、anchor 验签通过、且绑定字段与当前链/Goal 一致；
- 缺文件、空文件、只有空行 → `invalid`（T4）；
- 旧格式（无 `entry_hash`）未迁移 → `invalid`，提示 `audit migrate`。

`audit verify` 退出码：`valid`/`valid_unanchored` 为 0；`invalid` 为 2。权威性用 JSON 字段表达，不用“退出码 0”冒充权威。

### 3.3 签名 checkpoint

位置：`.project-memory/audit/head.json`。载荷（签名覆盖除 `authority` 外的全部字段）：

```json
{
  "schema_version": "1.3",
  "kind": "audit_checkpoint",
  "checkpoint_id": "CKPT-<...>",
  "goal_id": "G-B4",
  "status": "achieved",
  "chain_head": "<sha>",
  "chain_length": 7,
  "at": "2026-10-29T...Z",
  "approved_by": "reviewer@example.com",
  "evidence_sha256": "<sha>",
  "migration_sha256": null,
  "authority": {"anchor_id": "...", "issuer": "...", "algorithm": "rsa-sha256",
                "signed_payload_sha256": "...", "signature_b64": "..."}
}
```

- **谁签**：仓库外持有 anchor 私钥的人类/PM-01（与 B2/B3 的验证记录签名同一信任根）；Agent 无私钥；
- **绑定字段**：`goal_id`、`status`、`chain_head`、`chain_length`、`at`、`approved_by`、`evidence_sha256`、`migration_sha256`；
- **链头是前缀锚**：checkpoint 绑定“截至 `chain_length` 的链头”。之后追加的审计条目不会让已签 checkpoint 失效（仍可验证前缀），但**删除/改写前缀内条目**或**截断到更短链**会被检测；重建整条链（长度/链头变化）也会失败；
- **为什么不用“最新链头”**：达成之后仍会有新的验证尝试/审计追加；若要求“最新 head 完全相等”，任何后续日志都会把 `achieved` 打回未验证，产生误伤。前缀锚是标准取舍，残余风险见 §7。

### 3.4 生成与签署流程（Agent 不能自动签）

```text
goal transition --id G-B4 --to achieved --approved-by human@example.com
  → 追加审计条目（outcome=applied, from=evaluating, to=achieved）
  → 写 .project-memory/audit/head.request.json（canonical JSON，无 authority，未签名）
  → 返回 checkpoint_request（含 payload sha256）

外部签名者（anchor 私钥，仓库外）：
  openssl dgst -sha256 -sign <anchor.key> \
      -out head.sig .project-memory/audit/head.request.json

project-memory audit checkpoint-attach --signature head.sig
  → 用 anchor 公钥在进程内验签（不调用外部 openssl）
  → 验签失败 / 未配置 anchor → PMError（拒绝）
  → 成功 → 原子写 audit/head.json
```

- `checkpoint-attach` 只接受**已存在的有效签名**；它不生成密钥、不签名、不接受自报 `status=trusted`；
- 测试用测试 RSA key + patch `authority.load_anchor`，与 B2 相同；生产 key 不入库、本会话不读；
- `audit checkpoint-request --goal` 可为“先有历史、后补 checkpoint”的仓库重新生成请求。

### 3.5 派生 Goal 状态

`evaluate_goal` 与 `goal_show` 新增：

| 字段 | 语义 |
|---|---|
| `effective_status` | 消费方应使用的状态。`achieved` 仅在全部锚定条件满足时出现；否则若 raw 为 `achieved` 则为 `achieved_unverified` |
| `status_trusted` | 布尔。`achieved` 为 true 当且仅当锚定条件全部满足；其它状态无 B4 锚定要求，为 true，但 `status_problems` 会标注“非终态仅本地工作流声明” |
| `status_problems` | 不满足原因数组（如 `goal_not_satisfied`、`audit_missing`、`audit_chain_invalid`、`checkpoint_missing`、`checkpoint_untrusted`、`checkpoint_goal_mismatch`、`checkpoint_chain_mismatch`、`checkpoint_evidence_mismatch`、`status_history_mismatch`） |

`achieved` 的锚定条件：

1. raw `status == "achieved"`；
2. `evaluate_goal.satisfied == true`（证据/判据/来源门禁全部通过）；
3. `audit verify` 为 `valid`（链完整且非空）；
4. `head.json` 存在、anchor 验签通过；
5. checkpoint 的 `goal_id`/`status`/`chain_head`/`chain_length` 与当前链一致，`evidence_sha256` 与当前证据摘要一致，`migration_sha256` 与当前迁移摘要一致；
6. `history` 最后一条 `to` 等于 raw `status`（检测“只改 status 不改 history”的朴素手改；可被同时改写 history 的高级攻击绕过，见 §7）。

`recorded_status_consistent` 保留 B3/RC3 语义（`status != achieved or satisfied`），新增字段不改变既有字段。`status_consistent` 仍取 `recorded_status_consistent`，避免破坏既有消费方；但文档要求消费方改用 `effective_status`/`status_trusted`。

### 3.6 证据摘要与迁移摘要

```text
evidence_sha256 = sha256(canonical({
  "goal_id": ...,
  "criteria_definition_sha256": <稳定判据摘要>,
  "satisfying": [{"criterion_id": ..., "kind": ..., "ref": ...}, ...]  # 按 criterion id 排序
}))
```

- 只纳入“当时被判定 satisfied 的证据引用”，不纳入后来追加的普通证据；
- 判据定义变化、满足证据被替换/删除、验证记录失效导致不再 satisfied → 摘要变化 → checkpoint 不匹配；
- `migration_sha256`：若有 `audit/migration.json`，取其 `source_sha256`；否则 null。

### 3.7 `achieved` 的 `evaluate` 返回值

即使 raw `achieved` 且证据 satisfied，只要 checkpoint 无效，`evaluate_goal` 仍返回 `satisfied=true`（这是“证据是否支持成功标准”的独立判断），但 `effective_status="achieved_unverified"`、`status_trusted=false`、`status_problems` 列出缺失项，且 `recommendation` 改为 `checkpoint_required`。这样：

- 不把“证据成立”与“状态生效”混为一谈；
- 消费方若只看 `satisfied` 会看到 true，但 `status_trusted=false` 与 `effective_status` 明确阻止把 Goal 当作已达成；
- AC-1（无证据手改）仍 `satisfied=false`。

## 4. 空/缺审计与旧数据迁移

### 4.1 空/缺审计

- `audit verify`：文件不存在/为空/只有空白 → `invalid`，`problems=["audit_missing"|"audit_empty"]`；
- `evaluate_goal`：raw `achieved` → `status_problems` 含 `audit_missing`/`audit_empty`，`effective_status="achieved_unverified"`；
- 绝不允许“空链视为通过”，也不允许“无审计 = 没有坏消息 = achieved”。

### 4.2 旧审计（pre-1.3，无 hash）

- `audit migrate`：读取旧 JSONL，按当前顺序计算 `seq/prev_hash/entry_hash`，原子重写主文件；原文件复制为 `verification_attempts.pre-chain.jsonl`（不覆盖已存在副本）；写 `audit/migration.json`（`source_sha256`、`head`、`entries`、`at`）；
- 迁移本身是**普通写入**，不产生信任；迁移后的链是 `valid_unanchored`，只有 anchor 签名的 checkpoint 才能使其权威；
- `_audit_attempt` 遇到旧格式会自动调用同一迁移逻辑后再追加（保证运行不中断），并在返回/日志中记录迁移；
- 旧审计在迁移前被删改无法事后检测——这是 legacy 无链的固有边界，必须在发布说明中写明。

### 4.3 回滚

- 回滚到 B4 之前的代码：旧代码忽略新增字段，仍能读取链式 JSONL（字段向前兼容）；但旧代码不会验证链，`achieved` 会重新变成“仅本地声明”。因此回滚必须在发布说明中标注“失去 B4 保证”，并优先前滚修复；
- 回滚审计文件到迁移前副本：链验证失败（若已有 checkpoint）或变为 `valid_unanchored`；不会静默恢复信任；
- 删除 `head.json`：`achieved` 立即降级为 `achieved_unverified`；审计链本身仍可验证但非权威。

## 5. 实现不变量

1. `_audit_attempt` 只追加带链字段的条目；任何写失败不产生半条记录（原子替换）。
2. `audit verify` 从 genesis 重算**每一条**，不只检查最后一行。
3. 空/缺审计 → `invalid`；绝不返回“空链通过”。
4. 仓库内没有签名函数；`checkpoint-attach` 只验签，不接受自报 trusted。
5. `goal show`/`evaluate` 不把 raw `status` 当可信；`achieved` 的 effective 必须过 §3.5 六条。
6. 不改 B5B 默认拒绝、B5A 包装器、B3 摘要、B2 来源门禁。
7. 既有审计字段与既有测试语义保持不变；新增字段只追加。

## 6. 与任务卡 AC 的对应

| AC | 本 ADR / 实现 |
|---|---|
| AC-1 | §3.5 `effective_status`/`status_trusted`；手改无证据 → `satisfied=false` + 不 trusted |
| AC-2 | §3.1/§3.2 删中间行 → `prev_hash` 断链 |
| AC-3 | §3.1 `entry_hash` 重算单行 → 下一行 `prev_hash` 不匹配 |
| AC-4 | §3.3 checkpoint 前缀锚；重建自洽链 → 链头/长度不匹配 |
| AC-5 | §3.4 合法 transition + audit + 签名 checkpoint → `valid`/`authoritative` + effective achieved |
| AC-6 | §3.4 无 anchor/无效签名 → `checkpoint-attach` 拒绝；Agent 无签名函数 |
| AC-7 | §4.1 空/缺审计 → `invalid`；effective 不 achieved |
| AC-8 | 全量 pytest；新增 `tests/test_security_b4.py` |
| AC-9 | B5B/B5A/B3 定向回归 |
| AC-10 | 本文档 |
| AC-11 | `evidence/B4/<run-id>/` |
| AC-12 | 独立复核由 PM-03/人类执行，本会话不宣布 PASS |

## 7. 残余风险

1. **anchor 私钥被攻破**：可签任意 checkpoint；与 ADR-0002/0003 相同，超出本地防护范围；需密钥轮换/外部审计。
2. **重写 Git 历史**：本设计不把 Git 当唯一锚；若运维只用 Git tag 作第二锚，T7 下仍可被伪造；建议 tag 由受保护身份签名或托管在不可变存储。
3. **checkpoint 重放**：同一 checkpoint 复制到另一仓库会因 `goal_id`/链头/证据摘要不匹配被拒；但若攻击者能同时重建链与证据到相同摘要（碰撞/原样复制整个仓库），checkpoint 仍有效——它证明的是“这份历史由 anchor 签过”，不是“仓库未被整体复制”。
4. **前缀锚**：checkpoint 之后的追加条目不受签名保护；删除/改写它们只能靠链链接检测（若攻击者重算则不可检测），但不会影响已签前缀的 `achieved` 结论。这是有意取舍。
5. **history 内部一致性检查可绕过**：同时改 `status` 与 `history` 的高级手改不会触发 `status_history_mismatch`，但 checkpoint/证据条件仍会拦截 `achieved`。
6. **旧审计迁移前无链**：迁移前的删改不可检测；迁移只提供“从迁移点起”的完整性。
7. **单写者假设**：审计文件采用读-改-写原子替换；并发多写者可能丢失一条记录（链仍自洽但少一条）。B4 不做跨进程锁；多 Agent 并发写审计需要后续设计。
8. **离线**：验签完全离线、标准库实现；anchor 文件不可读时一律 fail closed（`unconfigured`/`untrusted`）。
9. **`effective_status` 是新字段**：既有消费方若仍读 raw `status`，不会自动获得保护；需要在运维/架档文档中要求迁移。
10. **非终态未锚定**：`approved`/`active` 等状态仍只是本地工作流声明；B4 只锚定 `achieved`，这是任务卡“至少 achieved”的范围。

## 8. 被拒绝的方案

| 方案 | 拒绝原因 |
|---|---|
| 只加 `prev_hash`，不做 verify | 任务卡防作弊判据 1；无法检测 |
| `audit verify` 只检查最后一行 | 任务卡防作弊判据 2；删中间行不可见 |
| 删除审计后“空链通过” | 任务卡防作弊判据 3；T4 |
| 允许 Agent 生成/更新 checkpoint | 任务卡防作弊判据 4；T3 |
| 只改 `goal show` 文案，仍信 raw `status` | 任务卡防作弊判据 5 |
| 纯 Git commit/tag 锚 | T7：同账号可重写历史；不是不可变存储 |
| hash 链 + 无签名 head | T2：攻击者可重算整条链 |
| 要求“最新链头”完全等于 checkpoint | 达成后任何审计追加都会误伤；改用前缀锚 + 残余风险披露 |
| 把 `achieved` 的 effective 直接等于 `evaluate.satisfied` | 证据成立 ≠ 状态由 anchor 生效；混淆两个命题 |
