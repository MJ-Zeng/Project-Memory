---
id: "ADR-0008"
status: "proposed"
owner: "MJ-Zeng"
related_issues: []
---

# ADR-0008：信任锚生命周期（有效期、吊销、指纹）与审批的仓库身份复检

- 状态：`proposed`（Agent 起草；接受需人类批准，见 `docs/decisions/README.md`）
- 日期：2026-11-01
- 任务：S4-2（差距 S4-G4 = B-13 锚无吊销/过期/轮换；S4-G9 `verify_approval` 不复检仓库身份）
- 基线：`40d3f1dbfeaa9e0d588e805377bad0d2c0575535`（S4-1 合并头）
- 影响范围：`project_memory/authority.py`（`_pem_der`、`public_key_fingerprint`、`_anchor_document` 的可选字段校验、`_anchor_lifecycle_problem`、`load_anchor` 的生命周期判定）、`project_memory/coordination.py`（`verify_approval` 的仓库身份复检）、`tests/test_s4_anchor_lifecycle.py`（新增）、`docs/`（运维轮换与吊销、架构信任判定顺序）、本文档
- 不涉及：PKI/CRL/OCSP 协议、网络依赖、新增加密算法、签名载荷算法、`_verify_signature`、已合并提交与已写出记录、`.github/`、issuer 的真人身份认证（属 S4-4）

## 1. 背景与实测缺口

ADR-0002 §6.5 把「无吊销机制」列为残余风险：锚一旦泄露或到期，验签路径仍然永远接受它的签名。S4-1 之后审批与证据清单都走同一入口（`_execution_record_authority` → `load_anchor`），于是这个缺口变成了三条链共用的单点：

| 缺口 | 事实 | 后果 |
|---|---|---|
| S4-G4 无有效期 | 锚文档只有 `anchor_id`/`issuer`/`algorithm`/`public_key_pem` | 私钥泄露后无法表达「这个锚只用这一年」；演练锚与生产锚在数据上同形 |
| S4-G4 无吊销 | 没有任何字段能声明某个 `anchor_id` 作废 | 泄露只能靠换锚 + 覆盖环境变量，且无法表达「这个锚曾存在且已作废」 |
| S4-G4 无指纹 | 公钥只以 PEM 文本存在，公布渠道无法核对 | 运维无法确认受保护文件里的公钥就是公布的那一个（DER 字节稳定，PEM 换行不稳定） |
| S4-G9 仓库身份 | `attach_approval`/`_approval_evidence`/`evaluate_goal` 都调用 `_approval_repository_matches`，只有 `verify_approval` 漏了 | 在仓库 B 上直接 `approval verify` 一份为仓库 A 签发的记录，签名有效即 exit 0 |

## 2. 决策

### 2.1 锚文档增量四个可选字段

必填字段与 `schema_version: "1.0"` 都不变；新增字段全部可选，因此老锚文档行为完全不变（回归由测试保证）。口径：字段显式写成 JSON `null` 与根本不提供该字段等同，都按「未启用」处理；空字符串 `""` 与纯空白串判非法——可选不等于宽松，值一旦给出就必须合规。

- `not_before` / `not_after`：带时区的 ISO-8601 字符串（`Z` 或 `±HH:MM`）。无时区、不可解析、`not_before > not_after` 都视为锚文档非法。判定用当前 UTC，闭区间 `not_before <= now <= not_after`；只给一端时另一端不限制。
- `revoked_anchor_ids`：字符串数组，每项匹配 `[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}`。不是数组、含非字符串、含空串或空白串一律非法；字段存在但格式错误必须 fail closed，不允许「忽略后继续」。数组含当前锚自己的 `anchor_id` ⇒ 该锚不再参与信任判定。
- `fingerprint_sha256`：64 位十六进制（大小写不敏感，允许 `sha256:` 前缀），值必须等于 `public_key_pem` 解出的 **DER SubjectPublicKeyInfo 字节**的 SHA-256。哈希 DER 而不是 PEM 文本，因为 PEM 的换行与空白不稳定；不一致 ⇒ 锚文档非法。
- 未识别的额外字段忽略（前向兼容），但绝不因它们授予信任。

