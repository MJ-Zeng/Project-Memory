# B3 独立复核报告 — 证据附件不得使已签名验证失效

- 任务：B3（Issue #16）
- 候选：`19bba33378ca45c8e776bbb11e99b9f5497cbaed`（PR #18，分支 `fix/b3-stable-criteria`）
- 基线：`832f2710bfde1cbc498ee6882a5e10b797db6a76`
- 任务卡：`tasks/B3.md`，SHA-256 `89b2d31b4dd604a384e3cc42531b2b8e47ae39e6be290ebdcde503dff8cef8bc`（与派发一致）
- 审查分支：`review/b3-19bba33`
- 证据：`evidence/B3/review-20261028T143901Z/`（`matrix.json`、`environment.txt`、`commands.jsonl`、`pytest.log` 等）
- 结论：**PASS（程序性独立复核）**。这不是安全认证，也不等于 v1.0 GO；合并仍由人类决定。

---

## 0. 复核方法

- 独立会话、独立 worktree（`.pilot/b3-base`、`.pilot/b3-candidate`）；未读取开发/主管会话、终端历史或工作树。
- 只读仓库工件 + PM-01 提供的 anchor-a fixture；每个 case 复制到 `/tmp` 后运行，不原地改 fixture。
- E2E 在 WSL（Ubuntu，uid 1000）执行，`PROJECT_MEMORY_TRUST_ANCHOR=/etc/pm-rc3-review/anchor-a.json`；未读取 `key-a.pem`。
- 回归用 Windows `C:\SoftWare\Anconda\python.exe`（3.12.4，pytest 9.1.1）在候选 worktree 重跑。

## 1. 接手恢复

六项事实：

1. B3 修的是正向自失效：`goal evidence` 把证据追加进 `success_criteria[i].evidence`，旧摘要覆盖整张表，导致已签名验证在 `evaluate` 时被误判失效（B2 AC-3 遗留子项）。
2. 基线 `832f2710`（PR #17 合并，`dev/v1.0` HEAD），候选为基线直接子提交。
3. 允许范围：`coordination.py`、`common.py`、`tests/`、`docs/decisions/`、相关 `docs/` 契约、`evidence/B3/`；禁止放宽 authority/来源门禁、删测试、自动重签。
4. AC-1..AC-12：正向 satisfied、记录字节不变、legacy 兼容、定义变更失效、证据变更不失效、B2 门禁不回归、213+ 测试、迁移路径、ADR、证据、独立复核、范围纪律。
5. Fixture 就绪：`fixtures/b2/{new-stable,definition-change}`（B3 用）+ `fixtures/b2/genuine-trusted`（legacy）；注意 B3 case 实际位于 `fixtures/b2/`，`fixtures/b3/` 只有 README/生成脚本。
6. 下一步：静态审 diff → WSL anchor-a 正负矩阵 → 全量 pytest → 证据与报告。

接手分钟数：**约 10 分钟**（读收尾/交接/任务卡/ADR + 校验哈希/祖先 + 定位 fixture）。

必须询问/需人类知道：

1. B3 fixture 落在 `fixtures/b2/` 而非文档写的 `fixtures/b3/` —— 是否需要归档到 `b3/`？内容与期望一致，本次按内容复核。
2. 候选与 PR 中没有开发侧证据包（`evidence/B3/run-20261028T135956Z/` 不可见）；AC-10 由本报告独立证据满足。
3. `tasks/B3-context-recovery.md` 在任务卡允许清单外（但派发要求恢复记录）；是否在合并前移入 `evidence/B3/`？

`contamination`：见 §9。

## 2. 静态检查

diff（`832f2710..19bba33`）：

```text
A docs/decisions/ADR-0004-criteria-digest.md
M project_memory/coordination.py
A tasks/B3-context-recovery.md
A tests/test_security_b3.py
```

`common.py`、`authority.py`、`execution.py` 未改；既有测试未改、未删。

逐项：

