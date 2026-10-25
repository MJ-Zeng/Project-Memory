# Project Memory v0.3 评估

日期：2026-10-25
范围：目标驱动的多 Agent 工程协作（Goal、Agent Run、独立验证、缺陷、知识对账）
代码分支：`feat/v0.3-goal-memory`（未推送、未合并）
测试：74 项通过，0 失败，0 错误（本机约 29 秒）

## 1. 结论

v0.3 的 P0 已经在本地真实可运行，不再是设计稿。Goal、执行记录、检查点、恢复、独立验证、缺陷生命周期和对账都有 CLI、schema、状态机和测试。一次本地端到端实验走完了“失败 → 缺陷 → 修复 → 复验 → 对账”，但对账在更新后仍只剩一个 low 级文档提醒。

但这不等于跨模型协作已经验证。**跨模型续接是 NOT RUN**：实验只用了 `auto` 模型的多个独立会话，Qoder CN 需要人在界面里切换模型。外部 GitHub、CI、review 和真实人工审批也都是 NOT RUN。下面的结论按证据边界分开写。

## 2. v0.2 审计

在开始 v0.3 前检查了仓库的代码、测试和记录，而不是只看 README：

- 仓库实际稳定在 v0.1 契约：1.1 task context、agent handoff、completion report，以及 `finish` 门禁。
- 没有 v0.2 的 Goal、Agent Run、Verification Record 或 reconcile 实现；也没有对应 schema 和测试。
- 因此 v0.3 直接补在 v0.1 的可用基础上，没有假装 v0.2 已经完成。

这避免了在未经验证的设计上继续叠加。v0.3 的每个新能力都以可执行命令和测试为准。

## 3. 交付内容

- 新增 6 个记录 schema：`goal`、`agent-run`、`run-checkpoint`、`verification-record`、`defect`、`knowledge-reconciliation`；更新 `agent-handoff` 和 `completion-report`。
- 新增 CLI：`goal create/show/transition/evaluate/evidence`、`run start/checkpoint/resume/finish/show/list`、`verify`、`defect list/show/update`、`reconcile`、`sync-tooling`。
- 状态机：Goal 7 个状态、Run 8 个状态、Defect 5 个状态；非法转换在写入前拒绝。
- 恢复：1.2 handoff、编号检查点、`run resume` 的 `resume_ready` / `needs_handoff` / `needs_human` / `stale_base` / `verified`。
- 独立验证：验证记录与执行记录分离；验证者必须是 `role=verifier`，且 agent/model/session 至少一项不同；证据级别与可信级别分开。
- 对账：Goal → Run → Verification → Defect → ADR → 文档；只报告，不自动改 canonical 文档。

详细契约在 `skill/project-memory/references/data-contracts.md`，工作流在 `workflows.md`，测试结果在 `docs/TEST_REPORT.md`。

## 4. 逐项回答

### 4.1 跨模型续接真的发生了吗？

**NOT RUN。**

实际发生的是：`auto` 模型的多个独立会话，由不同 run ID、不同会话 ID 记录，并通过 1.2 handoff 接续。这可以证明“同模型、跨会话”的记录链和恢复包可用，不能证明“换模型”可用。

Qoder CN 的 `create_chat_session` 没有模型参数；模型切换必须在客户端界面手动完成。本地确认存在的模型标识只有 `auto`、`dfmodel`（DeepSeek-Flash）、`qfmodel`（Qwen3.8-Flash）；`dfmodel`/`qfmodel` 没有在本次实验中实际切换。GLM、Kimi、MiniMax 等未验证。

如果你要继续这个实验，具体动作是：

1. 在 Qoder CN 界面新建会话，手动选择 `dfmodel` 或 `qfmodel`。
2. 在新会话里运行 `run resume --task local-auth-1`，读取 handoff 和检查点。
3. 用新的 run ID 登记，`--model-id` 填界面实际显示的模型。
4. 任何人不能替你在记录里填写“已切换模型”。

