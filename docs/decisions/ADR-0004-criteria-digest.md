---
id: "ADR-0004"
status: "proposed"
owner: "MJ-Zeng"
related_issues: [16]
---

# ADR-0004：判据定义摘要与证据分离（B3）

- 状态：`proposed`（Agent 起草；接受需人类批准，见 `docs/decisions/README.md`）
- 日期：2026-10-28
- 任务：B3（Issue #16）
- 基线：`832f2710bfde1cbc498ee6882a5e10b797db6a76`
- 影响范围：`project_memory/coordination.py`（判据摘要 helper、`_verification_current`、`_verification_ok`、`verify_run` 的摘要字段）、`tests/test_security_b3.py`（新增）、本文档
- 不涉及：`authority`/签名信任模型、`execution_provenance`/B2 来源门禁、Goal 数据布局、B2 任务卡/判据、B4/B5

## 1. 背景与问题

`verify_run` 写验证记录时，`goal_criteria_sha256` 是对**整个 `success_criteria`（包含每个 criterion 的 `evidence` 数组）**的规范化摘要：

```text
goal_criteria_sha256 = canonical_digest(goal["success_criteria"])
```

而 `add_goal_evidence`（`goal evidence`）把新证据追加到同一个 `success_criteria[i].evidence`：

```text
success_criteria[i].evidence.append({kind, ref, ...})
```

于是正向流程自失效：

1. 验证时 `evidence=[]`，摘要为 D0；
2. `goal evidence` 追加一条证据，`success_criteria` 变化，摘要变为 D1；
3. `_verification_current` 比较 `D1 != D0`，把**已签名且执行来源有效**的记录判为失效；
4. `goal evaluate` 返回 `insufficient_evidence`，即使证据、收据、attestation 与签名都有效。

这不是签名或来源门禁的问题：B2 正例 `goal evidence` exit 0，但 `goal evaluate` 仍 `satisfied=false`。问题在于**把可变证据纳入了判据定义的绑定**。

## 2. 两个正交概念

| 概念 | 含义 | 可变性 | 应否进入验证绑定 |
|---|---|---|---|
| **判据定义** | `id`、`statement`、`required`（以及顺序） | 验证后不应改变；改变即换了一个标准 | **是** |
| **判据证据** | `evidence[]`（追加或替换引用） | 验证后正常增长 | **否** |

验证签名回答的是“验证者是否针对这组判据定义、这个提交、这份执行给出了 PASS”。追加证据只是“后来有人为同一标准补充了引用”，不改变被验证的命题。

## 3. 决策

选择任务卡 §4 的**方案 1：稳定判据摘要 + legacy 兼容**。

不选方案 2（证据外置）的原因：

- 需要迁移 Goal 数据布局（`success_criteria` 不可变、evidence 移到新字段/文件），影响所有读写路径与旧数据回退；
- 本缺陷只需要把 evidence 从摘要中排除；evidence 仍在 Goal 内可读、可审计；
- 方案 1 的改动面更小，且不改变现有 Goal schema 与 `goal evidence` 的写入位置。

不选方案 3（1+2）的原因：证据外置没有为 B3 的验收标准增加任何可验证保证，只会扩大迁移与回滚风险。

### 3.1 稳定摘要定义

```text
criteria_definition(criteria) =
  [ {"id": c.id, "statement": c.statement, "required": c.required} for c in criteria ]

goal_criteria_sha256 = canonical_digest(criteria_definition(criteria))
```

- 按 Goal 中 criteria 的**原有顺序**纳入；顺序变化视为定义变化。
- 只覆盖三个定义字段；`evidence`、`note` 等不进入摘要。
- 新记录同时写 `goal_criteria_legacy_sha256 = canonical_digest(success_criteria)`（旧全量摘要），仅用于审计与迁移对照，**不参与** currentness 判定；它和记录内其他字段一样被签名覆盖。

### 3.2 currentness 判定

对记录里的 `goal_criteria_sha256`：

1. 等于当前 criteria 的**稳定摘要** → current（新记录；追加/替换 evidence 不影响）；
2. 等于当前 `success_criteria` 的**全量摘要** → current（legacy 记录且证据未变）；
3. 等于当前 criteria 在 **`evidence=[]` 投影**下的全量摘要 → current（legacy 记录在签名后追加了证据）；
4. 其他 → 判据定义已变化，记录失效。

第 3 条是 legacy 兼容：B2 正例签名时 `evidence=[]`，其后 `goal evidence` 追加；清空 evidence 的全量摘要仍等于签名时的 D0。它不会放宽定义绑定：改 `id`/`statement`/`required` 会同时改变第 1、2、3 条的计算结果。