| 检查 | 结果 |
|---|---|
| 新摘要只覆盖 `{id, statement, required}` | 是。`_criteria_definition`（`project_memory/coordination.py:229`）只投影三字段，`_criteria_definition_digest`（:235）规范化摘要 |
| 旧记录兼容路径 | 是。`_criteria_digest_matches`（:239）接受稳定摘要、当前全量摘要、或 `evidence=[]` 投影的全量摘要；无摘要字段时 `_verification_current` 保持原有“不比较”语义 |
| `add_goal_evidence` 是否改变判据定义 | 否，只 `append` 到 `criterion.evidence`（:1040-1042）；摘要已排除 evidence |
| `_verification_current` 是否仍比较摘要 | 是。:752-759 仍读取 `goal_criteria_sha256` 并调用匹配函数，未跳过 |
| 定义变更是否仍失效 | 是。三字段任一变化都会改变三种候选摘要 |
| 证据变更是否不使新记录失效 | 是。稳定摘要不含 evidence |
| 自动重签 / 忽略摘要 / 放宽来源门禁 | 均无。diff 不含签名逻辑；`_verification_ok` 的 authority/来源门禁未动（:838 起） |
| 删除/跳过既有测试 | 无 |
| 新字段是否进入签名载荷 | 是。`authority.verification_payload` 排除的只有 `authority`，`goal_criteria_legacy_sha256` 自动被签名覆盖；也进入 `verify_run` 的 identity 元组（:1798-1799） |
| ADR-0004 内容 | 覆盖摘要语义、三种 currentness 路径、迁移/回滚、残余风险、被拒方案，与实现一致 |

## 3. 逐条 AC

| AC | 判据 | 证据 | 结论 |
|---|---|---|---|
| AC-1 | 新记录 + 追加证据后 evaluate satisfied | `new-record.json`：追加前 `exit 2 / insufficient_evidence`，追加后 `exit 0 / satisfied`、`recommendation=achieved` | PASS |
| AC-2 | 不重新签名、记录字节不变 | new-stable 与 legacy 记录 SHA-256 在 `goal evidence` 前后一致；`authority.trusted=true` | PASS |
| AC-3 | legacy B2 正例仍可用 | `legacy-b2.json`：候选 `exit 0 / satisfied`；同 fixture 在基线 `exit 2 / false` | PASS |
| AC-4 | 改 id/statement/required 仍失效 | `negative.json`：三者 `_verification_current=false`；statement/id 的 evaluate 均 false。required 改后 evaluate 因“无 required 判据”而 trivially true（F-2，基线同） | PASS（带 F-2 说明） |
| AC-5 | 改 evidence 不失效（新记录） | 改 evidence note、追加第二条证据后仍 current、satisfied | PASS |
| AC-6 | B2 来源门禁不回归 | 两个伪造 case `exit 1`（“执行来源不可信：人类例外缺失”）；异常正例 `exit 0`；改收据/改记录分别被完整性校验与签名拒绝；B2 测试 13 passed | PASS |
| AC-7 | 回归 | 213 passed / 2 skipped（基线 203/2）；B3 10 passed + B2 13 passed；无删除/跳过 | PASS |
| AC-8 | 兼容/迁移 | 旧记录不改写，legacy 三路径明示；legacy 记录改定义后被拒（`legacy_definition_change`） | PASS |
| AC-9 | ADR | ADR-0004 与实现一致 | PASS |
| AC-10 | 证据可复现 | `environment.txt`/`commands.jsonl`/`matrix.json`/`pytest.log`/`sha256sums.txt` | PASS（本报告证据） |
| AC-11 | 独立复核 | 本报告 + 独立工作树/独立运行 | PASS |
| AC-12 | 范围纪律 | 功能文件仅 `coordination.py` + 新 ADR/测试；`tasks/B3-context-recovery.md` 越界（F-1，派发要求、B1/B2 同类先例） | PASS（Low 过程项） |

## 4. 动态矩阵

环境：WSL Ubuntu，uid 1000，Python 3.14.4，anchor-a `root:root 644`，sha256 `e85d1f50…`。

### 4.1 新记录正例（`fixtures/b2/new-stable`）

