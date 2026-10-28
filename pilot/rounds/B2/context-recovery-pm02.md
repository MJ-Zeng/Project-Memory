# B2 冷启动恢复（PM-02）

- 会话角色：PM-02 Developer
- 工作区：`C:/Documents/02_Research/Code/project-memory-verification-lab/import-workspace/pm-pilot-02`
- 记录时间：2026-10-28T18:55+08:00

## 1. 六项事实

| # | 事实 | 值 | 依据 |
|---|---|---|---|
| 1 | 任务一句话 | B2：有效签名不得包裹伪造执行收据；把“内容完整性”与“执行真实性”分开，手写/自报 trusted 收据必须被拒 | `pilot/rounds/B2/task.md` §1–§2 |
| 2 | 基线 SHA | `587ac6a5024db3a6076a863876076d7fc7ecdd98`（= `origin/dev/v1.0` 当前 HEAD） | `git rev-parse` / `git rev-parse origin/dev/v1.0` |
| 3 | 允许修改范围 | `project_memory/{coordination,execution,authority}.py`、`tests/`、`docs/decisions/`、`pilot/evidence/B2/`、`pilot/rounds/B2/handoff-*`、`pilot/kit/b2/`（仅 fixture 说明） | 任务卡 §3 |
| 4 | 验收标准编号 | AC-1 … AC-11（AC-1 手写 trusted=false 拒绝；AC-2 谎报 trusted=true 拒绝；AC-3 可验证 attestation 接受；AC-4 本地未受信默认拒绝/仅人类例外；AC-5 来源绑定；AC-6 回归；AC-7 无新绕过；AC-8 ADR；AC-9 证据；AC-10 独立复现；AC-11 范围纪律） | 任务卡 §5 |
| 5 | 当前分支状态 | `dev/v1.0`，工作树干净，与 `origin/dev/v1.0` 同步；尚未创建 `fix/b2-receipt-provenance` | `git status --short --branch` |
| 6 | 下一步 | 写 `docs/decisions/ADR-0003-*`，创建候选分支，实现执行来源门禁与单元测试 | 任务卡 §3–§5 |

## 2. 恢复耗时

- 会话开始 → 写完本文件：约 **8 分钟**（首次只读恢复 + 环境校验）。

## 3. 无法从工件确认、必须询问的问题

1. Issue #12 的正文内容无法用本机现有凭据独立读取（本机无 `gh`，无 `GITHUB_TOKEN`/`GH_TOKEN`）。当前只能确认：派发 Handoff 记录了 Issue URL 与任务卡 SHA-256，且该 SHA-256 与仓库内任务卡一致。未发现冲突，因此不作为阻塞。

## 4. 污染记录（contamination）

- `human_relay`: 无。用户消息只包含启动提示词与工件路径，未转述工件之外的修复思路或审查结论。
- `unauthorized_reads`: 无。未读取 PM-01/PM-03 的聊天、终端历史或工作树。
- `missing_artifacts`: `pilot/kit/b2/` 仅有 README，签名 fixture 尚未生成（任务卡已预期，不阻塞静态设计与单元测试）。
- `stale_artifacts`: 未发现。

## 5. 开工前检查结果

| 检查 | 结果 |
|---|---|
| `git remote -v` | `origin git@github.com:MJ-Zeng/Project-Memory.git` |
| 工作树 | 干净 |
| 基线可解析 | 是，`587ac6a…` = `origin/dev/v1.0` |
| 任务卡 SHA-256 | `3617dab0…a7900e`，与派发记录一致 |
| Windows Python | 3.12.4（`C:\SoftWare\Anconda\python.exe`） |
| pytest | 9.1.1；`--collect-only` 收集 192 项（= 190 passed + 2 skipped） |
| WSL | Ubuntu，`python3` 3.14.4 |
| B2 fixture | 未生成（预期） |
