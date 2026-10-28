# B1 冷启动上下文恢复 — PM-02

- 会话：PM-02 Developer（独立 Clone `pm-pilot-02`）
- 首次命令时间：2026-10-28T13:31+08:00（`git remote -v`）
- 本文件写完时间：2026-10-28T13:41+08:00
- **接手用时（会话开始 → 正确复述 6 项事实）：约 10 分钟**
- 恢复来源：仅仓库工件 + `git`（Issue #1 的 URL/SHA 由启动提示词与 `pilot/STATUS.md` 提供，未访问浏览器）

## 1. 六项事实

| # | 事实 | 值 | 来源工件 |
|---|---|---|---|
| 1 | 任务一句话 | 让签名验证器不再由 `PATH`/`PROJECT_MEMORY_OPENSSL` 决定，伪造签名无法被接受，同时人类预签的有效签名仍能通过 | `pilot/rounds/B1/task.md` §1；`pilot/reference/RC3_B1_B3.md` B1 |
| 2 | 基线 SHA | `25a919d63c7181fd4083e0fc1af33734d74c5515`（= `origin/dev/v1.0` 当前 tip，含 `pilot/kit/b1/positive/` fixture）；冻结参照 `0d08a1ad85144d11a46d6a361a2a3ce4eadbbed4` | 派发 Issue #1；`git merge-base --is-ancestor` 验证；`pilot/STATUS.md` |
| 3 | 允许修改范围 | `project_memory/authority.py`；`tests/test_security_rc3.py` 或新增 `tests/test_authority_verifier.py`；`docs/` 的 ADR/security note；必要的错误消息/帮助文本；`pilot/evidence/B1/`、`pilot/rounds/B1/handoff-*`、`context-recovery-*` | `task.md` §3 |
| 4 | 验收标准编号 | AC-1..AC-11（AC-1 正向签名、AC-2..4 探针三种替换、AC-5 打印 `Verified OK` 的假验签器、AC-6 身份固定/fail closed、AC-7 攻击链不到 `achieved`、AC-8 回归、AC-9 无新绕过、AC-10 ADR、AC-11 范围纪律）；防作弊 8 条 | `task.md` §4、§5 |
| 5 | 当前分支状态 | 已按 §3 从基线新建 `fix/b1-openssl-verifier`（工作树 = `25a919d`，干净）；上轮分支 `fix/b0-repo-identity` 保持原样未动 | `git status --short --branch` |
| 6 | 下一步 | 先写 ADR（信任根、被拒方案、残余风险、验签器校验/轮换），再把 `authority._verify_signature` 改为不依赖外部二进制的进程内实现，补负向测试，跑探针与正向 fixture，产出证据包 + Handoff | `task.md` §3/§8；`handoff-dispatch.md` §6 |

任务卡冻结校验：`git cat-file -p 25a919d:pilot/rounds/B1/task.md | sha256sum` =
`0fdc9469456b81bae26a3c29385f1745222e16b19211e27d4d04a418ef3be08d`，与 Issue #1、`criteria.sha256`、
`handoff-dispatch.md`、`dispatch-b1-r1.json` 一致。

## 2. 根因（我自己的读法，非转述）

- `_openssl()`：`os.environ.get('PROJECT_MEMORY_OPENSSL') or 'openssl'` → `shutil.which()`，验证器完全由调用者环境决定。
- `_verify_signature()`：只看 `subprocess.run([... 'dgst','-verify' ...]).returncode`，`exit 0` 即判签名有效。
- 两者叠加 ⇒ `/bin/true`、PATH 前置假 `openssl` 都能让伪造记录变 `trusted`，进而驱动 Goal 到 `achieved`。
- 同一类弱点还存在于信任根检查本身：`_windows_owner()` 用裸 `powershell.exe`（靠 `PATH` 解析），并用 `USERNAME`/`USER` 环境变量当身份来源。

## 3. 需要问人的问题（工件无法确认）

- 无阻塞性问题。启动提示词已给 Issue URL、基线 SHA、SHA-256 与推送授权；`pilot/kit/b1/positive/` 与 `/etc/pm-rc3-review/`（root 持有的 anchor/pub）在本机可用。
- 记录一个已知的工件内部不一致（不阻塞，已在 Handoff 里披露）：`task.md` §4 AC-8 与 Issue 写「147 项既有测试」，`pilot/STATUS.md` 记录的基线是「164 passed / 2 skipped」。我按实测基线数为准，不删改任何测试。

## 4. 污染记录

- contamination：**无**。没有 PM-01/PM-03 转述的工件外信息；未读它们的会话、终端历史或工作树。
- 启动提示词本身是 PM-01 派发工件的复制品，其中的 Issue URL、基线 SHA、SHA-256、`AUTHORIZED_PUSH=yes` 均已在 `pilot/rounds/B1/*` 与 `pilot/STATUS.md` 内独立核对一致。