| 步骤 | 结果 |
|---|---|
| 记录字段 | `goal_criteria_sha256=c13c299a…`（稳定摘要），`goal_criteria_legacy_sha256=b17a716f…` |
| `goal evaluate`（追加前） | exit 2，`insufficient_evidence` |
| `goal evidence` | exit 0 |
| `goal evaluate`（追加后） | exit 0，`satisfied=true`，`recommendation=achieved` |
| 记录字节 | 前后 SHA-256 相同；`authority.trusted=true` |

### 4.2 定义变更负例（`fixtures/b2/definition-change`）

| 步骤 | 结果 |
|---|---|
| `goal evidence` | exit 1，stderr：“判据定义已变化（id/statement/required），验证记录失效；追加证据本身不会导致失效” |
| `_verification_current` | false（签名仍 `trusted`，说明不是签名问题） |
| `goal evaluate` | exit 2，`satisfied=false`，`blocking=[C1]` |

### 4.3 Legacy B2 正例（`fixtures/b2/genuine-trusted`）

| 对象 | 追加前 evaluate | `goal evidence` | 追加后 evaluate | 记录字节 |
|---|---|---|---|---|
| 候选（19bba33） | exit 2 / false | exit 0 | exit 0 / **satisfied=true** | 不变 |
| 基线（832f2710） | exit 2 / false | exit 0 | exit 2 / false | — |

legacy 记录只有 `goal_criteria_sha256=b17a716f…`（全量摘要），无 legacy 字段；命中 `_criteria_digest_matches` 的 `evidence=[]` 投影路径。

### 4.4 负向

| case | `_verification_current` | evaluate | 说明 |
|---|---|---|---|
| statement → `changed after signing` | false | false | 稳定摘要与两种 legacy 摘要均不匹配 |
| id → `C2` | false | false（blocking C2） | 同上 |
| required → false | false | **true** | F-2：唯一 required 被关掉后 evaluator 无必达项；基线同 |
| evidence note 修改 | true | true | 证据不进入定义绑定 |
| 追加第二条证据（kind=commit） | true | true | 追加不破坏 current |
| legacy + statement 修改 | false | false | legacy 兼容不是“任何旧记录都接受”；`goal evidence` exit 1 |

`required_change` 的基线对照（legacy fixture，`b3-base`）：`_verification_current=false`、evaluate 同样 trivially true —— 证明 F-2 是既有 evaluator 语义，不是 B3 引入。

### 4.5 B2 回归

| case | `goal evidence` | 错误 |
|---|---|---|
| `forged-untrusted` | exit 1 | 执行来源不可信：人类例外缺失 |
| `forged-claimed-trusted` | exit 1 | 执行来源不可信：人类例外缺失 |
| `exception`（正例） | exit 0 | — |
| 改收据（exit_code） | exit 1 | 收据内容哈希不一致（收据被修改） |
| 改记录字段（未重签） | exit 1 | `signed_payload_sha256` 与记录内容不一致 |

B2 的 13 个专项测试全部通过（含换收据、改 provenance、attestation 换 commit/换收据）。

## 5. 回归

```text
C:\SoftWare\Anconda\python.exe -m pytest -q -p no:cacheprovider
213 passed, 2 skipped in 112.91s
```

与基线 203 passed / 2 skipped 相比新增 10 个 B3 测试；2 skipped 是既有 Windows 符号链接限制，未新增跳过。

## 6. 新发现

