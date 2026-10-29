# R1 独立复核报告 — 发布门槛

- 审查者：PM-03（独立审查会话；前一同任务会话崩溃后续跑）
- 日期：2026-10-29
- 性质：**程序性独立复核，不是安全认证，不是 v1.0 GO**；合并与发布由人类决定
- 证据：`evidence/R1/review-20261029T102343Z/`（本轮自跑，清单自校验 26/26 OK）

## 1. 对象

| 项 | 值 |
|---|---|
| 任务 | R1 — 发布门槛（#19 fail-closed、openssl fail-closed、契约/README、版本 1.0.0） |
| 基线 | `85bf6a05542aa6bca3ab0d9ef51c6216f76b6080`（B4 合并） |
| 候选 | `bb06037c469b6586b95fbcd69b6965585f2c977e` |
| 任务卡 | `tasks/R1.md`，SHA-256 `5949420f784feeb1484c8b8465cec40e7646931d5ff6c0a6af865113f13131f1` |
| 任务卡提交 | `cf0da825a47e3f0f7949b1bd3e6b18d3f3af7e14` |
| PR | #32（`fix/release-gates`） |
| 复核分支 | `review/r1-bb06037` |
| worktree | `.pilot/r1-base`(85bf6a0)、`.pilot/r1-candidate`(bb06037) |

核对结果：两个 SHA 解析一致；候选是基线后代（`merge-base --is-ancestor` exit 0）；`tasks/R1.md` 哈希一致且自 `cf0da82` 未改；`tasks/` 仅新增 `R1.md` 与 `R1-handoff-*`；`evidence/B4/` 无改动；`evidence/B5B/` 仅新增 `README.md`。**无 BLOCKED 停止条件。**

## 2. 逐条 AC 表

| AC | 判据 | 本轮实测 | 证据 | 结论 |
|---|---|---|---|---|
| AC-1 | 空必达 evaluate fail closed | `evaluate` exit 0；`satisfied=false`；`evaluation_status=insufficient_evidence`；`no_required_criteria=true`；不抛异常 | `vacuous-toggle.json` / `vacuous-delete.json` | PASS |
| AC-2 | 空必达不能 achieved | `transition --to achieved` exit 1；Goal 仍 `evaluating`；无 `head.request.json`；审计新增 `rejected/goal_achieved_unsatisfied`（`no_required_criteria=true`） | `transition-refused.json` | PASS |
| AC-3 | show 可读且不误导 | `goal show` exit 0；`status_problems=[no_required_criteria]`；`effective_status=evaluating`（非 achieved） | `show-vacuous.json` | PASS |
| AC-4 | 创建约束未放宽 | 无 `--criterion` 时 exit 1，提示“Goal 至少需要一个必达的成功标准…”；仅可选判据亦被拒（单测） | `create-without-required.json`；`tests/test_security_r1.py` | PASS |
| AC-5 | 缺 openssl + 开关开启 → fail | 37 errors、0 skipped、exit 1；消息含 `openssl` 与 `PROJECT_MEMORY_REQUIRE_OPENSSL` | `openssl-missing-required.log` | PASS |
| AC-6 | 默认不变 / 有 openssl 正常 | 缺省 37 skipped exit 0；有 openssl 开关关/开各 37 passed exit 0 | `openssl-missing-default.log`、`openssl-present-switch-{off,on}.log` | PASS |
| AC-7 | openssl 文档 | README、OPERATIONS 写明开关、发布/CI 必须开启、skip≠通过、仅测试依赖 | `README.md`、`docs/OPERATIONS.zh-CN.md` | PASS |
| AC-8 | fixtures README | 6 类用例、宿主 marker、WSL2 依赖、只陈述已验证行为；与 `tests/test_security_b5b.py` 静态逐条对应 | `fixtures/b5b/README.md`（静态核对） | PASS |
| AC-9 | B5B 证据说明 | 含混合行尾观测、NUL 日志（345B/42、443B/42 实测一致）、逐文件字节校验方法、不重写历史；**但“42/42 全部命中”不可复现（实测 41/42）** | `b5b-manifest-check.log` | PASS（附 Medium 发现 F1） |
| AC-10 | 契约同步 | schema 实数 21，与 ARCHITECTURE §5 一致；audit/checkpoint 字段与代码一致；样例 0 problem，PM-03 自造真实条目亦 valid | `schema-validation.log`、`commands.jsonl` | PASS |
| AC-11 | 版本与 CHANGELOG | `pyproject.toml`、`__init__.py` 均 `1.0.0`；CHANGELOG 覆盖、含回滚；本地无 tag | `git diff`、`commands.jsonl` | PASS（远端 tag 未验证） |
| AC-12 | 回归 | 默认 253 passed/2 skipped；开关 253 passed/2 skipped；定向 57 passed；2 skip 均为 `test_security_rc3` 符号链接 | `pytest-default.log`、`pytest-require-openssl.log`、`regression.log` | PASS |
| AC-13 | 证据与交接 | 命令/退出码/JSON/两份全量日志/diffstat/sha256sums 齐备且可复现；未代下结论 | 本报告 + 证据目录 | PASS |

