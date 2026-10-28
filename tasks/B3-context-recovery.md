# B3 上下文恢复（PM-02 Developer）

- 恢复时间：2026-10-28T14:05Z 左右（本地 UTC）
- 接手分钟数：约 14 分钟（只读恢复 + 任务卡哈希校验 + WSL fixture 复现）

## 1. 六项事实

1. **任务**：B3 — 证据附件不得使已签名验证失效。`goal evidence` 追加 evidence 后，验证记录的 `goal_criteria_sha256`（旧全量摘要）不再匹配，`goal evaluate` 返回 `satisfied=false`。这是 B2 AC-3 的遗留子项。
2. **基线**：`832f2710bfde1cbc498ee6882a5e10b797db6a76`（PR #17 merge；`dev/v1.0` HEAD）。
3. **允许范围**：`project_memory/coordination.py`、`project_memory/common.py`、`tests/`、`docs/decisions/`、`docs/` 中与 criteria digest/evidence 语义相关的契约文档、`evidence/B3/`；候选分支仅 `fix/b3-stable-criteria`。
4. **AC 编号**：AC-1 正向 evaluate satisfied；AC-2 不重新签名/记录字节不变；AC-3 legacy B2 正例仍可用；AC-4 改 criterion 定义仍失效；AC-5 改 evidence 不失效（新记录）；AC-6 B2 来源门禁不回归；AC-7 全量回归；AC-8 兼容/迁移路径；AC-9 ADR；AC-10 证据可复现；AC-11 独立复核；AC-12 范围纪律。
5. **当前分支**：`dev/v1.0`（干净，与 `origin/dev/v1.0` 同步）；将创建 `fix/b3-stable-criteria`。
6. **下一步**：写 ADR-0004 → 实现稳定判据摘要 + legacy 兼容 → 新增测试 → anchor-a E2E（legacy 正例/伪造 case）→ 证据包与 Handoff → 推送并开 PR（不合并）。

## 2. 校验结果

- `tasks/B3.md` SHA-256 = `89b2d31b4dd604a384e3cc42531b2b8e47ae39e6be290ebdcde503dff8cef8bc`，与派发一致。
- Issue #16 本会话无 GitHub token，无法独立读取；以任务卡与派发链接为准（见 `pilot/rounds/B2/handoff-close.md` 的已知限制）。
- 基线 `git log` 首条为 `832f271 Merge pull request #17 from MJ-Zeng/chore/b3-task`。

## 3. 复现（先于代码）

- 复制 `fixtures/b2/genuine-trusted/repo` 到 WSL `/tmp/b3-legacy`，未改动 fixture。
- `goal evidence` exit 0；`goal evaluate` exit 2，`satisfied=false`，reason `VER-B2-genuine-trusted 针对的不是当前提交或执行已失效`。
- 验证记录字节哈希在 `goal evidence` 前后一致（fixture 的 Goal 被改，记录未被改）。
- 证据：`evidence/B3/run-20261028T135956Z/`。

## 4. 必须询问/需要人类知道的问题

1. 任务卡 §7 要求 `fixtures/b3/new-stable`（PM-01 用 anchor-a 签名的“稳定摘要”新记录），当前**不存在**。PM-02 不读 key-a、不自行签名，因此 AC-1 的 **anchor-a 新记录 E2E** 无法由本会话完成；本会话用测试期临时 RSA 密钥做逻辑级正向验证，并用 anchor-a legacy fixture 做真实锚 E2E。请审查者/人类决定是否补 fixture。
2. `tasks/B3-context-recovery.md` 由派发指令第 1 节明确要求，但任务卡 §3 允许修改清单未列 `tasks/`；若按 AC-12 判越界，可在合并前移入 `evidence/B3/`。
3. 契约文档 `skill/project-memory/references/data-contracts.md` 含 digest/evidence 语义，但位于 `skill/` 而非任务卡允许的 `docs/`；本会话不改，作为 NOT_VERIFIED/范围外披露。

## 5. contamination

- none。未读取主管/审查者会话、终端历史或工作树；未读取 `/etc/pm-rc3-review/key-a.pem`；未修改 fixture；未读取 `project-memory-mvp`。
