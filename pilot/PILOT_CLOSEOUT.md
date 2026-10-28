# Project Memory 多 Agent 协作试点 — 收尾报告

- 日期：2026-10-28
- 范围：B0 / B1 / B2 三轮真实任务
- 结论：**试点目标（三轮协作）已完成，但有限制；v1.0 未 GO。**
- 本报告是程序性总结，不是安全认证，也不代替人类对产品的发布决定。

---

## 1. 一句话结论

Project Memory 已经能支撑**三个独立会话、通过仓库工件协作、完成有边界的真实安全修复**：开发交付、独立复核、人类合并的链路跑通了三次，复核确实抓到了开发没报告的问题，整改后通过。

但它**没有**证明效率提升、身份隔离、自治安全审批或 v1.0 可发布；这些仍是产品后续工作。

---

## 2. 试点目标与方法

目标：验证 PM 是否能作为多 Agent 的“项目记忆 + 交接”系统，而不是编排平台。

方法：

- 三个独立 Clone/会话：PM-01 主管、PM-02 开发、PM-03 审查；
- 同一私有 GitHub 仓库、同一台 Windows、同一 OS 用户/SSH key/GitHub 账号；
- 角色由提示词自述，**不是**认证；
- 每轮：Issue/任务卡 → 派发 Handoff → 开发候选 → 独立复核 → 整改（如有）→ 人类合并；
- 证据分级：E0 自报、E1 本地、E2 独立复核、E3 人类决定；
- 分支保护：Require PR、0 approvals、Merge only、禁 force push/删除；人类合并是程序性约束，不是 GitHub 强制。

---

## 3. 三轮结果

| 轮次 | 问题 | 候选 | 复核 | 合并 | 测试 |
|---|---|---|---|---|---|
| **B0** | 执行收据 `repo_id` 绑定绝对路径，复制仓库后失效（P-1） | `8506dd4`（B0.1） | PM-03 PASS（`review/b0-8506dd4` @ `b1e977c`） | PR #5 → `a70ad19` | 164 passed / 2 skipped |
| **B1** | 验签器可被 PATH/环境变量替换 | `1c7ad94` | PM-03 PASS（`review/b1-1c7ad94` @ `09f68d8`） | PR #9 → `15f4b3c` | 190 passed / 2 skipped |
| **B2** | 有效签名可包裹伪造执行收据 | `004a35b` | PM-03 PASS（`review/b2-004a35b` @ `6cbdc76`；逻辑 28/28 + anchor-a E2E 4/4） | PR #14 → `5a5abddf` | 203 passed / 2 skipped |

补充：

- B0 首轮被 PM-03 判 NOT VERIFIED，发现 F-2（验证映射仍绑路径）；B0.1 整改后才 PASS。这是试点最有价值的一次“复核抓到开发遗漏”。
- B1 复核发现 D-B1-R1-01（审查证据清单 CRLF/GBK 不可自校验），整改后 18/18 OK；另发现 `PYTHONPATH`/cwd 同名模块顶替 HIGH，超出 B1 范围，未修。
- B2 复核先判 NOT VERIFIED（缺 anchor-a E2E），补 fixture 后 PASS；但 AC-3 的 `goal evaluate satisfied=true` 子项仍留给 B3，人类已接受该 scope split。

---

## 4. 试点证明了什么

1. **工件足以支撑冷启动**：PM-02/PM-03 在独立会话中通过 `pilot/`、任务卡、Handoff、ADR、证据恢复任务；B1 的 CRR 为 6/6（PM-02 10 分钟、PM-03 8 分钟）。
2. **独立复核有实际价值**：B0 的 F-2、B1 的 D-B1-R1-01、B2 的 E2E 缺口，都是开发自报里没有或不愿定级的；复核改变了合并决定。
3. **“证据等级”能约束声明**：PM-02 没有把 NOT VERIFIED 写成 PASS；PM-03 没有用开发日志代替复现；B2 逻辑级通过但 E2E 缺失时，整体仍判 NOT VERIFIED。
4. **人类合并门禁可运行**：三次合并都由人类决定；Agent 没有自行合并、没有宣布 Goal `achieved`。
5. **失败关闭有效**：B2 两个伪造 case 在真实 anchor-a 下被来源门禁拒绝；B1 的 PATH/env 替换被拒；B0 的跨路径/跨仓库收据按身份判断。

---

## 5. 试点没有证明什么

1. **效率**：n=3，无对照组、无工时基线；不能声称“更快”或“更省人”。
2. **身份隔离**：三个角色同一 OS 用户、同一 SSH key、同一 GitHub 账号；角色标签是自述，不是认证。
3. **自治安全审批**：分支保护 0 approvals；同账号 Agent 技术上可自合并；人类批准是程序性的。
4. **真实受保护执行**：B2 的 attestation 隔离字段是签名者断言；真实 WSL `trusted_exec` 启动器未运行；真实人类签名例外未区分“人类本人”。
5. **跨机器/跨组织/长期记忆**：只在一台 Windows、一个私有仓库、三个本地 Clone 上验证。
6. **v1.0 可发布**：B3/B4/B5、WSL_EXE、发布工程、人工审批链都未完成。

---

## 6. 指标（描述性，n=3，不推导效率）