## 3. #19 空必达矩阵（evaluate / show / transition / create 四路一致）

在临时 Git 仓库中黑盒驱动 CLI（`python -m project_memory`），两个探针 + 一个对照：

| 路径 | evaluate | show | transition→achieved | 结论 |
|---|---|---|---|---|
| A：唯一 required 改 false | exit 0；`satisfied=false`；`insufficient_evidence`；`no_required_criteria=true`；`blocking=[]` | exit 0；`status_problems=[no_required_criteria]`；`effective_status=evaluating` | exit 1；status 仍 `evaluating`；`head.request.json` 不存在；审计 seq=4 `rejected/goal_achieved_unsatisfied`，`no_required_criteria=true` | fail closed |
| B：删除全部 required（保留 optional） | 同 A | 同 A | 同 A | fail closed |
| 对照：普通未满足（required 有证据缺失） | exit **2**；`satisfied=false`；`no_required_criteria=false` | — | — | 未被 exit-0 掩蔽 |
| create 无必达 | — | — | — | exit 1，拒绝创建 |

代码位置：`project_memory/coordination.py:1409-1413`（`no_required_criteria = not required`、`bool(required) and all(...)`，消除 `all([])` 真空真）、`:1438`（结构化字段）、`:1450-1452`（并入 `status_problems`）、`:1533`（拒绝审计携带标记）；`project_memory/cli.py:467-471`（仅 `no_required_criteria` 走 0，其余未满足仍 2）。`goal_show` 复用 `evaluate_goal`（`:1579`,`:1599`），故 show 一致。

**判定**：PASS。`evaluate` 为结构化返回而非抛异常；`load_goal` 未被改成直接拒绝读取（被改 Goal 仍可 show）；`no_required_criteria` 是机器可读字段，非仅文案。

## 4. openssl 三态矩阵（× b2/b3/b4）

| 环境 | 设置 | 结果 | exit |
|---|---|---|---|
| 无 openssl（`PATH=C:/Windows/System32`，`shutil.which('openssl')=None`） | 缺省 | 37 skipped | 0 |
| 无 openssl | `PROJECT_MEMORY_REQUIRE_OPENSSL=1` | 37 errors，0 skipped，消息含 `openssl` 与开关名 | 1 |
| 有 openssl（OpenSSL 3.5.9） | 缺省 | 37 passed | 0 |
| 有 openssl | `PROJECT_MEMORY_REQUIRE_OPENSSL=1` | 37 passed | 0 |

- 开关仅测试层：`tests/openssl_support.py` 被 b2/b3/b4 的 `setUpClass` 复用；b2/b3/b4 的 diff 仅“import + setUpClass 一行替换”，**断言与用例数未改**。
- 无默认注入：仓库无 `conftest.py`/`pytest.ini`；`PROJECT_MEMORY_REQUIRE_OPENSSL` 仅出现在 tests 与文档；`pyproject.toml` `dependencies=[]`，`project_memory/` 无 openssl 子进程调用 → 无运行时依赖。

**判定**：PASS（双向正确）。

## 5. 契约核对