实现上拆成两层：`_anchor_document` 负责结构与指纹（`attach`/`request` 也走这里），`_anchor_lifecycle_problem(anchor, now=None)` 负责时间与自吊销，`load_anchor` 在文档校验通过之后调用它，`now` 参数只为测试可读。`_pem_der` 从 `_public_key` 里抽出 PEM→DER 的解码，`public_key_fingerprint` 与 `_public_key` 共用它；签名载荷算法、`_verify_signature`、依赖表都不动。

### 2.2 生命周期在「每次信任判定」时求值

不在签发时写快照，也不在记录里存「当时锚有效」的证据。理由：

1. **判定发生在读取时**：所有 verifier（`verification_authority`、`approval_authority`、`evidence_authority`、执行 attestation/例外）都通过 `load_anchor` 读受保护锚，把生命周期放在 `load_anchor` 一处，四条链同时生效，没有「某条链忘了查」的可能。
2. **不追溯改写历史**：吊销与过期只让**之后**的验证失败；已签发的记录、已合并的提交、已写出的清单一个字节都不改。要撤回一次合并仍是 GitHub 的事，锚无权表达。
3. **不引入状态机**：签发时刻的有效性快照需要「谁写、何时写、能否重写」这套新状态，正是要避免的可篡改面；当前语义只有一条规则——现在这个锚可用吗。
4. **对历史证据的影响可控**：需要长期可验证就拉长 `not_after`，或轮换后用新锚重签同一载荷；`attach` 路径的幂等语义（S4-1）已经支持重签。

因此 `load_anchor_document` 明确不做时间与自吊销判定，只做文档级校验（含指纹），docstring 与架构文档都写清这个边界：那里回答「是不是格式正确的公钥文档」，不回答「我是否信任它」。

### 2.3 吊销来源只有受保护锚与 CI secret

`revoked_anchor_ids` 只能来自 `PROJECT_MEMORY_APPROVAL_ANCHOR` / `PROJECT_MEMORY_APPROVAL_ANCHOR_JSON`（以及验证锚对应变量）。不允许从仓库内文件、审批记录、清单或任何其他位置读取吊销列表。理由很直接：仓库内文件对 Agent 可写，若吊销列表可以放在仓库里，那么能写仓库的主体既能吊销别人的锚，也能删掉自己锚上的吊销条目——吊销就从防线变成了攻击面。

CI secret 分支同理：值来自仓库外，且只在 `GITHUB_ACTIONS=true` 时被采用；该开关是防误用闸门，不是密码学边界（ADR-0002 §2、OPERATIONS「CI 审批门禁」已记录）。

### 2.4 `verify_approval` 复用既有仓库身份复检

`verify_approval` 在 `problems` 里增加一条 `_approval_repository_matches(record, repo)` 检查（`repository.id` 必须等于当前 `repo_identity(repo).id`，`remote` 允许为 `None` 或与当前一致）。返回结构不变，因此 CLI 沿用现有映射：`verified=false` → exit 2，`approval verify-records --require-approve` 同样不会把这份记录算作批准。

这一条与签名无关：在仓库 B 上验签一份为仓库 A 签发的记录，签名依然有效（`trusted=true`），但 `problems` 只含仓库身份不一致，门禁必须拒绝。它把 `attach`/评估侧已有的检查补齐到验证侧，不新增数据模型。

## 3. 被拒方案

