# B2 — 有效签名不得包裹伪造执行收据

- 任务 ID：`B2`
- 状态：`draft`（派发前冻结）
- 优先级：P0 / security
- 基线：`dev/v1.0` 的 B2 dispatch 合并提交；精确 SHA 见派发 Issue
- 冻结参照：`0d08a1ad85144d11a46d6a361a2a3ce4eadbbed4`
- 候选分支：`fix/b2-receipt-provenance`
- 关联 Issue：见派发 Issue（本任务卡不绑定 URL）
- Goal：`G-B2`
- 依赖：B1 已合并；B0 已合并
- 来源：RC3 独立复核 B2（`reviews/independent-rc3-0d08a1a/FINAL_INDEPENDENT_STATUS.md`）

## 1. 问题

`project_memory/coordination.py` 的 `_verification_ok()` 要求
`checks.tests.receipt_integrity_valid`，但没有要求可验证的**执行来源**。

因此：

1. 手写一份自洽收据（`valid=true`、`provenance.trusted=false`、`executor=handwritten`）；
2. 用测试签名者签一条引用该收据的 Verification；
3. `goal evidence` 接受，`goal evaluate` satisfied，Goal 到 `achieved`。

**签名只证明“这条 Verification 记录被签过”，不证明“收据对应的执行真的发生过”。**

## 2. 目标

把**内容完整性**与**执行真实性**分开：

- 内容完整性：收据/快照/日志的哈希一致；
- 执行真实性：收据来自可验证的受保护执行器/attestation，或有人类明确例外授权；
- 授权：只有前者 + 后者同时满足，才能满足标准。

不能只检查一个自报的 `execution_provenance.trusted=true` 布尔值——手写收据也能写这个字段。

## 3. 范围

允许修改：

- `project_memory/coordination.py`（`_verification_ok` / `_evidence_result` / 相关判断）
- `project_memory/execution.py`（provenance/attestation 读取或校验；如需要）
- `project_memory/authority.py`（如签名载荷需要纳入 provenance/attestation 摘要）
- `tests/`（新增 B2 负向/正向测试）
- `docs/decisions/`（ADR）
- `pilot/evidence/B2/`、`pilot/rounds/B2/handoff-*`
- `pilot/kit/b2/`（如需要 fixture 说明）

不允许：

- 修改 B1/B3/B4/B5 的行为（除非为 B2 所必需，必须声明并说明不可拆分）；
- 删除/跳过既有测试；
- 修改任务卡/判据/探针/评测器；
- 放宽 authority、签名、`execution_provenance.trusted` 的语义；
- 只加一个 `if not trusted: reject` 就宣称完成（必须防“手写 trusted=true”）。

## 4. 设计选项（PM-02 选一个并写 ADR）

1. **验证 attestation，而不是验证布尔值**
   - 受保护执行器产出 attestation（launcher、command、commit、snapshot、receipt hash、时间）；
   - 用 anchor/受保护公钥验证 attestation 签名；
   - `execution_provenance.trusted` 只是展示标签，不是门禁。
2. **把执行来源纳入签名载荷**
   - Verification 的签名覆盖收据/attestation 的摘要；
   - 换收据、改 provenance、换 commit 都会使签名失效；
   - 签名者明确授权“这条执行事实”。
3. **显式人类例外**
   - 对无法 attestation 的执行，允许一条**人类签名/记录**的例外，绑定 receipt hash、commit、原因、范围；
   - 例外不是自动 pass，不得由 Agent 生成；
   - 没有例外时，未受信执行必须 fail closed。

可以组合 1+2，或 2+3；必须在 ADR 说明为什么不能只查 `trusted`。

## 5. 验收标准