### 3.3 错误分类

`_verification_ok` 在记录失效时区分两类原因：

- 判据摘要不匹配 → “判据定义已变化（id/statement/required），验证记录失效”；
- 其他（提交、run、日志、收据、tracked diff 等） → “针对的不是当前提交或执行已失效”。

证据追加本身不再产生任何失效原因，因此不会落到错误消息里。

## 4. 不变量

1. `goal evidence` 只改 Goal 文件，**不改验证记录字节**；签名与 `verification_digest` 不变。
2. 改 `id`/`statement`/`required` → 稳定摘要与 legacy 摘要都不匹配 → `_verification_current=false`，`goal evaluate` 不 satisfied。
3. 追加/替换 evidence → 稳定摘要不变 → 新记录仍 current；legacy 记录走第 3 条投影仍 current。
4. `goal evaluate` 仍经 `_evidence_result → _verification_ok → _verification_current`；不新增旁路。
5. `authority`、`execution_provenance`、attestation/例外校验、B2 来源门禁均不改动。
6. 不自动重新签名；Agent 不持有私钥。

## 5. 迁移与回滚

- **旧记录**：不重写、不清洗。按 §3.2 的第 2/3 条继续可用；旧 Goal 的 evidence 保持原位。
- **旧记录签在非空 evidence 上**：没有稳定摘要字段，无法区分“定义”与“当时的证据快照”。追加证据后第 2、3 条都不匹配，记录失效。这是 legacy 的已知限制（B2 正例签在 `evidence=[]` 上，不受影响）。
- **新记录**：`goal_criteria_sha256` 为稳定摘要，另带 legacy 摘要字段。外部签名者在记录生成后对整条记录（除 `authority`）签名，新增字段自动进入签名载荷。
- **回滚到 B3 之前的代码**：旧代码按全量摘要比较，会把新记录的稳定摘要判为不匹配，新记录失效；需要重新验证并由人类重新签名。回滚是 forward-only 的破坏性操作，必须在发布说明中写明。
- **B2 fixture**：`fixtures/b2/genuine-trusted` 保持只读，用第 3 条兼容路径验证。

## 6. 残余风险

1. legacy 记录若签名时 evidence 非空，追加证据后失效（无稳定字段可回溯）。
2. criteria **顺序**变化会失效；这是有意的“定义变化”判定，但顺序调整属于误伤面。
3. 摘要仍不绑定 `goal_id`/`title`/`outcome`；与 B3 之前一致，验证记录另有 `goal_id` 等字段，但摘要本身只覆盖 criteria。
4. 直接手改 Goal JSON 可以制造重复 criterion id；摘要仍确定，但 Goal 结构校验只在创建/写入路径执行。B3 不扩大这一既有面。
5. 信任根/私钥被攻破仍可签任意记录；本设计不防御，见 ADR-0003。
6. 新记录依赖外部签名者在字段变化后重新签名；若签名者仍按旧字段集签名，验签会失败（fail closed），不会静默接受。

## 7. 被拒绝的方案

| 方案 | 拒绝原因 |
|---|---|
| 删除 `goal_criteria_sha256` 检查 | 失去验证与判据定义的绑定；任务卡防作弊判据 1 |
| `_verification_current` 永远 true | 任务卡防作弊判据 2 |
| 追加证据后自动重新签名 | Agent 无私钥；自动签名使 Agent 成为信任主体；任务卡防作弊判据 3 |
| 只对 B2 fixture 的 goal id 特判 | 绕过与 fixture 绑死；任务卡防作弊判据 4 |
| `evaluate_goal` 不调用 `_verification_current` | 任务卡防作弊判据 5 |
| 放宽 B2 执行来源门禁 | 任务卡防作弊判据 6；B2 的伪造收据/谎报 trusted 必须继续失败 |
| 证据外置（方案 2） | 迁移面大、需要回退路径；对 B3 无额外安全收益 |
| 只要 `goal evidence` 成功就算 satisfied | 任务卡防作弊判据 8；evaluate 必须独立判定 |

## 8. 验收对应

- AC-1/AC-2：新记录 + `goal evidence` + `goal evaluate` satisfied；记录字节与签名不变。
- AC-3：legacy B2 正例走第 3 条兼容路径。
- AC-4/AC-5：改定义失效、改证据不失效。
- AC-6：B2 来源门禁回归由既有 `test_security_b2.py` 与 anchor-a fixture 覆盖。
- AC-7：全量 pytest 无删除/跳过。
- AC-8/AC-9：本 ADR 与实现一致；迁移/回滚/残余风险如上。