1. **CRL / OCSP 式外部吊销协议**：需要网络、需要另一个权威服务，而本项目是本地优先、离线可用、运行依赖为 `[]` 的 CLI。引入网络等于把「能否验证」变成「能否联网」，并新增一个可被拒绝服务的环节。
2. **把吊销列表放进仓库**（在记忆目录下新增一个已吊销锚的 JSON）：Agent 可写 ⇒ 既能伪造吊销，也能抹掉吊销。可写目录里的吊销不是吊销，是另一个待保护的密钥材料，成本高于收益。
3. **签发时把有效性写进记录**（`anchor_valid_at` 之类）：要么由 Agent 自报（不可信），要么由签名者承诺一个未来仍要复核的时间点（等价于当前语义，但多了一个可篡改字段）。
4. **时间戳权威（TSA）**：为「证明签名发生在有效期内」引入第三方，而门禁真正关心的是「现在这个锚还能用吗」。
5. **哈希链式吊销账本**：本项目账本只覆盖审计条目，扩展到锚生命周期需要新的 schema、迁移与门禁；B-13 的边界是「有可用吊销手段」，不是「有完整 PKI」。
6. **`fingerprint_sha256` 当作身份认证**：它只证明「这份文档里的公钥就是公布的那个公钥」，不证明 issuer 是真人；后者需要仓库外公布渠道，属 S4-4。

## 4. 失败关闭矩阵

| 场景 | 结果 |
|---|---|
| 锚文档缺 `not_before`/`not_after`/`revoked_anchor_ids`/`fingerprint_sha256` | 行为与 S4-1 相同（可选字段，向后兼容） |
| 时间在闭区间内 | 继续判定；`not_after` 缺失 ⇒ 只受 `not_before` 约束 |
| `not_after` 已过 / `not_before` 未到 | `load_anchor` 返回 `(None, 原因)` ⇒ 审批、清单、验证记录、执行记录与审计 checkpoint 一律 `trusted=false`，退出码见本节末尾的口径说明 |
| `anchor_id` 出现在自己的 `revoked_anchor_ids` | 同上，原因写明「已吊销」 |
| `revoked_anchor_ids` 不是数组 / 含空串 / 含非字符串 / 含非法字符 / 超 128 字符 | 锚文档非法 ⇒ `unconfigured`，该锚不参与信任判定 |
| 时间字段无时区或不可解析、`not_before > not_after` | 锚文档非法，该锚不参与信任判定 |
| `fingerprint_sha256` 与公钥 DER 实算不符、或不是 64 位十六进制 | 锚文档非法，该锚不参与信任判定 |
| 生命周期失败且同时配置了文件锚与 JSON 锚 | 不回退到 JSON 锚（保持「显式配置的文件锚权威」的既有语义） |
| 记录来自另一仓库（签名有效） | `approval verify` exit 2，`problems` 只含仓库身份不一致 |
| `attach`/`request` 面对过期或已自我吊销的锚文档 | 仍然只做格式与签名检查，不做生命周期判定（信任在 `verify`/门禁决定） |

**退出码不是一个数**。失效锚在所有信任判定点都只产生 `trusted=false`，但各链的 CLI 口径不同（下表为本卡实测，`goal evaluate` 的判据集合为空时甚至 exit 0）：

| 链 / 命令 | 锚失效时的结果 |
|---|---|
| `approval verify`（单条）、`approval verify --records-dir --require-approve`、`evidence verify` | exit 2，`trusted=false`，`problems`/`reason` 给出原因 |
| `audit checkpoint-attach` | `load_anchor` 失败 ⇒ `raise PMError` ⇒ CLI exit 1，stderr 写「无法验证 checkpoint：信任锚已吊销…」 |
| `goal evaluate` | 退出码只跟随 `satisfied`；判据不满足 exit 2，判据集合为空 exit 0 + `satisfied=false`（`no_required_criteria`；这个状态只能由改写 Goal 文件把必达判据删空或全部改成可选得到，`goal create` 要求至少一条必达判据，否则 `PMError`，所以它不是正常创建的产物） |

因此自动化必须读 JSON 字段（`trusted`/`verified`/`approved`/`satisfied`/`status_*`），不能只看退出码——这条与 OPERATIONS「CI 审批门禁」里既有的提醒一致。

## 5. 测试与证据