在这一步之前，任何“跨模型已验证”的说法都不成立。

### 4.2 中断恢复是否可用？

**PASS（本地范围内）。**

已验证：编号检查点幂等、结束后拒绝写入；没有 handoff 的活跃执行可以用最近检查点恢复；1.2 handoff 恢复时带出 completed/remaining/next_actions/tests；1.1 旧 handoff 可读但降级警告；base 不在当前历史时报 `stale_base`；执行标为 verified 但提交已漂移时报 `needs_human`；默认只选 executor，不把 verifier 当接手者。

未验证：断电、进程被杀、多个操作系统进程同时写、跨机器恢复。不能把本地 `resume_ready` 当成生产级恢复保证。

### 4.3 未验证声明能被发现吗？

**PASS（结构性声明），有明确上限。**

当前会拒绝或报告：

- `agent_claimed` 永远不能产生 pass；
- 同一个 run、同一个 agent/model/session 自验；
- 验证者没有 `role=verifier`；
- 验证记录跨 Goal 复用；
- 代码变化后继续使用旧 pass；
- high 缺陷存在时给 pass；
- `--resolves-defect` 失败却留下可用 pass；
- 缺陷被手工改成 `verified`，没有有效验证记录；
- run 的非法状态转换；
- 测试日志为空、不存在、是 URL 或 canonical 文档。

上限：CLI 不联网核对 CI 和 review，`externally_verified` / `human_approved` 只记录调用方声明并标为 `declared_unfetched`。它也不能判断日志内容是否真实覆盖了风险。要抓取真实 CI 和 review，需要 GitHub token、网络和仓库权限；目前是 NOT RUN。

### 4.4 独立 QA 是否发现了真实问题？

**是，而且不是风格问题。**

人工指定的只读 QA 会话在 61 项测试全部通过后检查实现，报告了 16 个问题：5 个 high、7 个 medium、4 个 low。高风险项包括：

1. 自验只检查 run ID，同 agent/model/session 也能通过；
2. 验证记录可以跨 Goal 复用；
3. pass 在提交漂移后仍满足 Goal；
4. 失败的 `--resolves-defect` 已写入可用 pass；
5. 缺陷可以手工改成 `verified`，没有验证记录。

全部修复并补了回归测试，测试从 61 项增加到 74 项。修复清单和对应测试在 `docs/TEST_REPORT.md` 的“独立 QA 发现与修复”。这证明“测试全绿”本身不足以证明实现正确。

### 4.5 基于证据的 Goal 评估是否有效？

**PASS（本地、记录层面）。**

评估只看成功标准和证据，不看 Issue 是否关闭。证据会重新检查提交是否在当前历史、验证是否绑定当前 HEAD、执行是否仍为 verified、测试日志是否存在且非空。达成的 Goal 必须经人工 `approved_by`，Agent 不能自己把标准改掉或把目标标成 achieved。

上限：评估判断“证据记录是否成立”，不判断“证据是否真的支持结论”。例如一份真实的测试日志可能只测了无关路径。要判断语义正确性，仍需独立验证者或人。

### 4.6 重复上下文和重复工作减少了吗？

**NOT MEASURED。**

结构上，1.2 handoff 把 head SHA、改动文件、测试、剩余工作和下一步放在一个恢复包里，减少了重新翻找的范围；检查点也避免每次从零开始。但本次没有做 A/B 对照，没有测 token 数、耗时或重复阅读量，因此不能声称“减少了 X%”。

同模型多会话实验只能说明记录链能接上，不能说明跨模型时上下文损失更小。要回答这个问题，需要至少两组任务：有无 Project Memory 各一组，记录人工介入次数、token 和返工次数。

### 4.7 还有哪些必须人工？