| 指标 | 观察 |
|---|---|
| 完成轮次 | 3（B0/B1/B2）；另有 B0.1 整改 |
| 合并 | 3 次 Merge commit；0 次 Agent 自合并 |
| 测试 | 164 → 190 → 203 passed；每轮 2 skipped（既有 Windows symlink） |
| CRR 冷启动复述 | B1：PM-02 6/6（10 分钟）、PM-03 6/6（8 分钟）；B2：PM-02 约 10 分钟 |
| RQ 补问率 | B1：0/2 次交接需要补问 |
| HR Handoff 完整率 | B1：27/27 |
| IR 独立复现率 | B1：AC-1..AC-11 全部由 PM-03 重跑；B2：逻辑 28/28 + E2E 4/4 |
| DY 审查发现 | B0：F-2（阻断）；B1：1 HIGH（范围外）+ 1 LOW + 1 INFO；B2：0 阻断 + 6 Low/Info |
| 任务结果 | B0 PASS、B1 PASS、B2 PASS（AC-3 evaluate 子项留给 B3） |

这些数字只说明“这三轮发生了什么”，不能外推为产品性能。

---

## 7. 仍然阻塞 v1.0 的事项

1. **B3**：正向流程自失效；正是 B2 AC-3 的 `goal evaluate satisfied=true` 子项。
2. **B4/B5**：按 RC3 清单；含默认 `test-run` 隔离、`WSL_EXE`、执行来源的真实观测。
3. **`PYTHONPATH`/cwd 同名 `project_memory/` 顶替 HIGH**：B1 复核发现，范围外，未修；应单独立条或并入 B5。
4. **人类身份/审批**：`issued_by` 是字符串；没有独立人身份核验；0 approvals 的分支保护不能强制人类批准。
5. **文档不一致**：`skill/project-memory/references/data-contracts.md:74` 仍写 `target_repository` 可为仓库名；任务卡 AC-8 的“147”是过期数字。
6. **Release/部署**：没有 tag、没有发布验证、没有回滚方案。
7. **Agent GitHub 访问**：PM-02/03 无 token，PR/评论/Issue 依赖 PM-01 转发；这削弱了角色边界。

---

## 8. 过程建议

1. **给 Agent 只读 GitHub token 或 Issue/PR 镜像**；至少让 PM-03 能独立读 PR/Issue，减少 PM-01 代述。
2. **任务卡的 AC 按轮次拆开**：B2 的 AC-3 把 B3 的 `evaluate` 写进来，导致后验 scope split；下一轮派发前先做 AC 归属检查。
3. **允许路径要可执行**：`context-recovery-*.md` 连续两轮越界；要么写入允许清单，要么在门禁里拒绝。
4. **状态更新与代码同 PR**：`pilot/STATUS.md` 多次滞后；收口时统一更新。
5. **model/session 字段只作自报**：B2 Handoff 写 `qoder/qoder-desktop-agent`，与当前环境不一致；不要当认证。
6. **人类合并门禁写进协议**：0 approvals 下，Agent 技术上可自合并；必须明确“Agent 不合并、人类点击”是程序约束。
7. **不要把逻辑级 PASS 写成整体 PASS**：B2 的处理是正面例子——逻辑 28/28 仍判 NOT VERIFIED，补 E2E 后才 PASS。
8. **fixture/key 流程要前置**：B0.1/B2 都因 anchor 所有权/签名 fixture 多花一轮；下一轮在派发前准备 anchor-a fixture。

---

## 9. 最终判定

- **试点目标：完成（3 轮，有限制）。**
  PM 能支撑有边界的真实安全修复，能留下可冷启动的工件，独立复核能改变结论，人类合并门禁可运行。
- **v1.0：NO-GO。**
  B3/B4/B5、模块顶替 HIGH、真实执行隔离、人类身份/审批、发布工程未完成。
- **适用边界：**
  适合“有明确任务卡、可独立复核、人类最终合并”的内部/受控项目；
  不适合“无人监督的安全审批”“跨组织身份隔离”“以效率为唯一目标的自动化”。
- **下一步：**
  产品侧先做 B3，再做 B4/B5 与模块顶替 HIGH；试点侧不再开新轮次，除非人类另行授权。

---

## 10. 主要工件索引

| 工件 | 位置 |
|---|---|
| 试点策略 | `import-workspace/MULTI_AGENT_VALIDATION_STRATEGY.md` |
| 试点计划 | `import-workspace/MULTI_AGENT_PILOT_PLAN.md` |
| B0 复审 | `review/b0-8506dd4` → `pilot/review/B0/REVIEW-B0.1.md` |
| B1 复审 | `review/b1-1c7ad94` → `pilot/review/B1/REVIEW-B1.md` |
| B2 复审 | `review/b2-004a35b` → `pilot/review/B2/REVIEW-B2.md` + `REVIEW-B2-E2E.md` |
| B2 E2E fixture | `verification-lab/fixtures/b2/` |
| B0/B1/B2 收口 | `pilot/rounds/{B0,B1,B2}/handoff-close.md` |
| 当前状态 | `pilot/STATUS.md` |
| 接续入口 | `import-workspace/PM01_RESUME_HANDOFF.md` |