| ID | 严重度 | 内容 | 影响 |
|---|---|---|---|
| F-1 | Low（过程） | `tasks/B3-context-recovery.md` 在任务卡 §3 允许清单之外（派发要求恢复记录；B1/B2 同类先例） | 不影响功能；建议合并前移入 `evidence/B3/` 或把 `tasks/*-context-recovery.md` 写入允许清单 |
| F-2 | Low（既有，非 B3 引入） | 把唯一 criterion 的 `required` 改为 false 后，`evaluate_goal` 对空必达集合返回 `satisfied=true`，即使该 criterion 证据未满足 | 需单独立条（B4/B5 或 evaluator 语义）；B3 本身正确地把记录判失效；基线行为相同 |
| F-3 | Info | B3 fixture 实际在 `fixtures/b2/{new-stable,definition-change}`，`fixtures/b3/` 只有 README/生成脚本 | 文档与目录不一致；内容符合期望 |
| F-4 | Info | 候选/PR 可见工件中没有开发侧证据包，开发自报的 anchor-a 正向 E2E 在其会话内不可得 | AC-10 由本报告独立证据满足；不阻塞 |
| F-5 | Info | `skill/project-memory/assets/verification-record.schema.json` 与 `data-contracts.md` 未描述稳定摘要/`goal_criteria_legacy_sha256`；schema `additionalProperties=true`，无运行时破坏 | `skill/` 不在任务卡允许范围，开发已披露；建议后续文档同步 |

未发现新的高危绕过：定义变更仍使记录失效；legacy 路径只豁免 evidence，不豁免定义；签名、收据、来源门禁均未放宽。

## 7. 残余风险 / NOT VERIFIED

残余风险：

1. legacy 记录若签名时 evidence 非空，追加证据后仍会失效（ADR-0004 §5 已披露，B2 正例签在 `evidence=[]` 上不受影响）。
2. criteria 顺序变化会失效：有意的定义绑定，但顺序调整属误伤面。
3. 摘要不绑定 `goal_id`/`title`；跨 Goal 由 `_verification_ok` 的 `goal_id` 检查兜底（与 B3 前一致）。
4. 回滚到 B3 前代码会使新记录失效，需要重新验证并由人类重签（ADR-0004 §5）。
5. 信任根/私钥被攻破仍可签任意记录（ADR-0003，B3 不改）。
6. F-2 的空必达集合语义（见上）。

NOT VERIFIED：

- PR #18 描述与评论、Issue #16 正文：本会话无 GitHub token（私有仓库 API 404），未独立读取；以任务卡与 PM-01 工件为准。
- 开发侧 anchor-a 正向 E2E 的原始日志：候选/PR 可见工件中不存在；本报告用 PM-01 fixture 独立重跑。
- attestation 的真实 WSL 启动器观测、人类本人 vs 持钥自动化：B2 既有边界，B3 未改变。
- Windows 符号链接拒绝路径（2 skipped，与基线相同）。

## 8. 与开发自报的差异

| 开发自报 | 复核 |
|---|---|
| 213 passed / 2 skipped，B3 10 passed | 一致（213/2；B3 10、B2 13） |
| “AC-1 anchor-a 新记录 fixture 不存在，无法 E2E” | 复核时 fixture 已由 PM-01 提供（位于 `fixtures/b2/new-stable`），独立 E2E 通过 |
| 正向 satisfied、legacy 兼容、定义变更失效 | 一致 |
| 未披露 `required=false` 时 evaluate trivially true | 复核新增 F-2（既有语义，基线同） |
| 已披露 context-recovery 越界 | 一致，维持 Low |

## 9. 污染/偏差

- `missing_artifacts`：无 GitHub token，PR #18/Issue #16 不能独立读取；开发证据包不在候选/PR 可见工件中。
- `stale_artifacts`：`pilot/STATUS.md` 仍写 B3“未开始”（历史状态）；B3 fixture 目录与 README 不一致。
- `unauthorized_reads`：无。未读开发/主管会话、终端历史、工作树；未读 `key-a.pem`。
- 偏差：正例使用 PM-01 生成的 anchor-a fixture，信任假设与 B2 相同（签名者身份未独立核验）；PASS 是程序性复核。

## 10. 最终判定

**PASS**（程序性独立复核）：新记录追加证据后 satisfied；legacy B2 正例 satisfied；定义变更仍失效；B2 门禁无回归；213 passed / 2 skipped；无自动重签、无跳过摘要检查。附带 Low 过程项（F-1）与既有 evaluator 语义项（F-2），均不改变 B3 的功能结论。

不 Approve、不合并；是否合并由人类决定。