- 在 Qoder CN 界面切换模型；
- 批准 Goal 从 `proposed` 到 `approved`、从 `evaluating` 到 `achieved`；
- 修改已批准的成功标准；
- 接受 ADR；
- 批准架构、安全、认证、权限、schema、数据迁移和生产变更；
- 合并 PR、关闭重要 Issue、部署生产；
- 配置 GitHub token、分支保护、CODEOWNERS、CI；
- 提供并核对真实 CI/review 证据；
- 审查 Skill 和 CLI 的修改；
- 处理多个活跃 executor 的冲突；
- 判断验证结论在语义上是否成立。

本次实验中的 Goal 批准是“实验自批”，不是真实审批，已在测试报告中标注。

### 4.8 架构是否过度设计？

**P0 没有明显过度设计，但已经接近上限。**

每个 P0 实体都对应一个真实失败模式：Goal 对应“Issue 关闭但目标没达成”；Run 对应“换会话后不知道做到哪”；Checkpoint 对应“中断后丢失上下文”；Verification 对应“Agent 自报通过”；Defect 对应“验证发现问题后没有闭环”；Reconcile 对应“记录之间互相矛盾”。这些不是为将来预留的抽象。

成本主要来自状态机、信任级别和引用完整性检查。它们让实现比“写几个 JSON”复杂，但也正是 QA 找到的问题所在。真正应该警惕的是继续增加实体和自动调度；P1/P2 目前没有足够证据支持。

### 4.9 v0.4 的自动编排值得做吗？

**现在不值得直接做调度器。**

建议顺序：

1. **先做一次真实的跨模型实验。** 两个模型、手动切换、同一 Goal、独立验证；记录 token、耗时、人工介入和 handoff 丢失的信息。没有这组数据，编排没有依据。
2. **再做真实的 GitHub/CI 只读适配。** 用最小权限 token 读取 Issue、PR、checks、review；把 `externally_verified` 从声明升级为可追溯证据。仍然不自动合并、不关闭、不部署。
3. **补人工审批的可验证载体。** 例如要求审批人通过 GitHub review 或签名记录批准，而不是让 CLI 接受任意 `approved_by` 字符串。
4. **只在观察到真实并发冲突后加锁。** 当前是多写者约定加乐观检查；没有分布式锁。不要为了假设中的并发引入服务端组件。
5. **自动编排保持设计稿。** 只有 Qoder CN 提供可授权的模型选择/会话编排接口，并且有真实跨模型数据支持时，才值得实现 Mode C。

v0.4 的优先级应是“把外部证据接进来”，不是“加一个调度器”。

## 5. 真实实验记录

仓库：`C:\Documents\02_Research\Code\project-memory-v03-lab`
提交：`ec5c031`（含授权绕过）→ `7d78b7e`（第一轮修复）→ `3250269`（第二轮修复）
模型：`auto`，多个独立 Qoder 会话
证据目录：实验室的 `experiment/`

- Goal `G-AUTH`：修复授权绕过，3 条成功标准。
- `run-dev-1` 第一轮执行；`VER-63c883e7c934` 验证 fail；生成 high 缺陷 `DEF-1b77a3e93a52`。
- `run-fix-1` 修复；`VER-f17891e6cdd3` 验证 pass；缺陷转 verified。
- `run-verify-1`、`run-verify-2` 为 verifier run，不参与“多个活跃 executor”的对账。
- 最终 `goal evaluate`：C1/C2/C3 全部 satisfied，`blocking: []`。
- 最终 `run resume --task local-auth-1`：`verified`，选中 `run-fix-1`，当前验证为 `VER-f17891e6cdd3`。
- 最终 `reconcile`：0 high、0 medium、1 low（`docs_entry_doc_unverified`）。

实验边界：

- 没有切换模型；没有真实 GitHub/CI/review；没有人类批准 achieved。
- 实验中的 verifier 角色是在功能加入后回填的，已在记录中保留真实会话信息。
- Goal 记录生成于“批准持久化”缺陷修复之前，`approved_by` 为空；没有回溯改写它，修复后的行为由 `test_goal_requires_criteria_and_approval` 覆盖。
- 实验使用更新后的 vendored tooling 重新跑了 evaluate/resume/reconcile；输出在 `experiment/34-*`、`35-*`、`36-*`。

