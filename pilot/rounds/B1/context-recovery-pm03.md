# B1 冷启动上下文恢复 — PM-03

- 会话：PM-03 Independent Reviewer（独立 Clone `pm-pilot-03`）
- 首次命令时间：2026-10-28T17:5x+08:00（`git status` / `git rev-parse`）
- 本文件写完时间：2026-10-28T18:03+08:00
- **接手用时（会话开始 → 正确复述 6 项事实）：约 9 分钟**
- 恢复来源：仅仓库工件（`pilot/README.md`..`handoff-*`、ADR-0002、`STATUS.md`）+ 本机 `git`；未读 PM-01/PM-02 的聊天、终端历史或工作树。

## 1. 六项事实

| # | 事实 | 值 | 来源工件 / 我的核对 |
|---|---|---|---|
| 1 | 任务一句话 | 让签名验证器不再由 `PATH`/`PROJECT_MEMORY_OPENSSL` 决定，伪造签名无法被接受，同时人类预签的有效签名仍能通过 | `pilot/rounds/B1/task.md` §1；`pilot/reference/RC3_B1_B3.md` B1 |
| 2 | 基线 SHA | `25a919d63c7181fd4083e0fc1af33734d74c5515`；冻结参照 `0d08a1ad85144d11a46d6a361a2a3ce4eadbbed4` | 我执行 `git rev-parse` 复核一致 |
| 3 | 候选 / 分支头 | 候选 `1c7ad94f8c3beb369f4a86a33accda6910213105`；分支头 `216f154da797a2e5c295e01f11429978796aa7c7`（= 候选 + 仅两个 Handoff 文件） | 我执行 `git rev-parse` 与 `git diff --name-status 1c7ad94 216f154` 复核 |
| 4 | 判据编号 | AC-1..AC-11；防作弊 8 条；AC-8 任务卡写“147”与实测基线不一致（见 §3） | `task.md` §4/§5；`sha256sum` 复核任务卡哈希 |
| 5 | PM-02 声明（self-claimed，未采信） | 进程内 RSA/ECDSA 标准库验签；probe 修复后三种替换全拒绝、control/agent-anchor 仍拒；正向 fixture exit 0；回归 190 passed / 2 skipped（基线 164/2）；chain 停在 `goal evidence`（exit 1→`achieved` exit 1，Goal=`evaluating`） | Handoff JSON `.project-memory/handoffs/B1/run-20261028T1344.json`、`handoff-run-20261028T1344.md`（JSON 为准） |
| 6 | 下一步 | 我独立复现：静态审查 diff → 原始探针 before/after → 自建 AC-7 链 → 自建 AC-5 假验签器 → 正向 fixture → 全量回归 → 至少一条新绕过 → 写 REPORT 与证据 | `task.md` §4/§8；本提示词 §3–§6 |

任务卡冻结校验（我在工作区执行）：`sha256sum pilot/rounds/B1/task.md` =
`0fdc9469456b81bae26a3c29385f1745222e16b19211e27d4d04a418ef3be08d`，与派发工件一致。
探针取自基线树：`sha256sum .pilot/b1-base/pilot/kit/b1/openssl_substitution.py` =
`827ad0c29d50cd15ce345485d24e5a75edf069522c89b048236c08ba9e617c73`，与 `pilot/kit/b1/README.md` 一致。

## 2. 我自己的根因读法（非转述）

- `_openssl()` = `shutil.which(os.environ.get('PROJECT_MEMORY_OPENSSL') or 'openssl')`；验签器由调用者环境决定。
- `_verify_signature()` 只看子进程 `returncode`，`exit 0` 即“签名有效”。
- 同族弱点：`_windows_owner()` 经 `subprocess` 调裸名 `powershell.exe`，并用 `USERNAME`/`USER` 当身份来源。

## 3. 必须询问 / 已记录的工件内偏差

- 阻塞性问题：无（Issue #1 URL、基线、SHA-256、推送授权、`/etc/pm-rc3-review/` root 锚点均可用）。
- 已知偏差（不阻塞，不修改任务卡）：
  1. `task.md` AC-8 与 Issue 写“147 项既有测试”，实测基线为 164 passed / 2 skipped（`pilot/STATUS.md` 亦记 147 collected 为旧值）。按实测基线判定。
  2. `pilot/STATUS.md` 仍是 `B1 blocked_by_B0` 的过期快照，未反映本轮候选；按提示词视为过期工件，不单独构成 FAIL。
  3. PR 未开（PM-02 环境无 gh；ROLES §4 不允许 PM-01 代开 B1 PR）。记为 `missing_artifacts`，不构成 FAIL。

## 4. 污染记录

- contamination：**无**。未读 PM-01/PM-02 的会话、终端历史或工作树；未读 `/etc/pm-rc3-review/key-*.pem`；未使用 `project-memory-mvp` 或 `pm-import`。
- 本提示词由 PM-01 填写，属派发工件复制品；其中 SHA/哈希/授权我已用 `git` 与 `sha256sum` 独立核对一致。
- 相邻只读：读取了 PM-02 提交进仓库的 Handoff / context-recovery / evidence（属于允许的“仓库工件”，但不是“用其日志代替我自己的复现”）。