| AC | 判据 | 方法 | 通过条件 |
|---|---|---|---|
| AC-1 | 手写自洽收据（`trusted=false`）+ 有效签名被拒 | `goal evidence` / `evaluate` | 拒绝；satisfied=false；不得 achieved |
| AC-2 | 手写收据谎报 `trusted=true`（无 attestation）+ 有效签名被拒 | 同上 | 拒绝；证明不是只查布尔值 |
| AC-3 | 真实可信执行（可验证 attestation）+ 有效签名被接受 | 正向 fixture / `--trusted` | 接受；satisfied=true；不得把所有执行都拒掉 |
| AC-4 | 本地未受信收据 + 有效签名：拒绝，或仅显式人类例外 | 负向 fixture + 例外 fixture | 默认拒绝；例外必须绑定 receipt/commit/原因，不能自动 |
| AC-5 | 来源绑定 | 换收据/改 provenance/换 commit/重算内容哈希 | 签名或 attestation 校验失败；不能靠改字段通过 |
| AC-6 | 回归 | 既有 190 passed / 2 skipped + 新增测试 | 全绿；无删除/跳过未说明 |
| AC-7 | 无新绕过 | 既有 B1/B2 负向用例 + PM-03 变体 | 全部拒绝；authority/签名未放宽 |
| AC-8 | ADR | 威胁模型、被拒方案、残余风险、迁移 | 与实现一致 |
| AC-9 | 证据 | 命令、退出码、日志、哈希 | 可复现；正负证据齐全 |
| AC-10 | 独立复现 | PM-03 从两个 Clone/路径复现 | 负向拒绝、正向接受 |
| AC-11 | 范围纪律 | diff 只在允许文件 | 无 B1/B3–B5 夹带 |

## 6. Fixtures（`pilot/kit/b2/`）

需要四类记录，均由 PM-01/人类用 anchor-a 签名（私钥不入库）：

1. `VER-b2-forged-untrusted`：引用手写收据，`provenance.trusted=false`；
2. `VER-b2-forged-claimed-trusted`：引用手写收据，谎报 `trusted=true`，无 attestation；
3. `VER-b2-genuine-trusted`：引用带可验证 attestation 的真实/测试执行；
4. `VER-b2-local-untrusted`：本地未受信收据（如无例外，应拒绝）。

另需：

- `receipts/`：对应收据与快照；
- `attestations/`：测试 attestation（如设计使用）；
- `README.md`：每个 fixture 证明什么、期望结果、生成命令/哈希；
- `sha256sums.txt`。

如果正向 `VER-b2-genuine-trusted` 在派发前无法生成，标记 `NOT VERIFIED`，不得用伪造的 `trusted=true` 冒充正向。

## 7. 防作弊判据

以下“修复”均判 **FAIL**：

1. 只检查 `execution_provenance.trusted` 布尔值；
2. 只检查 `executor.name`/`launcher` 字符串；
3. 只对 B2 fixture 的 receipt id/路径特判；
4. 让所有验证都失败（AC-3 失败）；
5. 放宽 authority/签名，或允许 Agent 生成“人类例外”；
6. 删除/跳过既有测试；
7. 把未受信执行自动标成 trusted；
8. 隐藏失败、把 NOT RUN 写成 PASS。

## 8. 证据包

```
pilot/evidence/B2/<run-id>/
  README.md
  environment.txt
  commands.jsonl
  forged-untrusted.json
  forged-claimed-trusted.json
  genuine-trusted.json
  local-untrusted.json
  pytest.log
  diffstat.txt
  sha256sums.txt
```

不含私钥、token、其他项目数据。

## 9. 判定语义

| 结论 | 条件 |
|---|---|
| **PASS** | AC-1..AC-11 全部满足；负向全拒绝、正向接受；无新绕过 |
| **FAIL** | 任一必需 AC 失败；手写收据（含谎报 trusted）被接受；或所有执行都被拒 |
| **BLOCKED** | 环境/密钥/fixture/授权缺失，无法执行 |
| **NOT VERIFIED** | 有 AC 未运行；整体不得记 PASS |

## 10. 不在范围

- B1/B3/B4/B5、WSL_EXE、发布；
- 多 Agent 编排、Web UI、知识图谱、额外模型服务；
- 修改冻结候选 `frozen/rc3-0d08a1a`。

## 11. 阅读顺序

`pilot/README.md` → `pilot/ROLES.md` → `pilot/ROUND_PROTOCOL.md` → 本任务卡 → `pilot/reference/RC3_B1_B3.md` → `pilot/kit/b2/README.md`。