## 6. 安全审查

已实现：

- GitHub token 只从环境变量读取，错误信息不包含 token；测试覆盖。
- 执行记录不保存 `model.key`，CLI 没有 `--model-key`。
- 新命令默认离线，不访问网络，不写 canonical 文档，不合并、不关闭 Issue、不部署。
- 路径使用安全化组件，任务 ID 含冒号不会在 Windows 上穿透或崩溃。
- 写文件使用原子 no-clobber；记录用 revision 乐观检查。
- 验证日志必须是本地、非空、非 canonical 的证据类文件。
- 外部 CI/review 只接受 http(s) URL，并明确标记未抓取。
- `reconcile` 只报告，不自动修复。

残余风险：

- `approved_by` 仍是调用方字符串，CLI 不能认证审批人身份。
- 本地日志可以被伪造；CLI 不能证明测试真的运行过。
- `.project-memory` 记录可能包含仓库路径和缺陷位置，但不是凭据；仍应按内部资料管理。
- 没有加密、签名或防篡改存储；能写文件的人可以改记录，对账只能发现部分不一致。
- 真实 GitHub/CI 接入尚未做权限最小化验证。

## 7. 兼容与迁移

- 1.1 handoff 仍可读；1.2 由 `run finish` 生成。
- 同一 run 已有 1.1 handoff 时不能原地升级，必须使用新的 run ID；不批量改写历史。
- 旧的 `model.key` 字段仍可被读取；新记录不再写入。实验数据中的空 `key` 没有泄漏。
- `completion-report` schema 放宽为接受字符串或整数 `task`、可空 `base_sha`，与代码输出一致。
- `failed -> verified` 被加入 Run 状态机，用于缺陷修复后的复验；其余转换保持严格。
- 新增命令是附加的；没有改动 v0.1 的 init/audit/start/handoff/finish/graph/search 行为。
- 现有 CLI 选项未删除；`--model-key` 只存在于 v0.3 开发过程中，没有发布，因此不构成破坏性变更。

## 8. 修改文件

新增：

- `project_memory/coordination.py`
- `skill/project-memory/assets/goal.schema.json`
- `skill/project-memory/assets/agent-run.schema.json`
- `skill/project-memory/assets/run-checkpoint.schema.json`
- `skill/project-memory/assets/verification-record.schema.json`
- `skill/project-memory/assets/defect.schema.json`
- `skill/project-memory/assets/knowledge-reconciliation.schema.json`

修改：

- `project_memory/cli.py`
- `project_memory/common.py`
- `project_memory/workflows.py`
- `project_memory/bootstrap.py`
- `skill/project-memory/SKILL.md`
- `skill/project-memory/assets/agent-handoff.schema.json`
- `skill/project-memory/assets/completion-report.schema.json`
- `skill/project-memory/references/{data-contracts,workflows,governance,onboarding,document-authoring}.md`
- `tests/test_project_memory.py`
- `README.md`
- `docs/ARCHITECTURE.zh-CN.md`
- `docs/OPERATIONS.zh-CN.md`
- `docs/TEST_REPORT.md`

实验仓库的修改只在其自身的未跟踪工作区；没有提交到本仓库，也没有推送。

## 9. 下一步

1. 由人审查本分支的 Skill 和 CLI 变更；在此之前不合并。
2. 完成一次真实的双模型手动切换实验，记录 token、耗时、返工和 handoff 丢失项。
3. 配置最小权限 GitHub token，接入真实 Issue/PR/checks/review 只读证据；在此之前保持 `externally_verified` 为声明。
4. 如果并发冲突真的出现，再决定是否加跨进程锁；不要先建服务。
5. 继续保留“不自动合并、不自动关闭、不自动部署”的边界。