- schema 计数：`skill/project-memory/assets/*.schema.json` = **21**，与 `docs/ARCHITECTURE.zh-CN.md:198`“共 21 份”一致（新增 `criterion-evidence`、`audit-ledger`）。
- `goal_criteria_sha256` 语义：`_criteria_definition_digest` 只覆盖 `id/statement/required`（`coordination.py:245-251`）；`_criteria_digest_matches` 兼容旧“整份 criteria / evidence=[]”摘要（`:254-272`）。文档描述与实现一致（ADR-0004 存在）。
- `audit-ledger.schema.json`：`verification_attempt` 必填 `schema_version/kind/seq/timestamp/prev_hash/entry_hash/outcome/reason`；`audit_checkpoint` 必填字段与 `_checkpoint_payload`（`:655-661`）及 `attach` 的 `authority{status,anchor_id,issuer,algorithm,signed_payload_sha256,signature_b64}`（`:710-714`）逐项吻合；`status const "achieved"` 与 `AUDITED_GOAL_STATUSES={'achieved'}` 一致。
- 样例校验：dev `validate.py` 复现 0 problem；PM-03 **自造**真实拒绝条目（14 字段）经 Draft 2020-12 校验 valid。

**判定**：PASS。

## 6. 历史证据检查

- R1 清单：`tr -d '\r' < evidence/R1/20261029T083252Z/sha256sums.txt | sha256sum -c -` → **36/36 OK**，exit 0。
- 不重写字节：对 `evidence/R1/**` 全部 37 个受控文件，`git hash-object --path=<p> <p>` 与 `git rev-parse HEAD:<p>` **37 MATCH / 0 MISMATCH**。
- B5B 未改：`git diff --name-status 85bf6a0..bb06037 -- evidence/B5B/` 只有 `A evidence/B5B/README.md`；既有文件哈希与 HEAD 一致，最新提交仍为 B5B 的 `78b8394`。B4 证据零改动。
- B5B README 校验方法实测：42 项中 raw 命中 29、LF 归一化 17、git blob 19，**至少命中一种 = 41/42**；`environment.txt` 三种表示**全部不命中**（详见发现 F1）。README 记录的 29/17/19 计数完全吻合，说明方法本身有效；“42/42”结论不可复现。两个 NUL 日志 345B/42、443B/42 与 README 完全一致。

**判定**：PASS（R1 未改历史证据；README 计数误差见 F1）。

## 7. 文档可执行性

- `README.md` / `docs/OPERATIONS.zh-CN.md` 的 `PROJECT_MEMORY_REQUIRE_OPENSSL=1 python3 -m pytest -q` 按原样执行 → exit 49、无输出：本机 `python3` 是 Microsoft Store 别名桩（环境产物，非产品缺陷）。以真实解释器跑等价命令 → `pytest-require-openssl.log` 253 passed/2 skipped exit 0；`python -m pytest -q` 默认同样 253/2。
- `fixtures/b5b/README.md` 与 `tests/test_security_b5b.py` 静态逐条对应：默认拒绝 exit 3 / 双 flag exit 3 / 显式 local exit 0+marker+`local_untrusted` / trusted 沙箱路径 inner exit 0+`marker-written`+宿主 marker 不出现 / trusted 宿主路径 `marker-write-failed` / trusted 不可用 exit 3 BLOCKED 不回退。`marker-command.py` 行为（缺参 exit 2、写失败 exit 1、成功 stdout `marker-written:` exit 0）与 README 一致。**未执行 `--trusted` 的不可信代码**（按要求静态核对）。

**判定**：PASS（windows `python3` 环境限制已在证据中注明）。

## 8. 回归

| 命令 | 结果 | exit |
|---|---|---|
| 默认全量 `pytest -q -p no:cacheprovider -rs` | 253 passed, 2 skipped | 0 |
| `PROJECT_MEMORY_REQUIRE_OPENSSL=1` 全量 | 253 passed, 2 skipped | 0 |
| 定向 b5b/b5a/b3/b2/b4 | 57 passed | 0 |

2 个 skip 均为 `tests/test_security_rc3.py:284/295`“当前平台不允许创建符号链接”，非签名测试。测试未见删除/跳过/断言改动（`tests/` diff 仅 b2/b3/b4 的 setUpClass 收敛与两份新文件）。

## 9. 新发现（按严重度）