`tests/test_s4_anchor_lifecycle.py`（20 项）覆盖：无可选字段的回归、有效期内 + 指纹正确 + 只吊销他人 id 的正例、签名执行记录在同一锚下 `trusted`；负对照含自我吊销、已过期、未生效、`revoked_anchor_ids` 各种非法形态、指纹不符、时间格式非法（逐形态断言对应的原因关键词）、区间倒置、跨仓库记录；对照含「只吊销别人」与「只有 `not_before` 且已生效」两条必须 exit 0 的情形，防止过度拦截。

另有 3 项专门走 **CI secret 通道**（`GITHUB_ACTIONS=true` + `PROJECT_MEMORY_APPROVAL_ANCHOR_JSON`），不 patch 任何生产函数，各自锁定的范围按测试名读得出来：`test_revoked_anchor_json_secret_is_not_trusted` 让自我吊销锚在**单条** `approval verify` 与 `--records-dir --require-approve` **批量**门禁下都 exit 2、`trusted=false`；`test_expired_anchor_json_secret_is_not_trusted` 让已过期锚在**单条**门禁下 exit 2 —— 过期锚的**批量**形态目前只有独立复核实测确认（exit 2、`approved=false`），本仓库还没有专属测试锁定它，这条差异写在这里，别让读者以为批量已被测过；`test_valid_anchor_json_secret_stays_trusted` 让有效期内的锚在同一通道下仍 exit 0（单条与批量都断言），防过度拦截。文件锚与 JSON 锚是 `load_anchor` 的两条分支，生命周期包装各一份；门禁 workflow 只注入 JSON secret，所以这条分支必须有独立的回归锁。

两处方法论约定：

- **不 patch `authority.load_anchor`**：那会绕过被测逻辑。文件锚用例 patch `authority._load_file_anchor`，其 side effect 仍调用真实的 `_anchor_document`，因此只替换了路径解析与所有者保护（不属于本卡），文档校验与生命周期判定都走真实代码；CI secret 用例不 patch 任何生产函数，环境变量用 `mock.patch.dict` 注入，走完整的 `load_anchor`。
- **变异验证**：删掉 `load_anchor` JSON 分支的生命周期包装后，上述 2 条负对照立即失败（`AssertionError: 2 != 0`，全量 370 项报 `FAILED (failures=2)`），还原后全部通过；同一变异在加入这 3 项之前（17 项）不被任何测试发现。这就是这条分支需要独立锁的理由。
- **时间一律相对当前 UTC 构造**，避免固定日期在未来某个时刻集体过期；闭区间边界用 `_anchor_lifecycle_problem(anchor, now=...)` 直接判定。
- 指纹实现与 `openssl pkey -pubin -outform DER | openssl dgst -sha256` 交叉核对（测试内用两条 openssl 命令独立计算）。

## 6. 残余风险

1. **吊销依赖人工操作**：私钥泄露后必须有人去改受保护文件或 CI secret；没有自动吊销、没有告警。本卡只提供手段，不提供发现能力。
2. **issuer 仍是自报字符串**：`fingerprint_sha256` 让运维能核对「文档里的公钥就是公布的那个」，但公布渠道本身在仓库外（S4-4 / D3）。
3. **时钟来源**：有效期判定用宿主当前 UTC 时间。宿主时钟错误会让有效锚被判过期或让过期锚仍被判有效；本项目不引入网络时间源（同 §3.1 的理由）。
4. **单一锚**：当前仍是「一个锚文档」，`revoked_anchor_ids` 主要用于自我吊销、演练锚登记与未来多锚场景；多锚并验不在本卡范围。
5. **不追溯**：吊销不能让历史验证「重新变成通过」，也不能证明当时那次通过是伪造——历史证据仍按「只做人工复核、不为清零改写历史」处理。
6. **ECDSA 非常量时间**（ADR-0002 §6.6）与 `anchor_is_protected` 不防 root（ADR-0002 §6.4）：本卡未改变这两条。