**F1（Medium）— `evidence/B5B/README.md` 的“42/42 全部命中”不可复现。**
- 实测 41/42：`receipts/.../environment.txt` 的清单哈希 `d4f6d19f…` 与工作树原始字节（`44c6eba…`）、LF 归一化（`a78b12e…`）、git blob（`a78b12e…`）**均不相等**；行尾变体、BOM、尾随换行、CR-only 等额外表示亦不命中。
- 该文件由 B5B 提交 `78b8394` 引入，**R1 未改动**（对基线 diff 为空、blob 与 HEAD 一致）。说明这是 B5B 阶段“清单生成后文件被改写/清单陈旧”的既有字节漂移，被 R1 新增 README 的经验性断言放大。
- 影响：R1 的 fail-closed/openssl/回归门禁均不受影响；但 AC-9“只陈述已验证/可复现行为”存在一处计数夸报。README 自身 §3 已写明“三项都不命中的文件才需要人工解释”，正与 `environment.txt` 相符。
- 建议（不在本轮改代码/证据）：把 README 计数改为 41/42，并把 `environment.txt` 列为需人工解释项；不要为凑 42/42 重写清单或证据。是否回查 B5B 生成过程属 B5B 后续事项，非 R1 阻断。

**F2（Low）— 文档命令使用 `python3`，本机 Windows 不可执行。**
- 这台机器 `python3` 为 Store 别名桩（exit 49）。文档面向 POSIX `python3` 无误，但发布检查者若在同类 Windows 环境按原样执行会误判；建议文档补一句“Windows 用实际解释器/Anaconda 路径”。等价命令已全部通过。

**F3（Info）— 空必达 exit 0 与并存缺陷。**
- `cli.py` 对 `no_required_criteria` 恒返回 0（AC-1 明确要求）。若同一 Goal 同时存在 open high 缺陷，exit 0 仍成立，但结构化输出保留 `open_high_defects`；仅看退出码的调用方可能漏读。属 AC-1 既定取舍，记录为残余风险，不作为阻断。

## 10. 残余风险 / NOT VERIFIED

- **远端 tag/Release 与 PR #32 实时状态**：本会话无 GitHub 凭据，未直连 API。本地 `git tag` 在候选上无 tag；远端 tag 状态 NOT VERIFIED。
- **POSIX 实装 / CI 配置**：任务明示不在范围，未验证。
- **生产 anchor-a 端到端 checkpoint 签名**：不在范围，未执行；checkpoint 契约仅做静态比对 + 样例校验。
- **`fixtures/b5b` 的 `--trusted` 真实执行**：按要求未运行不可信代码，仅静态核对。
- **B5B `environment.txt` 字节漂移的成因**：属 B5B 历史，未回溯；仅确认 R1 未改动它。

## 11. 与开发自报的差异

- AC-6 计数：开发自报“任务卡写 82、实测 37”，本轮对 b2/b3/b4 三文件同样收集 **37**，一致（82 含额外文件的旧口径）。
- AC-9：开发自报“42/42 至少命中一种表示”，本轮实测 **41/42**（`environment.txt` 全不命中），其余 29/17/19 计数一致。这是与自报的唯一实质偏差（F1）。
- 其余 AC 观测与交接文档一致。

## 12. 最终判定

**PASS**（程序性独立复核，非安全认证、非 v1.0 GO；合并由人类决定）。

理由：空必达两条路径在 evaluate/show/transition 三处一致 fail closed，create 约束未放宽；openssl 开关双向正确且仅影响测试、无运行时依赖、未进默认配置；契约（schema 计数/字段/样例）与实现一致；R1 未改写历史证据（哈希链 37/0、清单 36/36）；默认与开关全量 253+2、定向 57 全绿；无新高危绕过。唯一实质偏差为 F1（B5B README 计数 41/42），系文档计数问题且不触及证据字节或门禁逻辑，建议合并前顺手订正，不构成 FAIL 条件。

## 13. 污染 / 偏差 / 接手耗时

- 前一会话在“准备证据目录与环境记录”时崩溃；其未跟踪草稿 `evidence/R1/review-20261029T101815Z/` **保留未删、未提交**，仅作定位线索，本轮所有结论均由自跑探针独立得出（已逐项重跑 evaluate/show/transition/create 与 openssl/回归）。
- 本轮首次运行探针时修正了自身驱动脚本的一处 worktree 路径错误（失败于创建前，无结果产出），随后重跑；不影响结论。
- `python3` 桩导致的文档命令 exit 49 为环境差异，已用真实解释器等价执行。
- 未读取开发/主管聊天或终端历史；未读生产 anchor/私钥；未使用 `project-memory-mvp`；未联网。
- 接手耗时（读提示词+材料+恢复环境到开始产出）：约 14 分钟。
